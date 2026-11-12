"""기기 판독 실험용 OpenCV 흉내(numpy·PIL). 서버 app/ 이 쓰는 함수만: boxPoints·fillPoly·getRotationMatrix2D·getAffineTransform·
invertAffineTransform·warpAffine(INTER_LINEAR, BORDER_CONSTANT). Chaquopy 의 opencv 는 Python 3.10 용(4.5.1)뿐이라 3.13 앱에선 이것을 쓴다.

warpAffine 은 서버와 같은 OpenCV 5.0 의 float32 양선형 계산을 따라 한다(PC 무작위 시험 다른 픽셀 약 0.02%, 차이 1). PC 에서 진짜 cv2 와의 차이는 experiments/ondevice/cv2_shim_check.py 로 잰다.
"""
from __future__ import annotations

import math

import numpy as np

INTER_LINEAR = 1
BORDER_CONSTANT = 0
__version__ = "shim"


def boxPoints(box):  # noqa: N802 — OpenCV 이름 그대로
    """RotatedRect::points 와 같은 순서·float32 계산."""
    (cx, cy), (w, h), angle = box
    ang = float(angle) * math.pi / 180.0
    b = np.float32(math.cos(ang)) * np.float32(0.5)
    a = np.float32(math.sin(ang)) * np.float32(0.5)
    cx, cy, w, h = np.float32(cx), np.float32(cy), np.float32(w), np.float32(h)
    p0 = (cx - a * h - b * w, cy + b * h - a * w)
    p1 = (cx + a * h - b * w, cy - b * h - a * w)
    p2 = (np.float32(2) * cx - p0[0], np.float32(2) * cy - p0[1])
    p3 = (np.float32(2) * cx - p1[0], np.float32(2) * cy - p1[1])
    return np.array([p0, p1, p2, p3], np.float32)


def _line(m, p0, p1, val) -> None:
    """8 연결 Bresenham 선(OpenCV fillPoly 가 LINE_8 일 때 변을 먼저 긋는 것)."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x1 >= x0 else -1), (1 if y1 >= y0 else -1)
    H, W = m.shape[:2]
    err, x, y = dx - dy, x0, y0
    while True:
        if 0 <= x < W and 0 <= y < H:
            m[y, x] = val
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy


def fillPoly(img, pts, color):  # noqa: N802
    """OpenCV fillPoly(LINE_8, shift 0) 흉내: 16.16 고정 소수점 변으로 한 줄씩 채우고 변을 8 연결 선으로 긋는다.
    PC 무작위 회전 상자 500개에서 진짜와 다른 픽셀 약 0.2%."""
    H, W = img.shape[:2]
    val = int(color if np.isscalar(color) else color[0])
    for poly in pts:
        P = [(int(x), int(y)) for x, y in np.asarray(poly).reshape(-1, 2)]
        n = len(P)
        edges = []
        for i in range(n):
            (x0, y0), (x1, y1) = P[i], P[(i + 1) % n]
            if y0 == y1:
                continue
            if y0 > y1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            d = (x1 - x0) << 16
            q = abs(d) // (y1 - y0)
            edges.append((y0, y1, x0 << 16, q if d >= 0 else -q))
        if edges:
            for y in range(max(0, min(e[0] for e in edges)), min(H, max(e[1] for e in edges))):
                xs = sorted(e[2] + e[3] * (y - e[0]) for e in edges if e[0] <= y < e[1])
                for xa, xb in zip(xs[0::2], xs[1::2]):
                    x1, x2 = max((xa + (1 << 15)) >> 16, 0), min((xb + (1 << 15)) >> 16, W - 1)
                    if x1 <= x2:
                        img[y, x1:x2 + 1] = val
        for i in range(n):
            _line(img, P[i], P[(i + 1) % n], val)
    return img


def getRotationMatrix2D(center, angle, scale):  # noqa: N802
    ang = float(angle) * math.pi / 180.0
    alpha, beta = math.cos(ang) * scale, math.sin(ang) * scale
    cx, cy = float(center[0]), float(center[1])
    return np.array([[alpha, beta, (1 - alpha) * cx - beta * cy], [-beta, alpha, beta * cx + (1 - alpha) * cy]], np.float64)


def getAffineTransform(src, dst):  # noqa: N802
    src, dst = np.asarray(src, np.float64).reshape(3, 2), np.asarray(dst, np.float64).reshape(3, 2)
    a = np.zeros((6, 6))
    b = np.zeros(6)
    for i in range(3):
        a[2 * i, 0:3] = (src[i, 0], src[i, 1], 1)
        a[2 * i + 1, 3:6] = (src[i, 0], src[i, 1], 1)
        b[2 * i], b[2 * i + 1] = dst[i]
    return np.linalg.solve(a, b).reshape(2, 3)


def invertAffineTransform(m):  # noqa: N802
    m = np.asarray(m, np.float64)
    d = m[0, 0] * m[1, 1] - m[0, 1] * m[1, 0]
    d = 1.0 / d if d != 0 else 0.0
    a11, a22, a12, a21 = m[1, 1] * d, m[0, 0] * d, -m[0, 1] * d, -m[1, 0] * d
    b1 = -a11 * m[0, 2] - a12 * m[1, 2]
    b2 = -a21 * m[0, 2] - a22 * m[1, 2]
    return np.array([[a11, a12, b1], [a21, a22, b2]], np.float64)


def warpAffine(src, M, dsize, flags=INTER_LINEAR, borderMode=BORDER_CONSTANT, borderValue=0):  # noqa: N802, N803
    """OpenCV 5.0 warpAffine(INTER_LINEAR, BORDER_CONSTANT, uint8) 흉내: 역변환 좌표를 float32 로, 양선형 보간 뒤 반올림.
    (4.x 는 1/32 고정 소수점이었다. 서버는 opencv-python-headless 5.0.0.93.)"""
    src = np.asarray(src)
    if src.dtype != np.uint8:
        raise NotImplementedError("cv2 흉내: uint8 만")
    w, h = int(dsize[0]), int(dsize[1])
    mi = invertAffineTransform(M).astype(np.float32)
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    sx = mi[0, 0] * xs + mi[0, 1] * ys + mi[0, 2]
    sy = mi[1, 0] * xs + mi[1, 1] * ys + mi[1, 2]
    x0 = np.floor(sx).astype(np.int64)
    y0 = np.floor(sy).astype(np.int64)
    fx = (sx - x0).astype(np.float32)[..., None]
    fy = (sy - y0).astype(np.float32)[..., None]
    H, W = src.shape[:2]
    ch = 1 if src.ndim == 2 else src.shape[2]
    s = src.reshape(H, W, ch).astype(np.float32)
    bv = np.asarray([borderValue] * ch if np.isscalar(borderValue) else list(borderValue)[:ch], np.float32)

    def tap(yy, xx):
        ok = (xx >= 0) & (xx < W) & (yy >= 0) & (yy < H)
        v = s[np.clip(yy, 0, H - 1), np.clip(xx, 0, W - 1)]
        return np.where(ok[..., None], v, bv)

    v00, v01, v10, v11 = tap(y0, x0), tap(y0, x0 + 1), tap(y0 + 1, x0), tap(y0 + 1, x0 + 1)
    a = v00 + fx * (v01 - v00)
    b = v10 + fx * (v11 - v10)
    out = np.clip(np.rint(a + fy * (b - a)), 0, 255).astype(np.uint8)
    return out.reshape(h, w) if src.ndim == 2 else out
