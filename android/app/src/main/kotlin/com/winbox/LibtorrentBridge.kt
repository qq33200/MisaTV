package com.winbox

import android.util.Log
import org.libtorrent4j.Priority
import org.libtorrent4j.SessionManager
import org.libtorrent4j.Sha1Hash
import org.libtorrent4j.TorrentHandle
import org.libtorrent4j.TorrentInfo
import org.libtorrent4j.swig.torrent_flags_t
import java.io.File
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap

/**
 * WinBox 磁力播放的 libtorrent 原生桥。
 *
 * 设计参照 WinBox 桌面端 + Muse 11-22 的实测参数：
 *   · deadline 窗口 32 片；首片 2000ms，之后每片 +60ms；
 *   · 播放器每读 8MB 重推一次 deadline；
 *   · /bt 门控按 piece 查 havePieceRange，未就绪发 503；
 *   · aria2 分支是 remove 语义，libtorrent 分支同样显式 remove。
 */
class LibtorrentBridge {
    private data class Meta(
        val savePath: String,
        val pieceLength: Int,
        val fileOffsets: LongArray,
        val fileLengths: LongArray,
        val numPieces: Int,
    )

    private val lock = Any()
    private var manager: SessionManager? = null
    private val handles = ConcurrentHashMap<String, TorrentHandle>()
    private val metas = ConcurrentHashMap<String, Meta>()

    fun start(savePath: String): Map<String, Any?> {
        val dir = File(savePath).absoluteFile
        if (!dir.exists()) dir.mkdirs()
        synchronized(lock) {
            if (manager == null) {
                val m = SessionManager(false)
                m.start()
                manager = m
                Log.i(TAG, "libtorrent session started")
            }
        }
        return mapOf("ok" to true, "savePath" to dir.absolutePath)
    }

    fun addMagnet(
        magnet: String,
        savePath: String,
        infoHash: String,
        timeoutMs: Long,
    ): Map<String, Any?> {
        start(savePath)
        val hash = normalizeHash(infoHash)
        val m = manager ?: error("libtorrent session not started")
        val uri = magnet.trim()
        if (!uri.startsWith("magnet:?", ignoreCase = true)) {
            throw IllegalArgumentException("not a magnet uri")
        }
        // 空 flags 不会覆盖 parse_magnet_uri 自己带来的默认 flags；
        // 这里只传一个默认的 torrent_flags_t，避免依赖具体枚举常量名。
        m.download(uri, File(savePath).absoluteFile, torrent_flags_t())

        val handle = waitHandle(m, hash, timeoutMs)
        val ti = waitMeta(handle, timeoutMs)
        handles[hash] = handle
        metas[hash] = Meta(
            savePath = File(savePath).absolutePath,
            pieceLength = ti.pieceLength(),
            fileOffsets = LongArray(ti.numFiles()) { ti.files().fileOffset(it) },
            fileLengths = LongArray(ti.numFiles()) { ti.files().fileSize(it) },
            numPieces = ti.numPieces(),
        )

        val files = ArrayList<Map<String, Any>>(ti.numFiles())
        for (i in 0 until ti.numFiles()) {
            val fs = ti.files()
            files.add(
                mapOf(
                    // 与 aria2 / /bt 路由保持一致，对外用 1-based。
                    "index" to (i + 1),
                    "path" to fs.filePath(i, File(savePath).absolutePath),
                    "length" to fs.fileSize(i),
                    "offset" to fs.fileOffset(i),
                ),
            )
        }
        Log.i(TAG, "magnet ready hash=$hash files=${files.size} pieceLength=${ti.pieceLength()}")
        return mapOf(
            "ok" to true,
            "infoHash" to hash,
            "files" to files,
            "pieceLength" to ti.pieceLength(),
        )
    }

    fun selectFile(infoHash: String, fileIndex: Int): Map<String, Any?> {
        val hash = normalizeHash(infoHash)
        val handle = handleOf(hash)
        val ti = handles[hash]?.torrentFile()
            ?: throw IllegalStateException("torrent metadata not ready")
        val idx = fileIndex - 1
        if (idx < 0 || idx >= ti.numFiles()) {
            throw IllegalArgumentException("file index out of range: $fileIndex")
        }
        val priorities = Priority.array(Priority.IGNORE, ti.numFiles())
        priorities[idx] = Priority.TOP_PRIORITY
        handle.prioritizeFiles(priorities)
        return mapOf("ok" to true, "fileIndex" to fileIndex)
    }

    fun setPieceDeadlines(
        infoHash: String,
        firstPiece: Int,
        lastPiece: Int,
        firstDeadlineMs: Int,
        stepMs: Int,
        clear: Boolean,
    ): Map<String, Any?> {
        val handle = handleOf(normalizeHash(infoHash))
        if (clear) handle.clearPieceDeadlines()
        val end = lastPiece.coerceAtMost(firstPiece + 31)
        for (piece in firstPiece..end) {
            val deadline = firstDeadlineMs + (piece - firstPiece) * stepMs
            handle.setPieceDeadline(piece, deadline)
        }
        return mapOf("ok" to true, "firstPiece" to firstPiece, "lastPiece" to end)
    }

