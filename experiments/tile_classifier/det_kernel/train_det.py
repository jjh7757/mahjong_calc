"""캐글 GPU 에서 YOLO26n "앞면 패" 1종 검출기를 학습한다(2026-11-01). det_build.py 데이터셋을 쓴다.
fold_a·fold_b 는 시간대를 나눈 평가용, final 은 전부로 학습한 것. 결과 /kaggle/working/out/.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4"], check=True)
from ultralytics import YOLO  # noqa: E402

SRC = next(Path("/kaggle/input").rglob("images")).parent
WORK = Path("/kaggle/working/ds")
OUT = Path("/kaggle/working/out")
OUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(SRC, WORK, dirs_exist_ok=True)  # 입력은 읽기 전용이라 라벨 캐시를 못 쓴다

BCD = {"k25", "k28", "k15", "k26", "k12", "k16"}
images = sorted((WORK / "images").glob("*.jpg"))


def photo(p: Path) -> str:
    return p.stem.split("__")[0]


def part(name: str) -> str:
    if name in BCD:
        return "bcd"
    if name.startswith("k"):
        return "other"
    return "am" if name < "20261031_14" else "pm"


FOLDS = {"fold_a": ("pm", "bcd"), "fold_b": ("am", "bcd"), "final": ()}
summary = {}
for fold, held in FOLDS.items():
    train = [p for p in images if part(photo(p)) not in held]
    val = [p for p in images if part(photo(p)) in held] if held else [p for p in images if p.stem.endswith("__w")]
    (WORK / f"{fold}_train.txt").write_text("\n".join(map(str, train)))
    (WORK / f"{fold}_val.txt").write_text("\n".join(map(str, val)))
    yaml = WORK / f"{fold}.yaml"
    yaml.write_text(f"path: {WORK}\ntrain: {fold}_train.txt\nval: {fold}_val.txt\nnames:\n  0: tile\n")
    print("==", fold, "train", len(train), "val", len(val), flush=True)
    model = YOLO("yolo26n.pt")
    model.train(data=str(yaml), imgsz=1280, epochs=60, patience=20, batch=8, single_cls=True, device=0, workers=2, flipud=0.5, fliplr=0.5, degrees=8.0,
                project="/kaggle/working/runs", name=fold, exist_ok=True, plots=False, verbose=False)
    best = Path(f"/kaggle/working/runs/{fold}/weights/best.pt")
    shutil.copy(best, OUT / f"{fold}.pt")
    m = YOLO(str(best)).val(data=str(yaml), imgsz=1280, single_cls=True, device=0, plots=False, verbose=False)
    summary[fold] = dict(train=len(train), val=len(val), precision=float(m.box.mp), recall=float(m.box.mr), map50=float(m.box.map50), map50_95=float(m.box.map))
    print(fold, summary[fold], flush=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    shutil.copy(f"/kaggle/working/runs/{fold}/results.csv", OUT / f"{fold}_results.csv")
    onnx = YOLO(str(best)).export(format="onnx", imgsz=1280, dynamic=True, simplify=True)
    shutil.copy(onnx, OUT / f"{fold}.onnx")

shutil.rmtree(WORK)
shutil.rmtree("/kaggle/working/runs")
print("끝", summary)
