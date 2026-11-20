"""손에 가린 손패 보이게 하기(2026-11-20, handvideo.py --xray) — 지어내지 않는다.

손 밑에 그리는 것은 셋뿐:
  (1) 기억 — 그 자리 패가 손에 가리기 전 마지막으로 깨끗이 보였던 화소 조각(반투명 · 점선 테두리 · "기억 n.n초").
  (2) 틈 — 지금 손가락 사이로 실제로 보이는 패 등 색 화소(밝은 하늘색 테두리 · 살짝 밝게).
  (3) 세기 — 줄에 보이는 상자 수 a · 손 밑 기억 b · 합 a + b.
영상 복원 · 생성 모델은 쓰지 않음. 정답은 읽지 않음.

입력:
  패 상자 = slotgrid 검출 캐시 _work/slotgrid_1117/det_<판>.json(뒷면 상자, sheet_band 대국자 시점 [x0, x1, y0, y1]) —
    프레임 ms 와 같은 키, 없으면 가장 가까운 앞 검출(앞이 없으면 가장 가까운 뒤). 줄 상자만(slotgrid.row_line 으로 줄 가운데 선을 따라감).
    좌표: 넓힌 띠(frames_w220.json band) 시점 = sheet_band 시점 + off(두 시점 모두 같은 회전이라 차이가 상수 — to_view_xy 로 잼).
  손 = ov_GPU_w220.json 관절점(band2 좌표 → 넓힌 띠 = lm − (dx, dy)) — 그 프레임의 모든 손(그 사람 손 · 다른 손).
    손 영역 = 손마다 21점 볼록 껍질을 손 크기(손목 0 ~ 가운뎃손가락 뿌리 9 거리) × GROW 만큼 넓힌 것의 합
      ∪ 줄 둘레의 손 · 소매 화소(pixtrack.masks 의 skin — 살색 + 펠트 · 패 색이 아닌 덩어리, slotgrid 가림 열과 같은 계산) — SKIN_ROW.
      (11-20 r16_d03 53:44.9 ~ 53:47.5: 손이 10 ~ 14번을 덮는 26프레임 동안 관절이 하나도 안 잡혀 관절만으로는 기억이 안 생김 → 실제 화소 가림을 더함.)
    손이 한 프레임도 안 잡힌 프레임은 바로 앞 관절 영역을 HOLD 프레임까지 그대로 씀(관절 검출이 한두 장 끊기는 것).
기억 규칙(상자 짝짓기 · 생김 · 지움은 새 검출이 들어온 프레임에서만 — 검출과 손 영역이 같은 때일 때만 판단):
  상자를 앞 검출과 짝지음(가운데 거리 < MATCH 장 폭, 남은 것끼리 한 번 더 < MATCH2 장 폭 — 줄이 한 번에 0.5 ~ 1칸 밀린 것).
  짝 없이 사라진 상자가 손 영역과 GONE_OV 이상 겹치면 "손 밑으로 들어감" → 기억. 손 영역과 안 겹치는데 사라진 상자는 기억하지 않음(실제로 빠진 것).
    단, 손에 쥐고 옮기던 패(깨끗이 보인 적 없고 STABLE 번 넘게 같은 자리에 잡힌 적도 없는 상자)는 기억하지 않음 — 쥔 패가 손과 함께 움직여 두 번 세지 않게.
  기억 조각 = 그 상자가 손 영역과 CLEAN_OV 이하로 겹쳤던 마지막 프레임의 화소(손가락이 섞인 조각을 피하려고). 그런 프레임이 없으면 테두리만("모습없음").
    자리는 사라지기 직전 상자 자리(줄이 밀린 경우가 있어 칸 틀 대신 상자 자리 그대로).
  새로 잡힌 상자가 기억 자리에서 MATCH2 장 폭 안이면 그 기억이 다시 보인 것 → 기억을 지우고 새 상자가 그 기억의 깨끗한 조각을 이어받음.
  지움: 그 자리가 손 영역과 CLEAR_OV 미만으로 겹치게 됨(다시 보임) · 또는 그 자리(MATCH 안)에 줄 상자가 잡혀 있음.
  기억 조각은 손 영역 안 화소에만 겹침(손 밖으로 새지 않게) — 테두리 · 글자는 상자 전체에.
틈 색: 첫 프레임 줄 상자 위쪽(패 등 색 띠) 화소의 HSV 중앙값 · 5 ~ 95% 범위(+ 여유)로 배움. 손 영역 ∩ 줄 띠 안에서 그 색과 맞는 화소만.
"""
from __future__ import annotations

