# WinBox → Android APK · 路线决策（Muse，2026-11-20）

对应任务：qq33200/muse-workbuddy-pool Issue #7（status:muse，priority:high）
交接仓库：qq33200/winbox-apk（WINBOX_APK_HANDOFF.md + source-samples/ 11 份样例，已读）
上游核查：2026-11-20 上午浅克隆 yagami-hue/MisaTV，HEAD bd7e8ea（2026-11-19），version 1.2.0+13。

## 1. 选哪条路线

**选：fork MisaTV（Flutter）→ 原生构建 arm64 APK → 逐项移植 Win-Box 定制。**

理由（已核对源码，不是只看 README）：
- MisaTV 是 Win-box 同作者的 Flutter 重写，业务规则一致：TVBox/CatVod 订阅、jar/js/py 三类蜘蛛、网盘、磁力、弹幕、直播 EPG、DLNA 都在 README 功能清单里打勾。
- MisaTV 自带完整 `android/` 工程和 `.github/workflows/build-android.yml`（workflow_dispatch / release 触发，Flutter 3.47.9 + JDK 17，`flutter build apk --release --target-platform android-arm64`，含 R8 后 CatVod 宿主类校验），可直接复用，见第 2 节。
- Win-box 是 Electron/TypeScript 桌面应用，没有 Android 壳；改 asar 套 WebView 或把 Windows exe 转换，等于重做壳且拿不到原生能力，不做。

许可证影响：
- MisaTV 是 **GPL-3.0**，fork 后整个衍生 APK 也必须 GPL-3.0，源码必须公开，README/NOTICE 里保留上游署名与许可证说明（Win-box MIT、MisaTV GPL-3.0、TVBox/CatVod 致谢）。不能闭源分发。
- Win-box 本体 MIT，引用无问题；我们自己的补丁同样按 GPL-3.0 开源。

## 2. 能否直接复用上游 Android workflow

**能，基本零改动先跑通原样构建。** 上游 workflow 已验证可用形态：
Flutter 3.47.9（锁定，与主线 build.yml 同工具链）、JDK 17 Temurin、AGP 9.1 下
flutter_inappwebview 的 proguard 补丁、R8 后校验 CatVod 宿主类、shell-real jar 可选恢复。
最小改动只在我们 fork 后：
- 包名/应用名、签名：上游 `android/app/build.gradle.kts` 用 `signingConfig = debug`，`applicationId = "com.kniephos.kniephos"`。正式分发前需用户确认签名策略（debug 签名先跑通，release 签名再定）。
- 不删 R8 校验步骤；CatVod 宿主类（Spider/SpiderApi/SpiderHostPlugin、OkHttp 3.12.x、Gson、Jsoup、fastjson）必须 keep。

## 3. P0 四项实现顺序与里程碑

顺序按依赖排，先壳后功能：

1. **M0 基线（已修正 2026-11-20 02:21，用户提醒）**：上游 Releases 已有现成 Android APK，不用先从 fork 构建。基线 = 上游 MisaTV 1.2.0 的 `MisaTV-android-arm64.apk`，102,089,245 字节（约 97MB），2026-11-18 发布，下载：https://github.com/yagami-hue/MisaTV/releases/download/v1.2.0/MisaTV-android-arm64.apk。先由 WorkBuddy/用户装到真机，实测 jar/js 源、file:// 加载、封面布局，确认 py 源是否如源码判断那样不可用。fork 的 Actions 构建留到开始改代码（M1–M3）时再跑。
2. **M1 py 源可加载（最难，见第 5 节风险）**：先做技术验证，再写代码。Android 端 py 蜘蛛目前是**缺失能力**，不是现成能力。
3. **M2 PikPak 分享解析（已实现 2026-11-20，本地待验收）**：`pikpak-mobile.py` 就是 Android 版（不用跟 winbox 版合流——它已经按 `os.name != 'nt'` 判断手机路径：封面直链、自动读 App 的 `TV/proxy.json` 代理、常见本地代理端口探测、直连兜底），纯标准库，Chaquopy 不用再装依赖。随包内置：`assets/python_sources/pikpak.py`（= pikpak-mobile.py 原样）+ `magnet.py`，pubspec 已声明；`py_spider.dart` 新增 `asset://` 加载——站点 api 填 `asset://python_sources/pikpak.py` 就行，离线可用、版本跟 APK 走，不用下载。本地验证：走 Chaquopy 同款 `winbox_spider.invoke` 调 homeContent / categoryContent（help、recent）都正常返回；init 时 ext 里填了 proxy 就跳过自动探测。注意：脚本里 127.0.0.1:9978 的 import-csv / galleryopen 两个调用是桌面专属，在手机上会静默失败（已 try/except），不影响播放；magnet.py 要 Win-Box 内置 aria2 + /bt 中继，Android 上 assets/aria2 只有 README、没有引擎，磁力播放暂不可用，等 MisaTV 的 aria2 方案再定。搜索范围过滤（patch-search-scope.py 的 pikpakLink 判断）尚未移植，算 M2 剩余小项。
4. **M3 横封面 16:9**：Flutter 渲染层改，不是复用 CSS。上游海报卡默认是 2/3（`lib/ui/immersive/immersive_widgets.dart:641`、`lib/ui/pages/detail_page.dart:2572` 的 `AspectRatio(aspectRatio: 2/3)`，媒体库 `childAspectRatio: 0.60`），改成 16/9、卡片约 200px；封面自适应合成（640×360，完整海报居中+两侧模糊）用 Dart 图像库/原生插件重做，不搬 Windows 的 crop_service.py + 9917 端口方案。

