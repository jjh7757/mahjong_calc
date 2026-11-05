"""앱 흐름(integration_test/read_grid_timing_test.dart PAIR_WIDE·PAIR_EARLY) 결과 채점: 넓은 구역 판독 없이("plain") / 있이("wide") /
미리 보내기("early"), 같은 순간(2026-11-01). "넓은 판독" = 그 답을 쓴 수, "미리 보냄" = 자리 판독과 같이 보낸 수(안 쓴 것 포함), seatwide 초는 그 호출만.

  python -I -X utf8 experiments/speed/flow_visit.py grids        FIELD_GRIDS 값(매장 25장, 저장된 격자)을 찍는다
  python -I -X utf8 experiments/speed/flow_visit.py riichi       RIICHI_SIDES 값(truth.json 에서 리치 화료 장면의 화료자 자리) — 판 상태 추적 흉내
  python -I -X utf8 experiments/speed/flow_visit.py dora         TRACKED_DORA 값(dora_rounds.py 가 확정한 표시패) — 판 중 표시패 확정 흉내
  python -I -X utf8 experiments/speed/flow_visit.py score <로그>...

채점 보강(2026-11-03): "맞음" 은 손패·울기·화료패만 본다. "완전 맞음" 은 거기에 론/쯔모·방총자, 표시패(매장 truth 앞면 표시패 전부),
화료자 리치, 헛 리치 자리까지 맞고 B·C·D 는 정답 점수(BCD_POINTS)까지 같은 것. "완전 틀린 자동" = 자동 반영인데 완전 맞음이 아닌 수,
"경고 없는 틀린 자동" = 그중 auto_cautions 가 빈 것(사용자가 20초 경고도 못 보는 틀린 반영). 틀린 이유는 "틀림:..." 로 센다.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import flow_riichi as fr  # noqa: E402
import seat_grow as sg  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRUTH = json.loads((ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
VISIT = ROOT / "experiments/visit_20261031/captures"
# B·C·D 의 정답 점수(측정 테스트의 대국 정보 기준, device_timing.py·pair_timing_summary.py 와 같은 값). 표시패·리치까지 들어간 값이라
# 매장 사진처럼 표시패 정답을 따로 대조하지 않고 점수로 본다(2026-11-03 채점 보강).
BCD_POINTS = {"k25": "12000", "k28": "12000", "k15": "16000", "k26": "16000", "k12": "18000", "k16": "18000"}


def grids() -> None:
    out = []
    for s in sg.scenes():
        if s["set"] != "visit":
            continue
        g = s["grid"]
        out.append(f"{s['name'][-6:]}=" + ",".join(str(v) for v in [g["x1"], g["x2"], g["y1"], g["y2"], *g.get("sticks", [])]))
    print(";".join(out))


def riichi() -> None:
    """판 상태 추적이 화료자 리치를 확정해 둔 것으로 치는 장면(RIICHI_SIDES 형식, 화료자 자리는 meta.json)."""
    out = []
    for name, t in sorted(TRUTH.items()):
        if t.get("riichi"):
            m = json.loads((VISIT / name / "meta.json").read_text(encoding="utf-8"))
            out.append(f"{name[-6:]}={m['winner_side']}")
    print(";".join(out))


def dora() -> None:
    """dora_rounds.py 가 화료 시각에 확정해 둔 표시패(TRACKED_DORA 형식) — 판 중 프레임 투표 흉내(2026-11-03, 표 1-53)."""
    j = json.loads((ROOT / "experiments/tile_classifier/data/dora_rounds/online.json").read_text(encoding="utf-8"))
    print(";".join(f"{r['name'][-6:]}={r['confirmed'][0]}" for r in j["results"] if r.get("confirmed")))


def fitted() -> None:
    """fit_grids.py 가 사진마다 맞춘 격자(FIELD_GRIDS 형식)."""
    j = json.loads((ROOT / "experiments/speed/results/fit_grids.json").read_text(encoding="utf-8"))
    print(";".join(f"{k}=" + ",".join(str(v) for v in [g["x1"], g["x2"], g["y1"], g["y2"], *g["sticks"]]) for k, g in j.items()))


def norm_melds(ms):
    return sorted(" ".join(sorted(m.strip("[]").split())) for m in ms)


def truth_of(photo: str, scenes: dict) -> dict:
    s = scenes[photo]
    t = TRUTH.get(s["name"])
    lab = VISIT / s["name"] / "label.json"
    win = tsumo = loser = inds = riichi = None
    if t:
        win, tsumo, loser, inds, riichi = t.get("win_tile"), t.get("is_tsumo"), t.get("loser"), t.get("indicators"), t.get("riichi")
    elif s["set"] == "visit" and lab.exists():
        j = json.loads(lab.read_text(encoding="utf-8"))
        win, tsumo, loser = j["win_tile"], j["is_tsumo"], j["loser"]
    hand = list(s["hand"])
    # 정답 손패는 사진 기준. 13장 정답에 화료패(강 끝)를 더해 앱 값과 맞춘다.
    closed = hand + ([win] if win and len(hand) + 3 * len(s["melds"]) == 13 else [])
    return {"closed": sorted(closed), "hand": sorted(hand), "melds": norm_melds(s["melds"]), "win": win, "tsumo": tsumo, "loser": loser, "inds": inds, "riichi": riichi}


def judge_all(r: dict, t: dict, m: dict, full: bool, side_ok: bool, ind_ok: bool) -> tuple[bool, list[str]]:
    """손패 밖까지 본 '완전 맞음' 과 틀린 이유(2026-11-03 채점 보강).

    손패·울기·화료패(full) + 론/쯔모·방총자(side_ok) + 표시패(매장은 truth 의 앞면 표시패 전부, B·C·D 는 정답 점수로 대신)
    + 화료자 리치(매장 truth.riichi, B·C·D 는 flow_riichi.BCD_YES; 울린 손패는 리치 불가라 안 봄)
    + 헛 리치 자리(사진 리치 자리 중 정답에 없는 것 — 자동 반영이면 리치봉 1000점이 들어간다).
    표시패 정답이 없는 B·C·D 는 점수 정답(BCD_POINTS)으로 표시패·리치·상황을 한 번에 본다.
    """
    why = []
    if not full:
        why.append("손패")
    elif t["tsumo"] is not None and not side_ok:  # B·C·D 는 론/쯔모 정답이 없어 점수로만 본다
        why.append("론쯔모")
    bcd = r["scene"] != "V"
    win = m.get("winner")
    win_side = fr.SIDES[win] if win is not None else None
    if bcd:
        if r.get("points") != BCD_POINTS.get(r["photo"]):
            why.append(f"점수 {r.get('points')}≠{BCD_POINTS.get(r['photo'])}")
        marks = fr.BCD_YES.get(r["photo"], set())
    else:
        if t["inds"] is not None and not ind_ok:
            why.append("표시패")
        marks = fr.TRUTH.get(r["photo"], [])
        if t["riichi"] is not None and not m.get("melds") and bool(m.get("riichi")) != t["riichi"]:
            why.append("화료자 리치")
    if bcd and win_side and not m.get("melds") and bool(m.get("riichi")) != (win_side in marks):
        why.append("화료자 리치")
    extra = sorted(s for s in (fr.SIDES[i] for i in m.get("riichi_seats_photo") or []) if s != win_side and s not in marks and f"?{s}" not in marks)
    if extra:
        why.append(f"헛 리치 {extra}")
    return not why, why


def score(paths: list[str]) -> None:
    scenes = {(s["name"] if s["set"] == "bcd" else s["name"][-6:]): s for s in sg.eval_scenes()}
    rows = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
            i = line.find("TIMING {")
            if i >= 0:
                rows.append(json.loads(line[i + 7:]))
    tally: dict = {}
    pairs: dict = {}  # 같은 순간 짝: (세트, 사진, 회차) → 서버 → 전체 초
    for r in rows:
        if r["photo"] not in scenes:
            continue  # 채점 제외 사진(sg.EXCLUDED)이 든 옛 로그
        t = truth_of(r["photo"], scenes)
        if r["scene"] == "V" and t["win"] is None:
            continue  # 화료패 정답이 없는 매장 장면(142535·174020)은 뺀다(사용자 요청 2026-11-01)
        m = r.get("merge") or {}
        closed = sorted(m.get("closed") or [])
        melds = norm_melds(m.get("melds") or [])
        cands = m.get("win_candidates") or []
        meld_ok = melds == t["melds"]
        valid = bool(m.get("hand_valid"))
        if t["win"] is None:  # 화료패를 모르는 장면(B·C·D 등): 앱의 화료패를 빼고 손패만 본다
            rest = list(closed)
            if m.get("win_tile") in rest and len(closed) + 3 * len(melds) == 14:
                rest.remove(m["win_tile"])
            full = meld_ok and valid and (closed == t["hand"] or rest == t["hand"])
            pick = False
        else:
            full = meld_ok and valid and closed == t["closed"] and m.get("win_tile") == t["win"]
            pick = meld_ok and not valid and t["win"] in cands and sorted(closed + [t["win"]]) == t["closed"]
        wrong = valid and not full
        side_ok = full and t["tsumo"] is not None and bool(m.get("is_tsumo")) == t["tsumo"] and m.get("loser") == t["loser"]
        got = sorted(m.get("dora_indicators") or []) + sorted(m.get("ura_indicators") or [])
        ind_ok = t["inds"] is not None and sorted(got) == sorted(t["inds"])
        part = "BCD" if r["scene"] != "V" else ("오전" if r["photo"] < "14" else "오후")
        k = (part, r["server"])
        d = tally.setdefault(k, Counter())
        d["n"] += 1
        d["맞음"] += full
        d["고르면 맞음"] += pick
        d["계산했는데 틀림"] += wrong
        d["론쯔모까지"] += side_ok
        d["표시패"] += ind_ok
        d["표시패 정답 있음"] += t["inds"] is not None
        auto = r.get("auto_block") is None and "error" not in r
        cautions = r.get("auto_cautions") or []
        complete, why = judge_all(r, t, m, full, side_ok, ind_ok)
        d["완전 맞음"] += complete
        d["자동 반영"] += auto
        d["틀린 자동 반영"] += auto and not full
        d["자동 중 경고"] += auto and bool(cautions)
        d["완전 틀린 자동"] += auto and not complete
        d["경고 없는 틀린 자동"] += auto and not complete and not cautions
        for w in why:
            d[f"틀림:{w.split(' ')[0]}"] += 1
        if auto and not complete:
            print("  !! 틀린 자동", r["photo"], r["run"], r["server"], "경고" if cautions else "경고 없음", cautions, "|", "; ".join(why),
                  "| 표시패", m.get("dora_indicators"), m.get("ura_indicators"), "정답", t["inds"], "| 리치", m.get("riichi"), "사진 리치", m.get("riichi_seats_photo"), "점수", r.get("points"))
        d["넓은 판독"] += bool(r.get("wide_called"))
        d["미리 보냄"] += bool(r.get("wide_early"))
        d["표시패용 대기"] += bool(r.get("wide_for_dora"))
        d["강 끝 헤지"] += bool(r.get("last_hedged"))
        d["추적 리치"] += bool(r.get("tracked_riichi"))
        for name, ms in (r.get("call_ms") or {}).items():
            if name.startswith("seatwide_"):
                tally.setdefault((*k, "w"), []).append(ms / 1000)
        d["오류"] += "error" in r
        tally.setdefault((*k, "t"), []).append(r["total_ms"] / 1000)
        pairs.setdefault((part, r["photo"], r["run"]), {})[r["server"]] = r["total_ms"] / 1000
        if part != "BCD" or not full:
            print(r["photo"], r["server"], "맞음" if full else "고르면 맞음" if pick else "틀림" if wrong else "입력 화면", "넓은" if r.get("wide_called") else "", f"{r['total_ms'] / 1000:.1f}초",
                  "손패", " ".join(m.get("closed") or []), "울기", m.get("melds"), "화료", m.get("win_tile"), "쯔모" if m.get("is_tsumo") else "론", m.get("loser"), "후보", cands, "| 정답", t["win"], t["tsumo"], t["loser"], "자동" if r.get("auto_block") is None else "", r.get("error", ""))
    print()
    for k in sorted(k for k in tally if len(k) == 2):
        d = tally[k]
        ts = sorted(tally[(*k, "t")])
        ws = sorted(tally.get((*k, "w"), []))
        print(k, {x: d[x] for x in ("n", "맞음", "완전 맞음", "론쯔모까지", "고르면 맞음", "계산했는데 틀림", "자동 반영", "틀린 자동 반영", "완전 틀린 자동", "경고 없는 틀린 자동", "자동 중 경고", "표시패", "표시패 정답 있음", "넓은 판독", "미리 보냄", "표시패용 대기", "강 끝 헤지", "추적 리치", "오류")},
              {x: d[x] for x in sorted(d) if x.startswith("틀림:")},
              f"시간 {statistics.median(ts):.1f} / {ts[min(len(ts) - 1, int(.9 * len(ts)))]:.1f} / {ts[-1]:.1f}",
              f"seatwide {len(ws)}회 {statistics.median(ws):.1f} / {ws[min(len(ws) - 1, int(.9 * len(ws)))]:.1f} / {ws[-1]:.1f}" if ws else "")
    # 같은 순간 짝 차이(두 번째 서버 − 첫 서버, 사진마다): 시각 편차를 빼고 본다
    servers = sorted({sv for v in pairs.values() for sv in v})
    if len(servers) == 2:
        order = ["plain", "wide", "early", "ind"]
        s0, s1 = sorted(servers, key=lambda x: order.index(x) if x in order else 9)
        for part in sorted({k[0] for k in pairs}):
            ds = sorted(v[s1] - v[s0] for k, v in pairs.items() if k[0] == part and s0 in v and s1 in v)
            if ds:
                print(part, f"짝 차이 {s1} − {s0}: 중앙 {statistics.median(ds):+.1f}초, {s1} 이 빠름 {sum(d < 0 for d in ds)}/{len(ds)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"grids": grids, "fitted": fitted, "riichi": riichi, "dora": dora}.get(sys.argv[1], lambda: score(sys.argv[2:]))()
