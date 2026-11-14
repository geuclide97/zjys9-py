# -*- coding: utf-8 -*-
"""
小八影视 https://www.xiao8.tv —— OK影视爬虫插件
按「模板3.py」规范实现，继承 base.spider.Spider，基础框架原样复用。

已打通全链路：
  首页分类/筛选 → 分类列表(真实分页) → 视频详情(多线路/多集) → 搜索 → 播放解析

★ 线路过滤（默认开启）：线路名含「线路」二字的条目一律不输出
  （HN线路 / XL线路 / DB线路 / SB线路 / WJ线路 / IK线路 / JY线路 / GS线路），
  全量 18 条 → 保留 10 条。过滤在 detailContent 唯一出口统一执行，因此
  分类列表、首页推荐、搜索结果点进详情全部生效；搜索列表本身不含线路数据。
  需要恢复完整线路时传 extend={"hide_line": 0}。

站点为 Nuxt SSR，对外暴露同域 JSON 接口（无需 Cookie / 登录 / 签名头）：
  /api/web/lb  分类与筛选项(video_labels)
  /api/web/f   列表 videoType/sort/tag/actor_tags/area/year/page/size → {count, items}
  /api/web/q   搜索 key → {count, items}（支持中文、拼音、首字母）
  /api/web/d   详情 cid/page/size → {video, episodes, lines}
  /api/web/p   实时换链 cid/num/format/quality/vid/line → {url}
               num 为 0-based 集序号，line 为线路 siteId，
               vid = md5(platform + cid + num + "NEVteOSYZq")
               platform 取 video.source[0].platform（默认 keke）

★ 站点 2026 改版（多线路的关键）：
  明文 /api/web/d 现在只返回「降级数据」——lines=[]、episodes 无播放地址，
  网页 SSR 也只有 1 条线路；完整 18 条线路是客户端 hydration 后通过
  **加密通道**拿到的：GET /api/web/d?data={"Key","Iv","Edata"}
    Edata = AES-CBC(query 串, 16位随机会话密钥, IV="0000000000000000")
    Key   = RSA-PKCS1v1.5(会话密钥, 站点内置公钥)
    响应 data 用同一会话密钥 AES-CBC 加密，需解密后取 lines。
  插件双通道保证 18 条线路：
    1) 宿主带 cryptography / pycryptodome → 走加密通道，拿到 18 条线路 ×
       每集直连 m3u8（带浏览器同款头 + 3 次重试抵御站点间歇性降级）；
    2) 无加密库 / 加密通道被降级 → 用内置 18 条 (线路名, siteId) 表逐条
       生成播放项 x8live://，点播时由 playerContent 调 /api/web/p?line=
       实时换取该线路 m3u8（18 个 siteId 已逐个实测返回 200）。

播放项地址优先保持为真实 m3u8 直链（兼容所有播放器）；detailContent 同时在
内存登记每集对应的 cid/集序号/线路/平台，playerContent 据此调用 /api/web/p
换取最新地址，失败自动回退原直连地址，避免 sign/timestamp 过期导致播放失效。
另支持 x8live://<base64> 备用入口，可在无直连地址时直接换链。

宿主兼容说明（分类不显示时的关键处理）：
  * homeContent 默认返回 {"class": [...], "filters": {}}：筛选器为空字典。
    既满足「必须取 filters 键」的宿主，又避免庞大筛选器被解析失败而丢弃
    整个首页数据（这是分类栏全空的常见原因）。
    需要筛选时传 extend={"filters": 1} 开启。
  * type_id 使用纯数字，内部映射到站点 videoType，兼容只认数字ID的宿主。
  * init / homeContent 全程异常兜底，宿主基类差异或接口异常时仍返回静态分类。

extend 可选 JSON 配置：
  {"refresh": 0}                         关闭实时换链（纯直连）
  {"page_size": 30}                     调整每页条数
  {"api_base": "https://www.mohe.dev"}   切换 API 域名
  {"filters": 1}                         开启分类筛选器（默认关闭）
  {"hide_line": 0}                       保留名称含「线路」二字的线路（默认删除）

本地自测：python3 test_xiao8.py（同目录 base/spider.py 模拟 OK影视宿主）
"""
import re
import os
import json
import base64
import hashlib
import urllib.parse
import uuid
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

