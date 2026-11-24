"""헤드 녹화로 복구하는 반장(처음은 11-14 3반장, p01 ~ p03 · n01 ~ n08) 판을 손패 읽기 흐름(turncut → slotgrid → opusread → rebuild_opus)에 태우는 래퍼(2026-11-23).

기존 스크립트(turncut · sam2track · opusread · rebuild_opus · truthprep · slotgrid)는 고치지 않는다 — 다른 세션의 커밋 안 된 변경이 섞여 있어서.
여기서 그 모듈들을 import 한 뒤 **실행 중에만** 판 목록 · 파일 자리를 바꾸고 원래 main() 을 부른다.

11-24: 판 목록 · 경로 · 손 설정은 반장 설정 JSON(hanchan_cfg.py · experiments/paifu_frames/hanchan/*.json)에서 읽는다.
  모든 명령에 `--hanchan <json>`(안 주면 hanchan/h3_1123.json = 3반장) · `--prep <폴더>`(손패 재료 폴더 바꾸기 — 시험용, 안 주면 설정의 prep_dir)를 붙일 수 있다.
  아래 보기의 파일 이름(turns_han3.json · rawread_han3_1123 등)은 3반장 설정 값이다. 시작할 때 판 id · 차례 id 접두사가 기존 판과 겹치면 멈춘다.

  python -X utf8 han3.py turns [판…]                    # truthprep 꼴 차례 목록 → results/han3_1123/_prep/turns_han3.json (+ turn_fix.json 적용)
  python -X utf8 han3.py link <판…>                     # 기록기 결과를 turncut 이 읽는 자리로: _prep/rec/<판>/dart_overlay_v2.json · overlay_dump.json
  python -X utf8 han3.py fix <판…> [--write]            # 기록기 paifu_rec.json 과 차례 목록을 맞춰 turn_fix 후보(패 · 리치 · 울기 · 줄 장수)를 보임/씀
  python -X utf8 han3.py turncut build <판…>            # = turncut.py build --out _prep/turns_cut_han3.json(--out 을 안 주면 이 파일)
  python -X utf8 han3.py slotgrid detect <판…>          # = slotgrid.py detect(칸 틀 검출 캐시 _work/slotgrid_1117/det_<판>.json)
  python -X utf8 han3.py opusread prep --ids a,b --root rawread_han3_1123 --nosam --fromplan
  python -X utf8 han3.py rebuild <판…> --full --root rawread_han3_1123 [--json …]   # = rebuild_opus.py
  python -X utf8 han3.py ids <판>                       # 하위 에이전트에게 줄 차례 id(리치 뒤 · 울기 차례를 뺀 것)
  python -X utf8 han3.py status [판…]                   # 판마다 준비 상태
  python -X utf8 han3.py callprep [--ids a,b] [--root rawread_han3_1123]   # 울기 차례 읽기 재료(CALL_TURNS, 답: gone · k · end_order) — 복원은 patch 의 back_call 이 씀

실행 중에 바꾸는 것(patch):
  1. htcommon.jload: `_work/testtruth_1116/turns.json` 을 읽으면 원본 판들(3반장 판 id 는 뺌) + turns_han3.json 의 판을 합쳐 돌려준다(원본 파일은 안 바뀜).
     `HAN3_FINAL=result` 환경 변수면 `results/handtrack/<판>/game.json` 의 final_hand.closed 를 result_read.json 의 hand 로 바꿔 돌려준다.
  2. turncut.EXTRA 에 _prep/turns_cut_han3.json 을 더하고, turncut.rec_dir 를 3반장 판은 _prep/rec/<판>/ 로.
  3. sam2track.GAMES 에 3반장 판을 더함(차례 id 앞 세 글자 n01 ~ n08 로 판을 찾음 — 그래서 설정의 turn_prefix 는 판 id 앞 세 글자이고,
     sam2track.GAMES · 기존 판 목록 · 다른 반장 설정과 겹치면 시작할 때 멈춤).
  4. sam2track.truth_all: 정답 파일들 + turn_fix.json 의 "kind" 칸(3반장 판엔 정답이 없음 — 울기 차례를 rebuild_opus 의 "call" 처리로 보내려고).
  5. rebuild_opus.call_hand_tiles: turn_fix.json 에 "call_hand"(손에서 울기로 나간 패)가 있으면 그것을 씀(game.json meld_detail 의 cx 순 조각은
     울기가 둘 이상이면 시간 순과 어긋날 수 있음).
  6. pixtrack.Row: ROW_AT 의 판(n04)은 줄 높이를 잡을 프레임 시각을 손으로 줌(정지 상태가 공개 뒤 0.8초뿐이라).
turn_fix.json 은 `fix --write` 가 기록기(paifu_rec.json)에서 만든다 — 패 · 리치 · 줄 장수 · 울기 차례(kind "call" · call_hand) · 놓친 차례 끼우기(__insert__).
정답 · 읽기 답은 여기서 만들지 않는다. 시험으로 만든 것: _work/rawread_han3_test/n01_d02(prep 만, 읽기 없음).
"""
from __future__ import annotations

import difflib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import htcommon as hc  # noqa: E402
import hanchan_cfg as hcfg  # noqa: E402
import ht_redirect as htr  # noqa: E402

RES = hc.OUT.parent                       # experiments/paifu_frames/results
TURNS_ORIG = hc.WORK / "testtruth_1116" / "turns.json"
SIDES = ["bottom", "right", "top", "left"]

# ---- 반장 설정에서 오는 값(configure 가 채움 — 아래 줄 끝 주석은 3반장 설정 값)
CFG: "hcfg.Hanchan | None" = None
H3: list = []           # 판 목록(시간 순) — 3반장: p01 ~ p03 · n01 ~ n08
H3DIR = PREP = TURNS_H3 = CUT_H3 = FIX = None   # results/han3_1123 · _prep · _prep/turns_han3.json · _prep/turns_cut_han3.json · _prep/turn_fix.json
# FIX = {차례 id: {"tile", "sideways", "n_calc", "meld_tiles", "kind", "call_hand", "skip", "why"}}
READ_ROOT = None        # 읽기 폴더 이름(_work 아래) — 3반장: rawread_han3_1123
# pixtrack.Row(gid) 는 segments.json 의 가장 긴 정지 상태 한 프레임으로 줄 높이(흰 면 행)를 잡는다(slotgrid detect 의 가림 열 · 칸 틀이 이것을 씀).
# 3반장 n04 는 판 내내 두 손이 줄 위에 있어 정지 상태가 3개뿐이고 가장 긴 것(0.8초)이 공개 뒤라 줄 높이가 틀림(y 0 ~ 18) → 손이 줄에서 떨어진 프레임 시각을 줌.
ROW_AT: dict = {}       # 3반장: {"n04_151410": "15:14:53.9"} — 13장 줄이 서고 두 손이 줄 양 끝 밖에 있는 프레임(han3a 에서 눈으로 고름)
CUT_LAG = 1000               # 시작 줄은 차례 경계 + 이만큼(ms) 안이어야(뽑기 전) — patch 의 _anchor_limit 참고
ANCHOR_LEAD = 1500          # 시작 줄은 그 차례 버림보다 이만큼(ms) 앞이어야(뽑기 → 버림이 1.5초 안에 끝나는 일은 드묾) — patch 의 anchor 참고
ROW_PAD = 80               # 읽기 그림 띠를 줄 방향 양 끝으로 더 여는 폭(px, 원본) — patch 의 wide_band 참고
RECFIX = META = EXE = None   # results/han3_1123/recorder_fix.json · rounds_meta.json · _bin/replay_recorder.exe
STICKS = None           # 기록기 --sticks — 3반장: "424,425,618,622"
CALL_TURNS: list = []   # 울기 차례(callprep 기본) — 3반장: n03_d12 · n04_d05 · n04_d06 · n05_d10b · n07_d06 · n07_d10 · n07_d15


