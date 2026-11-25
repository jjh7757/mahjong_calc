"""자동 패보 — 손 추적 판별 설정을 코드로 만들고 handtrack 판별(features → segment → river → game · bandfit)을 돌린다(2026-11-24).

paifu_auto.py 의 S6a(손 추적 설정) · S6b(손 추적 판별)가 하위 프로세스로 부른다. 11-23 3반장 때 세션 · 하위 에이전트가 프레임을 눈으로 보고 손으로 쓴
handtrack/config/<판>.json 을 대신한다. 결과는 실행 폴더 안(<실행>/handtrack/config · <판>/ · _work/)에 쓰고, 공용 자리(handtrack/config ·
results/handtrack/ · _work/)에는 쓰지 않는다 — 공용 모듈(features · segment · river · game · bandfit)은 고치지 않고 handtrack/ht_redirect.py 가
실행 중에 그 판 id 의 경로만 실행 폴더로 돌린다(설정 handtrack.dir · handtrack.games).

  python -X utf8 experiments/paifu_frames/handtrack_auto.py frame [--write]                  # 녹화 틀 뽑기(기존 손 설정 → hanchan/h2_1114.json "frame")
  python -X utf8 experiments/paifu_frames/handtrack_auto.py conf --cfg <실행 hanchan.json> --spec <spec.json>   # S6a 판 하나: 설정 + features + t_ready
  python -X utf8 experiments/paifu_frames/handtrack_auto.py run  --cfg <실행 hanchan.json> <판 id> [--no-river]  # S6b 판 하나: segment · river · game · bandfit
                                                                                                                 # (--no-river: 앱 기록 반장 — 11-25 설계서 8-13 (가))
  python -X utf8 experiments/paifu_frames/handtrack_auto.py rules --spec <spec.json> --out <폴더>                  # 시험용: 규칙만(설정 · 특징을 --out 에만)

자동 규칙(문턱은 아래 상수 — 2반장 아홉 판(본 판)을 보고 정한 값이 있어 정확도 근거가 아님, 각 상수 주석 참고):
  side          = rounds_meta 손패 주인 자리(hero) − 아래 자리(bottom_seat)
  영역          = 반장 설정 frame.sides[side] (band · river · meld · reveal_region · wide · search) — 없으면 멈춤
  t_start       = 앞 판 마지막 버림 + PREV_GAP_S(앞 판 없으면 첫 버림 − FIRST_LOOKBACK_S) ~ 이 판 첫 버림(헤드 시계) 사이에서 손패 띠가 빈 첫 때
                  (1초마다 검출 상자 ≤ EMPTY_MAX 가 EMPTY_HOLD 번 — 앞 판 패를 밀어 넣은 뒤 · 새 배패 전). 못 찾으면 max(앞 판 마지막 버림 + PREV_GAP_S,
                  첫 버림 − READY_LOOKBACK_S). t_ready 를 찾는 아래 끝 · features 구간 시작
  t_reveal      = 유국: S4 공개 읽기 t_reveal. 화료: 마지막 버림 뒤 reveal_region 의 흰 면 비율이 바탕(마지막 버림 앞 REVEAL_BASE_S 초 중앙값)
                  + (가라앉은 값 − 바탕) / 2 를 처음 넘는 프레임(공개 프레임 rf 를 먼저 찾고 거꾸로)
  reveal_frame  = t_reveal(화료는 마지막 버림) 뒤 reveal_region 이 REVEAL_HOLD 장 이상 가만한(d1 ≤ REVEAL_D1 · 피부 ≤ REVEAL_SKIN) 구간의 첫 프레임 중
                  흰 면이 바탕 + REVEAL_RISE 이상이고 검출기 앞면 상자가 그 영역에 REVEAL_MIN_FACES 장 이상인 첫 것
  post_sec      = max(4, reveal_frame − t_reveal + 2초) 올림
  t_ready       = t_start 뒤 손패 띠(band)가 READY_HOLD 장 이상 가만한(segment.py 문턱: d1 · d3 ≤ ACT_DIFF, 피부 ≤ ACT_SKIN) 구간의 첫 프레임 중
                  검출기 뒷면 상자(band 를 줄 방향으로 ±READY_DET_PAD 넓힌 곳)의 가장 큰 덩어리가 13장이고, 그 뒤 READY_STABLE_S 초 안의
                  가만한 구간에서 줄이 다시 흩어지지 않는(덩어리 ≤ 11 이 없는) 첫 것(정리 중 잠깐 멈춘 줄을 거름).
                  못 찾으면 ① 피부 무시(손이 줄 끝에 얹혀 있음) ② 그래도 없으면 첫 버림 뒤 첫 가만한 구간(질문)
  sheet_band    = bandfit.py(그대로 --write)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HT = HERE / "handtrack"
sys.path.insert(0, str(HT))
import hanchan_cfg as hcfg  # noqa: E402
import htcommon as hc  # noqa: E402
import ht_redirect as htr  # noqa: E402

SIDES = ["bottom", "right", "top", "left"]
REGIONS = ["band", "river", "meld", "reveal_region", "wide", "search"]
# ---- t_start = 손패 띠가 빈 때(앞 판 패를 기계에 밀어 넣은 뒤 · 새 배패 전). 처음엔 "첫 버림 − 60초" 로 두었다가 2반장 w12 · w14 에서
#      앞 판 손패 줄(아래 자리 — 공개 뒤 밀어 넣기 전까지 13장이 그대로 섬)을 t_ready 로 잡아 바꿈(본 판을 보고 정한 규칙)
EMPTY_STEP_MS = 1000       # 1초마다 검출기
EMPTY_MAX = 2              # 띠(det_box) 안 검출 상자(앞면 + 뒷면) ≤ 2 = 빈 띠
EMPTY_HOLD = 3             # 빈 띠가 3번(3초) 넘게 이어져야(팔이 줄을 덮어 상자가 안 잡힌 순간을 빈 띠로 안 보게)
FIRST_LOOKBACK_S = 150     # 앞 판이 없으면 첫 버림 150초 앞부터 빈 띠를 찾음
READY_LOOKBACK_S = 60      # 빈 띠를 못 찾으면 t_start = max(앞 판 마지막 버림 + PREV_GAP_S, 첫 버림 − 60초)
PREV_GAP_S = 5             # 앞 판 마지막 버림 + 5초 앞으로는 안 감(앞 판 공개)
# ---- t_ready(손으로는 "13장 줄이 서고 손이 떨어져 가만히 있는 첫 프레임")
READY_HOLD = 10            # 가만한 구간 최소 길이(장, 초당 10장 = 1초). r13 손 메모: 35.9 한 장 정지 뒤 손이 다시 얹힘 → 37.7(손 설정)을 고르려고 1초
READY_DET_PAD = 150        # 뒷면 상자를 찾는 곳 = band 를 줄 방향으로 ±150px(뽑은 패 · 떼어 둔 패 자리, bandfit 의 오른쪽 여유 100px 보다 조금 넓게)
READY_N = 13               # 줄 장수
READY_JOIN = 0.45          # slotgrid.JOIN 과 같음(이웃 상자 틈이 한 장 폭의 이 비율 이하면 한 덩어리)
READY_STABLE_S = 20        # 고른 구간 뒤 20초 안의 가만한 구간에서 줄이 다시 흩어지면(덩어리 ≤ 11) 버리고 다음 후보 — 2반장 w13(13장이 1.5초 섰다가
                           # 첫 버림 뒤 두 손으로 다시 정렬, 손 설정은 정렬 뒤 13:27:37.7)을 보고 넣음(본 판을 보고 정한 규칙)
READY_ARRANGE_FLAG_S = 20  # 고른 t_ready 바로 뒤 활동에서 띠가 이만큼 넘게 움직이면 "정리 전 줄일 수 있음" 질문(값은 안 바꿈). 2반장 w14 는
                           # 정리 전 줄(13:37:14.2) 뒤 30.7초 움직이고 정렬(손 설정 13:37:48.0) — 나머지 여덟 판의 고른 t_ready 뒤는 0 ~ 16.6초(w11). 본 판을 보고 정한 문턱
# ---- 공개(화료 판). 2반장 w11 · w12 를 보고 정함(본 판) — 흰 면 비율은 반 해상도 reveal_region, features.py 와 같은 HSV 문턱
REVEAL_BASE_S = 3          # 바탕 = 마지막 버림 앞 3초의 흰 면 비율 중앙값
REVEAL_SCAN_S = 45         # 마지막 버림 뒤 45초까지 봄(손 설정 reveal_frame 은 마지막 버림 뒤 2 ~ 22초)
REVEAL_HOLD = 10           # 가만한 구간 최소 길이(장)
REVEAL_D1 = 0.002          # 가만함 = 앞 프레임과 20단계 넘게 다른 화소 비율 ≤ 이것(segment ACT_DIFF 와 같은 값)
REVEAL_SKIN = 0.003        # 피부 ≤ 이것(segment ACT_SKIN)
REVEAL_RISE = 0.03         # 공개 = 흰 면이 바탕보다 0.03 이상(w11 +0.06 · w12 +0.11)
REVEAL_MIN_FACES = 6       # 그 프레임 reveal_region 안 검출기 앞면 상자 수(눕힌 손패) — 울기 셋(닫힌 4장)도 지나게 작게, 표시패 2 장만으로는 안 되게
DIFF = 20


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=indent))


# ------------------------------------------------------------------ 녹화 틀
FRAME_SRC = {   # 녹화 rec_20261114_125617 의 손 설정(2반장 r11 ~ r19 · L16 + 3반장 p01 ~ p03 · n01 ~ n08). r02 · r04 는 다른 녹화(1반장)라 뺌
    "h2_1114": ["r11_130921", "r12_131655", "r13_132644", "r14_133610", "r15_134151", "r16_135321", "L16_135321", "r17_140450", "r18_141259", "r19_142013"],
    "h3_1123": ["p01_143158", "p02_143539", "p03_144427", "n01_144748", "n02_145625", "n03_150528", "n04_151410", "n05_151953", "n06_152545",
                "n07_153010", "n08_153825"],
}


def frame_template(prefer: str = "h2_1114") -> dict:
    """자리 넷 × 영역 틀. 규칙: 같은 녹화 손 설정에서 가장 흔한 값 → 같으면 prefer 반장 판 값 중 가장 흔한 것 → 그래도 같으면 좌표별 중앙값.
    돌려주는 것: {"sides": {side: {영역: 값}}, "how": {side: {영역: 글}}, "exceptions": [...]}."""
    cfgs = {g: jl(HT / "config" / f"{g}.json") for v in FRAME_SRC.values() for g in v}
    han = {g: h for h, v in FRAME_SRC.items() for g in v}
    sides, how, exc = {}, {}, []
    for side in SIDES:
        gs = [g for g, c in cfgs.items() if c.get("side") == side]
        if not gs:
            continue
        sides[side], how[side] = {}, {}
        for k in REGIONS:
            vals = {g: tuple(cfgs[g][k]) for g in gs if cfgs[g].get(k)}
            cnt = Counter(vals.values())
            top = max(cnt.values())
            tied = [v for v, n in cnt.items() if n == top]
            rule = f"가장 흔한 값({top}/{len(vals)})"
            if len(tied) > 1:
                pv = Counter(v for g, v in vals.items() if han[g] == prefer and v in tied)
                if pv:
                    t2 = max(pv.values())
                    tied2 = [v for v, n in pv.items() if n == t2]
                    if len(tied2) < len(tied):
                        rule = f"가장 흔한 값 {len(tied)}개가 {top}/{len(vals)} 로 같아 {prefer} 판 값 중 가장 흔한 것({t2})"
                        tied = tied2
            if len(tied) > 1:
                val = [int(round(float(np.median([v[i] for v in tied])))) for i in range(4)]
                rule += f" · 그래도 {len(tied)}개가 같아 좌표별 중앙값"
            else:
                val = list(tied[0])
            sides[side][k] = val
            users = sorted(g for g, v in vals.items() if list(v) == val)
            how[side][k] = rule + f" — 같은 값 판 {users or '없음(중앙값)'}"
            for g, v in sorted(vals.items()):
                if list(v) != val:
                    exc.append({"side": side, "region": k, "game": g, "value": list(v), "template": val})
    return {"sides": sides, "how": how, "exceptions": exc}


def cmd_frame(a):
    t = frame_template()
    for s, v in t["sides"].items():
        print(f"== {s}")
        for k, x in v.items():
            print(f"  {k:14s} {x}  ← {t['how'][s][k]}")
    print("예외(틀과 다른 손 설정):")
    for e in t["exceptions"]:
        print(f"  {e['side']:6s} {e['region']:14s} {e['game']} {e['value']} (틀 {e['template']})")
    if a.write:
        p = ROOT / "experiments" / "paifu_frames" / "hanchan" / "h2_1114.json"
        d = jl(p)
        d["frame"] = {"_note": "녹화 틀(자리 넷 × 영역, 원본 1496 좌표) — handtrack_auto.py frame 이 같은 녹화(rec_20261114_125617)의 손 설정 21개"
                               "(2반장 r11 ~ r19 · L16, 3반장 p01 ~ p03 · n01 ~ n08)에서 뽑음: 가장 흔한 값 → 같으면 2반장 값 중 가장 흔한 것 → 그래도 같으면 좌표별 중앙값. "
                               "자동 패보 S6a 가 손패 주인 자리의 값을 판별 설정 영역으로 씀(sheet_band 는 판마다 bandfit). how = 값마다 근거, 예외는 handtrack_auto.py frame 출력",
                      "recording": "rec_20261114_125617", "sides": t["sides"], "how": t["how"]}
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=1))
        print("→", p)


# ------------------------------------------------------------------ 신호
def _half(ms: int) -> np.ndarray:
    from PIL import Image
    im = Image.open(hc.path_of(ms))
    im.draft("RGB", (im.width // 2, im.height // 2))
    return np.asarray(im.convert("RGB"))


def _masks(rgb):
    import cv2
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    return (s < 45) & (v > 170), (h >= 3) & (h < 32) & (s > 40) & (v > 70)


def region_series(box: list, t0: int, t1: int) -> list:
    """[t0, t1] 의 모든 프레임: (ms, 흰 면 비율, 피부 비율, d1) — 반 해상도 box(원본 좌표)."""
    import cv2
    x0, y0, x1, y1 = [v // 2 for v in box]
    out, prev = [], None
    for ms in hc.frame_range(t0, t1):
        g = _half(ms)[y0:y1, x0:x1]
        wh, sk = _masks(g)
        gr = cv2.cvtColor(g, cv2.COLOR_RGB2GRAY).astype(np.int16)
        d = float((np.abs(gr - prev) > DIFF).mean()) if prev is not None else 1.0
        prev = gr
        out.append((ms, float(wh.mean()), float(sk.mean()), d))
    return out


_READER = [None]


def reader():
    if _READER[0] is None:
        import dettrack as dt
        _READER[0] = dt.reader()
        _READER[0]._sessions()
    return _READER[0]


def back_boxes(ms: int, box: list, side: str) -> list:
    """뒷면 상자 중 중심이 box(원본) 안인 것 → 대국자 시점 [x0, x1, y0, y1](dettrack.boxes_view 와 같은 꼴)."""
    import dettrack as dt
    return dt.boxes_view(reader(), hc.load(ms), {"sheet_band": box, "side": side})


def face_count(ms: int, box: list) -> int:
    """검출기 앞면 상자 중 중심이 box(원본) 안인 것의 수."""
    res, _b, _p, _s = reader()._seat_raw(hc.load(ms))
    x0, y0, x1, y1 = box
    n = 0
    for (x, y, w, h), _rc in res:
        cx, cy = x + w / 2, y + h / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            n += 1
    return n


def biggest_cluster(bs: list) -> int:
    if not bs:
        return 0
    p = float(np.median([b[1] - b[0] for b in bs]))
    cl = []
    for b in sorted(bs):
        if cl and b[0] - cl[-1][1] <= READY_JOIN * p:
            cl[-1][1] = max(cl[-1][1], b[1])
            cl[-1][2] += 1
        else:
            cl.append([b[0], b[1], 1])
    return max(c[2] for c in cl)


def det_box(band: list, side: str) -> list:
    x0, y0, x1, y1 = band
    if side in ("left", "right"):
        return [x0, max(0, y0 - READY_DET_PAD), x1, min(1496, y1 + READY_DET_PAD)]
    return [max(0, x0 - READY_DET_PAD), y0, min(1496, x1 + READY_DET_PAD), y1]


def runs_of(mask) -> list:
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


# ------------------------------------------------------------------ 규칙
def box_count(ms: int, box: list) -> int:
    """검출기 앞면 + 뒷면 상자 중 중심이 box(원본) 안인 것의 수."""
    res, backs, _p, _s = reader()._seat_raw(hc.load(ms))
    n = 0
    for (x, y, w, h), _rc in list(res) + list(backs):
        if box[0] <= x + w / 2 <= box[2] and box[1] <= y + h / 2 <= box[3]:
            n += 1
    return n


def find_start(band: list, side: str, prev_last_ms: int | None, first_ms: int) -> dict:
    """t_start = 손패 띠가 빈 첫 구간(EMPTY_HOLD 번 이어서 상자 ≤ EMPTY_MAX)의 첫 프레임 — 앞 판 마지막 버림 + PREV_GAP_S ~ 이 판 첫 버림 사이."""
    lo = (prev_last_ms + PREV_GAP_S * 1000) if prev_last_ms else first_ms - FIRST_LOOKBACK_S * 1000
    box = det_box(band, side)
    run, seen = [], []
    for t in range(lo, first_ms + 1, EMPTY_STEP_MS):
        m = hc.nearest(t)
        n = box_count(m, box)
        seen.append(n)
        run = run + [m] if n <= EMPTY_MAX else []
        if len(run) >= EMPTY_HOLD:
            return {"ok": True, "ms": run[0], "rule": f"손패 띠가 빈 첫 때(1초마다 검출 상자 ≤ {EMPTY_MAX} 가 {EMPTY_HOLD}번, {hc.hms(lo)} ~ 첫 버림 {hc.hms(first_ms)} 사이)",
                    "samples": len(seen)}
    ms = max(lo, first_ms - READY_LOOKBACK_S * 1000)
    return {"ok": False, "ms": ms, "rule": f"빈 띠를 못 찾음 → max(앞 판 마지막 버림 + {PREV_GAP_S}초, 첫 버림 − {READY_LOOKBACK_S}초)", "samples": len(seen),
            "min_count": min(seen) if seen else None}


def find_reveal(side: str, reveal_region: list, last_ms: int, t_reveal_read: int | None, n_closed: int) -> dict:
    """공개 시각 · 공개 프레임. t_reveal_read(유국 S4 읽기)가 있으면 t_reveal 은 그것, reveal_frame 만 찾음."""
    t0 = last_ms - REVEAL_BASE_S * 1000
    ser = region_series(reveal_region, t0, last_ms + REVEAL_SCAN_S * 1000)
    base = float(np.median([w for ms, w, s, d in ser if ms <= last_ms])) if any(ms <= last_ms for ms, *_ in ser) else ser[0][1]
    after = [x for x in ser if x[0] > (t_reveal_read if t_reveal_read else last_ms)]
    still = np.array([d <= REVEAL_D1 and s <= REVEAL_SKIN for _, _, s, d in after])
    tried, rf = [], None
    for a, b in runs_of(still):
        if b - a + 1 < REVEAL_HOLD:
            continue
        ms, w = after[a][0], after[a][1]
        if w < base + REVEAL_RISE:
            tried.append({"t": hc.hms(ms), "white": round(w, 3), "why": "흰 면 낮음"})
            continue
        nf = face_count(ms, reveal_region)
        if nf < min(REVEAL_MIN_FACES, max(1, n_closed - 2)):
            tried.append({"t": hc.hms(ms), "white": round(w, 3), "faces": nf, "why": "앞면 상자 적음"})
            continue
        rf = {"ms": ms, "white": round(w, 3), "faces": nf, "hold": b - a + 1}
        break
    out = {"base_white": round(base, 3), "tried": tried[:6], "frames": len(ser)}
    if rf is None:
        out.update(ok=False, why=f"마지막 버림 뒤 {REVEAL_SCAN_S}초 안에 흰 면이 오른 가만한 구간이 없음")
        return out
    out.update(ok=True, reveal_frame_ms=rf["ms"], rf=rf)
    if t_reveal_read:
        out.update(t_reveal_ms=t_reveal_read, t_reveal_rule="S4 공개 읽기 t_reveal")
    else:
        half = base + (rf["white"] - base) / 2
        cross = next((ms for ms, w, s, d in ser if last_ms < ms <= rf["ms"] and w >= half), rf["ms"])
        out.update(t_reveal_ms=cross, t_reveal_rule=f"마지막 버림 뒤 흰 면이 바탕 {base:.3f} 과 공개 프레임 {rf['white']:.3f} 의 중간({half:.3f})을 처음 넘은 프레임")
    return out


def find_ready(gid: str, band: list, side: str, t_start_ms: int, first_ms: int, feat_path: Path) -> dict:
    """t_ready — features npz(band_d1 · band_d3 · band_skin)의 가만한 구간 + 뒷면 상자 13장 한 덩어리."""
    import segment as sgm
    z = np.load(feat_path)
    ms = z["ms"]
    keep = ms >= t_start_ms
    idx = np.flatnonzero(keep)
    d1, d3, sk = z["band_d1"][idx], z["band_d3"][idx], z["band_skin"][idx]
    mov = (d1 > sgm.ACT_DIFF) | (d3 > sgm.ACT_DIFF)
    box = det_box(band, side)
    tried, cache = [], {}

    def cl(i):
        m = int(ms[idx[i]])
        if m not in cache:
            cache[m] = biggest_cluster(back_boxes(m, box, side))
        return m, cache[m]
    for kind, still in (("손 없음", ~mov & ~(sk > sgm.ACT_SKIN)), ("피부 무시(손이 줄 끝에 얹힘)", ~mov)):
        rs = [(a, b) for a, b in runs_of(still) if b - a + 1 >= READY_HOLD]
        for k, (a, b) in enumerate(rs):
            for i in dict.fromkeys([a, (a + b) // 2]):
                m, n = cl(i)
                tried.append({"t": hc.hms(m), "kind": kind, "hold": b - a + 1, "cluster": n})
                if n != READY_N:
                    continue
                # 정리가 끝났나: 뒤 READY_STABLE_S 초 안에 시작하는 가만한 구간에서 줄이 다시 흩어지면(가장 큰 덩어리 ≤ READY_N − 2) 정리 중 잠깐 멈춘 것
                broke = None
                for a2, b2 in rs[k + 1:]:
                    if int(ms[idx[a2]]) - int(ms[idx[a]]) > READY_STABLE_S * 1000:
                        break
                    m2, n2 = cl(a2)
                    if n2 <= READY_N - 2:
                        broke = {"t": hc.hms(m2), "cluster": n2}
                        break
                if broke:
                    tried[-1]["rejected"] = f"{broke['t']} 에 줄이 다시 흩어짐(덩어리 {broke['cluster']})"
                    break
                # 고른 구간 바로 뒤 활동(다음 가만한 구간까지)에서 띠가 움직인 초 — 길면 정리 전 줄일 수 있어 질문(값은 그대로)
                nb = rs[k + 1][0] if k + 1 < len(rs) else len(idx)
                moved = round(float((d1[b + 1:nb] > sgm.ACT_DIFF).sum()) / 10, 1)
                return {"ok": True, "ms": int(ms[idx[a]]), "rule": kind, "hold": b - a + 1, "checked_at": hc.hms(m), "tried": len(tried),
                        "tried_head": tried[-8:], "rejected": [x for x in tried if x.get("rejected")], "after_moved_s": moved, "arrange_flag": moved >= READY_ARRANGE_FLAG_S,
                        "after_until": hc.hms(int(ms[idx[nb]])) if nb < len(idx) else None}
            if len(tried) > 400:
                break
    # 못 찾음 — 첫 버림 뒤 첫 가만한 구간(손 없음)
    still = ~mov & ~(sk > sgm.ACT_SKIN)
    cand = [(a, b) for a, b in runs_of(still) if b - a + 1 >= READY_HOLD and int(ms[idx[a]]) >= first_ms]
    m = int(ms[idx[cand[0][0]]]) if cand else first_ms
    return {"ok": False, "ms": m, "rule": "못 찾음 — 첫 버림 뒤 첫 가만한 구간" if cand else "못 찾음 — 첫 버림 시각", "tried": len(tried), "tried_head": tried[:8]}


# ------------------------------------------------------------------ conf(S6a 판 하나)
def configure(cfg_path: str | None):
    if cfg_path:
        cfg = hcfg.load(cfg_path, check=False)
        cfg.apply_recording(hc)
        htr.install(hc, cfg.ht_dir, cfg.ht_games)
        return cfg
    return None


def conf_one(spec: dict, out_dir: Path | None = None) -> dict:
    """spec: gid · side · side_rule · regions · prev_last_ms(앞 판 마지막 버림, 없으면 null) · first_ms · last_ms(이 판 첫 · 마지막 버림, 헤드 시계) ·
    t_reveal_read_ms(유국 S4 공개 읽기) · n_closed · result · riichi. out_dir 이 있으면(시험) 설정 · 특징을 거기에(리다이렉트 없이)."""
    gid, side = spec["gid"], spec["side"]
    R = spec["regions"]
    T = {"t0": time.time()}
    stt = find_start(R["band"], side, spec.get("prev_last_ms"), spec["first_ms"])
    t_start = stt["ms"]
    T["start"] = time.time()
    rv = find_reveal(side, R["reveal_region"], spec["last_ms"], spec.get("t_reveal_read_ms"), spec.get("n_closed", 13))
    T["reveal"] = time.time()
    if rv["ok"]:
        t_rev, rf = rv["t_reveal_ms"], rv["reveal_frame_ms"]
    else:   # 공개를 못 찾음 — 유국은 읽기 시각, 화료는 마지막 버림 + 2초(S1 과 같은 짐작), 공개 프레임은 + 3초
        t_rev = spec.get("t_reveal_read_ms") or spec["last_ms"] + 2000
        rf = t_rev + 3000
    post = max(4, math.ceil((rf - t_rev) / 1000 + 2))
    auto = [f"자동 side: {spec['side_rule']}",
            f"자동 영역: 반장 설정 frame.sides.{side}(녹화 틀) 그대로",
            f"자동 t_start: {stt['rule']} = {hc.hms(t_start)}",
            (f"자동 t_reveal: {rv['t_reveal_rule']} = {hc.hms(t_rev)}" if rv["ok"] else f"자동 t_reveal: 공개를 못 찾아 짐작 = {hc.hms(t_rev)} — {rv['why']}"),
            (f"자동 reveal_frame: 그 뒤 reveal_region 이 {rv['rf']['hold']}장 가만하고 흰 면 {rv['rf']['white']}(바탕 {rv['base_white']}) · 앞면 상자 {rv['rf']['faces']}장인 첫 프레임 = {hc.hms(rf)}"
             if rv["ok"] else f"자동 reveal_frame: 짐작(t_reveal + 3초) = {hc.hms(rf)}"),
            f"자동 post_sec: max(4, reveal_frame − t_reveal + 2초) = {post}"]
    cf = {"id": gid, "side": side, "t_start": hc.hms(t_start), "t_ready": hc.hms(t_start), "t_reveal": hc.hms(t_rev),
          "reveal_frame": hc.hms(rf), "post_sec": post, **{k: list(R[k]) for k in REGIONS},
          "result": spec.get("result"), "riichi": spec.get("riichi"), "auto": True, "auto_notes": auto,
          "winner_side_how": f"자동: {spec['side_rule']}", "result_how": f"자동: {spec.get('result_how', '')}"}
    cpath = (out_dir / "config" / f"{gid}.json") if out_dir else hc.CONFIG / f"{gid}.json"
    fpath = (out_dir / "_work" / f"{gid}_feat.npz") if out_dir else hc.WORK / f"{gid}_feat.npz"
    # features(구간 = t_start − 3초 ~ t_reveal + post_sec — t_ready 와 무관)
    if out_dir:
        wj(cpath, cf)
        _features_into(cf, fpath)
    else:
        hc.jsave(cpath, cf)        # ht_redirect 가 실행 폴더로
        if not Path(htr.remap(fpath)).exists():
            import features
            sys.argv = ["features.py", gid]
            features.main()
    T["features"] = time.time()
    rd = find_ready(gid, R["band"], side, t_start, spec["first_ms"], htr.remap(fpath) if not out_dir else fpath)
    T["ready"] = time.time()
    cf["t_ready"] = hc.hms(rd["ms"])
    if rd["ok"]:
        auto.append(f"자동 t_ready: t_start 뒤 band 가 {rd['hold']}장 이상 가만하고({rd['rule']}) 뒷면 상자 가장 큰 덩어리가 {READY_N}장인 첫 프레임 = {cf['t_ready']}"
                    f"(검사한 가만한 구간 {rd['tried']}곳)")
    else:
        auto.append(f"자동 t_ready: {rd['rule']} = {cf['t_ready']} — 뒷면 상자 {READY_N}장 한 덩어리인 가만한 구간이 없음(질문)")
    cf["auto_notes"] = auto
    cf["ready_note"] = auto[-1]
    if out_dir:
        wj(cpath, cf)
    else:
        hc.jsave(cpath, cf)
    timing = {"start_s": round(T["start"] - T["t0"], 1), "reveal_s": round(T["reveal"] - T["start"], 1), "features_s": round(T["features"] - T["reveal"], 1), "ready_s": round(T["ready"] - T["features"], 1)}
    return {"gid": gid, "config": cf, "start": stt, "reveal": rv, "ready": rd, "timing": timing}


def _features_into(cf: dict, fpath: Path):
    """시험용: features.main 과 같은 계산을 cf(설정 dict)로 — 공용 자리에 안 씀."""
    import features as ft
    orig_config, orig_save = hc.config, np.savez_compressed
    try:
        hc.config = lambda g: cf
        np.savez_compressed = lambda f, *x, **k: orig_save(fpath, *x, **k)
        fpath.parent.mkdir(parents=True, exist_ok=True)
        sys.argv = ["features.py", cf["id"]]
        ft.main()
    finally:
        hc.config, np.savez_compressed = orig_config, orig_save


def cmd_conf(a):
    configure(a.cfg)
    spec = jl(a.spec)
    res = conf_one(spec)
    print("JSON" + json.dumps(res, ensure_ascii=False))


def cmd_rules(a):
    """시험: spec(여러 판 목록 가능)의 규칙만 돌려 --out 에 설정 · 특징을 씀(리다이렉트 없음, 공용 자리에 안 씀)."""
    specs = jl(a.spec)
    specs = specs if isinstance(specs, list) else [specs]
    out = Path(a.out)
    rows = []
    for sp in specs:
        if sp.get("recording"):
            hcfg.Hanchan(Path(a.spec), {"results_dir": "x", "read_root": "x", "games": [sp["gid"]], "turn_prefix": {sp["gid"][:3]: sp["gid"]},
                                        "recording": sp["recording"]}).apply_recording(hc)
        r = conf_one(sp, out_dir=out)
        rows.append(r)
        print(sp["gid"], "t_ready", r["config"]["t_ready"], r["ready"]["rule"], "· t_reveal", r["config"]["t_reveal"], "· rf", r["config"]["reveal_frame"], r["timing"], flush=True)
    wj(out / "rules_result.json", rows)


# ------------------------------------------------------------------ run(S6b 판 하나)
RUN_STEPS = ["segment", "river", "game", "bandfit"]


def run_one(gid: str, no_river: bool = False) -> dict:
    """segment · river · game(run.py 의 features 뒤 단계 — features 는 S6a 가 이미 돌림, sheets 는 대조표 그림이라 뺌) + bandfit --write.
    결과가 이미 있으면 그 단계는 건너뜀(멱등).
    (11-25, 설계서 8-13) no_river: 앱 기록 반장 — 강 읽기(river)를 안 돌림(차례 목록이 기록에서 옴). 설정에 reveal_region 이 없으면(기본 길 모드에서
    답에 공개 영역이 없음) game 도 안 돌림. 뺀 걸음은 skipped 칸에 적음(둘 다 없으면 이 칸 없음 — 옛 출력 그대로)."""
    od = Path(htr.remap(hc.OUT / gid / "segments.json")).parent
    outs = {"segment": od / "segments.json", "river": od / "river_states.json", "game": od / "game.json"}
    tm, done, skipped = {}, [], {}
    cf0 = hc.config(gid)
    for st in RUN_STEPS:
        if st == "river" and no_river:
            skipped[st] = "앱 기록 반장 — 차례 목록은 기록에서(han3 rturns)"
            continue
        if st == "game" and "reveal_region" not in cf0:
            skipped[st] = "reveal_region 없음 — 공개 손패를 영역으로 안 읽음(끝 손패는 판 결과 값)"
            continue
        if st == "bandfit":
            if "sheet_band" in hc.config(gid):
                continue
        elif outs[st].exists():
            continue
        t0 = time.time()
        m = __import__(st)
        sys.argv = [f"{st}.py", gid] + (["--write"] if st == "bandfit" else [])
        m.main()
        tm[st] = round(time.time() - t0, 1)
        done.append(st)
    out = {"gid": gid, "ran": done, "timing": tm, "sheet_band": hc.config(gid).get("sheet_band"), "dir": od.as_posix()}
    if skipped:
        out["skipped"] = skipped
    return out


def cmd_run(a):
    configure(a.cfg)
    res = run_one(a.gid, no_river=a.no_river)
    print("JSON" + json.dumps(res, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("frame")
    p.add_argument("--write", action="store_true")
    p = sp.add_parser("conf")
    p.add_argument("--cfg", required=True)
    p.add_argument("--spec", required=True)
    p = sp.add_parser("run")
    p.add_argument("--cfg", required=True)
    p.add_argument("gid")
    p.add_argument("--no-river", action="store_true", help="(11-25) 앱 기록 반장: 강 읽기 걸음을 안 돌림(차례 목록은 기록에서)")
    p = sp.add_parser("rules")
    p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    {"frame": cmd_frame, "conf": cmd_conf, "run": cmd_run, "rules": cmd_rules}[a.cmd](a)


if __name__ == "__main__":
    main()
