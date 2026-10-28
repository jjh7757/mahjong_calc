"""고정 카메라 사전 정보로 자리 틀 잡기: 지금 규칙(app/seat.structure)과 같은 YOLO 상자로 나란히 비교한다.

  python -I -X utf8 experiments/speed/seat_prior.py frames            (API 없이 틀만: 장수·구조가 정답과 같은지)
  python -I -X utf8 experiments/speed/seat_prior.py read --runs 3     (틀 잡힌 것을 서버와 같은 조각 읽기로 Gemini 에)

고정 카메라라면 자리마다 손패 줄이 놓이는 직선(기울기·위치), 패 한 장 크기, 손패가 시작하는 x 가 판마다 거의 같다.
그 값(사전 정보)을 **같은 자리의 다른 사진**에서 미리 알아 두고, 새 사진은 "그 직선 위, 그 크기의 패" 만 손패·울기 줄로 본다.
  - 지금 규칙: 사진만 보고 가장 많이 붙은 묶음 = 손패. 먼 자리(B)는 줄이 비스듬해 토막 나고, 울기가 많아 손패가
    줄면 울기 묶음(3~4장)이 손패로 뽑힐 수 있다.
  - 사전 정보: 직선 위 상자를 x 순으로 틈에서 끊고, 손패 시작 x 에서 시작하는 토막 = 손패(장수 무관),
    바로 뒤 한 장 = 떨어진 패, 나머지 3~4장 토막 = 울기.
사전 정보 출처(고정 카메라 흉내): 원본 사진은 같은 장면의 다른 사진(B k25↔k28, C k15↔k26, D k12↔k16),
울기 합성은 합성 전 원본. 사진이 손으로 찍은 갤러리라 진짜 고정 카메라보다 불리하다.

울기 합성(손패가 울기로 줄어든 자리): 지금 규칙으로 틀이 잡히는 C·D 원본에서 손패 줄 오른쪽 끝 패 3m 장을 펠트색으로
지우고, 그 패 그림을 3장씩 m 묶음으로 손패 끝 오른쪽에 붙인다(묶음 사이 패 0.6개). 손패 13 → 1 장까지.
정답 구조는 만든 대로(손패 n, 울기 묶음 수). 패 종류 정답은 원본 손패를 옮긴 순서 그대로.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402

sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
from app import river as rv  # noqa: E402
from app import seat  # noqa: E402

OUT = b.OUT / "seat_prior.json"
SEATS = {"B": "hand_right", "C": "hand_left", "D": "hand_bottom"}
PAIR = {"k25_1": "k28_1", "k28_1": "k25_1", "k15_1": "k26_1", "k26_1": "k15_1", "k12_1": "k16_1", "k16_1": "k12_1"}

# 사전 정보로 줄을 끊는 틈(패 너비 배수). 지금 규칙 GAP 0.35 보다 넉넉히 — 원근으로 먼 쪽 틈이 커 보인다.
LINE_TOL = 0.5  # 직선에서 패 높이 몇 배 안이면 줄 위
RUN_GAP = 0.45  # 줄 안 이웃 틈 < 패 몇 개
START_TOL = 2.5  # 손패 시작 x 가 사전 정보와 패 몇 개 안
SEP_DIST = seat.SEP_DIST

_det = None


def detector():
    global _det
    if _det is None:
        _det = rv.TileDetector(conf=0.04)
    return _det


def faces_of(rgb: np.ndarray) -> list[seat.Box]:
    """서버 틀 잡기와 같은 상자: 모자이크 검출 → 무늬 없는 상자 버림 → 앞면만 → 겹침 제거."""
    white = rv.white_mask(rgb)
    got = seat.mosaic(detector(), rgb, white)
    if got is None:
        return []
    boxes = [x for x in got[0] if seat.ink(rgb, x) >= seat.INK_MIN]
    return rv.dedupe(rv.keep_faces(boxes, white))


@dataclass
class Prior:
    slope: float
    icpt: float  # 패 가운데 y = slope * 가운데 x + icpt
    tw: float
    th: float
    x0: float  # 손패 시작 x(가장 왼쪽 패의 왼쪽 끝)

    def y(self, cx: float) -> float:
        return self.slope * cx + self.icpt


def fit_line(faces: list[seat.Box]) -> tuple[float, float, list[seat.Box]] | None:
    """가운데점 RANSAC(모든 쌍) → 가장 많은 상자가 패 높이 0.35 안에 드는 직선, 최소제곱으로 다듬음."""
    if len(faces) < 3:
        return None
    th = statistics.median(x[3] for x in faces)
    tw = statistics.median(x[2] for x in faces)
    c = [(x[0] + x[2] / 2, x[1] + x[3] / 2) for x in faces]
    best = None
    for i in range(len(c)):
        for j in range(i + 1, len(c)):
            (x1, y1), (x2, y2) = c[i], c[j]
            if abs(x2 - x1) < tw:
                continue
            m = (y2 - y1) / (x2 - x1)
            if abs(m) > 0.3:
                continue
            k = y1 - m * x1
            inl = [f for f, (cx, cy) in zip(faces, c) if abs(cy - (m * cx + k)) < 0.35 * th]
            if best is None or len(inl) > len(best[2]):
                best = (m, k, inl)
    if best is None or len(best[2]) < 3:
        return None
    xs = np.array([f[0] + f[2] / 2 for f in best[2]])
    ys = np.array([f[1] + f[3] / 2 for f in best[2]])
    m, k = np.polyfit(xs, ys, 1)
    return float(m), float(k), best[2]


def prior_of(faces: list[seat.Box]) -> Prior | None:
    fit = fit_line(faces)
    if fit is None:
        return None
    m, k, inl = fit
    up = [x for x in inl if x[3] > x[2]] or inl
    return Prior(m, k, statistics.median(x[2] for x in up), statistics.median(x[3] for x in up), min(x[0] for x in inl))


def structure_prior(faces: list[seat.Box], p: Prior) -> seat.SeatFrame | None:
    """사전 정보로 틀: 직선 위 상자를 x 순으로 틈에서 끊어 손패(시작 x 근처 토막) · 떨어진 한 장 · 울기(3~4장 토막)."""
    on, off = [], []
    for f in faces:
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        size_ok = 0.6 * p.th < max(f[2], f[3]) < 1.5 * p.th
        (on if abs(cy - p.y(cx)) < LINE_TOL * p.th and size_ok else off).append(f)
    if not on:
        return None
    on.sort(key=lambda x: x[0])
    runs = [[on[0]]]
    for f in on[1:]:
        prev = runs[-1][-1]
        if f[0] - (prev[0] + prev[2]) > RUN_GAP * p.tw:
            runs.append([f])
        else:
            runs[-1].append(f)
    if abs(runs[0][0][0] - p.x0) > START_TOL * p.tw:
        return None  # 손패가 있어야 할 곳에서 시작하지 않음(카메라가 움직였거나 가림)
    hand, rest = runs[0], runs[1:]
    sep = None
    hx1 = hand[-1][0] + hand[-1][2]
    if rest and len(rest[0]) == 1 and rest[0][0][0] - hx1 < SEP_DIST * p.tw:
        sep = rest[0][0]
        rest = rest[1:]
    melds, loose = [], list(off)
    for r in rest:
        if 3 <= len(r) <= 4:
            melds.append(r)
        else:
            loose.extend(r)
    return seat.SeatFrame(hand, sep, melds, loose, p.tw, p.th, len(faces))


# ---------------------------------------------------------------- 울기 합성

def with_melds(rgb: np.ndarray, hand: list[seat.Box], m: int) -> np.ndarray | None:
    """손패 줄 오른쪽 끝 3m 장을 지우고 3장씩 m 묶음으로 손패 끝 오른쪽에 붙인 그림. 자리가 모자라면 None."""
    hand = sorted(hand, key=lambda x: x[0])
    if len(hand) - 3 * m < 1:
        return None
    keep, moved = hand[: len(hand) - 3 * m], hand[len(hand) - 3 * m:]
    out = rgb.copy()
    tw = statistics.median(x[2] for x in hand)
    # 펠트색: 손패 줄 바로 위 띠의 중앙값.
    y0 = max(0, min(x[1] for x in hand) - int(0.6 * statistics.median(x[3] for x in hand)))
    y1 = max(1, min(x[1] for x in hand) - 2)
    felt = np.median(rgb[y0:y1, hand[0][0]:hand[-1][0] + hand[-1][2]].reshape(-1, 3), axis=0).astype(np.uint8)
    patches = [rgb[y:y + h, x:x + w].copy() for x, y, w, h in moved]
    for x, y, w, h in moved:
        out[y:y + h, x:x + w] = felt
    cur = keep[-1][0] + keep[-1][2] + int(1.0 * tw)
    for g in range(m):
        for k in range(3):
            (x, y, w, h), patch = moved[3 * g + k], patches[3 * g + k]
            if cur + w > out.shape[1]:
                return None
            out[y:y + h, cur:cur + w] = patch
            cur += w + 2
        cur += int(0.6 * tw)
    return out


# ---------------------------------------------------------------- 실행

def jpeg(rgb: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "JPEG", quality=92)
    return buf.getvalue()


def cases() -> list[dict]:
    """원본 6장 + C·D 울기 합성. 정답 구조(손패 장수, 떨어진 패, 울기 묶음 수)와 사전 정보를 뽑을 사진."""
    out = []
    for s in "BCD":
        truth = b.TRUTH[s]
        n_melds = len(truth[2])
        for p in b.PHOTOS[s]:
            rgb = np.asarray(Image.open(b.G / s / p / f"{SEATS[s]}.jpg").convert("RGB"))
            ref = np.asarray(Image.open(b.G / s / PAIR[p] / f"{SEATS[s]}.jpg").convert("RGB"))
            out.append({"name": f"{s} {p}", "scene": s, "rgb": rgb, "ref": ref, "hand": len(truth[1].split()),
                        "melds": n_melds, "tiles": truth[1].split(), "meld_tiles": [m.split() for m in truth[2]]})
    # 울기 합성: 지금 규칙으로 틀이 잡히는 원본(C·D)에서.
    for base in [c for c in out if c["scene"] in "CD"]:
        faces = faces_of(base["rgb"])
        fr = seat.structure(base["rgb"], faces)
        if fr is None or not seat.valid(fr):
            continue
        for m in range(1, 5):
            if base["melds"] + m > 4:
                break
            img = with_melds(base["rgb"], fr.hand, m)
            if img is None:
                print(f"  {base['name']} 울기 +{m}: 자리 모자람, 건너뜀")
                continue
            hand_tiles = base["tiles"][: base["hand"] - 3 * m]
            new = [base["tiles"][base["hand"] - 3 * m + 3 * g: base["hand"] - 3 * m + 3 * g + 3] for g in range(m)]
            out.append({"name": f"{base['name']} 울기+{m}", "scene": base["scene"], "rgb": img, "ref": base["rgb"],
                        "hand": base["hand"] - 3 * m, "melds": base["melds"] + m, "tiles": hand_tiles,
                        "meld_tiles": new + base["meld_tiles"], "synthetic": True})
    return out


def judge_frame(fr: seat.SeatFrame | None, rgb: np.ndarray, c: dict) -> dict:
    if fr is None:
        return {"ok": False, "why": "구조 없음"}
    v, s = seat.valid(fr), seat.safe_ok(fr, rgb)
    right = len(fr.hand) == c["hand"] and fr.separate is None and len(fr.melds) == c["melds"]
    return {"ok": v and s and right, "valid": v, "safe": s, "right": right, "sum": fr.summary()}


def frames(save: Path | None = None) -> None:
    rows = []
    for c in cases():
        faces = faces_of(c["rgb"])
        now = judge_frame(seat.structure(c["rgb"], faces), c["rgb"], c)
        p = prior_of(faces_of(c["ref"]))
        pri = judge_frame(structure_prior(faces, p) if p else None, c["rgb"], c)
        rows.append({"name": c["name"], "now": now, "prior": pri})
        print(f"{c['name']:18s} 정답 손패 {c['hand']:2d}·울기 {c['melds']} | 지금 {'OK' if now['ok'] else 'X '} "
              f"{now.get('sum', now.get('why'))} | 사전 {'OK' if pri['ok'] else 'X '} {pri.get('sum', pri.get('why'))}")
    for k, lab in (("now", "지금 규칙"), ("prior", "사전 정보")):
        orig = [r for r in rows if "울기+" not in r["name"]]
        syn = [r for r in rows if "울기+" in r["name"]]
        bad = [r for r in rows if r[k].get("valid") and r[k].get("safe") and not r[k].get("right")]
        print(f"{lab}: 원본 {sum(r[k]['ok'] for r in orig)}/{len(orig)} · 울기 합성 {sum(r[k]['ok'] for r in syn)}/{len(syn)}"
              f" · 검사 통과했는데 틀린 구조 {len(bad)}")
    if save:
        save.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["frames"])
    a = ap.parse_args()
    if a.cmd == "frames":
        frames(b.OUT / "seat_prior_frames.json")
