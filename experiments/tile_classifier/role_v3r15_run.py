"""생성기 v3 + 회전 ±15°(ROLE_SYNTH_V3_ROT=15) 사전학습 → 연출 뺀 33장 4겹 미세 조정 → 운영 나눔 fold ONNX(2026-11-09, metrics 표 1-132·1-133).
캐글 커널(role_kernel_v3/run_role_v3.py)과 같은 설정을 노트북에서: 합성 8,000장면 × 3 epoch(씨드 3, lr 1e-3) → 100 epoch·lr 3e-4·변형 사본 3.
  ROLE_SYNTH_V3_ROT=15 python -I -X utf8 experiments/tile_classifier/role_v3r15_run.py
출력 data/role/pre_synth8k_v3r15.pt, data/role/v2/cv_nostaged_v3r15.json, server_bench/models/tile-roles-v3r15{,_fold_*}.onnx
"""
import json, os, sys, time
from pathlib import Path
import torch
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs, role_synth_v3 as g, role_v2_train as t
from role_v3_export import export, MODELS
assert g.ROT == "15", "ROLE_SYNTH_V3_ROT=15 로 실행"
sys.stdout.reconfigure(encoding="utf-8")
torch.set_num_threads(8)
t0 = time.time()
pf = rs.OUT / "pre_synth8k_v3r15.pt"
pre = []
for seed in range(3):
    pre.append(rs.train(g.dataset(8000, 100 + seed), 3, seed))
    print("사전학습 씨드", seed, f"{round(time.time() - t0)}초", flush=True)
torch.save([n.state_dict() for n in pre], pf)
t.cv("nostaged", pf.name, 3, 100, tag_extra="_v3r15")
export(t.V2 / "role_v2_nostaged_v3r15_all.pt", MODELS / "tile-roles-v3r15.onnx")
scenes = [s for s in t.load() if not s["staged"]]
fs = rs.folds(sorted(json.loads((rs.OUT / "labels.json").read_text(encoding="utf-8"))))
for fold, names in fs.items():
    fk = {"오전": "am", "오후A": "pmA", "오후B": "pmB"}[fold]
    tr = [s for s in scenes if s["name"] not in set(names)]
    nets = [rs.train(t.train_set(tr, 3, seed), 100, seed, pre[seed], 3e-4) for seed in range(3)]
    pt = t.V2 / f"role_v3r15_opfold_{fk}.pt"
    torch.save([n.state_dict() for n in nets], pt)
    export(pt, MODELS / f"tile-roles-v3r15_fold_{fk}.onnx")
    print("운영 나눔", fk, f"{round(time.time() - t0)}초", flush=True)
print("끝", f"{round(time.time() - t0)}초")
