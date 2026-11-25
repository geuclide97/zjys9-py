# -*- coding: utf-8 -*-
# 点歌台 Spider（UI9 / 影视猫）
# 数据源：GD音乐台 music-api.gdstudio.xyz（与 LNSS 点歌同一接口），source=netease
import json
import sys
import time
import random
from urllib.parse import quote

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None

sys.path.append('..')
from base.spider import Spider

API = 'https://music-api.gdstudio.xyz/api.php'
UA = ('Mozilla/5.0 (Linux; Android 11; M2101K9C) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')


class Spider(Spider):
    name = '点歌台'

    def __init__(self):
        super().__init__()
        # ('榜单', 歌单id) 或 ('搜索', 关键词)
        self.categories = [
            ('热歌榜', 'pl', '3778678'),
            ('飙升榜', 'pl', '19723756'),
            ('原创榜', 'pl', '2884035'),
            ('华语经典', 'kw', '经典老歌'),
            ('粤语金曲', 'kw', '粤语经典'),
            ('抖音热歌', 'kw', '抖音热歌'),
            ('情歌对唱', 'kw', '情歌对唱'),
            ('怀旧金曲', 'kw', '怀旧金曲'),
            ('摇滚', 'kw', '摇滚'),
            ('民谣', 'kw', '民谣'),
            ('纯音乐', 'kw', '纯音乐'),
            ('DJ舞曲', 'kw', 'DJ舞曲'),
            ('儿歌', 'kw', '儿歌'),
            ('戏曲', 'kw', '戏曲'),
            ('英文歌', 'kw', '英文歌曲'),
            ('日韩', 'kw', '日语歌曲'),
        ]
        self.headers = {'User-Agent': UA, 'Referer': 'https://music.gdstudio.xyz/'}
        self._cache = {}

    def getName(self):
        return self.name

    def init(self, extend=''):
        self.extend = extend or ''

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False

    # ---------------- 接口 ----------------
    def _api(self, **params):
        if requests is None:
            return None
        params.setdefault('source', 'netease')
        key = json.dumps(params, sort_keys=True)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        for _ in range(2):
            try:
                r = requests.get(API, params=params, headers=self.headers, timeout=10, verify=False)
                txt = r.text.strip()
                if txt.startswith('[') or txt.startswith('{'):
                    data = json.loads(txt)
                    self._cache[key] = (time.time(), data)
                    return data
            except Exception:
                pass
            time.sleep(random.uniform(0.4, 0.9))
        return None

    @staticmethod
    def _artists(a):
        try:
            if isinstance(a, list):
                names = []
                for x in a:
                    if isinstance(x, dict):
                        names.append(x.get('name', ''))
                    else:
                        names.append(str(x))
                return '/'.join([n for n in names if n])
            if isinstance(a, dict):
                return a.get('name', '')
            return str(a or '')
        except Exception:
            return ''

    def _song_item(self, s, idx=0):
        sid = str(s.get('id') or s.get('url_id') or '')
        name = s.get('name') or '未知歌曲'
        ar = self._artists(s.get('ar') or s.get('artist'))
        pic = ''
        al = s.get('al') or {}
        if isinstance(al, dict) and al.get('picUrl'):
            pic = al['picUrl'].replace('http://', 'https://')
        elif s.get('pic'):
            pic = 'https://p2.music.126.net/%s/%s.jpg' % (s.get('pic_str', ''), s.get('pic'))
        return {
            'vod_id': '%s|%s' % (sid, quote(name)),
            'vod_name': name,
            'vod_pic': pic,
            'vod_remarks': ar,
            'vod_year': '',
            'type_name': '点歌',
        }

    # ---------------- 首页 / 分类 ----------------
    def homeContent(self, filter):
        classes = [{'type_id': str(i), 'type_name': n} for i, (n, _, _) in enumerate(self.categories)]
        first = self.categoryContent('0', 1, False, {})
        return {'class': classes, 'filters': {}, 'list': first.get('list', [])}

    def homeVideoContent(self):
        return {'list': self.categoryContent('0', 1, False, {}).get('list', [])}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            idx = int(tid or 0)
        except Exception:
            idx = 0
        pg = int(pg or 1)
        name, kind, arg = self.categories[idx % len(self.categories)]
        songs = []
        if kind == 'pl':
            data = self._api(types='playlist', id=arg)
            try:
                songs = (data or {}).get('playlist', {}).get('tracks') or []
            except Exception:
                songs = []
            if songs and pg == 1:
                songs = songs[:200]
        if not songs:
            data = self._api(types='search', name=arg)
            songs = data if isinstance(data, list) else []
        items = [self._song_item(s) for s in songs]
        per = 30
        start = (pg - 1) * per
        page_items = [x for x in items[start:start + per] if x['vod_name'] != '未知歌曲']
        total = max(len(items), 1)
        pagecount = max(1, (len(items) + per - 1) // per)
        return {'list': page_items, 'page': pg, 'pagecount': pagecount,
                'limit': per, 'total': total}

    # ---------------- 详情 ----------------
    def detailContent(self, ids):
        raw = str(ids[0])
        sid = raw.split('|')[0]
        title = raw.split('|')[1] if '|' in raw else ''
        try:
            from urllib.parse import unquote
            title = unquote(title)
        except Exception:
            pass
        content = '点歌：%s\n\n点「立即点歌」直接开始播放，支持 128/192/320 码率自适应。' % title
        vod = {
            'vod_id': raw,
            'vod_name': title or sid,
            'vod_pic': '',
            'type_name': '点歌',
            'vod_year': '',
            'vod_remarks': '点歌',
            'vod_content': content,
            'vod_play_from': '点歌台',
            'vod_play_url': '立即点歌$%s' % raw,
        }
        return {'list': [vod]}

    # ---------------- 搜索 ----------------
    def searchContent(self, key, quick, pg=1):
        data = self._api(types='search', name=key)
        songs = data if isinstance(data, list) else []
        items = [self._song_item(s) for s in songs]
        return {'list': items[:60], 'page': 1, 'pagecount': 1, 'limit': 60, 'total': len(items)}

    # ---------------- 播放 ----------------
    def playerContent(self, flag, id, vipFlags):
        sid = str(id).split('|')[0]
        for br in (320, 192, 128):
            d = self._api(types='url', id=sid, br=br) or {}
            u = d.get('url') or ''
            if u:
                return {'parse': 0, 'playUrl': '', 'url': u.replace('http://', 'https://'),
                        'header': {'User-Agent': UA, 'Referer': 'https://music.163.com/'}}
        return {'parse': 0, 'playUrl': '', 'url': '', 'header': {'User-Agent': UA}}
