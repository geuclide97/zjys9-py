# coding=utf-8
# !/usr/bin/python
# by嗷呜(finally)
#
# ============================ 优化说明 ============================
# [修复1] "高清-官方线路B" 只有码流没有画面
#   原因: playerContent 里的预检请求
#         self.fetch(url, headers=..., allow_redirects=False)
#         底层的 requests 默认 stream=False, 会把响应体完整读进内存。
#         而 B 线路解析出来的是 toutiaovod 的直链 MP4(单集约 337MB),
#         于是播放器拿到地址前必须先等这 337MB 下载完(实测约 268 秒),
#         表现就是"一直在缓冲/有码流但没有画面"。
#         其他线路都是几十 KB 的 m3u8, 预检瞬间完成, 所以只有 B 线路会犯病。
#   修法: 加 stream=True, 只读响应头, 不再吞响应体; 顺带把 ['Location']
#         换成 .get('Location') 并显式关闭连接。
#
# [修复2] vod_play_from 与 vod_play_url 的顺序错位隐患
#   原代码把名字一次性全部 append, 播放列表却是"先内联的、后异步的",
#   两者顺序一旦不一致就会串台(标签页点开是别的线路的剧集)。
#   现在改成按索引成对构建, 顺序永远对齐。
#
# [排序]  线路顺序: 4K → 无水印 → 官方线路-C → 其余保持接口原顺序
# ================================================================
import sys
import os
sys.path.append("..")
import re
import hashlib
import hmac
import random
import string
from Crypto.Util.Padding import unpad
from concurrent.futures import ThreadPoolExecutor
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES
from base64 import b64encode, b64decode
import json
import time
from base.spider import Spider

# ---- 线路置顶顺序(按此列表从前到后), 未列出的线路保持接口原顺序 ----
# 匹配规则: 忽略大小写、空格、连字符、下划线、括号后做"包含"匹配;
#          每条线路只会被占用一次, 所以 "4K-官方线路C" 会先被 "4K" 抢走,
#          不会又被 "官方线路-C" 重复匹配。
# 想改顺序直接调这个列表即可, 例如让修好的高清B排第一:
#   SOURCE_PRIORITY = ["4K", "无水印", "高清-官方线路B", "官方线路-C"]
SOURCE_PRIORITY = ["4K", "无水印", "官方线路-C"]

# 拉取失败的线路是否从列表里丢掉。
# False = 保持原样(会留一个空标签页), True = 直接不显示。
DROP_EMPTY_SOURCES = False


