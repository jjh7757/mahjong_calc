"""비전 임베딩 이미지 검색(학습 없음): 사전학습 모델의 특징으로 기준 그림 중 가장 가까운 패.

  python -I experiments/template/embed.py [모델 이름 ...]

시험·기준 그림 나누기는 match_shift.py 와 같다(B·C·D 손패 78장, 강은 장면끼리 겹쳐 뺌). 가중치는 HF 캐시(timm)에서만 읽는다.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter, defaultdict

os.environ.setdefault("HF_HUB_OFFLINE", "1")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import timm  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import faces as F  # noqa: E402

MODELS = {
    "dinov2_s": ("vit_small_patch14_dinov2.lvd142m", {"img_size": 224}),
    "dinov2_s_reg": ("vit_small_patch14_reg4_dinov2.lvd142m", {"img_size": 224}),
    "dinov2_b": ("vit_base_patch14_dinov2.lvd142m", {"img_size": 224}),
    "dinov2_l": ("vit_large_patch14_dinov2.lvd142m", {"img_size": 224}),
    "clip_b": ("vit_base_patch16_clip_224.openai", {}),
    "siglip2_b": ("vit_base_patch16_siglip_256.v2_webli", {}),
    "convnext_t": ("convnext_tiny.fb_in22k_ft_in1k", {}),
    "resnet50": ("resnet50.a1_in1k", {}),
}


DENSE = os.environ.get("DENSE") == "1"


def square(im: np.ndarray, size: int) -> np.ndarray:
    """세로로 긴 패를 가운데 두고 가장자리 색으로 채워 정사각형으로."""
    h, w = im.shape[:2]
    s = max(h, w)
    top, left = (s - h) // 2, (s - w) // 2
    sq = cv2.copyMakeBorder(im, top, s - h - top, left, s - w - left, cv2.BORDER_REPLICATE)
    return cv2.resize(sq, (size, size), interpolation=cv2.INTER_AREA)


def embed_all(model, cfg, images: list[np.ndarray], bs: int = 32) -> np.ndarray:
    size = cfg["input_size"][-1]
    mean, std = np.array(cfg["mean"], np.float32), np.array(cfg["std"], np.float32)
    out = []
    for i in range(0, len(images), bs):
        batch = []
        for im in images[i:i + bs]:
            x = cv2.cvtColor(square(im, size), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
            batch.append(((x - mean) / std).transpose(2, 0, 1))
        with torch.inference_mode():
            x = torch.from_numpy(np.stack(batch))
            if DENSE:
                # 위치별 특징: 패치 토큰을 4×4 칸으로 평균(전체 요약 벡터는 획 차이를 뭉갠다)
                t = model.forward_features(x)[:, getattr(model, "num_prefix_tokens", 1):]
                n = int(t.shape[1] ** 0.5)
                t = t.reshape(len(batch), n, n, -1).permute(0, 3, 1, 2)
                t = torch.nn.functional.adaptive_avg_pool2d(t, 4)
                t = t / (t.norm(dim=1, keepdim=True) + 1e-6)
                v = t.flatten(1).numpy()
            else:
                v = model(x).numpy()
        out.append(v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-6))
    return np.concatenate(out)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    names = sys.argv[1:] or list(MODELS)
    rows = F.store_crops() + F.set2_crops()
    raws = [F.read(r["path"]) for r in rows]
    faces = [F.face(im, (96, 128))[0] for im in raws]
    test_idx = [i for i, r in enumerate(rows) if r["group"] in "BCD" and r["src"] == "hand"]
    modes = {
        "loso(매장+집)": lambda g: [i for i, r in enumerate(rows) if r["group"] != g],
        "loso Q 제외": lambda g: [i for i, r in enumerate(rows) if r["group"] not in (g, "Q")],
        "A·E·Q+집": lambda g: [i for i, r in enumerate(rows) if r["group"] not in "BCD"],
        "집 패만": lambda g: [i for i, r in enumerate(rows) if r["group"] == "S"],
    }
    torch.set_num_threads(os.cpu_count() or 4)
    for name in names:
        arch, kw = MODELS[name]
        model = timm.create_model(arch, pretrained=True, num_classes=0, **kw).eval()
        cfg = timm.data.resolve_data_config({}, model=model)
        if "img_size" in kw:  # DINOv2 는 기본 518 → 224 로 만든 모델에 맞춘다
            cfg["input_size"] = (3, kw["img_size"], kw["img_size"])
        for inp_name, imgs in (("흰 면", faces), ("격자 크롭", raws)):
            t0 = time.perf_counter()
            E = embed_all(model, cfg, imgs)
            E180 = embed_all(model, cfg, [cv2.rotate(im, cv2.ROTATE_180) for im in imgs])
            per_img = (time.perf_counter() - t0) / (2 * len(imgs)) * 1000
            line = []
            worst = None
            for mname, refs_for in modes.items():
                ok, conf, per = 0, Counter(), defaultdict(lambda: [0, 0])
                for ti in test_idx:
                    g = rows[ti]["group"]
                    refs = refs_for(g)
                    R = E[refs]
                    sims = np.maximum(R @ E[ti], R @ E180[ti])
                    best = defaultdict(lambda: -9.0)
                    for j, s in zip(refs, sims):
                        c = rows[j]["code"]
                        best[c] = max(best[c], float(s))
                    pred = max(best, key=best.get)
                    hit = pred == rows[ti]["code"]
                    ok += hit
                    per[g][0] += hit
                    per[g][1] += 1
                    if not hit:
                        conf[f"{rows[ti]['code']}→{pred}"] += 1
                line.append(f"{mname} {ok}/{len(test_idx)} (" + " ".join(f"{g}{a}" for g, (a, b) in sorted(per.items())) + ")")
                if mname == "loso(매장+집)":
                    worst = conf
            print(f"{name:12s} {inp_name:5s} {per_img:5.0f}ms/장 | " + " | ".join(line), flush=True)
            print("     loso 자주 틀림:", ", ".join(f"{k}×{v}" for k, v in worst.most_common(6)), flush=True)


if __name__ == "__main__":
    main()
