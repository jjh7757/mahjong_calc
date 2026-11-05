"""앞면·뒷면 2종 1차 검출로 2차 라벨 후보를 만든다(2026-11-03, 노트북 CPU, API 없음). det_build_fb.py·캐글 1차(kaggle_out_fb) 다음에.

사진마다 그 사진을 학습하지 않은 모델: 오전 = fold_am, 오후 = fold_pm, k = fold_k(final 은 지금 라벨을 외워 쓰지 않는다, label_review2.md).
통째 + 토막 9장을 검출해 종류별로 겹친 상자는 확신 높은 것 하나만, 앞면·뒷면이 겹치면 확신 높은 쪽만 남긴다.
1차 라벨(boxes_final_fb.json)과 IoU 0.5 로 짝을 지어
  같음 = 짝이 있음(뒷면은 검출 상자로 바꾼다. 색 초안의 나눔 어긋남을 모델이 고르게 잡는지 눈으로 본다)
  검출만 = 라벨에 없는 상자, 라벨만 = 검출이 못 찾은 라벨. 둘은 눈 검수 대상(review_r2fb.json 으로 결정).
  python -I experiments/tile_classifier/det_relabel_fb.py
결과 data/det/backs/r2/cands.json, r2/check/<이름>.jpg(빨강 같음·하늘 검출만·보라 라벨만, 앞면은 초록·노랑), r2/crops_<번>.jpg(불일치 확대, 번호 = cands 의 id)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import det_build as db  # noqa: E402
from det_relabel import merge  # noqa: E402

DET = HERE / "data" / "det"
MODELS = DET / "kaggle_out_fb" / "out"
OUT = DET / "backs" / "r2"
CONF = 0.25


def part(name: str) -> str:
    return "k" if name.startswith("k") else "am" if name < "20261031_14" else "pm"


def detect(model: YOLO, im: Image.Image) -> dict[int, list[tuple]]:
    W, H = im.size
    out: dict[int, list[tuple]] = {0: [], 1: []}

    def add(r, x0: int, y0: int, tile: bool) -> None:
        for (a, b, c, d), s, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            if tile and ((a < 3 and x0 > 0) or (b < 3 and y0 > 0) or (c > db.TW - 3 and x0 + db.TW < W) or (d > db.TH - 3 and y0 + db.TH < H)):
                continue  # 토막 끝에 닿은 상자는 잘린 패일 수 있다
            out[int(k)].append((a + x0, b + y0, c + x0, d + y0, s))

    add(model.predict(im, imgsz=1280, conf=CONF, verbose=False, device="cpu")[0], 0, 0, False)
    for y0 in (0, (H - db.TH) // 2, H - db.TH):
        for x0 in (0, (W - db.TW) // 2, W - db.TW):
            add(model.predict(im.crop((x0, y0, x0 + db.TW, y0 + db.TH)), imgsz=1280, conf=CONF, verbose=False, device="cpu")[0], x0, y0, True)
    faces, backs = merge(out[0]), merge(out[1])
    # 같은 자리에 앞면·뒷면이 겹치면 확신 높은 쪽
    both = sorted([(b, 0) for b in faces] + [(b, 1) for b in backs], key=lambda t: -t[0][4])
    keep: list[tuple] = []
    for b, k in both:
        area = (b[2] - b[0]) * (b[3] - b[1])
        if not any(inter(b, q) > 0.5 * min(area, (q[2] - q[0]) * (q[3] - q[1])) for q, _ in keep):
            keep.append((b, k))
    return {0: [b for b, k in keep if k == 0], 1: [b for b, k in keep if k == 1]}


def inter(a, b) -> float:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def iou(a, b) -> float:
    i = inter(a, b)
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def pair(labels: list, dets: list) -> tuple[list, list, list]:
    """IoU 높은 순으로 하나씩 짝. (짝[(라벨, 검출, iou)], 검출만, 라벨만)"""
    L = [(x, y, x + w, y + h) for x, y, w, h in labels]
    cand = sorted(((iou(l, d), i, j) for i, l in enumerate(L) for j, d in enumerate(dets)), reverse=True)
    ul, ud, pairs = set(), set(), []
    for v, i, j in cand:
        if v < 0.5:
            break
        if i in ul or j in ud:
            continue
        ul.add(i)
        ud.add(j)
        pairs.append((labels[i], dets[j], v))
    return pairs, [d for j, d in enumerate(dets) if j not in ud], [labels[i] for i in range(len(L)) if i not in ul]


def xywh(b) -> list[int]:
    return [round(b[0]), round(b[1]), round(b[2] - b[0]), round(b[3] - b[1])]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    (OUT / "check").mkdir(parents=True, exist_ok=True)
    first = json.loads((DET / "backs" / "boxes_final_fb.json").read_text(encoding="utf-8"))
    paths = {n: r["path"] for n, r in json.loads((DET / "boxes_final.json").read_text(encoding="utf-8")).items()}
    models = {p: YOLO(str(MODELS / f"fold_{p}.pt")) for p in ("am", "pm", "k")}
    cands, crops, nid = {}, [], 0
    tot = dict(fs=0, fo=0, lo_f=0, bs=0, bo=0, lo_b=0)
    for name, r in first.items():
        im = Image.open(paths[name]).convert("RGB")
        det = detect(models[part(name)], im)
        fp, fo, flo = pair(r["faces"], det[0])
        bp, bo, blo = pair(r["backs"], det[1])
        items = []
        for kind, boxes, cls in (("검출만", fo, "face"), ("검출만", bo, "back")):
            for b in boxes:
                items.append(dict(id=nid, cls=cls, kind=kind, box=xywh(b), conf=round(b[4], 3)))
                nid += 1
        for kind, boxes, cls in (("라벨만", flo, "face"), ("라벨만", blo, "back")):
            for b in boxes:
                items.append(dict(id=nid, cls=cls, kind=kind, box=list(b)))
                nid += 1
        cands[name] = dict(faces=[list(l) for l, _, _ in fp], backs_draft=[list(l) for l, _, _ in bp], backs_det=[xywh(d) for _, d, _ in bp],
                           back_iou=[round(v, 3) for _, _, v in bp], items=items)
        for k, v in (("fs", len(fp)), ("fo", len(fo)), ("lo_f", len(flo)), ("bs", len(bp)), ("bo", len(bo)), ("lo_b", len(blo))):
            tot[k] += v
        v = im.copy()
        d = ImageDraw.Draw(v)
        for l, _, _ in fp:
            d.rectangle((l[0], l[1], l[0] + l[2], l[1] + l[3]), outline=(0, 220, 0), width=3)
        for _, q, _ in bp:
            d.rectangle(q[:4], outline=(255, 40, 40), width=3)
        for it in items:
            x, y, w, h = it["box"]
            col = {("face", "검출만"): (255, 230, 0), ("back", "검출만"): (0, 220, 255), ("face", "라벨만"): (255, 140, 0), ("back", "라벨만"): (220, 0, 255)}[(it["cls"], it["kind"])]
            d.rectangle((x, y, x + w, y + h), outline=col, width=5)
            d.text((x + 4, y + 2), str(it["id"]), fill=col)
            pad = 70
            c = im.crop((max(0, x - pad), max(0, y - pad), x + w + pad, y + h + pad))
            dc = ImageDraw.Draw(c)
            ox, oy = max(0, x - pad), max(0, y - pad)
            for l, _, _ in fp:
                dc.rectangle((l[0] - ox, l[1] - oy, l[0] + l[2] - ox, l[1] + l[3] - oy), outline=(0, 220, 0), width=2)
            for _, q, _ in bp:
                dc.rectangle((q[0] - ox, q[1] - oy, q[2] - ox, q[3] - oy), outline=(255, 40, 40), width=2)
            dc.rectangle((x - ox, y - oy, x + w - ox, y + h - oy), outline=col, width=4)
            c.thumbnail((300, 300))
            canvas = Image.new("RGB", (300, 320), (20, 20, 20))
            canvas.paste(c, (0, 20))
            ImageDraw.Draw(canvas).text((4, 2), f"{it['id']} {name[-6:]} {it['cls']} {it['kind']} {it.get('conf', '')}", fill=(255, 255, 255))
            crops.append(canvas)
        v.thumbnail((2040, 2040))
        v.save(OUT / "check" / f"{name}.jpg", quality=85)
        print(name, "앞면 같음", len(fp), "검출만", len(fo), "라벨만", len(flo), "| 뒷면 같음", len(bp), "검출만", len(bo), "라벨만", len(blo), flush=True)
    for s in range(0, len(crops), 30):
        sheet = Image.new("RGB", (6 * 300, 5 * 320), (0, 0, 0))
        for i, c in enumerate(crops[s:s + 30]):
            sheet.paste(c, ((i % 6) * 300, (i // 6) * 320))
        sheet.save(OUT / f"crops_{s // 30:02d}.jpg", quality=85)
    (OUT / "cands.json").write_text(json.dumps(cands, ensure_ascii=False), encoding="utf-8")
    print("합계", tot, "불일치", nid, "그림", (len(crops) + 29) // 30)


if __name__ == "__main__":
    main()
