import json
import base64
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

def format_remarks(brand="蝴蝶影视", meta=""):
    clean_meta = str(meta or "").strip()
    clean_meta = re.sub(r"[\r\n\t]+", " ", clean_meta).strip()
    if clean_meta:
        return "%s | %s" % (brand, clean_meta)
    return brand

def clean_label(text):
    t = str(text or "").strip()
    t = t.replace("$", "").replace("#", "")
    t = re.sub(r"\s+", " ", t)
    return t[:24]

API_DEFAULT = "https://14p.14pijq.com:51000"
SITE_DEFAULT = "https://14p.14pijq.com:51000"
CHANNEL_DEFAULT = "tz"
UA_DEFAULT = "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

PIC_KEY_STR = "H0Z%7n#k$H8*M7xSE^N@8xXZPG*RZ&wY"
DECRYPT_API_DEFAULT = "https://2.h8.ccwu.cc/?url="
PIC_BUCKET = "encryption-ts"

GATEWAYS = [
    # 2026-11-17实测: 14p/t6y 能通(302跳转), i68/7l8 连接失败(000), 所以活的放前面, 死的放最后兜底
    "https://14p.14pijq.com:51000",
    "https://t6y.t6ypaf.com:51000",
    "https://7l8.7l81uq.com:51000",
    "https://i68.i68q77.com:51888"
]

STATIC_CLASSES = [
    {"type_id": "last", "type_name": "最新更新"},
    {"type_id": "hot", "type_name": "热门"},
    {"type_id": "good", "type_name": "精选"},
    {"type_id": "c360", "type_name": "探花"},
    {"type_id": "c358", "type_name": "麻豆"},
    {"type_id": "c357", "type_name": "新闻"},
    {"type_id": "c356", "type_name": "擦边短剧"},
    {"type_id": "c346", "type_name": "VR"},
    {"type_id": "c345", "type_name": "女主播"},
    {"type_id": "c344", "type_name": "AV中字"},
    {"type_id": "c343", "type_name": "AV无码"},
    {"type_id": "c342", "type_name": "AI换脸"},
    {"type_id": "c341", "type_name": "三级"},
    {"type_id": "c267", "type_name": "动漫"},
    {"type_id": "c264", "type_name": "欧美"},
    {"type_id": "c266", "type_name": "传媒"},
    {"type_id": "c263", "type_name": "日本AV"},
    {"type_id": "c347", "type_name": "黑料"},
    {"type_id": "c262", "type_name": "国产"},
    {"type_id": "l131", "type_name": "AV有码"},
    {"type_id": "l133", "type_name": "自拍"},
    {"type_id": "l118", "type_name": "丝袜"},
    {"type_id": "l153", "type_name": "人妻"},
    {"type_id": "l158", "type_name": "学生"},
    {"type_id": "l377", "type_name": "偷拍"}
]

