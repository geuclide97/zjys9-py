# -*- coding: utf-8 -*-
"""
Brovod影视 UI9专用Python爬虫
适配UI9标准TVBox/Python爬虫规范，对齐爱影模板架构
依赖：requests
UI9后台配置JSON：
{
  "key": "brovod_py",
  "name": "Brovod影视",
  "type": 3,
  "api": "./py/brovod.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 1
}
extend可自定义配置示例：{"host":"https://xxx.com","ua":"自定义UA"}
"""
import sys
import re
import json
from urllib.parse import urljoin, quote, unquote, urlparse
from html import unescape as html_unescape

# 依赖容错降级
try:
    import requests
except Exception:
    requests = None

# UI9父类兜底，无base.spider不报错
try:
    sys.path.append('..')
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def fetch(self, url, headers=None, **kw):
            import requests as rq
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


# 全局常量全部移入类内，方便extend覆盖
DEAD_IMG_HOSTS = {"image.caiji.cyou", "wim.xrc888.com"}
CATEGORIES = {
    "Movies": "电影",
    "TV": "剧集",
    "Anime": "动漫",
    "Documentaries": "纪录片",
    "Snaps": "短剧",
    "Shows": "综艺",
}
WESERV_PREFIX = "https://images.weserv.nl/?url="
FROM_DISPLAY = {
    "xdrs": "蓝光②", "xdac": "蓝光③", "xd5": "蓝光⑤",
    "bfzym3u8": "极速①", "1080zyk": "极速②", "jsm3u8": "极速③",
}
BLOCKED_FROMS = {"xdxl", "xdyy", "xdjp"}


