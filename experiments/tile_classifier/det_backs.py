"""뒷면 패 라벨 초안을 색으로 만든다(2026-11-03, 노트북 CPU, API 없음). 색은 이 매장 패(연보라·분홍)만 맞으므로 라벨 초안에만 쓰고 앱·서버에는 넣지 않는다.

앞면 라벨(boxes_final.json)은 그대로 두고 뒷면만 더한다. 펠트 안 연보라·분홍 덩어리를 찾아, 줄 방향으로 패 폭만큼 나눈다. 나눔 자리는 패 사이 어두운 틈에 맞춘다.
한 줄 뒷면 = 패산은 쌓인 한 묶음, 세운 손패는 패 한 장. 상자는 보이는 뒷면 색 영역만.
  python -I experiments/tile_classifier/det_backs.py [이름 ...]
결과 data/det/backs/boxes.json(이름 → 원본 좌표 x,y,w,h), masks/<이름>.png(R = 뒷면, G = 펠트, 재색칠용), check/<이름>.jpg(초록 앞면·빨강 뒷면)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = DATA / "det" / "backs"
WORK = 2040  # 재는 사진 긴 변


def back_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV_FULL).astype(np.int32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    lav = (h > 165) & (h < 205) & (s > 22) & (s < 130) & (v > 110)  # 연보라
    pink = ((h > 222) | (h < 2)) & (s > 28) & (s < 110) & (v > 130)  # 분홍. 살색(주황 쪽)과 나뉘고, 진한 빨강(리치봉·버튼)은 뺀다
    return (lav | pink).astype(np.uint8) * 255


def felt_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV_FULL).astype(np.int32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (((h > 75) & (h < 130) & (s > 50) & (v > 25)).astype(np.uint8)) * 255


def poly_mask(shape, felt, grow: float = 0.012) -> np.ndarray:
    H, W = shape[:2]
    p = np.array(felt, np.float32)
    c = p.mean(axis=0)
    p = c + (p - c) * (1 + grow)
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.round(p * [W, H]).astype(np.int32)], 255)
    return m


def valley_cuts(gray: np.ndarray, M: np.ndarray, L: int, S: int, n: int) -> list[int]:
    """곧게 편 덩어리에서 n-1 개 나눔 자리를 어두운 틈에 맞춘다."""
    strip = cv2.warpAffine(gray, M, (L, S))
    prof = cv2.GaussianBlur(strip.mean(axis=0, dtype=np.float32).reshape(1, -1), (0, 0), 1.2).ravel()
    pitch = L / n
    cuts = []
    for i in range(1, n):
        c = round(i * pitch)
        w = max(2, round(pitch * 0.3))
        a, b = max(1, c - w), min(L - 1, c + w)
        cuts.append(a + int(np.argmin(prof[a:b])) if b > a else c)
    return cuts


def straight_parts(cnt: np.ndarray, shape, tw: float, depth: int = 0) -> list[np.ndarray]:
    """ㄱ자 덩어리를 곧은 조각으로 나눈다. 안쪽 꺾인 점에서 사각형 축 두 방향으로 잘라 보고 더 꽉 찬 쪽을 고른다."""
    area = cv2.contourArea(cnt)
    (_, _), (rw, rh), ang = cv2.minAreaRect(cnt)
    if depth >= 3 or area >= 0.72 * rw * rh or len(cnt) < 5:
        return [cnt]
    defects = cv2.convexityDefects(cnt, cv2.convexHull(cnt, returnPoints=False))
    if defects is None:
        return [cnt]
    defects = defects.reshape(-1, 4)
    d = defects[np.argmax(defects[:, 3])]
    if d[3] / 256 < 0.5 * tw:
        return [cnt]
    p = cnt[d[2], 0].astype(np.float32)
    best, score = [cnt], -1.0
    rad = np.deg2rad(ang)
    for u in (np.array([np.cos(rad), np.sin(rad)]), np.array([-np.sin(rad), np.cos(rad)])):
        m = np.zeros(shape, np.uint8)
        cv2.drawContours(m, [cnt], -1, 255, -1)
        a, b = p - u * 1e4, p + u * 1e4
        cv2.line(m, tuple(np.int32(a)), tuple(np.int32(b)), 0, 3)
        parts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        parts = [q for q in parts if cv2.contourArea(q) > 0.15 * tw * tw]
        if len(parts) < 2:
            continue
        s = sum(cv2.contourArea(q) / max(1.0, cv2.minAreaRect(q)[1][0] * cv2.minAreaRect(q)[1][1]) * cv2.contourArea(q) for q in parts) / sum(cv2.contourArea(q) for q in parts)
        if s > score:
            best, score = parts, s
    if score < 0:
        return [cnt]
    return [x for q in best for x in straight_parts(q, shape, tw, depth + 1)]


def body_extent(white: np.ndarray, M: np.ndarray, x0: int, x1: int, y0: int, y1: int, L: int, S: int, th: float) -> tuple[int, int]:
    """색 영역 위아래로 붙은 흰 패 몸통까지 넓힌다. 세운 패는 색이 띠만 보이므로 패 전체를 상자로 잡는다."""
    room = int(th * 1.15)
    strip = cv2.warpAffine(white, np.vstack([M[0], M[1] + [0, 0, room]]), (L, S + 2 * room))
    top, bot = y0 + room, y1 + room
    w = strip[:, max(0, x0):max(x0 + 1, x1)]
    while top > 0 and bot - top < th * 1.15 and w[top - 1].mean() > 127:
        top -= 1
    while bot < w.shape[0] and bot - top < th * 1.15 and w[bot].mean() > 127:
        bot += 1
    return top - room, bot - room


def split_blob(cnt: np.ndarray, gray: np.ndarray, white: np.ndarray, tw: float, th: float) -> list[tuple[int, int, int, int]]:
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(cnt)
    if rw < rh:
        rw, rh, ang = rh, rw, ang + 90
    L, S = int(round(rw)), int(round(rh))
    if L < 2 or S < 2:
        return []
    # 곧게 펴는 변환: 사각형 왼위가 (0,0)
    M = cv2.getRotationMatrix2D((cx, cy), ang, 1.0)
    M[0, 2] += L / 2 - cx
    M[1, 2] += S / 2 - cy
    Mi = cv2.invertAffineTransform(M)
    rows = max(1, round(S / th)) if S > 1.6 * th else 1  # 두 줄이 붙은 덩어리
    n = max(1, round(L / tw))
    xs = [0] + (valley_cuts(gray, M, L, S, n) if n > 1 else []) + [L]
    ys = [round(i * S / rows) for i in range(rows + 1)]
    out = []
    for r in range(rows):
        for i in range(n):
            a, b = body_extent(white, M, xs[i], xs[i + 1], ys[r], ys[r + 1], L, S, th)
            q = np.array([[xs[i], a, 1], [xs[i + 1], a, 1], [xs[i + 1], b, 1], [xs[i], b, 1]], np.float32)
            p = q @ Mi.T
            x0, y0 = p.min(axis=0)
            x1, y1 = p.max(axis=0)
            out.append((int(x0), int(y0), int(x1 - x0), int(y1 - y0)))
    return out


def one(name: str, r: dict, felt: list, device: list | None) -> tuple[list, np.ndarray, np.ndarray]:
    img = cv2.imread(r["path"])
    H0, W0 = img.shape[:2]
    k = WORK / max(H0, W0)
    im = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    table = poly_mask(im.shape, felt)
    faces = np.array(r["boxes"], np.float32) * k
    short = np.minimum(faces[:, 2], faces[:, 3])
    long_ = np.maximum(faces[:, 2], faces[:, 3])
    tw, th = float(np.median(short)), float(np.median(long_))
    m = cv2.bitwise_and(back_mask(im), table)
    if device:
        m[poly_mask(im.shape, device, 0.08) > 0] = 0  # 기기 위 버튼·표시등
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    white = ((hsv[..., 1] < 50) & (hsv[..., 2] > 140)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        if cv2.contourArea(c) < 0.2 * tw * th:
            continue
        for q in straight_parts(c, m.shape, tw):
            if cv2.contourArea(q) >= 0.2 * tw * th:
                boxes += split_blob(q, gray, white, tw, th)
    fm = cv2.bitwise_and(felt_mask(im), table)
    fm = cv2.morphologyEx(fm, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    vis = im.copy()
    for x, y, w, h in faces:
        cv2.rectangle(vis, (int(x), int(y)), (int(x + w), int(y + h)), (0, 220, 0), 2)
    for x, y, w, h in boxes:
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
    cv2.imwrite(str(OUT / "check" / f"{name}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 85])
    mask = np.dstack([np.zeros_like(m), fm, m])  # BGR 로 저장: R = 뒷면, G = 펠트
    cv2.imwrite(str(OUT / "masks" / f"{name}.png"), mask)
    return [[round(v / k) for v in b] for b in boxes], vis, mask


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    (OUT / "check").mkdir(parents=True, exist_ok=True)
    (OUT / "masks").mkdir(parents=True, exist_ok=True)
    rows = json.loads((DATA / "det" / "boxes_final.json").read_text(encoding="utf-8"))
    labels = json.loads((DATA / "zone_points" / "labels.json").read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(rows)
    f = OUT / "boxes.json"
    res = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    for n in names:
        if n not in labels or not labels[n].get("felt"):
            print(n, "펠트 라벨 없음, 건너뜀")
            continue
        res[n] = one(n, rows[n], labels[n]["felt"], labels[n].get("device"))[0]
        print(n, "앞면", len(rows[n]["boxes"]), "뒷면", len(res[n]), flush=True)
    f.write_text(json.dumps(res), encoding="utf-8")


if __name__ == "__main__":
    main()
