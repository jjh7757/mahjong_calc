#!/usr/bin/env bash
# 분류기 cls7 = cls6 설정(합성 사전학습 + 180° 뒤집기, 씨드 10·11) + 11-06·11-07 매장 5 계열 크롭(red5_harvest.py, 검토 반영 labels.json)
# 학습(8벌) 뒤 서버 단독 판정 — 같은 시각 연달아 전 cls6 / 후 cls7. 검출기·역할 모델(v3r15d)·서버 코드(mahjong-recognizer master 596101e)는 전·후 같음.
#   bash experiments/speed/run_cls7.sh <TAG>  → server_bench/models/cls7_*.onnx, data/synth/results_cls7.json,
#     results/robust_{fold,prod}_cls7{pre,post}_<TAG>.json, data/role/bench/field_det_final{,_recolored}_rect_cls7{pre,post}_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer}
M="$MAIN/experiments/tile_classifier/server_bench/models"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify"
PRE=(LOCAL_CLS_MODEL=$M/cls6_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls6_all_s1.onnx)
POST=(LOCAL_CLS_MODEL=$M/cls7_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls7_all_s1.onnx)
export ROBUST_SEAT=det_r8 ROBUST_ROLE=tile-roles-v3r15d
step() { echo "== $1 $(date +%T)"; }
step "학습";      python -I -X utf8 experiments/tile_classifier/train.py --synth-pre --rot180 --red5 --tag cls7 --seed-offset 10 2>&1 | grep -v -i warning
step "fold 전";   ROBUST_CLS=cls6 $RS --models fold --tag cls7pre_$TAG | tail -3
step "fold 후";   ROBUST_CLS=cls7 $RS --models fold --tag cls7post_$TAG | tail -3
step "prod 전";   env "${PRE[@]}" $RS --models prod --tag cls7pre_$TAG | tail -3
step "prod 후";   env "${POST[@]}" $RS --models prod --tag cls7post_$TAG | tail -3
step "테스트 전"; env "${PRE[@]}" $FB --suffix _cls7pre_$TAG | tail -3;  env "${PRE[@]}" $FB --recolored --suffix _cls7pre_$TAG | tail -3
step "테스트 후"; env "${POST[@]}" $FB --suffix _cls7post_$TAG | tail -3; env "${POST[@]}" $FB --recolored --suffix _cls7post_$TAG | tail -3
step "끝"
