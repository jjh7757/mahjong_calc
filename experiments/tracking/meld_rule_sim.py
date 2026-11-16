# 울기 픽셀 추적의 "늘어남" 규칙을 저장해 둔 프레임별 모서리 통계(corner_series.dart 결과, 테두리까지 든 통째 칸)로 다시 돌려 견준다(2026-11-16).
#   python experiments/tracking/meld_rule_sim.py <captures 폴더> <aspect 보정 1|0.75> <corner json>...
# 규칙: white = 흰 면이 패 1장 이상 늘면(예전), pat<θ> = 무늬 넓이가 패 θ장 분량 이상 늘면.
# MeldTracker(pixelOnly) 와 같은 순서: 장면 전체 변화면 기준 버림 → 직전 프레임과 다르면(diff > 0.03) 움직이는 중 → 같으면 기준과 견줌.
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
caps_dir, scale = sys.argv[1], float(sys.argv[2])
SIDES = ["bottom", "right", "top", "left"]
RULES = ["white", "pat0.1", "pat0.15", "pat0.2"]


def diff(a, b):
    w = min(a[0], b[0])
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + (abs(a[2] - b[2]) + abs(a[3] - b[3])) * w


def sim(frames, frac, side, rule):
    th = float(rule[3:]) if rule.startswith("pat") else None
    base = last = None
    out = []
    for x in frames:
        if x["shift"]:
            base = last = None
        cur = x["c"][side]
        prev, last = last, cur
        if base is None or prev is None:
            base = cur
            continue
        if diff(cur, prev) > 0.03:
            continue
        dw, dp = (cur[0] - base[0]) / frac, (cur[1] - base[1]) / frac
        if th is None:
            if abs(dw) >= 1:
                if dw > 0:
                    out.append((x["t"][11:19], round(dw, 1), round(dp, 2)))
                base = cur
        else:
            if abs(dw) >= 1 or abs(dp) >= th:
                if dp >= th:
                    out.append((x["t"][11:19], round(dw, 1), round(dp, 2)))
                base = cur
    return out


def stamp(n):
    return n[:15]


names = sorted(d for d in os.listdir(caps_dir))
tracks = [n for n in names if n.endswith("_track")]
caps = [n for n in names if re.fullmatch(r"\d{8}_\d{6}", n) and os.path.exists(os.path.join(caps_dir, n, "meta.json"))]
tot = {r: dict(ev=0, false=0, seen=0) for r in RULES}
n_no = n_meld = 0
for f in sys.argv[3:]:
    data = json.load(open(f, encoding="utf-8"))
    for name in sorted(data):
        d = data[name]
        nxt = min((t for t in tracks if stamp(t) > stamp(name)), default="99999999_999999")
        mine = [c for c in caps if stamp(name) < c <= stamp(nxt)]
        win = winner = None
        melds = []
        for c in mine:
            m = json.load(open(os.path.join(caps_dir, c, "meta.json"), encoding="utf-8"))
            mg = m.get("merge")
            if not mg or mg.get("riichi_seats_photo") is None:
                continue
            win = win or c[9:11] + ":" + c[11:13] + ":" + c[13:15]
            winner, melds = m.get("winner_side"), mg.get("melds") or []
        if not winner:
            continue
        frames = [x for x in d["frames"] if x["t"][11:19] <= win]
        line = [name[9:15], "화료", winner, f"울기 {len(melds)}"]
        if melds:
            n_meld += 1
        else:
            n_no += 1
        for r in RULES:
            ev = {s: sim(frames, d["tile_frac"][s] * scale, s, r) for s in SIDES}
            n = sum(len(v) for v in ev.values())
            tot[r]["ev"] += n
            if melds:
                tot[r]["seen"] += bool(ev[winner])
            else:
                tot[r]["false"] += len(ev[winner])
            line.append(f"| {r} {n}회·화료자 {len(ev[winner])}" + (f" {ev[winner][:3]}" if melds and r != 'white' else ""))
        print(*line)
print()
print(f"화료자 울기 없는 판 {n_no} · 있는 판 {n_meld}")
for r in RULES:
    t = tot[r]
    print(f"{r}: 늘어남 {t['ev']}회 · 울기 없는 화료자 모서리(헛) {t['false']} · 울기 있는 화료자 모서리를 본 판 {t['seen']}/{n_meld}")