from bisect import bisect_right

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import htcommon as hc
import pixtrack as pt
import slotgrid as sg

GROW = 0.25        # 손 영역 넓힘 = 손 크기 × 이것
HOLD = 2           # 손이 안 잡힌 프레임에서 앞 손 영역을 쓰는 최대 프레임 수
GONE_OV = 0.20     # 사라진 상자가 손 영역과 이만큼 겹치면 손 밑으로 들어간 것
CLEAN_OV = 0.02    # 기억 조각으로 쓸 "깨끗한" 프레임: 손 영역과 겹침이 이 이하
CLEAR_OV = 0.10    # 기억 자리가 손 영역과 이 미만으로 겹치면 다시 보이는 것 → 지움
MATCH = 0.5        # 짝짓기 · 다시 잡힘: 가운데 거리 < 장 폭 × 이것
MATCH2 = 1.0       # 남은 것끼리 둘째 짝짓기 · 새 상자가 기억을 이어받는 거리
STABLE = 4         # 깨끗한 조각이 없어도 기억하는 상자: 새 검출 이만큼 넘게 짝지어진 것(줄에 놓여 있던 패)
SKIN_ROW = True    # 줄 둘레 손 · 소매 화소를 손 영역에 더함
SKIN_GROW = 3      # 그 화소 넓힘(화소)
MEM_ALPHA = 0.45
TOP_FRAC = 0.40    # 색 배우기: 상자 위쪽 이 비율(패 등 색 띠)
H_PAD, S_PAD, V_PAD = 4, 20, 25   # 배운 범위 여유(OpenCV HSV: H 0 ~ 179, S · V 0 ~ 255)
MIN_BLOB = 12      # 틈 조각 최소 화소 수
SKY = (120, 220, 255)
DASH = (255, 190, 60)
FONT = "C:/Windows/Fonts/malgun.ttf"


