#!/usr/bin/env bash
# 격자 출처만 바꿔 자체 모델 앱 흐름을 잰다(metrics 표 1-40). saved = 저장 격자, median = 색 판독 설치별 중앙값, single = 사진 한 장 색 판독, initial = 맞추지 않은 기본 격자.
# 먼저 launch.json: photos, visit-captures, recognizer-local-bcd, recognizer-local-am, recognizer-local-pm.
#   bash experiments/zone_points/run_flow.sh saved median single initial   → experiments/speed/results/log_flow_zone_<방식>_{bcd,am,pm}.txt, 채점 flow_visit.py score
#   TAG=_1103 bash … saved dart tile   → log_flow_zone_<방식>_1103_*.txt (앞 표의 로그를 덮어쓰지 않게). tile = 패 상자 격자(tile_grid.py)
cd "$(dirname "$0")/../.."
F=/c/Users/jjh7757/flutter/bin/flutter
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
R=experiments/speed/results
RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_API_KEY=local --dart-define=SLEEP_S=5 --dart-define=LOCAL_ONLY=true)
for MODE in "$@"; do
  GRIDS=$(python -X utf8 experiments/zone_points/zones.py grids "$MODE" 2>/dev/null)
  VISIT=(--dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit --dart-define=REPEAT=1 "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI")
  BCD=(--dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2)
  [ "$MODE" = saved ] || BCD+=("--dart-define=FIELD_GRIDS=$GRIDS")  # 저장 격자의 B·C·D 는 장면 격자(수동) 그대로
  if [ -z "$SKIP_BCD" ]; then  # SKIP_BCD=1 이면 매장만(서버가 꺼져 매장만 다시 잴 때)
    "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8033 "${BCD[@]}" > "$R/log_flow_zone_${MODE}${TAG}_bcd.txt" 2>&1
    echo "$MODE bcd 끝 $?"
  fi
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8034 "${VISIT[@]}" --dart-define=PHOTO_MAX=14 > "$R/log_flow_zone_${MODE}${TAG}_am.txt" 2>&1
  echo "$MODE am 끝 $?"
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:8035 "${VISIT[@]}" --dart-define=PHOTO_MIN=14 > "$R/log_flow_zone_${MODE}${TAG}_pm.txt" 2>&1
  echo "$MODE pm 끝 $?"
done
