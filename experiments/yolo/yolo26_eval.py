"""YOLO26(HaseLab) 단독 정확도를 더 많은 패로, 설정을 바꿔 가며 잰다(2026-10-26).

세트:
  field  10/24 매장 카메라 헤드(60cm, 1x) 사진 6장. 정답 paifu_20261024/truth_field_115559.json(네 자리 손패 + 강 4개).
         115559·115801·115929·120037 은 네 자리 손패가 앞면, 120755·122922 는 오른쪽만 앞면(나머지는 엎음 = 정답 "엎음").
         강은 6장 모두 같다(35장). 탁자가 사진에서 약 40° 기울어 있다.
  kakao  사용자 갤러리 10장(손으로 찍음), 화료자 손패 + 울기만 정답.

파이프라인: 사진을 15° 씩 돌려 구역 YOLO26 → 자리마다 self_hand 확신도가 가장 높은 각도를 고름(자리는 탁자 중심에서 본 방향으로 정함)
  → 손패 구역 윤곽의 기울기만큼 더 돌려 줄을 수평으로 → 그 각도에서 self_hand·meld_0(손패 쪽에 있는 것만)·discard_0 구역 → 패 YOLO26 → 투시 변환 224 → ResNet-50.

설정(--configs, 쉼표):
  base   지금까지와 같음(구역 사방 여백, 패 imgsz 1024, 분류 확신도 0.3 미만 버림)
  frag   + 조각 거르기(세그 넓이가 구역 안 중앙값의 45% 미만이면 버림)
  tta    + 분류 4방향(0·90·180·270°) 중 확신도 가장 높은 답
  nopad  구역 여백 없이
  mask   중심이 구역 윤곽(세그 마스크) 안인 패만(상자는 옆 강·옆 구역과 겹침)
  whole  구역마다 따로가 아니라 돌린 사진 전체에서 패를 한 번 찾고 중심이 구역 안인 것만(구역 겹침 중복이 없어짐)
  ms     패 찾기를 640·1024·1280 × 좌우 반전, 확신도 0.05 로 모아 겹침 제거(분류기 확신도 0.3 이 거름)
  cv     손패는 패 YOLO 대신 색(흰 면)으로 찾고 패 높이로 나눔, 각도는 흰 면 가로 투영이 가장 또렷한 쪽(Y26.cv_hand)
  pick   손패를 패 YOLO(mask+frag+nopad) 후보와 색(cv) 후보 중 장수·텐파이 검사 통과 > 13장에 가까움 > 확신도 순으로 고름(정답 안 봄)
  line   손패 줄 연장선 위의 떨어진 무더기도 손패로(hybrid.split line_merge)
  fine   손패 각도를 ±25°(5° 간격)에서 패가 가장 많이 잡히는 각도로 다시 맞추고, 손패·울기를 감싼 창 하나를 씀
  sz640·sz1600  패 imgsz
  조합은 + 로: frag+tta+whole

채점: 구역마다 정답 다중집합과 비교 — 찾은 장수(재현율), 예측 중 맞은 비율(정밀도), 손패·강 통째 정답. 손패는 엎음/앞면 판정도.
python -I yolo26_eval.py [--sets field,kakao] [--configs base,frag,tta,frag+tta,frag+tta+whole]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hybrid as hy  # noqa: E402
import run_yolo as ry  # noqa: E402

EXP = ry.EXP
OUT = ry.HERE / "results" / "y26"
FIELD = ["115559", "115801", "115929", "120037", "120755", "122922"]
FIELD_FACEUP = {"120755": ["right"], "122922": ["right"]}  # 나머지 네 장은 네 자리 다 앞면
SEATS = ["bottom", "right", "top", "left"]
# 탁자 중심에서 본 손패 방향(이미지 좌표, y 아래, 도). field 는 탁자가 약 45° 돈 사진
SECTOR = {"field": {"bottom": 135, "right": 45, "top": -45, "left": -135},
          "kakao": {"bottom": 90, "right": 0, "top": -90, "left": 180}}
ANGLES = list(range(0, 360, 15))


def rotate(img: np.ndarray, deg: float):
    """반시계 deg 회전(캔버스 확장). (돌린 사진, 원본→돌린 좌표 행렬)"""
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
    c, s = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(h * s + w * c), int(h * c + w * s)
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(img, m, (nw, nh), borderValue=(0, 0, 0)), m


def angdiff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


class Y26:
    def __init__(self, opts=()):
        from ultralytics import YOLO

        self.opts = set(opts)
        self.h = ry.HaseLab()
        self.region = YOLO(str(ry.W / "haselab" / "regions-yolo-26n.pt"))

    # ---------------- 구역
    def _predict_at(self, img: np.ndarray, a: float):
        rot, m = rotate(img, a)
        r = self.region.predict(rot, conf=0.25, imgsz=1280, verbose=False, retina_masks=True)[0]
        boxes: dict[str, list] = {}
        polys = r.masks.xy if r.masks is not None else [None] * len(r.boxes)
        for c, p, b, poly in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy, polys):
            boxes.setdefault(self.region.names[int(c)], []).append((float(p), b.numpy(), poly))
        return rot, m, boxes

    @staticmethod
    def tilt(poly) -> float:
        """손패 구역 윤곽의 긴 변 기울기(도, 이미지 좌표). 이만큼 더 돌리면 줄이 수평이 된다."""
        if poly is None or len(poly) < 4:
            return 0.0
        box = cv2.boxPoints(cv2.minAreaRect(poly.astype(np.float32)))
        e = max((box[(i + 1) % 4] - box[i] for i in range(4)), key=np.linalg.norm)
        t = math.degrees(math.atan2(e[1], e[0]))
        return (t + 90) % 180 - 90

    def regions(self, img: np.ndarray, set_name: str):
        """자리마다 {angle, rot, M, hand, melds, discard} — 상자는 돌린 사진 좌표."""
        H, W = img.shape[:2]
        found = [(a, *self._predict_at(img, a)) for a in ANGLES]  # (angle, rot, M, boxes{name: [(conf, box, poly)]})
        # 탁자 중심: 각 각도의 강 상자 중심을 원본 좌표로 되돌려 평균
        pts = []
        for a, rot, m, boxes in found:
            inv = cv2.invertAffineTransform(m)
            for name in ("discard_0", "discard_1", "discard_2", "discard_3"):
                for p, b, _ in boxes.get(name, []):
                    if p > 0.5:
                        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                        pts.append(inv @ np.array([cx, cy, 1.0]))
        center = np.mean(pts, axis=0) if pts else np.array([W / 2, H / 2])
        def seat_of(m, b, cls):
            inv = cv2.invertAffineTransform(m)
            cx, cy = inv @ np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2, 1.0])
            ang = math.degrees(math.atan2(cy - center[1], cx - center[0]))
            seat = min(SEATS, key=lambda s: angdiff(ang, SECTOR[set_name][s]))
            return seat if angdiff(ang, SECTOR[set_name][seat]) <= 45 else None

        def seat_hands(a, rot, m, boxes, cls="self_hand"):
            for p, b, poly in boxes.get(cls, []):
                seat = seat_of(m, b, cls)
                if seat:
                    yield seat, dict(conf=p, angle=a, rot=rot, M=m, hand=b, poly=poly, boxes=boxes)

        best = {}
        for f in found:
            for seat, d in seat_hands(*f):
                if seat not in best or d["conf"] > best[seat]["conf"]:
                    best[seat] = d
        # 15° 간격이라 손패 줄이 최대 ±7.5° 이상(윤곽이 어긋나면 더) 기울어 있다 → 손패 윤곽의 기울기만큼 더 돌려 다시 구역을 찾는다
        if "notilt" not in self.opts:
            for seat in list(best):
                t = self.tilt(best[seat]["poly"])
                if abs(t) < 2:
                    continue
                a2 = best[seat]["angle"] + t
                cand = [d for s2, d in seat_hands(a2, *self._predict_at(img, a2)) if s2 == seat]
                if cand:
                    best[seat] = max(cand, key=lambda d: d["conf"])
        rivers = {}
        for f in found:
            for seat, d in seat_hands(*f, cls="discard_0"):
                if seat not in rivers or d["conf"] > rivers[seat]["conf"]:
                    rivers[seat] = d
        if "notilt" not in self.opts:
            for seat in list(rivers):
                t = self.tilt(rivers[seat]["poly"])
                if abs(t) < 2 or abs(t) > 30:  # 강은 6장 줄이 여러 단이라 윤곽이 정사각형에 가까우면 기울기가 엉뚱할 수 있다
                    continue
                a2 = rivers[seat]["angle"] + t
                cand = [d for s2, d in seat_hands(a2, *self._predict_at(img, a2), cls="discard_0") if s2 == seat]
                if cand:
                    rivers[seat] = max(cand, key=lambda d: d["conf"])
        self._finish(best, rivers)
        return best, rivers

    def fine(self, img: np.ndarray, d: dict, key: str, cache: dict):
        """구역 윤곽 기울기는 손패가 여러 무더기면 틀린다 → 각도를 ±25° 범위에서 5° 씩 바꿔 패가 가장 많이(같으면 확신도 합이 크게) 잡히는 각도.
        돌아오는 dict 는 d 와 같은 꼴(rot, hand, melds=[], poly=None)."""
        if key in cache:
            return cache[key]
        inv = cv2.invertAffineTransform(d["M"])
        boxes = [d["hand"]] + d["melds"]
        x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes); x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
        c = inv @ np.array([(x0 + x1) / 2, (y0 + y1) / 2, 1.0])
        w, h = (x1 - x0) * 1.1, (y1 - y0) * 1.4
        best = None
        for delta in range(-25, 26, 5):
            a = d["angle"] + delta
            rot, m = rotate(img, a)
            cx, cy = m @ np.array([c[0], c[1], 1.0])
            box = np.array([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2])
            X0, Y0, X1, Y1 = [int(v) for v in (max(0, box[0]), max(0, box[1]), min(rot.shape[1], box[2]), min(rot.shape[0], box[3]))]
            r = self.h.tile.predict(rot[Y0:Y1, X0:X1], conf=0.25, imgsz=1024, verbose=False)[0]
            score = (len(r.boxes), float(r.boxes.conf.sum()) if len(r.boxes) else 0.0)
            if best is None or score > best[0]:
                best = (score, dict(angle=a, rot=rot, M=m, hand=box, melds=[], poly=None, meld_polys=[]))
        cache[key] = best[1]
        return best[1]

    def cv_hand(self, img: np.ndarray, d: dict, key: str, cache: dict, cfg: set):
        """패 YOLO 대신 색으로 패 면 찾기(먼 자리에서 패 모델이 반듯한 크롭에서도 못 찾음).
        1) 손패·울기 구역을 감싼 창을 ±25° 에서 2.5° 씩 돌려, 흰 면(채도 낮고 밝음)의 가로 투영이 가장 또렷한 각도(줄이 수평)
        2) 흰 덩어리 중 높이가 패 높이 근처인 것만(테이블 흰 테두리는 너무 넓고 길어서 빠짐)
        3) 덩어리 폭 / (높이 × 0.72) 를 반올림한 장수로 똑같이 나눠 칸마다 분류기
        돌려주는 것: [(label, conf, center, size)]"""
        if key not in cache:
            inv = cv2.invertAffineTransform(d["M"])
            boxes = [d["hand"]] + d["melds"]
            x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes); x1 = max(b[2] for b in boxes); y1 = max(b[3] for b in boxes)
            c = inv @ np.array([(x0 + x1) / 2, (y0 + y1) / 2, 1.0])
            w, h = (x1 - x0) * 1.15, (y1 - y0) * 1.6
            best = None
            for delta in np.arange(-25, 25.1, 2.5):
                a = d["angle"] + delta
                m = cv2.getRotationMatrix2D((float(c[0]), float(c[1])), a, 1.0)
                m[0, 2] += w / 2 - c[0]
                m[1, 2] += h / 2 - c[1]
                win = cv2.warpAffine(img, m, (int(w), int(h)), borderValue=(0, 0, 0))
                hsv = cv2.cvtColor(win, cv2.COLOR_BGR2HSV)
                white = ((hsv[..., 1] < 60) & (hsv[..., 2] > 150)).astype(np.float32)
                score = float(white.mean(1).var())
                if best is None or score > best[0]:
                    best = (score, win)
            cache[key] = best[1]
        win = cache[key]
        hsv = cv2.cvtColor(win, cv2.COLOR_BGR2HSV)
        white = ((hsv[..., 1] < 60) & (hsv[..., 2] > 150)).astype(np.uint8) * 255
        white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, _, st, _ = cv2.connectedComponentsWithStats(white)
        comps = [st[i] for i in range(1, n) if st[i][4] > 0.0005 * win.shape[0] * win.shape[1]]
        if not comps:
            return []
        # 패 높이: 폭이 높이의 0.5~1.6배인 덩어리(한 장)의 높이 중앙값, 없으면 전체 중앙값
        singles = [c_[3] for c_ in comps if 0.5 <= c_[2] / c_[3] <= 1.6]
        th = float(np.median(singles if singles else [c_[3] for c_ in comps]))
        slots = []
        for x, y_, w_, h_, area in comps:
            if not (0.6 * th <= h_ <= 1.5 * th) or area < 0.5 * w_ * h_:
                continue  # 테두리·패산 옆면·반쯤 가린 것
            k = max(1, int(round(w_ / (h_ * 0.72))))
            for j in range(k):
                slots.append((x + w_ * j / k, y_, w_ / k, h_))
        if not slots:
            return []
        crops = [cv2.resize(win[int(yy):int(yy + hh), int(xx):int(xx + ww)], (224, 224)) for xx, yy, ww, hh in slots]
        x_ = np.stack([cv2.cvtColor(c_, cv2.COLOR_BGR2RGB).astype(np.float32) / 255 for c_ in crops])
        x_ = (x_ - self.h.mean) / self.h.std
        with self.h.torch.no_grad():
            p_ = self.h.torch.softmax(self.h.net(self.h.torch.from_numpy(x_.transpose(0, 3, 1, 2)).float()), 1).numpy()
        out = []
        for (xx, yy, ww, hh), pr in zip(slots, p_):
            if pr.max() >= 0.3:
                out.append((ry.HASE_CLASSES[int(pr.argmax())], float(pr.max()), np.array([xx + ww / 2, yy + hh / 2]), float(min(ww, hh))))
        return out

    @staticmethod
    def _finish(best: dict, rivers: dict):
        for seat, d in rivers.items():
            d["discard"], d["discard_poly"] = d["hand"], d["poly"]
        for seat, d in best.items():
            boxes = d["boxes"]
            disc = max(boxes.get("discard_0", []), key=lambda t: t[0], default=None)
            d["discard"] = disc[1] if disc else None
            d["discard_poly"] = disc[2] if disc else None
            # 울기는 손패 쪽(강 상자 아래 끝보다 아래)에 있는 것만 — 가운데 도라를 meld_0 으로 잡는 경우가 있었다
            lim = d["discard"][3] if d["discard"] is not None else d["rot"].shape[0] * 0.6
            mel = [(b, poly) for p, b, poly in boxes.get("meld_0", []) if p > 0.3 and (b[1] + b[3]) / 2 > lim]
            d["melds"] = [b for b, _ in mel]
            d["meld_polys"] = [poly for _, poly in mel]

    def regions_cached(self, img, set_name, cache_path: Path, key: str):
        """regions 는 24각도 + 보정으로 사진당 15초쯤 걸린다 → 고른 각도만 파일에 두고, 다음엔 그 각도에서만 구역을 다시 찾는다."""
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        if key in cache:
            hands, rivers = {}, {}
            for kind, store, cls in (("hand", hands, "self_hand"), ("river", rivers, "discard_0")):
                for seat, info in cache[key][kind].items():
                    rot, m, boxes = self._predict_at(img, info["angle"])
                    cand = [(p, b, poly) for p, b, poly in boxes.get(cls, [])]
                    if not cand:
                        continue
                    # 저장한 상자와 가장 가까운 것
                    ref = np.array(info["box"])
                    p, b, poly = min(cand, key=lambda t: np.abs(t[1] - ref).sum())
                    store[seat] = dict(conf=p, angle=info["angle"], rot=rot, M=m, hand=b, poly=poly, boxes=boxes)
            self._finish(hands, rivers)
            return hands, rivers
        hands, rivers = self.regions(img, set_name)
        cache[key] = {"hand": {s: {"angle": float(d["angle"]), "box": d["hand"].tolist()} for s, d in hands.items()},
                      "river": {s: {"angle": float(d["angle"]), "box": d["hand"].tolist()} for s, d in rivers.items()}}
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
        return hands, rivers

    # ---------------- 패
    def tiles(self, rot: np.ndarray, boxes: list, cfg: set, polys_in=None):
        """boxes 안의 패 [(label, conf, center, size)] (돌린 사진 좌표). 구역이 여러 개면 합친다.
        cfg 에 mask 가 있으면 중심이 구역 윤곽(polys_in, 패 짧은 변 절반 여유) 안인 패만 — 상자는 옆 강과 겹친다."""
        Hh, Ww = rot.shape[:2]
        sz = 640 if "sz640" in cfg else 1600 if "sz1600" in cfg else 1024

        def crop_box(b, pad=True):
            x0, y0, x1, y1 = b
            if pad and "nopad" not in cfg:
                px, py = (x1 - x0) * 0.08, (y1 - y0) * 0.15
                x0, y0, x1, y1 = x0 - px, y0 - py, x1 + px, y1 + py
            return int(max(0, x0)), int(max(0, y0)), int(min(Ww, x1)), int(min(Hh, y1))

        polys = []  # (poly in rot coords, region index)
        if "whole" in cfg:
            # 구역들을 감싸는 상자 하나에서 한 번 찾고, 중심이 어느 구역 안인 것만
            cb = [crop_box(b) for b in boxes]
            X0, Y0 = min(c[0] for c in cb), min(c[1] for c in cb)
            X1, Y1 = max(c[2] for c in cb), max(c[3] for c in cb)
            r = self.h.tile.predict(rot[Y0:Y1, X0:X1], conf=0.25, imgsz=max(sz, 1280), verbose=False, retina_masks=True)[0]
            for poly in ([] if r.masks is None else r.masks.xy):
                if len(poly) < 4:
                    continue
                poly = poly + np.array([X0, Y0])
                cx, cy = poly.mean(0)
                k = next((i for i, (a, b_, c, d) in enumerate(cb) if a <= cx <= c and b_ <= cy <= d), None)
                if k is not None:
                    polys.append((poly, k))
        else:
            for k, b in enumerate(boxes):
                x0, y0, x1, y1 = crop_box(b)
                crop = rot[y0:y1, x0:x1]
                if crop.size == 0:
                    continue
                if "ms" in cfg:
                    # 여러 크기 × 좌우 반전, 낮은 확신도로 모아 겹친 것은 확신도 높은 것만(틀린 후보는 뒤에서 분류기가 거름)
                    cand = []
                    for s_ in (640, 1024, 1280):
                        for flip in (False, True):
                            im_ = crop[:, ::-1].copy() if flip else crop
                            r = self.h.tile.predict(im_, conf=0.05, imgsz=s_, verbose=False, retina_masks=True)[0]
                            if r.masks is None:
                                continue
                            for poly, cf in zip(r.masks.xy, r.boxes.conf):
                                if len(poly) < 4:
                                    continue
                                if flip:
                                    poly = poly.copy(); poly[:, 0] = crop.shape[1] - 1 - poly[:, 0]
                                cand.append((float(cf), poly))
                    if cand:
                        ar = np.sqrt(np.median([cv2.contourArea(p_.astype(np.float32)) for _, p_ in cand]))
                        kept = []
                        for cf, poly in sorted(cand, key=lambda t: -t[0]):
                            c0 = poly.mean(0)
                            if all(np.linalg.norm(c0 - q.mean(0)) > 0.5 * ar for q in kept):
                                kept.append(poly)
                        polys += [(q + np.array([x0, y0]), k) for q in kept]
                    continue
                r = self.h.tile.predict(crop, conf=0.25, imgsz=sz, verbose=False, retina_masks=True)[0]
                for poly in ([] if r.masks is None else r.masks.xy):
                    if len(poly) >= 4:
                        polys.append((poly + np.array([x0, y0]), k))
        if "frag" in cfg and polys:
            areas = np.array([cv2.contourArea(p.astype(np.float32)) for p, _ in polys])
            keep = []
            for k in {k for _, k in polys}:
                idx = [i for i, (_, kk) in enumerate(polys) if kk == k]
                med = np.median(areas[idx])
                keep += [i for i in idx if areas[i] >= 0.45 * med]
            polys = [polys[i] for i in sorted(keep)]
        if "mask" in cfg and polys_in and polys:
            areas_sqrt = np.sqrt(np.median([cv2.contourArea(p.astype(np.float32)) for p, _ in polys]))
            keep = []
            for poly, k in polys:
                ref = polys_in[k] if k < len(polys_in) else None
                if ref is None or len(ref) < 3:
                    keep.append((poly, k))
                    continue
                cx, cy = poly.mean(0)
                if cv2.pointPolygonTest(ref.astype(np.float32), (float(cx), float(cy)), True) >= -0.5 * areas_sqrt:
                    keep.append((poly, k))
            polys = keep
        if not polys:
            return []
        dst = np.array([[0, 0], [223, 0], [223, 223], [0, 223]], np.float32)
        crops, centers, sizes = [], [], []
        for poly, _ in polys:
            c = self.h.corners(poly)
            w = np.linalg.norm(c[1] - c[0]); hh = np.linalg.norm(c[3] - c[0])
            if w > hh * 1.15:
                c = np.roll(c, -1, axis=0)
            crops.append(cv2.warpPerspective(rot, cv2.getPerspectiveTransform(c, dst), (224, 224)))
            centers.append(poly.mean(0))
            sizes.append(float(min(w, hh)))
        rots = [0, 1, 2, 3] if "tta" in cfg else [0]
        best_p = None
        for k in rots:
            x = np.stack([cv2.cvtColor(np.rot90(c, k).copy(), cv2.COLOR_BGR2RGB).astype(np.float32) / 255 for c in crops])
            x = (x - self.h.mean) / self.h.std
            with self.h.torch.no_grad():
                p = self.h.torch.softmax(self.h.net(self.h.torch.from_numpy(x.transpose(0, 3, 1, 2)).float()), 1).numpy()
            best_p = p if best_p is None else np.where(p.max(1, keepdims=True) > best_p.max(1, keepdims=True), p, best_p)
        out = []
        for i in range(len(crops)):
            conf = float(best_p[i].max())
            if conf >= 0.3:
                out.append((ry.HASE_CLASSES[int(best_p[i].argmax())], conf, centers[i], sizes[i]))
        return ry.dedupe(out)


def score_region(pred: list[str], truth: list[str]):
    hit = sum((Counter(pred) & Counter(truth)).values())
    return hit, len(pred), len(truth), Counter(pred) == Counter(truth)


def field_truth():
    t = json.loads((EXP / "paifu_20261024" / "truth_field_115559.json").read_text(encoding="utf-8"))
    hands = {s: t["hands"][s]["closed"] + [x for m in t["hands"][s]["melds"] for x in m[1:]] for s in SEATS}
    return hands, t["rivers"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="kakao")  # 평가는 갤러리 B·C·D(사용자 결정). field(매장 6장)는 --sets field 로만
    ap.add_argument("--configs", default="base,frag,tta,frag+tta,frag+tta+whole")
    ap.add_argument("--notilt", action="store_true", help="손패 기울기 보정 끄기(비교용)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    y = Y26(["notilt"] if a.notilt else [])
    configs = [set(c.split("+")) for c in a.configs.split(",")]
    names = a.configs.split(",")

    # 구역은 설정과 상관없으므로 사진마다 한 번
    jobs = []
    if "field" in a.sets:
        fh, fr = field_truth()
        for n in FIELD:
            jobs.append(("field", n, EXP / "field_20261024" / "captures" / f"20261024_{n}" / "original.jpg", fh, fr))
    if "kakao" in a.sets:
        for scene, (_, truth) in ry.SEAT_TRUTH.items():
            if scene not in ry.EVAL_SCENES:
                continue
            for p in ry.SEAT_PHOTOS[scene]:
                jobs.append(("kakao", f"{scene}/{p}", EXP / "field_20261024" / "kakao_photos" / f"{p}.jpg",
                             {ry.WINNER_SIDE[scene]: truth.split()}, None))
    regions = {}
    for set_name, n, path, *_ in jobs:
        t0 = time.perf_counter()
        regions[n] = y.regions_cached(ry.imread(path), set_name, OUT / "regions_cache.json", n)
        hb, rb = regions[n]
        print(f"구역 {n}: 손패 " + ", ".join(f"{s}@{d['angle']:.0f}°({d['conf']:.2f}, 울기 {len(d['melds'])})" for s, d in hb.items())
              + " | 강 " + ", ".join(f"{s}@{d['angle']:.0f}°({d['conf']:.2f})" for s, d in rb.items()) + f"  {time.perf_counter()-t0:.1f}초", flush=True)

    rows = []
    fine_cache: dict = {}
    cv_cache: dict = {}
    img_cache: dict = {}

    def y_img(path):
        if path not in img_cache:
            img_cache.clear()
            img_cache[path] = ry.imread(path)
        return img_cache[path]

    for name, cfg in zip(names, configs):
        for set_name, n, path, hands, rivers in jobs:
            reg, riv = regions[n]
            faceup = FIELD_FACEUP.get(n, SEATS) if set_name == "field" else list(hands)
            for seat in (SEATS if set_name == "field" else list(hands)):
                d = reg.get(seat)
                if d and "fine" in cfg:
                    d = y.fine(y_img(path), d, f"{n}/{seat}", fine_cache)
                # 손패
                t0 = time.perf_counter()
                picked = ""
                if d and "pick" in cfg:
                    # 정답을 보지 않고 고르기: 패 YOLO 후보와 색 후보 중 장수·텐파이 검사 통과 > 13장에 가까움 > 확신도 평균
                    cands = {"yolo": y.tiles(d["rot"], [d["hand"]] + d["melds"], {"mask", "frag", "nopad"}, [d["poly"]] + d["meld_polys"]),
                             "cv": y.cv_hand(y_img(path), d, f"{n}/{seat}", cv_cache, cfg)}

                    def rank(item):
                        _, ds = item
                        hh, mm, _ = hy.split([dict(t=t[0], x=float(t[2][0]), y=float(t[2][1])) for t in ds], line_merge=True) if ds else ([], [], 0)
                        ok = hy.check(hh, mm)[0] if hh else False
                        cnt = len(hh) + 3 * len(mm)
                        return (ok, -abs(cnt - 13), float(np.mean([t[1] for t in ds])) if ds else 0.0)
                    yb = cands["yolo"]
                    if yb and sum(t[0] == "back" for t in yb) * 2 > len(yb):
                        picked, dets = "yolo(엎음)", yb  # 엎은 손패는 색 후보가 흰 테두리를 패로 볼 수 있어 YOLO 분류(back)로 정한다
                    else:
                        picked, dets = max(cands.items(), key=rank)
                elif d and "cv" in cfg:
                    dets = y.cv_hand(y_img(path), d, f"{n}/{seat}", cv_cache, cfg)
                else:
                    dets = y.tiles(d["rot"], [d["hand"]] + d["melds"], cfg, [d["poly"]] + d["meld_polys"]) if d else []
                dt = time.perf_counter() - t0
                face = [t for t in dets if t[0] != "back"]
                pred_up = len(face) > len(dets) - len(face) and len(face) >= 3
                if seat in faceup:
                    if dets and pred_up:
                        # 손패 줄 + 울기 모양 고르기(엎은 2장 + 같은 패 2장 = 안깡)
                        hh, mm, _ = hy.split([dict(t=t[0], x=float(t[2][0]), y=float(t[2][1])) for t in dets], line_merge="line" in cfg or "pick" in cfg)
                        pred = hh + [t for m in mm for t in m]
                    else:
                        pred = []
                    hit, np_, nt, ex = score_region(pred, hands[seat])
                    rows.append(dict(cfg=name, set=set_name, photo=n, seat=seat, kind="hand", hit=hit, pred=np_, truth=nt,
                                     exact=ex, sec=round(dt, 2), read=" ".join(pred), up_ok=pred_up, picked=picked))
                else:
                    rows.append(dict(cfg=name, set=set_name, photo=n, seat=seat, kind="hand_down", up_ok=not pred_up,
                                     read=" ".join(t[0] for t in face)))
                # 강
                if rivers is not None:
                    rv_ = riv.get(seat)
                    rcfg = cfg | {"mask", "frag", "nopad"} if "pick" in cfg else cfg  # pick 은 손패 고르기 설정이고 강은 가장 나은 YOLO 설정으로
                    rd = y.tiles(rv_["rot"], [rv_["discard"]], rcfg, [rv_["discard_poly"]]) if rv_ else []
                    pred = [t[0] for t in rd if t[0] != "back"]
                    hit, np_, nt, ex = score_region(pred, rivers[seat])
                    rows.append(dict(cfg=name, set=set_name, photo=n, seat=seat, kind="river", hit=hit, pred=np_, truth=nt,
                                     exact=ex, read=" ".join(pred)))
        print(f"설정 {name} 끝", flush=True)
    (OUT / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# YOLO26 단독 설정 비교", "",
             "| 설정 | 세트 | 손패 패(재현율) | 손패 정밀도 | 손패 통째 정답 | 엎음 판정 | 강 패(재현율) | 강 정밀도 | 강 통째 정답 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name in names:
        for s in a.sets.split(","):
            rs = [r for r in rows if r["cfg"] == name and r["set"] == s]
            hd = [r for r in rs if r["kind"] == "hand"]
            dn = [r for r in rs if r["kind"] == "hand_down"]
            rv = [r for r in rs if r["kind"] == "river"]

            def pct(x, y_):
                return f"{x}/{y_} ({100*x/y_:.0f}%)" if y_ else "-"
            lines.append(
                f"| {name} | {s} | {pct(sum(r['hit'] for r in hd), sum(r['truth'] for r in hd))} | {pct(sum(r['hit'] for r in hd), sum(r['pred'] for r in hd))}"
                f" | {sum(r['exact'] for r in hd)}/{len(hd)} | {sum(r['up_ok'] for r in dn)}/{len(dn)} | "
                f"{pct(sum(r['hit'] for r in rv), sum(r['truth'] for r in rv))} | {pct(sum(r['hit'] for r in rv), sum(r['pred'] for r in rv))} | "
                f"{sum(r['exact'] for r in rv)}/{len(rv)} |")
    text = "\n".join(lines) + "\n"
    (OUT / "summary.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