def configure(cfg: "hcfg.Hanchan"):
    """반장 설정을 이 모듈 값으로 옮긴다(patch · 명령 전에). 녹화 자리 · 날짜가 설정에 있으면 htcommon 도 바꾼다."""
    global CFG, H3, H3DIR, PREP, TURNS_H3, CUT_H3, FIX, READ_ROOT, ROW_AT, CUT_LAG, ANCHOR_LEAD, ROW_PAD, RECFIX, META, EXE, STICKS, CALL_TURNS
    CFG = cfg
    H3 = list(cfg.games)
    H3DIR, PREP = cfg.results_dir, cfg.prep_dir
    TURNS_H3, CUT_H3, FIX = cfg.turns_file, cfg.cut_file, cfg.fix_file
    READ_ROOT = cfg.read_root
    ROW_AT = dict(cfg.row_at)
    CUT_LAG, ANCHOR_LEAD, ROW_PAD = cfg.cut_lag, cfg.anchor_lead, cfg.row_pad
    RECFIX, META, EXE, STICKS = cfg.recfix_file, cfg.meta_file, cfg.exe, cfg.sticks
    CALL_TURNS = list(cfg.call_turns)
    cfg.apply_recording(hc)
    # 11-24 자동 패보 S6a · S6b: 설정에 handtrack.dir 이 있으면 그 판의 판별 설정 · 출력(config · results/handtrack/<판> · <판>_feat.npz)을 실행 폴더에서
    # (ht_redirect — 공용 모듈은 안 고침). 없으면(3반장 · 손 설정) 아무것도 안 바꿈.
    if cfg.ht_dir or htr._ST["installed"]:
        htr.install(hc, cfg.ht_dir, cfg.ht_games)


configure(hcfg.load(check=False))   # import 만 한 쪽(han3_paifu 등)도 값이 있게 — 겹침 검사는 main · han3_paifu.main 이 설정을 다시 읽을 때

_base_jload = hc.jload


def _orig_jload(p):
    """htcommon.jload 원래 것(+ ht_redirect 경로 바꾸기 — handtrack.dir 이 없으면 그대로)."""
    return _base_jload(htr.remap(p))
_row_gid = None
ANCHOR_RELAXED: list = []   # 가림을 안 따지고 시작 줄을 잡은 프레임 시각(ms) — patch 의 anchor 참고
_cur_tid = [None]
_call_tid = [None]           # 복원 중 지금 울기 차례 — patch 의 back_call 참고
END_FALLBACK: list = []      # 끝 줄을 못 찾아 창 끝까지 준 차례 — patch 의 plan 참고
END_NOTE = """
## 이 차례만 다른 점(끝 줄)
- 코드가 버린 뒤의 끝 줄(줄 높이에 패 {n}장이 선 프레임)을 못 찾아 프레임을 차례 창 끝까지 줬다(손이 줄 끝을 계속 덮었거나, 패 한 장을 줄에서 조금 떼어 놓았을 수 있다).
  마지막 프레임까지 보고, 차례가 끝났을 때의 줄({n}장 — 줄에서 떼어 놓은 패도 그 자리 순서대로 셈)을 끝 줄로 적는다.
"""
END_NOTE_CALL = """- 이 차례 바로 뒤에 이 사람이 **울기**(남이 버린 패를 가져오려고 줄에서 두 장을 빼 옆으로 놓음)를 한다. 프레임 끝에 그 동작이 보이면
  **울기로 줄에서 패를 빼기 직전의 줄**을 끝 줄로 적고(end_order · j 도 그 줄 기준), why 에 그 직전 프레임 번호를 적는다. 울기로 빼는 두 장은 이 차례의 버림이 아니다.
"""


def _same(p, q) -> bool:
    try:
        return Path(p).resolve() == Path(q).resolve()
    except OSError:
        return False


def _fix() -> dict:
    return _orig_jload(FIX) if FIX.exists() else {}


def apply_fix(games: list, insert: bool = True) -> list:
    """turn_fix.json 적용. 칸 고침 + "__insert__": [{"after": 차례 id, "id", "tile", "sideways", "n_calc", "meld_tiles", "why"}] —
    차례 목록(강 사진 정지 상태 비교)이 놓친 손패 주인 버림(울려 나간 버림 · 공개 직전 마지막 버림 등)을 끼움. 끼운 차례는 앞 차례의 segs 를 빌려
    turncut 이 돌게 하고(turncut 은 차례 창을 네 자리 강으로 다시 긋고 프레임은 segments.json 에서 다시 모음), synthetic: true 로 표시."""
    import copy
    fx = _fix()
    for g in games:
        for ins in (fx.get("__insert__", []) if insert else []):
            if not CFG.owns(ins["id"], g["id"]) or any(t["id"] == ins["id"] for t in g["turns"]):
                continue
            k = next(i for i, t in enumerate(g["turns"]) if t["id"] == ins["after"])
            prev = g["turns"][k]
            nt = {**copy.deepcopy(prev), "id": ins["id"], "label": ins["id"].split("_d")[1], "repeat": True, "synthetic": True,
                  "tile": ins["tile"], "sideways": ins.get("sideways", False), "n_calc": ins.get("n_calc", prev.get("n_calc")),
                  "meld_tiles": ins.get("meld_tiles", prev.get("meld_tiles")), "same_seg": prev.get("same_seg"), "why": ins.get("why", "")}
            g["turns"].insert(k + 1, nt)
        for t in g["turns"]:
            f = fx.get(t["id"]) or {}
            for k in ("tile", "sideways", "n_calc", "meld_tiles"):
                if k in f:
                    t[k] = f[k]
            if f.get("skip"):
                t["skip"] = f["skip"]
    return games


def merged_turns(insert: bool = True) -> dict:
    base = _orig_jload(TURNS_ORIG)
    mine = _orig_jload(TURNS_H3)["games"] if TURNS_H3.exists() else []
    ids = {g["id"] for g in mine}
    return {**base, "games": [g for g in base["games"] if g["id"] not in ids] + apply_fix(mine, insert)}


def _jload(p):
    if _same(p, TURNS_ORIG):
        return merged_turns()
    d = _orig_jload(p)
    if _row_gid is not None and _same(p, hc.OUT / _row_gid / "segments.json"):
        ms = hc.to_ms(ROW_AT[_row_gid])
        return {**d, "still": [{"ms0": ms - 100, "ms1": ms + 100, "dur": 99.0, "note": "han3.ROW_AT"}]}
    if os.environ.get("HAN3_FINAL") == "result":
        pp = Path(p)
        if pp.name == "game.json" and pp.parent.name in H3 and _same(pp.parent.parent, hc.OUT):
            rr = H3DIR / pp.parent.name / "result_read.json"
            if rr.exists():
                r = _orig_jload(rr)
                d["final_hand"] = {**d["final_hand"], "closed": list(r["hand"]), "closed_from": "result_read.json",
                                   "closed_read": d["final_hand"]["closed"]}
    return d


