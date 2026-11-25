"""대국 뒤 자동 패보 — 반장 설정 자동 만들기 · 시작 보고(2026-11-25, 설계서 docs/paifu_auto_agent_design_1124.md 3-7 · 8-11 — 구현 2-①, LLM 0).

방문 폴더 하나(experiments/visit_<YYYYMMDD>/ — captures/ + head_rec/)에서 지금 사람이 손으로 쓰는 반장 설정(hanchan/h2_1114.json 꼴)의
코드로 알 수 있는 칸을 채우고, 시작 보고(판 표 · 길 · 경고 · 에이전트 수 · 토큰 어림 · 아직 손 입력으로 남은 칸)를 쓴다.

  python -X utf8 experiments/paifu_frames/paifu_setup.py scan --visit <방문 폴더> [--captures <폴더>] [--head-rec <폴더>] [--date YYYY-MM-DD] [--out <json>]
  python -X utf8 experiments/paifu_frames/paifu_setup.py make --visit <방문 폴더> [--game <대국 id | scan 순번 | 모름-n>] --run <실행 폴더>
                 [--captures …] [--head-rec …] [--date …] [--no-replay]
                 [시험용: --id-prefix <글자> · --id-start <번호> · --rerun-of <설정 id> · --sticks x1,y1,x2,y2 · --sticks-by-track HHMMSS=x1,y1,x2,y2(여러 번) · --clock-offset-ms <ms>]
(저장소 루트에서. make 는 <실행 폴더>/hanchan_auto.json · start_report.md · start_report.json 과 버림 수 어림용 <실행 폴더>/setup/ 만 쓴다.
 다음은 paifu_auto.py init --hanchan <실행 폴더>/hanchan_auto.json --run <실행 폴더> → next.)

scan — 촬영 기록을 날짜 통째로(00:00:00 ~ 23:59:59) app_record.collect 로 판으로 묶고(묶기 규칙 REDUCE_RULE 은 app_record 그대로),
  그 판들을 앱 대국 id(추적 폴더 round_key 첫 칸 = app_record 의 game_key)로 나눈다. 대국 id 가 없는 판(추적 폴더 없이 화료 · 유국 폴더뿐)은
  CHAIN_RULE 로 앞 · 뒤 판의 대국에 붙이거나 "모름-n" 으로 따로 낸다. 대국마다 시각 범위 · 판 수 · 국 진행 · 결과 있는 판 수 · paifu.json 있는 판 수 ·
  겹치는 녹화 폴더(record.json 의 startedAtMs · endedAtMs — 프레임은 읽지 않음).
  날짜는 방문 폴더 이름(visit_YYYYMMDD)에서, --date 가 이긴다. 판이 0 이면 종료 코드 2.

make — 고른 대국의 설정 · 시작 보고. 칸마다 어디서 왔는지는 설정의 _auto.sources 와 시작 보고에 적는다(설계서 8-11 표).
  멈춤(종료 코드 2 · 설정을 안 씀): 판 0 · 대국이 여럿인데 --game 없음 · 고른 대국과 겹치는 녹화 없음 · 실행 폴더에 state.json 이 이미 있음 ·
    설정 구간으로 다시 모은 판이 scan 의 그 대국 판과 다름(다른 대국 폴더가 섞임).
  겹침 오류(종료 코드 1 · 설정을 안 씀): hanchan_cfg.check_collisions 실패(--id-prefix 로 겹치는 접두사를 강제했을 때 등).
  길 낮춤(멈추지 않고 보고에): paifu.json 없음 → 옆길 가 · 앱 결과 없음 → 옆길 나 · 녹화가 그 판을 다 못 덮음.

정한 것(설계서에 값이 없어 이 파일이 정함 — 보고서에도 그대로):
  PREFIX_RULE · REC_SLACK_S · CHAIN_RULE · TOKEN_RULE(아래 상수).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "handtrack"))
import app_record as ar  # noqa: E402
import hanchan_cfg as hcfg  # noqa: E402

RES = HERE / "results"
SIDES = ar.SIDES
DAY = ("00:00:00", "23:59:59")
EXE_FALLBACK = RES / "han3_1123" / "_bin" / "replay_recorder.exe"   # 기록기 exe 사본 출처(읽기만 — 보호 폴더, paifu_auto 와 같은 곳)

# 녹화 고르기: record.json 의 [startedAtMs, endedAtMs] 가 대국 구간(태블릿 시계 — 첫 폴더 · 추적 프레임 ~ 끝 폴더)과 이만큼의 여유 안에서 겹치면 그 녹화를 쓴다.
# 까닭: 태블릿 시계와 헤드 폰 시계가 다르다(11-15 짝 자료 −0.4초, W5 버림 맞춤 p10 −3초 · p90 +0.4초). 1분은 그 차의 스무 배 남짓 — 시계 차 때문에
# 겹치는 녹화를 놓치지 않을 만큼만 넓게(겹치지 않는 녹화가 끼어도 S0 가 장수만 셀 뿐이고, 빠지면 판을 못 읽음). 판마다 "덮음" 판정은 여유 없이 한다.
REC_SLACK_S = 60
# 대국 id 없는 판 붙이기(CHAIN_RULE): 날짜 통째 판 목록(시각 순)에서 바로 앞 판과 (1) 시각이 이어지고(이 판 첫 시각 − 앞 판 끝 시각 ≤ CHAIN_GAP_S)
# (2) 국 진행이 맞으면(앞 판 결과를 알면 app_record._next_round 와 같은 값, 모르면 (같은 국, 본장 + 1) · (다음 국, 0) · (다음 국, 본장 + 1) 중 하나) 앞 판의 대국에 붙인다.
# 안 되면 바로 뒤 판(대국 id 있음)과 같은 검사로 뒤 판의 대국에 붙인다. 둘 다 안 되면 "모름-n" 새 대국(뒤따르는 대국 id 없는 판은 같은 규칙으로 여기에 이어 붙음).
# CHAIN_GAP_S 는 대국 id 없는 판의 시각이 끝 폴더 하나뿐이라 판 한 판의 길이를 품어야 한다 — 11-14 추적이 있는 판 18개(추적 첫 프레임 ~ 끝 폴더)는
# 둘째 긴 것이 11.4분, 가장 긴 것이 1반장 첫 판 19.6분(대국 준비 중 추적 시작 포함). 20분은 그 위 짐작 값(3반장 대역 11판의 끝 폴더 틈은 3.5 ~ 9분).
CHAIN_GAP_S = 20 * 60
CHAIN_RULE = (f"대국 id 없는 판: 바로 앞 판과 시각이 이어지고(≤ {CHAIN_GAP_S // 60}분) 국 진행이 맞으면 앞 판의 대국, 아니면 바로 뒤 판(대국 id 있음)과 같은 검사로 뒤 판의 대국, "
              "둘 다 아니면 '모름-n'(이어지는 대국 id 없는 판은 같은 규칙으로 이어 붙음). 국 진행 = 앞 판 결과를 알면 app_record._next_round, 모르면 "
              "(같은 국, 본장+1) · (다음 국, 0) · (다음 국, 본장+1) 중 하나")
# 판 id 접두사(PREFIX_RULE): 판 id = <글자><두 자리 순번>_<추적 폴더 시각(없으면 끝 폴더 시각)>(app_record.collect 의 꼴 그대로, 순번은 01 부터).
# 글자는 a ~ z 차례로, 아래 자리 어디에도 "<글자><두 자리 숫자>_" 로 시작하는 이름이 없는 첫 글자 — 그다음 hanchan_cfg.check_collisions 가 통과해야 함.
PREFIX_LETTERS = "abcdefghijklmnopqrstuvwxyz"
PREFIX_RULE = ("판 id = <글자><두 자리 순번(01부터)>_<추적 폴더 HHMMSS, 없으면 끝 폴더 HHMMSS>. 글자는 a ~ z 차례로, 기존 판 목록(testtruth_1116 turns · turns_cut*) · "
               "정답 파일 차례 id · hanchan/*.json 판 · sam2track.GAMES · results/ 폴더 이름 · results/handtrack 판 폴더 · _work 차례 폴더 · handtrack/config 손 설정 · "
               "assets/paifu*/ 파일 이름 어디에도 '<글자>NN_' 이 없는 첫 글자, 그리고 hanchan_cfg.check_collisions 통과")
# 토큰 어림(TOKEN_RULE — 설계서 8-11 의 상수 그대로, 위쪽 어림):
TOK_PREP = (130_000, 180_000, "준비(S6a) 판당 13 ~ 18만 — metrics 표 12-126")
TOK_TURN = (80_000, 190_000, "차례 읽기 하나 8 ~ 19만 — metrics 표 12-116")
TOK_SUP = (100_000, 140_000, "판 supervisor 10 ~ 14만(+ 다시 읽기) — metrics 표 12-129")
TURN_FALLBACK = 20   # 앱 버림 기록을 이 자리에서 못 얻은 판(추적 재생 출력 없음 · 헤드 녹화만)의 손패 주인 차례 수(짐작 — 위쪽)
TOKEN_RULE = ("손패 주인이 있는 판마다 준비 1 + 차례 읽기 n + supervisor 1. n = 앱 기록의 손패 주인 버림 중 첫 리치 버림까지(리치 뒤 쯔모기리는 안 읽음 — 위쪽 어림, "
              "울기 차례는 그 뒤 버림으로 이미 셈). 유국 손패 주인 = 텐파이 하나면 그 자리, 둘 이상이면 paifu_auto APP_HERO_RULE(울기 적은 자리 → 리치 → 선부터)을 "
              "앱 버림 기록에 적용. 토큰 = Σ판 (준비 + n × 차례 읽기 + supervisor) 의 낮은 값 ~ 높은 값. 다시 읽기 · 유국 공개 손패 읽기(S4, 판당 둘 · 다르면 셋)의 토큰은 "
              f"상수가 없어 넣지 않음(에이전트 수에만). 앱 버림을 못 얻은 판은 n = {TURN_FALLBACK}(짐작)")


# ------------------------------------------------------------------ 작은 도구
def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o):
    ar.wj(p, o)


def wt(p, s: str):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(s.encode("utf-8"))


def stop(msg: str, code: int = 2):
    print("멈춤: " + msg, file=sys.stderr)
    raise SystemExit(code)


def visit_date(visit: Path, date_opt: str | None) -> str:
    if date_opt:
        return date_opt
    m = re.fullmatch(r"visit_(\d{4})(\d{2})(\d{2})", visit.name)
    if not m:
        stop(f"방문 폴더 이름 {visit.name} 에서 날짜를 못 읽음 — --date 를 줄 것")
    return f"{m[1]}-{m[2]}-{m[3]}"


def hms(ms: int) -> str:
    return ar.hms_of(ms, 0)


def folder_ms(date: str, folder: str) -> int:
    return ar.ms_of(date, ar._folder_time(folder)[1])


# ------------------------------------------------------------------ 녹화
def read_recs(head_rec: Path) -> list:
    out = []
    if not head_rec.exists():
        return out
    for d in sorted(head_rec.iterdir()):
        f = d / "record.json"
        if not (d.is_dir() and f.exists()):
            continue
        o = jl(f)
        out.append({"rec": d.name, "start_ms": o.get("startedAtMs"), "end_ms": o.get("endedAtMs"), "start": hms(o["startedAtMs"]) if o.get("startedAtMs") else None,
                    "end": hms(o["endedAtMs"]) if o.get("endedAtMs") else None, "saved": o.get("saved"), "final": o.get("final"),
                    "saved_size": [o.get("savedWidth"), o.get("savedHeight")]})
    return out


def overlapping(recs: list, t0: int, t1: int, slack_s: int = REC_SLACK_S) -> list:
    s = slack_s * 1000
    return [x for x in recs if x["start_ms"] is not None and x["end_ms"] is not None and x["start_ms"] < t1 + s and x["end_ms"] > t0 - s]


def coverage(recs: list, t0: int, t1: int) -> str:
    """판 구간 [t0, t1](태블릿 시계)을 고른 녹화가 덮는지 — 여유 없이."""
    if any(x["start_ms"] <= t0 and x["end_ms"] >= t1 for x in recs):
        return "덮음"
    if overlapping(recs, t0, t1, 0):
        return "일부"
    return "못 덮음"


# ------------------------------------------------------------------ 판 · 대국
def round_span(r: dict, date: str) -> tuple[int, int]:
    """판 구간(태블릿 시계 ms): 폴더 시각 · 추적 첫 · 끝 프레임 · 끝 닻 중 가장 이른 것 ~ 가장 늦은 것."""
    ts = [folder_ms(date, f) for f in r["folders"]["all"]]
    a = r["anchors"]
    for k in ("track_first", "track_last", "end"):
        if a.get(k):
            ts.append(ar.ms_of(date, a[k]))
    return min(ts), max(ts)


def round_spans(rounds: list, date: str) -> list:
    """한 대국의 판들 → [(t0, t1, 시작을 아나)]. 추적 폴더가 없는 판(화료 · 유국 폴더뿐)은 시작 시각을 몰라 앞 판 끝을 시작으로 둔다(첫 판이면 끝 시각 하나)."""
    out = []
    for k, r in enumerate(rounds):
        t0, t1 = round_span(r, date)
        known = bool(r["folders"]["track"])
        if not known and k:
            t0 = min(t0, out[-1][1])
        out.append((t0, t1, known))
    return out


def folder_range(rounds: list) -> tuple[str, str]:
    ts = sorted(ar._folder_time(f)[1] for r in rounds for f in r["folders"]["all"])
    return ts[0], ts[-1]


def fits(a: dict, b: dict) -> tuple[bool, str]:
    """a 다음 판이 b 일 수 있나(국 진행)."""
    if a.get("kyoku_index") is None or b.get("kyoku_index") is None:
        return False, "국 이름을 모름"
    want = ar._next_round(a)
    got = (b["kyoku_index"], b["honba"])
    if want is not None:
        return want == got, f"앞 판 결과로 {ar._kyoku_name(want[0])} {want[1]}본장"
    k, h = a["kyoku_index"], a["honba"]
    cand = [(k, h + 1), (k + 1, 0), (k + 1, h + 1)]
    return got in cand, "앞 판 결과 모름 — " + " · ".join(f"{ar._kyoku_name(x)} {y}본장" for x, y in cand)


def split_games(rounds: list, date: str) -> list:
    """판(시각 순) → 대국 목록(첫 판 시각 순). 대국 = {"key", "rounds", "attach"}."""
    games, by_key, owner = [], {}, {}
    unknown_n = 0
    spans = [round_span(r, date) for r in rounds]
    for i, r in enumerate(rounds):
        gk = r.get("game_key")
        if gk:
            if gk not in by_key:
                by_key[gk] = {"key": gk, "rounds": [], "attach": {}, "warnings": []}
                games.append(by_key[gk])
            g = by_key[gk]
            if g["rounds"] and owner.get(i - 1) is not g:
                g["warnings"].append(f"{r['id']}: 같은 대국 id 의 판이 다른 대국 판 뒤에 다시 나옴")
            g["rounds"].append(r)
            owner[i] = g
            continue
        why = None
        if i > 0:
            gap = (spans[i][0] - spans[i - 1][1]) / 1000
            ok, how = fits(rounds[i - 1], r)
            if gap <= CHAIN_GAP_S and ok:
                g = owner[i - 1]
                why = f"앞 판 {rounds[i - 1]['id']}({rounds[i - 1]['round_label']})에 이어 붙임 — 틈 {gap:.0f}초 · {how}"
        if why is None and i + 1 < len(rounds) and rounds[i + 1].get("game_key"):
            gap = (spans[i + 1][0] - spans[i][1]) / 1000
            ok, how = fits(r, rounds[i + 1])
            if gap <= CHAIN_GAP_S and ok:
                gk2 = rounds[i + 1]["game_key"]
                if gk2 not in by_key:
                    by_key[gk2] = {"key": gk2, "rounds": [], "attach": {}, "warnings": []}
                    games.append(by_key[gk2])
                g = by_key[gk2]
                why = f"뒤 판 {rounds[i + 1]['id']}({rounds[i + 1]['round_label']})의 대국에 붙임 — 틈 {gap:.0f}초 · 이 판 결과로 {how}"
        if why is None:
            unknown_n += 1
            g = {"key": None, "unknown": f"모름-{unknown_n}", "rounds": [], "attach": {}, "warnings": []}
            games.append(g)
            why = "앞 · 뒤 판과 이어지지 않아 새 '대국 모름'"
        g["rounds"].append(r)
        g["attach"][r["id"]] = why
        owner[i] = g
    for g in games:
        g["rounds"].sort(key=lambda r: rounds.index(r))
    games.sort(key=lambda g: rounds.index(g["rounds"][0]))
    return games


def result_sig(x: dict):
    """결과 폴더 하나의 내용(같은 판의 결과 폴더끼리 견줌)."""
    if x.get("kind") == "draw":
        ch = x.get("chosen")
        return ("draw", tuple(sorted(ch.get("tenpai_seats") or []))) if ch else None
    src = x.get("label") or (x.get("meta") or {}).get("merge") or None
    if not src or src.get("winner") is None:
        return None
    return ("win", src.get("winner"), bool(src.get("is_tsumo")), src.get("loser"), src.get("win_tile"), tuple(src.get("closed") or []))


def multi_result(r: dict, captures: Path) -> dict | None:
    """한 판에 결과 폴더(화료 · 유국)가 여럿이면 {folders, differ}."""
    fs = [f for f in r["folders"]["all"] if not f.endswith("_track")]
    if len(fs) < 2:
        return None
    sigs = {}
    for f in fs:
        kind = "draw" if f.endswith("_draw") else "win"
        sigs[f] = result_sig(ar._read_folder(captures / f, kind))
    known = {v for v in sigs.values() if v is not None}
    return {"folders": fs, "used": r["folders"]["end"], "with_content": [f for f, v in sigs.items() if v is not None], "differ": len(known) > 1}


def game_name(g: dict) -> str:
    return g["key"] if g["key"] else g["unknown"]


def game_summary(g: dict, idx: int, date: str, recs: list, captures: Path) -> dict:
    rs = g["rounds"]
    f0, f1 = folder_range(rs)
    spans = round_spans(rs, date)
    t0, t1 = min(s[0] for s in spans), max(s[1] for s in spans)
    prog, breaks = [], []
    for k, r in enumerate(rs):
        prog.append(r["round_label"])
        if k:
            ok, how = fits(rs[k - 1], r)
            if not ok:
                breaks.append(f"{rs[k - 1]['round_label']} → {r['round_label']}({how})")
    multi = [dict(id=r["id"], **m) for r in rs for m in [multi_result(r, captures)] if m]
    ov = overlapping(recs, t0, t1)
    started = None
    if g["key"] and str(g["key"]).isdigit() and len(str(g["key"])) == 13:
        started = hms(int(g["key"]))
    return {"index": idx, "game": game_name(g), "game_key": g["key"], "game_key_time": started,
            "folders": [f0, f1], "span": [hms(t0), hms(t1)], "span_ms": [t0, t1], "rounds": len(rs),
            "round_ids_scan": [r["id"] for r in rs], "progression": prog, "progression_breaks": breaks,
            "results": sum(1 for r in rs if (r.get("result") or {}).get("recorded")), "wins": sum(1 for r in rs if r["end"] == "win"),
            "draws": sum(1 for r in rs if r["end"] == "draw"), "unknown_end": sum(1 for r in rs if r["end"] == "unknown"),
            "paifu_json": sum(1 for r in rs if r["discard_source"].get("paifu_json")), "track": sum(1 for r in rs if r["folders"]["track"]),
            "recordings": [x["rec"] for x in ov], "multi_result_folders": multi, "attach": g["attach"], "warnings": g["warnings"],
            "names": next((r["names"] for r in rs if r.get("names")), None)}


def scan_visit(visit: Path, captures: Path | None, head_rec: Path | None, date_opt: str | None) -> dict:
    visit = ar._p(visit)
    captures = ar._p(captures) if captures else visit / "captures"
    head_rec = ar._p(head_rec) if head_rec else visit / "head_rec"
    date = visit_date(visit, date_opt)
    if not captures.exists():
        stop(f"촬영 기록 폴더 없음: {captures}")
    day = ar.collect(captures, date, *DAY)
    recs = read_recs(head_rec)
    games = split_games(day["rounds"], date) if day["rounds"] else []
    out = {"_note": "paifu_setup.py scan — 날짜 통째 촬영 기록 → 앱 대국 id 로 나눈 대국(시각은 태블릿 시계). 판 id 는 날짜 통째 모으기의 임시 이름(a01 …)",
           "made": datetime.now().isoformat(timespec="seconds"), "visit": ar.rel(visit), "captures": ar.rel(captures), "head_rec": ar.rel(head_rec), "date": date,
           "rules": {"reduce": ar.REDUCE_RULE, "chain": CHAIN_RULE, "rec_slack_s": REC_SLACK_S},
           "recordings": [{k: v for k, v in x.items()} for x in recs], "loose": day["loose"], "collect_warnings": day["warnings"],
           "games": [game_summary(g, i + 1, date, recs, captures) for i, g in enumerate(games)]}
    out["_games"] = games      # make 가 씀(파일에는 안 씀)
    out["_day"] = day
    return out


def print_scan(o: dict):
    print(f"방문 {o['visit']} · 날짜 {o['date']} · 촬영 기록 {o['captures']} · 녹화 {', '.join(f'{x['rec']}({x['start']} ~ {x['end']})' for x in o['recordings']) or '없음'}")
    print(f"{'#':>2} {'대국 id':14s} {'시작(id)':8s} {'폴더 시각':19s} {'판':>2} {'결과':>2} {'paifu':>5} {'추적':>2}  녹화 · 국 진행")
    for g in o["games"]:
        print(f"{g['index']:>2} {g['game']:14s} {g['game_key_time'] or '-':8s} {g['folders'][0]} ~ {g['folders'][1]} {g['rounds']:>2} {g['results']:>2} {g['paifu_json']:>5} {g['track']:>2}  "
              f"{','.join(g['recordings']) or '겹치는 녹화 없음'} · {' → '.join(g['progression'])}")
        for b in g["progression_breaks"]:
            print(f"     국 진행 끊김: {b}")
        for gid, w in g["attach"].items():
            print(f"     대국 id 없는 판 {gid}: {w}")
        for m in g["multi_result_folders"]:
            print(f"     결과 폴더 여럿 {m['id']}: {m['folders']} → {m['used']}{' · 내용 다름' if m['differ'] else ''}")
        for w in g["warnings"]:
            print(f"     경고: {w}")
    if o["loose"]:
        print("묶지 못한 폴더:", o["loose"])


# ------------------------------------------------------------------ 접두사
def used_prefix_letters(exclude: Path | None = None) -> dict:
    """'<글자>NN_' 꼴 이름이 이미 있는 글자 → 어디서(첫 예)."""
    pat = re.compile(r"^([A-Za-z])\d\d_")
    used = {}

    def add(name, where):
        m = pat.match(name)
        if m and m[1] not in used:
            used[m[1]] = f"{name} ({where})"
    base = hcfg.BASE
    for f in ([base / "turns.json"] if (base / "turns.json").exists() else []) + sorted(base.glob("turns_cut*.json")):
        for g in jl(f).get("games", []):
            add(g["id"], ar.rel(f))
    for f in hcfg.TRUTH_FILES:
        if f.exists():
            for k in jl(f):
                add(k, ar.rel(f))
    for f in sorted(hcfg.CFG_DIR.glob("*.json")):
        o = jl(f)
        for g in o.get("games") or []:
            add(g, ar.rel(f))
        for k in o.get("turn_prefix") or {}:
            add(k + "_", ar.rel(f))
    s2 = HERE / "handtrack" / "sam2track.py"
    if s2.exists():
        m = re.search(r"^GAMES\s*=\s*\(([^)]*)\)", s2.read_text(encoding="utf-8"), re.M)
        for g in re.findall(r"\"([^\"]+)\"", m[1]) if m else []:
            add(g, "sam2track.GAMES")
    for d in (RES, RES / "handtrack", hcfg.WORK, HERE / "handtrack" / "config"):
        if d.exists():
            for p in d.iterdir():
                add(p.stem if p.is_file() else p.name, ar.rel(d))
    for f in sorted(RES.glob("*/hanchan*.json")):       # 다른 실행 폴더의 설정(자동 설정 · paifu_auto 실행 설정) — 다른 대국의 자동 설정과 접두사가 겹치지 않게
        if exclude is not None and f.parent.resolve() == exclude.resolve():
            continue
        try:
            o = jl(f)
        except (OSError, json.JSONDecodeError):
            continue
        for g in o.get("games") or [] if isinstance(o, dict) else []:
            add(g, ar.rel(f))
    for d in sorted((ROOT / "assets").glob("paifu*")):
        if d.is_dir():
            for p in d.iterdir():
                add(p.stem.removeprefix("h3_").removeprefix("h2_"), ar.rel(d))
    return used


# ------------------------------------------------------------------ make
def pick_game(games: list, sel: str | None) -> dict:
    if not games:
        stop("판이 0 — 이 날짜의 촬영 기록에 판이 없음")
    if sel is None:
        if len(games) > 1:
            stop(f"대국이 {len(games)}개 — --game <대국 id 또는 scan 순번> 으로 고를 것: " + ", ".join(f"{i + 1}={game_name(g)}" for i, g in enumerate(games)))
        return games[0]
    for i, g in enumerate(games):
        if sel in (str(g["key"]), g.get("unknown"), str(i + 1)):
            return g
    stop(f"--game {sel}: 그런 대국이 없음 — " + ", ".join(f"{i + 1}={game_name(g)}" for i, g in enumerate(games)))


def sticks_of_tracks(rounds: list, captures: Path) -> tuple[str | None, dict, list]:
    """앱이 추적 zip(frames.json grid.sticks)에 남긴 리치봉 구역 → (대국 기본값 = 프레임 수로 가장 흔한 값, 추적 폴더 HHMMSS → 값(기본값과 다른 것만), 메모)."""
    tot, per, notes = {}, {}, []
    for r in rounds:
        tf = r["folders"]["track"]
        if not tf:
            continue
        it = ar._read_folder(captures / tf, "track")
        c = {}
        for z in it.get("zips") or []:
            s = (z.get("grid") or {}).get("sticks")
            if s:
                k = ",".join(str(int(v)) for v in s)
                c[k] = c.get(k, 0) + z["n"]
                tot[k] = tot.get(k, 0) + z["n"]
        if c:
            best = max(c.items(), key=lambda kv: (kv[1], kv[0]))[0]
            per[tf.split("_")[1]] = best
            if len(c) > 1:
                notes.append(f"{tf}: zip 마다 리치봉 구역이 다름 {c} — 프레임이 가장 많은 {best}")
    if not tot:
        return None, {}, ["추적 zip 이 없어 앱 리치봉 구역 없음"]
    default = max(tot.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return default, {k: v for k, v in per.items() if v != default}, notes


def parse_sticks(s: str) -> str:
    v = [int(x) for x in s.split(",")]
    if len(v) != 4:
        raise SystemExit(f"리치봉 구역은 x1,y1,x2,y2 넷: {s}")
    return ",".join(map(str, v))


# ------------------------------------------------------------------ 펠트 격자(구현 2-② — 설계서 8-12 (가))
DART = "C:/Users/jjh7757/flutter/bin/dart.bat"     # headrec_run.py 와 같은 dart(bash PATH 에 없음)
FELT_SRC = HERE / "felt_sticks.dart"
# 판마다 뽑는 프레임(FELT_N): 판 구간(태블릿 시계 — 헤드 녹화 시계와의 차 −0.4초는 무시)을 FELT_N + 1 등분한 점마다 가장 가까운 프레임 하나(양 끝 —
# 배패 · 공개 장면 — 은 뺌). 손이 펠트 변을 덮은 프레임은 readFelt 가 ok 가 아니라 빠지고, 남은 것의 네 모서리 중앙값(medianFelt)으로 격자를 만든다.
# 15 는 짐작 값(판 9개 × 2 출처 × 15장 = 270장, 1496² 디코드 · 판독이 한 장 수백 ms). 헤드 녹화는 목표 시각에서 FELT_NEAR_MS 안에 프레임이 없으면 그 점을 뺀다.
FELT_N = 15
FELT_NEAR_MS = 5000
_REC_FRAMES: dict = {}


def rec_frame_ms(rec_dir: Path) -> list:
    if rec_dir not in _REC_FRAMES:
        import os
        ms = []
        with os.scandir(rec_dir) as it:
            for e in it:
                if e.name.startswith("f_") and e.name.endswith(".jpg"):
                    ms.append(int(e.name[2:-4]))
        ms.sort()
        _REC_FRAMES[rec_dir] = ms
    return _REC_FRAMES[rec_dir]


def pick_rec_frames(recs: list, head_rec: Path, t0: int, t1: int, n: int = FELT_N) -> list:
    import bisect
    out = []
    for k in range(1, n + 1):
        t = t0 + (t1 - t0) * k / (n + 1)
        best = None
        for x in recs:
            if not (x["start_ms"] <= t <= x["end_ms"]):
                continue
            ms = rec_frame_ms(head_rec / x["rec"])
            i = bisect.bisect_left(ms, t)
            for j in (i - 1, i):
                if 0 <= j < len(ms) and abs(ms[j] - t) <= FELT_NEAR_MS and (best is None or abs(ms[j] - t) < abs(best[0] - t)):
                    best = (ms[j], head_rec / x["rec"] / f"f_{ms[j]}.jpg")
        if best and (not out or out[-1] != best[1].as_posix()):
            out.append(best[1].as_posix())
    return out


def felt_exe(bin_dir: Path) -> Path:
    """felt_sticks.dart → bin_dir/felt_sticks.exe(소스가 새로우면 다시 — headrec_run.build 와 같은 방식)."""
    import subprocess
    exe = bin_dir / "felt_sticks.exe"
    if exe.exists() and exe.stat().st_mtime > FELT_SRC.stat().st_mtime:
        return exe
    bin_dir.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([DART, "compile", "exe", str(FELT_SRC.relative_to(ROOT)), "-o", str(exe)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise SystemExit("felt_sticks.dart 빌드 실패: " + p.stdout[-2000:] + p.stderr[-2000:])
    return exe


def app_grid_of(captures: Path, track_folder: str | None) -> dict | None:
    """추적 zip 의 저장 격자(frames.json grid) 중 프레임이 가장 많은 것."""
    if not track_folder:
        return None
    it = ar._read_folder(captures / track_folder, "track")
    c = {}
    for z in it.get("zips") or []:
        if z.get("grid"):
            k = json.dumps(z["grid"], sort_keys=True)
            c[k] = c.get(k, 0) + z["n"]
    return json.loads(max(c.items(), key=lambda kv: (kv[1], kv[0]))[0]) if c else None


def felt_rounds(rounds: list, ids: list, date: str, captures: Path, head_rec: Path, recs: list, out_dir: Path, n: int = FELT_N) -> dict:
    """판마다 추적 zip · 헤드 녹화 프레임에서 펠트 리치봉 구역 → {판 id: 행}. felt_sticks.dart 를 한 번 부름(out_dir/felt_spec.json · felt_out.json)."""
    import subprocess
    jobs, meta = [], {}
    spans = round_spans(rounds, date)
    for r, gid, (t0, t1, _) in zip(rounds, ids, spans):
        tf = r["folders"]["track"]
        app = app_grid_of(captures, tf)
        meta[gid] = {"track": tf, "app_grid": app, "span": [hms(t0), hms(t1)]}
        if tf:
            zips = sorted(str(z) for z in (captures / tf).glob("frames_*.zip"))
            if zips:
                jobs.append({"id": f"{gid}|track", "kind": "zip", "zips": zips, "n": n, **({"app_grid": app} if app else {})})
        files = pick_rec_frames(recs, head_rec, t0, t1, n)
        meta[gid]["head_frames"] = len(files)
        if files:
            jobs.append({"id": f"{gid}|head", "kind": "jpg", "files": files, **({"app_grid": app} if app else {})})
    out_dir.mkdir(parents=True, exist_ok=True)
    spec, outp = out_dir / "felt_spec.json", out_dir / "felt_out.json"
    wj(spec, {"jobs": jobs})
    exe = felt_exe(out_dir / "_bin")
    p = subprocess.run([str(exe), str(spec), str(outp)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    wt(out_dir / "felt_stderr.txt", p.stdout + p.stderr)
    if p.returncode != 0:
        raise SystemExit("felt_sticks 실패: " + p.stderr[-2000:])
    res = jl(outp)["jobs"]
    rows = {}
    for gid, m in meta.items():
        tr, hd = res.get(f"{gid}|track") or {}, res.get(f"{gid}|head") or {}
        j = lambda v: ",".join(str(int(x)) for x in v) if v else None  # noqa: E731
        app_st = j((m["app_grid"] or {}).get("sticks"))
        head_st, track_st = j(hd.get("sticks")), j(tr.get("sticks"))
        shift = hd.get("shift") if head_st else None
        smax = hd.get("shift_max") or tr.get("shift_max") or 30
        if head_st is None and (tr.get("shift") or 0) >= smax:
            flag = "앱 격자 어긋남 · 펠트로 못 고침(추적 펠트는 어긋남을 봤으나 헤드 녹화 펠트를 못 읽음)"
        elif head_st is None:
            flag = "격자 확인 못 함(헤드 녹화 프레임에서 펠트를 못 읽음)"
        elif app_st is None:
            flag = "앱 격자 없음(추적 zip 없음) — 견주지 못함"
        elif shift is not None and shift >= smax:
            flag = "앱 격자 어긋남"
        else:
            flag = None
        diff_th = None
        if head_st and track_st:
            diff_th = max(abs(int(x) - int(y)) for x, y in zip(head_st.split(","), track_st.split(",")))
        rows[gid] = {"track": m["track"], "span_tablet": m["span"], "app": app_st, "felt_head": head_st, "felt_track": track_st,
                     "felt_head_minus_track_max": diff_th, "shift_app_vs_felt": shift, "shift_track_job": tr.get("shift"), "shift_max": smax, "flag": flag,
                     "head_read": hd.get("read", 0), "head_ok": hd.get("ok", 0), "head_spread": hd.get("spread"),
                     "track_read": tr.get("read", 0), "track_ok": tr.get("ok", 0), "track_spread": tr.get("spread"), "track_candidates": tr.get("candidates"),
                     "head_frames_picked": m["head_frames"]}
    return rows


def coord_median(vals: list) -> str:
    import statistics
    v = [[int(x) for x in s.split(",")] for s in vals]
    return ",".join(str(round(statistics.median([x[k] for x in v]))) for k in range(4))


def make_ids(rounds: list, letter: str, start: int) -> list:
    if start + len(rounds) - 1 > 99:
        raise SystemExit(f"순번이 두 자리를 넘음(시작 {start} · 판 {len(rounds)})")
    out = []
    for i, r in enumerate(rounds):
        tf = r["folders"]["track"] or r["folders"]["end"] or ""
        out.append(f"{letter}{start + i:02d}_{tf.split('_')[1] if '_' in tf else i}")
    return out


def hero_seat(r: dict, events: list | None):
    res = r.get("result") or {}
    if r["end"] == "win":
        return res.get("winner"), "화료자"
    tp = list(res.get("tenpai") or [])
    if r["end"] != "draw" or not tp:
        return None, ("유국 텐파이 없음" if r["end"] == "draw" and res.get("tenpai") == [] else "결과 모름")
    if len(tp) == 1:
        return tp[0], "유국 — 혼자 텐파이"
    if not events:
        return tp, "유국 텐파이 둘 이상 · 앱 버림 없음 — 어림은 텐파이 자리 중 큰 값"
    from collections import Counter
    calls = Counter(e["seat"] for e in events if e["type"] == "call" and e.get("kind") != "kakan")
    rch = {e["seat"] for e in events if e["type"] == "discard" and e.get("riichi")}
    h = sorted(tp, key=lambda s: (calls.get(s, 0), 0 if s in rch else 1, (s - r["dealer"]) % 4))[0]
    return h, "유국 텐파이 둘 이상 — APP_HERO_RULE(울기 적은 자리 → 리치 → 선부터)"


def turns_of(events: list, seat: int, riichi_label: bool | None = None) -> tuple[int, int, bool]:
    """(손패 주인 버림 수, 첫 리치 버림까지의 수, 리치했나). riichi_label = 화료 판 label.json riichi_seats 에 이 자리가 있나(있으면 그것을 따름 —
    앱 기록기의 리치 표시는 격자가 어긋나면 틀림. False 면 리치로 자르지 않음, None(유국)이면 기록기 표시를 따름)."""
    ds = [e for e in events if e["type"] == "discard" and e["seat"] == seat]
    if riichi_label is False:
        return len(ds), len(ds), False
    for k, e in enumerate(ds):
        if e.get("riichi"):
            return len(ds), k + 1, True
    return len(ds), len(ds), False


def app_events_for_estimate(cfg_raw: dict, o: dict, captures: Path, out: Path, no_replay: bool) -> dict:
    """판 → (앱 버림 사건 | None, 출처). paifu.json → 그 사건 · 추적 재생은 이미 있는 겹쳐 보기 출력(app_record.find_overlay_dump)이 있을 때만
    앱 기록기를 돌려 out/app/<판>/ 에(app_record.build 와 같은 인자 · --sticks 규칙). 겹쳐 보기 출력을 새로 만드는 일(판마다 1 ~ 3분)은 하지 않는다(S0 몫)."""
    ar_cfg = cfg_raw["app_record"]
    st_def = ar_cfg.get("sticks") or (cfg_raw.get("recorder") or {}).get("sticks") or ar.DEFAULT_STICKS
    by_track = ar_cfg.get("sticks_by_track") or {}
    exe = out / "_bin" / "replay_recorder.exe"
    res = {}
    for r in o["rounds"]:
        src = r["discard_source"]
        if src["chosen"] == "paifu_json":
            res[r["id"]] = ((jl(captures / src["paifu_json"] / "paifu.json").get("events") or []), "paifu.json")
            continue
        if src["chosen"] != "track_replay" or no_replay:
            res[r["id"]] = (None, "헤드 녹화만" if src["chosen"] == "headrec" else "--no-replay")
            continue
        tf = r["folders"]["track"]
        cands = ar.find_overlay_dump(captures, tf)
        if not cands:
            res[r["id"]] = (None, "겹쳐 보기 출력이 아직 없음(S0 가 만듦)")
            continue
        ar.ensure_exe(exe, [EXE_FALLBACK])
        sticks = by_track.get(tf.split("_")[1], st_def)
        pj = ar.replay_track(exe, cands[0][1], r["dealer_side"], r["bottom_seat"], sticks, out / "app" / r["id"])
        res[r["id"]] = (pj.get("events") or [], f"앱 기록기 재생({ar.rel(cands[0][1])} · --sticks {sticks})")
    return res


def path_of(r: dict) -> tuple[str, str]:
    res = r.get("result") or {}
    if not res.get("recorded"):
        return "옆길 나", "앱 결과 없음(" + (r["folders"]["end_pick_rule"] or "") + ") — 결과를 영상에서 읽음"
    if not r["discard_source"].get("paifu_json"):
        return "옆길 가", "paifu.json 없음 — " + ("추적 프레임 재생" if r["folders"]["track"] else "추적 프레임도 없음 → 헤드 녹화 재생")
    return "기본", "paifu.json · 앱 결과"


def result_text(r: dict) -> str:
    res = r.get("result") or {}
    b = r["bottom_seat"]
    if r["end"] == "win":
        if not res.get("recorded"):
            return f"화료(결과 없음 · merge 화료자 {res.get('winner')})"
        t = {"ron": "론", "tsumo": "쯔모"}.get(res.get("type"), res.get("type"))
        return f"{t} {ar.side_of(res['winner'], b)}(자리 {res['winner']})" + (f" ← {ar.side_of(res['loser'], b)}" if res.get("loser") is not None and res.get("type") == "ron" else "")
    if r["end"] == "draw":
        tp = res.get("tenpai")
        return "유국 텐파이 " + ("모름" if tp is None else (" · ".join(ar.side_of(s, b) for s in tp) or "없음"))
    return "모름(결과 폴더 없음)"


def cmd_make(a):
    visit = ar._p(a.visit)
    sc = scan_visit(visit, a.captures, a.head_rec, a.date)
    date, captures = sc["date"], ar._p(sc["captures"])
    head_rec = ar._p(sc["head_rec"])
    games = sc["_games"]
    if not sc["_day"]["rounds"]:
        stop(f"판이 0 — {date} 촬영 기록({sc['captures']})에 판이 없음")
    g = pick_game(games, a.game)
    gi = games.index(g) + 1
    gs = sc["games"][gi - 1]
    run = ar._p(a.run)
    if (run / "state.json").exists():
        stop(f"{ar.rel(run)} 에 state.json 이 이미 있음(이미 시작한 실행 폴더) — 새 실행 폴더를 줄 것")
    recs_all = sc["recordings"]
    recs = [x for x in recs_all if x["rec"] in gs["recordings"]]
    if not recs:
        stop(f"대국 {game_name(g)}({gs['span'][0]} ~ {gs['span'][1]}, 태블릿 시계)과 겹치는 녹화가 없음(여유 {REC_SLACK_S}초) — 녹화 {[x['rec'] for x in recs_all] or '없음'}({ar.rel(head_rec)})")
    t_from, t_to = gs["folders"]
    # 설정 구간으로 다시 모아 scan 의 판과 같은지(다른 대국 폴더가 섞이지 않았나)
    test = {}
    letter = None
    if a.id_prefix is not None:
        if not re.fullmatch(r"[A-Za-z]", a.id_prefix):
            raise SystemExit(f"--id-prefix 는 글자 하나: {a.id_prefix!r}")
        letter = a.id_prefix
        test["id_prefix"] = a.id_prefix
    if a.id_start != 1:
        test["id_start"] = a.id_start
    o0 = ar.collect(captures, date, t_from, t_to)
    if [r["folders"]["all"] for r in o0["rounds"]] != [r["folders"]["all"] for r in g["rounds"]]:
        stop(f"설정 구간 {t_from} ~ {t_to} 으로 다시 모은 판({len(o0['rounds'])})이 scan 의 대국 {game_name(g)} 판({len(g['rounds'])})과 다름 — 다른 대국 폴더가 구간 안에 섞임", 3)
    rerun = None
    if a.rerun_of:
        f = hcfg.CFG_DIR / f"{a.rerun_of}.json"
        cand = [f] if f.exists() else [x for x in hcfg.CFG_DIR.glob("*.json") if jl(x).get("id") == a.rerun_of]
        if not cand:
            raise SystemExit(f"--rerun-of {a.rerun_of}: hanchan/ 에 그런 설정이 없음")
        rerun = jl(cand[0])
        test["rerun_of"] = a.rerun_of
    # 리치봉 구역
    app_st, app_by, st_notes = sticks_of_tracks(g["rounds"], captures)
    if a.sticks:
        sticks, st_src = parse_sticks(a.sticks), "option"
        test["sticks"] = sticks
    else:
        sticks, st_src = app_st, "app"
    if a.sticks_by_track:
        by = {}
        for x in a.sticks_by_track:
            k, v = x.split("=", 1)
            by[k] = parse_sticks(v)
        test["sticks_by_track"] = by
    else:
        by = app_by if st_src == "app" else {}
    # 펠트에서 다시 잡기(구현 2-② — 설계서 8-12 (가)): 시험용 --sticks · --sticks-by-track 이 없고 --sticks-source felt(기본)일 때
    felt_rows, grid_check = None, {}
    if a.sticks_source == "app":
        test["sticks_source"] = "app"
    if not a.sticks and not a.sticks_by_track and a.sticks_source == "felt":
        felt_rows = felt_rounds(g["rounds"], [r["id"] for r in g["rounds"]], date, captures, head_rec, recs, run / "setup")
        heads = [x["felt_head"] for x in felt_rows.values() if x["felt_head"]]
        if heads:
            sticks, st_src = coord_median(heads), "felt"
        else:
            st_notes.append("어느 판에서도 헤드 녹화 펠트를 못 읽음 — 앱 값을 둠(격자 확인 못 함)")
        by = {}
        for r in g["rounds"]:
            x, tf = felt_rows[r["id"]], r["folders"]["track"]
            if not tf:
                continue
            v = x["felt_head"] or x["app"]
            if st_src == "felt" and v and v != sticks:
                by[tf.split("_")[1]] = v
            grid_check[tf.split("_")[1]] = {"app": x["app"], "felt": x["felt_head"], "felt_track": x["felt_track"], "shift": x["shift_app_vs_felt"],
                                            "shift_track": x["shift_track_job"], "flag": x["flag"], "fixed_by_felt": x["felt_head"] is not None,
                                            "used": v if st_src == "felt" else (by.get(tf.split("_")[1]) or sticks)}
    if sticks is None:
        st_notes.append(f"리치봉 구역을 못 얻어 기록기 기본값 {ar.DEFAULT_STICKS} 을 씀(헤드 녹화 기록기 상수 — 거치가 다르면 틀림)")
        sticks, st_src = ar.DEFAULT_STICKS, "default"
    clock = 0
    if a.clock_offset_ms is not None:
        clock = a.clock_offset_ms
        test["clock_offset_ms"] = clock
    names = gs["names"] or [f"플레이어 {i}" for i in range(1, 5)]
    label = f"대국 {gi}"
    cid = f"auto_{date[5:7]}{date[8:10]}_g{gi}"

    def cfg_for(L: str) -> dict:
        ids = make_ids(g["rounds"], L, a.id_start)
        c = {"_note": f"paifu_setup.py make 가 {ar.rel(visit)} 의 대국 {game_name(g)}(scan {gi}번)에서 만든 반장 설정({datetime.now().isoformat(timespec='seconds')}). "
                      "칸마다 출처는 _auto.sources, 시험용 옵션은 _auto.test_options(자동 흐름은 안 씀). 손 추적 상자(frame)는 없음 — S6a 가 화면 절반에서 손패 줄 후보를 찾는다(2-③).",
             "id": cid, "label": label, "results_dir": ar.rel(run), "read_root": (run / "read").as_posix(),
             "recording": {"root": ar.rel(head_rec), "recs": [x["rec"] for x in recs], "date": date},
             "games": ids, "turn_prefix": {x[:3]: x for x in ids},
             "recorder": {"sticks": sticks, "sticks_source": st_src},
             "hand": {"call_turns": []},
             "paifu": {"title_prefix": f"{date} {label}", "names": names, "start_score": 25000, "event_fix": {}},
             "app_record": {"captures": ar.rel(captures), "from": t_from, "to": t_to, "date": date, "sticks": sticks, "sticks_by_track": by,
                            "sticks_source": st_src, "id_prefix": L, **({"grid_check": grid_check} if grid_check else {}),
                            "clock_ref": {"offset_ms": clock, "source": ("시험용 옵션 --clock-offset-ms" if "clock_offset_ms" in test else
                                                                       "자동 0 — 시계 차는 W5 가 맞은 버림으로 잼(설계서 3-7). 이 값은 W5 보고의 '다른 측정과의 차'(minus_ref_ms)에만 쓰임")}}}
        if rerun is not None:
            c["rerun_of"] = a.rerun_of
            rb = [x for x in rerun.get("replaces_base") or [] if x in ids]
            if rb:
                c["replaces_base"] = rb
        c["_auto"] = {"by": "paifu_setup.py make", "made": datetime.now().isoformat(timespec="seconds"), "visit": ar.rel(visit),
                      "game": {"key": g["key"], "name": game_name(g), "scan_index": gi, "span_tablet": gs["span"], "folders": gs["folders"]},
                      "test_options": test,
                      "sources": {
                          "app_record.from · to": f"대국 판들의 폴더 시각 처음 · 끝({t_from} ~ {t_to}) — 같은 구간으로 다시 모아 scan 과 같은 판인지 확인함",
                          "games · turn_prefix": PREFIX_RULE + (f" — 시험용 --id-prefix {L}" if "id_prefix" in test else "") + (f" · --id-start {a.id_start}" if "id_start" in test else ""),
                          "recording": f"record.json 시작 · 끝이 대국 구간({gs['span'][0]} ~ {gs['span'][1]}, 태블릿 시계)과 여유 {REC_SLACK_S}초 안에서 겹치는 폴더",
                          "recorder.sticks · app_record.sticks · sticks_by_track": ("시험용 옵션" if st_src == "option" else
                                                                                  (f"펠트(felt_sticks.dart — 판마다 헤드 녹화 프레임 {FELT_N}장의 펠트 모서리 중앙값 → gridFromFelt). "
                                                                                   "recorder · app_record.sticks = 판별 값의 좌표별 중앙값, 그와 다른 판(추적 폴더 시각)만 sticks_by_track · "
                                                                                   "헤드 녹화 펠트를 못 읽은 판은 앱 값(격자 확인 못 함). 판별 표 setup/felt_grid.json · app_record.grid_check") if st_src == "felt" else
                                                                                  "앱이 추적 zip(frames.json grid.sticks)에 남긴 값 — 프레임 수로 가장 흔한 값, 다른 추적만 sticks_by_track"
                                                                                  + (" · 시험용 --sticks-source app(펠트 끔)" if a.sticks_source == "app" else "")) + (" · " + " / ".join(st_notes) if st_notes else ""),
                          "clock_ref.offset_ms": "시험용 옵션" if "clock_offset_ms" in test else "0(설계서 8-11)",
                          "paifu": "title_prefix = 날짜 + 대국 순번 · names = 앱 meta.json names · start_score 25000",
                          "frame": "만들지 않음 — paifu_auto S6a 가 손패 주인 쪽 화면 절반에서 손패 줄 후보를 찾음(2-③, handtrack_prep.py bandcand)",
                          "check_windows": "안 넣음(시험용 칸)",
                          "rerun_of · replaces_base": (f"시험용 --rerun-of {a.rerun_of}(replaces_base 는 그 설정 값 중 이 판 목록에 있는 것)" if rerun is not None else "없음")}}
        return c

    def check(c: dict):
        h = hcfg.Hanchan(run / "hanchan_auto.json", c)
        h.check_collisions()
        return h

    if letter is not None:
        cfg = cfg_for(letter)
        check(cfg)          # HanchanError → 종료 코드 1, 설정을 안 씀
        prefix_how = f"시험용 --id-prefix {letter}"
    else:
        used = used_prefix_letters(exclude=run)
        tried = []
        cfg = None
        for L in PREFIX_LETTERS:
            if L in used:
                tried.append(f"{L}: {used[L]}")
                continue
            c = cfg_for(L)
            try:
                check(c)
            except hcfg.HanchanError as e:
                tried.append(f"{L}: 겹침 검사 {e.msg}")
                continue
            cfg, letter = c, L
            break
        if cfg is None:
            raise SystemExit("접두사로 쓸 글자가 없음: " + " / ".join(tried))
        prefix_how = f"자동 '{letter}'" + (f" — 앞 글자 {len(tried)}개는 쓰임: " + "; ".join(tried) if tried else " — a 부터 차례로 본 첫 글자(쓰인 곳 없음 · 겹침 검사 통과)")
    cfg["_auto"]["prefix"] = prefix_how
    run.mkdir(parents=True, exist_ok=True)
    cfg_f = run / "hanchan_auto.json"
    wj(cfg_f, cfg)
    if felt_rows is not None:
        wj(run / "setup" / "felt_grid.json", {"_note": "paifu_setup make — 판마다 앱 저장 리치봉 · 펠트(헤드 녹화 = 흐름이 씀 · 추적 = 대조) · gridShiftOf(앱, 펠트) · 표시",
                                               "n": FELT_N, "shift_max": "lib/table/felt_grid.dart feltGridShiftMax", "used_default": sticks,
                                               "rounds": {y: {**felt_rows[x["id"]], "used": (cfg["app_record"]["sticks_by_track"].get((x["folders"]["track"] or "_").split("_")[1]) or sticks)}
                                                          for x, y in zip(g["rounds"], cfg["games"])}})
    hcfg.load(cfg_f)        # 쓴 파일로 다시 검사(겹침 포함)
    # 설정으로 모으기(app_record.collect — S0 와 같은 입력)
    o = ar.collect(captures, date, t_from, t_to, ids=list(cfg["games"]), id_prefix=letter)
    evs = app_events_for_estimate(cfg, o, captures, run / "setup", a.no_replay)
    idmap = {x["id"]: y for x, y in zip(g["rounds"], cfg["games"])}     # scan 의 임시 판 id → 설정 판 id
    rep = start_report(a, sc, gs, g, cfg, o, evs, recs, prefix_how, test, st_notes, idmap)
    wj(run / "start_report.json", rep)
    wt(run / "start_report.md", report_md(rep))
    print(report_md(rep))
    print(f"→ {ar.rel(cfg_f)} · {ar.rel(run / 'start_report.md')} · {ar.rel(run / 'start_report.json')}")


def start_report(a, sc, gs, g, cfg, o, evs, recs, prefix_how, test, st_notes, idmap) -> dict:
    date = sc["date"]
    rows, warn, agents = [], [], {"prep": 0, "turn": 0, "sup": 0, "s4_draw": 0}
    tok_lo = tok_hi = 0
    spans = round_spans(o["rounds"], date)
    for r, (t0, t1, t_known) in zip(o["rounds"], spans):
        path, why = path_of(r)
        ev, ev_src = evs.get(r["id"], (None, "없음"))
        hero, hero_how = hero_seat(r, ev)
        b = r["bottom_seat"]
        if r["end"] == "win" and hero is not None:
            hero_side = ar.side_of(hero, b)
        elif r["end"] == "draw":
            hero_side = "묶음 2 뒤(공개 손패를 읽어야 정해짐)"
        else:
            hero_side = None
        seats = hero if isinstance(hero, list) else ([hero] if hero is not None else [])
        n_turn, turn_how = 0, None
        if seats:
            if ev is not None:
                lab_r = (r.get("result") or {}).get("riichi_seats") if r["end"] == "win" else None
                tt = [turns_of(ev, s, None if lab_r is None else (s in lab_r)) for s in seats]
                k = max(range(len(seats)), key=lambda i: tt[i][1])
                n_turn = tt[k][1]
                turn_how = f"자리 {seats[k]} 버림 {tt[k][0]}" + (f" 중 리치까지 {tt[k][1]}" if tt[k][2] else "") + f" ({ev_src})"
            else:
                n_turn, turn_how = TURN_FALLBACK, f"앱 버림 없음({ev_src}) — 짐작 {TURN_FALLBACK}"
            agents["prep"] += 1
            agents["sup"] += 1
            agents["turn"] += n_turn
            tok_lo += TOK_PREP[0] + n_turn * TOK_TURN[0] + TOK_SUP[0]
            tok_hi += TOK_PREP[1] + n_turn * TOK_TURN[1] + TOK_SUP[1]
        if r["end"] == "draw" and (r.get("result") or {}).get("tenpai"):
            agents["s4_draw"] += 2
        cov = coverage(recs, t0, t1)
        rows.append({"id": r["id"], "round": r["round_label"], "honba": r["honba"], "dealer": r["dealer"], "dealer_side": r["dealer_side"],
                     "bottom_seat": b, "end": r["end"], "result": result_text(r), "path": path, "path_why": why,
                     "discard_source": r["discard_source"]["chosen"], "recording": cov + ("" if t_known else "(시작 모름 — 앞 판 끝부터)"),
                     "span_tablet": [hms(t0), hms(t1)], "span_start_known": t_known,
                     "hero_side": hero_side, "hero_rule": hero_how, "turns_estimate": n_turn, "turns_how": turn_how,
                     "folders": r["folders"]["all"], "end_folder": r["folders"]["end"], "warnings": r["warnings"]})
        if path != "기본":
            warn.append(f"{r['id']}: 길 낮춤 {path} — {why}")
        if cov != "덮음":
            warn.append(f"{r['id']}: 녹화가 판을 {'일부만 덮음' if cov == '일부' else '못 덮음'}({hms(t0)} ~ {hms(t1)}) — 손패 없이 탁자 기록만")
        for w in r["warnings"]:
            warn.append(f"{r['id']}: {w}")
    for b_ in gs["progression_breaks"]:
        warn.append(f"국 진행 끊김(빠진 판 의심): {b_}")
    for m in gs["multi_result_folders"]:
        warn.append(f"{idmap.get(m['id'], m['id'])}: 한 판에 결과 폴더 여럿 {m['folders']} → {m['used']}" + (" · 내용 다름(끝의 질문)" if m["differ"] else " · 내용 같음 · 또는 하나만 결과"))
    for gid, w in gs["attach"].items():
        warn.append(f"대국 id 없는 판 {idmap.get(gid, gid)}: {w}")
    for w in st_notes:
        warn.append("리치봉 구역: " + w)
    for w in o["warnings"]:
        warn.append(w)
    if test:
        warn.append(f"시험용 옵션 씀(자동 흐름 아님): {test}")
    gc = cfg["app_record"].get("grid_check") or {}
    idmap_rev = {(r["folders"]["track"] or "_").split("_")[1]: r["id"] for r in o["rounds"] if r["folders"]["track"]}
    for k, v in gc.items():
        if v.get("flag"):
            warn.append(f"추적 {k}: {v['flag']}(앱 {v['app']} · 펠트 {v['felt']} · gridShiftOf {v['shift']}) → 씀 {v['used']}")
    remaining = [
        {"field": "recorder.sticks · app_record.sticks · sticks_by_track(리치봉 구역)",
         "now": f"{cfg['recorder']['sticks']}({cfg['recorder']['sticks_source']})" + (f" · 추적별 {cfg['app_record']['sticks_by_track']}" if cfg['app_record']['sticks_by_track'] else ""),
         "why": "앱 격자가 탁자와 어긋나 있었으면 앱 값이 틀림(11-14 2반장 — metrics 표 12-128). 펠트에서 다시 잡기는 2-②"},
        {"field": "frame(손 추적 상자)", "now": "없음 — S6a 가 손패 주인 쪽 화면 절반에서 손패 줄 후보를 찾음(2-③, band · search 만)",
         "why": "강 · 울기 영역(river · meld)은 묻지 않는데 공용 판별 features.py 가 읽음 — 준비 답에 없으면 S6a 적용이 멈춤(2-③ 보고)"},
    ]
    if cfg["app_record"]["sticks_source"] == "felt":
        remaining = remaining[1:]          # 펠트에서 잡음 — 격자 표(grid)로 옮김
    elif cfg["app_record"]["sticks_source"] == "app":
        remaining[0]["now"] += " — 사람이 확인하거나 펠트(기본)로 다시 만들 것"
    return {"_note": "paifu_setup.py make — 시작 보고(설계서 3-7 확정 1 · 8-11). '시작' 을 받는 일은 세션 · 스킬 몫", "made": datetime.now().isoformat(timespec="seconds"),
            "config": ar.rel(ar._p(a.run) / "hanchan_auto.json"), "visit": sc["visit"], "date": date,
            "game": {"name": gs["game"], "key": gs["game_key"], "scan_index": gs["index"], "span_tablet": gs["span"], "folders": gs["folders"],
                     "progression": gs["progression"], "recordings": [{k: x[k] for k in ("rec", "start", "end")} for x in recs]},
            "prefix": prefix_how, "test_options": test, "rounds": rows, "warnings": warn,
            "agents": {**agents, "total": agents["prep"] + agents["turn"] + agents["sup"] + agents["s4_draw"],
                       "note": "prep = 준비(S6a) · turn = 차례 읽기(S6) · sup = 판 supervisor · s4_draw = 유국 공개 손패 읽기(판당 둘, 다르면 셋째 — 셋째는 안 셈) · 다시 읽기는 안 셈"},
            "tokens": {"low": tok_lo, "high": tok_hi, "rule": TOKEN_RULE, "constants": [TOK_PREP[2], TOK_TURN[2], TOK_SUP[2]]},
            "remaining_hand_inputs": remaining, "sticks_source": cfg["app_record"]["sticks_source"], "sticks": cfg["recorder"]["sticks"],
            "grid": {idmap_rev.get(k, k): v for k, v in gc.items()},
            "rules": {"prefix": PREFIX_RULE, "rec_slack_s": REC_SLACK_S, "chain": CHAIN_RULE, "reduce": ar.REDUCE_RULE}}


def report_md(rep: dict) -> str:
    g = rep["game"]
    L = [f"# 시작 보고 — {rep['date']} 대국 {g['scan_index']}({g['name']})", "",
         f"- 설정: `{rep['config']}` · 판 {len(rep['rounds'])} · 폴더 시각 {g['folders'][0]} ~ {g['folders'][1]} · 판 구간(태블릿 시계) {g['span_tablet'][0]} ~ {g['span_tablet'][1]}",
         f"- 녹화: " + ", ".join(f"{x['rec']}({x['start']} ~ {x['end']})" for x in g["recordings"]),
         f"- 국 진행: {' → '.join(g['progression'])}",
         f"- 판 id 접두사: {rep['prefix']}", ""]
    if rep["test_options"]:
        L += [f"**시험용 옵션 씀(자동 흐름 아님):** `{json.dumps(rep['test_options'], ensure_ascii=False)}`", ""]
    L += ["## 판", "", "| 판 id | 국 | 본장 | 선 | 결과 | 길 | 녹화 | 손패 주인 쪽 | 차례 어림 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rep["rounds"]:
        L.append(f"| {r['id']} | {r['round']} | {r['honba']} | {r['dealer_side']}(자리 {r['dealer']}) | {r['result']} | {r['path']} | {r['recording']} | {r['hero_side'] or '—'} | {r['turns_estimate']} |")
    L += ["", "## 경고", ""] + ([f"- {w}" for w in rep["warnings"]] or ["- 없음"])
    a, t = rep["agents"], rep["tokens"]
    L += ["", "## 띄울 에이전트 · 토큰 어림", "",
          f"- 에이전트 {a['total']}: 준비 {a['prep']} · 차례 읽기 {a['turn']} · supervisor {a['sup']} · 유국 공개 읽기 {a['s4_draw']}(다시 읽기 · 셋째 읽기는 안 셈)",
          f"- 토큰 {t['low'] / 1e4:,.0f}만 ~ {t['high'] / 1e4:,.0f}만", f"- 식: {t['rule']}", f"- 상수: {' · '.join(t['constants'])}", "",
          "## 아직 손 입력으로 남은 칸", ""]
    L += [f"- **{x['field']}**: 지금 {x['now']} — {x['why']}" for x in rep["remaining_hand_inputs"]]
    if rep.get("grid"):
        L += ["", f"## 격자(리치봉 구역 — 출처 {rep['sticks_source']} · 기본 {rep['sticks']})", "",
              "| 추적 폴더 | 앱 저장 | 펠트(헤드 녹화) | 펠트(추적) | gridShiftOf(앱, 펠트) | 표시 | 씀 |", "|---|---|---|---|---|---|---|"]
        for k, v in rep["grid"].items():
            L.append(f"| {k} | {v['app']} | {v['felt']} | {v.get('felt_track')} | {v['shift']} | {v['flag'] or '—'} | {v['used']} |")
    L += ["", "## 판마다 근거", ""]
    for r in rep["rounds"]:
        L.append(f"- {r['id']}: 길 {r['path']}({r['path_why']}) · 버림 출처 {r['discard_source']} · 판 구간 {r['span_tablet'][0]} ~ {r['span_tablet'][1]} · "
                 f"손패 주인 {r['hero_rule']} · 차례 {r['turns_how'] or '—'} · 폴더 {r['folders']}")
    return "\n".join(L) + "\n"


def cmd_felt(a):
    """시험 · 점검용: scan 의 대국(들) 판마다 펠트 리치봉 구역(추적 · 헤드 녹화)과 앱 저장 값 · gridShiftOf 를 표로(끝 조건 1 · 2)."""
    sc = scan_visit(ar._p(a.visit), a.captures, a.head_rec, a.date)
    games = sc["_games"]
    sel = games if a.game in (None, "all") else [pick_game(games, x) for x in a.game.split(",")]
    rounds = [r for g in sel for r in g["rounds"]]
    rows = {}
    out = ar._p(a.out_dir)
    for g in sel:
        rows.update(felt_rounds(g["rounds"], [r["id"] for r in g["rounds"]], sc["date"], ar._p(sc["captures"]), ar._p(sc["head_rec"]),
                                [x for x in sc["recordings"] if x["rec"] in sc["games"][games.index(g)]["recordings"]], out / game_name(g), n=a.n))
        for r in g["rounds"]:
            rows[r["id"]]["game"] = game_name(g)
            rows[r["id"]]["round"] = r["round_label"]
    wj(out / "felt_table.json", {"_note": "paifu_setup.py felt — 판마다 앱 저장 리치봉 · 펠트(헤드 녹화 · 추적) · gridShiftOf", "n": a.n, "rows": rows})
    print(f"{'판':12s} {'대국':14s} {'국':10s} {'앱 저장':16s} {'펠트(헤드)':16s} {'펠트(추적)':16s} 헤드−추적 shift 헤드 ok/읽음 추적 ok/읽음 표시")
    for gid in [r["id"] for r in rounds]:
        x = rows[gid]
        print(f"{gid:12s} {x['game']:14s} {x['round']:10s} {str(x['app']):16s} {str(x['felt_head']):16s} {str(x['felt_track']):16s} {str(x['felt_head_minus_track_max']):>5} "
              f"{str(x['shift_app_vs_felt']):>5} {x['head_ok']}/{x['head_read']} {x['track_ok']}/{x['track_read']} {x['flag'] or '—'}")


# ------------------------------------------------------------------ 명령
def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "make", "felt"):
        p = sp.add_parser(name)
        p.add_argument("--visit", required=True)
        p.add_argument("--captures")
        p.add_argument("--head-rec")
        p.add_argument("--date")
        if name == "scan":
            p.add_argument("--out")
        elif name == "felt":
            p.add_argument("--game")
            p.add_argument("--out-dir", required=True)
            p.add_argument("--n", type=int, default=FELT_N)
        else:
            p.add_argument("--game")
            p.add_argument("--run", required=True)
            p.add_argument("--no-replay", action="store_true")
            p.add_argument("--id-prefix")
            p.add_argument("--id-start", type=int, default=1)
            p.add_argument("--rerun-of")
            p.add_argument("--sticks")
            p.add_argument("--sticks-by-track", action="append")
            p.add_argument("--clock-offset-ms", type=int)
            p.add_argument("--sticks-source", choices=["felt", "app"], default="felt")
    a = ap.parse_args()
    if a.cmd == "scan":
        o = scan_visit(ar._p(a.visit), a.captures, a.head_rec, a.date)
        if not o["_day"]["rounds"]:
            print_scan(o)
            stop(f"판이 0 — {o['date']} 촬영 기록({o['captures']})에 판이 없음")
        o.pop("_games")
        o.pop("_day")
        if a.out:
            wj(ar._p(a.out), o)
        print_scan(o)
    elif a.cmd == "felt":
        cmd_felt(a)
    else:
        cmd_make(a)


if __name__ == "__main__":
    main()
