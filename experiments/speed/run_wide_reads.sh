#!/usr/bin/env bash
# /v2/seatwide 3번 읽기("main", 8030) vs 1번 읽기("alt", 8031) 앱 흐름, 같은 순간(2026-11-02, 표 1-25).
# 먼저 launch.json: recognizer(--wide-reads 0 으로 3번 읽기), recognizer-wide1, photos, visit-captures. 채점: flow_visit.py score <로그>
cd "$(dirname "$0")/../.."
F=/c/Users/jjh7757/flutter/bin/flutter
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
R=experiments/speed/results
GRIDS=$(python -I -X utf8 experiments/speed/flow_visit.py grids)
RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_URL=http://127.0.0.1:8030 --dart-define=RECOGNIZER_API_KEY=local
  --dart-define=ALT_URL=http://127.0.0.1:8031 --dart-define=SLEEP_S=30)
"$F" "${COMMON[@]}" --dart-define=PHOTO_URL=http://127.0.0.1:8040 --dart-define=SET=bcd --dart-define=REPEAT=2 > $R/log_flow_wide1_bcd.txt 2>&1
echo "bcd 끝 $?"
"$F" "${COMMON[@]}" --dart-define=PHOTO_URL=http://127.0.0.1:8042 --dart-define=SET=visit "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI" > $R/log_flow_wide1_visit.txt 2>&1
echo "visit 끝 $?"
