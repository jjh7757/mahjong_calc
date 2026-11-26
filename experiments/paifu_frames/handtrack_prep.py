"""자동 패보 S6a — 손 추적 준비 읽기(설계서 docs/paifu_auto_agent_design_1124.md 8-8절, 2026-11-24 저녁).

화소 규칙(handtrack_auto.py conf — 2반장에 맞춘 규칙, 3반장 t_ready 2/11)을 기본 흐름에서 빼고, 눈으로 봐야 하는 판단(손패 줄 영역 ·
줄이 선 때 · 공개 프레임)을 읽기 에이전트(Opus 높음 하위 에이전트, 세션이 띄움)에게 넘긴다. 이 파일은 그 앞뒤의 코드 몫이다.

  S6a-1 꾸러미(pack):  python -X utf8 experiments/paifu_frames/handtrack_prep.py pack  --cfg <반장 설정 json> --spec <spec.json> --out <꾸러미 폴더>
      → <꾸러미>/TASK.md · overview/*.jpg(원본 프레임 + 녹화 틀 영역 + 100px 눈금) · frames_ready.txt · frames_reveal.txt · backs.md · pack.json
      화소 규칙이 고른 값(t_ready · reveal_frame 등)은 넣지 않는다(끌려가지 않게).
  S6a-3 적용 · 검사(apply):  python -X utf8 experiments/paifu_frames/handtrack_prep.py apply --cfg <실행 hanchan.json> --spec <spec.json> --answer <answer.json> --out <결과 json>
      → 판별 설정(<handtrack.dir>/config/<판>.json — ht_redirect 가 실행 폴더로 돌림) + features + 검사(검출기). 설정이 바뀌었으면 그 판의 옛 판별 출력
      (features · segments · river_states · game · 칸 틀 캐시 det_<판>.json)을 지우고 다시 만들게 한다. 공용 자리(handtrack/config · results/handtrack)에는 안 씀 —
      반장 설정에 handtrack.dir 이 없거나 그 판이 handtrack.games 에 없으면 멈춘다.

  S6a-2 돌려 보기(try — 설계서 8-9, 11-24 밤, 읽기 에이전트가 직접 부름):
      python -X utf8 experiments/paifu_frames/handtrack_prep.py try --pack <꾸러미 폴더> --answer <초안 답 json> [--n <시도 번호>]
      → <꾸러미>/try/<n>/ 에서만: 초안 답 → 판별 설정 · features(apply) → segment · river · game · bandfit(handtrack_auto run) →
        han3 turns · fix · turncut(칸 틀 검출 slotgrid 는 안 돌림) → 보고서 <꾸러미>/try/<n>/report.md(표준 출력에도) · report.json · frames_turns.txt.
      시험 자리마다 반장 설정 사본(try/<n>/cfg/hanchan.json — prep_dir · read_root · handtrack.dir 이 모두 그 시험 자리, handtrack.games = [이 판])을
      만들어 쓰므로 공용 자리 · 실행 폴더의 handtrack/ · _prep 에 안 쓰고, 여러 판(같은 판의 다른 번호도)을 동시에 돌려도 안 겹친다.
      재료는 pack.json 의 try 칸(pack 이 넣음 — 반장 설정 · 기록 폴더 · 판 결과 경로)만 쓴다. 판당 MAX_TRIES 번까지(넘으면 멈춤).

(11-25, 설계서 8-13) 손패 줄 후보(bandcand):  python -X utf8 experiments/paifu_frames/handtrack_prep.py bandcand --cfg <반장 설정> --side <자리> --t0 <시각> --t1 <시각> --out <json>
      손패 주인 쪽 화면 절반에서 검출기 뒷면 상자가 한 줄로 선 곳 → 후보 셋(band_candidates 머리 주석의 규칙 — 21개 손 설정에 맞춰 다듬지 않음).
  기본 길 모드(spec regions_mode "half" — 반장 설정에 녹화 틀 frame 이 없을 때 paifu_auto S6a 가 만듦): 영역 = wide(화면 절반) · band · search(후보 1위),
      후보 2 · 3위는 그림 · 표에만. pack 의 TASK.md 는 강 · 울기 · 공개 영역을 묻지 않음(task_half). 공개 영역이 없으면 공개 앞면 상자 검사 · game.py 를 안 함.
      (11-25, 설계서 8-14 (가)) river · meld 는 paifu_auto S6a 가 버림 기록기 덤프에서 낸 코드 값(dump_regions.py)이 spec regions 에 들어 온다 —
      그림에만 그리고 묻지 않으며, 답에 그 영역이 있어도 답 값이 아니라 코드 값을 쓴다(CODE_REGIONS). 그래도 없으면 멈춘다(features.py 가 읽음).
  앱 기록 반장(설정 app_record): try 는 강 읽기(river) 걸음을 빼고(handtrack_auto run --no-river) 차례 목록을 기록에서(han3 rturns) 만든다(8-13 (가)).
(11-25 밤, 설계서 8-16) 답 칸 t_ready_late {"time": 시각 또는 null, "why"} — 정리인지 한 장 끼움인지 가리기 어려운 동작을 정리로 볼 때의 줄이 선 때.
  apply · try 는 그 값이 답의 t_ready 보다 뒤면 그것을 판별 설정 t_ready 로 쓴다(같거나 앞이면 무시 · 그 뒤 손패 주인 버림이 0 이면 안 쓰고 질문 ·
  t_reveal 과 같거나 뒤면 답 꼴 오류). 적용 결과 ready_late 에 답의 값 · 늦은 후보 · 쓴 값을 남김. 칸이 없거나 time 이 null 이면 옛 그대로.
  지시문 글(늦은 후보 · 사실 고침 세 곳)은 기본 길 모드(task_half)에만 — 옛 길의 TASK.md 는 그대로.
(11-26, 설계서 8-19) 답의 unsure 줄 = {"what": 칸, "alt": 다른 후보 값 또는 null, "why"}(지시문 답 꼴 · 설명 줄 — 두 모드 모두).
  대안 돌리기(alt):  python -X utf8 experiments/paifu_frames/handtrack_prep.py alt --pack <꾸러미> --answer <답> --out <대안 자리> [--result <json>]
      → <대안 자리>/0(답 그대로 — 기준) · <n>(n 번째 unsure 의 what 칸만 alt 로)에서 try 와 같은 걸음(_try_steps)을 돌려 차례 목록 · 창을 견줌(cmd_alt 주석).
      try 번호 · MAX_TRIES 와 무관하고 꾸러미의 try/ 는 안 건드림. paifu_auto S6a-3 이 판마다 부르고 결과(s6a/_alt/<판>.json)로 질문을 가른다.

spec(paifu_auto.ht_spec 가 만듦 — 3반장 시험 스크립트도 같은 함수):
  gid · round_label · side · hero · bottom · dealer · end(win/draw) · win_type · loser_side · n_calls · n_closed_end · hero_riichi ·
  regions(녹화 틀 — band · river · meld · reveal_region · wide · search) · frame_from · prev_last_ms · first_ms · last_ms ·
  hero_discards[{n, tile, at, riichi, after_call}] · hero_calls[{kind, tiles, at}] · t_reveal_read_ms(유국 판 결과 읽기) · events_src

t_start(판별 설정): features 구간 시작에만 쓰인다(features.game_span = t_start − pre_sec 3초 ~ t_reveal + post_sec · game.py 는 interval 기록만 ·
  segment.py 는 t_ready 부터). 그래서 코드가 t_start = t_ready − T_START_LEAD_S 로 정한다(앞 판 끝 · 빈 띠를 찾지 않음 — 가장 단순한 쪽).
post_sec = max(4, ⌈reveal_frame − t_reveal + 2초⌉)(handtrack_auto 와 같음 — game.py 가 읽는 공개 프레임 ±0.5초가 판 구간 안에).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HT = HERE / "handtrack"
sys.path.insert(0, str(HT))
sys.path.insert(0, str(HERE))
import handtrack_auto as hta  # noqa: E402
import hanchan_cfg as hcfg  # noqa: E402
import htcommon as hc  # noqa: E402
import ht_redirect as htr  # noqa: E402

SIDES = ["bottom", "right", "top", "left"]
ASK = ["band", "river", "meld", "reveal_region", "search"]          # 에이전트가 맞는지 보는 영역(wide 는 이 흐름의 판별 코드가 안 씀 — 틀 값 그대로)
REGIONS = ASK + ["wide"]
SIDE_KO = {"bottom": "아래", "right": "오른쪽", "top": "위", "left": "왼쪽"}
LR = {"bottom": "사진 왼쪽 → 오른쪽", "right": "사진 아래 → 위", "top": "사진 오른쪽 → 왼쪽", "left": "사진 위 → 아래"}   # paifu_auto.DRAW_DIR 과 같음
FRONT = {"bottom": "위쪽(y 가 작아지는 쪽)", "right": "왼쪽(x 가 작아지는 쪽)", "top": "아래쪽(y 가 커지는 쪽)", "left": "오른쪽(x 가 커지는 쪽)"}
CORNER = {"bottom": "오른쪽 아래", "right": "오른쪽 위", "top": "왼쪽 위", "left": "왼쪽 아래"}
AXIS = {"bottom": "x", "top": "x", "left": "y", "right": "y"}       # 줄 방향 = 원본 좌표 축
ROW_TEXT = {"bottom": "가로로(x 방향) 놓인다", "top": "가로로(x 방향) 놓인다", "left": "세로로(y 방향) 놓인다", "right": "세로로(y 방향) 놓인다"}
COLORS = {"band": (255, 225, 0), "river": (0, 220, 255), "meld": (255, 0, 220), "reveal_region": (255, 130, 0), "search": (235, 235, 235),
          "band_cand2": (0, 235, 120), "band_cand3": (255, 70, 70)}
COLOR_KO = {"band": "노랑", "river": "하늘", "meld": "자홍", "reveal_region": "주황", "search": "흰색(가는 선)", "band_cand2": "초록", "band_cand3": "빨강"}
CAND_KEYS = ["band_cand2", "band_cand3"]   # 기본 길 모드(녹화 틀 없음, 설계서 8-13 (다)): 손패 줄 후보 2 · 3위 — 그림 · 표에 같이 보여 주기만(답 칸 아님)
MUST_FOR_FEATURES = ["river", "meld"]       # features.py(공용 판별 — 안 고침)가 읽는 영역. 기본 길 모드는 이 둘을 묻지 않으므로 답에 없으면 적용이 멈춘다(보고)
CODE_REGIONS = ["river", "meld"]            # (11-25, 설계서 8-14 (가)) 기본 길 모드: 코드 값(버림 기록기 덤프 — paifu_auto S6a)만 씀 — 답 값은 안 씀(묻지 않은 것)
# 꾸러미 창(설계서 8-8: 앞 판 끝 ~ 손패 주인 첫 몇 버림 뒤, 마지막 버림 ~ 공개 뒤)
A_FIRST_LOOKBACK_S = 150     # 앞 판이 없으면 판 첫 버림 이만큼 앞부터
A_HERO_DISCARDS = 3          # 손패 주인 이 번째 버림까지(없으면 마지막)
A_AFTER_S = 10               # 그 버림 + 이만큼
B_BEFORE_S = 5               # 마지막 버림 이만큼 앞부터
B_AFTER_S = 60               # 마지막 버림 + 이만큼까지(유국은 max(이것, 판 결과 읽기 공개 + B_DRAW_AFTER_S))
B_DRAW_AFTER_S = 30
BACK_PAD = hta.READY_DET_PAD  # 뒷면 상자를 셀 곳 = band 를 줄 방향으로 ±150px(handtrack_auto.det_box 와 같음 — 깊이는 band 그대로: 패산 뒷면이 안 섞이게)
JOIN = hta.READY_JOIN         # 이웃 상자 틈이 한 장 폭의 이 비율 이하면 한 덩어리(slotgrid.JOIN 과 같음)
T_START_LEAD_S = 10           # t_start = t_ready − 10초(features 구간 시작일 뿐)
REVEAL_MISS_OK = 2            # 검사: 공개 프레임 reveal_region 안 앞면 상자 ≥ 닫힌 장수 − 이것
READY_OUT_OK = 1             # 검사: t_ready 덩어리 중 band 밖(중심)인 상자 허용 수 — 손을 피하려고 band 를 좁힌 손 설정(줄 끝 한 장이 band 밖)을 헛 질문으로 안 올리려고
FACE_EDGE_PX = 60             # 검사 참고: reveal_region 을 이만큼 넓힌 곳에만 있는 앞면 상자 수(영역이 공개 손패를 자르는지)
MAX_TRIES = 5                 # try: 판당 시도 한도(설계서 8-9)
TRY_TURNS_SHOWN = 3           # try 보고서 ⑤: 창 시각 · 프레임 목록을 주는 첫 차례 수
TRY_NEAR_MS = 3000            # try 보고서 ①: t_ready 와 이만큼 안에 기록기가 처음 본 버림은 "경계에 걸침"(paifu_auto.S6_TURN_NEAR_MS 와 같음)
TRY_GLUED = 0.5               # try 보고서 ②: 가장 긴 활동 구간이 판 구간의 이 비율 넘으면 "한 덩어리로 붙음" 이라 적음
SCRIPT = Path(__file__).resolve()


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=indent))


def wt(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(s.encode("utf-8"))


# ------------------------------------------------------------------ 검출기(원본 좌표)
def raw_boxes(ms: int):
    """검출기 앞면 · 뒷면 상자(원본 좌표 (x, y, w, h))."""
    res, backs, _p, _s = hta.reader()._seat_raw(hc.load(ms))
    return [tuple(b) for b, _rc in res], [tuple(b) for b, _rc in backs]


def center_in(b, box) -> bool:
    x, y, w, h = b
    return box[0] <= x + w / 2 <= box[2] and box[1] <= y + h / 2 <= box[3]


def clusters(bs: list, side: str) -> list:
    """상자들을 줄 방향(원본 축)으로 이어 덩어리로 — [(장수, 시작, 끝, 상자들)], 장수 큰 순."""
    if not bs:
        return []
    ax = 1 if AXIS[side] == "y" else 0
    iv = sorted(((b[ax], b[ax] + b[ax + 2], b) for b in bs), key=lambda v: v[0])
    p = float(np.median([b - a for a, b, _ in iv]))
    out = []
    for a, b, bx in iv:
        if out and a - out[-1][2] <= JOIN * p:
            out[-1][2] = max(out[-1][2], b)
            out[-1][0] += 1
            out[-1][3].append(bx)
        else:
            out.append([1, a, b, [bx]])
    return sorted(([n, int(a), int(b), x] for n, a, b, x in out), key=lambda c: -c[0])


def back_row(ms: int, band: list, side: str) -> dict:
    """band 를 줄 방향으로 ±BACK_PAD 넓힌 곳의 뒷면 상자 · 가장 큰 덩어리 · 그 덩어리가 band 안인지."""
    faces, backs = raw_boxes(ms)
    box = hta.det_box(band, side)
    bs = [b for b in backs if center_in(b, box)]
    cl = clusters(bs, side)
    big = cl[0] if cl else [0, None, None, []]
    return {"backs": len(bs), "cluster": big[0], "range": [big[1], big[2]] if big[0] else None,
            "cluster_in_band": all(center_in(b, band) for b in big[3]) if big[0] else None,
            "cluster_out_of_band": sum(not center_in(b, band) for b in big[3]),
            "faces": sum(center_in(b, box) for b in faces), "_faces": faces}


# ------------------------------------------------------------------ 손패 줄 후보를 화면 절반에서(설계서 8-13 (나), 11-25)
# 손패 주인 쪽 화면 절반(wide) 안에서, 판 구간에 고르게 뽑은 프레임의 검출기 뒷면 상자가 한 줄로 선 곳을 찾는다. 규칙은 21개 손 설정을 보기 전에 정했고
# (12:56 대국 ② — 21판 밖 — 의 프레임 하나에서 검출기 출력 꼴만 봄: 손패 줄 · 패산이 둘 다 뒷면 줄로 잡히고, 손패 줄이 가장자리 쪽 · 패산이 가운데 쪽,
# 줄은 조금 기울어 있음) 판을 보고 고치지 않는다.
#   ① 프레임 CAND_FRAMES 장 = 판 구간(기록의 첫 버림 ~ 마지막 버림)을 고르게. 프레임마다 중심이 wide 안인 뒷면 상자.
#   ② 한 프레임 안 줄: 상자를 줄 방향 가운데 순으로 보며, 열린 줄 가운데 마지막 상자와 줄 방향 틈 ≤ JOIN × 한 장 폭이고 깊이(줄에 수직) 가운데 차 ≤
#      CAND_DEPTH_TOL × 한 장 깊이인 것(그중 깊이 차가 가장 작은 것)에 붙이고, 없으면 새 줄. 상자 CAND_ROW_MIN 장 이상인 줄만(울기 셋 = 닫힌 4장).
#   ③ 프레임 사이 묶기: 줄을 깊이 가운데가 가까운 후보(차 ≤ CAND_TRACK_TOL × 한 장 깊이 · 줄 방향으로 겹침 > 0)에 붙임, 없으면 새 후보.
#   ④ 후보 상자: 줄 방향 = 줄 시작의 CAND_PCT 백분위 − 한 장 폭 ~ 줄 끝의 100 − CAND_PCT 백분위 + 한 장 폭, 깊이 = 줄 깊이 시작 · 끝 중앙값 ∓ 한 장 깊이의 1/4.
#   ⑤ 점수 순: 자격(나온 프레임 비율 ≥ CAND_MIN_FRAC 이고 장수 중앙값 ≥ CAND_MIN_TILES) 있는 것 먼저 → 그 안에서 화면 가장자리에 가까운 것
#      (손패 줄은 패산보다 그 사람 쪽) → 나온 프레임 수. 위 셋까지 근거(프레임 수 · 장수 중앙값 · 깊이 퍼짐 · 줄 방향 범위)와 함께.
CAND_FRAMES = 24
CAND_ROW_MIN = 4
CAND_DEPTH_TOL = 0.5
CAND_TRACK_TOL = 1.0
CAND_PCT = 5
CAND_MIN_FRAC = 0.3
CAND_MIN_TILES = 5
CAND_TOP = 3
OUTER = {"bottom": 1, "right": 1, "top": -1, "left": -1}       # 깊이 축(원본 y · x)에서 그 사람 가장자리 쪽 = 큰 쪽(+1) · 작은 쪽(−1)


def half_screen(side: str) -> list:
    """손패 주인 쪽 화면 절반(원본 1496 좌표) — 기본 길 모드의 wide."""
    H = 1496
    return {"bottom": [0, H // 2, H, H], "top": [0, 0, H, H // 2], "left": [0, 0, H // 2, H], "right": [H // 2, 0, H, H]}[side]


def band_candidates(side: str, t0: int, t1: int, n_frames: int = CAND_FRAMES) -> dict:
    """화면 절반에서 손패 줄 후보(설계서 8-13 (나)) → {"wide", "frames", "candidates": [{"band", "frames", "frac", "tiles_med", "depth_spread", "along", ...}], "rule"}."""
    wide = half_screen(side)
    ax = 0 if AXIS[side] == "x" else 1          # 줄 방향 축(원본 x = 0 · y = 1)
    dx = 1 - ax
    step = (t1 - t0) / max(1, n_frames - 1)
    picks = sorted({hc.nearest(int(t0 + k * step)) for k in range(n_frames)})
    rows_all = []                                # (프레임 번호, a0, a1, d0, d1, 장수, 한 장 폭, 한 장 깊이)
    for fi, ms in enumerate(picks):
        _f, backs = raw_boxes(ms)
        bs = [b for b in backs if center_in(b, wide)]
        if len(bs) < CAND_ROW_MIN:
            continue
        pa = float(np.median([b[ax + 2] for b in bs]))
        pd = float(np.median([b[dx + 2] for b in bs]))
        rows = []                                # 열린 줄: [a0, a1, 마지막 상자 깊이 가운데, d0, d1, 장수]
        for b in sorted(bs, key=lambda b: b[ax] + b[ax + 2] / 2):
            a0, a1 = b[ax], b[ax] + b[ax + 2]
            dc = b[dx] + b[dx + 2] / 2
            ok = [r for r in rows if a0 - r[1] <= JOIN * pa and abs(dc - r[2]) <= CAND_DEPTH_TOL * pd]
            if ok:
                r = min(ok, key=lambda r: abs(dc - r[2]))
                r[1], r[2], r[3], r[4], r[5] = max(r[1], a1), dc, min(r[3], b[dx]), max(r[4], b[dx] + b[dx + 2]), r[5] + 1
            else:
                rows.append([a0, a1, dc, b[dx], b[dx] + b[dx + 2], 1])
        rows_all += [(fi, r[0], r[1], r[3], r[4], r[5], pa, pd) for r in rows if r[5] >= CAND_ROW_MIN]
    tracks = []                                  # 후보: {"rows": [...]} — 깊이 가운데 중앙값으로 붙임
    for row in sorted(rows_all, key=lambda r: (r[0], -r[5])):
        fi, a0, a1, d0, d1, n, pa, pd = row
        dc = (d0 + d1) / 2
        best = None
        for tr in tracks:
            tdc = float(np.median([(x[3] + x[4]) / 2 for x in tr["rows"]]))
            ta0, ta1 = min(x[1] for x in tr["rows"]), max(x[2] for x in tr["rows"])
            if abs(dc - tdc) <= CAND_TRACK_TOL * pd and min(a1, ta1) - max(a0, ta0) > 0:
                if best is None or abs(dc - tdc) < best[0]:
                    best = (abs(dc - tdc), tr)
        if best:
            best[1]["rows"].append(row)
        else:
            tracks.append({"rows": [row]})
    out = []
    for tr in tracks:
        R = tr["rows"]
        fr = sorted({x[0] for x in R})
        pa = float(np.median([x[6] for x in R]))
        pd = float(np.median([x[7] for x in R]))
        lo = float(np.percentile([x[1] for x in R], CAND_PCT)) - pa
        hi = float(np.percentile([x[2] for x in R], 100 - CAND_PCT)) + pa
        d0 = float(np.median([x[3] for x in R])) - pd / 4
        d1 = float(np.median([x[4] for x in R])) + pd / 4
        lo, hi = max(lo, wide[ax]), min(hi, wide[ax + 2])
        d0, d1 = max(d0, 0), min(d1, 1496)
        box = [0, 0, 0, 0]
        box[ax], box[ax + 2], box[dx], box[dx + 2] = int(round(lo)), int(round(hi)), int(round(d0)), int(round(d1))
        dcs = [(x[3] + x[4]) / 2 for x in R]
        tiles = float(np.median([x[5] for x in R]))
        frac = len(fr) / max(1, len(picks))
        out.append({"band": box, "frames": len(fr), "frac": round(frac, 2), "tiles_med": tiles, "tiles_max": max(x[5] for x in R),
                    "depth_center": round(float(np.median(dcs)), 1), "depth_spread": round(float(np.percentile(dcs, 90) - np.percentile(dcs, 10)), 1),
                    "along": [int(min(x[1] for x in R)), int(max(x[2] for x in R))], "tile_px": [round(pa, 1), round(pd, 1)],
                    "qualified": frac >= CAND_MIN_FRAC and tiles >= CAND_MIN_TILES})
    out.sort(key=lambda c: (not c["qualified"], -OUTER[side] * c["depth_center"] if c["qualified"] else 0, -c["frames"]))
    for k, c in enumerate(out, 1):
        c["rank"] = k
    rule = (f"화면 절반 {wide} · 판 구간 {hc.hms(t0)} ~ {hc.hms(t1)} 에서 고르게 {len(picks)}장 · 검출기 뒷면 상자 줄(틈 ≤ {JOIN} 장 · 깊이 차 ≤ {CAND_DEPTH_TOL} 장, "
            f"{CAND_ROW_MIN}장 이상) → 프레임 사이 묶음(깊이 차 ≤ {CAND_TRACK_TOL} 장) → 자격(프레임 ≥ {CAND_MIN_FRAC:.0%} · 장수 중앙값 ≥ {CAND_MIN_TILES}) 먼저, "
            f"그 안에서 가장자리({side}) 쪽 먼저")
    return {"side": side, "wide": wide, "frames": [hc.hms(m) for m in picks], "rows": len(rows_all), "candidates": out[:CAND_TOP], "all": len(out), "rule": rule}


def cmd_bandcand(a):
    """S6a(기본 길 모드)가 부름: 손패 줄 후보 → --out json."""
    cfg = hcfg.load(a.cfg, check=False)
    cfg.apply_recording(hc)
    t0 = time.time()
    r = band_candidates(a.side, hc.to_ms(a.t0) if ":" in a.t0 else int(a.t0), hc.to_ms(a.t1) if ":" in a.t1 else int(a.t1), a.n)
    r["wall_s"] = round(time.time() - t0, 1)
    wj(a.out, r)
    print("JSON" + json.dumps({k: v for k, v in r.items() if k != "frames"}, ensure_ascii=False))


# ------------------------------------------------------------------ 그림
def _font(size, ko=False):
    from PIL import ImageFont
    for f in (["C:/Windows/Fonts/malgun.ttf"] if ko else []) + ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/malgun.ttf"]:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def overview(ms: int, regions: dict, title: str, out: Path):
    """원본 프레임 전체 + 100px 눈금(좌표 글자) + 영역 상자(이름 · 좌표)."""
    from PIL import Image, ImageDraw
    im = Image.open(hc.path_of(ms)).convert("RGB")
    W, H = im.size
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f_s, f_m, f_t = _font(15), _font(17), _font(22, ko=True)
    for v in range(0, max(W, H) + 1, 100):
        a = 110 if v % 500 == 0 else 55
        d.line([(v, 0), (v, H)], fill=(255, 255, 255, a), width=1)
        d.line([(0, v), (W, v)], fill=(255, 255, 255, a), width=1)
    for v in range(0, max(W, H), 100):
        for xy in ((v + 2, 2), (v + 2, H - 18)):
            d.rectangle([xy[0] - 1, xy[1] - 1, xy[0] + 34, xy[1] + 16], fill=(0, 0, 0, 150))
            d.text(xy, str(v), fill=(255, 255, 255, 255), font=f_s)
        for xy in ((2, v + 2), (W - 40, v + 2)):
            d.rectangle([xy[0] - 1, xy[1] - 1, xy[0] + 36, xy[1] + 16], fill=(0, 0, 0, 150))
            d.text(xy, str(v), fill=(255, 255, 255, 255), font=f_s)
    for k in ASK + [x for x in CAND_KEYS if x in regions]:   # 후보 2 · 3(기본 길 모드에서만 regions 에 들어옴 — 꾸러미 그림에만)
        if k not in regions:
            continue
        x0, y0, x1, y1 = regions[k]
        c = COLORS[k]
        d.rectangle([x0, y0, x1, y1], outline=c + (255,), width=1 if k == "search" else 3)
        lab = f"{k} [{x0},{y0},{x1},{y1}]"
        tx, ty = x0 + 4, (y0 + 4 if k != "search" else y1 - 22)
        tx, ty = min(max(tx, 40), W - 300), min(max(ty, 20), H - 40)
        d.rectangle([tx - 2, ty - 1, tx + 9 * len(lab) + 4, ty + 20], fill=(0, 0, 0, 170))
        d.text((tx, ty), lab, fill=c + (255,), font=f_m)
    d.rectangle([40, 24, 40 + 13 * len(title) + 20, 56], fill=(0, 0, 0, 190))
    d.text((48, 28), title, fill=(255, 255, 255, 255), font=f_t)
    Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB").save(out, quality=90)


# ------------------------------------------------------------------ S6a-1 꾸러미
TASK = """# 손 추적 준비 읽기 — 판 `{gid}`({round_label})

