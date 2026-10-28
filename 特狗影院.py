# -*- coding: utf-8 -*-
"""
特狗影院 TVBox 爬虫源
站点: https://www.tegou.me
CMS: MacCMS V10 (stui 模板)
修复: 副标题 / 简介 / 选集 解析
"""
import re
import json
import base64
import requests
from urllib.parse import urljoin, quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

requests.packages.urllib3.disable_warnings()

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        def init(self, extend=""):
            pass
        def getProxyUrl(self, local=True):
            return ""


class Spider(BaseSpider):

    def getName(self):
        return "特狗影院"

    def init(self, extend=""):
        conf = {}
        if isinstance(extend, dict):
            conf = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                conf = json.loads(extend)
            except Exception:
                if extend.startswith("http"):
                    conf = {"host": extend}
        if isinstance(conf.get("ext"), dict):
            conf = conf["ext"]

        self.host = str(conf.get("host") or "https://www.tegou.me").rstrip("/")
        self.timeout = int(conf.get("timeout") or 15)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": self.host + "/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.cats = self._load_cats()

    # ═══════════════════════════════════════════════════════════════
    #  基础工具
    # ═══════════════════════════════════════════════════════════════

    def _get(self, url, referer=None):
        h = self.headers.copy()
        if referer:
            h["Referer"] = referer
        try:
            resp = self.session.get(url, headers=h, timeout=self.timeout)
            resp.raise_for_status()
            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp
        except Exception:
            return None

    def _fix(self, url, base=None):
        if not url:
            return ""
        url = str(url).strip()
        if url.startswith("//"):
            return "https:" + url
        if not url.startswith(("http://", "https://")):
            return urljoin(base or self.host, url)
        return url

    def _clean(self, text):
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", str(text))
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # ═══════════════════════════════════════════════════════════════
    #  分类
    # ═══════════════════════════════════════════════════════════════

    def _load_cats(self):
        try:
            r = self._get(self.host + "/")
            if r:
                cats = []
                seen = set()
                for m in re.finditer(r'<a[^>]+href="(/vodtype/(\d+)\.html)"[^>]*>([^<]+)</a>', r.text):
                    tid = m.group(2)
                    name = self._clean(m.group(3))
                    if not tid or not name or tid in seen or len(name) > 8:
                        continue
                    seen.add(tid)
                    cats.append({"type_id": tid, "type_name": name})
                if cats:
                    return cats[:10]
        except Exception:
            pass
        return [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "连续剧"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
        ]

    # ═══════════════════════════════════════════════════════════════
    #  列表解析（修复副标题）
    # ═══════════════════════════════════════════════════════════════

    def _parse_list(self, html):
        if not html:
            return []
        items = []
        seen = set()

        starts = [(m.start(), m.end()) for m in re.finditer(
            r'<div[^>]*class="[^"]*stui-vodlist__box[^"]*"', html)]

        for i, (start, end) in enumerate(starts):
            if i + 1 < len(starts):
                block_end = starts[i + 1][0]
            else:
                ul_end = html.find("</ul>", end)
                block_end = ul_end if ul_end > 0 else len(html)
            block = html[end:block_end]

            # 主链接
            a_m = re.search(r'<a[^>]+class="[^"]*stui-vodlist__thumb[^"]*"[^>]*>', block, re.S)
            if not a_m:
                a_m = re.search(r'<a[^>]+href="(/voddetail/[^"]+)"[^>]*>', block, re.S)
            if not a_m:
                continue
            a_tag = a_m.group(0)

            href_m = re.search(r'href="([^"]+)"', a_tag)
            title_m = re.search(r'title="([^"]*)"', a_tag)
            href = href_m.group(1) if href_m else ""
            title = title_m.group(1) if title_m else ""

            vid_m = re.search(r'/voddetail/(\d+)\.html', href)
            if not vid_m:
                continue
            vid = vid_m.group(1)
            if vid in seen:
                continue
            seen.add(vid)

            # 图片：data-original → style background-image → img src
            pic = ""
            pic_m = re.search(r'data-original="([^"]+)"', a_tag)
            if pic_m:
                pic = pic_m.group(1)
            else:
                bg_m = re.search(r'background-image\s*:\s*url\(([^)]+)\)', a_tag)
                if bg_m:
                    pic = bg_m.group(1).strip("'\" ")
                else:
                    img_m = re.search(r'<img[^>]+(?:data-original|data-src|src)="([^"]+)"', block)
                    if img_m:
                        pic = img_m.group(1)

            # 副标题：优先 <span class="pic-text ...">文本</span>
            remark = ""
            rm = re.search(
                r'<span[^>]*class="[^"]*pic-text[^"]*"[^>]*>(.*?)</span>',
                block, re.S)
            if rm:
                remark = self._clean(rm.group(1))

            # 兜底：<span class="text-right" title="xx">
            if not remark:
                rm2 = re.search(
                    r'<span[^>]*class="[^"]*text-right[^"]*"[^>]*title="([^"]*)"',
                    block)
                if rm2:
                    remark = self._clean(rm2.group(1))

            # 兜底：<p class="text text-muted">xx</p> 里取更新状态
            if not remark:
                rm3 = re.search(
                    r'<p[^>]*class="[^"]*text[^"]*text-muted[^"]*"[^>]*>(.*?)</p>',
                    block, re.S)
                if rm3:
                    txt = self._clean(rm3.group(1))
                    # 只取包含"更新/集/HD/BD/完结"这类状态文本
                    if txt and re.search(r"(更新|集|完结|HD|BD|TC|预告|共\d)", txt):
                        remark = txt

            # 标题兜底
            if not title:
                h4_m = re.search(
                    r'<h4[^>]*class="[^"]*title[^"]*"[^>]*>.*?<a[^>]*?title="([^"]*)"',
                    block, re.S)
                if h4_m:
                    title = h4_m.group(1)
            if not title:
                h4_m2 = re.search(
                    r'<h4[^>]*class="[^"]*title[^"]*"[^>]*>.*?<a[^>]*>([^<]+)</a>',
                    block, re.S)
                if h4_m2:
                    title = self._clean(h4_m2.group(1))
            if not title:
                continue

            items.append({
                "vod_id": vid,
                "vod_name": self._clean(title),
                "vod_pic": self._fix(pic),
                "vod_remarks": remark,
            })
        return items

    # ═══════════════════════════════════════════════════════════════
    #  TVBox 六接口
    # ═══════════════════════════════════════════════════════════════

    def homeContent(self, filter):
        return {"class": self.cats, "filters": self._build_filters()}

    def homeVideoContent(self):
        r = self._get(self.host + "/")
        return {"list": self._parse_list(r.text) if r else []}

    def _build_filters(self):
        filters = {}
        areas = [
            {"n": "全部", "v": ""},
            {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
            {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"},
            {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"},
            {"n": "泰国", "v": "泰国"}, {"n": "英国", "v": "英国"},
            {"n": "法国", "v": "法国"}, {"n": "其它", "v": "其它"},
        ]
        years = [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2025, 2009, -1)]
        orders = [
            {"n": "最新", "v": "time"},
            {"n": "最热", "v": "hits"},
            {"n": "评分", "v": "score"},
        ]
        langs = [
            {"n": "全部", "v": ""},
            {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
            {"n": "粤语", "v": "粤语"}, {"n": "日语", "v": "日语"},
            {"n": "韩语", "v": "韩语"},
        ]
        letters = [{"n": "全部", "v": ""}] + [{"n": c, "v": c} for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [{"n": "0-9", "v": "0-9"}]

        for cat in self.cats:
            filters[cat["type_id"]] = [
                {"key": "area", "name": "地区", "value": areas},
                {"key": "year", "name": "年份", "value": years},
                {"key": "by", "name": "排序", "value": orders},
                {"key": "lang", "name": "语言", "value": langs},
                {"key": "letter", "name": "字母", "value": letters},
            ]
        return filters

    def _build_cate_url(self, tid, pg, extend):
        area = (extend.get("area") or "").strip()
        by = (extend.get("by") or "").strip()
        cls = (extend.get("class") or "").strip()
        lang = (extend.get("lang") or "").strip()
        letter = (extend.get("letter") or "").strip()
        year = (extend.get("year") or "").strip()

        if pg == 1 and not any([area, cls, lang, letter, year]):
            return f"{self.host}/vodtype/{tid}.html"

        if not by:
            by = "time"
        return (
            f"{self.host}/vodtype/{tid}"
            f"/area/{area}/by/{by}/class/{cls}"
            f"/lang/{lang}/letter/{letter}"
            f"/page/{pg}/year/{year}.html"
        )

    def categoryContent(self, tid, pg, filter, extend):
        try:
            extend = extend or {}
            pg = int(pg) if str(pg).isdigit() else 1
            url = self._build_cate_url(tid, pg, extend)
            r = self._get(url)
            if not r:
                return {"list": [], "page": pg, "pagecount": pg, "limit": 20, "total": 0}
            html = r.text
            items = self._parse_list(html)
            pagecount = self._parse_pagecount(html, tid)
            if pagecount < pg:
                pagecount = pg + 1 if items else pg
            return {
                "list": items,
                "page": pg,
                "pagecount": pagecount,
                "limit": len(items) or 20,
                "total": pagecount * 20,
            }
        except Exception:
            return {
                "list": [], "page": int(pg) if str(pg).isdigit() else 1,
                "pagecount": 1, "limit": 20, "total": 0,
            }

    def _parse_pagecount(self, html, tid):
        if not html:
            return 1
        nums = []
        for m in re.finditer(r'共\s*(\d+)\s*页', html):
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                pass
        tid_re = re.escape(tid) if tid else r"\d+"
        for m in re.finditer(rf'/vodtype/{tid_re}/page/(\d+)', html):
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                pass
        for m in re.finditer(r'[?&]page=(\d+)', html):
            try:
                v = int(m.group(1))
                if 0 < v < 10000:
                    nums.append(v)
            except ValueError:
                pass
        return max(nums) if nums else 1

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            key = str(key or "").strip()
            if not key:
                return {"list": [], "page": pg}
            url = f"{self.host}/vod/search/page/{pg}/wd/{quote(key)}.html"
            r = self._get(url)
            if not r:
                return {"list": [], "page": pg, "pagecount": 1}
            items = self._parse_list(r.text)
            pagecount = self._parse_pagecount(r.text, "")
            return {"list": items, "page": pg, "pagecount": max(pagecount, pg)}
        except Exception:
            return {"list": [], "page": int(pg) if str(pg).isdigit() else 1}

    # ═══════════════════════════════════════════════════════════════
    #  详情（修复简介 + 选集）
    # ═══════════════════════════════════════════════════════════════

    def detailContent(self, ids):
        vid = str((ids or [""])[0] or "")
        if not vid:
            return {"list": []}
        try:
            r = self._get(f"{self.host}/voddetail/{vid}.html")
            if not r:
                return {"list": []}
            html = r.text

            # ── 标题 ──
            title = ""
            for pat in (
                r'<h1[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</h1>',
                r'<h1[^>]*>(.*?)</h1>',
            ):
                t_m = re.search(pat, html, re.S)
                if t_m:
                    title = self._clean(t_m.group(1))
                    if title:
                        break
            if not title:
                t_m = re.search(r'<title>(.*?)</title>', html, re.S)
                if t_m:
                    title = re.split(r"[-_|]", self._clean(t_m.group(1)))[0].strip()

            # ── 封面 ──
            pic = ""
            p_m = re.search(
                r'<a[^>]*class="[^"]*stui-content__thumb[^"]*"[^>]*>.*?<img[^>]+(?:data-original|src)="([^"]+)"',
                html, re.S)
            if not p_m:
                p_m = re.search(
                    r'<img[^>]*class="[^"]*lazyload[^"]*"[^>]*(?:data-original|src)="([^"]+)"',
                    html)
            if not p_m:
                p_m = re.search(r'<img[^>]+(?:data-original|src)="([^"]+)"', html)
            if p_m:
                pic = self._fix(p_m.group(1))

            # ── 简介：多路径尝试 ──
            desc = ""
            desc_patterns = (
                # stui V10 标准：<span class="detail-content">简介</span>
                r'<span[^>]*class="[^"]*detail-content[^"]*"[^>]*>(.*?)</span>',
                # <div class="detail-content">简介</div>
                r'<div[^>]*class="[^"]*detail-content[^"]*"[^>]*>(.*?)</div>',
                # <span class="detail">简介</span>
                r'<span[^>]*class="[^"]*detail[^"]*"[^>]*>(.*?)</span>',
                # <p class="desc">简介</p>
                r'<p[^>]*class="[^"]*desc[^"]*"[^>]*>(.*?)</p>',
                # <p class="col-pd">简介</p>
                r'<p[^>]*class="[^"]*col-pd[^"]*"[^>]*>(.*?)</p>',
                # 兜底：详情区第一个长文本 <p>
                r'<div[^>]*class="[^"]*stui-content__detail[^"]*"[^>]*>.*?<p[^>]*>(.*?)</p>',
            )
            for pat in desc_patterns:
                d_m = re.search(pat, html, re.S)
                if d_m:
                    candidate = self._clean(d_m.group(1))
                    # 过滤掉明显是标签栏、导演、主演等短信息
                    if candidate and len(candidate) > 10 and not re.match(
                            r"^(类型|地区|年份|导演|主演|语言|更新)[：:]", candidate):
                        desc = candidate
                        break

            # ── 选集 ──
            play_from, play_url = self._parse_playlist(html, vid)

            return {"list": [{
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_content": desc,
                "vod_play_from": play_from,
                "vod_play_url": play_url,
            }]}
        except Exception:
            return {"list": []}

    def _parse_playlist(self, html, vid):
        """
        正确解析 MacCMS V10 stui 模板的播放列表：
        - 线路名从 <a href="#playlistN">线路名</a> 提取
        - 每个线路的剧集从对应 <div id="playlistN"> 内的 <a href="/vodplay/..."> 提取
        """
        # 1. 提取线路名映射
        line_names = {}
        for m in re.finditer(
                r'<a[^>]+href="#playlist(\d+)"[^>]*>([^<]*)</a>', html):
            sid = m.group(1)
            name = self._clean(m.group(2))
            if name:
                line_names[sid] = name

        # 2. 提取每个线路块下的剧集
        # stui V10 结构：<div id="playlist1" class="tab-pane..."><ul>...剧集...</ul></div>
        # 用非贪婪切割各 playlist 块
        blocks = re.findall(
            r'<div[^>]+id="playlist(\d+)"[^>]*>(.*?)(?=<div[^>]+id="playlist\d+"|</div>\s*</div>\s*</div>|<footer)',
            html, re.S)

        play_from = []
        play_url = []

        # 兼容两种剧集链接格式
        ep_re = re.compile(
            r'<a[^>]+href="(/vodplay/(\d+)-(\d+)-(\d+)\.html)"[^>]*>(.*?)</a>',
            re.S)
        ep_re2 = re.compile(
            r'<a[^>]+href="(/vodplay/(\d+)/(\d+)/(\d+)\.html)"[^>]*>(.*?)</a>',
            re.S)

        for sid, block in blocks:
            # 剔除 tag 以外的内容，只保留当前线路下的剧集
            eps = []
            for m in ep_re.finditer(block):
                href, v, s, n, txt = m.group(1), m.group(2), m.group(3), m.group(4), self._clean(m.group(5))
                if v != vid:
                    continue
                eps.append({"sid": s, "nid": n, "href": href, "title": txt})
            if not eps:
                for m in ep_re2.finditer(block):
                    href, v, s, n, txt = m.group(1), m.group(2), m.group(3), m.group(4), self._clean(m.group(5))
                    if v != vid:
                        continue
                    eps.append({"sid": s, "nid": n, "href": href, "title": txt})

            if not eps:
                continue

            # 按 nid 排序
            eps.sort(key=lambda x: int(x["nid"]) if x["nid"].isdigit() else 0)

            line_name = line_names.get(sid, f"线路{sid}")
            # 去重（防止模板重复渲染）
            seen_ep = set()
            ep_strs = []
            for ep in eps:
                title = ep["title"] or f"第{ep['nid']}集"
                key = ep["href"]
                if key in seen_ep:
                    continue
                seen_ep.add(key)
                ep_strs.append(f"{title}${self._fix(ep['href'])}")

            if ep_strs:
                play_from.append(line_name)
                play_url.append("#".join(ep_strs))

        # 3. 兜底：整页扫一遍 /vodplay/{vid}-*-*.html
        if not play_from:
            groups = {}
            for m in ep_re.finditer(html):
                href, v, s, n, txt = m.group(1), m.group(2), m.group(3), m.group(4), self._clean(m.group(5))
                if v != vid:
                    continue
                groups.setdefault(s, []).append({
                    "nid": n, "href": href, "title": txt
                })
            for sid in sorted(groups.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                eps = sorted(groups[sid], key=lambda x: int(x["nid"]) if x["nid"].isdigit() else 0)
                line_name = line_names.get(sid, f"线路{sid}")
                seen_ep = set()
                ep_strs = []
                for ep in eps:
                    if ep["href"] in seen_ep:
                        continue
                    seen_ep.add(ep["href"])
                    title = ep["title"] or f"第{ep['nid']}集"
                    ep_strs.append(f"{title}${self._fix(ep['href'])}")
                if ep_strs:
                    play_from.append(line_name)
                    play_url.append("#".join(ep_strs))

        return "$$$".join(play_from), "$$$".join(play_url)

    # ═══════════════════════════════════════════════════════════════
    #  播放
    # ═══════════════════════════════════════════════════════════════

    def playerContent(self, flag, id, vipFlags):
        try:
            url = self._fix(str(id or ""))
            if not url:
                return {"parse": 1, "url": "", "header": self.headers}
            r = self._get(url)
            if not r:
                return {"parse": 1, "url": url, "header": self.headers}
            html = r.text

            # MacCMS player_aaaa
            m = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\});', html, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    pu = data.get("url", "")
                    enc = data.get("encrypt", 0)
                    if enc == 2 and pu:
                        try:
                            decoded = base64.b64decode(pu).decode("utf-8", "ignore")
                            if decoded.startswith("http"):
                                return {"parse": 0, "url": decoded, "header": self.headers}
                        except Exception:
                            pass
                    if pu.startswith("http"):
                        return {"parse": 0, "url": pu, "header": self.headers}
                except Exception:
                    pass

            # 直接抓 m3u8
            m2 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
            if m2:
                return {"parse": 0, "url": m2.group(1), "header": self.headers}

            return {"parse": 1, "url": url, "header": self.headers}
        except Exception:
            return {"parse": 1, "url": self._fix(str(id or "")), "header": self.headers}

    def isVideoFormat(self, url):
        return bool(url and any(x in str(url).lower() for x in [".m3u8", ".mp4", ".flv"]))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return None

    def destroy(self):
        try:
            self.session.close()
        except Exception:
            pass