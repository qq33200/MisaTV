# -*- coding: utf-8 -*-
# 360资源 - TVBox / CatVod Py 源
# 来源: 站长资源站Pro https://www.zzzypro.com/sites/733.html
# 接口: https://360zyzz.com/api.php/provide/vod/?ac=list / ?ac=detail
# 格式: 苹果CMS(MacCMS)标准采集接口, JSON, code=1 为成功
#   列表:  ?ac=list&pg=1&t=<type_id>&wd=<关键词>
#   详情:  ?ac=detail&ids=<vod_id>, 支持逗号批量 ids, 一次返回多条
#   播放:  vod_play_from 单线路 "360zy", vod_play_url 线路内用 # 分集, 每集 "集名$播放地址"
#          播放地址是直链 .m3u8 (如 vod1.maowushi.com/.../index.m3u8), 走 parse=0
#   注意: 列表接口不返回 vod_pic, 本文件用一次批量详情(ac=detail&ids=...)给当页补海报图
#   注意: 该接口 TLS 前端会挂起不带 ALPN 的 urllib 握手(实测无 ALPN 时握手 15 秒超时,
#         curl 带 ALPN 约 1 秒即通), 本文件在 SSL context 上设了 set_alpn_protocols(["http/1.1"])
# 实测 2026-11-18: 总量 75,214 条, 20 条/页, 接口返回 51 个分类, 其中 7 个总量为 0
#   (1 电影/2 连续剧/3 综艺/4 动漫为父级空类, 17 体育/42 篮球/51 反转爽剧), 已在分类里过滤掉,
#   剩余 44 个; 各分类总量求和 75,194, 与列表 total 75,214 差 20 条(接口数据浮动)。
#   列表/分类/搜索/详情均通, 批量详情 20 条全回; 搜索尊重 wd 关键词, 百分号编码的中文关键词
#   不 403 (搜"战斗之魂"返回 6 条且全部含关键词); 首个 m3u8 HEAD 200, 未观察到地域拦截。
import json
import re
import ssl
import time
import zlib
import gzip
import urllib.request
import urllib.parse
from urllib.parse import quote, unquote

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider(object):
        def getCache(self, key): return None
        def setCache(self, key, value): return "fail"
        def delCache(self, key): return "fail"

API_BASE = "https://360zyzz.com/api.php/provide/vod/"
UA_DEFAULT = "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 2026-11-18 实测: 以下分类总量为 0, 不展示
EMPTY_TYPE_IDS = {"1", "2", "3", "4", "17", "42", "51"}

# 接口挂了时分类也不至于全空, 按 2026-11-18 实测的有数据分类兜底
STATIC_CLASSES = [
    {"type_id": "0", "type_name": "最新更新"},
    {"type_id": "5", "type_name": "伦理片"},
    {"type_id": "6", "type_name": "动作片"},
    {"type_id": "7", "type_name": "喜剧片"},
    {"type_id": "8", "type_name": "爱情片"},
    {"type_id": "9", "type_name": "科幻片"},
    {"type_id": "10", "type_name": "恐怖片"},
    {"type_id": "11", "type_name": "剧情片"},
    {"type_id": "12", "type_name": "战争片"},
    {"type_id": "13", "type_name": "国产剧"},
    {"type_id": "14", "type_name": "香港剧"},
    {"type_id": "15", "type_name": "韩国剧"},
    {"type_id": "16", "type_name": "欧美剧"},
    {"type_id": "18", "type_name": "NBA"},
    {"type_id": "20", "type_name": "惊悚片"},
    {"type_id": "21", "type_name": "家庭篇"},
    {"type_id": "22", "type_name": "古装片"},
    {"type_id": "23", "type_name": "历史片"},
    {"type_id": "24", "type_name": "悬疑片"},
    {"type_id": "25", "type_name": "犯罪片"},
    {"type_id": "26", "type_name": "灾难片"},
    {"type_id": "27", "type_name": "纪录片"},
    {"type_id": "28", "type_name": "短片"},
    {"type_id": "29", "type_name": "动画片"},
    {"type_id": "30", "type_name": "台湾剧"},
    {"type_id": "31", "type_name": "日本剧"},
    {"type_id": "32", "type_name": "海外剧"},
    {"type_id": "33", "type_name": "泰国剧"},
    {"type_id": "34", "type_name": "大陆综艺"},
    {"type_id": "35", "type_name": "港台综艺"},
    {"type_id": "36", "type_name": "日韩综艺"},
    {"type_id": "37", "type_name": "欧美综艺"},
    {"type_id": "38", "type_name": "国产动漫"},
    {"type_id": "39", "type_name": "欧美动漫"},
    {"type_id": "40", "type_name": "日韩动漫"},
    {"type_id": "41", "type_name": "足球"},
    {"type_id": "43", "type_name": "未分类"},
    {"type_id": "45", "type_name": "西部片"},
    {"type_id": "46", "type_name": "爽文短剧"},
    {"type_id": "47", "type_name": "现代都市"},
    {"type_id": "48", "type_name": "脑洞悬疑"},
    {"type_id": "49", "type_name": "年代穿越"},
    {"type_id": "50", "type_name": "古装仙侠"},
    {"type_id": "52", "type_name": "女频恋爱"},
    {"type_id": "53", "type_name": "成长逆袭"},
]

