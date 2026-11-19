# -*- coding: utf-8 -*-
"""WinBox Android py 蜘蛛入口（Chaquopy 侧）。

与桌面版 assets/python_runner/runner.py 的调用语义对齐，但改为函数调用而非
CLI：Kotlin 经 Chaquopy 调 winbox_spider.invoke(...)，返回 JSON 字符串。

调用约定（与 runner.py _call_method 一致）：
  invoke(script_path, class_name, method, ext_json, args_json) -> str
  - script_path：磁盘上的 .py 源文件绝对路径（Dart 侧先下载到缓存目录）
  - method：homeContent / categoryContent / detailContent / searchContent /
    playerContent / liveContent / proxy
  - ext_json：init(ext) 用的配置字符串（可为空）
  - args_json：方法实参的 JSON 数组（字符串形式，与 runner.py argv[4:] 对齐）
返回值：结果的 JSON 字符串；失败抛异常，Kotlin 侧转成错误。
注意：不要在这里 print 到 stdout——Chaquopy 下 print 走 logcat，不会污染结果。
"""
import base64
import importlib.util
import inspect
import json
import os
import sys


_PLATFORM_STATE = (
    ('douyu', 'dyufdata', 'process_douyu'),
    ('bili', 'blfdata', 'process_bili'),
    ('douyin', 'dyifdata', 'process_douyin'),
    ('kugou', 'kgdata', 'process_kugou'),
    ('ks', 'ksdata', 'process_ks'),
)


def _invoke_variants(sp, name, variants):
    fn = getattr(sp, name, None)
    if fn is None:
        raise AttributeError('method not found: %s' % name)
    signature = inspect.signature(fn)
    for args in variants:
        try:
            signature.bind(*args)
        except TypeError:
            continue
        return fn(*args)
    raise TypeError('unsupported signature for %s: %s' % (name, signature))


def _invoke(sp, name, *args):
    fn = getattr(sp, name, None)
    if fn is None:
        raise AttributeError('method not found: %s' % name)
    return fn(*args)


def _ensure_platform_state(sp, tid, extend):
    if not isinstance(extend, dict) or not extend.get('cate'):
        return
    text = str(tid or '').lower()
    if 'click' in text:
        return
    for key, attr, method in _PLATFORM_STATE:
        if key not in text:
            continue
        if hasattr(sp, attr):
            return
        fn = getattr(sp, method, None)
        if fn is None:
            return
        try:
            fn()
        except Exception:
            pass
        return


def _load_script(py_path):
    script_dir = os.path.dirname(os.path.abspath(py_path))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    ns = {'__file__': os.path.abspath(py_path), '__name__': 'winbox_spider_src'}
    with open(py_path, 'r', encoding='utf-8-sig') as f:
        src = f.read()
    exec(compile(src, py_path, 'exec'), ns)
    return ns


def _call_method(sp, method, rest):
    if method == 'homeContent':
        return _invoke_variants(sp, 'homeContent', [(True,), ()])
    if method == 'homeVideoContent':
        return _invoke(sp, 'homeVideoContent')
    if method == 'categoryContent':
        tid = rest[0] if len(rest) > 0 else ''
        pg = rest[1] if len(rest) > 1 else '1'
        extend = rest[2] if len(rest) > 2 else '{}'
        try:
            extend_obj = json.loads(extend) if extend else {}
        except (ValueError, TypeError):
            extend_obj = {}
        _ensure_platform_state(sp, tid, extend_obj)
        try:
            return _invoke(sp, 'categoryContent', tid, (pg or '1'), True, extend_obj)
        except AttributeError as error:
            if any(name in str(error) for name, _, _ in _PLATFORM_STATE):
                return {'page': pg or '1', 'pagecount': 1, 'limit': 0, 'total': 0, 'list': []}
            raise
    if method == 'detailContent':
        ids = rest[0] if len(rest) > 0 else '[]'
        try:
            ids_obj = json.loads(ids) if ids else []
        except (ValueError, TypeError):
            ids_obj = []
        return _invoke(sp, 'detailContent', ids_obj)
    if method == 'searchContent':
        key = rest[0] if len(rest) > 0 else ''
        pg = rest[2] if len(rest) > 2 and rest[2].strip() else '1'
        return _invoke_variants(sp, 'searchContent', [(key, False, pg), (key, False), (key,)])
    if method == 'playerContent':
        flag = rest[0] if len(rest) > 0 else ''
        pid = rest[1] if len(rest) > 1 else ''
        vip = rest[2] if len(rest) > 2 else '[]'
        try:
            vip_obj = json.loads(vip) if vip else []
        except (ValueError, TypeError):
            vip_obj = []
        return _invoke(sp, 'playerContent', flag, pid, vip_obj)
    if method == 'liveContent':
        return _invoke(sp, 'liveContent', rest[0] if len(rest) > 0 else '')
    if method == 'proxy':
        params = json.loads(rest[0]) if rest else {}
        fn = 'proxy' if 'proxy' in type(sp).__dict__ else 'localProxy'
        result = _invoke(sp, fn, params)
        if isinstance(result, (list, tuple)) and len(result) >= 3 and isinstance(result[2], bytes):
            result = list(result)
            result[2] = {'base64': base64.b64encode(result[2]).decode('ascii')}
        return result
    raise ValueError('unknown method: %s' % method)


_INSTANCES = {}


def invoke(script_path, class_name, method, ext='', args_json='[]'):
    """Chaquopy 入口：执行一次 py 蜘蛛调用，返回 JSON 字符串。"""
    if not os.path.exists(script_path):
        raise FileNotFoundError('pyPath 不存在：%s' % script_path)
    try:
        args = json.loads(args_json) if args_json else []
    except (ValueError, TypeError):
        args = []
    if not isinstance(args, list):
        args = [args]
    rest = [a if isinstance(a, str) else json.dumps(a, ensure_ascii=False) for a in args]
    ns = _load_script(script_path)
    cls = ns.get(class_name or 'Spider')
    if cls is None:
        raise ValueError('Python 类不存在: %s' % class_name)
    key = (class_name, ext or '')
    sp = _INSTANCES.pop(key, None)
    if sp is None:
        sp = cls()
        try:
            sp.init(ext or '')
        except (AttributeError, TypeError):
            pass
    broken = False
    try:
        result = _call_method(sp, method, rest)
    except BaseException:
        broken = True
        raise
    finally:
        if not broken:
            if len(_INSTANCES) > 64:
                _INSTANCES.clear()
            _INSTANCES[key] = sp
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)
