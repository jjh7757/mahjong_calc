#!/usr/bin/env bash
# 개선 계획 7-2(2026-11-06) 서버 단독 판정 측정 — 같은 시각 연달아(전 = 운영 모델 / 후 = 9회차 자리 검출기 det_r9 + 분류기 cls3 / 검출기만 / 분류기만).
# 서버 코드는 feat/cls-alt worktree(RECOGNIZER_REPO, 답은 master 와 같음 — 표 1-93) 를 프로세스 안에서. 모델 경로는 env 로만 바꾼다. 역할 모델은 그대로.
#   bash experiments/speed/run_72.sh <TAG>   → results/robust_{fold,prod}_72{pre,post,det,cls}_<TAG>.json, role/bench/field_det_final_rect_72*.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer-s8}
M="$MAIN/experiments/tile_classifier/server_bench/models"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify"
CLS=(LOCAL_CLS_MODEL=$M/cls3_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls3_all_s1.onnx)
DET=(LOCAL_SEAT_MODEL=$M/det_r9_final.onnx)
step() { echo "== $1 $(date +%T)"; }
step "fold 전";         ROBUST_CLS=cls  ROBUST_SEAT=det_r8 $RS --models fold --tag 72pre_$TAG
step "fold 후";         ROBUST_CLS=cls3 ROBUST_SEAT=det_r9 $RS --models fold --tag 72post_$TAG
step "prod 전";         $RS --models prod --tag 72pre_$TAG
step "prod 후";         env "${CLS[@]}" "${DET[@]}" $RS --models prod --tag 72post_$TAG
step "테스트 전";       $FB --suffix _72pre_$TAG;  $FB --recolored --suffix _72pre_$TAG
step "테스트 후";       env "${CLS[@]}" "${DET[@]}" $FB --suffix _72post_$TAG; env "${CLS[@]}" "${DET[@]}" $FB --recolored --suffix _72post_$TAG
step "fold 검출기만";   ROBUST_CLS=cls  ROBUST_SEAT=det_r9 $RS --models fold --tag 72det_$TAG
step "fold 분류기만";   ROBUST_CLS=cls3 ROBUST_SEAT=det_r8 $RS --models fold --tag 72cls_$TAG
step "prod 검출기만";   env "${DET[@]}" $RS --models prod --tag 72det_$TAG
step "prod 분류기만";   env "${CLS[@]}" $RS --models prod --tag 72cls_$TAG
step "테스트 검출기만"; env "${DET[@]}" $FB --suffix _72det_$TAG
step "테스트 분류기만"; env "${CLS[@]}" $FB --suffix _72cls_$TAG
step "끝"
