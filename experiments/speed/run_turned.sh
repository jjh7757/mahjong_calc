#!/usr/bin/env bash
# 서버 규칙 TURNED_HAND(눕힌 손패·떼어 둔 패 돌려 읽기, metrics 표 1-159) a·c — 새 테스트 세트 회귀 21변형 prod, 같은 코드에서 끔 → 켬 연달아.
# 서버 코드는 RECOGNIZER_REPO(기본 mahjong-recognizer, feat/turned-hand 체크아웃), 역할 모델은 운영 기본 v3r15d.
#   bash experiments/speed/run_turned.sh <TAG>  → results/robust_prod_turned{0,1}_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer}
echo "서버 브랜치 $(git -C "$RECOGNIZER_REPO" branch --show-current) $(git -C "$RECOGNIZER_REPO" rev-parse --short HEAD) 변경 $(git -C "$RECOGNIZER_REPO" status --short | wc -l)"
RS="python -I -X utf8 experiments/speed/robust_suite.py run"
step() { echo "== $1 $(date +%T)"; }
step "prod 끔"; TURNED_HAND=0 $RS --models prod --tag turned0_$TAG
step "prod 켬"; TURNED_HAND=1 $RS --models prod --tag turned1_$TAG
step "끝"
