"""캐글 GPU 에서 YOLO26n 앞면·뒷면 2종 검출기를 학습한다(2026-11-04, 6회차, metrics 표 1-67). det_build.py --rim-blank --neg --backs 데이터셋(ds_r6).
det_kernel/train_det.py(1종, 5회차)를 그대로 복사하고 종류만 2개(0 face, 1 back)로 — 나눔·에폭·증강이 같아 5회차와 앞면을 나란히 비교한다.
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
print("이미지", len(images), "총 바이트", sum(p.stat().st_size for p in images), flush=True)  # 로컬 데이터셋과 대조(이전 버전으로 도는 실수 막기)


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
    # 증강본은 학습에만, 시험은 원본 토막만. 4회차(2026-11-04) 白 증강은 재료가 fold 별로 다르다: __ra(재료 오전·기타)는 fold_a·final, __rb(재료 오후·기타)는 fold_b·final
    # (시험 사진의 白 이 학습 사본에 붙는 누수를 막는다 — 3회차 __b 는 이걸 안 지켰다).
    aug = lambda p: p.stem.endswith(("__b", "__ra", "__rb"))
    skip = {"fold_a": "__rb", "fold_b": "__ra"}.get(fold)
    train = [p for p in images if part(photo(p)) not in held and not (skip and p.stem.endswith(skip))]
    val = [p for p in images if part(photo(p)) in held and not aug(p)] if held else [p for p in images if p.stem.endswith("__w")]
    (WORK / f"{fold}_train.txt").write_text("\n".join(map(str, train)))
    (WORK / f"{fold}_val.txt").write_text("\n".join(map(str, val)))
    yaml = WORK / f"{fold}.yaml"
    yaml.write_text(f"path: {WORK}\ntrain: {fold}_train.txt\nval: {fold}_val.txt\nnames:\n  0: face\n  1: back\n")
    print("==", fold, "train", len(train), "val", len(val), flush=True)
    model = YOLO("yolo26n.pt")
    model.train(data=str(yaml), imgsz=1280, epochs=60, patience=20, batch=8, device=0, workers=2, flipud=0.5, fliplr=0.5, degrees=8.0,
                project="/kaggle/working/runs", name=fold, exist_ok=True, plots=False, verbose=False)
    best = Path(f"/kaggle/working/runs/{fold}/weights/best.pt")
    shutil.copy(best, OUT / f"{fold}.pt")
    m = YOLO(str(best)).val(data=str(yaml), imgsz=1280, device=0, plots=False, verbose=False)
    summary[fold] = dict(train=len(train), val=len(val), precision=float(m.box.mp), recall=float(m.box.mr), map50=float(m.box.map50), map50_95=float(m.box.map), per_class_recall=[float(x) for x in m.box.r], per_class_map50=[float(x) for x in m.box.ap50])
    print(fold, summary[fold], flush=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    shutil.copy(f"/kaggle/working/runs/{fold}/results.csv", OUT / f"{fold}_results.csv")
    onnx = YOLO(str(best)).export(format="onnx", imgsz=1280, dynamic=True, simplify=True)
    shutil.copy(onnx, OUT / f"{fold}.onnx")

shutil.rmtree(WORK)
shutil.rmtree("/kaggle/working/runs")
print("끝", summary)
