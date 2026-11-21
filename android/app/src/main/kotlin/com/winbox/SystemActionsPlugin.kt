package com.winbox

import android.content.ActivityNotFoundException
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import androidx.core.content.FileProvider
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * 系统级打开动作（Android 专有）。
 *
 *   openFolder(path) -> {ok, error}  用系统文件管理器打开目录
 *   openFile(path)   -> {ok, error}  用系统默认应用打开文件（视频/图片/文档）
 *   saveToDownloads(name, content) -> {ok, path, error}
 *                      把文本存进系统 Download 目录（备份导出用）
 *
 * 为什么不用 Dart 的 Process.run(xdg-open)：Android 上根本没有 xdg-open，
 * 直接调等于没反应（之前「打开文件夹」点完毫无反应就是这个原因）。
 * 文件要走 FileProvider 共享 content:// URI，否则 API 24+ 会抛
 * FileUriExposedException。
 *
 * 为什么保存也要走原生：file_selector 的 getSaveLocation（保存对话框）在
 * Android 上根本没实现，调了就抛 UnimplementedError: getSavePath() has not
 * been implemented（备份导出就是这么坏的）。这里直接走 MediaStore 写进
 * 系统 Download 目录，不用存储权限，卸载后文件还在。
 */
class SystemActionsPlugin : FlutterPlugin, MethodChannel.MethodCallHandler {

    private lateinit var channel: MethodChannel
    private var context: Context? = null

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        context = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "com.winbox/system")
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
        context = null
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "openFolder" -> {
                val path = call.argument<String>("path") ?: ""
                result.success(openFolder(path))
            }
            "openFile" -> {
                val path = call.argument<String>("path") ?: ""
                result.success(openFile(path))
            }
            "saveToDownloads" -> {
                val name = call.argument<String>("name") ?: "backup.json"
                val content = call.argument<String>("content") ?: ""
                result.success(saveToDownloads(name, content))
            }
            else -> result.notImplemented()
        }
    }

    private fun openFolder(path: String): Map<String, Any?> {
        val ctx = context ?: return mapOf("ok" to false, "error" to "no context")
        val dir = File(path)
        if (!dir.exists()) return mapOf("ok" to false, "error" to "目录不存在")
        val target = if (dir.isDirectory) dir else (dir.parentFile ?: dir)
        return try {
            val uri = FileProvider.getUriForFile(
                ctx,
                "${ctx.packageName}.fileprovider",
                target,
            )
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "resource/folder")
                addFlags(
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        Intent.FLAG_ACTIVITY_NEW_TASK,
                )
            }
            ctx.startActivity(intent)
            mapOf("ok" to true)
        } catch (e: ActivityNotFoundException) {
            // 没有能处理 resource/folder 的文件管理器：退到通用查看，让系统选应用。
            try {
                val uri = FileProvider.getUriForFile(
                    ctx,
                    "${ctx.packageName}.fileprovider",
                    target,
                )
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "*/*")
                    addFlags(
                        Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_ACTIVITY_NEW_TASK,
                    )
                }
                ctx.startActivity(Intent.createChooser(intent, null))
                mapOf("ok" to true)
            } catch (e2: Exception) {
                mapOf("ok" to false, "error" to (e2.message ?: "无法打开文件管理器"))
            }
        } catch (e: Exception) {
            mapOf("ok" to false, "error" to (e.message ?: "打开失败"))
        }
    }

    private fun openFile(path: String): Map<String, Any?> {
        val ctx = context ?: return mapOf("ok" to false, "error" to "no context")
        val file = File(path)
        if (!file.exists()) return mapOf("ok" to false, "error" to "文件不存在")
        return try {
            val uri = FileProvider.getUriForFile(
                ctx,
                "${ctx.packageName}.fileprovider",
                file,
            )
            val ext = file.extension.lowercase()
            val mime = MimeTypeMap.getSingleton()
                .getMimeTypeFromExtension(ext) ?: "*/*"
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, mime)
                addFlags(
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or
                        Intent.FLAG_ACTIVITY_NEW_TASK,
                )
            }
            ctx.startActivity(intent)
            mapOf("ok" to true)
        } catch (e: Exception) {
            mapOf("ok" to false, "error" to (e.message ?: "打开失败"))
        }
    }

    /**
     * 把文本存进系统 Download 目录，返回 {ok, path, error}。
     *
     * API 29+ 走 MediaStore（不需要存储权限，文件进用户 Download 文件夹，
     * 卸载应用后还在）；API 29 以下直接写文件（旧版本无分区存储限制）。
     */
    private fun saveToDownloads(name: String, content: String): Map<String, Any?> {
        val ctx = context ?: return mapOf("ok" to false, "error" to "no context")
        val safeName = name.ifBlank { "backup.json" }
        val bytes = content.toByteArray(Charsets.UTF_8)
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.MediaColumns.DISPLAY_NAME, safeName)
                    put(MediaStore.MediaColumns.MIME_TYPE, "application/json")
                    put(
                        MediaStore.MediaColumns.RELATIVE_PATH,
                        Environment.DIRECTORY_DOWNLOADS,
                    )
                }
                val uri = ctx.contentResolver.insert(
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                    values,
                ) ?: return mapOf("ok" to false, "error" to "无法创建下载文件")
                ctx.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
                    ?: return mapOf("ok" to false, "error" to "无法写入下载文件")
                mapOf(
                    "ok" to true,
                    "path" to "${Environment.getExternalStoragePublicDirectory(
                        Environment.DIRECTORY_DOWNLOADS,
                    ).absolutePath}/$safeName",
                )
            } else {
                val dir = Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DOWNLOADS,
                )
                if (!dir.exists()) dir.mkdirs()
                val file = File(dir, safeName)
                file.writeBytes(bytes)
                mapOf("ok" to true, "path" to file.absolutePath)
            }
        } catch (e: Exception) {
            mapOf("ok" to false, "error" to (e.message ?: "保存失败"))
        }
    }
}
