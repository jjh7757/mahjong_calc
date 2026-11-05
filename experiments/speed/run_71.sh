#!/usr/bin/env bash
# 개선 계획 7-1(2026-11-06) 서버 단독 판정 측정 — 같은 시각 연달아(전 = 지금 모델 / 후 = 새 분류기 cls2 + 새 역할 rot2 / 분류기만 / 역할만).
# 서버 코드는 feat/cls-alt worktree(RECOGNIZER_REPO, 답은 master 와 같음 — 표 1-93) 를 프로세스 안에서. 모델 경로는 env 로만 바꾼다.
#   bash experiments/speed/run_71.sh <TAG>   → results/robust_{fold,prod}_71{pre,post,cls,role}_<TAG>.json, role/bench/field_det_final_rect_71*.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer-s7}
M="$MAIN/experiments/tile_classifier/server_bench/models"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify"
NEW=(LOCAL_CLS_MODEL=$M/cls2_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls2_all_s1.onnx LOCAL_ROLE_MODEL=$M/tile-roles-rot2.onnx)
step() { echo "== $1 $(date +%T)"; }
step "fold 전";        ROBUST_CLS=cls  ROBUST_ROLE=tile-roles-rot  $RS --models fold --tag 71pre_$TAG
step "fold 후";        ROBUST_CLS=cls2 ROBUST_ROLE=tile-roles-rot2 $RS --models fold --tag 71post_$TAG
step "prod 전";        $RS --models prod --tag 71pre_$TAG
step "prod 후";        env "${NEW[@]}" $RS --models prod --tag 71post_$TAG
step "테스트 전";      $FB --suffix _71pre_$TAG;            $FB --recolored --suffix _71pre_$TAG
step "테스트 후";      env "${NEW[@]}" $FB --suffix _71post_$TAG; env "${NEW[@]}" $FB --recolored --suffix _71post_$TAG
step "fold 분류기만";  ROBUST_CLS=cls2 ROBUST_ROLE=tile-roles-rot  $RS --models fold --tag 71cls_$TAG
step "fold 역할만";    ROBUST_CLS=cls  ROBUST_ROLE=tile-roles-rot2 $RS --models fold --tag 71role_$TAG
step "테스트 분류기만"; env LOCAL_CLS_MODEL=$M/cls2_all.onnx LOCAL_ALT_CLS_MODEL=$M/cls2_all_s1.onnx $FB --suffix _71cls_$TAG
step "테스트 역할만";  env LOCAL_ROLE_MODEL=$M/tile-roles-rot2.onnx $FB --suffix _71role_$TAG
step "끝"