P1 跟进：py 下载保 tk（核对 MisaTV 自身订阅 URL query 是否完整保留，若有同款 bug 按 `winbox_patch.py` 锚点在 Dart 侧修）、磁力解析（`magnet.py` 的 infoHash 计算，确认 Android 上 aria2c 是否随包/可下载）、封面自适应。

## 4. P2 语音字幕是否在本次范围

**不在本次范围，单列后续 Issue。** Windows 方案依赖 mpv 命名管道 + 常驻 Python + ffmpeg + sherpa-onnx/SenseVoice（228MB），Android 无 mpv IPC，需在 Flutter 播放层接音频帧或改云端 ASR，先做可行性评估再决定。先记为后续 Issue，不阻塞 P0。

## 5. 关键风险（本次核查的新发现）

**Android 端 py 蜘蛛目前不可用，是 P0 最大风险点。**
- `lib/services/py_spider/py_spider.dart:344` 写死找 `python.exe`，用 `Process.run` 执行；`lib/services/runtime_extension.dart` 明确写着 Python/JVM/加固壳运行时“只在 Windows 桌面端提供”（`supported` 要求 `TargetPlatform.windows`）。
- `lib/services/py_spider/py_runtime.dart` 的嵌入式 Python 是 Windows amd64 专属（python-3.11.6-embed-amd64.zip + win_amd64 wheel），Android 上没有对应运行时，仓库里也没有 Chaquopy。
- 可选方案（已定，2026-11-20 实施中）：**Chaquopy 17.2 + CPython 3.12**（支持 AGP 7.3–9.5，与 MisaTV 的 AGP 9.1.0 兼容；Chaquopy 12.0.1 起免费开源）。实现在 fork main 的 winbox-p0 一批改动里：`android/app/src/main/python/winbox_spider.py`（复用 runner.py 的调用语义，函数式入口）+ `base/spider.py` 随包、`PySpiderPlugin.kt`（MethodChannel `com.kniephos.kniephos/py_spider`）+ `py_spider.dart` 的 Android 分支（走 Chaquopy，不找 python.exe）。限制：常驻取流 `--hold` 暂不支持（Chaquopy 内无进程概念），指向脚本本机取流服务的播放地址暂时播不了，直链不受影响。jar 蜘蛛 Android 已有 DexClassLoader 路径，JS 蜘蛛是 Dart 层，问题小。
- 其余：jar 蜘蛛 Android 已有 `jar_spider_android.dart`（ART/DexClassLoader），JS 蜘蛛 QuickJS 是 Dart 层，跨平台问题小。

## 6. 明确不移植

`/share` 路由、share-helper（8788）、py-runtime 网关（9977）、Windows 开机自启 VBS、asar 守护脚本。Windows 端“本地端口 + 常驻服务 + 自启守护”的做法 Android 端不要照搬，尽量做成 App 内组件或可配置地址。

## 7. 兼容性矩阵（草稿，M0 后更新为实测状态）

| Win-Box 功能 | APK 状态（当前判断） |
|---|---|
| Flutter 壳 / 订阅导入 / 分类详情 / 播放 | 原样构建后可用（待 M0 验证） |
| jar 蜘蛛 | 可用（Android 已有 DexClassLoader 路径） |
| js 蜘蛛 | 可用（QuickJS，Dart 层） |
| py 蜘蛛（pikpak.py / magnet.py 等） | **不可用，需新做 Android Python 运行时（M1）** |
| PikPak 分享解析 / 搜索范围过滤 | 待移植（M2） |
| 横封面 16:9 / 封面自适应 | 待移植（M3 / P1） |
| py 下载保 tk | 待核对（P1） |
| 磁力 BT | 待确认 aria2c（P1） |
| 实时语音字幕 | 不做，P2 后续 Issue |
| /share、share-helper、py 网关、自启守护 | 不移植 |

## 8. 需要 WorkBuddy / 用户做的事（Muse 做不了）

- **Fork MisaTV 到 qq33200 名下**：Muse 的 GitHub App token 不能创建仓库/fork（2026-11-19 创建仓库已验证 403 “Resource not accessible by integration”），必须由 WorkBuddy 或用户在 GitHub 上 fork yagami-hue/MisaTV，fork 名建议 `qq33200/MisaTV`（或 `qq33200/winbox-android`），保持公开、GPL-3.0。
- fork 后在 pool Issue #7 评论贴 fork 地址，Muse 再把补丁分支推上去并触发 Actions 构建。
- 真机验收：Muse 无 Android 设备，APK 只能标“仅构建通过”，真机由用户/WorkBuddy 验收。
- 签名策略：debug 签名先跑通，正式 release 签名等用户确认。

