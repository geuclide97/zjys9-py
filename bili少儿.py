# -*- coding: utf-8 -*-
"""
B站少儿教育 UI9专用Python爬虫
UI9模板架构参考枫叶影院，支持extend后台改UA
依赖：requests
UI9配置JSON：
{
  "key": "bili_edu_py",
  "name": "教育儿童",
  "type": 3,
  "api": "./py/bili教育.py",
  "searchable": 1,
  "quickSearch": 1,
  "filterable": 1
}
"""
import re
import urllib.parse
import json
# 依赖容错降级
try:
    import requests
except Exception:
    requests = None
# UI9父类兜底，无base.spider不报错
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass
class Spider(BaseSpider):
    # UI9默认扩展配置，后台extend可JSON覆盖
    DEFAULT_EXT = {
        "ua_mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    }
    CLASS_LIST = [
        {"type_id": "幼儿英语", "type_name": "幼儿英语"},
        {"type_id": "少儿思维", "type_name": "少儿思维"},
        {"type_id": "少儿口才", "type_name": "少儿口才"},
        {"type_id": "十万个为什么", "type_name": "十万个为什么"},
        {"type_id": "DK百科", "type_name": "DK百科"},
        {"type_id": "小灯塔", "type_name": "小灯塔"},
        {"type_id": "成语故事", "type_name": "成语故事"},
        {"type_id": "安全教育", "type_name": "安全教育"},
        {"type_id": "少儿编程", "type_name": "少儿编程"},
        {"type_id": "古诗", "type_name": "古诗"},
        {"type_id": "声律启蒙", "type_name": "声律启蒙"},
        {"type_id": "笠翁对韵", "type_name": "笠翁对韵"},
        {"type_id": "三字经", "type_name": "三字经"},
        {"type_id": "弟子规", "type_name": "弟子规"},
        {"type_id": "百家姓", "type_name": "百家姓"},
        {"type_id": "儿童性教育", "type_name": "儿童性教育"},
        {"type_id": "小灯塔百科", "type_name": "10天玩转世界top10博物馆"},
        {"type_id": "小灯塔科学", "type_name": "小灯塔奇趣科学实验室"},
        {"type_id": "小灯塔地理", "type_name": "小灯塔自然地理大巡游"},
        {"type_id": "小灯塔国学", "type_name": "神奇的汉字故事 全20集"},
        {"type_id": "小灯塔人文", "type_name": "穿越唐诗大世界"},
        {"type_id": "儿童拼音", "type_name": "拼音启蒙动画课"},
        {"type_id": "儿童识字", "type_name": "悟空识字"},
        {"type_id": "儿童英语", "type_name": "洪恩幼儿英语"},
        {"type_id": "儿童硬笔", "type_name": "叫叫硬笔书法"},
        {"type_id": "儿童思维", "type_name": "摩比爱数学"},
        {"type_id": "儿童口才", "type_name": "少儿口才第一课：自我介绍"},
        {"type_id": "儿童编程", "type_name": "新版少儿编程scratch3.0"},
        {"type_id": "儿童武术", "type_name": "少儿武术：五步拳"},
        {"type_id": "兴趣培养", "type_name": "太极拳"},
        {"type_id": "益智动画", "type_name": "宝宝巴士动画合集"},
        {"type_id": "幼小衔接", "type_name": "幼儿拼音全套学习课程"},
    ]
    API_BASE = "https://api.bilibili.com"
    def getName(self):
        return "B站少儿教育"
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
        self.session = requests.Session() if requests else None
        # 请求头
        self.headers = {
            "User-Agent": self.ext["ua_mobile"],
            "Referer": "https://m.bilibili.com",
            "Accept": "application/json",
        }
        if self.session:
            self.session.headers.update(self.headers)
    # ===================== UI9通用工具（完全对齐爱影/枫叶模板） =====================
    def _ensure_runtime(self):
        if requests is None:
            raise RuntimeError("缺失requests依赖")
    def _request_raw(self, url, headers=None, params=None, timeout=12):
        self._ensure_runtime()
        full_header = dict(self.headers)
        if headers:
            full_header.update(headers)
        try:
            resp = self.session.get(url, headers=full_header, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"请求失败 {url} : {e}")
            return None
    def _fetch_json(self, url, params=None):
        resp = self._request_raw(url, params=params)
        if not resp:
            return {}
        try:
            return resp.json()
        except Exception:
            return {}
    @staticmethod
    def _safe_json(text, default=None):
        try:
            return json.loads(text)
        except Exception:
            return default if default is not None else {}
    def _video_item(self, item):
        if not isinstance(item, dict):
            return {}
        return {
            "vod_id": item.get("vod_id", ""),
            "vod_name": item.get("vod_name", ""),
            "vod_pic": item.get("vod_pic", ""),
            "vod_remarks": item.get("vod_remarks", "")
        }
    @staticmethod
    def _fix_pic(img_url):
        if not img_url:
            return ""
        if img_url.startswith("//"):
            return f"https:{img_url}"
        return img_url.replace("&amp;", "&")
    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.(m3u8|mp4|mkv|ts|flv)(\?|$)", str(url)))
    def manualVideoCheck(self):
        return False
    def _parse_video_result(self, result):
        """从 v2 搜索接口的 result 列表中提取视频数据"""
        videos = []
        for item in result:
            if isinstance(item, dict) and item.get("result_type") == "video":
                items = item.get("data", [])
                if isinstance(items, list):
                    for v in items:
                        bvid = v.get("bvid", "")
                        if bvid:
                            title = re.sub(r'<[^>]+>', '', v.get("title", ""))
                            pic = v.get("pic", "")
                            pic = self._fix_pic(pic)
                            dur = v.get("duration", "")
                            pubdate = v.get("pubdate", 0)
                            year = str(pubdate)[:4] if pubdate else ""
                            videos.append({
                                "vod_id": bvid,
                                "vod_name": title,
                                "vod_pic": pic or "",
                                "vod_actor": v.get("author", ""),
                                "vod_remarks": dur,
                                "vod_year": year,
                            })
        return videos
    # ===================== UI9标准入口方法 =====================
    def homeContent(self, filter):
        return {"class": self.CLASS_LIST, "filters": {}}
    def homeVideoContent(self):
        result = {"list": []}
        try:
            params = {"keyword": "小灯塔", "pn": 1}
            api_url = self.API_BASE + "/x/web-interface/search/all/v2"
            data = self._fetch_json(api_url, params=params)
            if data.get("code") == 0:
                result_list = data.get("data", {}).get("result", [])
                videos = self._parse_video_result(result_list)
                video_items = [self._video_item(i) for i in videos[:20]]
                result["list"] = video_items
        except Exception as e:
            print(f"[B站少儿教育] 首页推荐异常: {e}")
        return result
    def categoryContent(self, tid, pg, filter, extend):
        result = {"list": [], "page": int(pg), "pagecount": 999, "limit": 20, "total": 0}
        try:
            params = {"keyword": tid, "order": "totalrank", "pn": int(pg)}
            api_url = self.API_BASE + "/x/web-interface/search/all/v2"
            data = self._fetch_json(api_url, params=params)
            if data.get("code") == 0:
                result_list = data.get("data", {}).get("result", [])
                videos = self._parse_video_result(result_list)
                video_items = [self._video_item(i) for i in videos]
                result["list"] = video_items
                result["total"] = len(videos)
        except Exception as e:
            print(f"[B站少儿教育] 分类加载异常: {e}")
        return result
    def detailContent(self, ids):
        result = {"list": []}
        try:
            bvid = str(ids[0]).strip()
            if not bvid:
                return result
            api_url = self.API_BASE + "/x/web-interface/view"
            data = self._fetch_json(api_url, params={"bvid": bvid})
            if data.get("code") != 0:
                return result
            v = data["data"]
            episodes = []
            for i, p in enumerate(v.get("pages", [])):
                cid = int(p.get("cid", 0))
                name = p.get("part", "").strip() or f"第{i+1}集"
                dur = p.get("duration", "0")
                episodes.append(name + "$" + f"{bvid}@{cid}")
            pubdate = v.get("pubdate", 0)
            year = str(pubdate)[:4] if pubdate else ""
            vod = {
                "vod_id": bvid,
                "vod_name": v.get("title", ""),
                "vod_pic": self._fix_pic(v.get("pic", "")),
                "vod_year": year,
                "vod_area": "",
                "vod_actor": v.get("owner", {}).get("name", ""),
                "vod_director": "",
                "vod_type": v.get("typeName", ""),
                "vod_remarks": "",
                "vod_content": (v.get("desc", "") or "")[:200],
                "vod_play_from": "B站",
                "vod_play_url": "#".join(episodes) if episodes else "",
            }
            result["list"].append(vod)
        except Exception as e:
            print(f"[B站少儿教育] 详情加载异常: {e}")
        return result
    # UI9规范：双搜索函数
    def searchContent(self, key, quick, pg=1):
        return self.searchContentPage(key, quick, pg)
    def searchContentPage(self, key, quick, pg="1"):
        return self.categoryContent(key, pg, {}, {})
    def playerContent(self, flag, id, vipFlags):
        result = {"parse": 0, "url": "", "header": {}}
        try:
            # 解析 bvid@cid
            m = re.search(r'(.+)@(\d+)', str(id))
            if not m:
                return result
            bvid = m.group(1)
            cid = int(m.group(2))
            params = {"bvid": bvid, "cid": cid, "qn": 80, "fnval": 16|1|2048, "fourk": 1}
            api_url = self.API_BASE + "/x/player/playurl"
            data = self._fetch_json(api_url, params=params)
            if data.get("code") == 0:
                play_data = data["data"]
                if play_data.get("durl"):
                    result["url"] = play_data["durl"][0].get("url", "")
                elif play_data.get("dash", {}).get("video"):
                    videos = sorted(play_data["dash"]["video"], key=lambda x: int(x.get("bandwidth", 0)), reverse=True)
                    result["url"] = videos[0].get("baseUrl", videos[0].get("base_url", ""))
            # 修复：header直接字典，不再json.dumps
            result["header"] = self.headers
        except Exception as e:
            print(f"[B站少儿教育] 播放解析异常: {e}")
        return result
    def localProxy(self, param=''):
        return [404, "text/plain", "NotFound"]
if __name__ == '__main__':
    sp = Spider()
    sp.init()
