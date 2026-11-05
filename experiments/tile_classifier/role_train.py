"""앞면 패 역할 분류기 학습·교차 검증(2026-11-03, 노트북 CPU, API 없음). metrics 표 1-56.

입력 = 패 한 장을 가운데 둔 주변 패치(패 폭의 PATCH 배 정사각형, SIZE px), 출력 = 역할 6종 확률.
모델 = torchvision MobileNetV3 Small(ImageNet 사전학습) — 종류 분류기(train.py)와 같다. 라벨 = role_label.py(규칙 자동 생성, other 는 뺌).
나누기 = 사진 단위 3겹(오전 10 / 오후 앞 8 / 오후 뒤 7), 각 겹은 나머지로 학습해 그 겹을 잰다.

  python -I -X utf8 experiments/tile_classifier/role_train.py [--epochs 12] [--patch 8] [--size 160] [--pos]
  --pos: 패 위치(0~1)·상자 크기를 보조 입력으로 넣는다(탁자 배치를 외우기 쉬워 기본은 끔)
결과 data/role/cv.json
"""
from __future__ import annotations

import argparse
import json
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
OUT = HERE / "data" / "role"
ROLES = ["hand", "meld", "river", "wall", "pair", "loose"]
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def folds(names: list[str]) -> dict[str, list[str]]:
    am = sorted(n for n in names if n[9:11] < "14")
    pm = sorted(n for n in names if n[9:11] >= "14")
    return {"오전": am, "오후A": pm[: len(pm) // 2], "오후B": pm[len(pm) // 2:]}


def patches(labels: dict, patch: float, size: int) -> list[dict]:
    items = []
    for name, rec in labels.items():
        im = Image.open(rec["path"]).convert("RGB")
        tw = float(np.median([min(it["box"][2], it["box"][3]) for it in rec["items"]]))
        r = patch * tw / 2
        for i, it in enumerate(rec["items"]):
            if it["role"] not in ROLES:
                continue
            x, y, w, h = it["box"]
            cx, cy = x + w / 2, y + h / 2
            crop = im.crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r)))  # 밖은 검정으로 채워진다
            crop = crop.resize((size, size), Image.BILINEAR)
            items.append(dict(name=name, i=i, role=it["role"], img=crop, pos=[cx / im.width, cy / im.height, w / im.width, h / im.height]))
    return items


class Net(nn.Module):
    def __init__(self, pos: bool):
        super().__init__()
        self.body = torchvision.models.mobilenet_v3_small(weights=torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
        feat = self.body.classifier[3].in_features
        self.body.classifier[3] = nn.Identity()
        self.pos = pos
        self.head = nn.Linear(feat + (4 if pos else 0), len(ROLES))

    def forward(self, x, p=None):
        f = self.body(x)
        if self.pos:
            f = torch.cat([f, p], 1)
        return self.head(f)


def train(items: list[dict], epochs: int, pos: bool, seed: int = 0) -> nn.Module:
    torch.manual_seed(seed)
    np.random.seed(seed)
    aug = T.Compose([T.RandomAffine(6, translate=(0.04, 0.04), scale=(0.92, 1.08)), T.ColorJitter(0.25, 0.25, 0.2, 0.02), T.ToTensor(), T.Normalize(MEAN, STD)])
    net = Net(pos)
    freq = Counter(x["role"] for x in items)
    prob = np.array([1 / np.sqrt(freq[x["role"]]) for x in items])  # 드문 역할을 더 자주(제곱근 균형)
    prob /= prob.sum()
    opt = torch.optim.AdamW(net.parameters(), lr=5e-4, weight_decay=0.01)
    steps = max(1, len(items) // 32)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs * steps)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    net.train()
    for _ in range(epochs):
        for _ in range(steps):
            idx = np.random.choice(len(items), 32, p=prob)
            x = torch.stack([aug(items[i]["img"]) for i in idx])
            p = torch.tensor([items[i]["pos"] for i in idx], dtype=torch.float32)
            y = torch.tensor([ROLES.index(items[i]["role"]) for i in idx])
            opt.zero_grad()
            loss_fn(net(x, p), y).backward()
            opt.step()
            sched.step()
    return net.eval()


def predict(net: nn.Module, items: list[dict]) -> list[tuple[str, float]]:
    plain = T.Compose([T.ToTensor(), T.Normalize(MEAN, STD)])
    out = []
    with torch.no_grad():
        for k in range(0, len(items), 64):
            chunk = items[k:k + 64]
            x = torch.stack([plain(it["img"]) for it in chunk])
            p = torch.tensor([it["pos"] for it in chunk], dtype=torch.float32)
            pr = torch.softmax(net(x, p), 1)
            for row in pr:
                j = int(row.argmax())
                out.append((ROLES[j], round(float(row[j]), 3)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--patch", type=float, default=8)
    ap.add_argument("--size", type=int, default=160)
    ap.add_argument("--pos", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(8)
    labels = json.loads((OUT / "labels.json").read_text(encoding="utf-8"))
    items = patches(labels, a.patch, a.size)
    print("표본", len(items), Counter(x["role"] for x in items), flush=True)
    fs = folds(list(labels))
    conf = {r: Counter() for r in ROLES}
    per_fold = {}
    wrong = []
    t0 = time.time()
    for fold, names in fs.items():
        test = [x for x in items if x["name"] in names]
        tr = [x for x in items if x["name"] not in names]
        net = train(tr, a.epochs, a.pos)
        preds = predict(net, test)
        ok = Counter()
        n = Counter()
        for x, (p, c) in zip(test, preds):
            n[x["role"]] += 1
            ok[x["role"]] += p == x["role"]
            conf[x["role"]][p] += 1
            if p != x["role"]:
                wrong.append((x["name"][-6:], x["i"], x["role"], p, c))
        per_fold[fold] = {r: f"{ok[r]}/{n[r]}" for r in ROLES if n[r]}
        print(fold, per_fold[fold], f"{round(time.time() - t0)}초", flush=True)
    total = {r: f"{sum(conf[r][r] for _ in [0])}/{sum(conf[r].values())}" for r in ROLES}
    print("합계", total)
    print("혼동", {r: dict(conf[r]) for r in ROLES})
    (OUT / f"cv{'_pos' if a.pos else ''}.json").write_text(json.dumps(dict(args=vars(a), n=len(items), per_fold=per_fold, total=total, confusion={r: dict(c) for r, c in conf.items()}, wrong=wrong), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
