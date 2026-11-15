"""11-14 자료 화질 사본(2026-11-15, 1단계 B). v1114_collect.py 다음에.

고른 2992 그림(manifest selected) → data/v1114/images/{q2992,q1496,q997}/<split>/<판 id>/<name>
  q2992 = 원본 바이트 그대로 복사
  q1496 = 헤드 녹화 흉내: HeadCamera.average2x2(밝기 2×2 평균, 색차 쌍 2×2 평균) → JPEG 85
  q997  = 헤드 미리보기 흉내: HeadCamera.subsample(step 3, 가로·세로 짝수 내림 → 996×996) → JPEG 75(head_camera.dart jpeg 기본)
  두 사본 모두 paifu_frames/frame_split.head_small(NV21 흉내, 11-11 에 쓴 것) 그대로.
실제 1496·996 프레임(manifest native) → data/v1114/native/{q1496,q997}/<split>/<판 id>/<name>(바이트 그대로)
사본 vs native 분포 비교(같은 순간 짝 없음): 밝기 Laplacian 분산·평균 기울기·JPEG 바이트/화소·밝기 평균, 가운데 60% 영역.
  python -X utf8 experiments/tile_classifier/v1114_quality.py [--stats-only]
결과 data/v1114/quality_stats.json
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "paifu_frames"))
from frame_split import head_small  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v1114_split import image_rel, native_rel  # noqa: E402  (나눔 고친 뒤 폴더 — 3단계)

CAP = ROOT / "experiments" / "visit_20261114" / "captures"
OUT = HERE / "data" / "v1114"


def src_bytes(it: dict) -> bytes:
    if it["kind"] == "frame":
        with zipfile.ZipFile(CAP / it["src_dir"] / it["zip"]) as zf:
            return zf.read(it["file"])
    return (CAP / it["src_dir"] / it["file"]).read_bytes()


def make_q1496(rgb: np.ndarray) -> np.ndarray:
    return head_small(rgb, 2, "avg", 85)


def make_q997(rgb: np.ndarray) -> np.ndarray:
    return head_small(rgb, 3, "skip", 75)


def jpeg_bytes(rgb: np.ndarray, q: int) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "JPEG", quality=q)
    return buf.getvalue()


def stats(data: bytes) -> dict:
    im = Image.open(io.BytesIO(data))
    y = np.asarray(im.convert("L"), np.float32)
    H, W = y.shape
    c = y[int(H * 0.2):int(H * 0.8), int(W * 0.2):int(W * 0.8)]
    lap = c[1:-1, 2:] + c[1:-1, :-2] + c[2:, 1:-1] + c[:-2, 1:-1] - 4 * c[1:-1, 1:-1]
    gx, gy = np.abs(np.diff(c, axis=1)).mean(), np.abs(np.diff(c, axis=0)).mean()
    return {"lap_var": float(lap.var()), "grad": float((gx + gy) / 2), "bpp": len(data) * 8 / (W * H), "mean": float(c.mean()), "size": [W, H]}


def summ(v: list[float]) -> dict:
    a = np.asarray(v)
    return {"n": len(a), "p10": round(float(np.percentile(a, 10)), 3), "median": round(float(np.median(a)), 3), "p90": round(float(np.percentile(a, 90)), 3)} if len(a) else {"n": 0}


def main():
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    only_stats = "--stats-only" in sys.argv
    rows = {"copy": {"q1496": [], "q997": [], "q2992": []}, "native": {"q1496": [], "q997": []}}
    for it in man["items"]:
        if it["selected"]:
            data = src_bytes(it)
            outs = {q: OUT / image_rel(it, q) for q in ("q2992", "q1496", "q997")}  # v1114_split.py 뒤면 옮긴 자리
            if only_stats and all(p.exists() for p in outs.values()):
                byq = {q: p.read_bytes() for q, p in outs.items()}
            else:
                rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
                byq = {"q2992": data, "q1496": jpeg_bytes(make_q1496(rgb), 85), "q997": jpeg_bytes(make_q997(rgb), 75)}
                for q, p in outs.items():
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(byq[q])
            for q, b in byq.items():
                rows["copy"][q].append({"id": it["id"], "round": it["round"], "kind": it["kind"], **stats(b)})
            print("사본", it["id"], flush=True)
        elif it["native"]:
            data = src_bytes(it)
            p = OUT / native_rel(it)
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_bytes(data)
            rows["native"][it["native"]].append({"id": it["id"], "round": it["round"], "kind": it["kind"], **stats(data)})
    res = {"note": "가운데 60% 영역, 밝기(L). lap_var = 4이웃 Laplacian 분산, grad = 이웃 화소 차 절댓값 평균, bpp = JPEG 비트/화소. 같은 순간 짝 없음 — 분포 비교만.",
           "summary": {}, "rows": rows}
    for grp in ("copy", "native"):
        for q, v in rows[grp].items():
            res["summary"][f"{grp}/{q}"] = {k: summ([r[k] for r in v]) for k in ("lap_var", "grad", "bpp", "mean")}
    # 같은 판에 native 가 있는 경우만 따로(판 차이 줄이기)
    for q in ("q1496", "q997"):
        nr = {r["round"] for r in rows["native"][q] if r["kind"] == "frame"}
        c = [r for r in rows["copy"][q] if r["round"] in nr and r["kind"] == "frame"]
        n = [r for r in rows["native"][q] if r["kind"] == "frame"]
        res["summary"][f"same_rounds/{q}"] = {"rounds": sorted(nr), "copy": {k: summ([r[k] for r in c]) for k in ("lap_var", "grad", "bpp")},
                                             "native": {k: summ([r[k] for r in n]) for k in ("lap_var", "grad", "bpp")}}
    (OUT / "quality_stats.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