2026-11-14 매장 리치 마작(4인) 대국을 위에서 내려다본 헤드 폰 녹화다(원본 프레임 1496×1496, 초당 약 10장).
코드가 이 판 **손패 주인**의 손패 줄을 프레임마다 따라가 차례(뽑기 → 버림)를 나누려면, 판마다 영역 다섯과 시각 셋을 정해야 한다.
예전에는 사람이 프레임을 보고 적던 값이다. **프레임을 열어 보고 정하는 일이다** — 코드는 프레임 고르기 · 자르기 · 키우기 · 돌리기 · 이어 붙이기
(그리고 그림에 선 · 눈금 그리기)에만 쓴다. 정한 값은 `try` 명령으로 이 판 판별을 직접 돌려 보고 고칠 수 있다(아래 "일하는 순서").

## 이 판
- 손패 주인 = 자리 {hero} — 사진의 **{side_ko} 가장자리**에 앉은 사람(코드 이름 `{side}`). 선(친) = 자리 {dealer}{dealer_note}.
- 자리 번호: 사진 아래 = 자리 {bottom}, 그다음 오른쪽 → 위 → 왼쪽 순으로 하나씩 늘어난다(4 다음은 0).
- 끝: {end_text}
- 손패 주인 울기 {n_calls}번 → 판 끝 닫힌 손패 {n_closed_end}장{riichi_text}.

## 사진 방향(돌리지 않은 원본 프레임 기준) — 틀리면 안 된다
- 손패 주인의 손패 줄은 사진 {side_ko} 가장자리 가까이에 {row_text}. 줄 방향 = 원본 {axis} 축.
- 그 사람 기준 왼쪽 → 오른쪽 = **{lr}**. 그 사람 앞(탁자 가운데 쪽) = 사진 {front}.
- 그 사람의 울기 묶음은 그 사람 오른쪽 끝 쪽 탁자 모서리 = **사진 {corner} 모서리** 쪽에 놓인다.
- 그 사람 시점으로 돌려 보려면 반시계 {rot}°(PIL `Image.rotate({rot}, expand=True)`). 돌린 그림에서 본 것은 원본 좌표로 되돌려 적는다 —
  **답의 좌표는 모두 원본 프레임 좌표**다(왼쪽 위 (0, 0) · 오른쪽 아래 (1496, 1496), `[x0, y0, x1, y1]`, x0 < x1 · y0 < y1).

## 재료(이 폴더 `{dir}` 안)
- `overview/` — 원본 프레임 전체에 지금 녹화 틀 영역(아래 표)과 100px 눈금 · 좌표 글자를 그린 그림 {n_ov}장:
{ov_list}
- `frames_ready.txt` — {a_from} ~ {a_to}의 원본 프레임 목록({n_a}장, 초당 약 10장 그대로). 한 줄 = `HH:MM:SS.s<탭>원본 프레임 경로`.
- `frames_reveal.txt` — {b_from} ~ {b_to}의 원본 프레임 목록({n_b}장, 같은 꼴).
- `backs.md` — 두 구간을 1초마다 자리 판독 검출기로 잰 표(아래 "검출기 표"). **기계 판독이라 틀릴 수 있다.**
- `try/<번호>/` — 네가 `try` 를 돌릴 때마다 생기는 시험 자리(보고서 `report.md`, 첫 차례 창 프레임 목록 `frames_turns.txt`, 판별 출력). 읽어도 된다.
- 원본 프레임은 두 목록과 `try/<번호>/frames_turns.txt` 에 적힌 경로만 연다. 목록에 없는 시각이 필요하면 unsure 에 적는다.

## 지금 녹화 틀 영역 — 같은 녹화의 다른 판 손 설정에서 뽑은 값이라 이 판에 맞는지 모른다
| 칸 | 값 [x0, y0, x1, y1] | overview 그림 색 |
|---|---|---|
{region_rows}

## {ev_title}
- 버림 시각은 녹화를 재생한 버림 기록기가 **강에서 그 패를 처음 본 때**다. 기록기는 약 3초 간격 프레임을 보므로 실제로 패를 놓은 때보다 0 ~ 3초쯤 늦을 수 있다.
- 판 첫 버림(아무 자리): {first} · 판 마지막 버림(아무 자리): {last}{prev_text}
- 손패 주인 버림 {n_hd}장:

| 몇 번째 | 패 | 기록기가 처음 본 때 | 리치(가로) | 바로 앞에 이 사람 울기 |
|---|---|---|---|---|
{hd_rows}
{calls_text}{reveal_text}

## 정할 것과 정의(코드가 각 칸을 어떻게 쓰는지 → 그래서 무엇을 만족해야 하는지)

### ① band — 손패 줄 영역
- 코드: `features.py` 가 프레임마다 band 안 화소가 앞 프레임 · 3장 앞과 달라진 비율과 피부색 화소 비율을 잰다. `segment.py` 가 그 비율이 0.2% · 0.3% 를 넘는
  프레임을 "손이 움직임", 나머지를 "줄이 가만함" 으로 나누고, 가만한 구간마다 강을 읽어 그 사이 움직임 구간을 차례로 묶는다.
  `bandfit.py` 는 band 의 깊이(그 사람 앞뒤 방향) 범위는 그대로 두고 줄 방향으로만 넓혀 읽기 그림 띠를 만든다.
- 그래서: t_ready ~ 공개 동안 손패 줄이 놓이는 곳 전부 — 판 중에 줄이 옆으로 밀리는 범위, 줄 오른쪽 끝 밖(뽑은 패를 떼어 두는 곳), 줄 앞쪽 여백 — 를 덮는다.
  깊이는 줄의 앞 · 뒤 가장자리가 잘리지 않게 잡는다. 긴 변이 줄 방향(원본 {axis} 축)이다.
- 넣으면 안 되는 것: 가만히 있는 피부색 물체(주황 자리 패찰 같은 것), 판 내내 쉬고 있는 손(줄 끝 옆에 손을 늘 올려 두는 사람이 있다), 패산 · 남의 패.
  이런 것이 band 안에 있으면 판 전체가 "움직임" 한 덩어리가 되어 차례를 못 나눈다 — 줄은 다 덮되 그런 것은 피하도록 좁힌다.
  둘이 부딪히면(줄 끝까지 덮으면 늘 놓인 손이 들어옴) 손을 빼는 쪽을 고른다 — 줄 끝 한 장쯤은 band 밖으로 나가도 된다(읽기 그림 띠는 bandfit 이 줄 방향으로 따로 넓힌다).

### ② river — 손패 주인 강
- 코드: `river.py` 가 가만한 구간마다 프레임 3장을 그 사람 시점으로 돌려 패를 검출하고, **중심이 river 안인 패**만 이 사람 강으로 읽는다.
  앞뒤 가만한 구간의 강을 견줘 "새로 놓인 패" 하나를 버림 하나(= 차례 하나)로 센다. 가로로 놓인 패는 리치 선언 패다.
  `segment.py` 는 river 안 움직임 · 피부색도 "움직임" 으로 본다(줄을 안 건드리고 뽑아 바로 버리는 버림을 놓치지 않으려고).
