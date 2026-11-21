# -*- coding: utf-8 -*-
# 暴风资源 - TVBox / CatVod Py 源
# 来源: 站长资源站Pro https://www.zzzypro.com/sites/78.html
# 接口: https://bfzyapi.com/api.php/provide/vod/?ac=list / ?ac=detail
#   (zzzypro 页面另列了 /at/xml/ 的 XML 接口, 与默认接口同源同数据, 本文件只用默认接口)
# 格式: 苹果CMS(MacCMS)标准采集接口, JSON, code=1 为成功
#   列表:  ?ac=list&pg=1&t=<type_id>&wd=<关键词>
#   详情:  ?ac=detail&ids=<vod_id>, 支持逗号批量 ids, 一次返回多条
#   播放:  vod_play_from 单线路 bfzym3u8,
#          vod_play_url 用 # 分集, 每集 "集名$播放地址", 地址为直链 .m3u8
#          (v.baofeng9.com / v.fengbao14.com / s3.bfllvip.com 等);
#          集名常为日期如 "20251231$...", 电影为画质分集如 "HD$..."
#   注意: 列表接口自带 vod_pic, 本文件不需要批量详情补图
# 实测 2026-11-18: 总量 172,776 条(逐类求和 172,619, 差 157 条, 疑似未归类/新入库条目),
#   接口返回 49 个分类, 其中只有 53 体育赛事总量为 0, 已过滤, 剩余 48 个;
#   搜索实测有效: wd=狂飙 91 条且均含关键词, 无意义关键词 0 条。
#   列表/分类 p1+p2/详情/搜索均通; 详情 vod_pic 正常。
#   播放: 部分旧分集直链从本机出口 HEAD/GET 均 404(如 s3.bfllvip.com 的一集),
#   另一些分集 HEAD 200 且 GET 返回真实 #EXTM3U(v.fengbao14.com), 故不是统一地域拦截,
#   可能是个别旧链接失效, 在国内设备上以 TVBox 实测为准。
#   注意: 本接口偶发 TLS 握手慢, 本文件用 15 秒超时 + 最多重试 4 次, 并保留
#   MangGuo 的 IncompleteRead.partial 抢救逻辑。
#   另: 多家同类接口的 TLS 前置会挂起不带 ALPN 的握手, 本文件显式
#   set_alpn_protocols(["http/1.1"])。
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

API_BASE = "https://bfzyapi.com/api.php/provide/vod/"
UA_DEFAULT = "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 2026-11-18 实测: 以下分类总量为 0, 不展示
EMPTY_TYPE_IDS = {"53"}

