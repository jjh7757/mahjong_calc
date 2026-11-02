"""패 크롭 분류기 기준값(2026-11-01, 노트북 CPU). build_crops.py 다음에.

모델: torchvision MobileNetV3 Small(ImageNet 사전학습) 37종. 나누기 두 가지:
  세트 분리  B·C·D / 매장 오전 / 매장 오후 중 하나를 빼고 학습, 3 시드
  장면 분리  장면 하나(같은 손패의 사진은 함께)를 빼고 학습, 1 시드 — 같은 날 사진이 학습에 있어 낙관적
비교(학습 없음, 같은 크롭): YOLO11 s(운영 모델)의 패 종류 출력, HaseLab ResNet-50(로컬 실험만).
채점: 패 단위, 사진 단위(라벨된 패가 전부 맞음). 학습에 없는 종류의 패는 따로 센다.
  python -I experiments/tile_classifier/train.py [--base]
결과 experiments/tile_classifier/data/results.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image
from torch import nn
from torchvision import transforms as T

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CROPS = DATA / "crops"
sys.path.insert(0, str(HERE.parents[0] / "yolo"))
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")

CLASSES = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + ["0m", "0p", "0s"] + [f"{n}z" for n in range(1, 8)]
SIZE = 128
EPOCHS = 40
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
SAME_HAND = {"k25": "B", "k28": "B", "k15": "C", "k26": "C", "k12": "D", "k16": "D"}


def square(im: Image.Image, size: int = SIZE) -> Image.Image:
    im = im.copy()
    im.thumbnail((size, size))
    out = Image.new("RGB", (size, size), (114, 114, 114))
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


AUG = T.Compose([T.RandomAffine(8, translate=(0.06, 0.06), scale=(0.9, 1.1), fill=114), T.ColorJitter(0.25, 0.25, 0.2, 0.02),
                 T.RandomApply([T.GaussianBlur(3, (0.3, 1.2))], 0.3), T.ToTensor(), T.Normalize(MEAN, STD)])
PLAIN = T.Compose([T.ToTensor(), T.Normalize(MEAN, STD)])


def train(items: list[dict], images: dict, seed: int) -> nn.Module:
    torch.manual_seed(seed)
    np.random.seed(seed)
    net = torchvision.models.mobilenet_v3_small(weights=torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    net.classifier[3] = nn.Linear(net.classifier[3].in_features, len(CLASSES))
    freq = Counter(x["tile"] for x in items)
    prob = np.array([1 / freq[x["tile"]] for x in items])
    prob /= prob.sum()
    opt = torch.optim.AdamW(net.parameters(), lr=5e-4, weight_decay=0.01)
    steps = max(1, len(items) // 32)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, EPOCHS * steps)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    net.train()
    for _ in range(EPOCHS):
        for _ in range(steps):
            idx = np.random.choice(len(items), 32, p=prob)
            x = torch.stack([AUG(images[items[i]["file"]]) for i in idx])
            y = torch.tensor([CLASSES.index(items[i]["tile"]) for i in idx])
            opt.zero_grad()
            loss_fn(net(x), y).backward()
            opt.step()
            sched.step()
    return net.eval()


def predict(net: nn.Module, items: list[dict], images: dict) -> list[str]:
    with torch.no_grad():
        x = torch.stack([PLAIN(images[i["file"]]) for i in items])
        return [CLASSES[k] for k in net(x).argmax(1).tolist()]


def score(items: list[dict], preds: list[str], seen: set[str] | None = None) -> dict:
    ok = [p == x["tile"] for p, x in zip(preds, items)]
    scenes: dict[str, bool] = {}
    for good, x in zip(ok, items):
        scenes[x["scene"]] = scenes.get(x["scene"], True) and good
    unseen = [i for i, x in enumerate(items) if seen is not None and x["tile"] not in seen]
    return dict(n=len(items), ok=sum(ok), scenes=len(scenes), scene_ok=sum(scenes.values()), unseen=len(unseen), unseen_ok=sum(ok[i] for i in unseen),
                wrong=[(x["file"], x["tile"], p) for p, x, good in zip(preds, items, ok) if not good])


def baselines(items: list[dict]) -> dict:
    import run_yolo as ry
    m = ry.Nikmomo("s")
    y11 = []
    for x in items:
        bgr = np.asarray(Image.open(CROPS / x["file"]).convert("RGB"))[:, :, ::-1]
        ch, cw = bgr.shape[:2]
        S = max(ch, cw) * 8  # 패가 입력의 약 1/8 이 되게 회색 바탕 가운데에. 크롭을 꽉 채우면 학습 때 크기와 달라 거의 못 읽는다(첫 측정 1/259)
        canvas = np.full((S, S, 3), 114, np.uint8)
        canvas[(S - ch) // 2:(S - ch) // 2 + ch, (S - cw) // 2:(S - cw) // 2 + cw] = bgr
        d, _ = m.predict(canvas, conf=0.05)
        y11.append(max(d, key=lambda t: t[1])[0] if d else "없음")
    h = ry.HaseLab()
    with torch.no_grad():
        tf = T.Compose([T.Resize((224, 224)), T.ToTensor(), T.Normalize(MEAN, STD)])
        xs = torch.stack([tf(Image.open(CROPS / x["file"]).convert("RGB")) for x in items])
        hl = [ry.HASE_CLASSES[k] for b in xs.split(16) for k in h.net(b).argmax(1).tolist()]
    return {"YOLO11 s 패 종류": y11, "HaseLab ResNet-50": hl}


def report(label: str, s: dict) -> None:
    print(f"{label}: 패 {s['ok']}/{s['n']} ({100 * s['ok'] / s['n']:.1f}%) 사진 {s['scene_ok']}/{s['scenes']}" + (f" 학습에 없는 종류 {s['unseen']}장" if s["unseen"] else ""), flush=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    images = {x["file"]: square(Image.open(CROPS / x["file"]).convert("RGB")) for x in index}
    print("크롭", len(index), "장면", len({x["scene"] for x in index}), "없는 종류", [c for c in CLASSES if c not in {x["tile"] for x in index}], flush=True)
    res: dict = {"holdout": [], "scene": []}
    t0 = time.perf_counter()

    for name, preds in baselines(index).items():
        res[name] = {}
        for p in ("bcd", "am", "pm"):
            v = [(x, q) for x, q in zip(index, preds) if x["part"] == p]
            s = score([a for a, _ in v], [b for _, b in v])
            res[name][p] = s
            report(f"{name} {p}", s)
    print("기준 비교 끝", round(time.perf_counter() - t0), "초", flush=True)
    if "--base" in sys.argv:  # 학습 없이 비교만(결과 파일은 안 건드림)
        return

    for p in ("bcd", "am", "pm"):
        for seed in (0, 1, 2):
            tr = [x for x in index if x["part"] != p]
            te = [x for x in index if x["part"] == p]
            t1 = time.perf_counter()
            net = train(tr, images, seed)
            s = score(te, predict(net, te, images), {x["tile"] for x in tr})
            s.update(part=p, seed=seed, secs=round(time.perf_counter() - t1))
            res["holdout"].append(s)
            report(f"세트 분리 {p} 시드 {seed} ({s['secs']}초)", s)
            (DATA / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    groups = sorted({SAME_HAND.get(x["scene"], x["scene"]) for x in index})
    for g in groups:
        tr = [x for x in index if SAME_HAND.get(x["scene"], x["scene"]) != g]
        te = [x for x in index if SAME_HAND.get(x["scene"], x["scene"]) == g]
        s = score(te, predict(train(tr, images, 0), te, images), {x["tile"] for x in tr})
        s.update(group=g, part=te[0]["part"])
        res["scene"].append(s)
        report(f"장면 분리 {g}", s)
        (DATA / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("== 요약")
    for p in ("bcd", "am", "pm"):
        v = [s for s in res["holdout"] if s["part"] == p]
        print(f"세트 분리 {p}: 패 {statistics.mean(s['ok'] for s in v):.1f}/{v[0]['n']}, 사진 {statistics.mean(s['scene_ok'] for s in v):.1f}/{v[0]['scenes']}, 학습에 없는 종류 {v[0]['unseen']}장")
    tot, ok = sum(s["n"] for s in res["scene"]), sum(s["ok"] for s in res["scene"])
    un, un_ok = sum(s["unseen"] for s in res["scene"]), sum(s["unseen_ok"] for s in res["scene"])
    print(f"장면 분리: 패 {ok}/{tot} ({100 * ok / tot:.1f}%), 학습에 있는 종류만 {ok - un_ok}/{tot - un} ({100 * (ok - un_ok) / (tot - un):.1f}%), 사진 {sum(s['scene_ok'] for s in res['scene'])}/{sum(s['scenes'] for s in res['scene'])}")
    print("장면 분리 틀린 패", Counter((w[1], w[2]) for s in res["scene"] for w in s["wrong"]).most_common(25))
    print("총", round(time.perf_counter() - t0), "초")


if __name__ == "__main__":
    main()
