import re, sys, json, time
from base.spider import Spider

sys.path.append('..')


class Spider(Spider):
    headers = {'User-Agent': 'okhttp/4.12.0'}

    # ═══ PHP 服务器地址（部署后将此地址改为你自己的服务器） ═══
    SERVER = 'http://154.12.21.149:8019/smcms/kksm_server.php'

    def init(self, extend=''):
        # 从服务器拉取配置（不含敏感密钥）
        try:
            cfg = self.fetch(f'{self.SERVER}?action=config', headers=self.headers).json()
            d = cfg.get('data', {})
            self.host = d.get('host', '').rstrip('/')
            self.proxy_host = d.get('proxy_host', '')
            self.proxy_ua = d.get('proxy_ua', 'Windows')
            self.proxy_headers = {'User-Agent': self.proxy_ua,
                                  'allowCrossProtocolRedirects': 'true'}
            self.CLASSES = d.get('classes', [])
            self.LINE_NAMES = d.get('line_names', {})
        except Exception as e:
            print(f'[smcms] init FAIL err={e}', file=sys.stderr)
            self.host = ''
            self.proxy_host = ''
            self.proxy_ua = 'Windows'
            self.proxy_headers = {'User-Agent': 'Windows',
                                  'allowCrossProtocolRedirects': 'true'}
            self.CLASSES = []
            self.LINE_NAMES = {}
        # tid 兼容映射
        self.TID_ALIAS = {'1': 'tvplay', '2': 'movie', '3': 'tvshow', '4': 'comic',
                          '5': 'oumeiju', '6': 'hanguoju', '7': 'movie_4k', '8': 'movie_ZB'}
        print('[smcms] init ok host=%s' % self.host, file=sys.stderr)

    @staticmethod
    def _clean(item):
        if isinstance(item, dict):
            item.pop('type', None)
            item.pop('type_1', None)
        return item

    # ─── 首页推荐 ────────────────────────────────────────────────────
    def homeVideoContent(self):
        try:
            tt = int(time.time())
            url = f"{self.host}/api.php/localhost/recommend?tt={tt}&type=1"
            data = self.fetch(url, headers=self.headers).json()
            vlist = data.get('data', []) or []
            return {'list': [self._clean(v) for v in vlist]}
        except Exception:
            return {'list': []}

    # ─── 首页分类 + 筛选项（类型/年份/地区/排序，来自 ac=flitter） ───
    def homeContent(self, filter):
        return {"class": self.CLASSES, "filters": self._get_filters() if filter else {}}

    def _get_filters(self):
        """从 ac=flitter 拉取各分类筛选项，转 TVBox filters 格式；进程内缓存"""
        if getattr(self, '_filters_cache', None) is not None:
            return self._filters_cache
        SORT_VALUES = [
            {"n": "综合",     "v": ""},
            {"n": "最近更新", "v": "updatedesc"},
            {"n": "热度优先", "v": "Hotdesc"},
            {"n": "评分最高", "v": "scoredesc"},
        ]
        filters = {}
        try:
            data = self._local_get('?&ac=flitter')
            for c in self.CLASSES:
                groups = []
                for f in data.get(c['type_id'], []) or []:
                    vals = [{"n": "全部", "v": ""}] + \
                           [{"n": str(v), "v": str(v)} for v in f.get('values', []) if v]
                    if len(vals) > 1:
                        groups.append({"key": str(f.get('field')), "name": str(f.get('name')), "value": vals})
                groups.append({"key": "sort", "name": "排序", "value": SORT_VALUES})
                filters[c['type_id']] = groups
        except Exception as e:
            print(f'[smcms] _get_filters FAIL err={e}', file=sys.stderr)
            for c in self.CLASSES:
                filters[c['type_id']] = [{"key": "sort", "name": "排序", "value": SORT_VALUES}]
        self._filters_cache = filters
        return filters

    # ─── localhost 系接口请求（加密响应由服务器解密） ──────────────────
    def _local_get(self, qs):
        """qs 形如 '?ac=list&class=tvplay&page=1'，返回解密后的 dict"""
        tt = int(time.time())
        sep = '&' if '?' in qs else '?'
        url = f"{self.host}/api.php/localhost/vod/{qs}{sep}tt={tt}"
        txt = self.fetch(url, headers=self.headers).text.strip()
        # 将 hex 加密文本发给 PHP 服务器解密
        r = self.fetch(f'{self.SERVER}?action=decrypt_local&hex={txt}', headers=self.headers).json()
        return r.get('data', {})

    def _vod_item(self, x, tid):
        """localhost list 条目 → TVBox vod"""
        m = re.search(r'ids=(\d+)', str(x.get('nextlink', '')))
        if not m:
            return None
        type_name = next((c['type_name'] for c in self.CLASSES if c['type_id'] == tid), '')
        if not type_name:
            type_name = self.LINE_NAMES.get(str(x.get('type', '')).upper(), '')
        return {
            'vod_id': m.group(1),
            'type_id': tid,
            'vod_name': str(x.get('title') or ''),
            'vod_pic': str(x.get('pic') or ''),
            'vod_remarks': str(x.get('state') or ''),
            'vod_score': str(x.get('score') or ''),
            'type_name': type_name,
        }

    # ─── 分类列表 ──────────────────────────────────────────────────
    def categoryContent(self, tid, pg, filter, extend):
        try:
            tid = self.TID_ALIAS.get(str(tid), str(tid))
            from urllib.parse import quote
            ext = extend or {}
            qs = f"?ac=list&class={tid}&page={pg}"
            sort = ext.get('sort', '')
            if sort:
                qs += f"&sort={quote(str(sort))}"
            for k in ('type', 'area', 'year'):
                v = ext.get(k)
                if v:
                    qs += f"&{k}={quote(str(v))}"
            d = self._local_get(qs)
            vlist = [v for v in (self._vod_item(x, tid) for x in d.get('data', []) or []) if v]
            print(f'[smcms] categoryContent tid={tid} pg={pg} list={len(vlist)} totalpage={d.get("totalpage")}', file=sys.stderr)
            return {"list": vlist, "page": int(pg),
                    "pagecount": int(d.get('totalpage') or 0),
                    "total": int(d.get('videonum') or 0)}
        except Exception as e:
            print(f'[smcms] categoryContent FAIL tid={tid} err={e}', file=sys.stderr)
            return {"list": [], "page": pg, "pagecount": 0, "total": 0}

    # ─── 搜索 ─────────────────────────────────────────────────────
    def searchContent(self, key, quick, pg="1"):
        try:
            from urllib.parse import quote
            d = self._local_get(f"?ac=list&wd={quote(str(key))}&page={pg}")
            vlist = [v for v in (self._vod_item(x, '') for x in d.get('data', []) or []) if v]
            return {'list': vlist, 'page': pg}
        except Exception as e:
            print(f'[smcms] searchContent FAIL err={e}', file=sys.stderr)
            return {'list': [], 'page': pg}

    # ─── 详情 ─────────────────────────────────────────────────────
    def detailContent(self, ids):
        try:
            tt = int(time.time())
            url = f"{self.host}/api.php/localhost/vod/?ac=detail&ids={ids[0]}&tt={tt}"
            d = self.fetch(url, headers=self.headers).json()

            videolist = d.get('videolist', {}) or {}
            play_from, play_url = [], []
            for line, eps in videolist.items():
                play_from.append(self.LINE_NAMES.get(line, line))
                segs = []
                for ep in eps:
                    title = str(ep.get('title', '')).strip() or '播放'
                    addr = str(ep.get('url', '')).strip()
                    segs.append(f"{title}${addr}")
                play_url.append('#'.join(segs))

            def to_str(v):
                if isinstance(v, list):
                    return ','.join(str(x) for x in v)
                return '' if v is None else str(v)

            vod = {
                'vod_id': str(d.get('id', '')),
                'vod_name': to_str(d.get('title', '')),
                'vod_pic': to_str(d.get('img_url', '')),
                'vod_remarks': to_str(d.get('trunk', '')),
                'vod_year': to_str(d.get('pubtime', '')),
                'vod_area': to_str(d.get('area', '')),
                'vod_score': to_str(d.get('season_num', '')),
                'vod_actor': to_str(d.get('actor', '')),
                'vod_director': to_str(d.get('director', '')),
                'type_name': to_str(d.get('type', '')),
                'vod_content': to_str(d.get('intro', '')),
                'vod_play_from': '$$$'.join(play_from),
                'vod_play_url': '$$$'.join(play_url),
            }
            return {'list': [vod]}
        except Exception as e:
            import traceback
            print(f'[smcms] detailContent FAIL err={e}\n{traceback.format_exc()}', file=sys.stderr)
            return {'list': []}

    # ─── 播放（解密请求交给 PHP 服务器） ──────────────────────────────
    def playerContent(self, flag, video_id, vipFlags):
        from urllib.parse import unquote
        try:
            video_id = unquote(str(video_id))
        except Exception:
            video_id = str(video_id)
        video_id = video_id.strip()
        print(f'[smcms] playerContent flag={flag} video_id={video_id[:80]}', file=sys.stderr)

        # 1) 已是真实直链 → 直接播放
        if re.search(r'\.(m3u8|mp4|flv|ts)(\?|$)', video_id, re.IGNORECASE):
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': video_id, 'header': self.headers}

        # 2) 纯加密 hex 串 → 调用 PHP 服务器解密
        if re.fullmatch(r'[0-9a-fA-F]{32,}', video_id):
            real = self._decrypt_play(video_id)
            if real:
                return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': real, 'header': self.headers}
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': self.headers}

        # 3) 已是 7001 中转链接 → 提取 hex 解密
        if '7001/Client/' in video_id and 'url=' in video_id:
            hex_part = video_id.split('url=', 1)[1].split('&', 1)[0]
            if re.fullmatch(r'[0-9a-fA-F]{32,}', hex_part):
                real = self._decrypt_play(hex_part)
                if real:
                    return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': real, 'header': self.headers}
            return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': self.headers}

        # 4) 其它：返回空
        return {'parse': 0, 'jx': 0, 'playUrl': '', 'url': '', 'header': self.headers}

    def _decrypt_play(self, play_hex):
        """调用 PHP 服务器解密播放地址"""
        try:
            from urllib.parse import quote
            r = self.fetch(f'{self.SERVER}?action=decrypt_play&hex={quote(play_hex)}',
                           headers=self.headers).json()
            url = r.get('data', {}).get('url', '')
            print(f'[smcms] hex={play_hex[:20]}... -> {url[:60]}', file=sys.stderr)
            return url
        except Exception as e:
            print(f'[smcms] _decrypt_play FAIL hex={play_hex[:20]}... err={e}', file=sys.stderr)
            return ''

    def getName(self):
        pass

    def localProxy(self, param):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass
