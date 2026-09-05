# -*- coding: utf-8 -*-
"""
追剧吧 zjuba3.com UI9 Python Spider
依赖：
    requests
    beautifulsoup4
配置示例：
{
  "key": "追剧吧_py",
  "name": "🎬追剧吧",
  "type": 3,
  "api": "./py/追剧吧.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 1
}
"""
import base64
import hashlib
import html
import json
import re
import sys
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
    DEFAULT_EXT = {
        "host": "https://www.zjuba3.com",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        "img_proxy": "https://images.weserv.nl/?url="
    }

    CATEGORIES = [
        ("电影", "1"), ("连续剧", "2"), ("综艺", "3"), ("动漫", "4"),
        ("动作片", "6"), ("喜剧片", "7"), ("爱情片", "8"), ("科幻片", "9"),
        ("恐怖片", "10"), ("剧情片", "11"), ("战争片", "12"), ("国产剧", "13"),
        ("港台剧", "14"), ("日韩剧", "15"), ("欧美剧", "16")
    ]

    FILTER_CLASS_LIST = [
        "动作", "喜剧", "爱情", "科幻", "恐怖", "剧情", "战争", "犯罪",
        "武侠", "历史", "冒险", "经典", "儿童", "古装", "农村", "警匪",
        "奇幻", "悬疑", "微电影", "惊悚", "枪战", "动画", "家庭", "传记",
        "歌舞", "音乐", "运动", "灾难", "西部", "短片", "纪录片", "伦理",
        "青春", "励志", "商战", "谍战", "革命", "年代", "都市", "言情",
        "偶像", "军旅", "情景", "神话", "穿越", "宫廷", "罪案", "刑侦",
        "反腐", "抗战", "传奇", "生活", "乡土", "红色"
    ]
    FILTER_AREA_LIST = [
        "大陆", "香港", "台湾", "美国", "法国", "英国", "日本", "韩国",
        "德国", "泰国", "印度", "意大利", "西班牙", "加拿大", "其他"
    ]
    FILTER_BY_LIST = [
        {"n": "时间", "v": "time"},
        {"n": "人气", "v": "hits"},
        {"n": "评分", "v": "score"}
    ]

    def getName(self):
        return "追剧吧"

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
        self.host = str(self.ext.get("host", "https://www.zjuba3.com")).rstrip("/")
        self.ua = str(self.ext.get("ua"))
        self.img_proxy = str(self.ext.get("img_proxy"))
        self.timeout = (6, 20)
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update({
                "User-Agent": self.ua,
                "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
                "Referer": self.host + "/",
                "Accept-Language": "zh-CN,zh;q=0.9"
            })
        # m3u8存活缓存
        self._alive_domains = set()
        self._dead_domains = set()

    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(m3u8|mp4|flv)(?:\?|$)", str(url or "")))

    def manualVideoCheck(self):
        return False

    # -------------------- 工具函数 --------------------
    def _ensure_runtime(self):
        if requests is None:
            raise RuntimeError("缺少 requests 模块")
        if BeautifulSoup is None:
            raise RuntimeError("缺少 beautifulsoup4 模块")

    def _request_raw(self, path):
        self._ensure_runtime()
        url = path if str(path).startswith('http') else urljoin(self.host + '/', str(path).lstrip('/'))
        resp = self.session.get(url, timeout=self.timeout, verify=False)
        return self._response_text(resp)

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
        return BeautifulSoup(text or '', 'html.parser')

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

    def _build_filter_opts(self, name_list):
        seen = set()
        opts = [{"n": "全部", "v": ""}]
        for n in name_list:
            if n and n not in seen:
                seen.add(n)
                opts.append({"n": n, "v": n})
        return opts

    def _gen_filters(self):
        filter_tpl = [
            {"key": "class", "name": "剧情", "value": self._build_filter_opts(self.FILTER_CLASS_LIST)},
            {"key": "area", "name": "地区", "value": self._build_filter_opts(self.FILTER_AREA_LIST)},
            {"key": "by", "name": "排序", "value": self.FILTER_BY_LIST},
        ]
        return {cid: filter_tpl for (cname, cid) in self.CATEGORIES}

    def _proxy_pic_url(self, url):
        """图片防盗链代理，imgdb.cn绕过Referer 403"""
        if not url:
            return ""
        if url.startswith(self.img_proxy):
            return url
        if "imgdb.cn" in url:
            host_part = url.split("://", 1)[-1]
            return self.img_proxy + host_part
        return url

    def _image(self, img_tag):
        if not img_tag:
            return ''
        raw = img_tag.get('data-original') or img_tag.get('src') or ''
        full_url = urljoin(self.host + '/', raw)
        return self._proxy_pic_url(full_url)

    def _cards(self, text):
        """解析列表卡片，兼容首页/分类页module-poster-item，搜索页module-card-item"""
        soup = self._soup(text)
        result, seen = [], set()
        # poster item (首页分类)
        for a in soup.select('a[href*="/vod/detail/id/"]'):
            href = a.get('href', '')
            match = re.search(r'/detail/id/(\d+)\.html', href)
            vod_id = match.group(1) if match else None
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)
            img = a.select_one('img')
            card_wrap = a.find_parent(class_="module-card-item") or a.find_parent(class_="module-poster-item")
            name = (a.get("title") or (img.get("alt") if img else "") or
                    self._text(card_wrap.select_one(".module-card-item-title") if card_wrap else None) or
                    self._text(card_wrap.select_one(".module-poster-item-title") if card_wrap else None) or
                    self._text(a))
            if not name:
                continue
            remark = self._text(card_wrap.select_one(".module-item-note,.module-item-text") if card_wrap else None)
            result.append({
                "vod_id": vod_id,
                "vod_name": self._clean(name),
                "vod_pic": self._image(img),
                "vod_remarks": self._clean(remark)
            })
        return result

    def _check_m3u8_alive(self, m3u8_url):
        """快速检测m3u8有效性，域名缓存"""
        dm_m = re.match(r'https?://([^/]+)', m3u8_url)
        if not dm_m:
            return False
        domain = dm_m.group(1)
        if domain in self._alive_domains:
            return True
        if domain in self._dead_domains:
            return False
        try:
            resp = self.session.get(m3u8_url, headers={"User-Agent": self.ua, "Referer": self.host + "/"}, timeout=(5,10), verify=False)
            if resp and resp.text and '#EXTM3U' in resp.text[:100]:
                self._alive_domains.add(domain)
                return True
        except Exception:
            pass
        self._dead_domains.add(domain)
        return False

    def _extract_m3u8(self, html_text):
        """从播放页提取m3u8地址"""
        # player_xxx var
        m = re.search(r'var player_[^{]*=\s*(\{.*?\});', html_text, re.DOTALL)
        if m:
            jstr = m.group(1)
            url_find = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', jstr)
            if url_find:
                return url_find.group(1).replace('\\/', '/')
        # direct m3u8
        m2 = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_text)
        if m2:
            return m2.group(0)
        # data‑play
        m3 = re.search(r'data-play="([^"]+)"', html_text)
        if m3:
            pu = m3.group(1)
            if pu.startswith("http") and ".m3u8" in pu:
                return pu
        return None

    def _try_other_line_m3u8(self, vod_id, nid, exclude_sid):
        detail_html = self._request_raw(f"/index.php/vod/detail/id/{vod_id}.html")
        all_sid_list = re.findall(r'sid/(\d+)/nid/', detail_html)
        other_sids = sorted([int(s) for s in all_sid_list if int(s) != exclude_sid])
        for sid in other_sids:
            alt_play = f"/index.php/vod/play/id/{vod_id}/sid/{sid}/nid/{nid}.html"
            alt_html = self._request_raw(alt_play)
            m3u8 = self._extract_m3u8(alt_html)
            if m3u8 and self._check_m3u8_alive(m3u8):
                return m3u8
        return None

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
            lst = self._cards(self._request_raw('/'))[:80]
            return {"list": lst}
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
            cls_arg = ext_obj.get("class", "")
            area_arg = ext_obj.get("area", "")
            by_arg = ext_obj.get("by", "")

            path_parts = []
            if cls_arg:
                path_parts.append(f"class/{quote(cls_arg)}")
            if area_arg:
                path_parts.append(f"area/{quote(area_arg)}")
            if by_arg:
                path_parts.append(f"by/{by_arg}")
            path_parts.append(f"id/{tid}")
            path_parts.append(f"page/{page}")
            url_path = "/index.php/vod/show/" + "/".join(path_parts) + ".html"

            html_text = self._request_raw(url_path)
            videos = self._cards(html_text)

            # 简单分页估算
            pagecount = page
            pg_matches = re.findall(r'/vod/show/id/\d+/page/(\d+)\.html', html_text)
            if pg_matches:
                pagecount = max([self._int(x) for x in pg_matches])
            search_pg_matches = re.findall(r'/vod/search/page/(\d+)/wd/', html_text)
            if search_pg_matches:
                pagecount = max(pagecount, max([self._int(x) for x in search_pg_matches]))

            total_text = re.search(r'共\s*(\d+)\s*(条|部|个|页|影片)?', html_text)
            if total_text:
                total_val = self._int(total_text.group(1))
            else:
                total_val = len(videos) * pagecount

            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": 30,
                "total": total_val
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
            vod_id = ids[0] if isinstance(ids, list) else ids
            path = f"/index.php/vod/detail/id/{vod_id}.html"
            html_text = self._request_raw(path)
            soup = self._soup(html_text)

            # 标题
            h1_tag = soup.select_one("h1")
            name = self._text(h1_tag) if h1_tag else ""
            if not name:
                title_tag = soup.select_one("title")
                if title_tag:
                    name = self._clean(title_tag.get_text()).split("-")[0].split("在线")[0]

            # 封面
            poster_img = soup.select_one(".module-info-poster img") or soup.select_one("img[data-original]")
            poster = self._image(poster_img)

            # 简介
            intro_node = soup.select_one('div[class*="content"]')
            intro = self._clean(intro_node.get_text() if intro_node else "暂无剧情")

            # 导演、主演
            vod_director = ""
            dir_match = re.search(r'导演[\s:：]*</span>\s*<div[^>]*>(.*?)</div>', html_text, re.DOTALL)
            if dir_match:
                raw_dir = dir_match.group(1)
                dir_names = re.findall(r'>([^<]+)</a>', raw_dir)
                vod_director = ",".join(dir_names) if dir_names else self._clean(raw_dir)

            vod_actor = ""
            act_match = re.search(r'主演[\s:：]*</span>\s*<div[^>]*>(.*?)</div>', html_text, re.DOTALL)
            if act_match:
                raw_act = act_match.group(1)
                act_names = re.findall(r'>([^<]+)</a>', raw_act)
                vod_actor = ",".join(act_names) if act_names else self._clean(raw_act)

            vod_year = ""
            vod_area = ""
            for m in re.finditer(r'href="/index\.php/vod/search/(year|area)/([^"]+)\.html"[^>]*>([^<]+)<', html_text):
                k_type = m.group(1)
                k_val = unquote(m.group(2))
                disp_name = m.group(3)
                if k_type == "year":
                    vod_year = disp_name
                elif k_type == "area":
                    vod_area = disp_name

            # 线路名称
            line_names = []
            for tab in soup.select(".module-tab-item[data-dropdown-value]"):
                line_names.append(tab.get("data-dropdown-value", ""))

            # 播放选集分组 sid
            play_from, play_urls = [], []
            sid_groups = {}
            seen_sid_nid = set()
            for a in soup.select('a[href*="/vod/play/id/"]'):
                href = a.get("href", "")
                m_link = re.search(r'/play/id/\d+/sid/(\d+)/nid/(\d+)\.html', href)
                if not m_link:
                    continue
                sid = m_link.group(1)
                nid = m_link.group(2)
                key = (sid, nid)
                if key in seen_sid_nid:
                    continue
                seen_sid_nid.add(key)
                ep_title = f"第{int(nid):02d}集"
                sid_groups.setdefault(sid, []).append(f"{ep_title}${href}")

            sorted_sid_keys = sorted(sid_groups.keys(), key=lambda x: self._int(x))
            for idx, sid_key in enumerate(sorted_sid_keys):
                ln = line_names[idx] if idx < len(line_names) else f"线路{idx+1}"
                play_from.append(self._clean(ln))
                play_urls.append("#".join(sid_groups[sid_key]))

            # 兜底空播放
            if not play_urls:
                play_from.append("默认线路")
                play_urls.append(f"第01集$/index.php/vod/play/id/{vod_id}/sid/1/nid/1.html")

            vod = {
                "vod_id": vod_id,
                "vod_name": self._clean(name),
                "vod_pic": poster,
                "vod_year": vod_year,
                "vod_area": vod_area,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_content": intro,
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_urls)
            }
            return {"list": [vod]}
        except Exception as exc:
            return {"list": [], "error": str(exc)}

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        try:
            page = max(1, self._int(pg, 1))
            path = f"/index.php/vod/search/page/{page}/wd/{quote(key)}.html"
            lst = self._cards(self._request_raw(path))
            return {"list": lst, "page": page}
        except Exception as exc:
            return {"list": [], "page": int(pg or 1), "error": str(exc)}

    def playerContent(self, flag, pid, vipFlags):
        try:
            header = {"User-Agent": self.ua, "Referer": self.host + "/"}
            play_url = pid
            if not play_url.startswith("http"):
                play_url = urljoin(self.host + "/", play_url.lstrip("/"))

            m_play_parts = re.search(r'/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)', play_url)
            vod_id = self._int(m_play_parts.group(1)) if m_play_parts else None
            current_sid = self._int(m_play_parts.group(2)) if m_play_parts else None
            current_nid = self._int(m_play_parts.group(3)) if m_play_parts else None

            html_text = self._request_raw(play_url)
            m3u8_url = self._extract_m3u8(html_text)
            if m3u8_url:
                if self._check_m3u8_alive(m3u8_url):
                    return {"parse": 0, "url": m3u8_url, "header": header}
                # 当前线路失效尝试其他线路
                if vod_id and current_sid and current_nid:
                    alt_m3u8 = self._try_other_line_m3u8(str(vod_id), str(current_nid), current_sid)
                    if alt_m3u8:
                        return {"parse": 0, "url": alt_m3u8, "header": header}
                return {"parse": 0, "url": m3u8_url, "header": header}
            return {"parse": 1, "url": play_url, "header": header}
        except Exception as exc:
            return {
                "parse": 1,
                "url": str(pid or ""),
                "error": str(exc)
            }

    def localProxy(self, param):
        return [404, "text/plain", "Not Found"]
