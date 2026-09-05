// 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
// 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。

import { Crypto, _ } from 'assets://js/lib/cat.js';

let host = 'https://bubutv.top';
let hosts = ['https://bubutv.top'];
let device_id = '';

const pkg = 'com.sunshine.tv';
const ver = '3';
const device_id_cache_key = 'com.sunshine.tv_3qys_B7k7Dt56Rn';

async function init(cfg) {
    let ext = cfg && cfg.ext ? cfg.ext : '';
    try {
        if (typeof ext === 'string' && ext.trim().startsWith('{')) {
            ext = JSON.parse(ext);
        }
    } catch (e) {}

    let site = '';
    if (typeof ext === 'string') {
        site = ext;
    } else if (ext && typeof ext === 'object') {
        site = ext.site || ext.host || ext.url || '';
    }

    if (site) {
        hosts = site.split(',')
            .map((u) => u.trim().replace(/\/+$/, ''))
            .filter((u) => /^https?:\/\//i.test(u));
        if (hosts.length > 0) host = hosts[0];
    }
}

async function home(filter) {
    try {
        const json = await apiGet('/api.php/app/index/home');
        const categories = (((json || {}).data || {}).categories) || [];
        const classes = categories.map((i) => ({
            type_id: i.type_name || '',
            type_name: i.type_name || ''
        })).filter((i) => i.type_id && i.type_name);

        const videos = [];
        for (const cat of categories) {
            videos.push(...arr2vods(cat.videos || []));
        }
        return JSON.stringify({ class: classes, list: videos });
    } catch (e) {
        return JSON.stringify({ class: [], list: [] });
    }
}

async function homeVod() {
    try {
        const json = await apiGet('/api.php/app/index/home');
        const categories = (((json || {}).data || {}).categories) || [];
        const videos = [];
        for (const cat of categories) {
            videos.push(...arr2vods(cat.videos || []));
        }
        return JSON.stringify({ list: videos });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function category(tid, pg, filter, extend) {
    const page = parseInt(pg || 1);
    try {
        const path = `/api.php/app/filter/vod?type_name=${encodeURIComponent(tid || '')}&page=${page}&sort=hits`;
        const json = await apiGet(path);
        return JSON.stringify({
            list: arr2vods((((json || {}).data) || [])),
            pagecount: parseInt((json || {}).pageCount || 1),
            page: page,
            limit: 20,
            total: 999999
        });
    } catch (e) {
        return JSON.stringify({ list: [], pagecount: 0, page: page, limit: 20, total: 0 });
    }
}

async function search(wd, quick, pg = 1) {
    const page = parseInt(pg || 1);
    try {
        const path = `/api.php/app/search/index?wd=${encodeURIComponent(wd || '')}&page=${page}&limit=15`;
        const json = await apiGet(path);
        return JSON.stringify({
            list: arr2vods((((json || {}).data) || [])),
            pagecount: parseInt((json || {}).pageCount || 1),
            page: page,
            limit: 15,
            total: 999999
        });
    } catch (e) {
        return JSON.stringify({ list: [], pagecount: 0, page: page, limit: 15, total: 0 });
    }
}

async function detail(id) {
    try {
        const vodId = Array.isArray(id) ? id[0] : id;
        const json = await apiGet(`/api.php/app/vod/get_detail?vod_id=${encodeURIComponent(vodId || '')}`);
        const dataList = (((json || {}).data) || []);
        if (!dataList.length) return JSON.stringify({ list: [] });

        const data = dataList[0] || {};
        const vodplayer = (json || {}).vodplayer || [];
        const shows = [];
        const play_urls = [];
        const raw_shows = String(data.vod_play_from || '').split('$$$').filter(Boolean);
        const raw_urls_list = String(data.vod_play_url || '').split('$$$');

        for (let i = 0; i < raw_shows.length; i++) {
            const show_code = raw_shows[i];
            const urls_str = raw_urls_list[i] || '';
            let need_parse = 0;
            let is_show = 0;
            let name = show_code;
            const player_info = findPlayer(vodplayer, show_code);

            if (player_info) {
                is_show = 1;
                need_parse = player_info.decode_status || 0;
                const showName = player_info.show || show_code;
                if (String(show_code).toLowerCase() !== String(showName).toLowerCase()) {
                    name = `${showName} (${show_code})`;
                }
            } else {
                // 接口偶尔不返回 vodplayer，直接保留播放组，避免详情页无播放地址。
                is_show = 1;
            }

            if (is_show === 1) {
                const urls = [];
                for (const url_item of urls_str.split('#')) {
                    const pos = url_item.indexOf('$');
                    if (pos > -1) {
                        const episode = url_item.slice(0, pos);
                        const url = url_item.slice(pos + 1);
                        if (episode && url) urls.push(`${episode}$${show_code}@${parseInt(need_parse || 0)}@${url}`);
                    }
                }
                if (urls.length > 0) {
                    play_urls.push(urls.join('#'));
                    shows.push(name);
                }
            }
        }

        const video = {
            vod_id: toStr(data.vod_id),
            vod_name: data.vod_name || '',
            vod_pic: data.vod_pic || '',
            vod_remarks: data.vod_remarks || '',
            vod_year: data.vod_year || '',
            vod_area: data.vod_area || '',
            vod_actor: data.vod_actor || '',
            vod_director: data.vod_director || '',
            vod_content: data.vod_content || '',
            vod_play_from: shows.join('$$$'),
            vod_play_url: play_urls.join('$$$'),
            type_name: data.vod_class || data.type_name || ''
        };
        return JSON.stringify({ list: [video] });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function play(flag, vid, flags) {
    const parsed = parsePlayId(vid || '');
    const play_from = parsed.play_from;
    const need_parse = parsed.need_parse;
    const raw_url = parsed.raw_url;
    let url = '';
    let jx = 0;

    if (need_parse === '1') {
        try {
            const json = await apiGet(`/api.php/app/decode/url/?url=${encodeURIComponent(raw_url)}&vodFrom=${encodeURIComponent(play_from)}`, 30000);
            const playUrl = (json || {}).data || '';
            if (typeof playUrl === 'string' && playUrl.startsWith('http')) url = playUrl;
        } catch (e) {}
    }

    if (!url) {
        url = raw_url;
        if (/(www\.iqiyi|v\.qq|v\.youku|www\.mgtv|www\.bilibili)\.com/i.test(raw_url)) {
            jx = 1;
        }
    }

    return JSON.stringify({
        jx: jx,
        parse: 0,
        url: url,
        header: {
            'User-Agent': 'com.sunshine.tv/1.2.0 (Linux;Android 15) AndroidXMedia3/1.4.1',
            'Referer': host + '/'
        }
    });
}

async function apiGet(path, timeout) {
    const hd = await getHeaders();
    const list = hosts && hosts.length ? hosts : [host];
    let lastError = null;
    for (const h of list) {
        try {
            const base = h.replace(/\/+$/, '');
            const resp = await req(base + path, { headers: hd, timeout: timeout || 15000 });
            const content = resp && resp.content ? resp.content : '';
            if (!content) continue;
            const json = JSON.parse(content);
            if (json && (json.data !== undefined || json.pageCount !== undefined || json.code !== undefined || json.msg !== undefined)) {
                host = base;
                return json;
            }
        } catch (e) {
            lastError = e;
        }
    }
    throw lastError || new Error('api request failed');
}

async function getHeaders() {
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const nonce = randomStr(3, '0123456789');

    if (!device_id) {
        try {
            device_id = await local.get('cache', device_id_cache_key);
        } catch (e) {}
        if (!device_id || String(device_id).length !== 16) {
            device_id = randomStr(16);
            try {
                await local.set('cache', device_id_cache_key, device_id);
            } catch (e) {}
        }
    }

    const sign_str = `finger=SF-C3B2B41F6EFFFF9869176CF68F6790E8F07506FC88632C94B4F5F0430D5498CA&id=${pkg}&nonce=${nonce}&sk=SK-thanks&time=${timestamp}&v=${ver}`;
    const sign = sha256(sign_str);
    return {
        'User-Agent': 'okhttp/4.12.0',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'x-aid': pkg,
        'x-ave': ver,
        'x-time': timestamp,
        'x-nonc': nonce,
        'x-sign': sign,
        'x-device-id': device_id,
        'x-device-brand': 'vivo',
        'x-device-model': 'V2309A',
        'x-update-id': '0245861b-2ebf-5524-389d-f983830651ec'
    };
}

function arr2vods(arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map((i) => {
        i = i || {};
        let type_name = i.type_name || '';
        if (i.vod_class) type_name = type_name + (type_name ? ',' : '') + i.vod_class;
        return {
            vod_id: toStr(i.vod_id),
            vod_name: i.vod_name || '',
            vod_pic: i.vod_pic || '',
            vod_remarks: i.vod_remarks || '',
            type_name: type_name,
            vod_year: i.vod_year || ''
        };
    }).filter((i) => i.vod_id && i.vod_name);
}

function findPlayer(vodplayer, show_code) {
    if (!Array.isArray(vodplayer)) return null;
    for (const p of vodplayer) {
        if (p && p.from === show_code) return p;
    }
    return null;
}

function parsePlayId(vid) {
    const first = vid.indexOf('@');
    if (first < 0) return { play_from: '', need_parse: '0', raw_url: vid };
    const second = vid.indexOf('@', first + 1);
    if (second < 0) return { play_from: vid.slice(0, first), need_parse: '0', raw_url: vid.slice(first + 1) };
    return {
        play_from: vid.slice(0, first),
        need_parse: vid.slice(first + 1, second),
        raw_url: vid.slice(second + 1)
    };
}

function randomStr(len, chars = '0123456789abcdef') {
    let str = '';
    for (let i = 0; i < len; i++) {
        str += chars[Math.floor(Math.random() * chars.length)];
    }
    return str;
}

function toStr(v) {
    if (v === undefined || v === null) return '';
    return String(v);
}

function sha256(text) {
    return Crypto.SHA256(text).toString().toUpperCase();
}

export function __jsEvalReturn() {
    return {
        init: init,
        home: home,
        homeVod: homeVod,
        category: category,
        search: search,
        detail: detail,
        play: play
    };
}
