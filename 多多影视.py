# -*- coding: utf-8 -*-
"""
DDTV dduotv UI9专用Python爬虫
保留原版protobuf/签名解密逻辑，参考枫叶UI9模板结构改造，可直接粘贴使用
依赖：无，不需要pycryptodome
UI9配置JSON：
{
  "key": "ddtv_py",
  "name": "DDTV",
  "type": 3,
  "api": "./py/ddtv.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 0
}
"""
import json
import re
import sys
import time
import base64
import hashlib
import urllib.request
import urllib.parse
# 依赖容错降级
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass
# ==================== 常量定义（原版DDTV不动） ====================
HOSTS = ['https://323433ssdfd.top', 'https://duoduosdf12223234334.top', 'https://xds2435u23422342342u.top', 'https://dduotv01.top']
F = 'WF-2c064bc5b3400788f31b848849bc3a60f835423ba2dfe69d7ea93974c216e4f2'
SK = 'WEB-50a8e9c84a1dc05669a692ded99a2dac46527229e607a7be15db88dbc59059d1'
ID = 'com.web.player'
W = 'ddtvf65f3a83d6d9ad6f'
XC = '8f3d2a1c7b6e5d4c9a0b1f2e3d4c5b6a'
CATEGORIES = [{'type_id': '1', 'type_name': '电影'}, {'type_id': '2', 'type_name': '剧集'}, {'type_id': '3', 'type_name': '动漫'}, {'type_id': '4', 'type_name': '综艺'}]
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36'

# ==================== Protobuf 工具函数（原版DDTV不动） ====================
def _vint(n):
    out = b''
    while True:
        b = n & 0x7f
        n >>= 7
        if n:
            out += bytes([b | 0x80])
        else:
            out += bytes([b])
            break
    return out

def _pb(url, vf, ts):
    sig = hashlib.sha256(('finger=%s&id=%s&nonce=%s&sk=%s&time=%s&v=1' % (F, ID, '0' * 32, SK, ts)).encode()).hexdigest().upper()
    b = b'\x0a' + _vint(len(url)) + url.encode()
    b += b'\x12' + _vint(len(vf)) + vf.encode()
    b += b'\x18' + _vint(ts)
    b += b'\x22' + _vint(32) + b'0' * 32
    b += b'\x2a' + _vint(64) + sig.encode()
    b += b'\x32' + _vint(14) + b'com.web.player'
    b += b'\x38\x01'
    return b

def _parse_pb(b):
    i, fields = 0, {}
    while i < len(b):
        tag = b[i]; i += 1
        f = tag >> 3; w = tag & 7
        if w == 0:
            v = 0; s = 0
            while True:
                x = b[i]; i += 1
                v |= (x & 0x7f) << s
                if not x & 0x80: break
                s += 7
            fields[f] = v
        elif w == 2:
            ln = 0; s2 = 0
            while True:
                x = b[i]; i += 1
                ln |= (x & 0x7f) << s2
                if not x & 0x80: break
                s2 += 7
            fields[f] = b[i:i + ln].decode('utf-8', errors='replace')
            i += ln
        elif w == 5:
            i += 4
    return fields

