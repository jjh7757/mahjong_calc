"""wall_frames.py 가 찾은 표시패 상자를 키워서 분류기로 읽어 본다(2026-11-02, API 없음). 표 1-34.
서버 분류기 입력(_tensor)은 작은 패를 키우지 않아 프레임의 패(약 30px)가 회색 바탕에 작게 들어간다.
  python -I -X utf8 experiments/tile_classifier/wall_frames_read.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wall_frames as wf  # noqa: E402
from app import local_read as lr  # noqa: E402


def read_up(rd: lr.LocalReader, rgb, b, size: int, pad: float = 0.0) -> tuple[str, float]:
    x, y, w, h = b
    p = round(pad * max(w, h))
    im = Image.fromarray(rgb[max(0, y - p):y + h + p, max(0, x - p):x + w + p])
    s = size / max(im.size)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.BICUBIC)
    ts = (0, 2) if h > 1.15 * w else (1, 3) if w > 1.15 * h else (0, 1, 2, 3)
    pr = rd.probs([im.rotate(90 * k, expand=True) for k in ts])
    i = int(pr.max(1).argmax())
    return lr.CLASSES[int(pr[i].argmax())], round(float(pr[i].max()), 3)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = wf.all_frames()
    res = json.loads((wf.OUT / "picked.json").read_text(encoding="utf-8"))
    readers = {"a": lr.LocalReader(det_model=wf.MODELS / "det_fold_a.onnx", cls_model=wf.MODELS / "cls_pm.onnx"),
               "b": lr.LocalReader(det_model=wf.MODELS / "det_fold_b.onnx", cls_model=wf.MODELS / "cls_am.onnx")}
    print("CLS_SIZE", lr.CLS_SIZE)
    sizes = [lr.CLS_SIZE // 2, lr.CLS_SIZE * 3 // 4, lr.CLS_SIZE]
    score = {s: 0 for s in sizes}
    seen = 0
    for t, r in sorted(res.items(), key=lambda kv: int(kv[0])):
        if not r["top"]:
            continue
        t = int(t)
        rgb = wf.load(rows[t])
        rd = readers[wf.fold(rows[t]["at"])[0]]
        ans = {s: read_up(rd, rgb, r["top"]["box"], s) for s in sizes}
        tr = wf.READ_TRUTH.get(t)
        if tr:
            seen += 1
            for s in sizes:
                score[s] += ans[s][0] == tr
        print(t, "정답", tr or "-", ans)
    print("맞음", score, "/", seen)


if __name__ == "__main__":
    main()
