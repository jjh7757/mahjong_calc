#!/usr/bin/env bash
# 상대 위치 바이어스(--relbias) 대 기준선(2026-11-08). 둘 다 합성 사전학습부터 새로(role_synth.py 가 pre_synth8k_rot.pt 뒤에 바뀜).
# 교차 검증(role_set.py) → 테스트 15장(role_field.py score rot). 로그 data/role/log_role_<태그>.txt
#   bash experiments/tile_classifier/run_relbias.sh base2              # 기준선
#   bash experiments/tile_classifier/run_relbias.sh rel2 --relbias     # 상대 위치 바이어스
#   FIELD_ONLY=1 bash experiments/tile_classifier/run_relbias.sh base2 # 사전학습 파일이 있을 때 테스트 15장만
# (rel 태그는 평가 모드 NaN 고치기 전 코드로 돈 것 — 쓰지 않음)
set -u
cd "$(dirname "$0")/../.."
T=experiments/tile_classifier
tag=$1; shift
{
  if [ -z "${FIELD_ONLY:-}" ]; then
    ROLE_LABELS=labels_obb.json python -I -X utf8 $T/role_set.py --feat rot --synth 8000 --synth-epochs 3 --epochs 100 --seeds 3 \
      --pre-file pre_synth8k_rot_$tag.pt --tag _$tag "$@"
  fi
  ROLE_LABELS=labels_obb.json ROLE_TAG=_$tag python -I -X utf8 $T/role_field.py score rot pre_synth8k_rot_$tag.pt
} >> $T/data/role/log_role_$tag.txt 2>&1
echo "끝 $tag"
