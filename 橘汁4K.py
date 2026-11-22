# -*- coding: utf-8 -*-
# 橘汁视频 TVBox spider — 华谊同款协议栈移植
# v3.0.8.0 修复版 v3（2026-11-21，基于 upload-afaff165_fixed_v3.0.8.0_v2.py）：
#  v2 实测（2026-11-21 20:50）：分类只剩 5 个兜底、逐集跳过依旧。本次按 APK 再查修三处：
#  (1) tag/list 的 data 是加密串：App 走 getData(ConfigCateList.class, true)，
#  先双重 AES-ECB 解密（先 SAFECODE、后 SAFE，每步 base64 解→解密→UTF-8），v2
#  按明文 JSON 解析，逐字符迭代得 0 个 tab 才落到兜底。已补纯 Python AES 解密
#  （TVBox 上无 PyCryptodome 时用）+ 多种形态兼容解析；只发 GET，删掉错误的
#  POST _secure('') 兜底；按 state==1 过滤（CateBean 没有 enable 键）。
#  (2) 逐集跳过：direct==0 时 App 不解析 redirect，v2 却总是提前解析一次，
#  短时效签名地址到手就过期。已改成只在 direct==1 时解析跳转（最多跟 5 跳）；
#  direct==0 和详情里的直链原样返回。msg 非空 App 只弹提示不阻止播放，v2
#  之前直接判失败也改回来了。另：androidPlayCore=1(TX)/2(Ali) 是私有加密流，
#  TVBox 通用播放器解不开（能读到时长、分片全失败→逐集跳），spider 层面无解，
#  只能在详情页把第一集的核/direct 标在备注里供判断，并请用户确认官方 APP 能否播。
#  (3) 分集：同时读 DramaVideoBean field 13=episode、14=isVip；标题数字与
#  episode 号对不上的条目（预告/错集）跳过，VIP 集在集名后标 (VIP)。

#  本次修两处（用户截图实测 2026-11-21 20:15-20:17）：
#  (1) 分类错位：homeContent 原来用 /api/v3/drama/getCategory（那是直播频道页的接口，
#  返回的是频道分类 id，没有 typeId），拿它的 id 当 typeId1 去查 drama/category，
#  结果电影出电视剧、剧集出综艺、动漫出直播、综艺出动漫，短剧/漫剧空。已改成
#  用 /api/ex/v3/security/tag/list（带 _hdr）取 CateBean.typeId，mode==1 才走
#  drama/category；短剧走 api/v3/drama/getShortVideo?typeId=40；mode!=1 的 tab
#  用 tag/list 自带的 bannerList/sections，取不到就返回空，不再串内容。
#  兜底列表只用实测确认过的：剧集=21、综艺=22、动漫=26、直播=25；电影/漫剧的
#  typeId 在 APK 里没有硬编码表，必须由 tag/list 实时返回，编一个会再次错位。
#  (2) 个别集有进度条却跳过（如主角第4集 42:00/42:00 黑屏转圈）：playerContent
#  原来用正则抓 videoUsableUrl 原始 protobuf 里的第一个 http 链接，丢掉了
#  服务端返回的 per-URL headers（ParsePlayUrlBean field 6），也没做 APP 必做的
#  跳转解析。已改成按字段号解析：field 1=playUrl、field 6=headers map、
#  field 9=msg（非空即失败不播）、field 5=direct；先按 APP 方式解析一次跳转
#  （3xx 取 Location，2xx 用原地址），再把 field 6 的 headers 一并交给播放器。
#  未修：漫剧的独立接口在 APK 里没找到，待 tag/list 给出它的 mode/typeId 再接。

#  来源：官网 juzi5.app -> 蓝奏云 橘汁_v3.0.8.0.apk（99.5M），已拆包核对。
#  新值（已独立验算）：HOST=http://juziappcc.hzhcbkj.cn（注意是 http，不是 https；
#  由 az.txt 动态下发：tenxuncos.gexuanyi.top/az.txt -> {"domain":"http://juziappcc.hzhcbkj.cn","enabled":true}，
#  本机 curl 已复核；旧 host 已死，curl HTTP 000）；
#  PKG=com.asjdhjhd.mgd.p3，VC=3080，vName=3.0.8.0；
#  证书用 v1 签名（META-INF/CERT.RSA，O=waibuzuanyong）：CERT_MD5=3A4A23871C21D1F00D75C58AB5F688F8，
#  CERT_SHA1=8F2E5859B53F5F488F7021A07B7EFA62EB8FEDBD（注意 APK 里还有一套不同的 v2/v3 证书，应用不用它）；
#  SAFECODE=ZU1DSFFWNENKMDYXVUQRN0ZJDUC4PQ==，由新 PKG/VC/证书指纹按原公式算出，
#  已用 PyCryptodome 独立验算：旧值用旧常量能复现 OW1WBLFZCLJ0WTNJQMRSZ2DYSGNBPT0=，新值一致。
#  SAFE、PW_SAFE、PUB1_B64 与旧版相同，未变；接口路径未变。
#  安全/健壮性沿用上一修复版：_http 默认验签、只允许新 HOST；secrets 生成 udid/nonce；
#  _history_list 用本次登录的 tv_<udid>；Crypto 可选（纯 Python 回退）；init() 失败置 _ready=False。
#  未验证的风险（务必先在手机/TVBox 上实测）：(1) paramsData 在新版改由 native 库
#  libBaseNativeJNI.so 的 method01 生成，NATIVE_K 在 dex 和 .so 明文里都找不到，
#  本文件先沿用旧值 ed5fdsgucxumegqa，若服务端拒收 paramsData，需在真机上抓包/hook 提取新 native key；
#  (2) 本机出口 IP 被新站 WAF（TencentEdgeOne）挡，实测新 host 根路径 HTTP 567，
#  _zone/_login 无法在本机跑通，分类/搜索/播放必须在未被挡的网络（手机/国内 IP）上实测；
#  (3) site_config 是广告配置（cypher=2，未解出也不影响视频接口），不用管。
#  未修：AES-ECB / AES-CBC(key=IV) / RSA PKCS1 v1.5 均为服务端协议要求；硬编码密钥仍在。
import json
import re
import time
import base64
import string
import secrets
import hashlib
import ssl
import urllib.request
import urllib.error
import urllib.parse

try:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5, AES
    from Crypto.Util.Padding import pad as _crypto_pad
    _CRYPTO_OK = True
except Exception:
    RSA = None
    PKCS1_v1_5 = None
    AES = None
    _crypto_pad = None
    _CRYPTO_OK = False

try:
    from base.spider import Spider as _Base
except Exception:
    class _Base:
        pass

PUB1_B64 = 'MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCr8SzZhjYy+rsya1K09t8d2K50pWFoBkgUqMpKOiW+3IEVKd4eTdvg9RSOjQ82kypL6R9BnsmrS1V8s4PVDwjQbUtYhTPPC9Hz16qY7rpD6m0d2vr09/UpWQ5uOy9PR0QTrsioveZ+DIe9jc3C+zBCu/kZSY/R8stwJoiitki3gwIDAQAB'
NATIVE_K = b'ed5fdsgucxumegqa'
SAFE = b'OC1A06E197EF10CF3F6058CA7A803B5E'
PW_SAFE = b'11GK2we32144LO&hilUITB)FMd1khdaF'
CERT_MD5 = '3A4A23871C21D1F00D75C58AB5F688F8'
CERT_SHA1 = '8F2E5859B53F5F488F7021A07B7EFA62EB8FEDBD'
PKG = 'com.asjdhjhd.mgd.p3'
VC = '3080'
HOST = 'http://juziappcc.hzhcbkj.cn'
UA = 'okhttp/3.12.1'


# ---------- 纯 Python AES/RSA 回退（无 PyCryptodome 时用；仅加密方向） ----------
def _pad(data, bs=16):
    if _CRYPTO_OK and _crypto_pad is not None:
        return _crypto_pad(data, bs)
    _p = bs - len(data) % bs
    return data + bytes([_p]) * _p


def _xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _gmul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xt(a)
    return r


def _gen_sbox():
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x ^= _xt(x)
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    sbox = [0x63] * 256
    for i in range(1, 256):
        inv = exp[255 - log[i]]
        s = inv
        for sh in range(1, 5):
            s ^= ((inv << sh) | (inv >> (8 - sh))) & 0xFF
        sbox[i] = s ^ 0x63
    return sbox


_SBOX = _gen_sbox()
_M2 = [_gmul(i, 2) for i in range(256)]
_M3 = [_gmul(i, 3) for i in range(256)]
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB]


