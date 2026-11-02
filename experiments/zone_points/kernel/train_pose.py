"""캐글 GPU 에서 YOLO26n-pose 로 탁자 8점을 학습한다(2026-11-02). build_ds.py 데이터셋을 쓴다.
카메라 설치를 하나씩 뺀다: 시험 = 그 설치, 검증 = 다음 설치, 나머지 + 음성 = 학습. 시험 답을 fold 별로 저장해 노트북에서 채점한다. 결과 /kaggle/working/out/.
모자이크는 끈다(탁자 하나가 화면을 채우는 문제). 번호가 사진 기준이라 상하 뒤집기·큰 회전은 쓰지 않는다.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "ultralytics>=8.4"], check=True)
from ultralytics import YOLO  # noqa: E402

SRC = next(Path("/kaggle/input").rglob("index.json")).parent
WORK = Path("/kaggle/working/ds")
OUT = Path("/kaggle/working/out")
OUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(SRC, WORK, dirs_exist_ok=True)  # 입력은 읽기 전용이라 라벨 캐시를 못 쓴다

index = json.loads((WORK / "index.json").read_text(encoding="utf-8"))
VAL_OF = {"s0": "s1", "s1": "s3", "s3": "s4", "s4": "s5", "s5": "s8", "s8": "s13", "s13": "s14", "s14": "s0", "gal": "s4"}
LIMIT_S = 10 * 3600
start = time.time()
summary = {}
for fold, val_setup in VAL_OF.items():
    if time.time() - start > LIMIT_S:
        print("시간 초과로 멈춤", fold, flush=True)
        break
    path = lambda names: [str(WORK / "images" / f"{n}.jpg") for n in names]
    test = [n for n, r in index.items() if r["setup"] == fold]
    val = [n for n, r in index.items() if r["setup"] == val_setup]
    train = [n for n, r in index.items() if r["setup"] not in (fold, val_setup)]
    (WORK / f"{fold}_train.txt").write_text("\n".join(path(train)))
    (WORK / f"{fold}_val.txt").write_text("\n".join(path(val)))
    yaml = WORK / f"{fold}.yaml"
    yaml.write_text(f"path: {WORK}\ntrain: {fold}_train.txt\nval: {fold}_val.txt\nkpt_shape: [8, 3]\nflip_idx: [1, 0, 3, 2, 5, 4, 7, 6]\nnames:\n  0: table\n")
    print("==", fold, "train", len(train), "val", len(val), "test", len(test), flush=True)
    t0 = time.time()
    model = YOLO("yolo26n-pose.pt")
    model.train(data=str(yaml), imgsz=960, epochs=80, patience=25, batch=16, device=0, workers=2, mosaic=0.0, degrees=8.0, translate=0.2, scale=0.4, perspective=0.0003, fliplr=0.5, flipud=0.0,
                project="/kaggle/working/runs", name=fold, exist_ok=True, plots=False, verbose=False)
    best = Path(f"/kaggle/working/runs/{fold}/weights/best.pt")
    shutil.copy(best, OUT / f"{fold}.pt")
    infer = YOLO(str(best))
    preds = {}
    for n, res in zip(test, infer.predict(path(test), imgsz=960, conf=0.001, device=0, verbose=False, stream=True)):
        if len(res.boxes) == 0:
            preds[n] = None
            continue
        i = int(res.boxes.conf.argmax())
        preds[n] = {"conf": float(res.boxes.conf[i]), "xyn": res.keypoints.xyn[i].tolist(), "kconf": res.keypoints.conf[i].tolist()}
    (OUT / f"preds_{fold}.json").write_text(json.dumps(preds))
    summary[fold] = dict(train=len(train), val=len(val), test=len(test), seconds=round(time.time() - t0))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    shutil.copy(f"/kaggle/working/runs/{fold}/results.csv", OUT / f"{fold}_results.csv")
    print(fold, summary[fold], flush=True)

shutil.rmtree(WORK)
