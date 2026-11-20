"""차례 묶음 v2 — 차례의 경계를 네 자리 강으로 긋는다(2026-11-17, 사용자 "패를 쯔모하는 걸로 구간을 나눠야" → "전체 테이블 화면으로" → "만들어").
truthprep 은 "손이 움직인 구간" 을 통째로 차례에 붙여서, 손을 줄 옆에 올려 둔 채 기다리는 사람은 한 구간에 뽑기 · 버림이 두 번 들어가고
두 차례가 같은 프레임을 받았다(metrics 표 12-31 의 조용한 틀림). 여기서는 차례 k 의 프레임을 [경계 k, 경계 k+1) 로 자른다.

  경계 k = 내 버림 k-1 과 k 사이에서 **다른 자리 강에 패가 마지막으로 새로 보인** 추적 프레임의 바로 앞 프레임 시각
          (그 버림보다 늦을 수 없는 시각. 울기로 순서가 바뀌어도 "마지막" 을 쓰므로 누가 울었는지 몰라도 된다 — 표 12-32)
  사이에 찍힌 남의 버림이 없으면(추적 시작 전 · 내가 운 차례 등) truthprep 의 시작을 그대로 쓰고 cut.by = "옛 묶음" 으로 적는다.

  python -X utf8 turncut.py build <판 id…> [--out 파일]   # → _work/testtruth_1116/turns_cut.json (turns.json 은 안 건드림) + 모자란 프레임 그리기
      (11-19 r15 · L16 은 --out _work/testtruth_1116/turns_cut_r15L16_1119.json — turns_of 는 두 파일을 다 읽음)
  python -X utf8 turncut.py check <판 id…>     # 옛 묶음과 나란히: 차례끼리 겹치는 프레임, 창, 구간 수
  python -X utf8 turncut.py reread <판 id> --ids a,b[,…] [--readers ABE]   # 새 묶음으로 고정한 판독기를 다시 부름(있는 답은 안 부름) → _work/turncut_1117/
  python -X utf8 turncut.py score <판 id…>     # 다시 읽은 답을 정답 · 옛 묶음의 답과 나란히(호출 없음)
네 자리 강 = 앱 버림 기록기 재생 결과(results/h<판>/dart_overlay_v2.json). 차례 id · 패 · 줄 장수 등은 truthprep 의 것을 그대로 쓴다(정답 · 저장된 읽기와 id 가 같아야 하므로).
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
OUTF = BASE / "turns_cut.json"
# 11-19 r15 · L16 넓히기: 두 판의 새 묶음은 turns_cut.json 을 안 건드리려고 따로 씀(build --out). 읽을 땐 OUTF 먼저, 같은 판이 겹치면 앞 파일 것.
EXTRA = [BASE / "turns_cut_r15L16_1119.json"]
EDGE_MS = 300


def rec_dir(gid: str) -> Path:
    return hc.OUT.parent / f"h{gid[1:]}"


def old_turns(gid: str) -> list:
    return next(x for x in hc.jload(BASE / "turns.json")["games"] if x["id"] == gid)["turns"]


def cut_games() -> list:
    """새 묶음의 판 목록 — turns_cut.json 의 판 다음에 EXTRA 파일들의 판(이미 있는 판 id 는 건너뜀)."""
    out, seen = [], set()
    for f in [OUTF] + EXTRA:
        if not f.exists():
            continue
        for g in hc.jload(f)["games"]:
            if g["id"] not in seen:
                seen.add(g["id"])
                out.append(g)
    return out


def turns_of(gid: str) -> list:
    """새 묶음의 차례 목록(gemturn.turns_of 와 같은 꼴)."""
    g = next((x for x in cut_games() if x["id"] == gid), None)
    if g is None:   # 11-19: 전에는 next() 가 StopIteration 으로 죽었다(r15 · L16 은 build 를 안 돌려 turns_cut.json 에 없었음)
        raise KeyError(f"{gid} 가 새 묶음 파일({', '.join(f.name for f in [OUTF] + EXTRA)})에 없다 — turncut.py build {gid} --out <파일>")
    return g["turns"]


def build_game(gid: str) -> dict:
    side = hc.config(gid)["side"]
    old = old_turns(gid)
    rec = rec_dir(gid)
    d = json.load(open(rec / "dart_overlay_v2.json", encoding="utf-8"))
    ft = [int(dt.datetime.fromisoformat(f["at"]).timestamp() * 1000) for f in json.load(open(rec / "overlay_dump.json", encoding="utf-8"))["frames"]]
    day = dt.datetime.fromtimestamp(ft[0] / 1000).date()

    def T(s):
        h, m, x = s.split(":")
        return int(dt.datetime(day.year, day.month, day.day, int(h), int(m), int(x)).timestamp() * 1000)

    def seen_prev(t_ms):
        """그 시각(초 단위로 적힌 first_at)에 해당하는 추적 프레임과 그 바로 앞 프레임."""
        i = min(range(len(ft)), key=lambda k: abs(ft[k] - t_ms))
        return ft[i], ft[max(i - 1, 0)]

    ev = sorted((T(s["first_at"]), sd, s["i"], s["tile"]) for sd, v in d.items() for s in v["slots"])
    hero = [e for e in ev if e[1] == side]
    # 옛 차례 ↔ 기록기의 내 강 칸: 패 순서로 맞춘다(녹화 전 버림 · 울려 나간 패 때문에 번호가 어긋날 수 있다)
    sm = difflib.SequenceMatcher(None, [t["tile"] for t in old], [e[3] for e in hero], autojunk=False)
    pair = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            pair[blk.a + k] = blk.b + k
    acts = sorted(hc.jload(hc.OUT / gid / "segments.json")["active"], key=lambda a: a["ms0"])
    z = np.load(hc.WORK / f"{gid}_feat.npz")
    fms, rsk = z["ms"], z["river_skin"]
    thr = hc.jload(hc.OUT / gid / "segments.json")["params"]["RIVER_SKIN"]

    cuts, disc = [], []
    for n, t in enumerate(old):
        h = pair.get(n)
        cut, by, lo, hi = None, "옛 묶음", None, None
        if h is not None:
            hi, lo = seen_prev(hero[h][0])
            if h > 0:
                mid = [e for e in ev if hero[h - 1][0] < e[0] < hero[h][0] and e[1] != side]
                if mid:
                    cut, by = seen_prev(mid[-1][0])[1], f"{mid[-1][1]} {mid[-1][2]}번째 버림 앞"
        cuts.append((cut, by))
        disc.append((lo, hi))

    turns, prev_td = [], None
    for n, t in enumerate(old):
        o0, o1 = t["segs"][0]["frames"][0], t["segs"][-1]["frames"][-1]
        start, by = cuts[n]
        if start is None:
            # 경계를 못 그은 차례: 옛 묶음의 시작을 쓰되 앞 차례의 버림(강 위 손) 뒤부터. 기록기가 "처음 본" 시각은 추적 시작 때 늦게 찍히므로 안 쓴다.
            start = o0 if prev_td is None else max(o0, prev_td + 100)
        nxt = next((cuts[m][0] for m in range(n + 1, len(old)) if cuts[m][0] is not None), None) if n + 1 < len(old) else None
        end = cuts[n + 1][0] if n + 1 < len(old) and cuts[n + 1][0] is not None else (o1 + 1 if n + 1 == len(old) or nxt is None else min(o1 + 1, nxt))
        if end <= start:
            end = o1 + 1
        # 버림 시각: 이 차례 창 안에서, 기록기가 그 패를 처음 본 프레임보다 앞에서 강 위에 손이 마지막으로 잡힌 때.
        # (처음에는 "처음 본 프레임 바로 앞 3초" 만 봤는데, 기록기가 패를 늦게 알아보면 — r16 13순은 9초 — 버림 구간 표시가 엉뚱한 조각에 붙었다.
        #  그 표시를 따라 판독기 둘이 같은 틀린 답을 냈다. 11-17 고침.)
        lo, hi = disc[n]
        td = None
        if hi is not None:
            i0, i1 = int(np.searchsorted(fms, start)), int(np.searchsorted(fms, min(hi, end)))
            r = [i for i in range(i0, i1) if rsk[i] > thr]
            td = int(fms[r[-1]]) if r else min(hi, end - 1)
        segs, last = [], 0
        for a in acts:
            ms = [m for m in hc.frame_range(max(a["ms0"] - EDGE_MS, start), min(a["ms1"] + EDGE_MS, end - 1)) if m > last and start <= m < end]
            if not ms:
                continue
            last = ms[-1]
            role = "버림" if td is None or ms[0] - 500 <= td <= ms[-1] + 500 else ("앞" if ms[-1] < td else "뒤")
            segs.append({"seg": a["seg"], "role": role, "t0": hc.hms(ms[0])[3:], "frames": ms})
        if segs and not any(s["role"] == "버림" for s in segs):               # 버림 시각이 어느 조각에도 안 들면 가장 가까운 조각을 버림 구간으로
            k = min(range(len(segs)), key=lambda q: min(abs(segs[q]["frames"][0] - td), abs(segs[q]["frames"][-1] - td)))
            segs[k]["role"] = "버림"
            for q, s in enumerate(segs):
                if q != k:
                    s["role"] = "앞" if q < k else "뒤"
        prev_td = td if td is not None else prev_td
        nt = {k: v for k, v in t.items() if k not in ("segs", "more_after", "more_before")}
        nt.update(segs=segs, cut={"start": hc.hms(start)[3:], "end": hc.hms(end)[3:], "by": by, "discard": hc.hms(td)[3:] if td else None})
        turns.append(nt)
    return {"id": gid, "side": side, "turns": turns}


def render_missing(g: dict) -> int:
    import truthprep as tp
    cfg = hc.config(g["id"])
    (BASE / "frames" / g["id"]).mkdir(parents=True, exist_ok=True)
    ms = sorted({m for t in g["turns"] for s in t["segs"] for m in s["frames"] if not (BASE / "frames" / g["id"] / f"{m}.jpg").exists()})
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda m: tp.render(g["id"], m, cfg), ms))
    return len(ms)


def cmd_build(a):
    outf = Path(a.out) if a.out else OUTF
    have = {g["id"]: g for g in hc.jload(outf)["games"]} if outf.exists() else {}
    for gid in a.games:
        g = build_game(gid)
        have[gid] = g
        n = render_missing(g)
        print(f"{gid}: 차례 {len(g['turns'])} · 경계를 네 자리 강으로 그은 차례 {sum(t['cut']['by'] != '옛 묶음' for t in g['turns'])} · 새로 그린 프레임 {n}")
    hc.jsave(outf, {"rule": "차례 k = [내 버림 k-1 과 k 사이 마지막 남의 버림이 보이기 직전 프레임, 다음 차례의 같은 시각)", "games": list(have.values())})


def cmd_check(a):
    for gid in a.games:
        old, new = old_turns(gid), turns_of(gid)
        print(f"\n== {gid}")
        print("차례 | 옛 묶음: 프레임 · 창 | 새 묶음: 프레임 · 창 · 버림 시각 · 조각(역할) | 경계 근거")
        ov_old = ov_new = 0
        for n, (o, t) in enumerate(zip(old, new)):
            fo = [m for s in o["segs"] for m in s["frames"]]
            fn = [m for s in t["segs"] for m in s["frames"]]
            if n:
                po = {m for s in old[n - 1]["segs"] for m in s["frames"]}
                pn = {m for s in new[n - 1]["segs"] for m in s["frames"]}
                ov_old += len(po & set(fo))
                ov_new += len(pn & set(fn))
            roles = "".join(s["role"][0] for s in t["segs"])
            print(f" {t['label']:>3} {'두 버림' if (o.get('same_seg') or 1) >= 2 else '      '} | {len(fo):4d} · {hc.hms(fo[0])[3:]}~{hc.hms(fo[-1])[3:]} | {len(fn):4d} · "
                  + (f"{hc.hms(fn[0])[3:]}~{hc.hms(fn[-1])[3:]}" if fn else "없음") + f" · {t['cut']['discard']} · {roles} | {t['cut']['by']}")
        print(f"이웃한 차례끼리 겹치는 프레임: 옛 묶음 {ov_old} → 새 묶음 {ov_new} · 프레임 합 {sum(len(s['frames']) for o in old for s in o['segs'])} → {sum(len(s['frames']) for t in new for s in t['segs'])}")


def cmd_reread(a):
    """새 묶음으로 판독기 A · B 를 다시 부른다(고른 차례만) → _work/turncut_1117/<판>_<판독기>.json. 답은 score 로 본다."""
    import time
    from google.genai import types
    import gemframes as gf
    import gemturn as gt
    import pgraph as pg
    import pixtrack as pt
    gid = a.games[0]
    ids = set(a.ids.split(","))
    ts = [t for t in turns_of(gid) if t["id"] in ids]
    out = hc.WORK / "turncut_1117"
    for r in a.readers:
        f = out / f"{gid}_{r}.json"
        have = {x["id"]: x for x in hc.jload(f)["rows"]} if f.exists() else {}
        todo = [t for t in ts if not (have.get(t["id"]) or {}).get("kind")]
        if not todo:
            continue
        if r == "E":
            import endmove as em
            fn = lambda t: em.one(gf.client(), types, t, 1, 2, 0.55)  # noqa: E731  (pgraph2 의 고정값 v1 · 초당 5장 · 오른쪽 55%)
            todo = [t for t in ts if not (have.get(t["id"]) or {}).get("moved")]
            if not todo:
                continue
        elif r == "A":
            try:
                R = pt.Row(gid)
            except Exception:  # noqa: BLE001
                R = None
            fn = lambda t: pg.read_a(gf.client(), types, t, R)  # noqa: E731
        else:
            fn = lambda t: gt.one(gf.client(), types, pg.MODEL, t)  # noqa: E731
        with ThreadPoolExecutor(3) as ex:
            rows = list(ex.map(fn, todo))
        for x in rows:
            have[x["id"]] = x
        hc.jsave(f, {"game": gid, "reader": r, "at": hc.hms(int(time.time() * 1000), date=True), "rows": list(have.values())})
        i, o = sum(x.get("in", 0) for x in rows), sum(x.get("out", 0) + x.get("think", 0) for x in rows)
        print(f"{gid} {r}: 차례 {len(rows)} · 입력 {i:,} · 출력+생각 {o:,} · {i * 0.75e-6 + o * 3.75e-6:.2f}달러 · 오류 {sum('error' in x for x in rows)}")


def cmd_score(a):
    """새 묶음으로 다시 읽은 답을 정답 · 옛 묶음의 답과 나란히."""
    import pgraph as pg
    truth = hc.jload(BASE / "truth_final.json")
    for gid in a.games:
        new = {r: ({x["id"]: x for x in hc.jload(hc.WORK / "turncut_1117" / f"{gid}_{r}.json")["rows"]} if (hc.WORK / "turncut_1117" / f"{gid}_{r}.json").exists() else {}) for r in "ABE"}
        old = {"A": pg.load_a(gid, False) or {}, "B": pg.load_b(gid, False) or {}}
        show = lambda v: "-" if v is None else f"{v['kind'][:1]} {v['k']} {v['j']}"  # noqa: E731
        print(f"== {gid}")
        for i in sorted(set(new["A"]) | set(new["B"])):
            u = truth[i]
            line = f"  {i} 정답 {u['kind'][:1]} {u.get('k_id')} {u.get('j_closed')}"
            for r in "AB":
                o, n = pg.norm(old[r].get(i)), pg.norm(new[r].get(i))
                line += f" | {r} 옛 {show(o)} {'✓' if pg.right(o, u) else '✗'} → 새 {show(n)} {('✓' if pg.right(n, u) else '✗') if n else ''}"
            oa, ob, na, nb = (pg.norm(old["A"].get(i)), pg.norm(old["B"].get(i)), pg.norm(new["A"].get(i)), pg.norm(new["B"].get(i)))
            same = lambda x, y: x is not None and y is not None and (x["kind"], x["k"], x["j"]) == (y["kind"], y["k"], y["j"])  # noqa: E731
            st = lambda x, y: "사람" if not same(x, y) else ("자동 맞음" if pg.right(x, u) else "**조용한 틀림**")  # noqa: E731
            e = (new["E"].get(i) or {}).get("moved")
            ste = "-" if not (na and nb) else ("사람(E)" if same(na, nb) and e in ("yes", "unsure") else st(na, nb))
            print(line + f" | A+B 옛 {st(oa, ob)} → 새 {st(na, nb) if na and nb else '-'} | E {e or '안 부름'} → A+B+E 새 {ste}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "check", "reread", "score"):
        p = sp.add_parser(name)
        p.add_argument("games", nargs="+")
        if name == "build":
            p.add_argument("--out", help="쓸 파일(기본 turns_cut.json). r15 · L16 은 turncut.EXTRA 의 파일로")
        if name == "reread":
            p.add_argument("--ids", required=True)
            p.add_argument("--readers", default="AB")
    a = ap.parse_args()
    {"build": cmd_build, "check": cmd_check, "reread": cmd_reread, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
