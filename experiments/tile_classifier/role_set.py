"""패 상자 집합 → 역할 모델(2026-11-03, 노트북 CPU, API 없음). 그림을 안 보고 상자 배치만으로 역할을 정한다.

입력 = 사진 한 장의 상자 전부(앞면 = role_label.py 라벨, 뒷면 = det_backs.py 상자). 상자마다 벡터:
  펠트 격자(x1·x2·y1·y2) 기준 0~1 좌표·크기, 화료자 자리가 아래로 오게 돌림, 뒷면 플래그, 눕힘 플래그, 리치봉 기기 중심과의 차.
모델 = Transformer 인코더(3층·폭 64·4머리), 상자끼리 서로 보고 앞면 상자마다 역할 6종 확률. 파라미터 약 10만.
라벨 = data/role/labels.json(규칙 자동 + review.json 사람 수정). other 는 손실에서 뺌.
나누기 = role_train.py 와 같은 사진 단위 3겹(오전 / 오후 앞 / 오후 뒤). 가림·사용자 문제 사진(seat_grow.EXCLUDED)은 채점에서 뺌.
채점 = (1) 라벨 대비 상자별 정확도·혼동, (2) 라벨과 무관한 truth.json 대비: 손패 줄 장수·울기 장수가 맞는 사진 수(규칙 라벨도 같이 잼).

  python -I -X utf8 experiments/tile_classifier/role_set.py [--epochs 300] [--seeds 3] [--no-backs]
  python -I -X utf8 experiments/tile_classifier/role_set.py --synth 20000 [--synth-epochs 3] [--epochs 100] [--ft-lr 3e-4] [--no-ft] --tag _synth
  python -I -X utf8 experiments/tile_classifier/role_set.py --feat rot --synth 8000 ...   # 회전 상자 특징(아래)
결과 data/role/set_cv.json(pred = 사진별 모델 역할), 예측 전체 그림 set_pred/<이름>.jpg(색 = 역할, 빨간 바깥 테두리 = 라벨과 다름), 틀린 상자만 set_wrong/

특징(2026-11-05 `--feat rot`, 11칸): 검출기가 회전 상자(8회차)를 내므로 축 상자 대신 패에 맞는 상자로 잰다.
  0 u · 1 v · 2 패 폭×10 · 3 패 높이×10(회전 상자의 변 — 기운 패도 실제 크기) · 4 뒷면 · 5 눕힘(패 폭 > 높이×1.15, 회전 상자 기준)
  · 6 u−su · 7 v−sv · 8 상수 1 · 9 sin(2·기울기) · 10 cos(2·기울기). 기울기 = 패 변이 격자 축에서 벗어난 각(−45~45°, 시계 방향 +).
  실제 사진의 회전 상자는 7회차 라벨(data/det/obb/rects.json)에서 IoU 로 찾고, 없으면 축(기울기 0). 예전 9칸(`--feat old`)은 그대로 둔다.
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
# 2026-11-09 사용자 "none 으로 학습시켜야 될 거 같애"(표 1-142): ROLE_NONE=1 이면 7번째 역할 none = 역할 없는 앞면(실제 other, 생성기 외톨이 앞면 -2).
# 서버 roles.ROLES 도 끝에 "none" 을 더해야 7칸 ONNX 를 읽는다(6칸 ONNX 는 그대로 읽힘).
NONE = __import__("os").environ.get("ROLE_NONE") == "1"
ROLES = ["hand", "meld", "river", "wall", "pair", "loose"] + (["none"] if NONE else [])
COLORS = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow", "other": "gray", "none": "white"}
FEAT = 9  # 예전 특징(--feat old). 회전 상자 특징은 FEAT_ROT
FEAT_ROT = 11
RECTS = HERE / "data" / "det" / "obb" / "rects.json"
LABELS = __import__("os").environ.get("ROLE_LABELS", "labels.json")  # 7-1(2026-11-06): labels_obb.json = role_label.py --obb(전수 조사 상자)


def feat_dim(feat: str) -> int:
    return FEAT_ROT if feat == "rot" else FEAT


def iou(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)


def tile_geom(box, rect) -> tuple[float, float, float]:
    """(패 폭, 패 높이, 기울기°) 그림 좌표. rect = 회전 상자 ((cx, cy), (w, h), 각도°) 를 cv2.boxPoints 로 풀어 변 길이·방향으로 잰다
    (각도 규약에 상관없음). 격자 축에 가까운 변이 폭. 기울기는 −45~45(시계 방향 +, 그림 좌표 atan2(dy, dx)). rect 없으면 축 상자, 기울기 0."""
    if rect is None:
        return float(box[2]), float(box[3]), 0.0
    if isinstance(rect, np.ndarray) and rect.shape == (4, 2):  # 꼭짓점을 바로 준 경우(호모그래피로 보낸 뒤 등)
        p = rect.astype(float)
    else:
        import cv2

        p = cv2.boxPoints(((float(rect[0][0]), float(rect[0][1])), (float(rect[1][0]), float(rect[1][1])), float(rect[2])))
    e1, e2 = p[1] - p[0], p[2] - p[1]
    a1 = np.degrees(np.arctan2(e1[1], e1[0])) % 180
    if 45 < a1 < 135:  # e1 이 세로에 가까움
        h, w, ea = float(np.hypot(*e1)), float(np.hypot(*e2)), e2
    else:
        w, h, ea = float(np.hypot(*e1)), float(np.hypot(*e2)), e1
    tilt = ((np.degrees(np.arctan2(ea[1], ea[0])) + 45) % 90) - 45
    return w, h, float(tilt)


def match_rects(boxes: list, rects: list, thr: float = 0.3) -> list:
    """상자마다 IoU 가 가장 큰 회전 상자(thr 이상), 없으면 None. rects = [(축 상자, 회전 상자)]."""
    out = []
    for b in boxes:
        best = max(rects, key=lambda r: iou(r[0], b), default=None)
        out.append(best[1] if best is not None and iou(best[0], b) >= thr else None)
    return out


def scene_rects(name: str, rects_all: dict | None) -> dict:
    """rects.json 의 한 장면 → {"faces": [(축 상자, 회전 상자)], "backs": [...]}."""
    if not rects_all or name not in rects_all:
        return {"faces": [], "backs": []}
    out: dict = {"faces": [], "backs": []}
    for it in rects_all[name]["items"]:
        out["faces" if it["cls"] == 0 else "backs"].append((it["box"], it["rect"]))
    return out


def feat_row(u: float, v: float, bw: float, bh: float, back: bool, su: float, sv: float, tilt_deg: float, feat: str) -> list[float]:
    """상자 벡터 한 줄. bw·bh = 펠트 기준 패 폭·높이(돌린 자리 기준, 회전 상자면 패에 맞는 변), tilt = 기울기°."""
    row = [u, v, bw * 10, bh * 10, float(back), float(bw > bh * 1.15), u - su, v - sv, 1.0]
    if feat == "rot":
        t = np.radians(2 * tilt_deg)
        row += [float(np.sin(t)), float(np.cos(t))]
    return row


def axis_of(w: float, h: float, tilt_deg: float) -> tuple[float, float]:
    """기운 패(폭 w·높이 h·기울기)를 감싸는 축 상자의 폭·높이 — 예전 특징(축 상자 검출기)을 흉내 낼 때."""
    c, s = abs(np.cos(np.radians(tilt_deg))), abs(np.sin(np.radians(tilt_deg)))
    return w * c + h * s, w * s + h * c


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


def scene_tokens(rec: dict, grid: dict, backs: list, use_backs: bool, feat: str = "old", rects: dict | None = None) -> tuple[np.ndarray, list[int]]:
    """상자 벡터와 라벨 인덱스(-1 = 뒷면 또는 other). feat="rot" 면 rects(scene_rects)에서 찾은 회전 상자로 패 크기·기울기를 잰다."""
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
    faces = [it["box"] for it in rec["items"]]
    rr = rects or {"faces": [], "backs": []}
    fr = match_rects(faces, rr["faces"]) if feat == "rot" else [None] * len(faces)
    br = match_rects(backs, rr["backs"]) if feat == "rot" and use_backs else [None] * len(backs)
    boxes = [(b, it["role"], False, r) for b, it, r in zip(faces, rec["items"], fr)] + ([(b, None, True, r) for b, r in zip(backs, br)] if use_backs else [])
    for (x, y, w, h), role, back, rect in boxes:
        u, v = (x + w / 2) / W, (y + h / 2) / H
        u, v, swap = turn((u - x1) / fw, (v - y1) / fh, rec["side"])
        pw, ph, tilt = tile_geom((x, y, w, h), rect)
        bw, bh = pw / W / fw, ph / H / fh
        if swap:
            bw, bh = bh, bw
        rows.append(feat_row(u, v, bw, bh, back, su, sv, tilt, feat))
        labels.append(-1 if back or role not in ROLES else ROLES.index(role))
    return np.array(rows, np.float32).reshape(-1, feat_dim(feat)), labels


REL = 7  # 상대 위치 특징 칸 수(rel_feats)


def rel_feats(x: torch.Tensor) -> torch.Tensor:
    """상자 쌍 (i 가 j 를 볼 때) 상대 특징 [B, N, N, REL] (2026-11-08 `--relbias`). 거리는 i 의 패 크기로 나눔 = 패 몇 장 떨어졌나.
    0 du/s · 1 dv/s(±8 로 자르고 /4) · 2 log(1 + 거리/s) · 3 j 눕힘 · 4 j 뒷면 · 5 눕힘 같음 · 6 패 크기 비 log(s_j/s_i)."""
    u, v = x[..., 0], x[..., 1]
    s = ((x[..., 2] + x[..., 3]) / 20).clamp_min(1e-3)  # 패 폭·높이 평균(특징은 ×10)
    lie, back = x[..., 5], x[..., 4]
    du = (u[:, None, :] - u[:, :, None]) / s[:, :, None]
    dv = (v[:, None, :] - v[:, :, None]) / s[:, :, None]
    dist = torch.sqrt(du ** 2 + dv ** 2)
    n = x.shape[1]
    return torch.stack([du.clamp(-8, 8) / 4, dv.clamp(-8, 8) / 4, torch.log1p(dist),
                        lie[:, None, :].expand(-1, n, -1), back[:, None, :].expand(-1, n, -1),
                        (lie[:, None, :] == lie[:, :, None]).float(), torch.log(s[:, None, :] / s[:, :, None])], -1)


class SetNet(nn.Module):
    def __init__(self, d: int = 64, layers: int = 3, feat: int = FEAT, relbias: bool = False):
        super().__init__()
        self.feat = feat
        self.heads, self.layers, self.relbias = 4, layers, relbias
        self.inp = nn.Sequential(nn.Linear(feat, d), nn.GELU(), nn.Linear(d, d))
        enc = nn.TransformerEncoderLayer(d, 4, d * 2, dropout=0.1, batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(enc, layers, enable_nested_tensor=False)
        self.head = nn.Linear(d, len(ROLES))
        if relbias:  # 상자 쌍 상대 위치 → 층·머리마다 어텐션 점수에 더할 값. 0 으로 시작 = 처음엔 예전 모델과 같음
            self.rel = nn.Sequential(nn.Linear(REL, 32), nn.GELU(), nn.Linear(32, self.heads * layers))
            nn.init.zeros_(self.rel[2].weight)
            nn.init.zeros_(self.rel[2].bias)

    def forward(self, x: torch.Tensor, pad: torch.Tensor) -> torch.Tensor:
        if not self.relbias:
            return self.head(self.enc(self.inp(x), src_key_padding_mask=pad))
        B, N, _ = x.shape
        bias = self.rel(rel_feats(x)).permute(0, 3, 1, 2)  # [B, 층×머리, N, N]
        bias = bias.masked_fill(pad[:, None, None, :], -1e9)  # 패딩 상자는 안 봄
        h = self.inp(x)
        fast = torch.backends.mha.get_fastpath_enabled()
        torch.backends.mha.set_fastpath_enabled(False)  # 평가 모드 빠른 경로는 머리별 3차원 마스크에서 NaN(2026-11-08 확인)
        try:
            for l, layer in enumerate(self.enc.layers):
                h = layer(h, src_mask=bias[:, l * self.heads:(l + 1) * self.heads].reshape(B * self.heads, N, N))
        finally:
            torch.backends.mha.set_fastpath_enabled(fast)
        return self.head(h)


def crop_mask(x: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
    """서버 자리 크롭(seat_grow.seat_box grow 40) 범위의 상자만: 화료자 자리를 아래로 돌린 좌표에서 v ≥ 약 0.94, 펠트 왼쪽 선 u ≥ 0 ~ 사진 끝 u ≤ 1.6."""
    v0 = 0.94 + (rng.normal(0, 0.01) if rng is not None else 0)
    return (x[:, 1] >= v0) & (x[:, 0] >= -0.02) & (x[:, 0] <= 1.6)


def crop_filter(x: np.ndarray, y, rng: np.random.Generator | None = None):
    keep = crop_mask(x, rng)
    return x[keep], [l for l, k in zip(y, keep) if k]


DROP_SAFE = __import__("os").environ.get("ROLE_DROP_SAFE") == "1"
# 2026-11-09 사용자 결정 (a): 역할 없는 앞면(라벨 -2, 실제 other·생성기 v3 의 외톨이 앞면)은 교차 엔트로피에선 빼고
# "손패·울기·떼어 둔 패가 아니다" 손실 −log(1 − p_hand − p_meld − p_loose) 로 가르친다(표 1-138). 출력 6칸·서버는 그대로.
OTHER_NEG = __import__("os").environ.get("ROLE_OTHER_NEG") == "1"
WIN_IDX = [0, 1, 5]


def batch(scenes: list[dict], rng: np.random.Generator | None):
    xs, ys = [], []
    for s in scenes:
        x, y = s["x"], np.array(s["y"])
        if rng is not None:
            keep = rng.random(len(x)) > 0.08
            if DROP_SAFE:  # 2026-11-09 사용자: 무작위로 빠져도 되는 건 강·뒷면(산)뿐 — 손패·울기·떼어 둔 패·표시패·짝은 남김(외톨이 울기 1장 방지, 표 1-136)
                keep |= (y != 2) & (y != -1)
            if keep.sum() >= 3:
                x, y = x[keep], y[keep]
            x = x.copy()
            shift = rng.normal(0, 0.015, 2)
            scale = rng.uniform(0.95, 1.05)
            x[:, 0:2] = (x[:, 0:2] - 0.5) * scale + 0.5 + shift + rng.normal(0, 0.004, x[:, 0:2].shape)
            x[:, 2:4] *= rng.uniform(0.9, 1.1)
            x[:, 6:8] += shift
            if x.shape[1] == FEAT_ROT:  # 기울기 지터(검출기 각도 오차 + 격자 회전 오차)
                t = np.arctan2(x[:, 9], x[:, 10]) / 2 + np.radians(rng.normal(0, 1.0) + rng.normal(0, 1.5, len(x)))
                x[:, 9], x[:, 10] = np.sin(2 * t), np.cos(2 * t)
        xs.append(torch.tensor(x))
        ys.append(torch.tensor(y))
    n = max(len(x) for x in xs)
    X = torch.zeros(len(xs), n, xs[0].shape[1])
    Y = torch.full((len(xs), n), -1, dtype=torch.long)
    pad = torch.ones(len(xs), n, dtype=torch.bool)
    for i, (x, y) in enumerate(zip(xs, ys)):
        X[i, : len(x)] = x
        Y[i, : len(y)] = y
        pad[i, : len(x)] = False
    return X, Y, pad


def train(scenes: list[dict], epochs: int, seed: int, net: nn.Module | None = None, lr: float = 1e-3, relbias: bool = False) -> nn.Module:
    """net 을 주면 그 가중치에서 이어서(미세 조정). relbias 는 새로 만들 때만."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    net = SetNet(feat=scenes[0]["x"].shape[1], relbias=relbias) if net is None else copy.deepcopy(net)
    freq = Counter((6 if (NONE and r == -2) else r) for s in scenes for r in s["y"] if r >= 0 or (NONE and r == -2))
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
            logits = net(X, pad).reshape(-1, len(ROLES))
            Yf = Y.reshape(-1)
            if NONE:  # 역할 없는 앞면(-2) → none(6)
                Yf = torch.where(Yf == -2, torch.full_like(Yf, 6), Yf)
            loss = loss_fn(logits, Yf.clamp(min=-1))
            neg = Yf == -2
            if OTHER_NEG and neg.any():
                pw = torch.softmax(logits[neg], 1)[:, WIN_IDX].sum(1)
                loss = loss - torch.log((1 - pw).clamp_min(1e-4)).mean()
            loss.backward()
            opt.step()
        sched.step()
    return net.eval()


def add_bent(scenes: list[dict], k: int, seed: int, exclude=()) -> list[dict]:
    """학습 장면에 휜 손패 사본을 장면마다 k 개 더한다(2026-11-07, role_bend.py — 11-07 매장 153638 처럼 손패 줄이 계단·끝 흐름으로 휘어
    끝 패를 loose 로 보던 문제. 독립 검토 2회 data/role/bend_check/review_bend{,_v2}.json). 라벨은 그대로, 시험 장면에는 쓰지 않는다.
    exclude(평가 제외 사진)는 재료에서 뺀다. 손패 8장 미만이거나 겹침 검사에 계속 걸리면 그 사본은 건너뛴다."""
    if k <= 0:
        return scenes
    import role_bend as rb

    rng = np.random.default_rng(10_000 + seed)
    out = list(scenes)
    for s in scenes:
        if s["name"] in exclude:
            continue
        for j in range(k):
            xb, info = rb.bend(s["x"], s["y"], rng)
            if info["mode"] is not None:
                out.append(dict(name=f"{s['name']}#bend{j}", x=xb, y=list(s["y"]), n_face=s.get("n_face", len(s["x"]))))
    return out


def load_nets(path: Path) -> list[nn.Module]:
    """저장한 씨드별 가중치 → SetNet 목록(특징 수는 첫 층 모양에서)."""
    nets = []
    for sd in torch.load(path):
        net = SetNet(feat=sd["inp.0.weight"].shape[1], relbias=any(k.startswith("rel.") for k in sd))
        net.load_state_dict(sd)
        nets.append(net.eval())
    return nets


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
    ap.add_argument("--feat", default="old", choices=["old", "rot"], help="rot = 회전 상자 특징 11칸(패 크기·기울기), old = 예전 9칸")
    ap.add_argument("--save-folds", action="store_true", help="fold 별 씨드 가중치를 data/role/role_fold_<am|pmA|pmB><tag>.pt 로 저장(role_export.py 로 fold 별 ONNX, 개선 계획 2단계)")
    ap.add_argument("--bend", type=int, default=0, help="미세 조정 학습 장면마다 휜 손패 사본 수(add_bent, role_bend.py, 2026-11-07). 시험 장면엔 안 씀")
    ap.add_argument("--relbias", action="store_true", help="상자 쌍 상대 위치를 어텐션 점수에 더함(rel_feats, 2026-11-08). 사전학습도 이 구조로 새로 해야 함")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(8)
    labels = json.loads((OUT / LABELS).read_text(encoding="utf-8"))
    print("라벨", LABELS, flush=True)
    backs = json.loads(BACKS.read_text(encoding="utf-8")) if BACKS.exists() else {}
    rects_all = json.loads(RECTS.read_text(encoding="utf-8")) if a.feat == "rot" else None
    grids = {s["name"]: s["grid"] for s in sg.scenes()}
    scenes = []
    for name, rec in labels.items():
        x, y = scene_tokens(rec, grids[name], backs.get(name, []), not a.no_backs, a.feat, scene_rects(name, rects_all))
        if a.crop:  # 상자와 라벨 항목을 같은 마스크로 잘라 채점 인덱스를 맞춘다(앞면이 앞, 뒷면이 뒤)
            keep = crop_mask(x)
            rec = dict(rec, items=[it for it, k in zip(rec["items"], keep[: len(rec["items"])]) if k])
            x, y = x[keep], [l for l, k in zip(y, keep) if k]
        scenes.append(dict(name=name, rec=rec, x=x, y=y, n_face=len(rec["items"])))
    occl = set(getattr(sg, "EXCLUDED", ()))
    print("사진", len(scenes), "상자", sum(len(s["x"]) for s in scenes), "앞면", sum(s["n_face"] for s in scenes), "가림 제외", sorted(occl), "특징", a.feat, scenes[0]["x"].shape[1], flush=True)
    if a.feat == "rot":
        tilted = sum(int(abs(np.arctan2(s["x"][:, 9], s["x"][:, 10])).max() > np.radians(6)) for s in scenes for _ in [0])
        print("기운 상자(3° 넘음)", sum(int((np.abs(np.arctan2(s["x"][:, 9], s["x"][:, 10]) / 2) > np.radians(3)).sum()) for s in scenes), "사진", tilted, flush=True)
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
            pre = load_nets(pf)
            if pre[0].feat != feat_dim(a.feat):
                raise SystemExit(f"{pf}: 특징 {pre[0].feat}칸 가중치인데 --feat {a.feat} 는 {feat_dim(a.feat)}칸")
            if pre[0].relbias != a.relbias:
                raise SystemExit(f"{pf}: relbias={pre[0].relbias} 가중치인데 --relbias={a.relbias}")
            print("사전학습 가중치 읽음", pf, len(pre), flush=True)
        else:
            import role_synth
            for seed in range(a.seeds):
                syn = role_synth.dataset(a.synth, 100 + seed, a.feat)
                if a.no_backs:  # 서버는 뒷면 상자가 없다: 합성에서도 뺀다
                    for s in syn:
                        keep = s["x"][:, 4] == 0
                        s["x"], s["y"] = s["x"][keep], [l for l, k in zip(s["y"], keep) if k]
                if a.crop:
                    crng = np.random.default_rng(seed)
                    syn = [dict(s, **dict(zip(("x", "y"), crop_filter(s["x"], s["y"], crng)))) for s in syn]
                    syn = [s for s in syn if len(s["x"]) >= 3]
                pre.append(train(syn, a.synth_epochs, seed, relbias=a.relbias))
                print(f"합성 {a.synth}장 사전학습 씨드 {seed} {round(time.time() - t0)}초", flush=True)
            if pf:
                torch.save([n.state_dict() for n in pre], pf)
    for fold, names in fs.items():
        tr = [s for s in scenes if s["name"] not in names]
        te = [s for s in scenes if s["name"] in names]
        if a.bend and a.feat == "rot":  # 씨드마다 다른 사본(같은 씨드면 같은 사본 = 다시 돌려도 같음)
            trs = [add_bent(tr, a.bend, seed, occl) for seed in range(a.seeds)]
            print(fold, "휜 손패 사본 더함", len(trs[0]) - len(tr), flush=True)
        else:
            trs = [tr] * a.seeds
        if a.no_ft:
            nets = pre
        elif pre:
            nets = [train(trs[seed], a.epochs, seed, pre[seed], a.ft_lr) for seed in range(a.seeds)]
        else:
            nets = [train(trs[seed], a.epochs, seed, relbias=a.relbias) for seed in range(a.seeds)]
        if a.save_folds:  # 이 fold 의 사진(names)을 안 배운 가중치
            fk = {"오전": "am", "오후A": "pmA", "오후B": "pmB"}[fold]
            torch.save([net.state_dict() for net in nets], OUT / f"role_fold_{fk}{a.tag}.pt")
            print("저장", OUT / f"role_fold_{fk}{a.tag}.pt", "시험 사진", names, flush=True)
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
