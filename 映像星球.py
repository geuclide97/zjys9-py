# -*- coding: utf-8 -*-
# 架构沿用快看影视，深度提速优化版 | 映像星球
# by @一朵诡异的花 架构，全链路性能优化
import json
import random
import re
import sys
import time
from base64 import b64encode, b64decode
from urllib.parse import urljoin, quote

sys.path.append('..')
from base.spider import Spider

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None

from bs4 import BeautifulSoup


class Spider(Spider):

    def init(self, extend=""):
        self.headers = dict(self.headers)
        self._token_ready = True
        self._session = None
        self._play_cache = {}
        self._pub_key = None
        self._pri_key = None
        # deviceId只生成一次永久缓存，不再重复计算
        try:
            self.headers['deviceId'] = self.getdid()
        except Exception:
            hex_chars = '0123456789abcdef'
            self.headers['deviceId'] = ''.join(random.choice(hex_chars) for _ in range(16))

    def getName(self):
        return "映像星球"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    host = 'https://www.yxxq41.cc'
    headers = {
        'HOST': 'www.yxxq41.cc',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'client': 'web',
        'deviceType': 'PC',
        'Referer': host
    }

    publicKey_str = ""
    privateKey_str = ""

    def rsa_encrypt(self, text):
        return text
    def rsa_decrypt(self, text):
        return text

    def _get_session(self):
        # 全局只初始化一次session，全局复用连接池，最大减少TCP握手耗时
        if self._session:
            return self._session
        sess = requests.Session()
        retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[500,502,503,504])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        sess.headers.update(self.headers)
        sess.verify = False
        self._session = sess
        return sess

    def fetch(self, url, headers=None, timeout=20):
        sess = self._get_session()
        resp = sess.get(url, headers=headers, timeout=timeout)
        if resp.encoding in (None, "ISO-8859-1"):
            resp.encoding = resp.apparent_encoding
        return resp

    def post(self, url, headers=None, json=None, timeout=10):
        sess = self._get_session()
        return sess.post(url, headers=headers, json=json, timeout=timeout)

    def refresh_token(self):
        return
    def gettk(self):
        return ""

    def getdid(self):
        try:
            cache_id = self.getCache('ldid')
            if cache_id:
                return cache_id
        except Exception:
            pass
        hex_chars = '0123456789abcdef'
        new_id = ''.join(random.choice(hex_chars) for _ in range(16))
        try:
            self.setCache('ldid', new_id)
        except Exception:
            pass
        return new_id

    CATEGORY_MAP = {
        "1": "电影", "2": "电视剧", "3": "综艺", "4": "动漫",
        "7": "纪录片", "39": "短剧", "53": "体育",
    }

    def homeContent(self, filter):
        try:
            html = self.fetch(f"{self.host}/").text
        except Exception:
            return {"class": [], "filters": {}}
        classes = [{"type_id": k, "type_name": v} for k, v in self.CATEGORY_MAP.items()]
        sort_rule = {"key": "sort", "name": "排序", "value": [{"n": "最新", "v": "NEWEST"}, {"n": "热门", "v": "HOT"}]}
        filters = {tid: [sort_rule] for tid in self.CATEGORY_MAP}
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        try:
            html = self.fetch(f"{self.host}/").text
        except Exception:
            return {"list": []}
        soup = BeautifulSoup(html, "html.parser")
        videos = []
        seen = set()
        # 一步过滤广告item
        items = soup.select('a.module-poster-item:not([data-ad-slot]):not(.mac-ad-card)')
        for item in items[:40]:
            href = item.get("href", "")
            vid_res = re.search(r"/html/(\d+)\.html", href)
            if not vid_res:
                continue
            vid = vid_res.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            title = item.select_one(".module-poster-item-title").get_text(strip=True) if item.select_one(".module-poster-item-title") else ""
            img = item.select_one(".module-item-pic img")
            pic = urljoin(self.host, img.get("data-original", img.get("src", ""))) if img else ""
            note = item.select_one(".module-item-note").get_text(strip=True) if item.select_one(".module-item-note") else ""

            videos.append({"vod_id": f"{vid}@@", "vod_name": title, "vod_pic": pic, "vod_remarks": note})
            if len(videos) >= 36:
                break
        return {"list": videos}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if str(pg).isdigit() else 1
        url = f"{self.host}/list/{tid}.html" if page == 1 else f"{self.host}/list/{tid}-{page}.html"
        try:
            html = self.fetch(url).text
        except Exception:
            return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}

        soup = BeautifulSoup(html, "html.parser")
        vod_list = []
        items = soup.select('a.module-poster-item:not([data-ad-slot]):not(.mac-ad-card)')
        for item in items:
            href = item.get("href", "")
            vid_res = re.search(r"/html/(\d+)\.html", href)
            if not vid_res:
                continue
            vid = vid_res.group(1)
            title = item.select_one(".module-poster-item-title").get_text(strip=True) if item.select_one(".module-poster-item-title") else ""
            img = item.select_one(".module-item-pic img")
            pic = urljoin(self.host, img.get("data-original", img.get("src", ""))) if img else ""
            note = item.select_one(".module-item-note").get_text(strip=True) if item.select_one(".module-item-note") else ""
            vod_list.append({"vod_id": f"{vid}@@{tid}", "vod_name": title, "vod_pic": pic, "vod_remarks": note})

        total = 0
        total_match = re.search(r"共(\d+)条", html)
        if total_match:
            total = int(total_match.group(1))
        page_nums = [int(i.text) for i in soup.select(".module-page a") if i.text.isdigit()]
        total_page = max(page_nums) if page_nums else page

        return {
            "list": vod_list, "page": page, "pagecount": total_page, "limit": 20, "total": total
        }

    def detailContent(self, ids):
        ids_split = ids[0].split('@@')
        vod_id = ids_split[0]
        type_id = ids_split[-1] if len(ids_split) > 1 else ""
        try:
            html = self.fetch(f"{self.host}/html/{vod_id}.html").text
        except Exception:
            return {"list": []}
        soup = BeautifulSoup(html, "html.parser")

        # 基础信息一次性取值，减少重复查询
        h1_tag = soup.select_one(".module-info-heading h1")
        vod_name = h1_tag.get_text(strip=True) if h1_tag else ""

        img_pic = soup.select_one(".module-info-poster .module-item-pic img")
        vod_pic = urljoin(self.host, img_pic.get("data-original", img_pic.get("src", ""))) if img_pic else ""

        vod_year = vod_area = type_name = ""
        tag_texts = [tag.get_text(strip=True) for tag in soup.select(".module-info-tag-link a")]
        area_keywords = {"大陆", "香港", "台湾", "韩国", "日本", "欧美", "泰国", "印度", "国产"}
        for t in tag_texts:
            if not vod_year and re.match(r"20\d{2}", t):
                vod_year = t
            if not vod_area and t in area_keywords:
                vod_area = t
            if not type_name:
                type_name = t

        vod_remarks = vod_content = ""
        for info_block in soup.select(".module-info-item"):
            tit = info_block.select_one(".module-info-item-title")
            con = info_block.select_one(".module-info-item-content")
            if tit and con and "备注" in tit.get_text():
                vod_remarks = con.get_text(strip=True)
        intro_block = soup.select_one(".module-info-introduction-content")
        if intro_block:
            vod_content = intro_block.get_text(strip=True)

        # 播放线路解析 取消多线程，纯DOM快速解析
        source_names = [tab.get_text(strip=True) for tab in soup.select("#y-playList .tab-item") if tab.get_text(strip=True)]
        panel_list = soup.select(".tab-list.his-tab-list")
        play_sources = []

        if source_names and panel_list and len(source_names) == len(panel_list):
            for src_name, panel in zip(source_names, panel_list):
                eps = []
                for link in panel.select("a.module-play-list-link"):
                    ep_href = link.get("href", "")
                    ep_name_span = link.select_one("span")
                    ep_name = ep_name_span.get_text(strip=True) if ep_name_span else ""
                    if ep_href and ep_name:
                        eps.append((ep_name, ep_href))
                if eps:
                    play_sources.append((src_name, eps))
        else:
            # 正则兜底
            ep_reg = re.findall(r'<a class="module-play-list-link"[^>]*href="(/play/.*?\.html)"[^>]*>.*?<span>(.*?)</span>', html, re.S)
            if ep_reg:
                name_use = source_names[0] if source_names else "默认线路"
                play_sources.append((name_use, [(n.strip(), h) for h, n in ep_reg]))

        play_from_arr = []
        play_url_arr = []
        for src_name, ep_items in play_sources:
            play_from_arr.append(src_name)
            ep_str_buffer = []
            for ep_name, ep_href in ep_items:
                full_play = urljoin(self.host, ep_href)
                payload = json.dumps({"playUrl": full_play, "episodeId": f"{vod_id}_{ep_name}"})
                ep_str_buffer.append(f"{ep_name}${self.e64(payload)}")
            play_url_arr.append("#".join(ep_str_buffer))

        vod_info = {
            "type_name": type_name, "vod_year": vod_year, "vod_area": vod_area,
            "vod_actor": "", "vod_director": "", "vod_content": vod_content,
            "vod_name": vod_name, "vod_pic": vod_pic, "vod_remarks": vod_remarks,
            "vod_play_from": "$$$".join(play_from_arr),
            "vod_play_url": "$$$".join(play_url_arr)
        }
        return {"list": [vod_info]}

    def searchContent(self, key, quick, pg="1"):
        page = int(pg)
        encode_key = quote(key)
        search_url = f"{self.host}/search/{encode_key}-------------{page}.html"
        try:
            html = self.fetch(search_url).text
        except Exception:
            return {"list": [], "page": page, "total": 0}
        soup = BeautifulSoup(html, "html.parser")
        vod_list = []
        seen_ids = set()
        items = soup.select(".module-item")
        for block in items:
            a_tag = block.select_one('a[href*="/html/"]')
            if not a_tag:
                continue
            href = a_tag.get("href", "")
            vid_match = re.search(r"/html/(\d+)\.html", href)
            if not vid_match:
                continue
            vid = vid_match.group(1)
            if vid in seen_ids:
                continue
            seen_ids.add(vid)
            title = a_tag.get("title", "").strip() or a_tag.get_text(strip=True)
            img = block.select_one("img")
            pic = urljoin(self.host, img.get("data-original", img.get("src", ""))) if img else ""
            note_tag = block.select_one(".module-item-note,.video-note,.note")
            note = note_tag.get_text(strip=True) if note_tag else ""
            vod_list.append({"vod_id": f"{vid}@@", "vod_name": title, "vod_pic": pic, "vod_remarks": note})

        total_match = re.search(r"找到(\d+)部影片", html)
        total = int(total_match.group(1)) if total_match else len(vod_list)
        return {"list": vod_list, "page": page, "pagecount": 1, "limit": 20, "total": total}

    def playerContent(self, flag, id, vipFlags):
        header = {"User-Agent": self.headers["User-Agent"], "Referer": self.host}
        raw_json = self.d64(id)
        if not raw_json:
            return {"parse": 0, "url": "", "header": header}
        try:
            data = json.loads(raw_json)
            cache_key = data.get("episodeId", raw_json[:32])
            now_ts = time.time()
            # 命中缓存直接返回，完全跳过网络请求
            cache_item = self._play_cache.get(cache_key)
            if cache_item and now_ts - cache_item[0] < 1800:
                return {"parse": 0, "url": cache_item[1], "header": header}

            play_page = data["playUrl"]
            html = self.fetch(play_page, timeout=8).text
            player_match = re.search(r'player_aaaa\s*=\s*(\{.*?\});', html, re.DOTALL)
            real_url = ""
            if player_match:
                try:
                    real_url = json.loads(player_match.group(1)).get("url", "")
                except Exception:
                    pass
            if real_url:
                self._play_cache[cache_key] = (now_ts, real_url)
                return {"parse": 0, "url": real_url, "header": header}
            return {"parse": 1, "url": play_page, "header": header}
        except Exception:
            return {"parse": 0, "url": "", "header": header}

    def localProxy(self, param):
        pass
    def liveContent(self, url):
        pass

    def e64(self, text):
        try:
            return b64encode(text.encode("utf-8")).decode()
        except Exception:
            return ""
    def d64(self, text):
        try:
            return b64decode(text.encode("utf-8")).decode()
        except Exception:
            return ""

    # 无用兼容函数空占位，不会被执行
    def _fetch_desc(self, jdata): return {}
    def _fetch_players(self, payload): return []
    def getd(self, jdata, player): return jdata, []
    def getv(self, d, c): return {}
    def getlist(self, data): return []