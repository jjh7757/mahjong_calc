#!/usr/bin/env bash
# 개선 계획 7-2a(2026-11-06) 서버 단독 판정 측정 — 같은 시각 연달아(전 = 운영 모델 / 후 = 분류기만 cls4, 합성 사전학습·새 씨드 10·11).
# 검출기·역할 모델은 전·후 같음(8회차). 서버 코드는 feat/cls-alt worktree(RECOGNIZER_REPO) 를 프로세스 안에서, 모델 경로는 env 로만 바꾼다.
#   bash experiments/speed/run_72a.sh <TAG>   → results/robust_{fold,prod}_72a{pre,post}_<TAG>.json,
#                                               data/role/bench/field_det_final{,_recolored}_rect_72a{pre,post}_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer-s9}
M="$MAIN/experiments/tile_classifier/server_bench/models"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify"
CLS=(LOCAL_CLS_MODEL=$M/cls4_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls4_all_s1.onnx)
# "전" = 운영 분류기를 이름으로 못박음(feat/cls-alt 599473e 부터 기본값이 v2 라서. 측정한 c4484dd 에선 기본값과 같은 파일).
PRE=(LOCAL_CLS_MODEL=$RECOGNIZER_REPO/app/assets/tile-cls-mnv3s.onnx LOCAL_ALT_CLS_MODEL=$RECOGNIZER_REPO/app/assets/tile-cls-alt.onnx)
step() { echo "== $1 $(date +%T)"; }
step "fold 전";        ROBUST_CLS=cls  ROBUST_SEAT=det_r8 $RS --models fold --tag 72apre_$TAG
step "fold 후";        ROBUST_CLS=cls4 ROBUST_SEAT=det_r8 $RS --models fold --tag 72apost_$TAG
step "prod 전";        env "${PRE[@]}" $RS --models prod --tag 72apre_$TAG
step "prod 후";        env "${CLS[@]}" $RS --models prod --tag 72apost_$TAG
step "테스트 전";      env "${PRE[@]}" $FB --suffix _72apre_$TAG;  env "${PRE[@]}" $FB --recolored --suffix _72apre_$TAG
step "테스트 후";      env "${CLS[@]}" $FB --suffix _72apost_$TAG; env "${CLS[@]}" $FB --recolored --suffix _72apost_$TAG
step "끝"
