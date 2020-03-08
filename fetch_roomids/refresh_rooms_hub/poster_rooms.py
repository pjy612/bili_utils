# rank api搜索，无限后台循环
from typing import Dict
import asyncio
from itertools import zip_longest

import attr

from tasks.utils import UtilsTask
import utils
from static_rooms import var_static_room_checker
from refresher import Refresher


@attr.s(slots=True)
class PosterRoom:
    # 保持有效的时间
    DELAY = 3600 * 24 * 7

    real_roomid = attr.ib(validator=attr.validators.instance_of(int))
    latest_time = attr.ib(default=0, validator=attr.validators.instance_of(int))

    @property
    def weight(self) -> int:
        curr_time = utils.curr_time()
        weight = 0
        if self.latest_time + self.DELAY > curr_time:
            weight += self.latest_time
        return weight

    def update(self):
        self.latest_time = utils.curr_time()


class PosterRoomChecker(Refresher):
    NAME = 'POSTER'

    def __init__(self):
        self.urls = []        
        self.latest_refresh = ''
        self.latest_refresh_poster_num = []
        self.list_poster_rooms = []
        self.static_rooms = var_static_room_checker.rooms

    def add2rooms(self, real_roomid: int):
        if real_roomid in self.static_rooms:
            return
        # print(f'正在刷新{real_roomid}（未存在于静态房间）')
        if real_roomid not in self.list_poster_rooms:
            self.list_poster_rooms.append(real_roomid)
        
    def status(self) -> dict:
        return {
            'poster_rooms_latest_refresh': self.latest_refresh,
            'poster_realtime': len(self.list_poster_rooms)
        }
    
    async def refresh(self):
        latest_refresh_start = utils.timestamp()
        roomlists = await UtilsTask.fetch_poster_rooms()
        for real_roomid in roomlists:
            self.add2rooms(real_roomid)
        latest_refresh_end = utils.timestamp()
        self.latest_refresh = f'{latest_refresh_start} to {latest_refresh_end}'
        rooms = self.list_poster_rooms
        assert len(rooms) == len(set(rooms))
        return rooms


var_poster_room_checker = PosterRoomChecker()
