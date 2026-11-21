pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            file("local.properties").inputStream().use { properties.load(it) }
            val flutterSdkPath = properties.getProperty("flutter.sdk")
            require(flutterSdkPath != null) { "flutter.sdk not set in local.properties" }
            flutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "9.1.0" apply false
    id("org.jetbrains.kotlin.android") version "2.4.0" apply false
    // WinBox M1：Chaquopy 17.2（支持 AGP 7.3–9.5），Android 端 py 蜘蛛运行在
    // 嵌入式 CPython 3.11 上；构建机需有同版本 Python（见 fork 的 build-android.yml）。
    id("com.chaquo.python") version "17.2.0" apply false
}

include(":app")
