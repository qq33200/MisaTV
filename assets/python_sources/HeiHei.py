# -*- coding: utf-8 -*-
# 嘿嘿资源 - TVBox / CatVod Py 源
# 来源: 站长资源站Pro https://www.zzzypro.com/sites/758.html
# 接口: 苹果CMS(MacCMS)标准采集接口, JSON, code=1 为成功
#   主接口: https://api.heiapi.cc/api.php/provide/vod/
#   列表:  ?ac=list&pg=1&t=<type_id>&wd=<关键词>
#   详情:  ?ac=detail&ids=<vod_id>
#   播放:  单线路 heihei, 单集, 每集 "HD$直链.m3u8" (v.heicdn.com)
# 实测 2026-11-17: 总量 45,156 条, pagecount 2258, 每页 20 条,
#   接口返回 65 个分类, 其中 55/71/72/77/83/94 号总量为 0, 已在分类里过滤掉, 剩 59 个;
#   列表/详情/搜索均通, 播放地址为直链 .m3u8, 从本机出口 HEAD 测得 200, 未见地域拦截;
#   注意: 列表接口不返回 vod_pic, 用批量详情给当页补封面图;
#   该接口偶发 IncompleteRead(0 bytes), urllib 首次请求即可能失败, 已按 MangGuo.py 的做法
#   兜底 partial 并重试 4 次, curl 同环境 100% 成功。
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

API_BASES = [
    "https://api.heiapi.cc/api.php/provide/vod/",
    "http://api.heiapi.cc/api.php/provide/vod/",
]
UA_DEFAULT = "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

# 2026-11-17 实测: 65 个分类中这 6 个总量为 0
EMPTY_TYPE_IDS = {"55", "71", "72", "77", "83", "94"}

# 接口挂了时分类也不至于全空, 按 2026-11-17 实测的分类兜底(已去掉空分类)
STATIC_CLASSES = [
    {"type_id": "0", "type_name": "最新更新"},
    {"type_id": "48", "type_name": "国产视频"},
    {"type_id": "49", "type_name": "国产自拍"},
    {"type_id": "50", "type_name": "国产偷拍"},
    {"type_id": "51", "type_name": "国产探花"},
    {"type_id": "52", "type_name": "国产主播"},
    {"type_id": "53", "type_name": "国产户外"},
    {"type_id": "54", "type_name": "黑料吃瓜"},
    {"type_id": "56", "type_name": "麻豆传媒"},
    {"type_id": "57", "type_name": "精东影业"},
    {"type_id": "58", "type_name": "蜜桃传媒"},
    {"type_id": "59", "type_name": "果冻传媒"},
    {"type_id": "60", "type_name": "天美传媒"},
    {"type_id": "61", "type_name": "星空传媒"},
    {"type_id": "62", "type_name": "皇家华人"},
    {"type_id": "63", "type_name": "起点传媒"},
    {"type_id": "64", "type_name": "渡边传媒"},
    {"type_id": "65", "type_name": "葫芦影业"},
    {"type_id": "66", "type_name": "红斯灯影像"},
    {"type_id": "67", "type_name": "水果派解说"},
    {"type_id": "68", "type_name": "SA传媒"},
    {"type_id": "69", "type_name": "糖心Vlog"},
    {"type_id": "70", "type_name": "性视界"},
    {"type_id": "73", "type_name": "日本无码"},
    {"type_id": "74", "type_name": "日本有码"},
    {"type_id": "75", "type_name": "中字无码"},
    {"type_id": "76", "type_name": "中字有码"},
    {"type_id": "78", "type_name": "绿帽换妻"},
    {"type_id": "79", "type_name": "SM调教"},
    {"type_id": "80", "type_name": "男同系列"},
    {"type_id": "81", "type_name": "女同系列"},
    {"type_id": "82", "type_name": "乱伦系列"},
    {"type_id": "84", "type_name": "台北娜娜"},
    {"type_id": "85", "type_name": "玩偶姐姐"},
    {"type_id": "86", "type_name": "饼干姐姐"},
    {"type_id": "87", "type_name": "黑椒盖饭"},
    {"type_id": "88", "type_name": "冉冉学姐"},
    {"type_id": "89", "type_name": "小水水"},
    {"type_id": "90", "type_name": "柚子猫"},
    {"type_id": "91", "type_name": "捅主任"},
    {"type_id": "92", "type_name": "鸡教练"},
    {"type_id": "93", "type_name": "刘玥"},
    {"type_id": "95", "type_name": "国产伦理"},
    {"type_id": "96", "type_name": "香港伦理"},
    {"type_id": "97", "type_name": "台湾伦理"},
    {"type_id": "98", "type_name": "韩国伦理"},
    {"type_id": "99", "type_name": "日本伦理"},
    {"type_id": "100", "type_name": "西方伦理"},
    {"type_id": "101", "type_name": "欧美AV"},
    {"type_id": "102", "type_name": "美女写真"},
    {"type_id": "103", "type_name": "成人动漫"},
    {"type_id": "104", "type_name": "扣扣传媒"},
    {"type_id": "105", "type_name": "爱豆传媒"},
    {"type_id": "106", "type_name": "乌托邦传媒"},
    {"type_id": "107", "type_name": "爱神传媒"},
    {"type_id": "108", "type_name": "香蕉传媒"},
    {"type_id": "109", "type_name": "大象传媒"},
    {"type_id": "110", "type_name": "其他传媒"},
    {"type_id": "111", "type_name": "米菲兔"},
    {"type_id": "112", "type_name": "短视频"},
]

