#!/usr/bin/env bash
# 역할 모델 v3r15d(외톨이 앞면 = 울기 아님, metrics 표 1-138·1-140) 서버 단독 판정
# — 같은 시각 연달아 전(운영 tile-roles-rot*) / 후(tile-roles-v3r15d*). run_relbias.sh 와 같은 묶음: 회귀 fold·prod + 테스트 15장·색 바꾼 15장.
# 검출기·분류기(운영 v3 = cls6, 나눔 cls6_*)·서버 코드(mahjong-recognizer master)는 전·후 같음.
#   bash experiments/speed/run_v3r15d.sh <TAG>  → results/robust_{fold,prod}_v3r15d{0,1}_<TAG>.json,
#                                               data/role/bench/field_det_final{,_recolored}_rect_v3r15d{0,1}_<TAG>.json
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
step "fold 전";   ROBUST_ROLE=tile-roles-rot   $RS --models fold --tag v3r15d0_$TAG
step "fold 후";   ROBUST_ROLE=tile-roles-v3r15d $RS --models fold --tag v3r15d1_$TAG
step "prod 전";   $RS --models prod --tag v3r15d0_$TAG
step "prod 후";   LOCAL_ROLE_MODEL=$M/tile-roles-v3r15d.onnx $RS --models prod --tag v3r15d1_$TAG
step "테스트 전"; $FB --suffix _v3r15d0_$TAG; $FB --recolored --suffix _v3r15d0_$TAG
step "테스트 후"; LOCAL_ROLE_MODEL=$M/tile-roles-v3r15d.onnx $FB --suffix _v3r15d1_$TAG; LOCAL_ROLE_MODEL=$M/tile-roles-v3r15d.onnx $FB --recolored --suffix _v3r15d1_$TAG
step "끝"