def _aes_expand(key):
    nk = len(key) // 4
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(w[i - 1])
        if i % nk == 0:
            t = [_SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        w.append([w[i - nk][j] ^ t[j] for j in range(4)])
    return w, nr


def _aes_block(sched, block):
    w, nr = sched
    st = list(block)
    for i in range(16):
        st[i] ^= w[i >> 2][i & 3]
    for rnd in range(1, nr + 1):
        for i in range(16):
            st[i] = _SBOX[st[i]]
        t = list(st)
        for r in range(1, 4):
            for c in range(4):
                st[4 * c + r] = t[4 * ((c + r) % 4) + r]
        if rnd != nr:
            for c in range(4):
                b = 4 * c
                a0, a1, a2, a3 = st[b], st[b + 1], st[b + 2], st[b + 3]
                st[b] = _M2[a0] ^ _M3[a1] ^ a2 ^ a3
                st[b + 1] = a0 ^ _M2[a1] ^ _M3[a2] ^ a3
                st[b + 2] = a0 ^ a1 ^ _M2[a2] ^ _M3[a3]
                st[b + 3] = _M3[a0] ^ a1 ^ a2 ^ _M2[a3]
        rk = 4 * rnd
        for i in range(16):
            st[i] ^= w[rk + (i >> 2)][i & 3]
    return bytes(st)


def _aes_ecb_encrypt(key, data):
    if _CRYPTO_OK:
        return AES.new(key, AES.MODE_ECB).encrypt(data)
    sched = _aes_expand(key)
    return b"".join(_aes_block(sched, data[i:i + 16]) for i in range(0, len(data), 16))


def _aes_cbc_encrypt(key, iv, data):
    if _CRYPTO_OK:
        return AES.new(key, AES.MODE_CBC, iv).encrypt(data)
    sched = _aes_expand(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
        enc = _aes_block(sched, block)
        out += enc
        prev = enc
    return bytes(out)


_INV_SBOX = [0] * 256
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_M9 = [_gmul(i, 9) for i in range(256)]
_M11 = [_gmul(i, 11) for i in range(256)]
_M13 = [_gmul(i, 13) for i in range(256)]
_M14 = [_gmul(i, 14) for i in range(256)]


def _aes_block_decrypt(sched, block):
    w, nr = sched
    st = list(block)
    for i in range(16):
        st[i] ^= w[4 * nr + (i >> 2)][i & 3]
    for rnd in range(nr - 1, 0, -1):
        t = list(st)
        for r in range(1, 4):
            for c in range(4):
                st[4 * c + r] = t[4 * ((c - r) % 4) + r]
        for i in range(16):
            st[i] = _INV_SBOX[st[i]]
        rk = 4 * rnd
        for i in range(16):
            st[i] ^= w[rk + (i >> 2)][i & 3]
        for c in range(4):
            b = 4 * c
            a0, a1, a2, a3 = st[b], st[b + 1], st[b + 2], st[b + 3]
            st[b] = _M14[a0] ^ _M11[a1] ^ _M13[a2] ^ _M9[a3]
            st[b + 1] = _M9[a0] ^ _M14[a1] ^ _M11[a2] ^ _M13[a3]
            st[b + 2] = _M13[a0] ^ _M9[a1] ^ _M14[a2] ^ _M11[a3]
            st[b + 3] = _M11[a0] ^ _M13[a1] ^ _M9[a2] ^ _M14[a3]
    t = list(st)
    for r in range(1, 4):
        for c in range(4):
            st[4 * c + r] = t[4 * ((c - r) % 4) + r]
    for i in range(16):
        st[i] = _INV_SBOX[st[i]]
    for i in range(16):
        st[i] ^= w[i >> 2][i & 3]
    return bytes(st)


def _aes_ecb_decrypt(key, data):
    if _CRYPTO_OK:
        return AES.new(key, AES.MODE_ECB).decrypt(data)
    sched = _aes_expand(key)
    return b"".join(_aes_block_decrypt(sched, data[i:i + 16]) for i in range(0, len(data), 16))


def _unpad(data):
    if not data:
        raise ValueError('empty block')
    n = data[-1]
    if n < 1 or n > 16 or data[-n:] != bytes([n]) * n:
        raise ValueError('bad padding')
    return data[:-n]


def _double_decrypt_str(s):
    # tag/list 等安全端点的 data 加密：外层 SAFECODE、内层 SAFE，各 AES-ECB/PKCS7
    s = s.strip()
    raw = base64.b64decode(s + '=' * (-len(s) % 4))
    step = _unpad(_aes_ecb_decrypt(SAFECODE.encode(), raw)).decode('utf-8')
    step = step.strip()
    raw = base64.b64decode(step + '=' * (-len(step) % 4))
    return _unpad(_aes_ecb_decrypt(SAFE, raw)).decode('utf-8')


def _der_len(buf, i):
    b = buf[i]
    i += 1
    if b < 128:
        return b, i
    n = b & 0x7F
    return int.from_bytes(buf[i:i + n], "big"), i + n


def _rsa_n_e(der):
    if isinstance(der, str):
        der = base64.b64decode(der)
    if der.startswith(b"-----"):
        body = b"".join(l.strip() for l in der.splitlines() if not l.startswith(b"-----"))
        der = base64.b64decode(body)
    ints = []

    def walk(b):
        i = 0
        while i < len(b):
            if i + 2 > len(b):
                break
            tag = b[i]
            try:
                ln, j = _der_len(b, i + 1)
            except Exception:
                break
            if j + ln > len(b):
                break
            val = b[j:j + ln]
            if tag == 0x02:
                ints.append(int.from_bytes(val, "big"))
            elif tag in (0x30, 0x31, 0xA0, 0x03):
                walk(val[1:] if tag == 0x03 else val)
            i = j + ln

    walk(der)
    if len(ints) < 2:
        raise ValueError("cannot parse RSA public key")
    return ints[0], ints[1]


def _rsa_encrypt(der_bytes, data):
    if _CRYPTO_OK:
        return PKCS1_v1_5.new(RSA.import_key(der_bytes)).encrypt(data)
    n, e = _rsa_n_e(der_bytes)
    k = (n.bit_length() + 7) // 8
    if len(data) > k - 11:
        raise ValueError("RSA plaintext too long")
    ps_len = k - len(data) - 3
    ps = bytearray()
    while len(ps) < ps_len:
        b = secrets.token_bytes(1)
        if b != b"\x00":
            ps += b
    em = b"\x00\x02" + bytes(ps) + b"\x00" + data
    return pow(int.from_bytes(em, "big"), e, n).to_bytes(k, "big")


_e = base64.b64encode(_aes_ecb_encrypt(PW_SAFE, _pad(
    (CERT_MD5 + '######' + CERT_SHA1 + '~~~~~~' + PKG + '>>>+++' + VC).encode(), 16))).decode()
_e2 = base64.b64encode(_e.encode()).decode()
SAFECODE = (_e2[:16] + _e2[-16:]).upper()


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
        b = buf[i]; fn, wt = b >> 3, b & 7; i += 1
        if wt == 0:
            v = 0; sh = 0
            while i < n:
                x = buf[i]; i += 1
                v |= (x & 0x7f) << sh; sh += 7
                if not x & 0x80:
                    break
            out.append((fn, wt, v))
        elif wt == 2:
            ln = 0; sh = 0
            while i < n:
                x = buf[i]; i += 1
                ln |= (x & 0x7f) << sh; sh += 7
                if not x & 0x80:
                    break
            if i + ln > n:
                break
            out.append((fn, wt, buf[i:i + ln])); i += ln
        elif wt == 5:
            out.append((fn, wt, buf[i:i + 4])); i += 4
        elif wt == 1:
            out.append((fn, wt, buf[i:i + 8])); i += 8
        else:
            i += 1
    return out


def _rnd(k):
    CH = string.ascii_letters + string.digits
    return ''.join(secrets.choice(CH) for _ in range(k - 1)) + '='


class Spider(_Base):
    HOST_NAME = '橘汁视频'

    def getName(self):
        return '橘汁视频'

    _cur_id = ''

    def init(self, extend=''):
        # udid 原来是 md5(time.time())，可预测且易碰撞，改用 secrets。
        self.udid = secrets.token_hex(8).upper()
        self._username = 'tv_%s' % self.udid[:10].lower()
        self._rsa1_der = base64.b64decode(PUB1_B64)
        self._rsa2_der = None
        self._rsa2 = None
        self._tab_modes = {}
        self._tab_names = {}
        self._tab_sections = {}
        self._token = ''
        self._ready = False
        try:
            self._login()
        except Exception:
            self._token = ''
        try:
            self._ready = self._zone()
        except Exception:
            self._ready = False

    def _http(self, url, data=None, headers=None):
        # 只允许本 spider 的 host；之前无条件不验证证书，改用默认验证。
        host = urllib.parse.urlparse(url).netloc
        if host != urllib.parse.urlparse(HOST).netloc:
            raise ValueError('host not allowed: %s' % host)
        req = urllib.request.Request(url, data=data, headers=headers or {})
        ctx = ssl.create_default_context()
        return urllib.request.urlopen(req, timeout=25, context=ctx).read()

    def _login(self):
        try:
            body = json.dumps({'username': self._username,
                               'password': hashlib.md5(('tv' + self.udid).encode()).hexdigest(),
                               'udid': self.udid}).encode()
            try:
                self._http(HOST + '/api/ex/v3/user/register', body, {
                    'User-Agent': UA, 'Content-Type': 'application/json'})
            except Exception:
                pass
            d = self._http(HOST + '/api/ex/v3/user/login', body, {
                'User-Agent': UA, 'Content-Type': 'application/json'})
            data = json.loads(d).get('data') or {}
            self._token = (data.get('token') or (data.get('user') or {}).get('token') or '')
        except Exception:
            self._token = ''

    def _zone(self):
        ts = int(time.time() * 1000)
        rnd = _rnd(16)
        sign = base64.b64encode(_rsa_encrypt(self._rsa1_der, (str(ts) + rnd).encode())).decode()
        body = (_f(1, 0, _varint(ts)) + _f(2, 2, sign.encode()) +
                _f(3, 2, rnd.encode()) + _f(4, 2, rnd.encode()) + _f(5, 2, rnd.encode()))
        P = {'plat': 'android', 'vOs': '16', '_vOsCode': '36', 'vApp': VC,
             'vName': '3.0.8.0', 'pkg': PKG,
             'appName': '%E6%A9%98%E6%B1%81',
             'udid': self.udid, 'uuid': self.udid, 'chid': '10000',
             'androidID': self.udid, 'net': '1', 'young': 0, 'tenantId': '*',
             'v': 1, 'device': 0, 'lang': 'zh', 'country': 'CN', 'cpu': 'arm64-v8a'}
        d = self._http(HOST + '/api/v5/find/app/zone', body, {
            'User-Agent': UA, 'Content-Type': 'application/x-protobuf',
            'Accept': 'application/x-protobuf', 'Cache-Control': 'no-cache',
            'publicParams': json.dumps(P, separators=(',', ':'))})
        top = _pb(d)
        inner_list = [v for fn, wt, v in top if fn == 3 and wt == 2]
        if not inner_list:
            return False
        strs = {fn: v for fn, wt, v in _pb(inner_list[0]) if wt == 2}
        if not all(k in strs for k in (2, 3, 4, 5)):
            return False
        try:
            self._rsa2_der = base64.b64decode(strs[2] + strs[3] + strs[4] + strs[5])
            # 校验能解析出 n/e，解析失败即视为 zone 未就绪
            _rsa_n_e(self._rsa2_der)
        except Exception:
            self._rsa2_der = None
            return False
        self._rsa2 = True
        return True

    def _hdr(self):
        if not getattr(self, '_rsa2_der', None):
            raise RuntimeError('zone not ready: _rsa2 missing')
        ts = int(time.time() * 1000)
        rnd = _rnd(16)
        sig = base64.b64encode(_rsa_encrypt(self._rsa2_der, (str(ts) + rnd + VC).encode())).decode()
        # 注意：AES-ECB 是服务端协议要求，改模式会断协议，此处只能保留。
        ao = base64.b64encode(_aes_ecb_encrypt(SAFE, _pad((str(ts) + rnd).encode(), 16))).decode()
        J = {'country': 'CN', 'vName': '3.0.8.0', 'cpuId': '', 'young': 0,
             'facturer': 'OnePlus', 'pkg': PKG, 'uuid': self.udid,
             'resolution': '1080x2256', 'mac': '02%3A00%3A00%3A00%3A00%3A00',
             'sig': sig, 'abid': '7470', 'model': 'PJX110', 'plat': 'android',
             'udid': self.udid, 'dpi': '480', 'net': '1', 'lang': 'zh',
             'random_str': rnd, 'brand': 'OnePlus', 'timestamp': ts,
             'density': '3.0', 'appName': '%E6%A9%98%E6%B1%81',
             'cpu': 'arm64-v8a', 'chid': '10000', 'carrier': '%E8%81%94%E9%80%9A',
             'sig2': ao[:8], 'v': 1, 'sig3': ao[8:], 'tenantId': '*',
             '_vOsCode': '36', 'vOs': '16', 'vApp': VC, 'device': 0,
             'androidID': self.udid}
        blob = json.dumps(J, separators=(',', ':'), ensure_ascii=False).encode()
        # 注意：CBC 且 key=IV 是服务端协议要求，改模式会断协议，此处只能保留。
        pd_hex = _aes_cbc_encrypt(NATIVE_K, NATIVE_K, _pad(blob, 16)).hex()
        h = {'User-Agent': UA, 'Accept': 'application/json',
             'Cache-Control': 'no-cache',
             'publicParams': json.dumps({'paramsData': pd_hex}, separators=(',', ':'))}
        if self._token:
            h['token'] = self._token
        return h

    def _secure(self, mapkv):
        if not getattr(self, '_rsa2_der', None):
            raise RuntimeError('zone not ready: _rsa2 missing')
        ts = int(time.time() * 1000)
        rnd8 = _rnd(8)
        plain = (mapkv + str(ts)).encode()
        ct = _aes_ecb_encrypt(SAFECODE.encode(), _pad(plain, 16))
        b64 = base64.b64encode(ct).decode()
        return (_f(1, 2, (rnd8 + b64[:12]).encode()) +
                _f(2, 2, b64[12:].encode()) +
                _f(3, 2, _rnd(20).encode()) + _f(4, 0, _varint(ts)) +
                _f(5, 2, rnd8.encode()))


    def _resolve_redirect(self, url, headers=None):
        # 按 APP 做法：一次不跟随跳转的请求；3xx 取 Location，2xx 用原地址；失败用原地址。
        try:
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers):
                    return None
            hdrs = dict(headers or {})
            hdrs.setdefault('User-Agent', UA)
            req = urllib.request.Request(url, headers=hdrs, method='GET')
            opener = urllib.request.build_opener(_NoRedirect)
            try:
                resp = opener.open(req, timeout=10)
                code = resp.getcode()
                loc = resp.headers.get('Location')
                resp.close()
            except urllib.error.HTTPError as e:
                code = e.code
                loc = e.headers.get('Location') if e.headers else None
            if code in (301, 302, 303, 307, 308) and loc:
                return urllib.parse.urljoin(url, loc)
        except Exception:
            pass
        return url

    def _resolve_redirect_chain(self, url, headers=None):
        # App 用 OkHttp 默认跟随整条跳转链；只解一跳会拿到中间地址
        for _ in range(5):
            nxt = self._resolve_redirect(url, headers)
            if nxt == url:
                break
            url = nxt
        return url

    def _usable_url_info(self, pf, pu):
        # 返回 (play_url, headers, msg, direct, androidPlayCore)
        hh = self._hdr()
        hh['Content-Type'] = 'application/x-protobuf'
        hh['Accept'] = 'application/x-protobuf'
        qs = 'vodPlayFrom=%s&playUrl=%s' % (
            urllib.parse.quote(pf), urllib.parse.quote(pu, safe=''))
        d = self._http(HOST + '/api/proto/v5/videoUsableUrl',
                       self._secure(qs), hh)
        top = _pb(d)
        code = [v for fn, wt, v in top if fn == 1 and wt == 0]
        if (code[0] if code else 0) != 200:
            raise ValueError('videoUsableUrl code != 200')
        data = [v for fn, wt, v in top if fn == 3 and wt == 2]
        if not data:
            raise ValueError('videoUsableUrl no data')
        play_url, headers, msg, direct, core = self._parse_play_url(data[0])
        return play_url, headers, msg, direct, core

    def _parse_play_url(self, data):
        # ParsePlayUrlBean：1=playUrl，5=direct，6=headers map，7=androidPlayCore(字符串)，9=msg
        # androidPlayCore：1=TX 2=Ali 3=IJK 4=EXO 5=SYS；1/2 是私有加密流，TVBox 通用播放器解不开
        play_url = ''
        msg = ''
        core = ''
        direct = 0
        headers = {}
        try:
            for fn, wt, v in _pb(data):
                if fn == 1 and wt == 2:
                    play_url = v.decode('utf-8', 'replace')
                elif fn == 5 and wt == 0:
                    direct = int(v)
                elif fn == 7 and wt == 2:
                    core = v.decode('utf-8', 'replace')
                elif fn == 9 and wt == 2:
                    msg = v.decode('utf-8', 'replace')
                elif fn == 6 and wt == 2:
                    k = ''
                    val = ''
                    for f2, w2, v2 in _pb(v):
                        if f2 == 1 and w2 == 2:
                            k = v2.decode('utf-8', 'replace')
                        elif f2 == 2 and w2 == 2:
                            val = v2.decode('utf-8', 'replace')
                    if k:
                        headers[k] = val
        except Exception:
            pass
        return play_url, headers, msg, direct, core

    def _short_list(self, pg=1):
        # 短剧：api/v3/drama/getShortVideo?pagesize=20&page=1&typeId=40&orderBy=vod_id
        out = []
        try:
            pg = max(1, int(pg or 1))
        except Exception:
            pg = 1
        try:
            hh = self._hdr()
            hh['Accept'] = 'application/json'
            d = self._http(HOST + '/api/v3/drama/getShortVideo?pagesize=20&page=%d&typeId=40&orderBy=vod_id' % pg,
                           None, hh)
            try:
                j = json.loads(d)
                items = j.get('data') or j.get('list') or []
                if isinstance(items, dict):
                    items = items.get('list') or []
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    vid = it.get('id') or it.get('vod_id') or it.get('videoId') or ''
                    nm = it.get('name') or it.get('vod_name') or it.get('title') or ''
                    if vid and nm:
                        out.append({'vod_id': str(vid), 'vod_name': nm,
                                    'vod_pic': it.get('pic') or it.get('vod_pic') or it.get('cover') or '',
                                    'vod_remarks': it.get('remarks') or it.get('vod_remarks') or ''})
                if out:
                    return out
            except Exception:
                pass
            # 非 JSON 时按 _list 的 protobuf 结构兜底解析
            top = _pb(d)
            datas = [v for fn, wt, v in top if fn == 3 and wt == 2]
            if datas:
                for fn, wt, v in _pb(datas[0]):
                    if fn != 1 or wt != 2:
                        continue
                    info = {'vod_id': '', 'vod_name': '', 'vod_pic': '', 'vod_remarks': ''}
                    for f2, w2, v2 in _pb(v):
                        if f2 == 3 and w2 == 0:
                            info['vod_id'] = str(v2)
                        elif f2 == 5 and w2 == 2:
                            info['vod_name'] = v2.decode('utf-8', 'replace')
                        elif f2 == 13 and w2 == 2:
                            info['vod_remarks'] = v2.decode('utf-8', 'replace')
                    if info['vod_id']:
                        out.append(info)
        except Exception:
            pass
        return out

    def homeContent(self, f):
        cats = []
        # 正确 tab 来源：api/ex/v3/security/tag/list（GET，无 body）。App 走
        # getData(ConfigCateList.class, true)：data 是字符串，先双重 AES-ECB 解密
        # （外层 SAFECODE、内层 SAFE）再按 JSON 解析；data 本身就是列表。
        try:
            hh = self._hdr()
            hh['Content-Type'] = 'application/json;charset=UTF-8'
            hh['Accept'] = 'application/json'
            d = self._http(HOST + '/api/ex/v3/security/tag/list', None, hh)
            j = json.loads(d)
            if j.get('code') not in (200, 1, 0, None):
                raise ValueError('tag/list code %s' % j.get('code'))
            data = j.get('data')
            items = None
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get('list') or data.get('data') or []
            elif isinstance(data, str):
                s = data.strip()
                try:
                    items = json.loads(s)
                except Exception:
                    items = None
                if not isinstance(items, (list, dict)):
                    try:
                        items = json.loads(_double_decrypt_str(s))
                    except Exception:
                        items = None
                if isinstance(items, list) and items and all(isinstance(x, str) for x in items):
                    # ["<密文>", ...]：逐项解密再解析
                    dec = []
                    for x in items:
                        try:
                            dec.append(json.loads(_double_decrypt_str(x)))
                        except Exception:
                            pass
                    items = dec
                if isinstance(items, dict):
                    items = items.get('list') or items.get('data') or []
            for c in (items or []):
                if not isinstance(c, dict):
                    continue
                # CateBean 没有 enable 键；enable() == state==1
                if c.get('state') is not None:
                    try:
                        if int(c.get('state')) != 1:
                            continue
                    except Exception:
                        pass
                tid = c.get('typeId')
                if tid is None:
                    tid = c.get('type_id')
                nm = c.get('name') or ''
                if tid is None or not nm:
                    continue
                try:
                    mode = int(c.get('mode')) if c.get('mode') is not None else 1
                except Exception:
                    mode = 1
                tid = str(tid)
                if mode == 1 and tid == '0':
                    continue  # typeId 0 的 tab 不走 drama/category
                self._tab_modes[tid] = mode
                self._tab_names[tid] = nm
                secs = []
                for key in ('bannerList', 'sections'):
                    for s in (c.get(key) or []):
                        if isinstance(s, dict):
                            for it in (s.get('list') or s.get('videos') or s.get('data') or []):
                                if isinstance(it, dict):
                                    vid = it.get('id') or it.get('vod_id') or ''
                                    n2 = it.get('name') or it.get('vod_name') or it.get('title') or ''
                                    if vid and n2:
                                        secs.append({'vod_id': str(vid), 'vod_name': n2,
                                                     'vod_pic': it.get('pic') or it.get('vod_pic') or it.get('cover') or '',
                                                     'vod_remarks': it.get('remarks') or it.get('vod_remarks') or ''})
                if secs:
                    self._tab_sections[tid] = secs
                cats.append({'type_id': tid, 'type_name': nm})
        except Exception:
            cats = []
        if not cats:
            # tag/list 不可达时的兜底：只用实测确认过的 typeId1 值，电影/短剧/漫剧不编。
            cats = [{'type_id': '21', 'type_name': '剧集'},
                    {'type_id': '22', 'type_name': '综艺'},
                    {'type_id': '26', 'type_name': '动漫'},
                    {'type_id': '25', 'type_name': '直播'}]
            for c in cats:
                self._tab_modes[c['type_id']] = 1
                self._tab_names[c['type_id']] = c['type_name']
        cats.append({'type_id': 'history', 'type_name': '最近在看'})
        return {'class': cats}

    def homeVideoContent(self):
        return {'list': self._list('page=1&pagesize=24')}

    def _list(self, qs):
        out = []
        try:
            hh = self._hdr()
            hh['Content-Type'] = 'application/x-protobuf'
            hh['Accept'] = 'application/x-protobuf'
            d = self._http(HOST + '/api/proto/v5/drama/category',
                           self._secure(qs), hh)
            top = _pb(d)
            code = [v for fn, wt, v in top if fn == 1 and wt == 0]
            if (code[0] if code else 0) != 200:
                return out
            _datas = [v for fn, wt, v in top if fn == 3 and wt == 2]
            if not _datas:
                return out
            data = _datas[0]
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
        except Exception:
            pass
        return out

    def categoryContent(self, tid, pg, f, ext):
        try:
            pg = max(1, int(pg or 1))
        except Exception:
            pg = 1
        if tid == 'history':
            _h = self._history_list()
            return {'list': _h, 'page': 1,
                    'pagecount': 1, 'limit': 40, 'total': len(_h)}
        mode = self._tab_modes.get(str(tid))
        nm = self._tab_names.get(str(tid), '')
        if mode is not None and mode != 1:
            # mode!=1 不走 drama/category：短剧走 getShortVideo，其余用 tag/list 自带内容
            if '短剧' in nm:
                _lst = self._short_list(pg)
                if _lst:
                    return {'list': _lst, 'page': pg,
                            'pagecount': pg + 1 if _lst else pg, 'limit': 20, 'total': 0}
            secs = self._tab_sections.get(str(tid)) or []
            if secs:
                return {'list': secs, 'page': 1,
                        'pagecount': 1, 'limit': 40, 'total': len(secs)}
            return {'list': [], 'page': pg,
                    'pagecount': pg, 'limit': 24, 'total': 0}
        qs = 'page=%d&pagesize=24&typeId1=%s' % (pg, tid)
        _lst = self._list(qs)
        return {'list': _lst, 'page': pg,
                'pagecount': pg + 1 if _lst else pg, 'limit': 24, 'total': 0}

    def _history_list(self):
        out = []
        if not getattr(self, '_token', ''):
            return out
        try:
            d = self._http(HOST + '/api/ex/v3/user/history?username=' + urllib.parse.quote(getattr(self, '_username', '')),
                           None, {'User-Agent': UA, 'Accept': 'application/json', 'token': self._token})
            for it in (json.loads(d).get('data') or []):
                vid = it.get('videoId', '')
                if '|' in vid:
                    frm, url = vid.split('|', 1)
                    out.append({
                        'vod_id': 'h$%s$%s' % (frm, url),
                        'vod_name': it.get('videoName', ''),
                        'vod_pic': it.get('videoCover', ''),
                        'vod_remarks': '%s·第%s集' % (frm, it.get('videoPart', '')),
                    })
        except Exception:
            pass
        return out

    def detailContent(self, ids):
        out = {'vod_id': ids[0]}
        self._cur_id = ids[0]
        if ids[0].startswith('h$'):
            _, frm, url = ids[0].split('$', 2)
            return {'list': [dict(out, vod_name='继续观看',
                                   vod_play_from=frm,
                                   vod_play_url='正片$%s' % url,
                                   vod_pic='',
                                   vod_content='播放历史·线路:' + frm)]}
        try:
            hh = self._hdr()
            hh['Content-Type'] = 'application/x-protobuf'
            hh['Accept'] = 'application/x-protobuf'
            d = self._http(HOST + '/api/proto/v5/drama/getDetail',
                           self._secure('id=' + ids[0]), hh)
            top = _pb(d)
            _datas = [v for fn, wt, v in top if fn == 3 and wt == 2]
            if not _datas:
                return {'list': [out]}
            data = _datas[0]
            dd = _pb(data)
            for fn, wt, v in dd:
                if fn == 0 or fn > 100:
                    break  # protobuf 错位起点, 之后全是字符串碎片(乱码源)
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
                    out['vod_content'] = re.sub(
                        r'<[^>]+>', '', v.decode('utf-8', 'replace'))
                elif fn == 2 and wt == 2 and 'vod_pic' not in out:
                    cands = [v3.decode('utf-8', 'replace')
                             for f3, w3, v3 in _pb(v)
                             if w3 == 2 and v3.startswith(b'http')]
                    if cands:
                        out['vod_pic'] = next(
                            (u for u in cands if u.startswith('https')),
                            cands[0])
            # 演员兜底: f16/f25 无值时从错位块的干净中文串提取
            if 'vod_actor' not in out:
                for fn, wt, v in dd:
                    if fn == 0 and wt == 2:
                        txt = v.decode('utf-8', 'replace')
                        names = re.findall(
                            r'[\u4e00-\u9fa5]{2,4}(?:·[\u4e00-\u9fa5]{2,4})?', txt)
                        cand = [x for x in names if len(x) >= 4]
                        if cand:
                            out['vod_actor'] = ','.join(cand[:6])
                            break
            # f29 分集: 详情响应 _pb 会错位, 用原始 0xEA01 tag 扫描
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
                ep_no = 0
                is_vip = 0
                for f3_, w3_, v3_ in _pb(entry):
                    if w3_ == 2:
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
                    elif w3_ == 0:
                        if f3_ == 13:
                            ep_no = int(v3_)
                        elif f3_ == 14:
                            is_vip = int(v3_)
                if not pth:
                    continue
                # 集名归一化: "第01集"/"第01集完结"→"1"
                mm = re.match(r'^第?0*(\d{1,4})[集话期](?:完结)?$', title)
                if mm:
                    title = mm.group(1)
                # 标题数字与 episode 号对不上的是预告/错集，跳过
                if ep_no and title.isdigit() and int(title) != ep_no:
                    continue
                if is_vip:
                    title = title + '(VIP)'
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
            # 诊断：第一集的播放核/direct 标在备注里（核 1=TX、2=Ali 是私有加密流，
            # TVBox 通用播放器解不开；若官方 APP 能播、这里是 1/2，就是内核问题）
            try:
                if order and lines[order[0]]:
                    _first = lines[order[0]][0].split('$', 1)[1]
                    if not _first.startswith('http'):
                        _jm = json.loads(base64.b64decode(_first))
                        _pu, _hd, _msg, _dr, _core = self._usable_url_info(
                            _jm.get('vodPlayFrom', ''), _jm.get('playUrl', ''))
                        _names = {'1': 'TX', '2': 'Ali', '3': 'IJK', '4': 'EXO', '5': 'SYS'}
                        out['vod_remarks'] = '核:%s(%s) direct:%s%s' % (
                            _names.get(_core, '?'), _core, _dr,
                            (' msg:' + _msg) if _msg else '')
            except Exception:
                pass
            # 集名归一化: "第01集"→"1", 纯数字保留, 其他保留原名
            for ln_name in lines:
                norm = []
                for it in lines[ln_name]:
                    t, u = it.split('$', 1)
                    mm = re.match(r'^第?0*(\d{1,4})[集话期]$', t)
                    norm.append('%s$%s' % (mm.group(1) if mm else t, u))
                lines[ln_name] = norm
            # 线路排序: 超高清最前, 蓝光按名, 其余殿后
            def _rank(nm):
                if '超高清' in nm:
                    return 0
                if '蓝光' in nm:
                    return 1
                return 2
            order.sort(key=lambda x: (_rank(x), x))
            out['_lines'] = order
            out['_lines_map'] = lines
            lines = out.pop('_lines', [])
            lmap = out.pop('_lines_map', {})
            if lines:
                out['vod_play_from'] = '$$$'.join(lines)
                out['vod_play_url'] = '$$$'.join(
                    '#'.join(lmap[l]) for l in lines)
            else:
                out['vod_play_from'] = '橘汁'
                out['vod_play_url'] = '暂无片源$http://'
        except Exception:
            out['vod_name'] = ids[0]
            out['vod_play_from'] = '橘汁'
            out['vod_play_url'] = '播放$http://'
        return {'list': [out]}

    def searchContent(self, key, quick, pg=1):
        try:
            hh = self._hdr()
            hh['Content-Type'] = 'application/x-protobuf'
            hh['Accept'] = 'application/x-protobuf'
            try:
                _pg = max(1, int(pg or 1))
            except Exception:
                _pg = 1
            qs = 'page=%s&pagesize=24&searchKeys=%s' % (_pg, urllib.parse.quote(str(key), safe=''))
            d = self._http(HOST + '/api/proto/v5/drama/search',
                           self._secure(qs), hh)
            top = _pb(d)
            code = [v for fn, wt, v in top if fn == 1 and wt == 0]
            if (code[0] if code else 0) != 200:
                return {'list': [], 'page': int(pg or 1)}
            datas = [v for fn, wt, v in top if fn == 3 and wt == 2]
            if not datas:
                return {'list': [], 'page': int(pg or 1)}
            out = []
            for fn, wt, v in _pb(datas[0]):
                if wt != 2 or fn == 0 or fn > 100:
                    continue
                item = {'vod_id': '', 'vod_name': '', 'vod_pic': '',
                        'vod_remarks': ''}
                for f3, w3, v3 in _pb(v):
                    if w3 != 2 and not (f3 == 3 and w3 == 0):
                        continue
                    try:
                        if f3 == 3 and w3 == 0:
                            item['vod_id'] = str(v3)
                        elif f3 == 5:
                            item['vod_name'] = v3.decode('utf-8', 'replace')
                        elif f3 == 2:
                            # 海报 b64串: 取内部http
                            cands = [x.decode('utf-8', 'replace')
                                     for _, w4, x in _pb(v3)
                                     if w4 == 2 and x.startswith(b'http')]
                            if cands:
                                item['vod_pic'] = next(
                                    (u for u in cands if u.startswith('https')),
                                    cands[0])
                        elif f3 == 13:
                            item['vod_remarks'] = v3.decode('utf-8', 'replace')
                        elif f3 == 4:
                            item['vod_content'] = v3.decode(
                                'utf-8', 'replace')[:100]
                    except Exception:
                        pass
                if item['vod_id'] and item['vod_name']:
                    out.append(item)
            return {'list': out, 'page': int(pg or 1)}
        except Exception:
            return {'list': [], 'page': 1}

    def playerContent(self, flag, id, vipFlags):
        url = id
        headers = {'User-Agent': UA}
        try:
            if id and not id.startswith('http') and not id.startswith('h$'):
                jm = json.loads(base64.b64decode(id))
                pf, pu = jm.get('vodPlayFrom', ''), jm.get('playUrl', '')
                play_url, vheaders, msg, direct, core = self._usable_url_info(pf, pu)
                # App：msg 非空只弹提示，不阻止播放；只有 playUrl 为空才算失败
                if play_url and play_url.startswith('http'):
                    headers = dict(vheaders)
                    headers.setdefault('User-Agent', UA)
                    if direct == 1:
                        # 只有 direct==1 App 才解析跳转；direct==0 原样播，
                        # 提前解析会让短时效签名地址到手就过期
                        url = self._resolve_redirect_chain(play_url, headers)
                    else:
                        url = play_url
                else:
                    url = ''
            elif not url.startswith('http'):
                url = 'http://'
        except Exception:
            pass
        return {'parse': 0, 'playUrl': '', 'url': url,
                'header': headers}

    def isVideoFormat(self, url):
        u = (url or '').lower().split('?')[0]
        return u.endswith(('.m3u8', '.mp4', '.flv', '.mkv', '.avi', '.ts', '.mov', '.mpd', '.m4a', '.wmv'))

    def isTextFormat(self, url):
        return False

    def destroy(self):
        pass