def patch():
    hc.jload = _jload
    import pixtrack as pt
    _ri = pt.Row.__init__

    def row_init(self, gid):
        global _row_gid
        _row_gid = gid if gid in ROW_AT else None
        try:
            _ri(self, gid)
        finally:
            _row_gid = None
    pt.Row.__init__ = row_init
    # 시작 줄(slotgrid.anchor): 원래는 "상자 n개가 한 덩어리 + 그 위에 손 가림 없음" 인 첫 프레임. 위 자리(n02 · n05 · n06)처럼 손을 줄 끝 옆에
    # 늘 올려 두는 사람은 가림 열이 줄에 걸려 시작 줄을 못 잡는다(n02_d08: n개 한 덩어리 61장이 다 가림). 원래 규칙으로 못 잡을 때만
    # 가림을 따지지 않고 "상자 n개가 한 덩어리" 인 첫 프레임을 쓴다(검출기가 뒷면 n장을 다 봤다 = 손이 줄을 덮지는 않음). 쓴 때는 ANCHOR_RELAXED 에 남김.
    import slotgrid as sg
    import numpy as np
    if htr.active():   # 11-24: 판별 출력을 실행 폴더로 돌린 반장은 칸 틀 검출 캐시(det_<판>.json)도 실행 폴더에(공용 _work/slotgrid_1117 에 안 씀)
        sg.OUT = htr._ST["dir"] / "_work" / "slotgrid_1117"
    _an = sg.anchor

    def relaxed(frs, n, before=None):
        for ms, d in frs:
            if before is not None and ms >= before:
                break
            bs = d["b"]
            if len(bs) != n:
                continue
            cl = sg.clusters(bs, (max(b[1] for b in bs) - min(b[0] for b in bs)) / n)
            if len(cl) != 1:
                continue
            yc = float(np.median([(b[2] + b[3]) / 2 for b in bs]))
            return cl[0][0], (cl[0][1] - cl[0][0]) / n, yc, float(np.median([b[3] - b[2] for b in bs])), ms
        return None

    def anchor(frs, n):
        """시작 줄. 11-23 고침 둘:
        ① 원래 규칙으로 못 잡으면 가림을 안 따지고 "상자 n개 한 덩어리" 첫 프레임(n02_d08 · n04_d04).
        ② 잡은 시작 줄이 그 차례 버림 시각 − ANCHOR_LEAD 보다 늦으면(손이 줄을 계속 덮어 깨끗한 프레임이 뽑기 · 버림 뒤에야 나옴 — n06_d03 · d05:
           읽기 에이전트가 '뽑기 · 버림이 첫 프레임 앞에서 이미 끝남' 이라 답함) 그 시각 앞에서 가림 무시 규칙으로 다시 찾고,
           그것도 없으면 창 첫 프레임을 시작으로 삼고 줄 틀(왼쪽 끝 · 폭 · 높이)은 늦게 잡은 시작 줄 것을 빌림. 쓴 것은 ANCHOR_RELAXED 에 kind 와 함께."""
        a = _an(frs, n)
        lim = _anchor_limit(frs)
        late = a is not None and lim is not None and a[4] >= lim
        if a is not None and not late:
            return a
        b = relaxed(frs, n, before=lim)
        if b is not None:
            ANCHOR_RELAXED.append({"tid": _cur_tid[0], "ms": b[4], "t": hc.hms(b[4]),
                                   "kind": "가림 무시" + (f" · 원래 시작 줄이 한도(버림 − {ANCHOR_LEAD / 1000:g}초 · 경계 + {CUT_LAG / 1000:g}초) 뒤" if late else ""),
                                   "orig": hc.hms(a[4]) if a else None})
            return b
        if late:
            ms0 = frs[0][0]
            ANCHOR_RELAXED.append({"tid": _cur_tid[0], "ms": ms0, "t": hc.hms(ms0), "kind": "창 첫 프레임(줄 틀은 늦게 잡은 시작 줄 것)", "orig": hc.hms(a[4])})
            return a[0], a[1], a[2], a[3], ms0
        b = relaxed(frs, n)
        if b is not None:
            if lim is not None and b[4] >= lim:   # 한도 뒤에서만 잡힘 → 시작은 창 첫 프레임, 줄 틀만 빌림(p01_d03 · p02_d10)
                ms0 = frs[0][0]
                ANCHOR_RELAXED.append({"tid": _cur_tid[0], "ms": ms0, "t": hc.hms(ms0), "kind": f"창 첫 프레임(줄 틀은 한도 뒤 {hc.hms(b[4])} 가림 무시 시작 줄 것)", "orig": None})
                return b[0], b[1], b[2], b[3], ms0
            ANCHOR_RELAXED.append({"tid": _cur_tid[0], "ms": b[4], "t": hc.hms(b[4]), "kind": "가림 무시", "orig": None})
            return b
        # ③ 상자 n개 한 덩어리 프레임이 아예 없음(p02_d02: 오른쪽 사람이 두 손을 줄에 늘 올려 둠) — 버림 − 1.5초 앞에서 줄 높이 상자가 가장 많은
        #    프레임으로 줄 틀을 짐작하고, 시작은 창 첫 프레임. 읽기는 원본 프레임으로 하므로 사건 목록만 거칠어진다.
        cand = [(ms, d) for ms, d in frs if (lim is None or ms < lim) and d["b"]] or [(ms, d) for ms, d in frs if d["b"]]
        if not cand:
            return None
        ms_b, d_b = max(cand, key=lambda x: (min(len(x[1]["b"]), n), -x[0]))
        bs = d_b["b"]
        yc = float(np.median([(q[2] + q[3]) / 2 for q in bs]))
        row = sorted([q for q in bs if abs((q[2] + q[3]) / 2 - yc) <= 0.5 * float(np.median([q[3] - q[2] for q in bs]))])
        p = float(np.median([q[1] - q[0] for q in row]))
        ms0 = frs[0][0]
        ANCHOR_RELAXED.append({"tid": _cur_tid[0], "ms": ms0, "t": hc.hms(ms0), "kind": f"줄 틀 짐작(상자 {len(row)}개 프레임 {hc.hms(ms_b)})", "orig": None})
        return row[0][0], p, yc, float(np.median([q[3] - q[2] for q in row])), ms0
    sg.anchor = anchor

    def _anchor_limit(frs):
        """지금 차례(_cur_tid)의 시작 줄 한도(ms) = min(버림 − ANCHOR_LEAD, 차례 경계 + CUT_LAG). 모르면 None.
        경계(turncut cut.start) = 앞 자리 버림이 기록기에 처음 보이기 직전 추적 프레임 — 그 버림은 경계 뒤에 일어나고 손패 주인의 뽑기는 그 뒤라
        경계 + 1초 안의 줄은 뽑기 전이다(p01_d03: 시작 줄 32:55.1 이 뽑기 32:51.5 뒤 · 경계 32:49.0 — 버림 − 1.5초만으로는 못 거름)."""
        tid = _cur_tid[0]
        if not tid or not frs:
            return None
        try:
            import sam2track as s1x
            gid, t = s1x.turn_of(tid)
            c = t["cut"]
            v = [s1x.ms_of(c["discard"], frs[0][0]) - ANCHOR_LEAD] if c.get("discard") else []
            if c.get("start") and c.get("by") != "옛 묶음":
                v.append(s1x.ms_of(c["start"], frs[0][0]) + CUT_LAG)
            return min(v) if v else None
        except Exception:  # noqa: BLE001
            return None
    import turncut as tc
    if CUT_H3 not in tc.EXTRA:
        tc.EXTRA.append(CUT_H3)
    _rd = tc.rec_dir
    tc.rec_dir = lambda gid: (PREP / "rec" / gid) if gid in H3 else _rd(gid)
    # 11-24: 판별 출력을 실행 폴더로 돌린 판(ht_redirect)은 turncut build 의 대조 그림(_work/testtruth_1116/frames/<판>/ — 공용 · 보호 폴더)을 그리지 않는다.
    # S6 읽기 재료(opusread prep --fromplan · callprep)는 원본 프레임에서 직접 자르므로 이 그림을 안 씀.
    _rm = tc.render_missing

    def render_missing(g):
        if g["id"] in htr.games():
            print(f"  {g['id']}: 판별 출력이 실행 폴더(handtrack.dir)라 대조 그림(testtruth_1116/frames)은 안 그림", flush=True)
            return 0
        return _rm(g)
    tc.render_missing = render_missing
    import sam2track as s1
    # sam2track.turn_of 는 GAMES 를 앞에서부터 보며 차례 id 앞 세 글자가 같은 첫 판을 고른다 — 이 반장 판의 접두사가 이미 있는 판과 겹치면 엉뚱한 판으로 감
    clash = [(g, x) for g in H3 for x in s1.GAMES if x[:3] == CFG.prefix_of(g) and not (x == g and g in CFG.replaces_base)]
    if clash:
        raise hcfg.HanchanError(f"{CFG.path.name}: 차례 id 접두사가 sam2track.GAMES 의 판과 겹침 {clash} — 판 id 앞 세 글자를 바꿔라")
    s1.GAMES = tuple(s1.GAMES) + tuple(g for g in H3 if g not in s1.GAMES)
    # 읽기 그림 띠(band2 = wide_band(sheet_band)): 줄 방향 양 끝을 ROW_PAD 씩 더 연다. sheet_band 는 bandfit 의 0.5 ~ 99.5 백분위 + 40/100px 라
    # 줄을 끝까지 밀어 둔 순간 끝 패가 그림 가장자리에서 잘림(n02_d08 59:52 ~ 57: 떼어 둔 패가 원본 x 1050 ~ 1100, sheet_band 끝 1096 · n01 줄 끝 568 < 577).
    # 칸 틀 검출(det)은 sheet_band 그대로라 사건 목록은 같고, 그림만 넓어진다(plan 의 상자 좌표는 band2 로 다시 계산됨).
    _wb = s1.wide_band

    def wide_band(band):
        x0, y0, x1, y1 = band
        if x1 - x0 >= y1 - y0:
            band = [max(0, x0 - ROW_PAD), y0, min(1496, x1 + ROW_PAD), y1]
        else:
            band = [x0, max(0, y0 - ROW_PAD), x1, min(1496, y1 + ROW_PAD)]
        return _wb(band)
    s1.wide_band = wide_band
    _pl = s1.plan

    def plan(tid):
        """끝 줄(버림 1초 뒤 줄 높이 상자가 n개인 마지막 프레임)을 못 찾으면(n03_d11: 버린 직후 울기로 손이 줄을 덮음) 창 끝(slotgrid.window 의 끝)까지
        원본을 준다 — 읽기 프레임 = 시작 줄 ~ 창 끝. e_rule "window_end" 로 남기고 END_FALLBACK 에 적음."""
        _cur_tid[0] = tid
        p = _pl(tid)
        if p.get("ok") or p.get("why") != "끝 줄 없음":
            return p
        gid, t = s1.turn_of(tid)
        cfg = hc.config(gid)
        det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
        w0, w1 = sg.window(t)
        frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
        a = sg.anchor(frs, t["n_calc"])
        e_ms = max(ms for ms, _ in frs)
        band = cfg["sheet_band"]
        END_FALLBACK.append({"tid": tid, "a": hc.hms(a[4]), "e": hc.hms(e_ms)})
        return {"id": tid, "gid": gid, "ok": True, "n": t["n_calc"], "side": cfg["side"], "band": band, "band2": s1.wide_band(band),
                "w0": w0, "w1": w1, "a_ms": a[4], "e_ms": e_ms, "hh": a[3], "a_boxes": [], "e_boxes": [], "e_rule": "window_end"}
    s1.plan = plan
    _ta = s1.truth_all

    def truth_all():
        t = _ta()
        for k, v in _fix().items():
            if not k.startswith("__") and v.get("kind"):
                t[k] = {**t.get(k, {}), "kind": v["kind"]}
        return t
    s1.truth_all = truth_all
    import rebuild_opus as rb
    _ch = rb.call_hand_tiles

    def call_hand_tiles(game, t):
        _call_tid[0] = t["id"]          # 바로 뒤 back_call 이 어느 차례인지 알게(rebuild_opus.rebuild 는 call_hand_tiles → back_call 순서로 부름)
        f = _fix().get(t["id"]) or {}
        return list(f["call_hand"]) if f.get("call_hand") else _ch(game, t)
    rb.call_hand_tiles = call_hand_tiles
    _bc = rb.back_call

    def back_call(after, gone, sch):
        """11-23 3d: 울기 차례에 answer.json(gone · k · end_order)이 있으면 그 번호로 울기 전 줄을 만든다(call_back). 없거나 못 쓰면 원래 정렬 짐작."""
        tid = _call_tid[0]
        before, note = call_back(tid, list(after), list(gone), sch) if tid else (None, "차례 모름")
        if before is not None:
            CALL_LOG[tid] = {"how": "answer", "note": note}
            return before
        CALL_LOG[tid] = {"how": "guess", "note": f"울기 줄 짐작(정렬) — {note}"}
        return _bc(after, gone, sch)
    rb.back_call = back_call


