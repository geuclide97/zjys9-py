# -*- coding: utf-8 -*-
"""抖音网页短剧 TVBox 接口（蜜果盒子-http://6i.pw/）。"""

import base64
import json
import random
import sys
import time
from urllib.parse import urlencode

import requests

sys.path.append('..')
from base.spider import Spider as BaseSpider


UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/130.0.0.0 Safari/537.36')

class Spider(BaseSpider):
    HOST = 'https://www.douyin.com'
    API = HOST + '/aweme/v1/web'
    COMMON = {'device_platform': 'webapp', 'aid': '6383',
              'channel': 'channel_pc_web'}
    CATEGORIES = (
        ('推荐', 'recommend'), ('热榜', 'hot'), ('榜单', '1'),
        ('爱情', '1940'), ('剧情', '1957'), ('逆袭', '1944'),
        ('反转', '2092'), ('亲情', '1941'), ('恩怨', '2091'),
        ('玄幻', '1946'), ('奇幻', '1945'), ('古装', '1958'),
        ('悬疑', '1950'), ('友情', '1942'), ('喜剧', '1956'),
        ('犯罪', '2088'), ('惊悚', '1951'), ('青春', '1943'),
        ('科幻', '1947'), ('仙侠', '1948'), ('其他', '1959'),
    )

    def __init__(self):
        super(Spider, self).__init__()
        self.session = None
        self.cache = {}
        self.webid = str(random.SystemRandom().randint(7000000000000000000,
                                                       7999999999999999999))
        self.protected_ready = False

    def init(self, extend=''):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': UA,
            'Referer': self.HOST + '/series',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        ext = self._parse_ext(extend)
        if ext.get('cookie'):
            self.session.headers['Cookie'] = str(ext['cookie'])

    def getName(self):
        return '抖音短剧'

    def destroy(self):
        if self.session:
            self.session.close()

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        return {
            'class': [{'type_name': name, 'type_id': tid}
                      for name, tid in self.CATEGORIES],
            'filters': {},
        }

    def homeVideoContent(self):
        return {'list': self._category('recommend', 1).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        return self._category(str(tid), self._int(pg, 1))

    def detailContent(self, ids):
        series_id = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        detail = self._get('/series/detail/', {
            'series_id': series_id, 'req_from': 'channel_pc_web'
        })
        info = detail.get('series_info') or {}
        episodes = self._episodes(series_id, info)
        if not info and not episodes:
            return {'list': []}
        stats = info.get('stats') or {}
        cover = self._image(info.get('cover_url'))
        name = info.get('series_name') or series_id
        actor_names = [x.get('name', '') for x in (info.get('actors') or [])
                       if isinstance(x, dict)]
        play_items = []
        for index, item in enumerate(episodes, 1):
            ep = self._episode_number(item, index)
            payload = self._play_payload(item)
            if payload:
                play_items.append('%s$%s' % (ep, payload))
        vod = {
            'vod_id': series_id,
            'vod_name': name,
            'vod_pic': cover,
            'type_name': self._type_names(info),
            'vod_remarks': self._status_text(info),
            'vod_year': '',
            'vod_area': '中国大陆',
            'vod_actor': ','.join(actor_names),
            'vod_director': '',
            'vod_content': info.get('desc') or '',
            'vod_play_from': '抖音短剧',
            'vod_play_url': '#'.join(play_items),
        }
        if not play_items:
            vod['vod_remarks'] = '暂未取得分集播放地址'
        return {'list': [vod]}

    def searchContent(self, key, quick, pg='1'):
        return {'list': []}

    def playerContent(self, flag, pid, vipFlags):
        try:
            raw = base64.urlsafe_b64decode(str(pid) + '=' * (-len(str(pid)) % 4))
            data = json.loads(raw.decode('utf-8'))
            urls = data.get('urls') or []
            url = next((x for x in urls if str(x).startswith('http')), '')
        except Exception:
            url = str(pid)
        return {
            'parse': 0,
            'url': url,
            'header': {'User-Agent': UA, 'Referer': self.HOST + '/'},
        }

    def localProxy(self, param):
        return [404, 'text/plain', 'not found']

    def _category(self, tid, page):
        count = 16
        if tid == 'hot':
            data = self._get('/series/hot/list/', {'count': 100})
            raw_list = data.get('series_infos') or []
            has_more = False
        else:
            params = {'offset': (page - 1) * count, 'count': count}
            if tid not in ('recommend', ''):
                params['content_type'] = self._int(tid, 0)
            data = self._get('/series/card/feed/', params)
            raw_list = [(x or {}).get('series') for x in
                        (data.get('card_list') or [])]
            raw_list = [x for x in raw_list if isinstance(x, dict)]
            has_more = bool(data.get('has_more'))
        videos = [self._video(x) for x in raw_list if isinstance(x, dict)]
        videos = [x for x in videos if x.get('vod_id')]
        return {
            'list': videos, 'page': page,
            'pagecount': page + 1 if has_more else page,
            'limit': count, 'total': page * count + (count if has_more else 0),
        }

    def _episodes(self, series_id, info):
        cached = self.cache.get('ep:' + series_id)
        if cached and time.time() - cached[0] < 300:
            return cached[1]
        result, cursor = [], 0
        total = self._int((info.get('stats') or {}).get('total_episode'), 0)
        for _ in range(3):
            data = self._get('/series/aweme/', {
                'series_id': series_id, 'pull_type': 2,
                'cursor': cursor, 'count': 100,
            }, signed=True)
            chunk = data.get('aweme_list') or []
            if not isinstance(chunk, list) or not chunk:
                break
            result.extend(chunk)
            next_cursor = self._int(data.get('max_cursor'), cursor + len(chunk))
            if not data.get('has_more') or next_cursor <= cursor:
                break
            cursor = next_cursor
            if total and len(result) >= total:
                break
        self.cache['ep:' + series_id] = (time.time(), result)
        return result

    def _get(self, path, params, signed=False):
        query_params = dict(self.COMMON)
        query_params.update(params or {})
        if signed:
            self._ensure_protected_session()
            # 网页实际请求所用参数。配合官方 ttwid 注册回调即可通过分集
            # 接口校验，比逐次计算 A-Bogus 更快，也更适合电视端。
            query_params.update({
                'cookie_enabled': 'true',
                'screen_width': 1920, 'screen_height': 1080,
                'browser_language': 'zh-CN',
                'browser_platform': 'Win32',
                'browser_name': 'Chrome', 'browser_version': '130.0.0.0',
                'browser_online': 'true',
                'engine_name': 'Blink', 'engine_version': '130.0.0.0',
                'os_name': 'Windows', 'os_version': '10',
                'cpu_core_num': 8, 'device_memory': 8,
                'platform': 'PC', 'downlink': 10,
                'effective_type': '4g', 'round_trip_time': 50,
                'version_code': '170400', 'version_name': '17.4.0',
                'webid': self.webid, 'update_version_code': '170400',
                'pc_client_type': 1, 'pc_libra_divert': 'Windows',
                'support_h265': 0, 'support_dash': 0,
            })
        query = urlencode(query_params)
        try:
            response = self.session.get(self.API + path + '?' + query,
                                        timeout=(5, 15))
            if response.status_code == 200 and response.text != 'blocked':
                return response.json()
        except Exception:
            pass
        return {}

    def _ensure_protected_session(self):
        if self.protected_ready:
            return
        body = {
            'region': 'cn', 'aid': 6383, 'needFid': False,
            'service': 'www.douyin.com',
            'migrate_info': {'ticket': '', 'source': 'node'},
            'cbUrlProtocol': 'https', 'union': True,
        }
        try:
            response = self.session.post(
                'https://ttwid.bytedance.com/ttwid/union/register/',
                json=body, timeout=(5, 10))
            callback = (response.json() or {}).get('redirect_url')
            if callback:
                self.session.get(callback, timeout=(5, 10))
            self.protected_ready = bool(self.session.cookies.get('ttwid'))
        except Exception:
            self.protected_ready = False

    def _video(self, info):
        sid = str(info.get('series_id') or '')
        return {
            'vod_id': sid,
            'vod_name': info.get('series_name') or sid,
            'vod_pic': self._image(info.get('cover_url')),
            'vod_remarks': self._status_text(info),
        }

    def _play_payload(self, item):
        video = item.get('video') or {}
        candidates = []
        bit_rates = video.get('bit_rate') or []
        if isinstance(bit_rates, list):
            bit_rates = sorted(bit_rates, key=lambda x: self._int(
                (x or {}).get('bit_rate'), 0), reverse=True)
            for rate in bit_rates:
                candidates.extend(self._urls((rate or {}).get('play_addr')))
        candidates.extend(self._urls(video.get('play_addr')))
        candidates.extend(self._urls(video.get('play_addr_265')))
        unique = list(dict.fromkeys(x for x in candidates if x))
        if not unique:
            return ''
        raw = json.dumps({'urls': unique}, ensure_ascii=False,
                         separators=(',', ':')).encode('utf-8')
        return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

    @staticmethod
    def _urls(value):
        if isinstance(value, dict):
            value = value.get('url_list') or value.get('urlList') or []
        if isinstance(value, str):
            return [value]
        return [str(x) for x in (value or []) if x]

    @classmethod
    def _image(cls, value):
        urls = cls._urls(value)
        return urls[0] if urls else ''

    @staticmethod
    def _episode_number(item, fallback):
        info = item.get('series_info') or {}
        stats = info.get('stats') or {}
        number = (stats.get('current_episode') or info.get('current_episode')
                  or item.get('episode') or fallback)
        return '第%s集' % number

    @staticmethod
    def _type_names(info):
        values = info.get('series_content_types_new') or info.get('series_content_types') or []
        return '/'.join(str(x.get('name')) for x in values
                        if isinstance(x, dict) and x.get('name'))

    @staticmethod
    def _status_text(info):
        status = info.get('status') or {}
        if isinstance(status, dict) and status.get('status_desc'):
            return status['status_desc']
        stats = info.get('stats') or {}
        total = stats.get('total_episode') or info.get('total_episode')
        return ('%s集全' % total) if total else ''

    @staticmethod
    def _int(value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _parse_ext(extend):
        if isinstance(extend, dict):
            return extend
        getter = getattr(extend, 'get', None)
        if callable(getter):
            try:
                cookie = getter('cookie')
                return {'cookie': str(cookie)} if cookie else {}
            except Exception:
                pass
        try:
            text = str(extend or '').strip()
            value = json.loads(text) if text.startswith('{') else {}
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
