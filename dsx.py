# -*- coding: utf-8 -*-
"""
大师兄（dsx）· UI9 / TVBox 通用 py 源
协议来自 WeBox 原生源 dsx.webox.js v1.0.3：AES-128-CBC 打包请求，响应支持
明文 / base64 AES / 信封变体三种，解析接口的分块 RSA 响应也能解。
"""
import base64
import hashlib
import json
import random
import re
import time
from urllib.parse import quote, unquote

try:
    import requests
except Exception:
    requests = None

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except Exception:
    AES = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

ROOTS = ["http://app2.dsx.ac", "http://app.arkplansuk.com", "http://app.zgwanyuan.com"]
PROFILE = {
    "version": "4.1.2",
    "build": "4012",
    "time": "1793979269225",
    "package": "com.suishenji.cdscc.zaad",
}
PATH = "/ndsx.php/v7/logs"
MARKER = "eGRkYXBwc2VjcmV0a2V5"
SIGN_MD5 = "1aeb3180604b9dc9b22ef9f6293f3b28"
APK_LENGTH = 38769877
APK_PATH = "/data/app/com.suishenji.cdscc.zaad/base.apk"

PARSER_RSA = {
    "n": "ef689ac8becacedf9811f7c357740dfbd1010963d302c1d412375ec6fd5928aee2511cd4c7be5ee6e7cd3c5a40f0816e7b995117ab46b3bdf359fd1a1b109037169ad5be5f59a90a594e5adf1b6e75b028fb07a9e9911719dc0d613f7749c0f72ad99fa9cb572fc9ec327771526522cf5b34b02ba84891f0a56b01fd4f3522d7",
    "e": "10001",
    "p": "fbc7ab9d75533e39971e41b554990a57149ea3d115298d9d17630138a40f315339b7a69c6254dde2ffed520f5ad8c48fd2ef18ffd6c97ea0ca8d7329cf0146d5",
    "q": "f36bda059d298c1cf92fae597fcccc5ccb715e3935b485cb4185d20c6c19a3249ca195f4e604ebf1c26f08f75174e72764499d722ee2e10232f16e3aacd9f0fb",
    "dp": "7f28e1d0bd6f944eabb6d942c67e208dc85932ad273dfc4aa984141ad228e6257d51f670a6ecebbf78b81828af1e296fe5fd61a7dc87994f85dd189bb5f3941d",
    "dq": "6d86a9a2bd0464b6e4a83f9aa596509db02c6268fb712e8236093069c67a029e069bee0d333223b7b3f4a1e42612a3af65c079c756b15eecce5f3369d33c7ce1",
    "qi": "88911352f605c0254a3464d8333520eefdd06e5a985c1f88873714dfbb0764e9fa6b8e95e5e24369d6af22fb849a8c491d64f26e2fb566437b2de514838ca50b",
}

UA = "Dart/3.13 (dart:io)"
KEY = bytes.fromhex(hashlib.md5((PROFILE["time"] + "^~!@#[-" + PROFILE["package"]).encode()).hexdigest())
VIDEO_RE = re.compile(r"(?i)\.(?:mp4|m3u8|flv|mkv|mov|mpd|ts)(?:[?#].*)?$")


def _b64pad(s):
    return s + "=" * (-len(s) % 4)