# ------------------------------------------------------------------ 명령
def cmd_turns(games: list):
    import truthprep as tp
    tp.tr.GAMES = list(games)
    tp.EXTRA = []
    d = tp.build()
    have = {g["id"]: g for g in _orig_jload(TURNS_H3)["games"]} if TURNS_H3.exists() else {}
    for g in d["games"]:
        have[g["id"]] = g
    hc.jsave(TURNS_H3, {"games": [have[g] for g in H3 if g in have], "scale": d["scale"],
                        "note": f"truthprep.build 를 {CFG.label} 판에만 돌린 것(han3.py turns). 원본 turns.json 은 안 건드림 — han3.patch 가 읽을 때 합침. {FIX.name} 은 읽을 때 적용"})
    for g in apply_fix([have[x] for x in games]):
        bad = [t["id"] for t in g["turns"] if t.get("n_calc") is None]
        print(f"{g['id']}: 차례 {len(g['turns'])} · 첫 강 번호 {g['first_i']} · 패 모름 {sum(t['tile'] is None for t in g['turns'])} · "
              f"리치(가로) {[t['label'] for t in g['turns'] if t['sideways']]} · 줄 장수 모름 {bad}")


def rec_src(gid: str) -> dict:
    """기록기 결과 자리. recfix 가 만든 고친 결과(_prep/rec/<판>/paifu_rec.json)가 있으면 그것(fix · 조립이 씀)."""
    d = H3DIR / gid
    fx = PREP / "rec" / gid
    return {"dart": d / "dart_overlay.json", "dump": d / "overlay_dump.json", "result": d / "result_read.json",
            "paifu": fx / "paifu_rec.json" if (fx / "paifu_rec.json").exists() else d / "paifu_rec.json"}


def _wj(p, o, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=indent))


def meta_of(gid: str) -> dict:
    m = _orig_jload(META)
    r = next(x for x in m["rounds"] if x["id"] == gid)
    return {**r, "bottom_seat": m["bottom_seat"], "dealer_side": SIDES[(r["dealer"] - m["bottom_seat"]) % 4],
            "hero_side": SIDES[(r["hero"] - m["bottom_seat"]) % 4]}


