# -*- coding: utf-8 -*-
# by @一朵诡异的花
import json
import random
import re
import sys
import time
from base64 import b64encode, b64decode
from concurrent.futures import ThreadPoolExecutor

# 引入 RSA 加解密所需模块
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

sys.path.append('..')
from base.spider import Spider

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except Exception:
    requests = None

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
        self._pub_key = None      # RSA 公钥对象缓存
        self._pri_key = None      # RSA 私钥对象缓存
        self.refresh_token()

    def getName(self):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    # 1. 修改为主机域名
    host = 'http://qkys.qukanwh.com'

    # 2. 同步原脚本的配置请求头
    headers = {
        'HOST': 'qkys.qukanwh.com',
        'User-Agent': 'okhttp/4.12.0',
        'client': 'app',
        'deviceType': 'Android',
        'Referer': ''
    }

    # 3. 导入原脚本中的 RSA 密钥对与配置
    publicKey_str = "-----BEGIN PUBLIC KEY-----\nMIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCoYt0BP77U+DM08BiI/QbSRIfxijXo85BTPqIM1Ow8BNwhLETzRIZ+dEwdWDbydG/PspgBAfRpGaYVdJYtvaC2JnoO8+Ik6qMWojfEJxSFLa0Pb0A892tun4gsxoEMjcreZ+YGyaBxAfqX0BSMfdrOgIYaZQjYrw9TRLlUT31QoQIDAQAB\n-----END PUBLIC KEY-----"
    privateKey_str = "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCquQQ5r6+yJI8CDFkXRp8vUsdD45ov8EP12ooLs56ca2DQXaSNGS9910bAPVA9chkp0mKIvKqjAsHz5Tl9EeNPblarGEeJUIxpxZtiSqNTpvtiD/TjhpzuHYic7RAfQ/h7p/ypE8ymU42pYjsB5t26Mv6XgkLV+jzrSf73HlCuS0iMyLmt6zz3Mw9izM13EpB8iFLtfbbYymycKTx4RAmPQLwhNGex/AlUIYxXP4R2yyaa4W6mEtc6aME2QuzJFxPgP3HJ9NBx/LWVn4skxWjZ7zg+VRQRHnjyVaSLu3Z5gN5ITWCyE32qaHJa6WBahZj5jWhRyAG1bQ+xKJa8lBL5AgMBAAECggEAUwv9SjJ0PSwbhNuM2w23kcWquROWhYtTA91zGY4esehqB/IFgb2mpIh8Gje5OKqwIu/8jpd4SiOlRYdUF8sD0DfUYRZGdj2AkFNX6tBz8tVfo6wvbB6naA1lzzBij1L5JO3qsjS3cJFkb+kg2yP66AC2Z+0tpfk8eRhdtshAZwfcd1DEGt1uAvYL1eaUK9HRvpt9lPeGcHERDl2hBd4uyaF0K1O+zF9y59nYbTySWPxRZq3sFEE85xRMlstD7YZi7W2gKvMFRD4/FKmrZ3m7aKJRITtyKOyyPcYmepNv3Qv7kk59Pg38n2WWQ0Ra/bCH3E48YNCnQvZMpitkTfJhoQKBgQDbnROOYTP8OTJ6f/qhoGjxeO3x1VOaOp8l0x7b0SCfoqNGS0Cyiqj72BmJtPMPqSTjn6MmNzqbg1KOdhXyzNozs+i5ccW1M56j96mr5I/Z0FpE3oyIHNfDDBlf9M8YQqEF9oYxniYYft9oapO7cRQkHER6qpvnHTavwlv4m78CXwKBgQDHAjs2YlpKDdI1lcbZJCc7TwtH+Pd2bUki8YXafWNcPhITQHbOZjr310eK1QJC6GJncjkOqbX7yv3ivvTO35FZTQhuA1xEG1P00FG8bE0tHYPIwQHi9y0eA5cieMdo8E6XYria1mw/3fqSQEsfZyJlR32JQIoGAipM8iO1X2nZpwKBgDkMFIhnt5lNQk+P7wsNIDWZtDWdtJnboHuy29E+Abt2A/O+mI/IdRz2hau/1WO8DFkUnszOi+rZshhPlGP90rCbi1igtTrcrdjp/KkqNjPea5R4OwkgdOu1uOG0NheXNzzVTQaWjk7Opjn5dWa7eP/oV+GFb/oZHJuLYVizHGsBAoGADA7rjZEKDYCm4w5PPSr+oY5ZjaPdQrS+gLqHtMRyN82fBMGcMUdqfUfzEstzVqCEDeaS5HuOBlK3bXzKkppjUTjksN3NQmcxgBz7RuJ9DqXCLXDcb2cwuafYCYOt+YLOEEgwDVm+t2P44dG5e46hO+fICH/7nP+WlpD5buz4GfMCgYB57r3g/6hi9WUDnfc7ZAzWMqR0EhJVYKYy+KFEtdIPzhkkIHq5RASe88E9kzoGoZFdb3tIjvGZWcHerirrqWkMsuQtP/Qi0zjieid5tAPj+r4kbiCVTw0E0jnmPBzGInQi7lpeTTKnG1fbyS5lBS+WmHfIuzpECgCkxhaT+LJJkg==\n-----END PRIVATE KEY-----"

    # RSA 公钥加密实现（密钥对象缓存，避免重复 import）
    def rsa_encrypt(self, text):
        try:
            if getattr(self, '_pub_key', None) is None:
                self._pub_key = RSA.import_key(self.publicKey_str)
            cipher = PKCS1_v1_5.new(self._pub_key)
            cipher_text = cipher.encrypt(text.encode('utf-8'))
            return b64encode(cipher_text).decode('utf-8')
        except Exception as e:
            print(f"RSA加密失败: {e}")
            return ""

    # RSA 私钥解密实现（密钥对象缓存）
    def rsa_decrypt(self, text):
        try:
            if getattr(self, '_pri_key', None) is None:
                self._pri_key = RSA.import_key(self.privateKey_str)
            cipher = PKCS1_v1_5.new(self._pri_key)
            raw_bytes = b64decode(text.encode('utf-8'))
            
            decrypted = b""
            offset = 0
            while offset < len(raw_bytes):
                chunk = raw_bytes[offset:offset + 256]
                decrypted += cipher.decrypt(chunk, None)
                offset += 256
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"RSA解密失败: {e}")
            return ""

    def homeContent(self, filter):
        self.refresh_token()
        result = {}
        try:
            data = self.post(f"{self.host}/api/v1/app/screen/screenType", headers=self.headers).json()
        except Exception as e:
            print(f"首页分类获取失败: {e}")
            result['class'] = []
            result['filters'] = {}
            return result
        cate = {
            "类型": "type",
            "地区": "area",
            "年份": "year"
        }
        sort = {
            'key': 'sort',
            'name': '排序',
            'value': [{'n': '最新', 'v': 'NEWEST'}, {'n': '热门', 'v': 'HOT'}, {'n': '收藏', 'v': 'COLLECT'}]
        }
        classes = []
        filters = {}
        for k in data.get('data', []):
            classes.append({
                'type_name': k['name'],
                'type_id': str(k['id'])
            })
            filters[str(k['id'])] = []
            for v in k.get('children', []):
                if v['name'] in cate:
                    filters[str(k['id'])].append({
                        'name': v['name'],
                        'key': cate[v['name']],
                        'value': [{'n': i['name'], 'v': i['name']} for i in v.get('children', [])]
                    })
            filters[str(k['id'])].append(sort)
        result['class'] = classes
        result['filters'] = filters
        return result

    def homeVideoContent(self):
        self.refresh_token()
        jdata = {
            "condition": {
                "sreecnTypeEnum": "NEWEST"
            },
            "pageNum": 1,
            "pageSize": 40
        }
        try:
            data = self.post(f"{self.host}/api/v1/app/screen/screenMovie", headers=self.headers, json=jdata).json()
            return {'list': self.getlist(data.get('data', {}).get('records', []))}
        except Exception as e:
            print(f"首页视频获取失败: {e}")
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        self.refresh_token()
        # 保持最纯粹的条件字段，移除任何空字符串占位
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
            'pageNum': int(pg),
            'pageSize': 40,
        }
        
        try:
            data = self.post(f"{self.host}/api/v1/app/screen/screenMovie", headers=self.headers, json=jdata).json()
            result = {}
            if data and data.get('data') and 'records' in data['data']:
                result['list'] = self.getlist(data['data']['records'])
            else:
                result['list'] = []
            result['page'] = pg
            result['pagecount'] = 9999
            result['limit'] = 40
            result['total'] = 999999
            return result
        except Exception as e:
            print(f"分类获取错误: {e}")
            return {'list': [], 'page': pg}

    def detailContent(self, ids):
        self.refresh_token()
        ids = ids[0].split('@@')
        try:
            vod_id = int(ids[0])
        except (ValueError, IndexError):
            return {'list': []}
        type_id = ids[-1] if len(ids) > 1 else ''
        jdata = {"id": vod_id, "typeId": type_id}
        play_params = {
            "id": vod_id,
            "source": 0,
            "typeId": type_id
        }
        encrypt_payload = {"key": self.rsa_encrypt(json.dumps(play_params))}

        # 并行请求：影片描述 + 线路列表（两者互不依赖，省去一次往返耗时）
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_desc = executor.submit(self._fetch_desc, jdata)
            f_players = executor.submit(self._fetch_players, encrypt_payload)
            v = f_desc.result()
            l = f_players.result()

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

        # 一次性并发请求所有线路的剧集列表（不再单独串行请求首选线路）
        pd = {}
        with ThreadPoolExecutor(max_workers=len(l)) as executor:
            futures = [executor.submit(self.getd, play_params, player) for player in l]
            for future in futures:
                try:
                    o, p = future.result()
                    if p:
                        pd.update(self.getv(o, p))
                except Exception as ex:
                    print(f"线路剧集请求失败: {ex}")
        w, e = [], []
        for i, x in pd.items():
            if x:
                w.append(n.get(i, '未知线路'))
                e.append(x)
        vod['vod_play_from'] = '$$$'.join(w)
        vod['vod_play_url'] = '$$$'.join(e)
        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        self.refresh_token()
        jdata = {
            "condition": {
                "value": str(key)
            },
            "pageNum": int(pg),
            "pageSize": 40
        }
        try:
            data = self.post(f"{self.host}/api/v1/app/search/searchMovie", headers=self.headers, json=jdata).json()
            return {'list': self.getlist(data.get('data', {}).get('records', [])), 'page': pg}
        except Exception as e:
            print(f"搜索请求失败: {e}")
            return {'list': [], 'page': pg}

    def playerContent(self, flag, id, vipFlags):
        self.refresh_token()
        header = {'User-Agent': 'okhttp/4.12.0'}
        raw_id_str = self.d64(id)
        if not raw_id_str:
            return {'parse': 0, 'url': '', 'header': header}
        try:
            jdata = json.loads(raw_id_str)
            ep_key = str(jdata.get('episodeId', raw_id_str[:32]))
            # 播放地址缓存命中直接返回（30分钟内有效），省去两次网络请求
            play_cache = getattr(self, '_play_cache', None)
            if play_cache is None:
                play_cache = self._play_cache = {}
            now = time.time()
            cached = play_cache.get(ep_key)
            if cached and now - cached[0] < 1800 and cached[1]:
                return {'parse': 0, 'url': cached[1], 'header': header}

            # 第一次请求：movieDetails 换取 playerUrl
            encrypt_payload = {"key": self.rsa_encrypt(json.dumps(jdata))}
            data = self.post(f"{self.host}/api/v1/app/play/movieDetails", headers=self.headers, json=encrypt_payload, timeout=8).json()
            decrypted_url_data = json.loads(self.rsa_decrypt(data.get('data', '')))
            playerUrl = decrypted_url_data.get('url', '')
            if not playerUrl:
                return {'parse': 0, 'url': '', 'header': header}

            # playerUrl 已是直链则跳过二次解析，直接播放
            if re.search(r'\.(mp4|m3u8)(\?|$)', str(playerUrl), re.IGNORECASE):
                url = playerUrl
            else:
                from urllib.parse import quote
                query = f"playerUrl={quote(str(playerUrl), safe='')}&playerId={jdata['playerId']}"
                pd = self.fetch(f"{self.host}/api/v1/app/play/analysisMovieUrl?{query}", headers=self.headers, timeout=8).json()
                url = pd.get('data', '') or playerUrl
            if url:
                play_cache[ep_key] = (now, url)
            return {'parse': 0, 'url': url, 'header': header}
        except Exception as e:
            print(f"解析流媒体直链失败: {e}")
            return {'parse': 0, 'url': '', 'header': header}

    def localProxy(self, param):
        pass

    def liveContent(self, url):
        pass

    def post(self, url, headers=None, json=None, timeout=10):
        # 自实现POST，Session连接复用，减少TCP握手开销
        if requests is not None:
            sess = getattr(self, '_session', None)
            if sess is None:
                sess = requests.Session()
                self._session = sess
            return sess.post(url, headers=headers or self.headers, json=json, timeout=timeout, verify=False)
        return super().post(url, headers=headers, json=json)

    def refresh_token(self):
        if getattr(self, '_token_ready', False) and self.headers.get('token'):
            return
        try:
            token = self.gettk()
            if token:
                self.headers['token'] = token
                self._token_ready = True
        except Exception as e:
            print(f"获取token失败: {e}")

    def gettk(self):
        try:
            data = self.fetch(f"{self.host}/api/v1/app/user/visitorInfo", headers=self.headers, timeout=10).json()
            return data.get('data', {}).get('token', '')
        except:
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
        # 获取影片描述信息
        try:
            v = self.post(f"{self.host}/api/v1/app/play/movieDesc", headers=self.headers, json=jdata, timeout=8).json()
            return v.get('data') or {}
        except Exception as e:
            print(f"详情请求失败: {e}")
            return {}

    def _fetch_players(self, encrypt_payload):
        # 获取线路列表
        try:
            c_res = self.post(f"{self.host}/api/v1/app/play/movieDetails", headers=self.headers, json=encrypt_payload, timeout=8).json()
            decrypted = self.rsa_decrypt(c_res.get('data', ''))
            if decrypted:
                return json.loads(decrypted).get('moviePlayerList', [])
        except Exception as e:
            print(f"线路列表请求失败: {e}")
        return []

    def getd(self, jdata, player):
        x = jdata.copy()
        x.update({'playerId': player['id']})
        encrypt_payload = {"key": self.rsa_encrypt(json.dumps(x))}
        try:
            response = self.post(f"{self.host}/api/v1/app/play/movieDetails", headers=self.headers, json=encrypt_payload, timeout=8).json()
            decrypted_str = self.rsa_decrypt(response.get('data', ''))
        except Exception:
            return x, []
        if decrypted_str:
            decrypted_episode = json.loads(decrypted_str)
            return x, decrypted_episode.get('episodeList', [])
        return x, []

    def getv(self, d, c):
        f = {str(d['playerId']): ''}
        g = []
        for i in c:
            j = d.copy()
            j.update({'episodeId': i['id']})
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
            return b64encode(text.encode('utf-8')).decode('utf-8')
        except:
            return ""

    def d64(self, encoded_text):
        try:
            return b64decode(encoded_text.encode('utf-8')).decode('utf-8')
        except:
            return ""
