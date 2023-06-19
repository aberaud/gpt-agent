import base64
import copy
import json
import aiohttp
from aiohttp import web
import asyncio
from cryptography import fernet

import aiohttp_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage

class Session:
    def __init__(self, req: web.Request, ws: web.WebSocketResponse, session: aiohttp_session.Session):
        self.req = req
        self.session = session
        self.ws: web.WebSocketResponse = ws
        self.agent = None
        self.task = None
        self.state = None
    
    async def set_agent(self, agent, messages=[]):
        if self.agent is not None:
            await self.destroy_agent()
        self.state = {'model': agent.args.model, 'agents': {
            agent.name: {
                'id': agent.name,
                'messages': messages
            }
        }, 'state': 'idle'}
        self.agent = agent

    async def remove_agent(self):
        if self.agent:
            await self.agent.stop()
        if self.task:
            self.task.cancel()
            self.task = None
        self.agent = None

    def update(self, req: web.Request, ws: web.WebSocketResponse):
        self.req = req
        self.ws = ws

    async def set_property(self, key, value):
        self.state[key] = value
        await self.send_to_client({key: value})

    async def set_state(self, id, state, usage: dict | None = None):
        self.state['state'] = state
        if usage is not None:
            self.state['usage'] = usage
        await self.send_to_client({'state': state, 'id': id})

    async def get_input(self, id, message):
        self.pending_input = asyncio.get_running_loop().create_future()
        old_state = self.state['state']
        self.state['state'] = 'request'
        self.state['id'] = id
        self.state['message'] = message
        await self.send_to_client({
            'state': 'request',
            'id': id,
            'message': message
        })
        r = await self.pending_input
        self.state['state'] = old_state
        del self.state['id']
        del self.state['message']
        await self.send_to_client({
            'state': old_state,
            'id': id
        })
        return r

    async def send_to_client(self, message):
        if self.ws is not None:
            try:
                await self.ws.send_json(message)
            except Exception as e:
                print(f'Error sending to client: {e}')
        else:
            print('No websocket connected')

    async def send_init_state(self):
        await self.send_to_client(self.state)
    
    async def add_message(self, id: str, data: dict, usage: dict):
        self.state['usage'] = usage
        agent = self.state['agents'].get(id)
        if agent is None:
            agent = self.state['agents'][id] = {'id': id, 'messages': []}
        agent['messages'].append(data)
        await self.send_to_client({'state': 'message', 'id': id, 'message': data, 'usage': usage})

class WebServer:
    def __init__(self, args, add_agent):
        self.current_sessions: dict[str, Session] = dict()
        self.args = args
        self.add_agent = add_agent
        self.app = web.Application()
        self.index_content = open('/app/index.html', 'r').read()
        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        jar = EncryptedCookieStorage(secret_key)
        # jar = aiohttp_session
        aiohttp_session.setup(self.app, jar)
        self.app.add_routes([
            web.get('/', self.index),
            web.get('/ws', self.websocket_handler)
        ])
    
    async def run(self):
        await web._run_app(self.app)

    async def index(self, request):
        session = await aiohttp_session.get_session(request)
        if session.new:
            session['hits'] = 0
            session['id'] = str(id(session))
            session.set_new_identity(session['id'])
        session['hits'] += 1
        session.changed()
        return web.Response(body=self.index_content, content_type='text/html')

    async def websocket_handler(self, request: web.Request):
        session = await aiohttp_session.get_session(request)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        print(f'WebSocket connection with {request.remote} ({" ".join(request.headers["User-Agent"].split()[-2:])}) opened')

        # id = str(id(session))
        sid = session.get('id', str(id(session)))
        s = self.current_sessions.get(sid)
        if not s:
            s = Session(request, ws, session)
            self.current_sessions[sid] = s
            await self.add_agent(self.args, s)
        else:
            s.update(request, ws)
            await s.send_init_state()

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                print(f'{request.remote}: {msg.data}')
                if msg.data == 'close':
                    await ws.close()
                inmsg = json.loads(msg.data)
                if inmsg.get('restart'):
                    print('Restarting agent')
                    model=inmsg.get('model')
                    if model:
                        self.args.model = model
                    await s.remove_agent()
                    await self.add_agent(self.args, s)
                elif inmsg['id'] and s.pending_input:
                    s.pending_input.set_result(inmsg['message'])
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'WebSocket connection with {request.remote} closed with exception {ws.exception()}')

        # del self.current_sessions[sid]
        # await s.agent.stop()
        # if s.task:
        #     s.task.cancel()
        s.update(None, None)
    
        print(f'WebSocket connection with {request.remote} closed')
        return ws
