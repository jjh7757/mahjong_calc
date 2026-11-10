#!/bin/sh
# 세 판(R2·R3a·R4)을 규칙 두 벌로 돌려 채점. 검출(det.json)은 이미 있으면 다시 안 돌린다.
# v1 = 고정 규칙(R4 를 시험 판으로 처음 잰 것), v2 = R4 실패를 보고 더한 선 시작·같은 자리 바뀜.
cd "$(dirname "$0")"
C=../visit_20261107/captures
export PYTHONIOENCODING=utf-8
run() { # name track dealer t0 t1
  python paifu_frames.py "$C/$2" results --name "$1" ${4:+--t0 $4} ${5:+--t1 $5} --tag _v1 >/dev/null
  python paifu_frames.py "$C/$2" results --name "$1" ${4:+--t0 $4} ${5:+--t1 $5} --dealer-side "$3" --flip --tag _v2 >/dev/null
  for v in v1 v2; do python score.py "results/$1/slot_$v.json" truth.json "$1" | tail -1 | sed "s/^/$1 $v /"; done
}
run R2 20261107_153128_track top 15:30:40 15:33:10
run R3a 20261107_153423_track left 15:33:30 15:36:40
run R4 20261107_154029_track bottom
