"""역할 모델 v3 학습을 캐글 커널 하나로 묶는다(2026-11-09, metrics 표 1-128). 노트북을 끄고도 돌게.

커널(run_role_v3.py) = 아래 파일을 zip·base64 로 품고, 캐글에서 풀어 학습한다:
  role_set.py · role_synth_v3.py · role_v2_train.py · labels_v2.json · field_tokens.json(테스트 15장 입력, 미리 계산) · truth.json
  + seat_grow / role_field 대역(가져오기만 되게 — 학습에 필요한 EXCLUDED·OUT 만).
학습: 생성기 v3 합성 8,000장면 × 3 epoch 사전학습(옛 가중치 없이 새로, 씨드 3) → 연출 뺀 33장 4겹 미세 조정(100 epoch, lr 3e-4, 변형 사본 3) + 33장 전부.
출력(/kaggle/working/out): cv_nostaged_v3pre.json, pre_synth8k_v3.pt, role_v2_nostaged_v3pre_{fold_*,all}.pt, log.txt

  python -I -X utf8 experiments/tile_classifier/role_kernel_v3/build.py          # run_role_v3.py 만들기
  SMOKE=1 python -I -X utf8 experiments/tile_classifier/role_kernel_v3/run_role_v3.py   # 노트북에서 작게 시험
  kaggle kernels push -p experiments/tile_classifier/role_kernel_v3
  kaggle kernels output jjh7757/mahjong-role-v3 -p <폴더>
"""
from __future__ import annotations

import base64
import io
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TC = HERE.parent
ROOT = TC.parents[1]
sys.path.insert(0, str(TC.parent / "speed"))
import seat_grow as sg  # noqa: E402

FILES = {
    "experiments/tile_classifier/role_set.py": TC / "role_set.py",
    "experiments/tile_classifier/role_synth_v3.py": TC / "role_synth_v3.py",
    "experiments/tile_classifier/role_v2_train.py": TC / "role_v2_train.py",
    "experiments/tile_classifier/data/role/v2/labels_v2.json": TC / "data/role/v2/labels_v2.json",
    "experiments/tile_classifier/data/role/v2/field_tokens.json": TC / "data/role/v2/field_tokens.json",
    "experiments/visit_20261031/truth.json": ROOT / "experiments/visit_20261031/truth.json",
}
STUBS = {
    "experiments/speed/seat_grow.py": f'"""대역: 학습에 필요한 EXCLUDED 만(원본 experiments/speed/seat_grow.py)."""\nEXCLUDED = {sorted(sg.EXCLUDED)!r}\n\n\ndef scenes():\n    return []\n',
    "experiments/tile_classifier/role_field.py": '"""대역: role_v2_train 가져오기용(테스트 15장 입력은 field_tokens.json 으로 미리 계산)."""\nfrom pathlib import Path\n\nOUT = Path(__file__).resolve().parent / "data" / "role" / "field"\n',
}

RUNNER = r'''"""캐글 커널: 역할 모델 v3 사전학습 + v2 라벨 33장 미세 조정(만든 곳 experiments/tile_classifier/role_kernel_v3/build.py)."""
import base64, io, json, os, shutil, sys, time, zipfile
from pathlib import Path

SMOKE = os.environ.get("SMOKE") == "1"
WORK = Path("/tmp/mc") if Path("/kaggle").exists() else Path(os.environ.get("TEMP", "/tmp")) / "mc_role_v3"
OUTD = Path("/kaggle/working/out") if Path("/kaggle").exists() else WORK / "out"
if WORK.exists():
    shutil.rmtree(WORK)
zipfile.ZipFile(io.BytesIO(base64.b64decode(BUNDLE))).extractall(WORK)
OUTD.mkdir(parents=True, exist_ok=True)
TC = WORK / "experiments" / "tile_classifier"
sys.path.insert(0, str(TC))
log = open(OUTD / "log.txt", "a", encoding="utf-8")


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


import numpy as np
import torch
import role_set as rs
import role_synth_v3 as g
import role_v2_train as t

FT = json.loads((TC / "data/role/v2/field_tokens.json").read_text(encoding="utf-8"))
t.field_tokens = lambda: [dict(name=s["name"], x=np.array(s["x"], np.float32), items=s["items"]) for s in FT]
NSYN, SYN_EP, EP, SEEDS = (60, 1, 2, 2) if SMOKE else (8000, 3, 100, 3)
torch.set_num_threads(max(1, os.cpu_count() or 4))
say("시작", time.strftime("%Y-%m-%d %H:%M:%S"), "SMOKE", SMOKE, "cpu", os.cpu_count(), "torch", torch.__version__)
t0 = time.time()
pre = []
for seed in range(SEEDS):
    syn = g.dataset(NSYN, 100 + seed)
    say("합성 v3", len(syn), "장면 씨드", seed, f"{round(time.time() - t0)}초")
    pre.append(rs.train(syn, SYN_EP, seed))
    say("사전학습 끝 씨드", seed, f"{round(time.time() - t0)}초")
torch.save([n.state_dict() for n in pre], rs.OUT / "pre_synth8k_v3.pt")
shutil.copy(rs.OUT / "pre_synth8k_v3.pt", OUTD / "pre_synth8k_v3.pt")
_train = rs.train
t.cv("nostaged", "pre_synth8k_v3.pt", 3, EP)
res = json.loads((t.V2 / "cv_nostaged.json").read_text(encoding="utf-8"))
res["cfg"] = "nostaged_v3pre"
res["pre"] = "pre_synth8k_v3.pt(생성기 v3 8000×3, 커널에서 새로)"
(OUTD / "cv_nostaged_v3pre.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
for p in t.V2.glob("role_v2_nostaged_*.pt"):
    shutil.copy(p, OUTD / p.name.replace("nostaged", "nostaged_v3pre"))
say("끝", res["cv"], "테스트 15장", res["field"]["total"], f"{round(time.time() - t0)}초")
'''


def main() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in FILES.items():
            z.write(src, arc)
        for arc, text in STUBS.items():
            z.writestr(arc, text)
    b64 = base64.b64encode(buf.getvalue()).decode()
    (HERE / "run_role_v3.py").write_text(f'BUNDLE = "{b64}"\n' + RUNNER, encoding="utf-8")
    print("run_role_v3.py", len(b64) // 1024, "KB")


if __name__ == "__main__":
    main()
