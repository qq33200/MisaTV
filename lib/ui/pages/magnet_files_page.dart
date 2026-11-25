import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app.dart';
import '../../services/torrent/magnet.dart';
import '../../services/torrent/torrent_play.dart';
import 'player/magnet_play.dart';

/// 磁力文件列表：**先解析元数据，再让用户挑文件**（对齐迅雷那类 BT 下载器）。
///
/// 搜索框粘磁链后进这里，而不是直接起播：种子内常有正片/花絮/字幕/样片多个文件，
/// 自动选片只是兜底，用户想看哪一集应该自己点。解析出来的句柄会留在引擎里，
/// 选完文件直接出流，不用再等一次元数据。
class MagnetFilesPage extends StatefulWidget {
  const MagnetFilesPage({super.key, required this.magnet, this.title = ''});

  final String magnet;

  /// 解析出 `dn` 之前的占位标题。
  final String title;

  @override
  State<MagnetFilesPage> createState() => _MagnetFilesPageState();
}

class _MagnetFilesPageState extends State<MagnetFilesPage> {
  BtProbeResult? _result;
  String _status = '正在解析元数据…';
  bool _parsing = true;
  bool _closed = false;

  @override
  void initState() {
    super.initState();
    // 需要 AppScope，放到首帧之后取。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_probe());
    });
  }

  @override
  void dispose() {
    _closed = true;
    super.dispose();
  }

  Future<void> _probe() async {
    final torrent = AppScope.of(context).torrentPlay;
    if (torrent == null) {
      setState(() {
        _parsing = false;
        _result = const BtProbeResult.error('当前平台没有内置 BT 引擎');
      });
      return;
    }
    setState(() {
      _parsing = true;
      _status = '正在解析元数据…';
    });
    final result = await torrent.probe(
      widget.magnet,
      onProgress: (message) {
        if (!_closed && mounted) setState(() => _status = message);
      },
      isCancelled: () => _closed,
    );
    if (!mounted) return;
    setState(() {
      _parsing = false;
      _result = result;
    });
  }

  String get _pageTitle {
    final parsed = _result?.title.trim() ?? '';
    if (parsed.isNotEmpty) return parsed;
    if (widget.title.trim().isNotEmpty) return widget.title.trim();
    return '磁力解析';
  }

  Future<void> _copyMagnet() async {
    await Clipboard.setData(ClipboardData(text: widget.magnet));
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('磁力链接已复制')));
  }

  Future<void> _play(TorrentFile file) async {
    await startMagnetPlay(
      context,
      widget.magnet,
      title: widget.title,
      fileIndex: file.index,
    );
  }

  Future<void> _downloadAll() async {
    final app = AppScope.of(context);
    try {
      await app.downloadManager.add(widget.magnet);
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('已加入下载（整个种子）')));
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('加入下载失败：$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(
          _pageTitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        actions: [
          IconButton(
            onPressed: _copyMagnet,
            tooltip: '复制磁力',
            icon: const Icon(Icons.link_rounded),
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_parsing) return _buildParsing();
    final result = _result;
    if (result == null) return const SizedBox.shrink();
    if (!result.ok) return _buildError(result.error);
    return _buildFiles(result);
  }

  Widget _buildParsing() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 30,
              height: 30,
              child: CircularProgressIndicator(strokeWidth: 2.6),
            ),
            const SizedBox(height: 18),
            Text(_status, textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Text(
              '冷门种子可能要等几十秒（连 peer → 取元数据 → 校验文件表）。',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(
                  context,
                ).colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
            const SizedBox(height: 18),
            TextButton(
              onPressed: () => Navigator.of(context).maybePop(),
              child: const Text('取消'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError(String message) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.error_outline_rounded,
              size: 34,
              color: Theme.of(context).colorScheme.error,
            ),
            const SizedBox(height: 14),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 18),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                OutlinedButton.icon(
                  onPressed: _copyMagnet,
                  icon: const Icon(Icons.copy_rounded, size: 18),
                  label: const Text('复制磁力'),
                ),
                const SizedBox(width: 12),
                FilledButton(
                  onPressed: () => unawaited(_probe()),
                  child: const Text('重试'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFiles(BtProbeResult result) {
    final videos = result.files.where((f) => isVideoFile(f.path)).length;
    final total = result.files.fold<int>(
      0,
      (sum, f) => sum + (f.length > 0 ? f.length : 0),
    );
    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
          child: Text(
            '共 ${result.files.length} 个文件 · ${_sizeText(total)} · 视频 $videos 个',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ListView.separated(
            itemCount: result.files.length,
            separatorBuilder: (_, _) => const Divider(height: 1),
            itemBuilder: (_, index) {
              final file = result.files[index];
              final video = isVideoFile(file.path);
              return ListTile(
                enabled: video,
                leading: Icon(
                  video
                      ? Icons.movie_outlined
                      : Icons.insert_drive_file_outlined,
                ),
                title: Text(
                  _baseName(file.path),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                subtitle: Text(
                  '${_sizeText(file.length)}${video ? '' : ' · 非视频'}',
                ),
                trailing: video
                    ? FilledButton(
                        onPressed: () => unawaited(_play(file)),
                        child: const Text('播放'),
                      )
                    : null,
                onTap: video ? () => unawaited(_play(file)) : null,
              );
            },
          ),
        ),
        const Divider(height: 1),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => unawaited(_downloadAll()),
                    icon: const Icon(Icons.download_rounded, size: 18),
                    label: const Text('下载整个种子'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

String _baseName(String path) {
  final parts = path.split(RegExp(r'[\\/]')).where((p) => p.isNotEmpty).toList();
  if (parts.isEmpty) return path;
  return parts.last;
}

String _sizeText(int bytes) {
  if (bytes <= 0) return '未知大小';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var value = bytes.toDouble();
  var unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  final digits = unit == 0 || value >= 100 ? 0 : 1;
  return '${value.toStringAsFixed(digits)} ${units[unit]}';
}
