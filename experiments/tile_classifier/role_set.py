"""패 상자 집합 → 역할 모델(2026-11-03, 노트북 CPU, API 없음). 그림을 안 보고 상자 배치만으로 역할을 정한다.

입력 = 사진 한 장의 상자 전부(앞면 = role_label.py 라벨, 뒷면 = det_backs.py 상자). 상자마다 벡터:
  펠트 격자(x1·x2·y1·y2) 기준 0~1 좌표·크기, 화료자 자리가 아래로 오게 돌림, 뒷면 플래그, 눕힘 플래그, 리치봉 기기 중심과의 차.
모델 = Transformer 인코더(3층·폭 64·4머리), 상자끼리 서로 보고 앞면 상자마다 역할 6종 확률. 파라미터 약 10만.
라벨 = data/role/labels.json(규칙 자동 + review.json 사람 수정). other 는 손실에서 뺌.
나누기 = role_train.py 와 같은 사진 단위 3겹(오전 / 오후 앞 / 오후 뒤). 가림·사용자 문제 사진(seat_grow.EXCLUDED)은 채점에서 뺌.
채점 = (1) 라벨 대비 상자별 정확도·혼동, (2) 라벨과 무관한 truth.json 대비: 손패 줄 장수·울기 장수가 맞는 사진 수(규칙 라벨도 같이 잼).

  python -I -X utf8 experiments/tile_classifier/role_set.py [--epochs 300] [--seeds 3] [--no-backs]
  python -I -X utf8 experiments/tile_classifier/role_set.py --synth 20000 [--synth-epochs 3] [--epochs 100] [--ft-lr 3e-4] [--no-ft] --tag _synth
결과 data/role/set_cv.json(pred = 사진별 모델 역할), 예측 전체 그림 set_pred/<이름>.jpg(색 = 역할, 빨간 바깥 테두리 = 라벨과 다름), 틀린 상자만 set_wrong/
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from torch import nn

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
import seat_grow as sg  # noqa: E402

OUT = HERE / "data" / "role"
BACKS = HERE / "data" / "det" / "backs" / "boxes.json"
TRUTH = json.loads((HERE.parents[1] / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
ROLES = ["hand", "meld", "river", "wall", "pair", "loose"]
COLORS = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow", "other": "gray"}
FEAT = 9


def folds(names: list[str]) -> dict[str, list[str]]:
    am = sorted(n for n in names if n[9:11] < "14")
    pm = sorted(n for n in names if n[9:11] >= "14")
    return {"오전": am, "오후A": pm[: len(pm) // 2], "오후B": pm[len(pm) // 2:]}


def turn(u: float, v: float, side: str) -> tuple[float, float, bool]:
    """화료자 자리가 아래로 오게 돌린 좌표와 폭·높이를 바꿔야 하는지."""
    if side == "bottom":
        return u, v, False
    if side == "right":
        return 1 - v, u, True
    if side == "top":
        return 1 - u, 1 - v, False
    return v, 1 - u, True  # left


def scene_tokens(rec: dict, grid: dict, backs: list, use_backs: bool) -> tuple[np.ndarray, list[int]]:
    """상자 벡터와 라벨 인덱스(-1 = 뒷면 또는 other)."""
    W, H = rec["size"]
    x1, x2, y1, y2 = (grid[k] / 1000 for k in ("x1", "x2", "y1", "y2"))
    fw, fh = max(x2 - x1, 1e-3), max(y2 - y1, 1e-3)
    st = grid.get("sticks")
    if st:
        su, sv = (st[1] + st[3]) / 2000, (st[0] + st[2]) / 2000
    else:
        su, sv = (x1 + x2) / 2, (y1 + y2) / 2
    su, sv, _ = turn((su - x1) / fw, (sv - y1) / fh, rec["side"])
    rows, labels = [], []
    boxes = [(it["box"], it["role"], False) for it in rec["items"]] + ([(b, None, True) for b in backs] if use_backs else [])
    for (x, y, w, h), role, back in boxes:
        u, v = (x + w / 2) / W, (y + h / 2) / H
        u, v, swap = turn((u - x1) / fw, (v - y1) / fh, rec["side"])
        bw, bh = w / W / fw, h / H / fh
        if swap:
            bw, bh = bh, bw
        rows.append([u, v, bw * 10, bh * 10, float(back), float(bw > bh * 1.15), u - su, v - sv, 1.0])
        labels.append(-1 if back or role not in ROLES else ROLES.index(role))
    return np.array(rows, np.float32), labels


class SetNet(nn.Module):
    def __init__(self, d: int = 64, layers: int = 3):
        super().__init__()
        self.inp = nn.Sequential(nn.Linear(FEAT, d), nn.GELU(), nn.Linear(d, d))
        enc = nn.TransformerEncoderLayer(d, 4, d * 2, dropout=0.1, batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(enc, layers)
        self.head = nn.Linear(d, len(ROLES))

    def forward(self, x: torch.Tensor, pad: torch.Tensor) -> torch.Tensor:
        return self.head(self.enc(self.inp(x), src_key_padding_mask=pad))


def crop_mask(x: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
    """서버 자리 크롭(seat_grow.seat_box grow 40) 범위의 상자만: 화료자 자리를 아래로 돌린 좌표에서 v ≥ 약 0.94, 펠트 왼쪽 선 u ≥ 0 ~ 사진 끝 u ≤ 1.6."""
    v0 = 0.94 + (rng.normal(0, 0.01) if rng is not None else 0)
    return (x[:, 1] >= v0) & (x[:, 0] >= -0.02) & (x[:, 0] <= 1.6)


def crop_filter(x: np.ndarray, y, rng: np.random.Generator | None = None):
    keep = crop_mask(x, rng)
    return x[keep], [l for l, k in zip(y, keep) if k]


def batch(scenes: list[dict], rng: np.random.Generator | None):
    xs, ys = [], []
    for s in scenes:
        x, y = s["x"], np.array(s["y"])
        if rng is not None:
            keep = rng.random(len(x)) > 0.08
            if keep.sum() >= 3:
                x, y = x[keep], y[keep]
            x = x.copy()
            shift = rng.normal(0, 0.015, 2)
            scale = rng.uniform(0.95, 1.05)
            x[:, 0:2] = (x[:, 0:2] - 0.5) * scale + 0.5 + shift + rng.normal(0, 0.004, x[:, 0:2].shape)
            x[:, 2:4] *= rng.uniform(0.9, 1.1)
            x[:, 6:8] += shift
        xs.append(torch.tensor(x))
        ys.append(torch.tensor(y))
    n = max(len(x) for x in xs)
    X = torch.zeros(len(xs), n, FEAT)
    Y = torch.full((len(xs), n), -1, dtype=torch.long)
    pad = torch.ones(len(xs), n, dtype=torch.bool)
    for i, (x, y) in enumerate(zip(xs, ys)):
        X[i, : len(x)] = x
        Y[i, : len(y)] = y
        pad[i, : len(x)] = False
    return X, Y, pad


def train(scenes: list[dict], epochs: int, seed: int, net: nn.Module | None = None, lr: float = 1e-3) -> nn.Module:
    """net 을 주면 그 가중치에서 이어서(미세 조정)."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    net = SetNet() if net is None else copy.deepcopy(net)
    freq = Counter(r for s in scenes for r in s["y"] if r >= 0)
    w = torch.tensor([1 / np.sqrt(max(freq[i], 1)) for i in range(len(ROLES))], dtype=torch.float32)
    w = w / w.mean()
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    loss_fn = nn.CrossEntropyLoss(weight=w, ignore_index=-1, label_smoothing=0.05)
    net.train()
    for _ in range(epochs):
        order = rng.permutation(len(scenes))
        for k in range(0, len(order), 8):
            X, Y, pad = batch([scenes[i] for i in order[k:k + 8]], rng)
            opt.zero_grad()
            loss_fn(net(X, pad).reshape(-1, len(ROLES)), Y.reshape(-1)).backward()
            opt.step()
        sched.step()
    return net.eval()


