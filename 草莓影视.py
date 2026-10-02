# -*- coding: utf-8 -*-
"""
草莓影视 UI9专用Python爬虫
适配UI9标准规范，支持extend后台改域名UA
UI9配置JSON：
{
  "key": "caomei_py",
  "name": "草莓影视",
  "type": 3,
  "api": "./py/caomei.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 0
}
"""
import re
import urllib.parse
import json
# UI9父类兜底，无base.spider不报错
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

class Spider(BaseSpider):
    # UI9默认扩展配置，后台extend可JSON覆盖
    DEFAULT_EXT = {
        "host": "https://artcoast.cc",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    def getName(self):
        return "草莓影视"
    def init(self, extend=""):
        # 加载扩展配置
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
        self.site_url = self.ext["host"].rstrip("/")
        self.headers = {
            'User-Agent': self.ext["ua"],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.site_url + "/",
        }
        self.default_pic = "https://pic.rmb.bdstatic.com/bjh/user/default.png"
        # 分类映射: cid -> 中文名 (取自站点导航)
        self.categories = {
            "1": "电影", "2": "电视剧", "3": "综艺剧场", "4": "动漫大全",
            "6": "动作片", "7": "喜剧片", "8": "爱情片", "9": "科幻片",
            "10": "恐怖片", "11": "剧情片", "12": "战争片",
            "13": "国产剧", "14": "港台剧", "15": "日韩剧", "16": "欧美剧",
            "20": "国产", "21": "日韩", "22": "欧美", "23": "港台", "24": "海外",
        }

    def _http(self, url):
        """UI9内置fetch获取页面文本"""
        try:
            resp = self.fetch(url, headers=self.headers)
            if resp and getattr(resp, 'text', None):
                return resp.text
        except Exception:
            pass
        return ""

    def _parse_list(self, html):
        """从列表/首页/搜索页解析视频卡片 -> vod 字典列表"""
        videos = []
        seen = set()
        for art in re.findall(r'<article class="quartz-card.*?</article>', html, re.S):
            m = re.search(r'<a class="quartz-cover" href="/vid/(\d+)\.html" title="([^"]*)"', art)
            if not m:
                continue
            vid, name = m.group(1), m.group(2).strip()
            if vid in seen:
                continue
            seen.add(vid)
            pic = re.search(r'data-src="([^"]+)"', art)
            pic = pic.group(1) if pic else ""
            dur = re.search(r'<span class="duration">([^<]*)</span>', art)
            remark = dur.group(1).strip() if dur else ""
            meta = re.search(r'<p class="card-meta">([^<]*)</p>', art)
            year = area = type_name = ""
            if meta:
                parts = [p.strip() for p in meta.group(1).split('/') if p.strip()]
                if len(parts) >= 1:
                    year = parts[0]
                if len(parts) >= 2:
                    type_name = parts[1]
                if len(parts) >= 3:
                    area = parts[2]
            videos.append({
                "vod_id": vid,
                "vod_name": name,
                "vod_pic": pic if pic else self.default_pic,
                "vod_remarks": remark,
                "vod_year": year,
                "vod_area": area,
                "vod_type": type_name,
            })
        return videos

    def _calc_pagecount(self, html, pattern):
        """从分页链接中找最大页码"""
        nums = [int(n) for n in re.findall(pattern, html)]
        return max(nums) if nums else 0

    # ========== 首页 ==========
    def homeContent(self, filter):
        categories = [{"type_id": k, "type_name": v} for k, v in self.categories.items()]
        html = self._http(self.site_url + "/")
        videos = self._parse_list(html)
        return {"class": categories, "list": videos[:30], "filters": {}}

    def homeVideoContent(self):
        html = self._http(self.site_url + "/")
        videos = self._parse_list(html)
        return {"list": videos[:30]}

    # ========== 分类 ==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        url = self.site_url + "/cid/{0}-{1}.html".format(tid, pg)
        html = self._http(url)
        videos = self._parse_list(html)
        pagecount = self._calc_pagecount(html, r'/cid/{0}-(\d+)\.html'.format(tid)) or pg
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 0,
            "total": 0,
        }

    # ========== 搜索（UI9双搜索函数，对齐规范） ==========
    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        q = urllib.parse.quote(key)
        url = self.site_url + "/search.html?wd={0}&page={1}".format(q, pg)
        html = self._http(url)
        videos = self._parse_list(html)
        pagecount = self._calc_pagecount(html, r'/search\.html\?wd=[^"\']*?page=(\d+)') or pg
        return {
            "list": videos,
            "page": pg,
            "pagecount": pagecount,
            "limit": 0,
            "total": 0,
        }

    # ========== 详情 ==========
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]
        html = self._http(self.site_url + "/vid/{0}.html".format(vid))
        if not html:
            return {"list": []}
        # 标题 (从 <title> 去掉站点后缀)
        title = re.search(r'<title>([^<]+)</title>', html)
        title = title.group(1).split(' - ')[0].strip() if title else ""
        # 海报
        pic = re.search(r'<img[^>]+src="([^"]+)"[^>]+alt="{0}"'.format(re.escape(title)), html)
        if not pic:
            pic = re.search(r'data-src="([^"]+)"', html)
        pic = pic.group(1) if pic else self.default_pic
        # 简介
        content = re.search(r'<p class="description">([^<]*)</p>', html)
        content = content.group(1).strip() if content else ""
        # 年份 / 地区 / 类型 (detail-meta: <span>2025</span><span>其它</span><span>奇幻,爱情,喜剧</span>)
        year = area = type_name = ""
        meta = re.search(r'<p class="detail-meta">(.*?)</p>', html, re.S)
        if meta:
            spans = re.findall(r'<span>(.*?)</span>', meta.group(1), re.S)
            # spans[0] 是评分, 之后依次是 年份/地区/类型
            vals = [re.sub(r'<[^>]+>', '', s).strip() for s in spans]
            vals = [v for v in vals if v and '分' not in v]
            if len(vals) >= 1:
                year = vals[0]
            if len(vals) >= 2:
                area = vals[1]
            if len(vals) >= 3:
                type_name = vals[2]
        # 导演 / 主演
        def _extract_cast(label):
            blk = re.search(label + r'[：:]\s*(.*?)(?:<span>|</p>)', html, re.S)
            if not blk:
                return ""
            names = re.findall(r'<a[^>]*>([^<]+)</a>', blk.group(1))
            return " / ".join(names[:20])
        director = _extract_cast(r'导演')
        actor = _extract_cast(r'主演')
        # 播放源与选集
        play_from = []
        play_url = []
        for blk in re.findall(r'<div class="play-source">(.*?)</div>\s*</div>', html, re.S):
            line = re.search(r'<h3>(.*?)</h3>', blk)
            line_name = re.sub(r'<[^>]+>', '', line.group(1)).strip() if line else "线路"
            eps = re.findall(r'href="(/pid/[^"]+)"[^>]*>(.*?)</a>', blk)
            ep_list = []
            for href, ep_name in eps:
                ep_name = re.sub(r'<[^>]+>', '', ep_name).strip() or "播放"
                ep_list.append("{0}${1}".format(ep_name, self.site_url + href))
            if ep_list:
                play_from.append(line_name)
                play_url.append("#".join(ep_list))
        # 兜底
        if not play_from:
            play_from.append("默认线路")
            play_url.append("播放${0}/vid/{1}.html".format(self.site_url, vid))
        return {"list": [{
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_year": year,
            "vod_area": area,
            "vod_type": type_name,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags):
        """获取播放链接
        id 格式: ep_title$pid_full_url (从 vod_play_url 拆分而来)
        pid 播放页内含 player_xxxx 变量, url 字段即 m3u8 直链
        """
        play_url = id
        if "$" in id:
            play_url = id.split("$")[-1]
        play_url = play_url.strip()
        if not play_url:
            return {"parse": 1, "url": id, "header": self.headers}
        # /pid/ 播放页: 提取 m3u8 直链
        if "/pid/" in play_url:
            html = self._http(play_url)
            m = re.search(r'"url"\s*:\s*"([^"]*?\.m3u8[^"]*)"', html)
            if m:
                m3u8 = m.group(1).replace('\\/', '/')
                if m3u8.startswith('//'):
                    m3u8 = 'https:' + m3u8
                return {
                    "parse": 0,
                    "url": m3u8,
                    "header": {
                        'User-Agent': self.headers['User-Agent'],
                        'Referer': self.site_url + "/",
                    }
                }
        # 已经是 m3u8 / mp4 直链
        if '.m3u8' in play_url or '.mp4' in play_url:
            return {
                "parse": 0,
                "url": play_url,
                "header": {
                    'User-Agent': self.headers['User-Agent'],
                    'Referer': self.site_url + "/",
                }
            }
        # 其它情况交给 webview 嗅探
        return {
            "parse": 1,
            "url": play_url,
            "header": self.headers
        }

    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(m3u8|mp4|mkv|ts|flv)(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    def localProxy(self, param=''):
        return [404, "text/plain", "NotFound"]

    def destroy(self):
        pass

if __name__ == '__main__':
    sp = Spider()
    sp.init()