class XRay:
    def __init__(self, tid: str, fj: dict, n: int):
        self.tid, self.n = tid, n
        gid = sg.game_of(tid)
        cfg = hc.config(gid)
        c = (700, 700)
        a = hc.to_view_xy(c, fj["band"], fj["side"])
        b = hc.to_view_xy(c, cfg["sheet_band"], fj["side"])
        self.off = (a[0] - b[0], a[1] - b[1])            # sheet_band 시점 → 넓힌 띠 시점
        self.dxy = (fj["dx"], fj["dy"])
        det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
        ms0, ms1 = fj["frames"][0]["ms"], fj["frames"][-1]["ms"]
        self.det_ms = [m for m in sorted(det) if ms0 - 3000 <= m <= ms1 + 1000]
        self.det = {m: det[m]["b"] for m in self.det_ms}
        self.line = None                                  # 줄 가운데 선 (a, b, hh) — sheet_band 시점
        self.tracks: list[dict] = []
        self.mems: list[dict] = []
        self.prev_mask = None
        self.hold = 0
        self.last_det = None
        self.xspan = None
        self.color = None
        self.pw = None
        self.font = ImageFont.truetype(FONT, 11)
        self.stats = {"gap_px": [], "gap_px_outband": []}

    # ---------------------------------------------------------------- 입력
    def det_at(self, ms: int):
        i = bisect_right(self.det_ms, ms) - 1
        m = self.det_ms[i] if i >= 0 else self.det_ms[0]
        return m, self.det[m]

    def row_boxes(self, ms: int):
        m, bs = self.det_at(ms)
        if self.line is None:
            hh = float(np.median([x[3] - x[2] for x in bs]))
            self.line = (float(np.median([(x[2] + x[3]) / 2 for x in bs])), 0.0, hh)
        a, b, hh = self.line
        row, _off, a, b = sg.row_line(bs, a, b, hh)
        self.line = (a, b, hh)
        ox, oy = self.off
        rects = [(x[0] + ox, x[2] + oy, x[1] + ox, x[3] + oy) for x in row]   # 넓힌 띠 (x0, y0, x1, y1)
        if self.pw is None:
            self.pw = float(np.median([r[2] - r[0] for r in rects]))
        if rects:   # 줄이 지금까지 차지한 가로 범위(늘기만 함) — 손 · 소매 화소를 볼 가로 범위
            lo, hi = min(r[0] for r in rects), max(r[2] for r in rects)
            self.xspan = (lo, hi) if self.xspan is None else (min(self.xspan[0], lo), max(self.xspan[1], hi))
        return m, rects

    def hand_mask(self, hands: list, rgb: np.ndarray, rects: list) -> np.ndarray:
        m = self.lm_mask(hands, rgb.shape)
        if SKIN_ROW and self.xspan is not None:
            band = self.row_band(rgb.shape, 1.0)
            x0 = int(max(0, self.xspan[0] - 1.5 * self.pw))
            x1 = int(min(rgb.shape[1], self.xspan[1] + 2.5 * self.pw))
            band[:, :x0] = False
            band[:, x1:] = False
            sk = pt.masks(rgb)[0] & band
            if sk.any():
                sk = cv2.dilate(sk.astype(np.uint8), np.ones((2 * SKIN_GROW + 1, 2 * SKIN_GROW + 1), np.uint8)).astype(bool)
                m = m | sk
        return m

    def lm_mask(self, hands: list, shape) -> np.ndarray:
        H, W = shape[:2]
        if not hands:
            if self.prev_mask is not None and self.hold < HOLD:
                self.hold += 1
                return self.prev_mask
            self.prev_mask = None
            return np.zeros((H, W), bool)
        self.hold = 0
        dx, dy = self.dxy
        mask = np.zeros((H, W), np.uint8)
        for hd in hands:
            p = np.array([[x - dx, y - dy] for x, y in hd["lm"]], np.float32)
            r = GROW * float(np.hypot(*(p[0] - p[9])))
            one = np.zeros((H, W), np.uint8)
            cv2.fillConvexPoly(one, cv2.convexHull(p).astype(np.int32), 1)
            k = max(1, int(round(r)))
            one = cv2.dilate(one, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
            mask |= one
        self.prev_mask = mask.astype(bool)
        return self.prev_mask

    @staticmethod
    def ov(mask: np.ndarray, r) -> float:
        x0, y0, x1, y1 = (int(round(v)) for v in r)
        x0, y0 = max(0, x0), max(0, y0)
        sub = mask[y0:max(y0, y1), x0:max(x0, x1)]
        return float(sub.mean()) if sub.size else 0.0

    @staticmethod
    def cut(rgb: np.ndarray, r) -> np.ndarray:
        x0, y0, x1, y1 = (int(round(v)) for v in r)
        return rgb[max(0, y0):y1, max(0, x0):x1].copy()

    # ---------------------------------------------------------------- 색 배우기
    def learn_color(self, rgb: np.ndarray, rects: list):
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        px = []
        for x0, y0, x1, y1 in rects:
            w, h = x1 - x0, y1 - y0
            xa, xb = int(round(x0 + 0.15 * w)), int(round(x1 - 0.15 * w))
            ya, yb = int(round(y0 + 0.08 * h)), int(round(y0 + TOP_FRAC * h))
            px.append(hsv[ya:yb, xa:xb].reshape(-1, 3))
        px = np.concatenate(px).astype(np.float32)
        hm = float(np.median(px[:, 0]))
        dh = (px[:, 0] - hm + 90) % 180 - 90              # 색상은 원 — 중앙값 둘레 차이
        self.color = {"h": hm, "dh": (float(np.percentile(dh, 5)) - H_PAD, float(np.percentile(dh, 95)) + H_PAD),
                      "s": (float(np.percentile(px[:, 1], 5)) - S_PAD, float(np.percentile(px[:, 1], 95)) + S_PAD),
                      "v": (float(np.percentile(px[:, 2], 5)) - V_PAD, float(np.percentile(px[:, 2], 95)) + V_PAD),
                      "med": [round(hm, 1), round(float(np.median(px[:, 1])), 1), round(float(np.median(px[:, 2])), 1)],
                      "n_px": int(len(px))}

    def color_mask(self, rgb: np.ndarray, where: np.ndarray) -> np.ndarray:
        ys, xs = np.nonzero(where)
        out = np.zeros(where.shape, bool)
        if not len(ys):
            return out
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        hsv = cv2.cvtColor(np.ascontiguousarray(rgb[y0:y1, x0:x1]), cv2.COLOR_RGB2HSV).astype(np.float32)
        c = self.color
        dh = (hsv[..., 0] - c["h"] + 90) % 180 - 90
        m = ((dh >= c["dh"][0]) & (dh <= c["dh"][1]) & (hsv[..., 1] >= c["s"][0]) & (hsv[..., 1] <= c["s"][1])
             & (hsv[..., 2] >= c["v"][0]) & (hsv[..., 2] <= c["v"][1]) & where[y0:y1, x0:x1])
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        k, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        keep = np.zeros(k, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= MIN_BLOB
        out[y0:y1, x0:x1] = keep[lab]
        return out

    def row_band(self, shape, k: float = 0.8) -> np.ndarray:
        """줄 가운데 선 ± k 상자 높이(넓힌 띠 시점)."""
        H, W = shape[:2]
        a, b, hh = self.line
        ox, oy = self.off
        xs = np.arange(W, dtype=np.float32)
        yc = a + b * (xs - ox) + oy
        ys = np.arange(H, dtype=np.float32)[:, None]
        return np.abs(ys - yc[None, :]) <= k * hh

    # ---------------------------------------------------------------- 한 프레임
    def step(self, k: int, ms: int, rgb: np.ndarray, hands: list):
        dm, rects = self.row_boxes(ms)
        mask = self.hand_mask(hands, rgb, rects)
        if self.color is None:
            self.learn_color(rgb, rects)
        born = 0
        if dm != self.last_det:                               # 새 검출 — 짝짓기 · 생김 · 지움
            self.last_det = dm
            born = self.update(k, rects, mask)
        for t in self.tracks:                                 # 깨끗한 조각 갱신(검출은 0.1초 앞일 수 있으나 줄의 패는 거의 그대로)
            if self.ov(mask, t["rect"]) <= CLEAN_OV:
                t["clean"] = {"patch": self.cut(rgb, t["rect"]), "ms": ms}
        out = self.draw(rgb, mask, ms)
        return out, {"a": len(rects), "b": len(self.mems), "born": born, "det_ms": dm}

    def update(self, k: int, rects: list, mask: np.ndarray) -> int:
        cen = lambda r: ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)  # noqa: E731
        dist = lambda p, q: float(np.hypot(cen(p)[0] - cen(q)[0], cen(p)[1] - cen(q)[1]))  # noqa: E731
        used_t, used_r, new_tracks = set(), set(), []
        for lim in (MATCH * self.pw, MATCH2 * self.pw):
            pairs = sorted((dist(t["rect"], r), ti, ri) for ti, t in enumerate(self.tracks) if ti not in used_t
                           for ri, r in enumerate(rects) if ri not in used_r)
            for d, ti, ri in pairs:
                if d >= lim or ti in used_t or ri in used_r:
                    continue
                used_t.add(ti)
                used_r.add(ri)
                t = self.tracks[ti]
                t["rect"] = rects[ri]
                t["seen"] += 1
                new_tracks.append(t)
        # 새로 잡힌 상자: 가까운 기억이 있으면 그 기억이 다시 보인 것 — 기억을 지우고 조각을 이어받음
        for ri, r in enumerate(rects):
            if ri in used_r:
                continue
            t = {"rect": r, "clean": None, "seen": 1}
            near = [m for m in self.mems if dist(m["rect"], r) < MATCH2 * self.pw]
            if near:
                m = min(near, key=lambda m: dist(m["rect"], r))
                self.mems.remove(m)
                if m["patch"] is not None:
                    t["clean"] = {"patch": m["patch"], "ms": m["ms"]}
                t["seen"] = m["seen"]
            new_tracks.append(t)
        born = 0
        for ti, t in enumerate(self.tracks):
            if ti in used_t:
                continue
            if self.ov(mask, t["rect"]) < GONE_OV:              # 손 밖에서 사라짐 = 실제로 빠진 것
                continue
            if t["clean"] is None and t["seen"] < STABLE:        # 쥐고 옮기던 패
                continue
            self.mems = [m for m in self.mems if dist(m["rect"], t["rect"]) >= MATCH * self.pw]
            cl = t["clean"]
            self.mems.append({"rect": t["rect"], "patch": cl["patch"] if cl else None, "ms": cl["ms"] if cl else None,
                              "k": k, "seen": t["seen"]})
            born += 1
        self.tracks = new_tracks
        keep = []
        for m in self.mems:
            if m["k"] != k and self.ov(mask, m["rect"]) < CLEAR_OV:
                continue                                         # 다시 보임 — 그 자리에 상자가 없으면 실제로 빠진 것
            if any(dist(m["rect"], r) < MATCH * self.pw for r in rects):
                continue                                         # 그 자리에 상자가 잡혀 있음
            keep.append(m)
        self.mems = keep
        return born

    def draw(self, rgb: np.ndarray, mask: np.ndarray, ms: int) -> np.ndarray:
        out = rgb.astype(np.float32)
        H, W = mask.shape
        # (1) 기억 조각: 손 영역 안 화소에만 알파 MEM_ALPHA
        for m in self.mems:
            if m["patch"] is None:
                continue
            p = m["patch"].astype(np.float32)
            cx, cy = (m["rect"][0] + m["rect"][2]) / 2, (m["rect"][1] + m["rect"][3]) / 2
            x0, y0 = int(round(cx - p.shape[1] / 2)), int(round(cy - p.shape[0] / 2))
            xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + p.shape[1]), min(H, y0 + p.shape[0])
            if xa >= xb or ya >= yb:
                continue
            pp = p[ya - y0:yb - y0, xa - x0:xb - x0]
            al = MEM_ALPHA * mask[ya:yb, xa:xb, None]
            out[ya:yb, xa:xb] = out[ya:yb, xa:xb] * (1 - al) + pp * al
        # (2) 틈: 손 영역 ∩ 줄 띠에서 패 등 색 화소 — 원래 화소를 살짝 밝게(기억보다 위)
        band = self.row_band(mask.shape)
        gap = self.color_mask(rgb, mask & band)
        self.stats["gap_px"].append(int(gap.sum()))
        # 피부 걸림 점검용(그리지 않음): 손 영역 중 줄 띠 밖에서 같은 색으로 잡히는 화소 수 — 거기엔 손패가 없으니 대개 피부 · 손톱
        self.stats["gap_px_outband"].append(int(self.color_mask(rgb, mask & ~band).sum()))
        out[gap] = np.minimum(255, rgb[gap].astype(np.float32) * 1.08 + 30)
        img = Image.fromarray(out.clip(0, 255).astype(np.uint8))
        if gap.any():
            edge = gap & ~cv2.erode(gap.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            arr = np.asarray(img).copy()
            arr[edge] = SKY
            img = Image.fromarray(arr)
        # (3) 점선 테두리 · 글자
        d = ImageDraw.Draw(img)
        for m in self.mems:
            x0, y0, x1, y1 = m["rect"]
            dashed_rect(d, x0, y0, x1, y1, DASH)
            s1 = "기억"
            s2 = f"{(ms - m['ms']) / 1000:.1f}초" if m["ms"] is not None else "모습없음"
            for q, s in enumerate((s1, s2)):
                tw = d.textlength(s, font=self.font)
                tx, ty = (x0 + x1) / 2 - tw / 2, y0 + 2 + q * 12
                d.text((tx + 1, ty + 1), s, font=self.font, fill=(0, 0, 0))
                d.text((tx, ty), s, font=self.font, fill=DASH)
        return np.asarray(img)


def dashed_rect(d: ImageDraw.ImageDraw, x0, y0, x1, y1, col, dash=4, gap=3, width=1):
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        L = float(np.hypot(bx - ax, by - ay))
        t = 0.0
        while t < L:
            e = min(L, t + dash)
            d.line([(ax + (bx - ax) * t / L, ay + (by - ay) * t / L), (ax + (bx - ax) * e / L, ay + (by - ay) * e / L)], fill=col, width=width)
            t = e + gap
