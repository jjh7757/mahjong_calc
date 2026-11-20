"""SAM 2 추적으로 손에 가린 손패 보이게 하기(2026-11-20) — xray.py 의 기억 · 장수 · 틈 강조를 SAM 2 번호 마스크에 옮김. 손 관절은 안 씀.

사용자(11-20): "이 기능은 SAM 2 에 적용해야지, 손 관절은 빼고."

  python -X utf8 sam2xray.py r16_d03,r16_d13,r17_d11 [--png 10,20,30] [--fps 2.5]
  → _work/sam2xray_1120/<id>.mp4(+ 확인용 <id>_fNNN.png)

입력 = SAM 2 추적 결과뿐: sam2track.run_dir(<id>, model t · device xpu) 의 frames/(초당 5장 넓힌 띠 그림) · masks.npz(번호 1 ~ n,
  첫 프레임 줄 상자에 왼쪽부터) · 있으면 dmasks.npz(뽑은 패 D, sam2dtrack.py — r16_d03 · r16_d13 · r17_d11 은 11-20 지금 없음).
  가림 영역 = pixtrack.masks 의 살색 + 소매 화소(xray.hand_mask 의 SKIN_ROW 부분과 같은 계산 — 줄 가운데 선 ± 1.0 상자 높이 ·
  줄이 지금까지 차지한 가로 범위 −1.5 ~ +2.5 장 폭, SKIN_GROW 화소 넓힘). 줄 선 · 가로 범위는 slotgrid 검출 상자(det_<판>.json)로 잡음(xray 와 같음).
  손 관절(ov_GPU json · handevents · handcheck)은 읽지 않음. 정답도 읽지 않음.
그리는 것(지어내지 않음 — 생성 · 복원 모델 없음, 기억은 마지막으로 실제 보인 화소뿐):
  (1) 보이는 마스크: 번호마다 sam2img.COLORS 색 반투명 0.5 + 번호 글자(arialbd, 흰 글자 검은 테두리 — sam2img 와 같은 꼴).
      넓이가 깨끗한 때의 50% 밑인 마스크는 relabel 의 "떠 있는 숫자" 꼴(옅은 칠 0.2 · 회색 "o?").
  (2) 기억: 번호 o 가 MEM_IN(50%) 밑으로 줄거나 사라졌고 마지막 깨끗한 마스크 자리가 지금 가림 영역과 GONE_OV(20%) 넘게 겹치면 →
      그 마지막 깨끗한 마스크 자리에서 지금 안 보이는 부분(가림 영역 안 · 지금 o 마스크 밖)에만 그때 원본 화소를 0.45 로 겹치고
      그 번호 색 점선 테두리 + "o 기억" / "n.n초". 다시 MEM_OUT(70%) 넘게 보이면 지움.
      손이 걷혔는데(기억 자리 가림 몫 < CLEAR_OV 10% 가 CLEAR_RUN 프레임) o 가 없으면 기억을 지우고 "o 손 걷힘" 사건(번호를 잃었거나 패가 떠남).
  옮김(아래 사건 띠 2초): 칸 = 첫 프레임 마스크 가운데를 가로 순서로 늘어놓은 틀(1 ~ n, 바깥 0 · n+1, 소수는 칸 사이).
      번호가 자리를 떠난 때 = 기억이 생김 · 줄 밖(줄 선 ± OFFROW 상자 높이 밖)에서 다시 보임("o 줄 밖에 보임") · 손 걷힘 · 한 프레임에 JUMP_SLOT 넘게 뜀.
      그 번호가 줄 위에 깨끗이(손과 안 닿고) 멈추면(0.2초 동안 SETTLE_SLOT 칸 안) 떠난 자리와 비교 — MOVE_SLOT(0.5칸) 넘게 다르면 "o 옮김 a → b칸".
      (처음 지침은 "70% 넘게 다시 보인 순간" 에 쟀으나, 손이 덜 걷혀 아직 밀고 있거나 들린 채 다시 보인 때가 있어 멈춘 뒤로 미룸 —
       r17_d11 의 12 · 13 덩어리는 들려서 다시 보인 순간엔 14 · 15.6칸, 내려놓고 손 뗀 뒤 13 · 14칸.)
      그 마스크가 다른 번호 마스크와 한 패에 겹쳐 있으면(relabel.SAME_TILE) "번호 p 와 한 패에 겹침(미끄러짐일 수 있음)" 을 붙임.
      "o 한 번에 뜀 / 연달아 뜀 a → b칸" 사건도 띄움(이어 뛴 것은 한 줄로) — SAM 2 번호 미끄러짐 · 손에 든 패에 붙은 번호를 숨기지 않으려고.
  (3) 장수: 위 글 띠 "보이는 번호 a · 기억 b · 합 a+b (시작 n)". a = 넓이가 50% 이상이고 기억 중이 아닌 번호(D 추적이 있으면 D 포함).
      더해 "번호 없는 줄 패 c → a+b+c": 줄 검출 상자 중 어느 마스크도 relabel.BOX_COVER 만큼 못 덮고 손에 안 가린 것(흰 점선 "번호 없음")
      — D 추적이 없는 차례의 D, 번호를 잃은 패. 한 패에 번호 둘이면 a 에 둘 다 들어가 a+b+c 가 n+1 을 넘는다(그대로 둠).
  (4) 틈: xray.XRay.learn_color · color_mask 그대로(첫 프레임 줄 상자 위쪽 패 등 색). 찾는 곳은 가림 영역을 GAP_CLOSE 장 폭으로 닫은 것 ∩ 줄 띠(± 0.8 상자 높이)
      — 관절 볼록 껍질이 없으면 가림 화소 자체엔 패 등 색이 없어서(패 등 색이 아닌 것이 가림) 손가락 사이 구멍을 메워 찾음.
      살짝 밝게 + 윤곽: 조각의 반 넘게가 번호 o 의 지금 마스크 안이면 그 번호 색, 아니면 하늘색. 손톱이 패 등 색과 닮으면 잘못 잡힘(r17_d11).
  (5) 아래 사건 띠: slotgrid cmd_events(칸 틀 사건, handvideo 와 같은 줄 뽑기) · 옮김 · 줄 밖 · 손 걷힘 · 뜀 — 시작부터 2초 안인 줄.
결과 요약: <id>_info.json(장수 구간 · {n, n+1} 밖 프레임 · 기억 구간 · 사건 목록 · 틈 화소).
재생: 초당 5장을 --fps(기본 2.5)로 — 2배 느리게, libx264 · yuv420p. 그림은 가로 --width(기본 1280, 최대 SCALE_MAX 배)까지 키워 글자를 그림.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import re
import subprocess
import sys
from bisect import bisect_right
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402
import relabel as rl  # noqa: E402
import sam2img as si  # noqa: E402
import sam2track as s1  # noqa: E402
import slotgrid as sg  # noqa: E402
import xray as xr  # noqa: E402

OUT = hc.WORK / "sam2xray_1120"
V1 = argparse.Namespace(model="t", device="xpu")
MEM_IN = 0.50      # 깨끗한 때 넓이(중앙값)의 이 밑이면 "줄었음"
MEM_OUT = 0.70     # 이 넘게 다시 보이면 기억 지움
GONE_OV = 0.20     # 마지막 깨끗한 마스크 화소 중 지금 가림 영역에 든 몫이 이 넘으면 손 밑
CLEAN_OV = 0.02    # 깨끗이 보인 때: 마스크 상자 안 가림 영역 몫이 이 이하
CLEAR_OV = 0.10    # 기억 자리의 가림 몫이 이 미만으로 CLEAR_RUN 프레임 이어지면 손이 걷힌 것
CLEAR_RUN = 2
MOVE_SLOT = 0.5    # 다시 보인 자리가 기억 자리와 이 칸 넘게 다르면 옮김
OFFROW = 0.5      # 마스크 가운데가 줄 선에서 이 × 상자 높이 넘게 떨어지면 줄 밖
GAP_CLOSE = 0.4   # 틈 찾기: 가림 영역을 이 × 장 폭 크기로 닫아(손가락 사이 구멍을 메워) 그 안에서 패 등 색을 찾음
NOLAB_OCC = 0.30  # 번호 없는 패 표시: 상자 안 가림 몫이 이 미만인 것만(손 밑 상자는 안 그림)
SETTLE_SLOT = 0.25 # 줄 위에 멈춤: 0.2초 동안 이 칸 안에서만 움직임
JUMP_SLOT = 1.0    # 보이던 번호가 한 프레임 만에 이 칸 넘게 뛰면 "뜀"
MEM_ALPHA = 0.45
MASK_ALPHA = 0.5   # sam2img 와 같음
FLOAT_ALPHA = 0.2  # relabel 떠 있는 숫자와 같음
SKIN_GROW = xr.SKIN_GROW
SHOW_SEC = 2.0
SCALE_MAX = 1.6
FONT = "C:/Windows/Fonts/malgun.ttf"
FONT_B = "C:/Windows/Fonts/malgunbd.ttf"
TOP_H, LINE_H, BOT_LINES = 80, 22, 5
SKY = xr.SKY


def font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except OSError:
        return ImageFont.truetype(FONT, size)


def fit(d: ImageDraw.ImageDraw, s: str, f, w: int) -> str:
    if d.textlength(s, font=f) <= w:
        return s
    while s and d.textlength(s + "…", font=f) > w:
        s = s[:-1]
    return s + "…"


def sec_of_hour(s: str) -> float:
    mm, ss = s.split(":")
    return int(mm) * 60 + float(ss)


def grid_events(tid: str) -> list:
    """slotgrid cmd_events 출력 → [(시각 초(시간 안), 글)] — handvideo.grid_events 와 같은 줄 뽑기(손 관절 모듈을 안 불러오려고 옮겨 씀)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sg.cmd_events(argparse.Namespace(ids=[tid], count=False))
    out = []
    for ln in buf.getvalue().splitlines():
        m = re.match(r"\s+(\d{2}:\d{2}\.\d)(?:\(프레임 \d+\))?\s+(.*)$", ln)
        if m:
            out.append((sec_of_hour(m.group(1)), "칸 틀 " + m.group(1) + "  " + m.group(2).strip()))
    return out


def color_of(o) -> tuple:
    return (255, 255, 255) if o == "D" else si.COLORS[(int(o) - 1) % len(si.COLORS)]


def bbox(mk: np.ndarray):
    ys, xs = np.nonzero(mk)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


class SamXRay:
    def __init__(self, tid: str):
        self.tid = tid
        self.T = rl.Track(tid)
        T = self.T
        self.n, self.F, self.H, self.W = T.n, T.F, T.H, T.W
        self.ms = T.tr["frames"]
        p = T.tr["plan"]
        d = T.d
        self.DM = np.load(d / "dmasks.npz") if (d / "dmasks.npz").exists() else None
        self.objs = list(range(1, self.n + 1)) + (["D"] if self.DM is not None else [])
        # 검출 상자(줄 선 · 가로 범위용) — sheet_band 시점 → 넓힌 띠 시점은 같은 회전이라 상수 이동
        gid = p["gid"]
        det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
        self.det_ms = [m for m in sorted(det) if self.ms[0] - 3000 <= m <= self.ms[-1] + 1000]
        self.det = {m: det[m]["b"] for m in self.det_ms}
        b0 = self.det[self.det_ms[0]][0]
        r0 = s1.remap_box(b0, p["band"], p["band2"], p["side"])
        self.off = (r0[0] - b0[0], r0[1] - b0[2])
        self.line, self.xspan, self.pw = None, None, None
        # 첫 프레임 마스크 가운데 = 칸 틀
        cx = sorted(float(np.nonzero(m)[1].mean()) for o in range(1, self.n + 1) if (m := T.mask(0, o)) is not None)
        self.c1, self.pitch = cx[0], float(np.median(np.diff(cx)))
        self.lab_font = ImageFont.truetype("arialbd.ttf", 15)
        self.sub = SimpleNamespace(color=None)       # xray.XRay.learn_color · color_mask 를 그대로 부르려는 껍데기

    # ------------------------------------------------------------------ 입력
    def mask(self, fi: int, o):
        if o != "D":
            return self.T.mask(fi, o)
        if str(fi) not in self.DM:
            return None
        mk = np.unpackbits(self.DM[str(fi)])[: self.H * self.W].reshape(self.H, self.W).astype(bool)
        return mk if mk.sum() >= rl.MIN_AREA else None

    def slot(self, x: float) -> float:
        return 1 + (x - self.c1) / self.pitch

    def row_rects(self, ms: int):
        i = bisect_right(self.det_ms, ms) - 1
        bs = self.det[self.det_ms[max(0, i)]]
        if self.line is None:
            hh = float(np.median([x[3] - x[2] for x in bs]))
            self.line = (float(np.median([(x[2] + x[3]) / 2 for x in bs])), 0.0, hh)
        a, b, hh = self.line
        row, _o, a, b = sg.row_line(bs, a, b, hh)
        self.line = (a, b, hh)
        ox, oy = self.off
        rects = [(x[0] + ox, x[2] + oy, x[1] + ox, x[3] + oy) for x in row]
        if self.pw is None:
            self.pw = float(np.median([r[2] - r[0] for r in rects]))
        if rects:
            lo, hi = min(r[0] for r in rects), max(r[2] for r in rects)
            self.xspan = (lo, hi) if self.xspan is None else (min(self.xspan[0], lo), max(self.xspan[1], hi))
        return rects

    def row_band(self, k: float) -> np.ndarray:
        a, b, hh = self.line
        ox, oy = self.off
        xs = np.arange(self.W, dtype=np.float32)
        yc = a + b * (xs - ox) + oy
        ys = np.arange(self.H, dtype=np.float32)[:, None]
        return np.abs(ys - yc[None, :]) <= k * hh

    def occ_mask(self, rgb: np.ndarray) -> np.ndarray:
        """xray.hand_mask 의 SKIN_ROW 부분(관절 영역은 없음)."""
        band = self.row_band(1.0)
        x0 = int(max(0, self.xspan[0] - 1.5 * self.pw))
        x1 = int(min(self.W, self.xspan[1] + 2.5 * self.pw))
        band[:, :x0] = False
        band[:, x1:] = False
        sk = pt.masks(rgb)[0] & band
        if sk.any():
            sk = cv2.dilate(sk.astype(np.uint8), np.ones((2 * SKIN_GROW + 1, 2 * SKIN_GROW + 1), np.uint8)).astype(bool)
        return sk

    @staticmethod
    def box_ov(occ: np.ndarray, mk: np.ndarray) -> float:
        x0, y0, x1, y1 = bbox(mk)
        return float(occ[y0:y1, x0:x1].mean())

    # ------------------------------------------------------------------ 한 바퀴: 프레임마다 마스크 · 가림 · 깨끗한 때
    def pass1(self):
        """넓이 · 깨끗한 때 · 가림 영역(묶어 저장)만 — 그림 · 마스크는 둘째 바퀴에서 다시 읽음(메모리)."""
        self.occ_bits, self.lines, self.rects = [], [], []
        area = {o: [] for o in self.objs}
        clean = {o: [] for o in self.objs}
        for fi in range(self.F):
            rgb = self.T.raw(fi).astype(np.uint8)
            rects = self.row_rects(self.ms[fi])
            if self.sub.color is None:
                xr.XRay.learn_color(self.sub, rgb, rects)
            occ = self.occ_mask(rgb)
            for o in self.objs:
                mk = self.mask(fi, o)
                area[o].append(int(mk.sum()) if mk is not None else 0)
                if mk is not None and self.box_ov(occ, mk) <= CLEAN_OV:
                    clean[o].append(fi)
            self.occ_bits.append(np.packbits(occ))
            self.lines.append(self.line)
            self.rects.append(rects)
        self.area = area
        self.med = {}
        for o in self.objs:
            xs = [area[o][fi] for fi in clean[o]] or [a for a in area[o] if a > 0] or [1]
            self.med[o] = float(np.median(xs))
        self.clean = {o: set(v) for o, v in clean.items()}

    def occ_at(self, fi: int) -> np.ndarray:
        return np.unpackbits(self.occ_bits[fi])[: self.H * self.W].reshape(self.H, self.W).astype(bool)

    # ------------------------------------------------------------------ 둘째 바퀴: 기억 · 사건 · 그림
    def run(self):
        self.pass1()
        mems: dict = {}          # o → {"mk", "patch", "ms", "pos", "p0", "t0", "clear"}
        used: dict = {}          # o → 손 걷힘으로 지운 기억의 깨끗한 때(ms) — 빈 자리를 본 뒤 같은 조각으로 되살리지 않음
        carry: dict = {}         # o → (떠난 자리 칸, 시각, 까닭) — 줄 밖으로 들렸거나 · 손 걷힘 뒤 안 보이거나 · 뛴 번호. 줄 위에 다시 멈추면 순 옮김을 잼
        last_clean: dict = {}    # o → (마스크, 원본, ms)
        prev_pos: dict = {}
        streak: dict = {}        # o → [첫 자리, 지금 자리, 뜀 수, 첫 시각] — 0.2초마다 이어 뛴 것을 한 사건으로
        events = []              # (ms, 글, 종류)
        per = []
        for fi in range(self.F):
            ms, occ = self.ms[fi], self.occ_at(fi)
            rgb = self.T.raw(fi).astype(np.uint8)
            mks = {o: self.mask(fi, o) for o in self.objs}
            self.line = self.lines[fi]
            for o in self.objs:
                mk = mks[o]
                if mk is not None and fi in self.clean[o]:
                    last_clean[o] = (mk, rgb, ms)
            for o in self.objs:
                mk, a, med = mks[o], self.area[o][fi], self.med[o]
                pos = self.slot(float(np.nonzero(mk)[1].mean())) if mk is not None else None
                vis = a >= MEM_IN * med
                if o in mems:
                    m = mems[o]
                    if a > MEM_OUT * med:                          # 다시 보임 → 기억 지움
                        del mems[o]
                        if self.on_row(mk):                        # 옮김은 깨끗이 멈춘 뒤 아래에서 잼(손이 덜 걷혀 밀고 있는 중일 수 있음)
                            carry[o] = (m["p0"], m["t0"], "손 밑에 있다가")
                        else:
                            events.append((ms, f"{o} 줄 밖에 보임(손에 든 패 · 또는 번호가 딴 데 붙음) — {self.slot_txt(m['p0'])} 자리에서 손 밑 {(ms - m['t0']) / 1000:.1f}초 뒤", "out"))
                            carry[o] = (m["p0"], m["t0"], "줄 밖에 들렸다가")
                    else:
                        ov = float(occ[m["mk"]].mean())
                        m["clear"] = m["clear"] + 1 if ov < CLEAR_OV else 0
                        if m["clear"] >= CLEAR_RUN:                # 손이 걷혔는데 그 자리에 o 가 없음
                            events.append((ms, f"{o} 손 걷힘 — 옛 자리({self.slot_txt(m['pos'])})에 {o} 마스크 없음", "lost"))
                            carry[o] = (m["p0"], m["t0"], "안 보이다가")
                            used[o] = m["ms"]
                            del mems[o]
                elif not vis and o in last_clean and used.get(o) != last_clean[o][2]:
                    lm, lrgb, lms = last_clean[o]
                    if float(occ[lm].mean()) > GONE_OV:            # 줄었고 마지막 깨끗한 자리가 손 밑 → 기억
                        p = self.slot(float(np.nonzero(lm)[1].mean()))
                        c = carry.pop(o, None)
                        mems[o] = {"mk": lm, "patch": lrgb, "ms": lms, "pos": p, "p0": c[0] if c else p,
                                   "t0": c[1] if c else ms, "clear": 0}
                jumped = vis and o not in mems and prev_pos.get(o) is not None and pos is not None and abs(pos - prev_pos[o]) > JUMP_SLOT
                if jumped:
                    if o in streak:
                        streak[o][1], streak[o][2] = pos, streak[o][2] + 1
                    else:
                        streak[o] = [prev_pos[o], pos, 1, ms]
                        carry.setdefault(o, (prev_pos[o], ms, "뛰었다가"))
                elif o in streak:                                   # 뜀이 끝남 → 한 사건
                    p0, p1, k, t0 = streak.pop(o)
                    if k == 1:
                        s_ = f"{o} 한 번에 뜀 {self.slot_txt(p0, p1)} (0.2초)"
                    else:
                        s_ = f"{o} 연달아 뜀 {self.slot_txt(p0, p1)} ({k}번 · {(ms - t0) / 1000:.1f}초 — 손에 든 패에 붙었거나 번호 미끄러짐)"
                    events.append((ms, s_ + f" · {hc.mss(t0)} 부터", "jump"))
                # 가렸던 · 들렸던 · 뛰었던 번호가 줄 위에 깨끗이 멈춤(손과 안 닿음 · 0.2초 동안 SETTLE 칸 안) → 떠난 자리와 비교
                if (o in carry and vis and o not in mems and o not in streak and prev_pos.get(o) is not None
                        and abs(pos - prev_pos[o]) <= SETTLE_SLOT and fi in self.clean[o] and self.on_row(mk)):
                    p0, t0, why = carry.pop(o)
                    if abs(pos - p0) > MOVE_SLOT:
                        events.append((ms, self.move_txt(o, p0, pos, f"{why} {(ms - t0) / 1000:.1f}초 뒤 줄에 멈춤(손 떨어짐)", mks), "move"))
                prev_pos[o] = pos if (vis and o not in mems) else None
            na = sum(1 for o in self.objs if self.area[o][fi] >= MEM_IN * self.med[o] and o not in mems)
            nolab = self.unnumbered(fi, mks, occ)
            per.append({"fi": fi, "ms": ms, "a": na, "b": len(mems), "mems": sorted(str(o) for o in mems), "nolab": len(nolab),
                        "img": self.draw(fi, mems, rgb, occ, mks, nolab)})
            yield per[-1], events

    def move_txt(self, o, p0: float, pos: float, why: str, mks: dict) -> str:
        """옮김 글 — 그 마스크가 다른 번호 마스크와 한 패에 겹쳐 있으면(relabel SAME_TILE) 미끄러짐일 수 있다고 붙임."""
        mk = mks[o]
        same = [str(q) for q, m2 in mks.items() if q != o and m2 is not None
                and (mk & m2).sum() / max(1, min(mk.sum(), m2.sum())) >= rl.SAME_TILE]
        tail = f" · 번호 {', '.join(same)} 와 한 패에 겹침(미끄러짐일 수 있음)" if same else ""
        return f"{o} 옮김 {self.slot_txt(p0, pos)} — {why}{tail}"

    def unnumbered(self, fi: int, mks: dict, occ: np.ndarray) -> list:
        """줄 검출 상자 중 지금 어느 번호 마스크도 BOX_COVER 만큼 못 덮은 것(손에 안 가린 것만) — D(추적 없음)나 번호를 잃은 패."""
        allm = np.zeros((self.H, self.W), bool)
        for mk in mks.values():
            if mk is not None:
                allm |= mk
        out = []
        for x0, y0, x1, y1 in self.rects[fi]:
            xa, ya, xb, yb = int(max(0, x0)), int(max(0, y0)), int(min(self.W, x1)), int(min(self.H, y1))
            if xb <= xa or yb <= ya:
                continue
            if allm[ya:yb, xa:xb].mean() < rl.BOX_COVER and occ[ya:yb, xa:xb].mean() < NOLAB_OCC:
                out.append((xa, ya, xb, yb))
        return out

    def on_row(self, mk: np.ndarray) -> bool:
        """마스크 가운데가 줄 가운데 선 ± OFFROW 상자 높이 안인가(지금 프레임 줄 선)."""
        ys, xs = np.nonzero(mk)
        a, b, hh = self.line
        ox, oy = self.off
        return abs(float(ys.mean()) - (a + b * (float(xs.mean()) - ox) + oy)) <= OFFROW * hh

    def slot_txt(self, a: float, b: float | None = None) -> str:
        def one(x):
            r = int(round(x))
            return f"{r}칸" if 0 <= r <= self.n + 1 else f"{x:.1f}칸"
        if b is None:
            return one(a)
        ra, rb = int(round(a)), int(round(b))
        if ra == rb:
            return f"{a:.1f} → {b:.1f}칸"
        return f"{one(a)[:-1]} → {one(b)}"

    # ------------------------------------------------------------------ 그림
    def draw(self, fi: int, mems: dict, rgb: np.ndarray, occ: np.ndarray, mks: dict, nolab: list) -> Image.Image:
        out = rgb.astype(np.float32)
        allm = {}
        cents = []
        for o in self.objs:
            mk = mks[o]
            if mk is None:
                continue
            fl = self.area[o][fi] < MEM_IN * self.med[o]
            al = FLOAT_ALPHA if fl else (0.65 if o == "D" else MASK_ALPHA)
            out[mk] = (1 - al) * out[mk] + al * np.array(color_of(o), np.float32)
            if o == "D":
                inner = cv2.erode(mk.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
                out[mk & ~inner] = 0
            allm[o] = mk
            ys, xs = np.nonzero(mk)
            cents.append((o, xs.mean(), ys.mean(), fl))
        # 기억 조각: 마지막 깨끗한 마스크 자리 ∩ 지금 가림 영역 − 지금 그 번호 마스크, 그때 원본 화소를 MEM_ALPHA 로
        for o, m in mems.items():
            where = m["mk"] & occ
            if allm.get(o) is not None:
                where &= ~allm[o]
            if where.any():
                out[where] = out[where] * (1 - MEM_ALPHA) + m["patch"][where].astype(np.float32) * MEM_ALPHA
        # 틈: 가림 영역 ∩ 줄 띠의 패 등 색 화소
        k = max(3, int(round(GAP_CLOSE * self.pw)) | 1)
        hand = cv2.morphologyEx(occ.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(bool)
        gap = xr.XRay.color_mask(self.sub, rgb, hand & self.row_band(0.8))
        out[gap] = np.minimum(255, rgb[gap].astype(np.float32) * 1.08 + 30)
        arr = out.clip(0, 255).astype(np.uint8)
        if gap.any():
            k, lab, _st, _ = cv2.connectedComponentsWithStats(gap.astype(np.uint8), connectivity=8)
            edge = gap & ~cv2.erode(gap.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            col_of = {}
            for c in range(1, k):
                comp = lab == c
                npx = comp.sum()
                best = max(((float((comp & mk).sum()) / npx, o) for o, mk in allm.items()), key=lambda t: t[0], default=(0.0, None))
                col_of[c] = color_of(best[1]) if best[0] > 0.5 else SKY
            for c, col in col_of.items():
                arr[edge & (lab == c)] = col
        self.gap_px = getattr(self, "gap_px", []) + [int(gap.sum())]
        sc = self.scale
        Ws, Hs = int(round(self.W * sc)) // 2 * 2, int(round(self.H * sc))
        img = Image.fromarray(arr).resize((Ws, Hs), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        # 번호 없는 줄 패: 흰 점선 + "번호 없음"
        nf = font(max(10, int(round(10 * sc))), True)
        for x0, y0, x1, y1 in nolab:
            xr.dashed_rect(d, x0 * sc, y0 * sc, x1 * sc, y1 * sc, (255, 255, 255), dash=3, gap=3, width=1)
            for q, t in enumerate(("번호", "없음")):
                tw = d.textlength(t, font=nf)
                d.text(((x0 + x1) * sc / 2 - tw / 2, y1 * sc - 2 * (nf.size + 2) - 2 + q * (nf.size + 2)), t, font=nf,
                       fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        # 기억 테두리 · 글자
        mf = font(max(11, int(round(11 * sc))), True)
        for o, m in mems.items():
            x0, y0, x1, y1 = (v * sc for v in bbox(m["mk"]))
            col = color_of(o)
            xr.dashed_rect(d, x0, y0, x1, y1, col, dash=5, gap=3, width=2)
            for q, s in enumerate((f"{o} 기억", f"{(self.ms[fi] - m['ms']) / 1000:.1f}초")):
                tw = d.textlength(s, font=mf)
                d.text(((x0 + x1) / 2 - tw / 2, y0 + 2 + q * (mf.size + 2)), s, font=mf, fill=col, stroke_width=2, stroke_fill=(0, 0, 0))
        # 번호 글자(sam2img 꼴 — 겹치면 위로 비켜 씀)
        lf = ImageFont.truetype("arialbd.ttf", max(15, int(round(15 * sc))))
        seen = {}
        for o, x, y, fl in cents:
            x, y = x * sc, y * sc
            k = (round(x / (14 * sc)), round(y / (14 * sc)))
            off = seen.get(k, 0)
            seen[k] = off + 1
            yy = y - 15 * sc * off
            if fl:
                d.text((x, yy), f"{o}?", fill=(200, 200, 200), font=lf, anchor="mm", stroke_width=2, stroke_fill=(60, 60, 60))
            elif o == "D":
                d.text((x, yy - 17 * sc), "D", fill=(230, 0, 0), font=lf, anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255))
            else:
                d.text((x, yy), str(o), fill=(255, 255, 255), font=lf, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
        return img


def frame(img: Image.Image, head1: str, head2: str, head3: str, lines: list) -> Image.Image:
    Ws, Hs = img.size
    bot_h = BOT_LINES * LINE_H + 8
    canvas = Image.new("RGB", (Ws, TOP_H + Hs + bot_h), (16, 16, 16))
    canvas.paste(img, (0, TOP_H))
    c = ImageDraw.Draw(canvas)
    c.text((8, 4), fit(c, head1, font(19, True), Ws - 16), font=font(19, True), fill=(255, 255, 255))
    c.text((8, 30), fit(c, head2, font(14), Ws - 16), font=font(14), fill=(200, 200, 200))
    c.text((8, 52), fit(c, head3, font(18, True), Ws - 16), font=font(18, True), fill=(255, 190, 60))
    fe = font(15)
    y0 = TOP_H + Hs + 4
    cols = {"grid": (150, 210, 255), "move": (255, 200, 80), "lost": (255, 140, 140), "jump": (190, 190, 190), "out": (210, 170, 255)}
    for q, (kind, s) in enumerate(lines[-BOT_LINES:]):
        c.text((8, y0 + q * LINE_H), fit(c, s, fe, Ws - 16), font=fe, fill=cols[kind])
    if canvas.size[1] % 2:
        canvas = canvas.crop((0, 0, canvas.size[0], canvas.size[1] - 1))
    return canvas


def make(tid: str, fps: float, width: int, png: list | None, ff: str) -> dict:
    X = SamXRay(tid)
    X.scale = min(SCALE_MAX, width / X.W)
    gev = grid_events(tid)
    n, F = X.n, X.F
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{tid}.mp4"
    proc, size, counts, counts3, rows = None, None, [], [], []
    imgs = {}
    dnote = "D 추적 있음(흰 칠 · 빨간 D)" if X.DM is not None else "뽑은 패 D 추적 없음"
    for info, events in X.run():
        fi, ms = info["fi"], info["ms"]
        now = (ms / 1000) % 3600
        head1 = f"{tid}  프레임 {fi:03d}/{F - 1:03d}  {hc.mss(ms)}  SAM 2 추적(초당 5장) · 0.5배속 · 손 관절 안 씀 · {dnote}"
        head2 = (f"색 · 숫자 = SAM 2 번호(첫 프레임 왼쪽부터 1 ~ {n}, 미끄러질 수 있음) · o? = 넓이 50% 밑 · 색 점선 = 기억(마지막으로 보인 모습, 손 밑에만)"
                 f" · 흰 점선 = 번호 없는 패 · 하늘색 = 손가락 틈 패 등")
        head3 = f"보이는 번호 {info['a']} · 기억 {info['b']} · 합 {info['a'] + info['b']} (시작 {n})" + (f" · 번호 없는 줄 패 {info['nolab']} → {info['a'] + info['b'] + info['nolab']}" if info["nolab"] else "") + \
                (f"   기억: {', '.join(info['mems'])}" if info["mems"] else "")
        counts.append(info["a"] + info["b"])
        counts3.append(info["a"] + info["b"] + info["nolab"])
        lines = []
        for t, s in gev:
            dt = (now - t + 1800) % 3600 - 1800
            if -0.05 <= dt < SHOW_SEC:
                lines.append((dt, "grid", s))
        for ems, s, kind in events:
            dt = (ms - ems) / 1000
            if 0 <= dt < SHOW_SEC:
                lines.append((dt, kind, f"{hc.mss(ems)}  {s}"))
        lines.sort(key=lambda x: -x[0])
        img = frame(info["img"], head1, head2, head3, [(k, s) for _, k, s in lines])
        if proc is None:
            size = img.size
            proc = subprocess.Popen([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                     "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-",
                                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
                                     "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
        assert img.size == size
        proc.stdin.write(img.tobytes())
        imgs[fi] = img if png and fi in png else None
        rows.append({k: v for k, v in info.items() if k != "img"})
        evs = events
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"{tid}: ffmpeg 실패")
    for fi in png or []:
        if imgs.get(fi) is not None:
            imgs[fi].save(OUT / f"{tid}_f{fi:03d}.png")
    runs = []
    for k, c in enumerate(counts):
        if runs and runs[-1][0] == c:
            runs[-1][2] = k
        else:
            runs.append([c, k, k])
    mem_runs = {}
    for r in rows:
        for o in r["mems"]:
            mem_runs.setdefault(o, []).append(r["fi"])
    res = {"id": tid, "mp4": out.as_posix(), "frames": F, "fps": fps, "sec": round(F / fps, 1), "size": size,
           "bytes": out.stat().st_size, "n": n, "D_track": X.DM is not None,
           "off_n_n1": sum(c not in (n, n + 1) for c in counts), "count_runs": runs,
           "mem_frames": {o: rl.si_ranges(v) for o, v in mem_runs.items()},
           "events": [(hc.mss(e[0]), e[2], e[1]) for e in evs], "med_area": {str(o): round(v) for o, v in X.med.items()},
           "gap_px_med": float(np.median(X.gap_px)), "gap_px_max": int(max(X.gap_px)), "gap_frames": int(sum(g > 0 for g in X.gap_px)),
           "nolab_frames": int(sum(r["nolab"] > 0 for r in rows)), "color": X.sub.color,
           "off_frames": rl.si_ranges([k for k, c in enumerate(counts) if c not in (n, n + 1)]),
           "off3_n_n1": sum(c not in (n, n + 1) for c in counts3),
           "off3_frames": rl.si_ranges([k for k, c in enumerate(counts3) if c not in (n, n + 1)]),
           "gap_top": sorted(range(F), key=lambda k: -X.gap_px[k])[:6],
           "png": [(OUT / f"{tid}_f{fi:03d}.png").as_posix() for fi in (png or [])]}
    hc.jsave(OUT / f"{tid}_info.json", res, indent=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids")
    ap.add_argument("--fps", type=float, default=2.5, help="재생 초당 장수(SAM 2 프레임 초당 5장 — 2.5 면 2배 느리게)")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--png", default=None, help="확인용 프레임 번호(쉼표)")
    a = ap.parse_args()
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    png = [int(x) for x in a.png.split(",")] if a.png else None
    for tid in a.ids.split(","):
        r = make(tid, a.fps, a.width, png, ff)
        print({k: v for k, v in r.items() if k not in ("color",)}, flush=True)


if __name__ == "__main__":
    main()
