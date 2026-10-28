"""강 끝 픽셀 방식: 강 크롭(그 자리 쪽으로 세운 가운데 칸)에서 흰 패 면을 찾아 그 사람 강의 틀(줄·칸)을 잡고,
마지막 패 한 장만 잘라 낸다. 모델은 잘라 낸 패만 읽는다(2026-10-26, 사용자 요청으로 시험).

  python experiments/speed/river_px.py debug          B·C·D 18개 크롭의 찾은 상자·줄·마지막 패를 그림으로(results/river_px/)

결과(2026-10-26, EDGE=60): 마지막 패 위치 14/18. C 오른쪽(모델이 늘 틀리던 처진 패)은 2/2 맞지만, B 위쪽(론 패 7z)은
마지막 붉은 中 을 패로 못 찾아 그 앞 패를 고름(0/2), C 위쪽은 두 줄이 상자 하나로 붙음(2/2 애매). 위치가 론 패에서 틀려
모델 읽기 단계는 돌리지 않았다 — 병목은 패 하나하나 찾기(공개 YOLO 시험과 같은 결론).

틀 잡기(정답·모델 없이):
  1) 흰 면 = 채도 낮고 밝은 픽셀. 패 사이 그늘 틈을 살리려 조금 깎은 뒤 연결 요소 → 패 크기 상자만.
  2) 그 사람 강 = 가운데 기기 아래, 사진 아래쪽 가운데에 가장 가까운 상자에서 시작해 이웃 상자(틈 < 패 반 개)로 넓힌 묶음.
  3) 줄 = 상자 가운데 y 를 패 높이 반 안쪽끼리 묶음(처진 패도 같은 줄). 줄은 위(가운데 쪽)부터, 줄 안은 왼쪽부터.
  4) 마지막 패 = 마지막 줄의 가장 오른쪽.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
OUT = ROOT / "results" / "river_px"
EDGE = 60  # >0 이면 이 세기 이상의 밝기 변화를 경계로 보고 뺀다(0·120·200 보다 60 이 패를 가장 많이 찾음)


def white_boxes(img: np.ndarray, local: int = 31, drop: int = 14, erode: int = 3) -> list[tuple[int, int, int, int]]:
    """패 면 상자들. 흰 면(채도 낮음) 중에서 주변 평균보다 [drop] 이상 어두운 얇은 선(패 사이 틈·그림 획)을 빼고,
    덩어리마다 바깥 윤곽을 채워 그림 구멍을 메운 뒤, 패 크기 덩어리만 남긴다. 사진 위치마다 밝기가 달라 기준은 주변 평균."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s, v = hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    mean = cv2.blur(v.astype(np.float32), (local, local))
    face = (s < 50) & (v > 140) & (v > mean - drop)
    if EDGE:  # 밝기 변화가 큰 곳(패 경계·그림 획)을 뺀다. 그림 구멍은 아래에서 윤곽을 채워 메운다.
        g = cv2.GaussianBlur(v.astype(np.float32), (3, 3), 0)
        mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
        face &= mag < EDGE
    mask = face.astype(np.uint8) * 255
    mask = cv2.erode(mask, np.ones((erode, erode), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    H, W = mask.shape
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        if area < (W * H) * 0.003 or w > W * 0.2 or h > H * 0.25:
            continue
        if area < 0.6 * w * h or not 0.45 < w / h < 2.2:  # 패 면은 거의 꽉 찬 사각형
            continue
        e = erode // 2
        boxes.append((x - e, y - e, w + 2 * e, h + 2 * e))
    return boxes


def own_river(boxes, W: int, H: int):
    """사진 아래쪽 가운데에 가장 가까운 '세로로 선' 상자에서 시작해 이웃으로 넓힌 묶음 = 그 사람 강."""
    if not boxes:
        return []
    upright = [b for b in boxes if b[3] > b[2]]
    ref = upright or boxes
    tw = statistics.median(b[2] for b in ref)
    th = statistics.median(b[3] for b in ref)
    cand = [b for b in boxes if b[1] + b[3] / 2 > H * 0.25]
    if not cand:
        return []
    start = min(cand, key=lambda b: abs(b[0] + b[2] / 2 - W / 2) + abs(b[1] + b[3] - H * 0.75))
    group, todo = {start}, [start]

    def gap(a, b):
        dx = max(0, max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2]))
        dy = max(0, max(a[1], b[1]) - min(a[1] + a[3], b[1] + b[3]))
        return dx, dy

    while todo:
        a = todo.pop()
        for b in boxes:
            if b in group:
                continue
            dx, dy = gap(a, b)
            if dx < tw * 0.5 and dy < th * 0.5:
                group.add(b)
                todo.append(b)
    return sorted(group, key=lambda b: (b[1], b[0])), tw, th


def frame(boxes, th: float):
    """상자들을 줄로: 가운데 y 가 줄 평균과 패 높이 반 안이면 같은 줄."""
    rows: list[list] = []
    for b in sorted(boxes, key=lambda b: b[1] + b[3] / 2):
        cy = b[1] + b[3] / 2
        if rows and abs(cy - statistics.mean(r[1] + r[3] / 2 for r in rows[-1])) < th * 0.5:
            rows[-1].append(b)
        else:
            rows.append([b])
    return [sorted(r, key=lambda b: b[0]) for r in rows]


def locate_last(img: np.ndarray):
    H, W = img.shape[:2]
    boxes = white_boxes(img)
    got = own_river(boxes, W, H)
    if not got:
        return None, boxes, [], []
    group, tw, th = got
    rows = frame(group, th)
    return rows[-1][-1], boxes, group, rows


def crop_tile(img: np.ndarray, box, pad: float = 0.12) -> bytes:
    x, y, w, h = box
    px, py = int(w * pad), int(h * pad)
    H, W = img.shape[:2]
    c = img[max(0, y - py):min(H, y + h + py), max(0, x - px):min(W, x + w + px)]
    return cv2.imencode(".jpg", c, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def debug() -> None:
    sys.path.insert(0, str(ROOT))
    import last3 as l3
    import bench as b

    OUT.mkdir(parents=True, exist_ok=True)
    for scene, photos in l3.PHOTOS.items():
        for photo in photos:
            for side in l3.TRUTH[scene]:
                img = cv2.imread(str(b.G / scene / photo / f"last_{side}.jpg"))
                last, boxes, group, rows = locate_last(img)
                vis = img.copy()
                for bx in boxes:
                    cv2.rectangle(vis, (bx[0], bx[1]), (bx[0] + bx[2], bx[1] + bx[3]), (160, 160, 160), 2)
                for ri, r in enumerate(rows):
                    for ci, bx in enumerate(r):
                        cv2.rectangle(vis, (bx[0], bx[1]), (bx[0] + bx[2], bx[1] + bx[3]), (255, 140, 0), 3)
                        cv2.putText(vis, f"{ri}.{ci}", (bx[0] + 4, bx[1] + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 255), 2)
                if last:
                    cv2.rectangle(vis, (last[0], last[1]), (last[0] + last[2], last[1] + last[3]), (0, 0, 255), 6)
                cv2.imwrite(str(OUT / f"{photo}_{side}.jpg"), vis)
                print(f"{scene} {photo} {side:6s} 상자 {len(boxes):2d}  강 {len(group):2d}장  줄 {[len(r) for r in rows]}  정답 {l3.TRUTH[scene][side]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["debug"])
    a = ap.parse_args()
    if a.mode == "debug":
        debug()
