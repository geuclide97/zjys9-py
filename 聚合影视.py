# -*- coding: utf-8 -*-
# 聚合影视 Spider (av.telstra.com.cv)
# 兼容 FongMi/TV (T3) 标准 JSON API
#
# 数据源: 聚合影视站 JSON API (聚合 90+ 影视源, 统一 TVBox 协议)
# 站点: https://av.telstra.com.cv
# 默认源: iyf (爱壹帆影视), 可通过 ext {"source": "xxx"} 切换其它源
# 接口:
#   /api/v1/spiders/{key}/home
#   /api/v1/spiders/{key}/category?tid=&pg=
#   /api/v1/spiders/{key}/detail?id=
#   /api/v1/spiders/{key}/search?wd=&pg=
#   /api/v1/spiders/{key}/play?flag=&id=

import sys
import json
import urllib.parse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq

    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=20, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    host = 'https://av.telstra.com.cv'

    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    }

    source = 'iyf'  # 默认源: 爱壹帆影视

    def getName(self):
        return '聚合影视'

    def init(self, extend=''):
        self.source = 'iyf'
        if extend:
            try:
                if isinstance(extend, str):
                    e = json.loads(extend)
                else:
                    e = extend
                if isinstance(e, dict) and e.get('source'):
                    self.source = str(e['source'])
            except Exception:
                pass

    def isVideoFormat(self, url):
        return any(x in url for x in ['.m3u8', '.mp4', '.flv', '.avi', '.mkv', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ===== 请求封装 =====

    def _api(self, path, params=None):
        url = '%s/api/v1/spiders/%s%s' % (self.host, self.source, path)
        if params:
            parts = []
            for k, v in params.items():
                parts.append('%s=%s' % (k, urllib.parse.quote(str(v))))
            url = url + '?' + '&'.join(parts)
        r = self.fetch(url, headers=self.header)
        text = r.text if hasattr(r, 'text') else r.content.decode('utf-8', 'ignore')
        return json.loads(text)

    # ===== 首页 =====

    def homeContent(self, filter):
        try:
            data = self._api('/home')
            classes = []
            for c in data.get('categories', []):
                classes.append({
                    'type_id': str(c.get('tid', '')),
                    'type_name': str(c.get('name', '')),
                })
            return {'class': classes, 'filters': {}}
        except Exception:
            return {'class': [], 'filters': {}}

    def homeVideoContent(self):
        try:
            data = self._api('/home')
            cats = data.get('categories', [])
            if not cats:
                return {'list': []}
            d = self._api('/category', {'tid': cats[0].get('tid', ''), 'pg': 1})
            return {'list': self._to_list(d.get('list', []))}
        except Exception:
            return {'list': []}

    # ===== 列表转换 =====

    def _to_list(self, items):
        out = []
        for it in items:
            out.append({
                'vod_id': str(it.get('id', '')),
                'vod_name': it.get('name', ''),
                'vod_pic': it.get('pic', ''),
                'vod_remarks': it.get('remarks', ''),
                'type_name': it.get('category', ''),
                'vod_year': str(it.get('year') or ''),
                'vod_area': it.get('area', ''),
                'vod_actor': it.get('actor', ''),
                'vod_director': it.get('director', ''),
            })
        return out

    # ===== 分类 =====

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
            data = self._api('/category', {'tid': tid, 'pg': pg})
            return {
                'page': pg,
                'pagecount': int(data.get('pagecount') or 1),
                'limit': len(data.get('list', [])),
                'total': int(data.get('total') or 0),
                'list': self._to_list(data.get('list', [])),
            }
        except Exception:
            return {'page': pg, 'pagecount': 1, 'limit': 0, 'total': 0, 'list': []}

    # ===== 详情 =====

    def detailContent(self, ids):
        try:
            vid = ids[0] if isinstance(ids, list) else str(ids)
            data = self._api('/detail', {'id': vid})

            groups = []  # [[flag, [name$id, ...]], ...]
            for ep in data.get('episodes', []):
                flag = ep.get('flag', '') or '默认'
                name = ep.get('name', '') or '正片'
                eid = ep.get('id', '')
                item = '%s$%s' % (name, eid)
                found = False
                for g in groups:
                    if g[0] == flag:
                        g[1].append(item)
                        found = True
                        break
                if not found:
                    groups.append([flag, [item]])

            play_from = '$$$'.join([g[0] for g in groups])
            play_url = '$$$'.join(['#'.join(g[1]) for g in groups])

            vod = {
                'vod_id': str(data.get('id', vid)),
                'vod_name': data.get('name', ''),
                'vod_pic': data.get('pic', ''),
                'type_name': data.get('category', ''),
                'vod_year': str(data.get('year') or ''),
                'vod_area': data.get('area', ''),
                'vod_director': data.get('director', ''),
                'vod_actor': data.get('actor', ''),
                'vod_content': data.get('content', ''),
                'vod_remarks': data.get('remarks', ''),
                'vod_play_from': play_from,
                'vod_play_url': play_url,
            }
            return {'list': [vod]}
        except Exception:
            return {'list': []}

    # ===== 搜索 =====

    def searchContent(self, key, quick, pg=1):
        try:
            pg = int(pg or 1)
            data = self._api('/search', {'wd': key, 'pg': pg})
            return self._to_list(data.get('list', []))
        except Exception:
            return []

    # ===== 播放 =====

    def playerContent(self, flag, id, vipFlags):
        try:
            data = self._api('/play', {'flag': flag, 'id': id})
            url = data.get('url', '')
            header = data.get('header', {})
            if url.startswith('/'):
                url = self.host + url
            if not header:
                header = self.header
            return {
                'parse': int(data.get('parse') or 0),
                'url': url,
                'header': header,
            }
        except Exception:
            return {}
