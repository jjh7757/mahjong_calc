"""칸 틀 도구 — 손패 줄에 칸 0 ~ N+2 틀을 대고 프레임마다 칸별 참 / 빔 / 가림을 글로 낸다(2026-11-17, 계획서 3단계 "추가 16").

사용자 제안: 검출기로 손패를 잡아 패 한 장 폭을 재고, (13장이면) 0 ~ 15 칸 틀을 만들어 매 프레임에 갖다 대 빈칸을 본다 → 판독하는 쪽이 도구로 쓴다.
  python -X utf8 slotgrid.py detect <판 id…> [--ids a,b] [--step 2]   # 차례 창 프레임의 뒷면 상자 · 가림 열 캐시 → _work/slotgrid_1117/det_<판>.json
  python -X utf8 slotgrid.py look <차례 id…> [--raw]                    # 칸 상태 줄글(정답 · 판독기 답은 안 찍음)
  python -X utf8 slotgrid.py events <차례 id…> [--count]                # 사건 목록(줄을 따라가며 칸 변화 · 가림 구간 · 줄 밀림만) — look 의 1/5 길이
  python -X utf8 slotgrid.py score <이름>                               # _work/slotgrid_1117/read_<이름>.json 채점(호출 없음)
칸: 1 ~ N = 차례 시작 줄, N+1 = 뽑은 패 자리, 0 · N+2 = 양 끝 바깥(slotsim 과 같은 번호).
상태: 참 = 뒷면 상자가 칸의 75% 이상 / 가림 = 손 · 소매 화소가 칸의 30% 이상(상자가 없을 때) / 빔 = 상자 25% 이하 / 걸침 = 그 사이(줄이 밀려 칸 경계에 걸침).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402
import turncut as tc  # noqa: E402

OUT = hc.WORK / "slotgrid_1117"
PRE_MS, POST_MS = 2500, 1500   # 창 앞뒤로 더 보는 길이(시작 줄 · 끝 줄을 잡으려고)
FULL, EMPTY, OCC = 0.75, 0.25, 0.30
JOIN = 0.45                    # 이웃 상자 사이가 한 장 폭의 이 비율 이하면 같은 덩어리(dettrack 과 같음)


def game_of(tid: str) -> str:
    for g in tc.cut_games():          # 11-19: turns_cut.json + tc.EXTRA(r15 · L16)
        if any(t["id"] == tid for t in g["turns"]):
            return g["id"]
    raise SystemExit(f"차례 {tid} 가 turns_cut.json · {[f.name for f in tc.EXTRA]} 에 없다")


def window(t: dict) -> tuple[int, int]:
    return t["segs"][0]["frames"][0] - PRE_MS, t["segs"][-1]["frames"][-1] + POST_MS


def occ_cols(R: "pt.Row", v: np.ndarray) -> list:
    """손 · 소매가 줄을 덮은 열 범위(대국자 시점 x) — pixtrack.runs_of 의 skin_col 과 같은 계산."""
    skin = pt.masks(v)[0]
    h = R.y1 - R.y0
    col = skin[max(0, R.y0 - h):R.y1 + h // 2].mean(0) > 0.08
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


def cmd_detect(a):
    import dettrack as dt
    L = dt.reader()
    OUT.mkdir(parents=True, exist_ok=True)
    ids = set(a.ids.split(",")) if a.ids else None
    for gid in a.games:
        cfg, R = hc.config(gid), pt.Row(gid)
        f = OUT / f"det_{gid}.json"
        cache = hc.jload(f) if f.exists() else {}
        todo = sorted({ms for t in tc.turns_of(gid) if ids is None or t["id"] in ids for ms in hc.frame_range(*window(t))[::a.step]} - {int(k) for k in cache})
        t0 = time.time()
        for i, ms in enumerate(todo):
            rgb = hc.load(ms)
            cache[str(ms)] = {"b": dt.boxes_view(L, rgb, cfg), "o": occ_cols(R, hc.band_crop(rgb, cfg["sheet_band"], cfg["side"]))}
            if i % 300 == 0:
                print(gid, i, len(todo), f"{time.time() - t0:.0f}s", flush=True)
                hc.jsave(f, cache, indent=None)
        hc.jsave(f, cache, indent=None)
        print(gid, "끝", len(todo), "장", f"{time.time() - t0:.0f}s", flush=True)


def clusters(bs: list, p: float) -> list:
    out = []
    for b in sorted(bs):
        if out and b[0] - out[-1][1] <= JOIN * p:
            out[-1][1] = max(out[-1][1], b[1])
            out[-1][2] += 1
        else:
            out.append([b[0], b[1], 1])
    return out


def anchor(frs: list, n: int):
    """시작 줄: 상자 n개가 한 덩어리이고 그 위에 가림이 없는 첫 프레임 → (왼쪽 끝, 한 장 폭, 줄 y 가운데, 상자 높이, 시각)."""
    for ms, d in frs:
        bs = d["b"]
        if len(bs) != n:
            continue
        cl = clusters(bs, (max(b[1] for b in bs) - min(b[0] for b in bs)) / n)
        if len(cl) != 1:
            continue
        x0, x1 = cl[0][0], cl[0][1]
        if any(o[0] < x1 and o[1] > x0 for o in d["o"]):
            continue
        yc = float(np.median([(b[2] + b[3]) / 2 for b in bs]))
        return x0, (x1 - x0) / n, yc, float(np.median([b[3] - b[2] for b in bs])), ms
    return None


def state(d: dict, left0: float, p: float, yc: float, hh: float, n: int):
    row = [b for b in d["b"] if abs((b[2] + b[3]) / 2 - yc) <= 0.5 * hh]
    off = [b for b in d["b"] if abs((b[2] + b[3]) / 2 - yc) > 0.5 * hh]
    st = []
    for i in range(n + 3):
        a, b = left0 + (i - 1) * p, left0 + i * p
        cov = sum(max(0.0, min(b, x[1]) - max(a, x[0])) for x in row) / p
        oc = sum(max(0.0, min(b, o[1]) - max(a, o[0])) for o in d["o"]) / p
        st.append("참" if cov >= FULL else "가림" if oc >= OCC else "빔" if cov <= EMPTY else "걸침")
    u = lambda x: (x - left0) / p  # noqa: E731  칸 단위(0.0 = 1번 칸 왼쪽 끝)
    cl = [f"{u(c[0]):.1f}~{u(c[1]):.1f}({c[2]})" for c in clusters(row, p)]
    fl = [f"{u((b[0] + b[1]) / 2) + 0.5:.1f}{'앞' if (b[2] + b[3]) / 2 > yc else '뒤'}" for b in off]
    hand = f"{u(min(o[0] for o in d['o'])) + 1:.1f}~{u(max(o[1] for o in d['o'])) + 1:.1f}" if d["o"] else ""
    return st, len(row), cl, fl, hand


def line_of(st: list, n: int) -> str:
    ends = f"0:{st[0]} {n + 1}:{st[n + 1]} {n + 2}:{st[n + 2]}"
    inner = {k: [i for i in range(1, n + 1) if st[i] == k] for k in ("빔", "가림", "걸침")}
    return ends + " | 줄 안 " + (" ".join(f"{k}{v}" for k, v in inner.items() if v) or "다 참")


def cmd_look(a):
    for tid in a.ids:
        gid = game_of(tid)
        t = next(x for x in tc.turns_of(gid) if x["id"] == tid)
        det = {int(k): v for k, v in hc.jload(OUT / f"det_{gid}.json").items()}
        n = t["n_calc"]
        w0, w1 = window(t)
        frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
        print(f"== {tid} · {t['label']}순 · 시작 줄 {n}장 · 창 {t['cut']['start']}~{t['cut']['end']} · 버림 시각 {t['cut']['discard']}"
              + (" · 리치 선언(눕힘)" if t.get("sideways") else "") + (f" · 울기 {t['meld_tiles']}" if t.get("meld_tiles") else ""))
        print("   손 움직임 조각: " + " ".join(f"[{s['role']} {hc.mss(s['frames'][0])}~{hc.mss(s['frames'][-1])}]" for s in t["segs"]))
        an = anchor(frs, n)
        if an is None:
            print("   시작 줄을 못 잡음(상자 n개 한 덩어리 · 가림 없음인 프레임이 없다)")
            continue
        left0, p, yc, hh, ams = an
        print(f"   틀: {hc.mss(ams)} 의 줄로 잡음 · 한 장 폭 {p:.1f}px · 칸 0 ~ {n + 2} · 덩어리 = 칸 단위 범위(상자 수), 0.0 = 1번 칸 왼쪽 끝 · 뜬 상자 = 줄에서 앞(대국자 쪽)/뒤로 벗어난 상자의 칸 위치 · 손 = 가림 열의 칸 범위")
        prev, start, cnt, last_ms = None, None, 0, None

        def flush():
            if prev is not None:
                st, nb, cl, fl, hand = prev
                print(f"   {hc.mss(start)}~{hc.mss(last_ms)} ({cnt}장)  {line_of(st, n)} | 줄 상자 {nb} 덩어리 {' '.join(cl) or '-'}" + (f" | 뜬 상자 {' '.join(fl)}" if fl else "") + (f" | 손 {hand}" if hand else ""))

        for ms, d in frs:
            cur = state(d, left0, p, yc, hh, n)
            key = (cur[0], cur[1], bool(cur[3])) if not a.raw else None
            if prev is None or a.raw or key != (prev[0], prev[1], bool(prev[3])):
                flush()
                prev, start, cnt = cur, ms, 0
            cnt += 1
            last_ms = ms
        flush()


# ------------------------------------------------------------------ 사건 목록(줄 따라가기)
STEP_MIN = 0.10   # 상자들이 이만큼(칸) 넘게 같이 움직였을 때만 "줄이 통째로 몇 칸 밀렸나" 를 따진다
MERGE_MS = 1000   # 이 안에 한 칸이 차고 다른 칸이 비면 "빈칸이 옮겨 감" 한 줄로
COVER_MIN = 600   # 이보다 짧은 가림은 줄로 안 적는다(사건이 걸린 가림은 사건 줄에 적힌다)


def row_line(bs: list, a: float, b: float, hh: float):
    """줄 가운데 선 y = a + b·x 에 붙은 상자만(줄이 기울어도 따라감) → (줄 상자, 벗어난 상자, a, b)."""
    res = lambda x, a, b: (x[2] + x[3]) / 2 - (a + b * (x[0] + x[1]) / 2)  # noqa: E731
    near = [x for x in bs if abs(res(x, a, b)) <= 1.0 * hh]
    if len(near) >= 6:
        xs, ys = np.array([(x[0] + x[1]) / 2 for x in near]), np.array([(x[2] + x[3]) / 2 for x in near])
        b2, a2 = np.polyfit(xs, ys, 1)
        if abs(b2) < 0.2:
            a, b = float(a2), float(b2)
    row = [x for x in bs if abs(res(x, a, b)) <= 0.45 * hh]
    off = [(x, res(x, a, b)) for x in bs if abs(res(x, a, b)) > 0.45 * hh]
    return row, off, a, b


def slot_states(row: list, occ: list, left0: float, p: float, n: int) -> list:
    """칸 0 ~ n+2 → 'F'(참) · 'E'(빔) · '?'(가림 = 모름).
    참은 겹친 넓이가 아니라 덩어리의 순서로 매긴다: 덩어리 왼쪽 끝을 가장 가까운 칸에 맞추고 그 덩어리의 상자 수만큼 이어서 참.
    (이웃 패가 0.3칸쯤 밀려 빈칸이 좁아져도 "한 칸 빔" 으로 남는다 — 넓이로 재면 걸침이 돼 사라졌다.)"""
    full, nxt, spans = set(), -99, []
    for c in clusters(row, p):
        s = max(nxt, int(round((c[0] - left0) / p)) + 1)
        full.update(range(s, s + c[2]))
        spans.append((s, s + c[2] - 1))
        nxt = s + c[2]
    st = []
    for i in range(n + 3):
        a, b = left0 + (i - 1) * p, left0 + i * p
        oc = sum(max(0.0, min(b, o[1]) - max(a, o[0])) for o in occ) / p
        st.append("F" if i in full else "?" if oc >= OCC else "E")
    return st, spans


def track(frs: list, n: int, an) -> list:
    """프레임마다 줄을 따라가며(틀의 왼쪽 끝을 다시 맞춤) 칸 상태를 낸다 → [{ms, st, drift, cov(가린 칸 범위), off}]."""
    left0, p, yc, hh, ams = an
    a, b, drift, last, out, moved = yc, 0.0, 0.0, None, [], 0.0
    for ms, d in frs:
        if ms < ams:
            continue
        row, off, a, b = row_line(d["b"], a, b, hh)
        free = [x for x in row if not any(o[0] < x[1] + 2 and o[1] > x[0] - 2 for o in d["o"])]
        step = 0.0
        if len(free) >= 5:
            fr = np.array([(x[0] - left0) / p - round((x[0] - left0) / p) for x in free])
            dl = float(np.median(fr))
            # 줄이 통째로 밀릴 때만 따라간다: 보이는 상자의 80% 넘게 같은 만큼 움직였을 때(한 덩어리만 당겨진 것은 줄 밀림이 아니다)
            if float(np.mean(np.abs(fr - dl) < 0.12)) >= 0.8 and abs(dl) > 0.04:
                left0, step = left0 + dl * p, dl
        st, spans = slot_states(row, d["o"], left0, p, n)
        moved += abs(step)
        if moved >= STEP_MIN and last is not None and len(free) >= 5:
            # 가림 사이에 줄이 통째로 밀리면 소수 부분만으로는 몇 칸인지 모른다(0.8칸 밀림 = −0.2칸으로 보임) → 앞 상태와 덜 어긋나는 쪽을 고른다.
            # 줄 끝이 가려 있으면 가릴 수 없으니 moved 를 남겨 두고 끝이 보일 때 다시 따진다.
            # 상자가 제자리(moved ≈ 0)면 안 따진다: 패 한 장을 끝에서 끝으로 옮긴 것과 줄이 정확히 한 칸 밀린 것은 앞뒤 모양이 같고, 앞쪽이 훨씬 흔하다.
            mis = lambda s: sum(1 for x, y in zip(s, last) if x != "?" and y != "?" and x != y)  # noqa: E731
            m0 = mis(st)
            k = min((0, 1, -1, 2, -2, 3, -3), key=lambda q: (mis(slot_states(row, d["o"], left0 + q * p, p, n)[0]), abs(q)))
            if k and m0 - mis(slot_states(row, d["o"], left0 + k * p, p, n)[0]) >= 2:
                left0, step, moved = left0 + k * p, step + k, 0.0
                st, spans = slot_states(row, d["o"], left0, p, n)
                for o in out[::-1]:                      # 미끄러진 동안의 프레임은 칸 번호가 어긋났으니 모름으로 돌린다
                    if not o["slip"]:
                        break
                    o["st"] = ["?"] * (n + 3)
            elif m0 == 0 and not d["o"]:
                moved = 0.0
        drift += step
        if len(free) >= 5:
            last = [x if x != "?" else y for x, y in zip(st, last)] if last else st
        u = lambda x: (x - left0) / p + 1  # noqa: E731  칸 번호 단위(1.0 = 1번 칸 왼쪽 끝)
        fs = [i for i, s in enumerate(st) if s == "F"] or [1, n]
        lo_ok, hi_ok = min(fs) - 1, max(fs) + 1                       # 줄 양 끝 한 칸 밖까지만 가림으로 친다(줄 옆에 얹어 둔 손은 뺌)
        cov = [(max(lo_ok, int(np.floor(u(o[0])))), min(hi_ok, int(np.floor(u(o[1]))))) for o in d["o"] if u(o[1]) > lo_ok and u(o[0]) < hi_ok + 1]
        out.append({"ms": ms, "st": st, "drift": drift, "cov": (min(c[0] for c in cov), max(c[1] for c in cov)) if cov else None,
                    "off": [f"{u((x[0] + x[1]) / 2):.0f}번 {'앞' if r > 0 else '뒤'}" for x, r in off], "n": sum(s == "F" for s in st), "slip": moved >= STEP_MIN,
                    "spans": spans, "nrow": len(row), "hole": any(st[i] == "?" for i in range(min(fs), max(fs) + 1)), "force": {}})
    return out


def slot_events(tr: list, n: int):
    """칸마다 확인된 상태 변화(두 번 이어 보여야 확정) + 한 장만 보인 변화(약한 근거)."""
    cur = list(tr[0]["st"])
    seen = [tr[0]["ms"] if s != "?" else None for s in cur]   # 그 칸을 마지막으로 또렷이 본 때
    seen_i = [0 if s != "?" else None for s in cur]            # … 그 프레임 번호
    pend = [None] * (n + 3)
    ev = []
    for fi, f in enumerate(tr[1:], 1):
        for i, v in f["force"].items():                        # 줄 상자 수로 추론한 빈칸(fill_kind) — 바로 확정
            if cur[i] != v:
                ev.append({"ms": f["ms"], "slot": i, "to": v, "weak": False, "hid": None, "inf": True, "g": seen_i[i], "f": fi})
                cur[i], pend[i], seen[i], seen_i[i] = v, None, f["ms"], fi
        for i, v in enumerate(f["st"]):
            if v == "?" or i in f["force"]:
                continue
            if cur[i] == "?":
                cur[i], seen[i], seen_i[i] = v, f["ms"], fi
                continue
            if v == cur[i]:
                if pend[i]:
                    ev.append({"ms": pend[i][1], "slot": i, "to": pend[i][0], "weak": True, "hid": pend[i][2], "post": f["ms"]})
                    pend[i] = None
                seen[i], seen_i[i] = f["ms"], fi
            elif pend[i] and pend[i][0] == v:
                ev.append({"ms": pend[i][1], "slot": i, "to": v, "weak": False, "hid": pend[i][2], "g": pend[i][3], "f": pend[i][4]})
                cur[i], pend[i], seen[i], seen_i[i] = v, None, f["ms"], fi
            else:
                pend[i] = (v, f["ms"], seen[i], seen_i[i], fi)
    for i, q in enumerate(pend):
        if q:
            ev.append({"ms": q[1], "slot": i, "to": q[0], "weak": False, "hid": q[2], "tail": True, "g": q[3], "f": q[4]})
            cur[i] = q[0]
    return sorted(ev, key=lambda e: (e["ms"], e["slot"])), cur


def fill_kind(tr: list, g, f, s: int):
    """빈칸 s 가 찬 까닭을 줄 상자 수로 가른다(둘 다 줄 안에 가림이 없을 때만).
    상자 +1 → 그 자리에 패가 놓임('new'). 상자 그대로 → 옆 덩어리가 한 칸 당겨져 메운 것('L' = 오른쪽 패들이 왼쪽으로, 'R' = 반대) + 새로 빈 끝 칸."""
    if g is None or f is None:
        return None
    A, B = tr[g], tr[f]
    if A["hole"] or B["hole"]:
        return None
    if B["nrow"] == A["nrow"] + 1:
        return ("new", None)
    if B["nrow"] != A["nrow"]:
        return None
    ra = next((sp for sp in A["spans"] if sp[0] == s + 1), None)
    la = next((sp for sp in A["spans"] if sp[1] == s - 1), None)
    sb = next((sp for sp in B["spans"] if sp[0] <= s <= sp[1]), None)
    if ra and sb and sb[1] == ra[1] - 1 and (la is None or sb[0] == la[0]):
        return ("L", ra[1])
    if la and sb and sb[0] == la[0] + 1 and (ra is None or sb[1] == ra[1]):
        return ("R", la[0])
    return None


def ranges(xs: list) -> str:
    out, xs = [], sorted(xs)
    for x in xs:
        if out and x == out[-1][1] + 1:
            out[-1][1] = x
        else:
            out.append([x, x])
    return " · ".join(f"{a}" if a == b else f"{a}~{b}" for a, b in out) or "없음"


def sec_of(s: str) -> float:
    m, x = s.split(":")
    return int(m) * 60 + float(x)


def cmd_events(a):
    tot = 0
    for tid in a.ids:
        gid = game_of(tid)
        t = next(x for x in tc.turns_of(gid) if x["id"] == tid)
        det = {int(k): v for k, v in hc.jload(OUT / f"det_{gid}.json").items()}
        n = t["n_calc"]
        w0, w1 = window(t)
        frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
        lines = [f"== {tid} · {t['label']}순 · 시작 줄 {n}장 · 칸 0 ~ {n + 2}(1 ~ {n} = 시작 줄, {n + 1} = 오른쪽 끝 옆, 0 = 왼쪽 끝 옆)"
                 + (" · 리치 선언(눕힘)" if t.get("sideways") else "") + (f" · 울기 {t['meld_tiles']}" if t.get("meld_tiles") else "")]
        an = anchor(frs, n)
        if an is None:
            print(lines[0] + "\n   시작 줄을 못 잡음")
            continue
        tr = track(frs, n, an)
        why = {}
        for _ in range(4):                                   # 당겨져 메운 빈칸 → 새로 빈 끝 칸을 확정으로 넣고 다시(이어지는 당김까지)
            ev, cur = slot_events(tr, n)
            new = 0
            for e in ev:
                if e["weak"] or e["to"] != "F" or e.get("inf") or (e["ms"], e["slot"]) in why:
                    continue
                k = fill_kind(tr, e.get("g"), e.get("f"), e["slot"])
                why[(e["ms"], e["slot"])] = k
                if k and k[0] in "LR" and 0 <= k[1] <= n + 2 and tr[e["f"]]["st"][k[1]] != "F":
                    tr[e["f"]]["force"][k[1]] = "E"
                    new += 1
            if not new:
                break
        occ0 = [i for i, s in enumerate(tr[0]["st"]) if s == "F"]
        items = [(tr[0]["ms"], 0, f"시작 줄: {ranges(occ0)}번 참({len(occ0)}장)")]
        # 버림 시각(강 위 손)
        if t["cut"].get("discard"):
            ds = sec_of(t["cut"]["discard"])
            dms = min(tr, key=lambda f: abs((f["ms"] / 1000 - ds + 1800) % 3600 - 1800))["ms"]
            items.append((dms, 5, f"── 버림(강 위에 손) {t['cut']['discard']} ──"))
        # 사건: 가까운 [찼음 + 비었음] 한 쌍은 "빈칸이 옮겨 감" 으로
        strong = [e for e in ev if not e["weak"]]
        groups = []
        for e in strong:                                   # 가까운 사건끼리 묶음(묶음의 첫 사건에서 MERGE_MS 안)
            if groups and e["ms"] - groups[-1][0]["ms"] <= MERGE_MS:
                groups[-1].append(e)
            else:
                groups.append([e])
        hid_of = lambda e: f" ({e['slot']}번은 {hc.mss(e['hid'])} 부터 가려져 있었음)" if e["hid"] and e["ms"] - e["hid"] > 500 else ""  # noqa: E731
        for g in groups:
            kind = lambda e: why.get((e["ms"], e["slot"])) if e["to"] == "F" else None  # noqa: E731
            plain = [e for e in g if not e.get("inf")]
            hid = "".join(hid_of(e) for e in plain)
            tail = " (창 끝 한 장뿐)" if any(e.get("tail") for e in g) else ""
            if len(g) == 2 and len(plain) == 2 and {e["to"] for e in g} == {"F", "E"} and g[0]["slot"] != g[1]["slot"] and not any(kind(e) for e in g):
                f_ = next(e["slot"] for e in g if e["to"] == "F")
                m_ = next(e["slot"] for e in g if e["to"] == "E")
                near = m_ - 1 if m_ > f_ else m_ + 1
                txt = (f"{m_}번 패가 {f_}번으로 한 칸 옮겨 감" if abs(f_ - m_) == 1 else
                       f"{f_}번이 차고 {m_}번이 빔(줄 장수 그대로) — 사이 패들이 한 칸씩 밀려 메웠거나(순서 그대로), {m_}번 패를 {min(f_, near)}~{max(f_, near)}번 사이 어딘가에 끼운 것(어디인지는 이 목록으로 모름)")
                items.append((g[0]["ms"], 2, txt + hid + tail))
                continue
            parts, done = [], set()
            for q, e in enumerate(g):                        # 묶음 안에서도 일어난 순서대로
                if q in done:
                    continue
                k = kind(e)
                nxt = next((r for r in range(q + 1, len(g)) if r not in done and g[r]["slot"] == e["slot"]), None)
                if e["to"] == "F" and k and k[0] in "LR":    # 줄 상자 수 그대로 + 덩어리 끝이 한 칸 줄어듦 → 당겨져 메운 것(방향까지 앎)
                    done.update(r for r, o in enumerate(g) if o.get("inf") and o["slot"] == k[1] and o["to"] == "E")
                    lo, hi = (e["slot"] + 1, k[1]) if k[0] == "L" else (k[1], e["slot"] - 1)
                    quick = tr[e["f"]]["ms"] - tr[e["g"]]["ms"] <= 600   # 빈칸을 본 프레임과 찬 프레임이 붙어 있으면 그냥 당긴 것, 사이가 길면 끝 패를 안쪽에 끼웠을 수도
                    who = f"{lo}번 패가" if lo == hi else f"{lo}~{hi}번 패가"
                    parts.append(f"{e['slot']}번 빈칸이 메워짐 — {who} {'왼쪽' if k[0] == 'L' else '오른쪽'}으로 한 칸씩 당겨짐(줄 상자 수 그대로) → {k[1]}번이 빔"
                                 + ("" if quick else f" (빈칸을 마지막으로 본 때부터 {(tr[e['f']]['ms'] - tr[e['g']]['ms']) / 1000:.1f}초 — {k[1]}번 패를 그 사이 어딘가에 끼웠을 수도)"))
                elif e.get("inf"):
                    parts.append(f"{e['slot']}번이 빔(상자 수로 추론)")
                elif e["to"] == "E":
                    kn = kind(g[nxt]) if nxt is not None and g[nxt]["to"] == "F" else None
                    if nxt is not None and g[nxt]["to"] == "F" and not (kn and kn[0] in "LR"):
                        done.add(nxt)
                        parts.append(f"{e['slot']}번 패를 들었다가 그 칸에 다시 패를 놓음(줄 상자 −1 → +1)" if kn and kn[0] == "new" else f"{e['slot']}번 칸이 잠깐 비었다 다시 참")
                    else:
                        parts.append(f"{e['slot']}번 칸 패가 빠짐")
                else:
                    if nxt is not None and g[nxt]["to"] == "E" and not g[nxt].get("inf"):
                        done.add(nxt)
                        parts.append(f"{e['slot']}번 칸이 잠깐 찼다 다시 빔")
                    else:
                        parts.append(f"{e['slot']}번 칸에 패가 놓임" + ("(줄 상자 +1)" if k and k[0] == "new" else ""))
            items.append((g[0]["ms"], 2, " → ".join(parts) + hid + tail))
        # 손이 줄에 안 닿은 프레임의 줄 모양(두 프레임 넘게 이어진 것, 바뀔 때만) — 가장 믿을 만한 줄
        shown, i = tuple(k for k, x in enumerate(tr[0]["st"]) if x == "F"), 0
        while i < len(tr):
            if tr[i]["cov"] is not None or tr[i]["slip"]:
                i += 1
                continue
            occ_i = tuple(k for k, s in enumerate(tr[i]["st"]) if s == "F")
            j = i
            while j + 1 < len(tr) and tr[j + 1]["cov"] is None and tuple(k for k, s in enumerate(tr[j + 1]["st"]) if s == "F") == occ_i:
                j += 1
            if j > i and occ_i != shown:
                items.append((tr[i]["ms"], 0, f"[손 안 닿은 줄] {ranges(list(occ_i))}번 참({len(occ_i)}장)"))
                shown = occ_i
            i = j + 1
        for e in ev:
            if e["weak"]:
                alone = e["hid"] and e["ms"] - e["hid"] > 500 and e["post"] - e["ms"] > 500   # 앞뒤로 그 칸이 가려 있었다 = 그 사이에 본 것은 이 한 장뿐
                items.append((e["ms"], 3, f"(한 장만) {e['slot']}번 칸이 {'참' if e['to'] == 'F' else '빔'}"
                              + (f" — {hc.mss(e['hid'])}~{hc.mss(e['post'])} 사이 그 칸은 가려 있었고 보인 것은 이 한 장뿐" if alone else " — 앞뒤 프레임은 반대(깜빡임일 수 있음)")))
        # 가림 구간
        evms = sorted(e["ms"] for e in ev)
        i = 0
        while i < len(tr):
            if tr[i]["cov"] is None:
                i += 1
                continue
            j, lo, hi = i, tr[i]["cov"][0], tr[i]["cov"][1]
            while j + 1 < len(tr) and (tr[j + 1]["cov"] is not None or (j + 2 < len(tr) and tr[j + 2]["cov"] is not None)):
                j += 1
                if tr[j]["cov"]:
                    lo, hi = min(lo, tr[j]["cov"][0]), max(hi, tr[j]["cov"][1])
            t0, t1 = tr[i]["ms"], tr[j]["ms"]
            if t1 - t0 >= COVER_MIN:
                ch = any(t0 - 200 <= m <= t1 + 600 for m in evms)
                items.append((t0, 1, f"손 가림 {hc.mss(t0)}~{hc.mss(t1)}({(t1 - t0) / 1000:.1f}초) {lo}~{hi}번 칸" + ("" if ch else " · 앞뒤 줄 같음")))
            i = j + 1
        # 줄 전체 밀림
        rep = 0.0
        for f in tr:
            if abs(f["drift"] - rep) >= 0.3:
                items.append((f["ms"], 4, f"줄 전체가 {'오른쪽' if f['drift'] > rep else '왼쪽'}으로 {abs(f['drift'] - rep):.1f}칸 밀림(틀이 따라감 — 칸 번호는 줄 기준 그대로)"))
                rep = f["drift"]
        # 줄 밖 상자(두 프레임 넘게 이어진 것만)
        i = 0
        while i < len(tr):
            if not tr[i]["off"]:
                i += 1
                continue
            j = i
            while j + 1 < len(tr) and tr[j + 1]["off"]:
                j += 1
            if j > i:
                items.append((tr[i]["ms"], 6, f"줄 밖 상자 {hc.mss(tr[i]['ms'])}~{hc.mss(tr[j]['ms'])}: {', '.join(sorted(set(x for f in tr[i:j + 1] for x in f['off']), key=lambda s: int(s.split('번')[0])))}"))
            i = j + 1
        for ms, _, txt in sorted(items, key=lambda x: (x[0], x[1])):
            lines.append(f"   {hc.mss(ms)}  {txt}")
        occ1 = [i for i, s in enumerate(cur) if s == "F"]
        unk = [i for i, s in enumerate(cur) if s == "?" and 1 <= i <= n]
        lines.append(f"   끝 줄: {ranges(occ1)}번 참({len(occ1)}장)" + (f" · 모름 {ranges(unk)}번" if unk else "") + f" · 줄 밀림 합 {tr[-1]['drift']:+.1f}칸")
        lines.append("   (손 가림 밑에서 패를 빼고 그 자리에 다른 패를 넣거나, 가린 채 줄 안쪽에 끼우면 이 목록에 안 남는다 — 그 구간은 그림으로 볼 것)")
        txt = "\n".join(lines)
        tot += len(txt)
        print(txt)
    if a.count:
        print(f"[글자 수 합 {tot:,} · 차례 {len(a.ids)}]")


SEEN = {"r12_d02", "r12_d03", "r12_d03b", "r17_d11"}                                   # 이 세션이 읽기 전에 정답을 본 차례(계획서 추가 16)
HINT = {"r12_d04", "r12_d06", "r17_d03", "r17_d10", "r19_d03", "r19_d03b", "r19_d07"}  # 문서에서 힌트를 본 차례


def cmd_score(a):
    """도구만 보고 적은 답(read_<이름>.json)을 정답 · 저장된 A · B(옛 묶음) 답과 맞댄다. 호출 없음."""
    import pgraph as pg
    truth = hc.jload(tc.BASE / "truth_final.json")
    rows = {r["id"]: r for r in hc.jload(OUT / f"read_{a.name}.json")["rows"]}
    tot = {g: {"n": 0, "T": 0, "A": 0, "B": 0, "quiet": 0, "unsure": 0} for g in ("가린", "힌트", "정답 봄")}
    oa, ob = {}, {}
    for i in sorted(rows):
        gid = game_of(i)
        if gid not in oa:
            oa[gid], ob[gid] = pg.load_a(gid, False) or {}, pg.load_b(gid, False) or {}
        u, r = truth[i], pg.norm(rows[i])
        na, nb = pg.norm(oa[gid].get(i)), pg.norm(ob[gid].get(i))
        g = "정답 봄" if i in SEEN else "힌트" if i in HINT else "가린"
        show = lambda v: "-" if v is None else f"{v['kind'][:1]} {v['k']} {v['j']}"  # noqa: E731
        ok = pg.right(r, u)
        t = tot[g]
        t["n"] += 1
        t["T"] += ok
        t["A"] += pg.right(na, u)
        t["B"] += pg.right(nb, u)
        t["unsure"] += bool(rows[i].get("unsure"))
        t["quiet"] += (not ok) and not rows[i].get("unsure")
        print(f"  {i:9s} [{g}] 정답 {u['kind'][:1]} {u.get('k_id')} {u.get('j_closed')} | 도구 {show(r)}{' unsure' if rows[i].get('unsure') else ''} {'✓' if ok else '✗'}"
              f" | A {show(na)} {'✓' if pg.right(na, u) else '✗'} | B {show(nb)} {'✓' if pg.right(nb, u) else '✗'}")
    for g, t in tot.items():
        if t["n"]:
            print(f"{g}: {t['n']}차례 · 도구 {t['T']} · A {t['A']} · B {t['B']} · 도구 unsure {t['unsure']} · 도구 조용한 틀림 {t['quiet']}")
    s = {k: sum(t[k] for t in tot.values()) for k in ("n", "T", "A", "B", "unsure", "quiet")}
    print(f"합: {s['n']}차례 · 도구 {s['T']} · A {s['A']} · B {s['B']} · 도구 unsure {s['unsure']} · 도구 조용한 틀림 {s['quiet']}")


MOVE = {"r12_d02", "r12_d06", "r17_d11", "r19_d07", "r16_d02", "r16_d13", "r16_d16"}   # 옮김 표지(표 12-30 의 고친 표지 중 이 판들 + r16 2 · 13 · 16순)


def cmd_compare(a):
    """정답을 모르고 읽은 답 파일 여럿(read_<이름>.json)을 정답 · 저장된 A · B 와 나란히(계획서 추가 17). 호출 없음.
    A · B: r16 은 새 묶음 답(_work/turncut_1117), 나머지는 옛 묶음의 저장된 답."""
    import pgraph as pg
    truth = hc.jload(a.truth or tc.BASE / "truth_final.json")
    reads = {nm: {r["id"]: r for r in hc.jload(OUT / f"read_{nm}.json")["rows"]} for nm in a.names}
    ids = sorted(set().union(*[set(v) for v in reads.values()]))
    ab = {}
    for i in ids:
        gid = game_of(i)
        if gid not in ab:
            f = lambda r: hc.WORK / "turncut_1117" / f"{gid}_{r}.json"  # noqa: E731
            try:
                ab[gid] = ({x["id"]: x for x in hc.jload(f("A"))["rows"]}, {x["id"]: x for x in hc.jload(f("B"))["rows"]}) if gid.startswith("r16") \
                    else (pg.load_a(gid, False) or {}, pg.load_b(gid, False) or {})
            except Exception:  # noqa: BLE001  판독기를 안 돌린 판
                ab[gid] = ({}, {})
    cols = list(a.names) + ["A", "B"]
    tot = {g: {c: 0 for c in cols} | {"n": 0} | {f"q_{nm}": 0 for nm in a.names} | {f"u_{nm}": 0 for nm in a.names} for g in ("옮김", "그 밖")}
    silentAB = []
    show = lambda v: "-" if v is None else f"{v['kind'][:1]} {v['k']} {v['j']}"  # noqa: E731
    for i in ids:
        if i not in truth:
            continue
        u, g = truth[i], "옮김" if i in MOVE else "그 밖"
        na, nb = pg.norm(ab[game_of(i)][0].get(i)), pg.norm(ab[game_of(i)][1].get(i))
        t = tot[g]
        t["n"] += 1
        t["A"] += pg.right(na, u)
        t["B"] += pg.right(nb, u)
        if na and nb and (na["kind"], na["k"], na["j"]) == (nb["kind"], nb["k"], nb["j"]) and not pg.right(na, u):
            silentAB.append(i)
        line = f"  {i:9s}{' 옮김' if i in MOVE else '     '} 정답 {u['kind'][:1]} {u.get('k_id')} {u.get('j_closed')}"
        for nm in a.names:
            raw = reads[nm].get(i)
            r = pg.norm(raw)
            ok = pg.right(r, u)
            t[nm] += ok
            t[f"u_{nm}"] += bool(raw and raw.get("unsure"))
            t[f"q_{nm}"] += (not ok) and not (raw and raw.get("unsure"))
            line += f" | {nm} {show(r)}{'?' if raw and raw.get('unsure') else ''} {'✓' if ok else '✗'}"
        print(line + f" | A {show(na)} {'✓' if pg.right(na, u) else '✗'} | B {show(nb)} {'✓' if pg.right(nb, u) else '✗'}")
    for g in list(tot) + ["합"]:
        t = tot[g] if g != "합" else {k: sum(tot[x][k] for x in tot) for k in tot["옮김"]}
        print(f"{g}: {t['n']}차례 · " + " · ".join(f"{nm} {t[nm]}(unsure {t[f'u_{nm}']} · 조용한 틀림 {t[f'q_{nm}']})" for nm in a.names) + f" · A {t['A']} · B {t['B']}")
    print(f"A = B 인데 틀린 차례(조용한 틀림): {silentAB}")
    for nm in a.names:
        hit = [i for i in silentAB if not (pg.norm(reads[nm].get(i)) and (pg.norm(reads[nm][i])["kind"], pg.norm(reads[nm][i])["k"], pg.norm(reads[nm][i])["j"])
                                           == (pg.norm(ab[game_of(i)][0][i])["kind"], pg.norm(ab[game_of(i)][0][i])["k"], pg.norm(ab[game_of(i)][0][i])["j"]))]
        print(f"  그중 {nm} 이 A · B 와 다른 답을 낸 것(= 셋째 읽기로 걸러지는 것): {hit}")


def cmd_blind(a):
    """정답 모르는 읽는 쪽에게 줄 글 파일(안내문 + 그 판들의 리치 뒤 아닌 차례) → _work/slotgrid_1117/<out>. 내용은 화면에 안 찍는다."""
    import contextlib
    import io
    import endmove as em
    import slotgrid_guide as gd
    ids = []
    for gid in a.games:
        ts = tc.turns_of(gid)
        rule = em.rule_turns(ts)
        ids += [t["id"] for t in ts if t["id"] not in rule]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if a.kind == "look":
            cmd_look(argparse.Namespace(ids=ids, raw=False))
        else:
            cmd_events(argparse.Namespace(ids=ids, count=False))
    body = buf.getvalue()
    with open(OUT / a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(gd.COMMON + (gd.LOOK if a.kind == "look" else gd.EVENTS) + "# 차례들\n\n" + body)
    print(f"{a.out}: 차례 {len(ids)} {ids} · 본문 {len(body):,}자 · 시작 줄을 못 잡은 차례 {body.count('시작 줄을 못 잡음')}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("score")
    c.add_argument("name")
    m = sp.add_parser("compare")
    m.add_argument("names", nargs="+")
    m.add_argument("--truth", default="")
    b = sp.add_parser("blind")
    b.add_argument("games", nargs="+")
    b.add_argument("--out", required=True)
    b.add_argument("--kind", default="look", choices=["look", "events"])
    d = sp.add_parser("detect")
    d.add_argument("games", nargs="+")
    d.add_argument("--ids", default="")
    d.add_argument("--step", type=int, default=2)
    k = sp.add_parser("look")
    k.add_argument("ids", nargs="+")
    k.add_argument("--raw", action="store_true")
    e = sp.add_parser("events")
    e.add_argument("ids", nargs="+")
    e.add_argument("--count", action="store_true")
    a = ap.parse_args()
    {"detect": cmd_detect, "look": cmd_look, "score": cmd_score, "events": cmd_events, "compare": cmd_compare, "blind": cmd_blind}[a.cmd](a)


if __name__ == "__main__":
    main()
