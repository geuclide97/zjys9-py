# coding = utf-8
#!/usr/bin/python
import hashlib
import hmac
import json
import math
import re
import time
import uuid
import urllib.parse

from base.spider import Spider


class Spider(Spider):
    def __init__(self):
        self.name = "看剧AI"
        self.host = "https://kanju.ai"
        self.secret = "557d0e4ae929f438da6bd84412374e6086b8af09b3fed54bf22601d5bf8c54a0"
        self.ua = (
            "Mozilla/5.0 (Linux; Android 11; TV) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.cookie = ""
        self.anonymous_id = "web_{}".format(uuid.uuid4())
        self.cache = {}
        self.cache_timeout = 180

    def getName(self):
        return self.name

    def init(self, extend=""):
        pass

    def destroy(self):
        pass

    def _signature_headers(self, method, path):
        timestamp = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        message = "{}\n{}\n{}\n{}".format(method.upper(), path, timestamp, nonce)
        signature = hmac.new(
            self.secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Accept": "application/json",
            "User-Agent": self.ua,
            "Origin": self.host,
            "Referer": self.host + "/",
            "x-ai-movie-timestamp": timestamp,
            "x-ai-movie-nonce": nonce,
            "x-ai-movie-signature": signature,
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _save_session_cookie(self, response):
        try:
            cookies = getattr(response, "cookies", None)
            if cookies:
                value = cookies.get("ai_movie_session")
                if value:
                    self.cookie = "ai_movie_session={}".format(value)
                    return
        except Exception:
            pass

        try:
            headers = getattr(response, "headers", {})
            raw_values = []
            if hasattr(headers, "get_all"):
                raw_values = headers.get_all("Set-Cookie") or []
            if not raw_values:
                raw_values = [headers.get("Set-Cookie", "")]
            for raw_cookie in reversed(raw_values):
                match = re.search(r"ai_movie_session=([^;\s,]+)", str(raw_cookie))
                if match and match.group(1):
                    self.cookie = "ai_movie_session={}".format(match.group(1))
                    return
        except Exception:
            pass

    def _request(self, path, method="GET", body=None, need_session=False, use_cache=False):
        if need_session and not self.cookie and not self._ensure_session():
            return None

        cache_key = "{}:{}".format(method, path)
        if use_cache and cache_key in self.cache:
            value, cached_at = self.cache[cache_key]
            if time.time() - cached_at < self.cache_timeout:
                return value

        headers = self._signature_headers(method, path)
        url = self.host + path
        try:
            if method.upper() == "POST":
                headers["Content-Type"] = "application/json"
                payload = json.dumps(body or {}, ensure_ascii=False, separators=(",", ":"))
                response = self.post(url, headers=headers, data=payload, timeout=12)
            else:
                response = self.fetch(url, headers=headers, timeout=12)

            self._save_session_cookie(response)
            if getattr(response, "status_code", 0) not in (200, 201):
                return None
            data = response.json()
            if use_cache:
                self.cache[cache_key] = (data, time.time())
            return data
        except Exception as error:
            print("看剧AI请求失败 [{}]: {}".format(path, error))
            return None

    def _ensure_session(self):
        if self.cookie:
            return True
        data = self._request(
            "/v1/users/anonymous",
            method="POST",
            body={"anonymous_id": self.anonymous_id},
            need_session=False,
            use_cache=False,
        )
        return bool(data and self.cookie)

    def _parse_extend(self, extend):
        if isinstance(extend, dict):
            return extend
        if not extend:
            return {}
        try:
            value = json.loads(extend)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _card_to_video(self, item):
        return {
            "vod_id": str(item.get("id") or item.get("variant_id") or ""),
            "vod_name": str(item.get("title") or ""),
            "vod_pic": str(item.get("poster_url") or ""),
            "vod_remarks": str(item.get("remarks") or item.get("availability", {}).get("label") or ""),
            "style": {"type": "rect", "ratio": 0.75},
        }

    def _cards_to_videos(self, cards):
        videos = []
        seen = set()
        for item in cards or []:
            if not isinstance(item, dict):
                continue
            video = self._card_to_video(item)
            if video["vod_id"] and video["vod_id"] not in seen:
                seen.add(video["vod_id"])
                videos.append(video)
        return videos

    def _direct_lines(self, data):
        lines = []
        seen = set()
        for index, line in enumerate(data.get("line_options") or []):
            url = str(line.get("url") or "").strip()
            provider_id = str(line.get("provider_id") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            if line.get("resolved") is False or line.get("resolve_required") is True:
                continue
            if str(line.get("url_kind") or "").lower() not in ("m3u8", "mp4", "unknown"):
                continue
            unique_key = provider_id or url
            if unique_key in seen:
                continue
            seen.add(unique_key)
            label = str(
                line.get("provider_name")
                or line.get("display_label")
                or line.get("label")
                or "线路{}".format(len(lines) + 1)
            )
            label = label.replace("$", " ").replace("#", " ").strip()
            lines.append({
                "provider_id": provider_id,
                "play_from": str(line.get("play_from") or "").strip(),
                "label": label,
                "url": url,
                "weight": int(line.get("preference_weight") or 0),
                "index": index,
            })
        lines.sort(key=lambda item: (-item["weight"], item["index"]))
        return lines

    def _filters(self):
        return {
            key: [
                {
                    "key": "sort",
                    "name": "排序",
                    "value": [
                        {"n": "热度", "v": "trending"},
                        {"n": "最新", "v": "latest"},
                    ],
                },
                {
                    "key": "year",
                    "name": "年份",
                    "value": [{"n": "全部", "v": ""}]
                    + [{"n": str(year), "v": str(year)} for year in range(2026, 2015, -1)],
                },
                {
                    "key": "area",
                    "name": "地区",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "大陆", "v": "中国大陆"},
                        {"n": "香港", "v": "中国香港"},
                        {"n": "台湾", "v": "中国台湾"},
                        {"n": "美国", "v": "美国"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "英国", "v": "英国"},
                        {"n": "泰国", "v": "泰国"},
                    ],
                },
                {
                    "key": "genre",
                    "name": "类型",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "剧情", "v": "剧情"},
                        {"n": "喜剧", "v": "喜剧"},
                        {"n": "动作", "v": "动作"},
                        {"n": "爱情", "v": "爱情"},
                        {"n": "悬疑", "v": "悬疑"},
                        {"n": "犯罪", "v": "犯罪"},
                        {"n": "科幻", "v": "科幻"},
                        {"n": "奇幻", "v": "奇幻"},
                        {"n": "冒险", "v": "冒险"},
                        {"n": "动画", "v": "动画"},
                    ],
                },
            ]
            for key in ("hot", "movie", "series", "anime", "variety")
        }

    def homeContent(self, filter):
        result = {
            "class": [
                {"type_name": "热门", "type_id": "hot"},
                {"type_name": "电影", "type_id": "movie"},
                {"type_name": "电视剧", "type_id": "series"},
                {"type_name": "动漫", "type_id": "anime"},
                {"type_name": "综艺", "type_id": "variety"},
            ]
        }
        if filter:
            result["filters"] = self._filters()
        return result

    def homeVideoContent(self):
        path = "/v1/feed/home?scope=public&mode=preview&sections=4&cards=10&adult_confirmed=false"
        data = self._request(path, use_cache=True) or {}
        cards = []
        for section in data.get("sections") or []:
            cards.extend(section.get("cards") or [])
        return {"list": self._cards_to_videos(cards)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        extend = self._parse_extend(extend)
        tid = str(tid or "hot")

        params = []
        if tid != "hot":
            params.append(("kind", tid))
        sort = str(extend.get("sort") or "trending")
        params.append(("sort", sort))
        if sort == "trending":
            params.append(("window", "day"))
        for key in ("year", "area", "genre"):
            value = extend.get(key)
            if value not in (None, "", "0", "全部"):
                params.append((key, str(value)))
        params.extend((("page", str(page)), ("limit", "30")))
        path = "/v1/browse/catalog?" + urllib.parse.urlencode(params)
        data = self._request(path, use_cache=True) or {}
        videos = self._cards_to_videos(data.get("cards"))
        pagination = data.get("pagination") or {}
        limit = int(pagination.get("limit") or 30)
        total = int(pagination.get("total") or 0)
        has_more = bool(pagination.get("has_more"))
        pagecount = int(math.ceil(float(total) / limit)) if total and limit else page + (1 if has_more else 0)
        return {
            "list": videos,
            "page": page,
            "pagecount": max(page, pagecount),
            "limit": limit,
            "total": total,
        }

    def searchContent(self, key, quick, pg=1):
        try:
            page = max(1, int(pg or 1))
        except Exception:
            page = 1
        params = [("q", str(key or "")), ("page", str(page)), ("limit", "30")]
        path = "/v1/browse/catalog?" + urllib.parse.urlencode(params)
        data = self._request(path, use_cache=False) or {}
        pagination = data.get("pagination") or {}
        limit = int(pagination.get("limit") or 30)
        total = int(pagination.get("total") or 0)
        has_more = bool(pagination.get("has_more"))
        pagecount = int(math.ceil(float(total) / limit)) if total and limit else page + (1 if has_more else 0)
        return {
            "list": self._cards_to_videos(data.get("cards")),
            "page": page,
            "pagecount": max(page, pagecount),
            "limit": limit,
            "total": total,
        }

    def detailContent(self, ids):
        if isinstance(ids, (list, tuple)):
            vod_id = str(ids[0]) if ids else ""
        else:
            vod_id = str(ids or "")
        if not vod_id:
            return {"list": []}

        path = "/v1/catalog/{}?episodes=window&episode_limit=200".format(
            urllib.parse.quote(vod_id, safe="")
        )
        data = self._request(path, use_cache=True) or {}
        if not data.get("title"):
            return {"list": []}

        episodes = []
        for index, episode in enumerate(data.get("episodes") or []):
            token = str(episode.get("token") or "")
            if not token:
                continue
            number = episode.get("number") or index + 1
            title = str(episode.get("title") or "第{}集".format(number))
            title = title.replace("$", " ").replace("#", " ")
            episodes.append((title, token))

        if not episodes:
            return {"list": []}

        first_token = episodes[0][1]
        resolve_path = "/v1/playback/resolve/{}".format(
            urllib.parse.quote(first_token, safe="")
        )
        resolve_data = self._request(
            resolve_path, need_session=True, use_cache=True
        ) or {}
        direct_lines = self._direct_lines(resolve_data)

        play_from = []
        play_urls = []
        if direct_lines:
            used_labels = set()
            for line_index, line in enumerate(direct_lines, 1):
                label = line["label"] or "线路{}".format(line_index)
                original_label = label
                suffix = 2
                while label in used_labels:
                    label = "{}-{}".format(original_label, suffix)
                    suffix += 1
                used_labels.add(label)
                provider_id = line["provider_id"]
                play_from.append(label)
                play_urls.append("#".join(
                    "{}${}||{}".format(title, token, provider_id)
                    for title, token in episodes
                ))
        else:
            play_from.append("看剧AI")
            play_urls.append("#".join(
                "{}${}".format(title, token) for title, token in episodes
            ))

        vod = {
            "vod_id": vod_id,
            "vod_name": str(data.get("title") or ""),
            "vod_pic": str(data.get("poster_url") or ""),
            "type_name": ",".join(data.get("genres") or []),
            "vod_year": str(data.get("year") or ""),
            "vod_area": str(data.get("area") or ""),
            "vod_remarks": str(data.get("remarks") or ""),
            "vod_actor": ",".join(data.get("actors") or []),
            "vod_director": ",".join(data.get("directors") or []),
            "vod_content": str(data.get("description") or "").strip(),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_urls),
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_id = str(id or "").strip()
        parts = play_id.split("||", 1)
        token = parts[0].strip()
        selected_provider = parts[1].strip() if len(parts) > 1 else ""
        if not token:
            return {"parse": 0, "playUrl": "", "url": ""}
        if not token.startswith("YJ-") and re.match(r"^[a-fA-F0-9]{20}(?:\.m3u8)?$", token):
            token = "YJ-" + token.replace(".m3u8", "")

        path = "/v1/playback/resolve/{}".format(urllib.parse.quote(token, safe=""))
        data = self._request(path, need_session=True, use_cache=False) or {}
        direct_lines = self._direct_lines(data)

        if not direct_lines:
            return {"parse": 0, "playUrl": "", "url": ""}
        selected = None
        if selected_provider:
            selected = next(
                (line for line in direct_lines if line["provider_id"] == selected_provider),
                None,
            )
        if selected is None:
            selected = direct_lines[0]
        return {
            "parse": 0,
            "playUrl": "",
            "url": selected["url"],
            "header": json.dumps({"User-Agent": self.ua}, ensure_ascii=False),
        }

    def isVideoFormat(self, url):
        value = str(url or "").lower().split("?", 1)[0]
        return value.endswith((".m3u8", ".mp4", ".flv", ".ts", ".mkv"))

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None


if __name__ == "__main__":
    pass
