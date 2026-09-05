# -*- coding: utf-8 -*-
"""
泥巴影视（泥视频）- TVBox 通用 Python Spider
由“泥泥视频.js”明文 drpy2 规则转换。

依赖：
    requests
    beautifulsoup4
"""

import base64
import json
import re
from urllib.parse import quote, unquote, urljoin

try:
    import requests
except Exception:
    requests = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass


class Spider(BaseSpider):
    HOST = "https://www.nivod.vip/"

    CLASS_MAP = {
        "1": "电影",
        "2": "电视剧",
        "3": "综艺",
        "4": "动漫",
    }

    FILTERS = {
        "1": [
            {
                "key": "cateId",
                "name": "类型",
                "value": [
                    {"n": "全部", "v": "1"},
                    {"n": "动作片", "v": "6"},
                    {"n": "喜剧片", "v": "7"},
                    {"n": "爱情片", "v": "8"},
                    {"n": "科幻片", "v": "9"},
                    {"n": "奇幻片", "v": "10"},
                    {"n": "恐怖片", "v": "11"},
                    {"n": "剧情片", "v": "12"},
                    {"n": "战争片", "v": "20"},
                    {"n": "纪录片", "v": "21"},
                    {"n": "悬疑片", "v": "22"},
                    {"n": "冒险片", "v": "23"},
                    {"n": "犯罪片", "v": "24"},
                    {"n": "动画片", "v": "26"},
                    {"n": "惊悚片", "v": "45"},
                    {"n": "歌舞片", "v": "46"},
                    {"n": "灾难片", "v": "47"},
                    {"n": "网络片", "v": "48"},
                ],
            },
            {
                "key": "area",
                "name": "地区",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "大陆", "v": "大陆"},
                    {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"},
                    {"n": "美国", "v": "美国"},
                    {"n": "欧美", "v": "欧美"},
                    {"n": "日本", "v": "日本"},
                    {"n": "韩国", "v": "韩国"},
                    {"n": "泰国", "v": "泰国"},
                    {"n": "其他", "v": "其他"},
                ],
            },
        ],
        "2": [
            {
                "key": "cateId",
                "name": "类型",
                "value": [
                    {"n": "全部", "v": "2"},
                    {"n": "国产剧", "v": "13"},
                    {"n": "港台剧", "v": "14"},
                    {"n": "日剧", "v": "15"},
                    {"n": "欧美剧", "v": "16"},
                    {"n": "其他剧", "v": "25"},
                    {"n": "韩剧", "v": "33"},
                    {"n": "泰剧", "v": "34"},
                    {"n": "新马剧", "v": "35"},
                ],
            },
            {
                "key": "area",
                "name": "地区",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "内地", "v": "内地"},
                    {"n": "韩国", "v": "韩国"},
                    {"n": "香港", "v": "香港"},
                    {"n": "台湾", "v": "台湾"},
                    {"n": "日本", "v": "日本"},
                    {"n": "美国", "v": "美国"},
                    {"n": "泰国", "v": "泰国"},
                    {"n": "英国", "v": "英国"},
                    {"n": "新加坡", "v": "新加坡"},
                    {"n": "其他", "v": "其他"},
                ],
            },
        ],
        "3": [
            {
                "key": "cateId",
                "name": "类型",
                "value": [
                    {"n": "全部", "v": "3"},
                    {"n": "内地综艺", "v": "27"},
                    {"n": "港台综艺", "v": "28"},
                    {"n": "日本综艺", "v": "29"},
                    {"n": "欧美综艺", "v": "30"},
                    {"n": "韩国综艺", "v": "36"},
                    {"n": "新马泰综艺", "v": "37"},
                    {"n": "其他综艺", "v": "38"},
                ],
            },
            {
                "key": "area",
                "name": "地区",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "内地", "v": "内地"},
                    {"n": "港台", "v": "港台"},
                    {"n": "日韩", "v": "日韩"},
                    {"n": "欧美", "v": "欧美"},
                ],
            },
        ],
        "4": [
            {
                "key": "cateId",
                "name": "类型",
                "value": [
                    {"n": "全部", "v": "4"},
                    {"n": "国产动漫", "v": "31"},
                    {"n": "日本动漫", "v": "32"},
                    {"n": "韩国动漫", "v": "39"},
                    {"n": "港台动漫", "v": "40"},
                    {"n": "新马泰动漫", "v": "41"},
                    {"n": "欧美动漫", "v": "42"},
                    {"n": "其他动漫", "v": "43"},
                ],
            },
            {
                "key": "area",
                "name": "地区",
                "value": [
                    {"n": "全部", "v": ""},
                    {"n": "国产", "v": "国产"},
                    {"n": "日本", "v": "日本"},
                    {"n": "欧美", "v": "欧美"},
                    {"n": "其他", "v": "其他"},
                ],
            },
        ],
    }

    YEARS = [
        {"n": "全部", "v": ""},
        *[{"n": str(year), "v": str(year)} for year in range(2026, 2011, -1)]
    ]

    def getName(self):
        return "泥巴影视"

    def init(self, extend=""):
        self.host = self.HOST
        if isinstance(extend, dict):
            self.host = str(extend.get("host", self.host) or self.host)
        elif isinstance(extend, str) and extend.strip():
            text = extend.strip()
            if text.startswith("http"):
                self.host = text
            else:
                try:
                    obj = json.loads(text)
                    if isinstance(obj, dict):
                        self.host = str(obj.get("host", self.host) or self.host)
                except Exception:
                    pass

        self.host = self.host.rstrip("/") + "/"
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update(self.headers)

    def _ensure_runtime(self):
        if requests is None:
            raise RuntimeError("缺少 requests")
        if BeautifulSoup is None:
            raise RuntimeError("缺少 beautifulsoup4")

    def _get(self, url):
        self._ensure_runtime()
        response = self.session.get(
            urljoin(self.host, url),
            timeout=12,
            headers=self.headers
        )
        response.raise_for_status()
        return response.text

    @staticmethod
    def _text(node):
        return node.get_text(" ", strip=True) if node else ""

    def _parse_cards(self, html, selector):
        soup = BeautifulSoup(html, "html.parser")
        result = []

        for node in soup.select(selector):
            link = node if node.name == "a" else node.select_one("a")
            image = node.select_one(".lazyload") or node.select_one("img")
            note = node.select_one(".module-item-note")

            if not link:
                continue

            href = link.get("href", "")
            title = link.get("title", "") or self._text(link)
            pic = ""
            if image:
                pic = (
                    image.get("data-original", "")
                    or image.get("data-src", "")
                    or image.get("src", "")
                )

            result.append({
                "vod_id": urljoin(self.host, href),
                "vod_name": title,
                "vod_pic": urljoin(self.host, pic),
                "vod_remarks": self._text(note)
            })

        return result

    def homeContent(self, filter):
        filters = {}
        for tid, items in self.FILTERS.items():
            copied = json.loads(json.dumps(items, ensure_ascii=False))
            copied.append({
                "key": "year",
                "name": "年份",
                "value": self.YEARS
            })
            filters[tid] = copied

        return {
            "class": [
                {"type_id": tid, "type_name": name}
                for tid, name in self.CLASS_MAP.items()
            ],
            "filters": filters
        }

    def homeVideoContent(self):
        try:
            html = self._get("/")
            return {
                "list": self._parse_cards(
                    html,
                    "a:has(.lazyload)"
                )
            }
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(int(pg or 1), 1)
            extend = extend if isinstance(extend, dict) else {}

            cate_id = str(extend.get("cateId", tid) or tid)
            area = str(extend.get("area", "") or "")
            year = str(extend.get("year", "") or "")

            path = f"/k/{cate_id}-{area}-------{page}---{year}/"
            html = self._get(path)
            videos = self._parse_cards(
                html,
                "a:has(.module-item-pic)"
            )

            return {
                "page": page,
                "pagecount": page + 1 if videos else page,
                "limit": len(videos),
                "total": 999999 if videos else 0,
                "list": videos
            }
        except Exception as exc:
            page = int(pg or 1)
            return {
                "page": page,
                "pagecount": page,
                "limit": 0,
                "total": 0,
                "list": [],
                "error": str(exc)
            }

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        try:
            page = max(int(pg or 1), 1)
            path = (
                "/index.php/ajax/suggest"
                f"?mid=1&wd={quote(str(key))}"
                f"&page={page}&limit=30"
            )
            obj = json.loads(self._get(path))
            items = obj.get("list", [])
            videos = []

            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue

                item_id = str(item.get("id", "") or "")
                vod_id = urljoin(self.host, f"/nivod/{item_id}/")
                videos.append({
                    "vod_id": vod_id,
                    "vod_name": str(item.get("name", "") or ""),
                    "vod_pic": urljoin(
                        self.host,
                        str(item.get("pic", "") or "")
                    ),
                    "vod_remarks": str(item.get("en", "") or "")
                })

            return {
                "page": page,
                "pagecount": page + 1 if videos else page,
                "limit": len(videos),
                "total": 999999 if videos else 0,
                "list": videos
            }
        except Exception as exc:
            page = int(pg or 1)
            return {
                "page": page,
                "pagecount": page,
                "limit": 0,
                "total": 0,
                "list": [],
                "error": str(exc)
            }

    def detailContent(self, ids):
        try:
            detail_url = ids[0] if isinstance(ids, list) else ids
            html = self._get(str(detail_url))
            soup = BeautifulSoup(html, "html.parser")

            title = self._text(soup.select_one("h1"))
            tags = soup.select(".module-info-tag-link")

            def tag(index):
                return self._text(tags[index]) if len(tags) > index else ""

            pic_node = soup.select_one(".lazyload")
            pic = ""
            if pic_node:
                pic = (
                    pic_node.get("data-original", "")
                    or pic_node.get("data-src", "")
                    or pic_node.get("src", "")
                )

            info_items = soup.select(".module-info-item")

            def info_value(label):
                for node in info_items:
                    text = self._text(node)
                    if label in text:
                        return text.replace(label, "", 1).strip()
                return ""

            tabs = [
                self._text(node)
                for node in soup.select("#y-playList span")
                if self._text(node)
            ]

            play_groups = []
            for play_list in soup.select(".module-play-list"):
                episodes = []
                for a in play_list.select("a:not([rel])"):
                    name = self._text(a)
                    href = urljoin(str(detail_url), a.get("href", ""))
                    if name and href:
                        episodes.append(f"{name}${href}")
                play_groups.append("#".join(episodes))

            if len(tabs) < len(play_groups):
                tabs.extend(
                    f"线路{i + 1}"
                    for i in range(len(tabs), len(play_groups))
                )

            vod = {
                "vod_id": str(detail_url),
                "vod_name": title,
                "type_name": tag(2),
                "vod_pic": urljoin(str(detail_url), pic),
                "vod_remarks": info_value("集数："),
                "vod_year": tag(0),
                "vod_area": tag(1),
                "vod_director": info_value("导演："),
                "vod_actor": info_value("主演："),
                "vod_content": self._text(
                    soup.select_one(".module-info-introduction-content")
                ),
                "vod_play_from": "$$$".join(tabs[:len(play_groups)]),
                "vod_play_url": "$$$".join(play_groups)
            }

            return {"list": [vod]}
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    def playerContent(self, flag, id, vipFlags):
        try:
            page_url = str(id or "")
            html = self._get(page_url)

            match = re.search(
                r"var\s+player_.*?=\s*(\{.*?\})\s*<",
                html,
                re.S
            )
            if not match:
                match = re.search(
                    r"var\s+player_.*?=\s*(\{.*?\})\s*;",
                    html,
                    re.S
                )

            if not match:
                return {
                    "parse": 1,
                    "playUrl": "",
                    "url": page_url
                }

            player = json.loads(match.group(1))
            play_url = str(player.get("url", "") or "")
            encrypt = str(player.get("encrypt", "0") or "0")

            if encrypt == "1":
                play_url = unquote(play_url)
            elif encrypt == "2":
                play_url = unquote(
                    base64.b64decode(play_url).decode("utf-8")
                )

            if re.search(r"(?i)\.(m3u8|mp4)(?:\?|$)", play_url):
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": play_url,
                    "header": self.headers
                }

            return {
                "parse": 1,
                "playUrl": "",
                "url": page_url
            }
        except Exception as exc:
            return {
                "parse": 1,
                "playUrl": "",
                "url": str(id or ""),
                "error": str(exc)
            }

    def isVideoFormat(self, url):
        return bool(re.search(
            r"(?i)\.(m3u8|mp4|flv|avi|mkv|wmv|mpg|mpeg|mov|ts|3gp|rmvb?)",
            str(url or "")
        ))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [404, "text/plain", "Not Found"]
