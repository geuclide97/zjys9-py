# -*- coding: utf-8 -*-
"""
Pomo4K / PoMo Cinema · UI9 py 源（v2：加站内分类列表）
站点：https://www.omo1.cc
  站内  —— emlog 博客 + 4K 原盘帖（夸克网盘 / 磁力），有分类页与翻页
  播放  —— 站点播放器插件的服务端聚合搜索（西瓜 / 暴风 / 天堂 / 非凡），给直链 m3u8
vod_id 约定：p:<文章ID> = 站内帖（详情走文章页，播放靠同名聚合搜索）
            q:<片名>   = 豆瓣/搜索结果（详情直接走聚合搜索）
"""
import json
import re
import time

try:
    import requests
except Exception:
    requests = None

try:
    import urllib3
    urllib3.disable_warnings()
except Exception:
    pass

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

from urllib.parse import quote, unquote, urljoin

BASE = "https://www.omo1.cc"
DOUBAN_API = BASE + "/content/templates/4K/douban_movie.php?api=1&section=%s"
SEARCH_API = BASE + "/content/plugins/plyr_player/api.php?type=auto_search&wd=%s"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

SITE_CATS = [
    ("huayurm", "华语热门"),
    ("dianshiju", "电视剧"),
    ("jiating", "家庭影院"),
    ("donghuadadiany", "动画大电影"),
    ("lengmenjiapian", "冷门佳片"),
    ("paihangbang", "排行榜"),
]
DOUBAN_SECS = [("nowplaying", "正在热映"), ("hot_movie", "热门电影"), ("hot_tv", "热门电视剧")]
# 线路排序：西瓜（xgplay 系）常带插播广告，默认降到末位
SOURCE_ORDER = ["暴风", "天堂", "非凡", "西瓜"]
XG_FIRST = ["西瓜", "暴风", "天堂", "非凡"]
VIDEO_RE = re.compile(r"(?i)\.(?:m3u8|mp4|flv|mkv|mov|mpd)(?:[?#].*)?$")
M3U8_RE = re.compile(r"""["'](/[^"'\s]+\.m3u8[^"'\s]*)["']""")
PAN_RE = re.compile(r"https?://(?:pan\.quark\.cn|drive\.uc\.cn|115\.com|www\.aliyundrive\.com|"
                    r"alipan\.com|pan\.baidu\.com|cloud\.189\.cn|mypikpak\.com|pan\.xunlei\.com|"
                    r"www\.123pan\.com|magnet:)[^\"'<>\\\s]*", re.I)

_CACHE = {}
_CACHE_MAX = 160


def _cget(k, ttl):
    v = _CACHE.get(k)
    if v and time.time() - v[0] <= ttl:
        return v[1]
    return None


def _cput(k, v):
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.clear()
    _CACHE[k] = (time.time(), v)


