#!/usr/bin/env bash
# YOLO26 자동 격자(auto_grid.py → results/auto_grid/auto_grid.json) vs 사용자 수동 격자로 앱 판독 흐름(read_grid_test.dart) 그대로.
# 장면 B·C·D × 사진 2장. 자동 REPEAT=2, 수동 REPEAT=1(같은 시각의 비교용). 채점은 field_20261024/score_seat3.py.
#   bash experiments/yolo/run_auto_grid.sh http://127.0.0.1:8030
set -u
URL=${1:-http://127.0.0.1:8030}
cd "$(dirname "$0")/../.."
P=experiments/field_20261024/kakao_photos
J=experiments/yolo/results/auto_grid/auto_grid.json
declare -A SCENE_PHOTOS=([B]="k25 k28" [C]="k15 k26" [D]="k12 k16")
for s in B C D; do
  for p in ${SCENE_PHOTOS[$s]}; do
    AUTO=$(python -I -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1],encoding='utf-8'))[sys.argv[2]]['grid']))" "$J" "$s/$p")
    MAN=$(python -I -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1],encoding='utf-8'))[sys.argv[2]]['manual']))" "$J" "$s/$p")
    echo "$s/$p auto=$AUTO manual=$MAN"
    PHOTOS="$P/$p.jpg" OUT=experiments/yolo/results/auto_grid_scenes/$s REPEAT=2 URL=$URL GRID=$AUTO \
      /c/Users/jjh7757/flutter/bin/flutter test experiments/field_20261024/read_grid_test.dart --reporter compact 2>&1 | tail -1
    PHOTOS="$P/$p.jpg" OUT=experiments/yolo/results/manual_grid_scenes/$s REPEAT=1 URL=$URL GRID=$MAN \
      /c/Users/jjh7757/flutter/bin/flutter test experiments/field_20261024/read_grid_test.dart --reporter compact 2>&1 | tail -1
  done
done
