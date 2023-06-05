import json
import aiohttp
from aiohttp import web
import asyncio

class WebServer:
    def __init__(self):
        self.connected_clients: set[web.WebSocketResponse] = set()
        self.cached_result = None
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

    async def send_to_client(self, socket: web.WebSocketResponse, message):
        try:
            await socket.send_json(message)
        except Exception as e:
            print(f'Error sending to client: {e}')

    async def send_state(self, data, cache=True):
        if cache:
            self.cached_result = data
        await asyncio.gather(*[self.send_to_client(ws, data) for ws in self.connected_clients])

    async def index(self, request):
        return web.FileResponse('/app/index.html')

    async def websocket_handler(self, request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        print(f'WebSocket connection with {request.remote} ({" ".join(request.headers["User-Agent"].split()[-2:])}) opened')

        # Send initial cached data
        if self.cached_result:
            await self.send_to_client(ws, self.cached_result)
        self.connected_clients.add(ws)

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                print(f'{request.remote}: {msg.data}')
                if msg.data == 'close':
                    await ws.close()
                inmsg = json.loads(msg.data)
                if inmsg['id'] and self.pending_input:
                    self.pending_input.set_result(inmsg['message'])
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f'WebSocket connection with {request.remote} closed with exception {ws.exception()}')
        self.connected_clients.remove(ws)
        print(f'WebSocket connection with {request.remote} closed')
        return ws
