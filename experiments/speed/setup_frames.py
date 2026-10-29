"""카메라를 놓을 때 한 번: 사진 한 장으로 Gemini 가 네 자리 손패 줄·울기·강 틀과 가운데 기기 틀을 잡고, 그것으로 격자 선 4개를
제안한다(사용자가 선을 끌어 맞추는 "구역 격자 맞추기" 대신 — 사용자 결정 2026-10-29: 판마다는 도라 산만, 자리·리치봉 틀은 처음에 한 번).

  python -I -X utf8 experiments/speed/setup_frames.py [--runs 3] [--set bcd|tilt|all]

선 = 그 쪽 자리 손패 줄(울기 포함)의 안쪽 끝과 그 쪽 강의 바깥 끝 사이 한가운데(강이 없으면 기기 끝). 앱 격자와 같은 바람개비
(lib/table/grid_zones.dart). 리치봉 구역은 가운데 기기 틀 그대로(앱은 지금 가운데 칸 한가운데 비율로 자른다).
B·C·D 는 사용자가 맞춘 격자(MANUAL)와 선 차이를 잰다. 기울기 합성(kakao_photos/tilted, 개발용)은 수동 격자가 없어 그림으로 본다.
결과: results/setup_frames.json, results/setup_frames_<묶음>.jpg (하늘색 = 제안 격자, 흰색 점선 = 수동 격자, 노랑 = 손패, 분홍 = 울기,
초록 = 강, 주황 = 기기).
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from bench import call  # noqa: E402

ROOT = Path(__file__).parent
PHOTOS = ROOT.parent / "field_20261024" / "kakao_photos"
OUT = ROOT / "results"
SIDES = ["bottom", "right", "top", "left"]

MANUAL = {  # 사용자가 맞춘 격자(read_grid_timing_test.dart _bcd)
    "k25": (272, 735, 137, 727), "k28": (272, 735, 137, 727),
    "k15": (320, 760, 142, 717), "k26": (320, 760, 142, 717),
    "k12": (280, 745, 173, 713), "k16": (280, 745, 173, 713),
}
SETS = {
    "bcd": list(MANUAL),
    "tilt": [f"tilted/{p}_{v}" for p in MANUAL for v in "abc"],
}

PROMPT = """이 사진은 리치마작 자동탁을 위에서 찍은 것입니다. 구역의 틀(상자)만 잡습니다. 패의 종류는 읽지 않습니다.

사진 기준 네 자리(bottom = 사진 아래쪽 변, right = 오른쪽 변, top = 위쪽 변, left = 왼쪽 변)마다:
- hand: 그 자리 사람 앞의 손패 줄(세워져 있든 앞면으로 눕혀져 있든 10~14장, 줄 끝에서 조금 떨어뜨린 한 장 포함)을 감싸는 상자.
- melds: 그 사람 오른쪽 테이블 모서리 쪽에 놓인 울기 묶음(앞면 3~4장 묶음) 전부를 감싸는 상자. 없으면 빈 배열.
- river: 그 사람 쪽 가운데 기기 둘레에 6장씩 줄지어 버린 패(강)를 감싸는 상자. 없으면 빈 배열.
그리고 device: 가운데 자동탁 기기(주사위 창이 있는 사각 판)를 감싸는 상자.

