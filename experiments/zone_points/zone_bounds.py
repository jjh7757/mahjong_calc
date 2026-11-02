"""구역별 상한·하한을 잰다(2026-11-02, 사용자 제안 "모두 아우르는 격자", API 없음). labels.json 펠트로 전 사진을 편 뒤 네 변을 "아래 자리" 기준으로 돌려 쌓는다.
좌표: d = 그 자리 쪽 가운데 거리(편 좌표, 0.5 = 펠트 끝, 넘으면 흰 테두리), a = 그 사람 기준 옆(+ 가 오른쪽 = 울기 놓는 쪽).
앞면 패 = 검토한 패 상자(det/boxes_final.json, 사진 35장). 뒷면 = 분홍·연보라 색(사진 + 프레임 358장).
  python -X utf8 experiments/zone_points/zone_bounds.py [그림 앞이름]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones as z  # noqa: E402
from propose import DATA, load  # noqa: E402

SPAN = (-0.2, 1.2)  # 편 좌표에서 볼 범위(펠트 0~1, 바깥은 흰 테두리)
SIZE = 560
SIDES = ("bottom", "right", "top", "left")


def seat_coords(u: np.ndarray, v: np.ndarray, side: str) -> tuple[np.ndarray, np.ndarray]:
    """편 좌표 → (a 옆, d 거리)."""
    x, y = u - 0.5, v - 0.5
    return {"bottom": (x, y), "right": (-y, x), "top": (-x, -y), "left": (y, -x)}[side]


def side_of(u: float, v: float) -> str:
    x, y = u - 0.5, v - 0.5
    if abs(y) >= abs(x):
        return "bottom" if y > 0 else "top"
    return "right" if x > 0 else "left"


def back_mask(rgb: np.ndarray) -> np.ndarray:
    """분홍·연보라 뒷면."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    lav = (h > 112) & (h < 135) & (s > 25) & (s < 130) & (v > 120)
    pink = (h > 155) & (h < 178) & (s > 25) & (s < 130) & (v > 130)
    return lav | pink


def rectify(r: dict) -> np.ndarray:
    im = np.asarray(load(r["src"]).convert("RGB"))
    H, W = im.shape[:2]
    f = (np.array(r["felt"]) * [W, H]).astype(np.float32)
    k = SIZE / (SPAN[1] - SPAN[0])
    dst = (z.UNIT - SPAN[0]) * k
    return cv2.warpPerspective(im, cv2.getPerspectiveTransform(f, dst.astype(np.float32)), (SIZE, SIZE))


