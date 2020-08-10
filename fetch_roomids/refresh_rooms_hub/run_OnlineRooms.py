import asyncio
from random import shuffle
from os import path

import rsa
from aiohttp import web

import utils
from tasks.utils import UtilsTask
from static_rooms import var_static_room_checker
from online_rooms import var_online_room_checker
from poster_rooms import var_poster_room_checker
from printer import info as print


loop = asyncio.get_event_loop()
ctrl = utils.read_toml(file_path='conf/ctrl.toml')
distributed_clients = ctrl['distributed_clients']
url_index = ctrl['url_index']


async def check_max_rooms_num():
    return 50000

max_rooms_num = loop.run_until_complete(check_max_rooms_num())
assert max_rooms_num > 0
print(f'MAX_ROOMS_NUM = {max_rooms_num}')


class OnlineRoomNotStaticCheckers:  # 在线房间，剔除静态的结果
    def __init__(self):
        var_online_room_checker.reset_max_rooms_num(max_rooms_num, url_index=url_index)
        self.online_room_checker = var_online_room_checker
        self.static_rooms = var_static_room_checker.rooms

    async def refresh_and_get_rooms(self):
        self.static_rooms = await var_static_room_checker.refresh()
        self.poster_rooms = await var_poster_room_checker.refresh()
        static_rooms = list(set(self.static_rooms+self.poster_rooms))
        rooms = await self.online_room_checker.get_rooms()
        return [i for i in rooms if i not in static_rooms]  # 过滤掉静态房间里面的

    def status(self) -> dict:
        return self.online_room_checker.status()


class WebServer:
    def __init__(self, admin_privkey: rsa.PrivateKey):
        self.rooms = []

        self.checker = OnlineRoomNotStaticCheckers()

        self.admin_privkey = admin_privkey
        self.max_remain_roomids = 0
        self.max_num_roomids = -1

    async def intro(self, _):
        data = {
            'code': 0,
            'version': '2.0.0b1',
            **self.checker.status(),
            'max_remain_roomids': self.max_remain_roomids,
            'max_num_roomids': self.max_num_roomids,
            'max_rooms_num': max_rooms_num
        }
        return web.json_response(data)

    async def check_index(self, request):
        roomid = request.match_info['roomid']
        try:
            roomid = int(roomid)
            code = 0
            if roomid in self.rooms:
                is_in = True
                index = self.rooms.index(roomid)
            else:
                is_in = False
                index = -1
        except ValueError:
            code = -1
            is_in = False
            index = -1

        data = {'code': code, 'is_in': is_in, 'index': index}

        return web.json_response(data)

    async def refresh_and_get_rooms(self):
        self.rooms = await self.checker.refresh_and_get_rooms()
        self.max_num_roomids = max(self.max_num_roomids, len(self.rooms))
        
    async def push_roomids(self) -> float:  # 休眠时间
        print('正在准备推送房间')
        shuffle(distributed_clients)
        print(f'有效房间 {len(self.rooms)}')        
        online_rooms = []
        if self.rooms:
            all_rooms = utils.request_json('GET',f'http://49.235.200.131:5001/room/v1/Room/room/all')['data']
            if all_rooms:
                online_rooms = list(set(self.rooms).difference(set(all_rooms)))
            if online_rooms:
                rsp = utils.request_json_once('POST',f'http://49.235.200.131:5001/room/v1/Room/room_init_list',json=online_rooms)
                print(len(online_rooms),rsp)
        return 300


async def init():
    key_path = f'{path.dirname(path.realpath(__file__))}/key'
    with open(f'{key_path}/admin_privkey.pem', 'rb') as f:
        admin_privkey = rsa.PrivateKey.load_pkcs1(f.read())

    app = web.Application()
    webserver = WebServer(admin_privkey)
    app.router.add_get('/', webserver.intro)
    app.router.add_get('/is_in/{roomid}', webserver.check_index)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 9100)
    await site.start()

    wanted_time = 0
    while True:
        await webserver.refresh_and_get_rooms()
        await asyncio.sleep(wanted_time-utils.curr_time()+3)
        wanted_time = utils.curr_time() + await webserver.push_roomids()
        await asyncio.sleep(2)


loop.run_until_complete(init())
loop.run_forever()