requests.packages.urllib3.disable_warnings()

# ========== 站点加密通道（可选，用于取回完整多线路直连数据）==========
# 站点 2026 改版：明文 /api/web/d 只返回降级数据（lines=[]、episodes 无播放地址），
# 完整 18 条线路需走加密通道 /api/web/d?data={"Key":...,"Iv":...,"Edata":...}：
#   AES-CBC(固定 IV "0000000000000000") 加密 query 串；RSA(PKCS1v1.5) 加密 16 位会话密钥；
#   响应 data 用同一会话密钥 AES-CBC 解密。
# 仅当宿主 Python 带 cryptography / pycryptodome 时启用；否则自动降级为
# 「固定线路表 + 明文 /api/web/p 换链」，同样输出 18 条线路（不依赖第三方库）。
_X8_PUBKEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxDGjAoinx62PWXuCliLM"
    "Hq5TPrgIvAib+nsb9riac+ylLpVZTMpHkSI2CPmgz7ZMJY8/NQgtX42HHjV1qQj7"
    "7ngHbwvYcpSXMwRuTiJL3uFr+1gSGH8pcPGonOe/zUSlE7CkA9JRUQUNW2BuQpQI"
    "sCQ2MiwjRyxtADnS0Wh/pd+fkwa7x1l5Ke7sQMu13MOuzIHkckzaSjsSL9SroI9G"
    "U2UT+0ja/9MdD9jg0vLEX0blTM5NGeHhAQXhCWDIAVkxYe7O7mZjoz1c5qjb1WnS"
    "RjywrACJUmeYg5qtdz09T2FH5oa9zXwNlnCTUGFigZAxSBq1cEX8rBQKMurffYOp"
    "JwIDAQAB"
)
_X8_IV = b"0000000000000000"
try:
    from cryptography.hazmat.primitives.ciphers import Cipher as _X8Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms as _X8Algs
    from cryptography.hazmat.primitives.ciphers import modes as _X8Modes
    from cryptography.hazmat.primitives.asymmetric import padding as _X8Padding
    from cryptography.hazmat.primitives import serialization as _X8Ser
    _X8_CRYPTO = "cryptography"
except Exception:
    try:
        from Crypto.Cipher import AES as _X8PyAES
        from Crypto.PublicKey import RSA as _X8PyRSA
        from Crypto.Cipher import PKCS1_v1_5 as _X8PyPKCS1
        _X8_CRYPTO = "pycryptodome"
    except Exception:
        _X8_CRYPTO = ""


def _x8_pad(data):
    n = 16 - len(data) % 16
    return data + bytes([n]) * n


def _x8_unpad(data):
    if not data:
        return b""
    n = data[-1]
    return data[:-n] if 1 <= n <= 16 else data


def _x8_aes_enc(plain, key):
    p = _x8_pad(plain)
    if _X8_CRYPTO == "cryptography":
        c = _X8Cipher(_X8Algs.AES(key), _X8Modes.CBC(_X8_IV)).encryptor()
        return c.update(p) + c.finalize()
    if _X8_CRYPTO == "pycryptodome":
        return _X8PyAES.new(key, _X8PyAES.MODE_CBC, _X8_IV).encrypt(p)
    return b""


def _x8_aes_dec(cipher, key):
    if _X8_CRYPTO == "cryptography":
        d = _X8Cipher(_X8Algs.AES(key), _X8Modes.CBC(_X8_IV)).decryptor()
        return _x8_unpad(d.update(cipher) + d.finalize())
    if _X8_CRYPTO == "pycryptodome":
        return _x8_unpad(_X8PyAES.new(key, _X8PyAES.MODE_CBC, _X8_IV).decrypt(cipher))
    return b""


