"""역할 모델 v3pre 를 서버 판정(2단계, metrics 표 1-121 a~d 를 표 1-129 뒤에)용 ONNX 로(2026-11-09).

  전체: 캐글 출력 role_v2_nostaged_v3pre_all.pt(연출 뺀 33장 전부) → server_bench/models/tile-roles-v3pre.onnx
  fold : 운영 나눔(role_set.folds — 10-31 labels.json 25장의 오전·오후A·오후B)에 맞춰, 그 fold 의 10-31 사진을 뺀 v2 라벨(연출 뺌)로
         같은 사전학습(pre_synth8k_v3.pt) + 같은 미세 조정(100 epoch, lr 3e-4, 변형 사본 3, 씨드 3) → tile-roles-v3pre_fold_{am,pmA,pmB}.onnx
         (앱 흐름 개발 32회·회귀 fold 가 이 fold 를 쓴다 — 시험 사진을 안 배운 모델)
  python -I -X utf8 experiments/tile_classifier/role_v3_export.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_set as rs  # noqa: E402
import role_v2_train as t  # noqa: E402

K3 = t.V2 / "kaggle_v3" / "out"
MODELS = HERE / "server_bench" / "models"


def export(pt: Path, onnx: Path) -> None:
    subprocess.run([sys.executable, "-I", "-X", "utf8", str(HERE / "role_export.py"), str(pt), str(onnx), "--seeds-out"], check=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(8)
    pre_file = rs.OUT / "pre_synth8k_v3.pt"
    if not pre_file.exists():
        pre_file.write_bytes((K3 / "pre_synth8k_v3.pt").read_bytes())
    pre = rs.load_nets(pre_file)
    scenes = [s for s in t.load() if not s["staged"]]
    fs = rs.folds(sorted(json.loads((rs.OUT / "labels.json").read_text(encoding="utf-8"))))
    export(K3 / "role_v2_nostaged_v3pre_all.pt", MODELS / "tile-roles-v3pre.onnx")
    t0 = time.time()
    for fold, names in fs.items():
        fk = {"오전": "am", "오후A": "pmA", "오후B": "pmB"}[fold]
        tr = [s for s in scenes if s["name"] not in set(names)]
        nets = [rs.train(t.train_set(tr, 3, seed), 100, seed, pre[seed], 3e-4) for seed in range(len(pre))]
        pt = t.V2 / f"role_v3pre_opfold_{fk}.pt"
        torch.save([n.state_dict() for n in nets], pt)
        export(pt, MODELS / f"tile-roles-v3pre_fold_{fk}.onnx")
        print(fk, "학습", len(tr), "뺀 10-31", len([s for s in scenes if s["name"] in set(names)]), f"{round(time.time() - t0)}초", flush=True)


if __name__ == "__main__":
    main()
