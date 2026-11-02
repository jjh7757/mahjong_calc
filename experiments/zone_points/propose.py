"""탁자 8점 라벨 초안을 색으로 만든다(2026-11-02, API 없음). 펠트 네 모서리 + 리치봉 기기 네 모서리, 사진 기준 왼위부터 시계 방향.
모델 학습 재료의 초안이자, 모델 없이 색만으로 어디까지 되는지 보는 비교값이다. 사진을 긴 변 1020 으로 줄여 잰다.
  python -I experiments/zone_points/propose.py
결과 tile_classifier/data/zone_points/proposals.json: 이름 → part·src·size·felt·device(원본 비율 좌표 0~1, 못 찾으면 null)
10-24 삼각대 15장은 테스트 세트라 넣지 않고, 10-29·10-30 기록은 갤러리를 다시 읽은 것·천장 사진이라 뺀다.
"""
from __future__ import annotations

import glob
import io
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "experiments" / "tile_classifier" / "data" / "zone_points"
LONG = 1020
RECT = 1000  # 편 그림 한 변
SHOOT = ROOT / "experiments" / "visit_20261031" / "captures"
GALLERY = ROOT / "experiments" / "field_20261024" / "kakao_photos"


def sources() -> dict:
    """이름 → part(am·pm·gal)·kind·src. 프레임은 src = [zip, 파일]."""
    out = {}
    for d in sorted(SHOOT.glob("20261031_1*")):
        if d.name.endswith("_track") or not (d / "original.jpg").exists():
            continue
        out[d.name] = {"part": "am" if d.name < "20261031_14" else "pm", "kind": "photo", "src": str(d / "original.jpg")}
    for p in sorted(GALLERY.glob("k*.jpg")):
        out[p.stem] = {"part": "gal", "kind": "photo", "src": str(p)}
    for z in sorted(glob.glob(str(SHOOT / "20261031_*_track" / "frames_*.zip"))):
        with zipfile.ZipFile(z) as zf:
            meta = json.loads(zf.read("frames.json"))
        rec = Path(z).parent.name[:15]
        for f in meta["frames"]:
            hhmm = f["at"][11:16].replace(":", "")
            out[f"f{rec[9:]}_{f['file'][1:5]}"] = {"part": "am" if hhmm < "1400" else "pm", "kind": "frame", "src": [z, f["file"]], "at": f["at"][11:19], "why": f.get("why", [])}
    return out


def load(src) -> Image.Image:
    if isinstance(src, list):
        with zipfile.ZipFile(src[0]) as zf:
            return Image.open(io.BytesIO(zf.read(src[1]))).convert("RGB")
    return Image.open(src).convert("RGB")