class Spider(BaseSpider):
    def __init__(self):
        self.base = ROOTS[0]
        self.token = ""
        self.timeout = 12
        self.good_root = ""
        self.session = requests.Session() if requests else None

    # ---------- 基础 ----------
    def getName(self):
        return "大师兄"

    def init(self, extend=""):
        if isinstance(extend, dict):
            cfg = extend
        else:
            cfg = {}
            text = str(extend or "").strip()
            if text.startswith("{"):
                try:
                    cfg = json.loads(text)
                except Exception:
                    cfg = {}
        self.base = str(cfg.get("base") or cfg.get("api") or ROOTS[0]).rstrip("/")
        self.token = str(cfg.get("token") or "")
        try:
            self.timeout = max(4, min(30, int(cfg.get("timeout") or 12)))
        except Exception:
            self.timeout = 12
        return self

    def isVideoFormat(self, url):
        return bool(VIDEO_RE.search(str(url or "")))

    def manualVideoCheck(self):
        return False

    def _headers(self):
        return {
            "Content-Type": "text/plain",
            "User-Agent": UA,
            "version": PROFILE["version"],
            "version-number": PROFILE["build"],
            "build-time": PROFILE["time"],
            "pk-id": PROFILE["package"],
            "platform": "android",
            "platform-version": "16",
        }

    def _pack(self, method, params):
        data = dict(params or {})
        data["token"] = self.token
        text = json.dumps({"method": method, "data": data, "csrf": int(time.time() * 1000)},
                          separators=(",", ":"), ensure_ascii=False)
        iv = bytes(random.getrandbits(8) for _ in range(16))
        ct = AES.new(KEY, AES.MODE_CBC, iv).encrypt(pad(text.encode("utf-8"), 16))
        return base64.b64encode(iv + ct).decode().rstrip("=")

    def _decrypt(self, raw):
        if len(raw) < 32 or len(raw) % 16:
            raise ValueError("bad aes packet")
        text = unpad(AES.new(KEY, AES.MODE_CBC, raw[:16]).decrypt(raw[16:]), 16).decode("utf-8", "replace")
        return json.loads(text)

    def _unpack(self, text):
        s = (text or "").strip()
        if not s:
            raise ValueError("empty body")
        if s[0] in "{[":
            return json.loads(s)
        pos = s.find(MARKER)
        if pos >= 0:
            if s.find(MARKER, pos + len(MARKER)) >= 0:
                raise ValueError("repeated marker")
            prefix, tail = s[:pos], s[pos + len(MARKER):]
            count = int(base64.b64decode(_b64pad(tail)).decode())
            left = base64.b64decode(_b64pad(prefix[:count])).decode()
            if not re.fullmatch(r"(?:0x\d+)+", left):
                raise ValueError("bad envelope")
            values = [int(v) for v in re.findall(r"0x(\d+)", left)][::-1]
            right = base64.b64decode(_b64pad(prefix[count:]))
            out = bytearray(len(values) + len(right))
            for i, v in enumerate(values):
                delta = 11 if i % 2 == 0 else (4 if i % 3 == 0 else (2 if i % 5 == 0 else 3))
                out[i] = (v - delta) & 0xFF
            out[len(values):] = right
            return self._decrypt(bytes(out))
        return self._decrypt(base64.b64decode(_b64pad(s)))

    def _rpc(self, method, params=None):
        if not self.session or AES is None:
            raise RuntimeError("缺少 requests / pycryptodome")
        pool = [self.base]
        if self.base in ROOTS:
            if self.good_root in ROOTS and self.good_root != self.base:
                pool.insert(0, self.good_root)
            pool += [r for r in ROOTS if r not in pool]
        last = None
        for root in pool[:2]:
            try:
                r = self.session.post(root + PATH, data=self._pack(method, params or {}),
                                      headers=self._headers(), timeout=self.timeout)
            except Exception as e:
                last = e
                continue
            if r.status_code in (401, 403):
                raise RuntimeError("拒绝访问 %d" % r.status_code)
            if r.status_code != 200:
                last = RuntimeError("HTTP %d" % r.status_code)
                continue
            body = self._unpack(r.text)
            if int(body.get("code", 0)) == 1 and "data" in body:
                self.good_root = root
                return body["data"]
            raise RuntimeError("code=%s" % body.get("code"))
        raise RuntimeError("服务不可达: %s" % last)

    def _decode_parser(self, text):
        s = (text or "").strip()
        try:
            return json.loads(s)
        except Exception:
            pass
        if not s or len(s) > 5500 or not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", s):
            return None
        raw = base64.b64decode(_b64pad(s))
        if not raw or len(raw) % 128 or len(raw) > 128 * 32:
            return None
        n = int(PARSER_RSA["n"], 16)
        p, q = int(PARSER_RSA["p"], 16), int(PARSER_RSA["q"], 16)
        dp, dq, qi = int(PARSER_RSA["dp"], 16), int(PARSER_RSA["dq"], 16), int(PARSER_RSA["qi"], 16)
        chunks = []
        for at in range(0, len(raw), 128):
            c = int.from_bytes(raw[at:at + 128], "big")
            if c >= n:
                raise ValueError("rsa cipher too big")
            m1, m2 = pow(c, dp, p), pow(c, dq, q)
            block = (m2 + ((qi * (m1 - m2)) % p) * q).to_bytes(128, "big")
            if block[0] != 0 or block[1] != 2:
                raise ValueError("rsa padding")
            idx = 2
            while idx < 128 and block[idx]:
                idx += 1
            chunks.append(block[idx + 1:])
        return json.loads(unquote(b"".join(chunks).decode("ascii", "replace")))

    @staticmethod
    def _clean(v):
        return re.sub(r"<[^>]+>", "", str(v or "")).strip()

    def _card(self, v):
        if not isinstance(v, dict):
            return None
        vid = str(v.get("vod_id") or "")
        name = self._clean(v.get("vod_name"))
        if not vid.isdigit() or not name:
            return None
        item = {"vod_id": vid, "vod_name": name}
        if v.get("vod_pic"):
            item["vod_pic"] = str(v["vod_pic"])
        remarks = self._clean(v.get("vod_remarks") or v.get("vod_year"))
        if remarks:
            item["vod_remarks"] = remarks
        return item

    def _cards(self, rows):
        out, seen = [], set()
        for v in rows or []:
            c = self._card(v)
            if c and c["vod_id"] not in seen:
                seen.add(c["vod_id"])
                out.append(c)
        return out

    # ---------- 目录 ----------
    def homeContent(self, filter):
        try:
            classes = [{"type_id": "home", "type_name": "全部推荐"}]
            for n in self._rpc("nav") or []:
                tid, name = str(n.get("type_id") or ""), self._clean(n.get("type_name"))
                if tid.isdigit() and name and name != "直播":
                    classes.append({"type_id": tid, "type_name": name})
            return {"class": classes}
        except Exception:
            return {"class": [{"type_id": "home", "type_name": "全部推荐"}]}

    def homeVideoContent(self):
        try:
            data = self._rpc("index_recommend") or {}
            rows = []
            for block in data.get("videos") or []:
                rows.extend(block.get("vlist") or [])
            return {"list": self._cards(rows)}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        empty = {"list": [], "page": pg, "pagecount": 0, "limit": 21, "total": 0}
        try:
            ext = extend or {}
            if str(tid) == "home":
                data = self._rpc("index_recommend") or {}
                rows = []
                for block in data.get("videos") or []:
                    rows.extend(block.get("vlist") or [])
                return {"list": self._cards(rows), "page": 1, "pagecount": 1, "limit": len(rows), "total": len(rows)}
            if str(tid).startswith("rec:"):
                data = self._rpc("index_recommend_video_list", {"recommend_id": int(str(tid)[4:]), "pg": pg}) or []
                return {"list": self._cards(data), "page": pg, "pagecount": 9999 if len(data) >= 21 else pg,
                        "limit": 21, "total": 9999 if len(data) >= 21 else len(data)}
            order = str(ext.get("排序") or ext.get("order") or "")
            order = {"最新": "time", "最热": "hits", "热度": "hits", "评分": "score"}.get(order, order if order in ("time", "hits", "score") else "")
            data = self._rpc("video_list", {
                "tid": int(tid), "pg": pg,
                "class": str(ext.get("类型") or ""), "area": str(ext.get("地区") or ""),
                "lang": str(ext.get("语言") or ""), "year": str(ext.get("年份") or ""), "order": order,
            }) or []
            rows = self._cards(data)
            return {"list": rows, "page": pg, "pagecount": 9999 if len(data) >= 21 else pg,
                    "limit": 21, "total": 9999 if len(data) >= 21 else len(rows)}
        except Exception:
            return empty

    def searchContent(self, key, quick, pg="1"):
        try:
            data = self._rpc("search", {"text": str(key), "pg": int(pg or 1)}) or []
            return {"list": self._cards(data)}
        except Exception:
            return {"list": []}

    # ---------- 详情 ----------
    def detailContent(self, ids):
        try:
            vod_id = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
            d = self._rpc("video_detail", {"id": int(vod_id), "sign_md5": SIGN_MD5,
                                           "apk_path": APK_PATH, "apk_length": APK_LENGTH}) or {}
            info = d.get("vod_info") or {}
            if not info:
                return {"list": []}
            groups = self._groups(info)
            froms, urls = [], []
            for g in groups:
                parts = []
                for ep in g["episodes"]:
                    origin = ep["url"]
                    if self.isVideoFormat(origin) and origin.lower().startswith("http"):
                        token = origin
                    else:
                        token = base64.b64encode(json.dumps(
                            {"c": g["code"], "u": origin, "p": g["source"].get("parse_api") or "",
                             "x": g["source"].get("extra_parse_api") or "",
                             "s": g["source"].get("parse_secret") is True},
                            ensure_ascii=False, separators=(",", ":")).encode()).decode()
                    parts.append(ep["name"] + "$" + token)
                if not parts:
                    continue
                froms.append(g["name"])
                urls.append("#".join(parts))
            vod = {
                "vod_id": vod_id,
                "vod_name": self._clean(info.get("vod_name")),
                "vod_pic": str(info.get("vod_pic") or ""),
                "vod_remarks": self._clean(info.get("vod_remarks")),
                "vod_year": str(info.get("vod_year") or ""),
                "vod_area": self._clean(info.get("vod_area")),
                "vod_lang": self._clean(info.get("vod_lang")),
                "vod_class": self._clean(info.get("vod_class")),
                "vod_director": self._clean(info.get("vod_director")),
                "vod_actor": self._clean(info.get("vod_actor")),
                "vod_content": self._clean(info.get("vod_content")),
                "vod_play_from": "$$$".join(froms),
                "vod_play_url": "$$$".join(urls),
            }
            return {"list": [vod]}
        except Exception:
            return {"list": []}

    @staticmethod
    def _groups(info):
        groups, seen = [], set()
        for src in info.get("vod_url_with_player") or []:
            code, name, urls = str(src.get("code") or ""), str(src.get("name") or ""), src.get("url") or ""
            if not code or not name or code in seen:
                continue
            seen.add(code)
            eps, labels = [], {}
            for part in urls.split("#"):
                if "$" not in part:
                    continue
                label, origin = part.split("$", 1)
                label, origin = label.strip(), origin.strip()
                if not label or not origin or label in labels:
                    continue
                labels[label] = origin
                eps.append({"name": label, "url": origin})
            if eps:
                groups.append({"code": code, "name": name, "source": src, "episodes": eps})
        # 直链线路排前面
        groups.sort(key=lambda g: 0 if VIDEO_RE.search(g["episodes"][0]["url"]) else 1)
        return groups

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        url = str(id or "")
        if self.isVideoFormat(url) and url.lower().startswith("http"):
            return {"parse": 0, "url": url, "header": {}}
        try:
            box = json.loads(base64.b64decode(_b64pad(url)).decode())
        except Exception:
            return {"parse": 1, "url": url, "header": {"User-Agent": UA}}
        try:
            src = {"code": box.get("c"), "parse_api": box.get("p"), "extra_parse_api": box.get("x"),
                   "parse_secret": box.get("s")}
            got = self._resolve(src, box.get("u"))
            return {"parse": 0, "url": got["url"], "header": got.get("header") or {}}
        except Exception:
            return {"parse": 1, "url": box.get("u") or url, "header": {}}

    def _resolve(self, src, origin):
        direct = str(origin or "")
        if self.isVideoFormat(direct) and direct.lower().startswith("http"):
            return {"url": direct}

        headers = {"User-Agent": UA}
        if src.get("parse_secret") is True:
            body = self._rpc("secret_parse_api_url", {"url": direct, "player_code": src.get("code")})
            picked = self._pick(body)
            if picked:
                return picked
            raise RuntimeError("解析无结果")

        prefixes = []
        for field in ("parse_api", "extra_parse_api"):
            for line in str(src.get(field) or "").replace("\\n", "\n").split("\n"):
                line = line.strip()
                if line.startswith("http"):
                    prefixes.append(line)
        if not prefixes:
            raise RuntimeError("该线路无解析接口")

        err = None
        for prefix in prefixes[:2]:
            enc = quote(direct, safe="")
            if re.search(r"#url|\{\{url\}\}|\{url\}|%s", prefix):
                addr = re.sub(r"#url|\{\{url\}\}|\{url\}|%s", enc, prefix)
            else:
                addr = prefix + ("&" if "?" in prefix else "?") + "url=" + enc
            try:
                r = self.session.get(addr, timeout=self.timeout,
                                     headers={"User-Agent": UA, "Accept": "application/json,text/plain;q=0.9"})
            except Exception as e:
                err = e
                continue
            if r.status_code != 200:
                continue
            text = r.text or ""
            if text.lstrip().startswith("#EXTM3U"):
                return {"url": r.url, "header": headers}
            try:
                body = self._decode_parser(text)
            except Exception:
                body = None
            if body is None:
                continue
            body = json.loads(body) if isinstance(body, str) else body
            picked = self._pick(body)
            if picked:
                picked["header"] = headers
                return picked
            err = RuntimeError("解析无可用地址")
        raise RuntimeError("解析失败: %s" % err)

    @staticmethod
    def _pick(body):
        found = []

        def walk(v, depth=0):
            if depth > 6 or len(found) >= 12 or not v:
                return
            if isinstance(v, str):
                if v.startswith("http"):
                    found.append(v)
                return
            if isinstance(v, list):
                for x in v[:12]:
                    walk(x, depth + 1)
                return
            if isinstance(v, dict):
                for k in ("url", "play_url", "playUrl", "m3u8", "src",
                          "data", "result", "video", "play", "source", "sources", "urls"):
                    if k in v:
                        walk(v[k], depth + 1)
        walk(body)
        if not found:
            return None
        u = found[0]
        low = u.lower()
        mime = "HLS" if "m3u8" in low else ("MP4" if ".mp4" in low.split("?")[0] else "DASH" if ".mpd" in low.split("?")[0] else "")
        return {"url": u, "mime": mime}

    def localProxy(self, param):
        return [404, "text/plain", "", None]

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass
