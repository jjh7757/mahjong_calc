"""자리 판독을 강 끝처럼: YOLO11s(nikmomo, 서버 app/river.py 와 같은 onnxruntime 검출)로 패 위치를 잡고
코드가 손패 줄·떨어진 한 장·울기 묶음을 나눈 뒤, Gemini 는 번호 붙인 패 조각의 종류만 읽는다(2026-10-26 밤, 사용자 요청).

  python -I experiments/speed/seat_yolo.py locate [--conf 0.04]          검출·틀 그림 results/seat_yolo/
  python -I experiments/speed/seat_yolo.py read --runs 10 [--cond pieces] 조각 읽기 정확도·지연(bench.py seat 와 같은 채점)

비교 기준(지금 서버 자리 판독)은 bench.py seat --cond v3a_norule.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import bench as b  # noqa: E402

from app import river as rv  # noqa: E402  (bench 가 mahjong-recognizer 를 sys.path 에 넣음)

OUT = ROOT / "results" / "seat_yolo"
FONT = "C:/Windows/Fonts/arial.ttf"


# ---------------------------------------------------------------- 검출(창 나눠 돌리기)

WIN = 1.0  # 창 한 변 = 크롭 높이 × WIN


def detect_tiled(det: rv.TileDetector, rgb: np.ndarray) -> list[rv.Box]:
    """자리 크롭은 가로로 길어(2.2~3.3:1) 640 하나로 줄이면 패가 15~20px 가 된다 → 정사각 창(한 변 = 높이 × WIN)을
    가로·세로로 반씩 겹쳐 돌린다."""
    H, W = rgb.shape[:2]
    side = int(min(H, W) * WIN)

    def starts(n):
        xs = list(range(0, max(1, n - side) + 1, side // 2))
        if xs[-1] + side < n:
            xs.append(n - side)
        return xs

    boxes = []
    for y0 in starts(H):
        for x0 in starts(W):
            for bx in det.detect(rgb[y0:y0 + side, x0:x0 + side]):
                boxes.append((bx[0] + x0, bx[1] + y0, bx[2], bx[3]))
    return boxes


# ---------------------------------------------------------------- 틀(코드가 구조를 정함)

def structure(rgb: np.ndarray, boxes: list[rv.Box], gap: float = 0.35, sep_dist: float = 2.5) -> dict | None:
    """패 면 상자 → 손패 줄(가장 긴 줄) + 떨어진 한 장 + 오른쪽 묶음(울기 3~4장, 그 밖은 loose).
    사진은 그 사람 쪽에서 본 방향(손패가 아래, 울기는 손패 줄 오른쪽 모서리 쪽)."""
    faces = rv.dedupe(rv.keep_faces(boxes, rv.white_mask(rgb)))
    if not faces:
        return None
    upright = [x for x in faces if x[3] > x[2]] or faces
    tw = statistics.median(x[2] for x in upright)
    th = statistics.median(x[3] for x in upright)
    # 이웃(틈 < 패 0.35개)으로 묶기 — 손패 줄 안 틈은 거의 0, 떨어진 한 장·울기는 그보다 멀다
    groups = cluster(faces, tw * gap, th * 0.5)
    # 손패 줄: 가장 많은 묶음(같은 수면 아래쪽)
    hand_g = max(groups, key=lambda g: (len(g), max(x[1] + x[3] for x in g)))
    hand = sorted(hand_g, key=lambda x: x[0])
    rest = [g for g in groups if g is not hand_g]
    hx1 = max(x[0] + x[2] for x in hand)
    hcy = statistics.mean(x[1] + x[3] / 2 for x in hand)
    sep = None
    # 떨어진 한 장: 손패 줄 바로 오른쪽(패 2.5개 안), 같은 높이의 한 장 묶음
    near = [g for g in rest if len(g) == 1 and 0 <= g[0][0] - hx1 < sep_dist * tw and abs(g[0][1] + g[0][3] / 2 - hcy) < th * 0.6]
    if near:
        sep = min(near, key=lambda g: g[0][0])[0]
        rest = [g for g in rest if g[0] is not sep]
    melds, loose = [], []
    for g in rest:
        g = sorted(g, key=lambda x: x[0])
        # 울기: 손패 줄 오른쪽, 3~4장(가로 패는 폭이 넓다)
        if 3 <= len(g) <= 4 and min(x[0] for x in g) > hx1 - tw:
            melds.append(g)
        else:
            loose.extend(g)
    return {"hand": hand, "separate": sep, "melds": melds, "loose": loose, "tw": tw, "th": th,
            "detected": len(boxes), "faces": len(faces)}


def valid(st: dict | None) -> bool:
    """장수 검사(정답 없이): 손패 + 떨어진 한 장 + 울기(묶음마다 3장으로 셈)가 13 또는 14."""
    if not st:
        return False
    n = len(st["hand"]) + (1 if st["separate"] else 0) + 3 * len(st["melds"])
    return n in (13, 14)


# ---------------------------------------------------------------- 안전 검사(과적합 대비, overfit_check.py)
# 장수 검사만으로는 흔든 사진에서 "틀이 틀렸는데 통과" 가 15% 였다 → 사진에 맞춘 값이 아닌 패 모양의 일반 규칙을 더한다.

def strict_ok(st) -> bool:
    """장수 검사에 더하는 모양 검사(정답·사진과 무관한 일반 규칙): 손패 줄 상자가
    (1) 크기가 고르고(높이·너비가 중앙값의 ±25% 안) (2) 한 줄로 늘어서고(가운데 y 가 직선에서 패 높이 0.25 안)
    (3) 서로 반 장 넘게 겹치지 않고 (4) 이웃 간격이 고르다(패 너비 0.6~1.4배)."""
    hand = st["hand"]
    if len(hand) < 4:
        return False
    hs = [x[3] for x in hand]
    ws = [x[2] for x in hand]
    mh, mw = statistics.median(hs), statistics.median(ws)
    if any(abs(h - mh) > 0.25 * mh for h in hs) or any(abs(w - mw) > 0.25 * mw for w in ws):
        return False
    xs = np.array([x[0] + x[2] / 2 for x in hand])
    ys = np.array([x[1] + x[3] / 2 for x in hand])
    a, c = np.polyfit(xs, ys, 1)
    if np.max(np.abs(ys - (a * xs + c))) > 0.25 * mh:
        return False
    steps = np.diff(xs)
    return bool(np.all(steps > 0.6 * mw) and np.all(steps < 1.4 * mw))


def ink(rgb: np.ndarray, x) -> float:
    """상자 안쪽(가장자리 15% 빼고)에서 무늬(글자·동그라미·막대) 픽셀 비율: 어둡거나(V<120) 색이 진함(S>80)."""
    bx, by, bw, bh = x
    mx, my = int(bw * 0.15), int(bh * 0.15)
    c = rgb[by + my:by + bh - my, bx + mx:bx + bw - mx]
    if c.size == 0:
        return 0.0
    hsv = np.asarray(Image.fromarray(c).convert("HSV")).astype(int)
    return float(((hsv[..., 2] < 120) | (hsv[..., 1] > 80)).mean())


INK_MIN = 0.03  # 미리 정한 값(패 그림이 면의 10~30%) — 무늬 없는 白 은 걸러져 통째 읽기로 간다(안전한 쪽)


def safe_ok(st, rgb) -> bool:
    """strict_ok + 울기 모양(상자끼리 너비 30% 넘게 겹치지 않음, 높이가 손패 패 높이의 0.5~1.3배) + 모든 조각에 무늬."""
    if not strict_ok(st):
        return False
    th = statistics.median(x[3] for x in st["hand"])
    for m in st["melds"]:
        m = sorted(m, key=lambda x: x[0])
        for a, c in zip(m, m[1:]):
            if a[0] + a[2] - c[0] > 0.3 * min(a[2], c[2]):
                return False
        if any(not 0.5 * th <= x[3] <= 1.3 * th for x in m):
            return False
    return all(ink(rgb, x) >= INK_MIN for _, x in pieces(st))



DET_MODE = "tiled"  # tiled: 정사각 창 반씩 겹침(추론 4~6번) / mosaic: 손패 띠 4토막을 쌓아 한 번(추론 2번, seat_det_variants)


def seat_frame(dets: list, rgb: np.ndarray) -> tuple[dict | None, list, str]:
    """모델을 차례로(s → m) 돌려 장수 검사를 통과한 첫 틀. 다 실패하면 (None, 마지막 상자, "whole") — 지금 방식으로 읽는다."""
    boxes = []
    for name, det in dets:
        if DET_MODE == "mosaic":
            import seat_det_variants as dv
            boxes = dv.mosaic(det, rgb, 4)[0] or []
            boxes = [x for x in boxes if ink(rgb, x) >= INK_MIN]  # 무늬 없는 상자(테이블 테두리 등)는 버림
            st = structure(rgb, boxes)
            if valid(st) and safe_ok(st, rgb):
                return st, boxes, name
            continue
        boxes = detect_tiled(det, rgb)
        st = structure(rgb, boxes)
        if valid(st):
            return st, boxes, name
    return None, boxes, "whole"


def cluster(boxes, gx: float, gy: float) -> list[list[rv.Box]]:
    left = list(boxes)
    out = []
    while left:
        g = [left.pop()]
        i = 0
        while i < len(g):
            a = g[i]
            for x in left[:]:
                dx = max(0, max(a[0], x[0]) - min(a[0] + a[2], x[0] + x[2]))
                dy = max(0, max(a[1], x[1]) - min(a[1] + a[3], x[1] + x[3]))
                if dx < gx and dy < gy:
                    g.append(x)
                    left.remove(x)
            i += 1
        out.append(g)
    return out


def pieces(st: dict) -> list[tuple[str, rv.Box]]:
    """읽을 순서: 손패 → 떨어진 한 장 → 울기 묶음(왼쪽부터). loose 는 점수와 무관해 읽지 않는다."""
    out = [("hand", x) for x in st["hand"]]
    if st["separate"]:
        out.append(("sep", st["separate"]))
    for mi, m in enumerate(st["melds"]):
        out += [(f"meld{mi}", x) for x in m]
    return out


def draw(rgb: np.ndarray, boxes, st: dict | None, title: str) -> Image.Image:
    im = Image.fromarray(rgb).copy()
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 40)
    for x in boxes:
        d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=(150, 150, 150), width=2)
    if st:
        col = {"hand": (255, 140, 0), "sep": (255, 0, 0)}
        for i, (kind, x) in enumerate(pieces(st)):
            d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=col.get(kind, (0, 120, 255)), width=6)
            d.text((x[0] + 4, x[1] - 44), str(i + 1), fill=(255, 0, 255), font=f)
        for x in st["loose"]:
            d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=(0, 200, 0), width=4)
    d.text((10, 10), title, fill=(255, 255, 0), font=f)
    return im


def detectors(conf: float, models: str) -> list:
    path = {"s": rv.MODEL, "m": Path("C:/Users/jjh7757/dev/_downloads/nikmomo/mahjong-yolom-best.onnx")}
    return [(m, rv.TileDetector(path[m], conf=conf)) for m in models]


def locate_all(conf: float, models: str) -> dict:
    dets = detectors(conf, models)
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for scene in "BCD":
        for photo in b.PHOTOS[scene]:
            path = b.G / scene / photo / b.TRUTH[scene][0]
            rgb = np.asarray(Image.open(path).convert("RGB"))
            t0 = time.perf_counter()
            st, boxes, used = seat_frame(dets, rgb)
            secs = time.perf_counter() - t0
            truth_hand = len(b.TRUTH[scene][1].split())
            truth_melds = [len(m.split()) for m in b.TRUTH[scene][2]]
            got = (len(st["hand"]) + (1 if st["separate"] else 0), [len(m) for m in st["melds"]]) if st else None
            ok = got == (truth_hand, truth_melds)
            title = f"{photo} [{used}] hand {got}  truth {(truth_hand, truth_melds)}  {'OK' if ok else 'X'}"
            draw(rgb, boxes, st, title).save(OUT / f"{scene}_{photo}.jpg", quality=85)
            print(f"{scene} {photo} 검출 {len(boxes):3d} 면 {st['faces'] if st else 0:3d}  손패+떨어진 {got}  정답 "
                  f"{(truth_hand, truth_melds)}  {'OK' if ok else 'X'}  [{used}] {secs:.2f}s", flush=True)
            res[photo] = {"scene": scene, "ok": ok, "secs": secs, "st": st, "used": used}
    return res


# ---------------------------------------------------------------- 읽기(Gemini 는 종류만)

PIECE_PROMPT = """첫 사진은 리치마작 테이블에서 한 플레이어 자리를 그 사람 쪽에서 본 방향으로 세운 것이고, 읽을 패에 번호(1~{n})를 붙인 상자를 그려 두었습니다.
그 다음 {n}장은 번호 순서대로 그 패 한 장만 원본 해상도로 잘라 낸 조각입니다(가장자리에 이웃 패가 조금 걸릴 수 있음).

- tiles: 조각 순서대로 정확히 {n}개. 조각 가운데에 온전히 보이는 패 한 장의 종류(code)와 확신도.
  옆으로 눕힌 패는 그대로 읽습니다. 뒷면(연보라)만 보이면 code 를 "back" 으로 적습니다.
- 장수·순서·묶음은 이미 정해져 있습니다. 패를 더하거나 빼지 않습니다.

{notation}

마지막 사진은 이 패 세트의 통수(1p~9p)·삭수(1s~9s) 실물 참고표입니다(이름표가 위에 있음). 통수·삭수는 참고표와 무늬 개수·배치를 비교해 정합니다.
참고표는 답에 넣지 않습니다."""


# 입력 줄이기 변형(2026-10-26 밤): noov = 번호 사진 없이 조각 + 참고표, sheet = 조각을 번호 칸에 붙인 그림 한 장 + 참고표
PIECE_PROMPT_NOOV = PIECE_PROMPT.replace(
    """첫 사진은 리치마작 테이블에서 한 플레이어 자리를 그 사람 쪽에서 본 방향으로 세운 것이고, 읽을 패에 번호(1~{n})를 붙인 상자를 그려 두었습니다.
그 다음 {n}장은 번호 순서대로 그 패 한 장만 원본 해상도로 잘라 낸 조각입니다(가장자리에 이웃 패가 조금 걸릴 수 있음).""",
    """사진 {n}장은 각각 리치마작 테이블 위의 패 한 장을 원본 해상도로 잘라 낸 조각입니다(가장자리에 이웃 패가 조금 걸릴 수 있음).""")
PIECE_PROMPT_SHEET = PIECE_PROMPT.replace(
    """첫 사진은 리치마작 테이블에서 한 플레이어 자리를 그 사람 쪽에서 본 방향으로 세운 것이고, 읽을 패에 번호(1~{n})를 붙인 상자를 그려 두었습니다.
그 다음 {n}장은 번호 순서대로 그 패 한 장만 원본 해상도로 잘라 낸 조각입니다(가장자리에 이웃 패가 조금 걸릴 수 있음).""",
    """첫 사진은 리치마작 테이블 위의 패 {n}장을 한 장씩 잘라 번호(1~{n}) 칸에 순서대로 붙인 것입니다(칸 가장자리에 이웃 패가 조금 걸릴 수 있음).""").replace(
    "- tiles: 조각 순서대로 정확히 {n}개. 조각 가운데에",
    "- tiles: 번호 순서대로 정확히 {n}개. 칸 가운데에")


def piece_sheet(rgb: np.ndarray, st: dict, cell_h: int = 200, per_row: int = 7) -> bytes:
    cells = []
    for _, x in pieces(st):
        im = Image.open(io.BytesIO(rv.crop(rgb, x))).convert("RGB")
        im = im.resize((max(1, round(im.width * cell_h / im.height)), cell_h), Image.LANCZOS)
        cells.append(im)
    cw = max(c.width for c in cells) + 12
    lab = 40
    rows = (len(cells) + per_row - 1) // per_row
    sheet = Image.new("RGB", (cw * min(per_row, len(cells)), (cell_h + lab) * rows), "white")
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(FONT, 30)
    for i, c in enumerate(cells):
        x, y = (i % per_row) * cw, (i // per_row) * (cell_h + lab)
        d.text((x + cw // 2 - 10, y + 2), str(i + 1), fill=(200, 0, 0), font=f)
        sheet.paste(c, (x + (cw - c.width) // 2, y + lab))
    return b.jpeg(sheet)


def piece_schema(n: int) -> dict:
    item = {"type": "object", "properties": {"code": {"type": "string", "enum": b.ob.TILE_CODES + ["back"]},
                                             "confidence": {"type": "number"}}, "required": ["code", "confidence"]}
    return {"type": "object", "properties": {"tiles": {"type": "array", "items": item, "minItems": n, "maxItems": n},
                                             "notes": {"type": "string"}}, "required": ["tiles"]}


def numbered(rgb: np.ndarray, st: dict) -> bytes:
    im = Image.fromarray(rgb).copy()
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, max(24, int(st["th"] * 0.35)))
    for i, (_, x) in enumerate(pieces(st)):
        d.rectangle((x[0], x[1], x[0] + x[2], x[1] + x[3]), outline=(255, 0, 0), width=3)
        d.text((x[0] + 2, x[1] - f.size - 4), str(i + 1), fill=(255, 0, 0), font=f)
    im.thumbnail((3072, 3072))
    return b.jpeg(im)


def piece_read(scene: str, photo: str, rgb: np.ndarray, st: dict, layout: str, sheet: bytes) -> dict:
    """틀(st)의 조각을 Gemini 한 호출로 읽어 bench.judge 로 채점한 행."""
    ps = pieces(st)
    n = len(ps)
    crops = [rv.crop(rgb, x) for _, x in ps]
    if layout == "noov":
        first, res, extra = crops[0], None, [b.image_part(c, None) for c in crops[1:]] + [b.image_part(sheet, None)]
        prompt = PIECE_PROMPT_NOOV.format(n=n, notation=b.ob.NOTATION)
    elif layout == "sheet":
        first, res, extra = piece_sheet(rgb, st), "ULTRA_HIGH", [b.image_part(sheet, None)]
        prompt = PIECE_PROMPT_SHEET.format(n=n, notation=b.ob.NOTATION)
    else:
        first, res, extra = numbered(rgb, st), "ULTRA_HIGH", [b.image_part(c, None) for c in crops] + [b.image_part(sheet, None)]
        prompt = PIECE_PROMPT.format(n=n, notation=b.ob.NOTATION)
    r = b.call(first, prompt, piece_schema(n), b.BASE["model"], "low", res, extra=extra)
    row = {"scene": scene, "photo": photo, **{k: r.get(k) for k in ("s", "in", "out", "think", "error")}}
    if "data" in r:
        codes = [t["code"] for t in r["data"]["tiles"]]
        data = {"face_up": True, "separate_tile": None, "loose": [], "notes": "",
                "tiles": [{"code": c, "confidence": 1} for c, (k, _) in zip(codes, ps) if k == "hand"],
                "melds": []}
        sep = [c for c, (k, _) in zip(codes, ps) if k == "sep"]
        if sep:
            data["separate_tile"] = {"code": sep[0], "confidence": 1}
        for mi in range(len(st["melds"])):
            data["melds"].append({"tiles": [c for c, (k, _) in zip(codes, ps) if k == f"meld{mi}"],
                                  "sideways": [], "face_down": []})
        row.update(b.judge(scene, data))
        row["codes"] = codes
    return row


def read(runs: int, workers: int, conf: float, cond: str, models: str, layout: str = "pieces") -> None:
    dets = detectors(conf, models)
    prep = {}
    for scene in "BCD":
        for photo in b.PHOTOS[scene]:
            path = b.G / scene / photo / b.TRUTH[scene][0]
            rgb = np.asarray(Image.open(path).convert("RGB"))
            t0 = time.perf_counter()
            st, _, used = seat_frame(dets, rgb)
            prep[photo] = (scene, rgb, st, time.perf_counter() - t0)
            print(f"{scene} {photo} 틀 [{used}] {time.perf_counter() - t0:.2f}s", flush=True)
    # 틀을 못 잡은 사진은 지금 방식(bench v3a_norule)으로 읽는다 — 운영에서 강 끝의 method: whole 과 같은 장치
    prep = {p: v for p, v in prep.items() if v[2] is not None}
    sheet = b.ref_sheet_set2()

    def one(job):
        run_i, photo = job
        scene, rgb, st, det_s = prep[photo]
        row = {"run": run_i, "det_s": round(det_s, 2), **piece_read(scene, photo, rgb, st, layout, sheet)}
        print(f"{scene} {photo} #{run_i} {row['s']:5.1f}s think {row.get('think')}  "
              f"{'OK' if row.get('hand_ok') and row.get('melds_ok') else 'X ' + str(row.get('hand')) + ' ' + str(row.get('melds'))}",
              flush=True)
        return row

    jobs = [(r, p) for r in range(runs) for p in prep]
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, jobs))
    b.save(f"seat_{cond}", rows)
    b.summarize(cond, rows)
    stats(rows)


def stats(rows: list[dict]) -> None:
    t = sorted(r["s"] for r in rows if not r.get("error"))
    think = [r["think"] or 0 for r in rows if not r.get("error")]
    print(f"  시간 중앙 {statistics.median(t):.1f} / p90 {t[int(.9 * len(t))]:.1f} / 최대 {t[-1]:.1f}초  "
          f"생각한 호출 {sum(x > 0 for x in think)}/{len(think)}  생각 최대 {max(think)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["locate", "read", "stats"])
    ap.add_argument("--conf", type=float, default=0.04)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--cond", default="pieces")
    ap.add_argument("--win", type=float, default=1.0)
    ap.add_argument("--models", default="sm", help="차례로 시도할 YOLO11 모델(s, m)")
    ap.add_argument("--det", default="tiled", choices=["tiled", "mosaic"])
    ap.add_argument("--layout", default="pieces", choices=["pieces", "noov", "sheet"])
    a = ap.parse_args()
    WIN = a.win
    DET_MODE = a.det
    if a.mode == "locate":
        locate_all(a.conf, a.models)
    elif a.mode == "read":
        read(a.runs, a.workers, a.conf, a.cond, a.models, a.layout)
    else:
        for name in a.cond.split(","):
            rows = [r for r in json.loads((ROOT / "results" / f"seat_{name}.json").read_text(encoding="utf-8"))
                    if r["scene"] in "BCD"]
            b.summarize(name, rows)
            stats(rows)
