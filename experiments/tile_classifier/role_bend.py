"""역할 모델 보강 예시: 실제 라벨 장면의 화료자 손패 줄을 휘게 만든다(2026-11-07, 사용자 "문제 사진은 라벨로 안 쓰고 기존 사진에서 손패 예시를 더해서").

왜: 11-07 매장 153638 — 왼쪽 화료자 손패가 계단처럼 어긋나고(東東·中中中 덩이가 줄에서 반 장쯤 비켜남) 끝 1삭·2삭·3삭이 비스듬히 흘러,
역할 모델이 끝 3삭(2삭에 붙어 있음)을 loose(떼어 둔 화료패, 0.605)로 봐 손패가 12장이 됐다. 153638 은 시험용으로만 남기고,
학습 묶음(data/role/labels_obb.json 의 실제 장면)의 손패 상자를 옮겨 같은 꼴을 만든다. 라벨은 그대로 hand.

변형(장면마다 하나 이상, 손패 8장 이상일 때):
  - end  : 줄 오른쪽(70%) 또는 왼쪽 끝 2~5장이 줄과 수직으로 조금씩 흘러감(한 장마다 패 높이 0.08~0.25 씩 같은 방향, 누적 상한 0.8)
           + 낱장 기울기 3~12°(구간 안 같은 부호). 줄 방향 간격은 그대로(붙어 있음) — 떼어 둔 패와 달리 틈이 없다.
  - step : 손패를 2~4 덩이로 나눠 덩이마다 수직으로 N(0, 0.45) 패 높이(±1.2 로 자름, 평균 뺌, 이웃 차이 하나는 0.3 이상) 비킴(계단, 153638 의 中中中 덩이는 약 1.0). 간격은 그대로.
  - both : step 뒤 end(25%) — 153638 은 둘이 함께 나왔다.
검토(data/role/bend_check/review_bend.json, 새 세션 독립 검토 26장: ok 19·문제 7 은 모두 end) 반영: 기울기 반전 없앰, 회전 사각형 겹침 검사, 떨어진 끝 금지, 크롭 선, 누적 상한.
지키는 것: 떼어 둔 패(loose)·울기·강 등 다른 상자는 안 건드린다. 손패 끝에서 떨어져 놓인 진짜 loose 가 있으면 그쪽 끝은 흘리지 않는다
  (흘린 끝이 loose 와 겹쳐 보이지 않게) — 모델이 '붙어 있음 = 손패, 떨어짐 = loose' 를 배우게.

특징 칸(role_set.feat_row): 0 u · 1 v · 2 bw×10 · 3 bh×10 · 4 뒷면 · 5 눕힘 · 6 u−su · 7 v−sv · 8 1 · (rot) 9 sin 2t · 10 cos 2t.
화료자 자리가 아래로 돌려진 좌표라 손패 줄 방향 = u, 수직 = v.

  python -I -X utf8 experiments/tile_classifier/role_bend.py check [--n 24] [--seed 0]   # data/role/bend_check/ 원본·변형 나란히 그림 + index.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
HAND, LOOSE = 0, 5


def _tilt(x: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(x[:, 9], x[:, 10]) / 2)


def _set_tilt(x: np.ndarray, i: int, deg: float) -> None:
    t = math.radians(((deg + 45) % 90) - 45)
    x[i, 9], x[i, 10] = math.sin(2 * t), math.cos(2 * t)


def hand_index(x: np.ndarray, y) -> list[int]:
    """화료자 손패 상자 번호(줄 방향 u 순서)."""
    y = np.asarray(y)
    idx = [i for i in np.flatnonzero(y == HAND) if x[i, 4] == 0]
    return sorted(idx, key=lambda i: x[i, 0])


def _corners(row: np.ndarray) -> np.ndarray:
    """상자 한 줄(특징) → 회전 사각형 꼭짓점 4개(u, v)."""
    w, h = row[2] / 10, row[3] / 10
    t = math.atan2(row[9], row[10]) / 2
    c, s = math.cos(t), math.sin(t)
    return np.array([(row[0] + dx * c - dy * s, row[1] + dx * s + dy * c) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))])


def _depth(a: np.ndarray, b: np.ndarray) -> float:
    """회전 사각형 두 개의 SAT 파고든 깊이(안 겹치면 0)."""
    best = float("inf")
    for poly in (a, b):
        for k in range(4):
            e = poly[(k + 1) % 4] - poly[k]
            n = np.array([-e[1], e[0]]) / (np.hypot(*e) + 1e-12)
            pa, pb = a @ n, b @ n
            d = min(pa.max(), pb.max()) - max(pa.min(), pb.min())
            if d <= 0:
                return 0.0
            best = min(best, d)
    return best


def _new_overlap(x0: np.ndarray, x1: np.ndarray, moved: list[int], tw: float, limit: float = 0.15, limit_back: float = 0.08) -> bool:
    """움직인 상자와 다른 모든 상자(움직인 것끼리·뒷면 포함) 쌍에서 '새로 생긴 겹침'(변형 후 − 변형 전 깊이)이 limit×패 폭을 넘는지
    (검토 review_bend.json 요약 2 — 원본 라벨 상자도 이웃끼리 0.1 tw 안팎 겹쳐서 차이로 본다). 안 움직인 뒷면 상자(패산 등)와는
    limit_back(검토 v2 요약 2 — 패산이 손패에 바로 붙은 장면에서 위로 올라가 맞닿는 것)."""
    ms = set(moved)
    c0 = {i: _corners(x0[i]) for i in range(len(x0))}
    c1 = {i: (_corners(x1[i]) if i in ms else c0[i]) for i in range(len(x1))}
    for i in moved:
        for j in range(len(x1)):
            if j == i or (j in ms and j < i):
                continue
            if abs(x1[i, 0] - x1[j, 0]) > 0.2 or abs(x1[i, 1] - x1[j, 1]) > 0.2:
                continue
            lim = limit_back if (x1[j, 4] == 1 and j not in ms) else limit
            if _depth(c1[i], c1[j]) - _depth(c0[i], c0[j]) > lim * tw:
                return True
    return False


def _gap_at(x: np.ndarray, hi: list[int], end: str, tw: float) -> float:
    """손패 줄 끝 패와 그 이웃 사이 줄 방향 틈(패 폭 배수)."""
    a, b = (hi[-2], hi[-1]) if end == "right" else (hi[0], hi[1])
    return (abs(x[b, 0] - x[a, 0]) - (x[a, 2] + x[b, 2]) / 20) / tw


def _end(x: np.ndarray, hi: list[int], rng: np.random.Generator, end: str, th: float) -> dict:
    """끝 흐름: 2~5장, 한 장마다 0.08~0.25 th 같은 방향 누적(상한 0.8 th), 기울기는 구간 안 같은 부호 3~12°(검토 요약 1·5, 153638 실측 3~8°)."""
    m = int(rng.integers(2, 6))
    seg = hi[-m:] if end == "right" else hi[:m][::-1]  # 줄 안쪽 → 끝 순서로 누적(끝 패가 가장 많이 흐름)
    sign, tsign = rng.choice([-1, 1]), rng.choice([-1, 1])
    dv = 0.0
    for i in seg:
        dv = sign * min(abs(dv) + th * rng.uniform(0.08, 0.25), 0.8 * th)
        x[i, 1] += dv
        x[i, 7] += dv
        _set_tilt(x, i, _tilt(x[i:i + 1])[0] + tsign * rng.uniform(3, 12))
    return {"end": end, "m": m, "moved_end": [int(i) for i in seg], "max_dv_th": round(abs(dv) / th, 2)}


def _step(x: np.ndarray, hi: list[int], rng: np.random.Generator, th: float) -> dict:
    """계단: 2~4 덩이(2장 이상), 덩이마다 N(0, 0.45)(±1.2 로 자름) th, 평균을 빼 줄 전체 평행이동은 없애고 이웃 덩이 차이 하나는 0.3 th 이상(검토 요약 6)."""
    k = int(rng.integers(2, 5))
    groups = None
    for _ in range(30):
        cuts = sorted(rng.choice(np.arange(2, len(hi) - 1), size=k - 1, replace=False).tolist())
        gs = np.split(np.array(hi), cuts)
        if min(len(g) for g in gs) < 2:
            continue
        offs = np.clip(rng.normal(0, 0.45, len(gs)), -1.2, 1.2)
        offs = offs - offs.mean()
        diff = np.abs(np.diff(offs))
        # 이웃 덩이 차이 상한(검토 v2 요약 1): 끝 덩이(이웃 하나)는 0.9 th, 가운데는 1.2 th — 153638 中中中 은 가운데 덩이 1.07~1.24.
        # 끝 덩이가 더 비키면 줄에서 수직으로 완전히 떨어진 '떼어 둔 2장' 처럼 보인다.
        cap = np.full(len(diff), 1.2)
        cap[0] = cap[-1] = 0.9
        if diff.max() >= 0.3 and (diff <= cap).all():
            groups = gs
            break
    if groups is None:
        groups = np.split(np.array(hi), [len(hi) // 2])
        offs = np.array([-0.25, 0.25]) * rng.choice([-1, 1])
    for g, o in zip(groups, offs):
        x[g, 1] += o * th
        x[g, 7] += o * th
    return {"groups": [len(g) for g in groups], "off_th": [round(float(o), 2) for o in offs]}


def _bend_once(x: np.ndarray, y: np.ndarray, hi: list[int], rng: np.random.Generator, mode: str) -> dict:
    th = float(np.median(x[hi, 3])) / 10  # 패 높이(펠트 분율)
    tw = float(np.median(x[hi, 2])) / 10
    loose = list(np.flatnonzero(y == LOOSE))
    u0, u1 = x[hi[0], 0], x[hi[-1], 0]
    # 흘릴 수 없는 끝: 가까이 진짜 loose 가 있거나, 끝 패가 이미 0.3 tw 넘게 떨어져 있음(검토 요약 3 — hand 라벨인 떨어진 패를 더 흘리면 '떨어져도 손패' 를 배움)
    ok_end = {"right": not any(x[i, 0] > u1 and x[i, 0] - u1 < 4 * tw for i in loose) and _gap_at(x, hi, "right", tw) <= 0.3,
              "left": not any(x[i, 0] < u0 and u0 - x[i, 0] < 4 * tw for i in loose) and _gap_at(x, hi, "left", tw) <= 0.3}
    ends = [e for e, ok in ok_end.items() if ok]
    info: dict = {"mode": None, "moved": []}
    if mode == "end" and not ends:
        mode = "step"
    if mode in ("step", "both"):
        info.update(_step(x, hi, rng, th))
        info["moved"] = [int(i) for i in hi]
    if mode in ("end", "both") and ends:
        end = ends[0] if len(ends) == 1 else ("right" if rng.random() < 0.7 else "left")
        e = _end(x, hi, rng, end, th)
        info.update(e)
        if mode == "end":
            info["moved"] = e["moved_end"]
    info["mode"] = mode if (mode != "both" or "end" in info) else "step"
    return info


def bend(x: np.ndarray, y, rng: np.random.Generator, mode: str | None = None, tries: int = 15) -> tuple[np.ndarray, dict]:
    """(변형한 x 사본, 무엇을 했는지). 손패가 8장 미만·rot 특징 아님·tries 번 모두 걸리면 그대로(mode None).
    걸리는 것: 새로 생긴 겹침 > 0.15 tw(회전 사각형), 원래 자리 크롭 선(v ≥ 0.95) 안에 있던 손패가 선 밖으로(검토 요약 4)."""
    y = np.asarray(y)
    hi = hand_index(x, y)
    if len(hi) < 8 or x.shape[1] < 11:
        return x.copy(), {"mode": None, "moved": []}
    tw = float(np.median(x[hi, 2])) / 10
    # 손패 앞면에 붙은 뒷면 띠(패 자신의 뒷면 아랫단, 125839·131411): 앞면과 20% 넘게 겹친 뒷면 상자는 그 앞면과 같이 옮긴다(검토 v2 요약 3)
    backs = [j for j in range(len(x)) if x[j, 4] == 1]
    attach = {}
    for i in hi:
        ci = _corners(x[i])
        for j in backs:
            if abs(x[i, 0] - x[j, 0]) < 0.1 and abs(x[i, 1] - x[j, 1]) < 0.1 and _depth(ci, _corners(x[j])) > 0.2 * min(x[i, 3], x[j, 3]) / 10:
                attach.setdefault(i, []).append(j)
    for t in range(tries):
        xb = x.copy()
        r = rng.random()
        m = mode or ("end" if r < 0.45 else "step" if r < 0.75 else "both")  # 153638 은 계단 + 끝 흐름이 함께(검토 요약 7)
        info = _bend_once(xb, y, hi, rng, m)
        tied = sorted({j for i in info["moved"] for j in attach.get(i, [])})
        for i in info["moved"]:
            for j in attach.get(i, []):
                xb[j, 1] = x[j, 1] + (xb[i, 1] - x[i, 1])
                xb[j, 7] = x[j, 7] + (xb[i, 7] - x[i, 7])
        if tied:
            info["tied_backs"] = [int(j) for j in tied]
            info["moved"] = info["moved"] + [int(j) for j in tied]
        if _new_overlap(x, xb, info["moved"], tw):
            continue
        if any(x[i, 1] >= 0.95 and xb[i, 1] < 0.95 for i in info["moved"]):
            continue
        info["tries"] = t + 1
        return xb, info
    return x.copy(), {"mode": None, "moved": []}


def real_scenes(feat: str = "rot") -> list[dict]:
    """role_set.main 과 같은 실제 장면(ROLE_LABELS, 기본 labels_obb.json 을 쓰려면 env 로)."""
    import os

    os.environ.setdefault("ROLE_LABELS", "labels_obb.json")
    import role_set as rs
    import seat_grow as sg

    labels = json.loads((rs.OUT / rs.LABELS).read_text(encoding="utf-8"))
    backs = json.loads(rs.BACKS.read_text(encoding="utf-8")) if rs.BACKS.exists() else {}
    rects_all = json.loads(rs.RECTS.read_text(encoding="utf-8")) if feat == "rot" else None
    grids = {s["name"]: s["grid"] for s in sg.scenes()}
    out = []
    excluded = set(getattr(sg, "EXCLUDED", ()))  # 가림·사용자 문제 사진은 보강 재료에서 뺀다
    for name, rec in labels.items():
        if name in excluded:
            continue
        x, y = rs.scene_tokens(rec, grids[name], backs.get(name, []), True, feat, rs.scene_rects(name, rects_all))
        out.append(dict(name=name, x=x, y=y))
    return out


def check(n: int, seed: int) -> None:
    """검토용 그림: 장면마다 원본(왼쪽)·변형(오른쪽), 화료자 손패 띠만 크게. 손패 = 파랑 테두리, 움직인 패 = 빨강 점, loose = 노랑."""
    from PIL import Image, ImageDraw

    rng = np.random.default_rng(seed)
    scenes = real_scenes()
    out = HERE / "data" / "role" / "bend_check"
    out.mkdir(parents=True, exist_ok=True)
    col = {0: "blue", 1: "cyan", 2: "orange", 3: "red", 4: "magenta", 5: "yellow", -1: "gray"}
    index = []
    picks = [scenes[i % len(scenes)] for i in rng.permutation(max(n, len(scenes)))[:n]]
    for j, s in enumerate(picks):
        xb, info = bend(s["x"], s["y"], rng)
        if info["mode"] is None:
            continue
        hi = hand_index(s["x"], s["y"])
        us = [s["x"][i, 0] for i in hi]
        vs = [s["x"][i, 1] for i in hi]
        cu, cv = (min(us) + max(us)) / 2, float(np.median(vs))
        span = max(us) - min(us) + 0.5
        S, H = 900, 360
        im = Image.new("RGB", (S * 2 + 20, H + 30), (20, 90, 50))
        d = ImageDraw.Draw(im)
        for p, (x, title) in enumerate(((s["x"], "original"), (xb, f"bent ({info['mode']})"))):
            ox = p * (S + 20)
            sc = S / span
            d.text((ox + 5, 5), f"{s['name']} {title}", fill="white")
            for row, lab, i in zip(x, s["y"], range(len(x))):
                u, v, w, h = row[0], row[1], row[2] / 10, row[3] / 10
                if abs(u - cu) > span / 2 + w or abs(v - cv) > H / 2 / sc:
                    continue
                t = math.atan2(row[9], row[10]) / 2
                cs, sn = math.cos(t), math.sin(t)
                px, py = ox + S / 2 + (u - cu) * sc, 30 + H / 2 + (v - cv) * sc
                pts = [(px + (dx * cs - dy * sn) * sc, py + (dx * sn + dy * cs) * sc) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
                d.polygon(pts, fill=(200, 200, 230) if row[4] else "white", outline=col[int(lab)], width=3)
                if p == 1 and i in info.get("moved_end", []):
                    d.ellipse((px - 5, py - 5, px + 5, py + 5), fill="red")
        f = f"{j:02d}_{s['name']}.png"
        im.save(out / f)
        index.append(dict(file=f, scene=s["name"], **info))
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장", out, len(index))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    check(a.n, a.seed)
