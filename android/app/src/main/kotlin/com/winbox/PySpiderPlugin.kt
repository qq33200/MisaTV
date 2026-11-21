package com.winbox

import android.content.Context
import android.os.Handler
import android.os.Looper
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

/**
 * WinBox Android py 蜘蛛桥（Chaquopy）。
 *
 * Dart 侧走 MethodChannel "com.winbox/py_spider"，方法 "invoke"：
 *   args: {scriptPath, className, method, ext, argsJson}
 * 返回：py 蜘蛛结果的 JSON 字符串；失败时 result.error("PY_ERROR", msg, null)。
 *
 * 注意：Chaquopy 的 Python 调用必须在主线程初始化后执行；py 蜘蛛的网络请求
 * 在 Chaquopy 侧是同步阻塞的，因此 invoke 在后台线程跑，回调回主线程。
 * 常驻取流（runner.py --hold / -serve）暂不支持：Chaquopy 内没有进程概念，
 * 脚本内建的本机 HTTP 取流服务需另行设计，M1 只覆盖一次性调用。
 */
class PySpiderPlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
    private lateinit var channel: MethodChannel
    private lateinit var appContext: Context
    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        appContext = binding.applicationContext
        channel = MethodChannel(binding.binaryMessenger, "com.winbox/py_spider")
        channel.setMethodCallHandler(this)
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel.setMethodCallHandler(null)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        if (call.method != "invoke") {
            result.notImplemented()
            return
        }
        val scriptPath = call.argument<String>("scriptPath") ?: ""
        val className = call.argument<String>("className") ?: "Spider"
        val method = call.argument<String>("method") ?: ""
        val ext = call.argument<String>("ext") ?: ""
        val argsJson = call.argument<String>("argsJson") ?: "[]"
        Thread {
            try {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(appContext))
                }
                val py = Python.getInstance()
                val module = py.getModule("winbox_spider")
                val out = module.callAttr(
                    "invoke", scriptPath, className, method, ext, argsJson
                ).toString()
                mainHandler.post { result.success(out) }
            } catch (e: Exception) {
                val msg = (e.message ?: e.toString()).take(2000)
                mainHandler.post { result.error("PY_ERROR", msg, null) }
            }
        }.start()
    }
}