def cmd_recfix(games: list):
    """recorder_fix.json(조정자가 쓴 기록기 고침 표)을 기록기 결과에 적용 → _prep/rec/<판>/ 에 dart_overlay_v2.json · paifu_rec.json · overlay_dump.json.
    원본(han3_1123/<판>/dart_overlay.json · paifu_rec.json)은 안 건드림. op: retile · drop(그 버림 사건과, 바로 뒤에 그 버림을 받은 울기 사건이 있으면 그것도) ·
    use_run(그 폴더의 기록기 실행 옵션으로 paifu 까지 다시 — replay_recorder.exe 를 직접 부름, 다시 빌드 안 함) · riichi(남은 강 river_index 번째에 가로 표시).
    검사: ① 남은 강 = result_read.json rivers_final(표의 _reading_errors 칸은 기록기가 맞음) ② 엮임(headrec_run.interleave) ③ 같은 종류 5장."""
    import subprocess
    sys.path.insert(0, str(RES.parent))
    import headrec_run as hr
    tab = _orig_jload(RECFIX)
    rows = []
    for gid in games:
        src = H3DIR / gid
        out = PREP / "rec" / gid
        out.mkdir(parents=True, exist_ok=True)
        mt = meta_of(gid)
        ops = tab.get(gid, [])
        dump = src / "overlay_dump_c2x.json"
        log = []
        run = next((o for o in ops if o["op"] == "use_run"), None)
        if run:
            if not STICKS:
                raise SystemExit(f"{gid}: use_run 에 기록기 --sticks 값이 필요 — 반장 설정 recorder.sticks 를 적어라")
            od = out / f"run_{run['run']}"
            od.mkdir(parents=True, exist_ok=True)
            ref = (src / run["run"] / "stdout.txt").read_text(encoding="utf-8").splitlines()[0].split()
            extra = [x for x in ref if x == "--river-role"]
            args = [str(EXE), "overlay", str(dump), run["dealer"], str(od / "dart_overlay.json"), str(od / "paifu_rec.json"), str(mt["bottom_seat"]),
                    "--sticks", STICKS, *extra]
            p = subprocess.run(args, cwd=hc.ROOT, capture_output=True, text=True, encoding="utf-8")
            (od / "stdout.txt").write_bytes((" ".join(args[1:]) + "\n" + p.stdout + p.stderr).encode("utf-8"))
            if p.returncode:
                raise SystemExit(f"{gid}: 기록기 실패 {p.stdout}{p.stderr}")
            d, pr = _orig_jload(od / "dart_overlay.json"), _orig_jload(od / "paifu_rec.json")
            refd = _orig_jload(src / run["run"] / "dart_overlay.json")
            same = all([x["tile"] for x in d[s]["slots"]] == [x["tile"] for x in refd[s]["slots"]] for s in SIDES)
            log.append(f"use_run {run['run']}: 선 {run['dealer']} · 옵션 {extra} · bottomSeat {mt['bottom_seat']} 로 다시 돌림 → 강이 {run['run']} 과 {'같음' if same else '다름'}")
        else:
            d, pr = _orig_jload(src / "dart_overlay.json"), _orig_jload(src / "paifu_rec.json")
        ev = pr["events"]
        seat = {s: (pr["hero"] + SIDES.index(s)) % 4 for s in SIDES}

        def dis_idx(side, i):
            """그 자리 slots 의 칸 i(1부터) ↔ paifu 사건 번호(그 자리 discard 의 같은 순번)."""
            k = next(n for n, x in enumerate(d[side]["slots"]) if x["i"] == i)
            idx = [n for n, e in enumerate(ev) if e["type"] == "discard" and e["seat"] == seat[side]]
            assert len(idx) == len(d[side]["slots"]), (gid, side, len(idx), len(d[side]["slots"]))
            return k, idx[k]
        for o in ops:
            if o["op"] == "retile":
                k, n = dis_idx(o["side"], o["i"])
                assert d[o["side"]]["slots"][k]["tile"] == o["from"] == ev[n]["tile"], (gid, o)
                d[o["side"]]["slots"][k]["tile"] = o["to"]
                ev[n] = {**ev[n], "tile": o["to"]}
                log.append(f"retile {o['side']} {o['i']} {o['from']}→{o['to']}")
            elif o["op"] == "drop":
                k, n = dis_idx(o["side"], o["i"])
                sl = d[o["side"]]["slots"][k]
                assert sl["tile"] == o["tile"] == ev[n]["tile"], (gid, o)
                gone = [n]
                if sl.get("taken_at") and n + 1 < len(ev) and ev[n + 1]["type"] == "call" and ev[n + 1].get("from") == seat[o["side"]] and o["tile"] in ev[n + 1]["tiles"]:
                    gone.append(n + 1)
                del d[o["side"]]["slots"][k]
                log.append(f"drop {o['side']} {o['i']} {o['tile']} — 사건 {[ev[x] for x in gone]}")
                for x in sorted(gone, reverse=True):
                    del ev[x]
            elif o["op"] == "add_last":
                # 기록 구간 끝에 걸려 기록기가 못 본 마지막 버림(p02 위 1p) — 그 자리 slots 끝에 칸을 더하고, 사건은 그 시각보다 앞선 사건들 뒤에 끼움
                sl = d[o["side"]]["slots"]
                sl.append({"i": (max(x["i"] for x in sl) + 1) if sl else 1, "tile": o["tile"], "share": None, "n": 0, "first_at": o["at"],
                           "taken_at": None, "sideways": False, "added_by": "recorder_fix add_last"})
                ms = hc.to_ms(o["at"])
                late = [n for n, e in enumerate(ev) if e.get("at") is not None and e["at"] > ms]
                pos = late[0] if late else len(ev)
                ev.insert(pos, {"type": "discard", "seat": seat[o["side"]], "tile": o["tile"], "tsumogiri": None, "riichi": False, "at": ms})
                log.append(f"add_last {o['side']} {o['tile']} {o['at']} (사건 {pos + 1}번째 자리, 전체 {len(ev)})")
            elif o["op"] == "riichi":
                rem = [x for x in d[o["side"]]["slots"] if not x.get("taken_at")]
                sl = rem[o["river_index"] - 1]
                assert sl["tile"] == o["tile"], (gid, o, sl)
                sl["sideways"] = True
                k, n = dis_idx(o["side"], sl["i"])
                ev[n] = {**ev[n], "riichi": True}
                log.append(f"riichi {o['side']} 남은 강 {o['river_index']}번째 {o['tile']}(칸 {sl['i']})")
        pr = {**pr, "events": ev, "note": (pr.get("note") or "") + f" · han3 recfix: {'; '.join(log) or '고침 없음'}"}
        _wj(out / "dart_overlay_v2.json", d)
        _wj(out / "dart_overlay.json", d)
        _wj(out / "paifu_rec.json", pr)
        shutil.copyfile(dump, out / "overlay_dump.json")
        # 검사
        rr = _orig_jload(src / "result_read.json")
        diffs = []
        for s in SIDES:
            mine = [x["tile"] for x in d[s]["slots"] if not x.get("taken_at")]
            theirs = rr["rivers_final"][s]
            if mine != theirs:
                sm = difflib.SequenceMatcher(None, theirs, mine, autojunk=False)
                for tag, a0, a1, b0, b1 in sm.get_opcodes():
                    if tag != "equal":
                        diffs.append(f"{s} 읽기{a0 + 1}~{a1} {theirs[a0:a1]} ↔ 기록기 {mine[b0:b1]}")
        il = hr.interleave(d, mt["dealer_side"])
        fv = hr.five(d)
        dealer_ok = pr["dealer"] == mt["dealer"]
        n_ev = {s: sum(1 for e in ev if e["type"] == "discard" and e["seat"] == seat[s]) for s in SIDES}
        cnt_ok = all(n_ev[s] == len(d[s]["slots"]) for s in SIDES)
        rid = [x for x in rr["riichi"]]
        side_rec = {s: [k + 1 for k, x in enumerate([y for y in d[s]["slots"] if not y.get("taken_at")]) if x.get("sideways")] for s in SIDES}
        side_rr = {s: [x["river_index"] for x in rid if x["side"] == s] for s in SIDES}
        row = {"gid": gid, "ops": log, "river_diffs": diffs, "interleave": il["ok"], "interleave_left": il["left"], "five": fv,
               "dealer_ok": dealer_ok, "paifu_dealer": pr["dealer"], "meta_dealer": mt["dealer"], "count_ok": cnt_ok,
               "riichi_rec": {s: v for s, v in side_rec.items() if v}, "riichi_read": {s: v for s, v in side_rr.items() if v},
               "n_discards": sum(len(d[s]["slots"]) for s in SIDES)}
        _wj(out / "recfix_check.json", row)
        rows.append(row)
        print(f"== {gid}: {'; '.join(log) or '고침 없음'}")
        print(f"   ① 남은 강 vs 눈 읽기: {'모두 같음' if not diffs else diffs}")
        print(f"   ② 엮임 {'통과' if il['ok'] else '막힘 ' + str(il['left'])} {il['notes']} ③ 5장 {fv or '없음'} · 선 {pr['dealer']}(meta {mt['dealer']}) · 사건 장수 {'맞음' if cnt_ok else '다름'}"
              f" · 리치 기록기 {row['riichi_rec']} / 읽기 {row['riichi_read']}")
    _wj(PREP / "recfix_summary.json", rows)


def cmd_link(games: list):
    """turncut 은 <rec_dir>/dart_overlay_v2.json(자리별 강 칸 · first_at)과 overlay_dump.json(frames[].at — 추적 프레임 시각)을 읽는다.
    3반장 기록기 결과(han3_1123/<판>/dart_overlay.json)를 그 이름으로 복사. overlay_dump.json 이 없으면 헤드 녹화 프레임 시각으로 만든다
    (turncut 은 first_at(초 단위) 에 가장 가까운 프레임과 그 앞 프레임만 쓰므로 프레임 시각 목록이면 된다 — 헤드 녹화는 초당 10장)."""
    import datetime as dt
    for gid in games:
        s = rec_src(gid)
        out = PREP / "rec" / gid
        out.mkdir(parents=True, exist_ok=True)
        if (out / "recfix_check.json").exists():
            print(f"{gid}: recfix 가 만든 고친 결과가 이미 {out} 에 있음 — 그대로 씀(link 는 고침 없는 원본 복사라 안 덮음)")
            continue
        if not s["dart"].exists():
            print(f"{gid}: {s['dart']} 없음 — 기록기 재생이 아직")
            continue
        shutil.copyfile(s["dart"], out / "dart_overlay_v2.json")
        if s["dump"].exists():
            shutil.copyfile(s["dump"], out / "overlay_dump.json")
            how = "기록기 overlay_dump.json 복사"
        else:
            cf = hc.config(gid)
            ms = hc.frame_range(hc.to_ms(cf["t_start"]) - 30000, hc.to_ms(cf["t_reveal"]) + 30000)
            fr = [{"at": dt.datetime.fromtimestamp(m / 1000).isoformat()} for m in ms]
            hc.jsave(out / "overlay_dump.json", {"frames": fr, "note": "han3.py link: 헤드 녹화 프레임 시각만(turncut.build_game 용)"}, indent=None)
            how = f"헤드 녹화 프레임 시각 {len(fr)}장으로 만듦"
        print(f"{gid}: → {out} ({how})")