# 接口挂了时分类也不至于全空, 按 2026-11-18 实测的有数据分类兜底
STATIC_CLASSES = [
    {"type_id": "0", "type_name": "最新更新"},
    {"type_id": "20", "type_name": "电影片"},
    {"type_id": "21", "type_name": "动作片"},
    {"type_id": "22", "type_name": "喜剧片"},
    {"type_id": "23", "type_name": "恐怖片"},
    {"type_id": "24", "type_name": "科幻片"},
    {"type_id": "25", "type_name": "爱情片"},
    {"type_id": "26", "type_name": "剧情片"},
    {"type_id": "27", "type_name": "战争片"},
    {"type_id": "28", "type_name": "纪录片"},
    {"type_id": "29", "type_name": "理论片"},
    {"type_id": "30", "type_name": "连续剧"},
    {"type_id": "31", "type_name": "国产剧"},
    {"type_id": "32", "type_name": "欧美剧"},
    {"type_id": "33", "type_name": "香港剧"},
    {"type_id": "34", "type_name": "韩国剧"},
    {"type_id": "35", "type_name": "台湾剧"},
    {"type_id": "36", "type_name": "日本剧"},
    {"type_id": "37", "type_name": "海外剧"},
    {"type_id": "38", "type_name": "泰国剧"},
    {"type_id": "39", "type_name": "动漫片"},
    {"type_id": "40", "type_name": "国产动漫"},
    {"type_id": "41", "type_name": "日韩动漫"},
    {"type_id": "42", "type_name": "欧美动漫"},
    {"type_id": "43", "type_name": "港台动漫"},
    {"type_id": "44", "type_name": "海外动漫"},
    {"type_id": "45", "type_name": "综艺片"},
    {"type_id": "46", "type_name": "大陆综艺"},
    {"type_id": "47", "type_name": "港台综艺"},
    {"type_id": "48", "type_name": "日韩综艺"},
    {"type_id": "49", "type_name": "欧美综艺"},
    {"type_id": "50", "type_name": "动画片"},
    {"type_id": "51", "type_name": "电影解说"},
    {"type_id": "52", "type_name": "预告片"},
    {"type_id": "54", "type_name": "足球"},
    {"type_id": "55", "type_name": "篮球"},
    {"type_id": "56", "type_name": "网球"},
    {"type_id": "57", "type_name": "斯诺克"},
    {"type_id": "58", "type_name": "短剧大全"},
    {"type_id": "59", "type_name": "重生民国"},
    {"type_id": "60", "type_name": "穿越年代"},
    {"type_id": "61", "type_name": "现代言情"},
    {"type_id": "62", "type_name": "反转爽文"},
    {"type_id": "63", "type_name": "女恋总裁"},
    {"type_id": "64", "type_name": "闪婚离婚"},
    {"type_id": "65", "type_name": "都市脑洞"},
    {"type_id": "66", "type_name": "古装仙侠"},
    {"type_id": "67", "type_name": "福利"},
    {"type_id": "68", "type_name": "AI漫剧"},
]

SOURCE_NAMES = {
    "bfzym3u8": "暴风m3u8",
}


def _clean(s):
    s = str(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').strip()


def _clean_ep_name(name):
    # 集名不能含 $ # , 否则 TVBox 切集会错位; "4K"/"HD中字"这类画质名要保留,
    # 不能都改成"正片"; 只有光秃秃的 "HD" 才映射为"正片"
    t = _clean(name) or "正片"
    t = t.replace("$", "").replace("#", "").replace("$$$", "")
    if t.upper() == "HD":
        return "正片"
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
        # 本接口的 TLS 前置会挂起不带 ALPN 的握手(实测 urllib 默认无 ALPN 时握手 15 秒超时,
        # curl 带 ALPN 则 1 秒通); 显式声明 http/1.1, 在 TVBox 上同样无害
        try:
            self.ctx.set_alpn_protocols(["http/1.1"])
        except Exception:
            pass
        self._classes = None
        self._classes_exp = 0

    def getName(self):
        return "暴风资源"

    def init(self, extend=""):
        pass

    # ---------- 底层请求 ----------
    def _headers(self):
        return {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://bfzyapi.com/",
        }

    def _http_json(self, url):
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
            try:
                content = resp.read()
            except Exception as e:
                # chunked 传输偶发 IncompleteRead, e.partial 里往往已是完整 gzip 正文, 直接用它
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
        # 首个冷连接握手有时要 6-8 秒, 8 秒超时会直接判死, 所以 15 秒超时 + 失败重试
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
            cached = self.getCache("baofeng_classes")
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
                    # 只留有数据的分类, 实测总量为 0 的 6 个不展示
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
                self.setCache("baofeng_classes", json.dumps(classes, ensure_ascii=False))
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

    def _list_result(self, pg, limit, j):
        if not j:
            return {"page": pg, "pagecount": 1, "limit": limit, "total": 0, "list": []}
        lst = [self._vod(it) for it in (j.get("list") or [])]
        lst = [x for x in lst if x]
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
        # 首位放最新, 后面按接口顺序放有数据的分类, 共 48 个
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
        # 注意: 该接口实测搜索有效, wd 关键词正常过滤(见文件头注释)
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
                "header": {"User-Agent": self.ua, "Referer": "https://bfzyapi.com/"},
            }
        # 非直链播放地址, 交给 TVBox 解析
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
