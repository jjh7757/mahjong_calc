"""펠트 네 점에서 구역을 계산한다(2026-11-02, API 없음). 펠트를 정사각형으로 편 좌표 u,v(0~1)에서 가운데까지의 거리 r = max(|u-.5|, |v-.5|) 로 나눈다.
  기기(리치봉) = 가운데 폭 DEV_W·높이 DEV_H   강 = r < RIVER   산 = RIVER ≤ r < HAND(판이 진행되면 패산이 안쪽으로 밀려와 대략값)   손패·울기 = r ≥ HAND, 울기는 그 사람 오른쪽 모서리
값은 패 상자·저장 격자를 편 좌표로 옮긴 분포에서 정했다: 강은 0.24 까지, 손패·울기는 0.32 바깥, 사이에 패가 거의 없다. RIVER 0.30 은 손패 크롭이 안쪽으로 40/1000 넓어져도 강에 닿지 않는 값.
앱은 선 4개 격자만 받으므로 r = RIVER 사각형의 변 평균을 선으로 쓴다(기운 탁자에서는 근사).
  python -I experiments/zone_points/zones.py grids median|single|saved|initial    FIELD_GRIDS 값(B·C·D 포함)
  python -I experiments/zone_points/zones.py check                                패가 구역에 맞게 드는지
  python -I experiments/zone_points/zones.py sheet <그림 앞이름>                   사진에 구역을 겹친 그림
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propose import DATA, load  # noqa: E402

RIVER = 0.30
HAND = 0.40
DEV_W, DEV_H = 0.197, 0.194
STICK_MARGIN = 10  # 리치봉 상자 여유(0~1000)
BCD = ["k25", "k28", "k15", "k26", "k12", "k16"]
INITIAL = dict(x1=280, x2=745, y1=173, y2=713)
# 사진 좌표 고정 격자(fixed_grid.py): fixed = 매장 + 갤러리 전부로 맞춤, fixedstore = 매장 사진만으로 맞춤(갤러리는 시험).
FIXED = {"fixed": dict(x1=295, x2=722, y1=187, y2=777), "fixedstore": dict(x1=295, x2=722, y1=262, y2=777)}
UNIT = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)


def to_image(felt: list) -> np.ndarray:
    """편 좌표 → 사진 비율 좌표. 왼위부터 시계 방향 펠트 네 점. 비율 좌표로 풀어 사진 크기와 무관하다."""
    return cv2.getPerspectiveTransform(UNIT, np.array(felt, np.float32))


def project(M: np.ndarray, uv: list) -> np.ndarray:
    return cv2.perspectiveTransform(np.array(uv, np.float32).reshape(-1, 1, 2), M).reshape(-1, 2)


def box(cx: float, cy: float, hw: float, hh: float) -> list:
    return [[cx - hw, cy - hh], [cx + hw, cy - hh], [cx + hw, cy + hh], [cx - hw, cy + hh]]


def grid_of(felt: list) -> dict:
    M = to_image(felt)
    q = project(M, box(0.5, 0.5, RIVER, RIVER))
    d = project(M, box(0.5, 0.5, DEV_W / 2, DEV_H / 2))
    g = dict(x1=round((q[0, 0] + q[3, 0]) * 500), x2=round((q[1, 0] + q[2, 0]) * 500), y1=round((q[0, 1] + q[1, 1]) * 500), y2=round((q[2, 1] + q[3, 1]) * 500))
    g["sticks"] = [round(d[:, 1].min() * 1000) - STICK_MARGIN, round(d[:, 0].min() * 1000) - STICK_MARGIN, round(d[:, 1].max() * 1000) + STICK_MARGIN, round(d[:, 0].max() * 1000) + STICK_MARGIN]
    return g


def polygons(felt: list) -> dict:
    """그림용 구역 사각형(사진 비율 좌표). 자리는 아래 → 오른쪽 → 위 → 왼쪽, 손패는 변 가운데, 울기는 그 사람 오른쪽 모서리."""
    M = to_image(felt)
    a, b = 0.5 - HAND, 0.5 + HAND
    rect = lambda u0, v0, u1, v1: project(M, [[u0, v0], [u1, v0], [u1, v1], [u0, v1]])
    return {
        "device": project(M, box(0.5, 0.5, DEV_W / 2, DEV_H / 2)),
        "river": project(M, box(0.5, 0.5, RIVER, RIVER)),
        "wall": project(M, box(0.5, 0.5, HAND, HAND)),
        "hand": [rect(a, b, b, 1), rect(b, a, 1, b), rect(a, 0, b, a), rect(0, a, a, b)],
        "meld": [rect(b, b, 1, 1), rect(b, 0, 1, a), rect(0, 0, a, a), rect(0, b, a, 1)],
    }


def tables() -> tuple[dict, dict]:
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    return labels, rows


def scene_list() -> list[str]:
    labels, _ = tables()
    return BCD + [n for n, r in labels.items() if r["kind"] == "photo" and r["group"] != "gal"]


def mode_grid(mode: str, name: str, labels: dict, rows: dict, saved: dict) -> dict | None:
    if mode == "initial":
        return dict(INITIAL)
    if mode in FIXED:
        return dict(FIXED[mode])
    if mode == "gemini":  # 운영 /v2/setup 값(gemini_setup.py). 못 낸 사진은 저장 격자.
        d = json.loads((DATA / "gemini_setup.json").read_text(encoding="utf-8")).get(name)
        return d["grid"] if d and d["grid"] else saved.get(name)
    if mode == "dart":  # 앱 코드 값. 믿지 못한 사진은 앱처럼 지금 격자(저장 격자)를 그대로 쓴다.
        d = json.loads((DATA / "dart_felt.json").read_text(encoding="utf-8")).get(name)
        return d["grid"] if d and d["ok"] and d["grid"] else saved.get(name)
    if mode == "saved":
        return saved.get(name)
    felt = labels[name]["felt"] if mode == "median" else rows[name]["felt"]
    return grid_of(felt) if felt else None


def saved_grids() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "speed"))
    import seat_grow as sg  # noqa: PLC0415

    return {s["name"]: s["grid"] for s in sg.scenes()}


def field_key(name: str) -> str:
    return name if name.startswith("k") else name[-6:]


def grids(mode: str) -> None:
    labels, rows = tables()
    saved = saved_grids() if mode in ("saved", "dart", "gemini") else {}
    out = []
    for n in scene_list():
        g = mode_grid(mode, n, labels, rows, saved)
        if g:
            out.append(f"{field_key(n)}=" + ",".join(str(v) for v in [g["x1"], g["x2"], g["y1"], g["y2"], *g.get("sticks", [])]))
    print(";".join(out))


def check() -> None:
    """패 상자 가운데를 라벨 펠트로 편 뒤, 강 패(r < 0.25)가 가운데 칸 안에, 손패·울기 패(r > 0.32)가 가운데 칸 밖에 드는지 본다."""
    labels, rows = tables()
    saved = saved_grids()
    boxes = json.loads((DATA.parent / "det" / "boxes_final.json").read_text(encoding="utf-8"))
    print("방식: 강 패가 가운데 칸 밖 / 강 패 수, 손패·울기 패가 가운데 칸 안 / 수, 어긋난 사진 수")
    for mode in ("median", "single", "saved", "initial"):
        tally = {}
        for n in scene_list():
            r = labels[n]
            if n not in boxes:
                continue
            g = mode_grid(mode, n, labels, rows, saved)
            if g is None:
                continue
            W, H = r["size"]
            c = np.array([[x + w / 2, y + h / 2] for x, y, w, h in boxes[n]["boxes"]], np.float32)
            inv = np.linalg.inv(to_image(r["felt"]))
            uv = project(inv, (c / [W, H]).tolist())
            rr = np.abs(uv - 0.5).max(1)
            inside = (c[:, 0] / W * 1000 > g["x1"]) & (c[:, 0] / W * 1000 < g["x2"]) & (c[:, 1] / H * 1000 > g["y1"]) & (c[:, 1] / H * 1000 < g["y2"])
            part = "BCD" if n in BCD else ("오전" if r["group"] == "am" else "오후")
            t = tally.setdefault(part, [0, 0, 0, 0, 0])
            river_out, river_n = int(((rr < 0.25) & ~inside).sum()), int((rr < 0.25).sum())
            hand_in, hand_n = int(((rr > 0.32) & inside).sum()), int((rr > 0.32).sum())
            t[0] += river_out
            t[1] += river_n
            t[2] += hand_in
            t[3] += hand_n
            t[4] += (river_out + hand_in) > 0
        print(mode, {k: f"강 밖 {v[0]}/{v[1]}, 손패 안 {v[2]}/{v[3]}, 사진 {v[4]}" for k, v in sorted(tally.items())})


def sheet(prefix: str) -> None:
    labels, _ = tables()
    names = scene_list()
    cols, tw, th = 5, 480, 360
    for page in range(0, len(names), 20):
        part = names[page : page + 20]
        sh = Image.new("RGB", (cols * tw, ((len(part) + cols - 1) // cols) * th))
        for i, n in enumerate(part):
            im = load(labels[n]["src"]).resize((tw, th))
            d = ImageDraw.Draw(im)
            p = polygons(labels[n]["felt"])
            draw = lambda q, col: d.polygon([(x * tw, y * th) for x, y in q], outline=col)
            draw(p["device"], (255, 0, 255))
            draw(p["river"], (255, 255, 0))
            draw(p["wall"], (0, 255, 255))
            for q in p["hand"]:
                draw(q, (255, 120, 0))
            for q in p["meld"]:
                draw(q, (255, 40, 40))
            g = grid_of(labels[n]["felt"])
            for x in (g["x1"], g["x2"]):
                d.line((x * tw / 1000, 0, x * tw / 1000, th), fill=(255, 255, 255))
            for y in (g["y1"], g["y2"]):
                d.line((0, y * th / 1000, tw, y * th / 1000), fill=(255, 255, 255))
            d.rectangle((0, 0, 70, 12), fill="black")
            d.text((2, 0), n[-6:], fill="white")
            sh.paste(im, ((i % cols) * tw, (i // cols) * th))
        path = f"{prefix}_{page // 20}.jpg"
        sh.save(path, quality=85)
        print(path, len(part))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "grids":
        grids(sys.argv[2])
    elif sys.argv[1] == "check":
        check()
    else:
        sheet(sys.argv[2])
