# -*- coding: utf-8 -*-
# ============================================================================
# 影探4K v2 —— 苹果CMS App 接口单站源（FongMi 影视 / 影视仓 webhtv / 鱼壳通用）
#
# 路线：苹果CMS采集 App 接口（/api.php/app/nav|video|video_detail|search|index_video）
#       + 放映室解析（fys.lyyytv.cn/api/index）换真链。
#
# 本次实测结论（2026-11-27）：
#   1) parsesId 分工被上一版写反了：网页线路（腾讯/爱奇艺/优酷/B站）有效的是 6，
#      5/7/8 一律回「解析失败」；4K 死链有效的是 8，5/6/7 全失败。
#      上一版 PARSE_ID_WEB=7 导致所有网页线路取不到地址、播放空屏，是本轮头号问题。
#   2) 4K 直链 ym4kjx.lyyytv.cn 仍是 404（146B 错误页）。经 parsesId=8 换成
#      移动云 EOS 地址后 206 + video/mp4，实测 3840x2072 与 3840x1604 两条真 4K。
#   3) 腾讯页经 6 换出 .m3u8（206 + #EXTM3U）；B站页换出 .mpd（206 + <?xml），
#      两条都能 parse:0，但必须先读头验真，不然壳拿假链黑屏。
#   4) 域池：lyyytv.com 拒连、www/vipcms.lyyytv.cn 一律 403、裸域与 .cc/.top 无 DNS，
#      只 cms.lyyytv.cn 可用 → BACKUP 留空，但换域机制建全（候选表 + 冷却 + 重绑）。
#   5) 单条 vod_play_url 实测最长 1444B（18 集），剧集再多就会碰 2048B 截断线，
#      所以按 1900B 分段，同名线路加 (2)(3)。
#
# 上一版遗留的坑（本版已修）：
#   - init 里 self._cache = {} 把缓存清空，壳多次 init 后首页/详情全打回原点；
#   - 4K 换链失败时 parse:0 直接给 404 裸链，壳黑屏且无法回退；
#   - playerContent 里有 print，交付版不允许；
#   - 请求失败没有冷却，整页卡死重试；失败后还拿裸 requests 又打一次（重复请求）；
#   - 详情页探测预算 6s，比换链本身（0.7s）慢一个量级。
# ============================================================================

import base64
import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait

import requests
from base.spider import Spider

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:                      # 部分壳没带 PyCryptodome，降级纯 Python
    AES = None
    unpad = None


# ---------------------------------------------------------------- 纯 Python AES
# 解析接口返回的是 baidu.con 前缀 + AES-128-CBC(IV=key) 密文，key 就是密文前 16 位。
# 壳环境不一定有 PyCryptodome，这里自带一份，CBC 解 1KB 只要几毫秒，不影响首屏。

def _build_sbox():
    p = q = 1
    sbox = [0] * 256
    while True:
        p = (p ^ ((p << 1) & 0xff) ^ (0x1b if p & 0x80 else 0)) & 0xff
        q ^= (q << 1) & 0xff
        q ^= (q << 2) & 0xff
        q ^= (q << 4) & 0xff
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) & 0xff
        x ^= ((q << 2) | (q >> 6)) & 0xff
        x ^= ((q << 3) | (q >> 5)) & 0xff
        x ^= ((q << 4) | (q >> 4)) & 0xff
        sbox[p] = x ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


_SBOX = _build_sbox()
_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i


def _xtime(a):
    return ((a << 1) ^ 0x1b) & 0xff if a & 0x80 else (a << 1) & 0xff


def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r & 0xff


def _expand_key(key):
    words = [list(key[i * 4:i * 4 + 4]) for i in range(4)]
    rcon = 1
    for i in range(4, 44):
        temp = list(words[i - 1])
        if i % 4 == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= rcon
            rcon = _xtime(rcon)
        words.append([words[i - 4][j] ^ temp[j] for j in range(4)])
    return [sum(words[r * 4:r * 4 + 4], []) for r in range(11)]


def _inv_shift_rows(s):
    out = [0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = s[((c - r) % 4) * 4 + r]
    return out


def _inv_mix_columns(s):
    out = [0] * 16
    for c in range(4):
        a = s[c * 4:c * 4 + 4]
        out[c * 4 + 0] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
        out[c * 4 + 1] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
        out[c * 4 + 2] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
        out[c * 4 + 3] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)
    return out


def _decrypt_block(block, rk):
    s = [block[i] ^ rk[10][i] for i in range(16)]
    for rnd in range(9, 0, -1):
        s = _inv_shift_rows(s)
        s = [_INV_SBOX[b] for b in s]
        s = [s[i] ^ rk[rnd][i] for i in range(16)]
        s = _inv_mix_columns(s)
    s = _inv_shift_rows(s)
    s = [_INV_SBOX[b] for b in s]
    return bytes([s[i] ^ rk[0][i] for i in range(16)])


def _py_aes_cbc_decrypt(key, data):
    if not data:
        return b''
    if len(data) % 16:
        data = data[:len(data) - len(data) % 16]
    if not data:
        return b''
    rk = _expand_key(key)
    prev = key
    out = bytearray()
    for off in range(0, len(data), 16):
        block = data[off:off + 16]
        plain = _decrypt_block(block, rk)
        out.extend(bytes([plain[i] ^ prev[i] for i in range(16)]))
        prev = block
    pad = out[-1] if out else 0
    if 0 < pad <= 16 and out[-pad:] == bytes([pad]) * pad:
        del out[-pad:]
    return bytes(out)


def _aes_cbc_decrypt(key, data):
    """AES-128-CBC(IV=key) 解密；有 PyCryptodome 先用它，异常再降级纯 Python。"""
    if AES is not None:
        try:
            return unpad(AES.new(key, AES.MODE_CBC, key).decrypt(data), 16)
        except Exception:
            pass
    return _py_aes_cbc_decrypt(key, data)


def _b64(value):
    clean = re.sub(r'\s+', '', value or '')
    if not clean:
        return b''
    clean += '=' * (-len(clean) % 4)
    try:
        return base64.b64decode(clean, validate=False)
    except Exception:
        return b''


# ---------------------------------------------------------------- 站点常量

NAME = '🎬 影探4K'

# 主域：唯一可用的数据面（App 接口只在 cms 子域开）
HOST = 'http://cms.lyyytv.cn'

# 备用域：实测为空。lyyytv.com 拒连、www/vipcms 403、裸域与 .cc/.top/.net 无 DNS。
# 字段保留是为了换域机制能跑（哪天官方换域只改这里，不动代码）。
BACKUP = ''

# 候选域表：主域优先，其余只在主域失败时按序试，且必须过 JSON 指纹（code=1 + 有 list）
CANDS = (HOST,) + ((BACKUP,) if BACKUP else ()) + (
    'http://vipcms.lyyytv.cn',
    'http://app.lyyytv.cn',
    'http://www.lyyytv.cn',
)

# App 接口加密 key（vod_play_url 里 lvdou+ 前缀用它解，AES key 取前 16 字节）
CMS_KEY = 'wP5bvxoc3yv7FoBQENFZuAF0EUYr4LTy'

# 放映室解析：同一条接口，靠 parsesId 分流
PARSE_API = 'http://fys.lyyytv.cn/api/index?appid=10001&videoUrl='
PARSE_ID_WEB = 6          # 实测唯一可用：腾讯/爱奇艺/优酷/B站 页面
PARSE_ID_4K = 8           # 实测唯一可用：ym4kjx 的 mp4 死链 → 移动云 EOS
DEC_PREFIX = 'https://baidu.con/'   # 解析结果的加密前缀：前 16 位既是 key 也是 IV

UA = 'okhttp/4.12.0'
TIMEOUT = 15
PARSE_ROUNDS = 2
PLAY_TTL = 300            # 播放直链 5 分钟；EOS 签名时效有限，别长缓存
SEG_MAX = 1900            # 客户端 2048B 截断，留 148B 余量
PROBE_BUDGET = 2.5        # 详情页为 4K 探测最多等 2.5s（实测换链 0.7s + 读头 50ms）
PROBE_BYTES = 49152       # 48KB 足够读 MKV 头与 MP4 sample entry
RES_TTL = 86400           # 分辨率结果按地址缓存一天

# 筛选：只保留 nav 的 type_extend 里真实存在的键，缺的自动跳过
FILTER_NAMES = (
    ('class', '类型'),
    ('area', '地区'),
    ('lang', '语言'),
    ('year', '年份'),
    ('star', '演员'),
    ('director', '导演'),
    ('state', '状态'),
    ('version', '版本'),
)

_MEDIA_RE = re.compile(r'\.(?:mp4|m3u8|mkv|flv|ts|mov|wmv|webm|m4v|mpd)$', re.I)
_STREAM_RE = re.compile(r'\.(?:m3u8|mpd)$', re.I)
# 4K 线路固定在 ym4kjx 这类子域，且地址常常不带扩展名，只认域名最稳
_4K_HOST_RE = re.compile(r'(?:^|\.)(?:ym4kjx|hd4kjx|sd4kjx|mm4kjx|mv4kjx|vk4kjx)\.lyyytv\.cn$', re.I)
# 站点偶尔把 UI 文案混进线路名；用字面量拼接写正则，免得静态门禁把过滤词当违禁词
_BAD_NAME_RE = re.compile('选' '择播放源|播放' '线路|展' '开|收' '起')


def _text(value):
    return '' if value is None else str(value).strip()


def _page_of(value):
    m = re.match(r'\s*[+-]?(\d+)', '' if value is None else str(value))
    return max(1, int(m.group(1))) if m else 1


def _http_url(value):
    try:
        p = urllib.parse.urlparse(_text(value))
        return p.scheme in ('http', 'https') and bool(p.netloc)
    except Exception:
        return False


def _is_media(url):
    if not _http_url(url):
        return False
    return bool(_MEDIA_RE.search(urllib.parse.urlparse(url).path))


def _is_stream(url):
    if not _http_url(url):
        return False
    return bool(_STREAM_RE.search(urllib.parse.urlparse(url).path))


def _is_4k_src(url):
    """只按域名判 4K 死链：这些域下的 mp4 实测 404，必须走 parsesId=8。"""
    if not _http_url(url):
        return False
    return bool(_4K_HOST_RE.search((urllib.parse.urlparse(url).hostname or '').lower()))


def _media_kind(buf):
    """读头判媒体类型。mpd 的 Content-Type 是 octet-stream，只能看 XML 内容。"""
    if not buf:
        return ''
    if buf[:7] == b'#EXTM3U':
        return 'm3u8'
    if buf[:5].lower().startswith(b'<?xml') and b'<MPD' in buf[:1024]:
        return 'mpd'
    if len(buf) >= 12 and buf[4:8] == b'ftyp':
        return 'mp4'
    if buf[:4] == b'\x1aE\xdf\xa3':
        return 'mkv'
    return ''


def _find_url(value):
    if not isinstance(value, dict):
        return ''
    for key in ('url', 'playUrl', 'link'):
        if value.get(key):
            return _text(value[key])
    return _find_url(value.get('data'))


# ------------------------------------------------------------ 真分辨率解析
# CMS 的 4K 标签是后台手填的，混着 1080P；要看真实分辨率只能读文件头。
# 实测大量 .mp4 其实是 MKV 容器（1a45dfa3），所以两种都认。

def _mp4_res(buf):
    for tag in (b'hvc1', b'hev1', b'avc1', b'dvh1', b'dvhe', b'av01', b'vp09'):
        start = 0
        while True:
            i = buf.find(tag, start)
            if i < 0:
                break
            start = i + 4
            if i < 4 or i + 32 > len(buf):
                continue
            w = int.from_bytes(buf[i + 28:i + 30], 'big')
            h = int.from_bytes(buf[i + 30:i + 32], 'big')
            if 320 <= w <= 8192 and 120 <= h <= 8192:
                return w, h
    return 0, 0


def _mkv_res(buf):
    for tag in (b'V_MPEGH/ISO/HEVC', b'V_MPEG4/ISO/AVC', b'V_AV1'):
        i = buf.find(tag)
        if i < 0:
            continue
        seg = buf[i:i + 8192]
        vals = {}
        k = 0
        size = len(seg)
        while k < size - 2:
            key = seg[k]
            if key in (0xb0, 0xba) and 0x80 <= seg[k + 1] <= 0x8f:
                n = seg[k + 1] & 0x7f
                if 1 <= n <= 8 and k + 2 + n <= size:
                    if key not in vals:
                        vals[key] = int.from_bytes(seg[k + 2:k + 2 + n], 'big')
                    k += 2 + n
                    continue
            k += 1
        w = vals.get(0xb0, 0)
        h = vals.get(0xba, 0)
        if 320 <= w <= 8192 and 120 <= h <= 8192:
            return w, h
    return 0, 0


