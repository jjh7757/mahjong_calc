"""앞면 패의 역할 라벨 자동 생성(2026-11-03, API 없음). metrics 표 1-56.

검출 라벨(boxes_r2.json, 사진 31장 = B·C·D 6 + 매장 25) + 저장 격자 + truth 로 패마다 역할을 붙인다:
  hand(손패 줄) · meld(울기) · river(강) · wall(패산 위 표시패, 옆에 뒷면이 붙은 낱장) · pair(리치 화료의 탁자 위 표시패 짝) ·
  loose(떼어 둔 패) · other(모름, 학습에서 뺌)
규칙으로 만든 라벨이라 규칙이 틀린 곳은 틀리다. 그림 data/role/check/<이름>.jpg 로 확인하고 review.json 으로 고친다.

  python -I -X utf8 experiments/tile_classifier/role_label.py
결과 data/role/labels.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
import dora_outside as do  # noqa: E402
import seat_grow as sg  # noqa: E402
import wall_frames as wf  # noqa: E402
from app import local_read as lr  # noqa: E402

OUT = HERE / "data" / "role"
BOXES = json.loads((HERE / "data/det/boxes_r2.json").read_text(encoding="utf-8"))
TRUTH = json.loads((wf.ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
ROLES = ["hand", "meld", "river", "wall", "pair", "loose", "other"]
COLORS = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow", "other": "gray"}
SIDES = ["bottom", "right", "top", "left"]


def longest_chain(b: np.ndarray) -> list[int]:
    """experiments/zone_points/tile_row.py 의 longest_chain 그대로(그 파일은 import 하면 argv 를 읽는다): 가장 긴 곧은 사슬(인덱스)."""
    c = (b[:, :2] + b[:, 2:]) / 2
    wh = b[:, 2:] - b[:, :2]
    s = np.median(np.minimum(wh[:, 0], wh[:, 1])) if len(b) else 0
    best: list = []
    for i in range(len(b)):
        for j in range(i + 1, len(b)):
            d = c[j] - c[i]
            L = np.hypot(*d)
            if L < 1e-6 or L > s * 8:
                continue
            u = d / L
            n = np.array([-u[1], u[0]])
            off = np.abs((c - c[i]) @ n)
            idx = np.where(off < 0.35 * s)[0]
            if len(idx) <= len(best):
                continue
            order = idx[np.argsort((c[idx] - c[i]) @ u)]
            tt = (c[order] - c[i]) @ u
            run, cur = [order[0]], [order[0]]
            for k in range(1, len(order)):
                if tt[k] - tt[k - 1] < 2.0 * s:
                    cur.append(order[k])
                else:
                    cur = [order[k]]
                if len(cur) > len(run):
                    run = list(cur)
            if len(run) > len(best):
                best = run
    return [int(i) for i in best]


def cluster(boxes: list, gap: float) -> list[list[int]]:
    """틈이 gap 미만인 이웃끼리 묶기(인덱스)."""
    left = list(range(len(boxes)))
    out = []
    while left:
        g = [left.pop()]
        i = 0
        while i < len(g):
            a = boxes[g[i]]
            for k in left[:]:
                x = boxes[k]
                dx = max(0, max(a[0], x[0]) - min(a[0] + a[2], x[0] + x[2]))
                dy = max(0, max(a[1], x[1]) - min(a[1] + a[3], x[1] + x[3]))
                if dx < gap and dy < gap:
                    g.append(k)
                    left.remove(k)
            i += 1
        out.append(g)
    return out


def seat_of(u: float, v: float, g: dict, grow: int = 40) -> str | None:
    """자리 띠(선에서 가운데 쪽으로 grow 안까지)에 들면 그 자리."""
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    if v >= y2 - grow and x1 <= u:
        return "bottom"
    if u >= x2 - grow and v <= y2:
        return "right"
    if v <= y1 + grow and u <= x2:
        return "top"
    if u <= x1 + grow and v >= y1:
        return "left"
    return None


def label_scene(s: dict, rgb: np.ndarray) -> list[dict]:
    """격자 구역보다 패 묶음의 모양으로 정한다(구역은 격자 선 위치에 너무 흔들렸다):
    강 = 기기 상자 둘레(패 3.5장 안)에 있거나 두 줄 이상 쌓인 묶음, 손패 줄 = 그 밖의 5장 이상 한 줄, 울기 = 3~4장 한 줄,
    패산 위 표시패 = 옆에 뒷면이 붙은 낱장, 짝 = 리치 화료의 2장 묶음(강 둘레 밖), 떼어 둔 패 = 화료자 자리 띠의 낱장."""
    g = s["grid"]
    rec = BOXES[s["name"]]
    W, H = rec["size"]
    boxes = [tuple(b) for b in rec["boxes"]]
    t = TRUTH.get(s["name"])
    riichi = bool(t and t.get("riichi"))
    tw = float(np.median([min(b[2], b[3]) for b in boxes])) if boxes else 1
    th = float(np.median([max(b[2], b[3]) for b in boxes])) if boxes else 1
    cen = [((b[0] + b[2] / 2) / W * 1000, (b[1] + b[3] / 2) / H * 1000) for b in boxes]
    seat = [seat_of(u, v, g) for u, v in cen]
    st_box = g.get("sticks")  # [ymin, xmin, ymax, xmax] (1000 분율)
    near = 3.5 * tw / W * 1000

    def near_sticks(u: float, v: float) -> bool:
        if not st_box:
            return False
        ymin, xmin, ymax, xmax = st_box
        return xmin - near <= u <= xmax + near and ymin - near <= v <= ymax + near

    roles = ["other"] * len(boxes)
    # 손패 줄 먼저: 가장 긴 곧은 사슬(표 1-50 tile_row.longest_chain)이 10장 이상이고 기기 둘레 밖이면 손패 줄로 떼어 낸다.
    # (강 줄이 손패 줄에 닿아 한 묶음이 되는 사진이 많다)
    arr = np.array([[b[0], b[1], b[0] + b[2], b[1] + b[3]] for b in boxes], float)
    chain = longest_chain(arr) if len(boxes) else []
    hand_idx: set[int] = set()
    if len(chain) >= 10:
        cu, cv = sum(cen[i][0] for i in chain) / len(chain), sum(cen[i][1] for i in chain) / len(chain)
        if not near_sticks(cu, cv):
            hand_idx = set(int(i) for i in chain)
            for i in hand_idx:
                roles[i] = "hand"
    rest = [i for i in range(len(boxes)) if i not in hand_idx]
    groups = [[rest[k] for k in grp] for grp in cluster([boxes[i] for i in rest], tw * 0.5)]
    for grp in groups:
        n = len(grp)
        xs = [boxes[i][0] for i in grp] + [boxes[i][0] + boxes[i][2] for i in grp]
        ys = [boxes[i][1] for i in grp] + [boxes[i][1] + boxes[i][3] for i in grp]
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        line = min(bw, bh) <= 1.4 * th  # 한 줄
        gu, gv = sum(cen[i][0] for i in grp) / n, sum(cen[i][1] for i in grp) / n
        sd = {seat[i] for i in grp} - {None}
        if n >= 2 and (not line or near_sticks(gu, gv)):
            r = "river"
        elif n >= 5:
            r = "hand"
        elif n in (3, 4):
            r = "meld"
        elif n == 2:
            r = "pair" if riichi and sd <= {s["side"]} else "other"  # 다른 자리 띠의 2장(그 사람 공개 패)은 짝이 아니다
        else:
            sides, _ = lr.wall_score(rgb, boxes[grp[0]])
            if sides >= 1:
                r = "wall"
            elif s["side"] in sd:
                r = "loose"
            else:
                r = "other"
        for i in grp:
            roles[i] = r
    return [dict(box=list(b), u=round(u), v=round(v), role=r, seat=sd) for b, (u, v), r, sd in zip(boxes, cen, roles, seat)]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    (OUT / "check").mkdir(parents=True, exist_ok=True)
    review = json.loads((OUT / "review.json").read_text(encoding="utf-8")) if (OUT / "review.json").exists() else {}
    out = {}
    total = {r: 0 for r in ROLES}
    for s in sg.scenes():
        if s["name"] not in BOXES or s["grid"] is None or s["set"] != "visit":  # 카톡 B·C·D 는 기기 상자가 없어 뺀다
            continue
        im = Image.open(s["path"]).convert("RGB")
        items = label_scene(s, np.asarray(im))
        for it in items:
            it["rule"] = it["role"]  # 규칙이 낸 값(사람 수정 전)
        for k, v in review.get(s["name"], {}).items():
            items[int(k)]["role"] = v
            items[int(k)]["reviewed"] = True
        out[s["name"]] = dict(path=str(s["path"]), size=list(im.size), side=s["side"], set=s["set"], riichi=bool(TRUTH.get(s["name"], {}).get("riichi")), items=items)
        d = ImageDraw.Draw(im)
        for i, it in enumerate(items):
            x, y, w, h = it["box"]
            d.rectangle((x, y, x + w, y + h), outline=COLORS[it["role"]], width=5)
            d.text((x, y - 28), f"{i}", fill=COLORS[it["role"]])
        im.resize((im.width // 2, im.height // 2)).save(OUT / "check" / f"{s['name']}.jpg", quality=80)
        c = {r: sum(1 for it in items if it["role"] == r) for r in ROLES}
        for r in ROLES:
            total[r] += c[r]
        print(s["name"], s["side"], {r: n for r, n in c.items() if n}, flush=True)
    print("합계", total)
    (OUT / "labels.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
