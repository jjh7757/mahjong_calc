"""제안 확인(2026-10-27, 사용자 요청): "YOLO 로 자른 패를 표준 크기로 → 패마다 기준 그림 3~5장 → 사전학습 CNN(ResNet) 특징
최근접 비교(0°/180°) → 1등·2등 점수 차가 작으면 애매한 패로 Gemini 에 넘김".

  python -I experiments/template/resnet_nn.py

시험 = B·C·D 손패 78장(embed.py·match_shift.py 와 같음). 기준 그림은 시험 패의 장면을 뺀 나머지(다른 장면·매장 촬영 Q·집 패 S)에서
  all   쓸 수 있는 것 전부
  k3·k5 패마다 3장·5장만 무작위로(시드 10개 평균) — 제안의 "3~5장"
특징: ResNet-50(ImageNet, timm resnet50.a1_in1k) 전역 평균(제안 그대로) / layer4 특징 지도를 4×4 칸 평균(위치 정보 남김).
애매한 패 넘기기: 1등−2등 코사인 차가 기준보다 작으면 넘김 → 남은 패의 정답률(넘기지 않은 비율과 함께), 손패 13장이 전부 안 넘겨질 확률.
"""
from __future__ import annotations

import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import timm  # noqa: E402
import torch  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import embed as E  # noqa: E402
import faces as F  # noqa: E402


def features(model, cfg, images, spatial: bool) -> np.ndarray:
    size = cfg["input_size"][-1]
    mean, std = np.array(cfg["mean"], np.float32), np.array(cfg["std"], np.float32)
    out = []
    for i in range(0, len(images), 32):
        x = np.stack([((cv2.cvtColor(E.square(im, size), cv2.COLOR_BGR2RGB).astype(np.float32) / 255 - mean) / std)
                      .transpose(2, 0, 1) for im in images[i:i + 32]])
        with torch.inference_mode():
            f = model.forward_features(torch.from_numpy(x))  # (n, 2048, 7, 7)
            if spatial:
                f = torch.nn.functional.adaptive_avg_pool2d(f, 4)
                f = f / (f.norm(dim=1, keepdim=True) + 1e-6)
                v = f.flatten(1).numpy()
            else:
                v = f.mean((2, 3)).numpy()
        out.append(v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-6))
    return np.concatenate(out)


def classify(Ft, Ft180, Fr, ref_codes):
    """패마다 기준 그림과 코사인(0°·180° 중 큰 값), 종류별 최댓값 → (1등, 1등 점수, 2등 점수)."""
    sims = np.maximum(Fr @ Ft, Fr @ Ft180)
    best = defaultdict(lambda: -9.0)
    for c, s in zip(ref_codes, sims):
        best[c] = max(best[c], float(s))
    order = sorted(best.items(), key=lambda kv: -kv[1])
    return order[0][0], order[0][1], order[1][1] if len(order) > 1 else -9.0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = F.store_crops() + F.set2_crops()
    raws = [F.read(r["path"]) for r in rows]
    faces = [F.face(im, (96, 128))[0] for im in raws]
    test = [i for i, r in enumerate(rows) if r["group"] in "BCD" and r["src"] == "hand"]
    model = timm.create_model("resnet50.a1_in1k", pretrained=True, num_classes=0).eval()
    cfg = timm.data.resolve_data_config({}, model=model)
    torch.set_num_threads(os.cpu_count() or 4)
    cnt = Counter(r["code"] for r in rows if r["group"] != "C")
    print(f"기준 그림(예: C 를 시험할 때) 종류별 장수: 중앙 {sorted(cnt.values())[len(cnt) // 2]}, 최소 {min(cnt.values())}, "
          f"최대 {max(cnt.values())}, 종류 {len(cnt)}")
    for inp_name, imgs in (("흰 면(표준 크기)", faces), ("격자 크롭", raws)):
        for spatial in (False, True):
            Fa = features(model, cfg, imgs, spatial)
            Fa180 = features(model, cfg, [cv2.rotate(im, cv2.ROTATE_180) for im in imgs], spatial)
            feat = "4×4 칸" if spatial else "전역 평균"
            for refmode in ("all", "k3", "k5"):
                seeds = [0] if refmode == "all" else range(10)
                results = []  # (정답?, 차)
                for seed in seeds:
                    rng = random.Random(seed)
                    for ti in test:
                        g = rows[ti]["group"]
                        pool = [j for j, r in enumerate(rows) if r["group"] != g]  # embed.py 의 loso(매장+집)과 같음
                        if refmode != "all":
                            by = defaultdict(list)
                            for j in pool:
                                by[rows[j]["code"]].append(j)
                            k = int(refmode[1])
                            pool = [j for js in by.values() for j in rng.sample(js, min(k, len(js)))]
                        pred, s1, s2 = classify(Fa[ti], Fa180[ti], Fa[pool], [rows[j]["code"] for j in pool])
                        results.append((pred == rows[ti]["code"], s1 - s2))
                n = len(results)
                acc = sum(o for o, _ in results) / n
                line = [f"정답 {acc:5.1%}"]
                margins = sorted(m for _, m in results)
                for cover in (0.9, 0.7, 0.5):
                    thr = margins[int((1 - cover) * n)]
                    kept = [o for o, m in results if m >= thr]
                    line.append(f"안 넘긴 {cover:.0%}: 정답 {sum(kept) / max(1, len(kept)):5.1%}")
                # 정답률이 99% 이상이 되는 가장 낮은 기준에서 남는 비율 → 13장이 다 남을 확률
                best_cover = 0.0
                for thr in sorted({m for _, m in results}):
                    kept = [o for o, m in results if m >= thr]
                    if kept and sum(kept) / len(kept) >= 0.99:
                        best_cover = len(kept) / n
                        break
                line.append(f"99% 정답이 되게 거르면 남는 패 {best_cover:5.1%} → 손패 13장 전부 남을 확률 {best_cover ** 13:6.2%}")
                print(f"{inp_name:10s} {feat:6s} 기준 {refmode:3s} | " + " | ".join(line), flush=True)


if __name__ == "__main__":
    main()
