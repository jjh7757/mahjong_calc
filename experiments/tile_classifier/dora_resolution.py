"""해상도별 패산 표시패 읽기(2026-11-03, API 없음). metrics 표 1-53.
리치 아닌 화료 원본(표시패가 패산에 그대로, truth.json)을 긴 변 4080·2040·1360·1020 으로 줄여 read_wall(작은 패는 read_small)로 읽는다.
판 중 미리보기를 어느 크기로 받아야 종류를 믿을 수 있는지 정하기 위해.
  python -I -X utf8 experiments/tile_classifier/dora_resolution.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wall_frames as wf  # noqa: E402
from app import local_read as lr  # noqa: E402

TRUTH = json.loads((wf.ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
SIZES = [4080, 2040, 1360, 1020]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    readers = {"a": lr.LocalReader(det_model=wf.MODELS / "det_fold_a.onnx", cls_model=wf.MODELS / "cls_pm.onnx"),
               "b": lr.LocalReader(det_model=wf.MODELS / "det_fold_b.onnx", cls_model=wf.MODELS / "cls_am.onnx")}
    score = {s: [0, 0, 0] for s in SIZES}  # 맞음, 틀림, 없음
    for name, t in sorted(TRUTH.items()):
        if t["riichi"] or name[-6:] in ("172424", "174020"):
            continue
        im = Image.open(wf.CAPS / name / "original.jpg").convert("RGB")
        rd = readers["b" if name[9:11] < "14" else "a"]
        row = []
        for s in SIZES:
            r = im if s >= max(im.size) else im.resize((round(im.width * s / max(im.size)), round(im.height * s / max(im.size))), Image.LANCZOS)
            buf = io.BytesIO()
            r.save(buf, "JPEG", quality=90)
            o = rd.read_wall(buf.getvalue())
            got = o["indicators"][0]["tile"] if o["indicators"] else None
            k = 0 if got in t["indicators"] else (2 if got is None else 1)
            score[s][k] += 1
            row.append(f"{s}:{got}({o['conf']:.2f},{o['box'] and round(min(o['box'][2:]))}px)")
        print(name[-6:], "정답", t["indicators"], *row, flush=True)
    print({s: dict(zip(["맞음", "틀림", "없음"], v)) for s, v in score.items()})


if __name__ == "__main__":
    main()
