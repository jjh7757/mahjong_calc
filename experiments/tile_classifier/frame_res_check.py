"""프레임 해상도에서 패 종류를 구분할 수 있나(2026-11-01). 라벨 크롭을 프레임 패 크기로 줄여 HaseLab 분류기로 읽는다. API 없음.

운영 사진 패 짧은 변 88px, 프레임 21px(`frames_*.zip` 1020×764) → 축소 비율 약 0.24. 줄인 뒤 JPEG 75 로 눌렀다가 224 로 키운다.
학습 전 분류기의 값이라 프레임으로 학습한 모델의 값이 아니고, 실제 프레임의 흔들림·압축은 없어 그쪽엔 낙관적이다.
  python -I experiments/tile_classifier/frame_res_check.py
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms as T

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "yolo"))
import run_yolo as ry  # noqa: E402

DATA = HERE / "data"
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def shrink(im: Image.Image, scale: float) -> Image.Image:
    if scale >= 1:
        return im
    small = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.BILINEAR)
    b = io.BytesIO()
    small.save(b, "JPEG", quality=75)
    return Image.open(io.BytesIO(b.getvalue())).convert("RGB")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    net = ry.HaseLab().net
    tf = T.Compose([T.Resize((224, 224)), T.ToTensor(), T.Normalize(MEAN, STD)])
    for scale in (1.0, 0.5, 0.35, 0.24):
        x = torch.stack([tf(shrink(Image.open(DATA / "crops" / i["file"]).convert("RGB"), scale)) for i in index])
        with torch.no_grad():
            preds = [ry.HASE_CLASSES[k] for b in x.split(16) for k in net(b).argmax(1).tolist()]
        ok = sum(p == i["tile"] for p, i in zip(preds, index))
        wrong = Counter((i["tile"], p) for p, i in zip(preds, index) if p != i["tile"])
        print(f"배율 {scale} (패 짧은 변 약 {88 * scale:.0f}px): {ok}/{len(index)} ({100 * ok / len(index):.1f}%) 자주 틀림 {wrong.most_common(5)}", flush=True)


if __name__ == "__main__":
    main()