    fun setSeekDeadlines(
        infoHash: String,
        fileIndex: Int,
        offset: Long,
        horizon: Int,
        firstDeadlineMs: Int,
        stepMs: Int,
    ): Map<String, Any?> {
        val hash = normalizeHash(infoHash)
        val handle = handleOf(hash)
        val meta = metas[hash] ?: throw IllegalStateException("torrent meta missing")
        val idx = fileIndex - 1
        if (idx < 0 || idx >= meta.fileOffsets.size) {
            throw IllegalArgumentException("file index out of range: $fileIndex")
        }
        if (meta.pieceLength <= 0 || meta.numPieces <= 0) {
            throw IllegalStateException("bad piece metadata")
        }
        val first = ((meta.fileOffsets[idx] + offset) / meta.pieceLength)
            .toInt()
            .coerceIn(0, meta.numPieces - 1)
        val last = (first + horizon - 1).coerceAtMost(meta.numPieces - 1)

        handle.clearPieceDeadlines()
        for (piece in first..last) {
            val deadline = firstDeadlineMs + (piece - first) * stepMs
            handle.setPieceDeadline(piece, deadline)
        }
        return mapOf(
            "ok" to true,
            "firstPiece" to first,
            "lastPiece" to last,
        )
    }

    fun havePieceRange(infoHash: String, firstPiece: Int, lastPiece: Int): Boolean {
        if (lastPiece < firstPiece) return true
        val handle = handles[normalizeHash(infoHash)] ?: return false
        if (!handle.isValid()) return false
        for (piece in firstPiece..lastPiece) {
            if (!handle.havePiece(piece)) return false
        }
        return true
    }

    fun status(infoHash: String): Map<String, Any?> {
        val handle = handleOf(normalizeHash(infoHash))
        val st = handle.status()
        val ec = st.errorCode()
        return mapOf(
            "ok" to true,
            "progress" to st.progress().toDouble(),
            "done" to st.totalDone(),
            "wantedDone" to st.totalWantedDone(),
            "downloadRate" to st.downloadRate(),
            "uploadRate" to st.uploadRate(),
            "peers" to st.numPeers(),
            "seeds" to st.numSeeds(),
            "finished" to st.isFinished(),
            "seeding" to st.isSeeding(),
            "state" to st.state().toString(),
            "error" to if (ec.value() == 0) "" else ec.message(),
        )
    }

    fun remove(infoHash: String): Map<String, Any?> {
        val hash = normalizeHash(infoHash)
        val handle = handles.remove(hash)
        metas.remove(hash)
        if (handle != null && handle.isValid()) {
            manager?.remove(handle)
            Log.i(TAG, "removed magnet $hash")
        }
        return mapOf("ok" to true)
    }

    fun stop(): Map<String, Any?> {
        synchronized(lock) {
            handles.clear()
            metas.clear()
            val m = manager
            manager = null
            if (m != null) {
                try {
                    m.stop()
                } catch (t: Throwable) {
                    Log.w(TAG, "stop failed: ${t.message}")
                }
            }
        }
        return mapOf("ok" to true)
    }

    private fun handleOf(hash: String): TorrentHandle {
        val existing = handles[hash]
        if (existing != null && existing.isValid()) return existing
        val m = manager ?: error("libtorrent session not started")
        val found = m.find(Sha1Hash.parseHex(hash))
            ?: error("torrent handle not found: $hash")
        handles[hash] = found
        return found
    }

    private fun waitHandle(manager: SessionManager, hash: String, timeoutMs: Long): TorrentHandle {
        val sha1 = Sha1Hash.parseHex(hash)
        val deadline = System.currentTimeMillis() + timeoutMs.coerceAtLeast(1000)
        while (true) {
            val th = manager.find(sha1)
            if (th != null && th.isValid()) return th
            if (System.currentTimeMillis() >= deadline) {
                throw IllegalStateException("等待 torrent handle 超时")
            }
            Thread.sleep(200)
        }
    }

    private fun waitMeta(handle: TorrentHandle, timeoutMs: Long): TorrentInfo {
        val deadline = System.currentTimeMillis() + timeoutMs.coerceAtLeast(1000)
        while (true) {
            try {
                val ti = handle.torrentFile()
                if (ti != null && ti.isValid()) return ti
            } catch (t: Throwable) {
                Log.d(TAG, "metadata poll: ${t.message}")
            }
            if (System.currentTimeMillis() >= deadline) {
                throw IllegalStateException("等待种子 metadata 超时")
            }
            Thread.sleep(200)
        }
    }

    private fun normalizeHash(raw: String): String {
        val value = raw.trim().lowercase(Locale.ROOT)
        if (!REGEX_HASH.matches(value)) {
            throw IllegalArgumentException("invalid infoHash: $raw")
        }
        return value
    }

    companion object {
        private const val TAG = "WinBoxLt"
        private val REGEX_HASH = Regex("^[0-9a-f]{40}$")
    }
}
