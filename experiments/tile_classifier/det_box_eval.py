"""자리 판독 검출기(회전 상자, 운영 tile-obb-r8)만 따로 잰다 — 사람이 전수 조사한 상자(data/det/obb/rects.json)와 맞춰
앞면 재현율·헛검출을 원본과 회귀 변형(experiments/speed/robust)에서(2026-11-10, 사용자 "검출기 성능도 테스트해봐", 노트북, API 없음).

세트: 테스트 세트(seat_grow.eval_scenes) 중 정답 상자가 있는 B·C·D + 10-31(11-07 은 상자 정답 없음). 가림·사용자 문제 사진은 뺀다.
모델: fold = 그 사진을 안 배운 검출기(server_bench/meta.json 의 det 나눔 → det_r8_fold_a|b), prod = 서버 assets(운영).
검출: 서버와 같은 LocalReader._seat_raw(사진 전체, 서버의 가는 조각 버리기 obb.slivers 포함) → 앞면 상자.
맞추기: 예측 앞면 상자의 중심이 정답 회전 상자 안(변형 좌표로 옮긴 것)이면 후보, 정답 하나에 예측 하나(가까운 순).
  재현 = 맞은 정답 앞면 / 정답 앞면. 헛검출 = 어느 정답(앞면·뒷면)에도 안 든 예측. 뒷면 혼동 = 정답 뒷면 안에 든 앞면 예측.
변형 좌표: rot 는 robust_suite.rotate 와 같은 행렬, scale 은 크기 비, 나머지는 그대로(가림 hand 는 가려진 패도 정답에 남는다).
  python -I -X utf8 experiments/tile_classifier/det_box_eval.py [--models fold,prod] [--only orig,blur2]   → data/det/box_eval_<models>.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "speed"))
REPO = Path(os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
sys.path.insert(0, str(REPO))
import robust_suite as rs  # noqa: E402
import seat_grow as sg  # noqa: E402
from app import local_read as lr  # noqa: E402

RECTS = HERE / "data" / "det" / "obb" / "rects.json"
SB = HERE / "server_bench"


def load_rgb(p: Path) -> np.ndarray:
    return np.asarray(ImageOps.exif_transpose(Image.open(p)).convert("RGB"))


def gt_polys(items: list, M: np.ndarray | None, k: float) -> list[tuple[int, np.ndarray]]:
    """정답 회전 상자 → (종류 0 앞면·1 뒷면, 변형 좌표 꼭짓점 4×2)."""
    out = []
    for it in items:
        (cx, cy), (w, h), a = it["rect"]
        pts = cv2.boxPoints(((cx, cy), (w, h), a)).astype(np.float64)
        if M is not None:
            pts = np.c_[pts, np.ones(4)] @ M.T
        out.append((it["cls"], (pts * k).astype(np.float32)))
    return out


def match(preds: list, gts: list) -> dict:
    """preds = 축 상자(x, y, w, h). 중심이 정답 다각형 안이면 후보 — 정답마다 가장 가까운 예측 하나."""
    centers = [(x + w / 2, y + h / 2) for x, y, w, h in preds]
    used, hit = set(), 0
    fronts = [g for g in gts if g[0] == 0]
    for _, poly in fronts:
        c0 = poly.mean(0)
        best, bd = None, 1e18
        for i, (px, py) in enumerate(centers):
            if i in used or cv2.pointPolygonTest(poly, (px, py), False) < 0:
                continue
            d = (px - c0[0]) ** 2 + (py - c0[1]) ** 2
            if d < bd:
                best, bd = i, d
        if best is not None:
            used.add(best)
            hit += 1
    back, false = 0, 0
    for i, (px, py) in enumerate(centers):
        if i in used:
            continue
        inside = [c for c, poly in gts if cv2.pointPolygonTest(poly, (px, py), False) >= 0]
        if 1 in inside:
            back += 1
        elif not inside:
            false += 1
        # 앞면 정답 안인데 짝이 이미 있음 = 같은 패 두 번(중복)
    dup = len(preds) - hit - back - false
    return {"want": len(fronts), "hit": hit, "pred": len(preds), "false": false, "back": back, "dup": dup}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="fold,prod")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    rects = json.loads(RECTS.read_text(encoding="utf-8"))
    scenes = [s for s in sg.eval_scenes() if s["name"] in rects]
    meta = json.loads((rs.RB / "meta.json").read_text(encoding="utf-8"))
    sbm = {p["name"]: p for p in json.loads((SB / "meta.json").read_text(encoding="utf-8"))["photos"]}
    variants = [v for v in rs.FIXED if not a.only or v in a.only.split(",")]
    readers: dict = {}

    def reader(models: str, name: str) -> lr.LocalReader:
        path = lr.SEAT_MODEL if models == "prod" else rs.MODELS / f"det_r8_fold_{sbm[name]['det']}.onnx"
        if path not in readers:
            readers[path] = lr.LocalReader(threads=2, seat_model=path)
            readers[path]._sessions()  # 모델 올리기(_seat_raw 는 안 올림)
        return readers[path]

    out: dict = {"_meta": {"scenes": len(scenes), "variants": variants, "seat_prod": lr.SEAT_MODEL.name, "started": time.strftime("%Y-%m-%d %H:%M:%S")}}
    for models in a.models.split(","):
        res = out.setdefault(models, {})
        for v in variants:
            tot = dict(want=0, hit=0, pred=0, false=0, back=0, dup=0)
            rows = {}
            for s in scenes:
                info = meta.get(v, {}).get(s["name"])
                if info is None:
                    continue
                src = Path(info["src"])
                rgb = load_rgb(src)
                kind, arg = rs.spec_of(v)
                M, k = None, 1.0
                if kind == "rot":
                    w, h = info["size"]
                    M = cv2.getRotationMatrix2D((w / 2, h / 2), -arg, 1.0)
                    c, sn = abs(M[0, 0]), abs(M[0, 1])
                    W, H = int(math.ceil(w * c + h * sn)), int(math.ceil(w * sn + h * c))
                    M[0, 2] += W / 2 - w / 2
                    M[1, 2] += H / 2 - h / 2
                elif kind == "scale":
                    k = rgb.shape[1] / info["size"][0]
                gts = gt_polys(rects[s["name"]]["items"], M, k)
                faces, _, _, _ = reader(models, s["name"])._seat_raw(rgb)
                r = match([b for b, _ in faces], gts)
                rows[s["name"]] = r
                for key in tot:
                    tot[key] += r[key]
            res[v] = {"total": tot, "rows": rows}
            print(f"{models:5s} {v:12s} 재현 {tot['hit']}/{tot['want']} ({100 * tot['hit'] / max(1, tot['want']):.2f}%) · 헛검출 {tot['false']} · 뒷면을 앞면으로 {tot['back']} · 중복 {tot['dup']}", flush=True)
    out["_meta"]["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    p = HERE / "data" / "det" / f"box_eval_{a.models.replace(',', '_')}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", p)


if __name__ == "__main__":
    main()
