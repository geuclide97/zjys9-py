# -*- coding: utf-8 -*-
import re
import sys
import time
import base64
from urllib.parse import quote, unquote
import requests

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.host = "https://www.22a5.com"
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/"
        }
        self.session.headers.update(self.headers)

    def getName(self):
        return "爱听音乐"

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|mp3|m4a|flv|m4a)(\?|$)', url or "", re.I))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self.session.close()

    def homeContent(self, filter):
        classes = [
            {"type_name": "歌手", "type_id": "/singerlist/index/index/index/index.html"},
            {"type_name": "TOP榜单", "type_id": "/list/top.html"},
            {"type_name": "新歌榜", "type_id": "/list/new.html"},
            {"type_name": "电台", "type_id": "/radiolist/index.html"},
            {"type_name": "高清MV", "type_id": "/mvlist/oumei.html"},
            {"type_name": "专辑", "type_id": "/albumlist/index.html"},
            {"type_name": "歌单", "type_id": "/playtype/index.html"},
        ]
        filters = {
            "/singerlist/index/index/index/index.html": [
                {"key": "area", "name": "地区", "value": [{"n": n, "v": v} for n, v in [("全部", "index"), ("华语", "huayu"), ("欧美", "oumei"), ("韩国", "hanguo"), ("日本", "ribrn")]]},
                {"key": "sex", "name": "性别", "value": [{"n": n, "v": v} for n, v in [("全部", "index"), ("男", "male"), ("女", "girl"), ("组合", "band")]]},
                {"key": "genre", "name": "流派", "value": [{"n": n, "v": v} for n, v in [("全部", "index"), ("流行", "liuxing"), ("电子", "dianzi"), ("摇滚", "yaogun"), ("嘻哈", "xiha"), ("R&B", "rb"), ("民谣", "minyao"), ("爵士", "jueshi"), ("古典", "gudian")]]},
                {"key": "char", "name": "字母", "value": [{"n": n, "v": v} for n, v in [("全部", "index")] + [{"n": chr(i), "v": chr(i).lower()} for i in range(65, 91)]]}
            ],
            "/radiolist/index.html": [
                {"key": "id", "name": "分类", "value": [{"n": n, "v": v} for n, v in zip(["最新", "最热", "有声小说", "相声", "音乐", "情感", "国漫", "影视", "脱口秀", "历史", "儿童", "教育", "八卦", "推理", "头条"], ["index", "hot", "novel", "xiangyi", "music", "emotion", "game", "yingshi", "talkshow", "history", "children", "education", "gossip", "tuili", "headline"])]}
            ]
        }
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        url = tid
        if "/singerlist/" in tid:
            parts = tid.split('/')
            if len(parts) >= 6:
                parts[2] = extend.get("area", parts[2])
                parts[3] = extend.get("sex", parts[3])
                parts[4] = extend.get("genre", parts[4])
                char = extend.get("char", "index")
                url = "/".join(parts[:5]) + "/" + char + ".html"
        elif "id" in extend and extend["id"] not in ["index", "top"]:
            base = tid.rsplit('/', 1)[0]
            url = f"{base}/{extend['id']}.html"
        if pg > 1:
            sep = "/" if any(x in url for x in ["/singerlist/", "/radiolist/", "/mvlist/", "/playtype/", "/list/"]) else "_"
            url = re.sub(r'(_\d+|/\d+)?\.html$', f'{sep}{pg}.html', url)

        html = self._fetch(url)
        items = self._parse_list(html)
        return {"list": items, "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        url = f"/so/{quote(key)}/{pg}.html"
        html = self._fetch(url)
        items = self._parse_list(html)
        return {"list": items, "page": int(pg), "pagecount": 9999}

    def detailContent(self, ids):
        url = self._abs(ids[0])
        html = self._fetch(url)
        
        # 提取标题
        title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S) or re.search(r'<title>(.*?)</title>', html, re.S)
        title = self._clean(title_match.group(1) if title_match else "")
        
        # 提取封面
        pic_match = re.search(r'<img[^>]+src="([^"]+)"[^>]*>', html, re.S)
        pic = self._abs(pic_match.group(1)) if pic_match else ""
        
        vod = {
            "vod_id": url,
            "vod_name": title,
            "vod_pic": pic,
            "vod_play_from": "爱听音乐",
            "vod_content": ""
        }

        # 1. 尝试获取歌单/专辑/电台列表
        eps = self._get_episodes(html)
        if eps:
            vod["vod_play_from"] = "播放列表"
            vod["vod_play_url"] = "#".join(eps)
            return {"list": [vod]}

        # 2. 单曲或MV
        play_list = []
        
        # 单曲/电台
        mid = re.search(r'/(song|mp3|radio|radioplay)/([^/]+)\.html', url)
        if mid:
            song_id = mid.group(2)
            lrc_url = f"{self.host}/plug/down.php?ac=music&lk=lrc&id={song_id}"
            # 获取播放地址
            play_url = self._get_song_url(song_id)
            if play_url:
                play_list.append(f"播放${self._b64('0@@@@' + play_url + '|||' + lrc_url)}")
            else:
                # 如果API失败，尝试直接使用页面中的播放链接
                play_match = re.search(r'<a[^>]+href="([^"]+\.mp3)"', html, re.I)
                if play_match:
                    play_list.append(f"播放${self._b64('0@@@@' + self._abs(play_match.group(1)) + '|||' + lrc_url)}")
        
        # MV
        vid = re.search(r'/(video|mp4)/([^/]+)\.html', url)
        if vid:
            video_id = vid.group(2)
            for q in [1080, 720, 480]:
                u = self._api("/plug/down.php", {"ac": "vplay", "id": video_id, "q": q})
                if u and u.startswith("http"):
                    play_list.append(f"{q}p${self._b64('0@@@@'+u)}")
                    break
        
        # 如果没有获取到播放链接，尝试从页面直接提取
        if not play_list:
            play_match = re.search(r'<audio[^>]+src="([^"]+)"', html, re.I) or re.search(r'<source[^>]+src="([^"]+)"', html, re.I)
            if play_match:
                play_list.append(f"播放${self._b64('0@@@@' + self._abs(play_match.group(1)))}")
        
        vod["vod_play_url"] = "#".join(play_list) if play_list else f"解析失败${self._b64('1@@@@'+url)}"
        return {"list": [vod]}

    def _get_song_url(self, song_id):
        """获取歌曲播放地址"""
        try:
            # 方法1：通过API获取
            api_url = f"{self.host}/js/play.php"
            r = self.session.post(api_url, data={"id": song_id, "type": "music"}, 
                                  headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.host + "/"}, timeout=10)
            if r.status_code == 200:
                data = r.text.strip()
                if data.startswith("http"):
                    return data
                try:
                    import json
                    j = json.loads(data)
                    return j.get("url", "")
                except:
                    pass
        except:
            pass
        return ""

    def playerContent(self, flag, id, vipFlags):
        try:
            raw = self._b64(id, decode=True)
            if "@@@@@" in raw:
                raw = raw.split("@@@@@")[-1]
            elif "@@@@" in raw:
                raw = raw.split("@@@@")[-1]
            
            parts = raw.split("|||") if "|||" in raw else (raw, "")
            url = parts[0].strip()
            subt = parts[1].strip() if len(parts) > 1 else ""
            
            # 如果URL是相对路径，补全
            if url and not url.startswith("http"):
                url = self._abs(url)
            
            result = {
                "parse": 0,
                "playUrl": "",
                "url": url,
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.host + "/"
                }
            }
            
            # 添加歌词
            if subt:
                try:
                    r = self.session.get(subt, headers={"Referer": self.host + "/"}, timeout=5)
                    if r.status_code == 200:
                        lrc = self._filter_lrc(r.text)
                        if lrc:
                            result["lrc"] = lrc
                except:
                    pass
            
            return result
        except Exception as e:
            return {"parse": 0, "playUrl": "", "url": id, "header": {"User-Agent": self.headers["User-Agent"]}}

    def localProxy(self, param):
        url = unquote(param.get("url", ""))
        typ = param.get("type", "")
        if typ == "img":
            try:
                r = self.session.get(url, headers={"Referer": self.host + "/"}, timeout=10)
                return [200, "image/jpeg", r.content, {}]
            except:
                return [404, "text/plain", b"", {}]
        elif typ == "lrc":
            try:
                r = self.session.get(url, headers={"Referer": self.host + "/"}, timeout=10)
                if r.status_code == 200:
                    lrc = self._filter_lrc(r.text)
                    return [200, "text/plain", lrc.encode('utf-8'), {}]
            except:
                pass
            return [404, "text/plain", b"", {}]
        return None

    def _fetch(self, url, retry=3):
        for i in range(retry):
            try:
                r = self.session.get(self._abs(url), timeout=15)
                if r.status_code == 200:
                    return r.text
                if "验证" in r.text or "verify" in r.text.lower():
                    time.sleep(1)
                    continue
            except:
                time.sleep(0.5)
        return ""

    def _api(self, path, params=None, method="GET", data=None, headers=None):
        try:
            h = self.headers.copy()
            if headers:
                h.update(headers)
            if method.upper() == "POST":
                r = self.session.post(f"{self.host}{path}", params=params, data=data, headers=h, timeout=10)
            else:
                r = self.session.get(f"{self.host}{path}", params=params, headers=h, timeout=10)
            if r.status_code == 200:
                data = r.text.strip()
                if data.startswith("http"):
                    return data
                try:
                    import json
                    j = json.loads(data)
                    return j.get("url", "")
                except:
                    return data
        except:
            pass
        return ""

    def _parse_list(self, html):
        items = []
        # 匹配所有 li 标签
        for li in re.finditer(r'<li[^>]*>(.*?)</li>', html, re.S):
            li_html = li.group(1)
            a = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', li_html, re.S)
            if not a:
                continue
            href = self._abs(a.group(1))
            name = self._clean(a.group(2))
            # 如果名字为空，尝试从 span 或 title 获取
            if not name:
                span = re.search(r'<span[^>]*>(.*?)</span>', li_html, re.S)
                if span:
                    name = self._clean(span.group(1))
            if not name:
                title_match = re.search(r'title="([^"]+)"', li_html, re.S)
                if title_match:
                    name = self._clean(title_match.group(1))
            img = re.search(r'<img[^>]+src="([^"]+)"', li_html, re.S)
            pic = self._abs(img.group(1)) if img else ""
            if href and name:
                items.append({
                    "vod_id": href,
                    "vod_name": name,
                    "vod_pic": f"{self.getProxyUrl()}&url={quote(pic)}&type=img" if pic else "",
                })
        return items

    def _get_episodes(self, html):
        """提取歌单/专辑中的曲目列表"""
        eps = []
        for li in re.finditer(r'<li[^>]*>(.*?)</li>', html, re.S):
            li_html = li.group(1)
            a = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', li_html, re.S)
            if not a:
                continue
            href = a.group(1)
            # 只保留歌曲/电台链接
            if not re.search(r'/(song|mp3|radio|radioplay)/([^/]+)\.html', href):
                continue
            full_url = self._abs(href)
            title = self._clean(a.group(2))
            if not title:
                span = re.search(r'<span[^>]*>(.*?)</span>', li_html, re.S)
                if span:
                    title = self._clean(span.group(1))
            mid = re.search(r'/(song|mp3|radio|radioplay)/([^/]+)\.html', full_url)
            lrc_url = ""
            if mid:
                lrc_url = f"{self.host}/plug/down.php?ac=music&lk=lrc&id={mid.group(2)}"
            if title and full_url:
                eps.append(f"{title}${self._b64('0@@@@' + full_url + '|||' + lrc_url)}")
        return eps

    def _filter_lrc(self, lrc_text):
        if not lrc_text:
            return ""
        ads = ["欢迎来访", "本站", "广告", "QQ群", "www.", "http", ".com", ".cn", ".net", "音乐网", "提供", "下载"]
        lines = []
        for line in lrc_text.splitlines():
            if not line.strip():
                continue
            # 保留时间标签行，过滤广告
            if re.match(r'^\[\d{2}:\d{2}', line):
                is_ad = False
                for ad in ads:
                    if ad in line:
                        is_ad = True
                        break
                if not is_ad:
                    lines.append(line)
            elif re.match(r'^\[(ti|ar|al|by):', line, re.I):
                # 保留元数据标签
                lines.append(line)
        return "\n".join(lines)

    def _clean(self, text):
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'(爱玩音乐网|视频下载说明|视频下载地址|www\.2t58\.com|MP3免费下载|LRC歌词下载|全部歌曲|\[第\d+页\]|刷新|每日推荐|最新|热门|推荐|MV|高清|无损)', '', text, flags=re.I)
        return text.strip()

    def _abs(self, url):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.host + url
        return self.host + "/" + url

    def _b64(self, text, decode=False):
        if decode:
            try:
                return base64.b64decode(text.encode()).decode('utf-8')
            except:
                return text
        return base64.b64encode(text.encode()).decode('utf-8')