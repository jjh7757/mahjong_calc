#!/usr/bin/env bash
# 서버 규칙 짝은 늘 2장(LONE_PAIR_LOOSE, metrics 표 1-145) 서버 단독 판정 — 역할 모델은 둘 다 v3r15d
# — 같은 시각 연달아 전(운영 tile-roles-rot*) / 후(tile-roles-v3r15d*). run_relbias.sh 와 같은 묶음: 회귀 fold·prod + 테스트 15장·색 바꾼 15장.
# 검출기·분류기(운영 v3 = cls6, 나눔 cls6_*)·서버 코드(mahjong-recognizer master)는 전·후 같음.
#   bash experiments/speed/run_lonepair.sh <TAG>  → results/robust_{fold,prod}_lp{0,1}_<TAG>.json,
#                                               data/role/bench/field_det_final{,_recolored}_rect_lp{0,1}_<TAG>.json
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
export ROBUST_ROLE=tile-roles-v3r15d
L=$M/tile-roles-v3r15d.onnx
step "fold 전";   LONE_PAIR_LOOSE=0 $RS --models fold --tag lp0_$TAG
step "fold 후";   LONE_PAIR_LOOSE=1 $RS --models fold --tag lp1_$TAG
step "prod 전";   LOCAL_ROLE_MODEL=$L LONE_PAIR_LOOSE=0 $RS --models prod --tag lp0_$TAG
step "prod 후";   LOCAL_ROLE_MODEL=$L LONE_PAIR_LOOSE=1 $RS --models prod --tag lp1_$TAG
step "테스트 전"; LOCAL_ROLE_MODEL=$L LONE_PAIR_LOOSE=0 $FB --suffix _lp0_$TAG; LOCAL_ROLE_MODEL=$L LONE_PAIR_LOOSE=0 $FB --recolored --suffix _lp0_$TAG
step "테스트 후"; LOCAL_ROLE_MODEL=$L LONE_PAIR_LOOSE=1 $FB --suffix _lp1_$TAG; LOCAL_ROLE_MODEL=$L LONE_PAIR_LOOSE=1 $FB --recolored --suffix _lp1_$TAG
step "끝"
