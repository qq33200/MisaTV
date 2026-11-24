package com.winbox

import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/** MethodChannel: com.winbox/libtorrent */
class LibtorrentPlugin : FlutterPlugin, MethodChannel.MethodCallHandler {
    private var channel: MethodChannel? = null
    private var bridge: LibtorrentBridge? = null
    private val executor: ExecutorService = Executors.newCachedThreadPool { runnable ->
        Thread(runnable, "winbox-libtorrent").apply { isDaemon = true }
    }

    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        bridge = LibtorrentBridge()
        channel = MethodChannel(binding.binaryMessenger, CHANNEL).also {
            it.setMethodCallHandler(this)
        }
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        executor.execute {
            try {
                val b = bridge ?: error("libtorrent bridge not attached")
                val out: Map<String, Any?> = when (call.method) {
                    "start" -> b.start(call.string("savePath"))

                    "addMagnet" -> b.addMagnet(
                        magnet = call.string("magnet"),
                        savePath = call.string("savePath"),
                        infoHash = call.string("infoHash"),
                        timeoutMs = call.number("timeoutMs", 60_000L),
                    )

                    "selectFile" -> b.selectFile(
                        infoHash = call.string("infoHash"),
                        fileIndex = call.number("fileIndex", 0L).toInt(),
                    )

                    "setPieceDeadlines" -> b.setPieceDeadlines(
                        infoHash = call.string("infoHash"),
                        firstPiece = call.number("firstPiece", 0L).toInt(),
                        lastPiece = call.number("lastPiece", 0L).toInt(),
                        firstDeadlineMs = call.number("firstDeadlineMs", 2000L).toInt(),
                        stepMs = call.number("stepMs", 60L).toInt(),
                        clear = call.boolean("clear", false),
                    )

                    "setSeekDeadlines" -> b.setSeekDeadlines(
                        infoHash = call.string("infoHash"),
                        fileIndex = call.number("fileIndex", 0L).toInt(),
                        offset = call.number("offset", 0L),
                        horizon = call.number("horizon", 32L).toInt(),
                        firstDeadlineMs = call.number("firstDeadlineMs", 2000L).toInt(),
                        stepMs = call.number("stepMs", 60L).toInt(),
                    )

                    "havePieceRange" -> mapOf(
                        "ok" to true,
                        "covered" to b.havePieceRange(
                            infoHash = call.string("infoHash"),
                            firstPiece = call.number("firstPiece", 0L).toInt(),
                            lastPiece = call.number("lastPiece", 0L).toInt(),
                        ),
                    )

                    "status" -> b.status(call.string("infoHash"))
                    "remove" -> b.remove(call.string("infoHash"))
                    "stop" -> b.stop()
                    else -> {
                        result.notImplemented()
                        return@execute
                    }
                }
                result.success(out)
            } catch (t: Throwable) {
                result.error("LIBTORRENT_ERROR", t.message ?: t.toString(), null)
            }
        }
    }

    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        channel?.setMethodCallHandler(null)
        channel = null
        executor.execute {
            try {
                bridge?.stop()
            } catch (_: Throwable) {
            }
        }
        executor.shutdown()
        bridge = null
    }

    companion object {
        private const val CHANNEL = "com.winbox/libtorrent"
    }
}

private fun MethodCall.string(key: String): String =
    (argument<Any>(key) as? String)?.takeIf { it.isNotEmpty() }
        ?: throw IllegalArgumentException("missing string arg: $key")

private fun MethodCall.number(key: String, default: Long): Long =
    (argument<Any>(key) as? Number)?.toLong() ?: default

private fun MethodCall.boolean(key: String, default: Boolean): Boolean =
    (argument<Any>(key) as? Boolean) ?: default