def hero_seat(gid: str, p: dict) -> int:
    return (p["hero"] + SIDES.index(hc.config(gid)["side"])) % 4     # paifu_rec 의 hero = 아래 자리(replay_recorder bottomSeat)


def cmd_fix(games: list, write: bool):
    """기록기 사건(paifu_rec.json)의 손패 주인 버림 · 울기와 차례 목록(turns_han3)을 패 순서로 맞춰 차례마다 고칠 칸을 낸다.
    - tile: 기록기 패(강 사진 분류 tile 과 다르면 표시), sideways: 기록기 riichi
    - 울기: 손패 주인 울기 사건 바로 뒤 버림 = kind "call", n_calc = 울기 전 줄 장수, meld_tiles = [3c, 3c+3], call_hand = 묶음 − 받은 패
    - 그 밖: n_calc = 13 − 3 × (앞선 울기 수), meld_tiles = [3c, 3c]
    맞출 수 없는 차례(기록기에 없는 버림 · 차례 목록에 없는 버림)는 적기만 하고 손으로 정한다."""
    fx = _fix()
    for gid in games:
        s = rec_src(gid)
        if not s["paifu"].exists():
            print(f"{gid}: paifu_rec.json 없음")
            continue
        p = _orig_jload(s["paifu"])
        hero = hero_seat(gid, p)
        g = next(x for x in merged_turns(insert=False)["games"] if x["id"] == gid)   # 끼운 차례는 다시 셈(아래에서 이 판 몫을 새로 씀)
        if g.get("first_i") is None:   # 11-24: 차례 목록이 빈 판(판별 출력의 강 변화가 0 — 자동 설정이 틀렸을 때)은 맞출 것이 없음(옛 코드는 TypeError)
            print(f"\n== {gid}: 차례 목록이 비었음(first_i 없음) — 고칠 것 없이 건너뜀")
            continue
        ev, calls, last_dis = [], 0, {}
        for e in p["events"]:
            if e["type"] == "discard":
                last_dis[e["seat"]] = e["tile"]
                if e["seat"] == hero:
                    ev.append({"tile": e["tile"], "riichi": bool(e.get("riichi")), "c": calls, "after_call": None})
            elif e["type"] == "call" and e["seat"] == hero:
                tiles = list(e["tiles"])
                got = last_dis.get(e.get("from"))
                hand = list(tiles)
                if got in hand:
                    hand.remove(got)
                else:
                    hand = hand[1:]
                calls += 1
                ev.append({"call": e, "hand": hand, "got": got})
        dis = [x for x in ev if "tile" in x]
        # 울기 표시를 그 뒤 첫 버림에 붙임
        pend = None
        for x in ev:
            if "call" in x:
                pend = x
            elif pend is not None:
                x["after_call"] = pend
                pend = None
        # 판 구간 전(t_ready 앞) 버림 = 기록기 앞쪽 first_i − 1 장 — 짝짓기에서 뺀다(p02: 강 사진 d02 의 패가 3z 로 잘못 붙어 판 구간 전 3z 와 짝지어졌음)
        off = max(0, g["first_i"] - 1)
        sm = difflib.SequenceMatcher(None, [t["tile"] for t in g["turns"]], [x["tile"] for x in dis[off:]], autojunk=False)
        pair = {}
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                pair[blk.a + k] = blk.b + k + off
        print(f"\n== {gid} 손패 주인 자리 {hero}({hc.config(gid)['side']}) · 기록기 버림 {len(dis)} · 울기 {calls} · 차례 목록 {len(g['turns'])}")
        used = set(pair.values())
        for n, t in enumerate(g["turns"]):
            b = pair.get(n)
            if b is None:
                # 패가 다른 차례: 앞뒤 짝 사이에 남은 차례도 하나 · 기록기 버림도 하나면 둘을 짝짓는다(패 종류는 기록기 것을 씀 — 출력에 "바뀜 tile")
                pa = max([m for m in pair if m < n], default=-1)
                pb = min([m for m in pair if m > n], default=len(g["turns"]))
                lo = pair[pa] if pa >= 0 else off - 1
                hi = pair[pb] if pb < len(g["turns"]) else len(dis)
                free = [k for k in range(lo + 1, hi) if k not in used]
                if len(free) == 1 and pb - pa == 2:
                    b = free[0]
                    used.add(b)
            if b is None:
                print(f"  {t['id']} 강 사진 {t['tile']} → 기록기 짝 없음(손으로 정할 것)")
                continue
            x = dis[b]
            c = x["c"]
            # 리치(가로)는 둘 중 하나라도 보면 참 — 기록기가 가로 놓임을 놓치는 일이 있음(n08 12순: 강 사진 · result_read 는 리치, 기록기 riichi false)
            f = {"tile": x["tile"], "sideways": bool(x["riichi"] or t.get("sideways")), "n_calc": 13 - 3 * c, "meld_tiles": [3 * c, 3 * c]}
            if bool(x["riichi"]) != bool(t.get("sideways")):
                f["why_sideways"] = f"강 사진 sideways {t.get('sideways')} · 기록기 riichi {x['riichi']} — 참으로 둠"
            if x["after_call"] is not None:
                f.update(kind="call", n_calc=13 - 3 * (c - 1), meld_tiles=[3 * (c - 1), 3 * c], call_hand=x["after_call"]["hand"],
                         why=f"기록기 울기 {x['after_call']['call']} 바로 뒤 버림(받은 패 {x['after_call']['got']})")
            diff = [k for k in ("tile", "sideways", "n_calc", "meld_tiles") if t.get(k) != f[k]]
            print(f"  {t['id']} 강 사진 {t['tile']}{'*' if t['sideways'] else ''} n{t.get('n_calc')} → 기록기 {x['tile']}{'*' if x['riichi'] else ''} n{f['n_calc']}"
                  + (f" · 울기 차례 손에서 {f['call_hand']}" if f.get("kind") else "") + (f" · 바뀜 {diff}" if diff else ""))
            fx[t["id"]] = {**fx.get(t["id"], {}), **f}
        left = [k for k in range(len(dis)) if k not in used]
        pre = [k for k in left if k < off]
        if pre:
            print(f"  기록기에만 있는 손패 주인 버림(첫 차례 앞 = 녹화 전 · 판 구간 전) {[dis[k]['tile'] for k in pre]} · 차례 목록 첫 강 번호 {g['first_i']}"
                  + ("" if len(pre) == g["first_i"] - 1 else " — 장수가 first_i − 1 과 다름(확인할 것)"))
        # 기록기 버림 번호 → 차례 id(짝 지은 차례 + 끼운 차례). 끼운 차례 id = <판 앞 세 글자>_d<기록기에서 손패 주인 몇 번째 버림>r
        # (같은 차례 뒤에 둘 이상 끼울 때 id 가 겹치지 않고, 앞에 끼운 차례 뒤로 이어 붙게)
        id_of = {b: g["turns"][n]["id"] for n, b in pair.items()}
        ins_all = [x for x in fx.get("__insert__", []) if not CFG.owns(x["id"], gid)]
        for k in left:
            if k in pre:
                continue
            x = dis[k]
            pb = max((b for b in id_of if b < k), default=None)
            after = id_of.get(pb)
            if after is None:
                print(f"  기록기에만 있는 버림 {x['tile']}(기록기 {k + 1}번째) — 앞 짝 차례를 못 찾음, 손으로")
                continue
            c = x["c"]
            nid = f"{CFG.prefix_of(gid)}_d{k + 1:02d}r"
            id_of[k] = nid
            ins = {"after": after, "id": nid, "tile": x["tile"], "sideways": x["riichi"], "n_calc": 13 - 3 * c, "meld_tiles": [3 * c, 3 * c],
                   "why": f"기록기 손패 주인 {k + 1}번째 버림 — 강 사진 차례 목록에 없음(울려 나감 · 공개 직전 등)"}
            print(f"  끼울 차례 {ins['id']}: {x['tile']}{'*' if x['riichi'] else ''} n{ins['n_calc']} ({after} 뒤) — {ins['why']}")
            ins_all.append(ins)
        fx["__insert__"] = ins_all
    if write:
        hc.jsave(FIX, fx)
        print("→", FIX)


def turns_h3(gid: str) -> list:
    return next(x for x in merged_turns()["games"] if x["id"] == gid)["turns"]


