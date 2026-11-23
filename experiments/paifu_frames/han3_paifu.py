"""3반장(2026-11-14 14:31 ~ 15:45, p01 ~ p03 · n01 ~ n08) 패보 조립(2026-11-23).

앱 기록이 없는 반장이라 헤드 폰 녹화에서 복구한 재료를 앱 패보 형식(lib/paifu/paifu.dart, version 1)으로 묶는다.
  python -X utf8 experiments/paifu_frames/han3_paifu.py [판 id …] [--hands] [--dump]      (저장소 루트에서, --dump = 판별 매 순 시작 줄)
판을 안 주면 rounds_meta.json 의 열한 판 모두. 결과 = results/han3_1123/_prep/paifu/<판 id>.json (+ _check.json · _scores.json).

- 버림 · 울기 = 고친 기록기 결과 `_prep/rec/<판>/paifu_rec.json`(handtrack/han3.py recfix — recorder_fix.json 적용)
  + 조립 때 고침 EVENT_FIX(근거와 함께). 그 밖에 기록기와 눈 읽기(result_read.json)가 갈리는 리치 · 울기는 고치지 않고 목록으로만 낸다.
- 머리 = `rounds_meta.json`(국 · 본장 · 선 · 손패 주인), 이름 "플레이어 1 ~ 4", 표시패 · 결과 = `result_read.json`.
- 손패(--hands) = handtrack/han3.py 패치 + paifu_examples.add_hands_truth(rebuild_opus "full" — `_work/rawread_han3_1123` 의 Opus 답, 리치 뒤 규칙,
  울기 차례는 turn_fix) + fill_pre_record(t_ready 앞 순은 짐작). 읽을 차례의 answer.json 이 하나라도 없으면 그 판은 손패 없이 쓰고 없는 차례를 찍는다.
  끝 손패 기준 = result_read.json(HAN3_FINAL=result).
- 국 시작 점수 · 공탁 = 25,000점 · 공탁 0 에서 판 순서대로 굴린 계산값: 화료 점수 이동은 han3_check.dart(scoreOf) 의 지불액,
  리치 선언 −1,000(공탁에 쌓임, 화료자가 가져감), 유국은 노텐 벌점 3,000(텐파이 = result_read tenpai_revealed). 점봉 이동은 영상에서 읽지 않았다.
- 검사 = han3_check.dart(Paifu.check · 걸음 수 · 점수) + 손패 주인 손패 장수.
"""
import copy
import re
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "handtrack"))
import han3  # noqa: E402
import htcommon as hc  # noqa: E402

SIDES = han3.SIDES
OUT = han3.PREP / "paifu"
DART = "C:/Users/jjh7757/flutter/bin/dart.bat"
CHECK = "experiments/paifu_frames/han3_check.dart"
START = 25000

# 조립 때 고치는 사건(기록기 결과에 근거 있는 것만). side = 사진 기준 자리.
EVENT_FIX = {
    "n04_151410": [{"op": "unriichi", "side": "bottom", "tile": "5p",
                    "why": "아래 자리 7번째(론 당한 5p)에 기록기가 찍은 가로(리치) — 눈 읽기에 n04 리치 없음 · 리치봉 없음, 론 패가 비스듬히 놓인 것으로 봄(11-23 조정자)"}],
    "n03_150528": [{"op": "recall", "side": "bottom", "from_side": "left", "old_kind": "call", "old_tiles": ["6p"], "kind": "chi", "tiles": ["6p", "4p", "0p"],
                    "why": "기록기는 아래 자리가 왼쪽 강의 6p 를 가져간 것만 보고 종류를 모름('call' · 한 장). 눈 읽기(result_read melds) = 아래 자리 치 4p 0p 6p(왼쪽에서). "
                           "묶음 순서는 기록기 꼴(받은 패를 준 자리 쪽 칸 — 왼쪽 자리면 첫 칸, 나머지는 작은 패부터)(11-23 3d 조정자)"}],
    "n01_144748": [{"op": "kakan", "side": "top", "tile": "7z", "before_discard_at": "14:51:39",
                    "why": "눈 읽기 = 위 자리 7z 퐁 뒤 가깡(14:51:32 에 깡도라 4z 가 뒤집힘 — 표시패 7m · 4z). 기록기는 퐁만 적음. "
                           "가깡 사건(kind kakan)을 위 자리의 그 무렵 버림(8p, 기록기 첫 봄 14:51:39) 바로 앞에 끼움(11-23 3d 조정자)"}],
}


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=1))


def norm(t):
    return ("5" + t[1]) if t and t[0] == "0" else t


