#!/usr/bin/env bash
# 앱 크롭 줄이기(perf/local-crops) 전·후 앱 흐름을 같은 서버로 연달아 잰다(metrics 표 1-83).
# 빌드는 $WT(기본 이 폴더), 격자·리치 인자·로그는 이 폴더 것. 서버 포트는 U_BCD·U_AM·U_PM, 더 넘길 인자는 EXTRA="--dart-define=…".
# 먼저 launch.json: photos(8040), visit-captures(8042), recognizer-r8rot-{bcd,am,pm}(8033~8035).
#   bash experiments/speed/run_crops_compare.sh <TAG>   → experiments/speed/results/log_flow_zone_saved_<TAG>_{bcd,am,pm}.txt
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
WT="${WT:-$MAIN}"  # 다른 폴더에서 빌드하려면 WT=<worktree>
U_BCD=${U_BCD:-8033}; U_AM=${U_AM:-8034}; U_PM=${U_PM:-8035}  # 판독 서버 포트
EXTRA=(${EXTRA:-})  # 더 넘길 --dart-define 들
TAG=$1
F=/c/Users/jjh7757/flutter/bin/flutter
R="$MAIN/experiments/speed/results"
cd "$MAIN"
RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
GRIDS=$(python -X utf8 experiments/zone_points/zones.py grids saved 2>/dev/null)
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_API_KEY=local --dart-define=SLEEP_S=5 --dart-define=LOCAL_ONLY=true --dart-define=ROLES=true "${EXTRA[@]}")
VISIT=(--dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit --dart-define=REPEAT=1 "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI")
BCD=(--dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2)
cd "$WT"
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_BCD "${BCD[@]}" > "$R/log_flow_zone_saved_${TAG}_bcd.txt" 2>&1
echo "$TAG bcd 끝 $?"
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_AM "${VISIT[@]}" --dart-define=PHOTO_MAX=14 > "$R/log_flow_zone_saved_${TAG}_am.txt" 2>&1
echo "$TAG am 끝 $?"
"$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_PM "${VISIT[@]}" --dart-define=PHOTO_MIN=14 > "$R/log_flow_zone_saved_${TAG}_pm.txt" 2>&1
echo "$TAG pm 끝 $?"