def _x8_rsa_enc(session_key):
    """RSA PKCS#1 v1.5 加密 16 位会话密钥，返回 base64 字符串"""
    if _X8_CRYPTO == "cryptography":
        pem = ("-----BEGIN PUBLIC KEY-----\n" + _X8_PUBKEY_B64 +
               "\n-----END PUBLIC KEY-----").encode()
        pub = _X8Ser.load_pem_public_key(pem)
        return base64.b64encode(pub.encrypt(session_key, _X8Padding.PKCS1v15())).decode()
    if _X8_CRYPTO == "pycryptodome":
        pub = _X8PyRSA.import_key(base64.b64decode(_X8_PUBKEY_B64))
        c = _X8PyPKCS1.new(pub)
        return base64.b64encode(c.encrypt(session_key)).decode()
    return ""


# 核心：继承OK影视内置base.spider.Spider类（必须保留）
try:
    from base.spider import Spider
except Exception:
    # 宿主未注入基类时的最小兜底，保证插件一定可被实例化
    class Spider(object):
        def init(self, extend=""):
            pass
        def getName(self):
            return ""
        def homeContent(self, filter):
            return {"class": []}
        def homeVideoContent(self):
            return {"list": []}
        def categoryContent(self, tid, pg, filter, extend):
            return {"list": []}
        def detailContent(self, ids):
            return {"list": []}
        def searchContent(self, key, quick, pg=1):
            return {"list": []}
        def playerContent(self, flag, id, vipFlags):
            return {"parse": 0, "url": "", "header": {}}