def seat_of(side, bottom):
    return (bottom + SIDES.index(side)) % 4


def apply_event_fix(gid, events, bottom):
    log = []
    for o in EVENT_FIX.get(gid, []):
        s = seat_of(o["side"], bottom)
        if o["op"] == "unriichi":
            idx = [n for n, e in enumerate(events) if e["type"] == "discard" and e["seat"] == s and e.get("riichi")]
            if len(idx) != 1 or events[idx[0]]["tile"] != o["tile"]:
                raise SystemExit(f"{gid}: unriichi 대상이 예상과 다름 — {[events[n] for n in idx]}")
            events[idx[0]] = {**events[idx[0]], "riichi": False}
            log.append(f"{o['side']} {o['tile']} 리치 표시 지움")
        elif o["op"] == "recall":
            f = seat_of(o["from_side"], bottom)
            idx = [n for n, e in enumerate(events) if e["type"] == "call" and e["seat"] == s and e.get("from") == f
                   and e.get("kind") == o["old_kind"] and list(e.get("tiles") or []) == o["old_tiles"]]
            if len(idx) != 1:
                raise SystemExit(f"{gid}: recall 대상이 예상과 다름 — {idx}")
            events[idx[0]] = {**events[idx[0]], "kind": o["kind"], "tiles": list(o["tiles"])}
            log.append(f"{o['side']} 울기 {o['old_kind']} {o['old_tiles']} → {o['kind']} {o['tiles']}(눈 읽기)")
        elif o["op"] == "kakan":
            ms = hc.to_ms(o["before_discard_at"])
            idx = [n for n, e in enumerate(events) if e["type"] == "discard" and e["seat"] == s and e.get("at") is not None and abs(e["at"] - ms) < 1000]
            pon = [e for e in events if e["type"] == "call" and e["seat"] == s and e.get("kind") == "pon" and norm(e["tiles"][0]) == o["tile"]]
            if len(idx) != 1 or len(pon) != 1:
                raise SystemExit(f"{gid}: 가깡 자리를 못 정함 — 버림 {idx} · 퐁 {len(pon)}")
            # from = 자기 자리: Paifu._build 는 from 이 남의 자리면 그 강 끝 패를 '울려 나감' 으로 바꾸므로(가깡은 강에서 가져오지 않음)
            events.insert(idx[0], {"type": "call", "seat": s, "kind": "kakan", "from": s, "tiles": [o["tile"]] * 4})
            log.append(f"{o['side']} {o['tile']} 가깡 끼움({o['before_discard_at']} 버림 앞, 눈 읽기)")
    return log


def riichi_of_events(events):
    """자리별 리치 선언 버림의 '남은 강' 번호(울려 나간 버림은 세지 않음 — result_read river_index 와 같은 셈)."""
    out = {}
    for s in range(4):
        k = 0
        for n, e in enumerate(events):
            if e["type"] != "discard" or e["seat"] != s:
                continue
            nxt = events[n + 1] if n + 1 < len(events) else None
            called = nxt is not None and nxt["type"] == "call" and nxt.get("from") == s
            if not called:
                k += 1
            if e.get("riichi"):
                out[s] = k if not called else f"{k + 1}(울려 나감)"
    return out


def compare(gid, events, rr, bottom):
    """기록기 사건 ↔ 눈 읽기(result_read) — 갈리는 리치 · 울기."""
    diffs = []
    rec_r = riichi_of_events(events)
    rr_r = {seat_of(x["side"], bottom): x["river_index"] for x in rr.get("riichi") or []}
    for s in sorted(set(rec_r) | set(rr_r)):
        if rec_r.get(s) != rr_r.get(s):
            diffs.append(f"리치 자리 {s}({SIDES[(s - bottom) % 4]}): 기록기 {rec_r.get(s)} · 눈 읽기 {rr_r.get(s)}")
    rec_c = {s: [] for s in range(4)}
    for e in events:
        if e["type"] == "call":
            if e.get("kind") == "kakan":   # 가깡은 앞서 한 퐁을 바꾼다 — 퐁을 지우고 가깡(준 자리 = 퐁의 준 자리)으로
                t = norm(e["tiles"][0])
                pon = next(x for x in rec_c[e["seat"]] if x[0] == "pon" and x[1][0] == t)
                rec_c[e["seat"]].remove(pon)
                rec_c[e["seat"]].append(("kakan", tuple(sorted(norm(x) for x in e["tiles"])), pon[2]))
                continue
            rec_c[e["seat"]].append((e.get("kind"), tuple(sorted(norm(t) for t in e.get("tiles") or [])), e.get("from")))
    rr_c = {s: [] for s in range(4)}
    for side, ms in (rr.get("melds") or {}).items():
        for m in ms or []:
            fs = m.get("from_side")
            rr_c[seat_of(side, bottom)].append((m.get("kind"), tuple(sorted(norm(t) for t in m.get("tiles") or [])),
                                                seat_of(fs, bottom) if fs else None))
    for s in range(4):
        a, b = Counter(rec_c[s]), Counter(rr_c[s])
        if a != b:
            diffs.append(f"울기 자리 {s}({SIDES[(s - bottom) % 4]}): 기록기 {sorted(a.elements())} · 눈 읽기 {sorted(b.elements())}")
    return diffs


def result_of(rr, bottom):
    if rr["end"] != "win":
        return {"type": "draw"}
    w = seat_of(rr["winner_side"], bottom)
    riichi = any(x["side"] == rr["winner_side"] for x in rr.get("riichi") or [])
    melds = [{"kind": m["kind"], "tiles": list(m["tiles"])} for m in (rr.get("melds") or {}).get(rr["winner_side"]) or []]
    return {"type": rr["win_type"], "winner": w, "loser": seat_of(rr["loser_side"], bottom) if rr.get("loser_side") else None,
            "win_tile": rr["win_tile"], "hand": list(rr["hand"]), "melds": melds, "flags": {"riichi": riichi}}


def answers_missing(gid):
    root = hc.WORK / han3.READ_ROOT
    return [t for t in han3.read_ids(gid) if not (root / t / "answer.json").exists()]


def build(gid, meta, want_hands):
    bottom = meta["bottom_seat"]
    rec = jl(han3.PREP / "rec" / gid / "paifu_rec.json")
    rr = jl(han3.H3DIR / gid / "result_read.json")
    events = copy.deepcopy(rec["events"])
    fixes = [re.sub(r" — 사건 \[.*$", "", x) for x in jl(han3.PREP / "rec" / gid / "recfix_check.json")["ops"]]   # note 에는 사건 사본을 빼고
    fixes += apply_event_fix(gid, events, bottom)
    diffs = compare(gid, events, rr, bottom)
    if rec["dealer"] != meta["dealer"]:
        raise SystemExit(f"{gid}: 기록기 선 {rec['dealer']} ≠ rounds_meta {meta['dealer']}")
    hero = meta["hero"]
    res = result_of(rr, bottom)
    if res["type"] == "draw":
        if [seat_of(s, bottom) for s in rr.get("tenpai_revealed") or []] != [hero]:
            raise SystemExit(f"{gid}: 유국 텐파이 공개 {rr.get('tenpai_revealed')} 가 손패 주인 {hero} 와 다름")
    elif res["winner"] != hero:
        raise SystemExit(f"{gid}: 화료자 {res['winner']} ≠ 손패 주인 {hero}")
    final_row = list(rr["hand"])
    g = hc.jload(hc.OUT / gid / "game.json")["final_hand"]["closed"]
    if g != final_row:
        raise SystemExit(f"{gid}: 끝 손패 game.json {g} ≠ result_read {final_row} — 멈춤")
    tsumo_tile = res.get("win_tile") if res["type"] == "tsumo" else None
    hands, missing, n_fill, hero_calls, call_log = False, [], 0, 0, {}
    if want_hands:
        missing = answers_missing(gid)
    if want_hands and not missing:
        import paifu_examples as px
        px.HAND_FROM_OPUS[gid] = han3.READ_ROOT
        han3.CALL_LOG.clear()
        events, unknown = px.add_hands_truth(gid, events, hero, gid, final_row, tsumo_tile)
        call_log = {k: dict(v) for k, v in han3.CALL_LOG.items()}
        events, n_fill = px.fill_pre_record(gid, events, hero)
        hands = True
        hero_calls = sum(1 for e in events if e["type"] == "call" and e["seat"] == hero)
    elif tsumo_tile:
        events.append({"type": "draw", "seat": hero, "tile": tsumo_tile, "hand": None})
    fx = "; ".join(fixes) if fixes else "고친 칸 없음"
    hand_txt = ("내 손패는 Opus 가 영상에서 읽은 칸(정답 없음, 리치 뒤는 규칙)으로 끝 손패에서 거꾸로 복원" if hands
                else "내 손패는 아직 없음(영상 읽기 전)")
    note = ("앱 기록이 없어 헤드 폰 녹화 프레임으로 복구: 버림은 앱 버림 기록기를 녹화 프레임(2배 키움)에 돌리고 근거 있는 칸만 고침"
            f"({fx}), {hand_txt}, 결과 · 표시패는 Opus 가 프레임에서 읽고 끝 손패는 기계 판독과 같음을 확인.")
    if res["type"] == "draw":
        note = "유국(텐파이 공개 — 손패 주인은 혼자 텐파이를 공개한 사람). " + note
    if hands and n_fill:
        import paifu_examples as px
        note += px.PRE_NOTE
    if hands and hero_calls:
        guess = [k for k, v in call_log.items() if v["how"] != "answer"]
        chi = [k for k, v in call_log.items() if v["how"] == "answer" and "짐작" in v["note"]]
        if guess:
            note += f" 울기 {hero_calls}번 — 울기 차례 {len(guess)}개는 울기 전 손패 줄 순서를 정렬로 짐작(울기 차례의 손패 묶음은 확실하나, 그 앞 순들의 뽑은 패 · 손패 묶음은 이 짐작에 기대므로 틀릴 수 있음)."
        else:
            note += f" 울기 {hero_calls}번 — 울기 차례도 Opus 가 울기로 나간 칸 · 버린 칸을 읽어 복원" + (" (치의 두 장이 어느 칸이었는지는 정렬로 짐작)." if chi else ".")
    note += " 국 시작 점수 · 공탁은 25,000점에서 앞 판들의 점수 계산으로 굴린 계산값(점봉 이동은 영상에서 읽지 않음)."
    out = {
        "version": 1, "id": gid,
        "title": f"2026-11-14 3반장 {meta['round']}" + (f" {meta['honba']}본장" if meta["honba"] else ""),
        "round": meta["round"], "honba": meta["honba"], "dealer": meta["dealer"], "hero": hero,
        "names": ["플레이어 1", "플레이어 2", "플레이어 3", "플레이어 4"],
        "dora_indicators": list(rr.get("dora_indicators") or []), "ura_indicators": list(rr.get("ura_indicators") or []),
        "note": note, "source": "recorder+opus_hand" if hands else "recorder",
        "events": events, "result": res,
    }
    info = {"hands": hands, "missing_answers": missing, "fixes": fixes, "diffs": diffs, "n_fill": n_fill,
            "riichi_seats": sorted({e["seat"] for e in events if e["type"] == "discard" and e.get("riichi")}),
            "tenpai": [seat_of(s, bottom) for s in rr.get("tenpai_revealed") or []], "call_log": call_log}
    if hands:
        bad = []
        for n, e in enumerate(events):
            if e["seat"] == hero and e.get("hand") is not None:
                # 울기 사건의 손패 = 울고 나서 버리기 전(L16 예시와 같은 꼴: 13 − 3 × 울기 수 + 1). 11-23 3d 전에는 +1 을 빼먹어 "11장(≠10)" 헛 경고
                want = 13 - 3 * sum(1 for x in events[:n + 1] if x["type"] == "call" and x["seat"] == hero) + (1 if e["type"] == "call" else 0)
                if len(e["hand"]) != want:
                    bad.append(f"{e['type']} {e.get('tile')} 손패 {len(e['hand'])}장(≠{want})")
        info["hand_count_problems"] = bad
    return out, info