- 그래서: 판 끝까지 이 사람 강의 패(가로 놓인 리치 패, 셋째 · 넷째 줄까지)의 중심이 모두 안에 든다. 남의 강 패 · 패산 · 왕패의 중심은 들지 않게 좁힌다.

### ③ meld — 울기 자리
- 코드: `river.py` 가 가만한 구간마다 중심이 meld 안인 패를 이 사람 울기 묶음으로 읽고, `features.py` 가 meld 안 움직임을 잰다.
- 그래서: 이 사람이 울기 묶음을 내놓는 탁자 모서리(위 "사진 방향")를 덮는다. 울기가 없는 판도 그 모서리로 둔다. 남의 강 · 남의 울기 자리는 들지 않게.

### ④ reveal_region — 공개 손패 자리
- 코드: `game.py` 가 reveal_frame 과 그 앞뒤 0.5초 프레임(모두 3장)에서 **중심이 reveal_region 안인 앞면 패**를 그 사람 시점으로 돌려 읽는다.
  세로 중심이 같은 줄로 묶어 가장 긴 줄 = 손패 줄, 그 줄 안에서 패 폭 0.6 넘게 떨어진 덩어리 = 떼어 둔 패(화료패), 줄 밖 = 그 밖.
- 그래서: 공개 때 눕힌 손패 전부와 떼어 둔 화료패가 든다. 남의 강 · 패산 · 남이 공개한 손패는 되도록 들지 않게.

### ⑤ search — 참고 영역
- 이 흐름의 판별 코드(features · segment · river · game · bandfit)는 search 를 쓰지 않는다(예전에 band 를 정할 때 패 화소를 찾던 넓은 탐색 영역, `probe.py`).
  band 를 고쳤으면 고친 band 를 감싸게만 맞추고, 아니면 그대로 둔다.

### ⑥ t_ready — 줄이 선 때
- 코드: `segment.py` 의 판 구간은 t_ready ~ 공개 + 몇 초다. **t_ready 앞 프레임은 쓰지 않고**, t_ready 프레임은 "가만한 상태" 로 놓고 시작한다.
  차례 목록(`truthprep` · `han3 turns`)은 t_ready 때 강에 이미 있던 이 사람 버림을 "판 구간 전" 버림으로 보아 **차례로 만들지 않고**(그 순의 손패는 복원하지 않음),
  t_ready 뒤에 이 사람 강이 한 장 늘 때마다 차례 하나를 만든다. 첫 차례의 프레임 창은 t_ready 뒤 첫 움직임부터다.
- 그래서 t_ready = **배패를 세우고 이 사람이 하는 정리(정렬 · 옮기기)가 끝나, 닫힌 손패 줄이 가지런히 서서 가만한 첫 프레임**이다.
  손이 줄에서 떨어졌거나, 줄 끝 밖에 가만히 놓여 줄을 가리지 않으면 된다.
  - 그때 줄 장수 = 13 − 3 × (그때까지 이 사람 울기 수) — 보통 13장. 답의 closed_at_ready 에 그 프레임에서 센 장수를 적는다.
  - 13장이 잠깐 섰다가 다시 정리하면(줄이 다시 흩어지거나 크게 옮겨지면) 그 정리가 끝난 뒤가 t_ready 다. 너무 이르면 첫 차례 창에 정리 동작이 섞여 첫 차례를 잘못 읽는다.
  - 이 사람이 정리를 끝내기 전에 이미 버렸으면(선은 첫 버림 전 14장이라 첫 버림 뒤에야 13장 줄이 선다 · 패를 눕힌 채 먼저 버리는 사람도 있다)
    t_ready 는 그 버림 **뒤** 정리가 끝난 때다. 그 버림은 차례가 되지 않는다 — 그대로 두고 답의 pre_ready_discards 에 적는다.
  - 정리가 끝난 뒤 이 사람의 첫 버림보다는 앞이어야 한다(뒤로 잡으면 그 버림이 차례에서 빠진다).
  - 처음 가지런히 선 때에서 멈추지 말고, 그 뒤 이 사람의 첫 세 차례가 끝날 때까지 프레임을 보아 여러 장 재정리가 없는지 확인한다.
  - `frames_ready.txt` 앞쪽은 앞 판 끝이다. 앞 판의 손패 줄은 공개 · 정리 전까지 그대로 서 있을 수 있다 — 앞 판 패를 치우고 새 패산이 올라온 뒤,
    이 판 배패를 가져와 세운 줄인지 확인한다.
- 시각은 프레임 목록의 `HH:MM:SS.s`(0.1초) 그대로 적는다.

### ⑦ t_reveal · reveal_frame — 공개
{reveal_def}
- reveal_frame = 공개 뒤 끝 손패를 읽을 프레임. `game.py` 가 이 프레임과 앞뒤 0.5초 프레임, 모두 세 장으로 다수결해 읽으므로: 세 장 모두에서 눕힌 손패가
  **한 줄로 가지런하고**(몇 장이 한 칸 앞뒤로 어긋나 있으면 손패 줄을 짧게 읽는다), 손 · 팔 · 남의 손이 가리지 않으며, {reveal_tiles} 다 보이는 때.
- 코드는 판 구간 끝을 t_reveal + max(4초, reveal_frame − t_reveal + 2초) 로 둔다. reveal_frame 은 t_reveal 과 같거나 뒤다.

## 검출기 표(`backs.md`) 읽는 법
- 1초마다(가장 가까운 프레임) 자리 판독 검출기를 돌린 값이다. 셈하는 곳 = 지금 틀 band 를 줄 방향으로 ±{pad}px 넓힌 곳(깊이는 band 그대로).
  열: 그곳의 뒷면 상자 수 · 가장 큰 덩어리 장수(이웃 상자 틈이 한 장 폭의 {join} 이하면 한 덩어리) · 그 덩어리의 원본 {axis} 범위 · 같은 곳 앞면 상자 수.
  공개 쪽 표에는 지금 틀 reveal_region 안 앞면 상자 수도 있다.
- 서 있는 손패 줄은 뒷면 상자로 잡힌다. 손이 가리거나 줄이 기울면 장수가 모자라고, 틀 band 가 이 판 줄과 어긋나면 엉뚱한 값이 나온다.
  **어디를 볼지 고르는 데만 쓰고, 값은 프레임을 보고 정한다.**

## 일하는 순서 — 값을 정하고, 돌려 보고, 고친다
1. 재료와 프레임을 보고 영역 · t_ready · 공개를 정해 **초안 답**을 `{work}/draft_1.json` 에 쓴다(꼴은 아래 "답"과 같음).
2. `try` 를 돌린다(한 줄, 판 길이에 따라 1분 안팎):
   `python -X utf8 {script} try --pack {dir} --answer {work}/draft_1.json`
   이 판 하나만 초안 값으로 판별 설정 → 특징 → 활동 구간 → 강 → 공개 → 읽기 띠 → 차례 나누기를 이 폴더의 `try/<번호>/` 에서 돌리고
   보고서를 낸다(표준 출력과 `try/<번호>/report.md`). 번호는 1부터 저절로 붙는다.
3. 보고서 ① ~ ⑤ 를 읽고, ⑤ 의 첫 두세 차례 창 프레임(`try/<번호>/frames_turns.txt`)을 **직접 열어 본다**.
4. 이상하면 값을 고쳐 `{work}/draft_2.json` 으로 다시 `try`. **판당 5번까지**(6번째는 `try` 가 거절한다).
5. 마지막 값을 `{answer}` 에 쓴다 — `tries` 칸에 시도마다 한 줄(무엇을 보고 무엇을 고쳤나). 이 파일은 **맨 끝에 한 번만** 쓴다
   (이 파일이 생기면 흐름이 답이 왔다고 보고 다음으로 넘어간다). 초안은 `{work}` 에만 둔다.

### 보고서 읽는 법
- 보고서는 값이 맞는지 가늠하는 근거일 뿐이다. 값은 프레임을 보고 정한다 — 차례 수를 기록에 맞추려고 프레임과 안 맞는 값을 고르지 않는다.
- ① 차례 목록 ↔ 기록의 손패 주인 버림:
  - 차례가 기록의 버림(t_ready 뒤)보다 적거나 "차례에서 빠짐" · "강 사진은 못 잡고 기록으로 끼움" 이 있다 → 그 버림 시각 앞뒤에 활동 구간이 있는지(②),
    river 가 그 패가 놓인 자리를 덮는지 본다. 단, 남이 울어 가져간 버림은 강에 남지 않아 "끼움" 으로 나오는 것이 정상이다.
  - "기록에 없는 차례" 가 있다 → river 에 남의 강 패 · 패산 · 왕패가 들었거나, 한 버림이 둘로 읽혔을 수 있다.
  - "t_ready 앞(차례 아님)" 버림이 네가 적은 pre_ready_discards 와 다르다 → t_ready 를 다시 본다.
- ② 활동 구간이 판 전체로 붙었다(가장 긴 구간이 판 구간의 대부분 · 가만한 구간이 거의 없음) → band 에 가만한 피부색 물체나 쉬는 손이 들었는지 본다
  ("band 화소가 안 바뀌었는데 피부색이 문턱을 넘는 프레임" 비율이 크면 이 경우). river 쪽 비율이 크면 river 에 피부색 물체 · 손이 들었는지 본다.
  줄 위에 손을 늘 얹어 두는 사람처럼 줄을 다 덮으면서 손을 뺄 수 없는 판도 있다 — 그때 ① 이 기록과 맞으면 붙은 것만으로 값을 바꾸지 않는다.
- ⑤ 첫 차례 창 안에서 두 장 넘게 자리를 바꾸는 정리가 보인다 → t_ready 를 그 정리 뒤로 옮긴다(그 사이 버림은 pre_ready_discards).
- ③ 공개 프레임에서 읽은 끝 손패 장수가 기대와 다르거나 판 결과의 패와 다르다 → reveal_frame · reveal_region 을 본다
  (세 장 모두에서 눕힌 줄이 가지런한지, 영역이 줄 끝 · 떼어 둔 패를 자르지 않는지, 남의 패가 들지 않는지).
- ④ 적용 검사가 실패했다 → 그 칸을 프레임으로 다시 본다(검출기 셈이라 검사가 틀릴 수도 있다 — 프레임이 맞으면 값을 두고 unsure 에 적는다).
- 모두 맞아 보여도 ⑤ 의 프레임은 열어 본다. 그러고도 고칠 것이 없으면 첫 시도 값으로 끝내도 된다.

## 답 — `{answer}` 한 파일(UTF-8)
```json
{{
  "id": "{gid}",
  "band":          {{"value": [x0, y0, x1, y1], "changed": false, "why": "확인한 프레임 시각과 근거"}},
  "river":         {{"value": [x0, y0, x1, y1], "changed": false, "why": "…"}},
  "meld":          {{"value": [x0, y0, x1, y1], "changed": false, "why": "…"}},
  "reveal_region": {{"value": [x0, y0, x1, y1], "changed": false, "why": "…"}},
  "search":        {{"value": [x0, y0, x1, y1], "changed": false, "why": "…"}},
  "t_ready": "HH:MM:SS.s",
  "t_ready_why": "그 프레임에서 본 것(줄 장수 · 손 위치) · 그 앞 정리가 언제 끝났는지",
  "closed_at_ready": 13,
  "pre_ready_discards": [{{"tile": "패", "time": "HH:MM:SS.s"}}],
  "t_reveal": {t_reveal_example},
  "reveal_frame": "HH:MM:SS.s",
  "reveal_why": "공개 시작 · 읽을 프레임을 고른 근거",
  "unsure": [{{"what": "칸 이름", "alt": 다른 후보 값 또는 null, "why": "왜 확신이 낮은지"}}],
  "tries": ["1: 보고서 · 프레임에서 본 것 → 고친 것(또는 고칠 것 없음)", "2: …"]
}}
```
- 영역 value 는 늘 적는다(맞으면 위 표의 값 그대로, changed false). 좌표는 원본 프레임 정수.
- pre_ready_discards 는 t_ready 앞에 이 사람이 버린 패(없으면 []).
- tries 는 `try` 를 돌린 번호 순서로 한 줄씩. 마지막 답이 마지막 시도 값과 다르면(보고서를 보고 한 번 더 고치고 안 돌림) 그 줄에 그렇게 적는다.
- 확신이 없는 것을 그럴듯하게 채우지 않는다. 모르는 칸도 가장 그럴듯한 값을 적되 unsure 에 까닭을 적고, 다른 후보는 `alt` 에 그 칸과 같은 꼴의 값으로
  하나만 적는다(둘 넘으면 그다음으로 그럴듯한 하나 — 영역은 `[x0, y0, x1, y1]`, 시각은 `"HH:MM:SS.s"`, t_ready_late 는 시각 또는 null. null 도 후보 값이다:
  "늦은 후보를 안 씀"). 값으로 못 적는 걱정이면 `alt` 는 null.
- 코드가 `alt` 로 한 번 더 돌려 차례 목록 · 차례 창이 바뀌는지 보고, 바뀌는 것만 사용자에게 묻는다.

## 지킬 것
- 패 인식 모델 · 서버 · API 를 부르지 않는다. **예외는 위 `try` 명령 하나**(그 안에서 검출기 · 분류기가 돈다). 그 밖의 코드는 프레임 고르기 · 자르기 ·
  키우기 · 돌리기 · 이어 붙이기(그리고 그림에 선 · 눈금 그리기)에만 쓴다.
- 읽어도 되는 것: 이 문서, 이 폴더의 재료, `try` 가 만든 시험 자리(`{dir}/try/`), 두 프레임 목록과 `try/<번호>/frames_turns.txt` 에 적힌 원본 프레임,
  네 작업 폴더. **그 밖의 파일은 열지 않는다** — 정답 · 예시 · 손 설정(`handtrack/config`) · 판별 출력(`results/handtrack`) · 옛 차례 목록
  (`testtruth_1116` · `turns_han3`) · 다른 판 꾸러미 · 실행 폴더의 다른 파일 모두(시험 자리 안 설정 파일이 가리키는 폴더 밖 경로도 열지 않는다).
  Grep · Glob · ls 로 이 폴더 밖을 뒤지지 않는다.
