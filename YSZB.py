# -*- coding: utf-8 -*-
"""
央视频直播+7天回看 UI9专用Python爬虫
严格对标netflixgc UI9模板结构
只套标准格式、保留原生播放核心、零功能篡改
依赖：requests
"""
import re
import os
import time
import json
import random
import struct
import binascii
import base64
import urllib3
from urllib.parse import urljoin
from datetime import datetime

# 依赖容错降级（对标UI9模板）
try:
    import requests
except Exception:
    requests = None

# UI9父类兜底（对标UI9模板）
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

# 关闭SSL报错（保证接口正常请求）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Spider(BaseSpider):
    # UI9默认扩展配置，后台extend可JSON覆盖
    DEFAULT_EXT = {
        "ua_pc": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
    }

    # 频道数据源【原生无修改】
    CHANNELS = {
        'cctv1':     {'name': 'CCTV1',     'cnlid': '2024078201', 'livepid': '600001859', 'defn': 'fhd'},
        'cctv2':     {'name': 'CCTV2',     'cnlid': '2024075401', 'livepid': '600001800', 'defn': 'fhd'},
        'cctv3':     {'name': 'CCTV3',     'cnlid': '2024068501', 'livepid': '600001801', 'defn': 'fhd'},
        'cctv4':     {'name': 'CCTV4',     'cnlid': '2029797101', 'livepid': '600001814', 'defn': 'fhd'},
        'cctv5':     {'name': 'CCTV5',     'cnlid': '2024078401', 'livepid': '600001818', 'defn': 'fhd'},
        'cctv5p':    {'name': 'CCTV5+',    'cnlid': '2024078001', 'livepid': '600001817', 'defn': 'fhd'},
        'cctv6':     {'name': 'CCTV6',     'cnlid': '2013693901', 'livepid': '600108442', 'defn': 'fhd'},
        'cctv7':     {'name': 'CCTV7',     'cnlid': '2024072001', 'livepid': '600004092', 'defn': 'fhd'},
        'cctv8':     {'name': 'CCTV8',     'cnlid': '2029793001', 'livepid': '600001803', 'defn': 'fhd'},
        'cctv9':     {'name': 'CCTV9',     'cnlid': '2024078601', 'livepid': '600004078', 'defn': 'fhd'},
        'cctv10':    {'name': 'CCTV10',    'cnlid': '2024078701', 'livepid': '600001805', 'defn': 'fhd'},
        'cctv11':    {'name': 'CCTV11',    'cnlid': '2027248701', 'livepid': '600001806', 'defn': 'fhd'},
        'cctv12':    {'name': 'CCTV12',    'cnlid': '2027248801', 'livepid': '600001807', 'defn': 'fhd'},
        'cctv13':    {'name': 'CCTV13',    'cnlid': '2029797201', 'livepid': '600001811', 'defn': 'fhd'},
        'cctv14':    {'name': 'CCTV14',    'cnlid': '2027248901', 'livepid': '600001809', 'defn': 'fhd'},
        'cctv15':    {'name': 'CCTV15',    'cnlid': '2027249001', 'livepid': '600001815', 'defn': 'fhd'},
        'cctv16':    {'name': 'CCTV16',    'cnlid': '2027249101', 'livepid': '600098637', 'defn': 'fhd'},
        'cctv164k':  {'name': 'CCTV16(4K)', 'cnlid': '2027249301', 'livepid': '600099502', 'defn': 'fhd'},
        'cctv17':    {'name': 'CCTV17',    'cnlid': '2027249401', 'livepid': '600001810', 'defn': 'fhd'},
        'cctv4k':    {'name': 'CCTV4K',    'cnlid': '2029810301', 'livepid': '600002264', 'defn': 'fhd'},
        'cctv8k':    {'name': 'CCTV8K',    'cnlid': '2026774101', 'livepid': '600156816', 'defn': 'fhd'},
        'cgtn':      {'name': 'CGTN',       'cnlid': '2024181701', 'livepid': '600014550', 'defn': 'fhd'},
        'bjws':      {'name': '北京卫视',     'cnlid': '2024052703', 'livepid': '600002309', 'defn': 'fhd'},
        'jsws':      {'name': '江苏卫视',     'cnlid': '2024171103', 'livepid': '600002521', 'defn': 'fhd'},
        'dfws':      {'name': '东方卫视',     'cnlid': '2024054503', 'livepid': '600002483', 'defn': 'fhd'},
        'zjws':      {'name': '浙江卫视',     'cnlid': '2024054703', 'livepid': '600002520', 'defn': 'fhd'},
        'hnws':      {'name': '湖南卫视',     'cnlid': '2024054803', 'livepid': '600002475', 'defn': 'fhd'}
    }

    CHANNEL_GROUPS = {
        '央视': ['cctv1','cctv2','cctv3','cctv4','cctv5','cctv5p','cctv6','cctv7','cctv8','cctv9','cctv10','cctv11','cctv12','cctv13','cctv14','cctv15','cctv16','cctv164k','cctv17','cctv4k','cctv8k','cgtn'],
        '卫视': ['bjws','jsws','dfws','zjws','hnws']
    }

    # ===================== UI9标准固定方法（1:1对标模板） =====================
    def getName(self):
        return "央视频直播回看"

    def init(self, extend=""):
        # 加载后台扩展配置（UI9标准）
        self.ext = dict(self.DEFAULT_EXT)
        if isinstance(extend, dict):
            self.ext.update(extend)
        elif isinstance(extend, str) and extend.strip():
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict):
                    self.ext.update(cfg)
            except Exception:
                pass
        # 初始化会话、请求头
        self.session = requests.Session() if requests else None
        self.headers = {
            'User-Agent': self.ext["ua_pc"],
            'Referer': 'https://ysp.cctv.cn/'
        }
        self.timeout = 12

    # 空列表模板（UI9标准）
    def _empty_list(self, page=1):
        return {
            'list': [],
            'page': page,
            'pagecount': 1,
            'limit': 40,
            'total': 0
        }

    # 视频格式校验（UI9标准）
    def isVideoFormat(self, url):
        return bool(re.search(r"(?i)\.m3u8(\?|$)", str(url)))

    def manualVideoCheck(self):
        return False

    # ===================== UI9首页分类 =====================
    def homeContent(self, filter):
        return {
            "class": [
                {"type_id": "yx", "type_name": "央视频道"},
                {"type_id": "ws", "type_name": "卫视频道"}
            ],
            "filters": {}
        }

    def homeVideoContent(self):
        return self._empty_list()

    # ===================== 分类列表 =====================
    def categoryContent(self, cid, pg, filter, extend):
        page = int(pg) if pg.isdigit() else 1
        res_list = []
        if cid == "yx":
            keys = self.CHANNEL_GROUPS["央视"]
        elif cid == "ws":
            keys = self.CHANNEL_GROUPS["卫视"]
        else:
            return self._empty_list(page)

        for k in keys:
            info = self.CHANNELS.get(k)
            if not info:
                continue
            res_list.append({
                "vod_id": k,
                "vod_name": info["name"],
                "vod_pic": "",
                "vod_remarks": "高清直播"
            })
        return {
            "list": res_list,
            "page": page,
            "pagecount": 1,
            "limit": 40,
            "total": len(res_list)
        }

    # ===================== 详情选集（直播+7天回看） =====================
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]
        info = self.CHANNELS.get(vid)
        if not info:
            return {"list": []}

        play_list = []
        now = int(time.time())
        for i in range(7, -1, -1):
            ts = now - i * 86400
            dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            key_ts = datetime.fromtimestamp(ts).strftime("%Y%m%d%H%M%S")
            if i == 0:
                play_list.append(f"正在直播${vid}#{key_ts}")
            else:
                play_list.append(f"{dt} 回看${vid}#{key_ts}")

        return {
            "list": [{
                "vod_id": vid,
                "vod_name": info["name"],
                "vod_pic": "",
                "vod_play_from": "默认源",
                "vod_play_url": "#".join(play_list)
            }]
        }

    # ===================== 核心加密类【原生完整无截断、无修改】 =====================
    class CKeyManager:
        DELTA = 0x9e3779b9
        ROUNDS = 16
        LOG_ROUNDS = 4
        SALT_LEN = 2
        ZERO_LEN = 7
        TEA_CKEY = binascii.unhexlify('59b2f7cf725ef43c34fdd7c123411ed3')
        GUARD_TEA_KEY = binascii.unhexlify('110DBEC10C23E7D2E56A1CAD6914EF1B')

        def __init__(self):
            self.xorKey = bytes([0x84, 0x2E, 0xED, 0x08, 0xF0, 0x66, 0xE6, 0xEA,0x48, 0xB4, 0xCA, 0xA9, 0x91, 0xED, 0x6F, 0xF3])
            self.guardXorKey = bytes([0xB3, 0xC9, 0x53, 0xA0, 0x69, 0x13, 0xAD, 0x4D])
            self.standardAlphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
            self.customAlphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
            self.guid = self.generate_guid()

        def generate_guid(self):
            parts = [format(random.getrandbits(32), '08x'),format(random.getrandbits(16), '04x'),format(random.getrandbits(16), '04x'),format(random.getrandbits(16), '04x'),format(random.getrandbits(48), '012x')]
            return ''.join(parts).ljust(32, '0')

        @staticmethod
        def calc_signature(buffer_bytes):
            signature = 0
            for b in buffer_bytes:
                signature = (0x83 * signature + b) & 0x7FFFFFFF
            return signature

        def custom_decode(self, text):
            if not text:return b''
            text = text.rstrip('=')
            if len(text) % 4 != 0:text += '=' * (4 - len(text) % 4)
            trans = str.maketrans(self.customAlphabet[:64], self.standardAlphabet[:64])
            return base64.b64decode(text.translate(trans))

        def custom_encode(self, data):
            trans = str.maketrans(self.standardAlphabet[:64], self.customAlphabet[:64])
            return base64.b64encode(data).decode().translate(trans).rstrip('=')

        def xor_array(self, byte_array):
            result = bytearray(len(byte_array))
            for i, b in enumerate(byte_array):
                result[i] = b ^ self.xorKey[i & 0xF]
            return bytes(result)

        def tea_encrypt_ecb(self, p_in_buf, p_key):
            if len(p_in_buf) < 8:p_in_buf = p_in_buf.ljust(8, b'\0')
            y, z = struct.unpack('>2I', p_in_buf[:8])
            k = struct.unpack('>4I', p_key[:16])
            sum_val = 0
            for _ in range(self.ROUNDS):
                sum_val = (sum_val + self.DELTA) & 0xFFFFFFFF
                y = (y + (((z << 4) + k[0]) ^ (z + sum_val) ^ ((z >> 5) + k[1]))) & 0xFFFFFFFF
                z = (z + (((y << 4) + k[2]) ^ (y + sum_val) ^ ((y >> 5) + k[3]))) & 0xFFFFFFFF
            return struct.pack('>2I', y, z)

        def tea_decrypt_ecb(self, p_in_buf, p_key):
            y, z = struct.unpack('>2I', p_in_buf[:8])
            k = struct.unpack('>4I', p_key[:16])
            sum_val = (self.DELTA << self.LOG_ROUNDS) & 0xFFFFFFFF
            for _ in range(self.ROUNDS):
                z = (z - (((y << 4) + k[2]) ^ (y + sum_val) ^ ((y >> 5) + k[3]))) & 0xFFFFFFFF
                y = (y - (((z << 4) + k[0]) ^ (z + sum_val) ^ ((z >> 5) + k[1]))) & 0xFFFFFFFF
                sum_val = (sum_val - self.DELTA) & 0xFFFFFFFF
            return struct.pack('>2I', y, z)

        def oi_symmetry_encrypt2(self, p_in_buf, n_in_buf_len, p_key):
            n_pad_salt_body_zero_len = n_in_buf_len + 1 + self.SALT_LEN + self.ZERO_LEN
            n_pad_len = (8 - n_pad_salt_body_zero_len % 8) % 8
            p_out_buf = bytearray()
            src_buf = bytearray(8)
            src_buf[0] = (random.randint(0, 255) & 0xF8) | n_pad_len
            for i in range(1, 1 + n_pad_len):src_buf[i] = random.randint(0, 255)
            src_i = 1 + n_pad_len
            iv_plain, iv_crypt = bytearray(8), bytearray(8)
            for _ in range(self.SALT_LEN):
                if src_i >= 8:
                    for j in range(8):src_buf[j] ^= iv_crypt[j]
                    temp_out = self.tea_encrypt_ecb(bytes(src_buf), p_key)
                    temp_bytes = list(temp_out)
                    for j in range(8):temp_bytes[j] ^= iv_plain[j]
                    iv_plain, iv_crypt = src_buf[:], bytes(temp_bytes)
                    p_out_buf.extend(temp_bytes)
                    src_i = 0
                src_buf[src_i] = random.randint(0, 255)
                src_i += 1
            idx = 0
            while n_in_buf_len > 0:
                if src_i >= 8:
                    for j in range(8):src_buf[j] ^= iv_crypt[j]
                    temp_out = self.tea_encrypt_ecb(bytes(src_buf), p_key)
                    temp_bytes = list(temp_out)
                    for j in range(8):temp_bytes[j] ^= iv_plain[j]
                    iv_plain, iv_crypt = src_buf[:], bytes(temp_bytes)
                    p_out_buf.extend(temp_bytes)
                    src_i = 0
                src_buf[src_i] = p_in_buf[idx]
                src_i += 1
                idx += 1
                n_in_buf_len -= 1
            for _ in range(self.ZERO_LEN):
                if src_i >= 8:
                    for j in range(8):src_buf[j] ^= iv_crypt[j]
                    temp_out = self.tea_encrypt_ecb(bytes(src_buf), p_key)
                    temp_bytes = list(temp_out)
                    for j in range(8):temp_bytes[j] ^= iv_plain[j]
                    iv_plain, iv_crypt = src_buf[:], bytes(temp_bytes)
                    p_out_buf.extend(temp_bytes)
                    src_i = 0
                src_buf[src_i] = 0
                src_i += 1
            if src_i > 0:
                for j in range(src_i, 8):src_buf[j] = 0
                for j in range(8):src_buf[j] ^= iv_crypt[j]
                temp_out = self.tea_encrypt_ecb(bytes(src_buf), p_key)
                temp_bytes = list(temp_out)
                for j in range(8):temp_bytes[j] ^= iv_plain[j]
                p_out_buf.extend(temp_bytes)
            return bytes(p_out_buf)

        def generate_ck_guard_time(self, timestamp, guid):
            body = struct.pack('>I', timestamp)
            for part in [guid[-5:], "", "", "-1"]:
                body += struct.pack('>H', len(part)) + part.encode('utf-8')
            plain = struct.pack('>H', len(body)) + body
            checksum = self.calc_signature(plain)
            encrypted = self.oi_symmetry_encrypt2(plain, len(plain), self.GUARD_TEA_KEY)
            encrypted += struct.pack('>I', checksum)
            bytes_list = [b ^ self.guardXorKey[i & 7] for i, b in enumerate(encrypted)]
            return binascii.hexlify(bytes(bytes_list)).decode().upper()

        def encrypt_data_to_ckey(self, data):
            checksum = self.calc_signature(data)
            encrypted = self.oi_symmetry_encrypt2(data, len(data), self.TEA_CKEY)
            encrypted += struct.pack('>I', checksum)
            return "--01" + self.custom_encode(self.xor_array(encrypted))

        def build_packet(self, params):
            data = bytearray(binascii.unhexlify('0000004200000004000004d2'))
            data += struct.pack('>I', params['Platform'])
            data += struct.pack('>I', 0)
            data += struct.pack('>I', params['Timestamp'])
            for key in ['Sdtfrom','randFlag','appVer','vid','guid']:
                val = params[key].encode('utf-8')
                data += struct.pack('>H', len(val)) + val
            data += struct.pack('>I',1)+struct.pack('>I',1)
            data += struct.pack('>H',8)+b"2622783A"
            data += struct.pack('>H',3)+b"nil"
            uuid = params['uuid4'].encode('utf-8')
            data += struct.pack('>H',len(uuid))+uuid
            data += struct.pack('>H',3)+b"nil"
            data += struct.pack('>H',8)+b"v0.1.000"
            data += struct.pack('>H',35)+b"com.cctv.yangshipin.app.iphone"
            data += struct.pack('>H',7)+b"4330403"
            data += struct.pack('>H',9)+b"ex_json_bus"
            data += struct.pack('>H',8)+b"ex_json_vs"
            guard = params['ck_guard_time'].encode('utf-8')
            data += struct.pack('>H',len(guard))+guard
            body_len = len(data)
            buf = struct.pack('>H', body_len) + data
            sign = self.calc_signature(buf)
            buf = buf[:18] + struct.pack('>I', sign) + buf[22:]
            return buf

        def generate_ckey(self, cnlid):
            ts = int(time.time())
            randFlag = base64.b64encode(os.urandom(18)).decode()
            uuid4 = f"{random.getrandbits(16):04x}-{random.getrandbits(16):04x}-{random.getrandbits(16):04x}-{random.getrandbits(16):04x}"
            ck_guard = self.generate_ck_guard_time(ts, self.guid)
            params = {
                "Platform":4330403,"Timestamp":ts,"Sdtfrom":"dcgh","vid":cnlid,
                "guid":self.guid,"appVer":"V8.22.1035.3031","randFlag":randFlag,"uuid4":uuid4,"ck_guard_time":ck_guard
            }
            return {"ckey":self.encrypt_data_to_ckey(self.build_packet(params)),"params":params}

        def get_play_url(self, cnlid, livepid, defn, playback=None):
            ck = self.generate_ckey(cnlid)
            params = {
                "atime":"120","livepid":livepid,"cnlid":cnlid,"appVer":"V8.22.1035.3031",
                "cmd":"2","defn":defn,"device":"iPhone","encryptVer":"4.2","platform":"4330403",
                "sdtfrom":"v3021","stream":"1","system":"1","sysver":"ios18.2.1","cKey":ck['ckey'],"guid":self.guid
            }
            if playback:
                params["playbacktime"] = str(playback)
            headers = {"User-Agent":"qqlive","Referer":"https://ysp.cctv.cn/"}
            try:
                res = requests.get("https://bkliveinfo.ysp.cctv.cn", params=params, headers=headers, timeout=10, verify=False)
                js = res.json()
                if js.get("iretcode") == 0:
                    return js.get("playurl")
            except:
                pass
            return None

    # ===================== UI9播放器解析（原生可用） =====================
    def playerContent(self, flag, pid, vipFlags):
        try:
            if "#" in pid:
                cid, ts_str = pid.split("#")
                playback_dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
                playback_ts = int(playback_dt.timestamp())
            else:
                cid = pid
                playback_ts = None

            info = self.CHANNELS.get(cid)
            if not info:
                return {"parse":1,"url":""}

            ck = self.CKeyManager()
            url = ck.get_play_url(info["cnlid"], info["livepid"], info["defn"], playback_ts)
            if url and self.isVideoFormat(url):
                return {"parse":0,"url":url,"header":self.headers}
            return {"parse":1,"url":""}
        except:
            return {"parse":1,"url":""}

    # ===================== UI9搜索空方法（关闭搜索） =====================
    def searchContent(self, key, quick, pg=1):
        return self._empty_list(pg)

    def searchContentPage(self, key, quick, pg="1"):
        return self._empty_list(int(pg))

    # ===================== UI9必备兜底方法 =====================
    def localProxy(self, param=''):
        return [404, "text/plain", "NotFound"]

if __name__ == '__main__':
    sp = Spider()
    sp.init()
