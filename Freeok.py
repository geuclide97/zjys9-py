# -*- coding: utf-8 -*-
"""
Freeok freeok2.com / freeok.ac UI9 Python Spider
依赖：
    requests
    beautifulsoup4
配置示例：
{
  "key": "freeok_py",
  "name": "🎞️Freeok影视",
  "type": 3,
  "api": "./py/freeok.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 1
}
"""
import re
import sys
import json
import html
import urllib.parse
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
    DEFAULT_EXT = {
        "hosts": [
            "https://www.freeok2.com",
            "https://www.freeok.ac",
            "https://www.freeok3.com",
            "https://www.freeok4.com",
            "https://www.freeok5.com"
        ],
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "default_pic": "https://pic.rmb.bdstatic.com/bjh/user/default.png"
    }

    CATEGORIES = [
        ("电影", "dianying"),
        ("电视剧", "dianshiju"),
        ("动漫", "dongman"),
        ("综艺", "zongyi"),
        ("短剧", "duanju")
    ]

    FILTERS = {
        "dianying": {
            "cate": ["喜剧", "爱情", "恐怖", "动作", "科幻", "剧情", "战争", "警匪", "犯罪", "动画", "奇幻",
                     "武侠", "冒险", "枪战", "悬疑", "惊悚", "经典", "青春", "文艺", "微电影", "古装", "历史",
                     "运动", "农村", "儿童", "网络电影"],
            "area": ["大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国", "德国", "泰国", "印度",
                     "意大利", "西班牙", "加拿大", "其他"],
        },
        "dianshiju": {
            "cate": ["剧情", "动作", "喜剧", "古装", "战争", "青春偶像", "家庭", "犯罪", "奇幻", "历史", "网剧",
                     "商战", "情景", "乡村", "经典", "其他"],
            "area": ["内地", "香港", "台湾", "日本", "韩国", "美国", "英国", "泰国", "新加坡", "其他"],
        },
        "dongman": {
            "cate": ["热血", "冒险", "科幻", "推理", "搞笑", "校园", "机战", "运动", "少女", "少年", "情感",
                     "战争", "励志", "原创", "亲子", "益智", "社会", "萝莉", "动作", "其他"],
            "area": ["国产", "日本", "欧美", "其他"],
        },
        "zongyi": {
            "cate": ["情感", "播报", "旅游", "曲艺", "求职", "游戏互动", "生活", "纪实", "美食", "访谈",
                     "财经", "选秀", "音乐"],
            "area": ["内地", "日韩", "欧美", "港台"],
        },
        "duanju": {},
    }
    YEARS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017",
             "2016", "2015", "2014", "2013", "2012", "2011", "2010"]
    ORDERS = [("time", "更新时间"), ("hits", "最多播放"), ("hits_day", "实时热门"),
              ("hits_week", "近期热播"), ("year", "新片上线")]

    def getName(self):
        return "Freeok影视"

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
        self.hosts = self.ext.get("hosts")
        self.host_idx = 0
        self.ua = str(self.ext.get("ua"))
        self.default_pic = str(self.ext.get("default_pic"))
        self.timeout = (6, 20)
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update({
                "User-Agent": self.ua,
                "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9"
            })

        # 正则预编译
        self.RE_VIDEO_HREF = re.compile(r'href="/video/(\d+)/"')
        self.RE_CARD_PIC = re.compile(r'data-src="([^"]+)"')
        self.RE_CARD_NOTE = re.compile(r'module-item-note">([^<]*)<')
        self.RE_CARD_TITLE = re.compile(r'title="([^"]+)"|module-poster-item-title">([^<]*)<|<strong>([^<]+)</strong>')
        self.RE_TAG = re.compile(r'module-info-tag-link"><a href="[^"]*" title="([^"]*)"')
        self.RE_DIRECTOR = re.compile(r'导演：</span>[\s\S]{0,300}?module-info-item-link">([^<]*)<')
        self.RE_ACTORS = re.compile(r'主演：</span>[\s\S]{0,4000}?</div></div>')
        self.RE_ACTOR_ONE = re.compile(r'module-info-item-link">([^<]*)<')
        self.RE_BRIEF = re.compile(r'module-info-introduction-content">([^<]*)<')
        self.RE_PANEL_SPLIT = re.compile(r'<div class="module-list sort-list tab-list"')
        self.RE_TAB_NAME = re.compile(r'data-dropdown-value="([^"]*)"')
        self.RE_EPISODE = re.compile(r'href="(/play/(\d+)-(\d+)-(\d+)/)"[^>]*>\s*<span>([^<]*)</span>')
        self.RE_PAGE_LAST = re.compile(r'href="([^"]*)"[^>]*>\s*尾页')
        self.RE_PAGE_NEXT = re.compile(r'href="([^"]*)"[^>]*>\s*下一页')
        self.RE_PAGE_NUM = re.compile(r'-(\d+)---/')
        self.RE_PLAYER_CONF = re.compile(r'player_aaaa\s*=\s*(\{[^}]+\})')
        self.RE_TOTAL = re.compile(r'有关的(\d+)部影片|共(\d+)部影片')

    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(m3u8|mp4|flv)(?:\?|$)", str(url or "")))

    def manualVideoCheck(self):
        return False

    # -------------------- 工具函数 --------------------
    def _ensure_runtime(self):
        if requests is None:
            raise RuntimeError("缺少 requests 模块")

    def _request_raw(self, path, referer=None):
        self._ensure_runtime()
        for _ in range(len(self.hosts)):
            host = self.hosts[self.host_idx]
            url = path if str(path).startswith('http') else urllib.parse.urljoin(host + '/', str(path).lstrip('/'))
            headers = dict(self.session.headers)
            if referer:
                headers["Referer"] = urllib.parse.urljoin(host, referer)
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout, verify=False)
                text = self._response_text(resp)
                if len(text) > 500:
                    return text
            except Exception:
                pass
            self.host_idx = (self.host_idx + 1) % len(self.hosts)
        return ""

    @staticmethod
    def _response_text(response):
        text = response.content.decode('utf-8-sig', errors='replace')
        stripped = text.strip()
        if len(stripped) > 1 and stripped[0] == '"' and stripped[-1] == '"':
            try:
                dec = json.loads(stripped)
                if isinstance(dec, str):
                    return dec
            except Exception:
                pass
        return text

    @staticmethod
    def _soup(text):
        return BeautifulSoup(text or '', 'html.parser') if BeautifulSoup else None

    @staticmethod
    def _text(node):
        return node.get_text(' ', strip=True) if node else ''

    @staticmethod
    def _clean(value):
        return html.unescape(str(value or '')).replace('$', ' ').replace('#', ' ').replace('$$$', ' ').strip()

    @staticmethod
    def _int(value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    def _gen_filters(self):
        filter_out = {}
        for tid, conf in self.FILTERS.items():
            items = []
            if conf.get("cate"):
                items.append({
                    "key": "cate", "name": "类型",
                    "value": [{"n": "全部", "v": ""}] + [{"n": c, "v": c} for c in conf["cate"]],
                })
            if conf.get("area"):
                items.append({
                    "key": "area", "name": "地区",
                    "value": [{"n": "全部", "v": ""}] + [{"n": a, "v": a} for a in conf["area"]],
                })
            items.append({
                "key": "year", "name": "年份",
                "value": [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in self.YEARS],
            })
            items.append({
                "key": "by", "name": "排序",
                "value": [{"n": "默认", "v": ""}] + [{"n": n, "v": v} for v, n in self.ORDERS],
            })
            filter_out[tid] = items
        return filter_out

    @staticmethod
    def _show_url(tid, area="", by="", cate="", page=1, year=""):
        parts = ["show", tid,
                 urllib.parse.quote(area) if area else "",
                 by or "",
                 urllib.parse.quote(cate) if cate else "",
                 "", "", "", "",
                 str(page), "", "",
                 str(year) if year else ""]
        return "/" + "-".join(parts) + "/"

    @staticmethod
    def _search_url(key, page=1):
        key = key[:50]
        parts = ["search", urllib.parse.quote(key)] + [""] * 9 + [str(page)] + ["", "", ""]
        return "/" + "-".join(parts) + "/"

    def _parse_cards(self, html, limit=0):
        videos = []
        seen = set()
        if not html:
            return videos
        anchors = list(self.RE_VIDEO_HREF.finditer(html))
        n = len(anchors)
        for i, m in enumerate(anchors):
            vid = m.group(1)
            if vid in seen:
                continue
            seen.add(vid)
            start = m.start()
            end = min(start + 2600, len(html))
            for j in range(i + 1, n):
                if anchors[j].group(1) != vid:
                    end = min(anchors[j].start(), end)
                    break
            block = html[start:end]
            name = ""
            nm = self.RE_CARD_TITLE.search(block)
            if nm:
                name = (nm.group(1) or nm.group(2) or nm.group(3) or "").strip()
            pm = self.RE_CARD_PIC.search(block)
            pic = pm.group(1) if pm else ""
            nm = self.RE_CARD_NOTE.search(block)
            note = nm.group(1).strip() if nm else ""
            videos.append({
                "vod_id": vid,
                "vod_name": self._clean(name or ("视频" + vid)),
                "vod_pic": pic or self.default_pic,
                "vod_remarks": self._clean(note),
            })
            if limit and len(videos) >= limit:
                break
        return videos

    def _parse_pagecount(self, html, page):
        pagecount = page
        has_next = False
        nxt = self.RE_PAGE_NEXT.search(html)
        if nxt:
            has_next = True
            m = self.RE_PAGE_NUM.search(nxt.group(1))
            if m:
                pagecount = max(pagecount, int(m.group(1)))
        for m in self.RE_PAGE_LAST.finditer(html):
            pm = self.RE_PAGE_NUM.search(m.group(1))
            if pm:
                pagecount = max(pagecount, int(pm.group(1)))
        if pagecount == page and has_next:
            pagecount = page + 1
        return pagecount

    # -------------------- UI9 Spider 方法 --------------------
    def homeContent(self, filter):
        try:
            classes = [{'type_name': n, 'type_id': i} for n, i in self.CATEGORIES]
            filters = self._gen_filters()
            return {"class": classes, "filters": filters}
        except Exception as exc:
            return {"class": [], "filters": {}, "error": str(exc)}

    def homeVideoContent(self):
        try:
            html = self._request_raw("/page/hot/")
            return {"list": self._parse_cards(html, limit=60)}
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, self._int(pg, 1))
            ext_obj = {}
            if isinstance(extend, str):
                try:
                    ext_obj = json.loads(extend)
                except Exception:
                    ext_obj = {}
            elif isinstance(extend, dict):
                ext_obj = extend
            path = self._show_url(
                tid,
                area=ext_obj.get("area", ""),
                by=ext_obj.get("by", ""),
                cate=ext_obj.get("cate", ""),
                page=page,
                year=ext_obj.get("year", "")
            )
            html = self._request_raw(path)
            videos = self._parse_cards(html)
            pagecount = self._parse_pagecount(html, page)
            total = pagecount * len(videos) if videos else 0
            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": len(videos) or 24,
                "total": total
            }
        except Exception as exc:
            return {
                "list": [],
                "page": int(pg or 1),
                "pagecount": int(pg or 1),
                "limit": 0,
                "total": 0,
                "error": str(exc)
            }

    def detailContent(self, ids):
        try:
            if not ids:
                return {"list": []}
            vid = ids[0]
            html = self._request_raw("/video/{0}/".format(vid))
            if not html:
                return {"list": []}
            m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            title = m.group(1).strip() if m else ("视频" + vid)
            tags = self.RE_TAG.findall(html)
            year = tags[0] if len(tags) > 0 and tags[0].isdigit() else ""
            area = tags[1] if len(tags) > 1 else ""
            type_name = tags[2] if len(tags) > 2 else ""

            m_dir = self.RE_DIRECTOR.search(html)
            director = m_dir.group(1).strip() if m_dir else ""
            m_brief = self.RE_BRIEF.search(html)
            content = m_brief.group(1).strip() if m_brief else ""

            actors = []
            m_act_block = self.RE_ACTORS.search(html)
            if m_act_block:
                actors = [a for a in self.RE_ACTOR_ONE.findall(m_act_block.group(0))][:20]

            m_pic = re.search(r'module-poster-bg[\s\S]{0,400}?data-src="([^"]+)"', html)
            pic = m_pic.group(1) if m_pic else self.default_pic

            play_from = []
            play_url = []
            tabs = self.RE_TAB_NAME.findall(html)
            panels = self.RE_PANEL_SPLIT.split(html)[1:]
            name_count = {}
            for i, panel in enumerate(panels):
                src_name = tabs[i] if i < len(tabs) else ("线路" + str(i + 1))
                name_count[src_name] = name_count.get(src_name, 0) + 1
                if name_count[src_name] > 1:
                    src_name = f"{src_name}{name_count[src_name]}"
                eps = []
                seen_ep = set()
                for m2 in self.RE_EPISODE.finditer(panel):
                    link, _, _, eid, ep_name = m2.groups()
                    if link in seen_ep:
                        continue
                    seen_ep.add(link)
                    ep_name = ep_name.strip() or f"第{eid}集"
                    eps.append(f"{ep_name}${link}")
                if eps:
                    play_from.append(self._clean(src_name))
                    play_url.append("#".join(eps))

            if not play_from:
                m_play_btn = re.search(r'href="(/play/\d+-\d+-\d+/)"[^>]*title="立刻播放', html)
                if m_play_btn:
                    play_from.append("立即播放")
                    play_url.append(f"播放${m_play_btn.group(1)}")
            if not play_from:
                play_from.append("网页播放")
                play_url.append(f"播放$/video/{vid}/")

            remarks = ""
            if play_url:
                first_ep = play_url[0].split("#")[0].split("$")[0]
                remarks = first_ep if not first_ep.startswith("播放") else ""

            vod = {
                "vod_id": vid,
                "vod_name": self._clean(title),
                "vod_pic": pic,
                "vod_content": self._clean(content),
                "vod_actor": " / ".join(actors),
                "vod_director": self._clean(director),
                "vod_year": year,
                "vod_area": area,
                "type_name": type_name,
                "vod_remarks": self._clean(remarks),
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            }
            return {"list": [vod]}
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        try:
            page = max(1, self._int(pg, 1))
            if not key or not key.strip():
                return {"list": [], "page": page}
            html = self._request_raw(self._search_url(key.strip(), page))
            videos = self._parse_cards(html)
            pagecount = self._parse_pagecount(html, page)
            total = 0
            m_total = self.RE_TOTAL.search(html)
            if m_total:
                total = self._int(m_total.group(1) or m_total.group(2) or 0)
            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": len(videos) or 24,
                "total": total
            }
        except Exception as exc:
            return {
                "list": [],
                "page": int(pg or 1),
                "error": str(exc)
            }

    def playerContent(self, flag, pid, vipFlags):
        try:
            header = {"User-Agent": self.ua}
            raw_id = pid
            if "$" in raw_id:
                raw_id = raw_id.split("$")[-1]
            raw_id = raw_id.strip()
            if raw_id.startswith("http") and (".m3u8" in raw_id or ".mp4" in raw_id):
                return {"parse": 0, "url": raw_id, "header": header}
            if not raw_id.startswith("/play/"):
                return {"parse": 1, "url": raw_id, "header": header}
            html = self._request_raw(raw_id, referer="/")
            pos = html.find("player_aaaa")
            if pos < 0:
                return {"parse": 1, "url": self.hosts[self.host_idx] + raw_id, "header": header}
            conf_m = self.RE_PLAYER_CONF.search(html, pos, pos + 2000)
            if not conf_m:
                return {"parse": 1, "url": self.hosts[self.host_idx] + raw_id, "header": header}
            try:
                conf = json.loads(conf_m.group(1).replace("\\/", "/"))
            except Exception:
                return {"parse": 1, "url": self.hosts[self.host_idx] + raw_id, "header": header}
            url = conf.get("url", "")
            encrypt = self._int(conf.get("encrypt", 0))
            try:
                if encrypt == 1:
                    url = urllib.parse.unquote(url)
                elif encrypt >= 2:
                    url = urllib.parse.unquote(urllib.parse.unquote(url))
            except Exception:
                pass
            if url:
                cleaned = False
                for mark in (".m3u8", ".mp4"):
                    i = url.find(mark)
                    if i > -1:
                        url = url[:i + len(mark)]
                        cleaned = True
                        break
                if not cleaned and "&" in url and "?" not in url:
                    url = url.split("&")[0]
            if url and url.startswith("http"):
                return {
                    "parse": 0,
                    "url": url,
                    "header": header
                }
            return {"parse": 1, "url": self.hosts[self.host_idx] + raw_id, "header": header}
        except Exception as exc:
            return {
                "parse": 1,
                "url": str(pid or ""),
                "error": str(exc)
            }

    def localProxy(self, param):
        return [404, "text/plain", "Not Found"]
