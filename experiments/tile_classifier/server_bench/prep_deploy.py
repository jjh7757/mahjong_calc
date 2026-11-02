"""그림자 판독에 넣을 모델을 서버 app/assets 로(2026-11-02): 검출기 = 2회차 final(전부 학습), 분류기 = 고친 라벨 전부로 새로 학습.
전부 학습이라 지금 사진으로는 평가할 수 없다. 다음 매장 사진이 첫 시험이다.
  python -I -X utf8 experiments/tile_classifier/server_bench/prep_deploy.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
TC = HERE.parent
sys.argv = [sys.argv[0], "--r2"]
sys.path.insert(0, str(TC))
import det_eval as de  # noqa: E402
from det_eval import rw, tr  # noqa: E402

ASSETS = Path("C:/Users/jjh7757/dev/mahjong-recognizer/app/assets")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    base = json.loads((de.DATA / "index.json").read_text(encoding="utf-8"))
    add = rw.extra()
    images = {x["file"]: tr.square(Image.open(de.DATA / "crops" / x["file"]).convert("RGB")) for x in base}
    images.update({x["file"]: tr.square(Image.open(x["path"]).convert("RGB")) for x in add})
    pool = base + add
    print("학습", len(pool), "종류", len({x["tile"] for x in pool}), "드문 종류", Counter(x["tile"] for x in pool).most_common()[-4:], flush=True)
    net = tr.train(pool, images, 0)
    torch.save(net.state_dict(), de.DATA / "cls_all.pt")
    torch.onnx.export(net.eval(), torch.zeros(1, 3, tr.SIZE, tr.SIZE), ASSETS / "tile-cls-mnv3s.onnx", input_names=["x"], output_names=["y"],
                      dynamic_axes={"x": {0: "n"}, "y": {0: "n"}}, opset_version=17, dynamo=False)
    shutil.copy(de.OUT / "final.onnx", ASSETS / "tile-yolo26n.onnx")
    print({p.name: p.stat().st_size // 2**20 for p in ASSETS.glob("tile-*")}, "MB")


if __name__ == "__main__":
    main()
