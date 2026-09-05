# 蜜果-http://6i.pw/ 20260816 修复
# coding = utf-8
#!/usr/bin/python
import re
import sys
import json
import time
import base64
import hashlib
import random
import string
import urllib.parse
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
sys.path.append('..')
from base.spider import Spider

# TVBox 可能在同一次配置加载中创建多个 Spider 实例。共享认证状态可避免
# 每个实例都重新注册设备、重新获取 token。
_SESSION_STATE = {
    'device_id': str(864150060000000 + random.randint(0, 9999)),
    'device_key': ''.join(random.choices('0123456789ABCDEF', k=40)),
    'token': '',
    'token_id': '',
    'registered': False,
    'host_index': 0
}
_DATA_CACHE = {}
_RSA_KEY_CACHE = {'public': None, 'private': None}

class Spider(Spider):
    def __init__(self):
        super().__init__()
        self.name = "瓜子"
        # 新版应用的接口与媒体播放器使用不同的请求头。
        self.api_ua = 'okhttp/3.12.0'
        self.media_ua = 'Lavf/57.83.100'
        self.media_referer = 'http://WJiZxLXA2.com/'
        self.hosts = [
            'https://api.anctjd.com',
            'https://apinew.uozvr.com',
            'https://api.w32z7vtd.com',
            'https://api.6a7nnf7.com',
            'https://api.umygrx3.com',
            'https://api.rmedphk.com'
        ]
        self.host_index = _SESSION_STATE.get('host_index', 0) % len(self.hosts)
        self.host = self.hosts[self.host_index]

        # AES 固定密钥（与Java版一致）
        self.AES_KEY = 'OITxa5OqAYjhswxx'
        self.AES_IV = 'rCMNwZASNBKZ8mXV'

        # RSA 公钥/私钥
        self.RSA_PUBLIC_KEY = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDUM5+/y8sPsWkd1/RQS64X259EUwxFXFE5HlA65MqrxnPs0JqoSRojSDy5QhwvROlaD6TwRQHKMY2OAZ6SnQeUJsChTEFIR9qUkwrs3/MVUMxjsv6JS6Oe/juclyJGTgVmDhB55EafXsD0SQYVj/QXXsxR6ewR5E2kL52yAAD4yQIDAQAB"
        self.RSA_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIICdgIBADANBgkqhkiG9w0BAQEFAASCAmAwggJcAgEAAoGAe6hKrWLi1zQmjTT1
