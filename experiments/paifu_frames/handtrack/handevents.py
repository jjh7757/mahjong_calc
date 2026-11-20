"""손 관절 → 손끝 사건 목록(2026-11-20, 사용자 "넓혀서 해 줘" — 손끝이 머문 칸 · 줄을 벗어나는 방향을 자동으로).

  python -X utf8 handevents.py r16_d13 [--tag _w220] [--json] [--point index|mid]
  python -X utf8 handevents.py r16_d01,r16_d02 --score [--point index|mid] [--pick last|discard]   # → _work/hands_1120/score<tag>_<point>_<pick>.json
입력: _work/hands_1120/<id>/ov_GPU<tag>.json(handpose.py — 관절점은 band2 그림 좌표) · SAM 2 추적 폴더의 검출 상자(relabel.Track — 같은 좌표).
  추적(track.json)이 없는 차례(11-20 새 23차례)는 sam2track.plan 의 첫 프레임 줄 상자(a_boxes)로 칸 틀을 만듦.
변형(11-20, 새 차례 보기 전에 정함): --point mid = 엄지 끝(4) · 검지 끝(8) 가운데 점으로 상태 y · 칸 x 를 잼(손 고르기 · 뿌리 9 는 그대로),
  --pick discard = 차례 컷 버림 시각 td − 2초 ~ + 1초 안에서 시작한 "강 쪽" 중 td 에 가장 가까운 것을 버림으로.
칸: 첫 프레임 줄의 칸 틀(왼쪽 끝 x · 패 한 장 폭) — 1 ~ n = 시작 줄 자리, 0 = 왼쪽 밖, n+1 = 오른쪽 끝 옆. 줄 높이 = 첫 프레임 줄 상자의 위 · 아래.
손: 손목이 줄보다 그 사람 쪽(그림 아래)에 있는 손만(다른 사람 팔 빼기). 손끝 = 검지 끝(8).
사건(0.2초 = 초당 10장의 2프레임 이상 이어진 것만):
  머묾   — 손끝이 줄 높이 안 · 같은 칸에 있음
  강 쪽  — 손끝이 줄 위쪽(그림 위, 강 쪽)으로 벗어남 — 바로 앞에 머문 칸과 함께(버림 후보)
  몸 쪽  — 손끝이 줄 아래쪽(그림 아래)으로 벗어남 — 그동안 손끝 칸이 바뀌면 "줄 밑으로 옮김"(패를 들고 옮김 후보)
정답은 읽지 않음.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relabel as rl  # noqa: E402

WORK = rl.hc.WORK / "hands_1120"
MIN_RUN = 2          # 초당 10장 2프레임 = 0.2초("강 쪽" 은 한 프레임도 셈 — 손이 빠르게 빠져나감)
OFF_MARGIN = 0.35    # 줄 높이의 몇 배 넘게 벗어나야 "벗어남"


def grid_of_boxes(bs: list):
    """줄 상자들([x0, y0, x1, y1], band2 그림 좌표) → (왼쪽 끝 x, 한 장 폭, 줄 위, 줄 아래, 상자 수)."""
    bs = sorted(bs, key=lambda b: b[0])
    pitch = float(np.median([b2[0] - b1[0] for b1, b2 in zip(bs, bs[1:])]))
    left0 = bs[0][0]
    top, bot = float(np.median([b[1] for b in bs])), float(np.median([b[3] for b in bs]))
    return left0, pitch, top, bot, len(bs)


def grid(T: "rl.Track"):
    band = rl.row_band(T)
    return grid_of_boxes([b for b in T.boxes[0] if band[0] <= (b[1] + b[3]) / 2 <= band[1]])


def grid_plan(p: dict):
    """SAM 2 추적이 없는 차례(11-20): sam2track.plan 의 첫 프레임 줄 상자 a_boxes(band2 좌표 [x0, y0, x1, y1])로 같은 식."""
    return grid_of_boxes(p["a_boxes"])


def has_track(tid: str) -> bool:
    return (rl.s1.run_dir(tid, rl.V1) / "track.json").exists()


def grid_src(tid: str, force_plan: bool = False):
    """칸 틀 · n · 어느 길로 만들었나. track.json 이 있으면 지금처럼 Track, 없으면(또는 force_plan) plan."""
    if has_track(tid) and not force_plan:
        T = rl.Track(tid)
        return grid(T), T.n, "track"
    p = rl.s1.plan(tid)
    if not p.get("ok"):
        raise RuntimeError(f"{tid}: plan 실패 — {p.get('why')}")
    return grid_plan(p), p["n"], "plan"


def point_of(lm: list, point: str):
    """index = 검지 끝(8) · mid = 엄지 끝(4)과 검지 끝(8)의 가운데(쥔 패가 두 손가락 사이)."""
    if point == "index":
        return lm[8][0], lm[8][1]
    if point == "mid":
        return (lm[4][0] + lm[8][0]) / 2, (lm[4][1] + lm[8][1]) / 2
    raise ValueError(point)


def slot_of(x: float, left0: float, pitch: float, n: int) -> int:
    k = int(np.floor((x - left0) / pitch)) + 1
    return max(0, min(n + 1, k))


def frame_states(tid: str, tag: str, point: str = "index"):
    """→ (n, rows, 칸 틀, meta, 칸 틀 길 "track" | "plan")."""
    (left0, pitch, top, bot, nbox), n, src = grid_src(tid)
    h = bot - top
    data = json.loads((WORK / tid / f"ov_GPU{tag}.json").read_text(encoding="utf-8"))["frames"]
    meta = {r["i"]: r for r in json.loads((WORK / tid / f"frames{tag}.json").read_text(encoding="utf-8"))["frames"]}
    rows = []
    prev_wrist = None
    for f in data:
        own = [hd for hd in f["hands"] if hd["lm"][0][1] > bot or hd["lm"][9][1] > top]   # 손목(또는 손등)이 그 사람 쪽
        if not own and prev_wrist is not None:   # 버리러 손 전체가 줄을 넘어가도 앞 프레임의 그 사람 손에서 이어지면 같은 손
            own = [hd for hd in f["hands"]
                   if np.hypot(hd["lm"][0][0] - prev_wrist[0], hd["lm"][0][1] - prev_wrist[1]) < 2.5 * np.hypot(hd["lm"][0][0] - hd["lm"][9][0], hd["lm"][0][1] - hd["lm"][9][1])]
        if not own:
            rows.append((f["i"], f["t"], None, None, None))
            prev_wrist = None
            continue
        hd = max(own, key=lambda q: q["lm"][0][1])
        prev_wrist = hd["lm"][0]
        x, y = point_of(hd["lm"], point)
        knuckle_y = hd["lm"][9][1]   # 가운뎃손가락 뿌리 — 손가락만 패 너머로 뻗은 것(거짓 "강 쪽")과 손이 줄을 넘어간 것을 가름
        if y < top - OFF_MARGIN * h:
            st = "위" if knuckle_y >= top else "강 쪽"   # "위" 는 뒤에서 다시 봄(바로 뒤에 손이 사라지면 강 쪽으로 빠져나간 것)
        elif y > bot + OFF_MARGIN * h:
            st = "몸 쪽"
        else:
            st = "줄"
        rows.append((f["i"], f["t"], st, slot_of(x, left0, pitch, n), round(x)))
    for j, r in enumerate(rows):   # "위": 뒤 2프레임에 그 사람 손이 없으면 강 쪽(손이 빠르게 강으로 나가 추적이 끊김), 아니면 줄(손가락만 뻗음)
        if r[2] == "위":
            gone = all(k < len(rows) and rows[k][2] is None for k in (j + 1, j + 2))
            rows[j] = (r[0], r[1], "강 쪽" if gone else "줄", r[3], r[4])
    return n, rows, (left0, pitch, top, bot, nbox), meta, src


def events(rows: list, n: int):
    """같은 (상태, 칸) 이 MIN_RUN 프레임 넘게 이어진 구간 → 사건. 손 없는 프레임은 끊김."""
    segs = []
    cur = None
    for i, t, st, k, x in rows:
        key = None if st is None else (st, k if st == "줄" else None)
        if cur and key == cur["key"] and i == cur["b"] + 1:
            cur["b"], cur["tb"] = i, t
            cur["xs"].append(x)
            cur["ks"].append(k)
        else:
            if cur:
                segs.append(cur)
            cur = None if key is None else {"key": key, "a": i, "b": i, "ta": t, "tb": t, "xs": [x], "ks": [k]}
    if cur:
        segs.append(cur)
    segs = [s for s in segs if s["b"] - s["a"] + 1 >= MIN_RUN or s["key"][0] == "강 쪽"]
    out = []
    last_row = None
    for s in segs:
        st = s["key"][0]
        span = f"{s['a']:03d}~{s['b']:03d}(SAM 2 {s['a'] // 2:03d}~{s['b'] // 2:03d}, {s['ta']}~{s['tb']})"
        if st == "줄":
            k = s["key"][1]
            name = "왼쪽 밖(0)" if k == 0 else (f"오른쪽 끝 옆({n + 1})" if k == n + 1 else f"{k}번 칸")
            out.append(f"{span}  손끝이 줄 위 {name}에 머묾")
            last_row = name
        elif st == "강 쪽":
            out.append(f"{span}  손끝이 강 쪽으로 벗어남" + (f" — 바로 앞에 머문 곳: {last_row}" if last_row else ""))
        else:
            k0, k1 = s["ks"][0], s["ks"][-1]
            mv = f" · 손끝 칸 {k0} → {k1}(x {s['xs'][0]} → {s['xs'][-1]}) — 줄 밑으로 옮김" if k0 != k1 else ""
            out.append(f"{span}  손끝이 몸 쪽(줄 아래)으로 벗어남" + (f" — 바로 앞에 머문 곳: {last_row}" if last_row else "") + mv)
    return out


PICK_WIN = (-2000, 1000)   # --pick discard: 버림 시각 td 둘레 창(ms) — 새 23차례 보기 전에 정함(11-20), 결과 보고 바꾸지 말 것


def discard_ms(tid: str, ref_ms: int) -> int:
    """차례 컷의 버림 시각(events.txt "버림(강 위에 손)" 으로 읽는 쪽에도 주는 값 · 정답 아님) → ms. ref_ms = plan a_ms."""
    return rl.s1.ms_of(rl.s1.turn_of(tid)[1]["cut"]["discard"], ref_ms)


def decide(rows: list, n: int, pick: str = "last", td: int | None = None, ms_of_i: dict | None = None) -> dict:
    """미리 적은 판정(11-20, 53차례 재기 전): 마지막 "강 쪽" = 버림, 그 앞에 머문 곳이 1 ~ n 칸이면 hand(k = 칸),
    끝 옆(n+1) · 왼쪽 밖(0)이면 tsumogiri, 강 쪽이 없거나 앞에 머문 곳이 없으면 판정 못 함(None).
    pick="discard"(11-20, 새 23차례 보기 전에 정함): 시작 프레임 ms 가 [td − 2000, td + 1000] 안인 "강 쪽" 중
    시작이 td 에 가장 가까운 것(같으면 앞의 것)을 버림으로 — 없으면 판정 못 함. ms_of_i = 프레임 번호 → ms(frames json)."""
    segs = []
    cur = None
    for i, t, st, k, x in rows:
        key = None if st is None else (st, k if st == "줄" else None)
        if cur and key == cur["key"] and i == cur["b"] + 1:
            cur["b"] = i
        else:
            if cur:
                segs.append(cur)
            cur = None if key is None else {"key": key, "a": i, "b": i}
    if cur:
        segs.append(cur)
    segs = [s for s in segs if s["b"] - s["a"] + 1 >= MIN_RUN or s["key"][0] == "강 쪽"]
    river = [j for j, s in enumerate(segs) if s["key"][0] == "강 쪽"]
    if not river:
        return {"kind": None, "k": None, "why": "강 쪽 사건 없음"}
    if pick == "last":
        j = river[-1]
    elif pick == "discard":
        near = [j for j in river if PICK_WIN[0] <= ms_of_i[segs[j]["a"]] - td <= PICK_WIN[1]]
        if not near:
            return {"kind": None, "k": None, "why": "버림 시각 둘레 강 쪽 없음"}
        j = min(near, key=lambda j: abs(ms_of_i[segs[j]["a"]] - td))
    else:
        raise ValueError(pick)
    before = [s for s in segs[:j] if s["key"][0] == "줄"]
    if not before:
        return {"kind": None, "k": None, "why": "버림 앞에 머문 칸 없음", "at": segs[j]["a"]}
    k = before[-1]["key"][1]
    if 1 <= k <= n:
        return {"kind": "hand", "k": k, "at": segs[j]["a"], "from": before[-1]["a"]}
    return {"kind": "tsumogiri", "k": None, "slot": k, "at": segs[j]["a"], "from": before[-1]["a"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("id")
    ap.add_argument("--tag", default="_w220")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--score", action="store_true", help="a.id 를 쉼표 목록으로 · decide() 를 정답(truth_all)과 견줌")
    ap.add_argument("--point", choices=("index", "mid"), default="index", help="손끝 점: index = 검지 끝(8) · mid = 엄지 끝(4)과 검지 끝의 가운데")
    ap.add_argument("--pick", choices=("last", "discard"), default="last", help="버림 사건: last = 마지막 강 쪽 · discard = 버림 시각 td 둘레 강 쪽")
    a = ap.parse_args()
    if a.score:
        return score(a.id.split(","), a.tag, a.point, a.pick)
    n, rows, (left0, pitch, top, bot, nbox), _, src = frame_states(a.id, a.tag, a.point)
    ev = events(rows, n)
    pname = "검지 끝" if a.point == "index" else "엄지 끝 · 검지 끝 가운데"
    head = f"== {a.id} 손끝 사건({pname} · 초당 10장, 0.2초 넘게 이어진 것) · 칸 틀: 왼쪽 끝 x {left0:.0f} · 한 장 폭 {pitch:.1f} · 줄 높이 y {top:.0f}~{bot:.0f} · 첫 프레임 상자 {nbox}"
    if src != "track":
        head += f" · 칸 틀 {src}"
    seen = sum(r[2] is not None for r in rows)
    txt = "\n".join([head, f"   그 사람 손이 잡힌 프레임 {seen}/{len(rows)}"] + ["   " + e for e in ev])
    print(txt)
    suf = a.tag if a.point == "index" else f"{a.tag}_{a.point}"
    (WORK / a.id / f"hand_events{suf}.txt").write_text(txt + "\n", encoding="utf-8")
    if a.json:
        (WORK / a.id / f"hand_rows{suf}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def score(ids: list, tag: str, point: str = "index", pick: str = "last"):
    import sam2track as s1
    truth = s1.truth_all()
    tot = {"n": 0, "kind": 0, "none": 0, "hand": 0, "k": 0, "k1": 0}
    out = []
    for tid in ids:
        f = WORK / tid / f"ov_GPU{tag}.json"
        if not f.exists():
            print(tid, "손 관절 없음")
            continue
        n, rows, _, meta, src = frame_states(tid, tag, point)
        ms_of_i = {i: r["ms"] for i, r in meta.items()}
        td = discard_ms(tid, meta[0]["ms"]) if pick == "discard" else None   # meta[0] = 첫 프레임 = plan a_ms
        d = decide(rows, n, pick, td, ms_of_i)
        if td is not None:
            d["td"] = td
            if d.get("at") is not None:
                d["at_dt"] = ms_of_i[d["at"]] - td
        tr = truth[tid]
        seen = sum(r[2] is not None for r in rows)
        tot["n"] += 1
        if d["kind"] is None:
            tot["none"] += 1
        ok_kind = d["kind"] == tr.get("kind")
        tot["kind"] += ok_kind
        kk = ""
        if tr.get("kind") == "hand":
            tot["hand"] += 1
            if d["kind"] == "hand":
                tot["k"] += d["k"] == tr.get("k_id")
                tot["k1"] += abs(d["k"] - tr.get("k_id")) <= 1
                kk = f" · k {d['k']} {'✓' if d['k'] == tr.get('k_id') else ('±1' if abs(d['k'] - tr.get('k_id')) <= 1 else '✗')}"
        out.append({"id": tid, "truth": [tr.get("kind"), tr.get("k_id")], "decide": d, "seen": seen, "frames": len(rows), "grid": src})
        print(f"{tid:9s} 정답 {tr.get('kind'):9s} {str(tr.get('k_id')):4s} | 손 {str(d['kind']):9s} {str(d.get('k')):4s} {'✓' if ok_kind else '✗'}{kk} | 손 잡힌 {seen}/{len(rows)} {d.get('why', '')}")
    print(f"종류 맞음 {tot['kind']}/{tot['n']}(판정 못 함 {tot['none']}) · 손에서 버린 {tot['hand']}차례 중 k 정확 {tot['k']} · ±1 {tot['k1']}")
    # 11-20: 변형마다 따로(기본 index · last 도 이 이름 — 처음 잰 score{tag}.json 은 덮어쓰지 않음)
    (WORK / f"score{tag}_{point}_{pick}.json").write_text(json.dumps({"tot": tot, "rows": out, "point": point, "pick": pick},
                                                                     ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