SOURCE_NAMES = {
    "360zy": "360资源",
}


def _clean(s):
    s = str(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').strip()


def _clean_ep_name(name):
    # 集名不能含 $ # , 否则 TVBox 切集会错位; "4K"/"HD中字"这类画质名要保留, 不能都改成"正片"
    t = _clean(name) or "正片"
    t = t.replace("$", "").replace("#", "").replace("$$$", "")
    return t[:40]


class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.api = API_BASE
        self.ua = UA_DEFAULT
        self.timeout = 15
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        # 该接口 TLS 前端会挂起不带 ALPN 的握手, 必须显式声明 ALPN
        try:
            self.ctx.set_alpn_protocols(["http/1.1"])
        except Exception:
            pass
        self._classes = None
        self._classes_exp = 0

    def getName(self):
        return "360资源"

    def init(self, extend=""):
        pass

    # ---------- 底层请求 ----------
    def _headers(self):
        return {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://360zyzz.com/",
        }

    def _http_json(self, url):
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
            try:
                content = resp.read()
            except Exception as e:
                # 个别接口在 Cloudflare 后用 chunked 传输, 终止块常丢, http.client 会抛
                # IncompleteRead, 但 e.partial 里往往已是完整 gzip 正文, 直接用它
                content = getattr(e, "partial", b"") or b""
                if not content:
                    raise
            _stripped = content.lstrip()[:20].lower()
            if _stripped.startswith(b"<!doctype") or _stripped.startswith(b"<html"):
                raise ValueError("non-json html response")
            enc = (resp.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc or content.startswith(b"\x1f\x8b"):
                try:
                    content = gzip.decompress(content)
                except Exception:
                    pass
            elif "deflate" in enc:
                try:
                    content = zlib.decompress(content, -zlib.MAX_WBITS)
                except Exception:
                    pass
            j = json.loads(content.decode("utf-8", "replace"))
            if not isinstance(j, dict) or j.get("code") != 1:
                return None
            return j

    def _api(self, params):
        url = self.api + "?" + urllib.parse.urlencode(params)
        # 首个冷连接握手有时要 6-8 秒(代理/TLS), 8 秒超时会直接判死, 所以 15 秒超时;
        # 另: chunked 传输偶发 IncompleteRead / 连接被断, 多重试几次
        for _attempt in range(4):
            try:
                return self._http_json(url)
            except Exception:
                if _attempt == 3:
                    return None
                time.sleep(0.5)
                continue
        return None

    def _get_classes(self):
        # 1 小时内复用, 避免每次进首页都多请求一次 ac=list
        now = time.time()
        if self._classes and now < self._classes_exp:
            return self._classes
        try:
            cached = self.getCache("sanliuling_classes")
            if cached:
                j = json.loads(cached)
                if isinstance(j, list) and j:
                    self._classes = j
                    self._classes_exp = now + 3600
                    return j
        except Exception:
            pass
        j = self._api({"ac": "list", "pg": 1})
        classes = []
        if j:
            for c in j.get("class") or []:
                try:
                    tid = str(c.get("type_id"))
                    # 只留有数据的分类, 实测总量为 0 的 7 个不展示
                    if tid not in EMPTY_TYPE_IDS:
                        classes.append({
                            "type_id": tid,
                            "type_name": str(c.get("type_name") or ""),
                        })
                except Exception:
                    pass
        if classes:
            self._classes = classes
            self._classes_exp = now + 3600
            try:
                self.setCache("sanliuling_classes", json.dumps(classes, ensure_ascii=False))
            except Exception:
                pass
            return classes
        return list(STATIC_CLASSES)

    # ---------- 列表项 ----------
    def _vod(self, it):
        if not isinstance(it, dict):
            return None
        vid = str(it.get("vod_id") or "")
        if not vid:
            return None
        name = _clean(it.get("vod_name")) or ("视频 " + vid)
        pic = _clean(it.get("vod_pic") or it.get("vod_pic_original"))
        remarks = _clean(it.get("vod_remarks"))
        if not remarks:
            remarks = _clean(it.get("type_name") or "")
        if it.get("vod_area"):
            remarks = (remarks + " · " + _clean(it.get("vod_area"))) if remarks else _clean(it.get("vod_area"))
        v = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "style": {"type": "rect", "ratio": 1.33},
        }
        year = it.get("vod_year") or it.get("vod_pubdate")
        if year:
            v["vod_year"] = str(year)[:10]
        return v

    def _fill_pics(self, lst):
        # 列表接口不返回 vod_pic, 用一次批量详情给当页补海报图; 失败也不影响列表本身
        if not lst:
            return
        try:
            ids = ",".join(x["vod_id"] for x in lst if x.get("vod_id"))
            if not ids:
                return
            j = self._api({"ac": "detail", "ids": ids})
            if not j:
                return
            pics = {}
            for it in j.get("list") or []:
                pic = _clean(it.get("vod_pic") or it.get("vod_pic_original"))
                if it.get("vod_id") and pic:
                    pics[str(it.get("vod_id"))] = pic
            for x in lst:
                if not x.get("vod_pic") and pics.get(x["vod_id"]):
                    x["vod_pic"] = pics[x["vod_id"]]
        except Exception:
            pass

    def _list_result(self, pg, limit, j):
        if not j:
            return {"page": pg, "pagecount": 1, "limit": limit, "total": 0, "list": []}
        lst = [self._vod(it) for it in (j.get("list") or [])]
        lst = [x for x in lst if x]
        self._fill_pics(lst)
        total = int(j.get("total") or 0)
        pagecount = int(j.get("pagecount") or 0)
        if not pagecount and total:
            pagecount = (total + limit - 1) // limit
        return {
            "page": pg,
            "pagecount": max(1, pagecount),
            "limit": limit,
            "total": total,
            "list": lst,
        }

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter):
        classes = self._get_classes()
        # 首位放最新, 后面按接口顺序放有数据的分类, 共 44 个
        out = [{"type_id": "0", "type_name": "最新更新"}]
        seen = {"0"}
        for c in classes:
            if c["type_id"] not in seen:
                seen.add(c["type_id"])
                out.append(c)
        return {"class": out, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("0", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = max(1, int(pg or 1))
        except Exception:
            pg = 1
        tid = str(tid or "0")
        params = {"ac": "list", "pg": pg}
        if tid not in ("0", "last", ""):
            params["t"] = tid
        j = self._api(params)
        return self._list_result(pg, 20, j)

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        j = self._api({"ac": "detail", "ids": vid})
        if not j or not j.get("list"):
            return {"list": []}
        it = j["list"][0]
        v = self._vod(it)
        if not v:
            return {"list": []}
        v["vod_actor"] = _clean(it.get("vod_actor"))
        v["vod_director"] = _clean(it.get("vod_director"))
        v["vod_area"] = _clean(it.get("vod_area"))
        v["vod_lang"] = _clean(it.get("vod_lang"))
        v["vod_class"] = _clean(it.get("vod_class") or it.get("vod_tag"))
        content = _clean(it.get("vod_content") or it.get("vod_blurb"))
        if content and content != "暂无简介，敬请期待":
            v["vod_content"] = content
        if it.get("vod_year"):
            v["vod_year"] = str(it.get("vod_year"))

        play_from = str(it.get("vod_play_from") or "")
        play_url = str(it.get("vod_play_url") or "")
        if play_from and play_url:
            from_list = play_from.split("$$$")
            url_list = play_url.split("$$$")
            play_from_out = []
            play_url_out = []
            for idx, src in enumerate(from_list):
                if idx >= len(url_list):
                    break
                episodes = []
                for ep in url_list[idx].split("#"):
                    ep = ep.strip()
                    if not ep or "$" not in ep:
                        continue
                    ep_name, _, ep_url = ep.partition("$")
                    ep_url = ep_url.strip()
                    if not ep_url:
                        continue
                    # 播放地址整体 quote, 避免 ? & # 等字符在 TVBox 切分时断掉
                    episodes.append("%s$%s" % (_clean_ep_name(ep_name), quote(ep_url, safe="")))
                if episodes:
                    play_from_out.append(SOURCE_NAMES.get(src.strip(), src.strip() or ("线路%d" % (idx + 1))))
                    play_url_out.append("#".join(episodes))
            if play_from_out:
                v["vod_play_from"] = "$$$".join(play_from_out)
                v["vod_play_url"] = "$$$".join(play_url_out)
        return {"list": [v]}

    def searchContent(self, key, quick, page="1"):
        try:
            pg = max(1, int(page or 1))
        except Exception:
            pg = 1
        j = self._api({"ac": "list", "pg": pg, "wd": key})
        return self._list_result(pg, 20, j)

    def playerContent(self, flag, id, vipFlags):
        raw = unquote(str(id or "").strip())
        if not raw:
            return {"parse": 1, "playUrl": "", "url": "", "header": {"User-Agent": self.ua}}
        # TVBox 传进来的是整条 "集名$播放地址", 不剥掉集名,
        # url 就会变成 "全集$https://..." 导致播不了; 只有 $ 后是 http(s) 地址时才剥
        if "$" in raw:
            _name, _, _after = raw.partition("$")
            if _after.strip().lower().startswith(("http://", "https://")):
                raw = _after.strip()
        low = raw.lower()
        if any(k in low for k in (".m3u8", ".mp4", ".flv", ".mkv")):
            return {
                "parse": 0,
                "playUrl": "",
                "url": raw,
                "header": {"User-Agent": self.ua, "Referer": "https://360zyzz.com/"},
            }
        # 非直链播放页, 交给 TVBox 解析
        return {
            "parse": 1,
            "playUrl": "",
            "url": raw,
            "header": {"User-Agent": self.ua},
        }

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(k in u for k in (".m3u8", ".mp4", ".flv", ".mkv", "_play", "stream"))

    def destroy(self):
        pass