class Spider(BaseSpider):
    # UI9默认扩展配置，支持后台extend JSON覆盖
    DEFAULT_EXT = {
        "host": "https://www.brovod.com",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
    }

    def getName(self):
        return "Brovod影视"

    def init(self, extend=""):
        # 加载自定义扩展配置
        self.ext = dict(self.DEFAULT_EXT)
        if isinstance(extend, dict):
            self.ext.update(extend)
        elif isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict):
                    self.ext.update(cfg)
            except Exception:
                pass

        self.host = self.ext["host"].rstrip("/")
        self.ua = self.ext["ua"]
        self.session = requests.Session() if requests else None
        self.headers = {"User-Agent": self.ua}

        # 访问首页自动跳转真实HOST（原有逻辑保留）
        try:
            resp = self._request_raw(self.host, timeout=15)
            if hasattr(resp, 'url') and resp.url and resp.url.rstrip("/") != self.host:
                self.host = resp.url.rstrip("/")
        except Exception:
            pass

    # ===================== UI9通用工具函数（和爱影模板完全对齐） =====================
    def _ensure_runtime(self):
        if requests is None:
            raise RuntimeError("运行缺失requests依赖，请安装：pip install requests")

    def _request_raw(self, url, headers=None, timeout=12, method="get"):
        """统一请求封装，替换原生fetch，兼容会话复用"""
        self._ensure_runtime()
        final_header = dict(self.headers)
        if headers:
            final_header.update(headers)
        if not url.startswith("http"):
            url = urljoin(self.host, url)
        try:
            if method.lower() == "get":
                resp = self.session.get(url, headers=final_header, timeout=timeout)
            else:
                resp = self.session.post(url, headers=final_header, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"请求失败 {url} 错误: {str(e)}")
            return None

    @staticmethod
    def _safe_json(text, default=None):
        """JSON解析容错"""
        try:
            return json.loads(text)
        except Exception:
            return default if default is not None else {}

    def _video_item(self, item):
        """UI9统一标准化列表字段，统一vod四个核心字段"""
        if not isinstance(item, dict):
            return {}
        return {
            "vod_id": item.get("vod_id", ""),
            "vod_name": item.get("vod_name", ""),
            "vod_pic": item.get("vod_pic", ""),
            "vod_remarks": item.get("vod_remarks", "")
        }

    def isVideoFormat(self, url):
        """UI9视频链接识别规则"""
        return bool(re.search(r"(?i)\.(m3u8|mp4|mkv|ts|flv|avi|mov)(?:\?|$)", str(url or "")))

    def manualVideoCheck(self):
        return False

    # ===================== 原有工具函数（原样迁移，仅调用适配） =====================
    def _clean_pic(self, pic_url):
        if not pic_url:
            return ""
        if pic_url.startswith(WESERV_PREFIX):
            pic_url = pic_url[len(WESERV_PREFIX):]
            try:
                pic_url = unquote(pic_url)
            except Exception:
                pass
        if pic_url.startswith("http://"):
            pic_url = pic_url.replace("http://", "https://", 1)
        host = urlparse(pic_url).hostname or ""
        if host in DEAD_IMG_HOSTS:
            return ""
        return pic_url

    def _items(self, html, cat_filter=""):
        items, seen = [], set()
        for m in re.finditer(
            r'class="public-list-exp"[^>]*href="(/detail/[^"]+)"[^>]*title="([^"]*)"',
            html
        ):
            detail_url = m.group(1)
            name = m.group(2).strip()
            if not name or len(name) > 100:
                continue
            vid_m = re.search(r'-(\d+)/?$', detail_url)
            vid = vid_m.group(1) if vid_m else detail_url
            if vid in seen:
                continue
            seen.add(vid)

            after = html[m.end():m.end() + 3000]
            cover = re.search(r'data-src="(https?://[^"]+)"', after)
            if not cover:
                cover = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', after, re.I)
            pic_url = self._clean_pic(cover.group(1)) if cover else ""

            remark = re.search(r'class="public-list-prb[^"]*"[^>]*>([^<]+)<', after)
            if not remark:
                remark = re.search(r'class="[^"]*prb[^"]*"[^>]*>([^<]+)<', after)

            items.append({
                "vod_id": detail_url,
                "vod_name": name[:50],
                "vod_pic": pic_url,
                "vod_remarks": remark.group(1).strip() if remark else "",
            })
        return items

    def _search_items(self, html):
        items, seen = [], set()
        boxes = re.split(r'<div class="public-list-box[^"]*search-box', html)
        for box_html in boxes[1:]:
            detail_m = re.search(r'href="(/detail/[^"]+)"', box_html)
            if not detail_m:
                continue
            detail_url = detail_m.group(1)
            vid_m = re.search(r'-(\d+)/?$', detail_url)
            vid = vid_m.group(1) if vid_m else detail_url
            if vid in seen:
                continue
            seen.add(vid)

            name_m = re.search(r'class="thumb-txt[^"]*"[^>]*><a[^>]*href="[^"]*"[^>]*>(.*?)</a>', box_html, re.S)
            if name_m:
                name = html_unescape(re.sub(r'<[^>]+>', '', name_m.group(1)).strip())
            else:
                name_m = re.search(r'title="([^"]+)"', box_html)
                name = name_m.group(1).strip() if name_m else ""
            if not name or len(name) > 100:
                continue

            cover = re.search(r'data-src="(https?://[^"]+)"', box_html)
            if not cover:
                cover = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', box_html, re.I)
            pic_url = self._clean_pic(cover.group(1)) if cover else ""

            remark = re.search(r'class="public-list-prb[^"]*"[^>]*>([^<]+)<', box_html)

            items.append({
                "vod_id": detail_url,
                "vod_name": name[:50],
                "vod_pic": pic_url,
                "vod_remarks": remark.group(1).strip() if remark else "",
            })
        return items

    def _pagecount(self, html, current_page=1):
        max_page = current_page
        tail_m = re.search(r'尾页[^>]*href="[^"]*?-(\d+)---/"', html)
        if tail_m:
            try:
                max_page = int(tail_m.group(1))
                return max_page
            except Exception:
                pass
        pages = re.findall(r'/show/\w+-{4,}(\d+)---/', html)
        for p in pages:
            try:
                n = int(p)
                if n > max_page:
                    max_page = n
            except Exception:
                pass
        has_next = re.search(r'>下一页<', html)
        if has_next and max_page <= current_page + 5:
            max_page = current_page + 5
        return max_page if max_page >= 1 else 1

    def _build_category_url(self, cat, pn, extend=""):
        ext = {}
        if extend and isinstance(extend, str) and extend.strip():
            try:
                ext = json.loads(extend)
            except Exception:
                pass
        area = ext.get("area") or ""
        sort = ext.get("sort") or ""
        genre = ext.get("class") or ""
        lang = ext.get("lang") or ""
        letter = ext.get("letter") or ""
        year = ext.get("year") or ""

        parts = [cat, "", "", "", "", "", "", "", "", "", "", ""]
        if area and area != "全部":
            parts[1] = quote(area)
        if sort:
            parts[2] = sort
        if genre and genre != "全部":
            parts[3] = quote(genre)
        if lang and lang != "全部":
            parts[4] = quote(lang)
        if letter and letter != "全部":
            parts[5] = letter
        if pn > 1:
            parts[8] = str(pn)
        if year and year != "全部":
            parts[11] = str(year)
        url = "/show/" + "-".join(parts) + "/"
        return self.host + url

    # ===================== UI9标准入口方法 =====================
    def homeContent(self, filter=False):
        res = {"class": []}
        for k, v in CATEGORIES.items():
            res["class"].append({"type_id": k, "type_name": v})
        return res

    def homeVideoContent(self):
        try:
            resp = self._request_raw(self.host, timeout=15)
            html = resp.text if hasattr(resp, 'text') else str(resp)
            raw_list = [it for it in self._items(html) if it.get("vod_pic")]
            return {"list": [self._video_item(i) for i in raw_list]}
        except Exception:
            return {"list": []}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        pn = 1
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pass
        cat = str(tid)
        if cat not in CATEGORIES:
            return {"page": pn, "pagecount": 1, "limit": 36, "total": 0, "list": []}
        try:
            url = self._build_category_url(cat, pn, extend)
            resp = self._request_raw(url, timeout=30)
            html = resp.text if hasattr(resp, 'text') else str(resp)
            raw_items = [it for it in self._items(html) if it.get("vod_pic")]
            item_list = [self._video_item(i) for i in raw_items]
            pc = self._pagecount(html, pn)
            return {
                "page": pn,
                "pagecount": pc,
                "limit": 36,
                "total": len(item_list),
                "list": item_list
            }
        except Exception:
            return {"page": pn, "pagecount": 1, "limit": 36, "total": 0, "list": []}

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = str(ids) if ids else ""
        if not vid:
            return {"list": []}
        detail_id = vid
        if "/" in vid:
            detail_url = vid if vid.startswith("http") else urljoin(self.host, vid)
        else:
            detail_url = f"{self.host}/detail/{vid}/"

        try:
            resp = self._request_raw(detail_url, timeout=30)
            h = resp.text if hasattr(resp, 'text') else str(resp)
        except Exception:
            return {"list": []}

        d = {
            "vod_id": detail_id,
            "vod_name": "",
            "vod_pic": "",
            "vod_year": "",
            "vod_area": "",
            "vod_class": "",
            "vod_director": "",
            "vod_actor": "",
            "vod_content": "",
            "vod_remarks": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }

        tn = re.search(r'class="slide-info-title[^"]*"[^>]*>(.*?)</(?:h1|h2|h3)>', h, re.S)
        if tn:
            d["vod_name"] = re.sub(r'<[^>]+>', '', tn.group(1)).strip()
        if not d["vod_name"]:
            tn = re.search(r'<title>(.*?)</title>', h)
            if tn:
                d["vod_name"] = tn.group(1).split("-")[0].strip()

        p = re.search(r'data-src="(https?://[^"]+)"', h)
        if not p:
            p = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', h, re.I)
        if p:
            d["vod_pic"] = self._clean_pic(p.group(1))

        slide_info_tags = re.findall(
            r'<div class="slide-info[^"]*">\s*((?:<span class="slide-info-remarks">.*?</span>\s*)+)\s*</div>',
            h, re.S
        )
        if slide_info_tags:
            tag_text = re.sub(r'<[^>]+>', ' ', slide_info_tags[0])
            tag_text = re.sub(r'\s+', ' ', tag_text).strip()
            parts = [t.strip() for t in tag_text.split() if t.strip()]
            for p_text in parts:
                if re.match(r'^\d{4}$', p_text) and not d["vod_year"]:
                    d["vod_year"] = p_text
                elif p_text in ("大陆", "香港", "台湾", "美国", "韩国", "日本", "英国",
                                "法国", "德国", "泰国", "印度", "加拿大", "其他",
                                "意大利", "西班牙", "未知"):
                    if not d["vod_area"]:
                        d["vod_area"] = p_text
                elif not d["vod_area"] and re.match(r'^[\u4e00-\u9fff]{2,3}$', p_text):
                    d["vod_area"] = p_text
            type_parts = []
            year_done = False
            area_done = False
            for p_text in parts:
                if re.match(r'^\d{4}$', p_text):
                    year_done = True
                    continue
                if p_text in ("大陆", "香港", "台湾", "美国", "韩国", "日本", "英国",
                               "法国", "德国", "泰国", "印度", "加拿大", "其他",
                               "意大利", "西班牙", "未知"):
                    area_done = True
                    continue
                if year_done and area_done:
                    type_parts.append(p_text)
            if type_parts:
                d["vod_class"] = " ".join(type_parts)

        rm = re.search(r'备注\s*[：:]\s*</strong>\s*([^<\s]+)', h)
        if rm:
            d["vod_remarks"] = rm.group(1).strip()

        dm = re.search(r'导演\s*[：:]\s*</strong>([\s\S]*?)(?:</div>)', h)
        if dm:
            d["vod_director"] = re.sub(r'<[^>]+>', '', dm.group(1)).replace("/", ",").strip().rstrip(",").strip()

        am = re.search(r'演员\s*[：:]\s*</strong>([\s\S]*?)(?:</div>)', h)
        if am:
            d["vod_actor"] = re.sub(r'<[^>]+>', '', am.group(1)).replace("/", ",").strip().rstrip(",").strip()

        desc_m = re.search(r'class="slide-info-content"[^>]*>([\s\S]*?)</div>', h)
        if desc_m:
            d["vod_content"] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', desc_m.group(1))).strip()[:500]
        if not d["vod_content"]:
            desc_m = re.search(r'影视简介[\s\S]{0,10}?>([\s\S]*?)</(?:div|p)>', h)
            if desc_m:
                d["vod_content"] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', desc_m.group(1))).strip()[:500]
        if not d["vod_content"]:
            desc_m = re.search(r'class="card-text">([\s\S]*?)</div>', h)
            if desc_m:
                d["vod_content"] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', desc_m.group(1))).strip()[:500]

        try:
            pf_list, pu_list = [], []
            tab_section = re.search(
                r'<div class="anthology-tab[^"]*">(.*?)</div>\s*</div>\s*<div class="anthology-list',
                h, re.S
            )
            if not tab_section:
                tab_section = re.search(
                    r'<div class="anthology-tab[^"]*">(.*?)</div>\s*</div>',
                    h, re.S
                )
            tab_names = []
            if tab_section:
                for tab_m in re.finditer(r'<a[^>]*class="swiper-slide"[^>]*>([\s\S]*?)</a>', tab_section.group(1)):
                    tab_text = html_unescape(re.sub(r'<[^>]+>', '', tab_m.group(1)).strip())
                    tab_text = tab_text.replace('\xa0', ' ').strip()
                    if tab_text:
                        tab_names.append(tab_text)

            list_section = re.search(
                r'<div class="anthology-list[^"]*">(.*?)</div>\s*</div>\s*</div>',
                h, re.S
            )
            if not list_section:
                list_section = re.search(
                    r'class="anthology-list[^"]*"(.*?)$',
                    h, re.S
                )
            if list_section:
                boxes = re.findall(
                    r'<div class="anthology-list-box[^"]*">(.*?)</ul>\s*</div>',
                    list_section.group(1), re.S
                )
                if not boxes:
                    boxes = re.findall(
                        r'<div class="anthology-list-box[^"]*">(.*?)(?=<div class="anthology-list-box|</div>\s*</div>)',
                        list_section.group(1), re.S
                    )
                for idx, box_html in enumerate(boxes):
                    eps = re.findall(r'href="(/play/[^"]+)"[^>]*>(.*?)</a>', box_html, re.S)
                    if not eps:
                        continue
                    ep_list = []
                    skip = False
                    try:
                        first_url = urljoin(self.host, eps[0][0]) if eps else ""
                        rp = self._request_raw(first_url, timeout=5)
                        hp = rp.text if hasattr(rp, 'text') else str(rp)
                        fm = re.search(r'"from"\s*:\s*"([^"]+)"', hp)
                        if fm and fm.group(1) in BLOCKED_FROMS:
                            skip = True
                    except Exception:
                        pass
                    if skip:
                        continue
                    for ep_url, ep_name in eps:
                        ep_name = re.sub(r'<[^>]+>', '', ep_name).strip()
                        if not ep_name:
                            ep_name = f"第{len(ep_list) + 1}集"
                        full_url = urljoin(self.host, ep_url)
                        ep_list.append(f"{ep_name}${full_url}")
                    if ep_list:
                        if idx < len(tab_names):
                            line_name = tab_names[idx]
                        else:
                            line_name = f"线路{idx + 1}"
                        pf_list.append(line_name)
                        pu_list.append("#".join(ep_list))

            if not pf_list:
                play_links = re.findall(r'href="(/play/[^"]+-\d+-\d+)/"[^>]*>([\s\S]*?)</a>', h, re.S)
                line_episodes = {}
                line_froms = {}
                for link_url, ep_name in play_links:
                    ep_name = re.sub(r'<[^>]+>', '', ep_name).strip()
                    m2 = re.search(r'/play/.+?-(\d+)-(\d+)/', link_url)
                    if m2:
                        line_idx = m2.group(1)
                        if line_idx not in line_episodes:
                            line_episodes[line_idx] = []
                        full_url = urljoin(self.host, link_url)
                        line_episodes[line_idx].append((ep_name, full_url))
                        if line_idx not in line_froms:
                            try:
                                rp = self._request_raw(full_url, timeout=5)
                                hp = rp.text if hasattr(rp, 'text') else str(rp)
                                pm = re.search(r'"from"\s*:\s*"([^"]+)"', hp)
                                if pm:
                                    line_froms[line_idx] = pm.group(1)
                            except Exception:
                                pass
                for line_idx in sorted(line_episodes.keys(), key=lambda x: int(x)):
                    eps = line_episodes[line_idx]
                    from_val = line_froms.get(line_idx, "")
                    if from_val in BLOCKED_FROMS:
                        continue
                    line_name = FROM_DISPLAY.get(from_val, f"线路{line_idx}")
                    ep_list = []
                    for ep_name, ep_url in eps:
                        if not ep_name:
                            ep_name = f"第{len(ep_list) + 1}集"
                        ep_list.append(f"{ep_name}${ep_url}")
                    if ep_list:
                        pf_list.append(line_name)
                        pu_list.append("#".join(ep_list))
            if pf_list:
                d["vod_play_from"] = "$$$".join(pf_list)
                d["vod_play_url"] = "$$$".join(pu_list)
        except Exception:
            pass
        return {"list": [d]}

    def searchContent(self, key, quick=False, pg="1"):
        # UI9要求双搜索入口，searchContent调用searchContentPage
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick=False, pg="1"):
        try:
            pn = 1
            try:
                pn = int(str(pg))
            except Exception:
                pass
            url = f"{self.host}/ss/-------------/?wd={quote(key)}"
            resp = self._request_raw(url, timeout=30)
            html = resp.text if hasattr(resp, 'text') else str(resp)
            raw_items = self._search_items(html)
            video_list = [self._video_item(item) for item in raw_items]
            return {"list": video_list, "page": pn}
        except Exception:
            return {"list": [], "page": int(pg)}

    def playerContent(self, flag, id, vipFlags=None):
        url = str(id) if id else str(flag)
        if url.startswith("http") and ".m3u8" in url:
            return {"url": url, "header": {"User-Agent": self.ua}}
        if url.startswith("http"):
            full_url = url
        else:
            if not url.startswith("/"):
                url = "/" + url
            full_url = urljoin(self.host, url)
        try:
            resp = self._request_raw(full_url, timeout=30)
            h = resp.text if hasattr(resp, 'text') else str(resp)
        except Exception:
            return {"url": ""}

        player_m = re.search(r'player_aaaa\s*=\s*(\{.*?\})\s*</script>', h, re.S)
        if player_m:
            data = self._safe_json(player_m.group(1))
            play_url = data.get("url", "")
            if play_url and play_url.startswith("http") and ".m3u8" in play_url:
                return {"url": play_url, "header": {"User-Agent": self.ua}}
            if play_url:
                parse_url = f"https://play.brovod.com/?url={quote(play_url)}"
                return {
                    "url": parse_url,
                    "parse": 1,
                    "header": {"User-Agent": self.ua}
                }
        m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8)', h)
        if m3u8:
            return {"url": m3u8.group(1), "header": {"User-Agent": self.ua}}
        return {"url": full_url, "parse": 1, "header": {"User-Agent": self.ua}}

    def localProxy(self, param):
        # UI9标准返回格式：[http状态码, content-type, 文本内容]
        return [404, "text/plain", "Not Found"]


if __name__ == '__main__':
    sp = Spider()
    sp.init()