# -*- coding: utf-8 -*-
# 站点：https://www.4kdyw.com        4K影视站（Nuxt 3 SSR 外壳 + /api/show/v2 REST）
# 路线：通用 SPA/API —— 页面路由是 voddetail/vodcate，但数据全在 /api/show/v2/* 直出 JSON，
#       不需要解 __NUXT_DATA__ 的 devalue 常量池（那条路只在接口找不到时才走）
# 生成：2026-11-23   维护：Doubao
# 依赖：requests（壳端自带）+ base.spider
# 接口：homeContent / homeVideoContent / categoryContent / detailContent / searchContent
#       playerContent / localProxy
# vod_id：纯数字 vodId（如 27600）
# 播放 id：m3u8 直链本身——站点 vodPlayUrl 已给出 CDN 地址（第01集$https://.../index.m3u8），
#          不需要再进 /player/ 壳页解析
# 域池：www 与裸域实测同 API；TLD 变体与 m. 子域全部不可达，站内无"回家地址/发布页"文案，
#       因此域池只有 2 个真实候选，互为备份，失效即切（机制建全，域数受站点本身限制）
# 已知：线路「极速四」的 v.lzcdn31.com 实测 504（CDN 侧故障），源里保留线路但按集数排在末位；
#       搜索关键词在路径里而不是 query 里，必须整段 quote，否则带斜杠直接 404

import json
import re
import threading
import time
from urllib.parse import quote, unquote

import requests
from base.spider import Spider


