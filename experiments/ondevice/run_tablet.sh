#!/usr/bin/env bash
# 태블릿(adb 로 붙은 기기)에서 ONNX 시험. 앱은 건드리지 않고 /data/local/tmp/ort_bench 만 쓴다.
#   bash run_tablet.sh [push]   — push 면 실행 파일·라이브러리·모델·입력을 먼저 올림
# 결과는 results/tablet_<시각>.txt 에 RESULT 줄로.
set -e
cd "$(dirname "$0")"
export MSYS_NO_PATHCONV=1
A=/c/Users/jjh7757/dev/android-sdk/platform-tools/adb.exe
D=/data/local/tmp/ort_bench
ASSETS=C:/Users/jjh7757/dev/mahjong-recognizer/app/assets
RUNS=${RUNS:-11}
if [ "$1" = push ]; then
  "$A" shell mkdir -p $D
  "$A" push build/ort_bench ort/aar/jni/arm64-v8a/libonnxruntime.so $D/ >/dev/null
  for f in build/data/*; do "$A" push "$f" $D/ >/dev/null; done
  for m in $(awk '{print $2}' build/data/cases.txt | sort -u); do "$A" push "$ASSETS/$m" $D/ >/dev/null; done
  "$A" shell chmod 755 $D/ort_bench
fi
mkdir -p results
out=results/tablet_$(date +%m%d_%H%M).txt
{
  echo "# $("$A" shell getprop ro.product.model) $("$A" shell getprop ro.soc.model) $(date '+%F %T')"
  "$A" shell "dumpsys battery | grep -E '^  (level|temperature|AC powered)'" | tr -s ' ' | tr '\n' ' '; echo
  while read -r name model inname dims; do
    [ -z "$name" ] && continue
    for th in ${THREADS:-1 2 4}; do
      echo "$name $("$A" shell "cd $D && LD_LIBRARY_PATH=. ./ort_bench $model $name.in.bin $inname $name.ref.bin $th $RUNS $dims" </dev/null | grep RESULT)"
    done
  done < build/data/cases.txt
} | tee "$out"
