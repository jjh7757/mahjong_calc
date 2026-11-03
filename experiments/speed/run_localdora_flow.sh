#!/usr/bin/env bash
# 자체 모델 표시패 찾기(/v2/localdora) 앱 흐름 측정, 로컬 서버(metrics 표 1-36). 세트마다 그 사진을 학습하지 않은 나눔 모델 서버로.
# 먼저 launch.json: photos, visit-captures, recognizer-local-bcd, recognizer-local-am, recognizer-local-pm.
#   TAG=_dora bash experiments/speed/run_localdora_flow.sh only am pm   → 로그 이름에 TAG 가 붙는다(판 중 표시패 비교, 표 1-53)
#   bash experiments/speed/run_localdora_flow.sh on|off   → results/log_flow_ld_<on|off>_{bcd,am,pm}.txt, 채점 flow_visit.py score
cd "$(dirname "$0")/../.."
F=/c/Users/jjh7757/flutter/bin/flutter
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
R=experiments/speed/results
L=$([ "$1" = on ] && echo true || echo false)
EXTRA=()
[ "$1" = only ] && EXTRA=(--dart-define=LOCAL_ONLY=true)  # only = 자체 모델만, Gemini 없음(표 1-37)
[ "$1" = sticks ] && EXTRA=(--dart-define=LOCAL_ONLY=true --dart-define=GEMINI_STICKS=true)  # sticks = 자체 모델 + Gemini 리치봉(표 1-48)
GRIDS=$(python -I -X utf8 experiments/speed/flow_visit.py grids)
RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
DORA=$([ "$DORA_OFF" = 1 ] && echo "" || python -I -X utf8 experiments/speed/flow_visit.py dora)  # DORA_OFF=1 이면 판 중 표시패 없이(전)
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_API_KEY=local --dart-define=SLEEP_S=20 "--dart-define=LOCAL_DORA=$L" "${EXTRA[@]}")
VISIT=(--dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit --dart-define=REPEAT=1 "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI" "--dart-define=TRACKED_DORA=$DORA")
PARTS=${2:-bcd am pm}
AM_URL=${AM_URL:-http://127.0.0.1:8034}  # 다른 세션이 같은 포트를 쓰면 AM_URL/PM_URL 로 바꾼다(2026-11-03)
PM_URL=${PM_URL:-http://127.0.0.1:8035}  # 둘째 인자로 세트만 고른다(예: only pm)
if [[ " $PARTS " == *" bcd "* ]]; then
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8033 --dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2 > "$R/log_flow_ld_$1${TAG}_bcd.txt" 2>&1
  echo "bcd 끝 $?"
fi
if [[ " $PARTS " == *" am "* ]]; then
  "$F" "${COMMON[@]}" "--dart-define=RECOGNIZER_URL=$AM_URL" "${VISIT[@]}" --dart-define=PHOTO_MAX=14 > "$R/log_flow_ld_$1${TAG}_am.txt" 2>&1
  echo "am 끝 $?"
fi
if [[ " $PARTS " == *" pm "* ]]; then
  "$F" "${COMMON[@]}" "--dart-define=RECOGNIZER_URL=$PM_URL" "${VISIT[@]}" --dart-define=PHOTO_MIN=14 > "$R/log_flow_ld_$1${TAG}_pm.txt" 2>&1
  echo "pm 끝 $?"
fi
