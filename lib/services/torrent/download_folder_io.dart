import 'dart:io';

import 'package:flutter/services.dart';

/// 在系统文件管理器中打开下载目录。
///
/// 返回 null 表示已打开（或已发起），否则返回错误信息，调用方可以 toast 提示。
///
/// Android 上没有 xdg-open（之前直接调等于没反应）：走原生 MethodChannel
///（com.winbox/system），经 FileProvider 共享 content:// URI 打开系统文件管理器。
Future<String?> openDownloadFolder(String dir) async {
  final path = dir.trim();
  if (path.isEmpty) return '目录为空';
  try {
    if (Platform.isAndroid) {
      const channel = MethodChannel('com.winbox/system');
      final res = await channel.invokeMethod<Map<Object?, Object?>>(
        'openFolder',
        {'path': path},
      );
      if (res?['ok'] == true) return null;
      return res?['error']?.toString() ?? '打开失败';
    }
    if (Platform.isWindows) {
      await Process.run('explorer', [path]);
    } else if (Platform.isMacOS) {
      await Process.run('open', [path]);
    } else {
      await Process.run('xdg-open', [path]);
    }
    return null;
  } catch (e) {
    return '$e';
  }
}