- 그림 · 스크립트 · 초안은 작업 폴더 `{work}` 에만 쓴다(`try/` 는 `try` 명령만 쓴다). 저장소 파일을 고치지 않는다. git 을 쓰지 않는다.
- 여러 줄 Python 은 파일로 써서 `python -X utf8 <파일>` 로 돌린다(`python -c` 여러 줄 · heredoc 은 이 환경에서 멈춘다).
- 마지막 답은 네 줄 이내: t_ready / 공개(t_reveal · reveal_frame) / 고친 영역 · unsure 수 / try 횟수.
"""

REVEAL_DEF_WIN = """- t_reveal = 화료자(이 판은 손패 주인)가 손패를 앞면으로 **눕히기 시작한 프레임**의 시각. 마지막 버림(위 표) 뒤다 — 론이면 방총 자리가 버린 직후, 쯔모면
  손패 주인이 마지막으로 뽑은 패를 떼어 둔 뒤. 이 사람의 마지막 차례(버림)는 t_reveal 앞이어야 판 구간에 든다."""
REVEAL_DEF_DRAW = """- t_reveal = **{t_reveal}** — 판 결과 읽기(공개 손패 읽기)가 정한 값이다. 그대로 쓰고 답의 t_reveal 은 null 로 둔다(다르게 보이면 unsure 에 적는다)."""


def is_half(sp: dict) -> bool:
    """spec 이 기본 길 모드(녹화 틀 없음 — 영역 = 화면 절반 wide + 손패 줄 후보 band · search, 설계서 8-13 (다))인가."""
    return sp.get("regions_mode") == "half"


def task_half(t: str, sp: dict) -> str:
    """기본 길 모드(녹화 틀 없음 — 설계서 8-13 (다), 3-9 "준비 에이전트는 손패 줄 · 줄이 선 때 · 공개 프레임만")의 TASK.md:
    옛 지시문에서 묻는 영역이 준 만큼만 고친다 — 강 · 울기 · 공개 영역(② ③ ④)과 그 답 칸 · 그 영역을 보라는 보고서 읽는 법을 빼고,
    영역 출처(녹화 틀 → 화면 절반 후보)와 차례 목록 출처(강 사진 → 기록)를 바꿔 적는다. 바꿀 곳이 안 맞으면 멈춘다(옛 틀이 바뀐 것)."""
    cs = sp.get("band_candidates") or []
    ev = " / ".join(f"{c['rank']}위 {c['band']}(프레임 {c['frames']}/{sp.get('band_candidates_picks', '?')} · 장수 중앙값 {c['tiles_med']:g} · "
                    f"깊이 퍼짐 {c['depth_spread']:g}px)" for c in cs)
    subs = [
        ("판마다 영역 다섯과 시각 셋을 정해야 한다.", "판마다 영역 둘(손패 줄 band · 참고 search)과 시각 셋을 정해야 한다."),
        ("지금 녹화 틀 영역(아래 표)과 100px 눈금", "지금 영역(아래 표 — 손패 줄 후보 1 ~ 3위)과 100px 눈금"),
        ("## 지금 녹화 틀 영역 — 같은 녹화의 다른 판 손 설정에서 뽑은 값이라 이 판에 맞는지 모른다\n",
         "## 지금 영역 — 코드가 이 판 손패 주인 쪽 화면 절반에서 찾은 손패 줄 후보라 이 판에 맞는지 모른다\n"
         "- 찾은 법: 판 구간에서 고르게 뽑은 프레임마다 검출기 뒷면 상자가 한 줄로 선 곳을 모아, 여러 프레임에 나오고 장수가 많은 줄 가운데 그 사람 가장자리 쪽을 1위로 둠"
         "(기계 판독 — 패산 · 남의 줄을 잡았을 수 있다). band · search = 1위. 2 · 3위는 그림과 아래 표에만(맞는 것이 있으면 그 값을 band 로 적어도 된다).\n"
         f"- 후보 근거: {ev or '후보 없음'}\n"),
        ("가만한 구간마다 강을 읽어 그 사이 움직임 구간을 차례로 묶는다.", "기록의 손패 주인 버림 시각으로 움직임 구간을 차례에 붙인다(강 사진은 읽지 않는다)."),
        ("  공개 쪽 표에는 지금 틀 reveal_region 안 앞면 상자 수도 있다.\n", ""),
        ('  "river":         {"value": [x0, y0, x1, y1], "changed": false, "why": "…"},\n', ""),
        ('  "meld":          {"value": [x0, y0, x1, y1], "changed": false, "why": "…"},\n', ""),
        ('  "reveal_region": {"value": [x0, y0, x1, y1], "changed": false, "why": "…"},\n', ""),
        (" river 쪽 비율이 크면 river 에 피부색 물체 · 손이 들었는지 본다.", ""),
        ("- ③ 공개 프레임에서 읽은 끝 손패 장수가 기대와 다르거나 판 결과의 패와 다르다 → reveal_frame · reveal_region 을 본다\n"
         "  (세 장 모두에서 눕힌 줄이 가지런한지, 영역이 줄 끝 · 떼어 둔 패를 자르지 않는지, 남의 패가 들지 않는지).\n",
         "- ③ 이 판은 공개 손패를 영역으로 읽지 않는다(끝 손패는 판 결과 값) — reveal_frame 은 프레임을 보고 정한다.\n"),
        # (11-25 밤, 설계서 8-16) 사실이 틀린 세 곳(이 모드에서는 강 · 공개 읽기를 안 돌리고 차례 목록이 기록에서 옴) — 판단 잣대는 그대로
        ("판별 설정 → 특징 → 활동 구간 → 강 → 공개 → 읽기 띠 → 차례 나누기를",
         "판별 설정 → 특징 → 활동 구간 → 읽기 띠 → 차례 목록(기록에서) → 차례 나누기를"),
        ("  차례 목록(`truthprep` · `han3 turns`)은 t_ready 때 강에 이미 있던 이 사람 버림을 \"판 구간 전\" 버림으로 보아 **차례로 만들지 않고**(그 순의 손패는 복원하지 않음),\n"
         "  t_ready 뒤에 이 사람 강이 한 장 늘 때마다 차례 하나를 만든다.",
         "  차례 목록(기록에서 — `han3 rturns`)은 기록의 이 사람 버림 가운데 기록기가 처음 본 때가 t_ready 와 같거나 앞인 것을 \"판 구간 전\" 버림으로 보아 "
         "**차례로 만들지 않고**(그 순의 손패는 복원하지 않음),\n  t_ready 뒤 버림마다 차례 하나를 만든다."),
        ("- reveal_frame = 공개 뒤 끝 손패를 읽을 프레임. `game.py` 가 이 프레임과 앞뒤 0.5초 프레임, 모두 세 장으로 다수결해 읽으므로: 세 장 모두에서 눕힌 손패가\n"
         "  **한 줄로 가지런하고**(몇 장이 한 칸 앞뒤로 어긋나 있으면 손패 줄을 짧게 읽는다), ",
         "- reveal_frame = 공개 뒤 끝 손패를 볼 프레임. 이 판은 코드가 이 프레임에서 손패를 읽지 않는다(끝 손패는 판 결과 값 — 아래 판 구간 끝을 정하는 데 쓰인다).\n"
         "  고르는 잣대: 이 프레임과 앞뒤 0.5초 프레임, 세 장 모두에서 눕힌 손패가 **한 줄로 가지런하고**, "),
        # (설계서 8-16) 줄이 선 때의 늦은 후보 — ⑥ 의 "첫 세 차례까지 본다" 뒤 · 답 꼴 · 마지막 보고 줄
        ("  - 처음 가지런히 선 때에서 멈추지 말고, 그 뒤 이 사람의 첫 세 차례가 끝날 때까지 프레임을 보아 여러 장 재정리가 없는지 확인한다.\n",
         "  - 처음 가지런히 선 때에서 멈추지 말고, 그 뒤 이 사람의 첫 세 차례가 끝날 때까지 프레임을 보아 여러 장 재정리가 없는지 확인한다.\n"
         "  - t_ready 뒤 ~ 이 사람의 첫 세 차례가 끝날 때 사이에 여러 장을 옮기는 정리인지 한 장을 끼운 것인지 가리기 어려운 동작이 있으면, 한쪽으로 정하려 애쓰지 말고\n"
         "    t_ready 에는 더 그럴듯한 값을, 답의 t_ready_late 에는 늦은 후보 — 그 동작이 정리였다고 볼 때의 줄이 선 때(그 동작이 끝나 줄이 가만한 첫 프레임) — 를 적는다.\n"
         "    코드는 늦은 후보가 있으면(t_ready 보다 뒤면) 그것을 t_ready 로 쓴다. 늦게 잡으면 그 사이 버림의 차례를 복원하지 않을 뿐이고(패보에는 버림이 그대로 남는다),\n"
         "    이르게 잡으면 정리 동작이 첫 차례에 섞여 그 차례를 잘못 읽기 때문이다. 그런 동작이 없거나 t_ready 를 이미 그 뒤로 잡았으면 t_ready_late 의 time 은 null.\n"),
        ('  "t_ready_why": "그 프레임에서 본 것(줄 장수 · 손 위치) · 그 앞 정리가 언제 끝났는지",\n',
         '  "t_ready_why": "그 프레임에서 본 것(줄 장수 · 손 위치) · 그 앞 정리가 언제 끝났는지",\n'
         '  "t_ready_late": {"time": "HH:MM:SS.s", "why": "가리기 어려운 동작 · 그것을 정리로 볼 때 줄이 가만해진 프레임(없으면 time 은 null)"},\n'),
        ("- 마지막 답은 네 줄 이내: t_ready / 공개", "- 마지막 답은 네 줄 이내: t_ready · t_ready_late / 공개"),
    ]
    for a, b in subs:
        assert t.count(a) == 1, a[:60]
        t = t.replace(a, b)
    i0 = t.index("### ② river — 손패 주인 강")
    i1 = t.index("### ⑤ search — 참고 영역")
    t = t[:i0] + t[i1:]
    i0 = t.index("- ① 차례 목록 ↔ 기록의 손패 주인 버림:\n")
    i1 = t.index("- ② 활동 구간이 판 전체로 붙었다")
    t = t[:i0] + ("- ① 차례 목록은 기록에서 바로 만든다(강 사진을 읽지 않는다 — 기록의 t_ready 뒤 버림이 모두 차례가 된다).\n"
                  "  \"t_ready 앞(차례 아님)\" 버림이 네가 적은 pre_ready_discards 와 다르다 → t_ready 를 다시 본다.\n") + t[i1:]
    return t


def frame_lines(t0: int, t1: int) -> list:
    rec = hc.rec_of(t1)
    f = hc.frames(rec)
    t0 = max(t0, int(f[0]))
    return [(ms, hc.hms(ms), hc.path_of(ms)) for ms in hc.frame_range(t0, t1)]


def cmd_pack(a):
    cfg = hcfg.load(a.cfg, check=False)
    cfg.apply_recording(hc)
    sp = jl(a.spec)
    out = Path(a.out).resolve()
    gid, side = sp["gid"], sp["side"]
    R = sp["regions"]
    half = is_half(sp)                     # 기본 길 모드(녹화 틀 없음): 영역 = wide · band · search(후보 1위), 2 · 3위는 그림 · 표에만
    Rv = dict(R)
    for k_, c in zip(CAND_KEYS, (sp.get("band_candidates") or [])[1:]):
        Rv[k_] = list(c["band"])
    hd = sp.get("hero_discards") or []
    # 창
    a0 = sp["prev_last_ms"] if sp.get("prev_last_ms") else sp["first_ms"] - A_FIRST_LOOKBACK_S * 1000
    k = min(A_HERO_DISCARDS, len(hd))
    a1 = (hd[k - 1]["at"] if k else sp["first_ms"] + 120000) + A_AFTER_S * 1000
    b0 = sp["last_ms"] - B_BEFORE_S * 1000
    b1 = sp["last_ms"] + B_AFTER_S * 1000
    if sp.get("t_reveal_read_ms"):
        b1 = max(b1, sp["t_reveal_read_ms"] + B_DRAW_AFTER_S * 1000)
    A = frame_lines(a0, a1)
    B = frame_lines(b0, b1)
    (out / "work").mkdir(parents=True, exist_ok=True)
    (out / "overview").mkdir(parents=True, exist_ok=True)
    wt(out / "frames_ready.txt", "".join(f"{t}\t{p.as_posix()}\n" for _, t, p in A))
    wt(out / "frames_reveal.txt", "".join(f"{t}\t{p.as_posix()}\n" for _, t, p in B))
    # overview
    tr = sp.get("t_reveal_read_ms")
    shots = [(sp["first_ms"], "판 첫 버림"), ((sp["first_ms"] + sp["last_ms"]) // 2, "판 가운데"), (sp["last_ms"], "판 마지막 버림")]
    shots += [(tr + 3000, "판 결과 읽기 공개 + 3초"), (tr + 10000, "판 결과 읽기 공개 + 10초")] if tr else \
             [(sp["last_ms"] + 5000, "마지막 버림 + 5초"), (sp["last_ms"] + 15000, "마지막 버림 + 15초")]
    ov = []
    for n, (t, why) in enumerate(shots, 1):
        ms = hc.nearest(t)
        name = f"ov{n}_{hc.hms(ms).replace(':', '').replace('.', '_')}.jpg"
        if not a.task_only:
            overview(ms, Rv, f"{gid} {hc.hms(ms)} {why} · 손패 주인 = 사진 {SIDE_KO[side]}", out / "overview" / name)
        ov.append(f"  - `overview/{name}` — {hc.hms(ms)}({why})")
    # 검출기 표(--task-only 면 그대로 둠)
    rows_a, rows_b = [], []
    if a.task_only:
        old = jl(out / "pack.json")
        rows_a, rows_b = [None] * old["backs_rows"][0], [None] * old["backs_rows"][1]
    has_rev = "reveal_region" in R
    for rows, t0, t1, with_rev, is_b in (((rows_a, a0, a1, False, False), (rows_b, b0, b1, has_rev, True)) if not a.task_only else ()):
        t0 = max(t0, A[0][0] if not is_b else B[0][0])
        last = None
        for t in range(int(t0), int(t1) + 1, 1000):
            ms = hc.nearest(t)
            if ms == last:
                continue
            last = ms
            br = back_row(ms, R["band"], side)
            fr = sum(center_in(b, R["reveal_region"]) for b in br["_faces"]) if with_rev else None
            rng = f"{br['range'][0]} ~ {br['range'][1]}" if br["range"] else "—"
            rows.append(f"| {hc.hms(ms)} | {br['backs']} | {br['cluster']} | {rng} | {br['faces']} |" + (f" {fr} |" if with_rev else ""))
    ax = AXIS[side]
    md = [f"# 검출기 표 — 판 `{gid}`(기계 판독 — 틀릴 수 있다. TASK.md \"검출기 표\" 참고)", "",
          f"셈하는 곳 = 녹화 틀 band {R['band']} 를 줄 방향(원본 {ax})으로 ±{BACK_PAD}px 넓힌 곳 {hta.det_box(R['band'], side)} (깊이는 band 그대로).", "",
          f"## 줄이 서는 쪽({A[0][1]} ~ {A[-1][1]})", "",
          f"| 시각 | 뒷면 상자 | 가장 큰 덩어리 | 덩어리 범위(원본 {ax}) | 앞면 상자 |", "|---|---|---|---|---|", *rows_a, "",
          f"## 공개 쪽({B[0][1]} ~ {B[-1][1]})", "",
          *([f"| 시각 | 뒷면 상자 | 가장 큰 덩어리 | 덩어리 범위(원본 {ax}) | 앞면 상자 | reveal_region 안 앞면 상자 |", "|---|---|---|---|---|---|"] if has_rev else
            [f"| 시각 | 뒷면 상자 | 가장 큰 덩어리 | 덩어리 범위(원본 {ax}) | 앞면 상자 |", "|---|---|---|---|---|"]), *rows_b, ""]
    if half:
        md[2] = md[2].replace("녹화 틀 band", "band(손패 줄 후보 1위)", 1)
    if not a.task_only:
        wt(out / "backs.md", "\n".join(md))
    # TASK.md
    win = sp["end"] == "win"
    wtype = {"ron": "론", "tsumo": "쯔모"}.get(sp.get("win_type"), sp.get("win_type") or "모름")
    end_text = (f"화료 — 손패 주인의 {wtype}" + (f"(방총 = 사진 {SIDE_KO.get(sp.get('loser_side'), '?')} 자리)" if sp.get("win_type") == "ron" and sp.get("loser_side") else "")
                if win else "보통 유국(황패) — 손패 주인은 텐파이로 손패를 앞면으로 공개한 자리")
    hd_rows = "\n".join(f"| {x['n']} | {x['tile']} | {hc.hms(x['at']) if x.get('at') else '모름'} | {'예' if x.get('riichi') else ''} | {'예' if x.get('after_call') else ''} |"
                        for x in hd) or "| — | — | — | — | — |"
    calls = sp.get("hero_calls") or []
    calls_text = ("\n- 손패 주인 울기: " + " · ".join(f"{c.get('kind')} {' '.join(c.get('tiles') or [])}(받은 버림을 기록기가 처음 본 때 {hc.hms(c['at']) if c.get('at') else '모름'})"
                                                   for c in calls) + "\n") if calls else ""
    reveal_text = (f"\n- 공개(판 결과 읽기 값): t_reveal = {hc.hms(tr)}\n" if tr else "")
    t = TASK.format(
        gid=gid, round_label=sp.get("round_label") or "", hero=sp["hero"], side_ko=SIDE_KO[side], side=side, dealer=sp["dealer"],
        dealer_note=" — 손패 주인이 선이다" if sp["dealer"] == sp["hero"] else "", bottom=sp["bottom"], end_text=end_text, n_calls=sp.get("n_calls", 0),
        n_closed_end=sp["n_closed_end"], riichi_text=" · 리치함" if sp.get("hero_riichi") else "", row_text=ROW_TEXT[side], axis=AXIS[side], lr=LR[side],
        front=FRONT[side], corner=CORNER[side], rot=hc.ROT[side], dir=out.as_posix(), n_ov=len(ov), ov_list="\n".join(ov),
        a_from=(f"앞 판 마지막 버림({hc.hms(sp['prev_last_ms'])})" if sp.get("prev_last_ms") else f"판 첫 버림 {A_FIRST_LOOKBACK_S}초 앞(이 판 앞에 기록된 판이 없음)")
        if A[0][0] <= a0 + 100 else f"녹화 첫 프레임({A[0][1]})",
        a_to=(f"손패 주인 {k}번째 버림 + {A_AFTER_S}초" if k else f"판 첫 버림 + 120초") + f"({A[-1][1]})", n_a=len(A),
        b_from=f"판 마지막 버림 {B_BEFORE_S}초 앞({B[0][1]})", b_to=(f"마지막 버림 + {B_AFTER_S}초" + (f" · 판 결과 읽기 공개 + {B_DRAW_AFTER_S}초 중 늦은 쪽" if tr else "")) + f"({B[-1][1]})",
        n_b=len(B), region_rows="\n".join([f"| {k_} | {R[k_]} | {COLOR_KO[k_]} |" for k_ in ASK if k_ in R and not (half and k_ in CODE_REGIONS)]
                                          + [f"| ({k_} — 버림 기록기가 본 패에서 코드가 낸 값 · 답 칸 아님) | {R[k_]} | {COLOR_KO[k_]} |"
                                             for k_ in CODE_REGIONS if half and k_ in R]
                                          + [f"| (손패 줄 후보 {n_ + 2}위 — 답 칸 아님) | {Rv[k_]} | {COLOR_KO[k_]} |" for n_, k_ in enumerate(CAND_KEYS) if k_ in Rv]),
        ev_title=sp.get("events_title") or "기록에서 온 시각", first=hc.hms(sp["first_ms"]), last=hc.hms(sp["last_ms"]),
        prev_text=(f" · 앞 판 마지막 버림: {hc.hms(sp['prev_last_ms'])}" if sp.get("prev_last_ms") else ""),
        n_hd=len(hd), hd_rows=hd_rows, calls_text=calls_text, reveal_text=reveal_text,
        reveal_def=REVEAL_DEF_WIN if win else REVEAL_DEF_DRAW.format(t_reveal=hc.hms(tr) if tr else "모름"),
        reveal_tiles=f"닫힌 손패 {sp['n_closed_end']}장과 떼어 둔 화료패" if win else f"공개한 손패 {sp['n_closed_end']}장이",
        pad=BACK_PAD, join=JOIN, answer=(out / "answer.json").as_posix(), t_reveal_example='"HH:MM:SS.s"' if win else "null", work=(out / "work").as_posix(),
        script=SCRIPT.as_posix())
    if half:
        t = task_half(t, sp)
    wt(out / "TASK.md", t)
    pk = {"gid": gid, "spec": sp, "window_ready": [A[0][1], A[-1][1], len(A)], "window_reveal": [B[0][1], B[-1][1], len(B)], "overview": [x.split("`")[1] for x in ov],
          "backs_rows": [len(rows_a), len(rows_b)], "task": (out / "TASK.md").as_posix(), "answer": (out / "answer.json").as_posix(),
          "try": try_info(cfg, gid, a)}
    wj(out / "pack.json", pk)
    print("JSON" + json.dumps({k_: v for k_, v in pk.items() if k_ != "spec"}, ensure_ascii=False))


# ------------------------------------------------------------------ S6a-3 적용 · 검사
CONFIG_KEYS = ["side", "t_start", "t_ready", "t_reveal", "reveal_frame", "post_sec", "band", "river", "meld", "reveal_region"]   # 판별 출력이 이 값에 달림


def _region(v):
    if isinstance(v, dict):
        v = v.get("value")
    if isinstance(v, (list, tuple)) and len(v) == 4:
        try:
            return [int(round(float(x))) for x in v]
        except (TypeError, ValueError):
            return None
    return None


def _hms(v):
    if not isinstance(v, str) or v.count(":") != 2:
        return None
    try:
        return hc.to_ms(v.strip())
    except ValueError:
        return None


def parse_answer(ans: dict, sp: dict) -> tuple:
    """답 → (영역 dict, 시각 dict(ms), 꼴 오류 목록 — 멈출 것, 고친 영역 목록)."""
    R = dict(sp["regions"])
    fatal, changed = [], []
    for k in ASK:
        if is_half(sp) and k in CODE_REGIONS and k in R:   # (설계서 8-14 (가)) 묻지 않은 강 · 울기 — 답에 있어도 코드 값
            continue
        v = _region(ans.get(k))
        if v is None:
            if ans.get(k) is not None:
                fatal.append(f"{k}: 좌표 꼴이 아님({ans.get(k)!r:.80})")
            continue
        if v != R.get(k):          # 기본 길 모드: 묻지 않은 영역(river · meld · reveal_region)이 답에 있으면 그 값을 씀(고친 영역으로 적힘)
            changed.append(k)
        R[k] = v
    miss = [k for k in MUST_FOR_FEATURES if k not in R]
    if miss:
        fatal.append(f"{miss} 없음 — 공용 판별 features.py 가 이 영역을 읽고(segment.py 는 river 움직임을 활동으로, turncut 은 river 피부로 버림 때를 셈) "
                     "기본 길 모드는 이 영역을 묻지 않는다(설계서 8-13 (다) 와 지금 판별 코드가 안 맞음 — 구현 2-③ 보고)")
    T = {"t_ready": _hms(ans.get("t_ready")), "reveal_frame": _hms(ans.get("reveal_frame"))}
    T["t_reveal"] = sp["t_reveal_read_ms"] if sp["end"] != "win" and sp.get("t_reveal_read_ms") else _hms(ans.get("t_reveal"))
    for k, v in T.items():
        if v is None:
            fatal.append(f"{k}: 시각이 없거나 'HH:MM:SS.s' 꼴이 아님({ans.get(k)!r:.40})")
    # (11-25 밤, 설계서 8-16) 줄이 선 때의 늦은 후보 — 칸이 없거나 time 이 null 이면 None(옛 답과 똑같이 돎)
    T["t_ready_late"] = None
    late = ans.get("t_ready_late")
    if late is not None:
        lt = late.get("time") if isinstance(late, dict) else late
        if not isinstance(late, dict):
            fatal.append(f"t_ready_late: {{\"time\": \"HH:MM:SS.s\" 또는 null, \"why\": \"…\"}} 꼴이 아님({late!r:.60})")
        elif lt is not None:
            T["t_ready_late"] = _hms(lt)
            if T["t_ready_late"] is None:
                fatal.append(f"t_ready_late.time: 'HH:MM:SS.s' 꼴 또는 null 이 아님({lt!r:.40})")
            elif T["t_reveal"] is not None and T["t_ready_late"] >= T["t_reveal"]:
                fatal.append(f"t_ready_late.time {hc.hms(T['t_ready_late'])} 가 t_reveal {hc.hms(T['t_reveal'])} 과 같거나 뒤")
    return R, T, fatal, changed


def purge(gid: str) -> list:
    """실행 폴더(handtrack.dir)의 그 판 판별 출력 · 칸 틀 캐시를 지운다(설정이 바뀌었을 때). 공용 자리는 절대 안 건드림."""
    d = htr._ST["dir"]
    assert d is not None and gid in htr.games(), gid
    gone = []
    for p in (Path(htr.remap(hc.WORK / f"{gid}_feat.npz")), Path(htr.remap(hc.OUT / gid)), d / "_work" / "slotgrid_1117" / f"det_{gid}.json"):
        p = p.resolve()
        assert d.resolve() in p.parents, p     # 실행 폴더 밖이면 멈춤
        if p.is_dir():
            shutil.rmtree(p)
            gone.append(p.as_posix())
        elif p.exists():
            p.unlink()
            gone.append(p.as_posix())
    return gone


def check_coords(R: dict, side: str) -> list:
    bad = []
    for k in [x for x in ASK if x in R]:
        x0, y0, x1, y1 = R[k]
        if not (0 <= x0 < x1 <= 1496 and 0 <= y0 < y1 <= 1496):
            bad.append(f"{k} {R[k]}: 그림 밖이거나 x0 ≥ x1 · y0 ≥ y1")
        elif (x1 - x0) < 20 or (y1 - y0) < 20:
            bad.append(f"{k} {R[k]}: 너무 작음(한 변 < 20px)")
    x0, y0, x1, y1 = R["band"]
    along, depth = ((y1 - y0), (x1 - x0)) if AXIS[side] == "y" else ((x1 - x0), (y1 - y0))
    if along <= depth:
        bad.append(f"band {R['band']}: 줄 방향(원본 {AXIS[side]}) 길이 {along} ≤ 깊이 {depth} — 꼴이 줄과 안 맞음")
    return bad


def cmd_apply(a):
    cfg = hta.configure(a.cfg)
    sp = jl(a.spec)
    gid, side = sp["gid"], sp["side"]
    if htr._ST["dir"] is None or gid not in htr.games():
        raise SystemExit(f"{gid}: 반장 설정 handtrack.dir · games 에 이 판이 없다 — 공용 자리에 쓰지 않으려고 멈춤")
    ans = jl(a.answer)
    R, T, fatal, changed = parse_answer(ans, sp)
    res = {"gid": gid, "answer": Path(a.answer).as_posix(), "changed_regions": changed, "fatal": fatal, "checks": [], "questions": []}
    if fatal:
        wj(a.out, res)
        print("JSON" + json.dumps(res, ensure_ascii=False))
        return
    t_ready, t_rev, rf = T["t_ready"], T["t_reveal"], T["reveal_frame"]
    # (설계서 8-16) 쓰는 값 = 늦은 후보가 있고 답의 t_ready 보다 뒤면 그것(그 뒤 손패 주인 버림이 하나도 없으면 안 씀 — 질문), 아니면 답의 t_ready
    late, rl = T.get("t_ready_late"), None
    if late is not None:
        hd0 = sp.get("hero_discards") or []
        rl = {"answer": hc.hms(t_ready), "late": hc.hms(late), "why": (ans.get("t_ready_late") or {}).get("why", "")}
        if late <= t_ready:
            rl.update(which="answer", note="늦은 후보가 답의 t_ready 와 같거나 앞 — 무시")
        elif not any(x.get("at") and x["at"] > late for x in hd0):
            rl.update(which="answer", note="늦은 후보 뒤 손패 주인 버림 0(차례 0 이 됨) — 안 쓰고 답의 t_ready 로, 질문", ask=True)
        else:
            skip = [x for x in hd0 if x.get("at") and t_ready < x["at"] <= late]
            rl.update(which="late", note=f"늦은 후보를 씀 — 그 사이 손패 주인 버림 {len(skip)}장은 차례로 복원하지 않음",
                      not_restored=[f"{x['tile']}@{hc.hms(x['at'])}" for x in skip])
            t_ready = late
        rl["used"] = hc.hms(t_ready)
        res["ready_late"] = rl
    t_start = t_ready - T_START_LEAD_S * 1000
    post = max(4, math.ceil((rf - t_rev) / 1000 + 2))
    cf = {"id": gid, "side": side, "t_start": hc.hms(t_start), "t_ready": hc.hms(hc.nearest(t_ready)), "t_reveal": hc.hms(t_rev),
          "reveal_frame": hc.hms(hc.nearest(rf)), "post_sec": post, **{k: list(R[k]) for k in REGIONS if k in R},
          "result": {"draw": "draw_tenpai"}.get(sp["end"], sp.get("win_type") or sp["end"]), "riichi": bool(sp.get("hero_riichi")),
          "auto": "s6a_read", "s6a_answer": Path(a.answer).as_posix(),
          "winner_side_how": f"자동: {sp.get('side_rule', '')}", "result_how": f"자동: {sp.get('result_how', '')}",
          "ready_note": f"S6a 준비 읽기: {ans.get('t_ready_why', '')}"[:600],
          "notes": [f"S6a 준비 읽기 답({Path(a.answer).as_posix()}) — 영역 고침 {changed or '없음'}, t_start = t_ready − {T_START_LEAD_S}초(features 구간 시작일 뿐), "
                    f"post_sec = max(4, ⌈reveal_frame − t_reveal + 2⌉)" + ("" if sp["end"] == "win" else " · 유국 t_reveal = 판 결과 읽기 값"),
                    f"reveal: {ans.get('reveal_why', '')}"[:600]] + [f"{k}: {(ans.get(k) or {}).get('why', '')}"[:300] for k in changed if isinstance(ans.get(k), dict)]}
    if rl:   # (설계서 8-16) 늦은 후보가 있던 답만 — 칸 없음 · null 이면 설정은 옛 그대로
        cf["notes"].append(f"t_ready: 답 {rl['answer']} · 늦은 후보 {rl['late']} · 씀 {rl['used']} — {rl['note']}(설계서 8-16)")
    if is_half(sp):
        code = [k for k in CODE_REGIONS if k in sp["regions"]]
        unused = {k: ans.get(k) for k in code if ans.get(k) is not None} or "없음"
        cf["regions_note"] = (f"기본 길 모드(녹화 틀 없음, 설계서 8-13 (다)): wide = 화면 절반, band · search 는 손패 줄 후보 1위 {sp['regions'].get('band')} 에서 시작해 답 값. "
                              f"{code} 는 코드 값({sp.get('regions_code_from') or 'spec regions'} — 설계서 8-14 (가)), 답에 있던 값 {unused} 은 안 씀. "
                              f"답에 있던 그 밖의 묻지 않은 영역 {[k for k in ('river', 'meld', 'reveal_region') if k in R and k not in code]} 은 답 값 그대로")
    cpath = Path(htr.remap(hc.CONFIG / f"{gid}.json"))
    old = jl(cpath) if cpath.exists() else None
    gone = []
    if old is None or any(old.get(k) != cf.get(k) for k in CONFIG_KEYS):
        gone = purge(gid)
        hc.jsave(hc.CONFIG / f"{gid}.json", cf)       # ht_redirect → 실행 폴더
        res["config_written"] = True
    else:
        res["config_written"] = False                 # 같은 답 — 설정 · 판별 출력(sheet_band 포함) 그대로
        cf = old
    res["purged"] = gone
    fpath = Path(htr.remap(hc.WORK / f"{gid}_feat.npz"))
    if not fpath.exists():
        import features
        sys.argv = ["features.py", gid]
        features.main()
    # ---- 검사(어긋나면 질문 — 값은 에이전트 것을 둠)
    ck, qs = res["checks"], res["questions"]

    def check(name, ok, detail, q_why=None, clip=None):
        ck.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            qs.append({"check": name, "why": q_why or detail, "clip": clip})
    bad = check_coords(R, side)
    check("coords", not bad, "; ".join(bad) or "영역 다섯이 그림 안 · 꼴 맞음", clip=None)
    order = t_start < t_ready < t_rev <= rf
    check("time_order", order, f"t_start {hc.hms(t_start)} < t_ready {hc.hms(t_ready)} < t_reveal {hc.hms(t_rev)} ≤ reveal_frame {hc.hms(rf)}",
          clip={"t0": hc.hms(t_ready - 5000), "t1": hc.hms(rf + 5000)})
    hd = sp.get("hero_discards") or []
    after = [x for x in hd if x.get("at") and x["at"] > t_ready]
    pre = [x for x in hd if x.get("at") and x["at"] <= t_ready]
    res["hero_discards_after_ready"] = len(after)
    res["hero_discards_before_ready"] = [f"{x['tile']}@{hc.hms(x['at'])}" for x in pre]
    check("ready_before_discards", bool(after), f"t_ready 뒤 손패 주인 버림 {len(after)} · 앞 {len(pre)}({res['hero_discards_before_ready']})",
          q_why=f"t_ready {hc.hms(t_ready)} 뒤에 손패 주인 버림이 없음 — 차례가 0 이 됨", clip={"t0": hc.hms(t_ready - 30000), "t1": hc.hms(t_ready + 10000)})
    if rl:   # (설계서 8-16) 늦은 후보: 씀 · 무시는 통과(표시만), 뒤 버림 0 이라 못 씀은 질문
        check("ready_late", not rl.get("ask"), f"답 t_ready {rl['answer']} · 늦은 후보 {rl['late']} · 씀 {rl['used']} — {rl['note']}",
              q_why=f"늦은 후보 {rl['late']} 뒤에 손패 주인 버림이 없어 안 씀(답의 t_ready {rl['answer']} 로 감) — 늦은 후보 · t_ready 를 확인",
              clip={"t0": hc.hms(hc.to_ms(rl["answer"]) - 5000), "t1": hc.hms(hc.to_ms(rl["late"]) + 10000)})
    if sp["end"] == "win":
        check("reveal_after_last", t_rev >= sp["last_ms"] - 3000, f"t_reveal {hc.hms(t_rev)} · 마지막 버림(기록기) {hc.hms(sp['last_ms'])}",
              q_why=f"t_reveal {hc.hms(t_rev)} 가 판 마지막 버림(기록기가 처음 본 때 {hc.hms(sp['last_ms'])}) − 3초보다 앞",
              clip={"t0": hc.hms(sp["last_ms"] - 10000), "t1": hc.hms(rf + 5000)})
    calls_before = sum(1 for c in sp.get("hero_calls") or [] if c.get("at") and c["at"] <= t_ready)
    want = 13 - 3 * calls_before
    ms_r = hc.nearest(t_ready)
    br = back_row(ms_r, R["band"], side)
    nb = [back_row(hc.nearest(ms_r + d), R["band"], side)["cluster"] for d in (100, 200)]
    ok_r = br["cluster"] == want and br["cluster_out_of_band"] <= READY_OUT_OK
    check("ready_backs", ok_r, f"t_ready 프레임 {hc.hms(ms_r)} 뒷면 상자 가장 큰 덩어리 {br['cluster']}장(원하는 {want}) · 범위 {br['range']} · band 밖 상자 {br['cluster_out_of_band']}(허용 {READY_OUT_OK}) "
          f"(+0.1 · +0.2초 {nb})",
          q_why=f"t_ready {hc.hms(ms_r)} 프레임의 검출기 뒷면 상자 가장 큰 덩어리가 {br['cluster']}장(닫힌 장수 {want})"
                + (f" · 덩어리 중 {br['cluster_out_of_band']}장이 band 밖" if br["cluster_out_of_band"] > READY_OUT_OK else "") + f" — 답의 closed_at_ready {ans.get('closed_at_ready')}",
          clip={"t0": hc.hms(t_ready - 10000), "t1": hc.hms(t_ready + 10000)})
    ms_f = hc.nearest(rf)
    n_in = n_edge = None
    if "reveal_region" in R:
        faces, _b = raw_boxes(ms_f)
        n_in = sum(center_in(b, R["reveal_region"]) for b in faces)
        x0, y0, x1, y1 = R["reveal_region"]
        big = [x0 - FACE_EDGE_PX, y0 - FACE_EDGE_PX, x1 + FACE_EDGE_PX, y1 + FACE_EDGE_PX]
        n_edge = sum(center_in(b, big) and not center_in(b, R["reveal_region"]) for b in faces)
        need = sp["n_closed_end"] - REVEAL_MISS_OK
        check("reveal_faces", n_in >= need, f"reveal_frame {hc.hms(ms_f)} reveal_region 안 앞면 상자 {n_in}(닫힌 장수 {sp['n_closed_end']} − {REVEAL_MISS_OK} = {need} 이상이어야) · "
              f"영역 둘레 {FACE_EDGE_PX}px 에만 있는 앞면 상자 {n_edge}",
              q_why=f"공개 프레임 {hc.hms(ms_f)} 의 reveal_region 안 앞면 상자 {n_in}장 — 손패 {sp['n_closed_end']}장보다 많이 모자람(영역 · 프레임 확인)",
              clip={"t0": hc.hms(t_rev - 3000), "t1": hc.hms(rf + 5000)})
    else:   # 기본 길 모드에서 답에 reveal_region 이 없음 — 공개 손패를 영역으로 안 읽음(끝 손패는 판 결과 값), 이 검사는 안 함(표시)
        ck.append({"name": "reveal_faces", "ok": True, "skipped": True, "detail": "reveal_region 없음 — 안 봄(기본 길 모드: 끝 손패는 판 결과 값)"})
    unsure = ans.get("unsure") or []
    if unsure:
        res["unsure"] = unsure
    res["tries"] = len(ans.get("tries") or [])
    res["config"] = {k: cf.get(k) for k in CONFIG_KEYS + ["search", "wide"]}
    res["detail"] = {"ready_backs": {k: v for k, v in br.items() if k != "_faces"}, "reveal_faces": {"in": n_in, "edge": n_edge}, "want_closed_at_ready": want,
                     "answer_closed_at_ready": ans.get("closed_at_ready"), "answer_pre_ready": ans.get("pre_ready_discards")}
    wj(a.out, res)
    print("JSON" + json.dumps({k: v for k, v in res.items() if k != "detail"}, ensure_ascii=False))


# ------------------------------------------------------------------ S6a-2 돌려 보기(try — 설계서 8-9)
REC_NEED = ["paifu_rec.json", "dart_overlay_v2.json", "overlay_dump.json"]   # han3 fix(paifu_rec) · turncut build(dart_overlay_v2 · overlay_dump)


def try_info(cfg, gid: str, a) -> dict:
    """pack.json 의 try 칸 — try 가 꾸러미 폴더만으로 돌게 하는 경로. 기본: 기록 = <prep_dir>/rec/<판>, 판 결과 = <results_dir>/<판>/result_read.json."""
    rec = Path(a.rec).resolve() if getattr(a, "rec", None) else cfg.prep_dir / "rec" / gid
    rr = Path(a.result_read).resolve() if getattr(a, "result_read", None) else cfg.results_dir / gid / "result_read.json"
    return {"base_cfg": cfg.path.as_posix(), "rec_dir": rec.as_posix(), "rec_missing": [x for x in REC_NEED if not (rec / x).exists()],
            "result_read": rr.as_posix() if rr.exists() else None, "max_tries": MAX_TRIES, "script": SCRIPT.as_posix(),
            "note": "try 가 쓰는 재료(읽기만): 반장 설정(results_dir · rounds_meta · 녹화 자리) · 기록 폴더(시험 자리 prep/rec 로 복사) · 판 결과(보고서 ③ 견줌)"}


def norm(t):
    return ("5" + t[1]) if t and t[0] == "0" else t


def turns_after_fix(cfg, g: str) -> list:
    """han3 차례 목록 + turn_fix(칸 고침 · __insert__ 끼움) — paifu_auto.turns_after_fix 와 같은 셈(이 프로세스에 han3 · paifu_auto 를 안 들이려고 따로)."""
    T = jl(cfg.turns_file) if cfg.turns_file.exists() else {"games": []}
    gg = next((x for x in T["games"] if x["id"] == g), None)
    if gg is None:
        return []
    fx = jl(cfg.fix_file) if cfg.fix_file.exists() else {}
    turns = [dict(t) for t in gg["turns"]]
    for ins in fx.get("__insert__") or []:
        if not cfg.owns(ins["id"], g) or any(t["id"] == ins["id"] for t in turns):
            continue
        k = next((i for i, t in enumerate(turns) if t["id"] == ins["after"]), None)
        if k is None:
            continue
        turns.insert(k + 1, {"id": ins["id"], "label": ins["id"].split("_d")[1], "tile": ins["tile"], "sideways": ins.get("sideways", False), "synthetic": True})
    for t in turns:
        f = fx.get(t["id"]) or {}
        for k in ("tile", "sideways", "kind"):
            if k in f:
                t[k] = f[k]
    return turns


def _claim(troot: Path, n: int | None, force: bool) -> tuple:
    """시험 번호를 잡는다(mkdir 이 원자적이라 나란히 불러도 안 겹침)."""
    troot.mkdir(parents=True, exist_ok=True)
    used = sorted(int(p.name) for p in troot.iterdir() if p.is_dir() and p.name.isdigit())
    if len(used) >= MAX_TRIES and not force:
        raise SystemExit(f"try 한도 {MAX_TRIES}번을 다 썼다(이미 {used}) — 마지막 값을 answer.json 에 쓰고 끝낸다")
    if n:
        d = troot / str(n)
        try:
            d.mkdir()
        except FileExistsError:
            raise SystemExit(f"시험 자리 {d} 가 이미 있다 — --n 을 빼면 다음 번호를 쓴다")
        return n, d
    k = 1
    while True:
        d = troot / str(k)
        try:
            d.mkdir()
            return k, d
        except FileExistsError:
            k += 1


def _step(name: str, args: list, d: Path, T: dict) -> subprocess.CompletedProcess:
    t0 = time.time()
    env = {k: v for k, v in os.environ.items() if k != "HAN3_FINAL"}
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([str(x) for x in args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    T[name] = round(time.time() - t0, 1)
    wt(d / "logs" / f"{name}.log", " ".join(map(str, args)) + f"\n# rc {p.returncode} · {T[name]}s\n" + p.stdout + "\n--- stderr\n" + p.stderr)
    return p


def try_cfg(d: Path, ti: dict, gid: str) -> Path:
    """시험 자리의 반장 설정 사본 — 읽는 것(results_dir · 녹화)은 원래 설정 그대로, 쓰는 것(prep · read · handtrack · paifu)은 모두 시험 자리."""
    raw = jl(ti["base_cfg"])
    raw["_note"] = (f"handtrack_prep try 시험 자리 설정({ti['base_cfg']} 사본) — prep_dir · read_root · handtrack.dir · paifu.out_dir 만 이 시험 자리로 바꿈. "
                    "games · results_dir 은 원래 그대로(겹침 검사가 같은 반장 사본으로 봄)")
    raw["prep_dir"] = (d / "prep").as_posix()
    raw["read_root"] = (d / "read").as_posix()
    raw["handtrack"] = {"dir": (d / "handtrack").as_posix(), "games": [gid], "_note": "try: 이 판의 판별 설정 · 출력은 시험 자리(ht_redirect)"}
    raw["paifu"] = {**(raw.get("paifu") or {}), "out_dir": (d / "paifu").as_posix()}
    f = d / "cfg" / "hanchan.json"        # 이 폴더에 다른 json 을 두지 않는다(hanchan_cfg 겹침 검사 ④ 가 같은 폴더의 json 을 다른 반장 설정으로 읽음)
    wj(f, raw)
    return f


def cmd_try(a):
    t_all = time.time()
    pack = Path(a.pack).resolve()
    pk = jl(pack / "pack.json")
    ti = pk.get("try")
    if not ti:
        raise SystemExit(f"{pack}/pack.json 에 try 칸이 없다 — 꾸러미를 새 코드로 다시 만들어라(handtrack_prep.py pack --task-only)")
    sp = pk["spec"]
    gid = sp["gid"]
    ans_src = Path(a.answer).resolve()
    try:
        ans = jl(ans_src)                  # 꼴이 JSON 이 아니면 여기서 멈춤(시험 번호를 안 씀)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"초안 답 {ans_src} 를 못 읽음(JSON 이 아님 · 없음) — {e}")
    if ti.get("rec_missing"):
        raise SystemExit(f"기록 폴더 {ti['rec_dir']} 에 {ti['rec_missing']} 가 없다")
    n, d = _claim(pack / "try", a.n, a.force)
    wj(d / "answer.json", ans)
    wj(d / "spec.json", sp)
    T = {}
    cfgf, err, fatal = _try_steps(d, ti, gid, T)
    T["total"] = round(time.time() - t_all, 1)
    md, js = try_report(d, n, pk, cfgf, T, err, fatal)
    wt(d / "report.md", md)
    wj(d / "report.json", js)
    print(md)
    if err:
        raise SystemExit(1)


def _try_steps(d: Path, ti: dict, gid: str, T: dict) -> tuple:
    """시험 자리 d(d/answer.json · d/spec.json 이 있어야 함)에서 try 의 걸음: 반장 설정 사본 · 기록 복사 → apply → run → rturns(앱 기록) 또는 turns · fix
    → turncut. try 와 alt(설계서 8-19)가 같이 쓴다. T 에 걸음마다 초. → (시험 자리 설정 파일, 걸음 실패 글 또는 None, 적용 fatal 또는 None)."""
    cfgf = try_cfg(d, ti, gid)
    shutil.copytree(ti["rec_dir"], d / "prep" / "rec" / gid)
    err = None
    PY = sys.executable
    # 앱 기록 반장(설정 app_record — 설계서 8-13 (가)): 강 읽기(river) 걸음을 안 돌리고 차례 목록은 기록에서(han3 rturns). 아니면 옛 그대로(turns · fix)
    rec_mode = bool(hcfg.load(cfgf, check=False).app_record)
    steps = [("apply", [PY, "-X", "utf8", SCRIPT, "apply", "--cfg", cfgf, "--spec", d / "spec.json", "--answer", d / "answer.json", "--out", d / "applied.json"]),
             ("run", [PY, "-X", "utf8", HERE / "handtrack_auto.py", "run", "--cfg", cfgf, gid] + (["--no-river"] if rec_mode else []))]
    steps += ([("rturns", [PY, "-X", "utf8", HT / "han3.py", "rturns", gid, "--hanchan", cfgf])] if rec_mode else
              [("turns", [PY, "-X", "utf8", HT / "han3.py", "turns", gid, "--hanchan", cfgf]),
               ("fix", [PY, "-X", "utf8", HT / "han3.py", "fix", "--write", gid, "--hanchan", cfgf])])
    steps += [("turncut", [PY, "-X", "utf8", HT / "han3.py", "turncut", "build", gid, "--hanchan", cfgf])]
    fatal = None
    for name, args in steps:
        p = _step(name, args, d, T)
        if p.returncode:
            err = f"{name} 단계 실패(rc {p.returncode}) — 로그 {(d / 'logs' / (name + '.log')).as_posix()}\n" + (p.stderr or p.stdout)[-1200:]
            break
        if name == "apply":
            o = jl(d / "applied.json")
            if o.get("fatal"):
                fatal = o["fatal"]
                break
    return cfgf, err, fatal


# ------------------------------------------------------------------ 대안 돌리기(alt — 설계서 8-19, 11-26, LLM 0)
# 답의 unsure 줄마다 {"what": 칸, "alt": 다른 후보 값 또는 null, "why"} — 코드가 alt 로 try 와 같은 걸음을 한 번 더 돌려 차례 목록 · 차례 창을 기준(답 그대로)과 견준다.
ALT_WIN_S = 1.0            # 창 차이 문턱: id 가 같은 차례의 창(첫 · 끝 프레임)이 이만큼 넘게 움직이면 "창 흔들림"(8-15 의 줄이 선 때 ±1.0초 잣대 그대로)
ALT_PARALLEL = 4           # 기준 · 대안 시험 자리를 동시에 몇 개(try 는 여러 자리를 나란히 돌려도 안 겹침)
ALT_REGION_KEYS = ["band", "river", "meld", "reveal_region", "search"]
ALT_MARK = ".alt_dir"      # alt 가 만든 자리 표시(다시 부를 때 이 표시가 있는 자리만 지우고 새로)


def alt_whats(sp: dict) -> list:
    """alt 를 쓸 수 있는 what = 답 꼴에서 값을 갖는 칸(설계서 8-19 (가)). 기본 길 모드는 묻는 칸만(강 · 울기는 코드 값 — 답 값을 안 씀)."""
    if is_half(sp):
        return ["band", "search", "t_ready", "t_ready_late", "t_reveal", "reveal_frame"]
    return ["band", "river", "meld", "reveal_region", "search", "t_ready", "t_ready_late", "t_reveal", "reveal_frame"]


def alt_value_of(ans: dict, what: str):
    """답의 그 칸 지금 값(alt 와 같은 꼴 — 영역 [x0, y0, x1, y1] · 시각 글 · t_ready_late 는 time)."""
    v = ans.get(what)
    if what in ALT_REGION_KEYS:
        return _region(v)
    if what == "t_ready_late":
        return v.get("time") if isinstance(v, dict) else v
    return v


def alt_memo(u, sp: dict):
    """unsure 줄 하나가 대안으로 돌릴 수 있는가 — 못 돌리면 메모 까닭(글), 돌릴 수 있으면 None.
    순서: 꼴(사전 아님) → alt 칸 없음(옛 답) → 쓸 수 없는 what → null(t_ready_late 밖) → 값 꼴 틀림."""
    if not isinstance(u, dict):
        return "unsure 줄 꼴 틀림(사전이 아님) — 대안을 못 돌림"
    if "alt" not in u:
        return "alt 칸 없음(옛 답 꼴) — 대안을 못 돌림"
    what, v = u.get("what"), u.get("alt")
    if what not in alt_whats(sp):
        return f"쓸 수 없는 what {what!r} — 대안을 돌릴 수 있는 칸은 {', '.join(alt_whats(sp))}"
    if what == "t_reveal" and sp.get("end") != "win":
        return "유국 판의 t_reveal 은 판 결과 읽기 값(답의 값을 안 씀) — 대안을 돌릴 칸이 아님"
    if v is None:
        return None if what == "t_ready_late" else "alt 가 null — 값으로 적은 다른 후보 없음"
    if what in ALT_REGION_KEYS:
        ok = isinstance(v, (list, tuple)) and len(v) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
        return None if ok else f"alt 꼴 틀림 — 영역은 [x0, y0, x1, y1]({v!r:.60})"
    return None if _hms(v) is not None else f"alt 꼴 틀림 — 시각은 'HH:MM:SS.s'({v!r:.40})"


def alt_variant(ans: dict, what: str, v) -> dict:
    """답 사본에서 what 칸만 alt 값으로(영역은 value · t_ready_late 는 time — 나머지 글 칸은 그대로)."""
    a = json.loads(json.dumps(ans, ensure_ascii=False))
    if what in ALT_REGION_KEYS:
        vv = [int(round(float(x))) for x in v]
        a[what] = {**a[what], "value": vv} if isinstance(a.get(what), dict) else vv
    elif what == "t_ready_late":
        old = a.get("t_ready_late") if isinstance(a.get("t_ready_late"), dict) else {}
        a["t_ready_late"] = {**old, "time": v, "why": old.get("why") or "(설계서 8-19 대안 돌리기 — unsure 의 alt)"}
    else:
        a[what] = v
    a["_alt"] = {"what": what, "alt": v, "note": "handtrack_prep.py alt 가 만든 대안 사본(설계서 8-19) — 이 칸만 답과 다름"}
    return a


def alt_cut_turns(cfgf: Path, gid: str) -> list:
    """시험 자리 차례 자르기 파일의 그 판 차례 — (id · 버린 패 · 기록 버림 시각 · 창 첫 · 끝 프레임 ms)."""
    cfg = hcfg.load(cfgf, check=False)
    g = next((x for x in jl(cfg.cut_file)["games"] if x["id"] == gid), None)
    out = []
    for t in (g or {}).get("turns") or []:
        fr = [m for s in t.get("segs") or [] for m in s.get("frames") or []]
        out.append({"id": t["id"], "tile": t.get("tile"), "discard": (t.get("cut") or {}).get("discard"),
                    "w0": fr[0] if fr else None, "w1": fr[-1] if fr else None})
    return out


def alt_compare(base: list, alt: list) -> dict:
    """목록 차이(차례의 (버린 패 · 기록 버림 시각) 순서열 — 더해진 · 빠진 차례) · 창 차이(id 가 같은 차례의 창이 움직인 초 — 문턱 아래도 모두 적고,
    ALT_WIN_S 넘은 차례 목록)."""
    key = lambda t: (norm(t.get("tile")), t.get("discard"))   # noqa: E731
    A, B = [key(t) for t in base], [key(t) for t in alt]
    ma, mb = set(), set()
    for blk in difflib.SequenceMatcher(None, A, B, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            ma.add(blk.a + k)
            mb.add(blk.b + k)
    fmt = lambda t: {"id": t["id"], "tile": t.get("tile"), "discard": t.get("discard")}   # noqa: E731
    removed = [fmt(base[i]) for i in range(len(base)) if i not in ma]
    added = [fmt(alt[i]) for i in range(len(alt)) if i not in mb]
    bi = {t["id"]: t for t in base}
    moves, shifted = {}, []
    for t in alt:
        b = bi.get(t["id"])
        if not b or None in (b["w0"], b["w1"], t["w0"], t["w1"]):
            continue
        d0, d1 = t["w0"] - b["w0"], t["w1"] - b["w1"]
        m = max(abs(d0), abs(d1))
        if m:
            moves[t["id"]] = {"w0_s": round(d0 / 1000, 1), "w1_s": round(d1 / 1000, 1), "max_s": round(m / 1000, 1)}
        if m > ALT_WIN_S * 1000:
            shifted.append(t["id"])
    return {"base_turns": len(base), "alt_turns": len(alt), "added": added, "removed": removed, "moves": moves, "shifted": shifted, "win_s": ALT_WIN_S}


def _alt_job(d: Path, ti: dict, sp: dict, gid: str, ans: dict) -> dict:
    t0 = time.time()
    d.mkdir(parents=True)
    wj(d / "answer.json", ans)
    wj(d / "spec.json", sp)
    T, err, fatal, cfgf = {}, None, None, None
    try:
        cfgf, err, fatal = _try_steps(d, ti, gid, T)
    except Exception as e:  # noqa: BLE001 — 한 자리가 죽어도 나머지는 냄(까닭은 결과에)
        err = f"{type(e).__name__}: {e}"
    T["total"] = round(time.time() - t0, 1)
    o = {"dir": d.as_posix(), "timing": T, "error": err, "fatal": fatal}
    if err or fatal:
        return o
    try:
        app = jl(d / "applied.json")
        o["failed_checks"] = [c["name"] for c in app.get("checks") or [] if not c["ok"]]
        o["t_ready_used"] = (app.get("config") or {}).get("t_ready")
        o["ready_late"] = app.get("ready_late")
        o["turns"] = alt_cut_turns(cfgf, gid)
    except Exception as e:  # noqa: BLE001
        o["error"] = f"적용 결과 · 차례 자르기 파일을 못 읽음 — {type(e).__name__}: {e}"
    return o


def cmd_alt(a):
    """(설계서 8-19 (나)) 대안 돌리기: 답(--answer)의 unsure 줄마다 alt 를 가린 뒤, 돌릴 수 있는 것이 있으면 시험 자리 <out>/0(답 그대로 — 기준) ·
    <out>/<n>(n 번째 unsure 의 what 칸만 alt 로 바꾼 사본)에서 try 와 같은 걸음을 돌려 차례 목록 · 차례 창을 견준다. 꾸러미의 try/ · 실행 폴더 handtrack/ ·
    공용 자리에는 안 쓴다(시험 자리 설정 — try_cfg). 결과 한 파일(--result, 기본 <out>/result.json). 줄마다 status:
    memo(못 돌림 — 까닭) · fail(대안 걸음 실패 · 적용 fatal · 기준에 없던 검사 실패 — 메모) · diff(목록 차이) · window(목록 같음 · 창 차이) · zero(둘 다 없음) ·
    base_fail(기준 alt/0 이 실패 — 영향을 못 잼)."""
    t_all = time.time()
    pack = Path(a.pack).resolve()
    pk = jl(pack / "pack.json")
    ti = pk.get("try")
    if not ti:
        raise SystemExit(f"{pack}/pack.json 에 try 칸이 없다 — 꾸러미를 새 코드로 다시 만들어라(handtrack_prep.py pack --task-only)")
    sp = pk["spec"]
    gid = sp["gid"]
    ans_src = Path(a.answer).resolve()
    raw = ans_src.read_bytes()
    ans = json.loads(raw.decode("utf-8"))
    out = Path(a.out).resolve()
    resf = Path(a.result).resolve() if a.result else out / "result.json"
    if out == pack or out in pack.parents or (pack / "try") in [out, *out.parents]:
        raise SystemExit(f"--out {out} 이 꾸러미 · 꾸러미의 try/ 와 겹친다 — 대안 자리는 따로")
    rows = []
    for n, u in enumerate(ans.get("unsure") or [], 1):
        why = alt_memo(u, sp)
        what = u.get("what") if isinstance(u, dict) else None
        row = {"n": n, "what": what, "alt": u.get("alt") if isinstance(u, dict) else None, "has_alt": isinstance(u, dict) and "alt" in u,
               "why": (u.get("why") if isinstance(u, dict) else str(u)), "answer_value": alt_value_of(ans, what) if isinstance(what, str) else None}
        row.update({"status": "memo", "memo": why} if why else {"status": "run"})
        rows.append(row)
    res = {"_note": "handtrack_prep.py alt — 준비 읽기 unsure 의 alt 대안 돌리기(설계서 8-19 (나))", "gid": gid, "pack": pack.as_posix(),
           "answer": ans_src.as_posix(), "answer_sha": hashlib.sha256(raw).hexdigest(), "out": out.as_posix(), "win_s": ALT_WIN_S,
           "rows": rows, "base": None}
    run_rows = [x for x in rows if x["status"] == "run"]
    if run_rows or a.base_always:
        if out.exists():
            if not (out / ALT_MARK).exists() and any(out.iterdir()):
                raise SystemExit(f"--out {out} 이 alt 가 만든 자리가 아닌데 비어 있지 않다 — 지우지 않고 멈춤")
            shutil.rmtree(out)
        out.mkdir(parents=True)
        wt(out / ALT_MARK, f"handtrack_prep.py alt 자리 — 다시 부르면 지우고 새로 만든다 · 답 {ans_src.as_posix()}\n")
        if ti.get("rec_missing"):
            res["base"] = {"error": f"기록 폴더 {ti['rec_dir']} 에 {ti['rec_missing']} 가 없다", "timing": {}}
            done = {}
        else:
            from concurrent.futures import ThreadPoolExecutor
            jobs = [(0, ans)] + [(x["n"], alt_variant(ans, x["what"], x["alt"])) for x in run_rows]
            with ThreadPoolExecutor(max_workers=min(ALT_PARALLEL, len(jobs))) as ex:
                futs = {n: ex.submit(_alt_job, out / str(n), ti, sp, gid, va) for n, va in jobs}
                done = {n: f.result() for n, f in futs.items()}
            b = done[0]
            res["base"] = {**{k: b.get(k) for k in ("dir", "timing", "error", "fatal", "failed_checks", "t_ready_used", "ready_late")},
                           "turns": b.get("turns")}
        b = res["base"]
        base_bad = b.get("error") or b.get("fatal")
        for x in run_rows:
            j = done.get(x["n"]) or {}
            x.update(dir=j.get("dir"), timing=j.get("timing"), t_ready_used=j.get("t_ready_used"), ready_late=j.get("ready_late"))
            if base_bad:
                x.update(status="base_fail", reason=f"기준 alt/0 실패 — {str(base_bad)[:400]}")
                continue
            if j.get("error") or j.get("fatal"):
                x.update(status="fail", memo=f"대안 걸음 실패 — {str(j.get('fatal') or j.get('error'))[:400]}")
                continue
            newf = [c for c in j.get("failed_checks") or [] if c not in (b.get("failed_checks") or [])]
            if newf:
                x.update(status="fail", memo=f"기준에 없던 검사 실패 {newf} — 덜 그럴듯한 후보가 검사에 걸림")
                continue
            cmp = alt_compare(b.get("turns") or [], j.get("turns") or [])
            x["compare"] = cmp
            x["status"] = "diff" if (cmp["added"] or cmp["removed"]) else ("window" if cmp["shifted"] else "zero")
    else:
        res["note"] = "돌릴 대안 없음(unsure 모두 메모) — 기준도 안 돌림"
    res["counts"] = dict(Counter(x["status"] for x in rows))
    res["wall_s"] = round(time.time() - t_all, 1)
    wj(resf, res)
    view = {k: v for k, v in res.items() if k not in ("rows", "base")}
    view["rows"] = [{k: v for k, v in x.items() if k in ("n", "what", "alt", "status", "memo", "reason")} for x in rows]
    print("JSON" + json.dumps(view, ensure_ascii=False))


def _hms_near(mmss: str, ref_ms: int) -> str:
    """turncut 의 'MM:SS.s' → ref 와 가장 가까운 시의 'HH:MM:SS.s'."""
    h = int(hc.hms(ref_ms)[:2])
    c = [hc.to_ms(f"{x:02d}:{mmss}") for x in (h - 1, h, h + 1) if 0 <= x < 24]
    return hc.hms(min(c, key=lambda m: abs(m - ref_ms)))


def try_report(d: Path, n: int, pk: dict, cfgf: Path, T: dict, err, fatal) -> tuple:
    sp = pk["spec"]
    gid, side = sp["gid"], sp["side"]
    L = [f"# try {n} 보고서 — 판 `{gid}`({sp.get('round_label', '')}) · 손패 주인 = 사진 {SIDE_KO[side]}", "",
         f"- 초안 답: `{(d / 'answer.json').as_posix()}` · 시험 자리 `{d.as_posix()}` · 걸린 시간 {T.get('total')}초"
         f"(적용 · 특징 {T.get('apply', '—')} · 판별 {T.get('run', '—')} · 차례 {round(T.get('turns', 0) + T.get('fix', 0) + T.get('rturns', 0) + T.get('turncut', 0), 1)})",
         f"- 남은 시도: {max(0, MAX_TRIES - n)}번(판당 {MAX_TRIES}번까지)", ""]
    js = {"gid": gid, "n": n, "timing": T, "error": err, "fatal": fatal}
    rl = (jl(d / "applied.json") if (d / "applied.json").exists() else {}).get("ready_late")
    if rl:   # (설계서 8-16) 초안에 늦은 후보가 있음 — 답의 값 · 늦은 후보 · 쓰는 값(판별 · ① · ⑤ 는 쓰는 값 기준)
        L[4:4] = [f"- 줄이 선 때: 답의 t_ready **{rl['answer']}** · 늦은 후보 **{rl['late']}** · 쓰는 값 **{rl['used']}** — {rl['note']}"
                  + (f" {rl.get('not_restored')}(① 에서 't_ready 앞(차례 아님)' 으로 나옴)" if rl.get("which") == "late" else "")
                  + " · 아래 판별 · ① · ⑤ 는 쓰는 값 기준"]
        js["ready_late"] = rl
    if fatal:
        L += ["## 답 꼴 이상 — 판별을 돌리지 않음", "", *[f"- {x}" for x in fatal], "", "시각은 'HH:MM:SS.s', 영역은 [x0, y0, x1, y1] 정수로 고쳐 다시 try."]
        return "\n".join(L) + "\n", js
    if err:
        L += ["## 돌리다 멈춤", "", "```", err, "```", ""]
    cfg = hcfg.load(cfgf, check=False)
    cfg.apply_recording(hc)
    ht = d / "handtrack"
    try:
        cf = jl(ht / "config" / f"{gid}.json")
    except FileNotFoundError:
        L.append("판별 설정이 없다 — 적용 단계에서 멈춤.")
        return "\n".join(L) + "\n", js
    t_ready = hc.to_ms(cf["t_ready"])
    applied = jl(d / "applied.json") if (d / "applied.json").exists() else {}
    sections = [("① 차례 목록 ↔ 기록의 손패 주인 버림", _sec_turns), ("② 활동 구간(손이 움직인 때 · 가만한 때)", _sec_activity),
                ("③ 공개 — 끝 손패 읽기", _sec_reveal), ("④ 적용 검사(apply)", _sec_checks), (f"⑤ 첫 {TRY_TURNS_SHOWN} 차례의 창 — 프레임을 열어 볼 곳", _sec_first)]
    ctx = {"d": d, "sp": sp, "gid": gid, "side": side, "cfg": cfg, "cf": cf, "t_ready": t_ready, "applied": applied, "pk": pk, "rec": bool(cfg.app_record)}
    for title, fn in sections:
        L += ["", f"## {title}", ""]
        try:
            lines, sj = fn(ctx)
            L += lines
            js[title[0]] = sj
        except Exception as e:  # noqa: BLE001 — 한 절이 못 만들어져도 나머지는 냄
            L.append(f"(이 절을 못 만듦 — {type(e).__name__}: {e})")
    head = " · ".join(x for x in (ctx.get("headline"), ctx.get("headline_act"), ctx.get("headline_rev"), ctx.get("headline_chk")) if x)
    if head:
        L[4:4] = ["- **요약:** " + head]
    js["headline"] = head
    return "\n".join(L) + "\n", js


def _called_away(d: Path, gid: str, hero: int) -> set:
    """손패 주인 버림 중 바로 뒤에 남이 울어 가져간 것(몇 번째, 1부터)."""
    ev = jl(d / "prep" / "rec" / gid / "paifu_rec.json")["events"]
    out, k = set(), 0
    for i, e in enumerate(ev):
        if e["type"] == "discard" and e["seat"] == hero:
            k += 1
            nx = ev[i + 1] if i + 1 < len(ev) else None
            if nx and nx["type"] == "call" and nx.get("from") == hero and nx["seat"] != hero:
                out.add(k)
    return out


def _windows(ctx) -> dict:
    cfg, gid = ctx["cfg"], ctx["gid"]
    if not cfg.cut_file.exists():
        return {}
    g = next((x for x in jl(cfg.cut_file)["games"] if x["id"] == gid), None)
    out = {}
    for t in (g or {}).get("turns") or []:
        fr = [m for s in t.get("segs") or [] for m in s["frames"]]
        if not fr:
            continue
        c = t.get("cut") or {}
        out[t["id"]] = {"w0": fr[0], "w1": fr[-1], "discard": _hms_near(c["discard"], fr[0]) if c.get("discard") else None, "by": c.get("by")}
    return out


def _sec_turns(ctx):
    cfg, gid, sp, t_ready, d = ctx["cfg"], ctx["gid"], ctx["sp"], ctx["t_ready"], ctx["d"]
    raw = next((g for g in jl(cfg.turns_file)["games"] if g["id"] == gid), None) if cfg.turns_file.exists() else None
    turns = turns_after_fix(cfg, gid)
    rec = ctx.get("rec")                  # 앱 기록 반장: 차례 목록이 기록에서(han3 rturns) — 강 사진이 읽은 패가 없음
    raw_tile = {} if rec else {t["id"]: t.get("tile") for t in (raw or {}).get("turns") or []}
    W = _windows(ctx)
    ctx["turns"], ctx["W"] = turns, W
    hd = sp.get("hero_discards") or []
    away = _called_away(d, gid, sp["hero"])
    after = [x for x in hd if x.get("at") is not None and x["at"] > t_ready]
    before = [x for x in hd if x.get("at") is not None and x["at"] <= t_ready]
    noat = [x for x in hd if x.get("at") is None]
    A, B = [norm(t.get("tile")) for t in turns], [norm(x["tile"]) for x in after]
    pair = {}
    for blk in difflib.SequenceMatcher(None, A, B, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            pair[blk.a + k] = blk.b + k
    for i in range(len(turns)):          # 앞뒤 짝 사이에 남은 차례 하나 · 기록 버림 하나면 짝(han3 fix 와 같은 규칙 — 패가 다름)
        if i in pair:
            continue
        pa_ = max([m for m in pair if m < i], default=-1)
        pb_ = min([m for m in pair if m > i], default=len(turns))
        lo = pair[pa_] if pa_ >= 0 else -1
        hi = pair[pb_] if pb_ < len(turns) else len(B)
        free = [k for k in range(lo + 1, hi) if k not in pair.values()]
        if len(free) == 1 and pb_ - pa_ == 2:
            pair[i] = free[0]
    rev = {v: k for k, v in pair.items()}
    n_syn = sum(1 for t in turns if t.get("synthetic"))
    missed = [x for k, x in enumerate(after) if k not in rev]
    extra = [turns[i] for i in range(len(turns)) if i not in pair]
    first_i = (raw or {}).get("first_i")
    L = [f"- 기록 = {sp.get('events_title') or '버림 기록'}(TASK.md 의 손패 주인 버림 표와 같은 것)",
         f"- t_ready(적용한 값) = **{hc.hms(t_ready)}** · 판 구간 끝 = t_reveal {ctx['cf']['t_reveal']} + {ctx['cf']['post_sec']}초",
         (f"- 차례 **{len(turns)}**(기록에서 바로 — 강 사진 읽기 없음) · " if rec else
          f"- 차례 **{len(turns)}**(강 사진이 잡은 것 {len(turns) - n_syn} + 강 사진이 못 잡아 기록으로 끼운 것 {n_syn}) · ")
         + f"기록의 손패 주인 버림 {len(hd)}장 = t_ready 앞 {len(before)} + 뒤 **{len(after)}**" + (f" + 시각 모름 {len(noat)}" if noat else ""),
         f"- 기록의 t_ready 뒤 버림 중 차례로 잡힘 {len(after) - len(missed)} · **차례에서 빠짐 {len(missed)}** · **기록에 없는 차례 {len(extra)}**",
         (f"- 첫 차례의 강 번호 {first_i} − 1 = {first_i - 1 if first_i else '—'}(기록에서 셈 — 남이 울어 간 버림은 강에서 빠짐) · " if rec else
          f"- 강 사진이 t_ready 프레임에서 본 이 사람 강 장수 = {first_i - 1 if first_i else '—'}(첫 차례의 강 번호 {first_i} − 1) · ")
         + f"기록의 t_ready 앞 버림 {len(before)}장" + ("" if first_i is None or first_i - 1 == len(before) else " — **다름**"),
         f"- 답의 pre_ready_discards: {[x.get('tile') for x in (ctx['applied'].get('detail') or {}).get('answer_pre_ready') or []]} · "
         f"기록의 t_ready 앞 버림: {[x['tile'] for x in before]}", "",
         "### 차례 목록(코드가 나눈 것)", "",
         "| 차례 | id | 버린 패(기록으로 맞춤) | 강 사진이 읽은 패 | 리치 | 창 시작 ~ 끝 | 강 위 손(버림) | 비고 |", "|---|---|---|---|---|---|---|---|"]
    for i, t in enumerate(turns):
        w = W.get(t["id"]) or {}
        note = []
        if t.get("synthetic"):
            note.append("강 사진이 못 잡아 기록으로 끼움")
        if i not in pair:
            note.append("**기록에 없는 차례**")
        elif after[pair[i]]["n"] in away:
            note.append("남이 울어 가져감")
        if t.get("kind") == "call":
            note.append("이 사람 울기 뒤")
        rt = raw_tile.get(t["id"])
        if rt and i in pair and norm(rt) != norm(after[pair[i]]["tile"]):
            note.append(f"강 사진 {rt} ↔ 기록 {after[pair[i]]['tile']}")
        L.append(f"| {i + 1} | {t['id']} | {t.get('tile')} | {rt if rt else '—'} | {'예' if t.get('sideways') else ''} | "
                 f"{(hc.hms(w['w0']) + ' ~ ' + hc.hms(w['w1'])) if w else '—'} | {w.get('discard') or '—'} | {' · '.join(note)} |")
    if not turns:
        L.append("| — | — | — | — | — | — | — | **차례 0** |")
    L += ["", "### 기록의 손패 주인 버림(차례가 되는지)", "", "| 몇 번째 | 패 | 기록기가 처음 본 때 | 리치 | 상태 |", "|---|---|---|---|---|"]
    k_after = {id(x): k for k, x in enumerate(after)}
    for x in hd:
        near = x.get("at") is not None and abs(x["at"] - t_ready) <= TRY_NEAR_MS
        if x.get("at") is None:
            st = "시각 모름"
        elif x["at"] <= t_ready:
            st = "t_ready 앞(차례 아님)"
        else:
            k = k_after[id(x)]
            if k in rev:
                t = turns[rev[k]]
                st = f"차례 {rev[k] + 1}({t['id']})" + (" — 강 사진은 못 잡고 기록으로 끼움" if t.get("synthetic") else "")
            else:
                st = "**차례에서 빠짐**"
        if near:
            st += f" · t_ready 와 {TRY_NEAR_MS // 1000}초 안(기록기는 약 3초 늦게 볼 수 있음)"
        if x["n"] in away:
            st += " · 남이 울어 가져감(강에 안 남음)"
        L.append(f"| {x['n']} | {x['tile']} | {hc.hms(x['at']) if x.get('at') else '—'} | {'예' if x.get('riichi') else ''} | {st} |")
    same = len(turns) == len(after) and not missed and not extra
    ctx["headline"] = (f"차례 {len(turns)} · 기록(t_ready 뒤) {len(after)} — {'같음' if same else '다름'}"
                       + (f" · 빠짐 {len(missed)}" if missed else "") + (f" · 기록에 없는 차례 {len(extra)}" if extra else "")
                       + (f" · 끼움 {n_syn}" if n_syn else ""))
    return L, {"turns": len(turns), "synthetic": n_syn, "record_after": len(after), "record_before": len(before), "no_at": len(noat),
               "missed": [f"{x['n']}:{x['tile']}" for x in missed], "extra": [t["id"] for t in extra], "same_count": same, "first_i": first_i,
               "turn_tiles": [t.get("tile") for t in turns], "record_tiles": [x["tile"] for x in after]}


def _sec_activity(ctx):
    import segment as sgm
    d, gid, t_ready = ctx["d"], ctx["gid"], ctx["t_ready"]
    seg = jl(d / "handtrack" / gid / "segments.json")
    A, S, P = seg["active"], seg["still"], seg["params"]
    t_end = hc.to_ms(P["t_end"])
    span = (t_end - t_ready) / 1000
    nf = P["frames"]
    act_n = sum(a["n"] for a in A)
    lg = max(A, key=lambda a: a["dur"]) if A else None
    z = np.load(d / "handtrack" / "_work" / f"{gid}_feat.npz")
    ms = z["ms"]
    k = (ms >= t_ready) & (ms <= t_end)
    d1, d3, sk = z["band_d1"][k], z["band_d3"][k], z["band_skin"][k]
    rd, rs = z["river_d1"][k], z["river_skin"][k]
    bdiff = (d1 > sgm.ACT_DIFF) | (d3 > sgm.ACT_DIFF)
    bskin = sk > sgm.ACT_SKIN
    rdiff, rskin = rd > sgm.RIVER_DIFF, rs > sgm.RIVER_SKIN
    m = max(1, int(k.sum()))

    def pct(x, base=None):
        b = m if base is None else max(1, int(base.sum()))
        return round(100 * float(x.sum()) / b, 1)
    q_b, q_r = ~bdiff, ~rdiff
    skin_still = pct(bskin & q_b, q_b)
    river_still = pct(rskin & q_r, q_r)
    glued = bool(lg and lg["dur"] >= TRY_GLUED * span)
    L = [f"- 판 구간 {hc.hms(t_ready)} ~ {P['t_end']}({round(span, 1)}초 · 프레임 {nf}장) · 활동 구간 **{len(A)}** · 가만한 구간 {len(S)}",
         f"- 가장 긴 활동 구간 **{lg['dur'] if lg else 0}초**" + (f"({lg['t0']} ~ {lg['t1']}, 판 구간의 {round(100 * lg['dur'] / span)}%)" if lg else "")
         + (" — **판이 한 덩어리로 붙음**" if glued else ""),
         f"- 판 구간에서 '움직임' 프레임 비율 **{round(100 * act_n / max(1, nf), 1)}%**(활동 구간 프레임 {act_n}/{nf})",
         f"- 까닭별(프레임 비율, 겹침 있음): band 화소 바뀜 {pct(bdiff)}% · band 피부색 > {sgm.ACT_SKIN * 100:g}% {pct(bskin)}% · "
         f"river 화소 바뀜 {pct(rdiff)}% · river 피부색 > {sgm.RIVER_SKIN * 100:g}% {pct(rskin)}%",
         f"- **band 화소가 안 바뀐 프레임 중 band 피부색이 문턱을 넘는 비율 {skin_still}%** "
         f"(안 바뀐 프레임 {int(q_b.sum())}장 — 크면 band 에 가만한 피부색 물체 · 쉬는 손) · river 화소가 안 바뀐 프레임 중 river 피부색 비율 {river_still}%",
         f"- band 피부색 중앙값(판 구간) {round(float(np.median(sk)) * 100, 2)}% · river 피부색 중앙값 {round(float(np.median(rs)) * 100, 2)}%", "",
         "긴 활동 구간(길이 순 위 5):", "", "| 구간 | 시작 ~ 끝 | 길이(초) | 띠 움직임 프레임 | 강 움직임 프레임 | 띠 피부 최대 |", "|---|---|---|---|---|---|"]
    for a in sorted(A, key=lambda a: -a["dur"])[:5]:
        L.append(f"| {a['seg']} | {a['t0']} ~ {a['t1']} | {a['dur']} | {a['band_frames']} | {a['river_frames']} | {a['max_skin']} |")
    ctx["headline_act"] = f"활동 구간 {len(A)} · 가장 긴 {lg['dur'] if lg else 0}초"
    return L, {"active": len(A), "still": len(S), "span_s": round(span, 1), "longest_s": lg["dur"] if lg else 0, "longest": [lg["t0"], lg["t1"]] if lg else None,
               "active_frac": round(act_n / max(1, nf), 3), "glued": glued, "band_skin_when_still_pct": skin_still, "river_skin_when_still_pct": river_still}


def _sec_reveal(ctx):
    d, gid, sp, pk = ctx["d"], ctx["gid"], ctx["sp"], ctx["pk"]
    if not (d / "handtrack" / gid / "game.json").exists() and "reveal_region" not in ctx["cf"]:
        ctx["headline_rev"] = "공개 읽기 안 함"
        return ["- 공개 프레임 읽기를 안 했다 — reveal_region 이 없다(기본 길 모드: 끝 손패 순서는 판 결과 값, 설계서 8-13 (다))."], None
    g = jl(d / "handtrack" / gid / "game.json")
    f = g.get("final_hand") or {}
    closed, det = list(f.get("closed") or []), list(f.get("detached") or [])
    want = sp["n_closed_end"]
    win = sp["end"] == "win"
    tsumo = sp.get("win_type") == "tsumo"
    L = [f"- reveal_frame(적용한 값) {ctx['cf']['reveal_frame']} · 다수결에 쓴 프레임 {len(f.get('frames_voted') or [])}장({f.get('frame_time')} 둘레)",
         f"- 읽은 끝 손패 줄 **{len(closed)}장** {closed} · 기대 닫힌 장수 **{want}**" + ("" if len(closed) == want else " — **다름**"),
         f"- 떼어 둔 패 {len(det)}장 {[x.get('tile') for x in det]}" + (f" · 기대: 쯔모라 떼어 둔 화료패 1장" if win and tsumo else
                                                                    (" · 기대: 론이라 0장(론 패는 방총자 강)" if win else " · 기대: 유국이라 0장")),
         f"- 줄 밖 그 밖의 앞면 패(reveal_region 안) {len(f.get('other_in_region') or [])}장 · 울기 자리에서 읽은 패 {len(f.get('melds') or [])}장(기대 {3 * sp.get('n_calls', 0)}장 안팎 — 깡은 4장)"]
    rrp = (pk.get("try") or {}).get("result_read")
    cmp = None
    if rrp and Path(rrp).exists():
        rr = jl(rrp)
        hand = list(rr.get("hand") or [])
        if hand:
            a, b = Counter(map(norm, closed)), Counter(map(norm, hand))
            only_r, only_h = sorted((a - b).elements()), sorted((b - a).elements())
            same = not only_r and not only_h
            order = [norm(x) for x in closed] == [norm(x) for x in hand]
            L.append(f"- 판 결과(앞 단계 판 결과 읽기)의 끝 손패 {len(hand)}장과 패 종류: **{'같음' if same else '다름'}**"
                     + ("" if same else f" — 읽은 쪽에만 {only_r} · 판 결과에만 {only_h}") + (f" · 순서도 같음" if same and order else (" · 순서는 다름" if same else "")))
            if win and tsumo:
                wt_ = rr.get("win_tile")
                L.append(f"- 화료패: 읽은 떼어 둔 패 {[x.get('tile') for x in det]} · 판 결과 {wt_} — "
                         + ("같음" if wt_ and [norm(x.get("tile")) for x in det] == [norm(wt_)] else "**다름**"))
            cmp = {"same_kinds": same, "same_order": order, "only_read": only_r, "only_result": only_h}
        else:
            L.append("- 판 결과에 끝 손패가 없다(견주지 않음)")
    else:
        L.append("- 판 결과 파일 없음(견주지 않음)")
    ctx["headline_rev"] = f"끝 손패 {len(closed)}/{want}장" + ("" if cmp is None else (" · 판 결과와 같음" if cmp["same_kinds"] else " · 판 결과와 다름"))
    return L, {"closed": len(closed), "want": want, "detached": len(det), "result_cmp": cmp}


def _sec_checks(ctx):
    o = ctx["applied"]
    if not o:
        return ["(적용 결과 없음)"], None
    L = [f"- 고친 영역(녹화 틀 값과 다른 것): {o.get('changed_regions') or '없음'}",
         f"- t_ready 뒤 손패 주인 버림(기록) {o.get('hero_discards_after_ready')} · 앞 {o.get('hero_discards_before_ready')}", "",
         "| 검사 | 결과 | 내용 |", "|---|---|---|"]
    for c in o.get("checks") or []:
        L.append(f"| {c['name']} | {'통과' if c['ok'] else '**실패**'} | {c['detail']} |")
    bad = [c["name"] for c in o.get("checks") or [] if not c["ok"]]
    if o.get("unsure"):
        L += ["", f"- 답의 unsure {len(o['unsure'])}개(흐름에서는 코드가 `alt` 값으로 한 번 더 돌려 차례 목록 · 차례 창이 바뀌는 것만 사용자에게 묻는다 — "
                  "`alt` 가 없거나 값으로 못 쓰면 보고서에 메모로만 남는다)"]
    ctx["headline_chk"] = f"검사 실패 {bad}" if bad else "검사 모두 통과"
    return L, {"failed": bad}


def _sec_first(ctx):
    turns, W, t_ready, d = ctx.get("turns") or [], ctx.get("W") or {}, ctx["t_ready"], ctx["d"]
    first = [t for t in turns if t["id"] in W][:TRY_TURNS_SHOWN]
    if not first:
        return ["(차례 창 없음)"], None
    t1 = W[first[-1]["id"]]["w1"]
    lab = {}
    for t in first:
        for m in hc.frame_range(W[t["id"]]["w0"], W[t["id"]]["w1"]):
            lab.setdefault(m, t["id"])
    fr = hc.frame_range(t_ready, t1)
    wt(d / "frames_turns.txt", "".join(f"{hc.hms(m)}\t{hc.path_of(m).as_posix()}\t{lab.get(m, '가만(차례 창 밖)')}\n" for m in fr))
    # 차례 창마다 band 화소가 바뀐 시간(초) — 정리 동작이 섞인 창은 보통 차례보다 길다(참고 숫자일 뿐, 프레임으로 확인)
    import segment as sgm
    z = np.load(d / "handtrack" / "_work" / f"{ctx['gid']}_feat.npz")
    zms, bact = z["ms"], (z["band_d1"] > sgm.ACT_DIFF) | (z["band_d3"] > sgm.ACT_DIFF)

    def moved(w):
        k = (zms >= w["w0"]) & (zms <= w["w1"])
        return round(float(bact[k].sum()) / 10, 1)
    rest = [moved(W[t["id"]]) for t in turns if t["id"] in W and t not in first]
    med = round(float(np.median(rest)), 1) if rest else None
    L = [f"- 프레임 목록 `{(d / 'frames_turns.txt').as_posix()}` — t_ready {hc.hms(t_ready)} ~ {len(first)}번째 차례 창 끝 {hc.hms(t1)}, {len(fr)}장"
         " (한 줄 = `HH:MM:SS.s<탭>원본 프레임 경로<탭>차례 id 또는 '가만'`)",
         "- 이 창들을 열어 정리 동작(두 장 넘게 자리를 바꿈)이 섞였는지, 첫 차례가 뽑기 → 버림 하나인지 본다. ①이 기록과 같아도 t_ready 가 이르면 그렇게 나올 수 있다.",
         f"- 'band 움직임' = 창 안에서 band 화소가 바뀐 프레임 수 ÷ 10(초). 나머지 차례의 중앙값 {med if med is not None else '—'}초 — 훨씬 길면 그 창을 먼저 본다(참고 숫자).", "",
         "| 차례 | id | 버린 패 | 창 시작 ~ 끝 | 강 위 손(버림) | 창 프레임 수 | band 움직임(초) |", "|---|---|---|---|---|---|---|"]
    mv = []
    for i, t in enumerate(first):
        w = W[t["id"]]
        mv.append(moved(w))
        L.append(f"| {i + 1} | {t['id']} | {t.get('tile')} | {hc.hms(w['w0'])} ~ {hc.hms(w['w1'])} | {w.get('discard') or '—'} | "
                 f"{len(hc.frame_range(w['w0'], w['w1']))} | {mv[-1]} |")
    return L, [{"id": t["id"], "w0": hc.hms(W[t["id"]]["w0"]), "w1": hc.hms(W[t["id"]]["w1"])} for t in first]


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("pack")
    p.add_argument("--cfg", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--task-only", action="store_true", help="TASK.md · 프레임 목록 · pack.json 만 다시(그림 · 검출기 표는 그대로 — 읽기 전에 지시문 글만 바꿨을 때)")
    p.add_argument("--rec", help="try 가 쓸 기록 폴더(기본 <prep_dir>/rec/<판>)")
    p.add_argument("--result-read", help="try 보고서 ③ 이 견줄 판 결과(기본 <results_dir>/<판>/result_read.json)")
    p = sp.add_parser("apply")
    p.add_argument("--cfg", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--out", required=True)
    p = sp.add_parser("try", help="읽기 에이전트가 부름: 초안 답으로 이 판 판별 · 차례 나누기를 꾸러미 안 시험 자리에서 돌리고 보고서")
    p.add_argument("--pack", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--n", type=int, help="시도 번호(기본: 다음 빈 번호)")
    p.add_argument("--force", action="store_true", help=f"시험용: 한도 {MAX_TRIES}번을 넘겨도 돌림")
    p = sp.add_parser("bandcand", help="(설계서 8-13 (나)) 손패 줄 후보를 화면 절반에서 — S6a 기본 길 모드가 부름")
    p.add_argument("--cfg", required=True)
    p.add_argument("--side", required=True, choices=SIDES)
    p.add_argument("--t0", required=True, help="판 구간 시작(HH:MM:SS.s 또는 epoch ms)")
    p.add_argument("--t1", required=True)
    p.add_argument("--n", type=int, default=CAND_FRAMES)
    p.add_argument("--out", required=True)
    p = sp.add_parser("alt", help="(설계서 8-19 (나)) 답의 unsure alt 로 한 번 더 돌려 차례 목록 · 창을 기준과 견줌 — S6a-3 이 부름(LLM 0)")
    p.add_argument("--pack", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--out", required=True, help="대안 시험 자리 폴더(<out>/0 = 기준 · <out>/<n> = n 번째 unsure 대안)")
    p.add_argument("--result", help="결과 json(기본 <out>/result.json)")
    p.add_argument("--base-always", action="store_true", help="시험용: 돌릴 대안이 없어도 기준 <out>/0 을 돌림")
    a = ap.parse_args()
    {"pack": cmd_pack, "apply": cmd_apply, "try": cmd_try, "bandcand": cmd_bandcand, "alt": cmd_alt}[a.cmd](a)


if __name__ == "__main__":
    main()
