# assets/aria2

这个目录放 BT 引擎（磁力播放的地基，aria2 项目，GPLv2）：

- Windows：`aria2c.exe`（从 [aria2/releases](https://github.com/aria2/aria2/releases) 下载 Windows 64 位压缩包）。
- **Android arm64：`aria2c-android-arm64`，已内置** —— aria2 官方 1.37.0 的
  `aria2-1.37.0-aarch64-linux-android-build1.zip` 里的 `aria2c`（6.1MB，aarch64 ELF，
  仅依赖系统 libm/libdl/libc，OpenSSL/zlib/c-ares 已静态链接）。应用首次磁力播放时
  把它释放到应用数据目录下的 `aria2/aria2c` 并 chmod +x，然后用同一套 RPC 参数拉起。

程序首次使用磁力播放时会把引擎释放到应用数据目录下的 `aria2/`，
下载数据与 `.aria2` 控制文件在 `bt/`，可随时整个删除（只影响续传）。

注意：Android 版默认不开 c-ares 异步 DNS（系统无 /etc/resolv.conf），解析可能稍慢；
HTTPS tracker 需要 CA 证书时，系统证书不在标准 Unix 路径，暂不支持——磁力元数据主要
走 DHT 与 UDP/HTTP tracker，不受影响。
