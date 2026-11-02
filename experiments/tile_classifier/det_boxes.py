"""검출기 학습용 "앞면 패" 상자 후보를 사진마다 만들고 눈 확인 그림을 그린다(2026-11-01). API 없음, 노트북 CPU.

상자: 운영 YOLO11 s(conf 0.05)를 4×4 토막(절반 겹침)에 돌림 + 앞면(흰 면) + 크기 + 자체 분류기(model_round2) 확신. 패 종류 라벨은 안 쓴다. HaseLab 은 안 쓴다.
검출기는 상자가 없는 패를 "패 아님" 으로 배우므로, 빠진 패는 det_review 에서 사진 영역을 지우거나 상자를 더한다.
나누기: val = 매장 오후·B·C·D(틀 잡기 평가와 같은 사진), train = 나머지. B·C·D 를 다시 읽은 기록은 뺀다.
  python -I experiments/tile_classifier/det_boxes.py
결과 data/det/boxes.json, data/det/check/<이름>.jpg
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harvest as hv  # noqa: E402
import train as tr  # noqa: E402
from harvest import rv, st  # noqa: E402

OUT = hv.DATA / "det"
BCD = {"k25", "k28", "k15", "k26", "k12", "k16"}
COPIES = {"20261029_220339", "20261029_230849", "20261030_235803", "20261031_000209"}  # B·C·D 를 앱으로 다시 읽은 기록(review.leak_check)


def photos() -> list[tuple[str, Path, str]]:
    out = []
    for p in sorted(hv.EXP.glob("field_20261024/kakao_photos/*.jpg")):
        out.append((p.stem, p, "val" if p.stem in BCD else "train"))
    for base in ("field_20261024", "visit_20261031"):
        for p in sorted((hv.EXP / base / "captures").glob("*/original.jpg")):
            n = p.parent.name
            if n in COPIES:
                continue
            out.append((n, p, "val" if "20261031_14" <= n else "train"))
    return out


def faces(det: rv.TileDetector, rgb: np.ndarray) -> list[tuple[int, int, int, int]]:
    H, W = rgb.shape[:2]
    ws, hs = W // hv.GRID, H // hv.GRID
    out = []
    for yy in range(0, H - hs + 1, hs // 2):
        for xx in range(0, W - ws + 1, ws // 2):
            out += [(int(x + xx), int(y + yy), int(w), int(h)) for x, y, w, h in det.detect(np.ascontiguousarray(rgb[yy:yy + hs, xx:xx + ws]))]
    bs = rv.dedupe(rv.keep_faces(out, rv.white_mask(rgb), min_white=0.35))  # 0.5 면 그늘진 패·모서리 울기가 빠진다
    if not bs:
        return []
    short = statistics.median(min(b[2], b[3]) for b in bs)
    return [b for b in bs if 0.6 * short <= min(b[2], b[3]) <= 1.5 * short and max(b[2], b[3]) <= 2.2 * short]


def verified(net, rgb: np.ndarray, bs: list) -> list:
    """탁자 모서리 울기도 남기려고 탁자 거르기 대신 분류기로 거른다. 白(무늬 없음)은 분류기 답 + 펠트 근처일 때만."""
    short = statistics.median(min(b[2], b[3]) for b in bs) if bs else 0
    near = set(st.on_table(bs, rgb, st.TABLE_REACH * short)) if bs else set()
    inked, blank, weak = [], [], []
    for b in bs:
        pred, conf, _ = hv.label(net, hv.cut(rgb, b), b[2], b[3])
        if pred != "5z" and conf >= 0.5 and st.ink(rgb, b) >= st.INK_MIN:
            inked.append(b)
        elif pred == "5z" and conf >= 0.6 and b in near and 1.1 <= max(b[2], b[3]) / min(b[2], b[3]) <= 1.7:
            blank.append(b)
        elif pred != "5z" and st.ink(rgb, b) >= st.INK_MIN and 1.1 <= max(b[2], b[3]) / min(b[2], b[3]) <= 1.7:
            weak.append(b)
    # 확신이 낮아도 무늬가 있고 확실한 패 바로 옆이면 패(143104 손패의 二·七·八)
    inked += [b for b in weak if any(abs(b[0] + b[2] / 2 - i[0] - i[2] / 2) < 1.3 * short and abs(b[1] + b[3] / 2 - i[1] - i[3] / 2) < 0.8 * short
                                     or abs(b[0] + b[2] / 2 - i[0] - i[2] / 2) < 0.8 * short and abs(b[1] + b[3] / 2 - i[1] - i[3] / 2) < 1.3 * short for i in inked)]

    def beside(b) -> bool:  # 白은 무늬 있는 패 옆에 있을 때만. 탁자 테두리·패산의 흰 면을 白 으로 잡는다(131411·143104·171505)
        cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        return any(abs(cx - i[0] - i[2] / 2) < 1.8 * short and abs(cy - i[1] - i[3] / 2) < 1.8 * short for i in inked)

    return inked + [b for b in blank if beside(b)]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    (OUT / "check").mkdir(parents=True, exist_ok=True)
    det = rv.TileDetector(conf=0.05)
    net = tr.torchvision.models.mobilenet_v3_small()
    net.classifier[3] = tr.nn.Linear(net.classifier[3].in_features, len(tr.CLASSES))
    net.load_state_dict(tr.torch.load(hv.DATA / "model_round2.pt", map_location="cpu", weights_only=True))
    net.eval()
    rows = {}
    for name, p, split in photos():
        if name.startswith("20261024"):  # 40° 기운 탁자는 네모 상자가 겹쳐 라벨이 나쁘다. 거치는 반듯하게 하기로 했다(10-29)
            continue
        im = Image.open(p).convert("RGB")
        if im.width < 3000:
            continue
        arr = np.asarray(im)
        bs = verified(net, arr, faces(det, arr))
        rows[name] = dict(path=str(p), split=split, size=list(im.size), boxes=[list(b) for b in bs])
        s = 1400 / im.width
        v = im.resize((1400, round(im.height * s)))
        d = ImageDraw.Draw(v)
        for b in bs:
            d.rectangle((b[0] * s, b[1] * s, (b[0] + b[2]) * s, (b[1] + b[3]) * s), outline=(255, 0, 0), width=2)
        for i in range(1, 7):  # 사진 좌표를 읽기 쉽게 격자선
            d.line((i * 200, 0, i * 200, v.height), fill=(255, 255, 0), width=1)
        for i in range(1, 6):
            d.line((0, i * 200, 1400, i * 200), fill=(255, 255, 0), width=1)
        v.save(OUT / "check" / f"{name}.jpg", quality=85)
        print(name, split, im.size, len(bs), flush=True)
    (OUT / "boxes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("사진", len(rows), "train", sum(r["split"] == "train" for r in rows.values()), "val", sum(r["split"] == "val" for r in rows.values()), "상자", sum(len(r["boxes"]) for r in rows.values()))


if __name__ == "__main__":
    main()
