# -*- coding: utf-8 -*-
"""
奈飞工厂 NetflixGC UI9专用Python爬虫【修复版：有目录无数据】
适配UI9标准TVBox/Python爬虫规范，对齐爱影/Brovod模板架构
CMS: MacCMS DSN2模板
API: /index.php/ajax/data?mid=1&tid={tid}&page={pg}&limit={limit}
播放: player_aaaa JS变量(base64 + URL双重解码)
搜索: /vodsearch/-------------.html HTML解析
UI9后台配置JSON：
{
  "key": "netflixgc_py",
  "name": "奈飞工厂",
  "type": 3,
  "api": "./py/netflixgc.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 1
}
extend可自定义配置示例：{"host":"https://xxx.com","ua":"自定义UA"}
"""
import sys
import re
import json
import base64
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
        pass

# 全局常量移入类内，extend可覆盖
CATEGORIES = {
    "1": "电影",
    "2": "连续剧",
    "3": "漫剧",
    "23": "综艺",
    "24": "纪录片",
    "57": "直播"
}

class Spider(BaseSpider):
    # UI9默认扩展配置，后台extend JSON覆盖
    DEFAULT_EXT = {
        "host": "https://www.netflixgc.com",
        "ua": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    }

    def getName(self):
        return "奈飞工厂"

    def init(self, extend=""):
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
        self.headers = {
            "User-Agent": self.ua,
            "Referer": self.host
        }

    # ===================== UI9通用工具函数(对齐Brovod/爱影模板) =====================
    def _request_raw(self, url, headers=None, timeout=12, method="get"):
        """统一请求封装，优先requests，失败降级urllib"""
        final_header = dict(self.headers)
        if headers:
            final_header.update(headers)
        if not url.startswith("http"):
            url = urljoin(self.host, url)
        # requests优先
        if requests is not None and self.session:
            try:
                if method.lower() == "get":
                    resp = self.session.get(url, headers=final_header, timeout=timeout)
                else:
                    resp = self.session.post(url, headers=final_header, timeout=timeout)
                resp.raise_for_status()
                return resp
            except Exception as e:
                print(f"requests请求失败 {url} 错误: {str(e)}")
        # urllib降级兜底
        import urllib.request
        req = urllib.request.Request(url, headers=final_header)
        try:
            r = urllib.request.urlopen(req, timeout=timeout)
            body = r.read().decode("utf-8", errors="ignore")
            class UrllibResp:
                text = body
            return UrllibResp()
        except Exception as e:
            print(f"urllib降级请求失败 {url} 错误:{str(e)}")
            return None

    @staticmethod
    def _safe_json(text, default=None):
        """JSON解析容错"""
        try:
            return json.loads(text)
        except Exception:
            return default if default is not None else {}

    def _video_item(self, item):
        """UI9标准化列表字段"""
        if not isinstance(item, dict):
            return {}
        return {
            "vod_id": str(item.get("vod_id", "")),
            "vod_name": item.get("vod_name", ""),
            "vod_pic": self._fix_pic(item.get("vod_pic", "")),
            "vod_remarks": item.get("vod_remarks", "")
        }

    def isVideoFormat(self, url):
        """UI9视频链接识别规则"""
        return bool(re.search(r"(?i)\.(m3u8|mp4|mkv|ts|flv|avi|mov)(?:\?|$)", str(url or "")))

    def manualVideoCheck(self):
        return False

    # ===================== 站点专属工具 =====================
    def _fix_pic(self, pic):
        """修复百度转链图片URL"""
        if not pic:
            return ""
        if pic.startswith("https://image.baidu.com/search/down?url="):
            m = re.search(r"url=(https?://[^&]+)", pic)
            if m:
                return m.group(1)
        return pic

    @staticmethod
    def _extract_player(html):
        """提取player_aaaa JSON对象"""
        idx = html.find("var player_aaaa")
        if idx < 0:
            return None
        start = html.find("{", idx)
        depth = 0
        end = start
        for i, c in enumerate(html[start:]):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = start + i + 1
                    break
        try:
            return json.loads(html[start:end])
        except Exception:
            return None

    @staticmethod
    def _decode_url(url_val):
        """base64 + 双重url解码播放地址"""
        if not url_val:
            return ""
        try:
            decoded = base64.b64decode(url_val).decode("utf-8")
            decoded = unquote(decoded)
            decoded = unquote(decoded)
            return decoded
        except Exception:
            return url_val

    # ===================== UI9标准入口方法 =====================
    def homeContent(self, filter=False):
        res = {"class": []}
        for tid, tname in CATEGORIES.items():
            res["class"].append({"type_id": tid, "type_name": tname})
        if filter:
            res["filters"] = {}
            for tid in CATEGORIES:
                res["filters"][tid] = [
                    {"key": "area", "name": "地区", "value": [
                        {"n": "全部", "v": ""}, {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "美国", "v": "美国"}, {"n": "日本", "v": "日本"},
                        {"n": "韩国", "v": "韩国"}, {"n": "英国", "v": "英国"},
                    ]},
                    {"key": "year", "name": "年份", "value": [
                        {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"},
                        {"n": "2025", "v": "2025"}, {"n": "2024", "v": "2024"},
                        {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                    ]},
                    {"key": "by", "name": "排序", "value": [
                        {"n": "时间", "v": "time"}, {"n": "人气", "v": "hits"},
                        {"n": "评分", "v": "score"},
                    ]},
                ]
        return res

    def homeVideoContent(self):
        try:
            url = f"{self.host}/index.php/ajax/data?mid=1&page=1&limit=20"
            resp = self._request_raw(url, headers={"X-Requested-With":"XMLHttpRequest"})
            if not resp:
                print("homeVideoContent 请求返回None")
                return {"list": []}
            data = self._safe_json(resp.text)
            raw = data.get("list", [])
            if not raw:
                print("homeVideoContent接口list为空")
            return {"list": [self._video_item(i) for i in raw]}
        except Exception as e:
            print(f"homeVideoContent异常:{e}")
            return {"list": []}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        pn = 1
        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pass
        cat = str(tid)
        if cat not in CATEGORIES:
            return {"page": pn, "pagecount": 1, "limit": 20, "total": 0, "list": []}
        try:
            api_url = f"{self.host}/index.php/ajax/data?mid=1&tid={cat}&page={pn}&limit=20"
            resp = self._request_raw(api_url, headers={"X-Requested-With":"XMLHttpRequest"})
            if not resp:
                return {"page": pn, "pagecount": 1, "limit": 20, "total": 0, "list": []}
            data = self._safe_json(resp.text)
            raw_list = data.get("list", [])
            item_list = [self._video_item(i) for i in raw_list]
            total = data.get("total", 0)
            pagecount = max(1, (total + 19) // 20)
            return {
                "page": pn,
                "pagecount": pagecount,
                "limit": 20,
                "total": total,
                "list": item_list
            }
        except Exception as e:
            print(f"categoryContent异常:{e}")
            return {"page": pn, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    def detailContent(self, ids):
        if isinstance(ids, list):
            vid = ids[0] if ids else ""
        else:
            vid = str(ids) if ids else ""
        if not vid:
            return {"list": []}
        vod = {
            "vod_id": vid,
            "vod_name": "",
            "vod_pic": "",
            "type_name": "",
            "vod_remarks": "",
            "vod_content": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_year": "",
            "vod_area": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }
        # 不再依赖大接口500条，直接访问详情页HTML获取基础信息
        detail_url = f"{self.host}/voddetail/{vid}.html"
        resp_detail = self._request_raw(detail_url)
        if resp_detail:
            html = resp_detail.text
            # 解析名称封面
            title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            if title_match:
                vod["vod_name"] = title_match.group(1).strip()
            pic_match = re.search(r'data‑original="([^"]+)"', html)
            if pic_match:
                vod["vod_pic"] = self._fix_pic(pic_match.group(1))
        # 多线路抓取播放信息
        play_froms = []
        play_urls = []
        try:
            for pf in range(1, 10):
                play_page_url = f"{self.host}/vodplay/{vid}-{pf}-1.html"
                rp = self._request_raw(play_page_url)
                if not rp:
                    continue
                pa = self._extract_player(rp.text)
                if pa:
                    from_val = pa.get("from", "")
                    url_decoded = self._decode_url(pa.get("url", ""))
                    if from_val and url_decoded and url_decoded.startswith("http"):
                        play_froms.append(from_val)
                        # UI9格式:集数$播放页地址
                        play_urls.append(f"第1集${play_page_url}")
        except Exception as e:
            print(f"detail播放线路异常:{e}")
        if play_froms:
            vod["vod_play_from"] = "$$$".join(play_froms)
            vod["vod_play_url"] = "$$$".join(play_urls)
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick=False, pg="1"):
        pn = 1
        try:
            pn = int(str(pg))
        except Exception:
            pass
        result = {"list": [], "page": pn}
        try:
            search_url = f"{self.host}/vodsearch/-------------.html?wd={quote(key)}"
            resp = self._request_raw(search_url)
            if not resp:
                return result
            html = resp.text
            items = re.findall(
                r'<a[^>]*href=["\'](/voddetail/(\d+)[^"\']*)["\'][^>]*>.*?<h3[^>]*>([^<]+)</h3>',
                html, re.DOTALL
            )
            matched = []
            for _, vid, name in items:
                matched.append({
                    "vod_id": str(vid),
                    "vod_name": name.strip(),
                    "vod_pic": "",
                    "vod_remarks": "",
                })
            result["list"] = [self._video_item(i) for i in matched[:50]]
        except Exception as e:
            print(f"search异常:{e}")
        return result

    def playerContent(self, flag, id, vipFlags=None):
        res = {"parse": 0, "jx": 0, "url": "", "header": {"User-Agent": self.ua}}
        try:
            id_str = str(id) if id else str(flag)
            if "$" in id_str:
                id_str = id_str.rsplit("$", 1)[-1]
            m = re.match(r"(\d+)-(\d+)-(\d+)", id_str)
            if m:
                vid = m.group(1)
                pf = m.group(2)
                play_url = f"{self.host}/vodplay/{vid}-{pf}-1.html"
                rp = self._request_raw(play_url)
                if rp:
                    pa = self._extract_player(rp.text)
                    if pa:
                        url_decoded = self._decode_url(pa.get("url", ""))
                        if url_decoded and url_decoded.startswith("http"):
                            res["url"] = url_decoded
                            return res
            elif id_str.startswith("http"):
                res["url"] = id_str
                return res
        except Exception as e:
            print(f"playerContent异常:{e}")
        return res

    def localProxy(self, param):
        # UI9标准返回格式：[http状态码, content‑type, 文本内容]
        return [404, "text/plain", "Not Found"]

if __name__ == '__main__':
    sp = Spider()
    sp.init()
    # 本地调试测试
    # print(sp.homeVideoContent())
