"""남의 쯔모기리 B0 — 칸 틀 사건 목록 · 코드 판정(V1)을 hero 아닌 자리로 넓히고, 코드만으로 정해지는 물량을 센다(2026-11-22, 설계서 paifu_fill_scores_tsumogiri_design_1122.md 5절).
LLM 호출 없음 · 0달러. 검출기 = 운영 tile-obb-r8 뒷면 상자(dettrack.reader), 가림 = pixtrack.masks 손 · 소매 열(slotgrid.occ_cols 와 같은 계산).

  python -X utf8 tsumokind.py cfg <자리 이름…>                 # 시험 자리 config(handtrack/config/<이름>.json, 새 파일만) — 같은 쪽 config 의 깊이 띠 + 이 판 프레임으로 줄 방향 sheet_band
  python -X utf8 tsumokind.py turns <자리 이름…>               # 기록기 강(겹쳐 보기 재생)으로 그 자리 차례를 긋는다 → _work/tsumo_b0_1122/turns_<이름>.json
  python -X utf8 tsumokind.py detect <판 id> --seats a,b [--step 2]   # 판 하나의 프레임을 한 번 검출(전체 뒷면 상자) → raw_<판>.json, 자리마다 slotgrid 꼴 det/det_<자리>.json
  python -X utf8 tsumokind.py hero                             # hero 정답 117차례 다시 세기(저장된 검출 캐시 _work/slotgrid_1117/det_*.json, 없는 r11 · r14 는 위 detect 결과)
  python -X utf8 tsumokind.py selfcheck <판 id…>               # 같은 hero 자리를 "기록기 강만으로 그은 차례"(시험 자리와 같은 길)로 다시 판정해 turncut 차례 판정과 맞댐
  python -X utf8 tsumokind.py seats                            # 시험 자리 다섯 물량(정답 없음 — 정확도 안 셈)
  python -X utf8 tsumokind.py events <자리 이름> [--ids …]      # slotgrid.cmd_events 그대로(사건 목록 글) — 눈 확인용
  python -X utf8 tsumokind.py snap <자리 이름> <차례 id> [--n 6]  # 그 차례 창의 띠 그림 몇 장(칸 틀 · 칸 상태 표시) → _work/tsumo_b0_1122/snap/

자리 이름: hero 자리는 판 id(config 그대로), 시험 자리는 x_<판 앞글자>_<쪽>(예: x_r13_top — 기존 config 이름과 겹치지 않음).
코드 판정(slotroute 와 같은 신호 · 같은 규칙 RULE = V1 <= 0):
  규칙(읽지 않음): 그 자리 리치 선언(가로 패) 뒤 = 쯔모기리, 울기 직후 버림 = 손에서 냄.
  그 밖: 시작 줄을 못 잡음(slotgrid.anchor None) 또는 검출 프레임 없음 → 판정 불가 · V1 = 0 → 쯔모기리 확정 · V1 > 0 → 읽어야 함.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dtm
import io
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402
import slotgrid as sg  # noqa: E402
import slotroute as sr  # noqa: E402
import turncut as tc  # noqa: E402

OUTD = hc.WORK / "tsumo_b0_1122"
DETD = OUTD / "det"
RES = hc.OUT.parent                      # experiments/paifu_frames/results
HERO_DET = hc.WORK / "slotgrid_1117"     # 저장된 hero 검출 캐시(읽기만)

# 시험 정답을 만들 자리(설계서 5절, B0 결과를 보기 전에 고름): 이름 → (판, 쪽, 깊이 띠를 가져올 같은 쪽 config)
SEATS = {
    "x_r13_top": ("r13_132644", "top", "n05_151953"),
    "x_r12_top": ("r12_131655", "top", "n05_151953"),
    "x_r11_bottom": ("r11_130921", "bottom", "r12_131655"),
    "x_r17_left": ("r17_140450", "left", "r18_141259"),
    "x_r18_right": ("r18_141259", "right", "r16_135321"),
    # 11-22 B1: 위쪽 가림 설정(occ_rows face)의 깨끗한 확인용 — 다른 위쪽과 같은 방법 그대로, 이 자리 프레임을 보고 고치지 않음
    "x_r15_top": ("r15_134151", "top", "n05_151953"),
}
# 기록기 재생 결과: 시험 자리는 11-21 밤 새 기본값(헛 칸 C 채택) 재생 ghost_slot_1121/default_after/<판>/dart_overlay.json(시각 있는 것 중 가장 새것 —
# v5 · dart_examples 는 r13 위 · r17 위에서 칸 순서가 섞여 차례 위반이 있었음). hero 차례(turncut)는 v2 로 그어져 있다 — selfcheck 는 v2 로 같은 조건을 맞춘다.
NEW_DIR = "ghost_slot_1121/default_after"
LAST_END_MS = 10000      # 그 자리 마지막 버림 뒤 창 끝(다음 차례 경계가 없을 때)
FIRST_PRE_MS = 20000     # 앞선 남의 버림이 없을 때(친의 첫 버림) 창 시작 = 버림 − 이만큼
PRE_REC_MS = 3500        # 겹쳐 보기 첫 두 프레임(약 3초 간격) 안에 처음 보인 버림 = 기록기 추적 전 버림(시각 · 차례 경계를 모름)


# ------------------------------------------------------------------ 공통
def seat_game(name: str) -> tuple[str, str]:
    if name in SEATS:
        return SEATS[name][0], SEATS[name][1]
    return name if not name.startswith("L16") else "r16_135321", hc.config(name)["side"]


def overlay_paths(gid: str, ver: str) -> tuple[Path, Path]:
    """ver = "new"(시험 자리 — NEW_DIR) 또는 "v2"(selfcheck — turncut 과 같은 것)."""
    key = "r11" if gid.startswith("r11") else f"h{gid[1:]}"
    dump = RES / key / "overlay_dump.json"
    if ver == "new":
        return RES / NEW_DIR / key / "dart_overlay.json", dump
    return RES / key / f"dart_overlay_{ver}.json", dump


def save_lf(p: Path, txt: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(txt.encode("utf-8"))


# ------------------------------------------------------------------ 자리 차례 긋기(turncut.build_game 의 경계 규칙을 아무 자리로)
def seat_turns(name: str, ver: str = "new") -> list:
    gid, side = seat_game(name)
    ov, dump = overlay_paths(gid, ver)
    d = json.load(open(ov, encoding="utf-8"))
    ft = [int(dtm.datetime.fromisoformat(f["at"]).timestamp() * 1000) for f in json.load(open(dump, encoding="utf-8"))["frames"]]
    day = dtm.datetime.fromtimestamp(ft[0] / 1000).date()

    def T(s):
        h, m, x = s.split(":")
        return int(dtm.datetime(day.year, day.month, day.day, int(h), int(m), int(x)).timestamp() * 1000)

    def seen_prev(t_ms):
        i = min(range(len(ft)), key=lambda k: abs(ft[k] - t_ms))
        return ft[i], ft[max(i - 1, 0)]

    ev = sorted((T(s["first_at"]), sd, s["i"], s["tile"], bool(s.get("sideways")), T(s["taken_at"]) if s.get("taken_at") else None)
                for sd, v in d.items() for s in v["slots"])
    mine = [e for e in ev if e[1] == side]
    turns, calls, riichi = [], 0, False
    bounds = []
    for h, e in enumerate(mine):
        prev_t = mine[h - 1][0] if h else None
        mid = [x for x in ev if x[1] != side and (prev_t is None or prev_t < x[0]) and x[0] < e[0]]
        if mid:
            start, by = seen_prev(mid[-1][0])[1], f"{mid[-1][1]} {mid[-1][2]}번째 버림 앞"
        else:
            start, by = (prev_t + 1000, "앞 버림 뒤 1초(사이 남의 버림 없음)") if prev_t else (e[0] - FIRST_PRE_MS, f"버림 {FIRST_PRE_MS // 1000}초 앞(앞선 남의 버림 없음)")
        bounds.append((start, by))
    for h, e in enumerate(mine):
        prev_t = mine[h - 1][0] if h else None
        start, by = bounds[h]
        end = bounds[h + 1][0] if h + 1 < len(mine) else min(e[0] + LAST_END_MS, ft[-1] + 3000)
        if end <= start:
            end = e[0] + 2000
        # 울기 직후: 울려 간 패(남의 강, taken_at 있음)가 강에 처음 보인 시각보다 **엄격히 뒤**의 첫 버림이 이 자리의 이 버림이다.
        # (taken_at 은 늦게 찍힌다 — r11 위 5z 는 우는 사람 버림보다 4초 늦음. 같은 초에 찍힌 남의 버림은 앞선 것으로 안 침. 리치 뒤 자리는 못 운다.)
        # 11-21 울기 정답(ghost_slot_1121/truth_taken.json)과 맞는지는 seats 보고에 적는다.
        call = False
        if not riichi:
            for x in ev:
                if x[5] is None or x[1] == side or (prev_t is not None and x[0] < prev_t - 3000):
                    continue
                nxt = next((y for y in ev if y[0] > x[0] and y[1] != x[1]), None)
                if nxt is not None and nxt[1] == side and nxt[0] == e[0] and nxt[2] == e[2]:
                    call = True
        pre_rec = e[0] <= ft[0] + PRE_REC_MS
        hi, _ = seen_prev(e[0])
        n = 13 - 3 * calls
        turns.append({"id": f"{name}_d{h + 1:02d}", "label": str(h + 1), "game": gid, "side": side, "tile": e[3], "sideways": e[4],
                      "riichi_after": riichi, "call": call, "pre_record": pre_rec, "n_calc": n,
                      "meld_tiles": [3 * calls, 3 * (calls + call)] if (calls or call) else [0, 0],
                      "segs": [{"seg": 0, "role": "버림", "t0": hc.hms(start)[3:], "frames": [start, max(start, end - 1)]}],
                      "cut": {"start": hc.hms(start)[3:], "end": hc.hms(end)[3:], "by": by, "discard": hc.hms(hi)[3:], "discard_how": "기록기가 강에서 처음 본 프레임"},
                      "first_seen_ms": hi})
        calls += call
        riichi = riichi or e[4]
    return turns


# ------------------------------------------------------------------ config(시험 자리)
def row_depth_stats(L, gid: str, side: str, band: list, ts: list) -> tuple[list, list]:
    """프레임 몇 장에서 band 깊이 ± 60 · 줄 방향 ± 260 안의 뒷면 상자 → (깊이 가운데들, (줄 방향 최소, 최대) 들)."""
    x0, y0, x1, y1 = band
    if side in ("left", "right"):
        box = [x0 - 60, max(0, y0 - 260), x1 + 60, min(1496, y1 + 260)]
    else:
        box = [max(0, x0 - 260), y0 - 60, min(1496, x1 + 260), y1 + 60]
    dep, ext = [], []
    for ms in ts:
        _, backs, _, _ = L._seat_raw(hc.load(ms))
        bs = []
        for (x, y, w, h), _rc in backs:
            cx, cy = x + w / 2, y + h / 2
            if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                bs.append((x, y, w, h))
        if len(bs) < 6:
            continue
        if side in ("left", "right"):
            dep += [x + w / 2 for x, y, w, h in bs]
            ext.append((min(y for x, y, w, h in bs), max(y + h for x, y, w, h in bs), len(bs)))
        else:
            dep += [y + h / 2 for x, y, w, h in bs]
            ext.append((min(x for x, y, w, h in bs), max(x + w for x, y, w, h in bs), len(bs)))
    return dep, ext


def cmd_cfg(a):
    import dettrack as dt
    L = dt.reader()
    L._sessions()
    for name in a.names:
        f = hc.CONFIG / f"{name}.json"
        if f.exists() and not a.force:
            print(f"{name}: config 가 이미 있음 — 그대로 둠(--force 로 다시)")
            continue
        gid, side, src = SEATS[name]
        gc, sc = hc.config(gid), hc.config(src)
        band = list(sc["band"])
        t0, t1 = hc.to_ms(gc["t_ready"]) + 5000, hc.to_ms(gc["t_reveal"]) - 5000
        ts = [hc.nearest(int(t)) for t in np.linspace(t0, t1, a.n)]
        dep, ext = row_depth_stats(L, gid, side, band, ts)
        d0, d1 = (band[0], band[2]) if side in ("left", "right") else (band[1], band[3])
        dmed = float(np.median(dep))
        half = (d1 - d0) / 2
        # 11-22 처음엔 줄 가운데가 띠 가운데 60% 밖이면 띠를 줄 가운데로 옮겼으나, 옮긴 위 · 왼 · 오른 띠에 펠트 홈(탁자 안쪽 사각 홈)이 들어가
        # 가림(손 · 소매 열)이 차례 내내 줄 전체에 잡혀 시작 줄을 못 잡음(x_r13_top 13/18). hero 띠는 홈을 피해 그려져 있으므로 옮기지 않는다 — 줄이 띠 안인지만 적는다.
        inside = d0 + 0.15 * (d1 - d0) <= dmed <= d1 - 0.15 * (d1 - d0)
        moved = f" · 줄 가운데가 띠 양끝 15% 안쪽인가: {'예' if inside else '아니오(띠 끝 가까움)'}"
        lo = np.array([e[0] for e in ext])
        hi = np.array([e[1] for e in ext])
        lo_p, hi_p = float(np.percentile(lo, 2)), float(np.percentile(hi, 98))
        inc_right = side in ("bottom", "left")                    # 원본 축 증가 = 대국자 오른쪽(bandfit 과 같음)
        if inc_right:
            a0, a1 = max(0, lo_p - 40), min(1496, hi_p + 100)
        else:
            a0, a1 = max(0, lo_p - 100), min(1496, hi_p + 40)
        sb = [band[0], int(a0), band[2], int(a1)] if side in ("left", "right") else [int(a0), band[1], int(a1), band[3]]
        cfg = {"id": name, "game": gid, "side": side, "t_start": gc["t_start"], "t_ready": gc["t_ready"], "t_reveal": gc["t_reveal"],
               "post_sec": gc.get("post_sec", 4), "band": band, "sheet_band": sb,
               "how": (f"tsumokind.py cfg(11-22): 깊이 띠 = {src} 의 band({sc['band']}, 같은 카메라 — 테두리 위상상관 이동 0.4px 이하){moved}. "
                       f"줄 방향 sheet_band = 이 판 {gid} 의 {gc['t_ready']} + 5초 ~ {gc['t_reveal']} − 5초 고르게 {a.n}장(뒷면 상자 6개 이상인 {len(ext)}장)에서 "
                       f"깊이 띠 ± 60 · 줄 방향 ± 260 안 뒷면 상자의 줄 방향 끝 2 · 98백분위 {lo_p:.0f} ~ {hi_p:.0f}(최소 · 최대 {lo.min():.0f} ~ {hi.max():.0f}) + 대국자 왼쪽 40 · 오른쪽 100px(bandfit 과 같은 여유). "
                       f"상자 깊이 가운데 중앙 {dmed:.0f}(띠 {d0}~{d1}), 장수 중앙 {float(np.median([e[2] for e in ext])):.0f}"),
               "notes": ["시험 자리(B1 정답 만들 자리) — 프레임으로 규칙을 다듬지 않음. 물량 · 사건 목록이 나오는지 확인용"]}
        if side == "top":   # 11-22 위쪽은 모두 같은 가림 행(x_r13_top 에서 정함 — tsumokind.occ_of). x_r15_top 은 이 기본으로만 만듦
            cfg["occ_rows"] = "face"
            cfg["occ_rows_note"] = "위쪽 기본(cfg 가 자동으로 넣음): 가림 행 = 흰 면 가운데(y0 + h/2) ~ y1 + h/2 (tsumokind.occ_of, x_r13_top 프레임에서 정한 값)"
        hc.jsave(f, cfg)
        print(name, json.dumps({k: cfg[k] for k in ("band", "sheet_band")}), cfg["how"])


# ------------------------------------------------------------------ 검출
class SeatRow:
    """occ_cols 에 쓰는 줄 높이(흰 면 행) — pixtrack.Row 와 같은 계산, 정지 구간 대신 띠 피부가 가장 적은 프레임으로."""

    def __init__(self, name: str):
        self.cfg = hc.config(name)
        if (hc.OUT / name / "segments.json").exists():
            r = pt.Row(name)
            self.y0, self.y1, self.how = r.y0, r.y1, "pixtrack.Row(segments.json 가장 긴 정지)"
            return
        t0, t1 = hc.to_ms(self.cfg["t_ready"]) + 5000, hc.to_ms(self.cfg["t_reveal"]) - 5000
        best = None
        for t in np.linspace(t0, t1, 40):
            ms = hc.nearest(int(t))
            v = hc.band_crop(hc.load(ms), self.cfg["sheet_band"], self.cfg["side"])
            sk = float(pt.masks(v)[0].mean())
            if best is None or sk < best[0]:
                best = (sk, ms, v)
        _, felt, white, back = pt.masks(best[2])
        rows = np.flatnonzero(white.mean(1) > 0.08)
        b, cur = None, None
        for y in rows:
            cur = [y, y] if cur is None or y != cur[1] + 1 else [cur[0], y]
            if b is None or cur[1] - cur[0] > b[1] - b[0]:
                b = list(cur)
        self.y0, self.y1 = (int(b[0]), int(b[1])) if b else (0, best[2].shape[0] - 1)
        self.how = f"띠 피부 가장 적은 프레임 {hc.hms(best[1])}(피부 {best[0]:.3f})의 흰 면 행"


def occ_of(r: "SeatRow", v: np.ndarray) -> list:
    """가림 열. 기본 = slotgrid.occ_cols 그대로(행 y0 − h ~ y1 + h/2). config "occ_rows": "face" 면 행을 흰 면 가운데(y0 + h/2) ~ y1 + h/2 로 —
    위 자리는 패 줄의 탁자 가운데 쪽에 어두운 그림자 띠가 있어(조명) 기본 행 범위에서 줄 오른쪽 절반이 늘 가림으로 잡혔다(11-22 x_r13_top 프레임에서 봄)."""
    if r.cfg.get("occ_rows") != "face":
        return sg.occ_cols(r, v)
    skin = pt.masks(v)[0]
    h = r.y1 - r.y0
    col = skin[r.y0 + h // 2:r.y1 + h // 2].mean(0) > 0.08
    out, x, W = [], 0, len(col)
    while x < W:
        if col[x]:
            a = x
            while x < W and col[x]:
                x += 1
            out.append([a, x])
        else:
            x += 1
    return out


def view_boxes(backs: list, cfg: dict) -> list:
    """dettrack.boxes_view 와 같은 꼴(sheet_band 안 가운데 → 대국자 시점 [x0, x1, y0, y1])."""
    x0b, y0b, x1b, y1b = cfg["sheet_band"]
    out = []
    for x, y, w, h in backs:
        cx, cy = x + w / 2, y + h / 2
        if not (x0b <= cx <= x1b and y0b <= cy <= y1b):
            continue
        p = [hc.to_view_xy(q, cfg["sheet_band"], cfg["side"]) for q in ((x, y), (x + w, y + h))]
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        out.append([round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1)])
    return sorted(out)


def turns_for(name: str) -> list:
    if name in SEATS:
        return hc.jload(OUTD / f"turns_{name}.json")["turns"]
    if name == "r11_130921":
        return hc.jload(OUTD / "turns_hero_r11.json")["turns"]
    return tc.turns_of(name)


def cmd_detect(a):
    import dettrack as dt
    gid = a.game
    seats = a.seats.split(",")
    rows = {s: SeatRow(s) for s in seats}
    for s, r in rows.items():
        print(s, "줄 높이", r.y0, r.y1, r.how, flush=True)
    raw_f = OUTD / f"raw_{gid}.json"
    raw = hc.jload(raw_f) if raw_f.exists() else {}
    want = set()
    for s in seats:
        for t in turns_for(s):
            if t.get("pre_record") or t.get("riichi_after") or t.get("call"):   # 규칙으로 정하는 차례 · 녹화 전은 안 잼(시험 자리만 이 칸이 있음)
                continue
            want |= set(hc.frame_range(*sg.window(t))[::a.step])
    todo = sorted(want - {int(k) for k in raw})
    print(gid, "검출할 프레임", len(todo), "(이미", len(raw), ")", flush=True)
    if a.dry:
        return
    L = dt.reader()
    L._sessions()
    t0 = time.time()
    for i, ms in enumerate(todo):
        rgb = hc.load(ms)
        _, backs, _, _ = L._seat_raw(rgb)
        rec = {"b": [[round(float(x), 1), round(float(y), 1), round(float(w), 1), round(float(h), 1)] for (x, y, w, h), _rc in backs], "o": {}}
        for s, r in rows.items():
            rec["o"][s] = occ_of(r, hc.band_crop(rgb, r.cfg["sheet_band"], r.cfg["side"]))
        raw[str(ms)] = rec
        if i % 300 == 0:
            print(gid, i, len(todo), f"{time.time() - t0:.0f}s", flush=True)
            hc.jsave(raw_f, raw, indent=None)
    hc.jsave(raw_f, raw, indent=None)
    print(gid, "검출 끝", len(todo), "장", f"{time.time() - t0:.0f}s", flush=True)
    write_seat_det(gid, seats)


def cmd_reocc(a):
    """config(띠)를 고친 자리의 가림 열만 다시(검출기는 안 돌림 — raw 의 전체 뒷면 상자는 띠와 무관)."""
    gid, seats = a.game, a.seats.split(",")
    rows = {s: SeatRow(s) for s in seats}
    raw_f = OUTD / f"raw_{gid}.json"
    raw = hc.jload(raw_f)
    t0 = time.time()
    for i, (k, v) in enumerate(raw.items()):
        if not any(s in v["o"] for s in seats) and not a.add:
            continue
        rgb = hc.load(int(k))
        for s, r in rows.items():
            v["o"][s] = occ_of(r, hc.band_crop(rgb, r.cfg["sheet_band"], r.cfg["side"]))
        if i % 500 == 0:
            print(gid, i, len(raw), f"{time.time() - t0:.0f}s", flush=True)
    hc.jsave(raw_f, raw, indent=None)
    print(gid, "가림 다시", len(raw), f"{time.time() - t0:.0f}s", " · ".join(f"{s} 줄 높이 {r.y0}~{r.y1} {r.how}" for s, r in rows.items()))
    write_seat_det(gid, seats)


def write_seat_det(gid: str, seats: list):
    raw = hc.jload(OUTD / f"raw_{gid}.json")
    DETD.mkdir(parents=True, exist_ok=True)
    for s in seats:
        cfg = hc.config(s)
        det = {k: {"b": view_boxes(v["b"], cfg), "o": v["o"][s]} for k, v in raw.items() if s in v["o"]}
        hc.jsave(DETD / f"det_{s}.json", det, indent=None)
        print(s, "det 프레임", len(det))


# ------------------------------------------------------------------ 판정
def load_det(name: str, prefer_saved: bool = True) -> dict | None:
    f = HERO_DET / f"det_{name}.json"
    if prefer_saved and f.exists():
        return {int(k): v for k, v in hc.jload(f).items()}
    f = DETD / f"det_{name}.json"
    return {int(k): v for k, v in hc.jload(f).items()} if f.exists() else None


def judge(t: dict, det: dict | None, riichi_after: bool, call: bool) -> tuple[str, dict | None]:
    """→ (판정, 신호). 판정: 규칙 리치 뒤 / 규칙 울기 직후 / 녹화 전 / 불가(검출 없음 · 시작 줄 없음) / 쯔모기리 확정 / 읽어야 함."""
    if riichi_after:
        return "규칙:리치 뒤", None
    if call:
        return "규칙:울기 직후", None
    if t.get("pre_record"):
        return "불가:녹화 전", None
    if det is None:
        return "불가:검출 없음", None
    w0, w1 = sg.window(t)
    if not any(w0 <= ms <= w1 for ms in det):
        return "불가:검출 없음", None
    sig = sr.signals(t["game"] if "game" in t else "", t, det)
    if sig is None:
        return "불가:시작 줄 없음", None
    return ("쯔모기리 확정" if sr.route(sig, sr.RULE) == "쉬움" else "읽어야 함"), sig


def extra_signals(t: dict, det: dict) -> dict | None:
    """규칙 후보용 덧신호(117 개발 자료로만 봄): 칸 사건(slot_events) · 당겨 메움(fill_kind) · 끝 칸 · 줄 상자 수."""
    n = t["n_calc"]
    w0, w1 = sg.window(t)
    frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
    an = sg.anchor(frs, n)
    if an is None:
        return None
    tr = sg.track(frs, n, an)
    ev, cur = sg.slot_events(tr, n)
    strong = [e for e in ev if not e["weak"]]
    inner_e = [e for e in strong if 1 <= e["slot"] <= n and e["to"] == "E"]
    pulls = []
    for e in strong:
        if e["to"] == "F" and 1 <= e["slot"] <= n:
            k = sg.fill_kind(tr, e.get("g"), e.get("f"), e["slot"])
            if k and k[0] in "LR":
                pulls.append(k[0])
    # 잇달아 빈 가장 긴 run(프레임) — 칸 1 ~ n
    maxrun = 0
    for i in range(1, n + 1):
        for a_, b_ in sr.runs([f["st"][i] == "E" for f in tr]):
            maxrun = max(maxrun, b_ - a_ + 1)
    # 안쪽 칸이 2프레임 이상 비어 있는 동안 끝 칸(n+1 · n+2 · 0)에 패가 있었나 = 뽑은 패를 옆에 둔 채 다른 패를 들었나
    lift_with_d = 0
    for i in range(1, n + 1):
        for a_, b_ in sr.runs([f["st"][i] == "E" for f in tr]):
            if b_ > a_ and any(tr[j]["st"][n + 1] == "F" or tr[j]["st"][n + 2] == "F" or tr[j]["st"][0] == "F" for j in range(a_, b_ + 1)):
                lift_with_d += 1
    dms = None
    if t["cut"].get("discard"):
        ds = sg.sec_of(t["cut"]["discard"])
        dms = min(tr, key=lambda f: abs((f["ms"] / 1000 - ds + 1800) % 3600 - 1800))["ms"]
    fs = t.get("first_seen_ms")                    # 기록기가 그 버림을 강에서 처음 본 겹쳐 보기 프레임(시험 자리에도 있는 기준)
    runs2 = []                                     # 안쪽 칸이 2프레임 이상 잇달아 빈 run 의 (시작 ms, 끝 ms)
    for i in range(1, n + 1):
        for a_, b_ in sr.runs([f["st"][i] == "E" for f in tr]):
            if b_ > a_:
                runs2.append((tr[a_]["ms"], tr[b_]["ms"]))
    e1 = [f["ms"] for f in tr if any(f["st"][i] == "E" for i in range(1, n + 1))]   # V1 이 센 프레임 시각
    end_full = [i for i in range(1, n + 1) if cur[i] == "F"]
    return {"n_inner_E_events": len(inner_e), "inner_E_slots": sorted({e["slot"] for e in inner_e}), "pulls": "".join(pulls),
            "maxrun": maxrun, "lift_with_d": lift_with_d, "end_inner_full": len(end_full),
            "E_rel_s": [round((e["ms"] - dms) / 1000, 1) for e in inner_e] if dms else [],
            "run2_fs_s": [[round((a_ - fs) / 1000, 1), round((b_ - fs) / 1000, 1)] for a_, b_ in sorted(runs2)] if fs else [],
            "e1_fs_s": [round((m - fs) / 1000, 1) for m in e1] if fs else [],
            "anchor_fs_s": round((an[4] - fs) / 1000, 1) if fs else None, "w0_fs_s": round((w0 - fs) / 1000, 1) if fs else None,
            "w1_fs_s": round((w1 - fs) / 1000, 1) if fs else None,
            "win_s": round((w1 - w0) / 1000, 1), "anchor_rel_s": round((an[4] - dms) / 1000, 1) if dms else None}


def hero_turns() -> dict:
    """정답 117차례가 든 판 → 차례 목록. r11 은 turncut 차례가 없어 turns_hero_r11.json(이 도구 hero-r11 으로 만듦)."""
    import sam2track as s1
    truth = s1.truth_all()
    games = sorted({v["game"] for v in truth.values()})
    out = {}
    for gid in games:
        out[gid] = turns_for(gid)
    return out, truth


def cmd_hero_r11(a):
    """turncut.build_game 과 같은 계산을 r11 에(r11 은 기록기 결과가 results/r11/dart_overlay_fix.json — h11 폴더가 없어 turncut 이 못 읽음).
    turncut 의 함수를 그대로 쓰되 rec_dir · 겹쳐 보기 파일 이름만 바꿔 끼운다(turns_cut.json · 프레임 폴더는 안 건드림)."""
    gid = "r11_130921"
    real_open = open

    def fake_open(p, *x, **k):
        p = str(p)
        if p.endswith("dart_overlay_v2.json") and "r11" in p:
            p = str(RES / "r11" / "dart_overlay_fix.json")
        return real_open(p, *x, **k)

    old_rd = tc.rec_dir
    tc.rec_dir = lambda g: RES / "r11" if g == gid else old_rd(g)
    import builtins
    builtins.open = fake_open
    try:
        g = tc.build_game(gid)
    finally:
        builtins.open = real_open
        tc.rec_dir = old_rd
    for t in g["turns"]:
        t["game"] = gid
    hc.jsave(OUTD / "turns_hero_r11.json", {"rule": "turncut.build_game(r11 은 dart_overlay_fix.json)", "games": [g], "turns": g["turns"]})
    print(gid, "차례", len(g["turns"]), "· 경계를 강으로 그은 차례", sum(t["cut"]["by"] != "옛 묶음" for t in g["turns"]))


def attach_first_seen(gid: str, ts: list):
    """hero 차례에 '기록기가 그 버림을 처음 본 프레임' 시각을 붙인다(시험 자리와 같은 기준 — 시험 자리엔 강 피부 버림 시각이 없다).
    v2(turncut 이 쓴 것, r11 은 새 기본값) 기록기 차례와 패 순서로 맞춤."""
    import difflib
    side = hc.config(gid)["side"]
    ver = "new" if gid.startswith("r11") else "v2"
    mine = seat_turns_named(real_game(gid), side, ver)
    sm = difflib.SequenceMatcher(None, [t["tile"] for t in ts], [m["tile"] for m in mine], autojunk=False)
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            ts[blk.a + k]["first_seen_ms"] = mine[blk.b + k]["first_seen_ms"]


def cmd_hero(a):
    hts, truth = hero_turns()
    rows = []
    for gid, ts in hts.items():
        det = load_det(gid)
        attach_first_seen(gid, ts)
        riichi = False
        for t in ts:
            t.setdefault("game", gid)
            u = truth.get(t["id"])
            if u is None:
                continue
            kind = u.get("kind")
            call = kind == "call"            # hero 울기 차례(정답 칸) — 기록 흐름에서는 울기 자리로 앎
            j, sig = judge(t, det, riichi, call)
            ex = extra_signals(t, det) if sig is not None else None
            rows.append({"id": t["id"], "game": gid, "side": hc.config(gid)["side"], "truth": kind, "judge": j, "riichi_after": riichi,
                         "sideways": bool(t.get("sideways")), "n": t["n_calc"],
                         "sig": None if sig is None else {k: sig[k] for k in ("V", "V1", "O", "X", "S", "NF", "anchor")}, "ex": ex,
                         "order_changed": bool(u.get("moves")) or (bool(u.get("order")) and [str(x) for x in u["order"]] != [str(i) for i in range(1, (u.get("n") or t["n_calc"]) + 1)])
                         if kind == "tsumogiri" else None,
                         "difficulty": sr.difficulty(u, t["n_calc"])[0]})
            riichi = riichi or bool(t.get("sideways"))
            # 리치 뒤 차례에도 V1 을 따로 잼(규칙으로 정하는 차례지만 V1 의 쯔모기리 쪽 흔들림을 보려고)
            if rows[-1]["judge"] == "규칙:리치 뒤" and det is not None:
                _, s2 = judge(t, det, False, False)
                rows[-1]["v1_if_read"] = None if s2 is None else s2["V1"]
    hc.jsave(OUTD / "hero_rows.json", rows)
    rep = hero_report(rows)
    save_lf(OUTD / "hero_report.txt", rep)
    print(rep)


def hero_report(rows: list) -> str:
    L = []
    log = L.append
    log("== hero 정답 117차례 — 코드 판정(V1 <= 0 → 쯔모기리 확정) 다시 세기 (개발 자료 · 본 판)")
    log("판정 칸: 확정 = 쯔모기리 확정, 조용 = 확정인데 정답 hand, 넘김 = 읽어야 함(V1 > 0), 불가 = 시작 줄 없음 · 검출 없음, 규칙 = 리치 뒤(쯔모기리) · 울기 직후(손에서)")
    log(f"{'판 · 쪽':22s} {'전체':>4s} | {'규칙 리치뒤':>9s} {'규칙 울기':>8s} | {'확정':>4s} {'조용':>4s} | {'넘김':>4s} (정답 T / H / 기타) | {'불가':>4s} (정답 T / H / 기타) | unseen · call")
    key = lambda r: (r["game"], r["side"])  # noqa: E731
    groups = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    tot = Counter()

    def line(nm, rs):
        c = Counter()
        for r in rs:
            j, k = r["judge"], r["truth"]
            c["all"] += 1
            if j == "규칙:리치 뒤":
                c["rr"] += 1
                c["rr_bad"] += k not in ("tsumogiri",)
            elif j == "규칙:울기 직후":
                c["rc"] += 1
                c["rc_bad"] += k not in ("call", "hand")
            elif j == "쯔모기리 확정":
                c["fix"] += 1
                c["quiet"] += k == "hand"
                c["fix_other"] += k not in ("tsumogiri", "hand")
            elif j == "읽어야 함":
                c["read"] += 1
                c["read_T"] += k == "tsumogiri"
                c["read_H"] += k == "hand"
                c["read_O"] += k not in ("tsumogiri", "hand")
            else:
                c["na"] += 1
                c["na_T"] += k == "tsumogiri"
                c["na_H"] += k == "hand"
                c["na_O"] += k not in ("tsumogiri", "hand")
            c["unseen"] += k == "unseen"
            c["call"] += k == "call"
        log(f"{nm:22s} {c['all']:4d} | {c['rr']:9d} {c['rc']:8d} | {c['fix']:4d} {c['quiet']:4d} | {c['read']:4d} ({c['read_T']:2d} / {c['read_H']:2d} / {c['read_O']}) | {c['na']:4d} ({c['na_T']} / {c['na_H']} / {c['na_O']}) | {c['unseen']} · {c['call']}"
            + (f"  ※ 규칙과 정답이 다름 {c['rr_bad'] + c['rc_bad']}" if c["rr_bad"] + c["rc_bad"] else ""))
        return c

    for k in sorted(groups):
        tot += line(f"{k[0]} {k[1]}", groups[k])
    for side in ("bottom", "right", "left"):
        rs = [r for r in rows if r["side"] == side]
        if rs:
            line(f"[쪽 합] {side}", rs)
    line("합", rows)
    # 넘김 · 불가 상세
    log("\n-- 확정 · 넘김 · 불가 차례 상세(정답 · V · V1 · 끝 붙임 여부)")
    for r in rows:
        if r["judge"].startswith("규칙"):
            continue
        s = r["sig"] or {}
        log(f"  {r['id']:9s} {r['judge']:10s} 정답 {r['truth']:9s} {r['difficulty']:3s}"
            + (f" V {s.get('V')} V1 {s.get('V1')} O {s.get('O')} X {s.get('X')}" if s else "")
            + (" 줄바꿈 쯔모기리" if r.get("order_changed") else ""))
    rr = [r for r in rows if r["judge"] == "규칙:리치 뒤"]
    v = [r.get("v1_if_read") for r in rr]
    log(f"\n-- 리치 뒤 {len(rr)}차례(정답 모두 {Counter(r['truth'] for r in rr)}) 를 규칙 없이 V1 로 판정했다면: V1 = 0 {sum(x == 0 for x in v if x is not None)} · V1 > 0 {sum(x > 0 for x in v if x is not None)} · 시작 줄 없음 {sum(x is None for x in v)}")
    log("   V1 > 0 인 리치 뒤 차례: " + ", ".join(f"{r['id']}(V1 {r.get('v1_if_read')})" for r in rr if (r.get("v1_if_read") or 0) > 0))
    L.extend(candidates(rows))
    return "\n".join(L) + "\n"


def candidates(rows: list) -> list:
    """규칙 후보 — **이 117차례(본 판)를 보고 고른 것**. 틀리게 확정 0 을 지키는 것만 '후보' 로 둔다."""
    L = []
    log = L.append
    rs = [r for r in rows if r["sig"] is not None and r["truth"] in ("tsumogiri", "hand")]
    nT, nH = sum(r["truth"] == "tsumogiri" for r in rs), sum(r["truth"] == "hand" for r in rs)
    log(f"\n== 규칙 후보(읽기 대상 중 시작 줄을 잡은 {len(rs)}차례: 정답 쯔모기리 {nT} · 손에서 {nH}) — ※ 이 차례들을 보고 다듬은 것(개발 자료, 시험 아님)")

    def tab(nm, pred_t, pred_h):
        tt = sum(1 for r in rs if pred_t(r) and r["truth"] == "tsumogiri")
        th = sum(1 for r in rs if pred_t(r) and r["truth"] == "hand")
        hh = sum(1 for r in rs if pred_h(r) and r["truth"] == "hand")
        ht = sum(1 for r in rs if pred_h(r) and r["truth"] == "tsumogiri")
        left = sum(1 for r in rs if not pred_t(r) and not pred_h(r))
        bad = [r["id"] for r in rs if (pred_t(r) and r["truth"] == "hand") or (pred_h(r) and r["truth"] == "tsumogiri")]
        log(f"  {nm:58s} | T 확정 {tt:2d}(틀림 {th}) · H 확정 {hh:2d}(틀림 {ht}) · 남는 읽기 {left:2d}/{len(rs)}" + (f" · 틀린 차례 {bad}" if bad else ""))

    no = lambda r: False  # noqa: E731
    V1 = lambda r: r["sig"]["V1"]  # noqa: E731
    V = lambda r: r["sig"]["V"]  # noqa: E731
    ex = lambda r, k: (r["ex"] or {}).get(k)  # noqa: E731
    tab("C0 지금(slotroute.RULE): V1 = 0 → T", lambda r: V1(r) == 0, no)
    tab("C1 V = 0 → T (2프레임 이상 빈 적 없음)", lambda r: V(r) == 0, no)
    for th in (1, 2, 3):
        tab(f"C2 V1 <= {th} → T", lambda r, th=th: V1(r) <= th, no)
    for m in (2, 3, 4, 6):
        tab(f"C3 V1 = 0 → T · 안쪽 칸 가장 긴 빈 run >= {m}프레임 → H", lambda r: V1(r) == 0, lambda r, m=m: (ex(r, "maxrun") or 0) >= m)
    tab("C4 V1 = 0 → T · 뽑은 패를 옆에 둔 채 안쪽 칸이 2프레임 이상 빔 → H", lambda r: V1(r) == 0, lambda r: (ex(r, "lift_with_d") or 0) >= 1)
    tab("C5 V1 = 0 → T · 당겨 메움(L/R) 있음 → H", lambda r: V1(r) == 0, lambda r: bool(ex(r, "pulls")))
    tab("C6 V1 = 0 → T · (C4 AND 당겨 메움) → H", lambda r: V1(r) == 0, lambda r: (ex(r, "lift_with_d") or 0) >= 1 and bool(ex(r, "pulls")))
    # C7: 버림을 처음 본 프레임(fs) 둘레에서 2프레임 이상 빈 run 이 시작 → H (줄 정리로 미리 뺀 것은 버림에서 먼 때라 거름)
    near = lambda r, lo, hi: any(lo <= s <= hi for s, _ in (ex(r, "run2_fs_s") or []))  # noqa: E731
    for lo, hi in ((-8, 0), (-6, 0), (-5, 0), (-4, 0)):
        tab(f"C7 V1 = 0 → T · 처음 본 때 [{lo:+d}, {hi:+d}]초에 시작한 2프레임 빈 run → H", lambda r: V1(r) == 0, lambda r, lo=lo, hi=hi: near(r, lo, hi))
    clean = lambda r, lo, hi: (ex(r, "e1_fs_s") is not None) and not any(lo <= x <= hi for x in ex(r, "e1_fs_s"))  # noqa: E731
    for lo, hi in ((-6, 2), (-8, 2), (-10, 3)):
        tab(f"C8 처음 본 때 [{lo:+d}, {hi:+d}]초에 빈 프레임 0 → T · C7[-6, 0] → H", lambda r, lo=lo, hi=hi: clean(r, lo, hi) and not near(r, -6, 0),
            lambda r: near(r, -6, 0))
    log("  차례별 덧신호(넘김 차례만): id 정답 | V1 · V · 가장 긴 빈 run · 끝 칸 둔 채 듦 · 당겨 메움 · 빈 칸들 · 버림(강 피부) 기준 빈 칸 사건 시각(초) · 처음 본 때 기준 2프레임 빈 run(초)")
    for r in rs:
        if V1(r) == 0:
            continue
        e = r["ex"] or {}
        log(f"    {r['id']:9s} {r['truth'][:4]:4s}{' 줄바꿈' if r.get('order_changed') else '      '} | {V1(r):3d} · {V(r)} · {e.get('maxrun')} · {e.get('lift_with_d')} · {e.get('pulls') or '-'} · {e.get('inner_E_slots')} · {e.get('E_rel_s')} · {e.get('run2_fs_s')}")
    # 창: 처음 본 때(fs) 기준. 손에서 낸 차례 — fs 앞 가장 가까운 2프레임 빈 run 의 시작
    hs = [r for r in rs if r["truth"] == "hand" and (r["ex"] or {}).get("run2_fs_s")]
    lead = []
    for r in hs:
        st = [s for s, _ in r["ex"]["run2_fs_s"] if s <= 1.0]
        lead.append(max(st) if st else None)
    got = [x for x in lead if x is not None]
    if got:
        log(f"\n== 창 줄이기(처음 본 때 기준) — 손에서 낸 {len(hs)}차례(2프레임 빈 run 있음) 중 처음 본 때 +1초 앞에서 시작한 가장 늦은 run 의 시작(초): "
            f"5 / 50 / 95백분위 {np.percentile(got, 5):+.1f} / {np.percentile(got, 50):+.1f} / {np.percentile(got, 95):+.1f} · 최소 {min(got):+.1f} · 없음 {lead.count(None)}")
        for lo in (-4, -6, -8, -10, -12):
            log(f"  [{lo:+d}, +1]초 안에서 시작: {sum(1 for x in got if x >= lo)}/{len(hs)}")
        ts_ = [r for r in rs if r["truth"] == "tsumogiri"]
        for lo, hi in ((-6, 2), (-8, 2), (-10, 3)):
            clean = sum(1 for r in ts_ if not any(lo <= x <= hi for x in (r["ex"] or {}).get("e1_fs_s") or []))
            log(f"  쯔모기리 {len(ts_)}차례 중 [{lo:+d}, {hi:+d}]초 안에 빈 프레임이 하나도 없는 것: {clean} (전체 창 V1 = 0 은 {sum(1 for r in ts_ if V1(r) == 0)})")
        w0 = [r["ex"]["w0_fs_s"] for r in rs if r["ex"] and r["ex"].get("w0_fs_s") is not None]
        w1 = [r["ex"]["w1_fs_s"] for r in rs if r["ex"] and r["ex"].get("w1_fs_s") is not None]
        log(f"  지금 창의 처음 본 때 기준 시작 · 끝(초, 중앙): {np.median(w0):+.1f} · {np.median(w1):+.1f}")
    # 창 줄이기: 손에서 낸 차례의 빈 칸 사건이 버림 시각 기준 어디에 있나
    rel = [x for r in rs if r["truth"] == "hand" for x in ((r["ex"] or {}).get("E_rel_s") or [])]
    first = [min(r["ex"]["E_rel_s"]) for r in rs if r["truth"] == "hand" and r["ex"] and r["ex"].get("E_rel_s")]
    last = [max(r["ex"]["E_rel_s"]) for r in rs if r["truth"] == "hand" and r["ex"] and r["ex"].get("E_rel_s")]
    wins = [r["ex"]["win_s"] for r in rs if r["ex"]]
    if rel:
        q = lambda v: f"{np.percentile(v, 5):+.1f} / {np.percentile(v, 50):+.1f} / {np.percentile(v, 95):+.1f} (최소 {min(v):+.1f} · 최대 {max(v):+.1f})"  # noqa: E731
        log(f"\n== 창 줄이기 — 손에서 낸 {len(first)}차례의 안쪽 칸 빔 사건 시각(버림 표시 기준 초, 5 / 50 / 95백분위)")
        log(f"  모든 사건 {len(rel)}개: {q(rel)}")
        log(f"  차례마다 첫 사건: {q(first)}")
        log(f"  차례마다 마지막 사건: {q(last)}")
        log(f"  지금 창 길이(초): 중앙 {np.median(wins):.1f} · p90 {np.percentile(wins, 90):.1f} · 최대 {max(wins):.1f}")
        for lo, hi in ((-6, 3), (-8, 4), (-10, 5), (-12, 6)):
            inside = sum(1 for r in rs if r["truth"] == "hand" and r["ex"] and r["ex"].get("E_rel_s") and min(r["ex"]["E_rel_s"]) >= lo and max(r["ex"]["E_rel_s"]) <= hi)
            log(f"  창 [{lo:+d}, {hi:+d}]초 안에 그 차례의 빈 칸 사건이 다 드는 손에서 낸 차례: {inside}/{len(first)}")
    return L


# ------------------------------------------------------------------ selfcheck: hero 자리를 시험 자리와 같은 길(기록기 강만)로
def cmd_selfcheck(a):
    import sam2track as s1
    truth = s1.truth_all()
    L = ["== selfcheck — hero 자리를 기록기 강(v2)만으로 차례를 긋고(시험 자리 길) turncut 차례 판정과 맞댐. 검출은 저장된 hero 캐시 + 모자란 프레임"]
    agree = Counter()
    for gid in a.games:
        side = hc.config(gid)["side"]
        mine = seat_turns_named(real_game(gid), side, "v2")
        ref = tc.turns_of(gid)
        det = load_det(gid)
        extra = load_det(f"sc_{gid}", prefer_saved=False) or {}
        det2 = {**det, **extra}
        # 기록기 차례 ↔ turncut 차례: 패 순서로 맞춤(turncut 과 같은 방식)
        import difflib
        sm = difflib.SequenceMatcher(None, [t["tile"] for t in ref], [t["tile"] for t in mine], autojunk=False)
        pair = {}
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                pair[blk.a + k] = blk.b + k
        riichi = False
        for i, t in enumerate(ref):
            t.setdefault("game", gid)
            u = truth.get(t["id"], {})
            j1, s1_ = judge(t, det, riichi, u.get("kind") == "call")
            m = mine[pair[i]] if i in pair else None
            if m is None:
                L.append(f"  {t['id']} 짝 없음")
                continue
            w0, w1 = sg.window(m)
            import bisect
            kn = sorted(det2)
            miss = sum(1 for ms in hc.frame_range(w0, w1)[::2]
                       if (lambda i: i >= len(kn) or kn[i] > ms + 150)(bisect.bisect_left(kn, ms - 150))) if not m.get("pre_record") else 0
            j2, s2_ = judge(m, det2, m["riichi_after"], m["call"])
            same = j1 == j2
            agree[(j1, j2)] += 1
            L.append(f"  {t['id']:9s} 정답 {u.get('kind', '-'):9s} | turncut {j1:10s} V1 {None if s1_ is None else s1_['V1']!s:>4} 창 {hc.mss(sg.window(t)[0])}~{hc.mss(sg.window(t)[1])}"
                     f" | 기록기 {j2:10s} V1 {None if s2_ is None else s2_['V1']!s:>4} 창 {hc.mss(w0)}~{hc.mss(w1)} 모자란 프레임 {miss}{'' if same else '  ← 다름'}"
                     + (f" | 규칙 riichi_after {m['riichi_after']} call {m['call']}" if (m['riichi_after'] or m['call']) else ""))
            riichi = riichi or bool(t.get("sideways"))
    L.append("\n맞댐(turncut 판정, 기록기 판정) → 수: " + " · ".join(f"{a_}/{b_} {v}" for (a_, b_), v in sorted(agree.items())))
    txt = "\n".join(L) + "\n"
    save_lf(OUTD / "selfcheck_report.txt", txt)
    print(txt)


def real_game(gid: str) -> str:
    return "r16_135321" if gid.startswith("L16") else gid


def seat_turns_named(gid: str, side: str, ver: str) -> list:
    """seat_turns 를 hero 판 id 로(SEATS 밖) 부르기."""
    SEATS[f"sc_{gid}"] = (gid, side, gid)
    try:
        ts = seat_turns(f"sc_{gid}", ver)
    finally:
        SEATS.pop(f"sc_{gid}")
    for t in ts:
        t["game"] = gid
    return ts


def cmd_sc_detect(a):
    """selfcheck 에 모자란 프레임만 검출(hero 자리 · hero config) → det/det_sc_<판>.json(저장된 캐시는 안 건드림)."""
    import dettrack as dt
    L = dt.reader()
    for gid in a.games:
        cfg, R = hc.config(gid), pt.Row(gid)
        import bisect
        det = load_det(gid)
        f = DETD / f"det_sc_{gid}.json"
        have = hc.jload(f) if f.exists() else {}
        known = sorted(set(det) | {int(k) for k in have})
        want = set()
        for m in seat_turns_named(real_game(gid), cfg["side"], "v2"):
            if m.get("pre_record") or m["riichi_after"]:
                continue
            for ms in hc.frame_range(*sg.window(m))[::2]:      # 저장된 캐시는 차례마다 [::2] 라 홀짝이 다르다 — ±150ms 안에 검출이 없는 프레임만
                i = bisect.bisect_left(known, ms - 150)
                if i >= len(known) or known[i] > ms + 150:
                    want.add(ms)
        todo = sorted(want)
        print(gid, "모자란 프레임", len(todo), flush=True)
        t0 = time.time()
        for i, ms in enumerate(todo):
            rgb = hc.load(ms)
            have[str(ms)] = {"b": dt.boxes_view(L, rgb, cfg), "o": sg.occ_cols(R, hc.band_crop(rgb, cfg["sheet_band"], cfg["side"]))}
            if i % 300 == 0:
                print(gid, i, len(todo), f"{time.time() - t0:.0f}s", flush=True)
                hc.jsave(f, have, indent=None)
        hc.jsave(f, have, indent=None)
        print(gid, "끝", len(todo), f"{time.time() - t0:.0f}s", flush=True)


# ------------------------------------------------------------------ 시험 자리 물량
def cmd_turns(a):
    for name in a.names:
        ts = seat_turns(name)
        hc.jsave(OUTD / f"turns_{name}.json", {"seat": name, "game": SEATS[name][0], "side": SEATS[name][1], "overlay": str(overlay_paths(SEATS[name][0], "new")[0].relative_to(RES)),
                                               "turns": ts})
        print(f"{name}: 버림 {len(ts)} · 리치 선언 {sum(t['sideways'] for t in ts)} · 리치 뒤 {sum(t['riichi_after'] for t in ts)} · 울기 직후 {sum(t['call'] for t in ts)} · 녹화 전 {sum(t['pre_record'] for t in ts)}")
        for t in ts:
            print(f"   {t['id']} {t['tile']:3s} n{t['n_calc']:2d} {t['cut']['start']}~{t['cut']['end']} 처음 봄 {t['cut']['discard']} {t['cut']['by']}"
                  + (" 리치선언" if t["sideways"] else "") + (" 리치뒤" if t["riichi_after"] else "") + (" 울기직후" if t["call"] else "") + (" 녹화전" if t["pre_record"] else ""))


def cmd_seats(a):
    L = ["== 시험 자리 — 물량(정답 없음 · 정확도 안 셈)",
         f"{'자리':14s} {'버림':>4s} | {'규칙 리치뒤':>9s} {'규칙 울기':>8s} | {'확정 T':>6s} {'읽기':>4s} {'불가':>4s} (녹화 전 · 검출 없음 · 시작 줄 없음) | 읽기 대상 중 확정 비율 · V1 중앙"]
    rows = []
    tot = Counter()
    for name in SEATS:
        f = OUTD / f"turns_{name}.json"
        if not f.exists():
            L.append(f"{name:14s} 차례 파일 없음")
            continue
        ts = hc.jload(f)["turns"]
        det = load_det(name, prefer_saved=False)
        c = Counter()
        v1s = []
        for t in ts:
            j, sig = judge(t, det, t["riichi_after"], t["call"])
            c[j] += 1
            ex = None
            if sig is not None:
                v1s.append(sig["V1"])
                ex = extra_signals(t, det)
                if j == "읽어야 함" and ex and any(-6 <= s <= 0 for s, _ in ex.get("run2_fs_s") or []):
                    c["C7_H"] += 1                     # 개발 자료에서 고른 후보 C7[-6, 0] 이 "손에서 냄" 으로 정했을 차례(물량만)
                if j == "읽어야 함" and ex and any(-4 <= s <= 0 for s, _ in ex.get("run2_fs_s") or []):
                    c["C7b_H"] += 1                    # 여유를 둔 C7[-4, 0](117 에서 가장 가까운 쯔모기리 run 시작 −6.5초와 2.5초 떨어짐)
            rows.append({"id": t["id"], "seat": name, "judge": j, "sig": None if sig is None else {k: sig[k] for k in ("V", "V1", "O", "X", "S", "NF", "anchor")},
                         "ex": ex, "window_s": round((sg.window(t)[1] - sg.window(t)[0]) / 1000, 1)})
        tot += c
        na = c["불가:녹화 전"] + c["불가:검출 없음"] + c["불가:시작 줄 없음"]
        tgt = c["쯔모기리 확정"] + c["읽어야 함"] + na
        L.append(f"{name:14s} {len(ts):4d} | {c['규칙:리치 뒤']:9d} {c['규칙:울기 직후']:8d} | {c['쯔모기리 확정']:6d} {c['읽어야 함']:4d} {na:4d} ({c['불가:녹화 전']} · {c['불가:검출 없음']} · {c['불가:시작 줄 없음']})"
                 f" | {c['쯔모기리 확정']}/{tgt} · {np.median(v1s) if v1s else '-'} | 읽기 중 C7[-6,0] · C7[-4,0] 이 H 로 정했을 것 {c['C7_H']} · {c['C7b_H']}")
    na = tot["불가:녹화 전"] + tot["불가:검출 없음"] + tot["불가:시작 줄 없음"]
    n_all = sum(v for k, v in tot.items() if k not in ("C7_H", "C7b_H"))
    L.append(f"{'합':14s} {n_all:4d} | {tot['규칙:리치 뒤']:9d} {tot['규칙:울기 직후']:8d} | {tot['쯔모기리 확정']:6d} {tot['읽어야 함']:4d} {na:4d} ({tot['불가:녹화 전']} · {tot['불가:검출 없음']} · {tot['불가:시작 줄 없음']})"
             f" | 읽기 중 C7[-6,0] · C7[-4,0] 이 H 로 정했을 것 {tot['C7_H']} · {tot['C7b_H']}")
    # 한 판 견적: 시험 자리 비율 × 남 세 자리(한 자리 평균 버림 수 = 다섯 자리 평균)
    per_seat = n_all / max(1, len(SEATS))
    rd = tot["읽어야 함"] + na
    for nm, rr in (("지금 규칙(V1)", rd), ("+ C7[-6,0] 손에서 확정", rd - tot["C7_H"]), ("+ C7[-4,0] 손에서 확정", rd - tot["C7b_H"])):
        f_ = rr / max(1, n_all)
        L.append(f"한 판 견적[{nm}]: 자리당 버림 {per_seat:.1f} × 3자리 = {3 * per_seat:.0f} · 읽기(+ 불가) 비율 {rr}/{n_all} = {f_:.0%} → 판당 읽기 약 {3 * per_seat * f_:.0f}차례"
                 f" · 토큰(차례 중앙 8.9만, 표 12-103 창 그대로) 약 {3 * per_seat * f_ * 8.9:.0f}만")
    ws = [r["window_s"] for r in rows if r["judge"] == "읽어야 함"]
    if ws:
        L.append(f"읽을 차례의 지금 창 길이(초): 중앙 {np.median(ws):.1f} · p90 {np.percentile(ws, 90):.1f} · 최대 {max(ws):.1f}")
    hc.jsave(OUTD / "seat_rows.json", rows)
    txt = "\n".join(L) + "\n"
    save_lf(OUTD / "seats_report.txt", txt)
    print(txt)


# ------------------------------------------------------------------ 눈 확인
def patch_sg(name: str):
    """slotgrid.cmd_events 를 시험 자리 차례 · 검출로 돌리게 끼워 넣기(slotgrid 파일은 안 바꿈)."""
    ts = turns_for(name)
    sg.game_of = lambda tid: name
    real = tc.turns_of
    tc.turns_of = lambda gid: ts if gid == name else real(gid)
    sg.OUT = DETD if (DETD / f"det_{name}.json").exists() else HERO_DET


def cmd_events(a):
    patch_sg(a.name)
    ids = a.ids.split(",") if a.ids else [t["id"] for t in turns_for(a.name) if not t.get("riichi_after") and not t.get("call") and not t.get("pre_record")]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sg.cmd_events(argparse.Namespace(ids=ids, count=True))
    txt = buf.getvalue()
    save_lf(OUTD / f"events_{a.name}.txt", txt)
    print(txt[:a.head] if a.head else txt)


def cmd_snap(a):
    from PIL import Image, ImageDraw
    name, tid = a.name, a.tid
    t = next(x for x in turns_for(name) if x["id"] == tid)
    cfg = hc.config(name)
    det = load_det(name, prefer_saved=False) or load_det(name)
    n = t["n_calc"]
    w0, w1 = sg.window(t)
    frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
    an = sg.anchor(frs, n)
    tr = sg.track(frs, n, an) if an else []
    pick = [tr[int(i)] for i in np.linspace(0, len(tr) - 1, a.n)] if tr else [{"ms": m, "st": None} for m, _ in frs[::max(1, len(frs) // a.n)][:a.n]]
    if a.at:
        want = [sg.sec_of(x) for x in a.at.split(",")]
        pick = [min(tr, key=lambda f: abs((f["ms"] / 1000 - s + 1800) % 3600 - 1800)) for s in want]
    ims = []
    for f in pick:
        v = hc.band_crop(hc.load(f["ms"]), cfg["sheet_band"], cfg["side"])
        im = Image.fromarray(v).convert("RGB")
        dr = ImageDraw.Draw(im)
        for b in det[f["ms"]]["b"]:
            dr.rectangle([b[0], b[2], b[1], b[3]], outline=(0, 255, 255), width=1)
        for o in det[f["ms"]]["o"]:
            dr.rectangle([o[0], 0, o[1], 6], fill=(255, 0, 0))
        if an and f.get("st"):
            left0, p = an[0] + f["drift"] * an[1], an[1]
            for i, s in enumerate(f["st"]):
                x0 = left0 + (i - 1) * p
                col = {"F": (0, 200, 0), "E": (255, 255, 0), "?": (255, 0, 0)}[s]
                dr.rectangle([x0 + 1, im.height - 14, x0 + p - 1, im.height - 2], outline=col, width=2)
                dr.text((x0 + 3, im.height - 28), f"{i}{s}", fill=col)
        dr.text((4, 8), f"{hc.mss(f['ms'])} n{n}", fill=(255, 255, 255))
        ims.append(im)
    W = max(i.width for i in ims)
    H = sum(i.height + 4 for i in ims)
    sheet = Image.new("RGB", (W, H), (30, 30, 30))
    y = 0
    for i in ims:
        sheet.paste(i, (0, y))
        y += i.height + 4
    out = OUTD / "snap" / f"{tid}{a.tag}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    print(out, "시작 줄", None if an is None else hc.mss(an[4]), "한 장 폭", None if an is None else round(an[1], 1))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("cfg")
    c.add_argument("names", nargs="+")
    c.add_argument("--n", type=int, default=60)
    c.add_argument("--force", action="store_true")
    t = sp.add_parser("turns")
    t.add_argument("names", nargs="+")
    d = sp.add_parser("detect")
    d.add_argument("game")
    d.add_argument("--seats", required=True)
    d.add_argument("--step", type=int, default=2)
    d.add_argument("--dry", action="store_true")
    sp.add_parser("hero")
    sp.add_parser("hero-r11")
    s = sp.add_parser("selfcheck")
    s.add_argument("games", nargs="+")
    s2 = sp.add_parser("sc-detect")
    s2.add_argument("games", nargs="+")
    sp.add_parser("seats")
    e = sp.add_parser("events")
    e.add_argument("name")
    e.add_argument("--ids", default="")
    e.add_argument("--head", type=int, default=0)
    n = sp.add_parser("snap")
    n.add_argument("name")
    n.add_argument("tid")
    n.add_argument("--n", type=int, default=6)
    n.add_argument("--at", default="")
    n.add_argument("--tag", default="")
    cl = sp.add_parser("clip")             # B1 확인 영상 — tsumopack.cmd_clip 그대로
    cl.add_argument("ids", nargs="+")
    cl.add_argument("--out", required=True)
    ro = sp.add_parser("reocc")
    ro.add_argument("game")
    ro.add_argument("--seats", required=True)
    ro.add_argument("--add", action="store_true")
    w = sp.add_parser("writedet")
    w.add_argument("game")
    w.add_argument("--seats", required=True)
    a = ap.parse_args()
    {"cfg": cmd_cfg, "turns": cmd_turns, "detect": cmd_detect, "hero": cmd_hero, "hero-r11": cmd_hero_r11, "selfcheck": cmd_selfcheck,
     "sc-detect": cmd_sc_detect, "seats": cmd_seats, "events": cmd_events, "snap": cmd_snap,
     "writedet": lambda a: write_seat_det(a.game, a.seats.split(",")), "reocc": cmd_reocc,
     "clip": lambda a: __import__("tsumopack").cmd_clip(a)}[a.cmd](a)


if __name__ == "__main__":
    main()
