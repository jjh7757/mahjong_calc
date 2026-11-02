"""서버 벤치 재료를 만든다(2026-11-02, 노트북, API 없음): 분류기 ONNX, 검출기 ONNX 복사, 앱이 보내는 자리 크롭(q92)과 meta.json.
  python -I experiments/tile_classifier/server_bench/prep.py
결과 server_bench/models, crops(커밋 안 함)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
TC = HERE.parent
sys.argv = [sys.argv[0], "--r2"]
sys.path.insert(0, str(TC))
import det_eval as de  # noqa: E402
from det_eval import sg, tr  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    models, crops = HERE / "models", HERE / "crops"
    models.mkdir(exist_ok=True)
    crops.mkdir(exist_ok=True)
    for f in ("fold_a", "fold_b", "final"):
        shutil.copy(de.OUT / f"{f}.onnx", models / f"det_{f}.onnx")
    for part in ("bcd", "am", "pm"):
        net = tr.torchvision.models.mobilenet_v3_small()
        net.classifier[3] = tr.nn.Linear(net.classifier[3].in_features, len(tr.CLASSES))
        net.load_state_dict(torch.load(de.DATA / f"cls_{part}.pt", map_location="cpu", weights_only=True))
        torch.onnx.export(net.eval(), torch.zeros(1, 3, tr.SIZE, tr.SIZE), models / f"cls_{part}.onnx", input_names=["x"], output_names=["y"],
                          dynamic_axes={"x": {0: "n"}, "y": {0: "n"}}, opset_version=17, dynamo=False)
    rows = []
    for s in sg.scenes():
        if s["hand"] is None:
            continue
        part = "bcd" if not s["name"].startswith("2026") else "am" if s["name"] < "20261031_14" else "pm"
        im = sg.crop(Image.open(s["path"]).convert("RGB"), sg.seat_box(s["grid"], s["side"], 40), s["side"])
        im.save(crops / f"{s['name']}.jpg", quality=92)
        rows.append(dict(name=s["name"], part=part, frac=sg.hand_frac(s["grid"], s["side"]), det="b" if part == "am" else "a"))
    (HERE / "meta.json").write_text(json.dumps(dict(classes=tr.CLASSES, size=tr.SIZE, mean=tr.MEAN, std=tr.STD, photos=rows), ensure_ascii=False), encoding="utf-8")
    print(len(rows), sum(p.stat().st_size for p in models.iterdir()) // 2**20, "MB 모델", sum(p.stat().st_size for p in crops.iterdir()) // 2**20, "MB 크롭")


if __name__ == "__main__":
    main()
