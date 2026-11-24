import 'package:flutter/services.dart';

/// libtorrent 原生桥（MethodChannel `com.winbox/libtorrent`）。
///
/// Android 侧由 `LibtorrentPlugin` 实现。插件缺失 / 原生库加载失败时，
/// 所有方法静默返回 false/null，让 [TorrentPlay] 回落 aria2。
class LibtorrentEngine {
  LibtorrentEngine({MethodChannel? channel, this.logger})
    : _channel = channel ?? const MethodChannel('com.winbox/libtorrent');

  final MethodChannel _channel;
  final void Function(String message)? logger;

  bool _disabled = false;
  bool get disabled => _disabled;

  Future<bool> _ok(String method, [Map<String, Object?>? args]) async {
    if (_disabled) return false;
    try {
      final result = await _channel.invokeMapMethod<String, Object?>(
        method,
        args,
      );
      return result?['ok'] == true;
    } on MissingPluginException catch (e) {
      _disabled = true;
      logger?.call('libtorrent 插件未注册：$e');
      return false;
    } catch (e) {
      logger?.call('libtorrent $method 失败：$e');
      return false;
    }
  }

  Future<bool> start(String saveDir) =>
      _ok('start', <String, Object?>{'savePath': saveDir});

  Future<LibtorrentOpenResult?> openMagnet(
    String magnet, {
    required String infoHash,
    required String saveDir,
    required Duration timeout,
  }) async {
    if (_disabled) return null;
    try {
      final result = await _channel.invokeMapMethod<String, Object?>(
        'addMagnet',
        <String, Object?>{
          'magnet': magnet,
          'savePath': saveDir,
          'infoHash': infoHash,
          'timeoutMs': timeout.inMilliseconds,
        },
      );
      if (result == null || result['ok'] != true) return null;
      final files = <LibtorrentFile>[];
      final raw = result['files'];
      if (raw is List) {
        for (final item in raw) {
          if (item is! Map) continue;
          final map = Map<dynamic, dynamic>.from(item);
          files.add(
            LibtorrentFile(
              index: (map['index'] as num?)?.toInt() ?? 0,
              path: '${map['path'] ?? ''}',
              length: (map['length'] as num?)?.toInt() ?? 0,
              offset: (map['offset'] as num?)?.toInt() ?? 0,
            ),
          );
        }
      }
      return LibtorrentOpenResult(
        infoHash: '${result['infoHash'] ?? infoHash}',
        files: files,
        pieceLength: (result['pieceLength'] as num?)?.toInt() ?? 0,
      );
    } on MissingPluginException catch (e) {
      _disabled = true;
      logger?.call('libtorrent 插件未注册：$e');
      return null;
    } catch (e) {
      logger?.call('libtorrent addMagnet 失败：$e');
      return null;
    }
  }

  Future<bool> selectFile(String infoHash, int fileIndex) => _ok(
    'selectFile',
    <String, Object?>{'infoHash': infoHash, 'fileIndex': fileIndex},
  );

  /// 按桌面端契约给当前读取位置之后的 32 片排 deadline。
  Future<bool> setSeekDeadlines(
    String infoHash,
    int fileIndex,
    int offset, {
    int horizon = 32,
    int firstDeadlineMs = 2000,
    int stepMs = 60,
  }) =>
      _ok('setSeekDeadlines', <String, Object?>{
        'infoHash': infoHash,
        'fileIndex': fileIndex,
        'offset': offset,
        'horizon': horizon,
        'firstDeadlineMs': firstDeadlineMs,
        'stepMs': stepMs,
      });

  Future<bool> havePieceRange(String infoHash, int first, int last) async {
    if (_disabled) return false;
    try {
      final result = await _channel.invokeMapMethod<String, Object?>(
        'havePieceRange',
        <String, Object?>{
          'infoHash': infoHash,
          'firstPiece': first,
          'lastPiece': last,
        },
      );
      return result?['covered'] == true;
    } catch (e) {
      logger?.call('libtorrent havePieceRange 失败：$e');
      return false;
    }
  }

  Future<Map<String, Object?>?> status(String infoHash) async {
    if (_disabled) return null;
    try {
      return await _channel.invokeMapMethod<String, Object?>(
        'status',
        <String, Object?>{'infoHash': infoHash},
      );
    } catch (e) {
      logger?.call('libtorrent status 失败：$e');
      return null;
    }
  }

  Future<bool> remove(String infoHash) =>
      _ok('remove', <String, Object?>{'infoHash': infoHash});

  Future<bool> stop() => _ok('stop');
}

class LibtorrentFile {
  const LibtorrentFile({
    required this.index,
    required this.path,
    required this.length,
    required this.offset,
  });

  /// 1-based，与 aria2 / `/bt/<hash>/<index>` 保持一致。
  final int index;
  final String path;
  final int length;

  /// 该文件在 torrent 数据流内的绝对偏移（libtorrent FileStorage 给出）。
  final int offset;
}

class LibtorrentOpenResult {
  const LibtorrentOpenResult({
    required this.infoHash,
    required this.files,
    required this.pieceLength,
  });

  final String infoHash;
  final List<LibtorrentFile> files;
  final int pieceLength;
}
