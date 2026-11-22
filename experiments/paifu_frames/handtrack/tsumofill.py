"""남의 쯔모기리 B4 — 예시 패보(11-14 2반장 9판)의 hero 아닌 세 자리 버림에 tsumogiri 를 채운 사본(2026-11-22, 설계서 paifu_fill_scores_tsumogiri_design_1122.md "B4 명세").
LLM 호출 없음. assets/paifu/ · 기존 config · 정답 · B0 · B1 결과는 읽기만 — 새 산출물은 results/handtrack/_work/tsumo_b4_1122/.

  python -X utf8 tsumofill.py plan                 # 자리 번호 ↔ 쪽 대응(코드로 확인) · 기록기 강 ↔ 패보 버림 맞붙이기 · 새 자리 목록
  python -X utf8 tsumofill.py cfg                  # 새 자리 config(handtrack/config/x_<판>_<쪽>.json, 없을 때만 — tsumokind.cmd_cfg 그대로, 위쪽은 occ_rows face 자동)
  python -X utf8 tsumofill.py detect <판…>         # 그 판의 새 자리 + hero 자리 검출 · 가림 → tsumo_b4_1122/raw4_<판>.json · det/det_<자리>.json
  python -X utf8 tsumofill.py fill                 # 값 정하기 → filled/<판>.json · <판>.fill.json · summary.md · selfcheck.json(확인 ① ②)
  (확인 ③ ④ 는 experiments/paifu_frames/tsumofill_check.dart)

값을 정하는 순서(명세 1 → 4, 자리 · 버림마다):
  1 rule       패보 기준: 그 자리가 리치를 선언한 뒤의 버림 = 참, 그 자리 울기(call 사건) 바로 뒤 버림 = 거짓
  2 truth_b1   시험 자리 여섯(_work/tsumo_b1_1122_key/truth_b1.json, 뺀 3개는 unknown) · truth_hero = r16 판 왼쪽(assets/paifu/L16_135321.json 의 hero 값 = L16 정답)
  3 code_T / code_H   M1: tsumokind.judge == '쯔모기리 확정' → 참 · '읽어야 함' 이고 run2_fs_s 시작이 −4 ~ 0초인 것이 있으면 거짓
  4 unknown    그 밖(읽어야 함 · 시작 줄 없음 · 녹화 전 · 친의 첫 버림 · 맞붙이기 어긋남)
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import slotgrid as sg  # noqa: E402
import tsumokind as tk  # noqa: E402

ROOT = hc.ROOT
ASSETS = ROOT / "assets" / "paifu"
OUT4 = hc.WORK / "tsumo_b4_1122"
DET4 = OUT4 / "det"
KEYD = hc.WORK / "tsumo_b1_1122_key"
GAMES = ["r11_130921", "r12_131655", "r13_132644", "r14_133610", "r15_134151", "r16_135321", "r17_140450", "r18_141259", "r19_142013"]
ORDER = ["bottom", "right", "top", "left"]          # 위에서 본 차례 순(반시계) — 자리 번호가 1 늘면 다음 쪽
BAND_SRC = {"bottom": "r12_131655", "right": "r16_135321", "top": "n05_151953", "left": "r18_141259"}   # B0 와 같은 깊이 띠 출처
TEST = {v[0] + ":" + v[1]: k for k, v in tk.SEATS.items()}                                              # "판:쪽" → 시험 자리 이름
HERO_TRUTH_SEAT = {"r16_135321:left": "L16_135321"}


def seat_name(gid: str, side: str) -> str:
    hero_side = hc.config(gid)["side"]
    if side == hero_side:
        return gid
    key = f"{gid}:{side}"
    return TEST.get(key) or HERO_TRUTH_SEAT.get(key) or f"x_{gid[:3]}_{side}"


def register(gid: str, side: str):
    """새 자리를 tsumokind.SEATS 에 이 프로세스 안에서만 넣는다(tsumokind.py 파일의 SEATS 는 안 바꿈 — tsumopack 이 시험 자리로 읽으므로)."""
    nm = seat_name(gid, side)
    if nm.startswith("x_") and nm not in tk.SEATS:
        tk.SEATS[nm] = (gid, side, BAND_SRC[side])
    return nm


def side_of(p: dict, seat: int, gid: str) -> str:
    return ORDER[(ORDER.index(hc.config(gid)["side"]) + seat - p["hero"]) % 4]


def load_paifu(gid: str) -> dict:
    return json.loads((ASSETS / f"{gid}.json").read_text(encoding="utf-8"))


def overlay_by_side(gid: str) -> dict:
    ov, _ = tk.overlay_paths(gid, "new")
    d = json.load(open(ov, encoding="utf-8"))
    return {sd: [s["tile"] for s in sorted(v["slots"], key=lambda s: (s["first_at"], s["i"]))] for sd, v in d.items()}


def seat_discards(p: dict) -> dict:
    out = defaultdict(list)
    for i, e in enumerate(p["events"]):
        if e["type"] == "discard":
            out[e["seat"]].append(i)
    return out


def turns_of_seat(gid: str, side: str) -> list:
    nm = register(gid, side)
    if nm in tk.SEATS and (tk.OUTD / f"turns_{nm}.json").exists() and nm in TEST.values():
        return hc.jload(tk.OUTD / f"turns_{nm}.json")["turns"]          # 시험 자리는 B0 · B1 때 저장한 차례 그대로
    if nm == gid or nm.startswith("L16"):
        return tk.seat_turns_named(tk.real_game(gid), side, "new")
    return tk.seat_turns(nm, "new")


# ------------------------------------------------------------------ plan
def cmd_plan(a):
    L = ["== 자리 번호 ↔ 쪽: hero 쪽 = config side, 나머지는 자리 번호 차이로 ORDER(아래 → 오른 → 위 → 왼) 를 돎",
         "   확인: 네 회전 중 이 대응일 때 패보 자리별 버림 패 순서와 기록기 쪽별 강 순서가 가장 많이 맞는가(SequenceMatcher 일치 장수)"]
    for gid in GAMES:
        p = load_paifu(gid)
        ov = overlay_by_side(gid)
        sd = seat_discards(p)
        tiles = {s: [p["events"][i]["tile"] for i in sd[s]] for s in range(4)}
        score = {}
        for rot in range(4):
            m = 0
            for s in range(4):
                side = ORDER[(ORDER.index(hc.config(gid)["side"]) + s - p["hero"] + rot) % 4]
                m += sum(b.size for b in difflib.SequenceMatcher(None, tiles[s], ov.get(side, []), autojunk=False).get_matching_blocks())
            score[rot] = m
        best = max(score, key=score.get)
        L.append(f"{gid}: hero {p['hero']}({hc.config(gid)['side']}) dealer {p['dealer']} · 회전별 일치 {score} → {'OK(회전 0)' if best == 0 else '!! 회전 ' + str(best)}"
                 + " · " + " · ".join(f"{s}={side_of(p, s, gid)}:{seat_name(gid, side_of(p, s, gid))}" for s in range(4)))
    txt = "\n".join(L) + "\n"
    tk.save_lf(OUT4 / "plan.txt", txt)
    print(txt)


def cmd_cfg(a):
    names = []
    for gid in GAMES:
        p = load_paifu(gid)
        for s in range(4):
            side = side_of(p, s, gid)
            nm = register(gid, side)
            if nm.startswith("x_") and not (hc.CONFIG / f"{nm}.json").exists():
                names.append(nm)
    print("새 config", len(names), names)
    if names:
        tk.cmd_cfg(argparse.Namespace(names=names, n=60, force=False))


# ------------------------------------------------------------------ detect
def code_seats(gid: str) -> list:
    """M1 을 계산할 자리 = hero(확인 ②) + 새 자리(시험 자리 · r16 왼쪽은 정답이 있어 뺌)."""
    p = load_paifu(gid)
    out = []
    for s in range(4):
        side = side_of(p, s, gid)
        nm = register(gid, side)
        if nm in TEST.values() or nm.startswith("L16"):
            continue
        out.append((nm, side))
    return out


def cmd_detect(a):
    import bisect
    import dettrack as dt
    L = None
    for gid in a.games:
        t_all = time.time()
        seats = code_seats(gid)
        rows = {nm: tk.SeatRow(nm) for nm, _ in seats}
        f = OUT4 / f"raw4_{gid}.json"
        if f.exists():
            raw = hc.jload(f)
        else:
            b0 = tk.OUTD / f"raw_{gid}.json"
            raw = {k: {"b": v["b"], "o": {}} for k, v in hc.jload(b0).items()} if b0.exists() else {}   # B0 의 전체 뒷면 상자만 가져옴(가림은 자리마다 새로)
        want = set()
        for nm, side in seats:
            for t in turns_of_seat(gid, side):
                if t.get("pre_record") or t.get("riichi_after") or t.get("call"):
                    continue
                want |= set(hc.frame_range(*sg.window(t))[::2])
        known = sorted(int(k) for k in raw)
        todo = []
        for ms in sorted(want):
            i = bisect.bisect_left(known, ms - 150)
            if i >= len(known) or known[i] > ms + 150:
                todo.append(ms)
        print(gid, "자리", [nm for nm, _ in seats], "· 필요 프레임", len(want), "· 새로 검출", len(todo), "· 이미", len(raw), flush=True)
        t0 = time.time()
        if todo:
            L = L or dt.reader()
            L._sessions()
            for i, ms in enumerate(todo):
                _, backs, _, _ = L._seat_raw(hc.load(ms))
                raw[str(ms)] = {"b": [[round(float(x), 1), round(float(y), 1), round(float(w), 1), round(float(h), 1)] for (x, y, w, h), _rc in backs], "o": {}}
                if i % 500 == 0:
                    print(gid, "검출", i, len(todo), f"{time.time() - t0:.0f}s", flush=True)
        t_det = time.time() - t0
        # 가림: 자리마다 그 자리 창 안 프레임만
        need = defaultdict(set)
        for nm, side in seats:
            ws = [sg.window(t) for t in turns_of_seat(gid, side) if not (t.get("pre_record") or t.get("riichi_after") or t.get("call"))]
            for k in raw:
                ms = int(k)
                if nm not in raw[k]["o"] and any(w0 <= ms <= w1 for w0, w1 in ws):
                    need[k].add(nm)
        t1 = time.time()

        def one(k):
            rgb = hc.load(int(k))
            return k, {nm: tk.occ_of(rows[nm], hc.band_crop(rgb, rows[nm].cfg["sheet_band"], rows[nm].cfg["side"])) for nm in need[k]}

        with ThreadPoolExecutor(a.workers) as ex:
            for k, o in ex.map(one, sorted(need)):
                raw[k]["o"].update(o)
        hc.jsave(f, raw, indent=None)
        DET4.mkdir(parents=True, exist_ok=True)
        for nm, _ in seats:
            cfg = hc.config(nm)
            det = {k: {"b": tk.view_boxes(v["b"], cfg), "o": v["o"][nm]} for k, v in raw.items() if nm in v["o"]}
            hc.jsave(DET4 / f"det_{nm}.json", det, indent=None)
        print(gid, f"끝 · 검출 {len(todo)}장 {t_det:.0f}s · 가림 {len(need)}장 {time.time() - t1:.0f}s · 합 {time.time() - t_all:.0f}s", flush=True)


# ------------------------------------------------------------------ fill
def m1_of(t: dict, det: dict | None) -> tuple:
    """(값, 출처, 까닭) — 규칙 차례는 여기 안 옴."""
    if t.get("pre_record"):
        return None, "unknown", "녹화 전(기록기 추적 시작 전 버림)"
    j, sig = tk.judge(t, det, False, False)
    if j == "쯔모기리 확정":
        return True, "code_T", f"V1 = 0(시작 줄 {sig['anchor']})"
    if j == "읽어야 함":
        ex = tk.extra_signals(t, det) or {}
        hit = [s for s, _ in ex.get("run2_fs_s") or [] if -4 <= s <= 0]
        if hit:
            return False, "code_H", f"처음 본 때 {hit[0]:+.1f}초에 시작한 2프레임 빈 칸(V1 {sig['V1']})"
        return None, "unknown", f"읽어야 함(V1 {sig['V1']}, [−4, 0]초 빈 칸 없음)"
    return None, "unknown", j


def load_det4(nm: str):
    f = DET4 / f"det_{nm}.json"
    if f.exists():
        return {int(k): v for k, v in hc.jload(f).items()}
    return tk.load_det(nm, prefer_saved=False)           # 시험 자리 = B0 · B1 때의 det(바꾸지 않음)


def cmd_fill(a):
    truth_b1 = {x["turn"]: x["kind"] for x in hc.jload(KEYD / "truth_b1.json")["items"]}
    L16 = load_paifu("L16_135321")
    rows_all, mism, sc2 = [], [], []
    (OUT4 / "filled").mkdir(parents=True, exist_ok=True)
    for gid in GAMES:
        p = load_paifu(gid)
        q = copy.deepcopy(p)
        ov = overlay_by_side(gid)
        sd = seat_discards(p)
        fill_rows = []
        for s in range(4):
            side = side_of(p, s, gid)
            nm = register(gid, side)
            idx = sd[s]
            ts = turns_of_seat(gid, side)
            ptiles = [p["events"][i]["tile"] for i in idx]
            otiles = [t["tile"] for t in ts]
            # 맞붙이기: N번째 ↔ N번째, 처음 어긋난 곳부터 그 자리 끝까지 안 채움
            bad_from = next((k for k in range(min(len(ptiles), len(otiles))) if ptiles[k] != otiles[k]), None)
            if bad_from is None and len(ptiles) != len(otiles):
                bad_from = min(len(ptiles), len(otiles))
            if bad_from is not None:
                mism.append({"game": gid, "seat": s, "side": side, "name": nm, "hero": s == p["hero"], "from_n": bad_from + 1,
                             "paifu": ptiles[bad_from] if bad_from < len(ptiles) else None, "recorder": otiles[bad_from] if bad_from < len(otiles) else None,
                             "count_paifu": len(ptiles), "count_recorder": len(otiles), "ov_side_count": len(ov.get(side, [])),
                             # 참고(안 씀): 순서 맞춤(difflib)으로 이었다면 같은 패로 짝지어지는 버림 수
                             "aligned_if_difflib": sum(b.size for b in difflib.SequenceMatcher(None, ptiles, otiles, autojunk=False).get_matching_blocks())})
            det = None if (nm in TEST.values() or nm.startswith("L16")) else load_det4(nm)
            l16_idx = seat_discards(L16)[s] if nm.startswith("L16") else None
            riichi, last_call = False, False
            for n, ei in enumerate(idx):
                e = p["events"][ei]
                prev = next((p["events"][j] for j in range(ei - 1, -1, -1) if p["events"][j]["seat"] == s), None)
                after_call = prev is not None and prev["type"] == "call"
                t = ts[n] if n < len(ts) else None
                row = {"game": gid, "seat": s, "side": side, "name": nm, "n": n + 1, "tile": e["tile"], "orig": e.get("tsumogiri"), "hero": s == p["hero"]}
                if riichi:
                    v, src, why = True, "rule", "그 자리 리치 선언 뒤"
                elif after_call:
                    v, src, why = False, "rule", "울기 바로 뒤 버림"
                elif bad_from is not None and n >= bad_from:
                    v, src, why = None, "unknown", f"맞붙이기 어긋남({bad_from + 1}번째부터)"
                elif s == p["dealer"] and n == 0:
                    v, src, why = None, "unknown", "친의 첫 버림(뽑은 패 없음 — 정의 밖)"
                elif nm.startswith("L16"):
                    lv = L16["events"][l16_idx[n]].get("tsumogiri") if l16_idx and n < len(l16_idx) and L16["events"][l16_idx[n]]["tile"] == e["tile"] else None
                    v, src, why = (lv, "truth_hero", "L16 hero 정답") if lv is not None else (None, "unknown", "L16 정답 없음(녹화 전 등)")
                elif nm in TEST.values():
                    k = truth_b1.get(t["id"]) if t else None
                    v, src, why = ({"tsumogiri": True, "hand": False}[k], "truth_b1", "B1 시험 정답") if k else (None, "unknown", "B1 정답에서 뺌(녹화 전 · 친 첫 버림)")
                else:
                    v, src, why = m1_of(t, det) if t else (None, "unknown", "차례 없음")
                row.update(value=v, source=src, why=why, turn=t["id"] if t else None)
                # 확인용: 시험 자리 · hero 의 M1(값을 덮어쓰기 전)
                if t and (nm in TEST.values() or s == p["hero"]) and src not in ("rule",) and not (bad_from is not None and n >= bad_from) and not (s == p["dealer"] and n == 0):
                    d_ = load_det4(nm) if nm in TEST.values() else det
                    row["m1"] = m1_of(t, d_)[:2]
                if e.get("riichi"):
                    riichi = True
                if s == p["hero"]:
                    # 패보의 hero 값 중 guess(녹화 전 순을 짐작으로 채운 것)는 정답이 아니라 뺌
                    if row.get("m1") and e.get("tsumogiri") is not None and row["m1"][0] is not None and not e.get("guess"):
                        sc2.append({"game": gid, "n": n + 1, "tile": e["tile"], "paifu": e["tsumogiri"], "m1": row["m1"][0], "src": row["m1"][1], "ok": row["m1"][0] == e["tsumogiri"]})
                    fill_rows.append({**row, "value": e.get("tsumogiri"), "source": "hero(안 바꿈)"})
                    continue
                if v is not None and src != "unknown" and e.get("tsumogiri") is None:
                    q["events"][ei]["tsumogiri"] = v
                elif e.get("tsumogiri") is not None and v is not None and e["tsumogiri"] != v:
                    row["conflict"] = f"패보 원래 값 {e['tsumogiri']} 와 다름 — 원래 값 그대로 둠"
                fill_rows.append(row)
        (OUT4 / "filled" / f"{gid}.json").write_bytes((json.dumps(q, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        hc.jsave(OUT4 / "filled" / f"{gid}.fill.json", fill_rows)
        rows_all += fill_rows
        print(gid, "끝", flush=True)
    summary(rows_all, mism, sc2)


def summary(rows, mism, sc2):
    L = ["# B4 채우기 요약 (tsumofill.py fill)", ""]
    nh = [r for r in rows if not r["hero"]]
    srcs = ["rule", "truth_b1", "truth_hero", "code_T", "code_H", "unknown"]
    L.append("| 판 | 자리(쪽 · 이름) | 버림 | " + " | ".join(srcs) + " | 채움 |")
    L.append("|" + "---|" * (len(srcs) + 4))
    tot = Counter()
    for (g, s), grp in sorted(((k, list(v)) for k, v in _group(nh, lambda r: (r["game"], r["seat"])).items())):
        c = Counter(r["source"] for r in grp)
        tot += c
        filled = sum(c[x] for x in srcs[:-1])
        L.append(f"| {g[:3]} | {s} {grp[0]['side']} {grp[0]['name']} | {len(grp)} | " + " | ".join(str(c[x]) for x in srcs) + f" | {filled}/{len(grp)} |")
    n = sum(tot.values())
    L.append(f"| **합** | 27 자리 | **{n}** | " + " | ".join(f"**{tot[x]}**" for x in srcs) + f" | **{n - tot['unknown']}/{n} = {(n - tot['unknown']) / max(1, n):.0%}** |")
    L.append("")
    uk = Counter(r["why"].split("(")[0] for r in nh if r["source"] == "unknown")
    L.append("unknown 내역: " + " · ".join(f"{k} {v}" for k, v in uk.most_common()))
    conf = [r for r in nh if r.get("conflict")]
    L.append(f"원래 값과 다른 값(원래 값 그대로 둠): {len(conf)}" + (" — " + ", ".join(f"{r['game'][:3]} 자리 {r['seat']} {r['n']}번째" for r in conf) if conf else ""))
    L += ["", "## 맞붙이기 어긋남(기록기 새 기본값 강 N번째 ↔ 패보 그 자리 N번째 버림)", ""]
    for m in mism:
        L.append(f"- {m['game']} 자리 {m['seat']}({m['side']}{' · hero' if m['hero'] else ''}): {m['from_n']}번째부터 — 기록기 {m['recorder']} / 패보 {m['paifu']} · 장수 기록기 {m['count_recorder']} / 패보 {m['count_paifu']}"
                 f" · (참고: 순서 맞춤으로 이었다면 같은 패 짝 {m['aligned_if_difflib']} — 명세대로 쓰지 않음)")
    if not mism:
        L.append("- 없음")
    # 확인 ①
    t1 = [r for r in nh if r["name"] in TEST.values() and r.get("m1") and r["source"] == "truth_b1"]
    c1 = Counter(r["m1"][1] for r in t1)
    L += ["", "## 확인 ① 시험 자리 여섯 — 정답을 덮어쓰기 전 M1(정답 있는 71)", "",
          f"- 답함 {c1['code_T'] + c1['code_H']}(쯔모기리 {c1['code_T']} · 손에서 {c1['code_H']}) · 모름 {c1['unknown']} · 합 {len(t1)}",
          f"- M1 이 정답과 다른 것: {sum(1 for r in t1 if r['m1'][0] is not None and r['m1'][0] != r['value'])}"]
    b3 = hc.jload(KEYD / "b3_score.json")["M1"]["전체"]
    L.append(f"- b3_score.json M1 전체: 답함 {b3['답함']}(쯔모기리 {b3['답_tsumogiri']} · 손에서 {b3['답_hand']}) · 모름 {b3['모름']} → {'같음' if (c1['code_T'], c1['code_H'], c1['unknown']) == (b3['답_tsumogiri'], b3['답_hand'], b3['모름']) else '**다름**'}")
    # 확인 ②
    bad = [x for x in sc2 if not x["ok"]]
    L += ["", "## 확인 ② hero 자리에 같은 길(기록기 강 차례 → M1) — 패보에 이미 있는 hero 값과 맞댐(개발 자료)", "",
          f"- M1 이 값을 낸 hero 버림 {len(sc2)}(쯔모기리 {sum(x['m1'] for x in sc2)} · 손에서 {sum(not x['m1'] for x in sc2)}) · **틀리게 정한 것 {len(bad)}**"]
    for x in bad:
        L.append(f"  - {x['game']} {x['n']}번째 {x['tile']}: 패보 {x['paifu']} · M1 {x['m1']}({x['src']})")
    hc.jsave(OUT4 / "selfcheck.json", {"check1": {"m1": dict(c1), "b3": b3}, "check2": sc2, "mismatch": mism})
    tk.save_lf(OUT4 / "summary.md", "\n".join(L) + "\n")
    print("\n".join(L))


def _group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g


# ------------------------------------------------------------------ 남은 차례 읽기 꾸러미 · 합치기(11-22 밤, 사용자 "27차례 읽기")
RPACK = OUT4 / "read_pack"
RKEY = OUT4 / "read_pack_key"
B1 = hc.WORK / "tsumo_b1_1122"
RSEED = 20261126
READABLE = ("읽어야 함", "불가:시작 줄 없음")


def paifu_n(p: dict, seat: int, ei: int) -> int:
    """패보에서 그 버림 앞까지 그 자리 울기 수로 센 줄 장수."""
    calls = sum(1 for e in p["events"][:ei] if e["type"] == "call" and e["seat"] == seat)
    return 13 - 3 * calls


def brief_of(item: dict) -> dict:
    """B1 의 brief.json 과 같은 칸(tsumo_b1_1122/items/<id>/brief.json 꼴)."""
    return {"id": item["id"], "n": item["n"], "discarded_tile": item["discarded_tile"], "range_s": item["range_s"],
            "n_sheets": item["n_sheets"], "n_frames": item["n_frames"],
            "sheets": [{"file": s["file"], "from_s": s["rows_s"][0], "to_s": s["rows_s"][-1], "rows": len(s["rows_s"])} for s in item["sheets"]],
            "frames_note": "frames/t_<부호><초 세 자리>.<소수 둘>.jpg — 초당 약 10장. 있는 시각은 폴더 목록으로 본다(예: frames/t_-003.39.jpg)."}


def cmd_read_pack(a):
    import random
    import shutil
    import tsumopack as tp
    targets = []
    for gid in GAMES:
        p = load_paifu(gid)
        sd = seat_discards(p)
        for r in hc.jload(OUT4 / "filled" / f"{gid}.fill.json"):
            if r["hero"] or r["source"] != "unknown" or not r["why"].startswith(READABLE):
                continue
            t = next(x for x in turns_of_seat(gid, r["side"]) if x["id"] == r["turn"])
            ei = sd[r["seat"]][r["n"] - 1]
            pn = paifu_n(p, r["seat"], ei)
            no_anchor = r["why"].startswith("불가:시작 줄 없음")
            targets.append({"src": "target", "game": gid, "seat": r["seat"], "side": r["side"], "cfg": r["name"], "nth": r["n"], "event_index": ei,
                            "turn": t["id"], "n": pn if no_anchor else t["n_calc"], "n_recorder": t["n_calc"], "n_paifu": pn, "tile": r["tile"],
                            "w0": sg.window(t)[0], "t0": t["first_seen_ms"], "why_unknown": r["why"]})
    # 확인용 4: hero 86 중 B1 꾸러미에 안 들어간 것 — 읽어야 함인데 정답 쯔모기리 2 + 손에서 냄 2(쪽이 다르게)
    used = {x["turn"] for x in hc.jload(B1.parent / "tsumo_b1_1122_key" / "key_private.json")["items"] if x["src"] == "known"}
    pool = tp.hero_pool()
    rnd = random.Random(RSEED)
    known = []

    def add(r, cat):
        ref, m = tp.hero_seat_turn(r["game"], r["id"])
        if m is None or m["pre_record"]:
            return False
        known.append({"src": "known", "cat": cat, "truth": r["truth"], "game": tk.real_game(r["game"]), "hero_turn": r["id"], "seat_turn": m["id"],
                      "cfg": r["game"], "side": hc.config(r["game"])["side"], "n": ref["n_calc"], "tile": m["tile"], "w0": sg.window(m)[0], "t0": m["first_seen_ms"]})
        return True

    tr = [r for r in pool["T_read"] if r["id"] not in used]
    rnd.shuffle(tr)
    got = 0
    for r in tr:
        if got < 2 and add(r, "T_read"):
            got += 1
    hs = [r for k in ("H_right", "H_bottom", "H_left") for r in pool[k] if r["id"] not in used]
    rnd.shuffle(hs)
    sides = set()
    for r in hs:
        if len(sides) == 2:
            break
        if r["side"] not in sides and add(r, f"H_{r['side']}"):
            sides.add(r["side"])
    if len(known) != 4:
        raise SystemExit(f"확인용 {len(known)}/4")
    allit = targets + known
    order = list(range(len(allit)))
    rnd.shuffle(order)
    for k, i in enumerate(order):
        allit[i]["id"] = f"q{k + 1:03d}"
    if RPACK.exists() and a.force:
        shutil.rmtree(RPACK)
    RPACK.mkdir(parents=True, exist_ok=True)
    tp.PACK = RPACK                                           # 같은 코드 경로(tsumopack.build_item)로 그림 · item.json
    from concurrent.futures import ThreadPoolExecutor as TPE
    with TPE(a.workers) as ex:
        res = list(ex.map(tp.build_item, sorted(allit, key=lambda x: x["id"])))
    for it in allit:
        item = json.loads((RPACK / "items" / it["id"] / "item.json").read_text(encoding="utf-8"))
        (RPACK / "items" / it["id"] / "brief.json").write_bytes((json.dumps(brief_of(item), ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    for nm in ("READER.md", "READER_TASK.md"):
        shutil.copyfile(B1 / nm, RPACK / nm)                  # 확정본 그대로(글 안 고침)
    (RPACK / "answers" / "R").mkdir(parents=True, exist_ok=True)
    hc.jsave(RPACK / "index.json", {"items": res})
    # 몫: 8 · 8 · 8 · 7, 몫마다 확인용 1
    kn = [x["id"] for x in known]
    tg = [x["id"] for x in targets]
    rnd.shuffle(kn)
    rnd.shuffle(tg)
    sizes = [8, 8, 8, 7] if len(allit) == 31 else None
    if sizes is None:
        C = 4
        base = len(allit) // C
        sizes = [base + (1 if i < len(allit) % C else 0) for i in range(C)]
    batches, q = [], 0
    for i, sz in enumerate(sizes):
        ids = [kn[i]] + tg[q:q + sz - 1]
        q += sz - 1
        rnd.shuffle(ids)
        batches.append({"batch": f"R{i + 1}", "ids": ids})
    RKEY.mkdir(parents=True, exist_ok=True)
    hc.jsave(RKEY / "batches_R_private.json", batches)
    hc.jsave(RKEY / "key_private.json", {"note": "B4 남은 차례 읽기 꾸러미 열쇠 — 읽는 쪽에게 주지 않음. src = target(채울 차례) | known(정답 아는 hero 확인용). "
                                                 "event_index = 패보(assets/paifu/<판>.json) events 의 위치, nth = 그 자리 몇 번째 버림. n = 줄 장수(시작 줄 없음은 패보 울기 수로 셈)",
                                         "seed": RSEED, "items": sorted(allit, key=lambda x: x["id"])})
    nd = [x for x in targets if x["n_recorder"] != x["n_paifu"]]
    print(f"대상 {len(targets)}(읽어야 함 {sum(x['why_unknown'].startswith('읽어야 함') for x in targets)} · 시작 줄 없음 {sum(x['why_unknown'].startswith('불가') for x in targets)}) · 확인용 {len(known)}"
          f" · n 기록기 ≠ 패보 {[(x['id'], x['n_recorder'], x['n_paifu']) for x in nd]}")
    for b in batches:
        print(b["batch"], " ".join(b["ids"]))
    ns, nf = [r["n_sheets"] for r in res], [r["n_frames"] for r in res]
    print(f"표 수 중앙 {sorted(ns)[len(ns) // 2]} · 최대 {max(ns)} · 낱장 중앙 {sorted(nf)[len(nf) // 2]} · 최대 {max(nf)}")
    tp.PACK = RPACK
    tp.cmd_check(argparse.Namespace())


READER_EXTRA = """# 덧붙임 — 버린 시각을 모르는 항목 (brief.json 에 "special": "timing_unknown" 이 있는 것)

