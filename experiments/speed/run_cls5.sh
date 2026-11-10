#!/usr/bin/env bash
# 분류기 180° 뒤집기 재학습(cls5, 2026-11-07) 서버 단독 판정 — 같은 시각 연달아(전 = 운영 v2 = cls4 / 후 = cls5, 같은 씨드 10·11, 다른 것은 --rot180 뿐).
# run_72a.sh 와 같은 묶음: 회귀 fold·prod + 테스트 15장·색 바꾼 15장. 검출기·역할 모델은 전·후 같음. 서버 코드는 mahjong-recognizer master(08e44b0).
#   bash experiments/speed/run_cls5.sh <TAG>  → results/robust_{fold,prod}_cls5{pre,post}_<TAG>.json,
#                                              data/role/bench/field_det_final{,_recolored}_rect_cls5{pre,post}_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer}
M="$MAIN/experiments/tile_classifier/server_bench/models"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify"
PRE=(LOCAL_CLS_MODEL=$M/cls4_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls4_all_s1.onnx)
POST=(LOCAL_CLS_MODEL=$M/cls5_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls5_all_s1.onnx)
step() { echo "== $1 $(date +%T)"; }
step "fold 전";        ROBUST_CLS=cls4 ROBUST_SEAT=det_r8 $RS --models fold --tag cls5pre_$TAG
step "fold 후";        ROBUST_CLS=cls5 ROBUST_SEAT=det_r8 $RS --models fold --tag cls5post_$TAG
step "prod 전";        env "${PRE[@]}" $RS --models prod --tag cls5pre_$TAG
step "prod 후";        env "${POST[@]}" $RS --models prod --tag cls5post_$TAG
step "테스트 전";      env "${PRE[@]}" $FB --suffix _cls5pre_$TAG;  env "${PRE[@]}" $FB --recolored --suffix _cls5pre_$TAG
step "테스트 후";      env "${POST[@]}" $FB --suffix _cls5post_$TAG; env "${POST[@]}" $FB --recolored --suffix _cls5post_$TAG
step "끝"
