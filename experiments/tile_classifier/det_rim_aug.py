"""펠트 가장자리·흰 테두리 위 白 증강(2026-11-04, 4회차, metrics 표 1-64). det_build.py --rim-blank 가 부른다.

표 1-62(3회차)의 문제 둘을 고친다.
1. 누수: 白 재료를 모든 사진에서 모아 시험 사진(오후·B·C·D)의 白 이 다른 fold 학습 사진에 붙었다. 이번엔 재료를 fold 별로 나눈다 —
   사본 __ra(재료 = 오전·갤러리 기타 → fold_a 학습 전용), __rb(재료 = 오후·갤러리 기타 → fold_b 학습 전용). B·C·D 의 白 은 재료로 안 쓴다.
2. 모양: 흐린 사각형(첫 시도)은 실제와 달랐다. 실제 모서리 白 퐁(164501·171245)은 둥근 모서리·패 사이 회색 홈·옆으로 보이는 분홍 뒷면이 있고
   펠트 가장자리에 반쯤 걸친다. 그래서 재료를 白 면 상자를 6% 키운 크롭(모서리·홈 포함)으로 하고, 패 몸통(밝고 채도 낮은 픽셀, 가운데에 이어진 것)만 섞는다.
   (15% 는 옆 패 무늬가 딸려 왔다.) 밝기 ±6%.
놓는 곳: (a) 기존 상자 15% 를 白 으로 바꿈, (b) 펠트 경계 띠(펠트 3% 안 ~ 10% 밖, 테두리 포함) 빈자리에 白 1~4장 묶음 3개(세로·가로 무작위).
라벨은 白 면 상자(키우기 전 크기).
"""
from __future__ import annotations

import random

import cv2
import numpy as np
from PIL import Image

GROW = 0.06  # 15% 는 옆 패 무늬가 딸려 왔다(rim_sheet 확인). 둥근 모서리·홈만 남는 정도


def part(name: str) -> str:
    if name in {"k25", "k28", "k15", "k26", "k12", "k16"}:
        return "bcd"
    if name.startswith("k"):
        return "other"
    return "am" if name < "20261031_14" else "pm"


def build_bank(rows: dict, fixed_faces, is_blank) -> dict:
    """{"a": fold_a 학습에 써도 되는 白 크롭, "b": fold_b 용}. 크롭은 상자를 GROW 만큼 키운 것, 세운 모양으로."""
    src = {"am": [], "pm": [], "other": [], "bcd": []}
    for name, r in rows.items():
        im = Image.open(r["path"]).convert("RGB")
        rgb = np.asarray(im)
        for b in fixed_faces(name, r["boxes"]):
            if not is_blank(rgb, b):
                continue
            x, y, w, h = b
            g = int(GROW * max(w, h))
            c = im.crop((x - g, y - g, x + w + g, y + h + g))
            src[part(name)].append(c.rotate(90, expand=True) if w > h else c)
    return {"a": src["am"] + src["other"], "b": src["pm"] + src["other"], "_count": {k: len(v) for k, v in src.items()}}


def band_mask(rgb: np.ndarray, felt: list, boxes: list) -> np.ndarray:
    """펠트 경계 띠: 펠트를 3% 줄인 사각형 밖 · 10% 키운 사각형 안, 기존 상자(30% 키움)와 안 겹침."""
    H, W = rgb.shape[:2]
    p = np.array([[x * W, y * H] for x, y in felt], np.float32)
    c = p.mean(axis=0)
    inner = np.zeros((H, W), np.uint8)
    outer = np.zeros((H, W), np.uint8)
    cv2.fillPoly(inner, [np.round(c + (p - c) * 0.97).astype(np.int32)], 255)
    cv2.fillPoly(outer, [np.round(c + (p - c) * 1.10).astype(np.int32)], 255)
    m = cv2.bitwise_and(outer, cv2.bitwise_not(inner))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    skin = ((hsv[..., 0] <= 25) & (hsv[..., 1] >= 40) & (hsv[..., 1] <= 170) & (hsv[..., 2] >= 80)).astype(np.uint8) * 255
    m[cv2.dilate(skin, np.ones((25, 25), np.uint8)) > 0] = 0  # 손·팔 위에는 안 놓는다
    for x, y, w, h in boxes:
        g = int(0.3 * max(w, h))
        cv2.rectangle(m, (x - g, y - g), (x + w + g, y + h + g), 0, -1)
    return m