class Spider(BaseSpider):
    def __init__(self):
        self.host = BASE
        self.order = list(SOURCE_ORDER)
        self.timeout = 15
        self.session = requests.Session() if requests else None
        if self.session is not None:
            try:
                from requests.adapters import HTTPAdapter
                ad = HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
                self.session.mount("http://", ad)
                self.session.mount("https://", ad)
            except Exception:
                pass

    # ---------------- 基础 ----------------
    def getName(self):
        return "Pomo4K"

    def init(self, extend=""):
        cfg = extend if isinstance(extend, dict) else {}
        try:
            host = str(cfg.get("host") or "").strip()
            if host.startswith("http"):
                self.host = host.rstrip("/")
            self.timeout = max(6, min(30, int(cfg.get("timeout") or 12)))
            if str(cfg.get("xg_first") or "") in ("1", "true", "True"):
                self.order = list(XG_FIRST)
            custom = str(cfg.get("order") or "").strip()
            if custom:
                got = [x.strip() for x in custom.split(",") if x.strip()]
                if got:
                    self.order = got + [x for x in SOURCE_ORDER if x not in got]
        except Exception:
            pass

    def isVideoFormat(self, url):
        return bool(VIDEO_RE.search(str(url or "")))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass

    # ---------------- 网络 ----------------
    def _headers(self):
        return {"User-Agent": UA, "Referer": self.host + "/",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}

    def _fetch(self, url, as_json=False):
        if not self.session:
            raise RuntimeError("缺少 requests")
        r = self.session.get(url, headers=self._headers(), timeout=self.timeout, verify=False)
        if r.status_code != 200:
            raise RuntimeError("HTTP %d" % r.status_code)
        if not as_json:
            return r.text or ""
        try:
            return r.json()
        except Exception:
            return json.loads(r.text or "{}")

    def _douban(self, section):
        key = "douban|" + section
        hit = _cget(key, 600)
        if hit is not None:
            return hit
        rows = (self._fetch(DOUBAN_API % section, True).get("list")) or []
        _cput(key, rows)
        return rows

    def _auto_search(self, wd):
        key = "search|" + wd
        hit = _cget(key, 900)
        if hit is not None:
            return hit
        d = self._fetch(SEARCH_API % quote(wd, safe=""), True)
        rows = (d.get("data") or {}) if isinstance(d, dict) else {}
        _cput(key, rows)
        return rows

    # ---------------- 工具 ----------------
    @staticmethod
    def _pic(p):
        p = str(p or "").strip()
        if not p:
            return ""
        if p.startswith("//"):
            return "https:" + p
        if p.startswith("/"):
            return BASE + p
        return p.replace("://pomo.mom/", "://www.omo1.cc/")

    @staticmethod
    def _clean(v):
        return re.sub(r"<[^>]+>", " ", str(v or "")).strip()

    @staticmethod
    def _vid_post(pid):
        return "p:" + str(pid)

    @staticmethod
    def _vid_name(name):
        return "q:" + quote(str(name or ""), safe="")

    @staticmethod
    def _name_of(vid):
        s = str(vid or "")
        return unquote(s[2:]) if s.startswith("q:") else s

    @staticmethod
    def _cn(title):
        """把「中文名 English (年)」裁成中文名，用于聚合搜索"""
        t = str(title or "").strip()
        part = re.split(r"[A-Za-z（(]", t)[0].strip(" -·:，,")
        return part or t

    # ---------------- 列表解析 ----------------
    def _parse_list(self, html):
        out, seen = [], set()
        for chunk in (html or "").split('bg-cardbg rounded-xl')[1:]:
            m = re.search(r'href="https://www\.omo1\.cc/(\d+)\.html"', chunk)
            if not m:
                continue
            pid = m.group(1)
            if pid in seen:
                continue
            seen.add(pid)
            img = re.search(r'<img[^>]+src="([^"]+)"', chunk)
            alt = re.search(r'<img[^>]+alt="([^"]*)"', chunk)
            h3 = re.search(r"<h3[^>]*>([^<]{1,80})</h3>", chunk)
            imdb = re.search(r'IMDB<span[^>]*>([^<]{1,12})</span>', chunk)
            tags = re.findall(r'<div class="tag">([^<]{1,20})</div>', chunk)
            name = self._clean((h3.group(1) if h3 else "") or (alt.group(1) if alt else ""))
            if not name:
                continue
            notes = []
            if imdb and imdb.group(1).strip() not in ("N/A", "0"):
                notes.append(imdb.group(1).strip() + "分")
            for tg in tags:
                tg = self._clean(tg).replace("IMDB", "")
                if tg and tg not in notes and len(tg) <= 6:
                    notes.append(tg)
            item = {"vod_id": self._vid_post(pid), "vod_name": name,
                    "vod_pic": self._pic(img.group(1)) if img else ""}
            if notes:
                item["vod_remarks"] = " · ".join(notes)
            out.append(item)
        return out

    def _site_list(self, slug, pg):
        url = self.host + "/" + slug + (("/page/%d" % pg) if pg > 1 else "") + "?pjax=1"
        return self._parse_list(self._fetch(url))

    # ---------------- 目录 ----------------
    def homeContent(self, filter):
        classes = [{"type_id": s, "type_name": n} for s, n in SITE_CATS]
        classes += [{"type_id": s, "type_name": n} for s, n in DOUBAN_SECS]
        return {"class": classes}

    def homeVideoContent(self):
        try:
            items = self._parse_list(self._fetch(self.host + "/?pjax=1"))
            return {"list": items}
        except Exception:
            try:
                return {"list": self._cards_douban(self._douban("hot_movie"))}
            except Exception:
                return {"list": []}

    def _cards_douban(self, rows):
        out, seen = [], set()
        for v in rows or []:
            name = self._clean(v.get("title") or v.get("name"))
            if not name:
                continue
            key = self._vid_name(name)
            if key in seen:
                continue
            seen.add(key)
            item = {"vod_id": key, "vod_name": name, "vod_pic": self._pic(v.get("cover"))}
            notes = []
            score = str(v.get("score") or "").strip()
            if score and score not in ("0", "0.0"):
                notes.append(score + "分")
            year = self._clean(v.get("release"))
            if year:
                notes.append(year)
            reg = self._clean(v.get("region"))
            if reg:
                notes.append(reg)
            if notes:
                item["vod_remarks"] = " · ".join(notes)
            out.append(item)
        return out

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        tid = str(tid)
        empty = {"list": [], "page": pg, "pagecount": 0, "limit": 20, "total": 0}
        try:
            slugs = dict(SITE_CATS)
            if tid in slugs:
                items = self._site_list(tid, pg)
                if not items:
                    return empty
                more = 9999 if len(items) >= 16 else pg
                return {"list": items, "page": pg, "pagecount": more,
                        "limit": 16, "total": more}
            secs = dict(DOUBAN_SECS)
            if tid in secs:
                cards = self._cards_douban(self._douban(tid))
                return {"list": cards, "page": 1, "pagecount": 1,
                        "limit": len(cards) or 20, "total": len(cards)}
            return empty
        except Exception:
            return empty

    def searchContent(self, key, quick, pg="1"):
        try:
            data = self._auto_search(str(key))
            rows = []
            for src in SOURCE_ORDER + [k for k in data.keys() if k not in SOURCE_ORDER]:
                for it in data.get(src) or []:
                    it = dict(it)
                    rem = self._clean(it.get("remarks"))
                    it["remarks"] = (src + (" · " + rem if rem else ""))
                    rows.append(it)
            out, seen = [], set()
            for it in rows:
                name = self._clean(it.get("name") or it.get("title"))
                if not name or name in seen:
                    continue
                seen.add(name)
                out.append({"vod_id": self._vid_name(name), "vod_name": name,
                            "vod_pic": self._pic(it.get("cover")),
                            "vod_remarks": it.get("remarks") or ""})
            return {"list": out}
        except Exception:
            return {"list": []}

    # ---------------- 站点帖子 ----------------
    def _post(self, pid):
        key = "post|" + str(pid)
        hit = _cget(key, 900)
        if hit is not None:
            return hit
        html = self._fetch(self.host + "/" + str(pid) + ".html")
        info = {"title": "", "pic": "", "content": "", "year": "", "area": "",
                "class": "", "score": "", "remarks": "", "pans": []}
        m = re.search(r'<h2 class="x-dbjs-title">([^<]+)</h2>', html)
        if m:
            info["title"] = self._clean(m.group(1))
        m = re.search(r'x-dbjs-poster"><img[^>]+src="([^"]+)"', html)
        if m:
            info["pic"] = self._pic(m.group(1))
        m = re.search(r'<div class="x-dbjs-desc-block">[\s\S]{0,200}?<p>([\s\S]{0,900}?)</p>', html)
        if m:
            info["content"] = self._clean(m.group(1))[:600]
        for field, key_name in [("类型：", "class"), ("国家：", "area"),
                               ("时间：", "year"), ("语言：", "area2")]:
            m = re.search(r'<span>' + field + r'</span>([^<]{0,40})', html)
            if m:
                val = self._clean(m.group(1))
                if key_name == "year":
                    info["year"] = re.findall(r"\d{4}", val)[0] if re.findall(r"\d{4}", val) else val
                elif key_name == "class":
                    info["class"] = val
                elif key_name == "area":
                    info["area"] = val
        m = re.search(r'rating-badge">IMDB\s*([0-9.]{1,5})', html)
        if m:
            info["score"] = m.group(1)
        pans, seen = [], set()
        for u in PAN_RE.findall(html):
            u = u.rstrip("\\")
            if u and u not in seen:
                seen.add(u)
                pans.append(u)
        info["pans"] = pans[:12]
        _cput(key, info)
        return info

    # ---------------- 详情 --------------
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        vid = str(vid or "")
        try:
            if vid.startswith("p:"):
                return self._detail_post(vid[2:])
            return self._detail_name(self._name_of(vid))
        except Exception:
            return {"list": []}

    def _detail_post(self, pid):
        info = self._post(pid)
        title = info["title"] or ("Pomo4K " + pid)
        cn = self._cn(title)
        froms, urls = self._play_lines(cn)
        if info["pans"]:
            parts = []
            for i, u in enumerate(info["pans"]):
                kind = "夸克网盘" if "quark" in u else ("磁力" if u.startswith("magnet") else "网盘")
                parts.append("%s%d$%s" % (kind, i + 1, u))
            froms.append("原盘·网盘/磁力")
            urls.append("#".join(parts))
        if not froms:
            return {"list": []}
        vod = {
            "vod_id": self._vid_post(pid),
            "vod_name": cn or title,
            "vod_pic": info["pic"],
            "vod_remarks": ("IMDB " + info["score"]) if info["score"] else info["remarks"],
            "vod_year": info["year"],
            "vod_area": info["area"],
            "vod_class": info["class"],
            "vod_content": (info["content"] or cn) +
                            " ｜ 在线线路来自站点聚合搜索（西瓜/暴风/天堂/非凡）；原盘线路为网盘/磁力。",
            "vod_play_from": "$$$".join(froms),
            "vod_play_url": "$$$".join(urls),
        }
        return {"list": [vod]}

    def _detail_name(self, name):
        if not name:
            return {"list": []}
        froms, urls = self._play_lines(name)
        if not froms:
            return {"list": []}
        cover = ""
        try:
            data = self._auto_search(name)
            for src in SOURCE_ORDER:
                if data.get(src):
                    cover = self._pic(data[src][0].get("cover"))
                    break
        except Exception:
            pass
        vod = {"vod_id": self._vid_name(name), "vod_name": name, "vod_pic": cover,
               "vod_content": "%s ｜ 聚合搜索线路（西瓜/暴风/天堂/非凡）。" % name,
               "vod_play_from": "$$$".join(froms), "vod_play_url": "$$$".join(urls)}
        return {"list": [vod]}

    def _play_lines(self, name):
        froms, urls = [], []
        try:
            data = self._auto_search(name)
        except Exception:
            return froms, urls
        for src in self.order + [k for k in data.keys() if k not in self.order]:
            items = data.get(src) or []
            if not items:
                continue
            items = sorted(items, key=lambda x: -self._near(name, self._clean(x.get("name"))))
            it = items[0]
            groups = [g for g in str(it.get("play_url") or "").split("$$$") if g.strip()]
            # 保持站点原始顺序：落地页(/play/、/share/)在前，播放时换出带 sign 的直链，
            # 站点自带播放器走的就是这条路，实测少广告/更稳
            groups.sort(key=lambda g: 0 if ("/play/" in g or "/share/" in g) else 1)
            for gi, g in enumerate(groups):
                parts, seen = [], set()
                for ep in g.split("#"):
                    if "$" not in ep:
                        continue
                    label, addr = ep.split("$", 1)
                    label, addr = label.strip(), addr.strip()
                    if not label or not addr or label in seen:
                        continue
                    seen.add(label)
                    parts.append(label + "$" + addr)
                if not parts:
                    continue
                title = src if gi == 0 else src + "·%d" % (gi + 1)
                if title in froms:
                    title += "·%d" % (len(froms) + 1)
                froms.append(title)
                urls.append("#".join(parts))
        return froms, urls

    @staticmethod
    def _near(a, b):
        a, b = str(a or "").lower(), str(b or "").lower()
        if not a or not b:
            return 0
        if a == b:
            return 100
        if a in b or b in a:
            return 60
        return min(50, len(set(a) & set(b)) * 2)

    # ---------------- 播放 --------------
    def _hdr(self, url):
        """跟站点自带播放器一致的请求特征：浏览器 UA + 同源 Referer"""
        try:
            host = "https://" + str(url).split("/")[2]
        except Exception:
            host = ""
        return {"User-Agent": UA, "Referer": host + "/", "Origin": host}

    def playerContent(self, flag, id, vipFlags):
        url = str(id or "").strip()
        if not url:
            return {"parse": 1, "url": url, "header": {}}
        if self.isVideoFormat(url):
            return {"parse": 0, "url": url, "header": self._hdr(url)}
        hit = _cget("play|" + url, 900)
        if hit:
            return {"parse": 0, "url": hit, "header": self._hdr(hit)}
        try:
            html = self._fetch(url)
            got = self._extract(html, url)
            if got:
                _cput("play|" + url, got)
                return {"parse": 0, "url": got, "header": self._hdr(got)}
        except Exception:
            pass
        return {"parse": 1, "url": url, "header": self._hdr(url)}

    def _extract(self, html, page):
        for m in M3U8_RE.findall(html or ""):
            cand = urljoin(page, m)
            if self.isVideoFormat(cand):
                return cand
        m = re.search(r"""https?://[^"'\s]+\.m3u8[^"'\s]*""", html or "")
        return m.group(0) if m else ""

    def localProxy(self, param):
        return [404, "text/plain", "not supported"]
