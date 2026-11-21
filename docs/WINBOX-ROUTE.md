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
3. **M2 PikPak 分享解析**：把 `source-samples/pikpak-mobile.py` 与 `pikpak-winbox.py` 合流为一份，适配 Android 存储权限（`/sdcard/Download/` 的 `file://` 加载，上游 `lib/core/utils/file_url.dart` 已有 file:// 互转）与代理设置；搜索范围过滤按 `patch-search-scope.py` 的 `pikpakLink` 判断移植。
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
