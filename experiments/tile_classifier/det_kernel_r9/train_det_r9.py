"""캐글 GPU 에서 9회차 검출기(개선 계획 7-2, metrics 표 1-97): 8회차(det_kernel_r8/train_det_r8.py)와 미세 조정은 똑같이 하고, 그 앞에 합성 장면 사전학습만 더한다.
- 합성: 데이터셋 mahjong-scene-synth-r9 의 scene_synth.py + mat/ 로 이 커널 안에서 만든다(풀마다 학습 8,000 + 검증 200, 시드 고정).
  누수 금지 — fold_a(시험 오후·B·C·D) = 풀 a(오전·기타 사진 재료), fold_b(시험 오전·B·C·D) = 풀 b(오후·기타), final = 풀 all.
- 사전학습: yolo26n-obb.pt 에서 합성으로 PRE_EPOCHS 에폭(imgsz·batch·뒤집기·회전 = 8회차와 같음, close_mosaic 2, 조기 종료 없음, last.pt 사용 — 실제 시험 사진으로 고르지 않는다).
- 미세 조정: 8회차와 같은 데이터(mahjong-tile-obb-r8)·나눔·설정, 시작 가중치만 사전학습 last.pt. ultralytics 는 8회차 로그와 같은 8.4.202 로 고정.
결과 /kaggle/working/out/{fold}.pt·.onnx·{fold}_results.csv·pre_{fold}_results.csv·summary.json.
R9_SMOKE=1 이면 노트북 CPU 에서 작게(합성 16장·1 에폭·imgsz 320) 돌려 코드만 확인한다(R9_INPUT·R9_WORK 로 경로).
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SMOKE = os.environ.get("R9_SMOKE") == "1"
if not SMOKE:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics==8.4.202"], check=True)
from ultralytics import YOLO  # noqa: E402

INP = Path(os.environ.get("R9_INPUT", "/kaggle/input"))
WORKDIR = Path(os.environ.get("R9_WORK", "/kaggle/working"))
TMP = Path(os.environ.get("R9_TMP", "/tmp/r9"))
SRC = next(p for p in INP.rglob("images") if (p.parent / "labels").is_dir() and not (p.parent / "mat").exists()).parent
SYN_CODE = next(INP.rglob("scene_synth.py"))
MAT = next(p.parent for p in INP.rglob("index.json") if (p.parent / "faces").is_dir())
WORK = WORKDIR / "ds"
OUT = WORKDIR / "out"
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)
shutil.copytree(SRC, WORK, dirs_exist_ok=True)  # 입력은 읽기 전용이라 라벨 캐시를 못 쓴다
CODE = TMP / "code"
CODE.mkdir(exist_ok=True)
shutil.copy(SYN_CODE, CODE / "scene_synth.py")

N_TRAIN, N_VAL = (16, 4) if SMOKE else (8000, 200)
PRE_EPOCHS = 1 if SMOKE else 6
EPOCHS = 1 if SMOKE else 60
IMGSZ = 320 if SMOKE else 1280
DEVICE = "cpu" if SMOKE else 0
BCD = {"k25", "k28", "k15", "k26", "k12", "k16"}
images = sorted((WORK / "images").glob("*.jpg"))
if SMOKE:
    images = images[::24]
print("이미지", len(images), "총 바이트", sum(p.stat().st_size for p in images), flush=True)  # 로컬 ds_r8 과 대조(960 · 536536679)
print("합성 코드", SYN_CODE, "재료", MAT, flush=True)


def photo(p: Path) -> str:
    return p.stem.split("__")[0]


def part(name: str) -> str:
    if name in BCD:
        return "bcd"
    if name.startswith("k"):
        return "other"
    return "am" if name < "20261031_14" else "pm"


def gen_cmd(pool: str, workers: int) -> str:
    d = TMP / f"syn_{pool}"
    base = f"{sys.executable} -X utf8 {CODE / 'scene_synth.py'} det --pool {pool} --mat {MAT} --workers {workers}"
    return f"{base} --n {N_TRAIN} --out {d}/train && {base} --n {N_VAL} --start 100000 --out {d}/val && {sys.executable} -c \"import pathlib; pathlib.Path(r'{d}/done').touch()\""


def wait_pool(pool: str) -> Path:
    d = TMP / f"syn_{pool}"
    while not (d / "done").exists():
        time.sleep(20)
    return d


t0 = time.time()
# 풀 a 는 앞에서 4코어로, b·all 은 학습과 겹쳐 뒤에서 3코어로 만든다
subprocess.run(gen_cmd("a", 4), shell=True, check=True)
print("합성 a 끝", round(time.time() - t0), "초", flush=True)
bg = subprocess.Popen(f"({gen_cmd('b', 3)}) && ({gen_cmd('all', 3)})", shell=True)

FOLDS = {"fold_a": (("pm", "bcd"), "a"), "fold_b": (("am", "bcd"), "b"), "final": ((), "all")}
summary = {}
for fold, (held, pool) in FOLDS.items():
    # --- 사전학습(합성)
    syn = wait_pool(pool)
    n_box = sum(len(p.read_text().splitlines()) for p in (syn / "train" / "labels").glob("*.txt"))
    sy = TMP / f"syn_{pool}.yaml"
    sy.write_text(f"path: {syn}\ntrain: train/images\nval: val/images\nnames:\n  0: face\n  1: back\n")
    print("==", fold, "사전학습 풀", pool, "합성", len(list((syn / 'train' / 'images').glob('*.jpg'))), "상자", n_box, round(time.time() - t0), "초", flush=True)
    YOLO("yolo26n-obb.pt").train(data=str(sy), imgsz=IMGSZ, epochs=PRE_EPOCHS, patience=100, batch=8, device=DEVICE, workers=2, flipud=0.5, fliplr=0.5, degrees=8.0,
                                 close_mosaic=2, project=str(WORKDIR / "runs"), name=f"pre_{fold}", exist_ok=True, plots=False, verbose=False)
    init = WORKDIR / "runs" / f"pre_{fold}" / "weights" / "last.pt"
    shutil.copy(WORKDIR / "runs" / f"pre_{fold}" / "results.csv", OUT / f"pre_{fold}_results.csv")
    if pool != "all":  # all 은 마지막이라 지울 필요 없음, a·b 는 자리 비우기
        shutil.rmtree(syn, ignore_errors=True)
    # --- 미세 조정: det_kernel_r8 과 같은 줄(시작 가중치만 init)
    aug = lambda p: p.stem.endswith(("__b", "__ra", "__rb", "__c"))  # __c: 8회차 재색칠 사본
    skip = {"fold_a": "__rb", "fold_b": "__ra"}.get(fold)
    train = [p for p in images if part(photo(p)) not in held and not (skip and p.stem.endswith(skip))]
    val = [p for p in images if part(photo(p)) in held and not aug(p)] if held else [p for p in images if p.stem.endswith("__w")]
    (WORK / f"{fold}_train.txt").write_text("\n".join(map(str, train)))
    (WORK / f"{fold}_val.txt").write_text("\n".join(map(str, val)))
    yaml = WORK / f"{fold}.yaml"
    yaml.write_text(f"path: {WORK}\ntrain: {fold}_train.txt\nval: {fold}_val.txt\nnames:\n  0: face\n  1: back\n")
    print("==", fold, "train", len(train), "val", len(val), round(time.time() - t0), "초", flush=True)
    model = YOLO(str(init))
    model.train(data=str(yaml), imgsz=IMGSZ, epochs=EPOCHS, patience=20, batch=8, device=DEVICE, workers=2, flipud=0.5, fliplr=0.5, degrees=8.0,
                project=str(WORKDIR / "runs"), name=fold, exist_ok=True, plots=False, verbose=False)
    best = WORKDIR / "runs" / fold / "weights" / "best.pt"
    shutil.copy(best, OUT / f"{fold}.pt")
    m = YOLO(str(best)).val(data=str(yaml), imgsz=IMGSZ, device=DEVICE, plots=False, verbose=False)
    summary[fold] = dict(train=len(train), val=len(val), pre_pool=pool, pre_images=N_TRAIN, pre_epochs=PRE_EPOCHS, pre_boxes=n_box,
                         precision=float(m.box.mp), recall=float(m.box.mr), map50=float(m.box.map50), map50_95=float(m.box.map),
                         per_class_recall=[float(x) for x in m.box.r], per_class_map50=[float(x) for x in m.box.ap50], secs=round(time.time() - t0))
    print(fold, summary[fold], flush=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    shutil.copy(WORKDIR / "runs" / fold / "results.csv", OUT / f"{fold}_results.csv")
    onnx = YOLO(str(best)).export(format="onnx", imgsz=IMGSZ, dynamic=True, simplify=not SMOKE)
    shutil.copy(onnx, OUT / f"{fold}.onnx")

bg.wait()
shutil.rmtree(WORK)
shutil.rmtree(WORKDIR / "runs")
shutil.rmtree(TMP, ignore_errors=True)
print("끝", round(time.time() - t0), "초", summary)