def dump(gid, p):
    """판별 손패 주인의 매 순 시작 줄(뽑기 전 줄 · 울기 뒤 줄)과 그 순 사건 — 울기 차례 답을 넣기 전 · 뒤 견주기용(--dump)."""
    hero, k = p["hero"], 0
    print(f"\n== {gid} 손패 주인 자리 {hero} 매 순 시작 줄")
    ev = p["events"]
    for n, e in enumerate(ev):
        if e["seat"] != hero:
            continue
        g = " (짐작)" if e.get("guess") else ""
        h = " ".join(e["hand"]) if e.get("hand") else "모름"
        if e["type"] == "draw":
            k += 1
            nxt = next((x for x in ev[n + 1:] if x["seat"] == hero and x["type"] == "discard"), None)
            print(f"  {k:2d}순 시작 [{h}] + 뽑음 {e.get('tile')}" + (f" → 버림 {nxt['tile']}{' 쯔모기리' if nxt.get('tsumogiri') else ''}{' 리치' if nxt.get('riichi') else ''}" if nxt else "") + g)
        elif e["type"] == "call":
            k += 1
            nxt = next((x for x in ev[n + 1:] if x["seat"] == hero and x["type"] == "discard"), None)
            print(f"  {k:2d}순 울기 {e.get('kind')} {e.get('tiles')} 뒤 [{h}]" + (f" → 버림 {nxt['tile']}" if nxt else "") + g)
        elif e["type"] == "discard" and (n == 0 or ev[n - 1]["seat"] != hero):
            k += 1
            print(f"  {k:2d}순 (뽑기 없음) 버림 {e['tile']} 뒤 [{h}]{g}")


