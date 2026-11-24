# 内置 curl（JS 蜘蛛的同步 HTTP 引擎）

## 为什么需要

TVBox JS 蜘蛛的 `req()` 是同步调用：QuickJS 里调 `req()` 要立即拿到返回，
Dart 侧只能用 `Process.runSync` 跑子进程来做同步 HTTP。Windows 上直接用
系统自带的 `curl.exe`；但 Android 自带的 toybox 没有 curl，`curl.exe` 在
Android 上根本不存在，所以所有 JS 源的 `req()` 都失败，JS 站点打不开。

## 文件

- `curl-android-arm64`：curl 8.23.0，aarch64 全静态 PIE（musl static），
  来源 stunnel/static-curl 官方 release
  `curl-linux-aarch64-musl-8.23.0-1.tar.xz`（2026-11-21 下载），
  SHA-256 前 20 位 `3a7c6818343f1b518404`（完整值见构建记录）。
  静态链接，不依赖系统 libc，可在 Android 上运行；启动方式与 aria2 相同，
  走 `/system/bin/linker64`（Android 10+ W^X 限制，不能直接 exec 应用数据
  目录里的文件）。
- `cacert.pem`：Mozilla CA 根证书 bundle（curl.se/ca/cacert.pem，
  2026-11-21 下载），供 curl 做 HTTPS 证书校验；校验失败时代码里已有 `-k`
  不安全重试兜底。

## 运行时

`JsSpiderService` 在首次启动 JS 执行器前把这两个文件释放到应用 support
目录（`curl/curl` + `curl/cacert.pem`，chmod 755），路径经 isolate 参数
传给 JS worker；worker 的 `_curl` 在 Android 上用
`/system/bin/linker64 <curl> --cacert <cacert.pem> …` 代替 `curl.exe`。

## 注意

- 只随 Android arm64 分发；其它 ABI 的设备上 JS 源仍会走系统 `curl`（若有）
  或失败，见 `js_spider_worker.dart` 的 `_curl` 回退逻辑。
- 更新 curl 版本时同步更新这里的版本号与 SHA-256。
