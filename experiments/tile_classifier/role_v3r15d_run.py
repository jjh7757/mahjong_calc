"""v3r15d(2026-11-09 오후, metrics 표 1-138): v3r15c + 역할 없는 외톨이 앞면(생성기 -2 · 실제 other)을 "손패·울기·떼어 둔 패 아님" 손실로.
  ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 python -I -X utf8 experiments/tile_classifier/role_v3r15d_run.py
"""
import json, sys, time
from pathlib import Path
import torch
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs, role_synth_v3 as g, role_v2_train as t
from role_v3_export import export, MODELS
assert t.SHIFT_ON and g.ROT == "15" and g.DROP_SAFE and rs.DROP_SAFE and g.OTHER_NEG and rs.OTHER_NEG, "ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 로 실행"
sys.stdout.reconfigure(encoding="utf-8")
torch.set_num_threads(8)
t0 = time.time()
pf = rs.OUT / "pre_synth8k_v3r15d.pt"  # 생성기에 외톨이 앞면(-2, 표 1-138)이 생겨 사전학습 새로
pre = []
for seed in range(3):
    pre.append(rs.train(g.dataset(8000, 100 + seed), 3, seed))
    print("사전학습 씨드", seed, f"{round(time.time() - t0)}초", flush=True)
torch.save([n.state_dict() for n in pre], pf)
t.cv("nostaged", pf.name, 3, 100, tag_extra="_v3r15d")
export(t.V2 / "role_v2_nostaged_v3r15d_all.pt", MODELS / "tile-roles-v3r15d.onnx")
scenes = [s for s in t.load() if not s["staged"]]
fs = rs.folds(sorted(json.loads((rs.OUT / "labels.json").read_text(encoding="utf-8"))))
for fold, names in fs.items():
    fk = {"오전": "am", "오후A": "pmA", "오후B": "pmB"}[fold]
    tr = [s for s in scenes if s["name"] not in set(names)]
    nets = [rs.train(t.train_set(tr, 3, seed), 100, seed, pre[seed], 3e-4) for seed in range(3)]
    pt = t.V2 / f"role_v3r15d_opfold_{fk}.pt"
    torch.save([n.state_dict() for n in nets], pt)
    export(pt, MODELS / f"tile-roles-v3r15d_fold_{fk}.onnx")
    print("운영 나눔", fk, f"{round(time.time() - t0)}초", flush=True)
print("끝", f"{round(time.time() - t0)}초")
