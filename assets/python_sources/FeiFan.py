# -*- coding: utf-8 -*-
# 非凡资源 - TVBox / CatVod Py 源
# 来源: 站长资源站Pro https://www.zzzypro.com/sites/655.html
# 接口: http://api.ffzyapi.com/api.php/provide/vod/?ac=list / ?ac=detail
#   (https 同域名亦通, 本文件 http 失败时自动切 https 备用)
# 格式: 苹果CMS(MacCMS)标准采集接口, JSON, code=1 为成功
#   列表:  ?ac=list&pg=1&t=<type_id>&wd=<关键词>
#   详情:  ?ac=detail&ids=<vod_id>, 支持逗号批量 ids, 一次返回多条
#   播放:  vod_play_from 用 $$$ 分线路(feifan / ffm3u8),
#          vod_play_url 用 $$$ 分线路, 线路内用 # 分集, 每集 "集名$播放地址"
#   feifan 线路是 /share/ 播放器页, 走 parse=1; ffm3u8 线路是直链 .m3u8, 走 parse=0
#   注意: 列表接口不返回 vod_pic, 本文件用一次批量详情(ac=detail&ids=...)给当页补海报图
# 实测 2026-11-18: 总量 99,166 条(各分类求和与列表 total 一致), 20 条/页,
#   接口返回 31 个分类, 其中 1/2/3(电影片/连续剧/综艺片)为父级空分类, 总量均为 0, 已过滤,
#   剩余 28 个有数据分类(另: 动漫片仅 44 条, 港台动漫 42 条, 海外动漫 100 条, 均保留);
#   列表/分类/搜索/详情均通, 搜索正常按 wd 过滤(千岁→7 条全含千岁, 复仇→78 条, 无意义词→0 条,
#   含百分号编码中文关键词亦通), 批量详情 20 条全回, 详情 vod_pic 为 fffgood.com 直链;
#   播放地址 HEAD/GET 从本机出口 IP 返回 403(ffm3u8 直链 m3u8 与 feifan 分享页均 403,
#   换 Referer/UA 及 curl 同样 403), 属于地域限制, 在国内设备上以 TVBox 实测为准。
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

API_BASE = "http://api.ffzyapi.com/api.php/provide/vod/"
API_BASE_ALT = "https://api.ffzyapi.com/api.php/provide/vod/"
UA_DEFAULT = "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 2026-11-18 实测: 以下父级分类总量为 0, 不展示
EMPTY_TYPE_IDS = {"1", "2", "3"}

# 接口挂了时分类也不至于全空, 按 2026-11-18 实测的有数据分类兜底
STATIC_CLASSES = [
    {"type_id": "0", "type_name": "最新更新"},
    {"type_id": "4", "type_name": "动漫片"},
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
    {"type_id": "20", "type_name": "记录片"},
    {"type_id": "21", "type_name": "台湾剧"},
    {"type_id": "22", "type_name": "日本剧"},
    {"type_id": "23", "type_name": "海外剧"},
    {"type_id": "24", "type_name": "泰国剧"},
    {"type_id": "25", "type_name": "大陆综艺"},
    {"type_id": "26", "type_name": "港台综艺"},
    {"type_id": "27", "type_name": "日韩综艺"},
    {"type_id": "28", "type_name": "欧美综艺"},
    {"type_id": "29", "type_name": "国产动漫"},
    {"type_id": "30", "type_name": "日韩动漫"},
    {"type_id": "31", "type_name": "欧美动漫"},
    {"type_id": "32", "type_name": "港台动漫"},
    {"type_id": "33", "type_name": "海外动漫"},
    {"type_id": "34", "type_name": "伦理片"},
    {"type_id": "36", "type_name": "短剧"},
]

SOURCE_NAMES = {
    "feifan": "非凡播放器",
    "ffm3u8": "非凡m3u8",
}


def _clean(s):
    s = str(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').strip()


def _clean_ep_name(name):
    # 集名不能含 $ # , 否则 TVBox 切集会错位; "4K"/"HD中字"这类画质名要保留, 不能都改成"正片"
    t = _clean(name) or "正片"
    t = t.replace("$", "").replace("#", "").replace("$$$", "")
    if t.upper() == "HD":
        t = "正片"
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
        # 部分接口的 TLS 前端会挂起无 ALPN 的握手, 显式声明 http/1.1
        try:
            self.ctx.set_alpn_protocols(["http/1.1"])
        except Exception:
            pass
        self._classes = None
        self._classes_exp = 0

    def getName(self):
        return "非凡资源"

    def init(self, extend=""):
        pass

    # ---------- 底层请求 ----------
    def _headers(self):
        return {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "http://api.ffzyapi.com/",
        }

    def _http_json(self, url):
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
            try:
                content = resp.read()
            except Exception as e:
                # chunked 传输偶发 IncompleteRead, e.partial 里往往已是完整正文, 直接用它
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

    def _api_base(self, base, params):
        url = base + "?" + urllib.parse.urlencode(params)
        # 首个冷连接握手有时要 6-8 秒(代理/TLS), 8 秒超时会直接判死, 所以 15 秒超时 + 失败重试
        for _attempt in range(2):
            try:
                return self._http_json(url)
            except Exception:
                if _attempt == 1:
                    return None
                time.sleep(0.5)
                continue
        return None

    def _api(self, params):
        j = self._api_base(self.api, params)
        if j is not None:
            return j
        # 主接口失败时切备用协议再试一次, 通了就固定下来
        alt = API_BASE_ALT if self.api == API_BASE else API_BASE
        j = self._api_base(alt, params)
        if j is not None:
            self.api = alt
        return j

    def _get_classes(self):
        # 1 小时内复用, 避免每次进首页都多请求一次 ac=list
        now = time.time()
        if self._classes and now < self._classes_exp:
            return self._classes
        try:
            cached = self.getCache("feifan_classes")
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
                    # 只留有数据的分类, 实测总量为 0 的父级 1/2/3 不展示
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
                self.setCache("feifan_classes", json.dumps(classes, ensure_ascii=False))
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
        # 首位放最新, 后面按接口顺序放有数据的分类, 共 28 个
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
                "header": {"User-Agent": self.ua, "Referer": "http://api.ffzyapi.com/"},
            }
        # feifan 等分享页, 交给 TVBox 解析
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
