import { Crypto, load, _, jinja2 } from 'assets://js/lib/cat.js';

let url = 'http://dyxz.tv';

const UA = 'Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36';

async function request(reqUrl, extHeader) {
    let headers = {
        'User-Agent': UA,
        'Referer': url
    };
    if (extHeader) {
        let keys = Object.keys(extHeader);
        for (let k = 0; k < keys.length; k++) {
            headers[keys[k]] = extHeader[keys[k]];
        }
    }
    let res = await req(reqUrl, {
        method: 'get',
        headers: headers
    });
    return res.content;
}

async function init(cfg) {
}

async function home(filter) {
    let classes = [
        {'type_id': '1', 'type_name': '电影'},
        {'type_id': '2', 'type_name': '电视剧'},
        {'type_id': '3', 'type_name': '动漫'},
        {'type_id': '4', 'type_name': '综艺'},
        {'type_id': '6', 'type_name': '纪录片'}
    ];
    let filterObj = {
        '1': [
            {'key': 'order', 'name': '排序', 'value': [{'n': '按时间', 'v': 'time'}, {'n': '按人气', 'v': 'hit'}]}
        ],
        '2': [
            {'key': 'order', 'name': '排序', 'value': [{'n': '按时间', 'v': 'time'}, {'n': '按人气', 'v': 'hit'}]}
        ],
        '3': [
            {'key': 'order', 'name': '排序', 'value': [{'n': '按时间', 'v': 'time'}, {'n': '按人气', 'v': 'hit'}]}
        ],
        '4': [
            {'key': 'order', 'name': '排序', 'value': [{'n': '按时间', 'v': 'time'}, {'n': '按人气', 'v': 'hit'}]}
        ],
        '6': [
            {'key': 'order', 'name': '排序', 'value': [{'n': '按时间', 'v': 'time'}, {'n': '按人气', 'v': 'hit'}]}
        ]
    };
    return JSON.stringify({class: classes, filters: filterObj});
}

function parseVodList($) {
    let videos = [];
    // 主页/分类页结构: .stui-vodlist__box
    $('.stui-vodlist__box').each(function() {
        let a = $(this).find('a.stui-vodlist__thumb').first();
        let href = a.attr('href') || '';
        let title = a.attr('title') || '';
        let pic = a.attr('data-original') || a.find('img').attr('data-original') || '';
        let note = a.find('.pic-text').text().trim();
        if (!title) {
            title = $(this).find('h4.title a').attr('title') || $(this).find('h4.title a').text().trim();
        }
        if (href && title) {
            videos.push({
                vod_id: href,
                vod_name: title,
                vod_pic: pic,
                vod_remarks: note
            });
        }
    });
    // 搜索结果结构: .stui-vodlist__media > li
    if (videos.length === 0) {
        $('.stui-vodlist__media li').each(function() {
            let a = $(this).find('a.v-thumb').first();
            let href = a.attr('href') || '';
            let title = a.attr('title') || '';
            let pic = a.attr('data-original') || '';
            let note = a.find('.pic-text').text().trim();
            if (!title) {
                title = $(this).find('h3.title a').text().trim();
            }
            if (href && title) {
                videos.push({
                    vod_id: href,
                    vod_name: title,
                    vod_pic: pic,
                    vod_remarks: note
                });
            }
        });
    }
    return videos;
}

async function homeVod() {
    try {
        const html = await request(url + '/');
        const $ = load(html);
        let videos = parseVodList($);
        return JSON.stringify({list: videos.slice(0, 30)});
    } catch (e) {
        return JSON.stringify({list: []});
    }
}

async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    extend = extend || {};
    try {
        let link = url + '/list/' + tid;
        if (pg > 1) {
            link += '_' + pg;
        }
        link += '.html';
        if (extend.order) {
            link += '?order=' + extend.order;
        }
        const html = await request(link);
        if (!html) return JSON.stringify({page: pg, pagecount: pg, limit: 0, total: 0, list: []});
        const $ = load(html);
        let videos = parseVodList($);

        let pagecount = pg;
        let lastPage = $('.stui-page li:last a').attr('href');
        if (lastPage) {
            let pm = lastPage.match(/list\/\d+_(\d+)\.html/);
            if (pm) {
                pagecount = parseInt(pm[1]);
            }
        }

        return JSON.stringify({
            page: parseInt(pg),
            pagecount: pagecount,
            limit: videos.length,
            list: videos
        });
    } catch (e) {
        return JSON.stringify({page: pg, pagecount: pg, limit: 0, total: 0, list: []});
    }
}

