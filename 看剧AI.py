# -*- coding: utf-8 -*-
"""
看剧 (kanju.ai) Python Spider
兼容 FongMi/TV (T3) 和 WebHomeTV/PeekPro (T4) 双壳子

站点类型: SPA + RESTful API (HMAC-SHA256 签名认证)
API:
  - 首页/搜索: GET /v1/feed/home (带 q 参数即为搜索)
  - 详情: GET /v1/catalog/{card_id} (返回含剧集列表和播放 token)
  - 剧集: GET /v1/catalog/{export_id}/episodes
  - 播放解析: GET https://player.baipiaozhe.com/v1/playback/resolve/{token}
    返回 JSON, 含 resolved m3u8 URL 和 line_options (多条备用线路)
  - m3u8 有 AES-128 加密, 密钥在 m3u8 同目录下 enc.key
    通过 localProxy 代理改写相对路径为绝对路径
"""

import sys
import json
import time
import hmac
import hashlib
import secrets
import re
import urllib.parse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):

    BASE = "https://kanju.ai"
    SECRET = "557d0e4ae929f438da6bd84412374e6086b8af09b3fed54bf22601d5bf8c54a0"
    # 修复: 播放解析服务从 zy.baipiaozhe.com 迁移到 player.baipiaozhe.com
    # 旧端点 /v1/playback/yjapi/ 和 /v1/playback/yjm3u8/ 已全部 404
    # 新端点: /v1/playback/resolve/{token}
    PLAYBACK_HOST = "https://player.baipiaozhe.com"

    def getName(self):
        return "看剧"

    def init(self, extend=""):
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
        }
        self._feed_cache = None
        self._feed_cache_time = 0
        self._detail_cache = {}
        self._play_cache = {}
        self._cache_max = 100

    # ========== HMAC 签名 ==========

    def _sign(self, method, path, query=""):
        """生成 HMAC-SHA256 签名头"""
        timestamp = str(int(time.time() * 1000))
        nonce = secrets.token_hex(16)
        path_with_search = path + '?' + query if query else path
        sig_string = '{method}\n{path}\n{ts}\n{nonce}'.format(
            method=method, path=path_with_search, ts=timestamp, nonce=nonce
        )
        signature = hmac.new(
            self.SECRET.encode('utf-8'),
            sig_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return {
            'x-ai-movie-timestamp': timestamp,
            'x-ai-movie-nonce': nonce,
            'x-ai-movie-signature': signature,
        }

    def _api_get(self, path, params=None, timeout=15):
        """签名并发送 GET 请求到 kanju.ai API"""
        query = ""
        if params:
            query = urllib.parse.urlencode(params)
        headers = dict(self.header)
        headers.update(self._sign('GET', path, query))
        url = self.BASE + path
        if query:
            url += '?' + query
        try:
            rsp = self.fetch(url, headers=headers, timeout=timeout)
            return json.loads(rsp.text)
        except Exception:
            return None

    def _plain_get(self, url, timeout=15):
        """普通 GET 请求 (用于播放解析等不需要签名的端点)"""
        try:
            rsp = self.fetch(url, headers=self.header, timeout=timeout)
            return rsp.text
        except Exception:
            return ""

    # ========== 数据格式化 ==========

    def _format_card(self, card):
        """将 API 卡片数据转为 vod 字典"""
        return {
            "vod_id": card.get("id", ""),
            "vod_name": card.get("title", ""),
            "vod_pic": card.get("poster_url", ""),
            "vod_remarks": card.get("remarks", ""),
        }

    def _get_feed(self, use_cache=True):
        """获取首页 feed 数据 (带缓存)"""
        now = int(time.time())
        if use_cache and self._feed_cache and now - self._feed_cache_time < 300:
            return self._feed_cache

        data = self._api_get('/v1/feed/home', {
            'scope': 'public',
            'mode': 'page',
            'sections': '12',
            'cards': '20',
            'adult_confirmed': 'false',
        })
        if data and 'sections' in data:
            self._feed_cache = data
            self._feed_cache_time = now
            return data
        return None

    def _get_all_cards(self):
        """从 feed 中提取所有卡片"""
        data = self._get_feed()
        if not data:
            return []
        cards = []
        seen = set()
        for sec in data.get('sections', []):
            for card in sec.get('cards', []):
                cid = card.get('id', '')
                if cid and cid not in seen:
                    seen.add(cid)
                    cards.append(card)
        return cards

    # ========== 首页 ==========

    def homeContent(self, filter):
        categories = [
            {"type_id": "all", "type_name": "推荐"},
            {"type_id": "series", "type_name": "剧集"},
            {"type_id": "movie", "type_name": "电影"},
            {"type_id": "韩剧", "type_name": "韩剧"},
            {"type_id": "日剧", "type_name": "日剧"},
            {"type_id": "美剧", "type_name": "美剧"},
            {"type_id": "国产剧", "type_name": "国产剧"},
            {"type_id": "动画", "type_name": "动画"},
        ]
        return {"class": categories}

    def homeVideoContent(self):
        """从首页 feed 提取推荐视频"""
        data = self._get_feed()
        if not data:
            return {"list": []}

        videos = []
        seen = set()
        for sec in data.get('sections', []):
            for card in sec.get('cards', []):
                cid = card.get('id', '')
                if cid and cid not in seen:
                    seen.add(cid)
                    videos.append(self._format_card(card))
                    if len(videos) >= 60:
                        break
            if len(videos) >= 60:
                break

        return {"list": videos}

    # ========== 分类列表 ==========

    def categoryContent(self, tid, pg, filter, extend):
        """分类页: 从 feed 获取所有卡片, 客户端按类型过滤"""
        pg = int(pg or 1)
        cards = self._get_all_cards()

        if tid == 'all':
            filtered = cards
        elif tid == 'series':
            filtered = [c for c in cards if c.get('content_kind') == 'series']
        elif tid == 'movie':
            filtered = [c for c in cards if c.get('content_kind') == 'movie']
        elif tid == '动画':
            filtered = [c for c in cards
                        if c.get('content_kind') == 'anime'
                        or any('动漫' in g or '动画' in g for g in c.get('genres', []))]
        else:
            filtered = []
            for c in cards:
                genres = c.get('genres', [])
                area = c.get('area', '')
                title = c.get('title', '')
                if tid in genres or tid in area or tid in title:
                    filtered.append(c)

        page_size = 20
        total = len(filtered)
        page_count = max(1, (total + page_size - 1) // page_size)
        start = (pg - 1) * page_size
        end = start + page_size
        page_items = filtered[start:end]

        videos = [self._format_card(c) for c in page_items]

        return {
            "list": videos,
            "page": pg,
            "pagecount": page_count,
            "limit": page_size,
            "total": total,
        }

    # ========== 详情页 ==========

    def detailContent(self, ids):
        """详情页: 调用 /v1/catalog/{id} 获取完整信息"""
        if isinstance(ids, str):
            ids = [ids]
        vod_id = ids[0]

        cached = self._detail_cache.get(vod_id)
        if cached:
            return {"list": [cached]}

        data = self._api_get('/v1/catalog/' + urllib.parse.quote(vod_id, safe=''))
        if not data:
            return {"list": []}

        title = data.get('title', '')
        pic = data.get('poster_url', '')
        year = str(data.get('year', ''))
        area = data.get('area', '')
        content_kind = data.get('content_kind', '')
        genres = data.get('genres', [])
        type_name = '/'.join(genres[:3]) if genres else content_kind
        actors = data.get('actors', [])
        actor = ', '.join(actors[:8]) if actors else '内详'
        directors = data.get('directors', [])
        director = ', '.join(directors[:4]) if directors else '内详'
        description = data.get('description', '')
        remarks = data.get('remarks', '')
        language = data.get('language', '')

        play_from = []
        play_url = []

        episodes = data.get('episodes', [])
        playback_groups = data.get('playback_groups', [])

        if episodes:
            if playback_groups:
                for group in playback_groups:
                    group_id = group.get('id', '')
                    group_label = group.get('label', group_id)
                    group_type = group.get('type', '')
                    ep_list = []

                    for ep in episodes:
                        token = ep.get('token', '')
                        ep_title = ep.get('title', '') or '第{}集'.format(ep.get('number', ''))
                        if token:
                            ep_list.append('{}${}'.format(ep_title, token))

                    if ep_list:
                        play_from.append(group_label)
                        play_url.append('#'.join(ep_list))
            else:
                ep_list = []
                for ep in episodes:
                    token = ep.get('token', '')
                    ep_title = ep.get('title', '') or '第{}集'.format(ep.get('number', ''))
                    if token:
                        ep_list.append('{}${}'.format(ep_title, token))
                if ep_list:
                    play_from.append('默认线路')
                    play_url.append('#'.join(ep_list))

        if not play_url:
            export_id = data.get('variant_id', '') or data.get('export_id', '')
            if export_id and str(export_id).isdigit():
                ep_data = self._api_get(
                    '/v1/catalog/{}/episodes'.format(export_id)
                )
                if ep_data and 'episodes' in ep_data:
                    ep_list = []
                    for ep in ep_data['episodes']:
                        token = ep.get('token', '')
                        ep_title = ep.get('title', '') or '第{}集'.format(ep.get('number', ''))
                        if token:
                            ep_list.append('{}${}'.format(ep_title, token))
                    if ep_list:
                        play_from.append('默认线路')
                        play_url.append('#'.join(ep_list))

        vod = {
            "vod_id": vod_id,
            "vod_name": title or '未知影片',
            "vod_pic": pic,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_remarks": remarks,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": description[:500] if description else '',
            "vod_play_from": '$$$'.join(play_from) if play_from else '默认线路',
            "vod_play_url": '$$$'.join(play_url) if play_url else '',
        }

        self._detail_cache[vod_id] = vod
        if len(self._detail_cache) > self._cache_max:
            self._detail_cache.pop(next(iter(self._detail_cache)))

        return {"list": [vod]}

    # ========== 搜索 ==========

    def searchContent(self, key, quick, pg="1"):
        """搜索: 调用 /v1/feed/home 带 q 参数"""
        pg = int(pg or 1)
        data = self._api_get('/v1/feed/home', {
            'q': key,
            'scope': 'public',
            'mode': 'page',
            'sections': '5',
            'cards': '20',
            'adult_confirmed': 'false',
        })

        if not data or 'sections' not in data:
            return {"list": []}

        videos = []
        seen = set()
        for sec in data.get('sections', []):
            for card in sec.get('cards', []):
                cid = card.get('id', '')
                title = card.get('title', '')
                if cid and cid not in seen and key.lower() in title.lower():
                    seen.add(cid)
                    videos.append(self._format_card(card))

        if len(videos) < 5:
            for sec in data.get('sections', []):
                for card in sec.get('cards', []):
                    cid = card.get('id', '')
                    if cid and cid not in seen:
                        seen.add(cid)
                        videos.append(self._format_card(card))
                        if len(videos) >= 20:
                            break
                if len(videos) >= 20:
                    break

        page_size = 20
        start = (pg - 1) * page_size
        end = start + page_size
        page_items = videos[start:end]

        return {"list": page_items}

    # ========== 播放解析 ==========

    def playerContent(self, flag, id, vipFlags):
        """
        播放解析: 通过 resolve API 获取 m3u8 URL

        修复: 旧端点 zy.baipiaozhe.com/v1/playback/yjapi/ 已失效 (404)
        新端点: player.baipiaozhe.com/v1/playback/resolve/{token}
        返回 JSON 含:
          - url: 最佳 m3u8 直链
          - line_options: 32 条备用线路 (含 provider_id, url)
          - current_episode: 当前剧集信息

        策略:
          1. 调用 resolve API 获取 m3u8
          2. 如果 url 是直链 m3u8, 直接返回
          3. 如果 url 是 resolve:// 或其他, 从 line_options 找可用 m3u8
          4. 通过 localProxy 代理 m3u8, 确保 enc.key 相对路径被改写为绝对路径
        """
        if not id:
            return {"parse": 1, "playUrl": "", "url": ""}

        token = id.strip()
        if token.startswith('http'):
            return self._build_play_result(token)

        # 检查缓存
        cached = self._play_cache.get(token)
        if cached:
            return self._build_play_result(cached)

        # 调用 resolve API
        resolve_url = '{}/v1/playback/resolve/{}'.format(self.PLAYBACK_HOST, token)
        resolve_headers = dict(self.header)
        resolve_headers['Referer'] = 'https://player.baipiaozhe.com/yjplayer.html'
        resolve_headers['Origin'] = 'https://player.baipiaozhe.com'

        m3u8_url = ''
        try:
            rsp = self.fetch(resolve_url, headers=resolve_headers, timeout=15)
            data = json.loads(rsp.text)

            # 优先使用主 url
            main_url = data.get('url', '')
            url_kind = data.get('url_kind', '')

            if main_url and main_url.startswith('http') and '.m3u8' in main_url:
                m3u8_url = main_url
            else:
                # 主 url 不是直链 m3u8 (可能是 resolve:// 或官方源)
                # 从 line_options 中找可用的 m3u8 直链
                line_options = data.get('line_options', [])
                for line in line_options:
                    line_url = line.get('url', '')
                    line_kind = line.get('url_kind', '')
                    if line_url and line_url.startswith('http') and line_kind == 'm3u8':
                        m3u8_url = line_url
                        break

                # 如果 line_options 没有, 回退到主 url
                if not m3u8_url and main_url and main_url.startswith('http'):
                    m3u8_url = main_url

        except Exception:
            pass

        if not m3u8_url:
            return {"parse": 1, "playUrl": "", "url": ""}

        # 缓存
        self._play_cache[token] = m3u8_url
        if len(self._play_cache) > self._cache_max:
            self._play_cache.pop(next(iter(self._play_cache)))

        return self._build_play_result(m3u8_url)

    def _build_play_result(self, m3u8_url):
        """构建播放结果

        通过 localProxy 代理 m3u8, 将 enc.key 相对路径改写为绝对路径。
        localProxy 会:
          1. 拉取 m3u8 原始内容
          2. 把 URI="enc.key" 改写为绝对 URL
          3. 把相对 TS 段改写为绝对 URL
          4. 返回改写后的 m3u8 给播放器
        """
        # 构造 localProxy URL, 让播放器通过代理获取改写后的 m3u8
        proxy_url = 'http://127.0.0.1:9978/proxy?do=kanju&url=' + urllib.parse.quote(m3u8_url, safe='')

        return {
            "parse": 0,
            "playUrl": "",
            "url": proxy_url,
            "header": {
                "User-Agent": self.header['User-Agent'],
            },
        }

    # ========== 本地代理 ==========

    def localProxy(self, param):
        """
        本地代理: 处理 m3u8 中的 enc.key 相对路径
        将 URI="enc.key" 改写为绝对路径, 确保 AES-128 密钥可被播放器获取

        兼容 FongMi/TV (传 dict) 和 WebHTV (传 JSON 字符串)
        """
        try:
            # WebHTV 的 Chaquo 包装器传 JSON 字符串, FongMi/TV 传 dict
            if isinstance(param, str):
                try:
                    param = json.loads(param)
                except Exception:
                    pass

            url = param.get('url', '') if isinstance(param, dict) else str(param)
            if not url:
                return [200, "video/MP2T", b"", {}]

            url = urllib.parse.unquote(url)
            # 去掉可能的多层编码
            if 'do=py&url=' in url:
                url = url.split('do=py&url=', 1)[1]
                url = urllib.parse.unquote(url)
            elif 'do=kanju&url=' in url:
                url = url.split('do=kanju&url=', 1)[1]
                url = urllib.parse.unquote(url)

            rsp_text = self._plain_get(url, timeout=30)
            if not rsp_text:
                return [200, "video/MP2T", b"", {}]

            # 判断是否是 m3u8
            is_m3u8 = '#EXTM3U' in rsp_text or '.m3u8' in url.lower()

            if is_m3u8:
                # 计算 m3u8 的基础目录
                base_url = url.split('?')[0]
                base_dir = base_url.rsplit('/', 1)[0]

                lines = rsp_text.split('\n')
                fixed_lines = []

                for line in lines:
                    stripped = line.strip()

                    # 处理 #EXT-X-KEY 行中的 URI
                    if stripped.startswith('#EXT-X-KEY') and 'URI="' in stripped:
                        uri_match = re.search(r'URI="([^"]+)"', stripped)
                        if uri_match:
                            key_uri = uri_match.group(1)
                            # 如果是相对路径, 改为绝对路径
                            if not key_uri.startswith('http'):
                                if key_uri.startswith('/'):
                                    parsed = urllib.parse.urlparse(url)
                                    abs_key = '{}://{}{}'.format(
                                        parsed.scheme, parsed.netloc, key_uri
                                    )
                                else:
                                    abs_key = '{}/{}'.format(base_dir, key_uri)
                                stripped = stripped.replace(
                                    'URI="{}"'.format(key_uri),
                                    'URI="{}"'.format(abs_key)
                                )
                        fixed_lines.append(stripped)
                    elif stripped.startswith('#'):
                        fixed_lines.append(stripped)
                    elif not stripped:
                        fixed_lines.append('')
                    else:
                        # TS segment: 如果是相对路径, 改为绝对路径
                        if not stripped.startswith('http'):
                            if stripped.startswith('/'):
                                parsed = urllib.parse.urlparse(url)
                                abs_ts = '{}://{}{}'.format(
                                    parsed.scheme, parsed.netloc, stripped
                                )
                            else:
                                abs_ts = '{}/{}'.format(base_dir, stripped)
                            fixed_lines.append(abs_ts)
                        else:
                            fixed_lines.append(stripped)

                content = '\n'.join(fixed_lines)
                return [200, "application/x-mpegURL", content.encode('utf-8'), {
                    'Content-Type': 'application/x-mpegURL',
                    'Access-Control-Allow-Origin': '*',
                }]

            # 非 m3u8 内容, 直接返回
            return [200, "video/MP2T", rsp_text.encode('utf-8'), {
                'Access-Control-Allow-Origin': '*',
            }]

        except Exception:
            return [200, "video/MP2T", b"", {}]