def pct(v, q) -> str:
    return " ".join(f"{np.percentile(v, p):+.3f}" for p in q)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    prefix = sys.argv[1] if len(sys.argv) > 1 else None
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    boxes = json.loads((DATA.parent / "det" / "boxes_final.json").read_text(encoding="utf-8"))

    # 앞면 패: 자리 기준 (a, d, 상자 가까운 끝·먼 끝, 설치, 사진)
    rows = []
    for n, b in boxes.items():
        if n not in labels:
            continue
        r = labels[n]
        W, H = r["size"]
        inv = np.linalg.inv(z.to_image(r["felt"]))
        for x, y, w, h in b["boxes"]:
            c = z.project(inv, [[(x + w / 2) / W, (y + h / 2) / H]])[0]
            corners = z.project(inv, [[x / W, y / H], [(x + w) / W, y / H], [(x + w) / W, (y + h) / H], [x / W, (y + h) / H]])
            side = side_of(*c)
            ca, cd = seat_coords(c[0], c[1], side)
            ka, kd = seat_coords(corners[:, 0], corners[:, 1], side)
            rows.append((float(ca), float(cd), float(kd.min()), float(kd.max()), float(ka.min()), float(ka.max()), r["setup"], n))
    A = np.array([t[:6] for t in rows])
    setups = np.array([t[6] for t in rows])
    print(f"앞면 패 상자 {len(A)}개, 사진 {len({t[7] for t in rows})}장")
    print("\n[앞면 패 가운데 거리 d 분포] 0.02 칸")
    hist, e = np.histogram(A[:, 1], bins=np.arange(0.06, 0.70, 0.02))
    for h, a in zip(hist, e):
        print(f" {a:.2f} {h:4d} " + "#" * (h // 8))

    river = A[:, 1] < 0.27
    outer = A[:, 1] > 0.30
    print("\n[강(가운데 거리 < 0.27)] 개수", int(river.sum()))
    print(" 상자 안쪽 끝 d 최소·p1:", f"{A[river, 2].min():.3f} {np.percentile(A[river, 2], 1):.3f}", " 바깥쪽 끝 d p99·최대:", f"{np.percentile(A[river, 3], 99):.3f} {A[river, 3].max():.3f}")
    print(" 옆 a p1·최소:", f"{np.percentile(A[river, 4], 1):+.3f} {A[river, 4].min():+.3f}", " p99·최대:", f"{np.percentile(A[river, 5], 99):+.3f} {A[river, 5].max():+.3f}")
    print("\n[바깥 앞면 패(손패·울기·떼어 둔 패·표시패, d > 0.30)] 개수", int(outer.sum()))
    print(" 안쪽 끝 d 최소·p1·p5:", f"{A[outer, 2].min():.3f} {np.percentile(A[outer, 2], 1):.3f} {np.percentile(A[outer, 2], 5):.3f}", " 바깥 끝 d p99·최대:", f"{np.percentile(A[outer, 3], 99):.3f} {A[outer, 3].max():.3f}")
    print(" 옆 a 최소·최대:", f"{A[outer, 4].min():+.3f} {A[outer, 5].max():+.3f}")
    corner = outer & (A[:, 0] > 0.30)
    print(" 그중 오른쪽 모서리(a > 0.30) 개수", int(corner.sum()), "d 범위", f"{A[corner, 2].min():.3f}~{A[corner, 3].max():.3f}" if corner.any() else "", "a 범위", f"{A[corner, 4].min():+.3f}~{A[corner, 5].max():+.3f}" if corner.any() else "")
    gap = (A[:, 1] >= 0.24) & (A[:, 1] <= 0.34)
    print(" 강과 바깥 사이(0.24~0.34) 패", int(gap.sum()), "장, 사진", sorted({rows[i][7][-6:] for i in np.where(gap)[0]}))

    print("\n[설치별 앞면 패] 강 바깥 끝 최대 / 바깥 패 안쪽 끝 최소 → 그 설치에서 선을 그을 수 있는 폭")
    for s in sorted(set(setups)):
        m = setups == s
        ri, ou = m & river, m & outer
        print(f" {s}: 강 끝 {A[ri, 3].max():.3f} / 바깥 시작 {A[ou, 2].min():.3f}, 폭 {A[ou, 2].min() - A[ri, 3].max():+.3f}")

    # 뒷면: 전 사진 쌓기
    bg = np.zeros((SIZE, SIZE), np.float64)
    fg = np.zeros((SIZE, SIZE), np.float64)
    avg = np.zeros((SIZE, SIZE, 3), np.float64)
    by_setup: dict[str, np.ndarray] = {}
    n_setup: dict[str, int] = {}
    for n, r in labels.items():
        flat = rectify(r)
        m = back_mask(flat).astype(np.float64)
        bg += m
        avg += flat
        by_setup[r["setup"]] = by_setup.get(r["setup"], 0) + m
        n_setup[r["setup"]] = n_setup.get(r["setup"], 0) + 1
    N = len(labels)
    k = SIZE / (SPAN[1] - SPAN[0])
    ys, xs = np.mgrid[0:SIZE, 0:SIZE]
    U, V = xs / k + SPAN[0], ys / k + SPAN[0]
    rr = np.maximum(np.abs(U - 0.5), np.abs(V - 0.5))
    print("\n[뒷면 색 빈도: 가운데 거리별 그 띠에서 뒷면 색이 나온 넓이 비율, 358장 평균 %] (패산·세운 손패)")
    for lo in np.arange(0.10, 0.70, 0.04):
        band = (rr >= lo) & (rr < lo + 0.04)
        print(f" {lo:.2f}~{lo + 0.04:.2f}: {bg[band].mean() / N * 100:5.2f}% " + "#" * int(bg[band].mean() / N * 200))
    print("\n[설치별 뒷면 색이 시작되는 d: 띠 넓이 비율이 1% 넘는 첫 칸, 1% 아래로 떨어지는 마지막 칸]")
    for s, m in sorted(by_setup.items()):
        vals = [(lo, m[(rr >= lo) & (rr < lo + 0.02)].mean() / n_setup[s]) for lo in np.arange(0.10, 0.70, 0.02)]
        on = [lo for lo, v in vals if v > 0.01]
        print(f" {s}({n_setup[s]}장): {on[0]:.2f} ~ {on[-1] + 0.02:.2f}" if on else f" {s}: 없음")

    if prefix:
        view = (avg / N).astype(np.uint8)
        heat = cv2.applyColorMap((np.clip(bg / N * 3, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)[..., ::-1]
        faces = np.zeros((SIZE, SIZE), np.float64)
        for n, b in boxes.items():
            if n not in labels:
                continue
            r = labels[n]
            W, H = r["size"]
            inv = np.linalg.inv(z.to_image(r["felt"]))
            for x, y, w, h in b["boxes"]:
                c = z.project(inv, [[(x + w) / W, y / H], [(x + w) / W, (y + h) / H], [x / W, (y + h) / H], [x / W, y / H]])
                poly = ((c - SPAN[0]) * k).astype(np.int32)
                tmp = np.zeros((SIZE, SIZE), np.uint8)
                cv2.fillPoly(tmp, [poly], 1)
                faces += tmp
        fheat = cv2.applyColorMap((np.clip(faces / max(faces.max(), 1) * 2, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)[..., ::-1]
        def marks(o):
            o = o.copy()
            px = lambda t: int((t - SPAN[0]) * k)
            for d, col in ((0.0985, (255, 0, 255)), (0.24, (255, 255, 255)), (0.30, (255, 255, 0)), (0.40, (0, 255, 255)), (0.50, (0, 255, 0))):
                cv2.rectangle(o, (px(0.5 - d), px(0.5 - d)), (px(0.5 + d), px(0.5 + d)), col, 1)
            return o
        sheet = np.hstack([marks(view), marks(heat), marks(fheat)])
        cv2.imwrite(f"{prefix}.jpg", cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print("그림", f"{prefix}.jpg")


if __name__ == "__main__":
    main()