class Spider(Spider):
    # 播放换链签名盐值（站点 JS 内置常量）
    VID_SECRET = "NEVteOSYZq"
    # /api/web/lb 不可用时的兜底分类
    FALLBACK_LABELS = [
        {"label": "电视剧", "value": "dsj"},
        {"label": "电影", "value": "dy"},
        {"label": "综艺", "value": "zy"},
        {"label": "Netfix", "value": "hw"},
        {"label": "韩剧", "value": "kr"},
        {"label": "动漫", "value": "dm"},
        {"label": "纪录片", "value": "jlp"},
        {"label": "少儿", "value": "se"},
        {"label": "福利", "value": "fl"},
    ]
    CHANNEL_NAMES = {
        "100113": "剧集", "100173": "电影", "100109": "综艺纪录",
        "100119": "动漫", "100105": "纪录片", "100150": "少儿",
        "100222": "福利", "999997": "海外剧", "999996": "韩剧",
    }
    FILTER_KEYS = ("sort", "area", "year", "tag", "actor_tags", "recommend")
    # 纯数字 type_id → 站点 videoType（部分宿主只接受数字分类ID）
    CATE_NUM = {
        "1": "dsj", "2": "dy", "3": "zy", "4": "hw", "5": "kr",
        "6": "dm", "7": "jlp", "8": "se", "9": "fl", "10": "main",
    }
    # 站点 18 条线路（中文名 → siteId）。明文 /api/web/d 已不再返回 lines，
    # 但 /api/web/p?line=<siteId> 仍全量有效，可据此在降级环境还原多线路。
    # 顺序与网页「切换线路」一致，默认线路(dujia2)在前。
    # 其中 8 条名称含「线路」二字，默认由 _line_allowed 过滤掉（保留 10 条）。
    SITE_LINES = [
        ("超清2", "dujia2"), ("极速蓝光", "dujia1"), ("优质1", "feifan"),
        ("蓝光1", "baofeng"), ("HN线路", "hongniu"), ("蓝光9", "jisu"),
        ("蓝光", "dyttzy"), ("蓝光3", "1080zy"), ("蓝光7", "haohua"),
        ("优质2", "liangzi"), ("XL线路", "xinlang"), ("DB线路", "dbzy"),
        ("SB线路", "subo"), ("蓝光4", "suoni"), ("WJ线路", "wujin"),
        ("IK线路", "ikun"), ("JY线路", "jinying"), ("GS线路", "guangsu"),
    ]

    # ========== 插件基础配置（模板接口 1）==========
    def getName(self):
        """插件名称：OK影视插件列表中显示的名称"""
        return "小八影视"

    # ========== 初始化全局配置（模板接口 2）==========
    def init(self, extend=""):
        # 1. 先建立全套最小可用属性：任何一步异常都不会让插件初始化失败
        self.site_url = "https://www.xiao8.tv"
        self.api_base = self.site_url
        self.enable_refresh = True
        self.enable_filters = False
        # 默认删除名称含「线路」二字的线路
        self.hide_line_named = True
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.site_url + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        self.sess = None
        self.page_size = 60
        self.total = 0
        self._labels = None
        # 播放地址 → (cid, 集序号, 线路siteId, 平台) 换链参数登记表
        self._play_map = {}

        # 2. 继承父类初始化（模板要求保留；宿主实现有差异时用 try 兜住）
        try:
            super().init(extend)
        except Exception:
            pass

        # 3. 扩展配置：解析失败一律使用默认值
        try:
            if isinstance(extend, dict):
                cfg = extend
            elif isinstance(extend, str) and extend.strip().startswith("{"):
                cfg = json.loads(extend)
            else:
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}
            self.api_base = str(cfg.get("api_base") or self.site_url).rstrip("/")
            self.enable_refresh = str(cfg.get("refresh", "1")).lower() not in ("0", "false", "no", "off")
            self.enable_filters = str(cfg.get("filters", "0")).lower() in ("1", "true", "yes", "on")
            self.hide_line_named = str(cfg.get("hide_line", "1")).lower() not in ("0", "false", "no", "off")
            self.page_size = int(cfg.get("page_size") or 60) or 60
        except Exception:
            pass

        # 4. 会话保持 + 请求重试（模板原样保留；失败则退化为模块级 requests）
        try:
            self.sess = requests.Session()
            retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
            self.sess.mount("https://", HTTPAdapter(max_retries=retry))
            self.sess.mount("http://", HTTPAdapter(max_retries=retry))
        except Exception:
            self.sess = None

    # ========== 通用请求方法（模板接口 3，无需改）==========
    def fetch(self, url, timeout=10):
        """通用GET请求方法：全局复用，处理请求异常"""
        try:
            getter = self.sess.get if self.sess is not None else requests.get
            return getter(url, headers=self.headers, timeout=timeout, verify=False)
        except Exception:
            return None

    # ========== JSON API 请求（新增封装）==========
    def api(self, path, **params):
        """请求站点公开 JSON 接口，返回 data 段；失败返回 None"""
        query = {k: v for k, v in params.items() if v is not None and v != ""}
        try:
            getter = self.sess.get if self.sess is not None else requests.get
            res = getter(self.api_base + path, params=query,
                         headers=self.headers, timeout=15, verify=False)
            if not res.ok:
                return None
            obj = res.json()
            if not isinstance(obj, dict) or str(obj.get("code")) != "200":
                return None
            data = obj.get("data")
            return data if isinstance(data, (dict, list)) else None
        except Exception:
            return None

    # ========== 加密通道请求（站点改版后完整多线路数据的唯一来源）==========
    def _secure_api(self, path, **params):
        """AES+RSA 加密请求 /api/web/d，返回完整 data（18 条线路 × 每集直连）。

        站点会间歇性返回降级数据（lines=[]），故带浏览器同款头并重试 3 次；
        宿主无加密库、全部降级、解密失败时返回 None 或降级 data，由调用方
        用固定线路表兜底，保证任何环境都能输出多线路。
        """
        if not _X8_CRYPTO:
            return None
        query = {k: v for k, v in params.items() if v is not None and v != ""}
        plain = "&".join("%s=%s" % (k, v) for k, v in query.items())
        getter = self.sess.get if self.sess is not None else requests.get
        base_headers = dict(self.headers)
        ua = base_headers.get("User-Agent", "")
        base_headers.update({
            "AppId": "10011", "Language": "zh",
            "DeviceId": str(uuid.uuid4()),
            "ClientUserAgent": ua, "ClientIP": "",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua": '"Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
        })
        if query.get("cid"):
            base_headers["Referer"] = self.site_url + "/detail/" + str(query["cid"]) + "/"
        fallback = None
        for _ in range(3):
            try:
                alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
                session = "".join(alphabet[b % len(alphabet)] for b in os.urandom(16)).encode()
                edata = base64.b64encode(_x8_aes_enc(plain.encode("utf-8"), session)).decode()
                iv_b64 = base64.b64encode(_X8_IV).decode()
                key_b64 = _x8_rsa_enc(session)
                if not key_b64:
                    return fallback
                cipher_json = json.dumps({"Key": key_b64, "Iv": iv_b64, "Edata": edata},
                                         separators=(",", ":"))
                url = self.api_base + path + "?data=" + urllib.parse.quote(cipher_json, safe="")
                headers = dict(base_headers)
                headers.update({"dt-aes-key": key_b64, "dt-aes-iv": iv_b64,
                                "dt-encrypted": "1"})
                res = getter(url, headers=headers, timeout=20, verify=False)
                if not res.ok:
                    continue
                obj = res.json()
                if not isinstance(obj, dict) or str(obj.get("code")) != "200":
                    continue
                data = obj.get("data")
                if isinstance(data, str) and data.strip():
                    raw = _x8_aes_dec(base64.b64decode(data.strip()), session)
                    data = json.loads(raw.decode("utf-8"))
                if isinstance(data, dict):
                    if data.get("lines"):
                        return data
                    if fallback is None:
                        fallback = data
            except Exception:
                continue
        return fallback

    # ========== 首页分类接口（模板接口 4）==========
    def homeContent(self, filter=None):
        """分类一定返回：接口/宿主异常时回退静态分类，避免首页分类栏空白"""
        try:
            labels = self._get_labels()
            num_of = {v: k for k, v in self.CATE_NUM.items()}
            cate_list = []
            for i, x in enumerate(labels):
                if not isinstance(x, dict):
                    continue
                value = str(x.get("value") or "").strip()
                if not value:
                    continue
                cate_list.append({"type_name": str(x.get("label") or value),
                                  "type_id": num_of.get(value, str(i + 1))})
            cate_list.append({"type_name": "全部影视",
                              "type_id": num_of.get("main", "10")})
            # 默认带空 filters：兼容必须取该键的宿主，同时不引入可被误解析的内容
            result = {"class": cate_list, "filters": {}}
            if self.enable_filters:
                try:
                    result["filters"] = self._build_filters(labels, num_of)
                except Exception:
                    result["filters"] = {}
            return result
        except Exception:
            return {"class": self._static_cates(), "filters": {}}

    @classmethod
    def _static_cates(cls):
        num_of = {v: k for k, v in cls.CATE_NUM.items()}
        out = [{"type_name": x["label"], "type_id": num_of.get(x["value"], str(i + 1))}
               for i, x in enumerate(cls.FALLBACK_LABELS)]
        out.append({"type_name": "全部影视", "type_id": num_of.get("main", "10")})
        return out

    def _build_filters(self, labels, num_of):
        """可选筛选器；所有字段做类型检查，杜绝异常结构导致首页崩溃"""
        filters = {}
        for x in labels:
            if not isinstance(x, dict):
                continue
            value = str(x.get("value") or "").strip()
            tid = num_of.get(value, "")
            if not tid:
                continue
            opts = []

            def add(key, name, values):
                if not isinstance(values, (list, tuple)):
                    return
                vals = [str(v).strip() for v in values if str(v).strip()]
                if vals:
                    opts.append({"key": key, "name": name,
                                 "value": [{"n": "全部", "v": ""}] +
                                          [{"n": v, "v": v} for v in vals]})

            add("sort", "排序", x.get("sort"))
            add("area", "地区", x.get("area"))
            add("year", "年份", x.get("year"))
            add("tag", "类型", x.get("recommend"))
            act = x.get("act")
            if isinstance(act, (list, tuple)):
                add("actor_tags", "明星", act[:40])
            if opts:
                filters[tid] = opts
        return filters

    # ========== 首页推荐（OK影视可选接口，新增）==========
    def homeVideoContent(self):
        data = self.api("/api/web/f", videoType="main", page=1, size=24, sort="最热") or {}
        return {"list": [v for v in (self._to_vod(i) for i in (data.get("items") or [])) if v]}

    # ========== 分类列表接口（模板接口 5）==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        ex = self._merge(filter, extend)
        # 数字 type_id 映射回站点 videoType；直接传字母ID同样兼容
        video_type = self.CATE_NUM.get(str(tid), str(tid or "dy"))
        params = {"videoType": video_type, "page": pg,
                  "size": self.page_size, "sort": "最热"}
        for key in self.FILTER_KEYS:
            val = str(ex.get(key) or "").strip()
            if val and val != "全部":
                params[key] = val
        data = self.api("/api/web/f", **params) or {}
        items = data.get("items") or []
        count = data.get("count")
        count = int(count) if isinstance(count, (int, float)) else len(items)
        self.total = count
        video_list = [v for v in (self._to_vod(i) for i in items) if v]
        # 依据接口返回的真实 count 计算总页数
        pagecount = max(pg, (count + self.page_size - 1) // self.page_size) if count else pg
        return {"list": video_list, "page": pg, "pagecount": pagecount,
                "limit": self.page_size, "total": count}

    # ========== 视频详情接口（模板接口 6）==========
    def detailContent(self, ids):
        vod_id = str(ids[0]) if ids else ""
        cid = self._extract_cid(vod_id)
        if not cid:
            return {"list": [{"vod_name": "视频ID为空"}]}
        # 优先走加密通道取完整 18 条线路；失败降级明文接口（站点只给精简数据）
        data = self._secure_api("/api/web/d", cid=cid, page=1, size=9999)
        if not isinstance(data, dict):
            data = self.api("/api/web/d", cid=cid, page=1, size=9999)
        if not isinstance(data, dict):
            return {"list": [{"vod_id": vod_id, "vod_name": "视频详情解析失败"}]}

        video = data.get("video") or {}
        lines = data.get("lines") or []
        episodes = data.get("episodes") or []
        platform = "keke"
        src = video.get("source") or []
        if isinstance(src, list) and src and isinstance(src[0], dict):
            platform = str(src[0].get("platform") or "keke").strip() or "keke"

        play_froms, play_urls = [], []
        if isinstance(lines, list):
            # 默认选中线路排在最前
            ordered = sorted(lines, key=lambda l: 0 if (isinstance(l, dict) and l.get("selected")) else 1)
            for line in ordered:
                if not isinstance(line, dict):
                    continue
                name = self._clean(str(line.get("name") or line.get("siteId") or "默认源"), "[$#]")
                # 名称含「线路」二字的线路一律不输出（所有入口统一生效）
                if not self._line_allowed(name):
                    continue
                site = str(line.get("siteId") or "")
                parts = []
                for idx, ep in enumerate(line.get("list") or []):
                    if not isinstance(ep, dict):
                        continue
                    url = self._pick_url(ep.get("playUrls"))
                    if not url:
                        continue
                    title = self._clean(str(ep.get("title") or ("第" + str(idx + 1) + "集")), "[$#]")
                    raw_idx = ep.get("index")
                    num = int(raw_idx) - 1 if isinstance(raw_idx, int) else idx
                    if num < 0:
                        num = idx
                    parts.append(title + "$" + self._register(cid, num, site, platform, url))
                if parts:
                    play_froms.append(name)
                    play_urls.append("#".join(parts))

        # lines 为空的兜底（站点改版后明文详情不再返回 lines）：
        # 用站点固定线路表逐条还原（名称含「线路」二字的按配置过滤），
        # 每条线路覆盖全部剧集；播放项为
        # x8live:// 元数据，点播时由 playerContent 调 /api/web/p?line=<siteId>
        # 实时换取该线路 m3u8（18 个 siteId 已逐个实测返回 200）。
        # 这样即使宿主无加密库 / 加密通道被降级，也仍然显示完整多线路。
        if not play_froms:
            eps_src = [e for e in (episodes if isinstance(episodes, list) else [])
                       if isinstance(e, dict)] or [{"title": "正片"}]
            direct = str(video.get("url") or "").strip()
            if direct.startswith("http"):
                title = self._clean(str(eps_src[0].get("title") or "正片"), "[$#]")
                play_froms.append("正片直连")
                play_urls.append(title + "$" + self._register(cid, 0, "", platform, direct))
            for name, site in self.SITE_LINES:
                if not self._line_allowed(name):
                    continue
                parts = []
                for idx, ep in enumerate(eps_src):
                    title = self._clean(str(ep.get("title") or ("第" + str(idx + 1) + "集")), "[$#]")
                    parts.append(title + "$x8live://" +
                                 self._encode_meta(cid, idx, site, platform))
                if parts:
                    play_froms.append(name)
                    play_urls.append("#".join(parts))
            if not play_froms:
                fresh = self._refresh(cid, 0, "", platform)
                if fresh:
                    play_froms = ["默认源"]
                    play_urls = ["正片$" + fresh]

        eps_count = max((len(u.split("#")) for u in play_urls), default=0) or len(episodes)
        desc = " ".join(str(video.get("cover_description") or "").split())
        actors = "、".join(str(a) for a in (video.get("leading_actor_tags") or [])[:8])
        director = "、".join(str(a) for a in (video.get("director_tags") or [])[:4])
        year = str(video.get("year") or "") or str(video.get("publish_date") or "")[:4]
        detail_info = {
            "vod_id": vod_id,
            "vod_name": str(video.get("title") or "未知名称").strip(),
            "vod_pic": self._abs(str(video.get("new_pic_vt") or video.get("new_pic_hz") or "")),
            "vod_remarks": str(len(play_froms)) + "个播放源 · 共" + str(eps_count) + "集",
            "type_name": self.CHANNEL_NAMES.get(str(video.get("channel_id") or ""), "影视"),
            "vod_year": year,
            "vod_area": str(video.get("area_name") or ""),
            "vod_actor": actors,
            "vod_director": director,
            "vod_content": desc,
            "vod_play_from": "$$$".join(play_froms),
            "vod_play_url": "$$$".join(play_urls),
        }
        return {"list": [detail_info]}

    # ========== 搜索接口（模板接口 7）==========
    def searchContent(self, key, quick, pg=1):
        pg = int(pg) if str(pg).isdigit() else 1
        key = str(key or "").strip()
        video_list, count = [], 0
        if key:
            data = self.api("/api/web/q", key=key) or {}
            video_list = [v for v in (self._to_vod(i) for i in (data.get("items") or [])) if v]
            c = data.get("count")
            count = int(c) if isinstance(c, (int, float)) else len(video_list)
        return {"list": video_list, "page": pg, "pagecount": 1,
                "limit": max(self.page_size, len(video_list)), "total": count or len(video_list)}

    # ========== 播放解析接口（模板接口 8）==========
    def playerContent(self, flag, id, vipFlags):
        """默认直连（parse=0）；命中换链登记表时实时换取最新地址，失败回退直连"""
        raw = str(id or "").strip()
        if "$" in raw:
            raw = raw.split("$", 1)[1]
        raw = raw.strip()
        # 备用入口：只有换链元数据、没有直连地址时使用
        if raw.startswith("x8live://"):
            meta = self._decode_meta(raw[9:])
            return {"parse": 0, "url": self._refresh(*meta) if meta else "",
                    "header": self.headers}
        url = raw.split("#", 1)[0]
        if self.enable_refresh and url.startswith("http"):
            meta = self._play_map.get(url)
            if meta:
                fresh = self._refresh(*meta)
                if fresh:
                    url = fresh
        return {"parse": 0, "url": url, "header": self.headers}

    # ---------------- 内部工具方法 ----------------
    def _get_labels(self):
        if self._labels is None:
            labels = []
            try:
                data = self.api("/api/web/lb") or {}
                if isinstance(data, dict):
                    labels = [x for x in (data.get("video_labels") or [])
                              if isinstance(x, dict) and x.get("value")]
            except Exception:
                labels = []
            self._labels = labels or [dict(x) for x in self.FALLBACK_LABELS]
        return self._labels

    def _merge(self, filter, extend):
        """兼容 OK影视传入 dict 或 JSON 字符串的 filter/extend"""
        out = {}
        for src in (filter, extend):
            if isinstance(src, dict):
                out.update(src)
            elif isinstance(src, str) and src.strip().startswith("{"):
                try:
                    out.update(json.loads(src))
                except Exception:
                    pass
        return out

    def _to_vod(self, item):
        """把接口 item 转成 OK影视视频字典（列表/搜索/推荐共用）"""
        if not isinstance(item, dict):
            return None
        cid = str(item.get("cid") or "").strip()
        name = str(item.get("title") or "").strip()
        if not cid or not name:
            return None
        bits = []
        try:
            score = float(item.get("v_score") or 0)
            if score > 0:
                bits.append("%.1f分" % score)
        except (TypeError, ValueError):
            pass
        for key in ("year", "area_name"):
            val = str(item.get(key) or "").strip()
            if val:
                bits.append(val)
        ep = item.get("episode_count")
        if isinstance(ep, (int, float)) and int(ep) > 1:
            bits.append("共" + str(int(ep)) + "集")
        return {"vod_id": cid, "vod_name": name,
                "vod_pic": self._abs(str(item.get("new_pic_vt") or item.get("new_pic_hz") or "")),
                "vod_remarks": " · ".join(bits) if bits else "高清"}

    def _abs(self, url):
        """相对路径/协议相对地址补全为绝对地址"""
        url = (url or "").strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http://"):
            return "https://" + url[7:]
        if url.startswith("https://"):
            return url
        if url.startswith("/"):
            return self.site_url + url
        return url

    @staticmethod
    def _pick_url(play_urls):
        """从 playUrls 数组中取第一个可用的 http 地址"""
        if not isinstance(play_urls, list):
            return ""
        for p in play_urls:
            u = p.get("url") if isinstance(p, dict) else (p if isinstance(p, str) else "")
            if isinstance(u, str) and u.startswith("http"):
                return u.split("#", 1)[0]
        return ""

    @staticmethod
    def _clean(text, pattern):
        return re.sub(pattern, "", text).strip() or "默认源"

    def _line_allowed(self, name):
        """线路名含「线路」二字的一律不输出（分类/推荐/搜索进详情统一生效）。

        hide_line_named 由 extend={"hide_line": 0} 关闭，可恢复完整线路。
        """
        return not (self.hide_line_named and "线路" in str(name))

    @staticmethod
    def _extract_cid(vod_id):
        """兼容纯 cid、/detail/{cid}/标题、完整 URL 三种 vod_id"""
        s = str(vod_id or "").strip()
        m = re.search(r"/detail/([0-9]{6,})", s)
        if m:
            return m.group(1)
        m = re.match(r"^[0-9]{6,}$", s)
        if m:
            return s
        m = re.search(r"([0-9]{6,})", s)
        return m.group(1) if m else ""

    def _register(self, cid, num, line, platform, url):
        """登记播放地址对应的换链参数，返回纯净的直连地址（不含 # 与 $）"""
        url = url.split("#", 1)[0]
        self._play_map[url] = (str(cid), int(num), str(line or ""), str(platform or "keke"))
        return url

    @staticmethod
    def _encode_meta(cid, num, line, platform):
        """把换链参数编码为 x8live:// 备用入口使用的 token"""
        raw = "|".join([str(cid), str(num), str(line or ""), str(platform or "keke")])
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode().rstrip("=")

    @staticmethod
    def _decode_meta(token):
        try:
            s = token + "=" * (-len(token) % 4)
            parts = base64.urlsafe_b64decode(s.encode()).decode("utf-8").split("|")
            if len(parts) != 4:
                return None
            return parts[0], int(parts[1]), parts[2], parts[3]
        except Exception:
            return None

    def _refresh(self, cid, num, line="", platform="keke"):
        """调用 /api/web/p 实时换取最新播放地址（vid 为站点 MD5 签名）"""
        plain = str(platform) + str(cid) + str(num) + self.VID_SECRET
        vid = hashlib.md5(plain.encode("utf-8")).hexdigest()
        data = self.api("/api/web/p", cid=cid, num=num, format="m3u8",
                        quality="1", vid=vid, line=line) or {}
        url = data.get("url")
        return url.strip() if isinstance(url, str) and url.startswith("http") else ""

# ========== 无额外入口（OK影视自动识别Spider类，无需添加main函数）==========
