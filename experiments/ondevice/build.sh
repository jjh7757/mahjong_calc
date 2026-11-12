#!/usr/bin/env bash
# ort_bench.c 를 NDK 로 arm64 안드로이드용으로 빌드한다. ort/aar 에 onnxruntime-android-1.29.0.aar 를 풀어 둔 상태여야 한다
# (curl -o ort/ort.aar https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/1.29.0/onnxruntime-android-1.29.0.aar && unzip ort/ort.aar -d ort/aar).
set -e
cd "$(dirname "$0")"
NDK=/c/Users/jjh7757/dev/android-sdk/ndk/28.2.13676358
CC=$NDK/toolchains/llvm/prebuilt/windows-x86_64/bin/aarch64-linux-android29-clang.cmd
mkdir -p build
"$CC" -O2 -o build/ort_bench ort_bench.c -Iort/aar/headers -Lort/aar/jni/arm64-v8a -lonnxruntime -lm
"$CC" -O2 -o build/ort_daemon ort_daemon.c -Iort/aar/headers -Lort/aar/jni/arm64-v8a -lonnxruntime -lm
echo "build/ort_bench build/ort_daemon"
