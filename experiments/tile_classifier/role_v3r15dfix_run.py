"""v3r15dfix(2026-11-10, metrics 표 1-157): v3r15d 와 같은 설정·사전학습·씨드로, 고친 153311 라벨(4p 눕힌 쯔모 화료패 hand → loose)만 넣어 다시 미세 조정.
  ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 python -I -X utf8 experiments/tile_classifier/role_v3r15dfix_run.py
"""
import json, sys, time
from pathlib import Path
import torch
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs, role_synth_v3 as g, role_v2_train as t
from role_v3_export import export, MODELS
assert t.SHIFT_ON and g.ROT == "15" and g.DROP_SAFE and rs.DROP_SAFE and g.OTHER_NEG and rs.OTHER_NEG, "ROLE_OTHER_NEG=1 ROLE_DROP_SAFE=1 ROLE_LOOSE_SHIFT=1 ROLE_SYNTH_V3_ROT=15 로 실행"
lab = json.loads((t.V2 / "labels_v2.json").read_text(encoding="utf-8"))["20261107_153311"]
assert lab["items"][6]["role"] == "loose" and lab["items"][6]["box"] == [2614, 2427, 113, 84], "153311 라벨이 고쳐져 있지 않음"
sys.stdout.reconfigure(encoding="utf-8")
torch.set_num_threads(8)
t0 = time.time()
pf = rs.OUT / "pre_synth8k_v3r15d.pt"  # 합성만으로 한 사전학습 — 실제 라벨과 무관해 그대로 씀
pre = rs.load_nets(pf)
t.cv("nostaged", pf.name, 3, 100, tag_extra="_v3r15dfix")
export(t.V2 / "role_v2_nostaged_v3r15dfix_all.pt", MODELS / "tile-roles-v3r15dfix.onnx")
scenes = [s for s in t.load() if not s["staged"]]
fs = rs.folds(sorted(json.loads((rs.OUT / "labels.json").read_text(encoding="utf-8"))))
for fold, names in fs.items():
    fk = {"오전": "am", "오후A": "pmA", "오후B": "pmB"}[fold]
    tr = [s for s in scenes if s["name"] not in set(names)]
    nets = [rs.train(t.train_set(tr, 3, seed), 100, seed, pre[seed], 3e-4) for seed in range(3)]
    pt = t.V2 / f"role_v3r15dfix_opfold_{fk}.pt"
    torch.save([n.state_dict() for n in nets], pt)
    export(pt, MODELS / f"tile-roles-v3r15dfix_fold_{fk}.onnx")
    print("운영 나눔", fk, f"{round(time.time() - t0)}초", flush=True)
print("끝", f"{round(time.time() - t0)}초")
