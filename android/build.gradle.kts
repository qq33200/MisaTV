allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}

// WinBox: AGP 9.1 移除了 proguard-android.txt，flutter_inappwebview 的旧
// build.gradle 仍引用它。CI 的 pub-cache 路径和 workflow 里的 $HOME/.pub-cache
// 不一致，sed 补丁会漏；这里在插件被评估前直接改掉，保证任何构建环境都能过。
gradle.beforeProject {
    if (name.startsWith("flutter_inappwebview")) {
        val buildFile = file("build.gradle")
        if (buildFile.exists()) {
            val text = buildFile.readText()
            val fixed = text.replace(
                "getDefaultProguardFile('proguard-android.txt')",
                "getDefaultProguardFile('proguard-android-optimize.txt')"
            )
            if (fixed != text) {
                buildFile.writeText(fixed)
                println("WinBox: patched proguard file in ${path}")
            }
        }
    }
}
