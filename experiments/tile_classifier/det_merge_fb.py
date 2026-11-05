"""2차 라벨 후보를 정리한다(2026-11-03, API 없음). det_relabel_fb.py 다음에.

뒷면 불일치 눈 검수 결과(crops_00 등): 라벨만 있는 상자가 검출 상자와 겹치면 색 초안이 반 장씩 밀린 것이고 검출이 패 묶음에 맞았다(나눔 밖 모델이라 라벨을 외운 값이 아니다).
그래서 뒷면은 겹치는 불일치를 검출 쪽으로 정하고, 반대편과 겹침이 없는 외톨이만 눈으로 본다. 앞면 불일치는 전부 본다.
  규칙: 뒷면 = 짝의 검출 상자 + 검출만(라벨과 겹침 IoU ≥ 0.1 이면 받음, 외톨이는 검수) + 라벨만 중 외톨이(검수).
  검수 결정은 review_r2fb.json: {"keep": [id...], "drop": [id...]} — keep 은 외톨이·앞면 불일치 중 받을 것, 나머지 외톨이·앞면 불일치는 버린다.
  python -I experiments/tile_classifier/det_merge_fb.py           외톨이 그림 r2/lone_<번>.jpg 와 목록
  python -I experiments/tile_classifier/det_merge_fb.py --apply   review_r2fb.json 반영해 r2/boxes_r2fb.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
DET = HERE / "data" / "det"
R2 = DET / "backs" / "r2"


def xyxy(b):
    return (b[0], b[1], b[0] + b[2], b[1] + b[3])


def iou(a, b) -> float:
    a, b = xyxy(a), xyxy(b)
    i = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def classify(c: dict) -> tuple[list, list, list]:
    """(자동으로 받을 뒷면 상자, 검수할 항목, 버릴 라벨만 상자)"""
    dets = c["backs_det"] + [it["box"] for it in c["items"] if it["cls"] == "back" and it["kind"] == "검출만"]
    labels = c["backs_draft"] + [it["box"] for it in c["items"] if it["cls"] == "back" and it["kind"] == "라벨만"]
    auto, review, dropped = list(c["backs_det"]), [], []
    for it in c["items"]:
        if it["cls"] == "face":
            review.append(it)
            continue
        other = labels if it["kind"] == "검출만" else dets
        lone = max((iou(it["box"], o) for o in other), default=0) < 0.1
        if lone:
            review.append(it)
        elif it["kind"] == "검출만":
            auto.append(it["box"])
        else:
            dropped.append(it["box"])
    return auto, review, dropped


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cands = json.loads((R2 / "cands.json").read_text(encoding="utf-8"))
    paths = {n: r["path"] for n, r in json.loads((DET / "boxes_final.json").read_text(encoding="utf-8")).items()}
    if "--apply" in sys.argv:
        rv = json.loads((R2 / "review_r2fb.json").read_text(encoding="utf-8"))
        keep = set(rv["keep"])
        out, n = {}, dict(back_auto=0, back_keep=0, back_dropped=0)
        for name, c in cands.items():
            auto, review, dropped = classify(c)
            faces = list(c["faces"])
            backs = list(auto)
            for it in review:  # 검출만이면 더하고, 라벨만이면 라벨을 남긴다
                if it["id"] in keep:
                    (faces if it["cls"] == "face" else backs).append(it["box"])
            n["back_auto"] += len(auto)
            n["back_keep"] += sum(it["id"] in keep for it in review if it["cls"] == "back")
            n["back_dropped"] += len(dropped)
            out[name] = dict(faces=faces, backs=backs)
        (R2 / "boxes_r2fb.json").write_text(json.dumps(out), encoding="utf-8")
        print("앞면", sum(len(v["faces"]) for v in out.values()), "뒷면", sum(len(v["backs"]) for v in out.values()), n)
        return
    crops, listing = [], []
    for name, c in cands.items():
        auto, review, dropped = classify(c)
        if not review:
            continue
        im = Image.open(paths[name]).convert("RGB")
        for it in review:
            x, y, w, h = it["box"]
            pad = 90
            ox, oy = max(0, x - pad), max(0, y - pad)
            cr = im.crop((ox, oy, x + w + pad, y + h + pad))
            d = ImageDraw.Draw(cr)
            for f in c["faces"]:
                d.rectangle((f[0] - ox, f[1] - oy, f[0] + f[2] - ox, f[1] + f[3] - oy), outline=(0, 220, 0), width=2)
            for b in auto:
                d.rectangle((b[0] - ox, b[1] - oy, b[0] + b[2] - ox, b[1] + b[3] - oy), outline=(255, 40, 40), width=2)
            col = (0, 220, 255) if it["kind"] == "검출만" else (220, 0, 255)
            d.rectangle((x - ox, y - oy, x + w - ox, y + h - oy), outline=col, width=5)
            cr.thumbnail((320, 320))
            cv = Image.new("RGB", (320, 340), (20, 20, 20))
            cv.paste(cr, (0, 20))
            ImageDraw.Draw(cv).text((4, 2), f"{it['id']} {name[-6:]} {it['cls']} {'det' if it['kind'] == '검출만' else 'lab'} {it.get('conf', '')}", fill=(255, 255, 255))
            crops.append(cv)
            listing.append((it["id"], name, it["cls"], it["kind"], it.get("conf")))
    for s in range(0, len(crops), 24):
        sh = Image.new("RGB", (6 * 320, 4 * 340), (0, 0, 0))
        for i, c in enumerate(crops[s:s + 24]):
            sh.paste(c, ((i % 6) * 320, (i // 6) * 340))
        sh.save(R2 / f"lone_{s // 24:02d}.jpg", quality=85)
    tot = [classify(c) for c in cands.values()]
    print("뒷면 자동", sum(len(a) for a, _, _ in tot), "버림(밀린 라벨)", sum(len(d) for _, _, d in tot), "검수", len(listing), "그림", (len(crops) + 23) // 24)
    for row in listing:
        print(*row)


if __name__ == "__main__":
    main()
