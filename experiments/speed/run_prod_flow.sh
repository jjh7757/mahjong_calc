#!/usr/bin/env bash
# 운영 서버 단독 앱 흐름(B·C·D 12회 + 매장 25회), 배포 뒤 확인 측정. 표 1-16 과 같은 방식. 먼저 launch.json: photos, visit-captures.
#   LOCAL_ONLY=true bash ... = 자체 모델만(앱 기본과 같음), ROLES=1 을 더하면 /v2/localroles(지금 운영 앱)
#   bash experiments/speed/run_prod_flow.sh <로그 이름>   → results/log_flow_<이름>_{bcd,visit}.txt, 채점 flow_visit.py score
cd "$(dirname "$0")/../.."
F=/c/Users/jjh7757/flutter/bin/flutter
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
R=experiments/speed/results
GRIDS=$(python -I -X utf8 experiments/speed/flow_visit.py grids)
RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_URL=https://mahjong.ai-agent-develop.cloud "--dart-define=RECOGNIZER_API_KEY=$(cat .recognizer_key)" --dart-define=SLEEP_S=20 "--dart-define=LOCAL_ONLY=${LOCAL_ONLY:-false}")
[ -n "$ROLES" ] && COMMON+=(--dart-define=ROLES=true)  # ROLES=1 이면 자리 판독을 /v2/localroles 로(운영 앱 mount_screen 과 같음)
"$F" "${COMMON[@]}" --dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2 > "$R/log_flow_$1_bcd.txt" 2>&1
echo "bcd 끝 $?"
"$F" "${COMMON[@]}" --dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit --dart-define=REPEAT=1 "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI" > "$R/log_flow_$1_visit.txt" 2>&1
echo "visit 끝 $?"
