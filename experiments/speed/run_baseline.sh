#!/usr/bin/env bash
# 홀드아웃 기준선(개선 계획 2단계, docs/improvement_plan_1105.md): 개발 32회 앱 흐름을 "그 사진을 안 배운 모델" 서버로, 또는 운영과 같은 모델로.
# 먼저 launch.json: exp-files(8043, experiments/ 정적 — 사진 서버 셋 대신), 그리고
#   dev  : recognizer-fold-bcd(8033)·recognizer-fold-am(8034)·recognizer-fold-pmA(8035)·recognizer-fold-pmB(8037)  ← 홀드아웃
#   dev  + U_BCD=U_AM=U_PMA=U_PMB=8036 : recognizer-prodlike(운영과 같은 모델, 개발 사진을 전부 학습) ← 낙관 편향 비교
#   field: recognizer-prodlike(8036) — 운영 모델은 테스트 15장을 학습하지 않아 이게 곧 홀드아웃. RECOLOR=1 이면 색 바꾼 사본.
#   bash experiments/speed/run_baseline.sh dev <TAG>     → results/log_flow_base_<TAG>_{bcd,am,pmA,pmB}.txt, 채점 flow_visit.py score
#   bash experiments/speed/run_baseline.sh field <TAG>   → results/log_flow_base_<TAG>_field.txt, 채점 experiments/rectify/summarize_field.py
# 나눔(experiments/tile_classifier/README.md 끝 절): 오후A/오후B 경계는 역할 모델 교차 검증 fold(role_set.folds)와 같은 171245.
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
U_BCD=${U_BCD:-8033}; U_AM=${U_AM:-8034}; U_PMA=${U_PMA:-8035}; U_PMB=${U_PMB:-8037}; U_FIELD=${U_FIELD:-8036}
P=http://127.0.0.1:${P_PORT:-8043}
MODE=$1; TAG=$2
F=/c/Users/jjh7757/flutter/bin/flutter
R="$MAIN/experiments/speed/results"
COMMON=(drive --profile -d windows --driver=test_driver/integration_test.dart --target=integration_test/read_grid_timing_test.dart
  --dart-define=RECOGNIZER_API_KEY=local --dart-define=LOCAL_ONLY=true --dart-define=ROLES=true)
if [ "$MODE" = dev ]; then
  RIICHI=$(python -I -X utf8 experiments/speed/flow_visit.py riichi)
  GRIDS=$(python -X utf8 experiments/zone_points/zones.py grids saved 2>/dev/null)
  VISIT=(--dart-define=SLEEP_S=5 --dart-define=PHOTO_URL=$P/visit_20261031/captures --dart-define=SET=visit --dart-define=REPEAT=1 "--dart-define=FIELD_GRIDS=$GRIDS" "--dart-define=RIICHI_SIDES=$RIICHI")
  BCD=(--dart-define=SLEEP_S=5 --dart-define=PHOTO_URL=$P/field_20261024/kakao_photos --dart-define=SET=bcd --dart-define=REPEAT=2)
  echo "$TAG bcd 시작 $(date +%T)"
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_BCD "${BCD[@]}" > "$R/log_flow_base_${TAG}_bcd.txt" 2>&1
  echo "$TAG bcd 끝 $? $(date +%T)"
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_AM "${VISIT[@]}" --dart-define=PHOTO_MAX=14 > "$R/log_flow_base_${TAG}_am.txt" 2>&1
  echo "$TAG am 끝 $? $(date +%T)"
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_PMA "${VISIT[@]}" --dart-define=PHOTO_MIN=14 --dart-define=PHOTO_MAX=171245 > "$R/log_flow_base_${TAG}_pmA.txt" 2>&1
  echo "$TAG pmA 끝 $? $(date +%T)"
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_PMB "${VISIT[@]}" --dart-define=PHOTO_MIN=171245 > "$R/log_flow_base_${TAG}_pmB.txt" 2>&1
  echo "$TAG pmB 끝 $? $(date +%T)"
elif [ "$MODE" = field ]; then
  DIR=captures; [ -n "${RECOLOR:-}" ] && DIR=captures_recolor
  echo "$TAG field($DIR) 시작 $(date +%T)"
  "$F" "${COMMON[@]}" --dart-define=RECOGNIZER_URL=http://127.0.0.1:$U_FIELD --dart-define=SLEEP_S=0 --dart-define=PHOTO_URL=$P/field_20261024/$DIR \
    --dart-define=SET=field --dart-define=RECTIFY=true --dart-define=REPEAT=1 > "$R/log_flow_base_${TAG}_field.txt" 2>&1
  echo "$TAG field 끝 $? $(date +%T)"
else
  echo "모드는 dev 또는 field"; exit 2
fi