def paste(out: np.ndarray, b: tuple, crop: Image.Image, rng: random.Random) -> None:
    """白 면 상자 b 자리에 키운 크롭을 붙인다(밝기 ±6%, 가장자리 3px 흐림). 제자리 수정."""
    x, y, w, h = b
    c = crop.rotate(90, expand=True) if w > h else crop
    g = int(GROW * max(w, h))
    X0, Y0, X1, Y1 = x - g, y - g, x + w + g, y + h + g
    H, W = out.shape[:2]
    if X0 < 0 or Y0 < 0 or X1 > W or Y1 > H:
        return
    t8 = np.asarray(c.resize((X1 - X0, Y1 - Y0), Image.BILINEAR))
    tile = t8.astype(np.float32) * rng.uniform(0.94, 1.06)
    # 패 몸통만 섞는다: 밝고 채도 낮은 픽셀(흰 면·옆면) + 白 면 상자 안은 무조건. 크롭에 딸려 온 펠트·옆 패 무늬·손은 버린다.
    hsv = cv2.cvtColor(t8, cv2.COLOR_RGB2HSV)
    body = ((hsv[..., 2] >= 150) & (hsv[..., 1] <= 60)).astype(np.uint8)
    body[g:g + h, g:g + w] = 1
    ring = np.ones_like(body, bool)
    ring[g:g + h, g:g + w] = False
    body[ring & (t8.mean(axis=2) < 140)] = 0  # 여유 부분의 어두운 픽셀(옆 패 무늬·그늘 아닌 무늬)은 버린다
    n, lab, stats, _ = cv2.connectedComponentsWithStats(body)
    keep = lab == lab[g + h // 2, g + w // 2]  # 가운데(白 면)에 이어진 덩어리만
    body = cv2.morphologyEx(keep.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(np.float32)
    a = cv2.GaussianBlur(body, (0, 0), 1.5)[..., None]
    out[Y0:Y1, X0:X1] = out[Y0:Y1, X0:X1] * (1 - a) + np.clip(tile, 0, 255) * a


def augment(im: Image.Image, boxes: list, felt: list, bank: list, rng: random.Random, swap_frac: float = 0.15, groups: int = 3,
            negatives: int = 0, avoid: list | None = None) -> tuple[Image.Image, list, int]:
    """(증강 그림, 라벨 상자 = 기존 + 새 白, 새로 놓은 장수). negatives > 0 이면 패 아닌 흰 물체도 라벨 없이(5회차).
    avoid: 새 白·음성을 놓지 않을 상자(6회차 뒷면 라벨 — 덮으면 라벨이 틀어진다)."""
    avoid = [list(b) for b in (avoid or [])]
    rgb = np.asarray(im)
    out = rgb.astype(np.float32)
    tw = sorted(min(b[2], b[3]) for b in boxes)[len(boxes) // 2]
    th = sorted(max(b[2], b[3]) for b in boxes)[len(boxes) // 2]
    for b in boxes:
        if rng.random() < swap_frac:
            paste(out, tuple(b), rng.choice(bank), rng)
    mask = band_mask(rgb, felt, list(boxes) + avoid)
    ys, xs = np.nonzero(mask)
    added: list = []
    for _ in range(groups if len(xs) else 0):
        for _try in range(40):
            n = rng.choice([1, 2, 3, 3, 3, 4])
            s = rng.uniform(0.9, 1.1)
            upright = rng.random() < 0.5
            w, h = (round(tw * s), round(th * s)) if upright else (round(th * s), round(tw * s))
            along_x = rng.random() < 0.5
            gap = rng.uniform(0.0, 0.05)
            i = rng.randrange(len(xs))
            x0, y0 = int(xs[i]) - w // 2, int(ys[i]) - h // 2
            grp = [(round(x0 + k * w * (1 + gap)), y0, w, h) if along_x else (x0, round(y0 + k * h * (1 + gap)), w, h) for k in range(n)]
            g = int(GROW * max(w, h))
            inside = all(g <= b[0] and g <= b[1] and b[0] + b[2] + g < mask.shape[1] and b[1] + b[3] + g < mask.shape[0]
                         and mask[b[1]:b[1] + b[3], b[0]:b[0] + b[2]].mean() >= 0.8 * 255 for b in grp)
            free = all(max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) + 2 * g) * max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) + 2 * g) == 0
                       for a in grp for b in added)
            if inside and free:
                for b in grp:
                    paste(out, b, rng.choice(bank), rng)
                added += grp
                break
    if negatives:
        place_negatives(out, list(boxes) + added + avoid, tw, th, rng, negatives)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), [list(b) for b in boxes] + [list(b) for b in added], len(added)


