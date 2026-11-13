"""유국 공개 합성 채점: faceup.json(앱 analyzeGridShot) 의 앞면 자리 집합 vs 정답 텐파이 자리.
지금 판정(1등의 1/2 이상)과, 유국용으로 비율 없이 절대 넓이 문턱만 쓰는 안을 같이 본다.
  python -I -X utf8 experiments/draw_reveal/score.py
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
rows = json.loads((HERE / "faceup.json").read_text(encoding="utf-8"))
SCALE2 = 1.0  # 축소본 긴 변 1024 → scale 1


def key(r):
    return len(r["tenpai"])


def report(name, pred_fn):
    ok = Counter()
    tot = Counter()
    seat_ok = seat_tot = 0
    wrong = []
    for r in rows:
        p = set(pred_fn(r))
        t = set(r["tenpai"])
        k = key(r)
        tot[k] += 1
        if p == t:
            ok[k] += 1
        else:
            wrong.append((r["scene"], sorted(t), sorted(p)))
        for s in ("bottom", "right", "top", "left"):
            seat_tot += 1
            seat_ok += (s in p) == (s in t)
    print(f"== {name}: 장면 {sum(ok.values())}/{len(rows)}, 자리 {seat_ok}/{seat_tot}")
    print("   텐파이 수별", {k: f"{ok[k]}/{tot[k]}" for k in sorted(tot)})
    for w in wrong[:12]:
        print("   틀림", w)
    return wrong


report("지금 앱(1등의 1/2 이상, 300px 이상)", lambda r: r["faceUp"])
for th in (300, 500, 700, 900):
    report(f"절대 문턱 {th}px", lambda r, th=th: [s for s, v in r["patterns"].items() if v >= th])

# 무늬 넓이 분포
up, down = defaultdict(list), defaultdict(list)
for r in rows:
    for s, v in r["patterns"].items():
        (up if s in r["tenpai"] else down)[r["set"]].append(v)
for st in up:
    u, d = sorted(up[st]), sorted(down[st])
    print(f"{st}: 공개 최소 {u[0]} 중앙 {u[len(u)//2]} / 비공개 중앙 {d[len(d)//2]} 최대 {d[-1]}")
ms = sorted(r["ms"] for r in rows)
print("판정 시간 ms 중앙/p90/최대", ms[len(ms) // 2], ms[int(len(ms) * 0.9)], ms[-1])

# 펠트 밖 지운 무늬 넓이(feltPatterns[pad], 앱 readFelt 사각형을 pad 만큼 바깥으로)
PADS = ["0.01", "0.02", "0.03", "0.05", "0.08"]
nofelt = sorted({r["scene"] for r in rows if not r.get("feltPatterns")})
print("펠트 못 찾음", nofelt)
best = {}
for pad in PADS:
    for th in (300, 400, 500):
        print()
        w = report(f"펠트+{pad} 문턱 {th}px", lambda r, th=th, pad=pad: [s for s, v in (r["feltPatterns"].get(pad) or r["patterns"]).items() if v >= th])
    up, down = [], []
    for r in rows:
        for s, v in r["feltPatterns"][pad].items():
            (up if s in r["tenpai"] else down).append((v, r["scene"][-6:], s))
    up.sort(); down.sort()
    print(f"   펠트+{pad}: 공개 아래 5 {up[:5]} / 비공개 위 5 {down[-5:]}")
