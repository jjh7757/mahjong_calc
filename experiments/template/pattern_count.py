"""패 무늬를 필터로 뽑아 코드로 세는 검증기(2026-10-27, 사용자 요청). 학습·기준 그림 없음.

패 면(faces.face) → 무늬 마스크(흰 면보다 어둡거나 색이 진한 픽셀, 가장자리 6% 제외) → 덩어리(구멍 메움) →
  수패 종류: 무늬 없음 = 白(z) / 빨간 무늬가 아래쪽·검은 무늬가 위쪽 = 만(m) / 덩어리가 대부분 둥글면 통(p) / 대부분 길쭉하면 삭(s) / 그 밖 모름
  개수: 통 = 둥근 덩어리 수(하나가 면의 15% 넘게 크면 1통), 삭 = 길쭉한 덩어리 수
Gemini 답(code)과 어긋나면 표시(flag) — 모르면 말하지 않는다.

규칙 숫자는 패 그림의 일반 지식으로 정하고, 개발(눈으로 보며 고치기)은 집 패 세트(tileset2, 평가 밖)로만 한다.
평가: B·C·D 손패(tile_tool/tiles_raw) + B·C·D 강 전체(tile_tool/river_raw, 눈으로 적은 정답) — 이 결과로 규칙을 고치면 "본 사진" 이 된다.
참고(평가 밖, 숫자 따로): A·E 손패·강, 매장 촬영 크롭(Q).

  python -I experiments/template/pattern_count.py [--dev] [--sheet]
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import faces as F  # noqa: E402

OUT = Path(__file__).parent / "results_pattern"
SIZE = (120, 160)  # 패 면을 이 크기로(가로, 세로)

# Gemini 가 기록에 남긴 오독(정답 → 읽은 답), field_20261024/NOTES.md·problem_log 에서 모음(만수 4m→8m 는 검증 대상 밖)
CONFUSIONS = [("9s", "6s"), ("7s", "6s"), ("3s", "2s"), ("9s", "8s"), ("5p", "4p"), ("6p", "4p"), ("3s", "4s"),
              ("0s", "9s"), ("9p", "7p"), ("8s", "9s"), ("7p", "4p"), ("7p", "3p"), ("7s", "9s"), ("6p", "8s"),
              ("6s", "9s"), ("6s", "7s"), ("9p", "5s"), ("9s", "9p"), ("6s", "8s"), ("5p", "6p"), ("4s", "2s"),
              ("3p", "4p"), ("6p", "8p")]


def num(code: str) -> int:
    return 5 if code[0] == "0" else int(code[0])


def ink_mask(face: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    white_v = np.percentile(v, 90)
    m = ((v < white_v * 0.72) | ((s > 70) & (v < white_v * 1.05))).astype(np.uint8)
    h, w = m.shape
    by, bx = int(h * 0.06), int(w * 0.06)
    m[:by], m[-by:], m[:, :bx], m[:, -bx:] = 0, 0, 0, 0
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def blobs(m: np.ndarray) -> list[dict]:
    """구멍을 메운 덩어리(통수 고리 → 원판) 목록. 작은 점(면적 0.4% 미만)은 버림."""
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area_face = m.shape[0] * m.shape[1]
    out = []
    for c in cs:
        a = cv2.contourArea(c)
        if a < 0.004 * area_face:
            continue
        (cx, cy), (rw, rh), _ = cv2.minAreaRect(c)
        long_, short = max(rw, rh), max(1.0, min(rw, rh))
        x, y, w, h = cv2.boundingRect(c)
        per = cv2.arcLength(c, True)
        out.append({"area": a, "elong": long_ / short, "fill": a / max(1.0, rw * rh), "cx": cx, "cy": cy,
                    "circ": 4 * np.pi * a / max(1.0, per * per), "box": (x, y, w, h),
                    "vert": bool(h > 1.5 * w), "long": long_, "short": short})  # vert: 세로로 선 조각(바깥 상자 높이 > 너비 1.5배)
    return out


MIN_FACE_H = 60  # 패 면 높이(px)가 이보다 작으면 무늬가 붙어 보여 세지 않는다(집 패 42×53px 에서 동그라미가 뭉침)


def analyze_v1(face: np.ndarray, src_h: int | None = None) -> dict:
    """→ {suit: m|p|s|z|None, count: int|None, ...}. src_h = 원래 패 면 높이(작으면 말하지 않음)."""
    if src_h is not None and src_h < MIN_FACE_H:
        return {"ink": None, "suit": None, "count": None, "why": f"작음 {src_h}px"}
    face = cv2.resize(face, SIZE, interpolation=cv2.INTER_CUBIC)
    m = ink_mask(face)
    H, W = m.shape
    ink = m.mean()
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    hue, sat = hsv[..., 0], hsv[..., 1]
    red = (m > 0) & (sat > 80) & ((hue < 10) | (hue > 165))
    dark = (m > 0) & ~red
    res = {"ink": round(float(ink), 3), "suit": None, "count": None}
    if ink < 0.02:
        res.update(suit="z", why="무늬 없음(白)")
        return res
    ys = np.arange(H)[:, None].repeat(W, 1)
    bs = blobs(m)
    if not bs:
        return res
    is_round = lambda b: b["elong"] < 1.35 and b["circ"] > 0.75  # noqa: E731
    is_long = lambda b: b["elong"] > 1.6  # noqa: E731
    tot = sum(b["area"] for b in bs)
    round_a = sum(b["area"] for b in bs if is_round(b))
    long_a = sum(b["area"] for b in bs if is_long(b))
    res.update(round=round(round_a / tot, 2), long=round(long_a / tot, 2), n_blobs=len(bs))
    if round_a / tot > 0.75:
        rs = [b for b in bs if is_round(b)]
        if max(b["area"] for b in rs) > 0.15 * H * W:
            res.update(suit="p", count=1, why="큰 원 하나")
            return res
        med = statistics.median(b["area"] for b in rs)
        n = sum(1 for b in rs if b["area"] > 0.35 * med)
        if 2 <= n <= 9:
            res.update(suit="p", count=n, why=f"둥근 덩어리 {n}")
        return res
    if long_a / tot > 0.75:
        ls = [b for b in bs if is_long(b)]
        med = statistics.median(b["area"] for b in ls)
        n = sum(1 for b in ls if b["area"] > 0.35 * med)
        if 2 <= n <= 9:
            res.update(suit="s", count=n, why=f"길쭉한 덩어리 {n}")
        return res
    # 만수: 빨간 萬 이 아래, 검은 숫자가 위 — 빨간 무늬의 대부분이 아래 45% 에, 검은 무늬 중심이 위쪽(둥글거나 길쭉한 무늬가 아닐 때만)
    if red.sum() > 0.03 * H * W and dark.sum() > 0.01 * H * W:
        red_low = (red & (ys > H * 0.55)).sum() / red.sum()
        dark_cy = ys[dark].mean() / H
        if red_low > 0.7 and dark_cy < 0.45:
            res.update(suit="m", why=f"빨강 아래 {red_low:.2f}, 검정 중심 {dark_cy:.2f}")
    return res


def center_tile(face: np.ndarray) -> np.ndarray:
    """패 면이 이웃 패와 붙어 넓게 잡히면(가로 > 세로 × 0.85) 가운데에서 패 비율(가로 = 세로 × 0.75)만 남긴다.
    크롭은 패 한 장을 가운데 두고 자른 것(파이프라인에서는 YOLO 상자)."""
    h, w = face.shape[:2]
    if w <= 0.85 * h:
        return face
    tw = int(0.75 * h)
    x0 = (w - tw) // 2
    return face[:, x0:x0 + tw]


def circles(m: np.ndarray) -> int:
    """구멍을 메운 무늬에서 원 중심 개수: 거리 변환의 봉우리(반지름이 가장 큰 원의 절반 이상, 서로 반지름만큼 떨어짐)."""
    filled = np.zeros_like(m)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(filled, cs, -1, 1, -1)
    d = cv2.distanceTransform(filled, cv2.DIST_L2, 5)
    rmax = d.max()
    if rmax < 3:
        return 0
    k = max(3, int(rmax) | 1)
    peaks = (d == cv2.dilate(d, np.ones((k, k), np.uint8))) & (d > 0.5 * rmax)
    n, _, _, cent = cv2.connectedComponentsWithStats(peaks.astype(np.uint8), 8)
    pts = [tuple(c) for c in cent[1:]]
    kept = []
    for p in sorted(pts, key=lambda p: -d[int(p[1]), int(p[0])]):
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > (0.9 * rmax) ** 2 for q in kept):
            kept.append(p)
    return len(kept)


def analyze(face: np.ndarray, src_h: int | None = None) -> dict:
    """v2(B·C·D 첫 평가를 본 뒤 고침): 가운데 패만 / 동그라미는 거리 변환 봉우리로 / 막대는 세로로 선 길쭉한 조각이고
    굵기·길이가 고를 때만. → {suit: m|p|s|z|None, count: int|None, ...}"""
    if src_h is not None and src_h < MIN_FACE_H:
        return {"ink": None, "suit": None, "count": None, "why": f"작음 {src_h}px"}
    face = cv2.resize(center_tile(face), SIZE, interpolation=cv2.INTER_CUBIC)
    m = ink_mask(face)
    H, W = m.shape
    ink = m.mean()
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    hue, sat = hsv[..., 0], hsv[..., 1]
    red = (m > 0) & (sat > 80) & ((hue < 10) | (hue > 165))
    dark = (m > 0) & ~red
    res = {"ink": round(float(ink), 3), "suit": None, "count": None}
    if ink < 0.02:
        res.update(suit="z", why="무늬 없음(白)")
        return res
    bs = blobs(m)
    if not bs:
        return res
    tot = sum(b["area"] for b in bs)
    # 통수: 덩어리 윤곽이 둥글거나(원) 둥근 것들이 붙은 모양 — 원형도 대신 "구멍 메운 무늬 넓이 / 원 중심 수로 본 원 넓이" 가 맞는지
    round_a = sum(b["area"] for b in bs if b["elong"] < 1.35 and b["circ"] > 0.75)
    sticks = [b for b in bs if b["elong"] > 1.8 and b["vert"]]
    stick_a = sum(b["area"] for b in sticks)
    res.update(round=round(round_a / tot, 2), long=round(stick_a / tot, 2), n_blobs=len(bs))
    if round_a / tot > 0.6:
        rs = [b for b in bs if b["elong"] < 1.35 and b["circ"] > 0.75]
        if len(rs) == 1 and rs[0]["area"] > 0.15 * H * W:
            res.update(suit="p", count=1, why="큰 원 하나")
            return res
        n = circles(m)
        if 2 <= n <= 9:
            res.update(suit="p", count=n, why=f"원 중심 {n}")
        return res
    if stick_a / tot > 0.8 and len(sticks) >= 2:
        ws = [b["short"] for b in sticks]
        ls = [b["long"] for b in sticks]
        cv_w = statistics.pstdev(ws) / statistics.mean(ws)
        cv_l = statistics.pstdev(ls) / statistics.mean(ls)
        res.update(cv_w=round(cv_w, 2), cv_l=round(cv_l, 2))
        if cv_w < 0.3 and cv_l < 0.3 and 2 <= len(sticks) <= 9:
            res.update(suit="s", count=len(sticks), why=f"고른 막대 {len(sticks)}")
        return res
    ys = np.arange(H)[:, None].repeat(W, 1)
    if red.sum() > 0.03 * H * W and dark.sum() > 0.01 * H * W:
        red_low = (red & (ys > H * 0.55)).sum() / red.sum()
        dark_cy = ys[dark].mean() / H
        if red_low > 0.7 and dark_cy < 0.45:
            res.update(suit="m", why=f"빨강 아래 {red_low:.2f}, 검정 중심 {dark_cy:.2f}")
    return res


def face_height(im: np.ndarray) -> int:
    """faces.face 와 같은 방법으로 찾은 흰 면의 원래 높이(px)."""
    m = F.white_mask(im)
    h, w = im.shape[:2]
    k = max(1, round(min(h, w) * 0.04))
    er = cv2.erode(m, np.ones((k, k), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(er, 8)
    best = max(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA] / (h * w)
               - 2 * (((cent[i][0] - w / 2) / w) ** 2 + ((cent[i][1] - h / 2) / h) ** 2), default=None)
    if best is None:
        return 0
    c, _ = cv2.findContours((lab == best).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    (_, _), (rw, rh), _ = cv2.minAreaRect(max(c, key=cv2.contourArea))
    return int(max(rw, rh))


def flag(v: dict, code: str) -> str | None:
    """검증기 결과 v 와 Gemini 답 code 가 어긋나면 이유. 모르면 None."""
    suit = code[-1]
    if v["suit"] is None:
        return None
    if v["suit"] == "z":
        return None if suit == "z" else "무늬 없음인데 수패"
    if v["suit"] != suit:
        return f"종류 {v['suit']} ≠ {suit}"
    if suit in "ps" and v["count"] is not None and v["count"] != num(code):
        return f"개수 {v['count']} ≠ {num(code)}"
    return None


def load(sets: str) -> list[dict]:
    rows = []
    T = F.TOOL
    for p in sorted((T / "tiles_raw").glob("*.png")):
        rows.append({"path": p, "code": p.stem.split("_")[-1], "group": p.name[0], "src": "hand", "photo": "_".join(p.name.split("_")[:2])})
    for p in sorted((T / "river_raw").glob("*.png")):
        rows.append({"path": p, "code": p.stem.split("_")[-1], "group": p.name[0], "src": "river", "photo": "_".join(p.name.split("_")[:2])})
    for line in (T / "more_ok.txt").read_text(encoding="utf-8").split():
        f, code = line.split(":")
        rows.append({"path": T / "more_raw" / f, "code": code, "group": "Q", "src": "store", "photo": f.split("_")[1]})
    rows += [dict(r, src="set2") for r in F.set2_crops()]
    return [r for r in rows if r["group"] in sets]


def evaluate(rows: list[dict], title: str) -> dict:
    vs = []
    for r in rows:
        f, info = F.face(F.read(r["path"]), (96, 128))
        vs.append(analyze(f, face_height(F.read(r["path"])) if info["found"] else 0))
    n = len(rows)
    suit_said = [(r, v) for r, v in zip(rows, vs) if v["suit"]]
    suit_ok = sum(1 for r, v in suit_said if v["suit"] == r["code"][-1])
    ps = [(r, v) for r, v in zip(rows, vs) if r["code"][-1] in "ps"]
    cnt_said = [(r, v) for r, v in ps if v["suit"] == r["code"][-1] and v["count"] is not None]
    cnt_ok = sum(1 for r, v in cnt_said if v["count"] == num(r["code"]))
    false_alarm = [(r, v) for r, v in zip(rows, vs) if flag(v, r["code"])]
    # Gemini 오독을 걸러 내나: 정답 t 인 패마다, 기록된 오독 t→r 이 들어왔다고 치고 표시되는지
    catch = defaultdict(lambda: [0, 0])
    for r, v in zip(rows, vs):
        for t, wrong in CONFUSIONS:
            if r["code"] == t or (t == "0s" and r["code"] == "0s"):
                catch[(t, wrong)][1] += 1
                catch[(t, wrong)][0] += flag(v, wrong) is not None
    tot_c = sum(b for _, b in catch.values())
    hit_c = sum(a for a, _ in catch.values())
    print(f"\n[{title}] 패 {n}장 (통·삭 {len(ps)}장)")
    print(f"  수패 종류: 말함 {len(suit_said)}/{n} ({len(suit_said) / max(1, n):.0%}), 말한 것 중 정답 {suit_ok}/{len(suit_said)} ({suit_ok / max(1, len(suit_said)):.0%})")
    print(f"  통·삭 개수: 말함 {len(cnt_said)}/{len(ps)} ({len(cnt_said) / max(1, len(ps)):.0%}), 말한 것 중 정답 {cnt_ok}/{len(cnt_said)} ({cnt_ok / max(1, len(cnt_said)):.0%})")
    print(f"  헛경보(정답인데 표시): {len(false_alarm)}/{n} ({len(false_alarm) / max(1, n):.1%})  — 손패 13장 중 하나라도 헛경보일 확률 ≈ "
          f"{1 - (1 - len(false_alarm) / max(1, n)) ** 13:.0%}")
    print(f"  기록된 Gemini 오독을 표시: {hit_c}/{tot_c} ({hit_c / max(1, tot_c):.0%})")
    for (t, wrong), (a, b) in sorted(catch.items(), key=lambda kv: -kv[1][1]):
        if b:
            print(f"     {t}→{wrong}: {a}/{b}")
    fa = Counter(f"{r['code']}: {flag(v, r['code'])}" for r, v in false_alarm)
    if fa:
        print("  헛경보 예:", "; ".join(f"{k} ×{c}" for k, c in fa.most_common(8)))
    return {"rows": [{"path": str(r["path"]), "code": r["code"], **{k: v[k] for k in v if k != "box"}} for r, v in zip(rows, vs)]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true", help="개발용 집 패 세트(S)만")
    ap.add_argument("--ref", action="store_true", help="평가 밖 참고(A·E·Q)")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    if a.dev:
        evaluate(load("S"), "개발 — 집 패 세트(평가 밖)")
        return
    res = evaluate(load("BCD"), "평가 — B·C·D 손패 + 강")
    (OUT / "eval_bcd.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.ref:
        evaluate(load("AE"), "참고(평가 밖) — A·E 손패 + 강")
        evaluate(load("Q"), "참고(평가 밖) — 매장 촬영 크롭")


if __name__ == "__main__":
    main()
