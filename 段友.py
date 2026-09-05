#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
段友影视 (snmwg.com) 爬虫 - TVBox/影视仓 Spider 插件
适配 UI6 壳子，添加必需的空方法
"""

import re
import json
import logging
import urllib.parse
import os
import sys
import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from base.spider import Spider as BaseSpider
except ImportError:
    BaseSpider = object

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Spider(BaseSpider):
    """段友影视爬虫"""

    BASE_URL = "https://www.snmwg.com"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12; SM-S908U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    CATEGORY_MAP = {
        "1": {"name": "电影", "url": "/vodtype/dianying.html"},
        "2": {"name": "电视剧", "url": "/vodtype/dianshiju.html"},
        "3": {"name": "综艺", "url": "/vodtype/zongyi.html"},
        "4": {"name": "动漫", "url": "/vodtype/dongman.html"},
        "5": {"name": "短剧", "url": "/vodtype/duanju.html"},
        "6": {"name": "影视解说", "url": "/vodtype/yingshijieshuo.html"},
    }

    TYPE_MAP = {
        "dongzuo": "动作", "xiju": "喜剧", "aiqing": "爱情", "kexuan": "科幻",
        "kongbu": "恐怖", "juqing": "剧情", "zhanzheng": "战争", "donghua": "动画",
        "jilu": "记录", "qita": "其他",
    }
    AREA_MAP = {
        "dalu": "大陆", "xianggang": "香港", "taiwan": "台湾", "meiguo": "美国",
        "riben": "日本", "hanguo": "韩国", "yingguo": "英国", "faguo": "法国",
        "deguo": "德国", "eluosi": "俄罗斯", "qita": "其他",
    }
    LANG_MAP = {
        "guoyu": "国语", "yingyu": "英语", "riyu": "日语", "fayu": "法语",
        "hanyu": "韩语", "qita": "其他",
    }

    def __init__(self):
        try:
            super().__init__()
        except Exception:
            pass
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update(self.HEADERS)

    def init(self, extend):
        pass

    def getName(self):
        return "段友影视"

    # ========== UI6 必需的空方法 ==========
    def localProxy(self, params):
        return {}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ========== 以下是功能方法 ==========

    def _parse_ext(self, ext):
        if not ext:
            return {}
        if isinstance(ext, dict):
            return ext
        if isinstance(ext, str):
            try:
                return json.loads(ext)
            except Exception:
                return {}
        return {}

    def _fetch(self, url):
        try:
            # 使用 self.fetch（TVBox 提供的方法）
            rsp = self.fetch(url, headers=self.HEADERS)
            return rsp.text if rsp else ''
        except:
            # 降级使用 requests
            try:
                resp = self.session.get(url, timeout=30)
                resp.encoding = "utf-8"
                return resp.text
            except Exception as e:
                logger.error(f"请求失败 {url}: {e}")
                return ''

    def homeContent(self, filter=False):
        try:
            html = self._fetch(self.BASE_URL + "/")
            if not html:
                return {}
            classes = [{"type_id": cid, "type_name": info["name"]}
                       for cid, info in self.CATEGORY_MAP.items()]
            home_list = self._parse_video_list(html, is_home=True)
            return {"class": classes, "filters": self._get_filters(), "list": home_list}
        except Exception as e:
            logger.error(f"获取首页失败: {e}")
            return {}

    def homeVideoContent(self):
        return {"list": self.homeContent().get("list", [])}

    def _parse_video_list(self, html, is_home=False):
        videos = []
        seen_ids = set()
        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('a', class_=re.compile(r'vodlist_thumb'))
        for item in items:
            href = item.get('href', '')
            vid_match = re.search(r'/voddetail/(\d+)\.html', href)
            if not vid_match:
                continue
            vid_id = vid_match.group(1)
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)
            title = item.get('title', '')
            poster = item.get('data-original', '') or item.get('src', '')
            remark_tag = item.find(class_=re.compile(r'pic_text'))
            remarks = remark_tag.get_text(strip=True) if remark_tag else ''
            if title:
                videos.append({"vod_id": vid_id, "vod_name": title, "vod_pic": poster, "vod_remarks": remarks})
        return videos[:36]

    def _get_filters(self):
        filters = {}
        for cate_id in self.CATEGORY_MAP:
            filters[cate_id] = [
                {"key": "type", "name": "类型", "value": [
                    {"n": "全部", "v": ""}, {"n": "动作", "v": "dongzuo"}, {"n": "喜剧", "v": "xiju"},
                    {"n": "爱情", "v": "aiqing"}, {"n": "科幻", "v": "kexuan"}, {"n": "恐怖", "v": "kongbu"},
                    {"n": "剧情", "v": "juqing"}, {"n": "战争", "v": "zhanzheng"}, {"n": "动画", "v": "donghua"},
                    {"n": "记录", "v": "jilu"}, {"n": "其他", "v": "qita"},
                ]},
                {"key": "lang", "name": "语言", "value": [
                    {"n": "全部", "v": ""}, {"n": "国语", "v": "guoyu"}, {"n": "英语", "v": "yingyu"},
                    {"n": "日语", "v": "riyu"}, {"n": "法语", "v": "fayu"}, {"n": "韩语", "v": "hanyu"},
                    {"n": "其他", "v": "qita"},
                ]},
                {"key": "year", "name": "年份", "value": [
                    {"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                    {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"},
                    {"n": "更早", "v": "2015"},
                ]},
                {"key": "letter", "name": "字母", "value": [
                    {"n": "全部", "v": ""}, *[{"n": L, "v": L} for L in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
                    {"n": "其他", "v": "0"},
                ]},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""}, {"n": "大陆", "v": "dalu"}, {"n": "香港", "v": "xianggang"},
                    {"n": "台湾", "v": "taiwan"}, {"n": "美国", "v": "meiguo"}, {"n": "日本", "v": "riben"},
                    {"n": "韩国", "v": "hanguo"}, {"n": "英国", "v": "yingguo"}, {"n": "法国", "v": "faguo"},
                    {"n": "德国", "v": "deguo"}, {"n": "俄罗斯", "v": "eluosi"}, {"n": "其他", "v": "qita"},
                ]},
            ]
        return filters

    def categoryContent(self, tid, pg, filter, ext):
        try:
            page = int(pg) if pg else 1
            type_id = str(tid)
            cate_info = self.CATEGORY_MAP.get(type_id)
            if not cate_info:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            ext_dict = self._parse_ext(ext)
            type_filter = ext_dict.get('type', '')
            lang_filter = ext_dict.get('lang', '')
            year_filter = ext_dict.get('year', '')
            letter_filter = ext_dict.get('letter', '')
            area_filter = ext_dict.get('area', '')
            if type_filter and type_filter in self.TYPE_MAP:
                type_filter = self.TYPE_MAP[type_filter]
            if area_filter and area_filter in self.AREA_MAP:
                area_filter = self.AREA_MAP[area_filter]
            if lang_filter and lang_filter in self.LANG_MAP:
                lang_filter = self.LANG_MAP[lang_filter]
            has_filter = any([type_filter, lang_filter, year_filter, letter_filter, area_filter])
            if has_filter:
                type_name = cate_info["url"].replace('/vodtype/', '').replace('.html', '')
                if year_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}-----------{year_filter}.html"
                elif type_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}---{urllib.parse.quote(type_filter)}--------.html"
                elif area_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}-{urllib.parse.quote(area_filter)}----------.html"
                elif lang_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}----{urllib.parse.quote(lang_filter)}-------.html"
                elif letter_filter:
                    url = f"{self.BASE_URL}/vodshow/{type_name}------------{letter_filter}.html"
                else:
                    url = f"{self.BASE_URL}/vodshow/{type_name}-------------.html"
            else:
                url = self.BASE_URL + cate_info["url"]
            if page > 1:
                url = url.replace('.html', f'-{page}.html')
            html = self._fetch(url)
            if not html:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            videos = self._parse_video_list(html, is_home=False)
            pagecount = self._parse_total_pages(html)
            return {"list": videos, "page": page, "pagecount": pagecount, "limit": 20, "total": len(videos) * pagecount}
        except Exception as e:
            logger.error(f"获取分类内容失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}

    def _parse_total_pages(self, html):
        for pattern in [r'共有(\d+)页', r'共\s*(\d+)\s*页']:
            match = re.search(pattern, html)
            if match:
                return int(match.group(1))
        return 100

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            html = self._fetch(f"{self.BASE_URL}/voddetail/{vod_id}.html")
            if not html:
                return {"list": []}
            soup = BeautifulSoup(html, 'html.parser')
            title = ''
            title_tag = soup.find('h2', class_='title') or soup.find('h1')
            if title_tag:
                title = title_tag.get_text(strip=True)
            poster = ''
            thumb_a = soup.find('a', class_=re.compile(r'vodlist_thumb|thumb'))
            if thumb_a:
                poster = thumb_a.get('data-original', '') or thumb_a.get('href', '')
            if not poster:
                for img in soup.find_all('img'):
                    src = img.get('src', '') or img.get('data-original', '')
                    if 'upload/vod' in src:
                        poster = src
                        break
            year = area = type_name = lang = actor = director = content = ''
            hot_banner = soup.find(class_='hot_banner')
            if hot_banner:
                banner_text = hot_banner.get_text(strip=True)
                year_match = re.search(r'年份：(\d{4})', banner_text)
                if year_match:
                    year = year_match.group(1)
                area_match = re.search(r'地区：([^类型]+)', banner_text)
                if area_match:
                    area = area_match.group(1).strip()
                type_match = re.search(r'类型：([^状态]+)', banner_text)
                if type_match:
                    type_name = type_match.group(1).strip()
            detail_list = soup.find(class_='detail_list')
            if detail_list:
                for item in detail_list.find_all(['p', 'li', 'div']):
                    text = item.get_text(strip=True)
                    if text.startswith('主演：'):
                        actor = text.replace('主演：', '').strip()
                    elif text.startswith('导演：'):
                        director = text.replace('导演：', '').strip()
                    elif text.startswith('简介：'):
                        content = text.replace('简介：', '').strip()
                        content = re.sub(r'详细\s*>$', '', content).strip()
            if not content:
                intro_tag = soup.find(class_=re.compile(r'intro|content|desc'))
                if intro_tag:
                    content = intro_tag.get_text(strip=True)
            play_from_list, play_url_list = self._parse_play_sources(html, vod_id)
            remarks = ''
            remark_tag = soup.find(class_=re.compile(r'status|state'))
            if remark_tag:
                remarks = remark_tag.get_text(strip=True)
            vod_item = {
                "vod_id": vod_id, "vod_name": title, "vod_pic": poster, "type_name": type_name,
                "vod_year": year, "vod_area": area, "vod_lang": lang, "vod_remarks": remarks,
                "vod_actor": actor, "vod_director": director, "vod_content": content,
                "vod_play_from": '$$$'.join(play_from_list), "vod_play_url": '$$$'.join(play_url_list),
            }
            return {"list": [vod_item]}
        except Exception as e:
            logger.error(f"获取详情失败: {e}")
            return {"list": []}

    def _parse_play_sources(self, html, vod_id):
        play_from_list = []
        play_url_list = []
        play_links = re.findall(r'/vodplay/(\d+)-(\d+)-(\d+)\.html', html)
        sources = {}
        for vid, sid, nid in play_links:
            sources.setdefault(sid, []).append((int(nid), f"/vodplay/{vid}-{sid}-{nid}.html"))
        source_names = {"1": "线路1", "2": "线路2", "3": "线路3", "4": "线路4"}
        for sid in sorted(sources.keys()):
            episodes = sorted(set(sources[sid]), key=lambda x: x[0])
            from_name = source_names.get(sid, f"线路{sid}")
            play_from_list.append(from_name)
            urls = [f"第{nid}集${self.BASE_URL}{link}" for nid, link in episodes]
            play_url_list.append('#'.join(urls))
        if not play_from_list and play_links:
            play_from_list = ["线路1"]
            episodes = sorted(set([(int(nid), f"/vodplay/{vid}-{sid}-{nid}.html") for vid, sid, nid in play_links]), key=lambda x: x[0])
            urls = [f"第{nid}集${self.BASE_URL}{link}" for nid, link in episodes]
            play_url_list.append('#'.join(urls))
        return play_from_list, play_url_list

    def _get_m3u8_url(self, play_link):
        try:
            html = self._fetch(self.BASE_URL + play_link)
            if not html:
                return ""
            match = re.search(r'player_aaaa\s*=\s*({[^<]+})', html)
            if match:
                try:
                    data = json.loads(match.group(1))
                    m3u8_url = data.get('url', '')
                    if m3u8_url:
                        return m3u8_url
                except Exception:
                    pass
            m3u8_match = re.search(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
            if m3u8_match:
                return m3u8_match.group(0)
            return ""
        except Exception as e:
            logger.warning(f"获取m3u8失败 {play_link}: {e}")
            return ""

    def playerContent(self, flag, id, vipFlags):
        try:
            play_url = urllib.parse.unquote(id) if id else ''
            if '/vodplay/' in play_url:
                play_link = play_url.replace(self.BASE_URL, '')
                m3u8_url = self._get_m3u8_url(play_link)
                if m3u8_url:
                    return {"parse": 0, "url": m3u8_url}
            return {"parse": 0, "url": play_url}
        except Exception as e:
            logger.error(f"解析播放失败: {e}")
            return {"parse": 0, "url": ""}

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
            encoded_key = urllib.parse.quote(key)
            # 优先使用 AJAX 建议接口
            ajax_url = f"{self.BASE_URL}/index.php/ajax/suggest?mid=1&wd={encoded_key}"
            html = self._fetch(ajax_url)
            if html and html.strip().startswith('{'):
                try:
                    data = json.loads(html)
                    if data.get('code') == 1 and data.get('list'):
                        videos = []
                        for item in data['list']:
                            videos.append({
                                "vod_id": str(item.get('id', '')),
                                "vod_name": item.get('name', ''),
                                "vod_pic": item.get('pic', ''),
                                "vod_remarks": item.get('note', ''),
                            })
                        return {
                            "list": videos, "page": data.get('page', page),
                            "pagecount": data.get('pagecount', 1), "limit": data.get('limit', 20),
                            "total": data.get('total', len(videos)),
                        }
                except Exception:
                    pass
            # 回退到HTML搜索页
            url = f"{self.BASE_URL}/vodsearch/-------------.html?wd={encoded_key}"
            if page > 1:
                url += f"&page={page}"
            html = self._fetch(url)
            if not html:
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            if any(k in html for k in ['验证码', '人机验证', '安全验证']):
                logger.warning("搜索被安全验证拦截")
                return {"list": [], "page": page, "pagecount": 1, "limit": 20, "total": 0}
            videos = self._parse_video_list(html, is_home=False)
            return {"list": videos, "page": page, "pagecount": 100, "limit": 20, "total": len(videos) * 100}
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return {"list": [], "page": 1, "pagecount": 1, "limit": 20, "total": 0}