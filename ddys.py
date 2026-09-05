# -*- coding: utf-8 -*-
"""
低端影视 ddys.io - TVBox 通用 Python Spider
来源：csp_ddys
依赖：requests
"""
import json
import re
import sys
from urllib.parse import quote
try:
    import requests
except Exception:
    requests = None
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

sys.path.append('..')

class Spider(BaseSpider):
    DEFAULT_HOST = "https://ddys.io"
    API_PATH = "/api/v1"
    CATEGORIES = [
        {"type_id": "latest", "type_name": "最新更新"},
        {"type_id": "movie", "type_name": "电影"},
        {"type_id": "series", "type_name": "剧集"},
        {"type_id": "anime", "type_name": "动漫"},
        {"type_id": "variety", "type_name": "综艺"},
    ]

    def getName(self):
        return "低端影视"

    def init(self, extend=""):
        host = self.DEFAULT_HOST
        if isinstance(extend, dict):
            host = str(extend.get("host", host) or host)
        elif isinstance(extend, str) and extend.strip():
            text = extend.strip()
            if text.startswith("http"):
                host = text
            else:
                try:
                    obj = json.loads(text)
                    if isinstance(obj, dict):
                        host = str(obj.get("host", host) or host)
                except Exception:
                    pass
        self.host = host.rstrip("/")
        self.api = self.host + self.API_PATH
        self.session = requests.Session() if requests else None
        self.timeout = 10
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.host + "/",
            "X-Requested-With": "XMLHttpRequest",
        }
        if self.session:
            self.session.headers.update(self.headers)
            try:
                self.session.get(self.host + "/", timeout=self.timeout)
            except Exception:
                pass

    def isVideoFormat(self, url):
        return bool(re.search(
            r"(?i)(m3u8|mp4|flv|avi|mov|mkv|mpd)",
            str(url or "")
        ))

    def manualVideoCheck(self):
        return False

    # -------------------- 请求封装 --------------------
    def _check_runtime(self):
        if requests is None:
            raise RuntimeError("缺少 requests 模块")

    def _get_json(self, path, params=None):
        self._check_runtime()
        url = self.api + path
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    # -------------------- 列表解析 --------------------
    @staticmethod
    def _vod_item(item):
        if not isinstance(item, dict):
            return {}
        return {
            "vod_id": str(item.get("slug", "") or ""),
            "vod_name": str(item.get("title", "") or ""),
            "vod_pic": str(item.get("poster", "") or ""),
            "vod_remarks": str(item.get("rating", "") or ""),
            "vod_year": str(item.get("year", "") or ""),
            "type_name": str(item.get("type", "") or ""),
        }

    def _parse_vod_list(self, items):
        if not isinstance(items, list):
            return []
        return [
            self._vod_item(item)
            for item in items
            if isinstance(item, dict)
        ]

    # -------------------- 首页 --------------------
    def homeContent(self, filter):
        try:
            classes = []
            for cat in self.CATEGORIES:
                classes.append({
                    "type_id": cat["type_id"],
                    "type_name": cat["type_name"]
                })
            return {
                "class": classes,
                "list": []
            }
        except Exception as exc:
            return {
                "class": [],
                "list": [],
                "error": str(exc)
            }

    def homeVideoContent(self):
        try:
            data = self._get_json("/movies", {"limit": 24})
            if not data or not data.get("data"):
                return {"list": []}
            return {"list": self._parse_vod_list(data["data"])}
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    # -------------------- 分类 --------------------
    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(int(pg or 1), 1)
            params = {"page": page, "limit": 24}
            if tid and tid != "latest":
                params["type"] = tid
            data = self._get_json("/movies", params=params)
            if not data or not data.get("data"):
                return {
                    "page": page,
                    "pagecount": page,
                    "limit": 24,
                    "total": 0,
                    "list": []
                }
            meta = data.get("meta", {})
            videos = self._parse_vod_list(data["data"])
            return {
                "page": page,
                "pagecount": meta.get("total_pages", 1),
                "limit": meta.get("per_page", 24),
                "total": meta.get("total", 0),
                "list": videos
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

    # -------------------- 详情 --------------------
    def detailContent(self, ids):
        try:
            slug = str(ids[0]).strip() if ids else ""
            if not slug:
                return {"list": []}
            detail = self._get_json(f"/movies/{slug}")
            if not detail or not detail.get("data"):
                return {"list": []}
            d = detail["data"]
            sources = self._get_json(f"/movies/{slug}/sources")
            source_data = sources.get("data", {}) if sources else {}
            online_list = source_data.get("online", [])

            play_from = []
            play_url = []
            for idx, src in enumerate(online_list):
                if not isinstance(src, dict):
                    continue
                name = src.get("name", f"播放源{idx+1}") or f"播放源{idx+1}"
                url = src.get("url", "")
                if not url:
                    continue
                ep_list = []
                if "$" in url and "#" in url:
                    parts = url.split("#")
                    for part in parts:
                        part = part.strip()
                        if "$" in part:
                            ep_name, ep_u = part.split("$", 1)
                            ep_list.append(f"{ep_name.strip()}${ep_u.strip()}")
                        else:
                            ep_list.append(f"播放${part}")
                elif "http" in url:
                    ep_list.append(f"播放${url}")
                if ep_list:
                    play_from.append(name)
                    play_url.append("#".join(ep_list))

            if not play_from:
                play_from = ["在线播放"]
                play_url = ["播放$"]

            intro = re.sub(r'<[^>]+>', '', d.get("intro", "")).strip()
            actors = d.get("actors", [])
            directors = d.get("director", [])

            video = {
                "vod_id": slug,
                "vod_name": d.get("title", ""),
                "vod_pic": d.get("poster", ""),
                "vod_year": str(d.get("year", "")),
                "vod_area": d.get("region", ""),
                "vod_actor": "/".join(actors) if actors else "",
                "vod_director": "/".join(directors) if directors else "",
                "vod_remarks": str(d.get("rating", "")) if d.get("rating") else "",
                "vod_content": intro[:500],
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            }
            return {"list": [video]}
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    # -------------------- 搜索 --------------------
    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        try:
            page = max(int(pg or 1), 1)
            params = {"q": key, "page": page, "limit": 20}
            data = self._get_json("/search", params=params)
            if not data or not data.get("data"):
                return {
                    "page": page,
                    "pagecount": page,
                    "limit": 20,
                    "total": 0,
                    "list": []
                }
            meta = data.get("meta", {})
            videos = self._parse_vod_list(data["data"])
            return {
                "page": page,
                "pagecount": meta.get("total_pages", 1),
                "limit": meta.get("per_page", 20),
                "total": meta.get("total", 0),
                "list": videos
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

    # -------------------- 播放 --------------------
    def playerContent(self, flag, id, vipFlags):
        try:
            url = str(id or "").strip()
            if not url:
                return {"parse": 0, "playUrl": "", "url": ""}
            return {
                "parse": 0,
                "playUrl": "",
                "url": url,
                "header": self.headers if self.isVideoFormat(url) else {}
            }
        except Exception as exc:
            return {
                "parse": 1,
                "playUrl": "",
                "url": str(id or ""),
                "error": str(exc)
            }

    def localProxy(self, param):
        return [404, "text/plain", "Not Found"]


if __name__ == "__main__":
    spider = Spider()
    spider.init("")
    print("=== home ===")
    print(json.dumps(spider.homeContent(False), ensure_ascii=False, indent=2))
    print("\n=== homeVod ===")
    print(json.dumps(spider.homeVideoContent(), ensure_ascii=False, indent=2))
    print("\n=== cate movie ===")
    print(json.dumps(spider.categoryContent("movie", "1", False, {}), ensure_ascii=False, indent=2))
    print("\n=== search 凡人 ===")
    print(json.dumps(spider.searchContent("凡人", False, "1"), ensure_ascii=False, indent=2))
    print("\n=== detail ===")
    print(json.dumps(spider.detailContent(["a-mortals-journey-to-immortality"]), ensure_ascii=False, indent=2))