def dart_check(paths):
    env = dict(os.environ, PATH="C:/Users/jjh7757/flutter/bin;" + os.environ["PATH"])
    p = subprocess.run([DART, "run", CHECK, *[str(x) for x in paths]], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(f"han3_check.dart 실패\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    s = p.stdout
    return json.loads(s[s.index("{"):])


def roll(order, chk, infos):
    """국 시작 점수 · 공탁을 판 순서대로 굴린다."""
    sc, pot, rows = [START] * 4, 0, {}
    for gid, meta in order:
        c, inf = chk[gid], infos[gid]
        rows[gid] = {"start_scores": list(sc), "kyotaku": pot, "meta_kyotaku": meta["kyotaku"]}
        for s in inf["riichi_seats"]:
            sc[s] -= 1000
            pot += 1
        if "delta" in c:
            for s in range(4):
                sc[s] += c["delta"][s]
            sc[meta["hero"]] += pot * 1000          # 손패 주인 = 화료자(build 에서 확인)
            pot = 0
        elif meta["end"] == "draw":
            t = inf["tenpai"]
            if 0 < len(t) < 4:
                for s in range(4):
                    sc[s] += (3000 // len(t)) if s in t else -(3000 // (4 - len(t)))
        else:
            raise SystemExit(f"{gid}: 점수 이동을 못 정함 — {c}")
        rows[gid]["end_scores"] = list(sc)
        rows[gid]["pot_after"] = pot
    return rows


def main():
    a = sys.argv[1:]
    want_hands = "--hands" in a
    if want_hands:
        os.environ["HAN3_FINAL"] = "result"
    han3.patch()
    meta_all = jl(han3.META)
    order = [(r["id"], han3.meta_of(r["id"])) for r in meta_all["rounds"]]
    pick = [x for x in a if not x.startswith("--")] or [g for g, _ in order]
    built, infos = {}, {}
    for gid, meta in order:          # 점수를 굴리려고 열한 판 모두 만든다(고른 판만 손패를 붙임)
        out, info = build(gid, meta, want_hands and gid in pick)
        built[gid], infos[gid] = out, info
        wj(OUT / f"{gid}.json", out)
    chk = dart_check([OUT / f"{g}.json" for g, _ in order])
    rows = roll(order, chk, infos)
    for gid, _ in order:
        built[gid]["start_scores"] = rows[gid]["start_scores"]
        built[gid]["kyotaku"] = rows[gid]["kyotaku"]
        wj(OUT / f"{gid}.json", built[gid])
    chk = dart_check([OUT / f"{g}.json" for g, _ in order])
    wj(OUT / "_check.json", chk)
    wj(OUT / "_scores.json", rows)
    wj(OUT / "_info.json", infos)
    print("판 | 사건 · 걸음 | 손패 | check | 결과 · 점수 | 국 시작 점수 · 공탁(meta 공탁)")
    for gid, meta in order:
        c, inf, r = chk[gid], infos[gid], rows[gid]
        sc = c.get("score") or {}
        res = built[gid]["result"]
        what = (f"{res['type']} {sc.get('summary')} [{', '.join(sc.get('yaku') or [])}] {sc.get('payment')} Δ{c.get('delta')}" if res["type"] != "draw"
                else f"유국 텐파이 {inf['tenpai']}")
        print(f"{gid} {built[gid]['title']} | {c['events']} · {c['steps']} | {'O' if inf['hands'] else ('없음 ' + str(len(inf['missing_answers'])) if inf['missing_answers'] else 'X')} | "
              f"{c['check'] or '통과'} | {what} | {r['start_scores']} · {r['kyotaku']}({r['meta_kyotaku']})")
        if inf.get("hand_count_problems"):
            print("   손패 장수:", inf["hand_count_problems"])
        for k, v in inf.get("call_log", {}).items():
            print(f"   {k}: {'울기 줄 짐작' if v['how'] != 'answer' else '울기 답'} — {v['note']}")
        if want_hands and inf["missing_answers"] and gid in pick:
            print("   answer.json 없는 차례:", ",".join(inf["missing_answers"]))
    print("끝 점수", rows[order[-1][0]]["end_scores"], "· 공탁", rows[order[-1][0]]["pot_after"])
    if "--dump" in a:
        for gid, _ in order:
            if gid in pick:
                dump(gid, built[gid])
    print("\n기록기 ↔ 눈 읽기가 갈리는 사건(고치지 않음):")
    for gid, _ in order:
        for d in infos[gid]["diffs"]:
            print(f"  {gid}: {d}")


if __name__ == "__main__":
    main()
