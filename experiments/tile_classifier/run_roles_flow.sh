#!/usr/bin/env bash
# 자체 모델 앱 흐름을 자리 판독 경로만 바꿔 같은 순간에 잰다(metrics 표 1-61). plain = /v2/localseat(자리 크롭, 규칙), roles = /v2/localroles(사진 전체 + 격자, 역할 모델).
# 먼저 launch.json: photos, visit-captures, recognizer-local-bcd, recognizer-local-am, recognizer-local-pm. 격자는 저장 격자.
#   bash experiments/tile_classifier/run_roles_flow.sh plain roles   → experiments/speed/results/log_flow_roles_<방식>_{bcd,am,pm}.txt
#   채점: python -I -X utf8 experiments/speed/flow_visit.py score experiments/speed/results/log_flow_roles_<방식>_*.txt
cd "$(dirname "$0")/../.."
F=/c/Users/jjh7757/flutter/bin/flutter
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
R=experiments/speed/results
RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
GRIDS=$(python -X utf8 experiments/zone_points/zones.py grids saved 2>/dev/null)
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_API_KEY=local --dart-define=SLEEP_S=5 --dart-define=LOCAL_ONLY=true)
for MODE in "$@"; do
  EXTRA=()
  [ "$MODE" = roles ] && EXTRA=(--dart-define=ROLES=true)
  VISIT=(--dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit --dart-define=REPEAT=1 "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI")
  BCD=(--dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2)
  "$F" "${COMMON[@]}" "${EXTRA[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8033 "${BCD[@]}" > "$R/log_flow_roles_${MODE}_bcd.txt" 2>&1
  echo "$MODE bcd 끝 $?"
  "$F" "${COMMON[@]}" "${EXTRA[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8034 "${VISIT[@]}" --dart-define=PHOTO_MAX=14 > "$R/log_flow_roles_${MODE}_am.txt" 2>&1
  echo "$MODE am 끝 $?"
  "$F" "${COMMON[@]}" "${EXTRA[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8035 "${VISIT[@]}" --dart-define=PHOTO_MIN=14 > "$R/log_flow_roles_${MODE}_pm.txt" 2>&1
  echo "$MODE pm 끝 $?"
done
