#!/usr/bin/env bash
# 자리 판독 3번 동시 + 만장일치(서버 SEAT_READS=3)로 갤러리 장면 B·C·D × 사진 2장 × 2회를 앱 판독 흐름 그대로.
# 화료패가 사진에 없는 A·E 는 평가에서 뺀다(2026-10-25 사용자 결정).
# 격자는 5구역 측정(grid5_scenes)과 같다. 화료자 지정 없이 완전 자동.
#   bash experiments/field_20261024/run_seat3.sh http://127.0.0.1:8030
set -u
URL=${1:-http://127.0.0.1:8030}
cd "$(dirname "$0")/../.."
P=experiments/field_20261024/kakao_photos
declare -A GRID=(
  [B]='{"x1":272,"x2":735,"y1":137,"y2":727}'
  [C]='{"x1":320,"x2":760,"y1":142,"y2":717}'
  [D]='{"x1":280,"x2":745,"y1":173,"y2":713}'
)
declare -A SCENE_PHOTOS=([B]="k25 k28" [C]="k15 k26" [D]="k12 k16")
for s in B C D; do
  set -- ${SCENE_PHOTOS[$s]}
  PHOTOS="$P/$1.jpg;$P/$2.jpg" OUT=experiments/field_20261024/seat3_scenes/$s REPEAT=2 URL=$URL GRID=${GRID[$s]} \
    /c/Users/jjh7757/flutter/bin/flutter test experiments/field_20261024/read_grid_test.dart --reporter compact 2>&1 | tail -1
done
