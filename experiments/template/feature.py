"""특징점 매칭(SIFT·ORB·AKAZE)으로 패 종류 맞히기(학습 없음): 시험 패와 기준 그림의 특징점을 짝짓고,
비율 검사 + RANSAC 호모그래피로 기하가 맞는 짝(inlier) 수가 가장 많은 종류를 답으로.

  python -I experiments/template/feature.py [sift orb akaze] [--warp]

시험·기준 그림 나누기는 match_shift.py 와 같다(B·C·D 손패 78장, 강은 장면끼리 겹쳐 뺌).
--warp: 흰 면을 회전 대신 네 꼭짓점 원근 펴기(warpPerspective)로 세운다.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter, defaultdict

import cv2
import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import faces as F  # noqa: E402

SIZE = (120, 160)
WARP = "--warp" in sys.argv


def warp_face(im: np.ndarray, out=SIZE) -> np.ndarray:
    """흰 면 바깥 윤곽을 사각형으로 근사해 원근 펴기. 네 꼭짓점이 안 나오면 faces.face(회전)."""
    h, w = im.shape[:2]
    m = F.white_mask(im)
    k = max(1, round(min(h, w) * 0.04))
    er = cv2.erode(m, np.ones((k, k), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(er, 8)
    best, score = None, -1.0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < 0.04 * h * w:
            continue
        cx, cy = cent[i]
        sc = a / (h * w) - 2.0 * (((cx - w / 2) / w) ** 2 + ((cy - h / 2) / h) ** 2)
        if sc > score:
            best, score = i, sc
    if best is None:
        return F.face(im, out)[0]
    comp = cv2.dilate((lab == best).astype(np.uint8), np.ones((k, k), np.uint8)) & m
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(max(cs, key=cv2.contourArea))
    peri = cv2.arcLength(hull, True)
    quad = None
    for eps in (0.02, 0.04, 0.06, 0.08):
        q = cv2.approxPolyDP(hull, eps * peri, True)
        if len(q) == 4:
            quad = q.reshape(4, 2).astype(np.float32)
            break
    if quad is None:
        return F.face(im, out)[0]
    # 꼭짓점 순서: 왼위·오위·오아래·왼아래
    s, d = quad.sum(1), np.diff(quad, axis=1).ravel()
    src = np.array([quad[s.argmin()], quad[d.argmin()], quad[s.argmax()], quad[d.argmax()]], np.float32)
    wtop, wl = np.linalg.norm(src[1] - src[0]), np.linalg.norm(src[3] - src[0])
    if wtop > wl:  # 가로로 누운 패는 세로로
        src = np.roll(src, -1, axis=0)
    dst = np.array([[0, 0], [out[0] - 1, 0], [out[0] - 1, out[1] - 1], [0, out[1] - 1]], np.float32)
    return cv2.warpPerspective(im, cv2.getPerspectiveTransform(src, dst), out, borderMode=cv2.BORDER_REPLICATE)


def prep(f: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(2.0, (4, 4)).apply(g)


DETECTORS = {
    "sift": lambda: (cv2.SIFT_create(nfeatures=300, contrastThreshold=0.02), cv2.NORM_L2),
    "orb": lambda: (cv2.ORB_create(nfeatures=300, edgeThreshold=8, patchSize=15, fastThreshold=5), cv2.NORM_HAMMING),
    # akaze: opencv 5 본체에 없음(contrib)
}


def inliers(kt, dt, kr, dr, bf) -> int:
    """비율 검사(0.8) 뒤 RANSAC 호모그래피 inlier 수. 짝이 4 미만이면 그 수."""
    if dt is None or dr is None or len(dt) < 2 or len(dr) < 2:
        return 0
    good = [m for m, n in (p for p in bf.knnMatch(dt, dr, k=2) if len(p) == 2) if m.distance < 0.8 * n.distance]
    if len(good) < 5:
        return len(good) // 2
    a = np.float32([kt[m.queryIdx].pt for m in good])
    b = np.float32([kr[m.trainIdx].pt for m in good])
    H, mask = cv2.findHomography(a, b, cv2.RANSAC, 6.0)
    if H is None:
        return 0
    return int(mask.sum())


def slot(r):
    return r["path"].name.split("_")[3] if r["group"] != "S" else "set2"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(DETECTORS)
    rows = F.store_crops() + F.set2_crops()
    for r in rows:
        im = F.read(r["path"])
        r["g"] = prep(warp_face(im) if WARP else F.face(im, SIZE)[0])
    test = [r for r in rows if r["group"] in "BCD" and r["src"] == "hand"]
    modes = {
        "loso(매장+집)": lambda t: [r for r in rows if r["group"] != t["group"]],
        "loso Q 제외": lambda t: [r for r in rows if r["group"] not in (t["group"], "Q")],
        "A·E·Q+집": lambda t: [r for r in rows if r["group"] not in "BCD"],
        "집 패만": lambda t: [r for r in rows if r["group"] == "S"],
    }
    if os.environ.get("CEIL") == "1":
        # 상한(참고): 같은 장면의 다른 사진(같은 패·거의 같은 각도)을 기준 그림에 더함 = 고정 카메라로 매장 패를 미리 등록한 경우
        modes = {"상한: 같은 장면 다른 사진+전부": lambda t: [r for r in rows if r["photo"] != t["photo"]],
                 "상한: 같은 장면 다른 사진만": lambda t: [r for r in rows if r["group"] == t["group"] and r["photo"] != t["photo"]],
                 # 현실적: 같은 패 세트·같은 카메라지만 시험 패가 놓였던 자리(두 사진 모두)는 뺌 = 다른 자리의 같은 종류만
                 "같은 장면 다른 자리+전부": lambda t: [r for r in rows if not (r["group"] == t["group"] and slot(r) == slot(t))]}
    for name in names:
        det, norm = DETECTORS[name]()
        bf = cv2.BFMatcher(norm)
        t0 = time.perf_counter()
        for r in rows:
            r["kp"], r["d"] = det.detectAndCompute(r["g"], None)
            g180 = cv2.rotate(r["g"], cv2.ROTATE_180)
            r["kp180"], r["d180"] = det.detectAndCompute(g180, None)
        t_det = (time.perf_counter() - t0) / (2 * len(rows)) * 1000
        nkp = np.median([len(r["kp"]) for r in rows])
        print(f"== {name} {'원근 펴기' if WARP else '회전'}  특징점 중앙 {nkp:.0f}개, 검출 {t_det:.1f}ms/장", flush=True)
        for mname, refs_for in modes.items():
            ok, conf, per = 0, Counter(), defaultdict(lambda: [0, 0])
            t0, pairs = time.perf_counter(), 0
            for t in test:
                best = defaultdict(int)
                for r in refs_for(t):
                    s = max(inliers(t["kp"], t["d"], r["kp"], r["d"], bf),
                            inliers(t["kp180"], t["d180"], r["kp"], r["d"], bf))
                    pairs += 1
                    best[r["code"]] = max(best[r["code"]], s)
                pred = max(best, key=best.get)
                hit = pred == t["code"]
                ok += hit
                per[t["group"]][0] += hit
                per[t["group"]][1] += 1
                if not hit:
                    conf[f"{t['code']}→{pred}"] += 1
            dt = time.perf_counter() - t0
            print(f"  {mname:14s} 손패 {ok}/{len(test)} ({ok/len(test):.0%})  "
                  + " ".join(f"{g} {a}/{b}" for g, (a, b) in sorted(per.items()))
                  + f"  | 패 한 장 {dt/len(test)*1000:.0f}ms (기준 {pairs//len(test)}장 비교)", flush=True)
            print("     자주 틀림:", ", ".join(f"{k}×{v}" for k, v in conf.most_common(8)), flush=True)


if __name__ == "__main__":
    main()
