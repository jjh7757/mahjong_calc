"""서버 app/local_read.py read_wall 을 표 1-34·1-35 와 같은 사진·정답·나눔 모델로 다시 잰다(2026-11-02, API 없음). 표 1-36.
실험 규칙과 달리 뒷면 색을 분홍·보라로 묶지 않고, 확신도 0.7 미만은 답을 내지 않는다.
  python -I -X utf8 experiments/tile_classifier/wall_server_check.py
"""
from __future__ import annotations

import io
import json
import statistics
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wall_frames as wf  # noqa: E402
from app import local_read as lr  # noqa: E402

V = wf.ROOT / "experiments" / "visit_20261031"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    readers = {"a": lr.LocalReader(det_model=wf.MODELS / "det_fold_a.onnx", cls_model=wf.MODELS / "cls_pm.onnx"),
               "b": lr.LocalReader(det_model=wf.MODELS / "det_fold_b.onnx", cls_model=wf.MODELS / "cls_am.onnx")}
    rows = wf.all_frames()
    ok = 0
    for t, truth in sorted(wf.TRUTH.items()):
        buf = io.BytesIO()
        Image.fromarray(wf.load(rows[t])).save(buf, "JPEG", quality=92)
        r = readers[wf.fold(rows[t]["at"])[0]].read_wall(buf.getvalue())
        c = wf.center(r["box"]) if r["box"] else None
        good = (c is None) if truth is None else bool(c and wf.hit(c, truth))
        ok += good
        if not good:
            print("프레임 틀림", t, truth, r["box"], r["indicators"])
    print("프레임 위치", ok, "/", len(wf.TRUTH))
    scenes = json.loads((V / "truth.json").read_text(encoding="utf-8"))["scenes"]
    ms, conf_ok, n = [], 0, 0
    for name, s in sorted(scenes.items()):
        if s.get("riichi") or not s.get("indicators"):
            continue
        jpeg = (V / "captures" / name / "original.jpg").read_bytes()
        r = readers["b" if name < "20261031_14" else "a"].read_wall(jpeg)
        got = [x["tile"] for x in r["indicators"]]
        n += 1
        conf_ok += got == s["indicators"]
        ms.append(r["ms"])
        print(name[-6:], "정답", s["indicators"], "답", got, "conf", r["conf"], r["ms"], flush=True)
    print("리치 아닌 화료", conf_ok, "/", n)
    for k in ("decode", "detect", "rules", "read", "total"):
        print(k, statistics.median(m[k] for m in ms), "최대", max(m[k] for m in ms))


if __name__ == "__main__":
    main()
