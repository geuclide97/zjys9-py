# -*- coding: utf-8 -*-
"""
蛋蛋奇 dandanqi.cc UI9 Python Spider
依赖：
    requests
    beautifulsoup4
配置示例：
{
  "key": "蛋蛋奇_py",
  "name": "🥚蛋蛋奇",
  "type": 3,
  "api": "./py/蛋蛋奇.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 0
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
        "host": "https://www.dandanqi.cc",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    }
    CATEGORIES = [
        ("首页", "home"), ("电影", "dianying"), ("剧集", "juji"),
        ("综艺", "zongyi"), ("动漫", "dongman"),
        ("今日更新", "new"), ("热榜", "hot")
    ]

    def getName(self):
        return "蛋蛋奇"

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

        self.host = str(self.ext.get("host", "https://www.dandanqi.cc")).rstrip("/")
        self.ua = str(self.ext.get("ua"))
        self.timeout = (6, 20)
        self.session = requests.Session() if requests else None
        if self.session:
            self.session.headers.update({
                "User-Agent": self.ua,
                "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
                "Referer": self.host + "/"
            })
            self.session.cookies.set('accessAuth', 'ok', domain='www.dandanqi.cc', path='/')

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
        text = self._response_text(resp)
        if 'const PASSWORD' in text or '页面访问验证' in text:
            self.session.cookies.set('accessAuth', 'ok', domain='www.dandanqi.cc', path='/')
            resp = self.session.get(url, timeout=self.timeout, verify=False)
            text = self._response_text(resp)
        return text

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

    def _image(self, img):
        if not img:
            return ''
        url = img.get('data-original') or img.get('data-src') or img.get('src') or ''
        return urljoin(self.host + '/', url)

    def _cards(self, text):
        soup = self._soup(text)
        result, seen = [], set()
        for a in soup.select('a.module-poster-item[href*="/detail/"], a.module-card-item-poster[href*="/detail/"]'):
            href = a.get('href', '')
            match = re.search(r'/detail/(\d+)\.html', href)
            vid = match.group(1) if match else href
            if not vid or vid in seen:
                continue
            seen.add(vid)
            img = a.select_one('img')
            card = a.find_parent(class_='module-card-item')
            name = (a.get('title') or (img.get('alt') if img else '') or
                    self._text(card.select_one('.module-card-item-title') if card else None) or
                    self._text(a.select_one('.module-poster-item-title')) or self._text(a))
            if not name:
                continue
            result.append({
                'vod_id': href,
                'vod_name': self._clean(name),
                'vod_pic': self._image(img),
                'vod_remarks': self._text((card or a).select_one('.module-item-note'))
            })
        return result

    @staticmethod
    def _decode2(encoded):
        raw = base64.b64decode(encoded).decode('utf-8')
        alphabet = 'PXhw7UT1B0a9kQDKZsjIASmOezxYG4CHo5Jyfg2b8FLpEvRr3WtVnlqMidu6cN'
        out = []
        for pos in range(1, len(raw), 3):
            char = raw[pos]
            idx = alphabet.find(char)
            out.append(char if idx < 0 else alphabet[(idx + 59) % 62])
        return ''.join(out)

    @staticmethod
    def _decode1(encoded):
        key = hashlib.md5(b'test').hexdigest().encode('ascii')
        first = base64.b64decode(encoded)
        mixed = bytes(value ^ key[i % len(key)] for i, value in enumerate(first))
        custom = base64.b64decode(mixed).decode('utf-8')
        parts = custom.split('/')
        if len(parts) < 3:
            return ''
        source_alpha = json.loads(base64.b64decode(parts[1]).decode('utf-8'))
        target_alpha = json.loads(base64.b64decode(parts[0]).decode('utf-8'))
        payload = base64.b64decode('/'.join(parts[2:])).decode('utf-8')
        result = []
        for char in payload:
            if char.isascii() and char.isalpha() and char in target_alpha:
                try:
                    result.append(target_alpha[source_alpha.index(char)])
                except (ValueError, IndexError):
                    result.append(char)
            else:
                result.append(char)
        return ''.join(result)

    # -------------------- UI9 Spider 方法 --------------------
    def homeContent(self, filter):
        try:
            classes = [{'type_name': n, 'type_id': i} for n, i in self.CATEGORIES]
            return {"class": classes, "filters": {}}
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
            if tid == 'home':
                path = '/' if page == 1 else '/page/{0}.html'.format(page)
            elif tid in ('new', 'hot'):
                if page > 1:
                    return {'list': [], 'page': page, 'pagecount': page, 'limit': 0, 'total': 0}
                path = '/label/{0}.html'.format(tid)
            else:
                path = '/show/{0}--------{1}---.html'.format(tid, page)
            videos = self._cards(self._request_raw(path))
            pagecount = page + 1 if videos and tid not in ('new', 'hot') else page
            return {
                "list": videos,
                "page": page,
                "pagecount": pagecount,
                "limit": len(videos),
                "total": pagecount * max(1, len(videos))
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
            path = str(vod_id)
            html_text = self._request_raw(path)
            soup = self._soup(html_text)

            name = self._text(soup.select_one('.module-info-heading h1')) or '蛋蛋奇'
            poster = self._image(soup.select_one('.module-info-poster img'))
            intro = self._text(soup.select_one('.module-info-introduction-content'))
            tags = [self._text(x) for x in soup.select('.module-info-tag-link') if self._text(x)]
            info = {}
            for item in soup.select('.module-info-item'):
                k = self._text(item.select_one('.module-info-item-title')).rstrip('：:')
                v = self._text(item.select_one('.module-info-item-content'))
                if k and v:
                    info[k] = v

            line_names = []
            for tab in soup.select('#y-playList .module-tab-item'):
                line_names.append(tab.get('data-dropdown-value') or self._text(tab))

            play_from, play_urls = [], []
            for idx, block in enumerate(soup.select('.module-play-list')):
                eps = []
                for a in block.select('a.module-play-list-link[href*="/play/"]'):
                    href = a.get('href', '')
                    title = self._text(a) or str(len(eps) + 1)
                    if href:
                        eps.append(f"{self._clean(title)}${href}")
                if eps:
                    ln = line_names[idx] if idx < len(line_names) else f"线路{idx+1}"
                    play_from.append(self._clean(ln))
                    play_urls.append('#'.join(eps))

            vod = {
                "vod_id": vod_id,
                "vod_name": name,
                "vod_pic": poster,
                "type_name": " / ".join(tags),
                "vod_year": info.get("年份", ""),
                "vod_area": info.get("地区", ""),
                "vod_remarks": info.get("更新", "") or info.get("备注", ""),
                "vod_actor": info.get("主演", ""),
                "vod_director": info.get("导演", ""),
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
            path = '/search/{0}----------{1}---.html'.format(str(key), page)
            lst = self._cards(self._request_raw(path))
            return {"list": lst, "page": page}
        except Exception as exc:
            return {"list": [], "page": int(pg or 1), "error": str(exc)}

    def playerContent(self, flag, pid, vipFlags):
        try:
            path = str(pid)
            header = {"User-Agent": self.ua, "Referer": self.host + "/"}
            text = self._request_raw(path)
            match = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*</script>', text, re.S)
            if not match:
                match = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\})\s*;', text, re.S)
            if not match:
                return {"parse": 1, "url": urljoin(self.host, path), "header": header}

            data = json.loads(match.group(1))
            token = str(data.get('url') or '')
            enc = self._int(data.get('encrypt'), 0)
            if enc == 1:
                token = unquote(token)
            elif enc == 2:
                token = unquote(base64.b64decode(token).decode('utf-8'))

            parser = self.host + '/ddplay/index.php?vid=' + quote(token, safe='')
            resp = self.session.post(
                self.host + '/ddplay/api.php',
                data={"vid": token},
                headers={
                    "Referer": parser,
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": self.ua
                },
                timeout=self.timeout,
                verify=False
            )
            payload = resp.json()
            if self._int(payload.get("code"), 0) == 200:
                item = payload.get("data") or {}
                mode = self._int(item.get("urlmode"), 0)
                encoded = str(item.get("url") or "")
                direct = ""
                if mode == 2:
                    direct = self._decode2(encoded)
                elif mode == 1:
                    direct = self._decode1(encoded)
                else:
                    direct = encoded
                if direct.startswith(("http://", "https://")):
                    return {"parse": 0, "url": direct, "header": header}
            return {"parse": 1, "url": parser, "header": header}
        except Exception as exc:
            return {
                "parse": 1,
                "url": str(pid or ""),
                "error": str(exc)
            }

    def localProxy(self, param):
        return [404, "text/plain", "Not Found"]
