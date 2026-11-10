#!/usr/bin/env bash
# 분류기 입력 크기 실험(2026-11-10, 사용자 "분류기도 해상도 바꾸면서 테스트"): cls6 와 같은 설정(합성 사전학습 + 180° 뒤집기, 씨드 10)을
# 입력 크기만 바꿔 다시 학습(CLS_SIZE=64·96·192, 128 은 cls6 를 그대로 복사), 나눔 3벌(bcd·am·pm) + 전체 1벌(all, 테스트 15장용).
# 두 번째 분류기(_s1, 불확실성 신호용)는 모든 크기에서 빼서 같게 둔다. 검출(1280)·역할 모델(v3r15d)·서버 코드는 그대로.
#   bash experiments/speed/run_clssize.sh <TAG> [크기...]
#   → server_bench/models/clsr<N>_{bcd,am,pm,all}.onnx, data/synth/results_clsr<N>.json, results/clssize_holdout_<TAG>.json,
#     results/robust_fold_clsr<N>_<TAG>.json, data/role/bench/field_det_final{,_recolored}_rect_clsr<N>_<TAG>.json
set -u
MAIN="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$MAIN"
TAG=$1; shift
SIZES=${*:-"64 96 192"}
export RECOGNIZER_REPO=${RECOGNIZER_REPO:-C:/Users/jjh7757/dev/mahjong-recognizer}
M="$MAIN/experiments/tile_classifier/server_bench/models"
for p in bcd am pm all; do [ -f "$M/clsr128_$p.onnx" ] || cp "$M/cls6_$p.onnx" "$M/clsr128_$p.onnx"; done
for n in $SIZES; do
  echo "== 학습 $n $(date +%T)"
  CLS_SIZE=$n python -I -X utf8 experiments/tile_classifier/train.py --synth-pre --rot180 --tag clsr$n --seed-offset 10 --seeds 0 --only bcd,am,pm,all 2>&1 | grep -v Warning | tail -6
done
W="python -I -X utf8 experiments/speed/imgsz_run.py 1280"
export ROBUST_ROLE=tile-roles-v3r15d ROBUST_SEAT=det_r8 LOCAL_ALT_CLS_MODEL=$M/none.onnx
for n in 128 $SIZES; do
  echo "== 평가 $n $(date +%T)"
  CLS_SIZE=$n python -I -X utf8 experiments/speed/clssize_holdout.py $n $TAG
  CLS_SIZE=$n ROBUST_CLS=clsr$n $W experiments/speed/robust_suite.py run --models fold --tag clsr${n}_$TAG | tail -2
  CLS_SIZE=$n LOCAL_CLS_MODEL=$M/clsr${n}_all.onnx $W experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify --suffix _clsr${n}_$TAG | tail -2
  CLS_SIZE=$n LOCAL_CLS_MODEL=$M/clsr${n}_all.onnx $W experiments/tile_classifier/server_bench/field_bench.py --det det_final --rectify --recolored --suffix _clsr${n}_$TAG | tail -2
done
echo "== 끝 $(date +%T)"
