"""match.py 의 개선판 시험: 패 옆면 두께를 잘라낸 안쪽 면 + 위치(±)·크기(0.85~1.15) 찾기(opencv matchTemplate).
시험은 B·C·D 손패만(강 크롭은 갤러리 장면끼리 같은 강이 겹쳐 새는 값). 기준 그림: 시험 장면 아닌 매장 크롭(Q 포함/제외) + 집 패.
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

import cv2
import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import faces as F  # noqa: E402

BIG = (60, 80)      # 시험 패(여유를 둔 크기)
INNER = 0.82        # 기준 그림은 안쪽 82% 만(옆면·테두리 제외)


def prep(f):
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    g = cv2.createCLAHE(2.0, (4, 4)).apply(g)
    return cv2.GaussianBlur(g, (3, 3), 0)


def inner(g, k=INNER):
    h, w = g.shape
    dy, dx = round(h * (1 - k) / 2), round(w * (1 - k) / 2)
    return g[dy:h - dy, dx:w - dx]


def score(test_big, ref_inner_by_scale):
    best = -1.0
    for t in (test_big, cv2.rotate(test_big, cv2.ROTATE_180)):
        for r in ref_inner_by_scale:
            if r.shape[0] > t.shape[0] or r.shape[1] > t.shape[1]:
                continue
            best = max(best, float(cv2.matchTemplate(t, r, cv2.TM_CCOEFF_NORMED).max()))
    return best


def slot(r):
    return r["path"].name.split("_")[3] if r["group"] != "S" else "set2"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = F.store_crops() + F.set2_crops()
    for r in rows:
        f, _ = F.face(F.read(r["path"]), BIG)
        g = prep(f)
        r["big"] = g
        ri = inner(g)
        r["refs"] = [cv2.resize(ri, (round(ri.shape[1] * s), round(ri.shape[0] * s))) for s in (0.85, 0.92, 1.0, 1.08)]
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
    for name, refs_for in modes.items():
        ok, conf, per = 0, Counter(), defaultdict(lambda: [0, 0])
        for t in test:
            best = defaultdict(lambda: -9.0)
            for r in refs_for(t):
                best[r["code"]] = max(best[r["code"]], score(t["big"], r["refs"]))
            pred = max(best, key=best.get)
            hit = pred == t["code"]
            ok += hit
            per[t["group"]][0] += hit
            per[t["group"]][1] += 1
            if not hit:
                conf[f"{t['code']}→{pred}"] += 1
        print(f"{name:14s} 손패 {ok}/{len(test)} ({ok/len(test):.0%})  " + " ".join(f"{g} {a}/{b}" for g, (a, b) in sorted(per.items())))
        print("   자주 틀림:", ", ".join(f"{k}×{v}" for k, v in conf.most_common(8)))


if __name__ == "__main__":
    main()
