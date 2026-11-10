"""11-06·11-07 매장 원본에서 5 계열(5m·5p·5s·0m·0p·0s) 크롭 모으기 — 적5 학습 재료(2026-11-10, 사용자 "실제 매장 사진에서 0p·0s·0m 충분히 학습되게").

상자: 운영 자리 판독 검출기(`tile-obb-r8.onnx`, 회전 상자 앞면)를 사진 통째(1280)로. 크롭: 서버 `obb.upright(PAD 0.12)` 로 세워 자르고,
긴 변이 가로면 90°·270°, 세로면 0°·180° 중 운영 분류기(v3 = cls6_all) 확신이 높은 방향으로 돌려 저장(학습 크롭은 패가 바로 선 모양).
고르기: 1순위나 2순위가 5 계열이거나, 빨강 비율(서버 signals.red_ratio)이 0.3 이상인 것. 라벨은 임시(예측) — 사람·독립 검토 뒤에만 학습에 쓴다.
겹침: 10-31 매장·10-24 삼각대(테스트 15장)·B·C·D 원본과 작게 줄인 흑백 차이 < 12 면 뺀다(갤러리 다시 읽기). 1020px 트랙 프레임은 안 씀(패 약 30px).
  python -I -X utf8 experiments/tile_classifier/red5_harvest.py
결과 data/red5/{crops/*.png, index.json, sheet_<예측>.jpg, dedup.json}(커밋 안 함)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = Path("C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.insert(0, str(REPO))
from app import local_read as lr  # noqa: E402
from app import obb, signals  # noqa: E402

OUT = HERE / "data" / "red5"
FIVES = {"5m", "5p", "5s", "0m", "0p", "0s"}
RED_MIN = 0.3


def thumb(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("L").resize((64, 48)), np.float32)


def main() -> None:
    (OUT / "crops").mkdir(parents=True, exist_ok=True)
    old = [p for p in (EXP / "visit_20261031/captures").glob("*/original.jpg")] + list((EXP / "field_20261024/captures").glob("*/original.jpg")) \
        + list((EXP / "field_20261024/kakao_photos").glob("*.jpg"))
    old_t = {str(p): thumb(p) for p in old}
    photos, dedup = [], {}
    for p in sorted((EXP / "visit_20261107/captures").glob("2026110[67]_*/original.jpg")):
        if Image.open(p).size[0] < 3000:
            continue
        t = thumb(p)
        best = min(old_t, key=lambda k: np.abs(old_t[k] - t).mean())
        d = float(np.abs(old_t[best] - t).mean())
        dedup[p.parent.name] = {"nearest": best, "diff": round(d, 1)}
        if d < 12:
            print("겹침 뺌", p.parent.name, "≈", best, round(d, 1), flush=True)
            continue
        photos.append(p)
    (OUT / "dedup.json").write_text(json.dumps(dedup, ensure_ascii=False, indent=1), encoding="utf-8")
    print("사진", len(photos), flush=True)
    reader = lr.LocalReader(threads=4)
    reader._sessions()
    print("검출", reader.seat_model.name, "· 분류", reader.cls_model.name, flush=True)
    rows = []
    for p in photos:
        rgb = np.asarray(Image.open(p).convert("RGB"))
        faces, _, _, _ = reader._seat_raw(rgb)
        n0 = len(rows)
        for b, rect in faces:
            if rect is None:
                continue
            im = obb.upright(rgb, rect, lr.PAD)
            ks = (90, 270) if im.width > 1.15 * im.height else (0, 180)
            cands = [im.rotate(k, expand=True) for k in ks]
            pr = reader.probs(cands)
            i = int(pr.max(1).argmax())
            q = pr[i]
            o = np.argsort(-q)
            t1, t2 = lr.CLASSES[o[0]], lr.CLASSES[o[1]]
            red = signals.red_ratio(cands[i])
            if not ({t1, t2} & FIVES or (red is not None and red >= RED_MIN)):
                continue
            name = f"{len(rows):05d}.png"
            cands[i].save(OUT / "crops" / name)
            rows.append(dict(id=len(rows), file=name, photo=p.parent.name, box=[int(v) for v in b], pred=t1, conf=round(float(q[o[0]]), 3),
                             alt=t2, conf2=round(float(q[o[1]]), 3), red=red, size=list(cands[i].size)))
        print(p.parent.name, len(faces), "앞면 →", len(rows) - n0, flush=True)
    (OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    sheets(rows)


def sheets(rows: list[dict], cell: int = 110, cols: int = 12) -> None:
    for t in sorted({r["pred"] for r in rows}):
        sel = [r for r in rows if r["pred"] == t]
        lines = (len(sel) + cols - 1) // cols
        sh = Image.new("RGB", (cols * (cell + 6), lines * (cell + 30)), "white")
        dr = ImageDraw.Draw(sh)
        for k, r in enumerate(sel):
            im = Image.open(OUT / "crops" / r["file"])
            im.thumbnail((cell, cell))
            y, x = divmod(k, cols)
            sh.paste(im, (x * (cell + 6), y * (cell + 30)))
            dr.text((x * (cell + 6), y * (cell + 30) + cell + 2), f"#{r['id']} {r['pred']} {r['conf']:.2f}", fill="black")
            dr.text((x * (cell + 6), y * (cell + 30) + cell + 15), f"{r['alt']} red {r['red']}", fill=(110, 110, 110))
        sh.save(OUT / f"sheet_{t}.jpg", quality=90)
        print("sheet", t, len(sel))


if __name__ == "__main__":
    main()
