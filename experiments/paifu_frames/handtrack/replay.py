"""6단계: 판정 파일을 받아 번호 줄을 굴리고, 버림(강)·끝 손패·울기로 번호에 패 종류를 붙여 매 순 손패와 복원된 시작 손패를 낸다.

  python -X utf8 replay.py <판정 파일.json> [--game <판 id>] [--out <결과 폴더>]
판 id 는 판정 파일의 "game" 칸(없으면 --game). 읽는 것: results/handtrack/<판>/game.json · index.json.
결과: <결과 폴더 = results/handtrack/<판>>/replay_<판정 파일 이름>.json · .txt

판정 파일 형식(README 에 같은 설명):
{"game": "r18_141259", "start_tiles": 13,
 "judgments": [{"seg": 3, "kind": "tedashi", "out_pos": 5, "in_pos": 9, "moves": [[2, 7]], "conf": "high", "note": "..."}, ...]}
kind:
  none       변화 없음
  tsumogiri  뽑아서 그대로 버림(out_pos·in_pos null)
  tedashi    뽑고 손에서 냄. out_pos = 뽑기 전 n장 줄에서 나간 칸(대국자 왼쪽부터 1~n), in_pos = 버린 뒤 n장 줄에서 뽑은 패가 자리 잡은 칸
  draw       뽑아서 줄에 두기만 함(버림은 다음 구간). in_pos = n+1장 줄에서 뽑은 패의 칸(오른쪽 끝에 떼어 두었으면 n+1)
  discard    앞 구간 draw 뒤의 버림. out_pos = n+1장 줄에서 나간 칸(뽑은 패를 버리면 쯔모기리로 센다)
  call       남의 버림을 울기. meld_pos = 울기 전 줄에서 울기로 나간 칸들, out_pos = 울기 패를 뺀 줄에서 버린 칸(같은 구간에서 버렸으면)
  rearrange  옮기기만(moves)
  reveal     화료 공개(쯔모면 뽑은 패 = 화료패). 없으면 마지막에 자동으로 적용
  unclear    모름 → 여기서 끊음. 선택 칸 "discards"(이 구간의 버림 수, 없으면 index 강 변화 수), "calls"(울기 수, 기본 0)
moves = [[옮기기 전 칸, 옮긴 뒤 칸], …] — 주 동작이 끝난 줄에서 차례로 적용. 판정 없는 구간은 none 으로 보고 경고.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

KINDS = {"none", "tsumogiri", "tedashi", "draw", "discard", "call", "rearrange", "reveal", "unclear"}


def norm(t):
    return {"0m": "5m", "0p": "5p", "0s": "5s"}.get(t, t) if t else t


# ------------------------------------------------------------------ 정렬 방식
def sort_scheme(closed: list[str]) -> dict:
    """끝 손패(자리 순서)에서 무늬 묶음 순서와 숫자 방향을 읽는다."""
    suits, nums = [], {}
    for t in closed:
        t = norm(t)
        s = t[1]
        if not suits or suits[-1] != s:
            suits.append(s)
        nums.setdefault(s, []).append(int(t[0]))
    contiguous = len(suits) == len(set(suits))
    up = down = 0
    for s, v in nums.items():
        for a, b in zip(v, v[1:]):
            up += b > a
            down += b < a
    order = []
    for s in suits:
        if s not in order:
            order.append(s)
    return {"suit_order": order, "suits_contiguous": contiguous, "ascending": up >= down, "pairs_up": up, "pairs_down": down}


def key(t: str | None, sch: dict):
    if t is None or t == "?":
        return None
    t = norm(t)
    if t[1] not in sch["suit_order"]:
        return None
    n = int(t[0])
    return (sch["suit_order"].index(t[1]), n if sch["ascending"] else -n)


def fits(new: str, left: str | None, right: str | None, sch: dict) -> bool | None:
    k = key(new, sch)
    if k is None:
        return None
    kl, kr = key(left, sch) if left else None, key(right, sch) if right else None
    if (left and kl is None) or (right and kr is None):
        return None
    return (kl is None or kl <= k) and (kr is None or k <= kr)


# ------------------------------------------------------------------ 굴리기
class Chunk:
    def __init__(self, name: str, ids: list):
        self.name, self.start_ids = name, list(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("judgment")
    ap.add_argument("--game")
    ap.add_argument("--out")
    a = ap.parse_args()
    jp = Path(a.judgment)
    J = hc.jload(jp)
    gid = J.get("game") or a.game
    od = hc.OUT / gid
    game = hc.jload(od / "game.json")
    index = hc.jload(od / "index.json")
    segs = {s["seg"]: s for s in index["segments"]}
    jud = {}
    for j in J["judgments"]:
        assert j["kind"] in KINDS, j
        jud[j["seg"]] = j
    errors, warns = [], []

    final = game["final_hand"]
    closed_final = final["closed"]
    win_tile = final.get("win_tile")
    tsumo = str(game.get("result") or "").startswith("tsumo")
    sch = sort_scheme(closed_final)

    # 강 순서(화료자 버림, 시간순): 판 구간 안의 river_new 를 구간 순서·강 순서로 이어 붙임
    river_seq = []  # (seg, tile, sideways)
    for s in index["segments"]:
        rv = s.get("river") or {}
        for t in rv.get("river_new") or []:
            river_seq.append({"seg": s["seg"], "tile": t["tile"], "sideways": t.get("sideways", False), "row": t.get("row"), "col": t.get("col")})
    meld_seq = []
    for s in index["segments"]:
        rv = s.get("river") or {}
        for t in rv.get("meld_new") or []:
            meld_seq.append({"seg": s["seg"], "tile": t})

    n0 = J.get("start_tiles", 13)
    chunk_names = "ABCDEFGHIJ"
    chunks = [Chunk("A", list(range(1, n0 + 1)))]
    row = list(range(1, n0 + 1))
    next_id = [n0 + 1]
    ci = 0

    def new_id():
        if ci == 0:
            v = next_id[0]
        else:
            v = f"{chunk_names[ci]}{next_id[0]}"
        next_id[0] += 1
        return v

    calls = 0
    pending = None  # draw 뒤 버리기 전, 뽑은 패 번호
    riichi_after = False
    types: dict = {}  # 번호 → 종류
    discards = []  # {seg, id, tsumogiri, river_k, after_call, riichi}
    events = []
    river_k = 0
    last_was_call = False
    reveal_done = False
    breaks = []

    def n_now():
        return n0 - 3 * calls

    def take_river(seg_no: int, cnt: int = 1) -> list[dict]:
        nonlocal river_k
        out = []
        for _ in range(cnt):
            if river_k >= len(river_seq):
                errors.append(f"구간 {seg_no}: 버림이 강 기록({len(river_seq)}장)보다 많음")
                out.append({"seg": None, "tile": None, "sideways": False})
                continue
            r = river_seq[river_k]
            if r["seg"] != seg_no:
                warns.append(f"구간 {seg_no}: {river_k + 1}번째 버림을 강 기록에서는 구간 {r['seg']} 에서 봄({r['tile']})")
            out.append(r)
            river_k += 1
        return out

    def apply_moves(j, seg_no) -> list:
        done = []
        for fr, to in j.get("moves") or []:
            if not (1 <= fr <= len(row)) or not (1 <= to <= len(row)):
                errors.append(f"구간 {seg_no}: moves {fr}->{to} 칸이 줄({len(row)}장) 밖")
                continue
            x = row.pop(fr - 1)
            row.insert(to - 1, x)
            done.append({"from": fr, "to": to, "id": x})
        return done

    def do_discard(seg_no, did, tsumogiri, j):
        nonlocal riichi_after, last_was_call
        r = take_river(seg_no)[0]
        if did in [d["id"] for d in discards]:
            errors.append(f"구간 {seg_no}: 번호 {did} 가 두 번 나감")
        if r["tile"] is not None:
            if did in types and types[did] != r["tile"]:
                errors.append(f"구간 {seg_no}: 번호 {did} 종류 충돌 {types[did]} vs 강 {r['tile']}")
            types[did] = r["tile"]
        d = {"seg": seg_no, "id": did, "tile": r["tile"], "tsumogiri": tsumogiri, "after_call": last_was_call, "riichi_tile": r["sideways"],
             "after_riichi": riichi_after, "conf": j.get("conf")}
        if riichi_after and not tsumogiri:
            errors.append(f"구간 {seg_no}: 리치 뒤 버림인데 손에서 냄(번호 {did})")
        if last_was_call and tsumogiri:
            errors.append(f"구간 {seg_no}: 울기 직후 버림이 쯔모기리로 판정됨")
        if r["sideways"]:
            riichi_after = True
        last_was_call = False
        discards.append(d)
        return d

    order = sorted(set(segs) | set(jud))
    for seg_no in order:
        if seg_no not in segs:
            errors.append(f"판정의 구간 {seg_no} 가 index 에 없음")
            continue
        j = jud.get(seg_no)
        if j is None:
            warns.append(f"구간 {seg_no}: 판정 없음 → none")
            j = {"seg": seg_no, "kind": "none"}
        k = j["kind"]
        ev = {"seg": seg_no, "kind": k, "conf": j.get("conf"), "note": j.get("note")}
        n = n_now()
        if k in ("tsumogiri", "tedashi", "draw") and (len(row) != n or pending is not None):
            errors.append(f"구간 {seg_no} {k}: 뽑기 전 줄이 {len(row)}장(기대 {n}){' · 앞 draw 를 아직 안 버림' if pending is not None else ''}")
        if k == "tsumogiri":
            did = new_id()
            ev.update(drawn=did, out=did)
            ev["discard"] = do_discard(seg_no, did, True, j)
        elif k == "tedashi":
            op, ip = j.get("out_pos"), j.get("in_pos")
            did = new_id()
            if not (op and 1 <= op <= len(row)) or not (ip and 1 <= ip <= len(row)):
                errors.append(f"구간 {seg_no}: tedashi 칸 out {op} in {ip} 가 줄({len(row)}장) 밖")
            else:
                out_id = row.pop(op - 1)
                row.insert(ip - 1, did)
                ev.update(drawn=did, out=out_id, out_pos=op, in_pos=ip)
                ev["discard"] = do_discard(seg_no, out_id, False, j)
        elif k == "draw":
            ip = j.get("in_pos") or len(row) + 1
            did = new_id()
            if not 1 <= ip <= len(row) + 1:
                errors.append(f"구간 {seg_no}: draw in_pos {ip} 가 줄 밖")
                ip = len(row) + 1
            row.insert(ip - 1, did)
            pending = did
            ev.update(drawn=did, in_pos=ip)
        elif k == "discard":
            op = j.get("out_pos")
            if pending is None:
                errors.append(f"구간 {seg_no}: discard 인데 앞에 draw 가 없음")
            if len(row) != n + 1:
                errors.append(f"구간 {seg_no}: 버리기 전 줄이 {len(row)}장(기대 {n + 1})")
            if not (op and 1 <= op <= len(row)):
                errors.append(f"구간 {seg_no}: discard out_pos {op} 가 줄 밖")
            else:
                out_id = row.pop(op - 1)
                ev.update(out=out_id, out_pos=op)
                ev["discard"] = do_discard(seg_no, out_id, out_id == pending, j)
            pending = None
        elif k == "call":
            mp = sorted(j.get("meld_pos") or [], reverse=True)
            if len(row) != n or pending is not None:
                errors.append(f"구간 {seg_no} call: 울기 전 줄이 {len(row)}장(기대 {n})")
            took = []
            for p in mp:
                if 1 <= p <= len(row):
                    took.append(row.pop(p - 1))
                else:
                    errors.append(f"구간 {seg_no}: meld_pos {p} 가 줄 밖")
            took.reverse()
            if len(took) != 2:
                warns.append(f"구간 {seg_no}: 울기로 나간 패 {len(took)}장(퐁·치는 2장, 깡은 이 스크립트가 다루지 않음)")
            calls += 1
            last_was_call = True
            mt = [m["tile"] for m in meld_seq if m["seg"] == seg_no]
            ev.update(meld_ids=took, meld_seen=mt)
            if j.get("meld_tiles"):  # 판정자가 울기 패 종류를 적었으면 그것으로
                for i_, t in zip(took, j["meld_tiles"]):
                    types[i_] = t
            elif final.get("melds"):
                warns.append(f"구간 {seg_no}: 울기 패 종류는 끝 공개의 울기 {final['melds']} 에서 손으로 확인할 것(meld_tiles 칸)")
            if j.get("out_pos"):
                op = j["out_pos"]
                if 1 <= op <= len(row):
                    out_id = row.pop(op - 1)
                    ev.update(out=out_id, out_pos=op)
                    ev["discard"] = do_discard(seg_no, out_id, False, j)
                else:
                    errors.append(f"구간 {seg_no}: call out_pos {op} 가 줄 밖")
        elif k == "reveal":
            reveal_done = True
        elif k == "unclear":
            nd = j.get("discards")
            if nd is None:
                nd = len((segs[seg_no].get("river") or {}).get("river_new") or [])
            for r in take_river(seg_no, nd):
                discards.append({"seg": seg_no, "id": None, "tile": r["tile"], "tsumogiri": None, "unknown": True})
                if r["sideways"]:
                    riichi_after = True
            calls += j.get("calls", 0)
            ci += 1
            if ci >= len(chunk_names):
                raise SystemExit("unclear 가 너무 많음")
            next_id[0] = 1
            row = [new_id() for _ in range(n_now())]
            next_id[0] = n_now() + 1
            chunks.append(Chunk(chunk_names[ci], row))
            pending = None
            last_was_call = False
            breaks.append({"seg": seg_no, "discards_in_gap": nd, "new_chunk": chunk_names[ci]})
        if k != "unclear":
            ev["moves"] = apply_moves(j, seg_no)
        ev["row"] = list(row)
        ev["pending"] = pending
        events.append(ev)
        if k == "reveal":
            break

    # 공개: 끝 손패와 잇기
    win_id = None
    if pending is not None and tsumo:
        win_id = pending
        row.remove(pending)
    elif tsumo:
        win_id = new_id()
    if win_id is not None and win_tile:
        types[win_id] = win_tile
    if len(row) != len(closed_final):
        errors.append(f"공개: 줄 {len(row)}장 ≠ 끝 손패 {len(closed_final)}장 — 끝 손패를 번호에 붙이지 못함")
    else:
        for i_, t in zip(row, closed_final):
            if i_ in types and types[i_] != t:
                errors.append(f"공개: 번호 {i_} 종류 충돌 {types[i_]} vs 끝 손패 {t}")
            types[i_] = t
    if river_k != len(river_seq):
        warns.append(f"판정으로 센 버림 {river_k}장 ≠ 강 기록 {len(river_seq)}장(판 구간 안)")

    # 매 순 손패
    def tt(i_):
        return types.get(i_, "?")

    turns = []
    for ev in events:
        if "row" not in ev:
            continue
        turns.append({"seg": ev["seg"], "kind": ev.get("kind", "move"), "row_ids": ev["row"], "row_tiles": [tt(i_) for i_ in ev["row"]],
                      "out": ev.get("out"), "out_tile": tt(ev["out"]) if ev.get("out") is not None else None,
                      "drawn": ev.get("drawn"), "drawn_tile": tt(ev["drawn"]) if ev.get("drawn") is not None else None,
                      "in_pos": ev.get("in_pos"), "out_pos": ev.get("out_pos"), "moves": ev.get("moves") or []})
    # 검사: 같은 패 5장
    all_ids = set()
    for c in chunks:
        all_ids.update(c.start_ids)
    all_ids.update(i_ for ev in events for i_ in ev.get("row", []))
    all_ids.update(d["id"] for d in discards if d.get("id") is not None)
    cnt = Counter(norm(types[i_]) for i_ in all_ids if i_ in types)
    for d in discards:
        if d.get("id") is None and d.get("tile"):
            cnt[norm(d["tile"])] += 1
    for t, c in cnt.items():
        if c > 4:
            errors.append(f"같은 패 {t} 가 화료자 번호에 {c}장")
    for tu in turns:
        c = Counter(norm(x) for x in tu["row_tiles"] if x != "?")
        for t, v in c.items():
            if v > 4:
                errors.append(f"구간 {tu['seg']}: 손패에 {t} {v}장")
    # 정렬 검사: 뽑은 패가 들어간 칸
    ins = []
    for ev in events:
        if ev.get("kind") in ("tedashi", "draw") and ev.get("drawn") is not None and ev.get("in_pos"):
            r = ev["row"]
            p = r.index(ev["drawn"]) if ev["drawn"] in r else None
            if p is None:
                continue
            new = tt(ev["drawn"])
            left = tt(r[p - 1]) if p > 0 else None
            right = tt(r[p + 1]) if p + 1 < len(r) else None
            if ev.get("kind") == "draw" and p == len(r) - 1:
                continue  # 오른쪽 끝에 떼어 둔 것은 정렬 검사 밖
            f = fits(new, left, right, sch)
            others = [tt(x) for x in r if x != ev["drawn"]]
            # 아무 칸에나 넣었을 때 맞물릴 비율
            ok = tot = 0
            for q in range(len(others) + 1):
                fq = fits(new, others[q - 1] if q > 0 else None, others[q] if q < len(others) else None, sch)
                if fq is not None:
                    tot += 1
                    ok += fq
            ins.append({"seg": ev["seg"], "tile": new, "left": left, "right": right, "fit": f, "random_rate": round(ok / tot, 3) if tot else None})
    known = [x for x in ins if x["fit"] is not None]
    sort_check = {"scheme": sch, "insertions": ins, "known": len(known), "fit": sum(x["fit"] for x in known),
                  "fit_rate": round(sum(x["fit"] for x in known) / len(known), 3) if known else None,
                  "random_rate_mean": round(sum(x["random_rate"] for x in known if x["random_rate"] is not None) / len(known), 3) if known else None}
    # 순마다 줄 정렬 정도
    for tu in turns:
        ks = [key(x, sch) for x in tu["row_tiles"]]
        pairs = [(p, q) for p, q in zip(ks, ks[1:]) if p is not None and q is not None]
        tu["sorted_pairs"] = f"{sum(p <= q for p, q in pairs)}/{len(pairs)}"
    start = [{"chunk": c.name, "ids": c.start_ids, "tiles": [tt(i_) for i_ in c.start_ids]} for c in chunks]
    res = {"game": gid, "judgment_file": str(jp), "result": game.get("result"), "final_closed": closed_final, "win_tile": win_tile, "win_id": win_id,
           "chunks": start, "breaks": breaks, "start_hand": start[0]["tiles"] if not breaks else None,
           "start_hand_note": "끊김 없음 — 번호 1~13 = 복원된 시작 손패" if not breaks else
           "끊김 있음 — 첫 덩어리 시작 손패는 버린 패만 알 수 있고, 마지막 덩어리만 끝 손패에서 거꾸로 채워진다",
           "discards": discards, "turns": turns, "types": {str(k): v for k, v in types.items()}, "sort_check": sort_check,
           "counts": {"judged": len(jud), "segments": len(segs), "low_conf": sum(1 for j in jud.values() if j.get("conf") == "low"),
                      "discards_judged": len([d for d in discards if d.get("id") is not None]), "river_seq": len(river_seq),
                      "tsumogiri": sum(1 for d in discards if d.get("tsumogiri")), "tedashi": sum(1 for d in discards if d.get("tsumogiri") is False)},
           "errors": errors, "warnings": warns}
    outd = Path(a.out) if a.out else od
    outd.mkdir(parents=True, exist_ok=True)
    stem = f"replay_{jp.stem}"
    hc.jsave(outd / f"{stem}.json", res)
    lines = [f"{gid} 판정 {jp.name} · 결과 {game.get('result')} · 끝 손패 {' '.join(closed_final)} + {win_tile}",
             f"정렬 방식(끝 손패에서): 무늬 순서 {sch['suit_order']} · 숫자 {'오름' if sch['ascending'] else '내림'}차순 · 무늬 묶음 {'연속' if sch['suits_contiguous'] else '흩어짐'}"]
    for c in start:
        lines.append(f"덩어리 {c['chunk']} 시작 손패: " + " ".join(f"{i_}:{t}" for i_, t in zip(c["ids"], c["tiles"])))
    lines.append("")
    lines.append("(판정이 none 이고 옮김도 없는 구간은 줄을 생략)")
    for tu in turns:
        if tu["kind"] == "none" and not tu.get("moves"):
            continue
        o = f" 나감 {tu['out']}:{tu['out_tile']}" if tu["out"] is not None else ""
        dr = f" 뽑음 {tu['drawn']}:{tu['drawn_tile']}" + (f"→{tu['in_pos']}칸" if tu["in_pos"] else "") if tu["drawn"] is not None else ""
        mv = (" 옮김 " + ",".join(f"{m['from']}→{m['to']}" for m in tu["moves"])) if tu.get("moves") else ""
        lines.append(f"구간 {tu['seg']:3d} {tu['kind']:9s}{dr}{o}{mv} | " + " ".join(tu["row_tiles"]) + f"  (정렬 {tu['sorted_pairs']})")
    lines.append("")
    lines.append(f"정렬 검사: 뽑은 패가 끼어든 칸이 양옆과 맞물림 {sort_check['fit']}/{sort_check['known']} (비율 {sort_check['fit_rate']}) · 아무 칸에나 넣었을 때 기대 {sort_check['random_rate_mean']}")
    lines.append(f"버림 {res['counts']['discards_judged']}장(쯔모기리 {res['counts']['tsumogiri']}, 손에서 {res['counts']['tedashi']}) / 강 기록 {len(river_seq)}장")
    for b in breaks:
        lines.append(f"끊김: 구간 {b['seg']} (사이 버림 {b['discards_in_gap']}장) → 덩어리 {b['new_chunk']}")
    lines += [f"오류: {e}" for e in errors] + [f"경고: {w}" for w in warns]
    (outd / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