def read_ids(gid: str) -> list:
    """하위 에이전트가 읽을 차례: 리치 선언 뒤 차례(규칙 쯔모기리) · 울기 차례(kind call) · skip 을 뺀 전부(r18 과 같음)."""
    fx = _fix()
    out, riichi = [], False
    for t in turns_h3(gid):
        # 끼운 차례(synthetic)도 리치 앞이면 읽는다(11-23 조정자 지시) — 리치 뒤면 위 riichi 로 빠짐
        if riichi or (fx.get(t["id"]) or {}).get("kind") or t.get("skip"):
            pass
        else:
            out.append(t["id"])
        if t.get("sideways"):
            riichi = True
    return out


# ------------------------------------------------------------------ 울기 차례 읽기(11-23 3d)
# 화료자가 운 판(n03 · n04 · n05 · n07)의 울기 차례는 지금까지 읽지 않고 rebuild_opus.back_call 이 "묶음은 확실, 줄 순서는 정렬로 짐작" 으로
# 울기 전 줄을 만들었다. 그 앞 순들은 Opus 의 칸 번호를 그 짐작한 줄에 대고 거꾸로 풀어서, 줄 순서가 틀리면 뽑은 패 종류(= 손패 묶음)까지 틀린다.
# → 울기 차례도 읽는다: 줄 n장에서 울기로 나간 두 칸(gone) · 버린 칸(k) · 끝 줄 순서(end_order, n−3장).
CALL_LOG: dict = {}   # 복원 때 울기 차례마다 {"how": "answer" | "guess", "note"}


def call_task(n: int, F: int, tid: str, d: Path, work: Path) -> str:
    import opusread as o
    s = o.TASK_NOSAM.format(n=n, F=F, tid=tid, dir=d.as_posix(), work=work.as_posix())
    subs = [
        ("첫 프레임의 줄 {n}장을 왼쪽부터 원래 번호 1 ~ {n} 으로 부른다.".format(n=n),
         f"첫 프레임의 줄 {n}장을 왼쪽부터 원래 번호 1 ~ {n} 으로 부른다(첫 프레임에 손이 아직 줄을 다루는 중이면 처음으로 {n}장이 가지런히 선 프레임의 줄 — 그 프레임 번호를 why 에 적는다)."),
        ("이 차례 = 패산에서 한 장을 뽑아 오고(뽑은 패 = **D**), 한 장을 강에 버림. 차례를 시작할 때 줄은 **{n}장**이다.".format(n=n),
         f"이 차례는 **뽑기가 없다.** 남이 버린 패를 받아 **줄 {n}장에서 두 장을 빼** 받은 패와 함께 탁자 모서리에 앞면으로 내놓고(퐁 · 치), "
         f"이어서 **줄에서 한 장을 버린다**. 차례를 시작할 때 줄은 **{n}장**, 끝 줄은 **{n - 3}장**이다."),
        ("- **패는 사라지지 않는다.** 줄의 패 수는 {n} → D 를 줄에 놓으면 {n}+1 → 한 장 버리면 {n}.".format(n=n),
         f"- **패는 사라지지 않는다.** 줄의 패 수는 {n} → 울기로 두 장을 빼면 {n - 2} → 한 장 버리면 {n - 3}. 모서리에 내놓는 묶음은 세 장(받은 패 + 줄에서 뺀 두 장)이다."),
        ("- D 를 끝에 붙여 두고 한 장을 버리는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 버리는 사람, 버리기 전에 패를 옮기거나 맞바꾸는 사람이 다 있다. 끝 프레임까지 본다.",
         "- 두 장을 한꺼번에 집는 사람, 한 장씩 빼는 사람, 빼기 전에 두 장을 줄 끝으로 옮겨 두는 사람, 울기를 내놓은 뒤 줄을 다시 정리하고 버리는 사람, 버린 뒤 줄을 밀어 빈칸을 메우는 사람이 다 있다. "
         "줄에서 빠진 세 칸이 어디였는지를 원래 번호로 적는 것이 목적이다. 끝 프레임까지 본다."),
    ]
    subs.append(("**패가 실제로 움직인 때**(D 를 줄에 놓음 · 패를 뺌 · 버림 · 줄을 밂 · 끼움 · 옮김 · 맞바꿈)",
                 "**패가 실제로 움직인 때**(울기로 줄에서 패를 뺌 · 모서리에 내놓음 · 버림 · 줄을 밂 · 끼움 · 옮김 · 맞바꿈)"))
    for a, b in subs:
        assert s.count(a) == 1, a[:40]
        s = s.replace(a, b)
    i = s.index("## 답")
    s = s[:i] + f"""## 답
`{d.as_posix()}/answer.json` 한 파일만 쓴다:
```json
{{"id": "{tid}", "kind": "call",
 "gone": [울기로 줄에서 나간 두 장의 원래 줄 번호 둘(왼쪽부터 1 ~ {n})],
 "k": 버린 패의 원래 줄 번호(1 ~ {n}),
 "end_order": ["끝 줄({n - 3}장) 왼쪽부터 원래 번호 \\"1\\" ~ \\"{n}\\""], "unsure": 맞을 가능성 70% 밑이면 true,
 "events_used": "사건 목록에서 쓴 줄과 원본으로 바로잡은 곳(프레임 번호)", "why": "근거 3 ~ 5문장(시각 · 프레임 번호와 함께)"}}
```
gone 두 개 · k · end_order 의 번호를 합치면 1 ~ {n} 이 한 번씩 나와야 한다.
마지막 답변은 "gone · k 와 확신 여부" 한 줄이면 된다.
"""
    return s