이 항목은 `READER.md` 와 정의 · 답 꼴이 같다. 다른 점은 하나다: **그림의 시각 기준(R0)이 버린 순간이 아니다.**
R0 은 "이 버림이 이미 강에 놓여 있던 것이 확인된 때" 일 뿐이고, 실제로 버린 것은 그보다 앞 — 범위 안 어딘가다.

할 일:
1. `brief.json` 의 `find_nth` 를 본다. 1 이면 이 사람의 **이 국 첫 번째 버림**, 2 면 **두 번째 버림**을 판정한다.
2. 표를 처음부터 본다. 범위 앞쪽에는 앞 국의 끝(패를 무너뜨리고 섞는 장면)과 배패(패를 받아 세우는 장면)가 들어 있을 수 있다. **패를 받아 한 줄로 세운 뒤**부터 센다.
3. 줄을 세운 뒤 이 사람이 처음으로 패산에서 한 장을 뽑아 오고(줄이 n → n+1 장, 또는 손에 쥠) 한 장을 강으로 내는 동작이 첫 번째 버림이다. 그 다음 뽑고 버리는 동작이 두 번째 버림이다.
4. 찾은 그 버림에 대해 `READER.md` 의 기준대로 쯔모기리 / 손에서 냄을 가린다. `evidence` · `why` 의 시각은 R0 기준 초로 적고, `why` 첫머리에 "N번째 버림을 R0 −○○초 무렵으로 봄" 을 적는다.
5. 범위 안에 배패가 없거나(이미 대국이 진행 중인 장면부터 시작) N번째가 어느 것인지 가릴 수 없으면 `unsure` 로 하고 까닭을 적는다. 짐작으로 고르지 않는다.
"""
PRE_BACK_MS, PRE_POST_MS, PRE_ROW_MS = 120000, 5000, 500


def build_extra(it: dict) -> dict:
    """기록기 추적 전 버림 — 범위 R0 − 120초 ~ R0 + 5초, 표는 0.5초마다, 낱장은 전부(tsumopack.view · fname 와 같은 자르기 · 배율 · 이름)."""
    import numpy as np
    from PIL import Image, ImageDraw
    import tsumopack as tp
    cfg = hc.config(it["cfg"])
    d = RPACK / "items" / it["id"]
    (d / "frames").mkdir(parents=True, exist_ok=True)
    r0 = it["t0"]
    frames = hc.frame_range(r0 - PRE_BACK_MS, r0 + PRE_POST_MS)
    fa = np.array(frames)
    want = list(range(frames[0], r0 + PRE_POST_MS + 1, PRE_ROW_MS))
    pick = []
    for w in want:
        m = int(fa[int(np.argmin(np.abs(fa - w)))])
        if not pick or pick[-1] != m:
            pick.append(m)
    keep = set(pick)
    names, seen, imgs, fsize = [], set(), {}, None
    for ms in frames:
        nm = tp.fname(ms - r0)
        if nm in seen:
            nm = nm[:-4] + "b.jpg"
        seen.add(nm)
        im = tp.view(ms, cfg, tp.SCALE)
        im.save(d / "frames" / nm, quality=90)
        fsize = list(im.size)
        names.append((ms, nm))
        if ms in keep:
            imgs[ms] = im.resize((int(im.width * tp.SHEET_SCALE / tp.SCALE), int(im.height * tp.SHEET_SCALE / tp.SCALE)), Image.LANCZOS)
    k = -(-len(pick) // tp.SHEET_ROWS)
    per = -(-len(pick) // k)
    sheets, f_lab = [], tp.font(22)
    r0_row = next((m for m in pick if m >= r0), None)
    for s in range(k):
        part = pick[s * per:(s + 1) * per]
        rows = [imgs[m] for m in part]
        LW, GAP = 130, 6
        W, H = LW + max(r.width for r in rows), sum(r.height + GAP for r in rows)
        sh = Image.new("RGB", (W, H), (25, 25, 25))
        dr = ImageDraw.Draw(sh)
        y = 0
        for m, r in zip(part, rows):
            sh.paste(r, (LW, y))
            dt = round((m - r0) / 1000, 1) + 0.0
            if m == r0_row:
                dr.text((8, y + 8), "R0 >>", fill=(150, 150, 150), font=f_lab)
                dr.text((8, y + 40), f"{dt:+.1f}s", fill=(230, 230, 230), font=f_lab)
            else:
                dr.text((8, y + 12), f"{dt:+.1f}s", fill=(230, 230, 230), font=f_lab)
            y += r.height + GAP
        nm = f"sheet_{s + 1:02d}.jpg"
        sh.save(d / nm, quality=90)
        sheets.append({"file": nm, "rows_s": [round((m - r0) / 1000, 2) for m in part], "size": [W, H]})
    info = {"id": it["id"], "n": it["n"], "discarded_tile": it["tile"], "range_s": [round((frames[0] - r0) / 1000, 2), round((frames[-1] - r0) / 1000, 2)],
            "find_nth": it["nth"], "special": "timing_unknown",
            "t0_note": "R0 = 이 버림이 이미 강에 놓여 있던 것이 확인된 때(버린 순간이 아님 — READER_EXTRA.md)",
            "n_frames": len(names), "n_sheets": len(sheets), "sheets": sheets,
            "frames": [{"t_s": round((m - r0) / 1000, 2), "file": f"frames/{nm}"} for m, nm in names],
            "image_note": f"대국자 시점(줄이 가로 · 아래가 그 사람 쪽 · 왼쪽이 그 사람 왼손 쪽). 낱장 {tp.SCALE:g}배 · 표 {tp.SHEET_SCALE:g}배"}
    (d / "item.json").write_bytes((json.dumps(info, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    b = brief_of(info)
    b = {**{k: b[k] for k in ("id", "n", "discarded_tile", "range_s")}, "find_nth": it["nth"], "special": "timing_unknown",
         **{k: b[k] for k in ("n_sheets", "n_frames", "sheets", "frames_note")}}
    (d / "brief.json").write_bytes((json.dumps(b, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return {"id": it["id"], "n_sheets": len(sheets), "n_frames": len(names), "sheet_size": sheets[0]["size"], "frame_size": fsize}


def cmd_read_pack_extra(a):
    """기록기 추적 전 버림(녹화 전 + B1 에서 녹화 전이라 뺀 것, 친의 첫 버림 제외)을 다섯 번째 몫으로."""
    import random
    import tsumopack as tp
    key = hc.jload(RKEY / "key_private.json")
    have = {x.get("turn") for x in key["items"] if x["src"] == "target_pre"}
    pre = []
    for gid in GAMES:
        p = load_paifu(gid)
        sd = seat_discards(p)
        for r in hc.jload(OUT4 / "filled" / f"{gid}.fill.json"):
            if r["hero"] or r["source"] != "unknown":
                continue
            if not (r["why"].startswith("녹화 전") or r["why"].startswith("B1 정답에서 뺌")):
                continue
            t = next(x for x in turns_of_seat(gid, r["side"]) if x["id"] == r["turn"])
            if not t.get("pre_record") or r["turn"] in have:
                continue
            ei = sd[r["seat"]][r["n"] - 1]
            pre.append({"src": "target_pre", "game": gid, "seat": r["seat"], "side": r["side"], "cfg": r["name"], "nth": r["n"], "event_index": ei,
                        "turn": t["id"], "n": paifu_n(p, r["seat"], ei), "tile": r["tile"], "t0": t["first_seen_ms"], "why_unknown": r["why"]})
    if not pre:
        print("더할 것 없음(이미 있음)")
        return
    nums = [int(x["id"][1:]) for x in key["items"]]
    rnd = random.Random(RSEED + 1)
    rnd.shuffle(pre)
    for k, it in enumerate(pre):
        it["id"] = f"q{max(nums) + 1 + k:03d}"
    from concurrent.futures import ThreadPoolExecutor as TPE
    with TPE(min(5, len(pre))) as ex:
        res = list(ex.map(build_extra, pre))
    (RPACK / "READER_EXTRA.md").write_bytes(READER_EXTRA.encode("utf-8"))
    idx = hc.jload(RPACK / "index.json")
    idx["items"] += res
    hc.jsave(RPACK / "index.json", idx)
    key["items"] += pre
    key["note"] += " · src = target_pre(기록기 추적 전 버림 — t0 = R0, 범위 R0 − 120초 ~ R0 + 5초, nth = find_nth)"
    hc.jsave(RKEY / "key_private.json", key)
    bt = hc.jload(RKEY / "batches_R_private.json")
    ids = [x["id"] for x in pre]
    rnd.shuffle(ids)
    bt.append({"batch": f"R{len(bt) + 1}", "ids": ids, "note": "기록기 추적 전 버림(READER_EXTRA.md)"})
    hc.jsave(RKEY / "batches_R_private.json", bt)
    for it, r in zip(pre, res):
        print(it["id"], it["game"][:3], it["side"], "find_nth", it["nth"], "n", it["n"], "표", r["n_sheets"], "낱장", r["n_frames"], "표 크기", r["sheet_size"])
    print(bt[-1]["batch"], " ".join(bt[-1]["ids"]))
    tp.PACK = RPACK
    tp.cmd_check(argparse.Namespace())


def cmd_merge_read(a):
    import subprocess
    key = {x["id"]: x for x in hc.jload(RKEY / "key_private.json")["items"]}
    ans = {}
    for f in sorted((RPACK / "answers" / "R").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            ans[d.get("id", f.stem)] = d
        except Exception as e:  # noqa: BLE001
            print("답 파일 읽기 실패", f.name, e)
    OUTR = OUT4 / "filled_read"
    OUTR.mkdir(parents=True, exist_ok=True)
    L = ["# B4 + 남은 차례 읽기 합치기 (tsumofill.py merge-read)", "",
         "받는 규칙(읽기 전에 정함): kind 가 tsumogiri / hand 이고 confidence 가 high · mid → 값(출처 read, 추적 전 버림은 read_pre). low · unsure → 모름 그대로(까닭에 읽기 답).", ""]
    # 확인용
    L += ["## 확인용(정답 아는 hero) — 합치지 않음", "", "| id | 정답 | 답 | 확신 | 맞음 |", "|---|---|---|---|---|"]
    for i, it in sorted(key.items()):
        if it["src"] != "known":
            continue
        d = ans.get(i)
        k = d.get("kind") if d else "(답 없음)"
        L.append(f"| {i} | {it['truth']} | {k} | {d.get('confidence') if d else '-'} | {'✓' if d and k == it['truth'] else ('?' if not d or k == 'unsure' else '✗')} |")
    by_game = defaultdict(dict)
    for i, it in key.items():
        if it["src"] in ("target", "target_pre"):
            by_game[it["game"]][it["event_index"]] = (i, it)
    rows_all = []
    missing = []
    for gid in GAMES:
        p = json.loads((OUT4 / "filled" / f"{gid}.json").read_text(encoding="utf-8"))
        rows = hc.jload(OUT4 / "filled" / f"{gid}.fill.json")
        sd = seat_discards(p)
        for r in rows:
            if r["hero"]:
                continue
            ei = sd[r["seat"]][r["n"] - 1]
            if ei not in by_game[gid]:
                continue
            i, it = by_game[gid][ei]
            d = ans.get(i)
            r["read_id"] = i
            if d is None:
                missing.append(i)
                r["why"] += " · 읽기 답 없음"
                continue
            k, c = d.get("kind"), d.get("confidence")
            if k in ("tsumogiri", "hand") and c in ("high", "mid"):
                v = k == "tsumogiri"
                r.update(value=v, source="read_pre" if it["src"] == "target_pre" else "read", why=f"읽기 {i}: {k} · {c} — {d.get('why', '')}")
                if p["events"][ei].get("tsumogiri") is None:
                    p["events"][ei]["tsumogiri"] = v
            else:
                r["why"] += f" · 읽기 {i}: {k} · {c}(받지 않음) — {d.get('why', '')}"
        (OUTR / f"{gid}.json").write_bytes((json.dumps(p, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        hc.jsave(OUTR / f"{gid}.fill.json", rows)
        rows_all += [r for r in rows if not r["hero"]]
    L += ["", "## 판 · 자리별", "", "| 판 | 자리 | 읽기 대상 | read 로 채움 | 여전히 모름(그중 읽기 대상) | 채움 |", "|---|---|---|---|---|---|"]
    for (g, s), grp in sorted(_group(rows_all, lambda r: (r["game"], r["seat"])).items()):
        tgt = [r for r in grp if r.get("read_id")]
        rd = sum(r["source"] in ("read", "read_pre") for r in grp)
        uk = [r for r in grp if r["source"] == "unknown"]
        L.append(f"| {g[:3]} | {s} {grp[0]['side']} | {len(tgt)} | {rd} | {len(uk)}({sum(1 for r in uk if r.get('read_id'))}) | {len(grp) - len(uk)}/{len(grp)} |")
    n = len(rows_all)
    uk = sum(r["source"] == "unknown" for r in rows_all)
    c = Counter(r["source"] for r in rows_all)
    L += ["", f"출처 합: " + " · ".join(f"{k} {v}" for k, v in c.most_common()), f"**채움 {n - uk}/{n} = {(n - uk) / max(1, n):.0%}**(합치기 전 B4 = filled/ 기준 301/359)",
          f"읽기 답 없는 대상: {missing or '없음'}"]
    # check() · 채운 효과(합친 사본)
    out = OUT4 / "check_dart_read.json"
    cmd = [r"C:\Users\jjh7757\flutter\bin\dart.bat", "run", "experiments/paifu_frames/tsumofill_check.dart", "--filled",
           str(OUTR.relative_to(ROOT)).replace("\\", "/")] + GAMES
    with open(out, "w", encoding="utf-8") as fo:
        rc = subprocess.run(cmd, cwd=ROOT, stdout=fo, shell=False).returncode
    if rc == 0:
        d = json.loads(out.read_text(encoding="utf-8"))
        L += ["", "## check() · 채운 효과(합친 사본 대 원본, B4 확인 ④ 와 같은 표)", "",
              "| 판 | check 원본 → 사본 | 수비 차례 | 단계 바뀐 패 | 가장 안전한 패 바뀐 차례 | 버린 패 단계 바뀐 차례 | 위험 숫자 바뀐 차례 |", "|---|---|---|---|---|---|---|"]
        for g in GAMES:
            v = d[g]
            L.append(f"| {g[:3]} | {len(v['check_before'])} → {len(v['check_after'])}{' 더해짐 ' + str(v['check_added']) if v['check_added'] else ''} | {v['defense_turns']} | "
                     f"{v['tiles_level_changed']}/{v['tiles']} | {v['safest_changed_turns']} | {v['actual_level_changed_turns']} | {v['risk_number_changed_turns']} |")
        t = d["total"]
        L.append(f"| **합** | | {t['turns']} | {t['tiles_changed']}/{t['tiles']} | {t['safest_changed']} | {t['actual_changed']} | {t['risk_changed_turns']} |")
    else:
        L.append(f"\n!! tsumofill_check.dart 실패(종료 코드 {rc}) — {out} 참고. lib 를 다른 작업이 고치는 중이면 몇 분 뒤 다시: python -X utf8 tsumofill.py merge-read")
    tk.save_lf(OUT4 / "read_summary.md", "\n".join(L) + "\n")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("plan")
    sp.add_parser("cfg")
    d = sp.add_parser("detect")
    d.add_argument("games", nargs="+")
    d.add_argument("--workers", type=int, default=4)
    sp.add_parser("fill")
    rp = sp.add_parser("read-pack")
    rp.add_argument("--workers", type=int, default=6)
    rp.add_argument("--force", action="store_true", help="read_pack 을 지우고 새로(answers 도 지워짐 — 답이 들어오기 전에만)")
    sp.add_parser("merge-read")
    sp.add_parser("read-pack-extra")
    a = ap.parse_args()
    {"plan": cmd_plan, "cfg": cmd_cfg, "detect": cmd_detect, "fill": cmd_fill, "read-pack": cmd_read_pack, "merge-read": cmd_merge_read,
     "read-pack-extra": cmd_read_pack_extra}[a.cmd](a)


if __name__ == "__main__":
    main()
