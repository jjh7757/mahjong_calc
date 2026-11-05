"""개선 계획 5단계(2026-11-05): S3 "분류기 2벌 불일치" 용 두 번째 분류기와 온도 보정 T.

두 번째 분류기 = 같은 학습 묶음, 다른 씨드(1). 나눔 cls_<part>(det_eval.classifiers 와 같은 묶음 = 그 시간대를 안 배움)와
운영 cls_all(prep_deploy 와 같은 묶음 = 전부)에 각각 하나씩. 측정 때 fold 서버는 cls_<part> + cls_<part>_s1(둘 다 그 사진을 안 배움),
운영은 tile-cls-mnv3s(= cls_all 씨드 0) + cls_all_s1 → 서버 assets/tile-cls-alt.onnx.
온도 T = 나눔 분류기(씨드 0, 운영 ONNX 와 같은 export) 로짓을 그 나눔이 안 배운 크롭(base part == 나눔, extra half == 나눔)에서 모아
NLL 최소인 T 하나(격자 0.5~5, 0.01 간격). 답(argmax)은 안 바뀐다.

  python -I -X utf8 experiments/tile_classifier/server_bench/prep_alt_cls.py [--only bcd,am,pm,all] [--temp-only]
결과 server_bench/models/cls_<part>_s1.onnx, cls_all_s1.onnx, results/temperature.json(experiments/speed/results)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
TC = HERE.parent
sys.argv, _argv = [sys.argv[0], "--r2"], sys.argv
sys.path.insert(0, str(TC))
import det_eval as de  # noqa: E402
from det_eval import rw, tr  # noqa: E402

sys.argv = _argv
MODELS = HERE / "models"
RES = TC.parents[0] / "speed" / "results"
SEED = 1


def export(net, path: Path) -> None:
    torch.onnx.export(net.eval(), torch.zeros(1, 3, tr.SIZE, tr.SIZE), path, input_names=["x"], output_names=["y"],
                      dynamic_axes={"x": {0: "n"}, "y": {0: "n"}}, opset_version=17, dynamo=False)


def logits_onnx(path: Path, ims: list[Image.Image]) -> np.ndarray:
    """서버 LocalReader._tensor 와 같은 전처리(tr.square = 128 회색 바탕 가운데, ImageNet 정규화)로 ONNX 로짓."""
    import onnxruntime as ort

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    out = []
    for i in range(0, len(ims), 64):
        x = np.stack([tr.PLAIN(im).numpy() for im in ims[i:i + 64]])
        out.append(sess.run(None, {sess.get_inputs()[0].name: x})[0])
    return np.concatenate(out)


def nll(z: np.ndarray, y: np.ndarray, T: float) -> float:
    s = z / T
    s = s - s.max(1, keepdims=True)
    return float(-(s[np.arange(len(y)), y] - np.log(np.exp(s).sum(1))).mean())


def ece(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    conf, pred = p.max(1), p.argmax(1)
    e = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        m = (conf > lo) & (conf <= lo + 1 / bins)
        if m.any():
            e += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(e)


def soft(z: np.ndarray, T: float) -> np.ndarray:
    s = z / T
    e = np.exp(s - s.max(1, keepdims=True))
    return e / e.sum(1, keepdims=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="bcd,am,pm,all")
    ap.add_argument("--temp-only", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    base = json.loads((de.DATA / "index.json").read_text(encoding="utf-8"))
    add = rw.extra()
    images = {x["file"]: tr.square(Image.open(de.DATA / "crops" / x["file"]).convert("RGB")) for x in base}
    images.update({x["file"]: tr.square(Image.open(x["path"]).convert("RGB")) for x in add})
    if not a.temp_only:
        for part in a.only.split(","):
            dst = MODELS / f"cls_{part}_s{SEED}.onnx"
            if dst.exists():
                print("있음", dst, flush=True)
                continue
            if part == "all":
                pool = base + add
            else:  # det_eval.classifiers 와 같은 묶음
                pool = [x for x in base if x["part"] != part] + [x for x in add if x["half"] != part and (part != "bcd" or x["half"] != "other")]
            t0 = time.perf_counter()
            net = tr.train(pool, images, SEED)
            export(net, dst)
            print(f"분류기 {part} 씨드 {SEED} 학습 {len(pool)}장 {time.perf_counter() - t0:.0f}초 → {dst}", flush=True)

    # 온도 보정: 나눔 분류기(씨드 0)의 홀드아웃 로짓
    zs, ys, rows = [], [], {}
    for part in ("bcd", "am", "pm"):
        held = [x for x in base if x["part"] == part] + [x for x in add if x["half"] == part]
        z = logits_onnx(MODELS / f"cls_{part}.onnx", [images[x["file"]] for x in held])
        y = np.array([tr.CLASSES.index(x["tile"]) for x in held])
        acc = float((z.argmax(1) == y).mean())
        rows[part] = dict(n=len(held), acc=round(acc, 4))
        zs.append(z)
        ys.append(y)
        # 두 번째 분류기와의 불일치(홀드아웃, 참고)
        s1 = MODELS / f"cls_{part}_s{SEED}.onnx"
        if s1.exists():
            z1 = logits_onnx(s1, [images[x["file"]] for x in held])
            dis = z1.argmax(1) != z.argmax(1)
            wrong = z.argmax(1) != y
            rows[part].update(alt_acc=round(float((z1.argmax(1) == y).mean()), 4), disagree=int(dis.sum()), wrong=int(wrong.sum()),
                              wrong_caught=int((dis & wrong).sum()))
    z, y = np.concatenate(zs), np.concatenate(ys)
    grid = np.round(np.arange(0.5, 5.0001, 0.01), 2)
    losses = [nll(z, y, t) for t in grid]
    T = float(grid[int(np.argmin(losses))])
    res = dict(T=T, n=int(len(y)), acc=round(float((z.argmax(1) == y).mean()), 4), nll_T1=round(nll(z, y, 1.0), 4), nll_T=round(min(losses), 4),
               ece_T1=round(ece(soft(z, 1.0), y), 4), ece_T=round(ece(soft(z, T), y), 4), parts=rows,
               note="나눔 분류기 cls_<part>(씨드 0) 로짓, 그 나눔이 안 배운 크롭(data/index.json part + review.extra half). 축 상자 harvest 크롭이라 운영의 세운 크롭과 다르다.")
    # 확신도 구간별 실제 정확도(보정 전·후)
    for tag, t in (("T1", 1.0), ("T", T)):
        p = soft(z, t)
        conf, ok = p.max(1), p.argmax(1) == y
        res[f"reliab_{tag}"] = {f"{lo:.1f}-{lo + 0.1:.1f}": [int(((conf > lo) & (conf <= lo + 0.1)).sum()), int((ok & (conf > lo) & (conf <= lo + 0.1)).sum())]
                               for lo in np.arange(0, 1, 0.1)}
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "temperature.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
