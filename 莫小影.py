# -*- coding: utf-8 -*-
import sys
import re
import json
import base64
from urllib.parse import urljoin, quote, unquote

sys.path.append('..')
from base.spider import Spider

HOST = "https://www.moxy.top"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class Spider(Spider):
    def init(self, extend=""):
        global HOST
        try:
            # Chaquopy timeout单位为秒，不再使用毫秒
            r = self.fetch(HOST, headers={"User-Agent": UA}, timeout=15)
            if hasattr(r, 'url') and r.url and "moxy" not in r.url:
                HOST = r.url.rstrip("/")
        except Exception:
            pass

    def getName(self):
        return "moxy影视"

    # ==========UI9强制必填固定方法，禁止pass==========
    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [404, "text/plain", "", None]

    def destroy(self):
        pass

    def homeContent(self, filter=False):
        r = {"class": [], "filters": {}}
        type_dict = {"1": "电影", "2": "连续剧", "3": "综艺", "4": "动漫", "5": "短剧"}
        for k, v in type_dict.items():
            r["class"].append({"type_id": k, "type_name": v})

        try:
            resp = self.fetch(HOST, headers={"User-Agent": UA}, timeout=30)
            html = resp.text
            r["list"] = self._items(html)[:60]
        except Exception:
            r["list"] = []
        return r

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        pn = 1
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pass
        cid = str(tid) if str(tid) in ["1", "2", "3", "4", "5"] else "1"
        try:
            if pn > 1:
                url = f"{HOST}/vodshow/{cid}--------{pn}---.html"
            else:
                url = f"{HOST}/vodshow/{cid}-----------.html"
            resp = self.fetch(url, headers={"User-Agent": UA}, timeout=30)
            html = resp.text
            items = self._items(html)
            page_count = self._pagecount(html)
            return {
                "page": pn,
                "pagecount": page_count,
                "limit": 50,
                "total": len(items),
                "list": items
            }
        except Exception:
            return {
                "page": pn,
                "pagecount": 1,
                "limit": 50,
                "total": 0,
                "list": []
            }

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = str(ids) if ids else ""
        m = re.search(r'(\d+)', str(vid))
        vid = m.group(1) if m else ""
        if not vid:
            return {"list": []}

        try:
            resp = self.fetch(f"{HOST}/voddetail{vid}.html", headers={"User-Agent": UA}, timeout=30)
            h = resp.text
        except Exception:
            return {"list": []}

        d = {
            "vod_id": vid,
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
            "vod_play_url": ""
        }

        # 影视名称
        t1 = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.S)
        if t1:
            d["vod_name"] = t1.group(1).strip()
        if not d["vod_name"]:
            t2 = re.search(r'<title>(.*?)</title>', h)
            if t2:
                d["vod_name"] = t2.group(1).split("-")[0].strip()

        # 封面图
        p = re.search(r'data-original="([^"]+)"', h)
        if p:
            d["vod_pic"] = p.group(1)

        # 年份
        year_list = re.findall(r'<a[^>]*title="(\d{4})"', h)
        if year_list:
            d["vod_year"] = year_list[0]

        # 地区
        area_list = re.findall(r'<a[^>]*title="([^"]*)"', h)
        area_pool = ("中国大陆", "中国", "香港", "台湾", "美国", "日本", "韩国", "英国", "法国", "泰国", "印度")
        for area in area_list:
            if area in area_pool:
                d["vod_area"] = area
                break

        # 简介
        desc = re.search(r'<div[^>]*class="[^"]*module-info-introduction-content[^"]*"[^>]*>\s*<p>(.*?)</p>', h, re.S)
        if desc:
            clean_text = re.sub(r'<[^>]+>', '', desc.group(1)).strip()
            d["vod_content"] = clean_text[:500]

        # 导演、主演、备注
        match_info = re.finditer(r'<div[^>]*class="[^"]*module-info-item[^"]*"[^>]*>(.*?)</div>', h, re.S)
        for match in match_info:
            text = re.sub(r'<[^>]+>', '', match.group(1)).strip()
            if "导演" in text:
                d["vod_director"] = text.replace("导演：", "").replace("导演:", "").strip()
            elif "主演" in text:
                d["vod_actor"] = text.replace("主演：", "").replace("主演:", "").strip()
            elif "备注" in text:
                d["vod_remarks"] = text.replace("备注：", "").replace("备注:", "").strip()

        # 多线路、剧集整理
        try:
            sources = re.findall(r'data-dropdown-value="([^"]+)"', h) or ["默认"]
            blocks = re.findall(r'<div[^>]*class="[^"]*module-play-list[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>', h, re.S)
            if not blocks:
                blocks = re.findall(r'<div[^>]*class="[^"]*module-play-list-content[^"]*"[^>]*>(.*?)</div>', h, re.S)

            play_from = []
            play_url = []
            for idx, blk in enumerate(blocks):
                eps = re.findall(r'<a[^>]*href="(/vodplay/[^"]+)"[^>]*>(?:<[^>]+>)*([^<]{1,20})(?:</[^>]+>)*</a>', blk, re.S)
                if not eps:
                    eps = re.findall(r'<a[^>]*href="(/vodplay/[^"]+)"[^>]*>.*?<span>(.*?)</span>', blk, re.S)
                if eps:
                    line_name = sources[idx] if idx < len(sources) else f"源{idx+1}"
                    ep_join = [f"{name.strip()}${urljoin(HOST, link)}" for link, name in eps if name.strip()]
                    if ep_join:
                        play_from.append(line_name)
                        play_url.append("#".join(ep_join))
            if play_from:
                d["vod_play_from"] = "$$$".join(play_from)
                d["vod_play_url"] = "$$$".join(play_url)
        except Exception:
            pass

        return {"list": [d]}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            url = f"{HOST}/vodsearch/{quote(str(key))}-------------.html"
            resp = self.fetch(url, headers={"User-Agent": UA}, timeout=15)
            html = resp.text
            if len(html) > 200:
                return {"list": self._items(html)[:30], "page": pg}
        except Exception:
            pass
        return {"list": [], "page": pg}

    def playerContent(self, flag, id, vipFlags=None):
        flag_str = str(flag)
        id_str = str(id) if id else ""
        # 拼装播放页完整地址
        if flag_str.startswith("http") or "/vodplay/" in flag_str:
            url = flag_str
        elif id_str.startswith("http") or "/vodplay/" in id_str:
            url = id_str
        elif flag_str.startswith("/"):
            url = urljoin(HOST, flag_str)
        elif id_str.startswith("/"):
            url = urljoin(HOST, id_str)
        else:
            url = flag_str

        try:
            resp = self.fetch(url, headers={"User-Agent": UA}, timeout=30)
            h = resp.text
        except Exception:
            return {"url": "", "parse": 0, "header": {"User-Agent": UA}}

        real_play_url = ""
        pd = re.search(r'player_data\s*=\s*(\{.*?\})', h, re.S)
        if pd:
            try:
                data = json.loads(pd.group(1))
                u = data.get("url", "")
                if u:
                    try:
                        real_play_url = unquote(base64.b64decode(u).decode("utf-8"))
                    except Exception:
                        real_play_url = u
            except Exception:
                pass

        return {
            "parse": 0,
            "url": real_play_url,
            "header": {"User-Agent": UA}
        }

    def _pagecount(self, html):
        pc = 1
        # 尾页匹配
        last_page = re.search(r'<a[^>]*href="[^"]*vodshow/\d+[^"]*(\d+)---\.html"[^>]*>尾页', html, re.S)
        if last_page:
            pc = max(pc, int(last_page.group(1)))
        # 分页数字
        page_links = re.findall(r'<a[^>]*href="[^"]*vodshow/\d+-(\d+)', html)
        for p in page_links:
            try:
                num = int(p)
                if num <= 100:
                    pc = max(pc, num)
            except Exception:
                continue
        number_tags = re.findall(r'class="[^"]*page-number[^"]*"[^>]*>\s*(\d+)\s*<', html)
        for n in number_tags:
            try:
                pc = max(pc, int(n))
            except Exception:
                continue
        return pc

    def _items(self, html):
        items = []
        seen_id = set()

        def parse_item(href, block_html):
            vid_match = re.search(r'/voddetail(\d+)\.html', href)
            if not vid_match or vid_match.group(1) in seen_id:
                return None
            vid = vid_match.group(1)
            seen_id.add(vid)

            # 名称
            title_match = re.search(r'title="([^"]*)"', block_html) or re.search(r'alt="([^"]*)"', block_html)
            if not title_match:
                return None
            vod_name = title_match.group(1)
            # 封面
            pic_match = re.search(r'data-original="([^"]+)"', block_html)
            vod_pic = pic_match.group(1) if pic_match else ""
            # 集数备注
            note_match = re.search(r'<div[^>]*class="[^"]*module-item-note[^"]*"[^>]*>([^<]+)</div>', block_html)
            vod_remarks = note_match.group(1).strip() if note_match else ""

            return {
                "vod_id": vid,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks
            }

        # 两种卡片正则遍历
        pattern1 = r'<a[^>]*href="(/voddetail\d+\.html)"[^>]*title="([^"]*)"[^>]*class="[^"]*module-poster-item[^"]*"[\s\S]*?</a>'
        for match in re.finditer(pattern1, html):
            res = parse_item(match.group(1), match.group(0))
            if res:
                items.append(res)

        pattern2 = r'<a[^>]*href="(/voddetail\d+\.html)"[^>]*class="[^"]*module-card-item-poster[^"]*"[\s\S]*?</a>'
        for match in re.finditer(pattern2, html):
            res = parse_item(match.group(1), match.group(0))
            if res:
                items.append(res)

        return items