async function detail(id) {
    try {
        let detailUrl = id.startsWith('http') ? id : url + id;
        const html = await request(detailUrl);
        const $ = load(html);

        let title = $('h1.title').first().text().trim();
        if (!title) {
            title = $('.stui-content__thumb img').attr('alt') || '';
        }
        let pic = $('.stui-content__thumb img').attr('data-original') || $('.stui-content__thumb img').attr('src') || '';
        let desc = $('.stui-content__detail .desc').text().trim();
        if (!desc) {
            desc = $('#desc .col-pd').text().trim();
        }

        let playMap = {};
        let tabIdx = 0;
        $('.tab-pane').each(function() {
            tabIdx++;
            let from = '线路' + tabIdx;
            let episodes = [];
            $(this).find('.stui-content__playlist li a').each(function() {
                let epTitle = $(this).attr('title') || $(this).text().trim();
                let epHref = $(this).attr('href') || '';
                if (epHref && epTitle) {
                    episodes.push(epTitle + '$' + epHref);
                }
            });
            if (episodes.length > 0) {
                playMap[from] = episodes;
            }
        });

        if (Object.keys(playMap).length === 0) {
            let episodes = [];
            $('.stui-content__playlist').first().find('li a').each(function() {
                let epTitle = $(this).attr('title') || $(this).text().trim();
                let epHref = $(this).attr('href') || '';
                if (epHref && epTitle) {
                    episodes.push(epTitle + '$' + epHref);
                }
            });
            if (episodes.length > 0) {
                playMap['线路1'] = episodes;
            }
        }

        let vod = {
            vod_id: id,
            vod_name: title,
            vod_pic: pic,
            vod_content: desc,
            vod_play_from: Object.keys(playMap).join('$$$'),
            vod_play_url: Object.values(playMap).map(function(arr) {
                return arr.join('#');
            }).join('$$$')
        };
        return JSON.stringify({list: [vod]});
    } catch (e) {
        return JSON.stringify({list: []});
    }
}

async function play(flag, id, flags) {
    try {
        let playUrl = id.startsWith('http') ? id : url + id;
        let html = await request(playUrl);
        if (!html) {
            return JSON.stringify({parse: 1, jx: 1, url: playUrl});
        }

        let iframeMatch = html.match(/src="(http:\/\/meizi\.yongfan99\.com\/content\.php\?[^"]+)"/);
        if (!iframeMatch) {
            return JSON.stringify({parse: 1, jx: 1, url: playUrl});
        }

        let iframeUrl = iframeMatch[1];
        let vidMatch = iframeUrl.match(/[?&]vid=([^&]+)/);
        let typeMatch = iframeUrl.match(/[?&]type=([^&]+)/);
        if (!vidMatch || !typeMatch) {
            return JSON.stringify({parse: 1, jx: 1, url: playUrl});
        }

        let vid = decodeURIComponent(vidMatch[1]);
        let fromType = decodeURIComponent(typeMatch[1]);

        // 优先使用 parse.kuaijiz.com 解析站获取直链（支持所有类型）
        let parseUrl = 'https://parse.kuaijiz.com/index?t=' + fromType + '&vid=' + encodeURIComponent(vid);
        let parseRes = await req(parseUrl, {
            method: 'get',
            headers: {
                'User-Agent': UA,
                'Referer': url
            }
        });
        let parseHtml = parseRes.content || '';
        let videoUrlMatch = parseHtml.match(/const videoUrl = "([^"]+)"/);
        if (videoUrlMatch) {
            return JSON.stringify({
                parse: 0,
                jx: 0,
                url: videoUrlMatch[1],
                header: {
                    'User-Agent': UA,
                    'Referer': 'https://parse.kuaijiz.com/'
                }
            });
        }

        // 备用：使用 meizi.yongfan99.com 的 api.php（仅 lekanzyw/hyun 有效）
        let playerApi = 'http://meizi.yongfan99.com/player/index.php?t=' + fromType + '&url=' + encodeURIComponent(vid);
        let playerRes = await req(playerApi, {
            method: 'get',
            headers: {
                'User-Agent': UA,
                'Referer': playUrl
            }
        });
        let playerHtml = playerRes.content || '';
        let signMatch = playerHtml.match(/const Sign = "([^"]+)"/);
        if (signMatch) {
            let sign = signMatch[1];
            let apiUrl = 'http://meizi.yongfan99.com/player/api.php?url=' + encodeURIComponent(vid) + '&sign=' + sign + '&t=' + fromType;
            let apiRes = await req(apiUrl, {
                method: 'get',
                headers: {
                    'User-Agent': UA,
                    'Referer': playerApi
                }
            });
            let content = apiRes.content || '';
            if (content.trim().startsWith('{')) {
                let apiData = JSON.parse(content);
                if (apiData.code === 200 && apiData.url) {
                    return JSON.stringify({
                        parse: 0,
                        jx: 0,
                        url: apiData.url,
                        header: {
                            'User-Agent': UA,
                            'Referer': 'http://meizi.yongfan99.com/'
                        }
                    });
                }
            }
        }

        // 都失败则回退 WebView
        return JSON.stringify({parse: 1, jx: 1, url: playUrl});
    } catch (e) {
        return JSON.stringify({parse: 1, jx: 1, url: id});
    }
}

async function search(wd, quick, pg) {
    try {
        let link = url + '/search.php';
        let html = await req(link, {
            method: 'POST',
            headers: {
                'User-Agent': UA,
                'Referer': url,
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: 'searchword=' + encodeURIComponent(wd)
        });
        html = html.content || '';
        const $ = load(html);
        let videos = parseVodList($);
        return JSON.stringify({page: 1, pagecount: 1, limit: videos.length, list: videos});
    } catch (e) {
        return JSON.stringify({page: 1, pagecount: 1, limit: 0, list: []});
    }
}

export function __jsEvalReturn() {
    return {
        init: init,
        home: home,
        homeVod: homeVod,
        category: category,
        detail: detail,
        play: play,
        search: search
    };
}
