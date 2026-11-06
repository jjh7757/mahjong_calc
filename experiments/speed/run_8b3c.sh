#!/usr/bin/env bash
# 개선 계획 8b-3c(2026-11-06 밤) 서버 단독 판정 측정 — 같은 시각 연달아 전(WALL_FRAME 없음) → 후(hybrid + 격자 출처 강제값), 표 1-108 기준.
# 서버 코드 = feat/table-frame 18a54ca worktree(RECOGNIZER_REPO, v2 분류기 기본)를 프로세스 안에서. 회귀는 prod 만 세 변형(계획 세션 결정).
# 격자 출처(WALL_FRAME_GRID_SRC): 회귀·테스트 펴기·개발 표시패 = saved, 테스트 펴기 없이·색 바꾼·그 표시패 = none.
#   bash experiments/speed/run_8b3c.sh <TAG>      (TAG 에 단계 이름, 예: 8b3c_1106)
#   → results/robust_prod_wf{0,3}_<TAG>.json, data/role/bench/field_det_final{,_rect,_recolored}_wf{0,3}_<TAG>.json,
#     results/wall_frame_dora_{dev,field}_<TAG>.json
#   bash experiments/speed/run_8b3c.sh <TAG> e    → 조용할 때 (e): 회귀 orig prod 전·후 번갈아 3번 results/robust_prod_e{0,3}{1,2,3}_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer-8b}
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
FB="python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final"
step() { echo "== $1 $(date +%T)"; }
if [ "${2:-}" = e ]; then
  for k in 1 2 3; do
    step "e 전 $k"; WALL_FRAME= $RS --models prod --only orig --tag e0${k}_$TAG
    step "e 후 $k"; WALL_FRAME=hybrid WALL_FRAME_GRID_SRC=saved $RS --models prod --only orig --tag e3${k}_$TAG
  done
  step "끝"; exit 0
fi
V=orig,rot_p25,rc_gray
step "prod 전"; WALL_FRAME= $RS --models prod --only $V --tag wf0_$TAG
step "prod 후"; WALL_FRAME=hybrid WALL_FRAME_GRID_SRC=saved $RS --models prod --only $V --tag wf3_$TAG
step "테스트 전 펴기 없이"; WALL_FRAME= $FB --suffix _wf0_$TAG
step "테스트 전 펴기";      WALL_FRAME= $FB --rectify --suffix _wf0_$TAG
step "테스트 전 색 바꾼";   WALL_FRAME= $FB --recolored --suffix _wf0_$TAG
step "테스트 후 펴기 없이(none)"; WALL_FRAME=hybrid WALL_FRAME_GRID_SRC=none  $FB --suffix _wf3_$TAG
step "테스트 후 펴기(saved)";     WALL_FRAME=hybrid WALL_FRAME_GRID_SRC=saved $FB --rectify --suffix _wf3_$TAG
step "테스트 후 색 바꾼(none)";   WALL_FRAME=hybrid WALL_FRAME_GRID_SRC=none  $FB --recolored --suffix _wf3_$TAG
step "표시패 개발 전·후(saved)"
(cd "$RECOGNIZER_REPO" && WALL_FRAME_GRID_SRC=saved python -X utf8 scripts/wall_frame_dora.py --sets dev --modes ,hybrid --out "$MAIN/experiments/speed/results/wall_frame_dora_dev_$TAG.json")
step "표시패 테스트·색 바꾼 전·후(none)"
(cd "$RECOGNIZER_REPO" && WALL_FRAME_GRID_SRC=none python -X utf8 scripts/wall_frame_dora.py --sets test,recolor --modes ,hybrid --out "$MAIN/experiments/speed/results/wall_frame_dora_field_$TAG.json")
step "끝"