상자는 [ymin, xmin, ymax, xmax], 사진 크기를 0~1000 으로 본 정수입니다. 패산(뒷면이 보이게 2단으로 쌓인 더미)은 어느 상자에도 넣지 않습니다."""

_BOX = {"type": "array", "items": {"type": "integer"}}
SCHEMA = {
    "type": "object",
    "properties": {
        "seats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"side": {"type": "string", "enum": SIDES}, "hand": _BOX, "melds": _BOX, "river": _BOX},
                "required": ["side", "hand", "melds", "river"],
            },
        },
        "device": _BOX,
    },
    "required": ["seats", "device"],
}


def ok(b) -> bool:
    return isinstance(b, list) and len(b) == 4 and b[0] < b[2] and b[1] < b[3]


def lines(d: dict) -> tuple[int, int, int, int] | None:
    """틀 → 격자 선 (x1, x2, y1, y2). 손패(+울기) 안쪽 끝과 강 바깥 끝(없으면 기기 끝) 사이 한가운데."""
    seats = {s["side"]: s for s in d.get("seats") or [] if s.get("side") in SIDES}
    dev = d.get("device")
    if not ok(dev):
        return None

    def inner(side: str) -> list[int] | None:
        s = seats.get(side)
        if not s or not ok(s.get("hand")):
            return None
        return s["hand"]

    def river(side: str) -> list[int]:
        s = seats.get(side) or {}
        return s["river"] if ok(s.get("river")) else dev

    b, r, t, l_ = inner("bottom"), inner("right"), inner("top"), inner("left")
    if not (b and r and t and l_):
        return None
    y2 = (b[0] + river("bottom")[2]) // 2
    y1 = (t[2] + river("top")[0]) // 2
    x1 = (l_[3] + river("left")[1]) // 2
    x2 = (r[1] + river("right")[3]) // 2
    if not (0 < x1 < x2 < 1000 and 0 < y1 < y2 < 1000):
        return None
    return x1, x2, y1, y2


RIVER_ROWS = 4  # 판 끝까지 강이 늘어날 수 있는 줄 수(6장씩 3~4줄)
TILE_DEPTH = 1.35  # 패 세로 / 가로


def big(d: dict) -> dict | None:
    """처음 한 번 잡아 매 판 쓰는 넉넉한 구역(사용자 2026-10-29: "처음만 설정하고 매 판 하니 구역을 크게").

    패 크기 u = 손패 줄 길이 / 13. 선 = "기기 끝 + 강 RIVER_ROWS 줄" 과 "손패 안쪽 끝 − 패 1장" 사이 한가운데(판 끝까지 강은 가운데에,
    눕힌 손패는 자리에). 두 경계가 엇갈리면 손패 안쪽 끝과 기기 끝 사이 한가운데. 리치봉 = 기기 틀 + 사방 1u.
    자리 틀(기운 탁자용) = 손패 ∪ 울기 + 사방 1.5u. → {grid: (x1, x2, y1, y2), sticks: box, seats: {side: box}}"""
    seats = {s["side"]: s for s in d.get("seats") or [] if s.get("side") in SIDES}
    dev = d.get("device")
    if not ok(dev) or any(not ok((seats.get(x) or {}).get("hand")) for x in SIDES):
        return None
    hand = {x: seats[x]["hand"] for x in SIDES}
    # 손패 줄 길이: 아래·위는 가로, 왼쪽·오른쪽은 세로
    u = statistics.median([(hand[x][3] - hand[x][1]) / 13 if x in ("bottom", "top") else (hand[x][2] - hand[x][0]) / 13
                           for x in SIDES])
    depth = u * TILE_DEPTH

    def line(hand_inner: float, dev_edge: float, sign: int) -> int:
        """sign=+1: 손패가 기기보다 큰 좌표 쪽(아래·오른쪽)."""
        river_out = dev_edge + sign * RIVER_ROWS * depth
        hand_in = hand_inner - sign * u
        if (hand_in - river_out) * sign > 0:
            return round((river_out + hand_in) / 2)
        return round((hand_inner + dev_edge) / 2)

    y2 = line(hand["bottom"][0], dev[2], +1)
    y1 = line(hand["top"][2], dev[0], -1)
    x2 = line(hand["right"][1], dev[3], +1)
    x1 = line(hand["left"][3], dev[1], -1)
    if not (0 < x1 < x2 < 1000 and 0 < y1 < y2 < 1000):
        return None

    def pad(b: list[int], m: float) -> list[int]:
        return [max(0, round(b[0] - m)), max(0, round(b[1] - m)), min(1000, round(b[2] + m)), min(1000, round(b[3] + m))]

    seat_boxes = {}
    for x in SIDES:
        b = list(hand[x])
        m = (seats[x].get("melds") or [])
        if ok(m):
            b = [min(b[0], m[0]), min(b[1], m[1]), max(b[2], m[2]), max(b[3], m[3])]
        seat_boxes[x] = pad(b, 1.5 * u)
    return {"grid": (x1, x2, y1, y2), "sticks": pad(dev, u), "seats": seat_boxes, "u": round(u, 1)}


STRIP_MARGIN = 1.5  # 손패+울기 안쪽 끝에서 가운데 쪽으로 둘 여유(패 가로 단위) — 화료 때 눕혀 앞으로 나온 손패까지
STICKS_PAD = 0.5  # 리치봉 상자 = 기기 틀 + 이만큼(패 가로 단위)


def strips(d: dict) -> dict | None:
    """사용자 그림(2026-10-29)의 구조: 손패+울기 바깥 띠 4개(바람개비) · 리치봉 상자 · 나머지(패산·강·도라) 가운데.
    선 = 그 자리 손패(+울기) 안쪽 끝 − STRIP_MARGIN u. 리치봉 = 기기 틀 + STICKS_PAD u. → {grid, sticks, u}"""
    seats = {s["side"]: s for s in d.get("seats") or [] if s.get("side") in SIDES}
    dev = d.get("device")
    if not ok(dev) or any(not ok((seats.get(x) or {}).get("hand")) for x in SIDES):
        return None
    u = statistics.median([(seats[x]["hand"][3] - seats[x]["hand"][1]) / 13 if x in ("bottom", "top")
                           else (seats[x]["hand"][2] - seats[x]["hand"][0]) / 13 for x in SIDES])
    box = {}
    for x in SIDES:
        h = seats[x]["hand"]
        b = list(h)
        m = seats[x].get("melds") or []
        # 울기는 손패 줄과 같은 높이(테이블 가장자리 쪽)에 놓인다. 손패 안쪽 끝보다 패 1장 넘게 가운데로 나온 것은
        # 펠트 위 도라 표시패 같은 다른 패라 넣지 않는다(B·C 에서 Gemini 가 도라 표시패를 울기로 답함).
        inner = {"bottom": m[0] >= h[0] - u, "top": m[2] <= h[2] + u, "left": m[3] <= h[3] + u,
                 "right": m[1] >= h[1] - u}[x] if ok(m) else False
        if inner:
            b = [min(b[0], m[0]), min(b[1], m[1]), max(b[2], m[2]), max(b[3], m[3])]
        box[x] = b
    m = STRIP_MARGIN * u
    y2, y1 = round(box["bottom"][0] - m), round(box["top"][2] + m)
    x2, x1 = round(box["right"][1] - m), round(box["left"][3] + m)
    if not (0 < x1 < x2 < 1000 and 0 < y1 < y2 < 1000):
        return None
    p = STICKS_PAD * u
    sticks = [max(0, round(dev[0] - p)), max(0, round(dev[1] - p)), min(1000, round(dev[2] + p)), min(1000, round(dev[3] + p))]
    return {"grid": (x1, x2, y1, y2), "sticks": sticks, "u": round(u, 1)}


def jpeg(im: Image.Image) -> bytes:
    im = im.copy()
    im.thumbnail((1568, 1568))
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=90)
    return b.getvalue()


SERVER = False  # --server-prompt: 서버 /v2/setup 프롬프트(강 틀 없음)


def one(photo: str, run: int, data: bytes) -> dict:
    if SERVER:
        from app import observe as ob

        c = call(data, ob.SETUP_PROMPT_V2, ob.SETUP_SCHEMA_V2, "gemini-3.8-flash", "low", None)
    else:
        c = call(data, PROMPT, SCHEMA, "gemini-3.8-flash", "low", None)
    row = {"photo": photo, "run": run, "s": c["s"], "think": c.get("think")}
    if "error" in c:
        return {**row, "error": c["error"]}
    g = lines(c["data"])
    bg = big(c["data"])
    st = strips(c["data"])
    row.update(data=c["data"], grid=g, big=bg, strips=st)
    base = photo.split("/")[-1].split("_")[0]
    if g and photo in MANUAL:
        row["diff"] = [abs(a - b) for a, b in zip(g, MANUAL[base])]
    if bg and photo in MANUAL:
        row["big_diff"] = [a - b for a, b in zip(bg["grid"], MANUAL[base])]
    return row


def draw(name: str, ims: dict[str, Image.Image], rows: list[dict]) -> Path:
    tiles = []
    for p, im in ims.items():
        t = im.convert("RGB").copy()
        t.thumbnail((560, 560))
        w, h = t.size
        d = ImageDraw.Draw(t)

        def rect(b, color, width=2):
            if ok(b):
                d.rectangle((b[1] * w / 1000, b[0] * h / 1000, b[3] * w / 1000, b[2] * h / 1000), outline=color, width=width)

        def grid(g, color, width):
            x1, x2, y1, y2 = [v / 1000 for v in g]
            for a, b in [((x1 * w, y1 * h), (x1 * w, h)), ((x2 * w, 0), (x2 * w, y2 * h)),
                         ((0, y1 * h), (x2 * w, y1 * h)), ((x1 * w, y2 * h), (w, y2 * h))]:
                d.line([a, b], fill=color, width=width)

        if p in MANUAL:
            grid(MANUAL[p], (255, 255, 255), 2)
        first = next((r for r in rows if r["photo"] == p and r.get("data")), None)
        if first:
            for s in first["data"].get("seats") or []:
                rect(s.get("hand"), (255, 230, 0))
                rect(s.get("melds"), (255, 80, 200))
                rect(s.get("river"), (60, 220, 60))
            rect(first["data"].get("device"), (255, 140, 0), 3)
        for r in rows:
            if r["photo"] == p and r.get("big"):
                grid(r["big"]["grid"], (0, 230, 255), 3)
        if first and first.get("big"):
            rect(first["big"]["sticks"], (255, 0, 0), 3)
            for b in first["big"]["seats"].values():
                rect(b, (180, 120, 255), 2)
        marks = "".join("O" if r.get("big") else "x" for r in rows if r["photo"] == p)
        d.rectangle((0, 0, 230, 20), fill=(0, 0, 0))
        d.text((5, 4), f"{p} {marks}", fill=(255, 255, 0))
        tiles.append(t)
    cols = 3 if len(tiles) <= 6 else 6
    tw, th = max(x.width for x in tiles), max(x.height for x in tiles)
    canvas = Image.new("RGB", (tw * cols, th * ((len(tiles) + cols - 1) // cols)), "white")
    for i, x in enumerate(tiles):
        canvas.paste(x, ((i % cols) * tw, (i // cols) * th))
    out = OUT / f"setup_frames_{name}.jpg"
    canvas.save(out, quality=85)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--set", default="all")
    ap.add_argument("--server-prompt", action="store_true")
    a = ap.parse_args()
    global SERVER
    SERVER = a.server_prompt
    names = list(SETS) if a.set == "all" else [a.set]
    all_rows = []
    for name in names:
        ims = {p: Image.open(PHOTOS / f"{p}.jpg") for p in SETS[name]}
        data = {p: jpeg(im) for p, im in ims.items()}
        jobs = [(p, r) for r in range(1, a.runs + 1) for p in ims]
        with ThreadPoolExecutor(6) as ex:
            rows = list(ex.map(lambda j: one(j[0], j[1], data[j[0]]), jobs))
        all_rows += [{**r, "set": name} for r in rows]
        okr = [r for r in rows if "error" not in r]
        s = [r["s"] for r in okr] or [0]
        msg = (f"{name:5s} {len(ims)}장×{a.runs}: 격자 나옴 {sum(bool(r.get('grid')) for r in rows)}/{len(rows)}, 오류 {len(rows) - len(okr)}"
               f" | {statistics.median(s):.1f}/{sorted(s)[int(0.9 * (len(s) - 1))]:.1f}/{max(s):.1f}초")
        diffs = [max(r["diff"]) for r in rows if r.get("diff")]
        if diffs:
            msg += f" | 딱 맞춘 선 − 수동(가장 큰 차이) 중앙 {statistics.median(diffs)} · 최대 {max(diffs)}"
        msg += f" | 넉넉한 격자 나옴 {sum(bool(r.get('big')) for r in rows)}/{len(rows)}"
        msg += f" | 바깥 띠 나옴 {sum(bool(r.get('strips')) for r in rows)}/{len(rows)}"
        print(f"{msg} → {draw(name, ims, rows)}")
        for r in rows:
            if r.get("big_diff"):
                print(f"   {r['photo']}#{r['run']} 넉넉한 {r['big']['grid']} 수동 {MANUAL[r['photo']]} (넉넉한−수동 {r['big_diff']}, u {r['big']['u']})")
            elif not r.get("grid"):
                print(f"   {r['photo']}#{r['run']} 격자 못 냄 {r.get('error', '')[:100]}")
    OUT.mkdir(exist_ok=True)
    (OUT / ("setup_frames_server.json" if SERVER else "setup_frames.json")).write_text(json.dumps(all_rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
