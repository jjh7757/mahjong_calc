"""패 위치는 화료자 쪽 테이블 절반에서 찾고, 종류는 조각으로 읽으면 나아지나(2026-11-01). 표 1-5 의 통째 읽기는 위치는 잡고 종류가 나빴다.

위치(모델 호출 없음): 격자 가운데 선부터 화료자 쪽 끝까지 자른 사진을 겹치는 창으로 나눠 YOLO11 → 패 면 상자. 패가 작아지지 않게 창마다 긴 변 1280.
  손패 줄 = 사진 아래쪽에서 가장 많은 패가 놓인 직선, 놓친 패는 간격으로 채움. 줄보다 패 2.5개 넘게 위는 강으로 보고 버린다. 왼쪽 아래 모서리 묶음은 옆 사람 것.
  울기 = 오른쪽 아래 모서리 칸을 통째로 Gemini 에(흰 패 3장은 YOLO·무늬 검사가 못 잡음). 나머지 낱장 = 떨어진 패 또는 표시패 후보.
종류: 조각 그림 한 장 + 참고표를 3번 읽어 칸마다 다수결(운영 조각 읽기와 같은 문구). 모서리 칸도 3번 다수결.
고르기: 줄 + 울기×3 이 13·14 에 모자라면 낱장을 더한다. 낱장이 남으면 화료형(14) 또는 텐파이(13)를 이루는 조합만 받고, 조합이 하나가 아니면 확인 필요.

  python -X utf8 experiments/speed/wide_pieces.py --locate        위치만, 그림 results/wide_pieces/vis
  python -X utf8 experiments/speed/wide_pieces.py [--runs-bcd 2]  운영 /v2/seat 와 같은 순간에 나란히
  python -X utf8 experiments/speed/wide_pieces.py --show
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import wide_seat as ws  # noqa: E402  (GEMINI_API_KEY 도 여기서 읽는다)
from wide_seat import b, sg, ob  # noqa: E402
import visit_truth_check as vc  # noqa: E402

from app import river as rv  # noqa: E402
from app import seat as st  # noqa: E402
from app.recognizer import REF_SHEET  # noqa: E402

OUT = ws.OUT.parent / "wide_pieces.json"
VIS = ws.OUT.parent / "wide_pieces" / "vis"
WIN, OVER = 1280, 320
_det = None


def detector() -> rv.TileDetector:
    global _det
    if _det is None:
        _det = rv.TileDetector(conf=0.04)
    return _det


def detect_all(rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    H, W = rgb.shape[:2]
    xs = list(range(0, max(1, W - WIN), WIN - OVER)) + [max(0, W - WIN)]
    ys = list(range(0, max(1, H - WIN), WIN - OVER)) + [max(0, H - WIN)]
    boxes = []
    for x0, y0 in itertools.product(sorted(set(xs)), sorted(set(ys))):
        part = np.ascontiguousarray(rgb[y0:y0 + WIN, x0:x0 + WIN])
        for bx in detector().detect(part):
            if bx[0] <= 1 and x0 > 0 or bx[1] <= 1 and y0 > 0 or bx[0] + bx[2] >= part.shape[1] - 1 and x0 + WIN < W or bx[1] + bx[3] >= part.shape[0] - 1 and y0 + WIN < H:
                continue  # 창 경계에 잘린 상자는 옆 창에 맡긴다
            boxes.append((bx[0] + x0, bx[1] + y0, bx[2], bx[3]))
    white = rv.white_mask(rgb)
    return rv.dedupe(rv.keep_faces(boxes, white))


def locate(rgb: np.ndarray) -> dict | None:
    faces = detect_all(rgb)
    H, W = rgb.shape[:2]
    # 정상 크기만(패 긴 변 중앙값 ±40%): 흰 테두리·기기 반사 조각을 뺀다
    if len(faces) < 3:
        return None
    long = statistics.median(max(x[2], x[3]) for x in faces)
    faces = [x for x in faces if 0.6 * long <= max(x[2], x[3]) <= 1.4 * long]
    faces = st.on_table(faces, rgb, 1.3 * long)
    th = statistics.median(x[3] for x in faces if x[3] > x[2]) if any(x[3] > x[2] for x in faces) else long
    tw = statistics.median(x[2] for x in faces if x[3] > x[2]) if any(x[3] > x[2] for x in faces) else long * 0.75
    low = [f for f in faces if f[1] + f[3] / 2 > 0.35 * H]
    line = st.fit_line(low)
    if line is None:
        return None
    a, c = line
    on = sorted([f for f in low if abs(f[1] + f[3] / 2 - (a * (f[0] + f[2] / 2) + c)) < 0.6 * th], key=lambda x: x[0])
    runs = [[on[0]]]
    for f in on[1:]:
        if f[0] - (runs[-1][-1][0] + runs[-1][-1][2]) > 2.0 * tw:  # 손패를 벌려 놓은 틈은 패 2개까지 같은 줄
            runs.append([f])
        else:
            runs[-1].append(f)
    row = fill_row(max(runs, key=len), rgb, tw)
    rx0, rx1 = row[0][0], row[-1][0] + row[-1][2]
    ry = statistics.mean(f[1] for f in row)
    corner = corner_zone(rgb, rx1, ry, tw, th, a)
    used = set(row)
    near = [f for f in faces if f not in used and f[1] + f[3] > ry - 2.5 * th and st.ink(rgb, f) >= st.INK_MIN]
    singles, others = [], []
    for g in st.cluster(near, tw * 0.45, th * 0.5):
        cx = statistics.mean(x[0] + x[2] / 2 for x in g)
        cy = statistics.mean(x[1] + x[3] / 2 for x in g)
        if corner[0] <= cx and corner[1] <= cy:
            continue  # 모서리 칸은 통째로 읽는다
        if len(g) >= 3 and max(x[0] + x[2] for x in g) < rx0:
            others.extend(g)  # 왼쪽 아래 모서리: 옆 사람 울기
        else:
            singles.extend(g)
    return {"row": row, "corner": corner, "singles": singles, "others": others, "tw": tw, "th": th, "faces": len(faces)}


def white_at(rgb: np.ndarray, x: tuple[int, int, int, int]) -> float:
    c = rgb[max(0, x[1]):x[1] + x[3], max(0, x[0]):x[0] + x[2]]
    if c.size == 0 or x[0] < 0 or x[0] + x[2] > rgb.shape[1]:
        return 0.0
    return float(rv.white_mask(c).mean())


def fill_row(row: list, rgb: np.ndarray, tw: float) -> list:
    """YOLO 가 놓친 줄 안 패를 간격으로 채운다(흰 패 면이 70% 이상인 칸만, 줄 끝 바깥도 한 칸씩)."""
    if len(row) < 2:
        return row
    pitch = statistics.median(b2[0] - b1[0] for b1, b2 in zip(row, row[1:]))
    pitch = min(pitch, tw * 1.25)
    out = [row[0]]
    for nx in row[1:]:
        prev = out[-1]
        k = round((nx[0] - prev[0]) / pitch)
        for i in range(1, k):
            t = i / k
            box = (round(prev[0] + (nx[0] - prev[0]) * t), round(prev[1] + (nx[1] - prev[1]) * t), prev[2], prev[3])
            if white_at(rgb, box) >= 0.7:
                out.append(box)
        out.append(nx)
    for step, end in ((-1, 0), (1, -1)):
        while True:
            e = out[end]
            box = (round(e[0] + step * pitch), e[1], e[2], e[3])
            if white_at(rgb, box) < 0.7:
                break
            out.insert(0, box) if step < 0 else out.append(box)
    return out


def corner_zone(rgb: np.ndarray, rx1: float, ry: float, tw: float, th: float, slope: float = 0.0) -> tuple[int, int, int, int]:
    """오른쪽 아래 모서리 칸(x0, y0, x1, y1): 펠트 오른쪽 끝에서 패 4.5개 안쪽까지, 손패 줄 높이(줄 기울기만큼 옮김)부터 사진 끝까지. 끝에 놓인 패·테두리까지 넉넉히."""
    H, W = rgb.shape[:2]
    y0 = int(max(0, ry - 0.5 * th))
    felt = st.felt_mask(rgb[y0:H])
    cols = np.where(felt.mean(0) > 0.2)[0]
    right = int(cols.max()) if cols.size else W
    x0 = int(max(rx1 + 0.3 * tw, right - 4.5 * tw))
    y0 = int(max(0, y0 + min(0.0, slope) * (right - rx1)))  # 기운 사진: 오른쪽이 올라가면 칸도 올린다
    return x0, y0, min(W, int(right + 2 * tw)), H


CORNER_PROMPT = ob.CORNER_PROMPT_V2 + "\n\n무늬 없는 흰 패(5z) 3장도 묶음입니다. 흰 테두리와 헷갈리지 말고 패의 네모난 윗면과 뒷면 색 두께로 구분합니다."


def read_corner(rgb: np.ndarray, z: tuple[int, int, int, int]) -> dict:
    im = Image.fromarray(rgb[z[1]:z[3], z[0]:z[2]])
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    jpg = buf.getvalue()

    def one(_):
        r = b.call(jpg, CORNER_PROMPT, ob.CORNER_SCHEMA_V2, "gemini-3.8-flash", "low", "ULTRA_HIGH")
        return ob.normalize_corner_v2(r["data"]) if "data" in r else None

    with ThreadPoolExecutor(3) as ex:
        reads = [r for r in ex.map(one, range(3)) if r]
    if not reads:
        return {"melds": [], "loose": []}
    keyf = lambda r: tuple(sorted(" ".join(sorted(m["tiles"])) for m in r["melds"]))
    top = Counter(keyf(r) for r in reads).most_common(1)[0][0]
    r = next(x for x in reads if keyf(x) == top)
    return {"melds": [" ".join(m["tiles"]) for m in r["melds"]], "loose": [t["tile"] for t in r["loose"]]}


def draw(rgb: np.ndarray, loc: dict, path: Path, label: str) -> None:
    im = Image.fromarray(rgb).copy()
    d = ImageDraw.Draw(im)
    for key, col in (("row", (255, 0, 0)), ("singles", (255, 200, 0)), ("others", (120, 120, 120))):
        for x in loc[key]:
            d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=col, width=8)
    d.rectangle(loc["corner"], outline=(0, 120, 255), width=8)
    d.text((10, 10), label, fill=(255, 255, 0), font_size=60)
    im.thumbnail((1400, 1400))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=85)


def half_rgb(s: dict) -> np.ndarray:
    im = Image.open(s["path"]).convert("RGB")
    return np.asarray(sg.crop(im, ws.half_box(s["grid"], s["side"]), s["side"]))


def sheet_of(rgb: np.ndarray, boxes: list) -> bytes:
    fr = st.SeatFrame(hand=boxes, separate=None, melds=[])
    return st.sheet(rgb, fr)


def read_pieces(rgb: np.ndarray, boxes: list) -> tuple[list[str | None], bool]:
    img = sheet_of(rgb, boxes)
    n = len(boxes)
    extra = [b.image_part(REF_SHEET.read_bytes(), None)]
    prompt, schema = ob.piece_prompt(n), ob.piece_schema(n)

    def one(_):
        r = b.call(img, prompt, schema, "gemini-3.8-flash", "low", "ULTRA_HIGH", extra=extra)
        if "data" not in r:
            return None
        return [t["tile"] if t else None for t in ob.normalize_pieces(r["data"], n)]

    with ThreadPoolExecutor(3) as ex:
        reads = [r for r in ex.map(one, range(3)) if r]
    if not reads:
        return [None] * n, False
    out = [Counter(r[i] for r in reads).most_common(1)[0][0] for i in range(n)]
    return out, len(reads) == 3 and all(r == reads[0] for r in reads)


def is_ok_hand(ts: list[str], meld_n: int) -> bool:
    total = len(ts) + 3 * meld_n
    if total == 14:
        return vc.is_win(ts)
    return total == 13 and bool(vc.waits(ts))


def assemble(row: list[str], melds: list[list[str]], singles: list[str]) -> dict:
    """줄 + 울기에 낱장을 더해 13·14 를 맞춘다. 맞는 조합이 정확히 하나일 때만 답을 낸다."""
    base = len(row) + 3 * len(melds)
    picks = set()
    for need in (13 - base, 14 - base):
        if need < 0 or need > len(singles):
            continue
        for c in itertools.combinations(range(len(singles)), need):
            ts = row + [singles[i] for i in c]
            if is_ok_hand(ts, len(melds)):
                picks.add(tuple(sorted(singles[i] for i in c)))
    if len(picks) == 1:
        p = list(next(iter(picks)))
        rest = list((Counter(singles) - Counter(p)).elements())
        return {"sep": p, "rest": rest, "decided": True}
    return {"sep": [], "rest": singles, "decided": False, "choices": len(picks)}


def run_pieces(rgb: np.ndarray) -> dict:
    t0 = time.perf_counter()
    loc = locate(rgb)
    locate_s = time.perf_counter() - t0
    if not loc or not loc["row"]:
        return {"error": "위치 못 찾음", "s": round(time.perf_counter() - t0, 1)}
    H, W = rgb.shape[:2]

    def grown(x):  # 돌아간 낱장은 상자가 패 일부만 잡기도 해 넉넉히
        px, py = int(x[2] * 0.2), int(x[3] * 0.2)
        x0, y0 = max(0, x[0] - px), max(0, x[1] - py)
        return (x0, y0, min(W, x[0] + x[2] + px) - x0, min(H, x[1] + x[3] + py) - y0)

    boxes = loc["row"] + [grown(x) for x in loc["singles"]]
    with ThreadPoolExecutor(2) as ex:
        f1, f2 = ex.submit(read_pieces, rgb, boxes), ex.submit(read_corner, rgb, loc["corner"])
        (tiles, unan), corner = f1.result(), f2.result()
    nr = len(loc["row"])
    row = tiles[:nr]
    melds = corner["melds"]
    singles = tiles[nr:] + corner["loose"]
    known = [t for t in singles if t]
    out = {"row": row, "melds": melds, "singles": singles, "unanimous": unan, "locate_s": round(locate_s, 1), "s": round(time.perf_counter() - t0, 1)}
    if all(row):
        out.update(assemble(row, [m.split() for m in melds], known))
    else:
        out.update(sep=[], rest=known, decided=False, choices=0)
    return out


def judge(s: dict, r: dict) -> dict:
    if "error" in r:
        return {"ok": False, "decided": False}
    if s["hand"] is None:
        return {}
    melds = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    hand_ok = sorted([t for t in r["row"] if t] + r["sep"]) == sorted(s["hand"]) and melds(r["melds"]) == melds(s["melds"])
    # 위치·종류 진단: 정답 패가 후보 안에 다 있나(낱장 고르기와 무관)
    found = Counter([t for t in r["row"] if t] + [t for t in r["singles"] if t] + [t for m in r["melds"] for t in m.split()])
    truth = Counter(s["hand"] + [t for m in s["melds"] for t in m.split()])
    return {"ok": hand_ok and r.get("decided", False), "hand_ok": hand_ok, "all_found": not (truth - found)}


def do_locate() -> None:
    for s in sg.scenes():
        rgb = half_rgb(s)
        t0 = time.perf_counter()
        loc = locate(rgb)
        secs = time.perf_counter() - t0
        if not loc:
            print(s["name"][-6:], "못 찾음")
            continue
        total = len(s["hand"]) + 3 * len(s["melds"]) if s["hand"] is not None else None
        want = len(s["hand"]) if s["hand"] is not None else None
        print(s["name"][-6:], s["side"], f"줄 {len(loc['row'])} 낱장 {len(loc['singles'])} 뺀 묶음 {len(loc['others'])}",
              f"정답 비공개 {want} 정답 울기 {len(s['melds'])} 검출 {loc['faces']} {secs:.1f}초", flush=True)
        draw(rgb, loc, VIS / f"{s['name'][-6:]}.jpg", s["name"][-6:])


def main(a) -> None:
    rows = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    for s in sg.scenes():
        if a.only and a.only not in s["name"]:
            continue
        rgb = half_rgb(s)
        im = Image.fromarray(rgb) if False else Image.open(s["path"]).convert("RGB")
        for i in range(a.runs_bcd if s["set"] == "bcd" else a.runs_visit):
            with ThreadPoolExecutor(2) as ex:
                f1, f2 = ex.submit(ws.run_seat, s, im), ex.submit(run_pieces, rgb)
                seat, pc = f1.result(), f2.result()
            row = {"name": s["name"], "set": s["set"], "side": s["side"], "run": i, "at": time.strftime("%H:%M:%S"),
                   "seat": {**seat, **ws.judge(s, seat)}, "pieces": {**pc, **judge(s, pc)}}
            rows.append(row)
            OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            print(s["name"][-6:], s["side"], "seat", seat.get("s"), row["seat"].get("ok"), "| pieces", pc.get("s"), row["pieces"].get("ok"), row["pieces"].get("hand_ok"), pc.get("decided"), pc.get("error", ""), flush=True)
            time.sleep(a.sleep)


def show() -> None:
    rows = json.loads(OUT.read_text(encoding="utf-8"))
    parts = [("B·C·D", lambda r: r["set"] == "bcd"), ("매장 오전", lambda r: r["set"] == "visit" and r["name"] < "20261031_14"),
             ("매장 오후", lambda r: r["set"] == "visit" and r["name"] >= "20261031_14")]
    for label, f in parts:
        part = [r for r in rows if f(r)]
        if not part:
            continue
        v = [r["seat"] for r in part]
        t = sorted(x["s"] for x in v)
        print(f"{label} seat: 정답 {sum(1 for x in v if x.get('ok'))}/{len(v)} 시간 {statistics.median(t):.1f} / {t[min(len(t) - 1, int(.9 * len(t)))]:.1f} / {t[-1]:.1f}")
        v = [r["pieces"] for r in part]
        t = sorted(x["s"] for x in v)
        wrong = [x for x in v if x.get("decided") and not x.get("ok")]
        print(f"{label} pieces: 정답 {sum(1 for x in v if x.get('ok'))}/{len(v)} 답을 냄 {sum(1 for x in v if x.get('decided'))} 틀린 답 {len(wrong)} 확인 필요 {sum(1 for x in v if not x.get('decided'))}"
              f" 후보 안에 정답 패 전부 {sum(1 for x in v if x.get('all_found'))} 만장일치 {sum(1 for x in v if x.get('unanimous'))} 시간 {statistics.median(t):.1f} / {t[min(len(t) - 1, int(.9 * len(t)))]:.1f} / {t[-1]:.1f}")
    print("-- 사진별")
    for r in rows:
        p = r["pieces"]
        print(r["name"][-6:], "seat", r["seat"].get("ok"), "| pieces", p.get("ok"), "답", p.get("decided"), "전부", p.get("all_found"), " ".join(str(t) for t in p.get("row", [])), "| 울기", p.get("melds"), "| 낱장", p.get("singles"), "→", p.get("sep"), p.get("choices", ""), p.get("error", ""))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--locate", action="store_true")
    p.add_argument("--runs-bcd", type=int, default=2)
    p.add_argument("--runs-visit", type=int, default=1)
    p.add_argument("--only", default="")
    p.add_argument("--sleep", type=float, default=8)
    p.add_argument("--show", action="store_true")
    a = p.parse_args()
    show() if a.show else do_locate() if a.locate else main(a)
