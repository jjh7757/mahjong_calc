#!/usr/bin/env bash
# 역할 모델 v3r15dfix(153311 라벨 고침, metrics 표 1-157) 2단계 — 새 테스트 세트(표 1-153) 회귀 21변형 prod, 같은 시각 연달아
# 전 = 운영 기본(app/assets/tile-roles-v3r15d.onnx) / 후 = LOCAL_ROLE_MODEL=tile-roles-v3r15dfix.onnx. 그 밖(검출·분류·서버 코드 596101e)은 같음.
#   bash experiments/speed/run_v3r15dfix.sh <TAG>  → results/robust_prod_v3r15dfix{0,1}_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer}
M="$MAIN/experiments/tile_classifier/server_bench/models"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
step() { echo "== $1 $(date +%T)"; }
step "prod 전"; $RS --models prod --tag v3r15dfix0_$TAG
step "prod 후"; LOCAL_ROLE_MODEL=$M/tile-roles-v3r15dfix.onnx $RS --models prod --tag v3r15dfix1_$TAG
step "끝"