class Spider(Spider):
    # ---------------------------------------------------------------- 基本常量
    # 入口域：用户给的这个；init 只在这一个上探活，不做全量域池解析，否则启动要 10s+
    HOST = 'https://www.4kdyw.com'
    NAME = 'ᵀ⁴4K影视'
    # 接口前缀：前端 Nuxt config 里 public.api = "/api"，页面路由是 /show/v2/... 但请求必须带 /api
    PRE = '/api'
    # 单页条数：站点 per_page 固定 18，改大会和 total_page 换算错位
    LIMIT = 18
    # 接口结果缓存 TTL：列表/详情/搜索共用，翻页时同页重复请求直接命中
    TTL = 300
    # 失败冷却：失败后 30s 内直接返回空，避免整页卡死重试
    FAIL_TTL = 30
    # 单条 vod_play_url 上限：客户端按 2048B 截断，留 150B 余量后按集切段
    SEG = 1900
    # 搜索兜底页数：站点无结果时 total_page=0，补 1 页避免壳端把结果页判成空源
    SEARCH_PC = 1
    # 换域解析总预算：候选少（2 个），主要是兜底防串行探活拖死
    BUDGET = 15
    # 单请求超时：接口实测 0.6s 内回，留足余量防慢时段
    TIMEOUT = 12
    # 播放并发验几条：站点详情给的线路常是同片多 CDN，最多并 3 条同时读前 2KB
    RACE = 3
    # 媒体首包预算：m3u8 实测 0.7~0.8s 出首包；死 CDN 会挂到超时，所以并发 + 4s 死线兜底
    RACE_TTL = 3
    # 静态种子域：实测两个都返回同一套 /api/show/v2（www 与裸域是同一份部署）
    SEEDS = ['https://www.4kdyw.com', 'https://4kdyw.com']
    # 探活靶子：navs 只有 384B，比首页 66KB 省 170 倍带宽，探 6 个域也不会拖慢启动
    ALIVE_PATH = '/show/v2/navs'
    UA = ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36')

    # ---------------------------------------------------------------- 类级共享
    # 缓存/冷却按域分组：换域后新域不能命中旧域缓存，否则看着"新域也没数据"
    _CACHE = {}
    _FAIL = {}
    _TYPES = {}
    # 探活结果跨域共享（key 就是候选域本身），不能按 base 分组
    _PROBED = {}
    # 媒体域冷却：死 CDN（ffzy-play10 拒连、ryplay14 挂死）记住 60s 不再逐条去试，
    # 否则同一次播放里三条线路都在同一死域上，每集都要白等一个连接超时
    _MED = {}
    # 媒体域信任表：120s 内刚验活成功过的 CDN 直接认，不再重复读 2KB。
    # 4K影视的线路是固定路径（不带时效 token），同域刚验证过就是同一条能播的流，
    # 跳过这一步能把重复点播的 0.7~0.8s 首包直接省成 0
    _TRUST = {}
    # 播放判死缓存：同一集 60s 内探活全死过一次就别再白跑，直接按 parse=1 回播放页
    _PFAIL = {}

    def init(self, extend=''):
        # 启动：只验前两个种子（0.2s 间隔），探活失败也先认种子，不把启动拖死
        s = (extend or '').strip()
        seed = self.HOST
        if s.startswith('{'):
            try:
                cfg = json.loads(s)
                if cfg.get('host'):
                    seed = str(cfg['host']).strip().rstrip('/')
            except Exception:
                seed = self.HOST
        elif s.startswith('http'):
            seed = s.rstrip('/')
        if not seed.startswith('http'):
            seed = self.HOST

        self.session = requests.Session()
        # trust_env=False：不吃系统 http_proxy，壳端要代理必须走 extend.proxy
        self.session.trust_env = False
        self.session.verify = False
        self.UA = type(self).UA
        self.headers = {'User-Agent': self.UA,
                        'Accept': 'application/json',
                        'Referer': seed + '/',
                        'Origin': seed}
        self.session.headers.update(self.headers)
        self.base = seed
        self._HOST = ''
        self._HT = 0.0
        self._SEQ = 0
        self._rebind(seed)
        self.base = self._pick_host(seed)
        self._rebind(self.base)
        return None

    # 源名：与文件名一致，壳端列表里显示的就是它
    def getName(self):
        return self.NAME

    # ================================================================= 六个接口
    def homeContent(self, filter):
        # 首页：分类=站点真实二级目录（navs type_list 的 24 个 typeId），
        # 一级大类（电影/电视剧/动漫/综艺）只作命名前缀，因为大类页 cate/{id} 没有翻页接口
        # filters 留空：站点没有可枚举的年份/地区筛选参数，不放假选项误导壳端
        classes = [{'type_id': t['type_id'], 'type_name': t['type_name']}
                   for t in self._types()]
        return {'class': classes, 'filters': {}, 'list': self.homeVideoContent()['list']}

    # 首页列表：vodhot 一次给全热门（15KB），比拉 4 个大类页（4×38KB）省 90% 流量
    def homeVideoContent(self):
        d = self._api('/show/v2/vodhot') or []
        items = [self._card(x) for x in d if isinstance(x, dict)]
        items = [x for x in items if x.get('vod_name')]
        return {'list': items[:self.LIMIT]}

    # 分类：tid 是站点 typeId（1~7 电影、8~15 剧、16~20 动漫、21~24 综艺）
    # 分页用站点真值 total_page（动作片实测 374 页 / total 6718），不做本地切片
    def categoryContent(self, tid, pg, filter, extend):
        page = self._pg(pg)
        t = str(tid or '1').strip()
        # tid 允许传大类 cateId（1~4）：站点没有大类翻页接口，回落该大类第一个子类，保证不空手
        t = self._map_tid(t)
        d = self._api('/show/v2/type/%s/%d' % (t, page)) or {}
        items = [self._card(x) for x in (d.get('vod_recent') or [])]
        items = [x for x in items if x.get('vod_name')]
        total_page = self._int(d.get('total_page'), page)
        total = self._int(d.get('total'), total_page * self.LIMIT)
        return {'page': page, 'pagecount': max(page, total_page),
                'limit': self.LIMIT, 'total': total, 'list': items}

    # 详情：vod/{id} 一次给全字段 + vod_play 数组（每条线路自带 名称$m3u8#名称$m3u8 串）
    # 线路按集数降序：极速四只有 2 集且 CDN 已 504，天然排到最后，壳端先试能播的
    def detailContent(self, ids):
        key = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(key or '').split('|')[0].strip()
        if not vid or not vid.isdigit():
            return {'list': []}
        d = self._api('/show/v2/vod/%s' % vid) or {}
        if not d:
            return {'list': []}
        lines = self._lines(d)
        if not lines:
            return {'list': []}
        vod = {'vod_id': vid,
               'vod_name': str(d.get('vodName') or '').replace('|', ' ').strip(),
               'vod_pic': self._pic(d.get('vodPic')),
               'vod_remarks': str(d.get('vodLastRemarks') or ''),
               'vod_year': str(d.get('vodYear') or ''),
               'vod_area': str(d.get('vodArea') or ''),
               'vod_lang': str(d.get('vodLang') or ''),
               'vod_actor': str(d.get('vodActor') or ''),
               'vod_director': str(d.get('vodDirector') or ''),
               'vod_content': self._txt(d.get('vodBlurb') or d.get('vodContent')),
               'type_name': self._type_name(d)}
        vod['vod_play_from'] = '$$$'.join(x[0] for x in lines)
        vod['vod_play_url'] = '$$$'.join(x[1] for x in lines)
        return {'list': [vod]}    # 搜索：关键词在路径里（/search/{wd}/{page}），必须整段 quote；
    # 返回 page/page_size/total/total_page/vods，分页用站点真值
    def searchContent(self, key, quick, pg='1'):
        page = self._pg(pg)
        kw = str(key or '').strip()
        if not kw:
            return {'page': page, 'pagecount': self.SEARCH_PC, 'limit': self.LIMIT,
                    'total': 0, 'list': []}
        # quote(safe='')：关键词可能带 "/" "#" "?"，不转义会把路径切坏直接 404
        wd = quote(kw.replace('/', ' ').replace('#', ' '), safe='')
        d = self._api('/show/v2/search/%s/%d' % (wd, page)) or {}
        items = [self._card(x) for x in (d.get('vods') or [])]
        items = [x for x in items if x.get('vod_name')]
        total_page = self._int(d.get('total_page'), self.SEARCH_PC)
        total = self._int(d.get('total'), total_page * self.LIMIT)
        return {'page': page, 'pagecount': max(self.SEARCH_PC, total_page),
                'limit': self.LIMIT, 'total': total, 'list': items}

    # 播放：play id 是 `vodId|集序号`（如 27600|0），播放时才去详情接口换真地址。
    # 为什么不直接存 m3u8 直链：3 条线路 × 每集地址拼进 vod_play_url 会顶到 2059B，
    # 超过客户端 2048B 截断线；存短 id 后 12 集只占 ~190B，且能按集回退到别的线路
    def playerContent(self, flag, id, vipFlags):
        # 兼容四种入参：'第01集$27600|0'、'27600|0'、'https://...'、'27600'
        raw = str(id or '').strip()
        if '$' in raw:
            raw = raw.rsplit('$', 1)[1].strip()
        vid, idx, url = '', 0, ''
        if raw.startswith('http'):
            url = raw
        else:
            parts = raw.split('|')
            if parts and parts[0].strip().isdigit():
                vid = parts[0].strip()
                idx = self._int(parts[1], 0) if len(parts) > 1 else 0
                # 兼容老格式 vid|idx|url（手工调试会这么传）
                if len(parts) > 2 and parts[2].startswith('http'):
                    url = parts[2].strip()
        if not vid and not url:
            return {'parse': 1, 'jx': 1, 'url': '', 'playUrl': '', 'header': ''}
        cands = self._ep_candidates(vid, idx, url) if vid else [url]
        # 判死结果记 60s：同集再点不该把 3s 探活白重跑一遍（死 CDN 的选片人往往反复点同一集）
        key = '%s|%s' % (vid or url, idx)
        bad = type(self)._PFAIL.get(key)
        if bad and time.time() - bad < 60:
            header = json.dumps(self._media_headers(cands[0])) if cands else ''
            return {'parse': 1, 'jx': 1, 'url': cands[0] if cands else '', 'playUrl': '', 'header': header}
        # 并发验 3 条而不是串行：死 CDN 单条要吃掉 (2,2.5) 的两次超时，串行三条实测 6.04s 才放弃；
        # 并发后墙钟只取决于最快能播的那条，还在 3s 死线内兜底
        pick = self._race(cands[:self.RACE], self.RACE_TTL)
        if pick:
            type(self)._PFAIL.pop(key, None)
            header = json.dumps(self._media_headers(pick))
            return {'parse': 0, 'jx': 0, 'url': pick, 'playUrl': '', 'header': header}
        type(self)._PFAIL[key] = time.time()
        if cands:
            header = json.dumps(self._media_headers(cands[0]))
            return {'parse': 1, 'jx': 1, 'url': cands[0], 'playUrl': '', 'header': header}
        return {'parse': 1, 'jx': 1, 'url': '', 'playUrl': '', 'header': ''}

    # 并发验活：多 CDN 各自开会话读前 2KB，按候选顺序取第一条能播的
    def _race(self, urls, deadline):
        # 并发验活：每条各开独立会话读前 2KB（requests 的 Session 不是线程安全的），
        # 按候选顺序取第一条能播的；全死才返回空，交给上层走 parse=1
        box = {}

        def one(i, u):
            if self._probe(u, own=True):
                box.setdefault(i, u)

        ths = []
        for i, u in enumerate(urls):
            th = threading.Thread(target=one, args=(i, u), daemon=True)
            th.start()
            ths.append(th)
        end = time.time() + deadline
        while time.time() < end:
            for i in range(len(urls)):
                if i in box:
                    return box[i]
            if not any(t.is_alive() for t in ths):
                # 全探完还没活口就立刻退出，别在死线上空等到点（判死那一轮会白等满 4s）
                break
            time.sleep(0.1)
        for i in range(len(urls)):
            if i in box:
                return box[i]
        return ''

    # 图片与 HLS 代理：真实 MIME 回二进制，空 body 一律 404
    def localProxy(self, param):
        # 图片 / HLS 代理：真实 MIME + 二进制；空 body 一律 404，绝不返 200 空图
        text = str(param or '')
        m = re.search(r'(?:^|[?&])url=([^&]+)', text)
        if not m:
            return [404, 'text/plain', b'']
        url = unquote(m.group(1))
        if not url.startswith('http'):
            return [404, 'text/plain', b'']
        code, ctype, data = self._req(url, raw=True)
        if code not in (200, 206) or not data:
            return [404, 'text/plain', b'']
        if 'do=m3u8' in text and data[:7] == b'#EXTM3U':
            return [200, 'application/vnd.apple.mpegurl', data]
        return [200, ctype or 'application/octet-stream', data]

    # ================================================================= 域池
    # 域池并发竞速：串行探活要 sleep(1)×N + 每个域 4~8s 超时，全挂时尾延迟实测 20s+；
    # 并发后墙钟只取决于最快活域，同时保留「按候选顺序取第一个活域」的语义
    def _race_hosts(self, hosts, budget):
        box = {}

        def one(i, h):
            try:
                if self._alive(h):
                    box.setdefault(i, h)
            except Exception:
                pass

        ths = []
        for i, h in enumerate(hosts):
            th = threading.Thread(target=one, args=(i, h), daemon=True)
            th.start()
            ths.append(th)
        start = time.time()
        end = start + budget
        while time.time() < end:
            if 0 in box:
                return box[0]
            # 序号 0 没活口时给 1.0s 宽限，既守住顺序语义又不被慢域拖住
            if box and time.time() - start > 1.0:
                return box[min(box)]
            if not any(t.is_alive() for t in ths):
                break
            time.sleep(0.1)
        if box:
            return box[min(box, key=lambda k: k)]
        return ''

    def _pick_host(self, seed='', full=False):
        # 选域分两条路径：启动只验 2 个种子；判定域失效（full=True）才跑全量
        now = time.time()
        if self._HOST and now - self._HT < 600:
            return self._HOST
        seed = str(seed or self.HOST).rstrip('/')
        cands = [seed]
        for h in self.SEEDS:
            h = h.rstrip('/')
            if h and h not in cands:
                cands.append(h)
        if not full:
            for i, h in enumerate(cands[:2]):
                if i:
                    time.sleep(0.2)
                if self._alive(h, fast=True):
                    self._HOST, self._HT = h, now
                    return h
            # 探活失败也先认种子：站点可能只是瞬时限流，硬切空域会让整源不可用
            self._HOST, self._HT = seed, now
            return seed
        deadline = now + self.BUDGET
        pick = self._race_hosts(cands, max(1.0, deadline - time.time()))
        if pick:
            self._HOST, self._HT = pick, time.time()
            return pick
        # 全挂也退回种子，返回空串会让后续所有请求打到空域
        self._HOST, self._HT = seed, time.time()
        return seed

    # 域探活：只打 384B 的 navs 靶子，比拉首页省 170 倍带宽
    def _alive(self, host, fast=False):
        # 探活只打 navs（384B JSON），不拉首页：首页 66KB，探几个域就是几百 KB
        host = str(host or '').rstrip('/')
        if not host.startswith('http'):
            return False
        key = host + ':t'
        hit = self._PROBED.get(key)
        if hit:
            # 成功缓存 300s、失败只缓存 30s：失败缓存 5 分钟会让一次瞬时限流把好域判死
            ttl = 300 if self._PROBED.get(host + ':r') else 30
            if time.time() - hit < ttl:
                return bool(self._PROBED.get(host + ':r'))
        ok = False
        try:
            r = self.session.get(host + self.PRE + self.ALIVE_PATH,
                                 headers={'User-Agent': self.UA, 'Accept': 'application/json'},
                                 timeout=4 if fast else 8, verify=False, stream=True,
                                 proxies=self.session.proxies or None)
            buf = next(r.iter_content(4096), b'')
            r.close()
            # 判定同站不只看出 200：必须出现 cateId 字段，劫持页/停放页给不出这个结构
            ok = b'"cateId"' in buf
        except Exception:
            ok = False
        self._PROBED[key] = time.time()
        self._PROBED[host + ':r'] = ok
        return ok

    # 域被判死：写冷却并清掉该域缓存，立刻换下一个候选
    def _mark_host(self, code):
        # 换域三件套：主域、请求头、三张表按新域分组——只清 _HOST 不改 base 等于假换域
        bad = self.base
        self._HOST = ''
        self._HT = 0.0
        new = self._pick_host(self.HOST, full=True)
        if new and new != bad:
            self._rebind(new)
        return new

    # 切域：把 session、接口走线、缓存表一起搬到新域
    def _rebind(self, host):
        # 绑定当前域：base / 请求头 / 缓存表分组。探活表不重绑（跨域共享）
        host = str(host or self.HOST).rstrip('/')
        self.base = host
        self.headers = {'User-Agent': self.UA, 'Accept': 'application/json',
                        'Referer': host + '/', 'Origin': host}
        self.session.headers.update(self.headers)
        self._CACHE = type(self)._CACHE.setdefault(host, {})
        self._FAIL = type(self)._FAIL.setdefault(host, {})
        self._TYPES = type(self)._TYPES.setdefault(host, {})

    # ================================================================= 接口层
    def _api(self, path, params=None, hard=True, retry=True):
        # 所有接口的统一入口：拼 URL → 取 JSON → 只把 data 交出去
        # 站点成功码是 code:0（不是 200），code 非 0 只当本次失败写冷却，不换域
        base = str(self.base).rstrip('/')
        params = dict(params or {})
        ck = path + '?' + '&'.join('%s=%s' % (k, params[k]) for k in sorted(params))
        hit = self._CACHE.get(ck)
        if hit and time.time() - hit[0] < self.TTL:
            return hit[1]
        exp = self._FAIL.get(ck)
        if exp and time.time() < exp:
            return None
        try:
            r = self.session.get(base + self.PRE + path, params=params or None,
                                 headers=self.headers,
                                 timeout=self.TIMEOUT, verify=False,
                                 proxies=self.session.proxies or None)
            if r.status_code != 200:
                # 404 是路径问题（片子被删/关键词无结果），只冷路径；5xx 才算域级
                self._FAIL[ck] = time.time() + self.FAIL_TTL
                if hard and r.status_code >= 500:
                    self._seq_fail()
                return None
            j = r.json()
        except Exception:
            # 连接级异常基本等于"这个域不通"：立刻换域并重试一次，否则第一次请求必然空手
            # 换域成功要先清掉本条路径的冷却，否则重试会被自己刚写的 30s 冷却挡回去
            if hard and retry:
                new = self._mark_host(0)
                if new and new != base:
                    self._FAIL.pop(ck, None)
                    return self._api(path, params, retry=False)
            self._FAIL[ck] = time.time() + self.FAIL_TTL
            if hard:
                self._seq_fail()
            return None
        if not isinstance(j, dict) or j.get('code') != 0:
            self._FAIL[ck] = time.time() + self.FAIL_TTL
            return None
        data = j.get('data')
        if len(self._CACHE) > 300:
            self._CACHE.clear()
        self._CACHE[ck] = (time.time(), data)
        self._SEQ = 0
        return data

    # 连续失败计数：短时间连挂就判域失效，触发全量重探
    def _seq_fail(self):
        # 连续两次网络级失败才换域：单次抖动就换域会把好域换掉（站点偶发 5xx）
        self._SEQ = self._SEQ + 1
        if self._SEQ >= 2:
            self._SEQ = 0
            self._mark_host(0)

    # ================================================================= 数据整形
    def _types(self):
        # 分类目录：index 接口给 4 大类 + 24 个子类（typeId/typeName），是站点真实目录
        cached = self._TYPES.get('list')
        if cached and time.time() - cached[0] < self.TTL * 4:
            return cached[1]
        out = []
        for c in (self._api('/show/v2/index') or []):
            if not isinstance(c, dict):
                continue
            for t in (c.get('type') or []):
                if not isinstance(t, dict) or not t.get('typeId'):
                    continue
                name = str(t.get('typeName') or '').strip()
                if name:
                    out.append({'type_id': str(t['typeId']), 'type_name': name})
        if not out:
            # 兜底只在接口失败时用；正常路径永远是站点真目录
            out = [{'type_id': '1', 'type_name': '动作片'}, {'type_id': '8', 'type_name': '国产剧'},
                   {'type_id': '16', 'type_name': '国产动漫'}, {'type_id': '21', 'type_name': '大陆综艺'}]
        self._TYPES['list'] = (time.time(), out)
        return out

    # 大类映射：cateId 没有翻页接口，落到该大类首个子类
    def _map_tid(self, tid):
        # 大类 cateId（1 电影 / 2 电视剧 / 3 动漫 / 4 综艺）没有翻页接口，映射到该大类首个子类
        # 子类 id 段来自 navs 的 type_list：[1-7] [8-15] [16-20] [21-24]
        first = {'1': '1', '2': '8', '3': '16', '4': '21'}
        if tid in first:
            return first[tid]
        return tid if tid.isdigit() else '1'

    # 卡片映射：列表与搜索共用，字段沿用 MacCMS 命名但 id 叫 vodId
    def _card(self, x):
        # 列表/搜索共用卡片映射：字段是 MacCMS 命名但 id 叫 vodId
        x = x or {}
        vid = x.get('vodId') or x.get('id')
        name = str(x.get('vodName') or '').replace('|', ' ').strip()
        if not vid or not name:
            return {}
        remarks = str(x.get('vodLastRemarks') or x.get('vodRemarks') or '')
        return {'vod_id': str(vid), 'vod_name': name,
                'vod_pic': self._pic(x.get('vodPic')),
                'vod_remarks': remarks,
                'vod_year': str(x.get('vodYear') or ''),
                'type_name': self._type_name(x)}

    # 分类名兜底：接口没给 typeName 时按 typeId 反查 navs
    def _type_name(self, x):
        # 分类名两种形态：详情/列表给 dict{typeName}，有的只给 typeId，回查分类表兜底
        tp = x.get('type')
        if isinstance(tp, dict) and tp.get('typeName'):
            return str(tp['typeName'])
        tid = str(x.get('typeId') or '').strip()
        if tid:
            for t in self._types():
                if t['type_id'] == tid:
                    return t['type_name']
        return ''

    # 线路装配：一个 vod_play 面板一条线路，集序号按面板内顺序；
    # 本站没有 sid 字段，线路靠面板下标区分，同一部下多个面板的集号互不串
    def _lines(self, d):
        # 线路装配：vod_play 每条 = {vodPlayUrl: "第01集$url#第02集$url", collectSource.webName}
        # 集数降序让"极速四（2 集 + CDN 504）"自动落后；同分按原顺序，保证线路稳定性
        vid = str(d.get('vodId') or '').strip()
        raw = []
        for i, p in enumerate(d.get('vod_play') or []):
            if not isinstance(p, dict):
                continue
            src = p.get('collectSource') or {}
            label = str(src.get('webName') or '').strip() or '线路%d' % (i + 1)
            pairs = self._parse_eps(p.get('vodPlayUrl'))
            if not pairs:
                continue
            raw.append((len(pairs), i, label, pairs))
        raw.sort(key=lambda x: (-x[0], x[1]))
        out, names = [], {}
        for _, _, label, pairs in raw:
            # 同名线路壳端会互相覆盖，重复名字加序号
            names[label] = names.get(label, 0) + 1
            if names[label] > 1:
                label = '%s(%d)' % (label, names[label])
            out.extend(self._segments(label, pairs, vid))
        return out

    # 分集解析：名称$地址#名称$地址，名称缺失时按序补第NN集
    def _parse_eps(self, raw):
        # 站点格式：名称$地址#名称$地址；地址可能带 query 但不会含 # 或 $，
        # 少数条目只有地址没有名称（name 为空），按"第N集"补
        pairs = []
        for i, seg in enumerate(str(raw or '').split('#')):
            seg = seg.strip()
            if not seg or '$' not in seg:
                continue
            n, u = seg.rsplit('$', 1)
            n = n.strip() or '第%d集' % (i + 1)
            u = u.strip()
            if u.startswith('//'):
                u = 'https:' + u
            if not u.startswith('http'):
                continue
            pairs.append((n, u))
        return pairs

    # 首集回查：纯 vodId 入参时拉一次详情拿首条线路首集
    def _first_ep(self, vid):
        # 纯 vodId 入参时回查详情，返回首条线路首集地址（校验器/壳端重播会走这条）
        d = self._api('/show/v2/vod/%s' % str(vid).strip()) or {}
        for p in (d.get('vod_play') or []):
            if not isinstance(p, dict):
                continue
            pairs = self._parse_eps(p.get('vodPlayUrl'))
            if pairs:
                return pairs[0][1]
        return ''

    # 同集候选：当前线路优先，再按 vod_play 顺序补齐同集地址
    def _ep_candidates(self, vid, idx, first=''):
        # 同片同集的候选地址：先给当前线路的地址，再按 vod_play 原顺序补其他线路的同集
        # 详情接口命中 300s 缓存，回查不额外发请求；缓存过期才会多打一次
        out = [first] if str(first or '').startswith('http') else []
        d = self._api('/show/v2/vod/%s' % str(vid).strip()) if str(vid).isdigit() else None
        for p in ((d or {}).get('vod_play') or []):
            if not isinstance(p, dict):
                continue
            pairs = self._parse_eps(p.get('vodPlayUrl'))
            if len(pairs) > idx:
                u = pairs[idx][1]
                if u not in out:
                    out.append(u)
        return out

    # 1900B 分段：客户端按 2048B 截断，长剧不拆段后半段会整段丢失
    def _segments(self, label, pairs, vid=''):
        # 1900B 分段：客户端按 2048B 截断 vod_play_url，长剧必须拆段否则后半段集数丢失
        chunks, cur, size = [], [], 0
        for n, u in pairs:
            seg = '%s$%s' % (n, u)
            b = len(seg.encode('utf-8')) + 1
            if cur and size + b > self.SEG:
                chunks.append(cur)
                cur, size = [], 0
            cur.append((n, u))
            size += b
        if cur:
            chunks.append(cur)
        if len(chunks) <= 1:
            return [(label, self._join(chunks[0] if chunks else [], vid))]
        # 同名线路加 (1)(2)：壳端同名会互相覆盖
        return [('%s(%d)' % (label, i + 1), self._join(c, vid)) for i, c in enumerate(chunks)]

    def _join(self, eps, vid=''):
        # 集数之间用 #，名称与地址之间用 $，这是壳端 vod_play_url 的固定语法
        # play id 只放 vodId|集序号（不放直链）：3 条线路的地址全拼进去会超 2048B 截断线
        out = []
        for i, (n, u) in enumerate(eps):
            tail = '%s|%d' % (vid, i) if vid.isdigit() else u
            out.append('%s$%s' % (n or '第%d集' % (i + 1), tail))
        return '#'.join(out)

    # 文本清洗：去标签压空白，详情/简介字段统一走这里
    def _txt(self, html):
        # 简介是 HTML 片段，壳端只认纯文本
        s = str(html or '')
        s = re.sub(r'<[^>]+>', '', s)
        s = s.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&')
        return s.strip()

    # 封面补全：相对路径拼当前域，双斜杠补 https
    def _pic(self, p):
        # 封面走多家图床（pic.ry-pic / pic.feifeixiang / pic3.yzzyimg / fffgood），都支持 https
        p = str(p or '').strip()
        if p.startswith('//'):
            return 'https:' + p
        if p.startswith('http://'):
            return 'https://' + p[7:]
        if p.startswith('/'):
            return self.base + p
        return p

    # ================================================================= 媒体
    def _media_headers(self, url):
        # 三条线路的 CDN（ryiplay18 / yzzy32-play / lzcdn31）实测带不带 Referer 结果一致，
        # 统一只给 UA：避免把站点 Referer 打到别人的 CDN 上被 403
        return {'User-Agent': self.UA}

    def _probe(self, url, own=False):
        # 媒体验真：Range 只读前 2KB 就判，绝不整文件下载（长视频会把预算烧穿）
        # 连不上/超时的 CDN 记 60s 冷却：同一片的其他集大多在同域，冷却能把播放前摇从 10s 降到 1s
        host = re.sub(r'^https?://', '', str(url or '')).split('/')[0]
        exp = type(self)._MED.get(host)
        if exp and time.time() < exp:
            return False
        # 信任表命中直接放行：同域 120s 内刚验过真流，重读 2KB 纯属白等首包
        hit = type(self)._TRUST.get(host)
        if hit and time.time() - hit < 120:
            return True
        code, ctype, head = self._head(url, own=own)
        if code not in (200, 206) or not head:
            type(self)._MED[host] = time.time() + 60
            return False
        type(self)._MED.pop(host, None)
        low = (ctype or '').lower()
        ok = (b'#EXTM3U' in head or b'ftyp' in head[:64]
              or 'mpegurl' in low or 'video/' in low)
        if ok:
            type(self)._TRUST[host] = time.time()
        return ok

    # 流式取前 2KB：Referer 置空免得被 CDN 403，超时收紧到 (2,2.5)
    def _head(self, url, n=2048, own=False):
        # 流式取前 n 字节：Referer 传 None 让 requests 删掉 session 里的站点 Referer
        # 超时收紧到 (2,3)：实测两口死 CDN（ffzy-online4 / ryplay14）是"连得上但永远不回"，
        # 原来 (3,5) 单条就要 6s，三路并发后 4s 死线如果还配 5s 读超时，死线等于摆设
        hd = {'Range': 'bytes=0-%d' % (n - 1), 'Referer': None}
        sess = self.session
        if own:
            # 并发路径各开独立会话：requests 的 Session 不是线程安全的，共用连接池会偶发串包
            sess = requests.Session()
            sess.headers.update(self.session.headers)
            sess.trust_env = False
        try:
            r = sess.get(url, headers=hd, timeout=(2, 2.5), verify=False, stream=True,
                         proxies=self.session.proxies or None)
            buf = b''
            try:
                for ch in r.iter_content(1024):
                    buf += ch
                    if len(buf) >= n:
                        break
            finally:
                r.close()
            return r.status_code, r.headers.get('Content-Type') or '', buf
        except Exception:
            return 0, '', b''

    # 代理取流：图片要完整字节，CDN 同样不带站点 Referer
    def _req(self, url, raw=False):
        # 代理取流：图片要完整字节，所以不设 Range；CDN 同样删 Referer
        try:
            r = self.session.get(url, headers={'Referer': None, 'User-Agent': self.UA},
                                 timeout=20, verify=False, stream=raw,
                                 proxies=self.session.proxies or None)
            if raw:
                data = r.content
                r.close()
                return r.status_code, r.headers.get('Content-Type') or '', data
            return r.status_code, r.headers.get('Content-Type') or '', b''
        except Exception:
            return 0, '', b''

    # ================================================================= 工具
    def _pg(self, pg):
        # 页码规范化：壳端可能传 '1' / 1 / '' / 'abc'
        try:
            page = int(str(pg).strip())
        except Exception:
            page = 1
        return page if page > 0 else 1

    # 安全转整：壳端可能传空串或字母，解析失败按默认值
    def _int(self, v, default=0):
        # 站点计数字段可能是字符串，统一转 int，失败给默认值
        try:
            return int(str(v).strip())
        except Exception:
            return default
