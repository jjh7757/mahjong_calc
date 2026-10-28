"""템플릿 매칭으로 패 종류 맞히기(학습 없음): 잘라 세운 흰 면을 기준 그림들과 비교해 가장 비슷한 것.

  python -I experiments/template/match.py

시험 = 장면 B·C·D 크롭(손패·강, 평가 세트 규칙). 기준 그림은 시험 장면 사진에서 가져오지 않는다.
  · loso    : 시험 장면을 뺀 매장 크롭 전부 + 집 패(다른 B·C·D 장면 포함, "매장에 기준 그림을 모아 둔" 경우)
  · noBCD   : A·E·Q(매장 촬영) + 집 패만
  · store   : loso 에서 집 패 뺌
  · set2    : 집 패 정면 세트만(다른 패 세트)
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict

import cv2
import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import faces as F  # noqa: E402

W, H = 48, 64
CELL, BINS = 8, 9


def _hog(g: np.ndarray) -> np.ndarray:
    """HOG(opencv 5 에는 HOGDescriptor 가 없다): 8px 칸마다 방향 9칸 히스토그램, 2×2 칸 묶음 정규화."""
    g = g.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=1)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=1)
    mag = np.hypot(gx, gy)
    ang = (np.degrees(np.arctan2(gy, gx)) % 180) / (180 / BINS)
    b = np.minimum(ang.astype(int), BINS - 1)
    cy, cx = g.shape[0] // CELL, g.shape[1] // CELL
    hist = np.zeros((cy, cx, BINS), np.float32)
    for i in range(cy):
        for j in range(cx):
            sl = np.s_[i * CELL:(i + 1) * CELL, j * CELL:(j + 1) * CELL]
            hist[i, j] = np.bincount(b[sl].ravel(), mag[sl].ravel(), BINS)
    blocks = []
    for i in range(cy - 1):
        for j in range(cx - 1):
            v = hist[i:i + 2, j:j + 2].ravel()
            blocks.append(v / (np.linalg.norm(v) + 1e-6))
    return np.concatenate(blocks)


def gray_vec(f):
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    g -= g.mean()
    return (g / (np.linalg.norm(g) + 1e-6)).ravel()


def hog_vec(f):
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    g = cv2.equalizeHist(g)
    v = _hog(g)
    return v / (np.linalg.norm(v) + 1e-6)


def color_vec(f):
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV).astype(np.int32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    ink = (s > 60) & (v > 50)
    red = (ink & ((h < 12) | (h > 160))).astype(np.float32)
    green = (ink & (h > 35) & (h < 95)).astype(np.float32)
    blue = (ink & (h >= 95) & (h <= 135)).astype(np.float32)
    dark = (v < 90).astype(np.float32)
    parts = [cv2.resize(m, (6, 8), interpolation=cv2.INTER_AREA).ravel() for m in (red, green, blue, dark)]
    v = np.concatenate(parts)
    return v / (np.linalg.norm(v) + 1e-6)


METHODS = {
    "gray": lambda f: gray_vec(f),
    "hog": lambda f: hog_vec(f),
    "hog+color": lambda f: np.concatenate([hog_vec(f), 0.6 * color_vec(f)]),
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = F.store_crops() + F.set2_crops()
    for r in rows:
        r["face"], r["info"] = F.face(F.read(r["path"]), (W, H))
        r["face180"] = cv2.rotate(r["face"], cv2.ROTATE_180)
    test = [r for r in rows if r["group"] in "BCD"]
    print(f"시험 크롭 {len(test)}장(B·C·D: 손패 {sum(r['src']=='hand' for r in test)}, 강 {sum(r['src']=='river' for r in test)})")

    def refs_for(t, mode):
        g = t["group"]
        if mode == "loso":
            return [r for r in rows if r["group"] != g]
        if mode == "noBCD":
            return [r for r in rows if r["group"] not in "BCD"]
        if mode == "store":
            return [r for r in rows if r["group"] not in (g, "S")]
        return [r for r in rows if r["group"] == "S"]

    for mname, fn in METHODS.items():
        for r in rows:
            r["v"], r["v180"] = fn(r["face"]), fn(r["face180"])
        for mode in ("loso", "noBCD", "store", "set2"):
            ok = top3 = covered = 0
            conf = Counter()
            per_src = defaultdict(lambda: [0, 0])
            margins = []
            for t in test:
                refs = refs_for(t, mode)
                codes = {r["code"] for r in refs}
                covered += t["code"] in codes
                R = np.stack([r["v"] for r in refs])
                sims = np.maximum(R @ t["v"], R @ t["v180"])
                # 종류별 최고 유사도
                best = defaultdict(lambda: -9.0)
                for r, s in zip(refs, sims):
                    best[r["code"]] = max(best[r["code"]], float(s))
                ranked = sorted(best.items(), key=lambda kv: -kv[1])
                pred = ranked[0][0]
                hit = pred == t["code"]
                ok += hit
                top3 += t["code"] in [c for c, _ in ranked[:3]]
                per_src[t["src"]][0] += hit
                per_src[t["src"]][1] += 1
                margins.append((ranked[0][1] - ranked[1][1], hit))
                if not hit:
                    conf[f"{t['code']}→{pred}"] += 1
            n = len(test)
            # 확신(1·2위 차이) 상위 80% 만 자동으로 쓴다면
            ms = sorted(margins, key=lambda m: -m[0])
            k = int(n * 0.8)
            print(f"{mname:9s} {mode:5s} 정답 {ok}/{n} ({ok/n:.0%})  3위 안 {top3/n:.0%}  기준에 종류 있음 {covered}/{n}  "
                  f"손패 {per_src['hand'][0]}/{per_src['hand'][1]} 강 {per_src['river'][0]}/{per_src['river'][1]}  "
                  f"확신 상위80% 정답 {sum(h for _, h in ms[:k])}/{k}")
            print("          자주 틀림:", ", ".join(f"{k}×{v}" for k, v in conf.most_common(8)))


if __name__ == "__main__":
    main()