def cmd_callprep(ids: list, root: str):
    """울기 차례 읽기 재료. 창 = 시작 줄(han3 anchor 규칙: min(버림 − 1.5초, 경계 + 1초) 앞) ~ 차례 창 끝(slotgrid.window 끝 — 다음 차례 경계 + 1.5초).
    프레임 · 띠 · 사건 목록은 opusread.prep_fromplan 과 같은 꼴(띠 = wide_band(sheet_band) + ROW_PAD, 초당 5장)."""
    import opusread as o
    import claudeagent as ca
    import sam2track as s1
    import slotgrid as sg
    from PIL import Image
    out = hc.WORK / root
    for tid in ids:
        gid, t = s1.turn_of(tid)
        assert (_fix().get(tid) or {}).get("kind") == "call", f"{tid} 는 turn_fix 의 울기 차례가 아님"
        cfg = hc.config(gid)
        det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
        n = t["n_calc"]
        w0, w1 = sg.window(t)
        frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
        _cur_tid[0] = tid
        a = sg.anchor(frs, n)
        assert a is not None, tid
        e_ms = max(ms for ms, _ in frs)
        band2 = s1.wide_band(cfg["sheet_band"])
        d = out / tid
        if (d / "answer.json").exists():
            print(tid, "answer.json 이 이미 있음 — 건너뜀")
            continue
        (d / "raw").mkdir(parents=True, exist_ok=True)
        (d / "work").mkdir(exist_ok=True)
        # 창 시작은 손패 주인의 바로 앞 버림 + 1초 뒤(n03_d12: 시작 줄 10:01.7 이 앞 차례 d11 버림 10:02.9 앞이었음)
        ts = turns_h3(gid)
        k = next(i for i, x in enumerate(ts) if x["id"] == tid)
        start = a[4]
        if k > 0:
            import turncut as tcx
            pt = next((x for x in tcx.turns_of(gid) if x["id"] == ts[k - 1]["id"]), None)
            if pt and pt["cut"].get("discard"):
                pd = s1.ms_of(pt["cut"]["discard"], a[4]) + 1000
                if pd > start:
                    print(f"  {tid}: 시작 줄 {hc.mss(start)} 이 앞 차례 버림({pt['cut']['discard']}) + 1초 앞 → {hc.mss(pd)} 부터")
                    start = pd
        fl = [int(x) for x in hc.frames(hc.rec_of(start)) if start <= x <= e_ms][::2]
        lines, rows = [], []
        for i, ms in enumerate(fl):
            f = d / "raw" / f"{i:05d}.jpg"
            if not f.exists():
                Image.fromarray(hc.band_crop(hc.load(ms), band2, cfg["side"])).save(f, quality=95)
            lines.append(f"{i:03d} {hc.mss(ms)} {f.as_posix()}")
            rows.append((i, hc.mss(ms), f, f))
        (d / "frames.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        ev = ca.events_text(o._PlanTurn(tid, rows))
        assert ev.startswith(f"== {tid} ·"), ev[:80]
        (d / "events.txt").write_bytes((ev + "\n").encode("utf-8"))
        task = call_task(n, len(fl), tid, d, d / "work")
        old = "`opusread_1118` · `claudeagent_1119` · `geminiagent_1118`"
        task = task.replace(old, "`opusread_*` · `rawread_*` · `rawhand_*` · `m2bsub_*` · `claudeagent_*` · `geminiagent_*` · `mottrack_*` · `idsolve_*` · `hands_*` · `slotgrid_*`")
        if start != a[4]:   # 앞 차례 버림 직후 시작 — 앞 차례 끝 줄의 정의(울기로 패를 빼기 직전 줄)와 번호를 맞춤
            task = task.replace("\n## 보면 안 되는 것", f"""
## 이 차례만 다른 점(시작 줄)
- 첫 프레임 무렵에는 바로 앞 차례에 뽑은 패를 줄에 넣는 동작이 아직 이어질 수 있다. 원래 번호 1 ~ {n} 은 (위의 "첫 프레임의 줄" 대신) **울기로 줄에서 첫 패를 빼기 직전의 {n}장 줄**에 붙인다(그 프레임 번호를 why 에 적는다).
""" + "\n## 보면 안 되는 것", 1)
        (d / "TASK.md").write_bytes(task.encode("utf-8"))
        print(f"{tid} n={n} {len(fl)}장 {hc.mss(fl[0])} ~ {hc.mss(fl[-1])} · 경계 {t['cut']['start']} ~ {t['cut']['end']} · 버림 {t['cut'].get('discard')} → {d}", flush=True)


def call_back(tid: str, after: list, gone_tiles: list, sch) -> tuple:
    """울기 차례 answer.json(gone · k · end_order)으로 울기 전 줄 n장을 만든다. 못 쓰면 (None, 까닭).
    after = 끝 줄 n−3장(패), gone_tiles = 손에서 울기로 나간 두 장 + 버린 패(rebuild_opus 가 넘기는 꼴)."""
    from replay import key
    f = hc.WORK / READ_ROOT / tid / "answer.json"
    if not f.exists():
        return None, "answer.json 없음"
    a = _orig_jload(f)
    n = len(after) + 3
    try:
        eo = [int(x) for x in a.get("end_order") or []]
        gone = [int(x) for x in a.get("gone") or []]
        k = int(a["k"])
    except (TypeError, ValueError, KeyError) as e:
        return None, f"답 꼴 이상 {e}"
    if len(eo) != n - 3 or len(gone) != 2 or sorted(eo + gone + [k]) != list(range(1, n + 1)):
        return None, f"번호가 1 ~ {n} 을 한 번씩 덮지 않음(end_order {eo} · gone {gone} · k {k})"
    before = [None] * n
    for p, lab in enumerate(eo):
        before[lab - 1] = after[p]
    meld = list(gone_tiles[:-1])
    note = ""
    if len(set(meld)) > 1:   # 치: 어느 칸이 어느 패인지는 영상이 말해 주지 않음 → 정렬 순서로(왼쪽 칸에 작은 패)
        meld = sorted(meld, key=lambda v: (key(v, sch) is None, key(v, sch) or 0))
        note = f"치 두 장 {meld} 을 칸 {sorted(gone)} 에 정렬 순서로 붙임(어느 칸이 어느 패인지는 짐작)"
    for pos, v in zip(sorted(gone), meld):
        before[pos - 1] = v
    before[k - 1] = gone_tiles[-1]
    return before, note or "울기 칸 · 버린 칸 · 끝 줄 순서 = Opus 답"


def cmd_status(games: list):
    import turncut as tc
    cut = {g["id"]: g for g in tc.cut_games()}
    det = hc.WORK / "slotgrid_1117"
    for gid in games:
        cf = htr.remap(hc.CONFIG / f"{gid}.json")
        od = htr.remap(hc.OUT / gid)
        s = rec_src(gid)
        try:
            ts = turns_h3(gid)
        except StopIteration:
            ts = None
        rd = hc.WORK / READ_ROOT
        ids = read_ids(gid) if ts else []
        ans = sum((rd / i / "answer.json").exists() for i in ids)
        print(f"{gid}: 설정 {'O' if cf.exists() else 'X'} · sheet_band {'O' if cf.exists() and 'sheet_band' in hc.config(gid) else 'X'} · "
              f"game.json {'O' if (od / 'game.json').exists() else 'X'} · 차례 {len(ts) if ts else 'X'} · "
              f"기록기 {'O' if s['dart'].exists() else 'X'}/{'O' if s['paifu'].exists() else 'X'} · 판 결과 읽기 {'O' if s['result'].exists() else 'X'} · "
              f"rec 링크 {'O' if (PREP / 'rec' / gid / 'dart_overlay_v2.json').exists() else 'X'} · 경계 {len(cut[gid]['turns']) if gid in cut else 'X'} · "
              f"칸 틀 {'O' if (det / f'det_{gid}.json').exists() else 'X'} · 읽을 차례 {len(ids)} · 답 {ans}")


def passthrough(mod: str, args: list):
    name = {"rebuild": "rebuild_opus"}.get(mod, mod)
    if name == "turncut" and args[:1] == ["build"] and "--out" not in args:
        args = args + ["--out", str(CUT_H3)]
    m = __import__(name)
    sys.argv = [str(HERE / f"{name}.py")] + args
    try:
        m.main()
    finally:
        if ANCHOR_RELAXED:
            f = PREP / "anchor_relaxed.json"
            old = _orig_jload(f) if f.exists() else []
            keep = {(x["tid"], x["ms"]) for x in old}
            _wj(f, old + [x for x in ANCHOR_RELAXED if (x["tid"], x["ms"]) not in keep])
            print("시작 줄을 가림 무시로 잡은 차례:", sorted({x["tid"] for x in ANCHOR_RELAXED if x["tid"]}))
        if END_FALLBACK:
            f = PREP / "end_fallback.json"
            old = _orig_jload(f) if f.exists() else []
            _wj(f, [x for x in old if x["tid"] not in {y["tid"] for y in END_FALLBACK}] + END_FALLBACK)
            print("끝 줄을 못 찾아 창 끝까지 준 차례:", [x["tid"] for x in END_FALLBACK])
            if name == "opusread" and "--root" in args:
                root = hc.WORK / args[args.index("--root") + 1]
                fx = _fix()
                for x in END_FALLBACK:
                    tf = root / x["tid"] / "TASK.md"
                    if tf.exists():
                        s = tf.read_text(encoding="utf-8")
                        if "## 이 차례만 다른 점(끝 줄)" not in s:
                            ts = turns_h3(CFG.game_of(x["tid"]))
                            k = next(i for i, t in enumerate(ts) if t["id"] == x["tid"])
                            n = ts[k]["n_calc"]
                            nxt_call = k + 1 < len(ts) and (fx.get(ts[k + 1]["id"]) or {}).get("kind") == "call"
                            note = END_NOTE.format(n=n) + (END_NOTE_CALL if nxt_call else "")
                            s = s.replace("\n## 보면 안 되는 것", note + "\n## 보면 안 되는 것", 1)
                            tf.write_bytes(s.encode("utf-8"))
                            print("  TASK.md 에 끝 줄 안내 덧붙임:", x["tid"])


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    configure(hcfg.from_argv(a))   # --hanchan · --prep 를 꺼내고(a 에서 지움) 겹침 검사
    if not a:
        print(__doc__)
        return
    patch()
    cmd, rest = a[0], a[1:]
    games = [x for x in rest if not x.startswith("--")] or H3
    if cmd == "turns":
        cmd_turns(games)
    elif cmd == "recfix":
        cmd_recfix(games)
    elif cmd == "callprep":
        ids = rest[rest.index("--ids") + 1].split(",") if "--ids" in rest else CALL_TURNS
        cmd_callprep(ids, rest[rest.index("--root") + 1] if "--root" in rest else READ_ROOT)
    elif cmd == "link":
        cmd_link(games)
    elif cmd == "fix":
        cmd_fix(games, "--write" in rest)
    elif cmd == "ids":
        for g in games:
            print(g, ",".join(read_ids(g)))
    elif cmd == "status":
        cmd_status(games)
    else:
        passthrough(cmd, rest)


if __name__ == "__main__":
    main()
