# -*- coding: utf-8 -*-
# 短剧聚合 Spider - 适配七猫、星芽、西饭、围观、河马，对齐SMCMS规范日志/缓存/返回结构
import re
import json
import base64
import hashlib
import time
import random
import sys
from urllib.parse import quote, unquote

# requests容错兼容影视仓无内置requests环境
try:
    import requests
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.keys = 'd3dGiJc651gSQ8w1'
        self.char_map = {
            '+': 'P', '/': 'X', '0': 'M', '1': 'U', '2': 'l', '3': 'E', '4': 'r', '5': 'Y', '6': 'W', '7': 'b', '8': 'd', '9': 'J',
            'A': '9', 'B': 's', 'C': 'a', 'D': 'I', 'E': '0', 'F': 'o', 'G': 'y', 'H': '_', 'I': 'H', 'J': 'G', 'K': 'i', 'L': 't',
            'M': 'g', 'N': 'N', 'O': 'A', 'P': '8', 'Q': 'F', 'R': 'k', 'S': '3', 'T': 'h', 'U': 'f', 'V': 'R', 'W': 'q', 'X': 'C',
            'Y': '4', 'Z': 'p', 'a': 'm', 'b': 'B', 'c': 'O', 'd': 'u', 'e': 'c', 'f': '6', 'g': 'K', 'h': 'x', 'i': '5', 'j': 'T',
            'k': '-', 'l': '2', 'm': 'z', 'n': 'S', 'o': 'Z', 'p': '1', 'q': 'V', 'r': 'v', 's': 'j', 't': 'Q', 'u': '7', 'v': 'D',
            'w': 'w', 'x': 'n', 'y': 'L', 'z': 'e'
        }
        self.headers_default = {
            'User-Agent': 'okhttp/3.12.11',
            'content-type': 'application/json; charset=utf-8'
        }
        self.platform = {
            '星芽': {
                'host': 'https://app.whjzjx.cn',
                'url1': '/cloud/v2/theater/home_page?theater_class_id',
                'url2': '/v2/theater_parent/detail',
                'search': '/v3/search',
                'classes': '/cloud/v2/theater/classes',
                'rankDetail': '/cloud/v1/first_level_ranking/detail',
                'loginUrl': 'https://u.shytkjgs.com/user/v1/account/login'
            },
            '西饭': {
                'host': 'https://xifan-api-cn.youlishipin.com',
                'url1': '/xifan/drama/portalPage',
                'url2': '/xifan/drama/getDuanjuInfo',
                'search': '/xifan/search/getSearchList'
            },
            '七猫': {
                'host': 'https://api-store.qmplaylet.com',
                'url1': '/api/v1/playlet/index',
                'url2': 'https://api-read.qmplaylet.com/player/api/v1/playlet/info',
                'search': '/api/v1/playlet/search'
            },
            '围观': {
                'host': 'https://api.drama.9ddm.com',
                'url1': '/drama/home/shortVideoTags',
                'url2': '/drama/home/shortVideoDetail',
                'search': '/drama/home/search'
            },
            '河马': {
                'host': 'https://www.kuaikaw.cn',
                'search': '/seo/video/6007'
            }
        }
        self.platform_list = [
            {'name': '七猫短剧', 'id': '七猫'},
            {'name': '星芽短剧', 'id': '星芽'},
            {'name': '西饭短剧', 'id': '西饭'},
            {'name': '围观短剧', 'id': '围观'},
            {'name': '河马短剧', 'id': '河马'}
        ]
        self.rule_filter_def = {
            '星芽': {'area': '1', 'class2': '0', 'rank': '1'},
            '西饭': {'area': '都市'},
            '七猫': {'area': '0'},
            '围观': {'area': ''},
            '河马': {'area': '462'}
        }
        self.filter_options = {
            '七猫': [{
                'key': 'area',
                'name': '分类',
                'value': [
                    {'n': '全部', 'v': '0'},
                    {'n': '男频', 'v': '1'},
                    {'n': '新剧', 'v': '3'},
                    {'n': '现代言情', 'v': '21'},
                    {'n': '神豪', 'v': '37'},
                    {'n': '萌宝', 'v': '356'},
                    {'n': '穿越', 'v': '373'},
                    {'n': '战神', 'v': '527'},
                    {'n': '神医', 'v': '1269'},
                    {'n': '古装', 'v': '1272'}
                ]
            }],
            '星芽': [{
                'key': 'area',
                'name': '剧场',
                'value': [
                    {'n': '剧场', 'v': '1'},
                    {'n': '热播短剧', 'v': '2'},
                    {'n': '会员专享', 'v': '8'},
                    {'n': '星选好剧', 'v': '7'},
                    {'n': '新剧', 'v': '3'},
                    {'n': '阳光剧场', 'v': '5'},
                    {'n': '排行榜', 'v': '9'}
                ]
            }, {
                'key': 'class2',
                'name': '类型',
                'value': [
                    {'n': '全部', 'v': '0'},
                    {'n': '都市', 'v': '4'},
                    {'n': '逆袭', 'v': '7'},
                    {'n': '古装', 'v': '5'},
                    {'n': '亲情', 'v': '41'},
                    {'n': '现代言情', 'v': '15'},
                    {'n': '重生', 'v': '6'},
                    {'n': '虐恋', 'v': '8'},
                    {'n': '玄幻', 'v': '35'},
                    {'n': '穿越', 'v': '17'},
                    {'n': '脑洞', 'v': '32'},
                    {'n': '甜宠', 'v': '33'},
                    {'n': '古代言情', 'v': '37'},
                    {'n': '战神', 'v': '24'},
                    {'n': '历史', 'v': '40'},
                    {'n': '赘婿', 'v': '26'},
                    {'n': '萌宝', 'v': '9'},
                    {'n': '神医', 'v': '25'}
                ]
            }, {
                'key': 'rank',
                'name': '榜单',
                'value': [
                    {'n': '实时热榜', 'v': '1'},
                    {'n': '热搜榜', 'v': '2'},
                    {'n': '新剧榜', 'v': '3'},
                    {'n': '剧单榜', 'v': '4'},
                    {'n': '口碑榜', 'v': '5'}
                ]
            }],
            '西饭': [{
                'key': 'area',
                'name': '分类',
                'value': [
                    {'n': '都市', 'v': '都市'},
                    {'n': '甜宠', 'v': '甜宠'},
                    {'n': '逆袭', 'v': '逆袭'},
                    {'n': '战神', 'v': '战神'},
                    {'n': '古装', 'v': '古装'},
                    {'n': '穿越', 'v': '穿越'},
                    {'n': '萌宝', 'v': '萌宝'}
                ]
            }],
            '围观': [{
                'key': 'area',
                'name': '分类',
                'value': [
                    {'n': '全部', 'v': ''},
                    {'n': '都市', 'v': '都市'},
                    {'n': '逆袭', 'v': '逆袭'},
                    {'n': '家庭', 'v': '家庭'},
                    {'n': '古装', 'v': '古装'},
                    {'n': '复仇', 'v': '复仇'},
                    {'n': '甜宠', 'v': '甜宠'},
                    {'n': '悬疑', 'v': '悬疑'},
                    {'n': '爱情', 'v': '爱情'},
                    {'n': '重生', 'v': '重生'},
                    {'n': '总裁', 'v': '总裁'},
                    {'n': '穿越', 'v': '穿越'},
                    {'n': '萌宝', 'v': '萌宝'},
                    {'n': '战神', 'v': '战神'},
                    {'n': '职场', 'v': '职场'},
                    {'n': '神豪', 'v': '神豪'},
                    {'n': '神医', 'v': '神医'},
                    {'n': '赘婿', 'v': '赘婿'}
                ]
            }],
            '河马': [{
                'key': 'area',
                'name': '分类',
                'value': [
                    {'n': '甜宠', 'v': '462'},
                    {'n': '古装仙侠', 'v': '1102'},
                    {'n': '现代言情', 'v': '1145'},
                    {'n': '青春', 'v': '1170'},
                    {'n': '豪门恩怨', 'v': '585'},
                    {'n': '逆袭', 'v': '417-464'},
                    {'n': '重生', 'v': '439-465'},
                    {'n': '系统', 'v': '1159'},
                    {'n': '总裁', 'v': '1147'},
                    {'n': '职场商战', 'v': '943'}
                ]
            }]
        }
        # 各类缓存
        self.qm_header = {'value': None, 'timestamp': 0}
        self.xingya_token = None
        self.xingya_headers = self.headers_default.copy()
        self._filters_cache = None
        self._session = None
        self._play_cache = {}  # 播放地址缓存 30分钟有效

    def init(self, extend=""):
        self.extend = extend
        print(f'[duanju] init ok', file=sys.stderr)
        return self

    def getName(self):
        return "短剧聚合"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # 对齐SMCMS 通用字段清理函数
    @staticmethod
    def _clean(item):
        if isinstance(item, dict):
            item.pop('type', None)
            item.pop('type_1', None)
        return item

    def _md5(self, text):
        return hashlib.md5(text.encode()).hexdigest().lower()

    def _base64_encode(self, text):
        return base64.b64encode(text.encode()).decode()

    def _base64_decode(self, text):
        try:
            return base64.b64decode(text).decode()
        except Exception:
            return text

    # 统一会话请求封装 对齐参考http_get/http_post
    def http_get(self, url, headers=None, timeout=10):
        if requests:
            if not self._session:
                self._session = requests.Session()
            return self._session.get(url, headers=headers or self.headers_default, timeout=timeout, verify=False)
        return self.fetch(url, headers=headers)

    def http_post(self, url, headers=None, json=None, timeout=10):
        if requests:
            if not self._session:
                self._session = requests.Session()
            return self._session.post(url, headers=headers or self.headers_default, json=json, timeout=timeout, verify=False)
        return super().post(url, headers=headers, json=json)

    def _get_qm_params_and_sign(self):
        now = int(time.time() * 1000)
        if self.qm_header['value'] and now - self.qm_header['timestamp'] < 300000:
            return self.qm_header['value']

        session_id = str(now)
        data = {
            "static_score": "0.8",
            "uuid": "00000000-7fc7-08dc-0000-000000000000",
            "device-id": "20250220125449b9b8cac84c2dd3d035c9052a2572f7dd0122edde3cc42a70",
            "sourceuid": "aa7de295aad621a6",
            "refresh-type": "0",
            "model": "22021211RC",
            "client-id": "aa7de295aad621a6",
            "brand": "Redmi",
            "sys-ver": "12",
            "phone-level": "H",
            "wlb-uid": "aa7de295aad621a6",
            "session-id": session_id
        }

        json_str = json.dumps(data, separators=(',', ':'))
        base64_str = self._base64_encode(json_str)
        qm_params = ''
        for char in base64_str:
            qm_params += self.char_map.get(char, char)

        params_str = f"AUTHORIZATION=app-version=10001application-id=com.duoduo.readchannel=unknownis-white=net-env=5platform=androidqm-params={qm_params}reg={self.keys}"
        sign = self._md5(params_str)

        self.qm_header['value'] = {'qmParams': qm_params, 'sign': sign}
        self.qm_header['timestamp'] = now
        return self.qm_header['value']

    def _get_header_x(self):
        qm = self._get_qm_params_and_sign()
        return {
            'net-env': '5',
            'reg': '',
            'channel': 'unknown',
            'is-white': '',
            'platform': 'android',
            'application-id': 'com.duoduo.read',
            'authorization': '',
            'app-version': '10001',
            'user-agent': 'webviewversion/0',
            'qm-params': qm['qmParams'],
            'sign': qm['sign']
        }

    def _ensure_xingya_auth(self):
        if self.xingya_headers.get('authorization'):
            return self.xingya_headers
        try:
            plat = self.platform['星芽']
            res = self.http_post(
                plat['loginUrl'],
                headers={'User-Agent': 'okhttp/4.10.0', 'platform': '1', 'Content-Type': 'application/json'},
                json={'device': '24250683a3bdb3f118dff25ba4b1cba1a'},
                timeout=10
            )
            data = res.json()
            token = data.get('data', {}).get('token') or data.get('token')
            if token:
                self.xingya_headers = {**self.headers_default, 'authorization': token}
                self.xingya_token = token
        except Exception as e:
            print(f'[duanju] 星芽获取token失败 err={e}', file=sys.stderr)
        return self.xingya_headers

    # 统一请求工具
    def _request(self, url, method='GET', headers=None, data=None, timeout=5):
        try:
            headers = {**self.headers_default, **(headers or {})}
            if method.upper() == 'POST':
                res = self.http_post(url, headers=headers, json=data, timeout=timeout)
            else:
                res = self.http_get(url, headers=headers, timeout=timeout)
            return res.json()
        except Exception as e:
            print(f'[duanju] _request error url={url[:60]} err={e}', file=sys.stderr)
            return None

    # 筛选缓存统一化
    def _get_filters(self):
        if getattr(self, '_filters_cache', None) is not None:
            return self._filters_cache
        filters = {}
        for item in self.platform_list:
            pid = item['id']
            filters[pid] = self.filter_options.get(pid, [])
        self._filters_cache = filters
        return filters

    def homeContent(self, filter):
        classes = [{'type_name': p['name'], 'type_id': p['id']} for p in self.platform_list]
        filters = self._get_filters() if filter else {}
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        try:
            res = self.categoryContent('七猫', '1', False, {})
            return res
        except Exception as e:
            print(f'[duanju] homeVideoContent FAIL err={e}', file=sys.stderr)
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if pg else 1
        plat = self.platform.get(tid)
        area = extend.get('area') if extend.get('area') is not None else self.rule_filter_def.get(tid, {}).get('area', '')
        videos = []

        if not plat:
            return {'list': videos, 'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0}

        try:
            if tid == '七猫':
                if pg > 1:
                    return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0}
                sign = self._md5(f"operation=1playlet_privacy=1tag_id={area}{self.keys}")
                url = f"{plat['host']}{plat['url1']}?tag_id={area}&playlet_privacy=1&operation=1&sign={sign}"
                header_x = self._get_header_x()
                res = self._request(url, headers={**header_x, **self.headers_default})
                if res and res.get('data', {}).get('list'):
                    for i in res['data']['list'][:6]:
                        vod_item = {
                            'vod_id': f"七猫@{quote(str(i['playlet_id']))}",
                            'vod_name': i['title'],
                            'vod_pic': i['image_link'],
                            'vod_remarks': f"{i['total_episode_num']}集",
                            'vod_content': f"七猫短剧 | {i['total_episode_num']}集"
                        }
                        videos.append(self._clean(vod_item))
                print(f'[duanju] categoryContent tid={tid} pg={pg} list={len(videos)}', file=sys.stderr)
                return {'list': videos, 'page': pg, 'pagecount': 1, 'limit': len(videos), 'total': len(videos)}

            elif tid == '星芽':
                headers = self._ensure_xingya_auth()
                if area == '9':
                    rank = extend.get('rank') or extend.get('class2') or self.rule_filter_def['星芽'].get('rank', '1')
                    if pg > 1:
                        return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0}
                    res = self._request(f"{plat['host']}{plat['rankDetail']}?id={rank}", headers=headers)
                    for item in res.get('data', {}).get('list', []):
                        i = item.get('theater') or item
                        if not i or not i.get('id'):
                            continue
                        vod_item = {
                            'vod_id': f"星芽@{plat['host']}{plat['url2']}?theater_parent_id={i['id']}",
                            'vod_name': i['title'],
                            'vod_pic': i['cover_url'],
                            'vod_remarks': f"{i.get('total', '')}集"
                        }
                        videos.append(self._clean(vod_item))
                    print(f'[duanju] categoryContent tid={tid} pg={pg} list={len(videos)}', file=sys.stderr)
                    return {'list': videos, 'page': pg, 'pagecount': 1, 'limit': len(videos), 'total': len(videos)}

                class2 = extend.get('class2') or self.rule_filter_def['星芽'].get('class2', '0')
                url = f"{plat['host']}{plat['url1']}={area}&type=1&class2_ids={class2}&page_num={pg}&page_size=24"
                res = self._request(url, headers=headers)
                data = res.get('data', {})
                for i in data.get('list', []):
                    item = i.get('theater') or i
                    if not item or not item.get('id'):
                        continue
                    vod_item = {
                        'vod_id': f"星芽@{plat['host']}{plat['url2']}?theater_parent_id={item['id']}",
                        'vod_name': item['title'],
                        'vod_pic': item['cover_url'],
                        'vod_remarks': f"{item.get('total', '')}集"
                    }
                    videos.append(self._clean(vod_item))
                total = int(data.get('total') or len(videos))
                is_single_page = not videos or data.get('is_end') or total <= len(videos) or len(videos) > 24
                if is_single_page:
                    ret_list = videos if pg == 1 else []
                    pagecount = 1
                else:
                    pagecount = max(1, (total + 23) // 24)
                    ret_list = videos
                print(f'[duanju] categoryContent tid={tid} pg={pg} list={len(ret_list)} total={total}', file=sys.stderr)
                return {'list': ret_list, 'page': pg, 'pagecount': pagecount, 'limit': 24, 'total': total}

            elif tid == '西饭':
                if pg > 1:
                    return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0}
                search_url = f"{plat['host']}{plat['search']}?reqType=search&offset=0&keyword={quote(area or '')}&quickEngineVersion=-1&scene="
                search_res = self._request(search_url)
                for block in search_res.get('result', {}).get('elements', []):
                    for item in block.get('contents', []):
                        dj = item.get('duanjuVo') or {}
                        if not dj.get('duanjuId'):
                            continue
                        categories = dj.get('categories', [])
                        if area and area not in categories:
                            continue
                        vod_item = {
                            'vod_id': f"西饭@{dj['duanjuId']}#{dj['source']}",
                            'vod_name': dj['title'],
                            'vod_pic': dj['coverImageUrl'],
                            'vod_remarks': f"{dj.get('total', '')}集"
                        }
                        videos.append(self._clean(vod_item))
                print(f'[duanju] categoryContent tid={tid} pg={pg} list={len(videos)}', file=sys.stderr)
                return {'list': videos, 'page': pg, 'pagecount': 1, 'limit': len(videos), 'total': len(videos)}

            elif tid == '围观':
                device_name = 'Pixel 8 Pro'
                device_firm = 'Google'
                client_info = self._md5(str(int(time.time() * 1000))[-10:])
                url = f"{plat['host']}{plat['search']}?version_code=1500&version_name=1.5.0&device_name={quote(device_name)}&device_type=phone&is_first_day=true&is_first_24h=true&app_launch_way=icon&default_homepage=homepage_interaction&device_owning_firm={quote(device_firm)}&font_scale=default&os_type=1&clientInfo={client_info}"
                res = self._request(url, method='POST', headers={'User-Agent': 'okhttp/5.1.0', 'Content-Type': 'application/json; charset=utf-8'}, data={'audience': '全部', 'order': '最新', 'page': pg, 'pageSize': 30, 'searchWord': '', 'subject': area or ''})
                for i in res.get('data', []):
                    vod_item = {
                        'vod_id': f"围观@{i['oneId']}",
                        'vod_name': i['title'],
                        'vod_pic': i.get('horzPoster') or i.get('vertPoster'),
                        'vod_remarks': f"{i.get('episodeCount', '')}集"
                    }
                    videos.append(self._clean(vod_item))
                pagecount = pg if len(videos) < 30 else pg + 1
                total = (pg - 1) * 30 + len(videos)
                print(f'[duanju] categoryContent tid={tid} pg={pg} list={len(videos)}', file=sys.stderr)
                return {'list': videos, 'page': pg, 'pagecount': pagecount, 'limit': 30, 'total': total}

            elif tid == '河马':
                url = f"{plat['host']}/browse/{area or self.rule_filter_def['河马']['area']}/{pg}"
                try:
                    headers_h = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                        'Referer': url,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
                    }
                    rsp = self.http_get(url, headers=headers_h, timeout=10)
                    html = rsp.text
                    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([\s\S]*?)</script>', html)
                    if match:
                        json_data = json.loads(match.group(1))
                        page_props = json_data.get('props', {}).get('pageProps', {})
                        for book in page_props.get('bookList', []):
                            if not book.get('bookId'):
                                continue
                            vod_item = {
                                'vod_id': f"河马@/drama/{book['bookId']}",
                                'vod_name': book['bookName'],
                                'vod_pic': book.get('coverWap'),
                                'vod_remarks': f"{book.get('statusDesc', '')} {book.get('totalChapterNum', '')}集".strip()
                            }
                            videos.append(self._clean(vod_item))
                        pages = int(page_props.get('pages') or pg)
                        print(f'[duanju] categoryContent tid={tid} pg={pg} list={len(videos)}', file=sys.stderr)
                        return {'list': videos, 'page': pg, 'pagecount': pages, 'limit': len(videos), 'total': pages * len(videos)}
                except Exception as e:
                    print(f'[duanju] 河马分类请求异常 err={e}', file=sys.stderr)

        except Exception as e:
            import traceback
            print(f'[duanju] categoryContent FAIL tid={tid} err={e}\n{traceback.format_exc()}', file=sys.stderr)

        return {'list': videos, 'page': pg, 'pagecount': 1, 'limit': len(videos), 'total': len(videos)}

    def detailContent(self, ids):
        videos = []
        for raw_id in ids if isinstance(ids, list) else [ids]:
            if not raw_id:
                continue
            parts = raw_id.split('@', 1)
            if len(parts) < 2:
                continue
            plat_id, did = parts[0], parts[1]
            plat = self.platform.get(plat_id)
            if not plat:
                videos.append({'vod_id': raw_id, 'vod_name': '平台不支持', 'vod_play_url': ''})
                continue

            vod = {
                'vod_id': raw_id,
                'vod_name': '未知',
                'vod_pic': '',
                'vod_year': '',
                'vod_area': '',
                'vod_remarks': '',
                'vod_actor': '',
                'vod_director': '',
                'vod_content': '',
                'vod_play_from': '',
                'vod_play_url': ''
            }

            try:
                if plat_id == '七猫':
                    did_decoded = unquote(did)
                    sign = self._md5(f"playlet_id={did_decoded}{self.keys}")
                    url = f"{plat['url2']}?playlet_id={did_decoded}&sign={sign}"
                    header_x = self._get_header_x()
                    res = self._request(url, headers={**header_x, **self.headers_default})
                    if res and res.get('data'):
                        d = res['data']
                        play_list = d.get('play_list', [])
                        play_url = '#'.join([f"{i['sort']}${i['video_url']}" for i in play_list])
                        vod.update({
                            'vod_name': d['title'],
                            'vod_pic': d['image_link'],
                            'vod_remarks': f"{d['total_episode_num']}集",
                            'vod_content': d.get('intro', ''),
                            'vod_play_from': '七猫短剧',
                            'vod_play_url': play_url
                        })

                elif plat_id == '星芽':
                    headers = self._ensure_xingya_auth()
                    res = self._request(did, headers=headers)
                    if res and res.get('data'):
                        d = res['data']
                        theaters = d.get('theaters', [])
                        play_url = '#'.join([f"{i['num']}${i['son_video_url']}" for i in theaters])
                        vod.update({
                            'vod_name': d['title'],
                            'vod_pic': d['cover_url'],
                            'vod_remarks': str(d.get('desc_tags', '')),
                            'vod_play_from': '星芽短剧',
                            'vod_play_url': play_url
                        })

                elif plat_id == '西饭':
                    duanju_id, source = did.split('#', 1)
                    url = f"{plat['host']}{plat['url2']}?duanjuId={duanju_id}&source={source}"
                    res = self._request(url)
                    if res and res.get('result'):
                        d = res['result']
                        episode_list = d.get('episodeList', [])
                        play_url = '#'.join([f"{e['index']}${e['playUrl']}" for e in episode_list])
                        status = '已完结' if d.get('updateStatus') == 'over' else f"更新{d.get('total', '')}集"
                        vod.update({
                            'vod_name': d['title'],
                            'vod_pic': d['coverImageUrl'],
                            'vod_remarks': f"{d.get('total', '')}集 {status}",
                            'vod_play_from': '西饭短剧',
                            'vod_play_url': play_url
                        })

                elif plat_id == '围观':
                    device_name = 'Pixel 8 Pro'
                    device_firm = 'Google'
                    client_info = self._md5(str(int(time.time() * 1000))[-10:])
                    url = f"{plat['host']}{plat['url2']}?version_code=1500&version_name=1.5.0&device_name={quote(device_name)}&device_type=phone&is_first_day=true&is_first_24h=true&app_launch_way=icon&default_homepage=homepage_interaction&device_owning_firm={quote(device_firm)}&font_scale=default&os_type=1&clientInfo={client_info}&oneId={did}&page=1&pageSize=1000&userId=0&queryAll=true"
                    res = self._request(url, headers={'User-Agent': 'okhttp/5.1.0', 'Content-Type': 'application/json; charset=utf-8'})
                    episodes = res.get('data', [])
                    if episodes:
                        play_url = '#'.join([f"{e.get('playOrder') or e.get('title')}${self._base64_encode(json.dumps(e.get('videoClarityList', [])))}" for e in episodes])
                        vod.update({
                            'vod_name': res.get('title') or episodes[0].get('title') or vod['vod_name'],
                            'vod_pic': res.get('vertPoster') or episodes[0].get('vertPoster') or '',
                            'vod_remarks': f"共{len(episodes)}集",
                            'vod_content': res.get('description', ''),
                            'vod_play_from': '围观短剧',
                            'vod_play_url': play_url
                        })

                elif plat_id == '河马':
                    did_path = did if did.startswith('/drama/') else f"/drama/{did}"
                    full_url = f"{plat['host']}{did_path}"
                    headers_h = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                        'Referer': full_url,
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
                    }
                    rsp = self.http_get(full_url, headers=headers_h, timeout=10)
                    html = rsp.text
                    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([\s\S]*?)</script>', html)
                    if match:
                        json_data = json.loads(match.group(1))
                        page_props = json_data.get('props', {}).get('pageProps', {})
                        book_info = page_props.get('bookInfoVo', {})
                        chapter_list = page_props.get('chapterList', [])
                        play_urls = []
                        for chapter in chapter_list:
                            chapter_id = chapter.get('chapterId')
                            chapter_name = chapter.get('chapterName')
                            video_vo = chapter.get('chapterVideoVo', {})
                            direct_url = video_vo.get('mp4') or video_vo.get('mp4720p') or video_vo.get('vodMp4Url')
                            if direct_url and re.search(r'\.(mp4|m3u8)', direct_url, re.I):
                                play_urls.append(f"{chapter_name}${direct_url}")
                            else:
                                drama_id = did_path.replace('/drama/', '')
                                play_urls.append(f"{chapter_name}${drama_id}+{chapter_id}")
                        vod.update({
                            'vod_name': book_info.get('title') or book_info.get('bookName') or vod['vod_name'],
                            'vod_pic': book_info.get('coverWap') or '',
                            'vod_remarks': f"{book_info.get('statusDesc', '')} {book_info.get('totalChapterNum', '')}集".strip(),
                            'vod_content': book_info.get('introduction', ''),
                            'vod_play_from': '河马短剧',
                            'vod_play_url': '#'.join(play_urls)
                        })
            except Exception as e:
                import traceback
                print(f'[duanju] detail解析失败 id={raw_id} err={e}\n{traceback.format_exc()}', file=sys.stderr)
                vod['vod_name'] = '加载失败'

            videos.append(self._clean(vod))

        return {'list': videos}

    def playerContent(self, flag, id, vipFlags):
        now_ts = time.time()
        header = self.headers_default.copy()
        cache_key = f"{flag}_{id}"

        # 30分钟缓存复用，对齐SMCMS缓存逻辑
        if cache_key in self._play_cache:
            cache_time, real_url = self._play_cache[cache_key]
            if now_ts - cache_time < 1800 and real_url:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': real_url, 'header': header}

        final_url = id
        try:
            if '七猫' in flag:
                final_url = id
            elif '西饭' in flag:
                rsp = self.http_get(id, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10, allow_redirects=True)
                final_url = rsp.url
            elif '围观' in flag:
                ps = json.loads(self._base64_decode(id))
                urls = []
                for item in ps or []:
                    if item.get('name') and item.get('url'):
                        urls.append(item['url'])
                if urls:
                    final_url = urls[0]
                    header = {'User-Agent': 'okhttp/5.1.0'}
            elif '河马' in flag:
                if re.search(r'\.(mp4|m3u8)', id, re.I):
                    final_url = id
                else:
                    parts = id.split('+', 1)
                    if len(parts) >= 2:
                        drama_id, chapter_id = parts
                        episode_url = f"{self.platform['河马']['host']}/episode/{drama_id}/{chapter_id}"
                        headers_h = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                            'Referer': episode_url
                        }
                        rsp = self.http_get(episode_url, headers=headers_h, timeout=10)
                        html = rsp.text
                        match = re.search(r'(https?://[^"\']+\.(mp4|m3u8)[^"\']*)', html)
                        if match:
                            final_url = match.group(1)
        except Exception as e:
            print(f'[duanju] player解析异常 err={e}', file=sys.stderr)

        self._play_cache[cache_key] = (now_ts, final_url)
        return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': final_url, 'header': header}

    def searchContent(self, key, quick, pg="1"):
        pg = int(pg) if pg else 1
        if not key:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0}

        videos = []
        seen = set()

        def safe_push(item):
            if not item:
                return
            vid = str(item.get('vod_id', '')).strip()
            vname = str(item.get('vod_name', '')).strip()
            if not vid or not vname or vid in seen:
                return
            seen.add(vid)
            videos.append(self._clean(item))

        # 七猫搜索
        try:
            sign = self._md5(f"operation=2playlet_privacy=1search_word={key}{self.keys}")
            url = f"{self.platform['七猫']['host']}{self.platform['七猫']['search']}?search_word={quote(key)}&playlet_privacy=1&operation=2&sign={sign}"
            header_x = self._get_header_x()
            res = self._request(url, headers={**header_x, **self.headers_default})
            if res:
                for i in res.get('data', {}).get('list', []):
                    safe_push({
                        'vod_id': f"七猫@{quote(str(i['playlet_id']))}",
                        'vod_name': i.get('title', ''),
                        'vod_pic': i.get('image_link', ''),
                        'vod_remarks': f"七猫短剧｜{i.get('total_episode_num', '')}集"
                    })
        except Exception as e:
            print(f'[duanju] 七猫搜索失败 err={e}', file=sys.stderr)

        # 星芽搜索
        try:
            plat = self.platform['星芽']
            headers = self._ensure_xingya_auth()
            res = self._request(plat['host'] + plat['search'], method='POST', headers=headers, data={'text': key})
            if res:
                data = res.get('data', {})
                search_list = data.get('theater', {}).get('search_data', []) or data.get('search_data', []) or data.get('list', [])
                for i in search_list:
                    if not i.get('id'):
                        continue
                    safe_push({
                        'vod_id': f"星芽@{plat['host']}{plat['url2']}?theater_parent_id={i['id']}",
                        'vod_name': i.get('title', ''),
                        'vod_pic': i.get('cover_url', ''),
                        'vod_remarks': f"星芽短剧｜{i.get('total', '')}集"
                    })
        except Exception as e:
            print(f'[duanju] 星芽搜索失败 err={e}', file=sys.stderr)

        # 西饭搜索
        try:
            plat = self.platform['西饭']
            offset = (pg - 1) * 30
            url = f"{plat['host']}{plat['search']}?reqType=search&offset={offset}&keyword={quote(key)}&quickEngineVersion=-1&scene="
            res = self._request(url)
            if res:
                elements = res.get('result', {}).get('elements', [])
                for block in elements:
                    contents = [block] if block.get('duanjuVo') else block.get('contents', [])
                    for item in contents:
                        dj = item.get('duanjuVo') or {}
                        if not dj.get('duanjuId'):
                            continue
                        safe_push({
                            'vod_id': f"西饭@{dj['duanjuId']}#{dj['source']}",
                            'vod_name': dj.get('title', ''),
                            'vod_pic': dj.get('coverImageUrl', ''),
                            'vod_remarks': f"西饭短剧｜{dj.get('total', '')}集"
                        })
        except Exception as e:
            print(f'[duanju] 西饭搜索失败 err={e}', file=sys.stderr)

        # 围观搜索
        try:
            plat = self.platform['围观']
            device_name = 'Pixel 8 Pro'
            device_firm = 'Google'
            client_info = self._md5(str(int(time.time() * 1000))[-10:])
            url = f"{plat['host']}{plat['search']}?version_code=1500&version_name=1.5.0&device_name={quote(device_name)}&device_type=phone&is_first_day=true&is_first_24h=true&app_launch_way=icon&default_homepage=homepage_interaction&device_owning_firm={quote(device_firm)}&font_scale=default&os_type=1&clientInfo={client_info}"
            res = self._request(url, method='POST', headers={'User-Agent': 'okhttp/5.1.0', 'Content-Type': 'application/json; charset=utf-8'}, data={'audience': '', 'order': '', 'page': pg, 'pageSize': 30, 'searchWord': key, 'subject': ''})
            if res:
                for i in res.get('data', []):
                    safe_push({
                        'vod_id': f"围观@{i['oneId']}",
                        'vod_name': i.get('title', ''),
                        'vod_pic': i.get('horzPoster') or i.get('vertPoster'),
                        'vod_remarks': f"围观短剧｜{i.get('episodeCount', '')}集"
                    })
        except Exception as e:
            print(f'[duanju] 围观搜索失败 err={e}', file=sys.stderr)

        # 河马搜索
        try:
            plat = self.platform['河马']
            tmpid = ''.join(random.choices('0123456789abcdefghijklmnopqrstuvwxyz', k=16))
            headers_h = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': f"{plat['host']}/search?searchValue={quote(key)}",
                'Origin': 'https://www.kuaikaw.cn',
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/plain, */*',
                'pname': 'www.kuaikaw.cn',
                'tmpid': tmpid
            }
            res = self._request(f"{plat['host']}{plat['search']}", method='POST', headers=headers_h, data={'sourceType': 1, 'keyword': key, 'index': pg, 'page': pg})
            if res:
                for book in res.get('data', {}).get('bookList', []):
                    if not book.get('bookId'):
                        continue
                    safe_push({
                        'vod_id': f"河马@/drama/{book['bookId']}",
                        'vod_name': book.get('bookName', ''),
                        'vod_pic': book.get('coverWap', ''),
                        'vod_remarks': f"{book.get('statusDesc', '')} {book.get('totalChapterNum', '')}集".strip()
                    })
        except Exception as e:
            print(f'[duanju] 河马搜索失败 err={e}', file=sys.stderr)

        print(f'[duanju] searchContent key={key} pg={pg} total={len(videos)}', file=sys.stderr)
        return {
            'list': videos,
            'page': pg,
            'pagecount': 1,
            'limit': len(videos),
            'total': len(videos)
        }

    def localProxy(self, param):
        return None