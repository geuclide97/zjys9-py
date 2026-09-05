# -*- coding: utf-8 -*-
"""
爱影 App 接口 - TVBox 通用 Python Spider
由 get.js 转换。
依赖：
    requests
    pycryptodome
TVBox 配置示例：
{
  "key": "爱影_py",
  "name": "♨️爱影｜4K线路",
  "type": 3,
  "api": "./py/爱影.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 1
}
extend参数示例关闭验证码识别：{"code":""}
"""
import base64
import hashlib
import json
import random
import re
import time
import uuid
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
    pad = unpad = None
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):
    DEFAULT_EXT = {
        "host": "https://aysappto.oss-cn-chengdu.aliyuncs.com/q23.txt",
        "key": "nzEqOgYk3QzHuEP8",
        "init": "V122",
        "api": 2,
        "ua": "okhttp/3.10.0"
    }
    PREFIX_MAP = {
        "1": "getappapi.index",
        "2": "qijiappapi.index",
        "3": "appapi"
    }

    def getName(self):
        return "爱影"

    def init(self, extend=""):
        self.ext = dict(self.DEFAULT_EXT)
        if isinstance(extend, dict):
            self.ext.update(extend)
        elif isinstance(extend, str) and extend.strip():
            try:
                obj = json.loads(extend)
                if isinstance(obj, dict):
                    self.ext.update(obj)
            except Exception:
                pass
        self.site_key = ""
        self.site_type = 3
        self.site_url = ""
        self.key = str(self.ext.get("key", ""))
        self.iv = str(self.ext.get("iv", "") or self.key)
        self.api_prefix = self.PREFIX_MAP.get(
            str(self.ext.get("api", "1")),
            "getappapi.index"
        )
        init_value = str(self.ext.get("init", "") or "")
        self.has_custom_init = init_value.startswith("V")
        self.init_suffix = "init" + init_value if self.has_custom_init else "init"
        self.enable_verify_time_sign = str(
            self.ext.get("time", "0")
        ).lower() in ("1", "true")
        self.force_verify_code = str(
            self.ext.get("code", "") or ""
        ).strip() or None
        self.custom_play_ua = str(
            self.ext.get("ua2", "") or ""
        ).strip()
        self.headers = {
            "User-Agent": str(
                self.ext.get("ua", "okhttp/3.10.0")
            ),
            "app-user-device-id": str(
                self.ext.get(
                    "id",
                    "291b226282010337c9443590d6457be15"
                )
            ),
            "app-version-code": str(
                self.ext.get("version", "112")
            )
        }
        token = str(self.ext.get("token", "") or "").strip()
        if token:
            self.headers["app-user-token"] = token
        head = str(self.ext.get("head", "") or "").strip()
        if head:
            for item in head.split(","):
                item = item.strip()
                if ":" not in item:
                    continue
                k, v = item.split(":", 1)
                if k.strip() and v.strip():
                    self.headers[k.strip()] = v.strip()
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update(self.headers)
        self.search_api_suffix = ""
        self.sou_param_name = ""
        self.sou_salt = ""
        self.extra_search_headers = {}
        self.search_status = False
        self.home_vods = []
        self.third_danmu_base_url = ""
        self._resolve_host()

    def isVideoFormat(self, url):
        return bool(re.search(
            r"(?i)\.(m3u8|mp4|mkv|flv|ts|mpd|avi|mov)(?:\?|$)",
            str(url or "")
        ))

    def manualVideoCheck(self):
        return False

    # -------------------- 工具函数 --------------------
    def _ensure_runtime(self):
        if requests is None:
            raise RuntimeError("缺少 requests 模块")
        if AES is None:
            raise RuntimeError("缺少 pycryptodome 模块")

    def _resolve_host(self):
        host = str(self.ext.get("host", "") or "").strip()
        if not host:
            return
        if (
            host.startswith("http")
            and (host.lower().endswith(".txt")
                 or host.lower().endswith(".json"))
            and self.session
        ):
            try:
                text = self._request_raw(host, method="get", timeout=8)
                urls = [
                    line.strip()
                    for line in text.splitlines()
                    if line.strip().startswith("http")
                ]
                if urls:
                    host = urls[0]
            except Exception:
                pass
        host = host.rstrip("/")
        if host and "php" not in host.lower():
            host += "/api.php"
        self.site_url = host

    def _headers(self, extra=None):
        out = dict(self.headers)
        if self.enable_verify_time_sign:
            timestamp = str(int(time.time()))
            out["app-api-verify-time"] = timestamp
            out["app-api-verify-sign"] = self._aes_encode(timestamp)
        if extra:
            out.update(extra)
        return out

    def _request_raw(
        self,
        url,
        data=None,
        headers=None,
        method="get",
        timeout=12,
        binary=False
    ):
        self._ensure_runtime()
        final_headers = self._headers(headers)
        if method.lower() == "post":
            response = self.session.post(
                url,
                data=data or {},
                headers=final_headers,
                timeout=timeout
            )
        else:
            response = self.session.get(
                url,
                params=data or None,
                headers=final_headers,
                timeout=timeout
            )
        response.raise_for_status()
        return response.content if binary else response.text

    def _request_json(
        self,
        url,
        data=None,
        headers=None,
        method="get",
        timeout=12
    ):
        text = self._request_raw(
            url,
            data=data,
            headers=headers,
            method=method,
            timeout=timeout
        )
        return json.loads(text)

    def _aes_encode(self, text, key=None, iv=None, output="base64"):
        self._ensure_runtime()
        key_b = (key or self.key).encode("utf-8")
        iv_b = (iv or self.iv).encode("utf-8")
        cipher = AES.new(key_b, AES.MODE_CBC, iv_b)
        encrypted = cipher.encrypt(pad(str(text).encode("utf-8"), AES.block_size))
        if output == "hex":
            return encrypted.hex()
        return base64.b64encode(encrypted).decode("utf-8")

    def _aes_decode(self, text, key=None, iv=None, input_type="base64"):
        self._ensure_runtime()
        key_b = (key or self.key).encode("utf-8")
        iv_b = (iv or self.iv).encode("utf-8")
        if input_type == "hex":
            encrypted = bytes.fromhex(str(text))
        else:
            encrypted = base64.b64decode(str(text))
        cipher = AES.new(key_b, AES.MODE_CBC, iv_b)
        decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
        return decrypted.decode("utf-8")

    @staticmethod
    def _md5(text):
        return hashlib.md5(
            str(text).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _process_signature_value(value):
        value = str(value or "")
        if len(value) < 8:
            return value[::-1]
        return value[:-8][::-1] + value[-8:][::-1]

    @staticmethod
    def _safe_json(text, default=None):
        try:
            return json.loads(text)
        except Exception:
            return default if default is not None else {}

    @staticmethod
    def _list_value(obj, key):
        value = obj.get(key, [])
        return value if isinstance(value, list) else []

    @staticmethod
    def _video_item(item):
        if not isinstance(item, dict):
            return {}
        return {
            "vod_id": item.get("vod_id", item.get("id", "")),
            "vod_name": item.get("vod_name", item.get("name", "")),
            "vod_pic": item.get("vod_pic", item.get("pic", "")),
            "vod_remarks": item.get(
                "vod_remarks",
                item.get("remarks", item.get("vod_score", ""))
            )
        }

    # -------------------- 初始化数据 --------------------
    def _load_home_data(self):
        if not self.site_url:
            raise RuntimeError("动态域名获取失败，site_url 为空")
        url = f"{self.site_url}/{self.api_prefix}/{self.init_suffix}"
        response = self._request_json(url)
        encrypted = response.get("data", "")
        if not encrypted:
            raise RuntimeError("初始化接口未返回 data")
        data = self._safe_json(self._aes_decode(encrypted), {})
        raw_danmu = (
            data.get("config", {}).get("third_danmu_url", "")
            if isinstance(data.get("config"), dict)
            else ""
        )
        if isinstance(raw_danmu, list):
            raw_danmu = next(
                (
                    x.strip()
                    for x in raw_danmu
                    if isinstance(x, str) and x.strip()
                ),
                ""
            )
        elif not isinstance(raw_danmu, str):
            raw_danmu = ""
        if raw_danmu:
            self.third_danmu_base_url = raw_danmu.strip()
            if not re.search(
                r"[?&]url=$",
                self.third_danmu_base_url,
                re.I
            ):
                self.third_danmu_base_url += (
                    "&url="
                    if "?" in self.third_danmu_base_url
                    else "?url="
                )
        else:
            self.third_danmu_base_url = "https://dmku.hls.one/?ac=dm&url="
        box_config = data.get("box_config")
        if box_config:
            swapped_key = self.key[::-1]
            dynamic_iv = self._md5(swapped_key)[:16]
            try:
                box_json = self._safe_json(
                    self._aes_decode(
                        box_config,
                        key=swapped_key,
                        iv=dynamic_iv
                    ),
                    {}
                )
                self.search_api_suffix = str(
                    box_json.get("search_name", "") or ""
                )
                signature_name = str(
                    box_json.get("signature_name", "") or ""
                )
                signature_value = str(
                    box_json.get("signature_value", "") or ""
                )
                if signature_name and signature_value:
                    self.sou_param_name = signature_name
                    self.sou_salt = self._process_signature_value(
                        signature_value
                    )
                api_header = box_json.get("api_header", {})
                if isinstance(api_header, dict):
                    h_key = str(api_header.get("key", "") or "")
                    h_value = str(api_header.get("value", "") or "")
                    if h_key and h_value:
                        self.extra_search_headers[h_key] = h_value
            except Exception:
                pass
        else:
            self.search_api_suffix = "searchList"
            self.sou_param_name = ""
            self.sou_salt = ""
        config = data.get("config", {})
        self.search_status = bool(
            config.get("system_search_verify_status", False)
        ) if isinstance(config, dict) else False
        return data

    # -------------------- TVBox Spider 方法 --------------------
    def homeContent(self, filter):
        try:
            data = self._load_home_data()
            classes = []
            filters = {}
            self.home_vods = []
            for item in self._list_value(data, "type_list"):
                if not isinstance(item, dict):
                    continue
                type_id = item.get("type_id", "")
                type_name = item.get("type_name", "")
                classes.append({
                    "type_id": str(type_id),
                    "type_name": str(type_name)
                })
                if str(type_id) not in ("", "0"):
                    recommend_list = item.get("recommend_list", [])
                    if isinstance(recommend_list, list):
                        self.home_vods.extend(recommend_list)
                filter_list = []
                name_map = {
                    "class": "分类",
                    "area": "区域",
                    "lang": "语言",
                    "year": "年份",
                    "sort": "排序"
                }
                for row in item.get("filter_type_list", []) or []:
                    if not isinstance(row, dict):
                        continue
                    key = str(row.get("name", "") or "")
                    values = row.get("list", [])
                    if key not in name_map or not isinstance(values, list):
                        continue
                    filter_list.append({
                        "key": key,
                        "name": name_map[key],
                        "value": [
                            {"n": str(v), "v": str(v)}
                            for v in values
                        ]
                    })
                if filter_list:
                    filters[str(type_id)] = filter_list
            return {
                "class": classes,
                "filters": filters
            }
        except Exception as exc:
            return {
                "class": [],
                "filters": {},
                "error": str(exc)
            }

    def homeVideoContent(self):
        return {
            "list": [
                self._video_item(item)
                for item in self.home_vods
                if isinstance(item, dict)
            ]
        }

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(int(pg or 1), 1)
            extend = extend if isinstance(extend, dict) else {}
            params = {
                "area": extend.get("area", "全部"),
                "sort": extend.get("sort", "最新"),
                "class": extend.get("class", "全部"),
                "type_id": tid,
                "year": extend.get("year", "全部"),
                "lang": extend.get("lang", "全部"),
                "page": page
            }
            url = f"{self.site_url}/{self.api_prefix}/typeFilterVodList"
            response = self._request_json(
                url,
                data=params,
                method="post"
            )
            encrypted = response.get("data", "")
            decoded = self._safe_json(
                self._aes_decode(encrypted),
                {}
            ) if encrypted else {}
            videos = decoded.get("recommend_list", [])
            if not isinstance(videos, list):
                videos = []
            return {
                "page": page,
                "pagecount": 9999 if videos else page,
                "limit": len(videos),
                "total": 999999 if videos else 0,
                "list": [
                    self._video_item(item)
                    for item in videos
                    if isinstance(item, dict)
                ]
            }
        except Exception as exc:
            return {
                "page": int(pg or 1),
                "pagecount": int(pg or 1),
                "limit": 0,
                "total": 0,
                "list": [],
                "error": str(exc)
            }

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else ids
            url = f"{self.site_url}/{self.api_prefix}/vodDetail"
            response = self._request_json(
                url,
                data={"vod_id": vod_id},
                method="post"
            )
            encrypted = response.get("data", "")
            info = self._safe_json(
                self._aes_decode(encrypted),
                {}
            ) if encrypted else {}
            vod = info.get("vod", {})
            if not isinstance(vod, dict):
                vod = {}
            video = {
                "vod_id": vod.get("vod_id", vod_id),
                "vod_name": vod.get("vod_name", ""),
                "vod_area": vod.get("vod_area", ""),
                "vod_director": vod.get("vod_director", ""),
                "vod_actor": vod.get("vod_actor", ""),
                "vod_pic": vod.get("vod_pic", ""),
                "vod_content": vod.get("vod_content", ""),
                "type_name": vod.get("vod_class", ""),
                "vod_year": vod.get("vod_year", "")
            }
            sources = []
            for source in info.get("vod_play_list", []) or []:
                if not isinstance(source, dict):
                    continue
                player = source.get("player_info", {})
                if not isinstance(player, dict):
                    player = {}
                parse_api = str(player.get("parse", "") or "")
                play_ua = str(
                    player.get("user_agent", "")
                    or self.custom_play_ua
                    or ""
                )
                episodes = []
                for episode in source.get("urls", []) or []:
                    if not isinstance(episode, dict):
                        continue
                    name = str(episode.get("name", "") or "")
                    play_url = str(episode.get("url", "") or "")
                    token = str(episode.get("token", "") or "")
                    parse_api_url = str(
                        episode.get("parse_api_url", "") or ""
                    )
                    nid = str(episode.get("nid", 1) or 1)
                    payload = "@@".join([
                        play_url,
                        parse_api,
                        token,
                        parse_api_url,
                        play_ua,
                        str(vod.get("vod_id", vod_id)),
                        nid
                    ])
                    episodes.append(f"{name}${payload}")
                sources.append({
                    "show": str(player.get("show", "Unknown") or "Unknown"),
                    "urls": "#".join(episodes)
                })
            counts = {}
            normalized = []
            for source in sources:
                show = source["show"]
                counts[show] = counts.get(show, 0) + 1
                if counts[show] > 1:
                    show = f"{show}{counts[show]}"
                normalized.append({
                    "show": show,
                    "urls": source["urls"]
                })

            def priority(name):
                text = str(name).lower()
                if "4k" in text:
                    return 1
                if "独家" in text:
                    return 3
                if "秒播" in text:
                    return 4
                if "自建" in text:
                    return 5
                if "蓝光" in text:
                    return 6
                if "专线" in text:
                    return 7
                return 8

            normalized.sort(key=lambda x: priority(x["show"]))
            video["vod_play_from"] = "$$$".join(
                x["show"] for x in normalized
            )
            video["vod_play_url"] = "$$$".join(
                x["urls"] for x in normalized
            )
            return {"list": [video]}
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    def playerContent(self, flag, id, vipFlags):
        try:
            parts = str(id or "").split("@@")
            parts += [""] * (7 - len(parts))
            play_url = parts[0]
            parse_api = parts[1]
            token = parts[2]
            parse_api_url = parts[3]
            play_ua = parts[4]
            vod_id = parts[5]
            nid = parts[6] or "1"
            danmaku_url = self._get_danmaku(vod_id, nid)
            result_headers = {}
            if play_ua:
                result_headers["User-Agent"] = play_ua
            if (
                play_url.startswith(("http://", "https://"))
                and re.search(r"(?i)\.(m3u8|mp4|mkv)(?:\?|$)", play_url)
                and not parse_api_url
            ):
                result = {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "danmaku": danmaku_url
                }
                if result_headers:
                    result["header"] = result_headers
                return result
            if parse_api.startswith("http"):
                parse_url = parse_api + play_url
                if token:
                    separator = "&" if "?" in parse_url else "?"
                    parse_url += separator + "token=" + quote(token)
                text = self._request_raw(
                    parse_url,
                    headers=result_headers or None,
                    method="get"
                )
                if "DOCTYPE html" in text:
                    result = {
                        "parse": 1,
                        "playUrl": "",
                        "url": parse_url,
                        "danmaku": danmaku_url
                    }
                else:
                    obj = self._safe_json(text, {})
                    final_url = obj.get("url", "")
                    if not final_url and isinstance(obj.get("data"), dict):
                        final_url = obj["data"].get("url", "")
                    result = {
                        "parse": 0,
                        "playUrl": "",
                        "url": final_url,
                        "danmaku": danmaku_url
                    }
                if result_headers:
                    result["header"] = result_headers
                return result
            params = {
                "parse_api": parse_api,
                "url": self._aes_encode(play_url),
                "token": token
            }
            url = f"{self.site_url}/{self.api_prefix}/vodParse"
            response = self._request_json(
                url,
                data=params,
                headers=result_headers or None,
                method="post"
            )
            encrypted = response.get("data", "")
            decoded = self._safe_json(
                self._aes_decode(encrypted),
                {}
            ) if encrypted else {}
            nested = self._safe_json(decoded.get("json", "{}"), {})
            final_url = nested.get("url", "")
            result = {
                "parse": 0,
                "playUrl": "",
                "url": final_url,
                "danmaku": danmaku_url
            }
            if result_headers:
                result["header"] = result_headers
            return result
        except Exception as exc:
            return {
                "parse": 1,
                "playUrl": "",
                "url": str(id or ""),
                "error": str(exc)
            }

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        try:
            if self.has_custom_init or not self.search_api_suffix:
                self._load_home_data()
            search_path = self.search_api_suffix or "searchList"
            url = f"{self.site_url}/{self.api_prefix}/{search_path}"
            params = {
                "page": str(pg or "1"),
                "type_id": "0",
                "keywords": key
            }
            if self.sou_param_name and self.sou_salt:
                timestamp = str(int(time.time()))
                raw = (
                    f"/{self.sou_param_name}-{timestamp}"
                    f"-sb-0-{self.sou_salt}"
                )
                value = f"{timestamp}-sb-0-{self._md5(raw)}"
                params[self.sou_param_name] = value
            if self.force_verify_code:
                params["code"] = self.force_verify_code
                params["key"] = str(uuid.uuid4())
            search_headers = dict(self.extra_search_headers)
            attempted_slider = False
            attempted_captcha = False
            wait_retries = 0
            while True:
                response = self._request_json(
                    url,
                    data=params,
                    headers=search_headers,
                    method="post"
                )
                if (
                    response.get("code") == 1001
                    and response.get("need_slider") is True
                    and not attempted_slider
                ):
                    attempted_slider = True
                    if self._verify_slider(search_headers):
                        continue
                message = str(response.get("msg", "") or "")
                response_data = response.get("data")
                if (
                    response.get("code") == 0
                    and not response_data
                    and re.search(
                        r"等.*秒|等待.*秒|请等待|稍等|稍候",
                        message,
                        re.I
                    )
                    and wait_retries < 2
                ):
                    seconds = self._extract_wait_time(message)
                    time.sleep(min(max(seconds + 1, 2), 31))
                    wait_retries += 1
                    continue
                if response_data:
                    decoded = self._safe_json(
                        self._aes_decode(response_data),
                        {}
                    )
                    videos = decoded.get("search_list", [])
                    if not isinstance(videos, list):
                        videos = []
                    return {
                        "list": [
                            self._video_item(item)
                            for item in videos
                            if isinstance(item, dict)
                        ],
                        "page": int(pg or 1)
                    }
                need_code = (
                    self.search_status
                    or "验证码" in message
                )
                if (
                    need_code
                    and not self.force_verify_code
                    and not attempted_captcha
                ):
                    attempted_captcha = True
                    code_data = self._solve_captcha()
                    if code_data:
                        params.update(code_data)
                        continue
                break
            return {"list": [], "page": int(pg or 1)}
        except Exception as exc:
            return {
                "list": [],
                "page": int(pg or 1),
                "error": str(exc)
            }

    # -------------------- 搜索验证 --------------------
    def _verify_slider(self, search_headers):
        try:
            url = f"{self.site_url}/{self.api_prefix}/getSlider"
            response = self._request_json(
                url,
                data={},
                headers=search_headers,
                method="post"
            )
            encrypted = response.get("data", "")
            if response.get("code") != 1 or not encrypted:
                return False
            slider = self._safe_json(
                self._aes_decode(encrypted),
                {}
            )
            slider_id = str(slider.get("slider_id", "") or "")
            target_x = int(slider.get("target_x", 0) or 0)
            width = int(slider.get("bg_width", 280) or 280)
            if not slider_id or target_x <= 0:
                return False
            position = min(
                max(target_x + random.randint(-1, 1), 1),
                width
            )
            timestamp = str(int(time.time() * 1000))
            time.sleep(1)
            verify_url = (
                f"{self.site_url}/{self.api_prefix}/verifySlider"
            )
            verify = self._request_json(
                verify_url,
                data={
                    "pos_x": str(position),
                    "slider_id": slider_id,
                    "timestamp": timestamp
                },
                headers=search_headers,
                method="post"
            )
            encrypted_result = verify.get("data", "")
            if verify.get("code") != 1 or not encrypted_result:
                return False
            result = self._safe_json(
                self._aes_decode(encrypted_result),
                {}
            )
            return result.get("verified") is True
        except Exception:
            return False

    def _solve_captcha(self):
        """外部OCR接口已经大概率失效，需要自行替换可用OCR接口"""
        try:
            captcha_key = str(uuid.uuid4())
            prefix = self.api_prefix.replace(".index", "")
            url = (
                f"{self.site_url}/{prefix}.verify/create"
                f"?key={captcha_key}"
            )
            image = self._request_raw(
                url,
                method="get",
                binary=True
            )
            image_b64 = base64.b64encode(image).decode("utf-8")
            # 原接口已失效，如需验证码请替换为自己可用OCR服务
            """
            ocr = self.session.post(
                "https://api.nn.ci/ocr/b64/text",
                data=image_b64,
                headers={"User-Agent": "okhttp/3.10.0"},
                timeout=15
            )
            ocr.raise_for_status()
            code = ocr.text.strip()
            if not code:
                return None
            return {
                "code": code,
                "key": captcha_key
            }
            """
            return None
        except Exception:
            return None

    @staticmethod
    def _extract_wait_time(message):
        digit = re.search(r"(\d+)\s*秒", message)
        if digit:
            return int(digit.group(1))
        cn = re.search(
            r"([零一二三四五六七八九十两壹贰叁肆伍陆柒捌玖拾〇]+)\s*秒",
            message
        )
        if cn:
            return Spider._chinese_to_number(cn.group(1))
        if re.search(r"几秒|数秒|若干秒", message):
            return 3
        return 2

    @staticmethod
    def _chinese_to_number(text):
        mapping = {
            "零": 0, "〇": 0,
            "一": 1, "壹": 1,
            "二": 2, "贰": 2, "两": 2,
            "三": 3, "叁": 3,
            "四": 4, "肆": 4,
            "五": 5, "伍": 5,
            "六": 6, "陆": 6,
            "七": 7, "柒": 7,
            "八": 8, "捌": 8,
            "九": 9, "玖": 9,
            "十": 10, "拾": 10
        }
        if len(text) == 1:
            return mapping.get(text, 2)
        text = text.replace("拾", "十")
        if "十" in text:
            left, _, right = text.partition("十")
            tens = mapping.get(left, 1) if left else 1
            units = mapping.get(right, 0) if right else 0
            return tens * 10 + units
        return 2

    # -------------------- 弹幕 --------------------
    def _get_danmaku(self, vod_id, nid):
        if not self.third_danmu_base_url or not vod_id:
            return ""
        try:
            position = max(int(nid or 1) - 1, 0)
            url = f"{self.site_url}/{self.api_prefix}/danmuList"
            response = self._request_json(
                url,
                data={
                    "url_position": str(position),
                    "vod_id": str(vod_id)
                },
                method="post"
            )
            encrypted = response.get("data", "")
            if not encrypted:
                return ""
            data = self._safe_json(
                self._aes_decode(encrypted),
                {}
            )
            official = str(data.get("official_url", "") or "")
            if not official:
                return ""
            return self.third_danmu_base_url + official
        except Exception:
            return ""

    def localProxy(self, param):
        """本脚本未实现代理中转，需要壳自带proxy能力"""
        return [404, "text/plain", "Proxy Not Implemented"]