## 9. 用户规则（已遵守）

- 不主动抓取任何订阅 URL 或 py URL 做验证（会触发门禁封号）；本次只做静态代码核查与本地克隆。
- Issue、代码、README、提交记录里不写任何 PAT / API Key / Cookie / 订阅 token。
- 直接推进到 APK 产物或明确阻塞点，不以“建议用现成壳”作最终结论。

## 10. 当前状态（2026-11-20 13:32，本地构建，待用户/WorkBuddy 真机验收）

**最新 APK：WinBox-1.2.0-arm64.apk，156 MB，MD5 5ba3e5ac6c8ec59a57bd03c270001fe7，包名 com.winbox，versionCode 14，versionName 1.2.0。** 本地构建（Flutter 3.47.9 + JDK 17 + Chaquopy 3.11），未走 Actions。APK 太大（>100MB）不能直接 git push，见第 11 节。

已实现（都在本地构建里，待验收后统一推 fork main）：
- M1 Chaquopy：py 源可加载（winbox_spider.py + PySpiderPlugin.kt + py_spider.dart Android 分支）；`--hold` 取流暂不支持。
- M2 PikPak + magnet：assets/python_sources/pikpak.py（= pikpak-mobile.py）+ magnet.py；py_spider.dart `asset://` 加载；搜索范围过滤（粘贴 PikPak 链接时只搜 PikPak 源）。
- M3 横封面 16:9：首页/详情/媒体库海报改 16/9，卡片约 200px。
- 包名改 WinBox：com.winbox，MethodChannel com.winbox/py_spider、com.winbox/spider，应用名 WinBox，MainActivity 也加了 android:label="WinBox"（最近任务显示 WinBox）。
- 内置源：59 个 py 源（PikPak + 磁力 + 57 个 zzzypro 站）随包，首次启动自动生成「WinBox 内置源」订阅（UU.py 未内置，只留 UU_fixed）。
- 换源 bug：winbox_spider.py 的蜘蛛实例缓存键改成（脚本路径，类名，ext），之前只按类名缓存导致所有源都跑第一个（PikPak）。
- 磁力 aria2：官方 aria2 1.37.0 Android arm64 随包（assets/aria2/aria2c-android-arm64），Android 10+ 的 W^X 限制改走 /system/bin/linker64 启动。HTTPS tracker 暂无 CA 证书包。
- 下载管理：416 断点续传失败改从头重下（最多 2 次），流中断自动续传（2s/4s/6s 退避，最多 3 次）；下载完成可点开播/打开文件夹（原生 FileProvider + SystemActionsPlugin，xdg-open 在 Android 上不存在）。
- CSV 导入：LocalRelay 加 /import-csv，弹系统文件选择器（SAF）；粘贴多链接批量识别导入；导入的标题问题已修（见下）。
- 标题修复：粘贴导入时把解析出的真实标题一起存进 paste，CSV 列表打开时给没标题的旧条目并发补真实标题并写回（_fill_csv_names，6 秒预算）。
- 备份导出修复：file_selector 的保存对话框在 Android 上未实现，改走原生 MediaStore 直接写进系统 Download 目录（不用存储权限，卸载后文件还在）。
- 签名：持久 release keystore（~/winbox-release.keystore，alias winbox，有效期到 2051，证书 SHA-256 72d8b10e149845ac58334ced7b52a54916dd9dd0e1902b648392dfcfb75feb95），key.properties + release signingConfig（无 key.properties 时退回 debug）。**注意：之前一直用临时 debug 签名，机器重启就丢，所以这次必须先卸载一次旧包再装新包；装上这个包之后，以后更新都能直接覆盖。** 卸载前先在设置里导出备份（订阅/收藏/历史能保住；PikPak CSV 列表备份里没有，装完需重新导入原文件或重新粘贴链接）。

待验收（真机，用户/WorkBuddy）：
- 安装打开；PikPak 源打开、分享链接搜索、播放；首页封面横 16:9；换源；磁力播放；大文件下载不断线、下载完能打开；CSV 导入弹文件选择器、粘贴导入标题完整；备份导出能在 Download 里生成文件；切后台显示 WinBox；卸载重装后以后更新可覆盖。

已知限制：
- `_invokeHold` 在 Android 上退化为单次调用，脚本本机取流地址暂播不了，直链不受影响。
- aria2 的 HTTPS tracker 缺 CA 证书包；磁力主要靠 DHT + UDP/HTTP tracker，一般不受影响。
- 构建环境在 Muse 的 VM 里（$HOME 持久，/root、/usr 不持久；本地 Maven 镜像 127.0.0.1:18080；服务重启后需重启镜像再构建）。

## 11. 产物与交接方式

- APK（156 MB）无法 git push（GitHub 单文件上限 100MB），放在用户 Google Drive，链接见 pool Issue #7 最新评论。
- 本文档（docs/WINBOX-ROUTE.md）已推 fork main；本地全部源码改动待用户验收后统一推 fork main（再 revert 本地构建用的镜像/代理等临时改动）。
- 验收通过后：同步 Issue #7（按 PROTOCOL.md 改 label），再推代码。
