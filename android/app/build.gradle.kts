import java.io.File
import java.io.FileInputStream
import java.util.Properties

// WinBox: 找 runner 上的 Python 3.11。Chaquopy 的 lxml/pycryptodome
// Android wheel 目前只覆盖到 3.11；3.12+ 会在 pip 阶段报无可用版本。
fun findBuildPython(): String? {
    // 返回值会打印在 CI 配置日志里，便于核对实际解释器
    for (ver in listOf("3.11")) {
        for (p in listOf("/usr/bin/python$ver", "/usr/local/bin/python$ver")) {
            val f = File(p)
            if (f.canExecute()) return f.absolutePath
        }
    }
    val root = File("/opt/hostedtoolcache/Python")
    if (root.isDirectory) {
        val dirs: List<File> = root.listFiles()?.sortedByDescending { it.name } ?: emptyList()
        for (dir in dirs) {
            if (!dir.name.startsWith("3.11")) continue
            for (rel in listOf("x64/bin/python3", "x64/bin/python3.11")) {
                val f = File(dir, rel)
                if (f.canExecute()) return f.absolutePath
            }
        }
    }
    return null
}


plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
    // WinBox M1：Chaquopy，把 CPython 3.12 打进 APK 供 py 蜘蛛使用。
    id("com.chaquo.python")
}

val winboxBuildPython = findBuildPython()
println("WinBox buildPython = $winboxBuildPython")

android {
    namespace = "com.winbox"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    // Release 签名：读 android/key.properties（已进 .gitignore，不会进仓库）。
    // key.properties 里的 storeFile 指向 $HOME 下的持久 keystore，机器重启也不会丢，
    // 所以以后每次打包都是同一个签名，覆盖安装不再要求卸载。
    // key.properties 不存在时（比如别人直接 clone 下来编译）退回 debug 签名。
    val keystoreProperties = Properties()
    val keystorePropertiesFile = rootProject.file("key.properties")
    if (keystorePropertiesFile.exists()) {
        keystoreProperties.load(FileInputStream(keystorePropertiesFile))
    }

    signingConfigs {
        create("release") {
            if (keystorePropertiesFile.exists()) {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.winbox"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        // Chaquopy 的 CPython 是原生组件：ABI 必须在 android.defaultConfig.ndk 里限制。
        ndk {
            // Flutter 在 debug variant 会先塞入 armeabi-v7a/arm64-v8a/x86_64；
            // 只 += 会保留 32 位，Chaquopy 3.12 不接受 armeabi-v7a。先清空再指定。
            abiFilters.clear()
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            // 有 key.properties 就用持久 release 签名，否则退回 debug 签名。
            signingConfig = if (keystorePropertiesFile.exists()) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
            // Flutter 3.47 的 release 构建会跑 R8。CatVod 宿主类只被外部 jar/壳 dex
            // 反射引用，不 keep 会被裁掉或混淆成短名，导致加固壳 ClassNotFoundException。
            isMinifyEnabled = true
            // 资源裁剪：移除未被引用的 Android 资源（主要是启动图标等少量资源），
            // 在不砍 ABI 的前提下略微减小 APK。CatVod/Flutter 资源不受影响。
            isShrinkResources = true
            proguardFiles("proguard-rules.pro")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

dependencies {
    // CatVod / wex 加固壳解密出的「真实蜘蛛」运行在宿主 ClassLoader 的 parent 链上，
    // 会直接引用 TVBox 宿主自带的 Java 库。Flutter 侧一个都没有，缺了就在
    // homeContent 抛 `NoClassDefFoundError: Failed resolution of: Lokhttp3/Request$Builder;`。
    // 这些类宿主代码本身不引用，只被外部 dex 反射/链接使用，因此 proguard-rules.pro
    // 里必须一并 -keep，否则 R8 会把它们全裁掉。
    //
    // 固定 OkHttp 3.12.x：这批壳是按 TVBox 的 OkHttp3 3.x API 编译的
    // （RequestBody.create(MediaType, String) 等），4.x 改了签名会 NoSuchMethodError。
    implementation("com.squareup.okhttp3:okhttp:3.12.13")   // 传递依赖 okio 1.17.x
    implementation("com.google.code.gson:gson:2.10.1")
    implementation("org.jsoup:jsoup:1.16.1")
    implementation("com.alibaba:fastjson:1.2.83")
}

flutter {
    source = "../.."
}

// WinBox M1：Android 端 py 蜘蛛的 CPython 运行时（Chaquopy 17.2）。
// Python 3.11（64 位，与桌面端 3.11 的 py 源兼容：标准库 + requests 族）。
// pip 只装 py 源实际用到的纯 Python / 已有 Android wheel 的包；lxml、
// pycryptodome 在 Chaquopy 仓库有 Android wheel，requests 族为纯 Python。
chaquopy {
    defaultConfig {
        // 用构建机自带 Python 3.12（ubuntu-latest 默认即有），
        // 配合上面的 abiFilters.clear() 只打 arm64，避免 3.12 不支持 32 位 ABI。
        version = "3.14"
        // runner 的 python3 是 3.14，Chaquopy 17.2 支持到 3.14。
        pip {
            install("requests")
            install("urllib3")
            install("certifi")
            install("charset_normalizer")
            install("idna")
            install("beautifulsoup4")
            install("wheels/lxml-5.3.0-0-cp311-cp311-android_24_arm64_v8a.whl")
            install("pycryptodome")
        }
    }}
