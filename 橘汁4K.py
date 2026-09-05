# -*- coding: utf-8 -*-
import base64
import json
import random
import re
import struct
import time
import uuid
from urllib.parse import quote

try:
    import requests
except Exception:
    requests = None

try:
    from Crypto.Cipher import AES, PKCS1_v1_5
    from Crypto.PublicKey import RSA
    from Crypto.Util.Padding import pad, unpad
except Exception:
    AES = PKCS1_v1_5 = RSA = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):
    CONFIG = {
        "appName": "橘汁",
        "publicKey": "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCr8SzZhjYy+rsya1K09t8d2K50pWFoBkgUqMpKOiW+3IEVKd4eTdvg9RSOjQ82kypL6R9BnsmrS1V8s4PVDwjQbUtYhTPPC9Hz16qY7rpD6m0d2vr09/UpWQ5uOy9PR0QTrsioveZ+DIe9jc3C+zBCu/kZSY/R8stwJoiitki3gwIDAQAB",
        "dataKey": "DGVQRUX5R1LWWDLHTGJSUKG1DJRVPQ==",
        "dataIv": "OC1A06E197EF10CF3F6058CA7A803B5E",
        "pkg": "com.lxf.snzlcgtzxyx",
        "host": "",
        "site": "https://123-1349250429.cos.ap-shanghai.myqcloud.com/app.txt",
        "version": "3.0.2.1",
        "decrypt": "1"
    }

    def getName(self):
        return "橘汁"

    def init(self, extend=""):
        self.cfg = dict(self.CONFIG)
        if isinstance(extend, dict):
            self.cfg.update(extend)
        elif isinstance(extend, str) and extend.strip():
            try:
                self.cfg.update(json.loads(extend))
            except Exception:
                pass

        self.host = str(self.cfg.get("host", "")).rstrip("/")
        self.public_key = str(self.cfg.get("publicKey", ""))
        self.dynamic_key = ""
        self.data_key = str(self.cfg.get("dataKey", ""))
        self.data_iv = str(self.cfg.get("dataIv", ""))
        self.common_key = "ed5fdsgucxumegqa"
        self.session = requests.Session() if requests else None

        site = str(self.cfg.get("site", ""))
        if site and self.session:
            try:
                obj = self.session.get(site, timeout=12).json()
                domain = str(obj.get("domain", "")).strip().rstrip("/")
                if domain:
                    self.host = domain
            except Exception:
                pass

        if self.host:
            try:
                self._load_dynamic_key()
            except Exception:
                self.dynamic_key = ""

    # ========== UI6 必需的空方法 ==========
    def localProxy(self, param):
        return [404, "text/plain", "", None]

    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(?:mp4|m3u8|flv|mkv|avi|ts|mov|mpd|m4a|wmv)(?:\?.*)?$", str(url)))

    def manualVideoCheck(self):
        return False

    # ---------- protobuf wire ----------
    @staticmethod
    def _varint(value):
        value = int(value)
        out = bytearray()
        while value > 0x7f:
            out.append((value & 0x7f) | 0x80)
            value >>= 7
        out.append(value)
        return bytes(out)

    @classmethod
    def _pb_int(cls, field, value):
        return cls._varint(field << 3) + cls._varint(value)

    @classmethod
    def _pb_bytes(cls, field, value):
        if isinstance(value, str):
            value = value.encode("utf-8")
        return cls._varint((field << 3) | 2) + cls._varint(len(value)) + value

    @staticmethod
    def _read_varint(data, pos):
        value = 0
        shift = 0
        while pos < len(data):
            b = data[pos]
            pos += 1
            value |= (b & 0x7f) << shift
            if not b & 0x80:
                return value, pos
            shift += 7
            if shift > 70:
                raise ValueError("bad protobuf varint")
        raise ValueError("truncated protobuf varint")

    @classmethod
    def _pb_parse(cls, data):
        fields = {}
        pos = 0
        while pos < len(data):
            key, pos = cls._read_varint(data, pos)
            field, wire = key >> 3, key & 7
            if wire == 0:
                value, pos = cls._read_varint(data, pos)
            elif wire == 1:
                value = data[pos:pos + 8]
                pos += 8
            elif wire == 2:
                size, pos = cls._read_varint(data, pos)
                value = data[pos:pos + size]
                pos += size
            elif wire == 5:
                value = data[pos:pos + 4]
                pos += 4
            else:
                raise ValueError("unsupported protobuf wire type: %s" % wire)
            fields.setdefault(field, []).append(value)
        return fields

    @staticmethod
    def _first(fields, number, default=b""):
        values = fields.get(number)
        return values[0] if values else default

    @staticmethod
    def _text(value):
        if isinstance(value, bytes):
            return value.decode("utf-8", "ignore")
        return str(value or "")

    # ---------- crypto ----------
    @staticmethod
    def _random(length):
        chars = "1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        return "".join(random.choice(chars) for _ in range(max(0, length - 1))) + "="

    @staticmethod
    def _check_crypto():
        if AES is None or RSA is None:
            raise RuntimeError("缺少 pycryptodome：请确保 Python 环境可导入 Crypto")

    @classmethod
    def _aes_encrypt_ecb(cls, text, key):
        cls._check_crypto()
        cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
        return base64.b64encode(cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))).decode("utf-8")

    @classmethod
    def _aes_decrypt_ecb(cls, text, key):
        cls._check_crypto()
        raw = base64.b64decode(text)
        cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
        return unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8", "ignore")

    @classmethod
    def _aes_encrypt_cbc_hex(cls, text, key):
        cls._check_crypto()
        key_b = key.encode("utf-8")
        cipher = AES.new(key_b, AES.MODE_CBC, iv=key_b)
        return cipher.encrypt(pad(text.encode("utf-8"), AES.block_size)).hex()

    @classmethod
    def _rsa_encrypt(cls, text, public_key_b64):
        cls._check_crypto()
        der = base64.b64decode(public_key_b64)
        key = RSA.import_key(der)
        return base64.b64encode(PKCS1_v1_5.new(key).encrypt(text.encode("utf-8"))).decode("utf-8")

    # ---------- request protocol ----------
    def _device(self):
        uid = uuid.uuid4().hex.upper()
        version = str(self.cfg.get("version", ""))
        return {
            "country": "CN", "vName": version, "cpuId": "MT6893Z%2FCZA", "young": 0,
            "facturer": "Xiaomi", "pkg": self.cfg.get("pkg", ""), "uuid": uid,
            "resolution": "1080x2272", "mac": "02%3A00%3A00%3A00%3A00%3A00", "abid": "397",
            "model": "M2012K11AC", "plat": "android", "udid": uid, "dpi": "440", "net": "1",
            "lang": "zh", "brand": "Xiaomi", "density": "2.75", "appName": self.cfg.get("appName", "橘汁"),
            "cpu": "arm64-v8a", "chid": "10000", "carrier": "%E8%81%94%E9%80%9A",
            "_vOsCode": 30, "vOs": "11", "v": 1, "tenantId": "",
            "vApp": version.replace(".", ""), "device": 0, "androidID": uid.lower()[:16]
        }

    def _public_headers(self, protobuf=True):
        key = self.dynamic_key or self.public_key
        device = self._device()
        timestamp = int(time.time() * 1000)
        random_str = self._random(16)
        vapp = device.get("vApp") or "3019"
        device["sig"] = self._rsa_encrypt(str(timestamp) + random_str + vapp, key)
        device["random_str"] = random_str
        device["timestamp"] = timestamp
        sig23 = self._aes_encrypt_ecb(str(timestamp) + random_str, self.data_iv)
        device["sig2"] = sig23[:8]
        device["sig3"] = sig23[8:]
        params = self._aes_encrypt_cbc_hex(json.dumps(device, ensure_ascii=False, separators=(",", ":")), self.common_key)
        ctype = "application/x-protobuf" if protobuf else "application/json; charset=utf-8"
        accept = "application/x-protobuf" if protobuf else "application/json"
        return {
            "User-Agent": "okhttp/3.12.1", "Accept": accept, "Content-Type": ctype,
            "publicParams": json.dumps({"paramsData": params}, ensure_ascii=False, separators=(",", ":"))
        }

    def _secure_body(self, params):
        timestamp = int(time.time() * 1000)
        random8 = self._random(8)
        fake20 = self._random(20)
        query = "&".join("%s=%s" % (k, v) for k, v in params.items() if v is not None and str(v) != "")
        encrypted = random8 + self._aes_encrypt_ecb(query + str(timestamp), self.data_key)
        return b"".join([
            self._pb_bytes(1, encrypted[:20]), self._pb_bytes(2, encrypted[20:]),
            self._pb_bytes(3, fake20), self._pb_int(4, timestamp), self._pb_bytes(5, random8)
        ])

    # ========== 改写网络请求（优先使用 self.fetch） ==========
    def _post(self, path, body):
        if not self.host:
            raise RuntimeError("橘汁接口域名获取失败")
        url = self.host + path
        headers = self._public_headers(True)
        if hasattr(self, 'fetch') and callable(self.fetch):
            try:
                rsp = self.fetch(url, method='POST', headers=headers, data=body, timeout=18)
                if rsp and rsp.status_code == 200:
                    return rsp.content
            except Exception as e:
                print(f"[橘汁] fetch POST 失败: {e}")
        if self.session:
            try:
                r = self.session.post(url, data=body, headers=headers, timeout=18)
                r.raise_for_status()
                return r.content
            except Exception as e:
                raise RuntimeError(f"requests 请求失败: {e}")
        raise RuntimeError("无法发送 POST 请求")

    def _get_json(self, path):
        if not self.host:
            raise RuntimeError("橘汁接口域名获取失败")
        url = self.host + path
        headers = self._public_headers(False)
        if hasattr(self, 'fetch') and callable(self.fetch):
            try:
                rsp = self.fetch(url, method='GET', headers=headers, timeout=18)
                if rsp and rsp.status_code == 200:
                    return rsp.json()
            except Exception as e:
                print(f"[橘汁] fetch GET 失败: {e}")
        if self.session:
            try:
                r = self.session.get(url, headers=headers, timeout=18)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                raise RuntimeError(f"requests 请求失败: {e}")
        raise RuntimeError("无法发送 GET 请求")

    def _api_data(self, raw):
        return self._first(self._pb_parse(raw), 3, b"")

    def _load_dynamic_key(self):
        timestamp = int(time.time() * 1000)
        random_str = self._random(16)
        sign = self._rsa_encrypt(str(timestamp) + random_str, self.public_key)
        body = b"".join([
            self._pb_int(1, timestamp), self._pb_bytes(2, sign), self._pb_bytes(3, self._random(16)),
            self._pb_bytes(4, random_str), self._pb_bytes(5, self._random(16))
        ])
        data = self._api_data(self._post("/api/v5/find/app/zone", body))
        f = self._pb_parse(data)
        self.dynamic_key = "".join(self._text(self._first(f, n)) for n in (2, 3, 4, 5))

    # ---------- response parsers ----------
    def _parse_cover(self, raw):
        f = self._pb_parse(raw)
        return {"path": self._text(self._first(f, 1)), "thumb": self._text(self._first(f, 2))}

    def _parse_drama(self, raw):
        f = self._pb_parse(raw)
        cover = self._parse_cover(self._first(f, 2, b"")) if self._first(f, 2, b"") else {}
        return {
            "vod_id": str(self._first(f, 3, 0)), "vod_name": self._text(self._first(f, 5)),
            "vod_pic": cover.get("thumb") or cover.get("path", ""), "vod_remarks": self._text(self._first(f, 13)),
            "vod_year": str(self._first(f, 14, "")), "vod_area": self._text(self._first(f, 1))
        }

    def _parse_drama_page(self, raw):
        page = self._pb_parse(self._api_data(raw))
        return [self._parse_drama(v) for v in page.get(1, [])]

    def _parse_video(self, raw):
        f = self._pb_parse(raw)
        return {
            "title": self._text(self._first(f, 2)), "path": self._text(self._first(f, 4)),
            "source": self._text(self._first(f, 9)), "source_cn": self._text(self._first(f, 10))
        }

    # ---------- spider API ----------
    def homeContent(self, filter):
        try:
            obj = self._get_json("/api/v3/drama/getCategory?orderBy=type_id")
            classes, filters = [], {}
            for item in obj.get("data") or []:
                if str(item.get("name", "")) == "公告":
                    continue
                tid, name = str(item.get("id", "")), str(item.get("name", ""))
                if not tid:
                    continue
                classes.append({"type_id": tid, "type_name": name})
                raw_filter = item.get("converUrl") or ""
                try:
                    ext = json.loads(raw_filter) if isinstance(raw_filter, str) else raw_filter
                except Exception:
                    ext = {}
                fl = []
                for key in ("class", "lang", "area", "year", "extend_sort"):
                    value = ext.get(key, "") if isinstance(ext, dict) else ""
                    if value:
                        vals = [x for x in str(value).split("|") if x]
                        fl.append({"key": key, "name": key, "value": [{"n": x, "v": x} for x in vals]})
                if fl:
                    filters[tid] = fl
            return {"class": classes, "filters": filters}
        except Exception as e:
            return {"class": [], "filters": {}, "error": str(e)}

    def homeVideoContent(self):
        try:
            obj = self._get_json("/api/ex/v3/security/tag/list")
            data = obj.get("data", "")
            if str(self.cfg.get("decrypt", "1")) != "0" and data:
                data = self._aes_decrypt_ecb(data, self.data_key)
                data = self._aes_decrypt_ecb(data, self.data_iv)
            arr = json.loads(data) if isinstance(data, str) else data
            videos = []
            for block in arr or []:
                for section in block.get("sections") or []:
                    for vod in section.get("vodList") or []:
                        pic = (vod.get("coverImage") or {}).get("path", "")
                        videos.append({"vod_id": str(vod.get("id", "")), "vod_name": vod.get("name", ""), "vod_pic": pic, "vod_remarks": vod.get("remark", "")})
            return {"list": videos}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        params = {
            "pagesize": "21", "typeId1": str(tid), "page": str(pg),
            "vodOrderBy": (extend or {}).get("extend_sort", "最新"),
            "vodArea": (extend or {}).get("area", ""), "vodLang": (extend or {}).get("lang", ""),
            "vodClass": (extend or {}).get("class", ""), "vodYear": (extend or {}).get("year", "")
        }
        try:
            raw = self._post("/api/proto/v5/drama/getList", self._secure_body(params))
            videos = self._parse_drama_page(raw)
            page = int(pg)
            return {"list": videos, "page": page, "pagecount": page + (1 if len(videos) >= 21 else 0), "limit": 21, "total": 999999}
        except Exception as e:
            return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": 21, "total": 0, "error": str(e)}

    def detailContent(self, ids):
        try:
            print(f"[橘汁] 开始加载详情，ids={ids}")
            raw = self._post("/api/proto/v5/drama/getDetail", self._secure_body({"id": str(ids[0])}))
            print(f"[橘汁] 详情原始数据长度: {len(raw)}")
            
            api_data = self._api_data(raw)
            print(f"[橘汁] API 数据长度: {len(api_data)}")
            
            f = self._pb_parse(api_data)
            print(f"[橘汁] Protobuf 解析完成，字段: {list(f.keys())}")
            
            cover_raw = self._first(f, 2, b"")
            cover = self._parse_cover(cover_raw) if cover_raw else {}
            print(f"[橘汁] 封面解析: {cover}")
            
            sources = {}
            for item in f.get(29, []):
                video = self._parse_video(item)
                source = video["source_cn"] or "橘汁"
                path = video["path"]
                print(f"[橘汁] 视频源: {source}, path: {path[:50] if path else '空'}...")
                if not self.isVideoFormat(path):
                    token = base64.b64encode(json.dumps({"vodPlayFrom": video["source"], "playUrl": path}, ensure_ascii=False, separators=(",", ":")).encode()).decode()
                else:
                    token = path
                sources.setdefault(source, []).append((video["title"] or "播放") + "$" + token)
            
            vod = {
                "vod_id": str(ids[0]),
                "vod_name": self._text(self._first(f, 9)),
                "vod_pic": cover.get("path") or cover.get("thumb", ""),
                "vod_actor": self._text(self._first(f, 25)),
                "vod_director": self._text(self._first(f, 12)),
                "vod_area": self._text(self._first(f, 1)),
                "vod_year": str(self._first(f, 18, "")),
                "vod_remarks": self._text(self._first(f, 26)),
                "vod_content": self._text(self._first(f, 6)),
                "vod_play_from": "$$$".join(sources.keys()),
                "vod_play_url": "$$$".join("#".join(v) for v in sources.values())
            }
            print(f"[橘汁] 详情解析完成: {vod.get('vod_name')}")
            return {"list": [vod]}
        except Exception as e:
            import traceback
            print(f"[橘汁] detailContent 错误: {e}")
            traceback.print_exc()
            return {"list": [], "error": str(e)}

    def searchContent(self, key, quick, pg="1"):
        try:
            raw = self._post("/api/proto/v5/drama/search", self._secure_body({"searchKeys": key, "page": str(pg), "pagesize": "21"}))
            return {"list": self._parse_drama_page(raw)}
        except Exception as e:
            return {"list": [], "error": str(e)}

    def playerContent(self, flag, id, vipFlags):
        try:
            if self.isVideoFormat(id):
                return {"parse": 0, "url": id, "header": {}}
            params = json.loads(base64.b64decode(id).decode("utf-8"))
            raw = self._post("/api/proto/v5/videoUsableUrl", self._secure_body(params))
            f = self._pb_parse(self._api_data(raw))
            headers = {}
            for entry in f.get(6, []):
                ef = self._pb_parse(entry)
                k, v = self._text(self._first(ef, 1)), self._text(self._first(ef, 2))
                if k:
                    headers[k] = v
            return {"parse": 0, "url": self._text(self._first(f, 1)), "header": headers}
        except Exception as e:
            return {"parse": 1, "url": id, "header": {}, "error": str(e)}