# -*- coding: utf-8 -*-
# å½±æ¢4Kï¼ç± å½±æ¢4k.js ç§»æ¤å°é±¼å£³ webhtv ç«ç¹æ³¨å¥ä½¿ç¨ç Python Spiderã
# ç¨æ³ï¼ææ¬æä»¶æ¾å°ææº /sdcard/py/å½±æ¢4K.pyï¼ç«ç¹éç½® api å¡« file:///sdcard/py/å½±æ¢4K.py
#
# 2026-10-31 æ­æ¾ä¿®å¤ï¼å¨é¨ç»è®ºæ¥èªçå®è¯·æ±å®æµï¼éæ¨æµï¼ï¼
#   1) è§£ææ¥å£ http://fys.lyyytv.cn/api/index ä»ç¶æ´»çï¼ä½ parsesId=3 è¿æ¡è®°å½å·²ç»æ¥ä¸å°äºï¼
#      å¸¦ videoUrl è¯·æ±ç´æ¥æ PHP å¼å¸¸ï¼HTTP 500 / "Trying to get property 'url' of non-object"
#      ï¼Parses.php line 63ï¼ãæä¸¾ 1~12 ååªæ parsesId=5 æ­£å¸¸è¿å
#      {"code":200,"url":"https://baidu.con/..."}ï¼6ã7 è¿å {"code":0,"msg":"è§£æå¤±è´¥"}ï¼
#      å¶ä½å¨æ¯åä¸ä¸ª 500 éè¯¯é¡µãæä»¥è§£æä¸»çº¿è·¯æ¹ä¸º 5ï¼å¹¶ä¿ç 6/7 ä½ä¸ºååºéè¯ã
#   2) baidu.con åç¼ç AES è§£å¯é»è¾æ²¡æåï¼å 16 ä½å½ key å ivï¼ä½ä¸ base64 å¯æï¼AES/CBC/PKCS7ï¼ï¼
#      å®æµä»è½è§£åºçå® m3u8/mpd å°åï¼è¿æ®µä¿æåæ ·ã
#   3) å play() æææå°åæ æ¡ä»¶ä¸¢ç»è§£ææ¥å£ãä½ 4K(YD)/4K(BD) ä¸¤æ¡çº¿è·¯ç vod_play_url
#      æ¬èº«å°±æ¯ç´é¾ mp4ï¼http://ym4kjx.lyyytv.cn/d/file/xxx/çå4K.mp4ï¼ï¼
#      å°±ç®è§£ææ¥å£æ´»çï¼å¯¹ mp4 ç´é¾è¯·æ±ä¹åªä¼å¾å°ãè§£æå¤±è´¥ããç°å¨ç´é¾ç´æ¥äº¤ç»æ­æ¾å¨ï¼ä¸åç»è§£æã
#   4) 4K ç´é¾çæºç« ym4kjx.lyyytv.cn å·²ç»æ¬ç©ºï¼å®æµ 40 é¨å½±çå± 111 æ¡è¯¥ååç´é¾ï¼
#      éä¾¿åå¤æ¡é½æ¯ HTTP 404ï¼https æ¯ 502 Bad Gatewayï¼nginx åæºå¤±è´¥ï¼ã
#      è¿ä¸æ¯èæ¬è½ä¿®çï¼èæ¬æ¹æï¼è¯¦æé¡µæå·²ç¡®è®¤å¤±æçæºç«çº¿è·¯éèï¼æ­æ¾æ¶è¥ä»å½ä¸­ç»åºæç¡®æç¤ºï¼
#      é¿åç¨æ·ç¹è¿å»åªçå°é»å±ã
import base64
import json
import re
import time
import urllib.parse

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

try:
    from base.spider import Spider
except ImportError:
    import sys
    sys.path.append('..')
    from base.spider import Spider

KEY = 'yingtan4k'
HOST = 'http://cms.lyyytv.cn'
CMS_KEY = 'wP5bvxoc3yv7FoBQENFZuAF0EUYr4LTy'

# è§£ææ¥å£ï¼2026-10-31 å®æµï¼parsesId=3 å·²å¤±æè¿å HTTP 500ï¼parsesId=5 å¯ç¨ï¼
PARSE_API = 'http://fys.lyyytv.cn/api/index'
PARSE_APPID = '10001'
# è§£æçº¿è·¯ä¼åçº§ï¼5 æ¯å½åå¯ä¸ç¨³å®åºå°åçï¼6ã7 ä¼å¿«éè¿åãè§£æå¤±è´¥ãï¼çä½ååº
PARSE_IDS = (5, 6, 7)
HEADERS = {'User-Agent': 'okhttp/4.12.0'}
# è§£æè¯·æ±/åæºå¤´ï¼å¯¹é½ JS ç PHï¼é¿å gzip è±å±
PARSE_HEADERS = {'User-Agent': 'okhttp/4.12.0', 'Accept-Encoding': 'identity'}

# baidu.con åç¼å å¯å¸¸éï¼å¯¹é½ yt4k.jsï¼
DEC_PREFIX = 'https://baidu.con/'
# è§£æéè¯è½®æ°ä¸éé¿åºæ°ï¼ç§ï¼
PARSE_ROUNDS = 2
PARSE_BACKOFF = 0.3
# åä¸åå§å°åè§£æç»æç¼å­çªå£ï¼ç§ï¼
PLAY_CACHE_TTL = 120

PAGE_LIMIT = 20
# 2026-10-31ï¼nav ç type_extend å®éè¿å¸¦ star/director/state/versionï¼è¡¥ä¸æ å°
FILTER_NAMES = {
    'class': 'ç±»å', 'area': 'å°åº', 'lang': 'è¯­è¨', 'year': 'å¹´ä»½',
    'letter': 'å­æ¯', 'by': 'æåº', 'sort': 'é¡ºåº',
    'star': 'ä¸»æ¼', 'director': 'å¯¼æ¼', 'state': 'ç¶æ', 'version': 'çæ¬',
}
HOME_CACHE_TTL = 6 * 3600

# ç´é¾æºç«å¥åº·æ£æ¥ç¼å­ï¼ç§ï¼ï¼é¿åæ¯ä¸ªè¯¦æé¡µé½éå¤æ¢æµ
HOST_CHECK_TTL = 600
# æ¢æµæ¶åªè®¤è¿ä¸¤ä¸ªç¶æç ä¸ºãæºç«å·²å¤±æãï¼å¶ä½ä¸å¾æ¾è¡ï¼é¿åè¯¯æ
HOST_DEAD_STATUS = (404, 502)

_BASE64_RE = re.compile(r'(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?')
_LDMAX_RE = re.compile(r'^https?://ldmax\.cooom/', re.I)
_MEDIA_RE = re.compile(r'\.(?:mp4|m3u8?|flv|avi|mkv|ts|mov|wmv|webm|m4v|mpd)$', re.I)
_HOST_RE = re.compile(r'^https?://([^/]+)', re.I)

_home_cache = {}
_play_cache = {}
_host_cache = {}


def text(value):
    return '' if value is None else str(value).strip()


def page_of(value):
    m = re.match(r'\s*[+-]?\d+', '' if value is None else str(value))
    n = int(m.group(0)) if m else 0
    return max(1, n) if n else 1


def list_of(value):
    return value if isinstance(value, list) else []


def object_of(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def get_json(url, headers=None, timeout=15):
    headers = HEADERS if headers is None else headers
    rsp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    try:
        data = object_of(rsp.json())
    except Exception:
        data = {}
    if not data:
        raise Exception('å½±æ¢4Kï¼æ¥å£æªè¿åææ JSON')
    return data


def cms(path, params=None):
    params = params or {}
    query = urllib.parse.urlencode(params)
    data = get_json('%s/api.php/app/%s?%s' % (HOST, path, query))
    code = data.get('code')
    if code is not None:
        try:
            ok = int(code) in (1, 200)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            raise Exception('å½±æ¢4Kï¼CMS è¯·æ±å¤±è´¥')
    return data


def decode_base64(value):
    clean = re.sub(r'\s+', '', text(value))
    if not clean or not _BASE64_RE.fullmatch(clean):
        return None
    try:
        return base64.b64decode(clean)
    except Exception:
        return None


def decrypt_lvdou(value):
    """å¯¹é½ JS decUrlOneï¼lvdou+ â å16 key/å16 iv AES/CBC/PKCS7"""
    original = text(value)
    if not original.startswith('lvdou+'):
        return original
    if not CMS_KEY:
        return original
    try:
        encrypted = decode_base64(original[6:])
        if not encrypted:
            return original
        key = CMS_KEY[:16].encode('utf-8')
        iv = CMS_KEY[16:32].encode('utf-8') if len(CMS_KEY) >= 32 else key
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plain = unpad(cipher.decrypt(encrypted), AES.block_size)
        result = plain.decode('utf-8', errors='replace').strip()
        if result.startswith('http'):
            return result
    except Exception:
        pass
    return original


def is_http_url(value):
    try:
        parsed = urllib.parse.urlparse(text(value))
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


def is_site_url(value):
    if not is_http_url(value):
        return False
    host = (urllib.parse.urlparse(text(value)).hostname or '').lower()
    return host == 'lyyytv.cn' or host.endswith('.lyyytv.cn')


def is_ldmax_url(value):
    return bool(_LDMAX_RE.match(text(value)))


def decrypt_ldmax(value, depth=0):
    """å¼å®¹èå å¯ï¼ldmax.cooom åç¼"""
    if depth > 5:
        return ''
    url = text(value)
    decoded = decode_base64(url)
    if decoded:
        url = re.sub(r'\s+', '', decoded.decode('utf-8', errors='replace'))
    if not is_ldmax_url(url):
        return url
    path = _LDMAX_RE.sub('', url)
    if len(path) <= 16:
        return ''
    try:
        key = path[:16][::-1].encode('utf-8')
        encrypted = decode_base64(path[16:])
        if not encrypted or len(encrypted) % 16:
            return ''
        cipher = AES.new(key, AES.MODE_CBC, key)
        plain = bytearray(cipher.decrypt(encrypted))
        pad = plain[-1]
        if 0 < pad <= 16:
            del plain[-pad:]
        result = bytes(plain).decode('utf-8', errors='replace').strip()
        return decrypt_ldmax(result, depth + 1) if is_ldmax_url(result) else result
    except Exception:
        return ''


def find_url(value):
    """å¯¹é½ JS findUrlï¼ä»è§£æååº JSON ä¸­æåº url/playUrl/link/data.url"""
    if not isinstance(value, dict):
        return ''
    for key in ('url', 'playUrl', 'link'):
        v = value.get(key)
        if v:
            return text(v)
    return find_url(value.get('data'))


def resolve_parse(body):
    """
    å¯¹é½ JS resolveParseï¼
      1) JSON åè£¹ â ååº url
      2) https://baidu.con/ åç¼ â å16ä½ key=ivï¼ä½ä¸ base64 å¯æ AES/CBC/PKCS7
      3) ææ URL
    """
    body = text(body)
    if not body:
        return ''

    candidate = body
    if body.startswith('{'):
        try:
            parsed = json.loads(body)
            found = find_url(parsed)
            if found:
                candidate = found
        except Exception:
            pass

    if candidate.startswith(DEC_PREFIX):
        rest = candidate[len(DEC_PREFIX):]
        if len(rest) <= 16:
            return ''
        key = rest[:16].encode('utf-8')
        cipher_b64 = rest[16:]
        # ä¼åæ base64 å¯æè§£å¯ï¼å®æµè¿æ¡è·¯å¾ææï¼
        try:
            encrypted = base64.b64decode(cipher_b64 + '=' * (-len(cipher_b64) % 4), validate=False)
            cipher = AES.new(key, AES.MODE_CBC, key)
            plain = unpad(cipher.decrypt(encrypted), AES.block_size)
            result = plain.decode('utf-8', errors='replace').strip()
            if result.startswith('http'):
                return result
        except Exception:
            pass
        # ååºï¼å¯ææ¬èº«æ¯ raw bytes
        try:
            raw = cipher_b64.encode('latin-1', errors='ignore')
            if raw and len(raw) % 16 == 0:
                cipher = AES.new(key, AES.MODE_CBC, key)
                plain = unpad(cipher.decrypt(raw), AES.block_size)
                result = plain.decode('utf-8', errors='replace').strip()
                if result.startswith('http'):
                    return result
        except Exception:
            pass
        return ''

    return candidate


def parse_round(raw, parse_id):
    """ææå® parsesId è§£æä¸æ¬¡ï¼è¿åè§£åºççå®å°åï¼å¤±è´¥è¿åç©ºä¸²ï¼ã"""
    target = '%s?parsesId=%s&appid=%s&videoUrl=%s' % (
        PARSE_API, parse_id, PARSE_APPID, urllib.parse.quote(raw, safe="!'()*"))
    try:
        rsp = requests.get(target, headers=PARSE_HEADERS, timeout=20)
        # 2026-10-31ï¼parsesId å¤±ææ¶è¿éåçæ¯ HTTP 500 ç ThinkPHP éè¯¯é¡µï¼
        # ç´æ¥è·³è¿ï¼ä¸åä»»ä½è§£æï¼é¿åæ HTML å½æå°åã
        if rsp.status_code != 200 or not rsp.text:
            return ''
        if 'System Error' in rsp.text[:2000]:
            return ''
        resolved = resolve_parse(rsp.text)
        if resolved and resolved.startswith('http'):
            return resolved
    except Exception:
        pass
    return ''


def parse_url(raw):
    """å¯¹é½ JS play åé¨ï¼æåå§å°åæ¼å°è§£æåºååè¯·æ±ï¼è§£åºçå® URLã
    å¤ parsesId + å¤è½®éé¿ï¼ä»»ä¸æåå³è¿åã"""
    if not raw:
        return ''
    for rnd in range(PARSE_ROUNDS):
        if rnd > 0:
            time.sleep(rnd * PARSE_BACKOFF)
        for parse_id in PARSE_IDS:
            resolved = parse_round(raw, parse_id)
            if resolved:
                return resolved
    return ''


def is_media_url(url):
    if not is_http_url(url):
        return False
    return bool(_MEDIA_RE.search(urllib.parse.urlparse(text(url)).path))


def host_of(url):
    m = _HOST_RE.match(text(url))
    return m.group(1).lower() if m else ''


def host_dead(url):
    """æ¢æµç´é¾æºç«æ¯å¦è¿æ´»çã
    2026-10-31 å®æµ ym4kjx.lyyytv.cn ä¸ 111 æ¡ 4K ç´é¾å¨é¨ 404ï¼https 502ï¼ï¼
    è¿ç±»çº¿è·¯ç¹è¿å»å¿ç¶é»å±ï¼æåéèæ¯è®©ç¨æ·ç­è¶æ¶å¥½ã
    åªæ 404/502 å¤å®ï¼å¶ä½ç¶æç ä¸å¾è®¤ä¸ºå¯ç¨ï¼é¿åè¯¯ææ­£å¸¸ä½æç»ç®å½åè¡¨çæºç«ã"""
    host = host_of(url)
    if not host:
        return False
    cached = _host_cache.get(host)
    now = time.time()
    if cached and cached[0] > now:
        # ç¼å­éå­çå°±æ¯ãæ¯å¦å¤±æãï¼ç´æ¥è¿å
        return cached[1]
    dead = False
    try:
        rsp = requests.head('http://%s/d/file/' % host, headers=HEADERS, timeout=8,
                            allow_redirects=False)
        if rsp.status_code in HOST_DEAD_STATUS:
            dead = True
    except Exception:
        # æ¢æµæ¬èº«å¤±è´¥ï¼è¶æ¶/DNSï¼ä¸å½ä½å¤±æï¼äº¤ç»æ­æ¾å¨å®éè¯·æ±å»å¤å®
        dead = False
    _host_cache[host] = (now + HOST_CHECK_TTL, dead)
    return dead


def home(extend=''):
    cache_key = '%s_home_%s' % (KEY, text(extend))
    cached = _home_cache.get(cache_key)
    if cached and cached[0] > time.time():
        return cached[1]
    data = cms('nav', {'token': ''})
    classes = []
    filters = {}
    for item in list_of(data.get('list')):
        if not isinstance(item, dict):
            continue
        if item.get('type_id') is None or not text(item.get('type_name')):
            continue
        tid = text(item['type_id'])
        classes.append({'type_id': tid, 'type_name': text(item['type_name'])})
        ext = object_of(item.get('type_extend'))
        groups = []
        for key, name in FILTER_NAMES.items():
            values = [v for v in (text(x) for x in text(ext.get(key)).split(',')) if v]
            values = list(dict.fromkeys(values))
            if values:
                groups.append({
                    'key': key,
                    'name': name,
                    'init': '',
                    'value': [{'n': 'å¨é¨', 'v': ''}] + [{'n': v, 'v': v} for v in values],
                })
        if groups:
            filters[tid] = groups
    result = {'class': classes, 'filters': filters}
    if classes:
        _home_cache[cache_key] = (time.time() + HOME_CACHE_TTL, result)
    return result


def home_vod():
    data = cms('index_video', {'token': ''})
    vlist = []
    for item in list_of(data.get('list')):
        if isinstance(item, dict):
            vlist.extend(list_of(item.get('vlist')))
    return {'list': vlist}


def paginated(data, requested_page):
    lst = list_of(data.get('list'))
    raw_page = data.get('page')
    page = page_of(raw_page if raw_page is not None else requested_page)
    try:
        limit = int(data.get('limit') or 0)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        limit = PAGE_LIMIT
    try:
        raw_pagecount = int(data.get('pagecount') or 0)
    except (TypeError, ValueError):
        raw_pagecount = 0
    has_pagecount = raw_pagecount > 0
    pagecount = raw_pagecount if has_pagecount else page + (1 if len(lst) >= limit else 0)
    try:
        raw_total = data.get('total')
        has_total = raw_total is not None and int(raw_total) >= 0
    except (TypeError, ValueError):
        has_total = False
    if has_pagecount and has_total:
        total = int(data.get('total'))
    else:
        total = (page - 1) * limit + len(lst) + (1 if pagecount > page else 0)
    data['page'] = page
    data['pagecount'] = pagecount
    data['limit'] = limit
    data['total'] = total
    data['list'] = lst
    return data


def category(tid, pg, extend):
    page = page_of(pg)
    tid = text(tid)
    if not tid:
        return paginated({'list': []}, page)
    extend = extend if isinstance(extend, dict) else {}
    params = {'tid': tid, 'pg': str(page), 'limit': '18'}
    for key in FILTER_NAMES:
        value = text(extend.get(key))
        if value and value != 'all':
            params[key] = value
    return paginated(cms('video', params), page)


def playlist(value):
    parts = []
    for entry in text(value).split('#'):
        sep = entry.find('$')
        if sep <= 0 or not text(entry[sep + 1:]):
            continue
        parts.append('%s$%s' % (text(entry[:sep]), decrypt_lvdou(entry[sep + 1:])))
    return '#'.join(parts)


def detail(ids):
    if not isinstance(ids, (list, tuple)):
        ids = [ids]
    lst = []
    for vid in ids:
        vid = text(vid)
        if not vid:
            continue
        data = cms('video_detail', {'id': vid}).get('data')
        if not isinstance(data, dict):
            continue
        players = data.get('vod_url_with_player')
        vod = {k: v for k, v in data.items() if k != 'vod_url_with_player'}
        names = text(vod.get('vod_play_from')).split('$$$')
        if isinstance(players, list):
            sources = players
        else:
            sources = [
                {'name': names[i] if i < len(names) else '', 'url': u}
                for i, u in enumerate(text(vod.get('vod_play_url')).split('$$$'))
            ]
        froms = []
        urls = []
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                continue
            url = playlist(source.get('url'))
            if not url:
                continue
            # 2026-10-31ï¼æºç«æ´åå¤±æï¼å®æµ 4K ç´é¾ååå¨ 404ï¼ççº¿è·¯ä¸ä¸æ¶ï¼
            # å¦åç¨æ·ç¹è¿å»åªä¼é»å±ãå¥åº·æ£æ¥ç»ææååç¼å­ï¼ä¸å½±åå¶å®çº¿è·¯ã
            first_ep = text(url.split('#')[0].split('$')[-1])
            if is_media_url(first_ep) and host_dead(first_ep):
                continue
            name = text(source.get('name')) or text(source.get('code')) or 'çº¿è·¯%d' % (index + 1)
            froms.append(re.sub(r'[$#]', ' ', name))
            urls.append(url)
        vod['vod_play_from'] = '$$$'.join(froms)
        vod['vod_play_url'] = '$$$'.join(urls)
        lst.append(vod)
    return {'list': lst}


def search(key, pg):
    wd = text(key)
    page = page_of(pg)
    if not wd:
        return paginated({'list': []}, page)
    data = cms('search', {'text': wd, 'pg': str(page)})
    lst = []
    for item in list_of(data.get('list')):
        if isinstance(item, dict):
            lst.append({k: v for k, v in item.items() if k != 'type'})
    data['list'] = lst
    return paginated(data, page)


def play(play_id):
    """å¯¹é½ JS playï¼è§£æåºçå®å°ååäº¤æ­æ¾å¨ã
    2026-10-31 ä¿®å¤è¦ç¹ï¼
      - ç´é¾ï¼mp4/m3u8/mpdâ¦ï¼ä¸åç»è§£ææ¥å£ï¼è§£ææ¥å£å¯¹ mp4 ç´é¾åªä¼åãè§£æå¤±è´¥ãï¼
      - è§£æçº¿è·¯ä» parsesId=3 æ¢æ 5ï¼3 å·² 500ï¼ï¼å¹¶ä¿ç 6/7 ååºï¼
      - ä»»ä½å¤±è´¥é½è¿åç»æåæ³ç dict å¹¶å¸¦ msgï¼è®©å£³è½æ¾ç¤ºåå èä¸æ¯ç½å±ã
    """
    original = decrypt_lvdou(play_id)
    if not original:
        return {'parse': 0, 'url': '', 'header': dict(PARSE_HEADERS),
                'msg': 'å½±æ¢4Kï¼æ­æ¾å°åä¸ºç©º'}

    # å¼å®¹èå å¯ï¼ldmax åç¼åæ¬å°è§£å¯
    if is_ldmax_url(original):
        decrypted = decrypt_ldmax(original)
        if decrypted:
            original = decrypted

    # ç´é¾ä¼åï¼å·²ç»æ¯å¯æ­åªä½æä»¶å°±ä¸å¿è§£æ
    if is_media_url(original):
        if host_dead(original):
            return {'parse': 0, 'url': '', 'header': dict(PARSE_HEADERS),
                    'msg': 'å½±æ¢4Kï¼è¯¥çº¿è·¯æºç«å·²å¤±æï¼HTTP 404ï¼ï¼è¯·æ¢å¶å®çº¿è·¯'}
        return {'parse': 0, 'url': original, 'header': dict(PARSE_HEADERS)}

    # è§£æç»æç¼å­
    now = time.time()
    cached = _play_cache.get(original)
    if cached and cached[0] > now:
        return {'parse': 0, 'url': cached[1], 'header': dict(PARSE_HEADERS)}

    resolved = parse_url(original)
    if resolved:
        _play_cache[original] = (now + PLAY_CACHE_TTL, resolved)
        return {'parse': 0, 'url': resolved, 'header': dict(PARSE_HEADERS)}

    # è§£ææ´æ¡é¾è·¯å¤±è´¥ï¼ç»åºå¯è¯»åå ï¼ç­ç¨æ·åé¦å·ä½çº¿è·¯
    return {'parse': 0, 'url': '', 'header': dict(PARSE_HEADERS),
            'msg': 'å½±æ¢4Kï¼è§£æå¤±è´¥ï¼è§£ææ¥å£è¿åå¼å¸¸æè¯¥çº¿è·¯æä¸å¯ç¨ï¼ï¼è¯·æ¢çº¿è·¯éè¯'}


class Spider(Spider):
    def getName(self):
        return 'ð¬ å½±æ¢4K'

    def init(self, extend=''):
        self.extend = extend or ''

    def isVideoFormat(self, url):
        return is_media_url(url)

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        return home(self.extend)

    def homeVideoContent(self):
        return home_vod()

    def categoryContent(self, tid, pg, filter, extend):
        return category(tid, pg, extend)

    def detailContent(self, ids):
        return detail(ids)

    def searchContent(self, key, quick, pg='1'):
        return search(key, pg)

    def playerContent(self, flag, id, vipFlags):
        return play(id)

    def localProxy(self, param):
        return None

    def destroy(self):
        pass


# ---- 影视猫兼容层（追加，不改动原有逻辑）----
_orig_homeContent_ = Spider.homeContent
_orig_playerContent_ = Spider.playerContent

def _homeContent_cm(self, filter=False):
    r = _orig_homeContent_(self, filter)
    try:
        if isinstance(r, dict) and not r.get('list'):
            cls = r.get('class') or []
            if cls:
                c = self.categoryContent(cls[0]['type_id'], 1, False, {})
                lst = (c or {}).get('list') or []
                if lst:
                    r = dict(r); r['list'] = lst[:12]
    except Exception:
        pass
    return r

def _playerContent_cm(self, flag, id, vipFlags):
    r = _orig_playerContent_(self, flag, id, vipFlags)
    try:
        if isinstance(r, dict) and 'parse' in r:
            r['parse'] = int(r['parse'])
    except Exception:
        pass
    return r

Spider.homeContent = _homeContent_cm
Spider.playerContent = _playerContent_cm
