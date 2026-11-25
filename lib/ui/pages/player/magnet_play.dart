import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../app.dart';
import '../../../models/vod.dart';
import '../../../services/torrent/magnet.dart';
import '../../../services/torrent/torrent_play.dart';
import '../../raw_play.dart';

/// 统一的磁力播放入口：详情页点播与搜索框粘磁链都走这里。
///
/// 链路与详情页一致：迅雷云盘离线优先 → aria2 / libtorrent 回退；
/// 拿到地址后按容器分流——mp4/webm 交本机中继给内置播放器，其余拉外部播放器接力。
///
/// [title] 为空时用磁链里的 `dn`（显示名），再退到「磁力播放」。
/// [fileIndex] 由「磁力文件列表」传入（种子内文件序号）；为空时自动选片。
Future<void> startMagnetPlay(
  BuildContext context,
  String magnet, {
  String title = '',
  int? fileIndex,
}) async {
  final app = AppScope.of(context);
  final torrent = app.torrentPlay;
  final info = parseMagnet(magnet);
  final fallback = (info?.displayName ?? '').trim();
  final name = title.trim().isNotEmpty
      ? title.trim()
      : (fallback.isNotEmpty ? fallback : '磁力播放');
  if (torrent == null) {
    _toast(context, '当前平台没有内置 BT 引擎');
    return;
  }

  final progress = ValueNotifier<String>('正在准备磁力播放…');
  var cancelled = false;
  var dialogClosed = false;
  void closeDialog() {
    if (dialogClosed) return;
    dialogClosed = true;
    if (context.mounted) Navigator.of(context, rootNavigator: true).pop();
  }

  unawaited(
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _MagnetPreparingDialog(
        status: progress,
        onCancel: () {
          if (cancelled) return;
          cancelled = true;
          closeDialog();
        },
      ),
    ),
  );

  BtPlayOutcome outcome;
  try {
    outcome = await torrent.open(
      magnet,
      title: name,
      fileIndex: fileIndex,
      isCancelled: () => cancelled,
      onProgress: (message) {
        if (!cancelled && !dialogClosed) progress.value = message;
      },
    );
  } catch (e) {
    outcome = BtPlayOutcome.unsupported('$e');
  }
  if (!context.mounted) return;
  closeDialog();
  // 用户已取消：后台任务已中止，不再弹任何结果提示。
  if (cancelled) return;

  final provider = outcome.provider.isEmpty ? 'BT' : outcome.provider;
  if (outcome.kind == BtPlayKind.inline) {
    await openRawPlayback(
      context,
      title: outcome.title.isEmpty ? name : outcome.title,
      subtitle: '磁力 · $provider',
      episodes: [Episode(name: '正片', url: outcome.url)],
      sourceKey: 'bt:${outcome.infoHash}',
      flag: provider,
    );
  } else if (outcome.kind == BtPlayKind.external) {
    _toast(context, '已在 ${outcome.player} 中打开（${outcome.title}）');
  } else {
    await _showUnsupported(context, outcome.reason, magnet);
  }
}

Future<void> _showUnsupported(
  BuildContext context,
  String reason,
  String magnet,
) async {
  await showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('磁力暂时无法播放'),
      content: Text(reason.isEmpty ? '未知原因' : reason),
      actions: [
        TextButton.icon(
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: magnet));
            if (ctx.mounted) {
              Navigator.of(ctx).pop();
              _toast(context, '磁力链接已复制，可交给下载工具');
            }
          },
          icon: const Icon(Icons.copy_rounded),
          label: const Text('复制磁力'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('知道了'),
        ),
      ],
    ),
  );
}

void _toast(BuildContext context, String message) {
  if (!context.mounted) return;
  ScaffoldMessenger.of(
    context,
  ).showSnackBar(SnackBar(content: Text(message)));
}

/// 磁力解析等待中的模态提示（结果出来后由调用方 pop）。
///
/// 冷门种子取元数据可能要几十秒，弹窗不能没有出口：等待满 10 秒后出现
/// 「取消」并显示已等待时长，避免用户以为卡死。
class _MagnetPreparingDialog extends StatefulWidget {
  const _MagnetPreparingDialog({required this.status, required this.onCancel});

  final ValueListenable<String> status;
  final VoidCallback onCancel;

  @override
  State<_MagnetPreparingDialog> createState() => _MagnetPreparingDialogState();
}

class _MagnetPreparingDialogState extends State<_MagnetPreparingDialog> {
  static const _cancelAfterSeconds = 10;

  Timer? _timer;
  int _elapsed = 0;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _elapsed++);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canCancel = _elapsed >= _cancelAfterSeconds;
    final hintStyle = Theme.of(context).textTheme.bodySmall?.copyWith(
      color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.65),
    );
    return PopScope(
      canPop: false,
      child: AlertDialog(
        content: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2.5),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ValueListenableBuilder<String>(
                    valueListenable: widget.status,
                    builder: (_, message, _) => Text(message),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _elapsed < 3
                        ? '冷门资源或云端离线可能需要等待一段时间。'
                        : '已等待 $_elapsed 秒，冷门资源可能需要更久'
                              '${canCancel ? '；也可以取消后重试。' : '。'}',
                    style: hintStyle,
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          if (canCancel)
            TextButton(onPressed: widget.onCancel, child: const Text('取消')),
        ],
      ),
    );
  }
}