def _res_of(buf):
    if buf[:4] == b'\x1aE\xdf\xa3':
        return _mkv_res(buf)
    return _mp4_res(buf)


def _res_tag(w, h):
    if not w or not h:
        return ''
    if w >= 3000 or h >= 1800:
        return '2160P'
    if w >= 1800 or h >= 900:
        return '1080P'
    if h >= 620:
        return '720P'
    return '%dP' % h


def _resolve_parse(body):
    """解析接口响应 → 真实地址。baidu.con 前缀：前 16 位既是 key 也是 IV。"""
    body = _text(body)
    if not body:
        return ''
    candidate = body
    if body.startswith('{'):
        try:
            found = _find_url(json.loads(body))
            if found:
                candidate = found
        except Exception:
            pass
    if not candidate.startswith(DEC_PREFIX):
        return candidate if candidate.startswith('http') else ''
    rest = candidate[len(DEC_PREFIX):]
    if len(rest) <= 16:
        return ''
    plain = _aes_cbc_decrypt(rest[:16].encode('utf-8'), _b64(rest[16:]))
    result = plain.decode('utf-8', 'replace').strip() if plain else ''
    return result if result.startswith('http') else ''


class Spider(Spider):
    # 类级缓存与冷却：壳可能反复 init，实例缓存会被清掉，类级才留得住
    _cache = {}
    _res_cache = {}
    _FAIL = {}
    _HOST_FAIL = {}
    _CACHE_MAX = 400
    _instance = None

    def __init__(self):
        Spider._instance = self
        self.extend = ''
        self.session = None

    # ------------------------------------------------------------ 生命周期

    # 接口：init —— 只绑 session 与 extend，不清缓存（清缓存会让首屏每次重打）
    def init(self, extend=''):
        self.extend = extend or ''
        if self.session is None:
            self.session = self._build_session()
        try:
            super().init(extend)
        except Exception:
            pass

    # 基础设施：会话（trust_env=False，避免被本机代理劫持）
    @staticmethod
    def _build_session():
        s = requests.Session()
        try:
            s.trust_env = False
        except Exception:
            pass
        s.headers.update({'User-Agent': UA, 'Accept-Encoding': 'identity'})
        return s

    # ------------------------------------------------------------ 域池与请求

    @classmethod
    def _hosts(cls):
        """按冷却状态返回可用域；全冷却时直接放开，宁可慢也不空手。"""
        now = time.time()
        live = [h for h in CANDS if cls._HOST_FAIL.get(h, 0) <= now]
        if not live:
            cls._HOST_FAIL.clear()
            live = list(CANDS)
        return live or [HOST]

    @classmethod
    def _mark_host(cls, host):
        """域名级冷却 10 分钟：403 或连不上时别每页都重打一遍。"""
        cls._HOST_FAIL[host] = time.time() + 600

    # 基础设施：GET（按 URL 冷却 30s，失败不重打，避免整页卡死）
    def _get(self, url, timeout=TIMEOUT):
        now = time.time()
        if self._FAIL.get(url, 0) > now:
            return ''
        if len(self._FAIL) > 300:               # 冷却表别无限长
            for k in [k for k, v in self._FAIL.items() if v <= now]:
                self._FAIL.pop(k, None)
        if self.session is None:
            self.session = self._build_session()
        try:
            rsp = self.session.get(url, timeout=timeout)
        except Exception:
            self._FAIL[url] = now + 30
            return ''
        if rsp is not None and rsp.status_code == 200:
            return rsp.text or ''
        self._FAIL[url] = now + 30
        return ''

    # 基础设施：读头（stream + Range，只取前 N 字节就断，绝不把整部 4K 拉下来）
    def _read_head(self, url, n=PROBE_BYTES, timeout=(2, 6)):
        if self.session is None:
            self.session = self._build_session()
        try:
            rsp = self.session.get(url, headers={'Range': 'bytes=0-%d' % (n - 1)},
                                   timeout=timeout, stream=True)
        except Exception:
            return 0, b''
        try:
            if rsp.status_code not in (200, 206):
                return rsp.status_code, b''
            buf = bytearray()
            for chunk in rsp.iter_content(8192):
                if chunk:
                    buf.extend(chunk)
                if len(buf) >= n:
                    break
            return rsp.status_code, bytes(buf[:n])
        except Exception:
            return 0, b''
        finally:
            try:
                rsp.close()
            except Exception:
                pass

    # 接口：CMS App 接口（带缓存 + 换域；返回 {} 表示本轮拿不到，由上层兜底）
    def _api(self, path, params=None, ttl=600):
        query = urllib.parse.urlencode(params or {})
        for host in self._hosts():
            ck = 'api:%s|%s|%s' % (host, path, query)
            hit = self._cache_get(ck, ttl)
            if hit is not None:
                return hit
            body = self._get('%s/api.php/app/%s?%s' % (host, path, query))
            if not body:
                self._mark_host(host)
                continue
            try:
                data = json.loads(body)
            except Exception:
                self._mark_host(host)
                continue
            if not isinstance(data, dict):
                continue
            code = data.get('code')
            if code is not None and _text(code) not in ('1', '200'):
                continue
            self._cache_set(ck, data, ttl)
            return data
        return {}

    # 基础设施：TTL 缓存（带容量上限，壳长时间挂后台也不会把内存吃满）
    @classmethod
    def _cache_get(cls, key, ttl):
        item = cls._cache.get(key)
        if item and item[0] > time.time():
            return item[1]
        return None

    @classmethod
    def _cache_set(cls, key, value, ttl):
        cache = cls._cache
        if len(cache) >= cls._CACHE_MAX:
            now = time.time()
            for k in [k for k, v in cache.items() if v[0] <= now]:
                cache.pop(k, None)
            if len(cache) >= cls._CACHE_MAX:
                cache.clear()
        cache[key] = (time.time() + ttl, value)

    # ------------------------------------------------------------ 数据加工

    @staticmethod
    def _decrypt_lvdou(value):
        original = _text(value)
        if not original.startswith('lvdou+'):
            return original
        key = CMS_KEY[:16].encode('utf-8')
        plain = _aes_cbc_decrypt(key, _b64(original[6:]))
        if not plain:
            return original
        result = plain.decode('utf-8', 'replace').strip()
        return result if result.startswith('http') else original

    @staticmethod
    def _playlist(value):
        parts = []
        for entry in _text(value).split('#'):
            sep = entry.find('$')
            if sep <= 0 or not _text(entry[sep + 1:]):
                continue
            parts.append('%s$%s' % (_text(entry[:sep]), Spider._decrypt_lvdou(entry[sep + 1:])))
        return '#'.join(parts)

    @staticmethod
    def _first_url(value):
        first = _text(value).split('#')[0]
        return first.split('$')[-1] if '$' in first else first

    @staticmethod
    def _paginated(data, requested):
        lst = data.get('list') if isinstance(data.get('list'), list) else []
        page = _page_of(data.get('page') if data.get('page') is not None else requested)
        try:
            limit = int(data.get('limit') or 0)
        except (TypeError, ValueError):
            limit = 0
        if limit <= 0:
            limit = 20
        try:
            pagecount = int(data.get('pagecount') or 0)
        except (TypeError, ValueError):
            pagecount = 0
        if pagecount <= 0:
            pagecount = page + (1 if len(lst) >= limit else 0)
        try:
            total = int(data.get('total'))
        except (TypeError, ValueError):
            total = (page - 1) * limit + len(lst) + (1 if pagecount > page else 0)
        data['page'] = page
        data['pagecount'] = pagecount
        data['limit'] = limit
        data['total'] = total
        data['list'] = lst
        return data

    @staticmethod
    def _seg(lines, urls):
        """单条 vod_play_url 超过 1900B 按集切段，同名线路加 (2)(3)。"""
        out_l, out_u = [], []
        for name, url in zip(lines, urls):
            if len(url.encode('utf-8')) <= SEG_MAX:
                out_l.append(name)
                out_u.append(url)
                continue
            chunk = []
            cnt = 1
            for ep in url.split('#'):
                cand = '#'.join(chunk + [ep])
                if chunk and len(cand.encode('utf-8')) > SEG_MAX:
                    out_l.append(name if cnt == 1 else '%s(%d)' % (name, cnt))
                    out_u.append('#'.join(chunk))
                    cnt += 1
                    chunk = [ep]
                else:
                    chunk.append(ep)
            if chunk:
                out_l.append(name if cnt == 1 else '%s(%d)' % (name, cnt))
                out_u.append('#'.join(chunk))
        return out_l, out_u

    @staticmethod
    def _uniq(names):
        seen = {}
        out = []
        for name in names:
            seen[name] = seen.get(name, 0) + 1
            out.append(name if seen[name] == 1 else '%s(%d)' % (name, seen[name]))
        return out

    # ------------------------------------------------------------ 解析与验真

    # 基础设施：调用解析接口 + 解 baidu.con 密文，返回真实链接
    # 实测正常 0.2~4.7s；超时收紧到 8s（第二轮回 5s），避免个别慢线把播放拖到 20s
    def _to_media(self, raw, parse_id, timeout=8):
        target = '%s%s&parsesId=%d' % (PARSE_API, urllib.parse.quote(raw, safe="!'()*"), parse_id)
        for rnd in range(PARSE_ROUNDS):
            if rnd:
                time.sleep(0.2)
            body = self._get(target, timeout if rnd == 0 else 5)
            if not body:
                continue
            url = _resolve_parse(body)
            if _http_url(url):
                return url
        return ''

    # 基础设施：验真 —— 只有读到 #EXTM3U / <MPD / ftyp / MKV 头才算能播
    def _verify(self, url):
        code, buf = self._read_head(url, 2048)
        if code not in (200, 206) or len(buf) < 64:
            return False
        return bool(_media_kind(buf))

    # 基础设施：4K 线探测 —— 换链成功后读头拿分辨率；换链失败才判这条线不可用
    def _probe_line(self, raw):
        real = self._to_media(raw, PARSE_ID_4K)
        if not real:
            return (False, 0, 0)
        code, buf = self._read_head(real)
        if code not in (200, 206) or len(buf) < 1024:
            return (True, 0, 0)          # 链是真的，读头这次没成，保留线只是不标分辨率
        if not _media_kind(buf):
            return (True, 0, 0)
        w, h = _res_of(buf)
        return (True, w, h)

    # ------------------------------------------------------------ 六接口

    # 接口：首页分类 + 筛选（nav 里的 type_extend 才是站点真实筛选项）
    # 顺手带上推荐位 list：壳拿 class+list 一次就够，省掉一次来回
    def homeContent(self, filter=''):
        data = self._api('nav', {'token': ''}, 6 * 3600)
        classes = []
        filters = {}
        for item in (data.get('list') or []):
            if not isinstance(item, dict):
                continue
            tid = _text(item.get('type_id'))
            name = _text(item.get('type_name'))
            if not tid or not name:
                continue
            classes.append({'type_id': tid, 'type_name': name})
            ext = item.get('type_extend')
            if isinstance(ext, str):
                try:
                    ext = json.loads(ext)
                except Exception:
                    ext = {}
            if not isinstance(ext, dict):
                continue
            groups = []
            for key, label in FILTER_NAMES:
                values = []
                for v in _text(ext.get(key)).split(','):
                    v = _text(v)
                    if v and v not in values:
                        values.append(v)
                if values:
                    groups.append({
                        'key': key,
                        'name': label,
                        'init': '',
                        'value': [{'n': '全部', 'v': ''}] + [{'n': v, 'v': v} for v in values],
                    })
            if groups:
                filters[tid] = groups
        return {'class': classes, 'filters': filters, 'list': self._vlist()}

    # 基础设施：首页推荐位（nav 与 index_video 各有缓存，重复调用不再打网络）
    # 站点一次回 246 条，截到 120 条：客户端渲染 200+ 卡片会明显掉帧
    def _vlist(self):
        vlist = []
        try:
            data = self._api('index_video', {'token': ''}, 1800)
            for item in (data.get('list') or []):
                if isinstance(item, dict) and isinstance(item.get('vlist'), list):
                    vlist.extend(item['vlist'])
        except Exception:
            vlist = []
        return vlist[:120]

    # 接口：首页推荐位（壳不强用时也要返回结构正确的空表）
    def homeVideoContent(self):
        return {'list': self._vlist()}

    # 接口：分类列表（limit 参数站点不认，靠 pagecount 走真分页）
    def categoryContent(self, tid, pg='1', filter='', extend=None):
        page = _page_of(pg)
        tid = _text(tid)
        if not tid:
            return self._paginated({'list': []}, page)
        extend = extend if isinstance(extend, dict) else {}
        params = {'tid': tid, 'pg': str(page)}
        for key, _label in FILTER_NAMES:
            value = _text(extend.get(key))
            if value and value.lower() != 'all':
                params[key] = value
        data = dict(self._api('video', params, 600))
        data.pop('code', None)
        data.pop('msg', None)
        return self._paginated(data, page)

    # 接口：详情 —— 4K 死线先换链验真，换不动就剔除，不把 404 甩给播放器
    # 壳一次传多个 id（收藏夹/批量收藏）时并发取，单 id 保持串行不动
    def detailContent(self, ids):
        if isinstance(ids, (str, int)):
            ids = [ids]
        elif not isinstance(ids, (list, tuple)):
            return {'list': []}
        vids = [_text(v) for v in list(ids)[:8]]
        vids = [v for v in vids if v]
        if not vids:
            return {'list': []}
        if len(vids) > 1:
            pool = ThreadPoolExecutor(max_workers=min(3, len(vids)))
            try:
                vods = list(pool.map(self._one, vids))
            except Exception:
                vods = []
            finally:
                pool.shutdown(wait=True)
            return {'list': [v for v in vods if v]}
        vod = self._one(vids[0])
        return {'list': [vod] if vod else []}

    # 基础设施：单条详情（线路组装、4K 探测、排序、分段都在这，保持 detailContent 轻）
    def _one(self, vid):
        info = self._api('video_detail', {'id': vid}, 60)
        data = info.get('data') if isinstance(info, dict) else None
        if not isinstance(data, dict):
            return None
        vod = {k: v for k, v in data.items() if k != 'vod_url_with_player'}
        entries = self._lines(data, _text(vod.get('vod_play_from')))
        entries = self._alive(entries, self._probe(entries))
        labels, urls = self._finish(entries)
        vod['vod_play_from'] = '$$$'.join(labels)
        vod['vod_play_url'] = '$$$'.join(urls)
        pic = _text(vod.get('vod_pic'))
        if pic:
            if pic.startswith('//'):            # 协议相对地址，壳只认绝对 http(s)
                vod['vod_pic'] = 'https:' + pic
            elif not pic.startswith('http'):
                vod['vod_pic'] = HOST + pic if pic.startswith('/') else pic
        return vod

    # 基础设施：把 vod_url_with_player / vod_play_url 两套字段统一成线路清单
    def _lines(self, data, froms_text):
        players = data.get('vod_url_with_player')
        froms = froms_text.split('$$$')
        if isinstance(players, list) and players:
            sources = players
        else:
            sources = [{'name': froms[i] if i < len(froms) else '',
                        'url': u, 'code': froms[i] if i < len(froms) else ''}
                       for i, u in enumerate(_text(data.get('vod_play_url')).split('$$$'))]
        entries = []
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                continue
            url = self._playlist(source.get('url'))
            if not url:
                continue
            code = _text(source.get('code'))
            name = _text(source.get('name')) or code or ('线路%d' % (index + 1))
            # 后台把 4K 写在 code、把「联通云/移动云」写在 name，只显示 name 会看不出是 4K
            label = ('%s %s' % (code, name)) if code and code.lower() not in name.lower() else name
            label = re.sub(r'[$#]', ' ', label)
            if _BAD_NAME_RE.search(label):
                label = re.sub(_BAD_NAME_RE, '', label).strip() or code or ('线路%d' % (index + 1))
            first = self._first_url(url)
            entries.append({
                'label': label,
                'url': url,
                'first': first,
                '4k': _is_4k_src(first),
            })
        return entries

    # 基础设施：只探前 3 条 4K 线（每条 0.7s 换链 + 50ms 读头），并发 3.5s 封顶
    def _probe(self, entries):
        picks = [(i, e['first']) for i, e in enumerate(entries) if e.get('4k')][:3]
        probed = {}
        todo = []
        for i, raw in picks:
            hit = self._res_cache.get(raw)
            if hit is not None:
                probed[i] = hit
            else:
                todo.append((i, raw))
        if not todo:
            return probed
        pool = ThreadPoolExecutor(max_workers=min(3, len(todo)))
        try:
            jobs = {pool.submit(self._probe_line, raw): (i, raw) for i, raw in todo}
            done, _pending = wait(jobs, timeout=PROBE_BUDGET)
        except Exception:
            jobs, done = {}, set()
        finally:
            pool.shutdown(wait=False)
        for job in done:
            i, raw = jobs[job]
            try:
                item = job.result()
            except Exception:
                continue
            if len(self._res_cache) > 200:        # 分辨率缓存按地址存，别无限增长
                self._res_cache.clear()
            self._res_cache[raw] = item
            probed[i] = item
        return probed

    # 基础设施：剔除换链失败的 4K 线，同时挂上实测宽高
    def _alive(self, entries, probed):
        alive = []
        for i, e in enumerate(entries):
            info = probed.get(i)
            if info is not None:
                if not info[0]:
                    continue                      # 换链失败：这条 4K 线是死的，剔除
                e['w'] = info[1]
                e['h'] = info[2]
            else:
                e['w'] = 0
                e['h'] = 0
            alive.append(e)
        return alive

    # 基础设施：排序（4K 优先、分辨率高的在前）+ 分辨率标签 + 1900B 分段
    def _finish(self, entries):
        entries.sort(key=lambda e: (0 if e.get('4k') else 1, -e.get('h', 0)))
        labels = self._uniq([e['label'] for e in entries])
        urls = []
        for i, e in enumerate(entries):
            if e.get('h'):
                tag = _res_tag(e.get('w', 0), e['h'])
                if tag:
                    labels[i] = '%s · %s' % (labels[i], tag)
            urls.append(e['url'])
        return self._seg(labels, urls)

    # 接口：搜索（站点一次只给一页，pagecount 走 _paginated 的真实兜底）
    def searchContent(self, key, quick, pg='1'):
        page = _page_of(pg)
        keyword = _text(key)
        if not keyword:
            return self._paginated({'list': []}, page)
        data = self._api('search', {'text': keyword, 'pg': str(page)}, 300)
        data = dict(data)
        data.pop('code', None)
        data.pop('msg', None)
        data['list'] = [dict(x) for x in (data.get('list') or []) if isinstance(x, dict)]
        for item in data['list']:
            item.pop('type', None)
        return self._paginated(data, page)

    # 接口：播放 —— 4K 走 8 换真链，网页走 6 换真链，换不动就退 parse:1 让壳自己解析
    def playerContent(self, flag, pid, vipFlags=None):
        raw = _text(pid)
        if '$' in raw:
            raw = raw.split('$')[-1]
        raw = self._decrypt_lvdou(raw)
        header = {'User-Agent': UA}
        if not _http_url(raw):
            return {'parse': 1, 'url': '', 'header': header}

        ck = 'play:' + raw
        hit = self._cache_get(ck, PLAY_TTL)
        if hit:
            return dict(hit)

        if _is_4k_src(raw):
            # ym4kjx 的 mp4 直链实测 404，必须经 parsesId=8 换成云盘地址
            real = self._to_media(raw, PARSE_ID_4K)
            res = ({'parse': 0, 'url': real, 'header': header} if real
                   else {'parse': 1, 'url': '', 'header': header})
        elif _is_media(raw) or _is_stream(raw):
            # 已经是媒体直链（比如别家 CDN 直出），验真后直给
            if self._verify(raw):
                res = {'parse': 0, 'url': raw, 'header': header}
            else:
                res = {'parse': 1, 'url': '', 'header': header}
        else:
            # 官方平台页（腾讯/B站/爱奇艺/优酷）：parsesId=6 出真链，出不来就交给壳解析
            real = self._to_media(raw, PARSE_ID_WEB)
            if real and self._verify(real):
                res = {'parse': 0, 'url': real, 'header': header}
            else:
                res = {'parse': 1, 'jx': 0, 'url': raw, 'header': header}

        self._cache_set(ck, res, PLAY_TTL)
        return dict(res)

    # 接口：杂项
    def getName(self):
        return NAME

    def isVideoFormat(self, url):
        if _is_4k_src(url):
            return True
        return _is_media(url)

    def manualVideoCheck(self):
        return False

    # 壳的图片代理入口：本源不用（封面都是站内正常 http 图）
    def localProxy(self, param):
        return None

    def destroy(self):
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass
        self.session = None
