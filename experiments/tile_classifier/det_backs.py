"""뒷면 패 라벨 초안을 만든다(2026-11-03, 노트북 CPU, API 없음). 색은 이 매장 패(연보라·분홍)만 맞으므로 라벨 초안에만 쓰고 앱·서버에는 넣지 않는다.

앞면 라벨은 data/det/boxes_final.json 에 fixes_faces 를 더한 값, 뒷면은 아래처럼 만든다.
상자 규칙: 패산은 쌓인 한 묶음에 한 상자, 세운 손패는 한 장에 한 상자. 보이는 전체(색 면·흰 몸통·옆면)를 빈틈없이 감싼다.
찾는 법: 탁자 위 "뒷면 색 + 흰색" 에서 앞면 상자·기기·살색을 뺀 덩어리 중 뒷면 색이 있는 것 → ㄱ자는 곧은 조각으로 → 줄마다 패 간격을 자기상관으로 재서 나눔 → 나눈 칸 안 패 픽셀로 상자를 조임.
독립 평가(backs/label_review.md)의 지적을 반영했다: 어두운 뒷면 포함, 펠트 밖 허용, 사진 전체 패 폭 대신 줄별 간격, 옆면 줄무늬 조각 제거, 빈 펠트 상자 제거.
  python -I experiments/tile_classifier/det_backs.py [이름 ...]
결과 data/det/backs/boxes.json(이름 → x,y,w,h 원본 좌표), masks/<이름>.png(R = 뒷면 색, G = 펠트, 재색칠용), check/<이름>.jpg(초록 앞면·빨강 뒷면·번호)
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
# 독립 평가 M6: 패가 아닌 앞면 상자는 지우고, 빠진 앞면 패는 더한다. 원본 좌표 x,y,w,h
FACE_REMOVE = {"k15": [[2304, 1132, 56, 76]], "k26": [[2284, 1133, 56, 75], [0, 2978, 167, 22]], "k28": [[2189, 1155, 53, 74]], "20261031_124654": [[2946, 2902, 220, 94]],
               "20261031_170105": [[1382, 1973, 192, 187]]}  # 170105: 기울어 붙은 5삭·5통 2장을 상자 하나로 묶은 라벨(OBB 독립 검수 #55, 11-04) → 아래 FACE_ADD 2개로
FACE_ADD = {"20261031_125839": [[1713, 170, 82, 132], [1792, 170, 84, 132]], "20261031_174020": [[2565, 1275, 155, 145]],
            "20261031_170105": [[1382, 1966, 145, 141], [1434, 2024, 143, 141]]}


def fixed_faces(name: str, boxes: list) -> list:
    rm = [list(b) for b in FACE_REMOVE.get(name, [])]  # 더한 뒤 지운다 — 예전에 FACE_ADD 로 더한 상자도 전수 조사에서 지울 수 있게
    return [b for b in list(boxes) + FACE_ADD.get(name, []) if list(b) not in rm]


# 뒷면 라벨(표 1-54 검수 2차 backs/r2/boxes_r2fb.json) 고치기 — 7회차 전수 조사(11-04)
BACK_REMOVE: dict = {}
BACK_ADD: dict = {}
# 전수 조사 결과(det_audit_apply.py apply 가 쓰는 data/det/obb/audit/fixes.json)를 위 표에 더한다
_AUDIT = Path(__file__).resolve().parent / "data" / "det" / "obb" / "audit" / "fixes.json"
if _AUDIT.exists():
    for _k, _d in json.loads(_AUDIT.read_text(encoding="utf-8")).items():
        if _k in ("FACE_REMOVE", "FACE_ADD", "BACK_REMOVE", "BACK_ADD"):
            for _n, _bs in _d.items():
                globals()[_k].setdefault(_n, []).extend(_bs)


def fixed_backs(name: str, boxes: list) -> list:
    rm = [list(b) for b in BACK_REMOVE.get(name, [])]
    return [list(b) for b in list(boxes) + BACK_ADD.get(name, []) if list(b) not in rm]


def hsv_of(bgr: np.ndarray) -> tuple:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV_FULL).astype(np.int32)
    return hsv[..., 0], hsv[..., 1], hsv[..., 2]


def back_mask(bgr: np.ndarray, loose: bool = False) -> np.ndarray:
    h, s, v = hsv_of(bgr)
    if loose:  # 그늘진 뒷면까지
        lav = (h > 160) & (h < 212) & (s > 14) & (s < 150) & (v > 45)
        pink = ((h > 215) | (h < 3)) & (s > 18) & (s < 125) & (v > 60)
    else:
        lav = (h > 165) & (h < 205) & (s > 22) & (s < 130) & (v > 110)
        pink = ((h > 222) | (h < 2)) & (s > 28) & (s < 110) & (v > 130)  # 살색(주황 쪽)과 나뉘고, 진한 빨강(리치봉·버튼)은 뺀다
    return (lav | pink).astype(np.uint8) * 255


def white_mask(bgr: np.ndarray) -> np.ndarray:
    _, s, v = hsv_of(bgr)
    return ((s < 45) & (v > 125)).astype(np.uint8) * 255


def skin_mask(bgr: np.ndarray) -> np.ndarray:
    h, s, v = hsv_of(bgr)
    m = ((h >= 3) & (h < 32) & (s > 40) & (v > 70)).astype(np.uint8) * 255
    return cv2.dilate(m, np.ones((5, 5), np.uint8))


def felt_mask(bgr: np.ndarray) -> np.ndarray:
    h, s, v = hsv_of(bgr)
    return ((h > 75) & (h < 130) & (s > 50) & (v > 25)).astype(np.uint8) * 255


def poly_mask(shape, felt, grow: float = 0.012) -> np.ndarray:
    H, W = shape[:2]
    p = np.array(felt, np.float32)
    c = p.mean(axis=0)
    p = c + (p - c) * (1 + grow)
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [np.round(p * [W, H]).astype(np.int32)], 255)
    return m


def straight_parts(cnt: np.ndarray, shape, tw: float, depth: int = 0) -> list[np.ndarray]:
    """ㄱ자 덩어리를 곧은 조각으로 나눈다. 안쪽 꺾인 점에서 사각형 축 두 방향으로 잘라 보고 더 꽉 찬 쪽을 고른다."""
    area = cv2.contourArea(cnt)
    (_, _), (rw, rh), ang = cv2.minAreaRect(cnt)
    if depth >= 4 or area >= 0.7 * rw * rh or len(cnt) < 5:
        return [cnt]
    defects = cv2.convexityDefects(cnt, cv2.convexHull(cnt, returnPoints=False))
    if defects is None:
        return [cnt]
    defects = defects.reshape(-1, 4)
    d = defects[np.argmax(defects[:, 3])]
    if d[3] / 256 < 1.1 * tw:  # 패 줄의 들쭉날쭉한 가장자리는 자르지 않는다
        return [cnt]
    p = cnt[d[2], 0].astype(np.float32)
    best, score = [cnt], -1.0
    rad = np.deg2rad(ang)
    for u in (np.array([np.cos(rad), np.sin(rad)]), np.array([-np.sin(rad), np.cos(rad)])):
        m = np.zeros(shape, np.uint8)
        cv2.drawContours(m, [cnt], -1, 255, -1)
        cv2.line(m, tuple(np.int32(p - u * 1e4)), tuple(np.int32(p + u * 1e4)), 0, 3)
        parts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        parts = [q for q in parts if cv2.contourArea(q) > 0.15 * tw * tw]
        if len(parts) < 2:
            continue
        total = sum(cv2.contourArea(q) for q in parts)
        s = sum(cv2.contourArea(q) ** 2 / max(1.0, cv2.minAreaRect(q)[1][0] * cv2.minAreaRect(q)[1][1]) for q in parts) / total
        if s > score:
            best, score = parts, s
    if score < 0:
        return [cnt]
    return [x for q in best for x in straight_parts(q, shape, tw, depth + 1)]


def pitch_of(prof: np.ndarray, tw: float) -> float:
    """줄 방향 밝기의 자기상관으로 패 간격을 잰다. 뚜렷하지 않으면 사진 중앙값 폭."""
    L = len(prof)
    lo, hi = int(tw * 0.72), int(tw * 1.32)
    if L < 2.5 * tw or hi >= L - 1:
        return tw
    p = prof - cv2.GaussianBlur(prof.reshape(1, -1), (0, 0), max(2.0, tw * 0.6)).ravel()
    best, score = tw, 0.2  # 상관 0.2 미만은 믿지 않는다
    for lag in range(lo, hi + 1):
        a, b = p[:-lag], p[lag:]
        den = float(np.sqrt((a * a).sum() * (b * b).sum()))
        c = float((a * b).sum()) / den if den > 0 else 0.0
        if c > score:
            best, score = float(lag), c
    return best


def cuts_at(prof: np.ndarray, n: int) -> list[int]:
    L = len(prof)
    pitch = L / n
    p = cv2.GaussianBlur(prof.reshape(1, -1), (0, 0), 1.2).ravel()
    out = [0]
    for i in range(1, n):
        c = round(i * pitch)
        w = max(2, round(pitch * 0.25))
        a, b = max(1, c - w), min(L - 1, c + w)
        out.append(a + int(np.argmin(p[a:b])) if b > a else c)
    return out + [L]


def split_blob(cnt: np.ndarray, gray: np.ndarray, body: np.ndarray, tw: float, th: float) -> list[tuple[int, int, int, int]]:
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(cnt)
    if rw < rh:
        rw, rh, ang = rh, rw, ang + 90
    L, S = int(round(rw)), int(round(rh))
    if L < 4 or S < 4:
        return []
    M = cv2.getRotationMatrix2D((cx, cy), ang, 1.0)
    M[0, 2] += L / 2 - cx
    M[1, 2] += S / 2 - cy
    strip = cv2.warpAffine(gray, M, (L, S)).astype(np.float32)
    mask = cv2.warpAffine(body, M, (L, S), flags=cv2.INTER_NEAREST)
    Mi = cv2.invertAffineTransform(M)
    rows = 2 if S > 1.9 * th else 1  # 두 줄이 붙은 덩어리
    ys = cuts_at(strip.mean(axis=1), rows) if rows > 1 else [0, S]
    out = []
    for r in range(rows):
        part = strip[ys[r]:ys[r + 1]]
        prof = part.mean(axis=0)
        pitch = pitch_of(prof, tw)
        n = max(1, round(L / pitch))
        xs = cuts_at(prof, n) if n > 1 else [0, L]
        for i in range(n):
            cell = mask[ys[r]:ys[r + 1], xs[i]:xs[i + 1]]
            if cell.size == 0 or (cell > 0).mean() < 0.3:  # 대부분 빈 펠트
                continue
            yy, xx = np.nonzero(cell)
            q = np.stack([xx + xs[i], yy + ys[r], np.ones_like(xx)], axis=1).astype(np.float32)
            p = q @ Mi.T
            x0, y0 = p.min(axis=0)
            x1, y1 = p.max(axis=0)
            out.append((int(x0), int(y0), int(x1 - x0 + 1), int(y1 - y0 + 1)))
    return out


def one(name: str, r: dict, felt: list, device: list | None) -> list:
    img = cv2.imread(r["path"])
    H0, W0 = img.shape[:2]
    k = WORK / max(H0, W0)
    im = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    faces = np.array(fixed_faces(name, r["boxes"]), np.float32) * k
    tw, th = float(np.median(np.minimum(faces[:, 2], faces[:, 3]))), float(np.median(np.maximum(faces[:, 2], faces[:, 3])))
    colour_wide = cv2.bitwise_and(back_mask(im, loose=True), poly_mask(im.shape, felt, 0.05))  # 테두리에 걸친 패
    white = cv2.bitwise_and(white_mask(im), poly_mask(im.shape, felt, 0.0))
    body = cv2.bitwise_or(colour_wide, white)
    body[skin_mask(im) > 0] = 0
    if device:
        body[poly_mask(im.shape, device, 0.08) > 0] = 0  # 기기 위 버튼·표시등
    for x, y, w, h in faces:  # 앞면 패와 그 옆면
        body[int(max(0, y - 2)):int(y + h + 2), int(max(0, x - 2)):int(x + w + 2)] = 0
    body = cv2.morphologyEx(body, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    body = cv2.morphologyEx(body, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    strict = cv2.bitwise_and(back_mask(im), body)
    cnts, _ = cv2.findContours(body, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        for q in straight_parts(c, body.shape, tw):
            area = cv2.contourArea(q)
            if area < 0.35 * tw * th:  # 옆면 줄무늬·작은 조각
                continue
            m = np.zeros(body.shape, np.uint8)
            cv2.drawContours(m, [q], -1, 255, -1)
            colour = cv2.countNonZero(cv2.bitwise_and(strict, m))
            if colour < 0.08 * area:  # 뒷면 색이 없으면 패 옆면·종이 등
                continue
            boxes += [b for b in split_blob(q, gray, cv2.bitwise_and(body, m), tw, th) if b[2] * b[3] >= 0.3 * tw * th and min(b[2], b[3]) >= 0.35 * tw]  # 앞면 패 옆면의 색 띠
    fm = cv2.morphologyEx(cv2.bitwise_and(felt_mask(im), poly_mask(im.shape, felt)), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    box_area = np.zeros(body.shape, np.uint8)
    for x, y, w, h in boxes:
        box_area[y:y + h, x:x + w] = 255
    colour = cv2.bitwise_and(back_mask(im, loose=True), box_area)
    vis = im.copy()
    for x, y, w, h in faces:
        cv2.rectangle(vis, (int(x), int(y)), (int(x + w), int(y + h)), (0, 220, 0), 2)
    for i, (x, y, w, h) in enumerate(boxes):
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(vis, str(i), (x + 2, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite(str(OUT / "check" / f"{name}.jpg"), vis, [cv2.IMWRITE_JPEG_QUALITY, 85])
    cv2.imwrite(str(OUT / "masks" / f"{name}.png"), np.dstack([np.zeros_like(colour), fm, colour]))  # BGR: R = 뒷면, G = 펠트
    return [[round(v / k) for v in b] for b in boxes]


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
        res[n] = one(n, rows[n], labels[n]["felt"], labels[n].get("device"))
        print(n, "뒷면", len(res[n]), flush=True)
    f.write_text(json.dumps(res), encoding="utf-8")


if __name__ == "__main__":
    main()