def _line_fit(pts: np.ndarray) -> tuple[float, float, float]:
    """점들에 맞는 직선 ax + by = c. 벗어난 점(손·패)을 두 번 걸러 낸다."""
    keep = pts
    for th in (6.0, 3.0):
        vx, vy, x0, y0 = cv2.fitLine(keep.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        a, b = -vy, vx
        c = a * x0 + b * y0
        d = np.abs(pts @ np.array([a, b]) - c)
        k2 = pts[d < th]
        if len(k2) >= 8:
            keep = k2
    return float(a), float(b), float(c)


def _meet(l1, l2):
    a = np.array([[l1[0], l1[1]], [l2[0], l2[1]]])
    if abs(np.linalg.det(a)) < 1e-6:
        return None
    return np.linalg.solve(a, np.array([l1[2], l2[2]]))


def order_cw(q: np.ndarray) -> np.ndarray:
    """가운데 기준 각도로 왼위부터 시계 방향."""
    c = q.mean(0)
    ang = np.arctan2(q[:, 1] - c[1], q[:, 0] - c[0])
    q = q[np.argsort(ang)]
    start = int(np.argmin(q[:, 0] + q[:, 1]))
    return np.roll(q, -start, axis=0)


def felt_quad(rgb: np.ndarray) -> np.ndarray | None:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = ((h > 55) & (h < 95) & (s > 70) & (v > 40)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[big, cv2.CC_STAT_AREA] < 0.08 * mask.size:
        return None
    cnt = max(cv2.findContours((lab == big).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea)
    hull = cv2.convexHull(cnt)
    # 볼록 껍질을 4각형으로 줄인 뒤, 변마다 윤곽 점으로 직선을 다시 맞춘다.
    peri = cv2.arcLength(hull, True)
    approx = None
    for k in np.linspace(0.01, 0.12, 45):
        ap = cv2.approxPolyDP(hull, k * peri, True)
        if len(ap) == 4:
            approx = ap.reshape(-1, 2).astype(np.float64)
            break
    if approx is None:
        return None
    approx = order_cw(approx)
    pts = cnt.reshape(-1, 2).astype(np.float64)
    H, W = rgb.shape[:2]
    # 사진 끝에 닿은 윤곽은 펠트 변이 아니다.
    pts = pts[(pts[:, 0] > 1) & (pts[:, 0] < W - 2) & (pts[:, 1] > 1) & (pts[:, 1] < H - 2)]
    rng = np.random.default_rng(0)
    lines = []
    for i in range(4):
        a, b = approx[i], approx[(i + 1) % 4]
        d = b - a
        ln = np.hypot(*d)
        t = (pts - a) @ d / ln**2
        dist = np.abs((pts - a) @ np.array([-d[1], d[0]]) / ln)
        # 손·모서리 패가 껍질을 끌어도 곧은 구간이 가장 많은 점을 모으는 직선을 고른다.
        sel = pts[(t > -0.05) & (t < 1.05) & (dist < 0.08 * ln)]
        best, best_n = None, 0
        if len(sel) >= 25:
            for _ in range(400):
                p, q = sel[rng.choice(len(sel), 2, replace=False)]
                v = q - p
                n = np.hypot(*v)
                if n < 0.15 * ln or abs(v @ d) / (n * ln) < 0.97:  # 변 방향에서 약 14° 넘게 벗어난 짝은 버림
                    continue
                nv = np.array([-v[1], v[0]]) / n
                cnt_in = int((np.abs((sel - p) @ nv) < 2.0).sum())
                if cnt_in > best_n:
                    best, best_n = (nv, p), cnt_in
        if best is None or best_n < 25:
            lines.append((float(-d[1] / ln), float(d[0] / ln), float((-d[1] * a[0] + d[0] * a[1]) / ln)))
        else:
            nv, p = best
            lines.append(_line_fit(sel[np.abs((sel - p) @ nv) < 3.0]))
    q = [_meet(lines[i - 1], lines[i]) for i in range(4)]
    if any(p is None for p in q):
        return None
    return order_cw(np.array(q))


def device_quad(rgb: np.ndarray, felt: np.ndarray) -> np.ndarray | None:
    """펠트를 편 그림의 가운데에서 남색 기기를 찾아 원래 사진 좌표로."""
    dst = np.array([[0, 0], [RECT, 0], [RECT, RECT], [0, RECT]], np.float32)
    M = cv2.getPerspectiveTransform(felt.astype(np.float32), dst)
    flat = cv2.warpPerspective(rgb, M, (RECT, RECT), flags=cv2.INTER_LINEAR)
    c0, c1 = int(RECT * 0.33), int(RECT * 0.67)
    hsv = cv2.cvtColor(flat[c0:c1, c0:c1], cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = ((h > 100) & (h < 135) & (s > 60) & (v < 140)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    # 기기 조각들(강 패로 나뉨)을 함께 쓰되 작은 티끌은 뺀다.
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 60]
    if not keep:
        return None
    pts = np.column_stack(np.where(np.isin(lab, keep)))[:, ::-1].astype(np.float32)
    if len(pts) < 400:
        return None
    # 편 그림에서 기기는 탁자와 나란하다: 각 변을 바깥쪽 백분위 값으로 잡는다.
    x0, x1 = np.percentile(pts[:, 0], [0.5, 99.5])
    y0, y1 = np.percentile(pts[:, 1], [0.5, 99.5])
    if min(x1 - x0, y1 - y0) < 60 or max(x1 - x0, y1 - y0) / min(x1 - x0, y1 - y0) > 1.35:
        return None
    sq = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float32) + c0
    return cv2.perspectiveTransform(sq.reshape(-1, 1, 2), np.linalg.inv(M)).reshape(-1, 2)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    DATA.mkdir(parents=True, exist_ok=True)
    src = sources()
    out = {}
    for i, (name, r) in enumerate(src.items()):
        im = load(r["src"])
        W, H = im.size
        s = LONG / max(W, H)
        small = np.asarray(im.resize((round(W * s), round(H * s))))
        h, w = small.shape[:2]
        felt = felt_quad(small)
        dev = device_quad(small, felt) if felt is not None else None
        norm = lambda q: None if q is None else [[round(float(x) / w, 5), round(float(y) / h, 5)] for x, y in q]
        out[name] = {**r, "size": [W, H], "felt": norm(felt), "device": norm(dev)}
        if i % 200 == 0:
            print(i, len(src), name, flush=True)
    (DATA / "proposals.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    for part in ("am", "pm", "gal"):
        rows = [r for r in out.values() if r["part"] == part]
        print(part, len(rows), "펠트", sum(r["felt"] is not None for r in rows), "기기", sum(r["device"] is not None for r in rows))


if __name__ == "__main__":
    main()