def negative_patch(w: int, h: int, plain: bool, rng: random.Random) -> tuple[np.ndarray, np.ndarray]:
    """패가 아닌 흰 물체(5회차, 표 1-65): 흰·베이지·연분홍 종이·카드. (그림 float32 h×w×3, 알파 h×w).
    plain=False 면 글씨 줄·QR 같은 네모·색 줄을 찍는다(패 크기 음성은 반드시 무늬가 있게 — 무늬 없는 패 크기 흰 사각형은 白 과 같다).
    모서리는 각지게(패는 둥근 모서리), 홈·옆면 그림자 없음, 가장자리에 얇은 그림자 한쪽."""
    base = np.array(rng.choice([(245, 245, 240), (240, 228, 215), (238, 222, 222), (250, 250, 250), (230, 230, 225)]), np.float32) * rng.uniform(0.92, 1.05)
    img = np.ones((h, w, 3), np.float32) * base
    img += rng.uniform(-4, 4) * np.linspace(-1, 1, w)[None, :, None]  # 약한 밝기 기울기
    if not plain:
        ink = np.array(rng.choice([(40, 40, 40), (200, 60, 90), (60, 60, 160), (120, 120, 120)]), np.float32)
        for _ in range(rng.randint(3, 9)):  # 글씨 줄
            yy = rng.randint(int(0.1 * h), max(int(0.1 * h) + 1, int(0.9 * h)))
            x0 = rng.randint(int(0.05 * w), max(int(0.05 * w) + 1, int(0.5 * w)))
            x1 = min(w - 2, x0 + rng.randint(max(2, w // 6), max(3, int(0.8 * w))))
            t = max(1, int(rng.uniform(0.01, 0.03) * h))
            img[yy:yy + t, x0:x1] = img[yy:yy + t, x0:x1] * 0.3 + ink * 0.7
        if rng.random() < 0.5:  # QR 같은 네모
            q = max(4, int(min(w, h) * rng.uniform(0.15, 0.3)))
            qx, qy = rng.randint(0, max(0, w - q - 1)), rng.randint(0, max(0, h - q - 1))
            cells = (np.random.default_rng(rng.randint(0, 1 << 30)).random((8, 8)) < 0.5).astype(np.float32)
            img[qy:qy + q, qx:qx + q] *= 1 - 0.8 * cv2.resize(cells, (q, q), interpolation=cv2.INTER_NEAREST)[..., None]
    a = np.ones((h, w), np.float32)
    a = cv2.GaussianBlur(a, (0, 0), 0.8)
    return img, a


def place_negatives(out: np.ndarray, taken: list, tw: float, th: float, rng: random.Random, n: int) -> None:
    """라벨 없이 흰 물체 n 개를 사진 아무 데(라벨 상자와 안 겹치게)에 놓는다. 제자리 수정.
    크기·비율: 패와 다른 것(긴 변 1.4~4 배 또는 비율 2~4)은 무늬 없음도 허용, 패 크기(0.8~1.3 배, 비율 1.1~1.7)는 늘 무늬 있음."""
    H, W = out.shape[:2]
    for _ in range(n):
        for _try in range(30):
            if rng.random() < 0.5:  # 패와 다른 크기·비율 — 종이·카드·영수증
                L = th * rng.uniform(1.4, 4.0)
                S = L / rng.uniform(1.2, 4.0)
                plain = rng.random() < 0.5
            else:  # 패 크기지만 무늬 있는 종이 조각(134815 서랍 종이 조각 같은 것)
                L = th * rng.uniform(0.8, 1.3)
                S = L / rng.uniform(1.1, 1.7)
                plain = False
            w, h = (int(L), int(S)) if rng.random() < 0.5 else (int(S), int(L))
            if w < 6 or h < 6 or w >= W - 2 or h >= H - 2:
                continue
            x, y = rng.randint(0, W - w - 1), rng.randint(0, H - h - 1)
            pad = int(0.3 * max(tw, th))
            if any(x < b[0] + b[2] + pad and b[0] - pad < x + w and y < b[1] + b[3] + pad and b[1] - pad < y + h for b in taken):
                continue
            img, a = negative_patch(w, h, plain, rng)
            sh = max(1, int(0.04 * min(w, h)))  # 한쪽 얇은 그림자
            out[y + h:min(H, y + h + sh), x:x + w] *= 0.8
            out[y:y + h, x:x + w] = out[y:y + h, x:x + w] * (1 - a[..., None]) + img * a[..., None]
            taken = taken + [(x, y, w, h)]
            break
