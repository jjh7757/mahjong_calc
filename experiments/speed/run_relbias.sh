#!/usr/bin/env bash
# 역할 모델 상대 위치 바이어스(_rel2, metrics 표 1-120·1-121) 서버 단독 판정 — 같은 시각 연달아 전(운영 tile-roles-rot*) / 후(tile-roles-rel2*)
# + 참고 _base2(같은 조건 바이어스 없음, 판정에 안 씀). run_cls6.sh 와 같은 묶음: 회귀 fold·prod + 테스트 15장·색 바꾼 15장.
# 검출기·분류기(운영 v3 = cls6, 나눔 cls6_*)·서버 코드(mahjong-recognizer master)는 전·후 같음.
#   bash experiments/speed/run_relbias.sh <TAG>  → results/robust_{fold,prod}_rb{pre,post,base}_<TAG>.json,
#                                                 data/role/bench/field_det_final{,_recolored}_rect_rb{pre,post,base}_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer}
M="$MAIN/experiments/tile_classifier/server_bench/models"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify"
export ROBUST_CLS=cls6 ROBUST_SEAT=det_r8
step() { echo "== $1 $(date +%T)"; }
step "fold 전";   ROBUST_ROLE=tile-roles-rot  $RS --models fold --tag rbpre_$TAG
step "fold 후";   ROBUST_ROLE=tile-roles-rel2 $RS --models fold --tag rbpost_$TAG
step "prod 전";   $RS --models prod --tag rbpre_$TAG
step "prod 후";   LOCAL_ROLE_MODEL=$M/tile-roles-rel2.onnx $RS --models prod --tag rbpost_$TAG
step "테스트 전"; $FB --suffix _rbpre_$TAG; $FB --recolored --suffix _rbpre_$TAG
step "테스트 후"; LOCAL_ROLE_MODEL=$M/tile-roles-rel2.onnx $FB --suffix _rbpost_$TAG; LOCAL_ROLE_MODEL=$M/tile-roles-rel2.onnx $FB --recolored --suffix _rbpost_$TAG
step "참고 base2"
ROBUST_ROLE=tile-roles-base2 $RS --models fold --tag rbbase_$TAG
LOCAL_ROLE_MODEL=$M/tile-roles-base2.onnx $RS --models prod --tag rbbase_$TAG
LOCAL_ROLE_MODEL=$M/tile-roles-base2.onnx $FB --suffix _rbbase_$TAG; LOCAL_ROLE_MODEL=$M/tile-roles-base2.onnx $FB --recolored --suffix _rbbase_$TAG
step "끝"