class Spider(Spider):

    def getName(self):
        return "电影猎手"

    def init(self, extend=""):
        self.device = self.device_id()
        self.host = self.gethost()
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def action(self, action):
        pass

    def destroy(self):
        pass

    t = str(int(time.time()))

    def homeContent(self, filter):
        result = {}
        filters = {}
        classes = []
        bba = self.url()
        data = self.fetch(f"{self.host}/api/v1/app/config?pack={bba[0]}&signature={bba[1]}", headers=self.header()).text
        data1 = self.aes(data)
        dy = {"class":"类型","area":"地区","lang":"语言","year":"年份","letter":"字母","by":"排序","sort":"排序"}
        data1['data']['movie_screen']['sort'].pop(0)
        for item in data1['data']['movie_screen']['sort']:
            item['n'] = item.pop('name')
            item['v'] = item.pop('value')
        for item in data1['data']['movie_screen']['filter']:
            has_non_empty_field = False
            classes.append({"type_name": item["name"], "type_id": str(item["id"])})
            for key in dy:
                if key in item and item[key]:
                    has_non_empty_field = True
                    break
            if has_non_empty_field:
                filters[str(item["id"])] = []
                filters[str(item["id"])].append(
                    {"key": 'sort', "name": '排序', "value": data1['data']['movie_screen']['sort']})
                for dkey in item:
                    if dkey in dy and item[dkey]:
                        item[dkey].pop(0)
                        value_array = [
                            {"n": value.strip(), "v": value.strip()}
                            for value in item[dkey]
                            if value.strip() != ""
                        ]
                        filters[str(item["id"])].append(
                            {"key": dkey, "name": dy[dkey], "value": value_array}
                        )
        result["class"] = classes
        result["filters"] = filters
        return result

    def homeVideoContent(self):
        bba = self.url()
        url = f'{self.host}/api/v1/movie/index_recommend?pack={bba[0]}&signature={bba[1]}'
        data = self.fetch(url, headers=self.header()).json()
        videos = []
        for item in data['data']:
            if len(item['list']) > 0:
                for it in item['list']:
                    try:
                        videos.append(self.voides(it))
                    except Exception as e:
                        continue
        result = {"list": videos}
        return result

    def categoryContent(self, tid, pg, filter, extend):
        body = {"type_id": tid, "sort": extend.get("sort", "by_default"), "class": extend.get("class", "类型"),
                "area": extend.get("area", "地区"), "year": extend.get("year", "年份"), "page": str(pg),
                "pageSize": "21"}
        result = {}
        list = []
        bba = self.url(body)
        url = f"{self.host}/api/v1/movie/screen/list?pack={bba[0]}&signature={bba[1]}"
        data = self.fetch(url, headers=self.header()).json()['data']['list']
        for item in data:
            list.append(self.voides(item))
        result["list"] = list
        result["page"] = pg
        result["pagecount"] = 9999
        result["limit"] = 90
        result["total"] = 999999
        return result

    def detailContent(self, ids):
        body = {"id": ids[0]}
        bba = self.url(body)
        url = f'{self.host}/api/v1/movie/detail?pack={bba[0]}&signature={bba[1]}'
        data = self.fetch(url, headers=self.header()).json()['data']
        video = {'vod_name': data.get('name'),'type_name': data.get('type_name'),'vod_year': data.get('year'),'vod_area': data.get('area'),'vod_remarks': data.get('dynami'),'vod_content': data.get('content')}

        # entries[i] = [原始顺序, 线路名, 播放列表]; 播放列表为 None 表示待异步拉取
        # 用索引对齐而不是两次独立 append, 从根上避免 names/play 错位
        entries = []
        tasks = []
        for i, itt in enumerate(data["play_from"]):
            if len(itt["list"]) > 0:
                entries.append([i, itt["name"], self.playeach(itt['list'])])
            else:
                entries.append([i, itt["name"], None])
                tasks.append((i, itt["code"]))

        if tasks:
            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                results = list(executor.map(
                    self.playlist,
                    [{"movie_id": ids[0], "from_code": code} for _, code in tasks]
                ))
            for (i, _code), result in zip(tasks, results):
                entries[i][2] = result if result else ""

        entries = self.sortSources(entries)

        names = [e[1] for e in entries]
        play = [e[2] for e in entries]
        if DROP_EMPTY_SOURCES:
            pairs = [(n, p) for n, p in zip(names, play) if p]
            names = [n for n, _ in pairs]
            play = [p for _, p in pairs]

        video["vod_play_from"] = "$$$".join(names)
        video["vod_play_url"] = "$$$".join(play)
        result = {"list": [video]}
        return result

    def sortSources(self, entries):
        """按 SOURCE_PRIORITY 把指定线路提到前面, 其余保持接口原顺序(稳定排序)"""
        if not SOURCE_PRIORITY:
            return entries
        rank = {}
        taken = set()
        for pos, key in enumerate(SOURCE_PRIORITY):
            nk = self.normName(key)
            if not nk:
                continue
            for idx, entry in enumerate(entries):
                if idx in taken:
                    continue
                if nk in self.normName(entry[1]):
                    rank[idx] = pos
                    taken.add(idx)
                    break
        fallback = len(SOURCE_PRIORITY)
        order = sorted(range(len(entries)), key=lambda k: (rank.get(k, fallback), entries[k][0]))
        return [entries[k] for k in order]

    def normName(self, name):
        return re.sub(r'[\s\-_（）()【】\[\]]+', '', str(name)).lower()

    def searchContent(self, key, quick, pg=1):
        body = {"keyword": key, "sort": "", "type_id": "0", "page": str(pg), "pageSize": "10",
                "res_type": "by_movie_name"}
        bba = self.url(body)
        url = f"{self.host}/api/v1/movie/search?pack={bba[0]}&signature={bba[1]}"
        data = self.fetch(url, headers=self.header()).json()['data'].get('list')
        videos = []
        for it in data:
            try:
                videos.append(self.voides(it))
            except Exception as e:
                continue
        result = {"list": videos, "page": pg}
        return result

    def playerContent(self, flag, id, vipFlags):
        url = id
        if "m3u8" not in url and "mp4" not in url:
            try:
                add = id.split('|||')
                data = {"from_code": add[0], "play_url": add[1], "episode_id": add[2], "type": "play"}
                bba = self.url(data)
                data2 = self.fetch(f"{self.host}/api/v1/movie_addr/parse_url?pack={bba[0]}&signature={bba[1]}",
                                   headers=self.header()).json()['data']
                url = data2.get('play_url') or data2.get('download_url')
                # 预检只是为了拿 302 的 Location。
                # 必须带 stream=True: 不加的话 requests 会把整个响应体读下来,
                # B 线路是 337MB 的直链 MP4, 会把播放器活活拖死(有码流无画面)。
                try:
                    resp = self.fetch(url, headers=self.header(), allow_redirects=False, stream=True)
                    url1 = resp.headers.get('Location')
                    try:
                        resp.close()
                    except Exception:
                        pass
                    if url1 and "http" in url1:
                        url = url1
                except Exception:
                    pass
            except Exception as e:
                pass
        if '.jpg' in url or '.jpeg' in url or '.png' in url:
            url = self.getProxyUrl() + "&url=" + b64encode(url.encode('utf-8')).decode('utf-8') + "&type=m3u8"
        result = {}
        result["parse"] = 0
        result["url"] = url
        result["header"] = {'user-agent': 'okhttp/4.9.2'}
        return result

    def localProxy(self, param):
        url = b64decode(param["url"]).decode('utf-8')
        durl = url[:url.rfind('/')]
        data = self.fetch(url, headers=self.header()).content.decode("utf-8")
        lines = data.strip().split('\n')
        for index, string in enumerate(lines):
            # if 'URI="' in string and 'http' not in string:
            #     lines[index] = index
            # 暂时预留，貌似用不到
            if '#EXT' not in string and 'http' not in string:
                lines[index] = durl + ('' if string.startswith('/') else '/') + string
        data = '\n'.join(lines)
        return [200, "application/vnd.apple.mpegur", data]

    def device_id(self):
        characters = string.ascii_lowercase + string.digits
        random_string = ''.join(random.choices(characters, k=32))
        return random_string

    def gethost(self):
        headers = {
            'User-Agent': 'okhttp/4.9.2',
            'Connection': 'Keep-Alive',
        }
        response = self.fetch('https://app-site.ecoliving168.com/domain_v5.json', headers=headers).json()
        url = response['api_service'].replace('/api/', '')
        return url

    def header(self):
        headers = {
            'User-Agent': 'Android',
            'Accept': 'application/prs.55App.v2+json',
            'timestamp': self.t,
            'x-client-setting': '{"pure-mode":1}',
            'x-client-uuid': '{"device_id":' + self.device + '}, "type":1,"brand":"Redmi", "model":"M2012K10C", "system_version":30, "sdk_version":"3.1.0.7"}',
            'x-client-version': '3096 '
        }
        return headers

    def url(self, id=None):
        if not id:
            id = {}
        id["timestamp"] = self.t
        public_key = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA02F/kPg5A2NX4qZ5JSns+bjhVMCC6JbTiTKpbgNgiXU+Kkorg6Dj76gS68gB8llhbUKCXjIdygnHPrxVHWfzmzisq9P9awmXBkCk74Skglx2LKHa/mNz9ivg6YzQ5pQFUEWS0DfomGBXVtqvBlOXMCRxp69oWaMsnfjnBV+0J7vHbXzUIkqBLdXSNfM9Ag5qdRDrJC3CqB65EJ3ARWVzZTTcXSdMW9i3qzEZPawPNPe5yPYbMZIoXLcrqvEZnRK1oak67/ihf7iwPJqdc+68ZYEmmdqwunOvRdjq89fQMVelmqcRD9RYe08v+xDxG9Co9z7hcXGTsUquMxkh29uNawIDAQAB'
        encrypted_text = json.dumps(id)
        public_key = RSA.import_key(b64decode(public_key))
        cipher = PKCS1_v1_5.new(public_key)
        encrypted_message = cipher.encrypt(encrypted_text.encode('utf-8'))
        encrypted_message_base64 = b64encode(encrypted_message).decode('utf-8')
        result = encrypted_message_base64.replace('+', '-').replace('/', '_').replace('=', '')
        key = '635a580fcb5dc6e60caa39c31a7bde48'
        sign = hmac.new(key.encode(), result.encode(), hashlib.md5).hexdigest()
        return result, sign

    def playlist(self, body):
        try:
            bba = self.url(body)
            url = f'{self.host}/api/v1/movie_addr/list?pack={bba[0]}&signature={bba[1]}'
            data = self.fetch(url, headers=self.header()).json()['data']
            return self.playeach(data)
        except Exception:
            return []

    def playeach(self,data):
        play_urls = []
        for it in data:
            if re.search(r"mp4|m3u8", it["play_url"]):
                play_urls.append(f"{it['episode_name']}${it['play_url']}")
            else:
                play_urls.append(
                    f"{it['episode_name']}${it['from_code']}|||{it['play_url']}|||{it['episode_id']}"
                )
        return '#'.join(play_urls)

    def voides(self, item):
        if item['name'] or item['title']:
            voide = {
                "vod_id": item.get('id') or item.get('click'),
                'vod_name': item.get('name') or item.get('title'),
                'vod_pic': item.get('cover') or item.get('image'),
                'vod_year': item.get('year') or item.get('label'),
                'vod_remarks': item.get('dynamic') or item.get('sub_title')
            }
            return voide

    def aes(self, text):
        text = text.replace('-', '+').replace('_', '/') + '=='
        key = b"e6d5de5fcc51f53d"
        iv = b"2f13eef7dfc6c613"
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(b64decode(text)), AES.block_size).decode("utf-8")
        return json.loads(pt)
