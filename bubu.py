# -*- coding: utf-8 -*-
# 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
# 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。
#
# 修复重点：
# 1. 域名全部集中到 ext.site，支持多个域名逗号分隔。
# 2. 首页、分类、搜索、详情、播放解析统一走 api_get()，同一批 ext 域名自动切换。
# 3. 不再只用单一 host，避免“搜索能出结果，但详情/播放接口没对上”。
# 4. 兼容 data 为 list/dict、vodplayer 缺失、decode 接口返回 dict/string 等情况。

import sys
sys.path.append('..')

from base.spider import Spider
import json
import re
import time
import random
import secrets
import hashlib
import urllib3
import threading
import requests
from urllib.parse import urlencode, quote

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Spider(Spider):
    # 默认也放这里兜底；实际建议在配置 ext.site 里写全。
    # 例如："site": "https://bubutv.top,https://bbys.app,https://www.bbys.app"
    DEFAULT_SITES = 'https://bubutv.top,https://bbys.app,https://www.bbys.app'
    host = 'https://bubutv.top'
    sites = []
    device_id = ''

    def init(self, extend=''):
        hosts = self.DEFAULT_SITES
        try:
            if extend:
                ext = json.loads(extend) if isinstance(extend, str) else extend
                hosts = ext.get('site') or ext.get('host') or ext.get('url') or hosts
        except Exception:
            pass

        self.sites = self.parse_sites(hosts)
        if not self.sites:
            self.sites = self.parse_sites(self.DEFAULT_SITES)
        self.host = self.host_late(self.sites)

    def getName(self):
        return '布布'

    def homeContent(self, filter):
        response = self.api_get('/api.php/app/index/home')
        categories = []
        data = response.get('data') if isinstance(response, dict) else None
        if isinstance(data, dict):
            categories = data.get('categories') or []
        elif isinstance(data, list):
            categories = data

        videos, classes = [], []
        for i in categories:
            if not isinstance(i, dict):
                continue
            type_name = i.get('type_name') or i.get('typeName') or i.get('name') or ''
            if not type_name:
                continue
            classes.append({'type_id': type_name, 'type_name': type_name})
            videos.extend(self.arr2vods(i.get('videos') or i.get('vods') or i.get('list') or []))
        return {'class': classes, 'list': videos}

    def homeVideoContent(self):
        try:
            return {'list': self.homeContent(False).get('list', [])}
        except Exception:
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        params = {
            'type_name': tid,
            'page': pg,
            'sort': extend.get('sort', 'hits') if isinstance(extend, dict) else 'hits'
        }
        response = self.api_get('/api.php/app/filter/vod', params=params)
        data = response.get('data', []) if isinstance(response, dict) else []
        if isinstance(data, dict):
            data = data.get('list') or data.get('data') or []
        return {
            'list': self.arr2vods(data if isinstance(data, list) else []),
            'pagecount': int(response.get('pageCount') or response.get('pagecount') or 9999) if isinstance(response, dict) else 9999,
            'page': int(pg),
            'limit': 20,
            'total': 999999
        }

    def searchContent(self, key, quick, pg='1'):
        # 搜索也统一走 ext 域名池，避免固定到错误 host。
        response = self.api_get('/api.php/app/search/index', params={
            'wd': key,
            'page': pg,
            'limit': 15
        })
        data = response.get('data', []) if isinstance(response, dict) else []
        if isinstance(data, dict):
            data = data.get('list') or data.get('result') or data.get('data') or []
        return {
            'list': self.arr2vods(data if isinstance(data, list) else []),
            'pagecount': int(response.get('pageCount') or response.get('pagecount') or 9999) if isinstance(response, dict) else 9999,
            'page': int(pg)
        }

    def detailContent(self, ids):
        vod_id = ids[0] if isinstance(ids, list) else ids
        response = self.api_get('/api.php/app/vod/get_detail', params={'vod_id': vod_id})

        data_list = response.get('data') if isinstance(response, dict) else None
        if isinstance(data_list, dict):
            data = data_list
        elif isinstance(data_list, list) and data_list:
            data = data_list[0]
        else:
            return {'list': []}

        players = response.get('vodplayer') or response.get('player') or response.get('players') or []
        player_map = {}
        if isinstance(players, list):
            for p in players:
                if not isinstance(p, dict):
                    continue
                frm = str(p.get('from') or p.get('code') or '')
                if frm:
                    player_map[frm.casefold()] = p

        shows, play_urls = [], []
        raw_shows = str(data.get('vod_play_from') or '').split('$$$')
        raw_urls_list = str(data.get('vod_play_url') or '').split('$$$')

        for show_code, urls_str in zip(raw_shows, raw_urls_list):
            show_code = str(show_code or '').strip()
            urls_str = str(urls_str or '').strip()
            if not show_code or not urls_str:
                continue

            pinfo = player_map.get(show_code.casefold(), {})
            # 如果接口没有 vodplayer，不强行隐藏播放组。
            need_parse = pinfo.get('decode_status', 0) if isinstance(pinfo, dict) else 0
            try:
                need_parse = int(need_parse)
            except Exception:
                need_parse = 0

            show_name = pinfo.get('show') if isinstance(pinfo, dict) else ''
            name = show_name or show_code
            if show_name and show_code.casefold() != str(show_name).casefold():
                name = f'{show_name}\u2005({show_code})'

            urls = []
            for url_item in urls_str.split('#'):
                if '$' not in url_item:
                    continue
                episode, url = url_item.split('$', 1)
                episode, url = episode.strip(), url.strip()
                if episode and url:
                    # 这里保留 show_code + 是否解析 + 原始地址，playerContent 再统一处理。
                    urls.append(f'{episode}${show_code}@{need_parse}@{url}')

            if urls:
                shows.append(name)
                play_urls.append('#'.join(urls))

        video = {
            'vod_id': data.get('vod_id', vod_id),
            'vod_name': data.get('vod_name', ''),
            'vod_pic': data.get('vod_pic', ''),
            'vod_remarks': data.get('vod_remarks', ''),
            'vod_year': data.get('vod_year', ''),
            'vod_area': data.get('vod_area', ''),
            'vod_actor': data.get('vod_actor', ''),
            'vod_director': data.get('vod_director', ''),
            'vod_content': data.get('vod_content', ''),
            'vod_play_from': '$$$'.join(shows),
            'vod_play_url': '$$$'.join(play_urls),
            'type_name': data.get('vod_class') or data.get('type_name') or ''
        }
        return {'list': [video]}

    def playerContent(self, flag, vid, vip_flags):
        try:
            play_from, need_parse, raw_url = vid.split('@', 2)
        except Exception:
            return {'jx': 0, 'parse': 0, 'url': vid, 'header': self.play_header()}

        jx, url = 0, ''
        if str(need_parse) == '1':
            try:
                response = self.api_get('/api.php/app/decode/url/', params={
                    'url': raw_url,
                    'vodFrom': play_from
                }, timeout=30)
                play_url = response.get('data') if isinstance(response, dict) else ''
                if isinstance(play_url, dict):
                    play_url = play_url.get('url') or play_url.get('play_url') or play_url.get('playUrl') or ''
                if isinstance(play_url, str) and play_url.startswith('http'):
                    url = play_url
            except Exception:
                pass

        if not url:
            url = raw_url
            if re.search(r'(?:iqiyi|v\.qq|youku|mgtv|bilibili)\.com', raw_url):
                jx = 1

        return {'jx': jx, 'parse': 0, 'url': url, 'header': self.play_header()}

    def api_get(self, path, params=None, timeout=30):
        # 所有接口统一从 ext 域名池尝试。某个域名搜索可用但播放失败时，会继续试下一个。
        if not self.sites:
            self.init()

        path = '/' + path.lstrip('/')
        query = ''
        if params:
            query = '?' + urlencode(params)

        last_error = None
        hosts = []
        if self.host:
            hosts.append(self.host.rstrip('/'))
        for h in self.sites:
            h = h.rstrip('/')
            if h and h not in hosts:
                hosts.append(h)

        for host in hosts:
            try:
                url = f'{host}{path}{query}'
                res = self.fetch(url, headers=self.headers(), verify=False, timeout=timeout)
                data = res.json()
                if isinstance(data, dict) and (data.get('code') in [401, 403] or data.get('msg') == 'Unauthorized'):
                    last_error = Exception('unauthorized')
                    continue
                self.host = host
                return data
            except Exception as e:
                last_error = e
                continue

        raise last_error or Exception('all hosts failed')

    def arr2vods(self, arr):
        videos = []
        if isinstance(arr, dict):
            arr = arr.get('list') or arr.get('data') or []
        if not isinstance(arr, list):
            return videos

        for i in arr:
            if not isinstance(i, dict):
                continue
            vod_id = i.get('vod_id') or i.get('id') or i.get('vodId') or ''
            vod_name = i.get('vod_name') or i.get('name') or i.get('vodName') or ''
            vod_pic = i.get('vod_pic') or i.get('pic') or i.get('cover') or i.get('vodPic') or ''
            vod_remarks = i.get('vod_remarks') or i.get('remarks') or i.get('note') or ''
            type_name = i.get('type_name') or i.get('typeName') or ''
            vod_class = i.get('vod_class') or i.get('class') or ''
            if vod_class:
                type_name = f'{type_name},{vod_class}' if type_name else vod_class
            if vod_id and vod_name:
                videos.append({
                    'vod_id': vod_id,
                    'vod_name': vod_name,
                    'vod_pic': vod_pic,
                    'vod_remarks': vod_remarks,
                    'type_name': type_name,
                    'vod_year': i.get('vod_year') or i.get('year') or ''
                })
        return videos

    def headers(self):
        timestamp = str(int(time.time()))
        nonce = ''.join(random.choice('0123456789') for _ in range(3))
        ver, pkg = '3', 'com.sunshine.tv'
        sign_str = (
            'finger=SF-C3B2B41F6EFFFF9869176CF68F6790E8F07506FC88632C94B4F5F0430D5498CA'
            f'&id={pkg}&nonce={nonce}&sk=SK-thanks&time={timestamp}&v={ver}'
        )
        sign = hashlib.sha256(sign_str.encode('utf-8')).hexdigest().upper()

        device_id_cache_key = 'bubu_device_id_16'
        try:
            if not (isinstance(self.device_id, str) and len(self.device_id) == 16):
                self.device_id = self.getCache(device_id_cache_key)
            if not (isinstance(self.device_id, str) and len(self.device_id) == 16):
                self.device_id = ''.join(secrets.choice('0123456789abcdef') for _ in range(16))
                self.setCache(device_id_cache_key, self.device_id)
        except Exception:
            if not (isinstance(self.device_id, str) and len(self.device_id) == 16):
                self.device_id = ''.join(random.choice('0123456789abcdef') for _ in range(16))

        return {
            'User-Agent': 'okhttp/4.12.0',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'x-aid': pkg,
            'x-ave': ver,
            'x-time': timestamp,
            'x-nonc': nonce,
            'x-sign': sign,
            'x-device-id': self.device_id,
            'x-device-brand': 'vivo',
            'x-device-model': 'V2309A',
            'x-update-id': '0245861b-2ebf-5524-389d-f983830651ec'
        }

    def play_header(self):
        return {
            'User-Agent': 'com.sunshine.tv/1.2.0 (Linux;Android 15) AndroidXMedia3/1.4.1'
        }

    def parse_sites(self, url_list):
        if isinstance(url_list, str):
            urls = url_list.split(',')
        elif isinstance(url_list, list):
            urls = url_list
        else:
            urls = []

        result = []
        for u in urls:
            u = str(u).strip().rstrip('/')
            if not u:
                continue
            if not u.startswith('http'):
                u = 'https://' + u
            if u not in result:
                result.append(u)
        return result

    def host_late(self, url_list):
        urls = self.parse_sites(url_list)
        if len(urls) <= 1:
            return urls[0] if urls else self.host

        results = {}
        threads = []

        def test_host(url):
            try:
                start_time = time.time()
                # 直接测 API 首页，不测根目录；根目录可访问不代表 app api 可用。
                requests.get(
                    f'{url.rstrip("/")}/api.php/app/index/home',
                    headers=self.headers(),
                    timeout=1.8,
                    verify=False
                )
                results[url] = (time.time() - start_time) * 1000
            except Exception:
                results[url] = float('inf')

        for url in urls:
            t = threading.Thread(target=test_host, args=(url,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return min(results.items(), key=lambda x: x[1])[0] if results else urls[0]

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass
