"""원본 사진의 앞면 패를 전부 잘라 임시 라벨을 붙인다(2026-11-01, 노트북 CPU, API 없음). build_crops.py 다음에.

상자: 운영 YOLO11 s 를 사진 4×4 토막(절반 겹침)에 돌려 앞면·무늬·탁자 안·크기로 거른다. 패 종류 출력은 안 쓴다.
임시 라벨: 라벨 크롭 259장 전부로 학습한 MobileNetV3 Small. 패 주인을 모르므로 상자 모양에 맞는 방향 중 확신이 가장 높은 쪽으로 돌린다.
같은 패: 같은 날 앞 사진들에 같은 자리·같은 임시 라벨이 있으면 dup 표시(10-24 은 같은 장면을 여러 번 찍었다).
HaseLab 은 라벨에 쓰지 않는다. 임시 라벨은 사람이 sheet_* 를 보고 고친 뒤에만 학습에 쓴다.
  python -I experiments/tile_classifier/harvest.py
결과 data/harvest/{crops/*.jpg, index.json, sheet_<종류>_<번호>.jpg}, data/model_259.pt
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import train as tr  # noqa: E402
from app import river as rv  # noqa: E402
from app import seat as st  # noqa: E402

DATA = HERE / "data"
OUT = DATA / "harvest"
CROPS = OUT / "crops"
EXP = ROOT / "experiments"
PAD = 0.12
GRID = 4
UNSURE = 0.6  # 이보다 확신이 낮으면 unsure 묶음


def boxes(det: rv.TileDetector, rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    H, W = rgb.shape[:2]
    ws, hs = W // GRID, H // GRID
    out = []
    for yy in range(0, H - hs + 1, hs // 2):
        for xx in range(0, W - ws + 1, ws // 2):
            part = np.ascontiguousarray(rgb[yy:yy + hs, xx:xx + ws])
            out += [(int(x + xx), int(y + yy), int(w), int(h)) for x, y, w, h in det.detect(part)]
    bs = rv.dedupe(rv.keep_faces(out, rv.white_mask(rgb)))
    bs = [b for b in bs if st.ink(rgb, b) >= st.INK_MIN]
    if not bs:
        return []
    short = statistics.median(min(b[2], b[3]) for b in bs)
    bs = [b for b in bs if 0.6 * short <= min(b[2], b[3]) <= 1.5 * short and max(b[2], b[3]) <= 2.2 * short]
    return st.on_table(bs, rgb, st.TABLE_REACH * short * 1.3)


def cut(rgb: np.ndarray, b: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = b
    H, W = rgb.shape[:2]
    px, py = int(w * PAD), int(h * PAD)
    return Image.fromarray(rgb[max(0, y - py):min(H, y + h + py), max(0, x - px):min(W, x + w + px)])


def turns(w: int, h: int) -> tuple[int, ...]:
    if h > 1.15 * w:
        return (0, 2)
    if w > 1.15 * h:
        return (1, 3)
    return (0, 1, 2, 3)


def label(net, crop: Image.Image, w: int, h: int) -> tuple[str, float, int]:
    ts = turns(w, h)
    x = torch.stack([tr.PLAIN(tr.square(crop.rotate(90 * k, expand=True))) for k in ts])
    with torch.no_grad():
        p = torch.softmax(net(x), 1)
    best = p.max(1).values.argmax().item()
    return tr.CLASSES[p[best].argmax().item()], float(p[best].max()), ts[best]


def iou(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    u = a[2] * a[3] + b[2] * b[3] - ix * iy
    return ix * iy / u if u else 0.0


def sheets(rows: list[dict], cell: int = 76, cols: int = 16, lines: int = 9) -> None:
    groups = defaultdict(list)
    for r in rows:
        if not r["dup"]:
            groups["unsure" if r["conf"] < UNSURE else r["pred"]].append(r)
    for g, v in groups.items():
        v.sort(key=lambda r: r["conf"])
        for k in range(0, len(v), cols * lines):
            part = v[k:k + cols * lines]
            im = Image.new("RGB", (cols * cell, (len(part) // cols + 1) * (cell + 14)), "white")
            d = ImageDraw.Draw(im)
            for i, r in enumerate(part):
                t = Image.open(CROPS / r["file"])
                t.thumbnail((cell, cell))
                x, y = (i % cols) * cell, (i // cols) * (cell + 14)
                im.paste(t, (x, y))
                d.text((x + 1, y + cell), f"{r['id']}" + (f" {r['pred']}" if g == "unsure" else ""), fill="blue")
            im.save(OUT / f"sheet_{g}_{k // (cols * lines)}.jpg", quality=88)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    CROPS.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    images = {x["file"]: tr.square(Image.open(DATA / "crops" / x["file"]).convert("RGB")) for x in index}
    net = tr.train(index, images, 0)
    torch.save(net.state_dict(), DATA / "model_259.pt")
    print("모델 학습", round(time.perf_counter() - t0), "초", flush=True)

    photos = sorted(list((EXP / "visit_20261031/captures").glob("*/original.jpg")) + list((EXP / "field_20261024/captures").glob("*/original.jpg")), key=lambda p: p.parent.name)
    det = rv.TileDetector(conf=0.25)
    rows: list[dict] = []
    seen: dict[str, list[tuple]] = defaultdict(list)
    used = 0
    for p in photos:
        im = Image.open(p).convert("RGB")
        if im.width < 3000:
            print("건너뜀(저해상도)", p.parent.name, im.size, flush=True)
            continue
        used += 1
        rgb = np.asarray(im)
        day = p.parent.name[:8]
        bs = boxes(det, rgb)
        here = []
        for b in bs:
            crop = cut(rgb, b)
            pred, conf, k = label(net, crop, b[2], b[3])
            dup = any(pred == q and iou(b, c) > 0.5 for c, q in seen[day])
            i = len(rows)
            f = f"{i:05d}.jpg"
            crop.rotate(90 * k, expand=True).save(CROPS / f, quality=92)
            rows.append(dict(id=i, file=f, photo=p.parent.name, day=day, box=list(b), pred=pred, conf=round(conf, 3), turn=k, dup=dup))
            here.append((b, pred))
        seen[day] += here
        print(p.parent.name, im.size, "상자", len(bs), "새 패", sum(not r["dup"] for r in rows if r["photo"] == p.parent.name), round(time.perf_counter() - t0), "초", flush=True)
        (OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    sheets(rows)
    new = [r for r in rows if not r["dup"]]
    print("사진", used, "상자", len(rows), "dup 뺀 패", len(new), "unsure", sum(r["conf"] < UNSURE for r in new))
    print("날짜별", Counter(r["day"] for r in new))
    print("종류별", dict(sorted(Counter(r["pred"] for r in new if r["conf"] >= UNSURE).items())))
    print("총", round(time.perf_counter() - t0), "초")


# ---------------------------------------------------------------- 7-1: 회전 상자로 세워 자른 크롭(2026-11-06)
OBB_OUT = DATA / "harvest_obb"
OBB_IOU = 0.5  # 기존 라벨 상자 ↔ 전수 조사 상자(축) IoU 이 이상이면 같은 패


def _unrotate(b, side: str, cw: int, ch: int) -> tuple[float, float, float, float]:
    """seat_grow.crop 이 돌린 자리 크롭(rotate(-ROT_CW[side], expand)) 의 상자 → 돌리기 전 크롭 좌표. cw·ch = 돌리기 전 크기."""
    x, y, w, h = b
    r = {"bottom": 0, "right": 90, "top": 180, "left": 270}[side]
    if r == 0:
        return x, y, w, h
    if r == 90:  # 시계 90: x' = ch - y, y' = x
        return y, ch - (x + w), h, w
    if r == 180:
        return cw - (x + w), ch - (y + h), w, h
    return cw - (y + h), x, h, w  # 시계 270(= 반시계 90): x' = y, y' = cw - x


def obb_labels() -> list[dict]:
    """기존 라벨 전부를 원본 사진 좌표 상자로: data/index.json(자리 크롭 좌표) + review.extra(harvest 원본 좌표, 돌린 방향 turn) + 白(blank).
    turn = 원본 방향 크롭에 PIL rotate(turn, expand) 하면 예전 학습 크롭과 같은 방향."""
    import review as rw

    sys.path.insert(0, str(ROOT / "experiments" / "speed"))
    import seat_grow as sg

    out = []
    for x in json.loads((DATA / "index.json").read_text(encoding="utf-8")):
        W, H = x["photo"]
        y0, x0, y1, x1 = x["seat_box"]
        X0, Y0, X1, Y1 = round(x0 * W / 1000), round(y0 * H / 1000), round(x1 * W / 1000), round(y1 * H / 1000)
        bx, by, bw, bh = _unrotate(x["box"], x["side"], X1 - X0, Y1 - Y0)
        out.append(dict(src="base", ref=x["file"], photo=x["scene"], box=[X0 + bx, Y0 + by, bw, bh], tile=x["tile"], part=x["part"],
                        turn=-sg.ROT_CW[x["side"]], kind=x["kind"]))
    hv = {r["file"]: r for r in json.loads((OUT / "index.json").read_text(encoding="utf-8"))}
    bl = {r["file"]: r for r in json.loads((OUT / "blank/index.json").read_text(encoding="utf-8"))}
    for x in rw.extra():
        if x["file"].startswith("h_"):
            r = hv[x["file"][2:]]
            out.append(dict(src="extra", ref=x["file"], photo=x["photo"], box=r["box"], tile=x["tile"], part=x["half"], turn=90 * r["turn"], kind="any"))
        else:
            r = bl[x["file"][2:]]
            out.append(dict(src="blank", ref=x["file"], photo=x["photo"], box=r["box"], tile=x["tile"], part=x["half"], turn=None, kind="any"))
    return out


def main_obb() -> None:
    """7회차 전수 조사 회전 상자(data/det/obb/rects.json, audit/fixes.json 반영됨)를 서버 app/obb.upright(같은 PAD)로 세워 자른다 — 학습 = 추론.
    라벨은 기존 라벨 상자와 IoU 로 옮긴다(못 옮긴 라벨은 버리고 센다). 한 상자에 라벨이 둘 이상이면(base·extra 가 같은 패) 하나로, 종류가 다르면 base 를 쓰고 기록.
      python -I -X utf8 experiments/tile_classifier/harvest.py --obb
    결과 data/harvest_obb/{crops/*.jpg, index.json, report.json, sheet_<종류>_<n>.jpg, sample50.jpg}"""
    import random

    from app import local_read as lr
    from app import obb

    sys.stdout.reconfigure(encoding="utf-8")
    crops = OBB_OUT / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    rects = json.loads((DATA / "det/obb/rects.json").read_text(encoding="utf-8"))
    labels = obb_labels()
    by_photo = defaultdict(list)
    for x in labels:
        by_photo[x["photo"]].append(x)
    rows, lost, conflicts, ious = [], Counter(), [], []
    for name, v in rects.items():
        rgb = np.asarray(Image.open(v["path"]).convert("RGB"))
        faces = [it for it in v["items"] if it["cls"] == 0]
        got: dict[int, list] = defaultdict(list)
        for x in by_photo.get(name, []):
            best = max(range(len(faces)), key=lambda i: iou(faces[i]["box"], x["box"]), default=None)
            q = iou(faces[best]["box"], x["box"]) if best is not None else 0.0
            if q < OBB_IOU:
                lost[x["src"]] += 1
                continue
            ious.append(q)
            got[best].append(x)
        for i, xs in sorted(got.items()):
            xs.sort(key=lambda x: {"base": 0, "extra": 1, "blank": 2}[x["src"]])
            x = xs[0]
            if len({y["tile"] for y in xs}) > 1:
                conflicts.append(dict(photo=name, box=faces[i]["box"], labels=[(y["src"], y["ref"], y["tile"]) for y in xs]))
            it = faces[i]
            (cx, cy), (w, h), a = it["rect"]
            im = obb.upright(rgb, ((cx, cy), (w, h), a), lr.PAD)
            turn = x["turn"]
            if turn is None:  # 白: 세로로
                turn = 90 if im.width > 1.15 * im.height else 0
            if turn % 360:
                im = im.rotate(turn, expand=True)
            f = f"{len(rows):05d}.jpg"
            im.save(crops / f, quality=95)
            rows.append(dict(id=len(rows), file=f, photo=name, tile=x["tile"], part=x["part"], src=x["src"], ref=x["ref"], kind=x["kind"],
                             key=it["key"], status=it["status"], angle=round(float(it["angle"]), 1), n_labels=len(xs), turn=turn))
        print(name, "앞면 상자", len(faces), "라벨", len(by_photo.get(name, [])), "옮김", len(got), flush=True)
    for name in set(by_photo) - set(rects):
        lost["사진 없음 " + by_photo[name][0]["part"]] += len(by_photo[name])
    rep = dict(labels=len(labels), labels_by_src=dict(Counter(x["src"] for x in labels)), crops=len(rows), by_part=dict(Counter(r["part"] for r in rows)),
               by_src=dict(Counter(r["src"] for r in rows)), lost=dict(lost), conflicts=conflicts, iou_min=round(min(ious), 3) if ious else None,
               iou_median=round(statistics.median(ious), 3) if ious else None, merged=sum(r["n_labels"] - 1 for r in rows),
               tiles=dict(sorted(Counter(r["tile"] for r in rows).items())), not_axis=sum(r["status"] != "axis" for r in rows))
    (OBB_OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (OBB_OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "conflicts"}, ensure_ascii=False))
    print("종류 다름", len(conflicts), conflicts[:20])
    obb_sheets(rows, crops)
    random.seed(20261106)
    sample_sheet(random.sample(rows, 50), crops, OBB_OUT / "sample50.jpg")


def obb_sheets(rows: list[dict], crops: Path, cell: int = 76, cols: int = 16, lines: int = 9) -> None:
    groups = defaultdict(list)
    for r in rows:
        groups[r["tile"]].append(r)
    for g, v in groups.items():
        for k in range(0, len(v), cols * lines):
            part = v[k:k + cols * lines]
            im = Image.new("RGB", (cols * cell, (len(part) // cols + 1) * (cell + 14)), "white")
            d = ImageDraw.Draw(im)
            for i, r in enumerate(part):
                t = Image.open(crops / r["file"])
                t.thumbnail((cell, cell))
                x, y = (i % cols) * cell, (i // cols) * (cell + 14)
                im.paste(t, (x, y))
                d.text((x + 1, y + cell), str(r["id"]), fill="blue")
            im.save(OBB_OUT / f"sheet_{g}_{k // (cols * lines)}.jpg", quality=88)


def sample_sheet(rows: list[dict], crops: Path, dst: Path, cell: int = 150, cols: int = 10) -> None:
    im = Image.new("RGB", (cols * cell, (len(rows) + cols - 1) // cols * (cell + 26)), "white")
    d = ImageDraw.Draw(im)
    for i, r in enumerate(rows):
        t = Image.open(crops / r["file"])
        t.thumbnail((cell, cell))
        x, y = (i % cols) * cell, (i // cols) * (cell + 26)
        im.paste(t, (x, y))
        d.text((x + 2, y + cell + 2), f"{i} #{r['id']} {r['tile']}", fill="red")
    im.save(dst, quality=90)


if __name__ == "__main__":
    main_obb() if "--obb" in sys.argv else main()
