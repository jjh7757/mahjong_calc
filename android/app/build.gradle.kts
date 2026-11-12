plugins {
    id("com.android.application")
    // 기기 판독 실험(exp/on-device-read): Chaquopy 로 서버 자체 판독 코드를 앱 안에서(OnDeviceReader.kt·src/main/python/ondevice.py)
    id("com.chaquo.python")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "dev.jjh.mahjong_calc"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "dev.jjh.mahjong_calc"
        // 기기 판독 실험 브랜치는 사본 앱으로 깐다(2026-11-11 사용자 "기존 앱은 그대로 두고 사본 앱으로"): 패키지 이름·앱 이름이 달라
        // 원래 앱(dev.jjh.mahjong_calc)과 나란히 설치되고 데이터도 따로다.
        applicationIdSuffix = ".ondevice"
        manifestPlaceholders["appLabel"] = "마작 실험"
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
        // Chaquopy 는 ABI 를 정해야 한다. 태블릿·폰 모두 arm64.
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
            // 기기 판독 실험: Python 이 부르는 OrtBridge 를 R8 이 지우지 않게
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

// ---- 기기 판독 실험(exp/on-device-read) ----
// 서버 저장소(mahjong-recognizer)의 app/*.py 와 운영 모델을 빌드 때 복사해 Python 소스로 넣는다(앱 저장소엔 커밋하지 않음).
// 다른 위치면 -PrecognizerRepo=<경로>. cv2·onnxruntime 은 src/main/python 의 흉내 모듈(서버 판 대신).
val recognizerRepo = file(providers.gradleProperty("recognizerRepo").getOrElse("${rootDir}/../../mahjong-recognizer"))
val ondeviceServerDir = layout.buildDirectory.dir("ondevice_server")
val syncServerPy by tasks.registering(Sync::class) {
    from(recognizerRepo.resolve("app")) {
        include("*.py")
        exclude("main.py")
        include(
            "assets/tile-yolo26n.onnx", "assets/tile-obb-r8.onnx", "assets/tile-cls-mnv3s-v3.onnx",
            "assets/tile-cls-alt-v3.onnx", "assets/tile-roles-v3r15d.onnx", "assets/table_frame_zones.json",
        )
    }
    // 역할 + 주인 모델 D(실험 5b, 2026-11-12, docs/role_owner_plan_1111.md): 겹쳐 보기 role=d 경로가 서버 assets 옆에서 찾는다.
    // 파일은 role_owner_export.py 가 만든 것(.gitignore 대상 — 이 PC 로컬 빌드 전용). 없으면 그냥 빠지고 role=d 요청만 실패한다.
    from(file("${rootDir}/../experiments/tile_classifier/server_bench/models")) {
        include("tile-roles-owner-d.onnx")
        into("assets")
    }
    into(ondeviceServerDir.map { it.dir("app") })
}
tasks.named("preBuild") { dependsOn(syncServerPy) }
tasks.matching { it.name.endsWith("PythonSources") }.configureEach { dependsOn(syncServerPy) }

chaquopy {
    defaultConfig {
        version = "3.13"
        buildPython(providers.gradleProperty("buildPython").getOrElse("C:/Users/jjh7757/.pyenv/pyenv-win/versions/3.13.13/python.exe"))
        pip {
            install("numpy==1.26.2")
            install("pillow==11.0.0")
        }
        // 서버 코드가 Path(__file__).parent / "assets" 로 모델을 연다 → 파일로 풀어 둔다.
        extractPackages("app")
    }
    sourceSets {
        getByName("main") {
            srcDir(ondeviceServerDir)
        }
    }
}

dependencies {
    // 카메라 헤드 전용 카메라(HeadCamera.kt): camera 플러그인(camera_android_camerax)과 같은 CameraX 판.
    val cameraxVersion = "1.6.2"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    // 기기 판독 실험: OrtBridge.kt(서버와 같은 1.29.0)
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.29.0")
}
