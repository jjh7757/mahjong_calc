#!/usr/bin/env bash
# 자체 모델 표시패 찾기(/v2/localdora) 앱 흐름 측정, 로컬 서버(metrics 표 1-36). 세트마다 그 사진을 학습하지 않은 나눔 모델 서버로.
# 먼저 launch.json: photos, visit-captures, recognizer-local-bcd, recognizer-local-am, recognizer-local-pm.
#   bash experiments/speed/run_localdora_flow.sh on|off   → results/log_flow_ld_<on|off>_{bcd,am,pm}.txt, 채점 flow_visit.py score
cd "$(dirname "$0")/../.."
F=/c/Users/jjh7757/flutter/bin/flutter
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
R=experiments/speed/results
L=$([ "$1" = on ] && echo true || echo false)
EXTRA=()
[ "$1" = only ] && EXTRA=(--dart-define=LOCAL_ONLY=true)  # only = 자체 모델만, Gemini 없음(표 1-37)
GRIDS=$(python -I -X utf8 experiments/speed/flow_visit.py grids)
RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_API_KEY=local --dart-define=SLEEP_S=20 "--dart-define=LOCAL_DORA=$L" "${EXTRA[@]}")
VISIT=(--dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit --dart-define=REPEAT=1 "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI")
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8033 --dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2 > "$R/log_flow_ld_$1_bcd.txt" 2>&1
echo "bcd 끝 $?"
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8034 "${VISIT[@]}" --dart-define=PHOTO_MAX=14 > "$R/log_flow_ld_$1_am.txt" 2>&1
echo "am 끝 $?"
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8035 "${VISIT[@]}" --dart-define=PHOTO_MIN=14 > "$R/log_flow_ld_$1_pm.txt" 2>&1
echo "pm 끝 $?"
