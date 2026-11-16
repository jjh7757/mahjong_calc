"""1단계: 판 구간의 모든 프레임에서 손패 띠(band)·강(river)·울기 자리(meld) 영역의 움직임·피부 특징을 잰다(반 해상도, JPEG draft).

  python -X utf8 features.py <판 id>
결과 _work/<판 id>_feat.npz: ms, band_d1(앞 프레임과 20단계 넘게 다른 화소 비율), band_d3(3장 앞과), band_skin(피부 비율),
  river_skin, river_d1, meld_d1, band_small(띠 회색 1/4 축소, 줄 생략·정지 상태 비교용).
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

DIFF = 20  # 회색 차이 문턱(0~255)


def load_half(ms: int) -> np.ndarray:
    im = Image.open(hc.path_of(ms))
    im.draft("RGB", (im.width // 2, im.height // 2))
    return np.asarray(im.convert("RGB"))


def skin(rgb: np.ndarray) -> float:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return float(((h >= 3) & (h < 32) & (s > 40) & (v > 70)).mean())


def half(box):
    return [v // 2 for v in box]


def game_span(cf: dict) -> tuple[int, int]:
    return hc.to_ms(cf.get("t_start", cf["t_ready"])) - int(cf.get("pre_sec", 3) * 1000), hc.to_ms(cf["t_reveal"]) + int(cf.get("post_sec", 4) * 1000)


def main():
    gid = sys.argv[1]
    cf = hc.config(gid)
    t0, t1 = game_span(cf)
    ms_list = hc.frame_range(t0, t1)
    bx, rx, mx = half(cf["band"]), half(cf["river"]), half(cf["meld"])
    out = {k: [] for k in ("band_d1", "band_d3", "band_skin", "river_skin", "river_d1", "meld_d1", "meld_skin")}
    small = []
    hist: list[np.ndarray] = []
    prev_r = prev_m = None
    for i, ms in enumerate(ms_list):
        rgb = load_half(ms)
        b = rgb[bx[1]:bx[3], bx[0]:bx[2]]
        g = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY).astype(np.int16)
        r = rgb[rx[1]:rx[3], rx[0]:rx[2]]
        gr = cv2.cvtColor(r, cv2.COLOR_RGB2GRAY).astype(np.int16)
        m = rgb[mx[1]:mx[3], mx[0]:mx[2]]
        gm = cv2.cvtColor(m, cv2.COLOR_RGB2GRAY).astype(np.int16)
        out["band_d1"].append(float((np.abs(g - hist[-1]) > DIFF).mean()) if hist else 0.0)
        out["band_d3"].append(float((np.abs(g - hist[-3]) > DIFF).mean()) if len(hist) >= 3 else 0.0)
        out["band_skin"].append(skin(b))
        out["river_skin"].append(skin(r))
        out["river_d1"].append(float((np.abs(gr - prev_r) > DIFF).mean()) if prev_r is not None else 0.0)
        out["meld_d1"].append(float((np.abs(gm - prev_m) > DIFF).mean()) if prev_m is not None else 0.0)
        out["meld_skin"].append(skin(m))
        hist = (hist + [g])[-3:]
        prev_r, prev_m = gr, gm
        small.append(cv2.resize(g.astype(np.uint8), (g.shape[1] // 2, g.shape[0] // 2), interpolation=cv2.INTER_AREA))
        if i % 500 == 0:
            print(f"{i}/{len(ms_list)} {hc.hms(ms)}", flush=True)
    np.savez_compressed(hc.WORK / f"{gid}_feat.npz", ms=np.array(ms_list, np.int64), band_small=np.stack(small),
                        **{k: np.array(v, np.float32) for k, v in out.items()})
    print("frames", len(ms_list), "gaps>150ms", int((np.diff(ms_list) > 150).sum()), "max gap", int(np.diff(ms_list).max()))


if __name__ == "__main__":
    main()
