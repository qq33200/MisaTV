import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/services.dart';

/// 本地文件/目录选择与保存。桌面端走系统对话框；Web 版在 `*_web.dart` 里统一拒绝。
class FileDialogService {
  const FileDialogService._();

  static const jsonType = XTypeGroup(
    label: 'JSON / TVBox 订阅',
    extensions: ['json', 'txt'],
  );
  static const pyType = XTypeGroup(label: 'Python 蜘蛛', extensions: ['py']);
  static const backupType = XTypeGroup(
    label: 'MisaTV / Win-Box 备份',
    extensions: ['json'],
  );
  static const liveType = XTypeGroup(
    label: '直播源（TXT / M3U）',
    extensions: ['txt', 'm3u', 'm3u8'],
  );
  static const zipType = XTypeGroup(label: '本地包（ZIP）', extensions: ['zip']);
  static const csvType = XTypeGroup(
    label: 'CSV / 文本（PikPak 分享链接）',
    extensions: ['csv', 'txt'],
  );
  static const exeType = XTypeGroup(label: '第三方播放器', extensions: ['exe']);
  static const fontType = XTypeGroup(
    label: '字体（TTF / OTF）',
    extensions: ['ttf', 'otf'],
  );

  /// 选择单个文件，返回绝对路径；取消返回 null。
  static Future<String?> pickFile({
    required List<XTypeGroup> types,
    String confirmButtonText = '选择',
  }) async {
    final file = await openFile(
      acceptedTypeGroups: types,
      confirmButtonText: confirmButtonText,
    );
    return file?.path;
  }

  /// 多选文件，返回绝对路径列表；取消返回 null。
  static Future<List<String>?> pickFiles({
    required List<XTypeGroup> types,
    String confirmButtonText = '选择',
  }) async {
    final files = await openFiles(
      acceptedTypeGroups: types,
      confirmButtonText: confirmButtonText,
    );
    if (files.isEmpty) return null;
    return files.map((file) => file.path).toList();
  }

  /// 选择目录，返回绝对路径；取消返回 null。
  static Future<String?> pickDirectory({String confirmButtonText = '选择文件夹'}) =>
      getDirectoryPath(confirmButtonText: confirmButtonText);

  /// 读取文本文件（备份导入等）。
  static Future<String> readText(String path) => File(path).readAsString();

  /// 选择保存位置并写入文本；取消返回 null，成功返回文件路径。
  ///
  /// Android 上 file_selector 的保存对话框根本没实现（调 getSaveLocation
  /// 就抛 UnimplementedError），所以直接走原生通道写进系统 Download 目录
  ///（MediaStore，不用存储权限，卸载后文件还在），返回真实路径。
  static Future<String?> saveText({
    required String suggestedName,
    required String text,
    XTypeGroup? type,
  }) async {
    if (Platform.isAndroid) {
      const channel = MethodChannel('com.winbox/system');
      final res = await channel.invokeMethod<Map<Object?, Object?>>(
        'saveToDownloads',
        {'name': suggestedName, 'content': text},
      );
      if (res?['ok'] == true) return res?['path'] as String?;
      throw StateError(res?['error']?.toString() ?? '保存失败');
    }
    final location = await getSaveLocation(
      suggestedName: suggestedName,
      acceptedTypeGroups: type == null ? const [] : [type],
      confirmButtonText: '保存',
    );
    if (location == null) return null;
    final file = File(location.path);
    await file.writeAsString(text);
    return file.path;
  }
}