class Spider(BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.api = SITE_DEFAULT
        self.site = SITE_DEFAULT
        self.channel = CHANNEL_DEFAULT
        self.ua = UA_DEFAULT
        self.timeout = 10
        self.decrypt_api = DECRYPT_API_DEFAULT
        self.brandActor = "🦋 TG群: @tvshare23"
        self.brandDirector = "🦋 蝴蝶影视"
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.token = ""
        self.token_exp = 0
        self.user_gateway = GATEWAYS[0]
        self._cdns = [
            "https://jqsp.xn--xhq15jk0k96h.cn",
            "https://lmcsxdd.xn--xhq15jk0k96h.cn"
        ]

    def getName(self):
        return "蝴蝶·Uu影视"

    def init(self, extend=""):
        pass

    def _headers(self, token=False, json_body=False):
        h = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "channel": self.channel,
            "Origin": self.site,
            "Referer": self.site + "/",
        }
        if json_body:
            h["Content-Type"] = "application/json"
        if token and self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    # ---- 302 跳转处理: 网关现在一律 302 到一个新域名(只有域名、没有路径) ----
    # urllib 默认会跟随 302 到 Location 的根路径 "/", 路径 /api/... 就丢了, 拿到的永远是首页 HTML, 列表必然为空。
    # 正确做法: 把 Location 当作新 base, 用原路径在新域名上重发一次请求, 并把新域名记下来以后直接用。
    def _fetch(self, url, data=None, headers=None, timeout=None, update_base=True):
        timeout = timeout or self.timeout
        _parsed = urllib.parse.urlparse(url)
        _orig_path = _parsed.path
        if _parsed.query:
            _orig_path += "?" + _parsed.query
        _cur_url = url
        _cur_data = data
        for _hop in range(3):
            class _NoFollow(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                    return None
            _opener = urllib.request.build_opener(
                urllib.request.ProxyHandler(),
                _NoFollow(),
                urllib.request.HTTPSHandler(context=self.ctx),
                urllib.request.HTTPHandler(),
            )
            _req = urllib.request.Request(_cur_url, data=_cur_data, headers=headers or {})
            try:
                with _opener.open(_req, timeout=timeout) as resp:
                    return resp.read(), dict(resp.headers), _cur_url
            except urllib.error.HTTPError as e:
                _loc = None
                try:
                    _loc = (e.headers or {}).get("Location")
                except Exception:
                    pass
                if e.code in (301, 302, 303, 307, 308) and _loc:
                    _loc_p = urllib.parse.urlparse(_loc)
                    if not _loc_p.path or _loc_p.path == "/":
                        _new_base = "%s://%s" % (_loc_p.scheme or "https", _loc_p.netloc)
                        _cur_url = _new_base + _orig_path
                        if update_base:
                            self.api = _new_base
                            self.site = _new_base
                            self.user_gateway = _new_base
                            if _new_base not in GATEWAYS:
                                GATEWAYS.insert(0, _new_base)
                        if e.code == 303:
                            _cur_data = None
                        continue
                    _cur_url = _loc
                    continue
                raise
        raise ValueError("too many redirects: %s" % url)

    def _http(self, url, data=None, token=False, referer=None):
        _headers = self._headers(token=token, json_body=data is not None)
        if referer:
            _headers["Referer"] = referer
        content, _hdrs, _final_url = self._fetch(url, data=data, headers=_headers)
        _stripped = content.lstrip()[:20].lower()
        if _stripped.startswith(b"<!doctype") or _stripped.startswith(b"<html"):
            raise ValueError("non-json html response")
        enc = (_hdrs.get("Content-Encoding") or "").lower()
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
        return json.loads(content.decode("utf-8", "replace"))

    @staticmethod
    def _unxor(text, key):
        s = str(text or "").strip().replace("-", "+").replace("_", "/")
        s += "=" * ((4 - len(s) % 4) % 4)
        try:
            buf = base64.b64decode(s)
        except Exception:
            return None
        kb = key.encode("utf-8")
        return bytes(b ^ kb[i % len(kb)] for i, b in enumerate(buf)).decode("utf-8", "replace")

    def _api(self, path, params=None, token=False):
        q = path
        if params:
            q += "?" + urllib.parse.urlencode(params)
        # 优先用登录成功的网关, 再按 GATEWAYS 顺序轮询, 最后才试旧默认值
        # 原代码只试 self.api(API已死) + API_DEFAULT(已死), 登录/play 能走的网关这里根本没用, 列表/详情/搜索全空
        bases = []
        for b in [getattr(self, "user_gateway", ""), self.api, API_DEFAULT] + GATEWAYS:
            if b and b not in bases:
                bases.append(b)
        last_err = None
        for base in bases:
            _api_before = self.api
            try:
                j = self._http(base + q, token=token)
            except Exception as e:
                last_err = e
                continue
            if not isinstance(j, dict) or j.get("code") != 200:
                continue
            data = j.get("data")
            if isinstance(data, str) and j.get("key"):
                txt = self._unxor(data, j["key"])
                if not txt:
                    continue
                try:
                    data = json.loads(txt)
                except Exception:
                    # 解密后不是JSON: 别返回字符串(调用方 .get() 会崩), 换下一个网关试
                    continue
            if not isinstance(data, (dict, list)):
                continue
            # 这个网关通了, 记住它, 下次直接用
            # 注意: _fetch 可能已因 302 跳转把 self.api 改成了新域名(_api_before != self.api), 别覆盖回旧网关
            if self.api == _api_before:
                self.api = base
                self.site = base
                self.user_gateway = base
            return data
        return None

    def _fingerprint(self):
        h = 2166136261
        for ch in (self.ua + self.channel):
            h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
        return "fp-%08x" % h

    def _login(self):
        body = json.dumps({"channel": self.channel, "fingerPrint": self._fingerprint()}).encode("utf-8")
        headers = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "identity",
            "Content-Type": "application/json",
            "channel": self.channel,
            "Origin": self.site,
            "Referer": self.site + "/"
        }
        for gw in list(GATEWAYS):
            _gw_before = self.user_gateway
            try:
                content, _hdrs, _final_url = self._fetch(gw + "/api-user/v2/login/fingerprint", data=body, headers=headers, timeout=10)
                j = json.loads(content.decode("utf-8", "replace"))
                if isinstance(j, dict) and j.get("code") == 200:
                    data = j.get("data")
                    if isinstance(data, str) and j.get("key"):
                        txt = self._unxor(data, j["key"])
                        if txt:
                            try:
                                data = json.loads(txt)
                            except Exception:
                                continue
                    tok = (data or {}).get("accessToken") if isinstance(data, dict) else None
                    if tok:
                        self.token = tok
                        self.token_exp = time.time() + 1400
                        # _fetch 跳转时已更新 user_gateway; 没跳转时用当前网关, 别留在旧网关上
                        if self.user_gateway == _gw_before:
                            self.user_gateway = gw
                        self.api = self.user_gateway
                        self.site = self.user_gateway
                        return tok
            except Exception:
                pass
        return ""

    def _ensure_token(self):
        if self.token and time.time() < self.token_exp:
            return self.token
        return self._login()

    def _get_play_data(self, vid):
        self._ensure_token()
        if not self.token:
            return {}

        path = "/api/v2/home/user/video/play/url?" + urllib.parse.urlencode({"id": vid, "channel": self.channel})
        headers = {
            "User-Agent": self.ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "identity",
            "channel": self.channel,
            "Origin": self.site,
            "Referer": self.site + "/",
            "Authorization": "Bearer " + self.token
        }

        candidates = [self.user_gateway] + [gw for gw in GATEWAYS if gw != self.user_gateway]
        for gw in candidates:
            try:
                content, _hdrs, _final_url = self._fetch(gw + path, headers=headers, timeout=10)
                j = json.loads(content.decode("utf-8", "replace"))
                if isinstance(j, dict) and j.get("code") == 200:
                    data = j.get("data")
                    if isinstance(data, str) and j.get("key"):
                        txt = self._unxor(data, j["key"])
                        if txt:
                            try:
                                data = json.loads(txt)
                            except Exception:
                                continue
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def _build_inline_m3u8(self, m3u8_url):
        try:
            raw_m3u8, _hdrs, _final_m3u8_url = self._fetch(m3u8_url, headers={
                "User-Agent": self.ua,
                "Referer": self.site + "/"
            }, timeout=3, update_base=False)
            raw_m3u8 = raw_m3u8.decode("utf-8", "replace")
            # CDN 跳转后, 分片/key 要按跳转后的最终地址解析, 不能按原地址, 否则会指到旧 host 上 404
            m3u8_url = _final_m3u8_url
            if not raw_m3u8.lstrip().startswith("#EXTM3U"):
                return ""

            # 先把所有相对地址改成绝对地址, 否则 data: 协议的 m3u8 没有 base, 播放器解析不到分片
            def _abs_uri(m):
                uri = m.group(2)
                if uri.startswith(("http", "data:")):
                    return m.group(0)
                return '%s"%s"' % (m.group(1), urllib.parse.urljoin(m3u8_url, uri))
            raw_m3u8 = re.sub(r'(URI=)["\']([^"\']+)["\']', _abs_uri, raw_m3u8)
            # 上面只处理了 URI=, 下面处理分片/子列表等纯相对路径行
            lines = []
            for line in raw_m3u8.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith(("http", "data:")):
                    line = urllib.parse.urljoin(m3u8_url, line)
                lines.append(line)
            raw_m3u8 = "\n".join(lines) + "\n"

            key_match = re.search(r'#EXT-X-KEY:METHOD=AES-128,URI=["\']([^"\']+)["\'](.*)', raw_m3u8)
            if key_match:
                key_uri = key_match.group(1)
                extra_attr = key_match.group(2)
                # key_uri 现在已经是绝对地址了, 直接取, 不要再用 self.site 拼
                key_full_url = key_uri
                try:
                    key_bytes, _khdrs, _kfinal = self._fetch(key_full_url, headers={
                        "User-Agent": self.ua,
                        "Referer": self.site + "/"
                    }, timeout=2, update_base=False)
                    if len(key_bytes) >= 16:
                        key_b64 = base64.b64encode(key_bytes[:16]).decode("ascii")
                        inline_key_uri = "data:application/octet-stream;base64,%s" % key_b64
                        new_key_line = '#EXT-X-KEY:METHOD=AES-128,URI="%s"%s' % (inline_key_uri, extra_attr)
                        raw_m3u8 = re.sub(r'#EXT-X-KEY:METHOD=AES-128,URI=["\'][^"\']+["\'].*', new_key_line, raw_m3u8, count=1)
                except Exception:
                    pass

            m3u8_b64 = base64.b64encode(raw_m3u8.encode("utf-8")).decode("ascii")
            return "data:application/vnd.apple.mpegurl;base64,%s" % m3u8_b64
        except Exception:
            return ""

    def _pic(self, thumb):
        t = str(thumb or "").strip()
        if not t:
            return ""
        if t.startswith("//"):
            enc = "https:" + t
        elif t.startswith("http"):
            enc = t
        else:
            if not t.startswith("/"):
                t = "/" + t
            enc = "%s/%s%s" % (self._cdns[0], PIC_BUCKET, t)
        if self.decrypt_api:
            return "%s%s&key=%s" % (self.decrypt_api, urllib.parse.quote(enc, safe=""), urllib.parse.quote(PIC_KEY_STR, safe=""))
        return enc

    def _clean(self, s):
        s = str(s or "")
        return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').strip()

    def _vod(self, it):
        vid = str(it.get("id") or "")
        name = self._clean(it.get("title")) or ("视频 " + vid)
        tags = self._clean(it.get("labelTitles") or it.get("classifyTitles"))
        meta_info = tags.replace(",", " · ")[:20] if tags else self._clean(it.get("createdAt"))[:10]
        pic_url = self._pic(it.get("thumb"))
        return {
            "vod_id": vid,
            "vod_name": name,
            "vod_pic": pic_url,
            "vod_bg": pic_url,
            "vod_background": pic_url,
            "vod_banner": pic_url,
            "vod_remarks": format_remarks("蝴蝶影视", meta_info),
            "style": {"type": "rect", "ratio": 1.78}
        }

    def homeContent(self, filter):
        return {
            "class": STATIC_CLASSES,
            "filters": {}
        }

    def homeVideoContent(self):
        return self.categoryContent("last", 1, False, {})

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = max(1, int(pg or 1))
        except Exception:
            pg = 1
        tid = str(tid or "last")
        params = {"page": pg, "limit": 20, "videoType": "long"}
        if tid in ("last", "hot", "good", "collect"):
            params["type"] = tid
        elif tid.startswith("c") and tid[1:].isdigit():
            params["type"] = "cate"
            params["typeId"] = tid[1:]
        elif tid.startswith("l") and tid[1:].isdigit():
            params["type"] = "label"
            params["typeId"] = tid[1:]
        else:
            params["type"] = "last"

        try:
            d = self._api("/api/v2/home/public/video/list", params) or {}
            lst = d.get("list") or []
            if not lst and params.get("type") == "cate":
                alt = dict(params)
                alt["type"] = "label"
                try:
                    d_alt = self._api("/api/v2/home/public/video/list", alt) or {}
                    if d_alt.get("list"):
                        d = d_alt
                        lst = d_alt.get("list")
                except Exception:
                    pass

            total = int(d.get("total") or 0)
            limit = int(params.get("limit") or 20)
            return {
                "page": pg,
                "pagecount": max(1, (total + limit - 1) // limit) if total else 1,
                "limit": limit,
                "total": total,
                "list": [self._vod(it) for it in lst],
            }
        except Exception:
            return {"page": pg, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    def detailContent(self, ids):
        vid = str(ids[0] if isinstance(ids, (list, tuple)) else ids).strip()
        try:
            raw_detail = self._api("/api/v2/home/public/video/long/detail", {"id": vid}) or {}
            v = self._vod(raw_detail)

            title = v["vod_name"]
            desc = self._clean(raw_detail.get("content") or title)
            raw_actor = self._clean(raw_detail.get("actor") or "")

            if raw_actor:
                v["vod_actor"] = "%s | %s" % (raw_actor, self.brandActor)
            else:
                v["vod_actor"] = self.brandActor
            v["vod_director"] = self.brandDirector

            if desc:
                v["vod_content"] = "🦋 蝴蝶影视专线直连 | %s | 官方交流群: @tvshare23" % desc
            else:
                v["vod_content"] = "🦋 蝴蝶影视专线加速播放 | 官方TG交流群：@tvshare23 | 4K高清原生极速画质"

            episodes = ["正片$%s@@720p@@@%s" % (vid, quote(title))]
            seen_ids = set([str(vid)])

            next_obj = raw_detail.get("next")
            if isinstance(next_obj, dict) and next_obj.get("id"):
                n_id = str(next_obj.get("id"))
                n_title = self._clean(next_obj.get("title") or "下一部")
                if n_id not in seen_ids:
                    seen_ids.add(n_id)
                    episodes.append("下一部·%s$%s@@720p@@@%s" % (clean_label(n_title), n_id, quote(n_title)))

            prev_obj = raw_detail.get("prev")
            if isinstance(prev_obj, dict) and prev_obj.get("id"):
                p_id = str(prev_obj.get("id"))
                p_title = self._clean(prev_obj.get("title") or "上一部")
                if p_id not in seen_ids:
                    seen_ids.add(p_id)
                    episodes.append("上一部·%s$%s@@720p@@@%s" % (clean_label(p_title), p_id, quote(p_title)))

            classify_raw = str(raw_detail.get("classify") or "").strip()
            if classify_raw:
                c_ids = re.findall(r"\d+", classify_raw)
                if c_ids:
                    first_cid = c_ids[0]
                    rel_data = self._api("/api/v2/home/public/video/list", {"page": 1, "limit": 12, "videoType": "long", "type": "cate", "typeId": first_cid}) or {}
                    rel_items = rel_data.get("list") or []
                    rel_idx = 1
                    for r_it in rel_items:
                        r_id = str(r_it.get("id") or "")
                        if not r_id or r_id in seen_ids:
                            continue
                        seen_ids.add(r_id)
                        r_title = self._clean(r_it.get("title") or "")
                        clean_t = clean_label(r_title)
                        episodes.append("%02d·%s$%s@@720p@@@%s" % (rel_idx, clean_t, r_id, quote(r_title)))
                        rel_idx += 1
                        if rel_idx > 10:
                            break

            v["vod_remarks"] = format_remarks("蝴蝶影视", "全%s部连播" % len(episodes))
            v["vod_play_from"] = "蝴蝶专线"
            v["vod_play_url"] = "#".join(episodes)
            return {"list": [v]}
        except Exception:
            return {"list": []}

    def searchContent(self, key, quick, page="1"):
        try:
            pg = max(1, int(page or 1))
        except Exception:
            pg = 1
        try:
            d = self._api("/api/v2/home/public/video/search", {"page": pg, "limit": 20, "keyword": key, "videoType": "long"}) or {}
            lst = d.get("list") or []
            total = int(d.get("total") or len(lst))
            return {"page": pg, "pagecount": max(1, (total + 19) // 20), "limit": 20, "total": total, "list": [self._vod(it) for it in lst]}
        except Exception:
            return {"page": pg, "pagecount": 1, "limit": 20, "total": 0, "list": []}

    def playerContent(self, flag, id, vipFlags):
        raw = str(id or "").strip()
        desc_title = ""
        if "@@@" in raw:
            target, raw_title = raw.split("@@@", 1)
            desc_title = unquote(raw_title)
        else:
            target = raw

        vid, _, variant = target.partition("@@")
        variant = variant or "720p"

        try:
            d = self._get_play_data(vid)
            key = {"720p": "p720Url", "480p": "p480Url"}.get(variant, "masterUrl")
            raw_url = str(d.get(key) or d.get("p720Url") or d.get("masterUrl") or "")
            if raw_url:
                if raw_url.startswith("/"):
                    real_m3u8_url = self.site + raw_url
                else:
                    real_m3u8_url = raw_url

                if "cdnId=2" in real_m3u8_url:
                    real_m3u8_url = real_m3u8_url.replace("cdnId=2", "cdnId=1", 1)

                data_uri_stream = self._build_inline_m3u8(real_m3u8_url)
                if data_uri_stream:
                    _m3u8_host = urllib.parse.urlparse(real_m3u8_url).scheme + "://" + urllib.parse.urlparse(real_m3u8_url).netloc + "/"
                    res = {
                        "parse": 0,
                        "playUrl": "",
                        "url": data_uri_stream,
                        "header": {"User-Agent": self.ua, "Referer": _m3u8_host}
                    }
                    if desc_title:
                        res["desc"] = desc_title
                    return res

                # inline 失败(超时/403/不是 m3u8)就直接走直链, 让播放器自己用用户网络取 m3u8/key/分片,
                # 别再让爬虫侧的网络问题拖垮播放, 也别直接掉到 embed
                _m3u8_host = urllib.parse.urlparse(real_m3u8_url).scheme + "://" + urllib.parse.urlparse(real_m3u8_url).netloc + "/"
                res = {
                    "parse": 0,
                    "playUrl": "",
                    "url": real_m3u8_url,
                    "header": {"User-Agent": self.ua, "Referer": _m3u8_host}
                }
                if desc_title:
                    res["desc"] = desc_title
                return res
        except Exception:
            pass

        embed_url = "%s/video/player/embed?id=%s" % (self.site, vid)
        res = {
            "parse": 1,
            "playUrl": "",
            "url": embed_url,
            "header": {"User-Agent": self.ua, "Referer": self.site + "/"}
        }
        if desc_title:
            res["desc"] = desc_title
        return res

    def isVideoFormat(self, url):
        u = str(url or "").lower()
        return any(k in u for k in (".m3u8", ".mp4", "_play", "stream", "data:application/vnd.apple.mpegurl"))

    def destroy(self):
        pass