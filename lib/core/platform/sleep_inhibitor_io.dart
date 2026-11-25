import 'dart:ffi';
import 'dart:io';

import 'package:wakelock_plus/wakelock_plus.dart';

typedef _SetThreadExecutionStateNative = Uint32 Function(Uint32);
typedef _SetThreadExecutionStateDart = int Function(int);

/// 播放期间阻止系统自动休眠 / 关屏。
///
/// Windows：`SetThreadExecutionState` 是**按线程**记录状态的，必须在同一个线程
/// 先 `ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED`，结束时再
/// `ES_CONTINUOUS` 撤销。Dart UI isolate 一直存活，所以 acquire/release 成对调用即可。
///
/// Android：Muse 交接版用 `wakelock_plus` 持有 wake lock，覆盖「视频加载中」与
/// 「播放中」两个阶段——之前 fork 只有 Windows 分支（`if (!Platform.isWindows) return;`），
/// Android 上加载/播放会息屏。外层 _depth 引用计数保证换集/重进播放器时不会
/// 因调用方 acquire/release 不配对而过早撤销。
class SleepInhibitor {
  SleepInhibitor._();

  static const _continuous = 0x80000000;
  static const _systemRequired = 0x00000001;
  static const _displayRequired = 0x00000002;

  static _SetThreadExecutionStateDart? _fn;
  static int _depth = 0;

  /// 引用计数：换集/重进播放器时避免提前撤销。
  static void acquire() {
    _depth++;
    if (_depth != 1) return;
    _apply(true);
  }

  static void release() {
    if (_depth <= 0) return;
    _depth--;
    if (_depth != 0) return;
    _apply(false);
  }

  /// 播放器销毁时兜底：无论计数多少都恢复系统默认休眠策略。
  static void releaseAll() {
    _depth = 0;
    _apply(false);
  }

  static void _apply(bool keepAwake) {
    if (Platform.isAndroid) {
      // wakelock_plus 内部有 Android 平台实现（WakeLock ACTION_ACQUIRE），
      // toggle 是异步的，这里不 await：播放器 acquire/release 频繁，排队无妨。
      WakelockPlus.toggle(enable: keepAwake);
      return;
    }
    if (Platform.isWindows) {
      _callWindows(
        keepAwake
            ? (_continuous | _systemRequired | _displayRequired)
            : _continuous,
      );
    }
  }

  static void _callWindows(int flags) {
    try {
      _fn ??= DynamicLibrary.open('kernel32.dll')
          .lookupFunction<_SetThreadExecutionStateNative, _SetThreadExecutionStateDart>(
        'SetThreadExecutionState',
      );
      _fn!(flags);
    } catch (_) {
      // 调用失败（权限、无桌面会话）时静默忽略，不影响播放
    }
  }
}