ozbE4QdFeJGNxubxld6GrFGximxfMsMB6BpJhpcTouAqywAFppiKetUBBbXwYsYU
1wNr648XVmPmCMCy4rY8vdliFnbMUj086DU6Z+/oXBdWU3/b1G0DN3E9wULRSwcK
ZT3wj/cCI1vsCm3gj2R5SqkA9Y0CAwEAAQKBgAJH+4CxV0/zBVcLiBCHvSANm0l7
HetybTh/j2p0Y1sTXro4ALwAaCTUeqdBjWiLSo9lNwDHFyq8zX90+gNxa7c5EqcW
V9FmlVXr8VhfBzcZo1nXeNdXFT7tQ2yah/odtdcx+vRMSGJd1t/5k5bDd9wAvYdI
DblMAg+wiKKZ5KcdAkEA1cCakEN4NexkF5tHPRrR6XOY/XHfkqXxEhMqmNbB9U34
saTJnLWIHC8IXys6Qmzz30TtzCjuOqKRRy+FMM4TdwJBAJQZFPjsGC+RqcG5UvVM
iMPhnwe/bXEehShK86yJK/g/UiKrO87h3aEu5gcJqBygTq3BBBoH2md3pr/W+hUM
WBsCQQChfhTIrdDinKi6lRxrdBnn0Ohjg2cwuqK5zzU9p/N+S9x7Ck8wUI53DKm8
jUJE8WAG7WLj/oCOWEh+ic6NIwTdAkEAj0X8nhx6AXsgCYRql1klbqtVmL8+95KZ
K7PnLWG/IfjQUy3pPGoSaZ7fdquG8bq8oyf5+dzjE/oTXcByS+6XRQJAP/5ciy1b
L3NhUhsaOVy55MHXnPjdcTX0FaLi+ybXZIfIQ2P4rb19mVq1feMbCXhz+L1rG8oa
t5lYKfpe8k83ZA==
-----END RSA PRIVATE KEY-----"""

        self.DEVICE_OLD_KEY = "aLFBMWpxBrIDAD1Si/KVvm41"

        # 同一 Python 进程内复用设备身份和认证结果。
        self.deviceId = _SESSION_STATE['device_id']
        self.deviceKey = _SESSION_STATE['device_key']
        self.token = _SESSION_STATE.get('token', '')
        self.token_id = _SESSION_STATE.get('token_id', '')
        self.registered = _SESSION_STATE.get('registered', False)

        self.header = {
            'User-Agent': self.api_ua,
            'code': 'GZ0055',
            'deviceId': self.deviceId,
            'lang': 'zh_cn',
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Version': '2608011',
            'PackageName': 'com.f29439b8aa.c2afcf94ea.n9b31ac48420260814',
            'Ver': '3.0.5.2',
            'api-ver': '3.0.5.2',
            'Referer': self.host
        }

        # 分类/详情缓存也跨 Spider 实例复用，避免 TVBox 重建实例后重复请求。
        self.cache = _DATA_CACHE
        self.cache_timeout = 300
        # RSA PEM 解析在安卓设备上开销明显，按实例只解析一次。
        self._rsa_public = _RSA_KEY_CACHE['public']
        self._rsa_private = _RSA_KEY_CACHE['private']

        # 不在构造函数中联网，避免部分 TVBox/绿豆加载脚本时阻塞。
        # 首次业务请求时再执行设备认证。
        self._auth_in_progress = False

    def getName(self):
        return self.name

    def init(self, extend=''):
        pass

    # ---------- 设备注册与认证 ----------
    def init_token(self, force=False):
        """按需初始化 token；force=True 时强制重新认证。"""
        if self._auth_in_progress:
            return bool(self.token)
        if self.token and (self.token_id or not force):
            return True

        self._auth_in_progress = True
        try:
            if force:
                self.token = ""
                self.token_id = ""
                _SESSION_STATE['token'] = ''
                _SESSION_STATE['token_id'] = ''
            if not self.registered:
                self.sign_up()
            else:
                self.sign_in()
            # signUp/signIn 已直接返回可用 token。旧逻辑立即 refresh 一次，
            # token 实际没有变化，却会让首次加载多一次加密网络请求。
            return bool(self.token)
        except Exception as e:
            print(f"初始化token失败: {e}")
            return False
        finally:
            self._auth_in_progress = False

    def sign_up(self):
        """注册设备"""
        print("注册新设备...")
        params = {
            "new_key": self.deviceKey,
            "old_key": self.DEVICE_OLD_KEY,
            "phone_type": 1,
            "code": ""
        }
        result = self._auth_request('/App/Authentication/Device/signUp', params)
        self._apply_auth(result)
        self.registered = True
        _SESSION_STATE['registered'] = True

    def sign_in(self):
        """登录设备"""
        print("设备登录...")
        params = {
            "new_key": self.deviceKey,
            "old_key": self.DEVICE_OLD_KEY
        }
        result = self._auth_request('/App/Authentication/Device/signIn', params)
        self._apply_auth(result)

    def _apply_auth(self, result):
        """从认证响应中提取token"""
        if not isinstance(result, dict):
            raise Exception(f"认证接口无有效响应: {result}")
        new_token = result.get('token', '')
        if not new_token:
            raise Exception("认证失败，无token返回: {}".format(result))
        self.token = new_token
        new_token_id = result.get('app_user_id') or result.get('token_id') or result.get('user_id') or ''
        if new_token_id:
            self.token_id = new_token_id
        _SESSION_STATE['token'] = self.token
        _SESSION_STATE['token_id'] = self.token_id
        _SESSION_STATE['registered'] = self.registered
        print(f"获取token成功, token前缀: {self.token[:30]}...")

    def refresh_token(self):
        """刷新token"""
        print("刷新token...")
        result = self._auth_request('/App/Authentication/Authenticator/refresh', {})
        self._apply_auth(result)

    def _auth_request(self, path, params):
        """认证类请求（不需要ensure_token）"""
        return self._send_encrypted_request(params, path, is_auth=True)

    # ---------- 业务请求核心（修复加密与签名） ----------
    def ensure_token(self, force=False):
        """确保 token 可用。认证失败时由调用方切换域名后重试。"""
        if force:
            return self.init_token(force=True)
        if self.token:
            return True
        return self.init_token(force=False)

    def _send_encrypted_request(self, data, path, is_auth=False):
        """
        发送加密请求，返回解密后的字典
        :param data: 业务参数字典
        :param path: 请求路径
        :param is_auth: 是否为认证类请求（signUp/signIn/refresh），此时不使用ensure_token
        """
        try:
            if not is_auth and not self.ensure_token():
                raise Exception('设备认证失败')

            # 1. 将参数转为JSON并AES加密
            json_params = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            encrypted = self.aes_encrypt(json_params, self.AES_KEY, self.AES_IV)
            request_key = encrypted.upper()  # Java中是bytesToHex(encrypted).toUpperCase()

            # 2. 生成keys (RSA加密 iv/key JSON)
            key_json = json.dumps({"iv": self.AES_IV, "key": self.AES_KEY}, separators=(',', ':'))
            keys = self.rsa_encrypt(key_json, self.RSA_PUBLIC_KEY)

            # 3. 生成签名
            t = str(int(time.time()))
            sign_str = f"token_id=,token={self.token},phone_type=1,request_key={request_key},app_id=1,time={t},keys={keys}*&zvdvdvddbfikkkumtmdwqppp?|4Y!s!2br"
            signature = self.get_md5(sign_str)  # 已改为大写

            # 4. 构建请求体
            body = {
                'token': self.token,
                'token_id': '',
                'phone_type': '1',
                'time': t,
                'phone_model': 'xiaomi-25031',  # 与Java版保持一致
                'keys': keys,
                'request_key': request_key,
                'signature': signature,
                'app_id': '1',
                'ad_version': '1'
            }

            # 5. 发送请求
            url = f"{self.host}{path}"
            # 避免失效域名让 TVBox 单次请求阻塞十秒。
            response = self.post(url, headers=self.header, data=body, timeout=6)

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")

            resp_json = response.json()
            # 检查业务code（若不为200可能token过期）
            if 'code' in resp_json and str(resp_json['code']) not in ('0', '200'):
                print(f"业务错误码: {resp_json['code']}, 信息: {resp_json}")
                # 如果不是认证请求，尝试重新获取token后重试一次（这里简单处理，外层get_data已有重试）
                raise Exception("业务错误")

            data_section = resp_json.get('data')
            if not data_section:
                raise Exception("响应缺少data字段")

            encrypted_response = data_section.get('response_key', '')
            encrypted_keys = data_section.get('keys', '')

            # 6. 解密响应
            decrypted_keys_json = self.rsa_decrypt(encrypted_keys, self.RSA_PRIVATE_KEY)
            key_info = json.loads(decrypted_keys_json)
            resp_key = key_info['key']
            resp_iv = key_info['iv']
            decrypted_data = self.aes_decrypt(encrypted_response, resp_key, resp_iv)
            return json.loads(decrypted_data)

        except Exception as e:
            print(f"请求失败 [{path}]: {e}")
            return None

    def get_data(self, data, path, use_cache=True):
        """带缓存、域名轮询及一次强制重新认证的数据请求。"""
        cache_key = f"{path}_{json.dumps(data, ensure_ascii=False, sort_keys=True)}" if use_cache else None
        if use_cache and cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_timeout:
                return cached_data

        for auth_round in range(2):
            # 新版首选域名通常可用；最多检测三个节点，避免盒子长时间转圈。
            for _ in range(min(3, len(self.hosts))):
                self.host = self.hosts[self.host_index]
                self.header['Referer'] = self.host
                result = self._send_encrypted_request(data, path)
                if result is not None:
                    print(f"请求成功: {path}, 域名: {self.host}")
                    _SESSION_STATE['host_index'] = self.host_index
                    if use_cache and cache_key:
                        self.cache[cache_key] = (result, time.time())
                    return result
                self.host_index = (self.host_index + 1) % len(self.hosts)

            if auth_round == 0:
                print("业务请求全部失败，强制重新认证后再试...")
                self.ensure_token(force=True)
                self.host_index = 0
        return None

    # ---------- 加解密工具 ----------
    def aes_encrypt(self, text, key, iv):
        try:
            key_bytes = key.encode('utf-8')
            iv_bytes = iv.encode('utf-8')
            cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
            encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
            return encrypted.hex().upper()
        except Exception as e:
            print(f"AES加密失败: {e}")
            return ""

    def aes_decrypt(self, text, key, iv):
        try:
            key_bytes = key.encode('utf-8')
            iv_bytes = iv.encode('utf-8')
            cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
            encrypted_bytes = bytes.fromhex(text)
            decrypted = unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"AES解密失败: {e}")
            return ""

    def rsa_encrypt(self, text, public_key_str):
        """RSA公钥加密（PKCS1v1.5）"""
        try:
            if self._rsa_public is None:
                self._rsa_public = RSA.import_key(
                    "-----BEGIN PUBLIC KEY-----\n" + public_key_str + "\n-----END PUBLIC KEY-----"
                )
                _RSA_KEY_CACHE['public'] = self._rsa_public
            cipher = PKCS1_v1_5.new(self._rsa_public)
            encrypted = cipher.encrypt(text.encode('utf-8'))
            return base64.b64encode(encrypted).decode('utf-8')
        except Exception as e:
            print(f"RSA加密失败: {e}")
            return ""

    def rsa_decrypt(self, encrypted_data, private_key_str):
        """RSA私钥解密"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_data)
            if self._rsa_private is None:
                self._rsa_private = RSA.import_key(private_key_str)
                _RSA_KEY_CACHE['private'] = self._rsa_private
            cipher = PKCS1_v1_5.new(self._rsa_private)
            decrypted = cipher.decrypt(encrypted_bytes, None)
            return decrypted.decode('utf-8') if decrypted else ""
        except Exception as e:
            print(f"RSA解密失败: {e}")
            return ""

    def get_md5(self, text):
        return hashlib.md5(text.encode()).hexdigest().upper()  # 与Java一致大写

    # ---------- App 端首页与分类 ----------
    # pid 决定 App 首页专题内容，tid 决定分类筛选接口。海外剧和国产剧
    # 共用 tid=2，但首页 pid 不同；漫剧首页导航返回 tid=0，实际资源为 74。
    APP_CATEGORIES = [
        {"type_name": "热门", "type_id": "hot", "pid": "1", "tid": "0"},
        {"type_name": "动漫", "type_id": "4", "pid": "5", "tid": "4"},
        {"type_name": "漫剧", "type_id": "74", "pid": "62344", "tid": "74"},
        {"type_name": "电影", "type_id": "1", "pid": "3", "tid": "1"},
        {"type_name": "国产剧", "type_id": "2", "pid": "4", "tid": "2"},
        {"type_name": "短剧", "type_id": "64", "pid": "16", "tid": "64"},
        {"type_name": "综艺", "type_id": "3", "pid": "6", "tid": "3"},
        {"type_name": "海外剧", "type_id": "overseas", "pid": "23656", "tid": "2", "default_sub": "18"},
        {"type_name": "儿童", "type_id": "children", "pid": "26916", "tid": "4", "no_filter": True}
    ]

    def _category_meta(self, category_id):
        category_id = str(category_id)
        for item in self.APP_CATEGORIES:
            if item['type_id'] == category_id:
                return item
        return {"type_id": category_id, "pid": "", "tid": category_id}

    def _screen_values(self, items):
        result = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get('name', '')).strip()
            value = item.get('value', '')
            if name:
                result.append({"n": name, "v": str(value)})
        return result

    def _app_filters(self, meta):
        """使用与 App 相同的 indexScreen 接口生成二级分类。"""
        if meta.get('no_filter'):
            return []
        screen = self.get_data(
            {"t_id": meta['tid']}, '/App/IndexList/indexScreen', use_cache=True
        )
        if not isinstance(screen, dict):
            return []

        filters = []
        # 热门页的 App 筛选包含“全部/电影/AI漫剧/连续剧/综艺/动漫……”列。
        if meta['type_id'] == 'hot':
            values = self._screen_values(screen.get('column'))
            if values:
                filters.append({"key": "tid", "name": "分类", "value": values})

        for key, name in (("area", "地区"), ("year", "年份"), ("sort", "排序")):
            values = self._screen_values(screen.get(key))
            if values:
                filters.append({"key": key, "name": name, "value": values})

        sub_values = self._screen_values(screen.get('sub'))
        if sub_values:
            # 海外剧首页必须默认落在海外剧，而不是同 tid 下的国产剧。
            default_sub = meta.get('default_sub')
            if default_sub:
                sub_values.sort(key=lambda x: 0 if x['v'] == default_sub else 1)
            filters.append({"key": "sub", "name": "剧种", "value": sub_values})

        for key, name in (("class", "类型"), ("lang", "语言")):
            values = self._screen_values(screen.get(key))
            if values:
                filters.append({"key": key, "name": name, "value": values})
        return filters

    def homeContent(self, filter=True):
        classes = [
            {"type_name": item['type_name'], "type_id": item['type_id']}
            for item in self.APP_CATEGORIES
        ]
        result = {'class': classes}
        if filter:
            filters = {}
            for item in self.APP_CATEGORIES:
                values = self._app_filters(item)
                if values:
                    filters[item['type_id']] = values
            result['filters'] = filters

        # App 的热门页来自 pid=1 的首页专题，不是旧脚本的 tid=0+d_hits。
        home_vod = self.categoryContent('hot', 1, False, {})
        result['list'] = home_vod.get('list', []) if isinstance(home_vod, dict) else []
        return result

    def homeVideoContent(self):
        try:
            data = self.categoryContent('hot', 1, False, {})
            return {'list': data.get('list', []) if isinstance(data, dict) else []}
        except Exception as e:
            print(f"首页视频获取失败: {e}")
            return {'list': []}

    def _cache_read(self, key):
        cached = self.cache.get(key)
        if not cached:
            return None
        value, timestamp = cached
        if time.time() - timestamp >= self.cache_timeout:
            self.cache.pop(key, None)
            return None
        return value

    def _video_item(self, item):
        if not isinstance(item, dict):
            return None
        vod_id = str(item.get('vod_id', '')).strip()
        if not vod_id:
            return None
        continu = item.get('vod_continu', 0)
        name = item.get('vod_name') or item.get('c_name') or ''
        pic = item.get('vod_pic') or item.get('c_pic') or ''
        remarks = item.get('new_continue') or ''
        if not remarks:
            remarks = '电影' if str(continu or '0') == '0' else f'更新至{continu}集'
        return {
            "vod_id": f"{vod_id}/{continu}",
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks
        }

    def _app_home_videos(self, pid):
        """拉取并展平 App 首页某一栏目，顺序与 App 专题区一致。"""
        data = self.get_data({"pid": str(pid)}, '/App/IndexList/index', use_cache=True)
        videos, seen = [], set()
        if not isinstance(data, dict):
            return videos
        for section in data.get('list', []) or []:
            if not isinstance(section, dict):
                continue
            for raw in section.get('list', []) or []:
                video = self._video_item(raw)
                if not video:
                    continue
                vod_key = video['vod_id'].split('/')[0]
                if vod_key in seen:
                    continue
                seen.add(vod_key)
                videos.append(video)
        return videos

    def categoryContent(self, tid, pg, filter, extend):
        videos = []
        try:
            extend = extend or {}
            meta = self._category_meta(tid)
            page = int(pg)

            # 每个 App 一级栏目第一页都使用自己的 pid 专题数据，因此热门、
            # 海外剧、儿童等内容能与手机 App 首页保持一致。
            if page == 1 and not extend and meta.get('pid'):
                videos = self._app_home_videos(meta['pid'])
                if videos:
                    return {
                        'list': videos, 'page': page, 'pagecount': 9999,
                        'limit': len(videos), 'total': 999999
                    }

            request_tid = str(extend.get('tid', meta.get('tid', tid)))
            request_sort = extend.get('sort', 'd_id')
            # 新版短剧/漫剧接口第 1 页包含大量“仅发布资料、播放资源
            # 尚未入库”的预发布条目。服务端第 2 页起资源完整，因此
            # 这两个分类向后偏移一页，兼顾加载速度与可播放率。
            request_page = page
            if request_tid in ('64', '74'):
                request_page += 1
            body = {
                "pageSize": "30",
                "sort": request_sort,
                "page": str(request_page),
                "tid": request_tid
            }
            for key in ('sub', 'class', 'lang', 'area', 'year'):
                value = extend.get(key)
                if value not in (None, ''):
                    body[key] = str(value)
            if meta.get('default_sub') and 'sub' not in body:
                body['sub'] = meta['default_sub']
            data = self.get_data(body, '/App/IndexList/indexList', use_cache=True)
            if data and 'list' in data:
                for item in data['list']:
                    video = self._video_item(item)
                    if video:
                        videos.append(video)
        except Exception as e:
            print(f"获取分类内容失败: {e}")
        return {'list': videos, 'page': int(pg), 'pagecount': 9999, 'limit': 30, 'total': 999999}

    def detailContent(self, ids):
        try:
            vod_id = str(ids[0]).split('/')[0]
            # 详情参数本身包含 token；必须先认证再构造请求体。网页版每次调用
            # 都会启动新进程，不能依赖上一次首页调用留下的认证状态。
            if not self.ensure_token():
                return {'list': []}
            t = str(int(time.time()))
            body1 = {"token_id": self.token_id or "", "vod_id": vod_id, "mobile_time": t, "token": self.token}
            qdata = self._cache_read('__play_info__' + vod_id)
            if qdata is None:
                qdata = self.get_data(body1, '/App/IndexPlay/playInfo')
            body2 = {"vurl_cloud_id": "2", "vod_d_id": vod_id}
            jdata = self._cache_read('__vurl__' + vod_id)
            if jdata is None:
                # 空资源不能进入五分钟通用缓存，否则后台刚补齐资源后仍
                # 会一直显示无播放地址。
                jdata = self.get_data(body2, '/App/Resource/Vurl/show', use_cache=False)
                if not isinstance(jdata, dict) or not jdata.get('list'):
                    time.sleep(0.2)
                    jdata = self.get_data(body2, '/App/Resource/Vurl/show', use_cache=False)
                if isinstance(jdata, dict) and jdata.get('list'):
                    self.cache['__vurl__' + vod_id] = (jdata, time.time())
            if not qdata or 'vodInfo' not in qdata:
                return {'list': []}
            vod = qdata['vodInfo']
            video_detail = {
                "vod_id": vod_id,
                "vod_name": vod.get('vod_name', ''),
                "vod_pic": vod.get('vod_pic', ''),
                "vod_year": vod.get('vod_year', ''),
                "vod_area": vod.get('vod_area', ''),
                "vod_actor": vod.get('vod_actor', ''),
                "vod_director": vod.get('vod_director', ''),
                "vod_content": vod.get('vod_use_content', '').strip(),
                "vod_play_from": "瓜子影视"
            }
            play_list = []
            if jdata and 'list' in jdata:
                for index, item in enumerate(jdata['list']):
                    if 'play' in item:
                        n, p = [], []
                        for key, value in item['play'].items():
                            if 'param' in value and value['param']:
                                n.append(key)
                                p.append(value['param'])
                        if p:
                            play_name = str(index + 1) if len(jdata['list']) != 1 else vod.get('vod_name', '')
                            # param 与清晰度必须来自同一个 play 项，否则新版
                            # showOne 会返回防盗链短片或空地址。
                            play_url = f"{p[-1]}||{n[-1]}"
                            play_list.append(f"{play_name}${play_url}")
            video_detail["vod_play_url"] = "#".join(play_list)
            return {'list': [video_detail]}
        except Exception as e:
            print(f"获取详情失败: {e}")
            return {'list': []}

    def searchContent(self, key, quick, pg=1):
        videos = []
        try:
            body = {"keywords": key, "order_val": "1", "page": str(pg)}
            data = self.get_data(body, '/App/Index/findMoreVod', use_cache=False)
            if data and 'list' in data:
                for item in data['list']:
                    vod_continu = item.get('vod_continu', 0)
                    remarks = '电影' if str(vod_continu or '0') == '0' else f'更新至{vod_continu}集'
                    videos.append({
                        "vod_id": f"{item.get('vod_id', '')}/{vod_continu}",
                        "vod_name": item.get('vod_name', ''),
                        "vod_pic": item.get('vod_pic', ''),
                        "vod_remarks": remarks
                    })
        except Exception as e:
            print(f"搜索失败: {e}")
        return {'list': videos, 'page': int(pg), 'pagecount': 9999, 'limit': 30, 'total': 999999}

    def playerContent(self, flag, id, vipFlags):
        """解析真实播放地址。保留 param 中的 +、/、= 等加密字符。"""
        try:
            parts = id.split('||', 1)
            param_str = parts[0].strip()
            resolutions = parts[1].split('@') if len(parts) > 1 and parts[1] else []

            params = {}
            for pair in param_str.split('&'):
                if '=' not in pair:
                    continue
                key, value = pair.split('=', 1)
                # 不能使用 unquote_plus：播放 param 常含“+”，转为空格后接口会失效。
                params[urllib.parse.unquote(key)] = urllib.parse.unquote(value)

            if resolutions:
                # 接口通常接受原始清晰度名称，例如 1080、1080P、4K。
                resolutions = [x for x in resolutions if x]
                resolutions.sort(
                    key=lambda x: (int(re.sub(r'\D', '', x) or (2160 if '4K' in x.upper() else 0))),
                    reverse=True
                )
                if resolutions:
                    params['resolution'] = resolutions[0]

            if not params:
                print(f"播放参数为空，原始ID: {id}")
                return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

            data = self.get_data(params, '/App/Resource/VurlDetail/showOne', use_cache=False)
            play_url = self._extract_play_url(data)
            if not play_url:
                print(f"播放接口未返回地址: {data}")
                return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

            # 网页版后台会读取 header 对象并据此通过同源媒体代理请求 HLS。
            play_header = {
                "User-Agent": self.media_ua,
                "Referer": self.media_referer
            }
            return {
                "parse": 0,
                "jx": 0,
                "playUrl": "",
                "url": play_url,
                "header": play_header
            }
        except Exception as e:
            print(f"播放解析失败: {e}")
            return {"parse": 0, "jx": 0, "playUrl": "", "url": "", "header": {}}

    def _extract_play_url(self, data):
        """兼容新版接口不同层级的播放地址字段。"""
        if isinstance(data, str):
            return data.strip() if data.startswith(('http://', 'https://')) else ''
        if not isinstance(data, dict):
            return ''

        for key in ('url', 'play_url', 'playUrl', 'vurl', 'video_url', 'videoUrl'):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        for key in ('data', 'info', 'result', 'vod', 'play'):
            value = data.get(key)
            if isinstance(value, (dict, str)):
                found = self._extract_play_url(value)
                if found:
                    return found
        return ''

    def isVideoFormat(self, url):
        video_formats = ['.m3u8', '.mp4', '.avi', '.mkv', '.flv', '.ts']
        path = urllib.parse.urlsplit(str(url or '')).path.lower()
        return any(path.endswith(fmt) for fmt in video_formats)

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return None

    def get_cached_data(self, cache_key, data, path):
        current_time = time.time()
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if current_time - timestamp < self.cache_timeout:
                return cached_data
        result = self.get_data(data, path)
        if result:
            self.cache[cache_key] = (result, current_time)
        return result

if __name__ == '__main__':
    pass
