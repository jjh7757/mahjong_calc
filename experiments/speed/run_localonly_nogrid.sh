#!/usr/bin/env bash
# 자체 모델만(Gemini 없음) + 격자를 맞추지 않음(GridZones.initial, 280·745·173·713), 앱 흐름 측정(metrics 표 1-37).
# 먼저 launch.json: photos, visit-captures, recognizer-local-bcd, recognizer-local-am, recognizer-local-pm.
#   bash experiments/speed/run_localonly_nogrid.sh   → results/log_flow_ld_nogrid_{bcd,am,pm}.txt, 채점 flow_visit.py score
cd "$(dirname "$0")/../.."
F=/c/Users/jjh7757/flutter/bin/flutter
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
R=experiments/speed/results
INIT=280,745,173,713
BCD="k25=$INIT;k28=$INIT;k15=$INIT;k26=$INIT;k12=$INIT;k16=$INIT"
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_API_KEY=local --dart-define=SLEEP_S=5 --dart-define=LOCAL_ONLY=true)
VISIT=(--dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit --dart-define=REPEAT=1)
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8033 --dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2 "--dart-define=FIELD_GRIDS=$BCD" > "$R/log_flow_ld_nogrid_bcd.txt" 2>&1
echo "bcd 끝 $?"
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8034 "${VISIT[@]}" --dart-define=PHOTO_MAX=14 > "$R/log_flow_ld_nogrid_am.txt" 2>&1
echo "am 끝 $?"
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8035 "${VISIT[@]}" --dart-define=PHOTO_MIN=14 > "$R/log_flow_ld_nogrid_pm.txt" 2>&1
echo "pm 끝 $?"
