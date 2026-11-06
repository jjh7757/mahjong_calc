#!/usr/bin/env bash
# 개선 계획 8b-3b(2026-11-06 밤) 서버 단독 판정 측정 — 같은 시각 연달아 전(WALL_FRAME 없음) → 후(rot2), 표 1-106 기준.
# 서버 코드 = feat/table-frame bc556f6 worktree(RECOGNIZER_REPO, v2 분류기 기본)를 프로세스 안에서. fold 분류기는 cls4_<나눔>(7-2a 채택분).
#   bash experiments/speed/run_8b3b.sh <TAG>
#   → results/robust_{fold,prod}_wf{0,2}_<TAG>.json, data/role/bench/field_det_final{,_rect,_recolored}_wf{0,2}_<TAG>.json,
#     results/wall_frame_dora_8b3b_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer-8b}
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final"
step() { echo "== $1 $(date +%T)"; }
step "fold 전";  WALL_FRAME=     ROBUST_CLS=cls4 ROBUST_SEAT=det_r8 $RS --models fold --tag wf0_$TAG
step "fold 후";  WALL_FRAME=rot2 ROBUST_CLS=cls4 ROBUST_SEAT=det_r8 $RS --models fold --tag wf2_$TAG
step "prod 전";  WALL_FRAME=     $RS --models prod --tag wf0_$TAG
step "prod 후";  WALL_FRAME=rot2 $RS --models prod --tag wf2_$TAG
for m in 0 2; do
  W=; [ $m = 2 ] && W=rot2
  step "테스트 $m 펴기 없이"; WALL_FRAME=$W $FB --suffix _wf${m}_$TAG
  step "테스트 $m 펴기";      WALL_FRAME=$W $FB --rectify --suffix _wf${m}_$TAG
  step "테스트 $m 색 바꾼";   WALL_FRAME=$W $FB --recolored --suffix _wf${m}_$TAG
done
step "표시패 전·후"
(cd "$RECOGNIZER_REPO" && python -X utf8 scripts/wall_frame_dora.py --modes ,rot2 --out "$MAIN/experiments/speed/results/wall_frame_dora_8b3b_$TAG.json")
step "끝"