SOURCE_NAMES = {
    "heihei": "嘿嘿m3u8",
}


def _clean(s):
    s = str(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').strip()


def _clean_ep_name(name):
    t = _clean(name) or "正片"
    if t in ("HD", "SD", "播放", "正片"):
        return "正片"
    t = t.replace("$", "").replace("#", "").replace("$$$", "")
    return t[:40]


class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.api = API_BASES[0]
        self.ua = UA_DEFAULT
        self.timeout = 15
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self._classes = None
        self._classes_exp = 0

    def getName(self):
        return "嘿嘿资源"

    def init(self, extend=""):
        pass

    # ---------- 底层请求 ----------
    def _headers(self):
        return {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://api.heiapi.cc/",
        }

    def _http_json(self, url):
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
            try:
                content = resp.read()
            except Exception as e:
                # 该接口偶发 IncompleteRead, e.partial 里往往已是完整 gzip 正文, 直接用它
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
        qs = urllib.parse.urlencode(params)
        # 主接口挂了就换备用接口, 通了就记住它, 下次直接用;
        # 首个冷连接握手有时要 6-8 秒, 15 秒超时 + 每接口最多 4 次重试
        for base in [self.api] + [b for b in API_BASES if b != self.api]:
            for _attempt in range(4):
                try:
                    j = self._http_json(base + "?" + qs)
                except Exception:
                    if _attempt == 3:
                        break
                    time.sleep(0.5)
                    continue
                if j:
                    self.api = base
                    return j
                break
        return None

    def _get_classes(self):
        now = time.time()
        if self._classes and now < self._classes_exp:
            return self._classes
        try:
            cached = self.getCache("heihei_classes")
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
                self.setCache("heihei_classes", json.dumps(classes, ensure_ascii=False))
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
        v = {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic,
            "vod_remarks": remarks,
            "style": {"type": "rect", "ratio": 1.33},
        }
        year = it.get("vod_year")
        if year:
            try:
                if int(year) > 0:
                    v["vod_year"] = str(year)
            except Exception:
                pass
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
        if content:
            v["vod_content"] = content

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
                "header": {"User-Agent": self.ua, "Referer": "https://api.heiapi.cc/"},
            }
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
