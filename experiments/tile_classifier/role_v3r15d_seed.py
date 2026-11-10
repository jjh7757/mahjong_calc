"""v3r15d 잡음 측정(2026-11-09 밤, metrics 표 1-144): 설정은 v3r15d 그대로, 씨드만 바꿈(사전학습 데이터 100+OFF+s·학습 OFF+s, 미세 조정 변형 사본·학습 OFF+s).
같은 설정에서 26장 장면 수가 얼마나 흔들리는지 본다. ONNX·운영 나눔은 만들지 않는다.
  ROLE_SEED_OFF=10 ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 python -I -X utf8 experiments/tile_classifier/role_v3r15d_seed.py
"""
import os, sys, time
from pathlib import Path
import torch
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs, role_synth_v3 as g, role_v2_train as t
assert t.SHIFT_ON and g.ROT == "15" and g.DROP_SAFE and rs.DROP_SAFE and g.OTHER_NEG and rs.OTHER_NEG and not rs.NONE
OFF = int(os.environ["ROLE_SEED_OFF"])
sys.stdout.reconfigure(encoding="utf-8")
torch.set_num_threads(8)
t0 = time.time()
pf = rs.OUT / f"pre_synth8k_v3r15d_s{OFF}.pt"
pre = []
for seed in range(3):
    pre.append(rs.train(g.dataset(8000, 100 + OFF + seed), 3, OFF + seed))
    print("사전학습 씨드", OFF + seed, f"{round(time.time() - t0)}초", flush=True)
torch.save([n.state_dict() for n in pre], pf)
t.cv("nostaged", pf.name, 3, 100, tag_extra=f"_v3r15d_s{OFF}", seed_off=OFF)
print("끝", f"{round(time.time() - t0)}초")
