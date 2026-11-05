"""캐글 GPU 에서 YOLO26n 앞면·뒷면 2종 검출기를 학습한다(2026-11-03). det_build_fb.py 데이터셋을 쓴다.
2차(2026-11-03): 라벨 = 1차 나눔 밖 검출 + 불일치 검수(det_merge_fb.py). 뒷면 시험 수치는 라벨이 1차 모델 검출에서 와서 부풀려진다(label_review3.md).
fold_am·fold_pm 은 10-31 오전·오후를 서로 시험, 10-24 k 사진은 같은 판이 겹쳐 둘 다 안 쓴다. fold_k 는 10-31 전부로 학습하고 처음 보는 날짜인 k 10장을 시험한다. final 은 전부로 학습한 배포 후보이고 수치는 학습 사진 점수라 표에 안 쓴다.
재색칠본(__c)은 학습에만, COCO128 50장은 패 없는 배경으로 학습에만 넣는다. 시험은 앱처럼 사진 통째(__w)만. 에폭을 고정하고 마지막 모델을 쓴다(시험 세트로 모델을 고르지 않는다). 결과 /kaggle/working/out/.
"""
import csv  # noqa: F401
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics==8.4.183"], check=True)
from ultralytics import YOLO  # noqa: E402

SRC = next(Path("/kaggle/input").rglob("images")).parent
WORK = Path("/kaggle/working/ds")
OUT = Path("/kaggle/working/out")
OUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(SRC, WORK, dirs_exist_ok=True)  # 입력은 읽기 전용이라 라벨 캐시를 못 쓴다
# 데이터셋 버전 확인: 통째 라벨의 앞면·뒷면 상자 수가 올린 값과 같아야 한다(11-03 2차 첫 시도가 처리 전 1차 데이터로 돈 일 때문)
EXPECT = (2243, 1817)
got = [0, 0]
for f in (WORK / "labels").glob("*__w.txt"):
    for line in f.read_text().splitlines():
        got[int(line.split()[0])] += 1
print("통째 라벨 앞면·뒷면", got, "기대", EXPECT, flush=True)
assert tuple(got) == EXPECT, "데이터셋 버전이 다르다"

zf = Path("/kaggle/working/coco128.zip")
urllib.request.urlretrieve("https://github.com/ultralytics/assets/releases/download/v0.0.0/coco128.zip", zf)
with zipfile.ZipFile(zf) as z:
    z.extractall("/kaggle/working/coco")
for p in sorted(Path("/kaggle/working/coco").rglob("*.jpg"))[:50]:
    shutil.copy(p, WORK / "images" / f"bg{p.name}")
    (WORK / "labels" / f"bg{p.stem}.txt").write_text("")
zf.unlink()

images = sorted((WORK / "images").glob("*.jpg"))
OCCLUDED = {"20261031_172424", "20261031_174020"}  # 손·팔 가림은 평가에서 뺀다(seat_grow.py 와 같음)


def photo(p: Path) -> str:
    return p.stem.split("__")[0]


def part(name: str) -> str:
    if name.startswith("bg"):
        return "bg"
    if name.startswith("k"):
        return "k"
    return "am" if name < "20261031_14" else "pm"


FOLDS = {"fold_am": (("pm",), "am"), "fold_pm": (("am",), "pm"), "fold_k": (("am", "pm"), "k"), "final": (("am", "pm", "k"), None)}
summary = {}
for fold, (use, held) in FOLDS.items():
    train = [p for p in images if part(photo(p)) in use or part(photo(p)) == "bg"]
    val = [p for p in images if p.stem.endswith("__w") and photo(p) not in OCCLUDED and (part(photo(p)) == held if held else part(photo(p)) != "bg")]
    (WORK / f"{fold}_train.txt").write_text("\n".join(map(str, train)))
    (WORK / f"{fold}_val.txt").write_text("\n".join(map(str, val)))
    yaml = WORK / f"{fold}.yaml"
    yaml.write_text(f"path: {WORK}\ntrain: {fold}_train.txt\nval: {fold}_val.txt\nnames:\n  0: face\n  1: back\n")
    print("==", fold, "train", len(train), "val", len(val), flush=True)
    model = YOLO("yolo26n.pt")
    model.train(data=str(yaml), imgsz=1280, epochs=40, patience=0, batch=8, device=0, workers=2, flipud=0.5, fliplr=0.5, degrees=8.0, perspective=0.0002, scale=0.5,
                project="/kaggle/working/runs", name=fold, exist_ok=True, plots=False, verbose=False)
    last = Path(f"/kaggle/working/runs/{fold}/weights/last.pt")
    shutil.copy(last, OUT / f"{fold}.pt")
    m = YOLO(str(last)).val(data=str(yaml), imgsz=1280, device=0, plots=False, verbose=False)
    summary[fold] = dict(train=len(train), val=len(val), precision=float(m.box.mp), recall=float(m.box.mr), map50=float(m.box.map50), map50_95=float(m.box.map),
                         per_class_map50=[float(x) for x in m.box.ap50], per_class_recall=[float(x) for x in m.box.r])
    print(fold, summary[fold], flush=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    shutil.copy(f"/kaggle/working/runs/{fold}/results.csv", OUT / f"{fold}_results.csv")
    onnx = YOLO(str(last)).export(format="onnx", imgsz=1280, dynamic=True, simplify=True)
    shutil.copy(onnx, OUT / f"{fold}.onnx")

shutil.rmtree(WORK)
shutil.rmtree("/kaggle/working/runs")
print("끝", summary)
