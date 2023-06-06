import json
import aiohttp
from aiohttp import web
import asyncio

class Session:
    def __init__(self, ws: web.WebSocketResponse):
        self.ws: web.WebSocketResponse = ws
        self.agent = None
        self.task = None

    async def get_input(self, msg):
        self.pending_input = asyncio.get_running_loop().create_future()
        await self.send_state(msg, cache=True)
        return await self.pending_input

    async def send_to_client(self, message):
        try:
            await self.ws.send_json(message)
        except Exception as e:
            print(f'Error sending to client: {e}')

    async def send_state(self, data, cache=True):
        if cache:
            self.cached_result = data
        await self.send_to_client(data)

class WebServer:
    def __init__(self, args, add_agent):
        self.current_sessions: set[Session] = set()
        self.args = args
        self.add_agent = add_agent
        self.app = web.Application()
        self.app.add_routes([
            web.get('/', self.index),
            web.get('/ws', self.websocket_handler)
        ])
    
    async def run(self):
        await web._run_app(self.app)

    async def get_input(self, msg):
        self.pending_input = asyncio.get_running_loop().create_future()
        await self.send_state(msg, cache=True)
        return await self.pending_input

    async def index(self, request):
        return web.FileResponse('/app/index.html')

    async def websocket_handler(self, request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        print(f'WebSocket connection with {request.remote} ({" ".join(request.headers["User-Agent"].split()[-2:])}) opened')

        s = Session(ws)
        await self.add_agent(self.args, s)
        self.current_sessions.add(s)

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                print(f'{request.remote}: {msg.data}')
                if msg.data == 'close':
                    await ws.close()
                inmsg = json.loads(msg.data)
                if inmsg['id'] and s.pending_input:
                    s.pending_input.set_result(inmsg['message'])
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'WebSocket connection with {request.remote} closed with exception {ws.exception()}')
        self.current_sessions.remove(s)
        await s.agent.stop()
        if s.task:
            s.task.cancel()
        print(f'WebSocket connection with {request.remote} closed')
        return ws
