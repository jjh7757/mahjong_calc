"""검출 상자 + 다중 객체 추적기만으로 손패 번호 따라가기 — SAM 없이, 초당 5장 대 10장(2026-11-20, 계획서 3단계 "추가 55").

사용자가 붙인 조언 "검출 + 다중 객체 추적(ByteTrack 등)으로 고정 track_id · 손 가림 보류 · 거리 문턱 · 30fps" → "재 보기".
규칙 · 문턱값은 돌리기 전에 계획서(docs/paifu_review_plan_1113.md "추가 55")에 적은 것 그대로 — 결과를 보고 바꾸지 않는다. API 0달러.

  python -X utf8 mottrack.py detect [--ids a,b]                        # 차례 a_ms ~ e_ms 원본 초당 10장 전부 검출 → _work/mottrack_1120/det10_<판>.json
  python -X utf8 mottrack.py cmpold [--ids a,b]                        # 새 캐시의 5장 프레임 상자 · 가림 열 ↔ 옛 slotgrid_1117/det_<판>.json(읽기만) 일치 세기
  python -X utf8 mottrack.py run [--ids a,b] [--arm b0|b1|all] [--fps 5|10|all]   # 정답 안 읽음 → _work/mottrack_1120/<팔>_<장수>/<id>.json
  python -X utf8 mottrack.py score [--ids a,b]                         # 정답과 맞대 채점 → _work/mottrack_1120/score.json (검토자가 한 번만 돌림)
  python -X utf8 mottrack.py selftest                                  # 합성 차례 4개 × 팔 2 × 장수 2(정답 파일 안 읽음)

재료: 대상 = idsolve.targets()(저장된 v1 SAM 2 추적 track.json 이 있는 56차례). 차례의 a_ms · e_ms · a_boxes · e_boxes(넓힌 띠 band2 시점
[x0, y0, x1, y1])는 track.json 의 plan 그대로. 검출 = 운영 뒷면 검출기(dettrack.reader() 의 LocalReader, 자리 판독 회전 상자 모델)를
a_ms ~ e_ms 의 원본 초당 10장 전부에 — 새 캐시 det10_<판>.json {"<ms>": {"b": [[x0, x1, y0, y1, 점수], …], "o": [[a, b], …]}}
(sheet_band 시점, 거르기 · 시점 변환은 dettrack.boxes_view 와 같음, 가림 열 "o" = slotgrid.occ_cols). 옛 캐시 slotgrid_1117/det_<판>.json 은 쓰지 않는다.
  점수: LocalReader._seat_raw 가 내는 backs 의 둘째 값은 회전 상자((cx, cy), (w, h), 각도)라 점수가 아니다. 그래서 _seat_raw 와 같은 계산
  (local_read._letterbox → 자리 판독 세션 → obb.decode(…, cls=1))을 여기서 다시 하되 obb.decode 의 scores 인자로 점수를 받는다
  (obb.decode 설명: "scores 를 주면 {축 상자: 검출 점수} 를 채운다, 답은 그대로"). 판마다 첫 프레임에서 dettrack.boxes_view 와 상자가 같은지 확인한다.
프레임: 5장 팔 = track.json["frames"](idsolve 가 쓴 그 프레임), 10장 팔 = 녹화 프레임 중 a_ms ~ e_ms 전부(끝 = e_ms). 둘 다 새 캐시에서 읽는다.
좌표: 검출 상자 → sam2track.remap_box(b, band, band2, side) 로 band2 시점. 가림 열 x 는 idsolve.Turn 과 같은 평행 이동 ox
  (= 그 팔 프레임 중 상자가 있는 첫 프레임의 첫 상자 b0 에 대해 remap_box(b0)[0] − b0[0], 새 캐시 기준). 장폭 = a_boxes 가운데 x 간격 중앙값.
  띠 안 검출 상자 전부를 추적기에 넣는다(줄 높이로 거르지 않음).

번호 · 판정(두 팔 같음, 정답 안 씀):
  첫 프레임(a_ms): a_boxes 각각과 IoU ≥ IOU_LABEL 인 트랙(가장 큰 IoU) → 왼쪽부터 1 ~ n. 하나라도 못 붙이거나 한 트랙이 두 상자에 붙으면 "못 정함".
    그 밖의 트랙은 추적기 번호 그대로 "x<번호>".
  끝 프레임(e_ms): e_boxes 를 가운데 x 순으로, 상자마다 그 프레임에서 IoU ≥ IOU_LABEL 로 그 상자를 잡은 트랙(가장 큰 IoU)의 이름(없으면 None).
    ① 같은 이름이 두 상자 → 못 정함 ② 끝 줄 이름이 정확히 1 ~ n 전부 → tsumogiri
    ③ 1 ~ n 중 정확히 하나(k)가 없고 끝 상자 중 정확히 하나가 1 ~ n 밖(x… 또는 None) → hand, k = 없는 번호, j = 그 상자의 왼쪽부터 순서(1부터)
    ④ 그 밖 → 못 정함(kind None) + 사유.
  "잡은" 상자 = B0 은 추적기가 그 프레임에 낸 (상자, track id)(칼만 갱신 상자), B1 은 그 프레임에 짝지은 검출 상자.

팔 B0 — ByteTrack 그대로: ultralytics(8.4.183) trackers.byte_tracker.BYTETracker + 설치된 cfg/trackers/bytetrack.yaml 값 그대로. 가림 열 안 씀.
  ★ 이 판의 BYTETracker 는 frame_rate 인자가 없다(__init__(args) · max_frames_lost = track_buffer). 계획서 "frame_rate 만 5 / 10(잃은 번호 보관이
    두 팔 모두 1초)" 를 글자대로 지키려고, 옛 ByteTrack 의 frame_rate 계산 max_time_lost = int(frame_rate / 30 × track_buffer) 를 만든 뒤 넣는다
    (5장 → 5프레임, 10장 → 10프레임 = 1초). cfg 값 자체는 안 바꾼다.
  ★ lap 이 없다 → matching.py 가 import 때 lap 자동 설치를 부른다. YOLO_AUTOINSTALL=false 로 설치를 끄고(그래도 import lap 이 실패),
    빈 lap 모듈을 sys.modules 에 끼워 import 만 통과시킨 뒤 matching.linear_assignment 를 use_lap=False(ultralytics.utils.ops.linear_sum_assignment
    = scipy) 로 부르게 바꾼다. 차이: lap.lapjv(cost_limit=thresh) 는 문턱을 넘는 짝을 처음부터 안 고르고 최적화하지만, scipy 길은 전체 최적 뒤
    문턱 넘는 짝을 버린다(짝 수가 드물게 더 적을 수 있음).
팔 B1 — 조언의 팁(직접 구현, 칼만 · 속도 예측 없음 — 마지막 본 자리 기준):
  보류: 트랙의 마지막 상자 가로 범위 중 그 프레임 가림 열에 걸린 몫 ≥ OCC_FRAC 이면 그 프레임 그 트랙은 보류(좌표 안 고침 · 짝짓기에서 뺌 ·
    잃은 시간 안 셈). 검출 상자도 가로의 ≥ OCC_FRAC 가 가림 열에 걸리면 그 프레임엔 안 씀.
  1단계: 보류 아님 + 직전 프레임에 보였던(active) 트랙 ↔ 쓸 수 있는 검출, 가운데 유클리드 거리 / 장폭 헝가리안, GATE 장폭 넘는 짝 금지.
  2단계: 방금 보류가 풀린 트랙 + 잃은(lost) 트랙 ↔ 남은 검출, 같은 거리 헝가리안, REMATCH 장폭 안. 1단계에서 짝 못 찾은 active 는 lost 가 되어
    같은 프레임 2단계에 낀다. 2단계에서도 못 찾은 "방금 풀린" 트랙도 lost. lost 는 보류 시간을 뺀 잃은 시간이 LOST_MS 를 넘으면 지운다.
  3단계: 남은 (쓸 수 있는) 검출 = 새 트랙(새 번호). 끝 프레임(e_ms)은 가림을 안 따짐(보류 없음 · 모든 검출 사용).
  첫 프레임도 가림 규칙을 그대로 따른다(계획서가 끝 프레임만 뺌).
팔 B0z · B1z — 잃은 번호 바로 지움(계획서 "채점 전 덧붙임 2", 사용자 "사라진 번호는 바로 지우는 방식은 어떠니"):
  B0z = B0 와 모두 같고 max_frames_lost = 0 만. ★ 설치된 판에서는 0 이어도 잃은 트랙이 "다음 프레임" 짝짓기 풀에는 한 번 들어간다
    (그 프레임 끝 merge 때 lost_stracks 에 붙고, _remove_stale_lost 는 다음 프레임 짝짓기 뒤에 돈다) — 그다음 프레임에도 못 찾으면 지워짐.
  B1z = B1 과 모두 같고 LOST_MS = 0 만(잃은 번호를 다음 프레임 짝짓기 전에 지움). 손 가림 보류 · 같은 프레임 2단계는 그대로. 값은 인자로 넘김(ARM_SPEC).
합친 팔 F0 · F1 · FX(계획서 "채점 전 덧붙임 3") = (출력 1 바로 지움, 출력 2 보관) = (b0z, b0) · (b1z, b1) · (b0z, b1). 추적은 다시 안 돌리고
  두 재료 팔 저장 결과의 end_order 만 씀: 상자마다 출력 1 이름이 원래 번호(1 ~ n)면 그것, 아니면 출력 2 이름(그대로). 한쪽 end_order 가 없으면(첫 프레임
  번호 붙이기 실패) 다른 쪽만, 둘 다 없거나 길이가 다르면 못 정함. 원래 번호가 두 상자면 못 정함(x… 겹침은 안 봄), 그 밖은 재료 팔과 같은 끝 줄 판정
  (judge_order 공유). 곁들여 conflicts(두 출력이 같은 상자에 다른 원래 번호) · from1 · from2 를 적음.
팔 g(계획서 "추가 56" — 근거 맞추기, 초당 5장만): 가설 = 쯔모기리 + hand(k, j) 1 + n² 개(끝 줄 = k 뺀 1 ~ n 순서 그대로 + j 번째 D).
  굳은 근거(출력 1 = b0z 를 다시 돌린 프레임별 트랙): 끝 상자 s 를 잡은 트랙이 원래 번호 o → 가설 s 번째 = o. 새 번호이고 처음 나온 프레임 상자 →
  끝 상자 가운데 x 이동이 −1 ± SLIDE_TOL 장폭이면 s 번째 = D 또는 s + 1, +1 ± SLIDE_TOL 이면 D 또는 s − 1. 어기는 가설은 버림(다 버려지면 "근거 모순").
  무른 근거(출력 2 = b1 저장 end_order): 원래 번호 상자마다 가설과 같으면 +1, 다르면 −1. 최고 − G_MARGIN 초과 = 동점 묶음, 종류 · k · j 를 성분별로 확신.
  채점은 성분별(both = 모두 확신하고 맞음 · silent_wrong = 확신한 성분 중 틀림 · 그 밖 못 정함).
차례 묶음 --set dev(56, 기본) | new23(안 본 23차례, SAM 2 track.json 없음 → sam2track.plan + frame_list(p, 2), 10장 팔 없음).
  detect --fps 5 = 차례의 5장 프레임만 새 캐시에 더함. score --set new23 → score_new23.json(dev 만 score.json).

채점(score 만 정답을 읽음): idsolve.grade 그대로(hand = k 와 j 둘 다, 쯔모기리 = 종류). 팔 × 장수 네 칸마다 all · hand · tsumogiri · three 묶음의
  n · both · k · j · undecided(kind None) · silent_wrong(kind 를 정했는데 both 아님). idsolve_1120/score.json 이 있으면 그 숫자도 나란히.
기준(계획서): "10장이 보탬" = 같은 팔에서 hand both 가 5장보다 3 이상 많고 조용한 틀림이 안 늚. "검출 + 추적기만으로 idsolve 만큼" = hand both ≥ 13 · 조용한 틀림 ≤ 6.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import types
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import idsolve as ids_  # noqa: E402
import sam2track as s1  # noqa: E402

OUT = hc.WORK / "mottrack_1120"
V1 = ids_.V1

# 두 팔 공통
IOU_LABEL = 0.5     # 첫 · 끝 프레임에서 a_boxes · e_boxes 에 트랙을 붙이는 IoU 하한
# 팔 B1
OCC_FRAC = 0.5      # 상자 가로 중 가림 열에 걸린 몫이 이 이상이면 보류(트랙) · 안 씀(검출)
GATE = 0.6          # 1단계 짝 거리 한도(장폭)
REMATCH = 1.5       # 2단계 짝 거리 한도(장폭)
LOST_MS = 3000      # 잃은 트랙을 지우는 시간(보류 시간 뺌, ms)
# 팔 B0
B0_REF_FPS = 30.0   # 옛 ByteTrack: max_time_lost = int(frame_rate / 30.0 * track_buffer)

ARMS = ("b0", "b1", "b0z", "b1z")
FPSS = (5, 10)
# 팔 → (추적기, 덮어쓸 값). None = 기본(B0: int(fps / 30 × track_buffer), B1: LOST_MS). 채점 전 덧붙임 2: 잃은 번호 바로 지움.
ARM_SPEC = {"b0": ("b0", None), "b1": ("b1", None), "b0z": ("b0", 0), "b1z": ("b1", 0)}
# 합친 팔(채점 전 덧붙임 3) → (출력 1 = 바로 지움, 출력 2 = 보관)
FUSED = {"f0": ("b0z", "b0"), "f1": ("b1z", "b1"), "fx": ("b0z", "b1")}
ALL_ARMS = ARMS + tuple(FUSED)
THREE = ("r16_d03", "r16_d13", "r17_d11")
# 팔 g(추가 56 — 근거 맞추기, 초당 5장만)
G_ARM, G_FPS = "g", 5
SLIDE_TOL = 0.3     # 새 번호 트랙이 태어난 자리 → 끝 상자 가로 이동이 ±1 장폭에서 이만큼 안이면 "한 칸 밀림"
G_MARGIN = 2        # 최고 점수에서 이 미만으로 뒤진 가설 = 동점 묶음
G_TOP_MAX = 30      # 결과에 적는 동점 묶음 최대 수
# 차례 묶음(추가 56): dev = idsolve.targets()(SAM 2 track.json 있는 56차례), new23 = 안 본 23차례(track.json 없음 — sam2track.plan 으로 틀)
NEW23 = ("r15_d11", "r15_d12", "r15_d13", "r15_d14", "r15_d15", "r15_d16", "r15_d17",
         "L16_d03", "L16_d04", "L16_d05", "L16_d06", "L16_d07", "L16_d08", "L16_d09", "L16_d10", "L16_d11", "L16_d12", "L16_d13",
         "L16_d14", "L16_d15", "L16_d16", "L16_d17", "L16_d18")
SETS = ("dev", "new23")


# ------------------------------------------------------------------ 작은 도구
def cx(b) -> float:
    return (b[0] + b[2]) / 2


def cy(b) -> float:
    return (b[1] + b[3]) / 2


def iou(a, b) -> float:
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def occ_frac(x0: float, x1: float, ivs: list) -> float:
    """가로 범위 [x0, x1] 중 가림 열에 걸린 몫(idsolve.iv_overlap 과 같은 셈)."""
    return ids_.iv_overlap(x0, x1, ivs)


def save_atomic(p: Path, obj):
    tmp = p.with_name(p.name + ".tmp")
    hc.jsave(tmp, obj, indent=None)
    os.replace(tmp, p)


def all_targets(a) -> list:
    if getattr(a, "ids", None):
        return a.ids.split(",")
    return list(NEW23) if getattr(a, "set", "dev") == "new23" else ids_.targets()


class NoTen(Exception):
    """SAM 2 track.json 이 없는 새 차례의 10장 팔 — 지원 안 함."""


_TF: dict = {}


def turn_frame(tid: str) -> dict:
    """차례 틀: {"plan", "frames"(5장), "has_track"}. track.json 이 있으면 그대로, 없으면 sam2track.plan + frame_list(p, 2)(추가 56)."""
    if tid not in _TF:
        f = s1.run_dir(tid, V1) / "track.json"
        if f.exists():
            tr = hc.jload(f)
            _TF[tid] = {"plan": tr["plan"], "frames": [int(x) for x in tr["frames"]], "has_track": True}
        else:
            p = s1.plan(tid)
            if not p.get("ok"):
                raise SystemExit(f"{tid}: sam2track.plan 실패 — {p.get('why')}")
            _TF[tid] = {"plan": p, "frames": [int(x) for x in s1.frame_list(p, 2)], "has_track": False}
    return _TF[tid]


def frames10(p: dict) -> list:
    return [int(x) for x in hc.frames(hc.rec_of(p["a_ms"])) if p["a_ms"] <= x <= p["e_ms"]]


# ------------------------------------------------------------------ detect
def boxes_conf(L, rgb, cfg) -> list:
    """dettrack.boxes_view 와 같은 상자(뒷면 · sheet_band 안 · 대국자 시점 [x0, x1, y0, y1]) + 검출 점수를 5번째 값으로.
    _seat_raw 의 backs 는 (축 상자, 회전 상자) 라 점수가 없다 → 같은 계산을 다시 하며 obb.decode 의 scores 로 점수를 받는다."""
    from app import obb
    from app.local_read import _letterbox
    L._sessions()
    x, r, left, top = _letterbox(rgb)
    sess = L._seat
    out = L._run(lambda: sess.run(None, {sess.get_inputs()[0].name: x})[0][0])
    H, W = rgb.shape[:2]
    sc: dict = {}
    backs = obb.decode(out, r, left, top, W, H, cls=1, scores=sc) if out.shape[0] >= 7 else []
    x0b, y0b, x1b, y1b = cfg["sheet_band"]
    res = []
    for (bx, by, bw, bh), _rc in backs:
        ccx, ccy = bx + bw / 2, by + bh / 2
        if not (x0b <= ccx <= x1b and y0b <= ccy <= y1b):
            continue
        p = [hc.to_view_xy(q, cfg["sheet_band"], cfg["side"]) for q in ((bx, by), (bx + bw, by + bh))]
        xs, ys = [a for a, _ in p], [b for _, b in p]
        res.append([round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1), float(sc.get((bx, by, bw, bh), 1.0))])
    return sorted(res, key=lambda b: b[:4])


def det_path(gid: str) -> Path:
    return OUT / f"det10_{gid}.json"


def cmd_detect(a):
    import dettrack as dt
    import pixtrack as pt
    import slotgrid as sg
    L = dt.reader()
    OUT.mkdir(parents=True, exist_ok=True)
    want: dict = {}
    for tid in all_targets(a):
        tf = turn_frame(tid)
        p = tf["plan"]   # --fps 5: 그 차례의 5장 프레임만(추가 56), 없으면 지금처럼 10장 전부
        want.setdefault(p["gid"], set()).update(tf["frames"] if getattr(a, "fps", None) == "5" else frames10(p))
    for gid, mss in want.items():
        assert det_path(gid).parent == OUT and "slotgrid_1117" not in str(det_path(gid))
        cfg, R = hc.config(gid), pt.Row(gid)
        f = det_path(gid)
        cache = hc.jload(f) if f.exists() else {}
        todo = sorted(mss - {int(k) for k in cache})
        t0 = time.time()
        for i, ms in enumerate(todo):
            rgb = hc.load(ms)
            b = boxes_conf(L, rgb, cfg)
            if i == 0:   # 판마다 한 번: 운영 계산(dettrack.boxes_view)과 상자가 같은지
                ref = dt.boxes_view(L, rgb, cfg)
                if [x[:4] for x in b] != ref:
                    raise SystemExit(f"{gid} {ms}: 점수 붙인 상자가 dettrack.boxes_view 와 다르다\n{b}\n{ref}")
            cache[str(ms)] = {"b": b, "o": sg.occ_cols(R, hc.band_crop(rgb, cfg["sheet_band"], cfg["side"]))}
            if i % 300 == 0:
                print(gid, i, len(todo), f"{time.time() - t0:.0f}s", flush=True)
                save_atomic(f, cache)
        save_atomic(f, cache)
        print(gid, "끝", len(todo), "장", f"{time.time() - t0:.0f}s", f"장당 {(time.time() - t0) / max(1, len(todo)):.2f}초", flush=True)


def cmd_cmpold(a):
    """새 캐시의 5장 프레임 상자 · 가림 열이 옛 캐시(slotgrid_1117/det_<판>.json, 읽기만)와 같은지(소수 첫째 자리) 센다."""
    import slotgrid as sg
    old_c, new_c = {}, {}
    tot = {"frames": 0, "missing_old": 0, "missing_new": 0, "b_same": 0, "o_same": 0, "boxes": 0, "boxes_same": 0}
    for tid in all_targets(a):
        tr = turn_frame(tid)
        gid = tr["plan"]["gid"]
        if gid not in old_c:
            old_c[gid] = hc.jload(sg.OUT / f"det_{gid}.json")
            new_c[gid] = hc.jload(det_path(gid)) if det_path(gid).exists() else {}
        o, n = old_c[gid], new_c[gid]
        c = {"frames": 0, "missing_old": 0, "missing_new": 0, "b_same": 0, "o_same": 0, "boxes": 0, "boxes_same": 0}
        for ms in tr["frames"]:
            k = str(ms)
            c["frames"] += 1
            if k not in o:
                c["missing_old"] += 1
                continue
            if k not in n:
                c["missing_new"] += 1
                continue
            ob = sorted(tuple(round(v, 1) for v in b[:4]) for b in o[k]["b"])
            nb = sorted(tuple(round(v, 1) for v in b[:4]) for b in n[k]["b"])
            c["b_same"] += ob == nb
            c["o_same"] += [list(x) for x in o[k]["o"]] == [list(x) for x in n[k]["o"]]
            c["boxes"] += len(ob)
            c["boxes_same"] += len(set(ob) & set(nb))
        print(tid, c, flush=True)
        for kk in tot:
            tot[kk] += c[kk]
    print("합", tot)


# ------------------------------------------------------------------ 입력(정답 안 읽음)
_DET: dict = {}


def det10(gid: str) -> dict:
    if gid not in _DET:
        f = det_path(gid)
        if not f.exists():
            raise SystemExit(f"새 캐시 {f} 가 없다 — detect 먼저")
        _DET[gid] = hc.jload(f)
    return _DET[gid]


def turn_input(tid: str, fps: int) -> dict:
    tr = turn_frame(tid)
    if fps == 10 and not tr["has_track"]:
        raise NoTen(tid)
    p = tr["plan"]
    det = det10(p["gid"])
    mss = list(tr["frames"]) if fps == 5 else frames10(p)
    if mss[0] != p["a_ms"] or mss[-1] != p["e_ms"]:
        raise SystemExit(f"{tid} {fps}장: 프레임 목록 처음 · 끝이 a_ms · e_ms 가 아니다")
    miss = [ms for ms in mss if str(ms) not in det]
    if miss:
        raise SystemExit(f"{tid} {fps}장: 새 캐시에 없는 프레임 {len(miss)}장(처음 {miss[:3]}) — detect 먼저")
    b0 = next((det[str(ms)]["b"][0] for ms in mss if det[str(ms)]["b"]), None)
    if b0 is None:
        raise SystemExit(f"{tid}: 상자가 있는 프레임이 없다")
    ox = s1.remap_box(b0, p["band"], p["band2"], p["side"])[0] - b0[0]
    frames = []
    for ms in mss:
        e = det[str(ms)]
        dets = [s1.remap_box(b, p["band"], p["band2"], p["side"]) + [float(b[4]) if len(b) > 4 else 1.0] for b in e["b"]]
        occ = [(o[0] + ox, o[1] + ox) for o in e["o"]]
        frames.append((ms, dets, occ))
    ab = p["a_boxes"]
    pitch = float(np.median(np.diff([cx(b) for b in ab])))
    return {"id": tid, "n": p["n"], "fps": fps, "a_boxes": ab, "e_boxes": p["e_boxes"], "frames": frames, "pitch": pitch, "ox": ox}


# ------------------------------------------------------------------ 팔 B0: ByteTrack
_BT = None


def bytetrack():
    """(BYTETracker 클래스, cfg dict, 우회 설명) — lap 이 없으면 자동 설치를 끄고 scipy 짝짓기로(머리말 참고)."""
    global _BT
    if _BT is not None:
        return _BT
    os.environ["YOLO_AUTOINSTALL"] = "false"
    note = []
    try:
        import lap  # noqa: F401
    except ImportError:
        stub = types.ModuleType("lap")
        stub.__version__ = "0-mottrack-stub"

        def _no_lapjv(*_a, **_k):
            raise RuntimeError("lap 대용 모듈 — lapjv 를 부르면 안 됨(use_lap=False 로 바꿨어야 함)")

        stub.lapjv = _no_lapjv
        sys.modules["lap"] = stub
        note.append("lap 없음 → 빈 lap 모듈로 import 만 통과, matching.linear_assignment 를 use_lap=False(scipy) 로")
    import yaml
    import ultralytics
    from ultralytics.trackers.byte_tracker import BYTETracker
    from ultralytics.trackers.utils import matching
    if note:
        orig = matching.linear_assignment

        def _la(cost_matrix, thresh, use_lap=True):
            return orig(cost_matrix, thresh, use_lap=False)

        matching.linear_assignment = _la
    cfg_path = Path(ultralytics.__file__).parent / "cfg" / "trackers" / "bytetrack.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    _BT = (BYTETracker, cfg, note, ultralytics.__version__, str(cfg_path))
    return _BT


class _Dets:
    """BYTETracker.update 가 받는 꼴: conf · cls · xywh(가운데 x, y, 폭, 높이) · len · 불리언 색인."""

    def __init__(self, arr: np.ndarray):
        self.arr = arr.reshape(-1, 5).astype(np.float32)
        self.conf = self.arr[:, 4]
        self.cls = np.zeros(len(self.arr), np.float32)
        a = self.arr
        self.xywh = np.stack([(a[:, 0] + a[:, 2]) / 2, (a[:, 1] + a[:, 3]) / 2, a[:, 2] - a[:, 0], a[:, 3] - a[:, 1]], 1) if len(a) else np.zeros((0, 4), np.float32)
        self.xyxy = a[:, :4]

    def __len__(self):
        return len(self.arr)

    def __getitem__(self, m):
        return _Dets(self.arr[m])


def b0_max_lost(fps: int, cfg: dict, override=None) -> int:
    return int(fps / B0_REF_FPS * cfg["track_buffer"]) if override is None else int(override)


def run_b0(frames: list, fps: int, max_lost=None) -> tuple:
    """프레임마다 {트랙 번호: 상자} 와 사건 목록. 사건 = (프레임 번호, 종류, 트랙 번호, 설명).
    max_lost = None 이면 옛 ByteTrack frame_rate 식(B0), 숫자면 그 값(B0z = 0)."""
    BYTETracker, cfg, _note, _v, _p = bytetrack()
    args = types.SimpleNamespace(**cfg)
    T = BYTETracker(args)
    T.max_frames_lost = b0_max_lost(fps, cfg, max_lost)
    per, events = [], []
    seen, prev, gone = set(), set(), set()
    for fi, (ms, dets, _occ) in enumerate(frames):
        out = T.update(_Dets(np.asarray(dets, np.float32) if dets else np.zeros((0, 5), np.float32)))
        cur = {}
        for r in out:
            cur[int(r[4])] = [float(r[0]), float(r[1]), float(r[2]), float(r[3])]
        per.append(cur)
        now = set(cur)
        for t in sorted(now - prev):
            if fi > 0:   # 첫 프레임의 트랙은 사건으로 안 적음(B1 과 같게)
                events.append((fi, "new" if t not in seen else "back", t, f"x {cx(cur[t]):.0f}"))
        for t in sorted(prev - now):
            events.append((fi, "lost", t, ""))
        alive = {s.track_id for s in T.tracked_stracks + T.lost_stracks}
        for t in sorted(seen - alive - now - gone):
            gone.add(t)
            events.append((fi, "del", t, "추적기에서 지워짐"))
        seen |= now
        prev = now
    return per, events


# ------------------------------------------------------------------ 팔 B1: 직접 짠 추적기
def hungarian(tr_ids: list, tr_pts: list, det_ids: list, det_pts: list, gate: float, pitch: float) -> list:
    if not tr_ids or not det_ids:
        return []
    C = np.full((len(tr_ids), len(det_ids)), 1e6)
    for i, (ax, ay) in enumerate(tr_pts):
        for j, (bx, by) in enumerate(det_pts):
            d = float(np.hypot(ax - bx, ay - by)) / pitch
            if d <= gate:
                C[i, j] = d
    r, c = linear_sum_assignment(C)
    return [(tr_ids[i], det_ids[j]) for i, j in zip(r, c) if C[i, j] <= gate]


def run_b1(frames: list, pitch: float, lost_ms_max=None) -> tuple:
    """lost_ms_max = None 이면 LOST_MS(B1), 숫자면 그 값(B1z = 0 — 잃은 번호를 다음 프레임 짝짓기 전에 지움)."""
    lost_lim = LOST_MS if lost_ms_max is None else lost_ms_max
    tracks: dict = {}   # 번호 → {"box", "st": active|lost|held, "lost_ms", "held"}
    nid = [1]
    per, events = [], []
    prev_ms = None
    for fi, (ms, dets, occ) in enumerate(frames):
        final = fi == len(frames) - 1
        dt = 0 if prev_ms is None else ms - prev_ms
        prev_ms = ms
        usable = [i for i, d in enumerate(dets) if final or occ_frac(d[0], d[2], occ) < OCC_FRAC]
        # 보류 판정(마지막 상자 기준)
        released = set()
        for t, s in tracks.items():
            h = (not final) and occ_frac(s["box"][0], s["box"][2], occ) >= OCC_FRAC
            if h and not s["held"]:
                events.append((fi, "hold", t, f"x {cx(s['box']):.0f} 가림 {occ_frac(s['box'][0], s['box'][2], occ):.2f}"))
                s["was"] = s["st"]
                s["st"] = "held"
            elif s["held"] and not h:
                released.add(t)
                events.append((fi, "release", t, f"x {cx(s['box']):.0f}"))
            s["held"] = h
        # 잃은 시간(보류 시간 뺌) · 지우기
        for t in [t for t, s in tracks.items() if s["st"] == "lost" and not s["held"]]:
            tracks[t]["lost_ms"] += dt
            if tracks[t]["lost_ms"] > lost_lim:
                events.append((fi, "del", t, f"잃은 지 {tracks[t]['lost_ms']}ms"))
                del tracks[t]
        cur = {}
        free = list(usable)
        # 1단계
        A = [t for t, s in tracks.items() if s["st"] == "active" and not s["held"]]
        m1 = hungarian(A, [(cx(tracks[t]["box"]), cy(tracks[t]["box"])) for t in A], free, [(cx(dets[i]), cy(dets[i])) for i in free], GATE, pitch)
        for t, i in m1:
            tracks[t]["box"] = list(dets[i][:4])
            cur[t] = tracks[t]["box"]
        got = {t for t, _ in m1}
        free = [i for i in free if i not in {i for _, i in m1}]
        just_lost = []
        for t in A:
            if t not in got:
                tracks[t]["st"] = "lost"
                tracks[t]["lost_ms"] = 0
                just_lost.append(t)
        # 2단계
        B = [t for t, s in tracks.items() if not s["held"] and (s["st"] == "lost" or t in released)]
        m2 = hungarian(B, [(cx(tracks[t]["box"]), cy(tracks[t]["box"])) for t in B], free, [(cx(dets[i]), cy(dets[i])) for i in free], REMATCH, pitch)
        for t, i in m2:
            old = tracks[t]["box"]
            tracks[t].update(box=list(dets[i][:4]), st="active", lost_ms=0)
            cur[t] = tracks[t]["box"]
            if t not in released or tracks[t].get("was") == "lost":
                events.append((fi, "back", t, f"x {cx(old):.0f} → {cx(dets[i]):.0f}" + (" (같은 프레임 1단계 실패 뒤)" if t in just_lost else "")))
        got2 = {t for t, _ in m2}
        free = [i for i in free if i not in {i for _, i in m2}]
        for t in just_lost:
            if t not in got2:
                events.append((fi, "lost", t, f"x {cx(tracks[t]['box']):.0f}"))
        for t in released:
            if t in tracks and t not in got2:
                if tracks[t].get("was") == "active":
                    tracks[t]["lost_ms"] = 0
                    events.append((fi, "lost", t, f"보류 풀렸는데 못 찾음 x {cx(tracks[t]['box']):.0f}"))
                tracks[t]["st"] = "lost"
        # 3단계
        for i in free:
            t = nid[0]
            nid[0] += 1
            tracks[t] = {"box": list(dets[i][:4]), "st": "active", "lost_ms": 0, "held": False}
            cur[t] = tracks[t]["box"]
            if fi > 0:
                events.append((fi, "new", t, f"x {cx(dets[i]):.0f}"))
        per.append(cur)
    return per, events


# ------------------------------------------------------------------ 번호 · 판정
def best_track(box, cur: dict):
    best, bv = None, IOU_LABEL
    for t, b in cur.items():
        v = iou(box, b)
        if v >= bv and (best is None or v > bv):
            best, bv = t, v
    return best


def label_and_judge(per: list, a_boxes: list, e_boxes: list, n: int) -> dict:
    first, last = per[0], per[-1]
    lab, why = {}, []
    for o, b in enumerate(a_boxes, 1):
        t = best_track(b, first)
        if t is None:
            why.append(f"첫 프레임 a_box {o}(x {cx(b):.0f})에 붙일 트랙 없음")
        elif t in lab:
            why.append(f"첫 프레임 트랙 {t} 가 a_box {lab[t]} · {o} 둘에 붙음")
        else:
            lab[t] = o
    name = lambda t: None if t is None else (lab[t] if t in lab else f"x{t}")  # noqa: E731
    if why:
        return {"kind": None, "k": None, "j": None, "reasons": why, "end_order": None, "labels": {str(t): o for t, o in lab.items()}, "name": name}
    eb = sorted(e_boxes, key=cx)
    order = [name(best_track(b, last)) for b in eb]
    res = {"labels": {str(t): o for t, o in lab.items()}, "end_order": order, "name": name}
    res.update(judge_order(order, n))
    return res


def judge_order(order: list, n: int, x_dup: bool = True) -> dict:
    """끝 줄 판정(재료 팔 · 합친 팔 공통). order = 상자 x 순 이름(원래 번호 int · "x…" · None).
    x_dup = True(재료 팔): x… 이름 겹침도 못 정함. False(합친 팔): 원래 번호 겹침만 봄(x… 는 추적기마다 따로 센 것)."""
    named = [x for x in order if (x is not None if x_dup else isinstance(x, int))]
    dup = sorted({str(x) for x in named if named.count(x) > 1})
    full = list(range(1, n + 1))
    miss = [o for o in full if o not in order]
    outs = [i for i, x in enumerate(order) if not isinstance(x, int)]
    if dup:
        return {"kind": None, "k": None, "j": None, "reasons": [f"같은 이름이 두 상자 이상: {dup}"]}
    if sorted(x for x in order if isinstance(x, int)) == full and len(order) == n:
        return {"kind": "tsumogiri", "k": None, "j": None, "reasons": []}
    if len(miss) == 1 and len(outs) == 1:
        return {"kind": "hand", "k": miss[0], "j": outs[0] + 1, "reasons": []}
    return {"kind": None, "k": None, "j": None, "reasons": [f"끝 줄 {len(order)}상자 · 없는 번호 {miss} · 1 ~ {n} 밖 상자 {len(outs)}개"]}


# ------------------------------------------------------------------ 합친 팔(채점 전 덧붙임 3)
def _orig(x, n: int):
    """저장된 end_order 이름 → 원래 번호면 int, 아니면 그대로("x…" · None)."""
    if x is not None and x.isdigit() and 1 <= int(x) <= n:
        return int(x)
    return x


def fuse(r1: dict, r2: dict, n: int) -> dict:
    """출력 1(바로 지움) · 출력 2(보관)의 end_order 만 써서 합침 — 상자마다 출력 1 이 원래 번호면 그것, 아니면 출력 2 이름."""
    o1, o2 = r1.get("end_order"), r2.get("end_order")
    conflicts = from1 = from2 = 0
    reasons = []
    if o1 is None and o2 is None:
        return {"kind": None, "k": None, "j": None, "reasons": ["두 출력 모두 첫 프레임 번호 붙이기 실패"], "end_order": None,
                "conflicts": 0, "from1": 0, "from2": 0}
    if o1 is not None and o2 is not None and len(o1) != len(o2):
        return {"kind": None, "k": None, "j": None, "reasons": [f"두 출력의 끝 줄 길이가 다름 {len(o1)} ≠ {len(o2)}"], "end_order": None,
                "conflicts": 0, "from1": 0, "from2": 0}
    if o1 is None:
        reasons.append("출력 1 첫 프레임 번호 붙이기 실패 — 출력 2 만 씀")
        order = [_orig(x, n) for x in o2]
        from2 = sum(isinstance(x, int) for x in order)
    elif o2 is None:
        reasons.append("출력 2 첫 프레임 번호 붙이기 실패 — 출력 1 만 씀")
        order = [_orig(x, n) for x in o1]
        from1 = sum(isinstance(x, int) for x in order)
    else:
        order = []
        for a, b in zip(o1, o2):
            a, b = _orig(a, n), _orig(b, n)
            if isinstance(a, int) and isinstance(b, int) and a != b:
                conflicts += 1
            if isinstance(a, int):
                order.append(a)
                from1 += 1
            else:
                order.append(b)
                from2 += isinstance(b, int)
    j = judge_order(order, n, x_dup=False)
    return {**j, "reasons": reasons + j["reasons"], "end_order": [None if x is None else str(x) for x in order],
            "conflicts": conflicts, "from1": from1, "from2": from2}


def fused_result(tid: str, arm: str, fps: int, n: int, r1: dict, r2: dict) -> dict:
    f = fuse(r1, r2, n)
    return {"id": tid, "arm": arm, "fps": fps, "n": n, "kind": f["kind"], "k": f["k"], "j": f["j"], "reasons": f["reasons"],
            "end_order": f["end_order"], "conflicts": f["conflicts"], "from1": f["from1"], "from2": f["from2"], "src": list(FUSED[arm])}


def line_of_fused(r: dict) -> str:
    kind = r["kind"] or "못정함"
    s = f"{r['arm']}_{r['fps']:<2} {r['id']:9s} {kind:9s} k {r['k']} · j {r['j']}"
    if r["end_order"] is not None:
        s += " | 끝 " + " ".join("-" if x is None else x for x in r["end_order"])
    s += f" | {r['src'][0]}+{r['src'][1]} · 어긋 상자 {r['conflicts']} · 출력1 번호 {r['from1']} · 출력2 로 채운 번호 {r['from2']}"
    if r["reasons"]:
        s += " | " + " / ".join(r["reasons"])
    return s


def material(tid: str, arm: str, fps: int, cache: dict, inp_get) -> dict:
    """재료 팔 결과: 이번에 만든 것 → 저장 파일 → 없으면 돌려 저장."""
    if (arm, fps) in cache:
        return cache[(arm, fps)]
    f = OUT / f"{arm}_{fps}" / f"{tid}.json"
    if f.exists():
        r = hc.jload(f)
    else:
        r = run_one(inp_get(), arm)
        hc.jsave(f, r, indent=None)
    cache[(arm, fps)] = r
    return r


def run_one(inp: dict, arm: str) -> dict:
    fr = inp["frames"]
    t0 = time.time()
    trk, ov = ARM_SPEC[arm]
    per, ev = run_b0(fr, inp["fps"], ov) if trk == "b0" else run_b1(fr, inp["pitch"], ov)
    r = label_and_judge(per, inp["a_boxes"], inp["e_boxes"], inp["n"])
    name = r.pop("name")
    nm = lambda t: str(name(t))  # noqa: E731
    events = [(fi, fr[fi][0], hc.mss(fr[fi][0]) if fr[fi][0] > 10 ** 11 else f"{fr[fi][0]}ms", k, nm(t), s) for fi, k, t, s in ev]
    cnt = {}
    for e in events:
        cnt[e[3]] = cnt.get(e[3], 0) + 1
    lab_ev = [e for e in events if e[4].isdigit()]
    return {"id": inp["id"], "arm": arm, "fps": inp["fps"], "n": inp["n"], "kind": r["kind"], "k": r["k"], "j": r["j"],
            "reasons": r["reasons"], "end_order": None if r["end_order"] is None else [None if x is None else str(x) for x in r["end_order"]],
            "labels": r["labels"], "frames": len(fr), "pitch": round(inp["pitch"], 2), "ox": inp.get("ox"),
            "n_tracks": len({t for d in per for t in d}), "event_counts": cnt, "labeled_event_counts": {k: sum(1 for e in lab_ev if e[3] == k) for k in cnt},
            "events": events, "sec": round(time.time() - t0, 2)}


def line_of(r: dict) -> str:
    kind = r["kind"] or "못정함"
    s = f"{r['arm']}_{r['fps']:<2} {r['id']:9s} {kind:9s} k {r['k']} · j {r['j']}"
    if r["end_order"] is not None:
        s += " | 끝 " + " ".join("-" if x is None else x for x in r["end_order"])
    c = r["event_counts"]
    s += f" | 트랙 {r['n_tracks']} · 새 {c.get('new', 0)} · 잃음 {c.get('lost', 0)} · 다시 {c.get('back', 0)} · 보류 {c.get('hold', 0)} · 지움 {c.get('del', 0)}"
    if r["reasons"]:
        s += " | " + " / ".join(r["reasons"])
    return s


# ------------------------------------------------------------------ 팔 g(추가 56 — 두 출력의 근거를 가설마다 맞춰 보기, 초당 5장만)
def g_hyps(n: int) -> list:
    """가설 1 + n² 개: ("tsumogiri", None, None, [1 … n]) · ("hand", k, j, k 를 뺀 1 … n 에 j 번째(1부터) "D")."""
    out = [("tsumogiri", None, None, list(range(1, n + 1)))]
    for k in range(1, n + 1):
        rest = [o for o in range(1, n + 1) if o != k]
        for j in range(1, n + 1):
            pred = list(rest)
            pred.insert(j - 1, "D")
            out.append(("hand", k, j, pred))
    return out


def run_g(inp: dict, r_b1: dict) -> dict:
    """출력 1 = b0z(5장, max_frames_lost 0)의 프레임별 트랙을 다시 돌려 굳은 근거, 출력 2 = b1 저장 결과 end_order 로 점수."""
    n, pitch = inp["n"], inp["pitch"]
    base = {"id": inp["id"], "arm": G_ARM, "fps": inp["fps"], "n": n, "kind": None, "k": None, "j": None, "reasons": [],
            "fixed": {}, "slid": {}, "n_candidates": 0, "top": [], "src": ["b0z", "b1"]}
    per, _ev = run_b0(inp["frames"], inp["fps"], 0)
    lj = label_and_judge(per, inp["a_boxes"], inp["e_boxes"], n)
    if lj["end_order"] is None:
        base["reasons"] = ["출력 1(b0z) 첫 프레임 번호 붙이기 실패: " + " / ".join(lj["reasons"])]
        return base
    lab = {int(t): o for t, o in lj["labels"].items()}
    eb = sorted(inp["e_boxes"], key=cx)
    if len(eb) != n:
        base["reasons"] = [f"끝 상자 {len(eb)}개 ≠ n {n}"]
        return base
    birth: dict = {}
    for d in per:
        for t, b in d.items():
            birth.setdefault(t, b)
    fixed, slid = {}, {}
    for s, b in enumerate(eb, 1):
        t = best_track(b, per[-1])
        if t is None:
            continue
        if t in lab:
            fixed[s] = lab[t]
        else:
            sl = (cx(b) - cx(birth[t])) / pitch
            if abs(sl + 1) <= SLIDE_TOL:
                slid[s] = -1
            elif abs(sl - 1) <= SLIDE_TOL:
                slid[s] = 1
    base["fixed"] = {str(s): o for s, o in fixed.items()}
    base["slid"] = {str(s): d for s, d in slid.items()}
    cands = []
    for h in g_hyps(n):
        pred = h[3]
        if any(pred[s - 1] != o for s, o in fixed.items()):
            continue
        if any(not (pred[s - 1] == "D" or pred[s - 1] == s - d) for s, d in slid.items()):
            continue
        cands.append(h)
    base["n_candidates"] = len(cands)
    if not cands:
        base["reasons"] = ["근거 모순"]
        return base
    o2 = r_b1.get("end_order")
    if o2 is not None and len(o2) != n:
        base["reasons"].append(f"출력 2(b1) 끝 줄 {len(o2)}상자 ≠ n — 점수 0")
        o2 = None
    if o2 is None:
        if not base["reasons"]:
            base["reasons"].append("출력 2(b1) 끝 줄 없음 — 모든 가설 0점")
        names = [None] * n
    else:
        names = [_orig(x, n) for x in o2]
    scored = []
    for h in cands:
        sc = sum((1 if h[3][i] == x else -1) for i, x in enumerate(names) if isinstance(x, int))
        scored.append((h[0], h[1], h[2], sc))
    best = max(x[3] for x in scored)
    grp = [x for x in scored if x[3] > best - G_MARGIN]
    kinds = {x[0] for x in grp}
    kind = kinds.pop() if len(kinds) == 1 else None
    k = j = None
    if kind == "hand":
        ks, js = {x[1] for x in grp}, {x[2] for x in grp}
        k = ks.pop() if len(ks) == 1 else None
        j = js.pop() if len(js) == 1 else None
    base.update(kind=kind, k=k, j=j,
                top=[list(x) for x in sorted(grp, key=lambda x: (-x[3], x[0] != "tsumogiri", x[1] or 0, x[2] or 0))[:G_TOP_MAX]],
                group_size=len(grp), best_score=best)
    return base


def line_of_g(r: dict) -> str:
    kind = r["kind"] or "못정함"
    s = f"{r['arm']}_{r['fps']:<2} {r['id']:9s} {kind:9s} k {r['k']} · j {r['j']}"
    s += f" | 굳은 번호 {len(r['fixed'])} · 밀림 {len(r['slid'])} · 후보 {r['n_candidates']} · 묶음 {r.get('group_size', 0)}"
    if r.get("top"):
        s += " | 위 " + " ".join(f"{x[0][0]}{'' if x[1] is None else f'{x[1]}·{x[2]}'}({x[3]})" for x in r["top"][:4])
    if r["reasons"]:
        s += " | " + " / ".join(r["reasons"])
    return s


def g_result(tid: str, made: dict, inp_get) -> dict:
    r_b1 = material(tid, "b1", G_FPS, made, inp_get)
    return run_g(inp_get(), r_b1)


def arms_fpss(a):
    arms = ALL_ARMS + (G_ARM,) if a.arm == "all" else (a.arm,)
    fpss = FPSS if a.fps == "all" else (int(a.fps),)
    return arms, fpss


def cmd_run(a):
    arms, fpss = arms_fpss(a)
    for tid in all_targets(a):
        for fps in fpss:
            if fps == 10 and not turn_frame(tid)["has_track"]:
                print(f"{tid}: 10장 팔 건너뜀(SAM 2 track.json 없는 새 차례는 5장만)", flush=True)
                continue
            box = {}

            def inp_get(tid=tid, fps=fps, box=box):
                if "inp" not in box:
                    box["inp"] = turn_input(tid, fps)
                return box["inp"]

            made = {}
            for arm in (x for x in arms if x in ARMS):    # 재료 팔
                r = run_one(inp_get(), arm)
                hc.jsave(OUT / f"{arm}_{fps}" / f"{tid}.json", r, indent=None)
                made[(arm, fps)] = r
                print(line_of(r), flush=True)
            for arm in (x for x in arms if x in FUSED):   # 합친 팔 — 재료는 이번 결과 → 파일 → 없으면 돌림
                r1 = material(tid, FUSED[arm][0], fps, made, inp_get)
                r2 = material(tid, FUSED[arm][1], fps, made, inp_get)
                r = fused_result(tid, arm, fps, r1["n"], r1, r2)
                hc.jsave(OUT / f"{arm}_{fps}" / f"{tid}.json", r, indent=None)
                print(line_of_fused(r), flush=True)
            if G_ARM in arms and fps == G_FPS:            # 팔 g — 5장만
                r = g_result(tid, made, inp_get)
                hc.jsave(OUT / f"{G_ARM}_{fps}" / f"{tid}.json", r, indent=None)
                print(line_of_g(r), flush=True)
            elif a.arm == G_ARM and fps != G_FPS:
                print(f"{tid}: 팔 g 는 5장만 — {fps}장 건너뜀", flush=True)


# ------------------------------------------------------------------ score(정답은 여기서만 — 검토자가 한 번만 실행)
def consts() -> dict:
    BYTETracker, cfg, note, ver, path = bytetrack()
    return {"IOU_LABEL": IOU_LABEL, "OCC_FRAC": OCC_FRAC, "GATE": GATE, "REMATCH": REMATCH, "LOST_MS": LOST_MS,
            "B0_REF_FPS": B0_REF_FPS, "bytetrack_cfg": cfg, "bytetrack_cfg_path": path, "ultralytics": ver,
            "arms": list(ARMS), "arm_spec": {a: list(v) for a, v in ARM_SPEC.items()},
            "b0_max_frames_lost": {a: {str(f): b0_max_lost(f, cfg, ARM_SPEC[a][1]) for f in FPSS} for a in ARMS if ARM_SPEC[a][0] == "b0"},
            "b1_lost_ms": {a: (LOST_MS if ARM_SPEC[a][1] is None else ARM_SPEC[a][1]) for a in ARMS if ARM_SPEC[a][0] == "b1"},
            "fused": {a: {"out1_immediate_delete": v[0], "out2_keep": v[1],
                          "rule": "상자마다 출력 1 이 원래 번호(1 ~ n)면 그것, 아니면 출력 2 이름 · 원래 번호 겹침만 못 정함(x… 겹침은 안 봄) · 한쪽 end_order 가 없으면 다른 쪽만"}
                      for a, v in FUSED.items()},
            "all_arms": list(ALL_ARMS), "b0_workaround": note,
            "g": {"fps": G_FPS, "SLIDE_TOL": SLIDE_TOL, "G_MARGIN": G_MARGIN, "G_TOP_MAX": G_TOP_MAX, "out1": "b0z(max_frames_lost 0, 다시 돌림)",
                  "out2": "b1 저장 결과 end_order",
                  "rule": "굳은 근거(b0z 끝 트랙이 원래 번호 → 그 자리 = 그 번호 · 새 번호가 태어난 자리→끝 상자 −1/+1 ± SLIDE_TOL 장폭 → 그 자리 = D 또는 s+1/s−1)를 "
                          "어기는 가설 버림 · 남은 가설 점수 = b1 원래 번호 상자 같음 +1 · 다름 −1 · 최고 − G_MARGIN 초과 = 동점 묶음 · 성분별 확신"},
            "sets": {"dev": "idsolve.targets()", "new23": list(NEW23)}}


def grade_g(r: dict, u: dict) -> dict:
    """팔 g 채점(추가 56): idsolve.grade + 성분별 확신. both = 종류 맞고(hand 면 k · j 모두 확신하고 맞음), silent_wrong = 확신한 성분 중 하나라도 틀림."""
    gk, gj = ids_.grade(r, u)
    kind, k, j = r["kind"], r["k"], r["j"]
    if u["kind"] == "tsumogiri":
        both = kind == "tsumogiri"
        silent = kind is not None and kind != "tsumogiri"
    else:
        both = kind == "hand" and k is not None and j is not None and k == u["k_id"] and j == u["j_closed"]
        silent = (kind is not None and kind != "hand") or (kind == "hand" and ((k is not None and k != u["k_id"]) or (j is not None and j != u["j_closed"])))
    hand_t = u["kind"] == "hand"
    return {"pred": [kind, k, j], "k": gk, "j": gj, "both": both, "undecided": not both and not silent, "silent_wrong": silent,
            "reasons": r["reasons"], "kind_sure": kind is not None, "kind_right": kind is not None and kind == u["kind"],
            "k_sure": k is not None, "k_right": k is not None and hand_t and k == u["k_id"],
            "j_sure": j is not None, "j_right": j is not None and hand_t and j == u["j_closed"],
            "n_candidates": r["n_candidates"], "fixed": len(r["fixed"]), "slid": len(r["slid"])}


def cmd_score(a):
    truth = s1.truth_all()
    tids = all_targets(a)
    sname = getattr(a, "set", "dev")
    fpss = FPSS if getattr(a, "fps", None) in (None, "all") else (int(a.fps),)
    if 10 in fpss and any(not turn_frame(t)["has_track"] for t in tids):
        print("10장 칸 건너뜀 — SAM 2 track.json 없는 새 차례가 있음(5장만 채점)", flush=True)
        fpss = tuple(f for f in fpss if f != 10)
    cols = [f"{arm}_{fps}" for arm in ALL_ARMS for fps in fpss] + ([f"{G_ARM}_{G_FPS}"] if G_FPS in fpss else [])
    rows = []
    for tid in tids:
        u = truth.get(tid)
        if u is None or u["kind"] not in ("hand", "tsumogiri"):
            continue
        row = {"id": tid, "truth": [u["kind"], u.get("k_id"), u.get("j_closed")]}
        for fps in fpss:
            box = {}

            def inp_get(tid=tid, fps=fps, box=box):
                if "inp" not in box:
                    box["inp"] = turn_input(tid, fps)
                return box["inp"]

            mats = {}
            for arm in ALL_ARMS:
                if arm in ARMS:
                    r = material(tid, arm, fps, mats, inp_get)
                else:
                    f = OUT / f"{arm}_{fps}" / f"{tid}.json"
                    if f.exists():
                        r = hc.jload(f)
                    else:
                        r1 = material(tid, FUSED[arm][0], fps, mats, inp_get)
                        r2 = material(tid, FUSED[arm][1], fps, mats, inp_get)
                        r = fused_result(tid, arm, fps, r1["n"], r1, r2)
                        hc.jsave(f, r, indent=None)
                gk, gj = ids_.grade(r, u)
                row[f"{arm}_{fps}"] = {"pred": [r["kind"], r["k"], r["j"]], "k": gk, "j": gj, "both": gk and gj,
                                       "undecided": r["kind"] is None, "silent_wrong": r["kind"] is not None and not (gk and gj),
                                       "reasons": r["reasons"]}
                if arm in FUSED:
                    row[f"{arm}_{fps}"].update(conflicts=r["conflicts"], from1=r["from1"], from2=r["from2"])
            if fps == G_FPS:   # 팔 g
                f = OUT / f"{G_ARM}_{fps}" / f"{tid}.json"
                if f.exists():
                    r = hc.jload(f)
                else:
                    r = g_result(tid, mats, inp_get)
                    hc.jsave(f, r, indent=None)
                row[f"{G_ARM}_{fps}"] = grade_g(r, u)
        rows.append(row)
        print(f"{tid:9s} 정답 {u['kind'][:4]} {u.get('k_id')}·{u.get('j_closed')} | " + " | ".join(
            f"{c} {(row[c]['pred'][0] or '못정')[:4]} {row[c]['pred'][1]}·{row[c]['pred'][2]} {'✓' if row[c]['both'] else ('?' if row[c]['undecided'] else '✗')}"
            for c in cols), flush=True)
    groups = (("all", rows), ("hand", [r for r in rows if r["truth"][0] == "hand"]),
              ("tsumogiri", [r for r in rows if r["truth"][0] == "tsumogiri"]), ("three", [r for r in rows if r["id"] in THREE]))
    tot = {}
    for c in cols:
        tot[c] = {}
        for gname, sel in groups:
            tot[c][gname] = {"n": len(sel), **{k: sum(bool(r[c][k]) for r in sel) for k in ("both", "k", "j", "undecided", "silent_wrong")}}
            if "conflicts" in (sel[0][c] if sel else {}):
                tot[c][gname]["conflict_boxes"] = sum(r[c]["conflicts"] for r in sel)
                tot[c][gname]["conflict_turns"] = sum(r[c]["conflicts"] > 0 for r in sel)
            if c == f"{G_ARM}_{G_FPS}":
                for k in ("kind_sure", "kind_right", "k_sure", "k_right", "j_sure", "j_right"):
                    tot[c][gname][k] = sum(bool(r[c][k]) for r in sel)
                tot[c][gname]["contradiction"] = sum(r[c]["n_candidates"] == 0 for r in sel)
    print()
    for c, v in tot.items():
        for gname, x in v.items():
            print(f"{c:6s} {gname:9s} n {x['n']:2d} · both {x['both']:2d} · k {x['k']:2d} · j {x['j']:2d} · 못 정함 {x['undecided']:2d} · 조용한 틀림 {x['silent_wrong']:2d}"
                  + (f" · 어긋 상자 {x['conflict_boxes']} ({x['conflict_turns']}차례)" if "conflict_boxes" in x else "")
                  + (f" · 종류 확신 {x['kind_sure']} 중 맞음 {x['kind_right']} · k 확신 {x['k_sure']} 중 맞음 {x['k_right']}"
                     f" · j 확신 {x['j_sure']} 중 맞음 {x['j_right']} · 근거 모순 {x['contradiction']}" if "kind_sure" in x else ""))
    out_f = OUT / ("score.json" if sname == "dev" else f"score_{sname}.json")
    hc.jsave(out_f, {"set": sname, "fps": list(fpss), "totals": tot, "rows": rows, "consts": consts()}, indent=1)
    print("저장", out_f)
    ref = hc.WORK / "idsolve_1120" / "score.json"
    if sname == "dev" and ref.exists():   # totals 만 읽음(행별 정답 칸은 안 찍음) · new23 에서는 안 찍음
        rt = hc.jload(ref).get("totals", {})
        print("\n견줄 것(idsolve_1120/score.json totals):")
        for gname in ("all", "hand", "tsumogiri", "three"):
            if gname in rt:
                b, i = rt[gname].get("base", {}), rt[gname].get("idsolve", {})
                print(f"  {gname:9s} n {rt[gname].get('n')} | SAM 2 그대로 both {b.get('both')} · k {b.get('k')} · j {b.get('j')} · 못 정함 {b.get('undecided')}"
                      f" · 조용한 틀림 {b.get('silent_wrong')} | idsolve both {i.get('both')} · k {i.get('k')} · j {i.get('j')} · unsure {i.get('unsure')}"
                      f" · 조용한 틀림 {i.get('silent_wrong')}")


# ------------------------------------------------------------------ selftest(합성 — 정답 파일 안 읽음)
SP, SW, SH, SY, SX0 = 40, 36, 50, 100, 100   # 장폭 · 상자 폭 · 높이 · 윗변 y · 1번 가운데 x


def synth(scn: str, dt: int) -> dict:
    xs = {i: SX0 + (i - 1) * SP for i in range(1, 14)}
    x13 = xs[13]
    t_gap = next(ms for ms in range(0, 3001, dt) if ms >= 1500)   # 5번째가 없는 첫 프레임(5장 1600 · 10장 1500) — 여기서부터 프레임당 8 / 4

    def shift(ms):
        return SP * min(1.0, max(0.0, (ms - t_gap) / 1000)) if scn == "S3" else 0.0

    def box(x):
        return [x - SW / 2, SY, x + SW / 2, SY + SH, 0.9]

    frames = []
    for ms in range(0, 3001, dt):
        bs, occ = [], []
        for i in range(1, 14):
            x = xs[i]
            if scn in ("S2", "S3") and i == 5 and ms >= 1500:
                continue
            if scn == "S3" and i >= 6:
                x -= shift(ms)
            if scn == "S4" and 4 <= i <= 7 and 1000 <= ms < 2000:
                continue
            bs.append(box(x))
        if scn == "S1" and 1000 <= ms < 2000:
            bs.append(box(x13 + 2 * SP))            # 줄 오른쪽 끝에서 한 칸 띄운 자리
        if scn in ("S2", "S3") and ms >= 1000:
            bs.append(box(x13 + SP - shift(ms)))    # 13번째 오른쪽 한 칸 자리
        if scn == "S4" and 1000 <= ms < 2000:
            occ.append((xs[4] - SP / 2, xs[7] + SP / 2))
        frames.append((ms, sorted(bs), occ))
    ab = [b[:4] for b in frames[0][1]]
    eb = [b[:4] for b in frames[-1][1]]
    return {"id": scn, "n": 13, "fps": 1000 // dt, "a_boxes": ab, "e_boxes": eb, "frames": frames,
            "pitch": float(np.median(np.diff([cx(b) for b in ab]))), "ox": 0.0}


EXPECT = {"S1": ("tsumogiri", None, None), "S2": ("hand", 5, 13), "S3": ("hand", 5, 13), "S4": ("tsumogiri", None, None)}


NO_EXPECT = {("S4", "b0"), ("S4", "b0z")}          # 기대값 없음(출력만)
KNOWN_BAD = {("S3", "b0", 5), ("S3", "b0", 10)}    # 채점 전 덧붙임 1: 알려진 어긋남(기대값은 안 바꿈, 종료 코드에 안 셈)


def cmd_selftest(_a):
    bad, known = 0, 0
    for scn in ("S1", "S2", "S3", "S4"):
        for fps in FPSS:
            inp = synth(scn, 1000 // fps)
            mats = {}
            for arm in ALL_ARMS + ((G_ARM,) if fps == G_FPS else ()):
                if arm in ARMS:
                    r = run_one(inp, arm)
                    mats[arm] = r
                elif arm == G_ARM:
                    r = run_g(inp, mats["b1"])
                else:
                    r = fused_result(scn, arm, fps, inp["n"], mats[FUSED[arm][0]], mats[FUSED[arm][1]])
                got = (r["kind"], r["k"], r["j"])
                fixed = (scn, arm) not in NO_EXPECT
                ok = got == EXPECT[scn]
                is_known = (scn, arm, fps) in KNOWN_BAD
                if not fixed:
                    mark = "(기대값 없음)"
                elif ok:
                    mark = "통과" + (" (알려진 어긋남이었는데 맞음)" if is_known else "")
                elif is_known:
                    mark = "어긋남(알려진 어긋남)"
                    known += 1
                else:
                    mark = "어긋남"
                    bad += 1
                ln = line_of(r) if arm in ARMS else (line_of_g(r) if arm == G_ARM else line_of_fused(r))
                print(f"{scn} {arm}_{fps:<2} → {got} 기대 {EXPECT[scn] if fixed else '-'} {mark} | {ln.split('|', 1)[1].strip()}")
                if fixed and not ok and not is_known:
                    for e in r.get("events", [r]):
                        print("    ", e)
    BYTETracker, cfg, note, ver, path = bytetrack()
    c = consts()
    print(f"\nultralytics {ver} · {path}\nbytetrack cfg {cfg} · max_frames_lost {c['b0_max_frames_lost']} · B1 LOST_MS {c['b1_lost_ms']} · 우회 {note}")
    print("selftest", ("모두 통과" if bad == 0 else f"새 어긋남 {bad}") + (f" · 알려진 어긋남 {known}" if known else ""))
    if bad:
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("detect", "cmpold", "score"):
        q = sp.add_parser(name)
        q.add_argument("--ids")
        q.add_argument("--set", default="dev", choices=list(SETS))
        if name == "detect":
            q.add_argument("--fps", default=None, choices=["5", "10"], help="5 = 차례의 5장 프레임만(없거나 10 = 10장 전부)")
        if name == "score":
            q.add_argument("--fps", default=None, choices=["5", "10", "all"])
    q = sp.add_parser("run")
    q.add_argument("--ids")
    q.add_argument("--set", default="dev", choices=list(SETS))
    q.add_argument("--arm", default="all", choices=[*ALL_ARMS, G_ARM, "all"])
    q.add_argument("--fps", default="all", choices=["5", "10", "all"])
    sp.add_parser("selftest")
    a = ap.parse_args()
    {"detect": cmd_detect, "cmpold": cmd_cmpold, "run": cmd_run, "score": cmd_score, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
