# -*- coding: utf-8 -*-
# by @一朵诡异的花
# UI9通用架构适配 | 永乐视频 ylys.tv 网页爬虫
import json
import random
import re
import sys
import time
from base64 import b64encode, b64decode
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, quote

sys.path.append('..')
from base.spider import Spider

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None

# 网页无RSA加密，密钥置空，加解密空兼容
class Spider(Spider):

    def init(self, extend=""):
        # 复制为实例属性，避免污染类级 headers
        self.headers = dict(self.headers)
        try:
            self.headers['deviceId'] = self.getdid()
        except Exception as e:
            print(f"deviceId初始化失败: {e}")
        self._token_ready = False
        self._session = None      # requests 会话（连接复用）
        self._play_cache = {}     # 播放地址缓存 {episodeId: (时间戳, url)}
        self._pub_key = None
        self._pri_key = None
        self.refresh_token()

    def getName(self):
        return "永乐视频"

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    # 站点域名
    host = 'https://www.ylys.tv/'

    # 适配UI9头部，网页UA替换，保留原有字段兼容框架
    headers = {
        'HOST': 'www.ylys.tv',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'client': 'web',
        'deviceType': 'PC',
        'Referer': host
    }

    # RSA全部空，网页不需要加密解密
    publicKey_str = ""
    privateKey_str = ""

    def rsa_encrypt(self, text):
        return text
    def rsa_decrypt(self, text):
        return text

    def homeContent(self, filter):
        self.refresh_token()
        result = {}
        try:
            resp = self.fetch(self.host, timeout=25)
            html = resp.text
        except Exception as e:
            print(f"首页分类获取失败: {e}")
            result['class'] = []
            result['filters'] = {}
            return result

        cate = {"类型": "type", "地区": "area", "年份": "year"}
        sort = {
            'key': 'sort',
            'name': '排序',
            'value': [{'n': '最新', 'v': 'NEWEST'}, {'n': '热门', 'v': 'HOT'}]
        }
        # 固定四大分类
        cate_list = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "剧集"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"}
        ]
        classes = cate_list
        filters = self._build_filters()
        # 所有分类附加排序
        for tid in filters:
            filters[tid].append(sort)
        result['class'] = classes
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        self.refresh_token()
        try:
            resp = self.fetch(self.host, timeout=25)
            html = resp.text
        except Exception as e:
            print(f"首页视频获取失败: {e}")
            return {'list': []}
        # 正则批量提取首页卡片
        pattern = re.compile(r'<a href="/voddetail/(\d+)/".*?title="([^"]+)".*?<div class="module-item-note">([^<]+)</div>.*?data-original="([^"]+)"', re.S | re.I)
        all_data = pattern.findall(html)
        vod_records = []
        for vid, name, remark, pic in all_data:
            vod_records.append({
                "id": vid,
                "name": name,
                "cover": urljoin(self.host, pic),
                "year": "",
                "totalEpisode": remark
            })
        return {'list': self.getlist(vod_records[:20])}

    def categoryContent(self, tid, pg, filter, extend):
        self.refresh_token()
        page = int(pg) if str(pg).isdigit() else 1
        condition = {
            'sreecnTypeEnum': 'NEWEST',
            'typeId': int(tid) if str(tid).isdigit() else tid
        }
        if extend:
            if 'sort' in extend:
                condition['sreecnTypeEnum'] = extend.pop('sort')
            condition.update(extend)

        jdata = {
            'condition': condition,
            'pageNum': page,
            'pageSize': 20,
        }

        # 拼接分类地址
        if page == 1:
            url = f"{self.host}/vodtype/{tid}/"
        else:
            url = f"{self.host}/vodtype/{tid}/page/{page}/"
        try:
            resp = self.fetch(url, timeout=25)
            html = resp.text
        except Exception as e:
            print(f"分类获取错误: {e}")
            return {'list': [], 'page': pg, "pagecount": 1, "limit": 20, "total": 0}

        pattern = re.compile(r'<a href="/voddetail/(\d+)/".*?title="([^"]+)".*?<div class="module-item-note">([^<]+)</div>.*?data-original="([^"]+)"', re.S | re.I)
        all_data = pattern.findall(html)
        vod_records = []
        for vid, name, remark, pic in all_data:
            vod_records.append({
                "id": vid,
                "name": name,
                "cover": urljoin(self.host, pic),
                "year": "",
                "totalEpisode": remark
            })
        list_data = self.getlist(vod_records)

        # 统计真实分页
        total = 0
        total_match = re.search(r'共(\d+)条数据', html)
        if total_match:
            total = int(total_match.group(1))
        soup_page = BeautifulSoup(html, "html.parser")
        page_nums = [int(i.get_text(strip=True)) for i in soup_page.select(".page a") if i.get_text(strip=True).isdigit()]
        pagecount = max(page_nums) if page_nums else page

        result = {
            "list": list_data,
            "page": page,
            "pagecount": pagecount,
            "limit": 20,
            "total": total
        }
        return result

    def searchContent(self, key, quick, pg="1"):
        self.refresh_token()
        page = int(pg)
        search_key = quote(key)
        if page == 1:
            url = f"{self.host}/vodsearch/{search_key}-------------/"
        else:
            url = f"{self.host}/vodsearch/{search_key}-------------/page/{page}/"

        try:
            resp = self.fetch(url, timeout=25)
            html = resp.text
        except Exception as e:
            print(f"搜索请求失败: {e}")
            return {'list': [], 'page': pg, "pagecount": 1, "limit": 20, "total": 0}

        soup = BeautifulSoup(html, "html.parser")
        records = []
        for item in soup.select('.module-card-item'):
            link = item.select_one('a[href^="/voddetail/"]')
            if not link:
                continue
            href = link.get("href", "")
            vid_match = re.search(r'/voddetail/(\d+)/', href)
            if not vid_match:
                continue
            vid = vid_match.group(1)
            title_elem = item.select_one('.module-card-item-title strong')
            img_elem = item.select_one('img')
            note_elem = item.select_one('.module-item-note')

            name = title_elem.get_text(strip=True) if title_elem else ""
            pic = ""
            if img_elem:
                pic = img_elem.get('data-original', img_elem.get('src', ''))
            cover = urljoin(self.host, pic)
            remark = note_elem.get_text(strip=True) if note_elem else ""
            records.append({
                "id": vid,
                "name": name,
                "cover": cover,
                "year": "",
                "totalEpisode": remark
            })
        total = 0
        total_match = re.search(r'找到(\d+)条', html)
        if total_match:
            total = int(total_match.group(1))
        return {
            'list': self.getlist(records),
            'page': page,
            "pagecount": 1,
            "limit": 20,
            "total": total
        }

    def detailContent(self, ids):
        self.refresh_token()
        ids = ids[0].split('@@')
        vod_id = ids[0]
        type_id = ids[-1] if len(ids) > 1 else ''
        detail_url = f"{self.host}/voddetail/{vod_id}/"
        try:
            resp = self.fetch(detail_url, timeout=25)
            html = resp.text
        except Exception as e:
            print(f"详情请求失败: {e}")
            return {'list': []}

        # 解析基础信息
        v = {}
        # 标题
        title_match = re.search(r'<meta property="og:title" content="([^"]+)', html, re.S | re.I)
        if title_match:
            raw_title = title_match.group(1).strip()
            raw_title = re.sub(r"[-｜].*?$", "", raw_title)
            v["name"] = raw_title
        else:
            h1_res = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            v["name"] = h1_res.group(1).strip() if h1_res else "未知"

        # 封面
        pic_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        v["cover"] = urljoin(self.host, pic_match.group(1).strip()) if pic_match else ""

        # 简介
        desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html)
        if desc_match and desc_match.group(1).strip():
            v["introduce"] = desc_match.group(1).strip()
        else:
            intro_res = re.search(r'<div class="module-info-introduction-content">([\s\S]+?)</div>', html)
            v["introduce"] = intro_res.group(1).strip() if intro_res else "暂无简介"

        # 年份、地区、分类
        year = "未知年份"
        year_match = re.search(r'<a title="(\d{4})" href="/vodshow/\d+-----------\1/">', html, re.S | re.I)
        if year_match:
            year = year_match.group(1)
        area = "未知产地"
        area_match = re.search(r'<a title="([^"]+)" href=".*?vodshow.*?地区">', html, re.S | re.I)
        if area_match:
            area = area_match.group(1)
        type_str = "未知类型"
        type_match = re.search(r'vod_class":"([^"]+)"', html, re.S | re.I)
        if type_match:
            type_str = type_match.group(1).replace(",", "/")

        v["year"] = year
        v["area"] = area
        v["typeId"] = type_str
        v["star"] = ""
        v["director"] = ""

        # 解析线路列表
        l = []
        soup = BeautifulSoup(html, "html.parser")
        tab_list = soup.select(".module-tab-item")
        line_mapping = {"全球3线": "3", "大陆0线": "1", "大陆3线": "4", "大陆5线": "2", "大陆6线": "3"}
        for tab in tab_list:
            line_name = tab.get_text(strip=True)
            if not line_name:
                continue
            href_attr = tab.get("href", "")
            id_res = re.search(r"/play/{}-\d+-(\d+)/".format(vod_id), href_attr)
            line_id = id_res.group(1) if id_res else line_mapping.get(line_name, "1")
            l.append({"id": line_id, "moviePlayerName": line_name})

        vod = {
            'type_name': v.get('typeId', ''),
            'vod_year': v.get('year', ''),
            'vod_area': v.get('area', ''),
            'vod_actor': v.get('star', ''),
            'vod_director': v.get('director', ''),
            'vod_content': v.get('introduce', ''),
            'vod_play_from': '',
            'vod_play_url': ''
        }
        if not l:
            return {'list': [vod]}

        n = {str(i['id']): i['moviePlayerName'] for i in l}
        pd = {}
        # 无接口，串行解析剧集，不用多线程
        for player in l:
            o, p = self.getd({"id": vod_id, "typeId": type_id}, player)
            if p:
                pd.update(self.getv(o, p))

        w, e = [], []
        for i, x in pd.items():
            if x:
                w.append(n.get(i, '未知线路'))
                e.append(x)
        vod['vod_play_from'] = '$$$'.join(w)
        vod['vod_play_url'] = '$$$'.join(e)
        return {'list': [vod]}

    def playerContent(self, flag, id, vipFlags):
        self.refresh_token()
        header = {'User-Agent': self.headers["User-Agent"], "Referer": self.host}
        raw_id_str = self.d64(id)
        if not raw_id_str:
            return {'parse': 0, 'url': '', 'header': header}
        try:
            jdata = json.loads(raw_id_str)
            ep_key = str(jdata.get('episodeId', raw_id_str[:32]))
            play_cache = getattr(self, '_play_cache', None)
            if play_cache is None:
                play_cache = self._play_cache = {}
            now = time.time()
            cached = play_cache.get(ep_key)
            # 缓存30分钟
            if cached and now - cached[0] < 1800 and cached[1]:
                return {'parse': 0, 'url': cached[1], 'header': header}

            play_page_url = jdata.get("playUrl")
            resp = self.fetch(play_page_url, timeout=12)
            html = resp.text
            real_url = ""
            real_url_match = re.search(r'var player_aaaa\s*=\s*(\{.*?\});', html, re.S | re.I)
            if real_url_match:
                json_str = real_url_match.group(1).replace(r"\u002F", "/").replace(r"\/", "/")
                js_data = json.loads(json_str)
                real_url = js_data.get("url", "")
            if real_url:
                play_cache[ep_key] = (now, real_url)
                return {'parse': 0, 'url': real_url, 'header': header}
            return {"parse": 1, "url": play_page_url, "header": header}
        except Exception as e:
            print(f"解析流媒体直链失败: {e}")
            return {'parse': 0, 'url': '', 'header': header}

    def localProxy(self, param):
        pass
    def liveContent(self, url):
        pass

    def post(self, url, headers=None, json=None, timeout=10):
        if requests is not None:
            sess = self._get_session()
            return sess.post(url, headers=headers or self.headers, json=json, timeout=timeout, verify=False)
        return super().post(url, headers=headers, json=json)

    def fetch(self, url, headers=None, timeout=10):
        if requests is not None:
            sess = self._get_session()
            resp = sess.get(url, headers=headers or self.headers, timeout=timeout, verify=False)
            if resp.encoding in (None, "ISO-8859-1"):
                resp.encoding = resp.apparent_encoding
            return resp
        return super().fetch(url, headers=headers)

    def _get_session(self):
        if self._session:
            return self._session
        sess = requests.Session()
        retry_strategy = Retry(total=2, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=15, pool_maxsize=15)
        sess.mount("http://", adapter)
        sess.mount("https://", adapter)
        sess.headers.update(self.headers)
        sess.verify = False
        self._session = sess
        return sess

    def refresh_token(self):
        # 网页无token，永久就绪
        self._token_ready = True
        return
    def gettk(self):
        return ""

    def getdid(self):
        did = None
        try:
            did = self.getCache('ldid')
        except Exception:
            pass
        if not did:
            hex_chars = '0123456789abcdef'
            did = ''.join(random.choice(hex_chars) for _ in range(16))
            try:
                self.setCache('ldid', did)
            except Exception:
                pass
        return did

    def _fetch_desc(self, jdata):
        return {}
    def _fetch_players(self, encrypt_payload):
        return []

    def getd(self, jdata, player):
        vod_id = jdata["id"]
        line_id = player["id"]
        html_url = f"{self.host}/voddetail/{vod_id}/"
        try:
            resp = self.fetch(html_url)
            html = resp.text
        except:
            return jdata, []
        ep_matches = re.findall(rf'<a class="module-play-list-link" href="/play/{vod_id}-{line_id}-(\d+)/"[^>]*>.*?<span>([^<]+)</span></a>', html, re.S | re.I)
        episode_list = []
        for ep_num, ep_name in ep_matches:
            episode_list.append({"id": ep_num, "episode": ep_name.strip()})
        return jdata, episode_list

    def getv(self, d, c):
        f = {str(d['playerId']): ''}
        g = []
        for i in c:
            j = d.copy()
            j.update({'episodeId': i['id']})
            play_link = f"{self.host}/play/{d['id']}-{d['playerId']}-{i['id']}/"
            j["playUrl"] = play_link
            g.append(f"{i['episode']}${self.e64(json.dumps(j))}")
        f[str(d['playerId'])] = '#'.join(g)
        return f

    def getlist(self, data):
        videos = []
        for i in data:
            if not i.get('id'):
                continue
            videos.append({
                'vod_id': f"{i['id']}@@{i.get('typeId', '')}",
                'vod_name': i.get('name', ''),
                'vod_pic': i.get('cover', ''),
                'vod_year': i.get('year', ''),
                'vod_remarks': i.get('totalEpisode', '')
            })
        return videos

    def e64(self, text):
        try:
            return b64encode(text.encode('utf-8')).decode()
        except:
            return ""
    def d64(self, encoded_text):
        try:
            return b64decode(encoded_text.encode('utf-8')).decode()
        except:
            return ""

    def _build_filters(self):
        return {
            "1": [{"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "动作片", "v": "6"}, {"n": "喜剧片", "v": "7"},
                {"n": "爱情片", "v": "8"}, {"n": "科幻片", "v": "9"}, {"n": "恐怖片", "v": "11"}
            ]}],
            "2": [{"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "国产剧", "v": "13"}, {"n": "港台剧", "v": "14"},
                {"n": "日剧", "v": "15"}, {"n": "韩剧", "v": "33"}, {"n": "欧美剧", "v": "16"}
            ]}],
            "3": [{"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "内地综艺", "v": "27"}, {"n": "港台综艺", "v": "28"},
                {"n": "日本综艺", "v": "29"}, {"n": "韩国综艺", "v": "36"}
            ]}],
            "4": [{"key": "class", "name": "类型", "value": [
                {"n": "全部", "v": ""}, {"n": "国产动漫", "v": "31"}, {"n": "日本动漫", "v": "32"},
                {"n": "欧美动漫", "v": "42"}, {"n": "其他动漫", "v": "43"}
            ]}]
        }

# 本地自测
if __name__ == "__main__":
    from bs4 import BeautifulSoup
    spider = Spider()
    spider.init()
    print("===首页测试===")
    h = spider.homeContent(False)
    print("分类数量", len(h["class"]))
    hv = spider.homeVideoContent()
    print("首页影片数", len(hv["list"]))

    print("\n===分类电影第一页===")
    cat = spider.categoryContent("1", "1", False, {})
    print("分类数量", len(cat["list"]), "总页数", cat["pagecount"])

    print("\n===详情测试 86027===")
    det = spider.detailContent(["86027@@"])
    if det["list"]:
        info = det["list"][0]
        print("片名", info["vod_name"], "线路", len(info["vod_play_from"].split("$$$")))

    print("\n===播放解析===")
    playtest = spider.playerContent("", "ODg2MDI3LTItMQ==", [])
    print("直链", playtest["url"][:100])