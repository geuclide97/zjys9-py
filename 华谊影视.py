# -*- coding: utf-8 -*-
"""
华谊影视 UI9专用Python爬虫
适配UI9标准规范，支持extend后台改域名UA
依赖：pycryptodome
UI9配置JSON：
{
  "key": "huayi_py",
  "name": "华谊影视",
  "type": 3,
  "api": "./py/huayi.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 0
}
"""
import re
import urllib.parse
import json
import time
import base64
import string
import random
import hashlib
# 加密库容错
try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5, AES
    from Crypto.Util.Padding import pad, unpad
except Exception:
    RSA = None
    PKCS1_v1_5 = None
    AES = None
    pad = None
    unpad = None

# UI9父类兜底，无base.spider不报错
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


PUB1_B64 = 'MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCr8SzZhjYy+rsya1K09t8d2K50pWFoBkgUqMpKOiW+3IEVKd4eTdvg9RSOjQ82kypL6R9BnsmrS1V8s4PVDwjQbUtYhTPPC9Hz16qY7rpD6m0d2vr09/UpWQ5uOy9PR0QTrsioveZ+DIe9jc3C+zBCu/kZSY/R8stwJoiitki3gwIDAQAB'
NATIVE_K = b'ed5fdsgucxumegqa'
SAFE = b'OC1A06E197EF10CF3F6058CA7A803B5E'
PW_SAFE = b'11GK2we32144LO&hilUITB)FMd1khdaF'
CERT_MD5 = '089C68CF7E7F6A5A29790CC656EB7126'
CERT_SHA1 = '7E1141ECF197A3A7FD9A41900F8C638A12BA102F'
PKG = 'com.lxf.sncgtzxyx'
VC = '6001'


def _varint(n):
    b = b''
    while True:
        x = n & 0x7f
        n >>= 7
        if n:
            b += bytes([x | 0x80])
        else:
            return b + bytes([x])


def _f(num, wire, payload):
    t = _varint((num << 3) | wire)
    if wire == 2:
        return t + _varint(len(payload)) + payload
    return t + payload


def _pb(buf):
    out = []
    i = 0
    n = len(buf)
    while i < n:
        b = buf[i]
        fn, wt = b >> 3, b & 7
        i += 1
        if wt == 0:
            v = 0
            sh = 0
            while i < n:
                x = buf[i]
                i += 1
                v |= (x & 0x7f) << sh
                sh += 7
                if not x & 0x80:
                    break
            out.append((fn, wt, v))
        elif wt == 2:
            ln = 0
            sh = 0
            while i < n:
                x = buf[i]
                i += 1
                ln |= (x & 0x7f) << sh
                sh += 7
                if not x & 0x80:
                    break
            out.append((fn, wt, buf[i:i + ln]))
            i += ln
        elif wt == 5:
            out.append((fn, wt, buf[i:i + 4]))
            i += 4
        elif wt == 1:
            out.append((fn, wt, buf[i:i + 8]))
            i += 8
        else:
            i += 1
    return out


def _rnd(k):
    CH = string.ascii_letters + string.digits
    return ''.join(random.sample(list(CH), k - 1)) + '='


_e = base64.b64encode(AES.new(PW_SAFE, AES.MODE_ECB).encrypt(pad(
    (CERT_MD5 + '######' + CERT_SHA1 + '~~~~~~' + PKG + '>>>+++' + VC).encode(), 16))).decode()
_e2 = base64.b64encode(_e.encode()).decode()
SAFECODE = (_e2[:16] + _e2[-16:]).upper()


class Spider(BaseSpider):
    # UI9默认扩展配置，后台extend可JSON覆盖
    DEFAULT_EXT = {
        "host": "http://43.240.158.154:18004",
        "ua": "okhttp/3.12.1"
    }

    def getName(self):
        return "华谊影视"

    def init(self, extend=""):
        # 加载扩展配置
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
        self.HOST = self.ext["host"].rstrip("/")
        self.UA = self.ext["ua"]

        self.udid = hashlib.md5(str(time.time()).encode()).hexdigest()[:16].upper()
        self._rsa1 = None
        self._rsa2 = None
        self._token = ''
        self._cur_id = ''

        # 加密库检测
        if not RSA or not PKCS1_v1_5 or not AES or not pad or not unpad:
            print("【华谊】缺少pycryptodome依赖，爬虫无法工作")
            return

        try:
            self._rsa1 = PKCS1_v1_5.new(RSA.import_key(base64.b64decode(PUB1_B64)))
        except Exception as e:
            print("【华谊】rsa1初始化失败", e)
            return
        # 登录、获取公钥，异常不阻断init，后续接口会空返回
        try:
            self._login()
        except Exception as e:
            print("【华谊】登录异常", e)
        try:
            self._zone()
        except Exception as e:
            print("【华谊】zone公钥获取异常", e)

    def _http(self, url, data=None, headers=None):
        import urllib.request
        req_headers = {"User-Agent": self.UA}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=data, headers=req_headers)
        resp = urllib.request.urlopen(req, timeout=20)
        return resp.read()

    def _login(self):
        body = json.dumps({
            'username': 'tv_%s' % self.udid[:10].lower(),
            'password': hashlib.md5(('tv' + self.udid).encode()).hexdigest(),
            'udid': self.udid
        }).encode()
        try:
            self._http(self.HOST + '/api/ex/v3/user/register', body, {'Content-Type': 'application/json'})
        except Exception:
            pass
        d = self._http(self.HOST + '/api/ex/v3/user/login', body, {'Content-Type': 'application/json'})
        j = json.loads(d)
        data = j.get('data') or {}
        self._token = (data.get('token') or (data.get('user') or {}).get('token') or '')

    def _zone(self):
        ts = int(time.time() * 1000)
        rnd = _rnd(16)
        sign = base64.b64encode(self._rsa1.encrypt((str(ts) + rnd).encode())).decode()
        body = (_f(1, 0, _varint(ts)) + _f(2, 2, sign.encode()) +
                _f(3, 2, rnd.encode()) + _f(4, 2, rnd.encode()) + _f(5, 2, rnd.encode()))
        P = {'plat': 'android', 'vOs': '16', '_vOsCode': '36', 'vApp': '6001',
             'vName': '6.0.0.1', 'pkg': PKG,
             'appName': '%E5%8D%8E%E8%B0%8A%E5%BD%B1%E8%A7%86',
             'udid': self.udid, 'uuid': self.udid, 'chid': '10000',
             'androidID': self.udid, 'net': '1', 'young': 0, 'tenantId': '',
             'v': 1, 'device': 0, 'lang': 'zh', 'country': 'CN', 'cpu': 'arm64-v8a'}
        d = self._http(self.HOST + '/api/v5/find/app/zone', body, {
            'Content-Type': 'application/x-protobuf',
            'Accept': 'application/x-protobuf',
            'Cache-Control': 'no-cache',
            'publicParams': json.dumps(P, separators=(',', ':'))})
        top = _pb(d)
        inner = [v for fn, wt, v in top if fn == 3 and wt == 2][0]
        strs = {fn: v for fn, wt, v in _pb(inner) if wt == 2}
        self._rsa2 = PKCS1_v1_5.new(RSA.import_key(base64.b64decode(
            strs[2] + strs[3] + strs[4] + strs[5])))

    def _hdr(self):
        ts = int(time.time() * 1000)
        rnd = _rnd(16)
        sig = base64.b64encode(self._rsa2.encrypt((str(ts) + rnd + '6001').encode())).decode()
        ao = base64.b64encode(AES.new(SAFE, AES.MODE_ECB).encrypt(
            pad((str(ts) + rnd).encode(), 16))).decode()
        J = {'country': 'CN', 'vName': '6.0.0.1', 'cpuId': '', 'young': 0,
             'facturer': 'OnePlus', 'pkg': PKG, 'uuid': self.udid,
             'resolution': '1080x2256', 'mac': '02%3A00%3A00%3A00%3A00%3A00',
             'sig': sig, 'abid': '3884', 'model': 'PJX110', 'plat': 'android',
             'udid': self.udid, 'dpi': '480', 'net': '1', 'lang': 'zh',
             'random_str': rnd, 'brand': 'OnePlus', 'timestamp': ts,
             'density': '3.0', 'appName': '%E5%8D%8E%E8%B0%8A%E5%BD%B1%E8%A7%86',
             'cpu': 'arm64-v8a', 'chid': '10000', 'carrier': '%E8%81%94%E9%80%9A',
             'sig2': ao[:8], 'sig3': ao[8:], 'v': 1, 'tenantId': '',
             '_vOsCode': '36', 'vOs': '16', 'vApp': '6001', 'device': 0,
             'androidID': self.udid}
        blob = json.dumps(J, separators=(',', ':'), ensure_ascii=False).encode()
        pd_hex = AES.new(NATIVE_K, AES.MODE_CBC, NATIVE_K).encrypt(pad(blob, 16)).hex()
        h = {'User-Agent': self.UA, 'Accept': 'application/json',
             'Cache-Control': 'no-cache',
             'publicParams': json.dumps({'paramsData': pd_hex}, separators=(',', ':'))}
        if self._token:
            h['token'] = self._token
        return h

    def _secure(self, mapkv):
        ts = int(time.time() * 1000)
        rnd8 = _rnd(8)
        plain = (mapkv + str(ts)).encode()
        ct = AES.new(SAFECODE.encode(), AES.MODE_ECB).encrypt(pad(plain, 16))
        b64 = base64.b64encode(ct).decode()
        return (_f(1, 2, (rnd8 + b64[:12]).encode()) +
                _f(2, 2, b64[12:].encode()) +
                _f(3, 2, _rnd(20).encode()) + _f(4, 0, _varint(ts)) +
                _f(5, 2, rnd8.encode()))

    @staticmethod
    def _video_item(item):
        if not isinstance(item, dict):
            return {}
        return {
            "vod_id": item.get("vod_id", ""),
            "vod_name": item.get("vod_name", ""),
            "vod_pic": item.get("vod_pic", ""),
            "vod_remarks": item.get("vod_remarks", "")
        }

    def homeContent(self, filter):
        cats = []
        try:
            d = self._http(self.HOST + '/api/v3/drama/getCategory?orderBy=type_id',
                           None, {'User-Agent': self.UA, 'Accept': 'application/json'})
            arr = json.loads(d).get('data') or []
            for c in arr:
                if str(c.get('id')) != '29':
                    cats.append({'type_id': str(c['id']),
                                 'type_name': c.get('name', '')})
        except Exception as e:
            print("【华谊】homeContent分类获取失败", e)
        if not cats:
            cats = [
                {'type_id': '21', 'type_name': '电影'},
                {'type_id': '22', 'type_name': '剧集'},
                {'type_id': '25', 'type_name': '动漫'},
                {'type_id': '26', 'type_name': '综艺'},
                {'type_id': '27', 'type_name': '短剧'},
                {'type_id': '28', 'type_name': '漫剧'}
            ]
        cats.append({'type_id': 'history', 'type_name': '最近在看'})
        return {"class": cats, "filters": {}}

    def homeVideoContent(self):
        raw = self._list('page=1&pagesize=24')
        list_out = [self._video_item(i) for i in raw]
        return {"list": list_out}

    def _list(self, qs):
        out = []
        if not self._rsa2:
            print("【华谊】_rsa2为空，跳过列表请求")
            return out
        try:
            hh = self._hdr()
            hh['Content-Type'] = 'application/x-protobuf'
            hh['Accept'] = 'application/x-protobuf'
            d = self._http(self.HOST + '/api/proto/v5/drama/category',
                           self._secure(qs), hh)
            top = _pb(d)
            code = [v for fn, wt, v in top if fn == 1 and wt == 0]
            if (code[0] if code else 0) != 200:
                return out
            data = [v for fn, wt, v in top if fn == 3 and wt == 2][0]
            for fn, wt, v in _pb(data):
                if fn != 1 or wt != 2:
                    continue
                info = {'vod_id': '', 'vod_name': '', 'vod_pic': '', 'vod_remarks': ''}
                for f2, w2, v2 in _pb(v):
                    if f2 == 3 and w2 == 0:
                        info['vod_id'] = str(v2)
                    elif f2 == 5 and w2 == 2:
                        info['vod_name'] = v2.decode('utf-8', 'replace')
                    elif f2 == 2 and w2 == 2:
                        cands = [v3.decode('utf-8', 'replace')
                                 for f3, w3, v3 in _pb(v2)
                                 if w3 == 2 and v3.startswith(b'http')]
                        if cands:
                            info['vod_pic'] = next(
                                (u for u in cands if u.startswith('https')),
                                cands[0])
                    elif f2 == 13 and w2 == 2:
                        info['vod_remarks'] = v2.decode('utf-8', 'replace')
                if info['vod_id']:
                    out.append(info)
        except Exception as e:
            print("【华谊】_list接口异常", e)
        return out

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        if tid == 'history':
            his = self._history_list()
            return {'list': [self._video_item(x) for x in his], 'page': 1,
                    'pagecount': 1, 'limit': 40, 'total': 40}
        qs = 'page=%d&pagesize=24&typeId1=%s' % (pg, tid)
        lst = self._list(qs)
        return {"list": [self._video_item(i) for i in lst],
                "page": pg, "pagecount": 999, "limit": 24, "total": 99999}

    def _history_list(self):
        out = []
        try:
            d = self._http(self.HOST + '/api/ex/v3/user/history?username=fzcrym',
                           None, {'User-Agent': self.UA, 'Accept': 'application/json'})
            arr = json.loads(d).get('data') or []
            for it in arr:
                vid = it.get('videoId', '')
                if '|' in vid:
                    frm, url = vid.split('|', 1)
                    out.append({
                        'vod_id': 'h$%s$%s' % (frm, url),
                        'vod_name': it.get('videoName', ''),
                        'vod_pic': it.get('videoCover', ''),
                        'vod_remarks': '%s·第%s集' % (frm, it.get('videoPart', '')),
                    })
        except Exception as e:
            print("【华谊】历史记录异常", e)
        return out

    def detailContent(self, ids):
        result = {"list": []}
        vid = ids[0].split(',')[0].strip()
        self._cur_id = vid
        if vid.startswith('h$'):
            _, frm, url = vid.split('$', 2)
            result["list"].append({
                "vod_id": vid,
                "vod_name": "继续观看",
                "vod_play_from": frm,
                "vod_play_url": "正片$%s" % url,
                "vod_pic": "",
                "vod_content": "播放历史·线路:" + frm
            })
            return result
        if not self._rsa2:
            return result
        try:
            hh = self._hdr()
            hh['Content-Type'] = 'application/x-protobuf'
            hh['Accept'] = 'application/x-protobuf'
            d = self._http(self.HOST + '/api/proto/v5/drama/getDetail',
                           self._secure('id=' + vid), hh)
            top = _pb(d)
            data = [v for fn, wt, v in top if fn == 3 and wt == 2][0]
            dd = _pb(data)
            out = {"vod_id": vid}
            for fn, wt, v in dd:
                if fn == 9 and wt == 2 and 'vod_name' not in out:
                    out['vod_name'] = v.decode('utf-8', 'replace')
                elif fn == 1 and wt == 2 and 'vod_area' not in out:
                    out['vod_area'] = v.decode('utf-8', 'replace')
                elif fn == 12 and wt == 2 and 'vod_director' not in out:
                    out['vod_director'] = v.decode('utf-8', 'replace')
                elif fn == 16 and wt == 2 and 'vod_actor' not in out:
                    out['vod_actor'] = v.decode('utf-8', 'replace').lstrip(' ,')
                elif fn == 25 and wt == 2 and 'vod_actor' not in out:
                    out['vod_actor'] = v.decode('utf-8', 'replace')
                elif fn == 6 and wt == 2 and 'vod_content' not in out:
                    out['vod_content'] = re.sub(r'<[^>]+>', '', v.decode('utf-8', 'replace'))
                elif fn == 2 and wt == 2 and 'vod_pic' not in out:
                    cands = [v3.decode('utf-8', 'replace')
                             for f3, w3, v3 in _pb(v)
                             if w3 == 2 and v3.startswith(b'http')]
                    if cands:
                        out['vod_pic'] = next((u for u in cands if u.startswith('https')), cands[0])
            eps = []
            pos = 0
            n = len(data)
            while True:
                j = data.find(b'\xea\x01', pos)
                if j < 0:
                    break
                k = j + 2
                ln = 0
                sh = 0
                while k < n and data[k] & 0x80:
                    ln |= (data[k] & 0x7f) << sh
                    sh += 7
                    k += 1
                if k >= n:
                    break
                ln |= (data[k] & 0x7f) << sh
                k += 1
                if ln <= 0 or k + ln > n:
                    pos = j + 1
                    continue
                entry = data[k:k + ln]
                pos = k + ln
                title = pth = src = src_cn = ''
                for f3_, w3_, v3_ in _pb(entry):
                    if w3_ != 2:
                        continue
                    if f3_ == 2:
                        title = v3_.decode('utf-8', 'replace')
                    elif f3_ == 3:
                        title = v3_.decode('utf-8', 'replace')
                    elif f3_ == 4:
                        pth = v3_.decode('utf-8', 'replace')
                    elif f3_ == 9:
                        src = v3_.decode('utf-8', 'replace')
                    elif f3_ == 10:
                        src_cn = v3_.decode('utf-8', 'replace')
                if not pth:
                    continue
                mm = re.match(r'^第?0*(\d{1,4})[集话期](?:完结)?$', title)
                if mm:
                    title = mm.group(1)
                eps.append((title, pth, src, src_cn))
            lines = {}
            order = []
            for title, pth, src, src_cn in eps:
                line = src_cn or src or '正片'
                if line not in lines:
                    lines[line] = []
                    order.append(line)
                if re.match(r'(?i).*\.(mp4|m3u8|flv|mkv|avi|ts|mov|mpd|m4a|wmv)(\?.*)?$', pth):
                    ep_url = pth
                else:
                    ep_url = base64.b64encode(json.dumps(
                        {'vodPlayFrom': src, 'playUrl': pth},
                        separators=(',', ':')).encode()).decode()
                lines[line].append('%s$%s' % (title or '正片', ep_url))
            def _rank(nm):
                if '超高清' in nm:
                    return 0
                if '蓝光' in nm:
                    return 1
                return 2
            order.sort(key=lambda x: (_rank(x), x))
            if lines:
                out['vod_play_from'] = '$$$'.join(order)
                out['vod_play_url'] = '$$$'.join('#'.join(lines[l]) for l in order)
            else:
                out['vod_play_from'] = '华谊'
                out['vod_play_url'] = '暂无片源$http://'
            result["list"].append(out)
        except Exception as e:
            print("【华谊】detailContent异常", e)
        return result

    # UI9双搜索函数，和枫叶模板对齐
    def searchContent(self, key, quick, pg=1):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        out_list = []
        if not self._rsa2:
            return {"list": out_list, "page": int(pg)}
        try:
            qs = 'page=%s&pagesize=24&searchKeys=%s' % (pg or 1, key)
            hh = self._hdr()
            hh['Content-Type'] = 'application/x-protobuf'
            hh['Accept'] = 'application/x-protobuf'
            d = self._http(self.HOST + '/api/proto/v5/drama/search',
                           self._secure(qs), hh)
            top = _pb(d)
            code = [v for fn, wt, v in top if fn == 1 and wt == 0]
            if (code[0] if code else 0) != 200:
                return {"list": out_list, "page": int(pg)}
            data = [v for fn, wt, v in top if fn == 3 and wt == 2][0]
            for fn, wt, v in _pb(data):
                if fn != 1 or wt != 2:
                    continue
                info = {'vod_id': '', 'vod_name': '', 'vod_pic': '', 'vod_remarks': ''}
                for f2, w2, v2 in _pb(v):
                    if f2 == 3 and w2 == 0:
                        info['vod_id'] = str(v2)
                    elif f2 == 5 and w2 == 2:
                        info['vod_name'] = v2.decode('utf-8', 'replace')
                    elif f2 == 2 and w2 == 2:
                        cands = [v3.decode('utf-8', 'replace')
                                 for f3, w3, v3 in _pb(v2)
                                 if w3 == 2 and v3.startswith(b'http')]
                        if cands:
                            info['vod_pic'] = next(
                                (u for u in cands if u.startswith('https')),
                                cands[0])
                    elif f2 == 13 and w2 == 2:
                        info['vod_remarks'] = v2.decode('utf-8', 'replace')
                if info['vod_id'] and info['vod_name']:
                    out_list.append(self._video_item(info))
        except Exception as e:
            print("【华谊】搜索异常", e)
        return {"list": out_list, "page": int(pg), "pagecount": 1, "limit": 24, "total": len(out_list)}

    def playerContent(self, flag, id, vipFlags):
        url = id
        if not self._rsa2:
            return {"parse": 0, "playUrl": "", "url": url, "header": {"User-Agent": self.UA}}
        try:
            if id and not id.startswith('http') and not id.startswith('h$'):
                jm = json.loads(base64.b64decode(id))
                pf, pu = jm.get('vodPlayFrom', ''), jm.get('playUrl', '')
                hh = self._hdr()
                hh['Content-Type'] = 'application/x-protobuf'
                hh['Accept'] = 'application/x-protobuf'
                qs = 'vodPlayFrom=%s&playUrl=%s' % (
                    urllib.parse.quote(pf), urllib.parse.quote(pu, safe=''))
                d = self._http(self.HOST + '/api/proto/v5/videoUsableUrl',
                               self._secure(qs), hh)
                top = _pb(d)
                code = [v for fn, wt, v in top if fn == 1 and wt == 0]
                if (code[0] if code else 0) == 200:
                    data = [v for fn, wt, v in top if fn == 3 and wt == 2]
                    if data:
                        mm = re.search(rb'https?://[\x21-\x7e]+', data[0])
                        if mm:
                            url = mm.group(0).decode('utf-8', 'replace')
        except Exception as e:
            print("【华谊】playerContent异常", e)
        return {"parse": 0, "playUrl": "", "url": url, "header": {"User-Agent": self.UA}}

    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(m3u8|mp4|mkv|ts|flv)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param=''):
        return [404, "text/plain", "NotFound"]

    def destroy(self):
        pass


if __name__ == '__main__':
    sp = Spider()
    sp.init()
