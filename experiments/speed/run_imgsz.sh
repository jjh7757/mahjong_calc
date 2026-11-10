#!/usr/bin/env bash
# 검출 입력 크기 실험(2026-11-10, 사용자 "해상도를 늘리면 성능이 좋아지는지 테스트"): 모델·서버 코드는 그대로(운영 596101e 구성), app.local_read.IMG 만 바꿈.
#   bash experiments/speed/run_imgsz.sh <TAG> [크기...]
#   → results/robust_fold_img<N>_<TAG>.json(나눔 모델 회귀 21변형), data/role/bench/field_det_final{,_recolored}_rect_img<N>_<TAG>.json(테스트·색 바꾼 15장)
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1; shift
SIZES=${*:-"1280 960 1600 1920 2560"}
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer}
export ROBUST_CLS=cls6 ROBUST_ROLE=tile-roles-v3r15d ROBUST_SEAT=det_r8
# field_bench 는 LOCAL_CLS_MODEL 이 없으면 11-02 v1 분류기(tile-cls-mnv3s.onnx)를 쓴다 — 운영 v3 로 맞춤
export LOCAL_CLS_MODEL=$RECOGNIZER_REPO/app/assets/tile-cls-mnv3s-v3.onnx LOCAL_ALT_CLS_MODEL=$RECOGNIZER_REPO/app/assets/tile-cls-alt-v3.onnx
W="python -I -X utf8 experiments/speed/imgsz_run.py"
for n in $SIZES; do
  echo "== $n fold $(date +%T)"; $W $n experiments/speed/robust_suite.py run --models fold --tag img${n}_$TAG | tail -2
  echo "== $n field $(date +%T)"; $W $n experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify --suffix _img${n}_$TAG | tail -3
  echo "== $n recolored $(date +%T)"; $W $n experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify --recolored --suffix _img${n}_$TAG | tail -3
done
echo "== 끝 $(date +%T)"
