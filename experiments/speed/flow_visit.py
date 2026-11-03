"""앱 흐름(integration_test/read_grid_timing_test.dart PAIR_WIDE·PAIR_EARLY) 결과 채점: 넓은 구역 판독 없이("plain") / 있이("wide") /
미리 보내기("early"), 같은 순간(2026-11-01). "넓은 판독" = 그 답을 쓴 수, "미리 보냄" = 자리 판독과 같이 보낸 수(안 쓴 것 포함), seatwide 초는 그 호출만.

  python -I -X utf8 experiments/speed/flow_visit.py grids        FIELD_GRIDS 값(매장 25장, 저장된 격자)을 찍는다
  python -I -X utf8 experiments/speed/flow_visit.py riichi       RIICHI_SIDES 값(truth.json 에서 리치 화료 장면의 화료자 자리) — 판 상태 추적 흉내
  python -I -X utf8 experiments/speed/flow_visit.py score <로그>...
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import seat_grow as sg  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRUTH = json.loads((ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
VISIT = ROOT / "experiments/visit_20261031/captures"


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
    win = tsumo = loser = inds = None
    if t:
        win, tsumo, loser, inds = t.get("win_tile"), t.get("is_tsumo"), t.get("loser"), t.get("indicators")
    elif s["set"] == "visit" and lab.exists():
        j = json.loads(lab.read_text(encoding="utf-8"))
        win, tsumo, loser = j["win_tile"], j["is_tsumo"], j["loser"]
    hand = list(s["hand"])
    # 정답 손패는 사진 기준. 13장 정답에 화료패(강 끝)를 더해 앱 값과 맞춘다.
    closed = hand + ([win] if win and len(hand) + 3 * len(s["melds"]) == 13 else [])
    return {"closed": sorted(closed), "hand": sorted(hand), "melds": norm_melds(s["melds"]), "win": win, "tsumo": tsumo, "loser": loser, "inds": inds}


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
            continue  # 가림 사진(sg.OCCLUDED)이 든 옛 로그
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
        d["자동 반영"] += r.get("auto_block") is None and "error" not in r
        d["틀린 자동 반영"] += r.get("auto_block") is None and "error" not in r and not full
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
        print(k, {x: d[x] for x in ("n", "맞음", "론쯔모까지", "고르면 맞음", "계산했는데 틀림", "자동 반영", "틀린 자동 반영", "표시패", "넓은 판독", "미리 보냄", "표시패용 대기", "강 끝 헤지", "추적 리치", "오류")},
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
    {"grids": grids, "fitted": fitted, "riichi": riichi}.get(sys.argv[1], lambda: score(sys.argv[2:]))()
