"""0단계 E1 다시 재기(2026-11-16, `docs/role_pair_plan_1116.md` 5절 0단계 3): v3r15d 를 만든 것과 같은 cv 호출을 한 번 더.
role_v3r15d_run.py 의 `t.cv("nostaged", pf.name, 3, 100, tag_extra=...)` 와 같은 인자·환경 변수, 사전학습은 저장된 pre_synth8k_v3r15d.pt(다시 안 만듦).
라벨은 지금 `labels_v2.json`(11-10 153311 고친 뒤 — v3r15d 는 고치기 전, v3r15dfix 는 고친 뒤 같은 명령). 기존 파일을 덮지 않게 태그 `_v3r15d_rerun1116`.
  ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 python -I -X utf8 experiments/tile_classifier/role_pair_e1_rerun.py
결과 data/role/v2/cv_nostaged_v3r15d_rerun1116.json, 가중치 role_v2_nostaged_v3r15d_rerun1116_{fold_*,all}.pt
"""
import sys
import time
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs, role_synth_v3 as g, role_v2_train as t  # noqa: E401,E402

assert t.SHIFT_ON and g.ROT == "15" and g.DROP_SAFE and rs.DROP_SAFE and g.OTHER_NEG and rs.OTHER_NEG and not rs.NONE, \
    "ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 로 실행"
TAG = "_v3r15d_rerun1116"
for p in [t.V2 / f"cv_nostaged{TAG}.json", t.V2 / f"role_v2_nostaged{TAG}_all.pt", *(t.V2 / f"role_v2_nostaged{TAG}_fold_{f}.pt" for f in t.FOLDS)]:
    assert not p.exists(), f"{p} 가 이미 있음 — 덮어쓰지 않음"
sys.stdout.reconfigure(encoding="utf-8")
torch.set_num_threads(8)
t0 = time.time()
print("시작", time.strftime("%Y-%m-%d %H:%M:%S"), flush=True)
pf = rs.OUT / "pre_synth8k_v3r15d.pt"
t.cv("nostaged", pf.name, 3, 100, tag_extra=TAG)
print("끝", time.strftime("%Y-%m-%d %H:%M:%S"), f"{round(time.time() - t0)}초", flush=True)
