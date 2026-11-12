"""역할 라벨 v2 에 주인 자리(seat) 초안 더하기(2026-11-11, docs/role_owner_plan_1111.md 3-1·3-2, 5절 1단계).

입력 data/role/v2/labels_v2.json(고치지 않음) → 출력
  data/role/v2/labels_v2_owner.draft.json   items 마다 "seat"(bottom|right|top|left|null) + "seat_src"(auto|rule|eye), 나머지 필드는 그대로
  data/role/v2/owner_check/<장면>.jpg         앞면 상자 색 = 주인 자리(bottom 파랑·right 초록·top 빨강·left 노랑·없음 회색), 옆 글자 = 역할 첫 글자
  data/role/v2/owner_draft_uncertain.json   규칙이 스스로 애매하다고 본 상자·덩어리

자리 정의(계획서 3-1):
  hand·loose·winner meld → 장면 side(auto). wall·pair·other → null.
  다른 사람 meld → 운 사람 자리, river → 버린 사람 자리: 아래 규칙(rule), 눈으로 본 뒤 FIX 표(eye).
규칙(모델 예측은 쓰지 않음 — 상자 모양·위치만):
  1) 기기 중심: sticks(10-31) 가운데, 없으면 격자 가운데. 1차 배정 뒤 강 첫 줄 안쪽 끝으로 다시 잡는다(sticks 없을 때만).
  2) 강 패 방향: 세로로 긴 상자(h > w·1.12) = 아래·위 사람(중심보다 아래면 bottom), 가로로 긴 상자 = 왼쪽·오른쪽 사람.
  3) 줄 이웃 다수결: 아래·위 강은 줄이 가로, 왼쪽·오른쪽 강은 줄이 세로다. 상자가 자기 방향 자리의 줄 이웃이 하나도 없는데
     다른 자리의 줄 이웃이 있으면 그 자리로 옮긴다(리치 선언패). 줄 이웃도 없고 같은 자리 이웃도 없으면 붙은 이웃 다수결.
  4) 다른 사람 울기: 붙은 울기 상자끼리 덩어리 → 중심에서 본 모서리(오른아래 bottom·오른위 right·왼위 top·왼아래 left = 운 사람의 오른손 쪽).
     방향 다수결은 확인용(다르면 애매 목록). 처음엔 방향 다수결을 앞세웠으나 가장자리 상자가 정사각에 가까워 3덩어리가 틀려 바꿈.

  python -I -X utf8 experiments/tile_classifier/role_owner_draft.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "speed"))
import seat_grow as sg  # noqa: E402

V2 = HERE / "data" / "role" / "v2"
SRC = V2 / "labels_v2.json"
OUT = V2 / "labels_v2_owner.draft.json"
CHECK = V2 / "owner_check"
UNC = V2 / "owner_draft_uncertain.json"
TRUTH = EXP / "paifu_frames" / "truth.json"
PAIRS1107 = EXP / "visit_20261107" / "review" / "pairs_1107.json"

SEATS = ("bottom", "right", "top", "left")
SEAT_COLOR = {"bottom": (40, 90, 255), "right": (0, 200, 0), "top": (255, 30, 30), "left": (255, 220, 0), None: (150, 150, 150)}
VERT_RATIO = 1.12  # h/w 이 이보다 크면 세로, 1/이 보다 작으면 가로
GAP = 0.40  # 이웃 = 상자 사이 틈 < 패 짧은 변 × GAP
OVERLAP = 0.35  # 줄 이웃 = 다른 축으로 겹침 > 작은 쪽 변 × OVERLAP
MELD_GAP = 0.6

# 눈으로 확인하고 고친 상자: {장면: {상자 번호: 자리}} → seat_src="eye"
FIX: dict[str, dict[int, str]] = {}


def grids() -> dict[str, dict]:
    g = {s["name"]: s["grid"] for s in sg.scenes()}
    for p in json.loads(PAIRS1107.read_text(encoding="utf-8")):
        g.setdefault(p["name"], p["grid"])
    return g


def orient(b) -> str:
    w, h = b[2], b[3]
    if h > w * VERT_RATIO:
        return "V"
    if w > h * VERT_RATIO:
        return "H"
    return "?"


def gaps(a, b):
    dx = max(0.0, max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3]))
    ox = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    oy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return dx, dy, ox, oy


def row_axis(seat: str) -> str:
    return "x" if seat in ("bottom", "top") else "y"


def neighbors(boxes, idx, short):
    """idx 상자들 사이 이웃 관계: {i: [(j, 축)]}. 축 x = 좌우로 붙음(세로 겹침), y = 위아래로 붙음, d = 모서리로만."""
    nb = defaultdict(list)
    for a in idx:
        for b in idx:
            if a >= b:
                continue
            dx, dy, ox, oy = gaps(boxes[a], boxes[b])
            th = short * GAP
            if dx < th and dy < th:
                if dx >= 0 and oy > OVERLAP * min(boxes[a][3], boxes[b][3]) and dy == 0:
                    ax = "x"
                elif dy >= 0 and ox > OVERLAP * min(boxes[a][2], boxes[b][2]) and dx == 0:
                    ax = "y"
                else:
                    ax = "d"
                nb[a].append((b, ax))
                nb[b].append((a, ax))
    return nb


def by_orient(o, dx, dy):
    if o == "V":
        return "bottom" if dy > 0 else "top"
    if o == "H":
        return "right" if dx > 0 else "left"
    # 정사각에 가까움: 중심에서 더 멀리 나간 축
    if abs(dy) >= abs(dx):
        return "bottom" if dy > 0 else "top"
    return "right" if dx > 0 else "left"


def assign_river(boxes, ridx, cx, cy, short):
    seat, why = {}, defaultdict(list)
    for i in ridx:
        b = boxes[i]
        o = orient(b)
        seat[i] = by_orient(o, b[0] + b[2] / 2 - cx, b[1] + b[3] / 2 - cy)
        if o == "?":
            why[i].append("square_box")
    nb = neighbors(boxes, ridx, short)
    for _ in range(3):
        changed = False
        for i in ridx:
            own = seat[i]
            sup = Counter()
            for j, ax in nb[i]:
                if ax == row_axis(seat[j]):
                    sup[seat[j]] += 1
            same_any = sum(1 for j, _ in nb[i] if seat[j] == own)
            new = own
            if sup[own] == 0 and sup:
                cand = sup.most_common()
                if len(cand) == 1 or cand[0][1] > cand[1][1]:
                    new = cand[0][0]
                else:
                    why[i].append("row_neighbor_tie")
            elif sup[own] == 0 and same_any == 0 and nb[i]:
                c = Counter(seat[j] for j, _ in nb[i]).most_common()
                if len(c) == 1 or c[0][1] > c[1][1]:
                    new = c[0][0]
                else:
                    why[i].append("neighbor_tie")
            if new != own:
                seat[i] = new
                why[i].append(f"moved_{own}_to_{new}")
                changed = True
        if not changed:
            break
    # 다른 자리와 붙은 상자(강 둘이 닿는 모서리)
    for i in ridx:
        others = {seat[j] for j, _ in nb[i] if seat[j] != seat[i]}
        if others:
            why[i].append("touches_" + "_".join(sorted(others)))
        if not nb[i]:
            why[i].append("isolated")
    return seat, why


def refine_center(boxes, seat, cx, cy):
    """강 첫 줄 안쪽 끝으로 중심 다시 잡기(sticks 없는 장면). 양쪽 다 3장 이상일 때만 그 축을 고침."""
    def inner(s):
        bs = [boxes[i] for i, v in seat.items() if v == s]
        if len(bs) < 3:
            return None
        if s == "bottom":
            vals = sorted(b[1] for b in bs)
        elif s == "top":
            vals = sorted((b[1] + b[3] for b in bs), reverse=True)
        elif s == "right":
            vals = sorted(b[0] for b in bs)
        else:
            vals = sorted((b[0] + b[2] for b in bs), reverse=True)
        return statistics.median(vals[:3])
    t, bt, l, r = inner("top"), inner("bottom"), inner("left"), inner("right")
    ncx = (l + r) / 2 if l is not None and r is not None else cx
    ncy = (t + bt) / 2 if t is not None and bt is not None else cy
    return ncx, ncy


def assign_melds(boxes, midx, cx, cy, short):
    seat, groups = {}, []
    nb = defaultdict(list)
    for a in midx:
        for b in midx:
            if a < b:
                dx, dy, _, _ = gaps(boxes[a], boxes[b])
                if dx < short * MELD_GAP and dy < short * MELD_GAP:
                    nb[a].append(b)
                    nb[b].append(a)
    left = set(midx)
    while left:
        s = left.pop()
        g, todo = {s}, [s]
        while todo:
            a = todo.pop()
            for b in nb[a]:
                if b in left:
                    left.discard(b)
                    g.add(b)
                    todo.append(b)
        g = sorted(g)
        gx = statistics.mean(boxes[i][0] + boxes[i][2] / 2 for i in g) - cx
        gy = statistics.mean(boxes[i][1] + boxes[i][3] / 2 for i in g) - cy
        oc = Counter(orient(boxes[i]) for i in g)
        corner = {(True, True): "bottom", (True, False): "right", (False, False): "top", (False, True): "left"}[(gx > 0, gy > 0)]
        # 모서리 우선(2026-11-11 눈 확인): 탁자 가장자리 울기는 원근 때문에 상자가 정사각에 가까워 방향 다수결이 흔들린다
        # (172424·181209·154904 의 오른아래 울기 = 아래 사람 것인데 방향으로는 right). 울기 자리는 모서리 하나에 한 사람뿐이라 위치로 정하고,
        # 방향 다수결이 다르면 애매 목록에 올린다.
        reasons = []
        st = corner
        if oc["V"] > oc["H"]:
            os_ = "bottom" if gy > 0 else "top"
        elif oc["H"] > oc["V"]:
            os_ = "right" if gx > 0 else "left"
        else:
            os_ = None
            reasons.append("orient_tie")
        if os_ and os_ != corner:
            reasons.append(f"orient_says_{os_}")
        if len(g) < 3:
            reasons.append(f"small_group_{len(g)}")
        for i in g:
            seat[i] = st
        groups.append(dict(idx=g, seat=st, orient=dict(oc), reasons=reasons))
    return seat, groups


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    G = grids()
    out, unc = {}, {}
    CHECK.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 30)
    river_counts = {}
    for name, sc in data.items():
        W, H = sc["size"]
        g = G[name]
        items = sc["items"]
        boxes = [it["box"] for it in items]
        if "sticks" in g:
            y0, x0, y1, x1 = g["sticks"]
            cx, cy = (x0 + x1) / 2000 * W, (y0 + y1) / 2000 * H
            csrc = "sticks"
        else:
            cx, cy = (g["x1"] + g["x2"]) / 2000 * W, (g["y1"] + g["y2"]) / 2000 * H
            csrc = "grid"
        ridx = [i for i, it in enumerate(items) if it["role"] == "river"]
        midx = [i for i, it in enumerate(items) if it["role"] == "meld" and it.get("owner") == "other"]
        short = statistics.median(min(boxes[i][2], boxes[i][3]) for i in ridx) if ridx else 80
        c0 = (cx, cy)
        if ridx:
            # 강 전체 상자 범위의 가운데. 기기 위치 값(sticks·격자)이 이보다 패 1.5장 넘게 어긋나면(합성 사본·탁자 이동) 이것으로 시작
            bx = (min(boxes[i][0] for i in ridx) + max(boxes[i][0] + boxes[i][2] for i in ridx)) / 2
            by = (min(boxes[i][1] for i in ridx) + max(boxes[i][1] + boxes[i][3] for i in ridx)) / 2
            if max(abs(bx - cx), abs(by - cy)) > short * 1.5:
                cx, cy = bx, by
                csrc += "->riverbox"
        rseat, why = assign_river(boxes, ridx, cx, cy, short)
        # 강 첫 줄 안쪽 끝으로 중심을 다시 잡고 다시 배정(두 번)
        for _ in range(2):
            ncx, ncy = refine_center(boxes, rseat, cx, cy)
            if (ncx, ncy) == (cx, cy):
                break
            cx, cy = ncx, ncy
            rseat, why = assign_river(boxes, ridx, cx, cy, short)
        csrc += "+refine"
        mseat, mgroups = assign_melds(boxes, midx, cx, cy, short)
        new_items, s_unc = [], []
        for i, it in enumerate(items):
            it2 = dict(it)
            r = it["role"]
            if r in ("hand", "loose") or (r == "meld" and it.get("owner") == "winner"):
                st, src = sc["side"], "auto"
            elif r == "meld":
                st, src = mseat[i], "rule"
            elif r == "river":
                st, src = rseat[i], "rule"
                if why.get(i):
                    s_unc.append(dict(idx=i, kind="river", seat=st, reasons=why[i]))
            else:
                st, src = None, "auto"
            if i in FIX.get(name, {}):
                st, src = FIX[name][i], "eye"
            it2["seat"], it2["seat_src"] = st, src
            new_items.append(it2)
        for gr in mgroups:
            if gr["reasons"]:
                s_unc.append(dict(idx=gr["idx"], kind="meld_group", seat=gr["seat"], orient=gr["orient"], reasons=gr["reasons"]))
        sc2 = dict(sc)
        sc2["items"] = new_items
        sc2["seat_center"] = [round(cx, 1), round(cy, 1), csrc]
        out[name] = sc2
        if s_unc:
            unc[name] = s_unc
        rc = Counter(it["seat"] for it in new_items if it["role"] == "river")
        river_counts[name] = {s: rc.get(s, 0) for s in SEATS}
        draw_check(name, sc2, font, c0)
        mc = [(gr["seat"], len(gr["idx"])) for gr in mgroups]
        print(f"{name} side={sc['side']:6s} center={csrc}({cx:.0f},{cy:.0f}) river {river_counts[name]} "
              f"spread={max(river_counts[name].values()) - min(river_counts[name].values())} other_meld={mc} unc={len(s_unc)}")
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    UNC.write_text(json.dumps(unc, ensure_ascii=False, indent=1), encoding="utf-8")
    report(out, river_counts)


def draw_check(name, sc, font, c0):
    im = Image.open(sc["image"]).convert("RGB")
    d = ImageDraw.Draw(im)
    for i, it in enumerate(sc["items"]):
        x, y, w, h = it["box"]
        col = SEAT_COLOR[it["seat"]]
        wd = 9 if it["seat_src"] == "eye" else 6
        d.rectangle([x, y, x + w, y + h], outline=col, width=wd)
        lab = it["role"][0].upper() + str(i)
        d.text((x + 4, y + 2), lab, fill=col, font=font, stroke_width=3, stroke_fill=(0, 0, 0))
    cx, cy, _ = sc["seat_center"]
    for (px, py), col in (((cx, cy), (255, 0, 255)), (c0, (255, 255, 255))):
        d.line([px - 40, py, px + 40, py], fill=col, width=6)
        d.line([px, py - 40, px, py + 40], fill=col, width=6)
    s = 2400 / max(im.size)
    im.resize((round(im.size[0] * s), round(im.size[1] * s)), Image.LANCZOS).save(CHECK / f"{name}.jpg", quality=88)


def report(out, river_counts):
    tab = Counter()
    src = Counter()
    for sc in out.values():
        for it in sc["items"]:
            tab[(it["role"], it["seat"])] += 1
            src[it["seat_src"]] += 1
    roles = sorted({r for r, _ in tab})
    print("\n역할 × 자리")
    print("role    " + " ".join(f"{s:>7s}" for s in (*SEATS, "null")))
    for r in roles:
        print(f"{r:7s} " + " ".join(f"{tab.get((r, s), 0):7d}" for s in (*SEATS, None)))
    print("seat_src", dict(src))
    # truth 대조
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    print("\ntruth 대조(별표 뺀 버림 수)")
    for k, v in truth.items():
        if not isinstance(v, dict) or "seq" not in v:
            continue
        cnt = Counter(e.split()[0] for e in v["seq"] if not e.endswith("*"))
        exp = {s: cnt.get(s, 0) for s in SEATS}
        wp = v.get("win_photo")
        got = river_counts.get(wp)
        print(f"  {k} {wp}: truth {exp} | draft {got if got else '(labels_v2 에 없음)'}")


if __name__ == "__main__":
    main()