class Spider(BaseSpider):
    # UI9默认扩展配置，后台extend可JSON覆盖（枫叶模板风格）
    DEFAULT_EXT = {
        "host_idx": 0,
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
    }
    def getName(self):
        return "DDTV"
    def init(self, extend=""):
        # 加载扩展配置（完全对齐枫叶init写法）
        self.ext = dict(self.DEFAULT_EXT)
        if isinstance(extend, dict):
            self.ext.update(extend)
        elif isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict):
                    self.ext.update(cfg)
            except Exception:
                pass
        self.host_idx = int(self.ext.get("host_idx",0))
        self.host = HOSTS[self.host_idx].rstrip("/")
        self.ua = self.ext["ua"]
        self.h = {'web-sign': W, 'X-Client': XC, 'User-Agent': self.ua}

    # ===================== UI9通用工具（枫叶模板工具函数） =====================
    def _ensure_runtime(self):
        pass
    def _http(self, url, data=None, headers=None):
        req = urllib.request.Request(url, data=data, headers=headers or {})
        import ssl
        ctx = ssl._create_unverified_context()
        return urllib.request.urlopen(req, timeout=25, context=ctx).read()
    @staticmethod
    def _safe_json(text, default=None):
        try:
            return json.loads(text)
        except Exception:
            return default if default is not None else {}
    def _video_item(self, item):
        if not isinstance(item, dict):
            return {}
        return {
            "vod_id": item.get("vod_id", ""),
            "vod_name": item.get("vod_name", ""),
            "vod_pic": item.get("vod_pic", ""),
            "vod_remarks": item.get("vod_remarks", "")
        }
    @staticmethod
    def _fix_pic(img_url):
        if not img_url:
            return ""
        if img_url.startswith("//"):
            return f"https:{img_url}"
        return img_url.replace("&amp;", "&")
    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(m3u8|mp4|mkv|ts|flv)(\?|$)", str(url)))
    def manualVideoCheck(self):
        return False

    # ==================== 网络请求 + 多HOST轮询（原版DDTV逻辑保留） ====================
    def _fetch(self, url, params=None, headers=None, data=None, method='GET'):
        for host in HOSTS:
            u = url.replace(HOSTS[0], host, 1) if HOSTS[0] in url else url
            try:
                if params:
                    u += ('&' if '?' in u else '?') + '&'.join('%s=%s' % (k, urllib.parse.quote(str(v))) for k, v in params.items())
                req = urllib.request.Request(u, data=data, headers=headers or {})
                import ssl
                ctx = ssl._create_unverified_context()
                r = urllib.request.urlopen(req, timeout=6, context=ctx)
                return r.read()
            except Exception:
                continue
        return b''

    def _get(self, path, params=None):
        for _ in range(2):
            r = self._fetch(self.host + path, params=params, headers=self.h)
            if r:
                try:
                    return json.loads(r)
                except Exception:
                    pass
            time.sleep(0.3)
        return {}

    # ===================== UI9标准入口方法（严格对齐枫叶UI9函数名） =====================
    def homeContent(self, filter):
        j = self._get('/api.php/web/index/home')
        d = j.get('data') or {}
        cats = []
        for c in d.get('categories') or []:
            cats.append({'type_id': str(c.get('type_id')), 'type_name': c.get('type_name')})
        if not cats:
            cats = CATEGORIES
        # filterable=0，不返回filters
        return {"class": cats}

    def homeVideoContent(self):
        j = self._get('/api.php/web/index/home')
        d = j.get('data') or {}
        vids = []
        for c in d.get('categories') or []:
            for v in c.get('videos') or []:
                vids.append(self._video_item(v))
        return {"list": vids}

    def categoryContent(self, tid, pg, filter, extend):
        name = next((c['type_name'] for c in CATEGORIES if c['type_id'] == str(tid)), '电影')
        j = self._get('/api.php/web/filter/vod', {'type_name': name, 'page': pg, 'sort': 'hits'})
        data = j.get('data') or []
        vids = [self._video_item(v) for v in data]
        return {"list": vids, "page": pg, "pagecount": 9999, "limit": 18, "total": 9999}

    def detailContent(self, ids):
        j = self._get('/api.php/web/vod/get_detail', {'vod_id': ids[0]})
        d = (j.get('data') or [{}])[0]
        v = {
            'vod_id': d.get('vod_id'),
            'vod_name': d.get('vod_name'),
            'vod_pic': d.get('vod_pic'),
            'type_name': d.get('type_name'),
            'vod_year': d.get('vod_year'),
            'vod_area': d.get('vod_area'),
            'vod_remarks': d.get('vod_remarks'),
            'vod_actor': d.get('vod_actor'),
            'vod_director': d.get('vod_director'),
            'vod_content': d.get('vod_content'),
            'vod_play_from': d.get('vod_play_from'),
            'vod_play_url': d.get('vod_play_url')
        }
        return {"list": [v]}

    # UI9规范：双搜索函数
    def searchContent(self, key, quick, pg=1):
        return self.searchContentPage(key, quick, pg)
    def searchContentPage(self, key, quick, pg="1"):
        j = self._get('/api.php/web/search/index', {'wd': key, 'page': pg, 'limit': 15})
        data = j.get('data') or []
        video_list = [self._video_item(v) for v in data]
        return {"list": video_list, "page": int(pg or 1), "pagecount": 1, "limit":15, "total": len(video_list)}

    def playerContent(self, flag, id, vipFlags):
        ts = int(time.time() * 1000)
        body = _pb(id, flag, ts)
        h = dict(self.h)
        h['Content-Type'] = 'application/x-protobuf'
        h['Accept'] = 'application/x-protobuf'
        for _ in range(2):
            try:
                r = self._fetch(self.host + '/api.php/web/decode/url', headers=h, data=body, method='POST')
                fields = _parse_pb(r)
                if fields.get(1) == 1 and fields.get(3):
                    return {"parse": 0, "url": fields[3], "header": {"User-Agent": self.ua}}
            except Exception:
                pass
            time.sleep(0.3)
        return {}

    def localProxy(self, param=''):
        return [404, "text/plain", "NotFound"]

if __name__ == '__main__':
    sp = Spider()
    sp.init()
