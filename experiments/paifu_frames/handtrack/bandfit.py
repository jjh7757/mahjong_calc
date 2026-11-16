"""대조표용 띠(sheet_band) 정하기 도움: 판 동안 손패 줄이 가는 범위를 재서 양쪽 여유를 붙인다(2026-11-16 판정자 지적: 줄이 띠 밖으로 잘림).

  python -X utf8 bandfit.py <판 id> [--write]
구간 나누기용 band 는 그대로 두고(구간 번호가 바뀌지 않게), 깊이(대국자 앞뒤) 범위도 band 그대로, 줄 방향으로만 넓힌다.
재는 프레임: 정지 구간 가운데 프레임 전부 + 활동 구간에서 STEP 장마다 띠 피부 비율 < SKIN_MAX 인 프레임(손가락이 줄을 미는 순간은 넣고, 팔이 띠를 덮어 소매·팔이 패로 잘못 잡히는 프레임은 뺌).
줄 찾기: band 깊이 × (줄 방향으로 band ±SEARCH px) 영역을 대국자 시점으로 돌려, 패 화소(흰·분홍·보라, 피부 아님)가
  가로의 15~90% 를 차지하는 세로 줄들(펠트 끝 흰 줄처럼 가로 전체가 흰 줄은 뺌)에서 절반 넘게 패 화소인 가로 칸의 처음~끝.
sheet_band = 그 범위(프레임별 끝의 0.5·99.5 백분위 — 공개 순간·헛 검출 몇 장은 뺌) − LEFT_PAD ~ + RIGHT_PAD(대국자 오른쪽 = 뽑은 패 한두 장 자리), 그림 밖은 자름.
--write 면 config 에 sheet_band 와 sheet_band_note 를 쓴다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

SEARCH = 260
LEFT_PAD = 40
RIGHT_PAD = 100
STEP = 3
SKIN_MAX = 0.05
GAP_OK = 60  # 패 1.5장 폭까지의 틈은 같은 줄(떼어 둔 뽑은 패 포함)


def tile_mask(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    white = (s < 45) & (v > 170)
    back = ((h >= 115) | (h <= 2)) & (s >= 35) & (v > 120)
    skin = (h >= 3) & (h < 32) & (s > 40) & (v > 70)
    return (white | back) & ~skin


def search_box(cf: dict) -> list:
    x0, y0, x1, y1 = cf["band"]
    if cf["side"] in ("left", "right"):  # 줄 방향 = 원본 y
        return [x0, max(0, y0 - SEARCH), x1, min(1496, y1 + SEARCH)]
    return [max(0, x0 - SEARCH), y0, min(1496, x1 + SEARCH), y1]


def extent(v: np.ndarray) -> tuple[int, int] | None:
    m = tile_mask(v)
    frac = m.mean(1)
    rows = np.flatnonzero((frac > 0.15) & (frac < 0.9))
    if len(rows) < 8:
        return None
    col = m[rows].mean(0) > 0.5
    xs = np.flatnonzero(col)
    if len(xs) < 40:
        return None
    # 틈 GAP_OK 이하로 이어지는 덩어리 중 가장 긴 것(탁자 테두리 흰 줄·패산 끝 같은 떨어진 덩어리를 뺌)
    runs = [[xs[0], xs[0]]]
    for x in xs[1:]:
        if x - runs[-1][1] <= GAP_OK:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    a, b = max(runs, key=lambda r: r[1] - r[0])
    if b - a < 120:
        return None
    return int(a), int(b)


def view_to_axis(vx: int, box: list, side: str) -> int:
    """시점 가로 좌표 → 원본의 줄 방향 좌표."""
    x0, y0, x1, y1 = box
    if side == "bottom":
        return x0 + vx
    if side == "top":
        return x1 - 1 - vx
    if side == "left":
        return y0 + vx
    return y1 - 1 - vx  # right


def main():
    gid = sys.argv[1]
    cf = hc.config(gid)
    side = cf["side"]
    seg = hc.jload(hc.OUT / gid / "segments.json")
    z = np.load(hc.WORK / f"{gid}_feat.npz")
    off = seg["feat_index0"]
    idx = [(s["i0"] + s["i1"]) // 2 + off for s in seg["still"]]
    for a in seg["active"]:
        for i in range(a["i0"] + off, a["i1"] + off + 1, STEP):
            if z["band_skin"][i] < SKIN_MAX:
                idx.append(i)
    box = search_box(cf)
    lo, hi, worst = [], [], []
    for i in idx:
        ms = int(z["ms"][i])
        e = extent(hc.band_crop(hc.load(ms), box, side))
        if e is None:
            continue
        a, b = view_to_axis(e[0], box, side), view_to_axis(e[1], box, side)
        lo.append(min(a, b))
        hi.append(max(a, b))
        worst.append((ms, min(a, b), max(a, b)))
    lo_a, hi_a = np.array(lo), np.array(hi)
    # 대국자 왼쪽/오른쪽이 원본 축의 어느 끝인가: bottom·left 는 원본 증가 = 대국자 오른쪽, top·right 는 반대
    inc_right = side in ("bottom", "left")
    lo_p, hi_p = int(np.percentile(lo_a, 0.5)), int(np.percentile(hi_a, 99.5))  # 공개 순간·헛 검출 몇 장은 뺌
    left_end = lo_p if inc_right else hi_p
    right_end = hi_p if inc_right else lo_p
    if inc_right:
        a0, a1 = max(0, left_end - LEFT_PAD), min(1496, right_end + RIGHT_PAD)
    else:
        a0, a1 = max(0, right_end - RIGHT_PAD), min(1496, left_end + LEFT_PAD)
    x0, y0, x1, y1 = cf["band"]
    sb = [x0, int(a0), x1, int(a1)] if side in ("left", "right") else [int(a0), y0, int(a1), y1]
    old = (y0, y1) if side in ("left", "right") else (x0, x1)
    print(f"{gid} {side}: 잰 프레임 {len(lo)} · 줄 범위(원본 줄 방향) {lo_a.min()}~{hi_a.max()} "
          f"(1·99백분위 {int(np.percentile(lo_a, 1))}~{int(np.percentile(hi_a, 99))}) · band {old} → sheet_band {sb} 폭 {int(a1 - a0)}")
    out_lo = [w for w in worst if w[1] < min(old)]
    out_hi = [w for w in worst if w[2] > max(old)]
    print(f"  band 밖으로 나간 프레임: 작은 쪽 {len(out_lo)} 큰 쪽 {len(out_hi)}",
          [hc.hms(w[0]) for w in out_lo[:4]], [hc.hms(w[0]) for w in out_hi[:4]])
    if "--write" in sys.argv:
        p = hc.CONFIG / f"{gid}.json"
        d = hc.jload(p)
        d["sheet_band"] = sb
        d["sheet_band_note"] = (f"bandfit.py: 줄 범위 0.5~99.5백분위 {lo_p}~{hi_p}(최소·최대 {int(lo_a.min())}~{int(hi_a.max())}, 원본 줄 방향, {len(lo)}프레임) + 대국자 왼쪽 {LEFT_PAD}px · 오른쪽 {RIGHT_PAD}px. "
                                "구간 나누기는 band 그대로")
        hc.jsave(p, d)


if __name__ == "__main__":
    main()