def predict(net: nn.Module, s: dict) -> list[tuple[str, float]]:
    X, _, pad = batch([s], None)
    with torch.no_grad():
        pr = torch.softmax(net(X, pad)[0], 1)
    return [(ROLES[int(r.argmax())], round(float(r.max()), 3)) for r in pr]


def truth_check(name: str, roles: list[str], n_face: int) -> dict:
    """라벨과 무관한 검사: 손패 줄 장수(정답 장수 또는 +1 = 론 화료패 붙여 둠), 울기 장수(치·퐁 3, 깡 4)."""
    t = TRUTH.get(name)
    if not t:
        return {}
    c = Counter(roles[:n_face])
    hand_n = len(t["hand"].split())  # 쯔모는 화료패 포함, 론은 뺀 값(+1 허용)
    meld_n = sum(len(m.split()) for m in t["melds"])
    return dict(hand=c["hand"], hand_ok=c["hand"] in (hand_n, hand_n + 1), hand_truth=hand_n, meld=c["meld"], meld_ok=c["meld"] == meld_n, meld_truth=meld_n)


def draw_pred(s: dict, pred: list[str]) -> None:
    """모델이 매긴 역할 전부. 색 = 역할(아래 범례), 빨간 바깥 테두리 = 라벨과 다름."""
    im = Image.open(s["rec"]["path"]).convert("RGB")
    d = ImageDraw.Draw(im)
    for i, (it, p) in enumerate(zip(s["rec"]["items"], pred)):
        x, y, w, h = it["box"]
        d.rectangle((x, y, x + w, y + h), outline=COLORS[p], width=6)
        if p != it["role"] and it["role"] in ROLES:
            d.rectangle((x - 8, y - 8, x + w + 8, y + h + 8), outline="red", width=4)
            d.text((x, y - 30), f"{i} {p}", fill="red")
    y0 = 20
    for r in ROLES:
        d.rectangle((20, y0, 60, y0 + 40), fill=COLORS[r])
        d.text((70, y0 + 10), r, fill="white")
        y0 += 50
    im.resize((im.width // 2, im.height // 2)).save(OUT / "set_pred" / f"{s['name']}.jpg", quality=80)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--no-backs", action="store_true")
    ap.add_argument("--draw-only", action="store_true", help="학습 없이 set_cv.json 의 pred 로 set_pred/ 그림만 다시")
    ap.add_argument("--synth", type=int, default=0, help="합성 장면 수(role_synth.py)로 먼저 학습한 뒤 실제로 미세 조정")
    ap.add_argument("--synth-epochs", type=int, default=3)
    ap.add_argument("--ft-lr", type=float, default=3e-4)
    ap.add_argument("--no-ft", action="store_true", help="합성만 학습하고 실제 미세 조정 없이 채점")
    ap.add_argument("--tag", default="")
    ap.add_argument("--crop", action="store_true", help="서버 자리 크롭처럼 자리 띠 안의 상자만 보고 배우기(합성·실제 모두)")
    ap.add_argument("--pre-file", default="", help="합성 사전학습 가중치를 여기 저장/있으면 읽음(data/role/ 아래 이름)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(8)
    labels = json.loads((OUT / "labels.json").read_text(encoding="utf-8"))
    backs = json.loads(BACKS.read_text(encoding="utf-8")) if BACKS.exists() else {}
    grids = {s["name"]: s["grid"] for s in sg.scenes()}
    scenes = []
    for name, rec in labels.items():
        x, y = scene_tokens(rec, grids[name], backs.get(name, []), not a.no_backs)
        if a.crop:  # 상자와 라벨 항목을 같은 마스크로 잘라 채점 인덱스를 맞춘다(앞면이 앞, 뒷면이 뒤)
            keep = crop_mask(x)
            rec = dict(rec, items=[it for it, k in zip(rec["items"], keep[: len(rec["items"])]) if k])
            x, y = x[keep], [l for l, k in zip(y, keep) if k]
        scenes.append(dict(name=name, rec=rec, x=x, y=y, n_face=len(rec["items"])))
    occl = set(getattr(sg, "EXCLUDED", ()))
    print("사진", len(scenes), "상자", sum(len(s["x"]) for s in scenes), "앞면", sum(s["n_face"] for s in scenes), "가림 제외", sorted(occl), flush=True)
    print("규칙 라벨", Counter(r for s in scenes for r in s["y"] if r >= 0), flush=True)
    fs = folds([s["name"] for s in scenes])
    conf = {r: Counter() for r in ROLES}
    rconf = {r: Counter() for r in ROLES}  # 규칙(사람 수정 전) 대 라벨
    per_fold, wrong, tc_model, tc_rule = {}, [], {}, {}
    (OUT / "set_wrong").mkdir(parents=True, exist_ok=True)
    (OUT / "set_pred").mkdir(parents=True, exist_ok=True)  # 모델이 매긴 역할 전부(색 = 역할, 빨간 바깥 테두리 = 라벨과 다름)
    preds: dict = {}
    if a.draw_only:
        for s, pred in ((s, json.loads((OUT / "set_cv.json").read_text(encoding="utf-8"))["pred"][s["name"]]) for s in scenes):
            draw_pred(s, pred)
        return
    t0 = time.time()
    pre: list = []
    if a.synth:
        pf = OUT / a.pre_file if a.pre_file else None
        if pf and pf.exists():
            for sd in torch.load(pf):
                net = SetNet()
                net.load_state_dict(sd)
                pre.append(net.eval())
            print("사전학습 가중치 읽음", pf, len(pre), flush=True)
        else:
            import role_synth
            for seed in range(a.seeds):
                syn = role_synth.dataset(a.synth, 100 + seed)
                if a.no_backs:  # 서버는 뒷면 상자가 없다: 합성에서도 뺀다
                    for s in syn:
                        keep = s["x"][:, 4] == 0
                        s["x"], s["y"] = s["x"][keep], [l for l, k in zip(s["y"], keep) if k]
                if a.crop:
                    crng = np.random.default_rng(seed)
                    syn = [dict(s, **dict(zip(("x", "y"), crop_filter(s["x"], s["y"], crng)))) for s in syn]
                    syn = [s for s in syn if len(s["x"]) >= 3]
                pre.append(train(syn, a.synth_epochs, seed))
                print(f"합성 {a.synth}장 사전학습 씨드 {seed} {round(time.time() - t0)}초", flush=True)
            if pf:
                torch.save([n.state_dict() for n in pre], pf)
    for fold, names in fs.items():
        tr = [s for s in scenes if s["name"] not in names]
        te = [s for s in scenes if s["name"] in names]
        if a.no_ft:
            nets = pre
        elif pre:
            nets = [train(tr, a.epochs, seed, pre[seed], a.ft_lr) for seed in range(a.seeds)]
        else:
            nets = [train(tr, a.epochs, seed) for seed in range(a.seeds)]
        ok, n = Counter(), Counter()
        for s in te:
            votes = [predict(net, s) for net in nets]
            pred = [Counter(v[i][0] for v in votes).most_common(1)[0][0] for i in range(len(s["x"]))]
            roles = [it["role"] for it in s["rec"]["items"]]
            rule = [it.get("rule", it["role"]) for it in s["rec"]["items"]]
            tc_model[s["name"]] = truth_check(s["name"], pred, s["n_face"])
            tc_rule[s["name"]] = truth_check(s["name"], rule, s["n_face"])
            preds[s["name"]] = [p for p, _ in zip(pred, s["rec"]["items"])]
            draw_pred(s, pred)
            if s["name"] in occl:
                continue
            bad = []
            for i, (p, r) in enumerate(zip(pred[: s["n_face"]], roles)):
                if r not in ROLES:
                    continue
                n[r] += 1
                ok[r] += p == r
                conf[r][p] += 1
                rconf[r][rule[i]] += 1
                if p != r:
                    wrong.append((s["name"][-6:], i, r, p))
                    bad.append((i, r, p))
            if bad:
                im = Image.open(s["rec"]["path"]).convert("RGB")
                d = ImageDraw.Draw(im)
                for i, r, p in bad:
                    x, y, w, h = s["rec"]["items"][i]["box"]
                    d.rectangle((x, y, x + w, y + h), outline=COLORS[p], width=6)
                    d.text((x, y - 30), f"{i} {r}->{p}", fill="red")
                im.resize((im.width // 2, im.height // 2)).save(OUT / "set_wrong" / f"{s['name']}.jpg", quality=80)
        per_fold[fold] = {r: f"{ok[r]}/{n[r]}" for r in ROLES if n[r]}
        print(fold, per_fold[fold], f"{round(time.time() - t0)}초", flush=True)
    total = {r: f"{conf[r][r]}/{sum(conf[r].values())}" for r in ROLES}
    allok = sum(conf[r][r] for r in ROLES)
    alln = sum(sum(conf[r].values()) for r in ROLES)
    print("합계(라벨 대비)", total, f"전체 {allok}/{alln}")
    print("혼동", {r: dict(conf[r]) for r in ROLES})
    rtotal = {r: f"{rconf[r][r]}/{sum(rconf[r].values())}" for r in ROLES}
    rok = sum(rconf[r][r] for r in ROLES)
    print("규칙(수정 전) 라벨 대비", rtotal, f"전체 {rok}/{alln}")
    ev = [k for k in tc_model if k not in occl and tc_model[k]]
    summ = {}
    for tag, tc in (("모델", tc_model), ("규칙", tc_rule)):
        summ[tag] = dict(hand=f"{sum(tc[k]['hand_ok'] for k in ev)}/{len(ev)}", meld=f"{sum(tc[k]['meld_ok'] for k in ev)}/{len(ev)}")
        print(f"truth 대비 {tag}: 손패 장수 {summ[tag]['hand']}, 울기 장수 {summ[tag]['meld']}")
    for k in ev:
        m, r = tc_model[k], tc_rule[k]
        if not (m["hand_ok"] and m["meld_ok"] and r["hand_ok"] and r["meld_ok"]):
            print(f"  {k[-6:]} 정답 손{m['hand_truth']}·울{m['meld_truth']} | 모델 손{m['hand']}·울{m['meld']} | 규칙 손{r['hand']}·울{r['meld']}")
    print("틀린 상자", wrong)
    (OUT / f"set_cv{a.tag}.json").write_text(json.dumps(dict(args=vars(a), per_fold=per_fold, total=total, all=f"{allok}/{alln}", confusion={r: dict(c) for r, c in conf.items()}, rule_total=rtotal, rule_all=f"{rok}/{alln}", truth=summ, truth_model=tc_model, truth_rule=tc_rule, wrong=wrong, pred=preds), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
