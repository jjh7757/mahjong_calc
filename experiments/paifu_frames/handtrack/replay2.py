"""판정 형식 v2(JUDGE.md 사건 목록)를 받아 후보를 가지로 굴리고, 버림(강)·울기·끝 손패로 번호에 종류를 붙여 매 순 손패를 거꾸로 복원한다.

  python -X utf8 replay2.py <판 id> <판정 파일…> [--out 폴더] [--use-rules] [--name 이름]
  python -X utf8 replay2.py --selftest

읽는 것: results/handtrack/<판>/game.json · index.json. 판정 파일 여러 개(구간을 나눠 맡은 몫)를 합쳐 읽는다 — 같은 구간이 둘이면 멈춤.
결과: <폴더 = results/handtrack/<판>>/replay2_<이름>.json · .txt (이름 기본 = 판정 파일 이름들을 + 로 이음).

자세한 뜻·정한 것은 README_replay2.md.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from itertools import combinations, permutations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
from replay import key, norm, sort_scheme  # noqa: E402  (v1 의 정렬 방식 읽기를 그대로 씀)

KINDS = {"draw", "discard", "place", "move", "shuffle", "call", "reveal", "unknown"}
LIMIT = 200_000
SKIN_MIN = 0.003
SHUFFLE_MAX = 4
SHOW_HANDS = 6


# ------------------------------------------------------------------ 입력
def cands(v) -> list:
    """칸 값 → 후보 목록(한 값이면 길이 1)."""
    if isinstance(v, list):
        return list(v)
    return [v]


def meld_cands(v) -> list[list[int]]:
    """meld_pos: [6, 7] → [[6, 7]], [[6, 7], [7, 8]] → 후보 둘."""
    if not v:
        return [[]]
    if all(isinstance(x, list) for x in v):
        return [list(x) for x in v]
    return [list(v)]


def load_judgments(paths, game_id: str):
    """판정 파일들을 합친다. 같은 구간이 두 번 나오면 SystemExit."""
    jud, meta, errors = {}, [], []
    for p in paths:
        p = Path(p)
        J = hc.jload(p)
        g = J.get("game")
        if g and g != game_id:
            errors.append(f"판정 파일 {p.name} 의 game {g} ≠ {game_id}")
        for j in J.get("judgments") or []:
            s = j["seg"]
            if s in jud:
                raise SystemExit(f"오류: 구간 {s} 가 두 번 판정됨 — {jud[s]['_file']} · {p.name}")
            for e in j.get("events") or []:
                if e.get("kind") not in KINDS:
                    raise SystemExit(f"오류: {p.name} 구간 {s} 의 사건 kind {e.get('kind')!r} 를 모름")
            j = dict(j)
            j["_file"] = p.name
            j["_judge"] = J.get("judge")
            jud[s] = j
        meta.append({"file": str(p), "judge": J.get("judge"), "segments": len(J.get("judgments") or [])})
    return jud, meta, errors


def river_new(seg: dict) -> list[dict]:
    return list(((seg.get("river") or {}).get("river_new")) or [])


def build_plan(index: dict, jud: dict, errors: list, warns: list) -> list[dict]:
    """index 의 구간마다 사건 목록을 정한다(판정 / 자동 / 판정 없음)."""
    plan = []
    known = {s["seg"] for s in index["segments"]}
    for s in sorted(set(jud) - known):
        errors.append(f"판정의 구간 {s} 가 index 에 없음(무시)")
    for s in index["segments"]:
        no = s["seg"]
        rn = river_new(s)
        skin = s.get("max_skin") or 0.0
        base = {"seg": no, "river": rn, "skin": skin}
        j = jud.get(no)
        if j is not None:
            plan.append({**base, "events": list(j.get("events") or []), "source": "judge", "file": j["_file"],
                         "n_before": j.get("n_before"), "n_after": j.get("n_after"), "d_at_start": bool(j.get("d_at_start")),
                         "note": j.get("note")})
        elif skin < SKIN_MIN:
            ev = []
            for _ in rn:
                ev += [{"kind": "draw", "auto": True}, {"kind": "discard", "what": "D", "auto": True}]
            if len(rn) > 1:
                warns.append(f"구간 {no}: 손이 안 들어왔는데 강에 새 패 {len(rn)}장 → 쯔모기리 {len(rn)}번으로 넣음")
            plan.append({**base, "events": ev, "source": "auto" if rn else "empty", "n_before": None, "n_after": None, "d_at_start": False})
        else:
            errors.append(f"구간 {no}: 손이 띠에 들어왔는데(max_skin {skin:.3f}) 판정이 없음 → 끊김(unknown)으로 처리")
            plan.append({**base, "events": [{"kind": "unknown", "note": "판정 없음", "auto": True}], "source": "missing",
                         "n_before": None, "n_after": None, "d_at_start": False})
    return plan


def ev_str(e: dict) -> str:
    """사건 한 개를 짧은 글로(txt·compare 용)."""
    k = e.get("kind")
    if k == "discard":
        w = e.get("what")
        s = f"discard {w}"
        if e.get("left") is not None or e.get("right") is not None:
            s += f"(L{e.get('left')}R{e.get('right')})"
        if e.get("end_hidden"):
            s += " 끝가림"
        return s
    if k == "place":
        return f"place {e.get('pos')}"
    if k == "move":
        return f"move {e.get('from')}→{e.get('to')}"
    if k == "shuffle":
        return f"shuffle {e.get('pos')}"
    if k == "call":
        return f"call {e.get('meld_pos')}"
    if k == "reveal":
        return "reveal" + ("" if e.get("order_kept", True) else "(순서?)")
    return k + ("(자동)" if e.get("auto") else "")


def L(log, *entries):
    for e in entries:
        log = (log, e)
    return log


# ------------------------------------------------------------------ 굴리기
class Overflow(Exception):
    pass


class Engine:
    def __init__(self, game: dict, index: dict, plan: list[dict], n0: int, use_rules=False, limit=LIMIT, widen=0):
        self.game, self.index, self.plan, self.n0 = game, index, plan, n0
        self.use_rules, self.limit, self.widen = use_rules, limit, widen
        self.n_widened = 0
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.river_seq = [{"seg": s["seg"], "tile": t.get("tile"), "sideways": bool(t.get("sideways"))}
                          for s in index["segments"] for t in river_new(s)]
        fh = game.get("final_hand") or {}
        self.closed = list(fh.get("closed") or [])
        self.win_tile = fh.get("win_tile")
        self.tsumo = str(game.get("result") or "").startswith("tsumo")
        self.n_calls_plan = sum(1 for sp in plan for e in sp["events"] if e.get("kind") == "call")
        self.meld_groups = self._meld_groups(fh)

    # -- 울기 패 종류: final_hand.melds 를 3장씩, 가로 놓인 패(남의 패)를 뺀 2장이 화료자 몫
    def _meld_groups(self, fh) -> list[list[tuple]]:
        melds = list(fh.get("melds") or [])
        det = list(fh.get("meld_detail") or [])
        groups = []
        if not melds:
            return groups
        if len(melds) % 3:
            self.warns.append(f"끝 공개 울기 {melds} 가 3장 묶음으로 안 나뉨(깡?) — 울기 종류를 붙이지 않음")
            return groups
        for g in range(len(melds) // 3):
            tiles = melds[3 * g:3 * g + 3]
            dd = det[3 * g:3 * g + 3] if len(det) == len(melds) else []
            side = [i for i, d in enumerate(dd) if d.get("sideways")]
            if len(side) == 1:
                shares = [tuple(t for i, t in enumerate(tiles) if i != side[0])]
            else:
                shares = sorted({tuple(sorted(c)) for c in combinations(tiles, 2)})
                self.warns.append(f"울기 {tiles}: 가로 놓인(가져온) 패를 못 정함 → 화료자 몫 2장을 후보 {shares} 로")
            opts = set()
            for sh in shares:
                opts.update(permutations(sh))
            groups.append(sorted(opts))
        if len(groups) != self.n_calls_plan:
            self.warns.append(f"끝 공개 울기 {len(groups)}묶음 ≠ 판정의 call {self.n_calls_plan}번 — 순서대로 붙이고 남는 call 은 종류 ?")
        elif len(groups) > 1:
            self.warns.append("울기 여럿: 공개 울기 묶음을 call 순서대로 붙임(가정)")
        return groups

    def widen_opts(self, ev: dict, v) -> list:
        """--widen-place K: 후보를 양쪽으로 K칸 넓힘(줄 범위 밖은 사건 적용 때 걸러짐). conf high 인 한 값은 그대로."""
        opts = cands(v)
        if not self.widen or (not isinstance(v, list) and ev.get("conf") == "high"):
            return opts
        ints = [p for p in opts if isinstance(p, int)]
        wide = sorted({q for p in ints for q in range(p - self.widen, p + self.widen + 1) if q >= 1})
        if len(wide) > len(set(ints)):
            self.n_widened += 1
        return wide + [p for p in opts if not isinstance(p, int)]

    def new_id(self):
        v = self.next_id
        self.next_id += 1
        return v

    def expand(self, br, fn, where: str):
        # 같은 상태(R, D)에 같은 기록(log 객체)인 가지는 결과가 똑같으므로 하나로 합친다(예: shuffle 두 번이 같은 줄로 감).
        out, dead, seen = [], Counter(), set()
        for b in br:
            r = fn(b)
            if isinstance(r, str):
                dead[r] += 1
                continue
            for nb in r:
                kk = (nb[0], nb[1], id(nb[2]))
                if kk in seen:
                    continue
                seen.add(kk)
                out.append(nb)
        if dead and out:
            self.warns.append(f"{where}: 가지 {sum(dead.values())}개가 사라짐(" + ", ".join(f"{k} {v}" for k, v in dead.items()) + ")")
            self.died += sum(dead.values())
        if not out:
            self.errors.append(f"{where}: 모든 가지가 불가능(" + ", ".join(f"{k} {v}" for k, v in dead.items()) + ")")
            return None
        if len(out) > self.limit:
            self.overflow = {"where": where, "branches": len(out)}
            raise Overflow
        return out

    def check_count(self, br, n, where):
        if n is None:
            return br
        lens = Counter(len(R) for R, _, _ in br)
        if n in lens and len(lens) > 1:
            keep = [b for b in br if len(b[0]) == n]
            self.count_pruned += len(br) - len(keep)
            self.warns.append(f"{where}: 장수 {n} 과 다른 가지 {len(br) - len(keep)}개를 버림")
            return keep
        if n not in lens:
            self.errors.append(f"{where}: 장수 모순 — 사건을 적용한 R {dict(lens)}장 ≠ 판정 {n}장 (v1 처럼 계속)")
        return br

    def synth_draw(self, br, seg, why):
        self.t += 1
        t = self.t
        did = self.new_id()
        self.turns.append({"t": t, "seg": seg, "kind": "draw", "synthetic": True, "events": [f"(뽑기 넣음: {why})"]})
        self.warns.append(f"구간 {seg}: {why} → 뽑기를 넣음(번호 {did})")
        self.turn_did, self.turn_dcand = did, False
        self.fresh = False
        return [(R, did, L(log, ("T", t, R), ("d", t, did))) if D is None else (R, D, log) for R, D, log in br]

    def do_break(self, br, sp, ei, reason, ev):
        seg = sp["seg"]
        n_disc = sum(1 for e in sp["events"] if e.get("kind") == "discard")
        consumed = ev.get("discards")
        if consumed is None:
            consumed = max(0, len(sp["river"]) - n_disc)
        gap = []
        for _ in range(consumed):
            rv = self.river_seq[self.k] if self.k < len(self.river_seq) else None
            gap.append(rv["tile"] if rv else None)
            self.k += 1
        self.unknown_tiles += [x for x in gap if x]
        self.seg_consumed[seg] = self.seg_consumed.get(seg, 0) + consumed
        # 새 덩어리 장수 = n_after 에서 뒤 사건의 증감을 뺀 값
        delta = 0
        for e in sp["events"][ei + 1:]:
            k = e.get("kind")
            if k == "place":
                delta += 1
            elif k == "discard" and cands(e.get("what"))[0] != "D":
                delta -= 1
            elif k == "call":
                delta -= len(meld_cands(e.get("meld_pos"))[0])
        if sp.get("n_after") is not None:
            m = sp["n_after"] - delta
        else:
            m = len(br[0][0])
        ids = tuple(self.new_id() for _ in range(m))
        ci = len(self.chunks)
        name = chr(ord("A") + ci) if ci < 26 else f"Z{ci}"
        self.chunks.append({"name": name, "seg": seg, "ids": ids})
        self.breaks.append({"seg": seg, "event": ei, "reason": reason, "river_in_gap": gap, "new_chunk": name, "new_n": m})
        self.fresh = True
        self.post_call_pending = False
        self.turn_dcand = False
        return [(ids, None, L(log, ("c", ci))) for _, _, log in br]

    # ---------------------------------------------------------- 사건 하나
    def step(self, br, sp, ei, ev):
        seg = sp["seg"]
        kind = ev["kind"]
        where = f"구간 {seg} 사건 {ei + 1}({ev_str(ev)})"
        if self.turns and kind not in ("draw", "call"):
            self.turns[-1]["events"].append(ev_str(ev))

        if kind == "draw":
            if ev.get("auto") and all(D is not None for _, D, _ in br):
                self.warns.append(f"구간 {seg}: 자동 쯔모기리인데 이미 D 가 있음 → 뽑기 없이 그 D 를 버린 것으로")
                return br
            self.t += 1
            t = self.t
            did = self.new_id()
            self.turns.append({"t": t, "seg": seg, "kind": "draw", "synthetic": False, "auto": bool(ev.get("auto")), "events": [ev_str(ev)]})
            self.turn_dcand = False
            self.turn_did = did
            self.fresh = False

            def f(b):
                R, D, log = b
                if D is not None:
                    return "D 가 남은 채 뽑음"
                return [(R, did, L(log, ("T", t, R), ("d", t, did)))]
            nb = self.expand(br, f, where)
            if nb is None:
                self.errors.append(f"{where}: 남은 D 를 줄 오른쪽 끝에 넣은 것으로 보고 뽑음")
                nb = [(R + (D,), did, L(log, ("p", t - 1, len(R) + 1), ("T", t, R + (D,)), ("d", t, did))) for R, D, log in br]
            return nb

        if kind == "discard":
            opts = cands(ev.get("what"))
            eh = bool(ev.get("end_hidden"))
            if self.fresh and opts == ["D"] and all(D is None for _, D, _ in br):
                br = self.synth_draw(br, seg, "끊김 뒤 D 없이 discard D")
            di = len(self.discs)
            k = self.k
            self.k += 1
            rv = self.river_seq[k] if k < len(self.river_seq) else None
            if rv is None:
                self.errors.append(f"{where}: 버림이 강 기록({len(self.river_seq)}장)보다 많음 — 종류 ?")
            elif rv["seg"] != seg:
                self.warns.append(f"{where}: {k + 1}번째 버림을 강 기록에서는 구간 {rv['seg']} 에서 봄({rv['tile']})")
            self.discs.append({"di": di, "k": k, "seg": seg, "t": self.t, "tile": rv["tile"] if rv else None,
                               "sideways": rv["sideways"] if rv else False, "what": ev.get("what"), "end_hidden": eh,
                               "post_call": self.post_call_pending, "auto": bool(ev.get("auto"))})
            self.post_call_pending = False
            if eh:
                self.n_end_hidden += 1
            if (len(opts) > 1 and "D" in opts) or (eh and "D" in opts):
                # D 를 버린 가지에서 뒤따르는 place 를 어떻게 볼지: R 후보에 줄의 마지막 칸이 있거나 끝 가림이면
                # "끝 두 장 중 남은 한 장(= 마지막 칸 패)을 옮김", 아니면 넘김(경고)
                nR = {len(R) for R, _, _ in br}
                last_ok = eh or any(isinstance(o, int) and o in nR for o in opts)
                self.turn_dcand = ("move" if last_ok else "skip", seg)
            if len(opts) == 1 and isinstance(opts[0], int):
                lf, rt = ev.get("left"), ev.get("right")
                nR = {len(R) for R, _, _ in br}
                if lf is not None and lf + 1 != opts[0]:
                    self.warns.append(f"{where}: left {lf} + 1 ≠ what {opts[0]}")
                if lf is not None and rt is not None and all(lf + rt + 1 != n for n in nR):
                    self.warns.append(f"{where}: left+right+1 = {lf + rt + 1} ≠ 버리기 전 R {sorted(nR)}장")

            def f(b):
                R, D, log = b
                out = []
                for o in opts:
                    if o == "D":
                        if D is None:
                            continue
                        out.append((R, None, L(log, ("x", di, D, True, None))))
                        if eh and R:
                            n = len(R)
                            out.append((R[:-1] + (D,), None, L(log, ("x", di, R[-1], False, n), ("p", self.t, n))))
                    elif isinstance(o, int) and 1 <= o <= len(R):
                        out.append((R[:o - 1] + R[o:], D, L(log, ("x", di, R[o - 1], False, o))))
                return out or "버릴 패가 없음(D 없음 또는 칸이 줄 밖)"
            nb = self.expand(br, f, where)
            if nb is None:
                self.errors.append(f"{where}: 이 버림을 건너뜀(강 패 {rv['tile'] if rv else '?'} 는 종류 셈에만 넣음)")
                if rv:
                    self.unknown_tiles.append(rv["tile"])
                return br
            return nb

        if kind == "place":
            opts = self.widen_opts(ev, ev.get("pos"))
            if self.fresh and all(D is None for _, D, _ in br):
                br = self.synth_draw(br, seg, "끊김 뒤 D 없이 place")
            t = self.t
            dc = self.turn_dcand
            mv = bool(dc) and dc[0] == "move" and dc[1] == seg
            tdid = self.turn_did
            if dc and not mv and any(D is None for _, D, _ in br):
                self.warns.append(f"{where}: D 를 버린 가지에서는 이 place 를 넘김"
                                  + (" (버림 R 후보가 줄의 마지막 칸이 아님)" if dc[0] == "skip" else " (버림과 다른 구간)"))

            def f(b):
                R, D, log = b
                if D is None:
                    if mv:
                        # D 를 버린(또는 끝 가림으로 D 가 끝 칸에 선) 가지: 마지막 칸 패를 p칸으로 옮김
                        out = []
                        for p in opts:
                            if isinstance(p, int) and 1 <= p <= len(R):
                                x, rest = R[-1], R[:-1]
                                R2 = rest[:p - 1] + (x,) + rest[p - 1:]
                                out.append((R2, None, L(log, ("p", t, p)) if x == tdid else log))
                        return out or "칸이 줄 밖"
                    if dc:
                        return [(R, None, log)]  # 후보 중 D 를 버린 가지: 자리 잡을 D 가 없음
                    return "D 없음"
                out = [(R[:p - 1] + (D,) + R[p - 1:], None, L(log, ("p", t, p))) for p in opts if isinstance(p, int) and 1 <= p <= len(R) + 1]
                return out or "칸이 줄 밖"
            nb = self.expand(br, f, where)
            if nb is None:
                self.errors.append(f"{where}: 이 place 를 건너뜀")
                return br
            return nb

        if kind == "move":
            froms, tos = cands(ev.get("from")), self.widen_opts(ev, ev.get("to"))

            def f(b):
                R, D, log = b
                out, seen = [], set()
                for fr in froms:
                    for to in tos:
                        if isinstance(fr, int) and isinstance(to, int) and 1 <= fr <= len(R) and 1 <= to <= len(R):
                            x = R[fr - 1]
                            rest = R[:fr - 1] + R[fr:]
                            R2 = rest[:to - 1] + (x,) + rest[to - 1:]
                            if R2 not in seen:
                                seen.add(R2)
                                out.append((R2, D, log))
                return out or "칸이 줄 밖"
            nb = self.expand(br, f, where)
            if nb is None:
                self.errors.append(f"{where}: 이 move 를 건너뜀")
                return br
            return nb

        if kind == "shuffle":
            S = sorted({p for p in cands(ev.get("pos")) if isinstance(p, int)})
            if len(S) > SHUFFLE_MAX:
                self.n_shuffle_big += 1
                return self.do_break(br, sp, ei, f"shuffle {len(S)}칸(> {SHUFFLE_MAX}) → 끊김", ev)
            self.n_shuffle += 1

            def f(b):
                R, D, log = b
                if not all(1 <= s <= len(R) for s in S):
                    return "칸이 줄 밖"
                out = []
                for perm in permutations([R[s - 1] for s in S]):
                    R2 = list(R)
                    for s, v in zip(S, perm):
                        R2[s - 1] = v
                    out.append((tuple(R2), D, log))
                return out
            nb = self.expand(br, f, where)
            if nb is None:
                self.errors.append(f"{where}: 이 shuffle 을 건너뜀")
                return br
            return nb

        if kind == "call":
            self.t += 1
            t = self.t
            self.turns.append({"t": t, "seg": seg, "kind": "call", "synthetic": False, "events": [ev_str(ev)]})
            self.turn_did = None
            self.turn_dcand = False
            self.fresh = False
            ci = self.n_calls
            self.n_calls += 1
            opts = meld_cands(ev.get("meld_pos"))
            if ev.get("meld_tiles"):
                assigns = [tuple(ev["meld_tiles"])]
            elif ci < len(self.meld_groups):
                assigns = self.meld_groups[ci]
            else:
                assigns = [None]
            self.post_call_pending = True

            def g(b, need_noD=True):
                R, D, log = b
                if need_noD and D is not None:
                    return "D 가 남은 채 울기"
                out = []
                for mp in opts:
                    mp = sorted(set(mp))
                    if not mp or not all(isinstance(p, int) and 1 <= p <= len(R) for p in mp):
                        continue
                    ids = tuple(R[p - 1] for p in mp)
                    R2 = tuple(x for i, x in enumerate(R, 1) if i not in mp)
                    for ty in assigns:
                        if ty is not None and len(ty) != len(ids):
                            ty = tuple(ty[:len(ids)]) + ("?",) * max(0, len(ids) - len(ty))
                        out.append((R2, D, L(log, ("T", t, R), ("m", t, ids, ty))))
                return out or "칸이 줄 밖"
            nb = self.expand(br, g, where)
            if nb is None:
                self.errors.append(f"{where}: D 를 둔 채로 울기를 적용")
                nb = self.expand(br, lambda b: g(b, False), where + " 다시")
                if nb is None:
                    return br
            return nb

        if kind == "reveal":
            if ev.get("order_kept") is False:
                self.reveal_uncertain = True
                self.warns.append(f"{where}: 공개 순서 불확실(order_kept false) — 읽은 순서를 그대로 씀")
            self.revealed = True
            return [(R, D, L(log, ("r", R, D))) for R, D, log in br]

        if kind == "unknown":
            return self.do_break(br, sp, ei, "unknown" + (f": {ev.get('note')}" if ev.get("note") else ""), ev)
        raise ValueError(kind)

    # ---------------------------------------------------------- 전체
    def run(self) -> list:
        n0 = self.n0
        self.next_id = n0 + 1
        start = tuple(range(1, n0 + 1))
        self.chunks = [{"name": "A", "seg": None, "ids": start}]
        self.t = 0
        self.turns, self.discs, self.breaks, self.unknown_tiles = [], [], [], []
        self.k = 0
        self.n_calls = 0
        self.seg_consumed: dict = {}
        self.post_call_pending = self.turn_dcand = self.fresh = False
        self.turn_did = None
        self.revealed = self.reveal_uncertain = False
        self.overflow = None
        self.count_pruned = self.died = 0
        self.n_end_hidden = self.n_shuffle = self.n_shuffle_big = 0
        br = [(start, None, None)]
        try:
            for sp in self.plan:
                seg = sp["seg"]
                if self.revealed:
                    if sp["events"] and sp["source"] == "judge":
                        self.warns.append(f"구간 {seg}: 공개 뒤 사건 — 무시")
                    continue
                br = self.check_count(br, sp.get("n_before"), f"구간 {seg} 시작(n_before)")
                if sp.get("d_at_start"):
                    if all(D is None for _, D, _ in br):
                        br = self.synth_draw(br, seg, "d_at_start 인데 앞에서 D 가 없음")
                elif sp["source"] == "judge" and all(D is not None for _, D, _ in br):
                    self.warns.append(f"구간 {seg}: 앞 구간에서 D 가 남았는데 d_at_start 가 없음")
                k0 = self.k
                for ei, ev in enumerate(sp["events"]):
                    br = self.step(br, sp, ei, ev)
                    if self.revealed:
                        if ei + 1 < len(sp["events"]):
                            self.warns.append(f"구간 {seg}: reveal 뒤 사건 {len(sp['events']) - ei - 1}개 무시")
                        break
                used = self.k - k0
                if used != len(sp["river"]):
                    self.errors.append(f"구간 {seg}: 버림 수 불일치 — 판정 버림 {used - self.seg_consumed.get(seg, 0)}"
                                       f"{'(+끊김 ' + str(self.seg_consumed[seg]) + ')' if self.seg_consumed.get(seg) else ''}"
                                       f" ≠ 강 새 패 {len(sp['river'])}({' '.join(t.get('tile') or '?' for t in sp['river'])}) → 전체 순서 k번째로 맞춰 계속")
                br = self.check_count(br, sp.get("n_after"), f"구간 {seg} 끝(n_after)")
            if not self.revealed:
                self.warns.append("reveal 사건이 없음 → 마지막 상태에서 공개 적용")
                br = [(R, D, L(log, ("r", R, D))) for R, D, log in br]
        except Overflow:
            return []
        if self.k != len(self.river_seq):
            self.warns.append(f"판정으로 센 버림(끊김 포함) {self.k}장 ≠ 강 기록 {len(self.river_seq)}장(판 구간 안)")
        return br

    # ---------------------------------------------------------- 가지 하나 펼치기
    def view(self, log, msgs: set | None = None) -> dict:
        ent = []
        while log is not None:
            log, e = log
            ent.append(e)
        ent.reverse()
        types: dict = {}
        turnR, drawn, disc, placed = {}, {}, {}, {}
        reveal = None
        for e in ent:
            tag = e[0]
            if tag == "T":
                turnR[e[1]] = e[2]
            elif tag == "d":
                drawn[e[1]] = e[2]
            elif tag == "x":
                di, i_, isD, slot = e[1:]
                m = self.discs[di]
                disc.setdefault(m["t"], []).append((di, i_, isD, slot))
                if m["tile"]:
                    types[i_] = m["tile"]
            elif tag == "p":
                placed.setdefault(e[1], []).append(e[2])
            elif tag == "m":
                if e[3] is not None:
                    for i_, ty in zip(e[2], e[3]):
                        if ty and ty != "?":
                            types[i_] = ty
            elif tag == "r":
                reveal = (e[1], e[2])
        if reveal is not None:
            R, D = reveal
            if len(R) != len(self.closed):
                if msgs is not None:
                    msgs.add(f"공개: 줄 {len(R)}장 ≠ 끝 손패 {len(self.closed)}장 — 끝 손패를 번호에 붙이지 못함")
            else:
                for i_, t in zip(R, self.closed):
                    if i_ in types and types[i_] != t and msgs is not None:
                        msgs.add(f"공개: 번호 {i_} 종류 충돌 {types[i_]} vs {t}")
                    types[i_] = t
            if self.tsumo:
                if D is not None and self.win_tile:
                    types[D] = self.win_tile
                elif D is None and msgs is not None:
                    msgs.add("쯔모인데 공개 때 D 가 없음 — 화료패를 번호에 붙이지 못함")
            elif D is not None and msgs is not None:
                msgs.add("론인데 공개 때 D 가 있음 — 그 번호 종류 ?")
        return {"types": types, "turnR": turnR, "drawn": drawn, "disc": disc, "placed": placed}

    def tt(self, types, i_):
        return types.get(i_, "?")


# ------------------------------------------------------------------ 모으기
def ms_inter(hands):
    it = None
    for h in hands:
        c = Counter(h)
        it = c if it is None else (it & c)
    return it or Counter()


def hand_stat(hands: set) -> dict:
    inter = ms_inter(hands)
    known = Counter({t: v for t, v in inter.items() if t != "?"})
    n = len(next(iter(hands))) if hands else 0
    st = {"n": n, "distinct": len(hands), "confirmed": sum(known.values()),
          "confirmed_tiles": sorted(known.elements(), key=tile_sort)}
    if len(hands) > 1 and len(hands) <= SHOW_HANDS:
        st["candidates"] = [sorted((Counter(h) - inter).elements(), key=tile_sort) for h in sorted(hands)]
    elif len(hands) == 1:
        st["candidates"] = []
    unk = inter.get("?", 0)
    if unk:
        st["unknown_in_all"] = unk
    return st


def tile_sort(t):
    if t == "?" or not t:
        return (9, 0)
    t2 = norm(t)
    return ("mpsz".index(t2[1]) if t2[1] in "mpsz" else 8, int(t2[0]), t)


def aggregate(eng: Engine, br: list, idx: list[int], sch: dict) -> dict:
    """가지 묶음(idx)에서 차례마다 손패·뽑음·버림 모으기."""
    T = len(eng.turns)
    hands = [set() for _ in range(T + 1)]
    drawn = [set() for _ in range(T + 1)]
    isD = [set() for _ in range(T + 1)]
    outs = [set() for _ in range(T + 1)]
    ins = [set() for _ in range(T + 1)]
    starts = [set() for _ in eng.chunks]
    for i in idx:
        v = eng.view(br[i][2])
        ty = v["types"]
        for c, ch in enumerate(eng.chunks):
            starts[c].add(tuple(sorted((eng.tt(ty, x) for x in ch["ids"]), key=tile_sort)))
        for t in range(1, T + 1):
            R = v["turnR"].get(t)
            if R is not None:
                hands[t].add(tuple(sorted((eng.tt(ty, x) for x in R), key=tile_sort)))
            if t in v["drawn"]:
                drawn[t].add(eng.tt(ty, v["drawn"][t]))
            for di, i_, d_, slot in v["disc"].get(t, []):
                isD[t].add(d_)
                outs[t].add("D" if d_ else slot)
            pl = v["placed"].get(t)
            if pl:
                ins[t].add(pl[-1])  # 끝 가림 뒤 place 처럼 두 번 자리 잡으면 마지막 자리
            if t in v["drawn"] and not v["placed"].get(t) and any(d_ for _, _, d_, _ in v["disc"].get(t, [])):
                ins[t].add(None)
    turns = []
    for t in range(1, T + 1):
        m = eng.turns[t - 1]
        dl = [d for d in eng.discs if d["t"] == t]
        st = hand_stat(hands[t]) if hands[t] else {"n": 0, "distinct": 0, "confirmed": 0, "confirmed_tiles": []}
        if isD[t] == {True}:
            mode = "쯔모기리"
        elif isD[t] == {False}:
            mode = "손에서"
        elif isD[t]:
            mode = "둘 다"
        else:
            mode = None
        turns.append({"t": t, "seg": m["seg"], "kind": m["kind"], "synthetic": m.get("synthetic", False), "auto": m.get("auto", False),
                      "judged": m["events"], **st,
                      "drawn": sorted(drawn[t], key=tile_sort),
                      "discard": [{"tile": d["tile"], "seg": d["seg"], "k": d["k"] + 1, "after_riichi": d.get("after_riichi", False),
                                   "post_call": d["post_call"]} for d in dl],
                      "mode": mode, "out_slots": sorted(outs[t], key=lambda x: (isinstance(x, str), x if isinstance(x, int) else 0)),
                      "in_slots": sorted(ins[t], key=lambda x: (x is None, x or 0))})
    start = [{"chunk": ch["name"], "seg": ch["seg"], **hand_stat(starts[c])} for c, ch in enumerate(eng.chunks)]
    return {"turns": turns, "start": start}


def summarize(agg: dict, eng: Engine) -> dict:
    tu = agg["turns"]
    real = [x for x in tu if x["n"]]
    disc_t = [x for x in real if x["mode"]]
    ted = [x for x in disc_t if x["mode"] == "손에서"]
    conf = [x["confirmed"] for x in real]
    s0 = agg["start"][0]
    return {"turns": len(real), "turns_with_discard": len(disc_t),
            "mode_decided": sum(1 for x in disc_t if x["mode"] != "둘 다"),
            "tsumogiri": sum(1 for x in disc_t if x["mode"] == "쯔모기리"), "tedashi": len(ted),
            "tedashi_out_one": sum(1 for x in ted if len(x["out_slots"]) == 1),
            "tedashi_in_one": sum(1 for x in ted if len([p for p in x["in_slots"] if p is not None]) == 1 and None not in x["in_slots"]),
            "fully_confirmed": sum(1 for x in real if x["confirmed"] == x["n"]),
            "confirmed_mean": round(sum(conf) / len(conf), 2) if conf else None, "confirmed_min": min(conf) if conf else None,
            "start_confirmed": s0["confirmed"], "start_n": s0["n"], "start_distinct": s0["distinct"]}


def score_branch(eng: Engine, v: dict, sch: dict):
    ok = tot = 0
    ty = v["types"]
    for t, R in v["turnR"].items():
        ks = [key(eng.tt(ty, x), sch) for x in R]
        for p, q in zip(ks, ks[1:]):
            if p is not None and q is not None:
                tot += 1
                ok += p <= q
    return (ok / tot if tot else None), ok, tot


def bad_pairs(eng: Engine, v: dict, sch: dict) -> list[tuple]:
    """정렬과 어긋난 이웃 쌍: (차례, 구간, 왼쪽 칸, 왼쪽 패, 오른쪽 패)."""
    out = []
    ty = v["types"]
    for t in sorted(v["turnR"]):
        tiles = [eng.tt(ty, x) for x in v["turnR"][t]]
        ks = [key(x, sch) for x in tiles]
        for i, (p, q) in enumerate(zip(ks, ks[1:])):
            if p is not None and q is not None and p > q:
                out.append((t, eng.turns[t - 1]["seg"], i + 1, tiles[i], tiles[i + 1]))
    return out


# ------------------------------------------------------------------ 한 판
def run_game(game: dict, index: dict, jud: dict, n0: int | None = None, use_rules=False, limit=LIMIT, pre_errors=None,
             widen=0, sort_filter=False) -> dict:
    errors, warns = list(pre_errors or []), []
    plan = build_plan(index, jud, errors, warns)
    n0 = n0 or game.get("start_tiles") or 13
    eng = Engine(game, index, plan, n0, use_rules, limit, widen=widen)
    eng.errors, eng.warns = errors, warns + eng.warns
    br = eng.run()
    closed = eng.closed
    res = {"game": game.get("id"), "result": game.get("result"), "tsumo": eng.tsumo, "n0": n0, "use_rules": use_rules,
           "final_closed": closed, "win_tile": eng.win_tile, "melds": (game.get("final_hand") or {}).get("melds") or [],
           "plan": [{"seg": sp["seg"], "source": sp["source"], "file": sp.get("file"), "events": [ev_str(e) for e in sp["events"]],
                     "river": [t.get("tile") for t in sp["river"]]} for sp in plan if sp["events"] or sp["source"] != "empty"]}
    opts = None
    if widen or sort_filter:  # 옵션을 안 주면 결과에 이 칸이 없다(기본 출력 그대로)
        opts = {"widen_place": widen, "sort_filter": bool(sort_filter)}
        res["options"] = opts
    if eng.overflow:
        if opts is not None:
            opts["widened_events"] = eng.n_widened
        res.update(status="가지 넘침", overflow=eng.overflow, errors=errors + [f"가지 넘침: {eng.overflow['where']} 에서 {eng.overflow['branches']}개 > {limit}"],
                   warnings=eng.warns)
        return res
    # 리치·울기 직후 표시(판정 기준 — 가지와 상관없음)
    riichi_k = next((i for i, r in enumerate(eng.river_seq) if r["sideways"]), None)
    if riichi_k is None and game.get("riichi"):
        eng.warns.append("game.json 은 리치인데 강에서 가로 놓인 버림을 못 찾음 — 리치 뒤 규칙을 쓰지 않음")
    for d in eng.discs:
        d["after_riichi"] = riichi_k is not None and d["k"] > riichi_k
    # 가지마다: 5장 검사·규칙·정렬 점수
    sch = sort_scheme(closed) if closed else {"suit_order": [], "suits_contiguous": True, "ascending": True, "pairs_up": 0, "pairs_down": 0}
    extra = Counter(norm(t) for t in (game.get("river_before_ready") or []) if t) + Counter(norm(t) for t in eng.unknown_tiles if t)
    points = [d for d in eng.discs if d["after_riichi"] or d["post_call"]]
    msgs: set = set()
    five_bad, choice, scores = [], [], []
    for R, D, log in br:
        v = eng.view(log, msgs)
        c = Counter(norm(t) for t in v["types"].values() if t and t != "?") + extra
        five_bad.append(sorted(f"{t} {n}장" for t, n in c.items() if n > 4))
        isd = {}
        for t, lst in v["disc"].items():
            for di, i_, d_, slot in lst:
                isd[di] = d_
        choice.append(isd)
        scores.append(score_branch(eng, v, sch))
    errors += sorted(msgs)
    alive = list(range(len(br)))
    prune_log = []
    bad = [i for i in alive if five_bad[i]]
    if bad and len(bad) == len(alive):
        errors.append(f"같은 패 5장 이상이 모든 가지에 있음({five_bad[bad[0]]}) — 자료(강·공개 읽기) 오류로 보고 가지를 버리지 않음")
    elif bad:
        alive = [i for i in alive if not five_bad[i]]
        prune_log.append(f"같은 패 5장 이상인 가지 {len(bad)}개를 버림")
    rule_points = []
    for d in points:
        need = True if d["after_riichi"] else False
        name = "리치 뒤 버림은 D" if d["after_riichi"] else "울기 직후 버림은 R"
        viol = [i for i in alive if d["di"] in choice[i] and choice[i][d["di"]] != need]
        rp = {"seg": d["seg"], "k": d["k"] + 1, "tile": d["tile"], "rule": name, "judged": d["what"], "end_hidden": d["end_hidden"],
              "violating_branches": len(viol), "of": len(alive)}
        if use_rules:
            if viol and len(viol) == len(alive):
                rp["action"] = "모든 가지가 어긋남 — 버리지 않음(판정이 규칙과 다름)"
                errors.append(f"규칙: 구간 {d['seg']} {d['k'] + 1}번째 버림({d['tile']}) — {name} 인데 모든 가지가 어긋남")
            elif viol:
                vs = set(viol)
                alive = [i for i in alive if i not in vs]
                rp["action"] = f"가지 {len(viol)}개 버림"
        rule_points.append(rp)
    # 규칙 사건 대조(판정 그대로)
    def judged_mode(d):
        w = cands(d["what"])
        if len(w) > 1:
            return "후보"
        if w[0] == "D":
            return "D(끝가림)" if d["end_hidden"] else "D"
        return "R"
    ra = [d for d in eng.discs if d["after_riichi"]]
    pc = [d for d in eng.discs if d["post_call"]]
    rule_check = {"riichi_k": riichi_k + 1 if riichi_k is not None else None,
                  "after_riichi": {"n": len(ra), **Counter(judged_mode(d) for d in ra)},
                  "post_call": {"n": len(pc), **Counter(judged_mode(d) for d in pc)},
                  "points": rule_points}
    agg = aggregate(eng, br, alive, sch)
    summ = summarize(agg, eng)
    # 정렬 점수
    sc = [(scores[i][0] if scores[i][0] is not None else -1.0) for i in alive]
    best = max(sc) if sc else None
    best_idx = [i for i, s in zip(alive, sc) if s == best]
    agg_best = aggregate(eng, br, best_idx, sch) if best_idx and len(best_idx) < len(alive) else agg
    sort_res = {"scheme": sch, "best": round(best, 4) if best is not None and best >= 0 else None,
                "worst": round(min(sc), 4) if sc and min(sc) >= 0 else None,
                "mean": round(sum(s for s in sc if s >= 0) / max(1, sum(1 for s in sc if s >= 0)), 4) if sc else None,
                "best_branches": len(best_idx), "best_pairs": f"{scores[best_idx[0]][1]}/{scores[best_idx[0]][2]}" if best_idx else None,
                "best_summary": summarize(agg_best, eng),
                "note": "참고용 — 기본 결과에는 정렬로 가지를 버리지 않는다"}
    summ.update(branches_before=len(br), branches_after=len(alive), count_pruned=eng.count_pruned, died_midway=eng.died,
                end_hidden=eng.n_end_hidden, shuffle=eng.n_shuffle, breaks=len(eng.breaks),
                reveal_order_uncertain=eng.reveal_uncertain)
    res.update(status="ok", summary=summ, prune=prune_log, rule_check=rule_check, sort=sort_res,
               start=agg["start"], turns=agg["turns"], breaks=eng.breaks,
               chunks=[{"name": c["name"], "seg": c["seg"], "ids": list(c["ids"])} for c in eng.chunks],
               errors=errors, warnings=eng.warns)
    if opts is not None:
        opts["widened_events"] = eng.n_widened
        summ["options"] = dict(opts)
    if sort_filter:
        sb = summarize(agg_best, eng)
        sb.update(branches=len(best_idx), of=len(alive))
        pats = {}
        for i in best_idx:
            bp = tuple(bad_pairs(eng, eng.view(br[i][2]), sch))
            pats.setdefault(bp, 0)
            pats[bp] += 1
        first = next(iter(pats)) if pats else ()
        common = set(first)
        for bp in pats:
            common &= set(bp)
        res["sort_filter"] = {
            "best": sort_res["best"], "best_pairs": sort_res["best_pairs"], "best_branches": len(best_idx), "of": len(alive),
            "summary": sb, "start": agg_best["start"], "turns": agg_best["turns"],
            "mismatch_patterns": len(pats),
            "mismatch_first": [{"t": t, "seg": s, "slot": k, "left": a_, "right": b_} for t, s, k, a_, b_ in first],
            "mismatch_common": [{"t": t, "seg": s, "slot": k, "left": a_, "right": b_} for t, s, k, a_, b_ in sorted(common)],
            "note": "정렬 점수가 최고인 가지만 남긴 결과(참고용). 어긋난 쌍은 최고 가지 중 첫 가지 것과 모든 최고 가지에 공통인 것"}
    return res


# ------------------------------------------------------------------ 글
def fmt_hand(x: dict) -> str:
    parts = [" ".join(x["confirmed_tiles"])] if x["confirmed_tiles"] else []
    if x["distinct"] > 1:
        if x.get("candidates") is not None:
            parts.append("+ ?{" + " | ".join(" ".join(c) for c in x["candidates"]) + "}")
        else:
            parts.append(f"+ ?{{{x['distinct']}가지}}")
    if x.get("unknown_in_all"):
        parts.append(f"?×{x['unknown_in_all']}")
    return " ".join(parts) or "-"


def fmt_slots(v: list) -> str:
    v = [("없음" if p is None else str(p)) for p in v]
    return "|".join(v) if v else "-"


def start_lines(start: list) -> list[str]:
    return [f"덩어리 {c['chunk']}{'' if c['seg'] is None else ' (구간 ' + str(c['seg']) + ' 끊김 뒤)'} 시작 손패: {fmt_hand(c)} · 확정 {c['confirmed']}/{c['n']} · 서로 다른 손패 {c['distinct']}"
            for c in start]


def summary_lines(s: dict) -> list[str]:
    return [f"차례 {s['turns']} · 버림 있는 차례 {s['turns_with_discard']} 중 쯔모기리/손에서 정해짐 {s['mode_decided']}"
            f"(쯔모기리 {s['tsumogiri']}, 손에서 {s['tedashi']}) · 손에서 냄 중 나간 칸 한 칸 {s['tedashi_out_one']} · 들어간 칸 한 칸 {s['tedashi_in_one']}",
            f"손패 완전 확정 차례 {s['fully_confirmed']}/{s['turns']} · 확정 장수 평균 {s['confirmed_mean']} 최소 {s['confirmed_min']}"
            f" · 시작 손패 확정 {s['start_confirmed']}/{s['start_n']}(후보 {s['start_distinct']}가지)"]


def turn_lines(turns: list) -> list[str]:
    out = ["순 · 구간 · 뽑음 · 버림(쯔모기리/손에서 k칸) · 들어간 칸 · 뽑기 전 손패(확정 + ?{후보}) · 확정 · [판정]"]
    for x in turns:
        dr = "울기" if x["kind"] == "call" else ("|".join(x["drawn"]) or "-")
        if x["discard"]:
            tiles = ",".join((d["tile"] or "?") + ("*" if d["after_riichi"] else "") for d in x["discard"])
            if x["mode"] == "쯔모기리":
                m = "쯔모기리"
            elif x["mode"] == "손에서":
                m = f"손에서 {fmt_slots(x['out_slots'])}칸"
            else:
                m = f"쯔모기리|손에서 {fmt_slots([p for p in x['out_slots'] if p != 'D'])}칸"
            ds = f"{tiles}({m})"
        else:
            ds = "-"
        tag = "(넣음)" if x["synthetic"] else ("(자동)" if x["auto"] else "")
        out.append(f"{x['t']:2d}{tag} · {x['seg']:3d} · {dr} · {ds} · {fmt_slots(x['in_slots'])} · {fmt_hand(x)} · {x['confirmed']}/{x['n']}"
                   + (f"({x['distinct']}가지)" if x["distinct"] > 1 else "") + f" · [{'; '.join(x['judged'])}]")
    out.append("(* = 리치 뒤 버림. 들어간 칸 '없음' = 그 가지에서는 D 를 버림)")
    return out


def to_text(res: dict, title: str) -> str:
    op = res.get("options")
    out = [f"{res['game']} · {title} · 결과 {res['result']} · 끝 손패 {' '.join(res['final_closed'])} + {res['win_tile']}"
           + (f" · 울기 {' '.join(res['melds'])}" if res["melds"] else "") + f" · 규칙으로 가지 버리기 {'켬' if res['use_rules'] else '끔'}"
           + (f" · place·move.to 넓히기 {op['widen_place']}칸(넓어진 사건 {op.get('widened_events')}) · 정렬 거르기 {'켬' if op['sort_filter'] else '끔'}" if op else "")]
    if res["status"] != "ok":
        out.append(f"상태: {res['status']} — {res.get('overflow')}")
        out += [f"오류: {e}" for e in res["errors"]] + [f"경고: {w}" for w in res["warnings"]]
        return "\n".join(out)
    s = res["summary"]
    sch = res["sort"]["scheme"]
    out += start_lines(res["start"])
    out.append("")
    out += turn_lines(res["turns"])
    out.append("")
    out += summary_lines(s)
    out.append(f"끝 가림 {s['end_hidden']} · shuffle {s['shuffle']} · 끊김 {s['breaks']} · 가지 {s['branches_before']} → {s['branches_after']}"
               f" (중간에 장수로 버림 {s['count_pruned']}, 사건이 안 맞아 사라짐 {s['died_midway']})"
               + (" · 공개 순서 불확실" if s["reveal_order_uncertain"] else ""))
    for p in res["prune"]:
        out.append(f"버린 가지: {p}")
    rc = res["rule_check"]
    out.append(f"규칙 사건 대조(판정 그대로): 리치 뒤 버림 {rc['after_riichi']} · 울기 직후 버림 {rc['post_call']}")
    for p in rc["points"]:
        out.append(f"  구간 {p['seg']} {p['k']}번째 버림 {p['tile']} — {p['rule']}: 판정 {p['judged']}{' 끝가림' if p['end_hidden'] else ''},"
                   f" 어긋난 가지 {p['violating_branches']}/{p['of']}" + (f" → {p['action']}" if p.get("action") else ""))
    so = res["sort"]
    bs = so["best_summary"]
    out.append(f"정렬(끝 손패에서): 무늬 {sch['suit_order']} · 숫자 {'오름' if sch['ascending'] else '내림'}차순 · 가지별 이웃 쌍 맞음 비율 최고 {so['best']}"
               f"({so['best_pairs']}) 최저 {so['worst']} 평균 {so['mean']} · 최고 가지 {so['best_branches']}개만 남기면: 완전 확정 {bs['fully_confirmed']}/{bs['turns']},"
               f" 확정 평균 {bs['confirmed_mean']} 최소 {bs['confirmed_min']}, 시작 확정 {bs['start_confirmed']}/{bs['start_n']}(후보 {bs['start_distinct']}) (참고용)")
    for b in res["breaks"]:
        out.append(f"끊김: 구간 {b['seg']} 사건 {b['event'] + 1} — {b['reason']} · 사이 버림 {b['river_in_gap']} → 덩어리 {b['new_chunk']}({b['new_n']}장)")
    sf = res.get("sort_filter")
    if sf:
        sb = sf["summary"]
        out.append("")
        out.append(f"==== 정렬 최고 가지만 (참고용): 점수 {sf['best']}({sf['best_pairs']}) · 최고 가지 {sf['best_branches']}/{sf['of']}개 ====")
        out += start_lines(sf["start"])
        out.append("")
        out += turn_lines(sf["turns"])
        out.append("")
        out += summary_lines(sb)
        if sf["best"] is not None and sf["best"] < 1.0:
            out.append(f"어긋난 이웃 쌍(최고 가지 중 첫 가지, 어긋남 모양 {sf['mismatch_patterns']}가지): "
                       + " · ".join(f"{m['t']}순(구간 {m['seg']}) {m['slot']}~{m['slot'] + 1}칸 {m['left']}>{m['right']}" for m in sf["mismatch_first"]))
            out.append("모든 최고 가지에 공통: " + (" · ".join(f"{m['t']}순(구간 {m['seg']}) {m['slot']}~{m['slot'] + 1}칸 {m['left']}>{m['right']}"
                                                       for m in sf["mismatch_common"]) or "없음"))
    out += [f"오류: {e}" for e in res["errors"]] + [f"경고: {w}" for w in res["warnings"]]
    return "\n".join(out)


# ------------------------------------------------------------------ 자체 시험(손 계산과 대조)
def _fake(closed, win, river, result="tsumo", melds=None, meld_detail=None, skins=None, riichi=None, before=None):
    segs = []
    for i, r in enumerate(river, 1):
        segs.append({"seg": i, "max_skin": (skins or {}).get(i, 0.5),
                     "river": {"river_new": [{"tile": t[0], "sideways": bool(t[1:])} if isinstance(t, tuple) else {"tile": t} for t in r]}})
    game = {"id": "selftest", "result": result, "riichi": riichi, "river_before_ready": before or [],
            "final_hand": {"closed": closed, "win_tile": win, "melds": melds or [], "meld_detail": meld_detail or []}}
    return game, {"segments": segs}


def _j(*segs):
    return {s["seg"]: {**s, "_file": "test"} for s in segs}


def selftest() -> None:
    ok = 0

    def check(name, got, want):
        nonlocal ok
        assert got == want, f"{name}: {got!r} ≠ {want!r}"
        ok += 1

    # 1) 손패 4장, 버림 3번, place 후보 1번 [3,4]
    #    시작 R [1,2,3,4]. 구간1 draw 5, discard 2칸(9p), place [3|4] → 가 [1,3,5,4] / 나 [1,3,4,5]
    #    구간2 draw 6, discard D(1z). 구간3 draw 7, discard 1칸(7s), place 4 → 가 [3,5,4,7] / 나 [3,4,5,7]
    #    구간4 draw 8, reveal 쯔모: 끝 2s 3s 4s 5s + 6s
    #    가: 3=2s 5=3s 4=4s 7=5s 8=6s 1=7s 2=9p 6=1z → 시작 {7s 9p 2s 4s}
    #    나: 3=2s 4=3s 5=4s 7=5s           → 시작 {7s 9p 2s 3s}
    #    시작 확정 3(2s 7s 9p), 후보 2가지. 1순 손패 = 시작(확정 3), 뽑음 {3s|4s}. 2·3·4순 손패 {2s 3s 4s 7s}/{…}/{2s..5s} 확정 4.
    game, index = _fake(["2s", "3s", "4s", "5s"], "6s", [["9p"], ["1z"], ["7s"], []])
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": 2, "left": 1, "right": 2}, {"kind": "place", "pos": [3, 4]}]},
             {"seg": 2, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D"}]},
             {"seg": 3, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1, "left": 0, "right": 3}, {"kind": "place", "pos": 4}]},
             {"seg": 4, "events": [{"kind": "draw"}, {"kind": "reveal", "order_kept": True}]})
    r = run_game(game, index, jud, n0=4)
    s = r["summary"]
    check("1 가지", (s["branches_before"], s["branches_after"]), (2, 2))
    check("1 시작", (r["start"][0]["confirmed"], r["start"][0]["distinct"], r["start"][0]["candidates"]), (3, 2, [["3s"], ["4s"]]))
    check("1 확정 장수", [x["confirmed"] for x in r["turns"]], [3, 4, 4, 4])
    check("1 1순 뽑음", r["turns"][0]["drawn"], ["3s", "4s"])
    check("1 1순 들어간 칸", r["turns"][0]["in_slots"], [3, 4])
    check("1 3순 손에서 1칸", (r["turns"][2]["mode"], r["turns"][2]["out_slots"]), ("손에서", [1]))
    check("1 완전 확정", (s["fully_confirmed"], s["turns"], s["confirmed_mean"], s["confirmed_min"]), (3, 4, 3.75, 3))
    # 정렬: 가 1순 [7s 9p 2s 4s] 1/1, 2·3순 [7s 2s 3s 4s] 2/3, 4순 [2s 3s 4s 5s] 3/3 → 8/10. 나도 8/10.
    check("1 정렬", (r["sort"]["best"], r["sort"]["best_pairs"], r["sort"]["best_branches"]), (0.8, "8/10", 2))
    check("1 오류 없음", r["errors"], [])

    # 2) 끝 가림: R [1,2], draw 3, discard D 끝가림(9m), 론 공개 1p 2p
    #    가: 3 버림 → R [1,2]=1p 2p.  나: 2(끝 칸) 버림, 3 이 끝 칸에 → R [1,3]: 1=1p 3=2p, 2=9m
    #    시작 {1p 2p} / {1p 9m} → 확정 1, 뽑음 {9m|2p}, 쯔모기리|손에서 2칸, 들어간 칸 2|없음
    game, index = _fake(["1p", "2p"], None, [["9m"], []], result="ron")
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D", "end_hidden": True}]},
             {"seg": 2, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=2)
    check("2 가지", r["summary"]["branches_after"], 2)
    check("2 시작", (r["start"][0]["confirmed"], r["start"][0]["confirmed_tiles"]), (1, ["1p"]))
    check("2 뽑음·버림", (r["turns"][0]["drawn"], r["turns"][0]["mode"], r["turns"][0]["out_slots"], r["turns"][0]["in_slots"]),
          (["9m", "2p"], "둘 다", [2, "D"], [2, None]))
    check("2 끝가림 수", r["summary"]["end_hidden"], 1)

    # 3) 리치 규칙: R [1,2,3]. 구간1 draw 4, discard 1칸(1z 가로 = 리치), place 3 → [2,3,4]
    #    구간2 draw 5, discard [2, D](9m), place 2 → R가지 [2,5,4] / D가지 [2,3,4](place 없음)
    #    구간3 draw 6 쯔모 공개 1p 2p 3p + 4p
    #    R가지: 2=1p 5=2p 4=3p 3=9m → 시작 {1z 1p 9m}.  D가지: 2=1p 3=2p 4=3p 5=9m → 시작 {1z 1p 2p}
    game, index = _fake(["1p", "2p", "3p"], "4p", [[("1z", "s")], ["9m"], []], riichi=True)
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1}, {"kind": "place", "pos": 3}]},
             {"seg": 2, "events": [{"kind": "draw"}, {"kind": "discard", "what": [2, "D"]}, {"kind": "place", "pos": 2}]},
             {"seg": 3, "events": [{"kind": "draw"}, {"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=3)
    check("3 규칙 끔", (r["summary"]["branches_after"], r["start"][0]["confirmed"], r["turns"][1]["confirmed"], r["turns"][2]["confirmed"]), (2, 2, 2, 3))
    check("3 대조", r["rule_check"]["after_riichi"], {"n": 1, "후보": 1})
    r = run_game(game, index, jud, n0=3, use_rules=True)
    check("3 규칙 켬", (r["summary"]["branches_after"], r["start"][0]["confirmed"], r["start"][0]["confirmed_tiles"]), (1, 3, ["1p", "2p", "1z"]))
    # 리치 뒤 손에서 낸 판정(모든 가지 위반) → 버리지 않고 오류
    jud2 = dict(jud)
    jud2[2] = {**jud[2], "events": [{"kind": "draw"}, {"kind": "discard", "what": 2}, {"kind": "place", "pos": 2}]}
    r = run_game(game, index, jud2, n0=3, use_rules=True)
    check("3 모두 위반", (r["summary"]["branches_after"], any("모든 가지가 어긋남" in e for e in r["errors"])), (1, True))

    # 4) shuffle 3칸 → 3! = 6 가지. 시작 R [1,2,3], draw 4, discard D(9s), shuffle [1,2,3], 론 공개 1m 2m 3m
    #    어느 가지든 손패 multiset 은 {1m 2m 3m} → 확정 3, 서로 다른 손패 1
    game, index = _fake(["1m", "2m", "3m"], None, [["9s"], []], result="ron")
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D"}, {"kind": "shuffle", "pos": [1, 2, 3]}]},
             {"seg": 2, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=3)
    check("4 shuffle", (r["summary"]["branches_after"], r["summary"]["shuffle"], r["start"][0]["distinct"], r["start"][0]["confirmed"]), (6, 1, 1, 3))

    # 5) 같은 패 5장: 끝 1m×4 + 버림 1m → 모든 가지 → 버리지 않고 오류
    game, index = _fake(["1m", "1m", "1m", "1m"], None, [["1m"], []], result="ron")
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D"}]}, {"seg": 2, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=4)
    check("5 5장", any("5장 이상이 모든 가지" in e for e in r["errors"]), True)

    # 6) 울기: R [1..5]. 구간1 draw 6, discard D(9m), call [2,3](퐁 7p), discard 1칸(1z) → R [4,5]
    #    구간2 draw 7 쯔모 공개 2s 3s + 4s, 울기 7p 7p 7p(셋째 가로)
    #    번호: 2=7p 3=7p 1=1z 6=9m 4=2s 5=3s → 시작 {1z 7p 7p 2s 3s} 확정 5. 울기 직후 버림 R 1건
    game, index = _fake(["2s", "3s"], "4s", [["9m", "1z"], []], melds=["7p", "7p", "7p"],
                        meld_detail=[{}, {}, {"sideways": True}])
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D"}, {"kind": "call", "meld_pos": [2, 3]},
                                   {"kind": "discard", "what": 1}]},
             {"seg": 2, "events": [{"kind": "draw"}, {"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=5, use_rules=True)
    check("6 울기", (r["summary"]["branches_after"], r["start"][0]["confirmed"], r["rule_check"]["post_call"]), (1, 5, {"n": 1, "R": 1}))
    check("6 차례", [(x["kind"], x["n"], x["confirmed"]) for x in r["turns"]], [("draw", 5, 5), ("call", 5, 5), ("draw", 2, 2)])

    # 7) unknown 끊김: R [1,2]. 구간1 draw 3, discard 1칸(5z), place 2 → [2,3]. 구간2 unknown(강 6z 1장 소모, n_after 2)
    #    → 덩어리 B [4,5]. 구간3 draw 6, discard D(7z). 구간4 공개 1s 2s (론)
    #    덩어리 A 시작: 1=5z, 2=? → 확정 1. 덩어리 B 시작 {1s 2s}. 1순 손패 [1,2] = 5z ? → 확정 1/2
    game, index = _fake(["1s", "2s"], None, [["5z"], ["6z"], ["7z"], []], result="ron")
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1}, {"kind": "place", "pos": 2}]},
             {"seg": 2, "n_after": 2, "events": [{"kind": "unknown", "note": "손바닥 밑"}]},
             {"seg": 3, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D"}]},
             {"seg": 4, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=2)
    check("7 끊김", (len(r["breaks"]), r["breaks"][0]["river_in_gap"], [c["confirmed"] for c in r["start"]]), (1, ["6z"], [1, 2]))
    check("7 1순", (r["turns"][0]["confirmed"], r["turns"][0]["unknown_in_all"]), (1, 1))
    check("7 오류 없음", r["errors"], [])

    # 8) 자동 처리: 손 없는 구간(max_skin 0)의 강 새 패 → draw·discard D 자동 / 손 있는데 판정 없음 → 오류·끊김
    game, index = _fake(["1s", "2s"], None, [["5z"], ["6z"], []], result="ron", skins={1: 0.0})
    jud = _j({"seg": 3, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=2)
    check("8 자동", (r["turns"][0]["auto"], r["turns"][0]["mode"], len(r["breaks"]), any("판정이 없음" in e for e in r["errors"])), (True, "쯔모기리", 1, True))

    # 4b) 같은 칸 shuffle 두 번 → 줄 순서는 여전히 3! = 6 가지(같은 상태·같은 기록은 합침)
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D"}, {"kind": "shuffle", "pos": [1, 2, 3]},
                                   {"kind": "shuffle", "pos": [1, 2, 3]}]},
             {"seg": 2, "events": [{"kind": "reveal"}]})
    game, index = _fake(["1m", "2m", "3m"], None, [["9s"], []], result="ron")
    r = run_game(game, index, jud, n0=3)
    check("4b shuffle 두 번", r["summary"]["branches_after"], 6)

    # 9) 가지 넘침: place 후보 4개 × 3번 = 64 > 상한 50 → 구간 3 에서 넘침
    game, index = _fake([f"{i}m" for i in range(1, 5)], None, [["1z"], ["2z"], ["3z"], []], result="ron")
    jud = _j(*[{"seg": i, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1}, {"kind": "place", "pos": [1, 2, 3, 4]}]} for i in (1, 2, 3)],
             {"seg": 4, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=4, limit=50)
    check("9 넘침", (r["status"], r["overflow"]["where"].startswith("구간 3")), ("가지 넘침", True))
    # 10) --widen-place 1: conf high 한 값은 그대로, low 한 값은 ±1
    #     R [1..4]. 구간1 draw, discard 1(high), place 4(high) → 넓히지 않음. 구간2 draw, discard 1, place 3(low) → 2|3|4 → 3가지
    game, index = _fake(["1m", "2m", "3m", "4m"], None, [["1z"], ["2z"], []], result="ron")
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1, "conf": "high"}, {"kind": "place", "pos": 4, "conf": "high"}]},
             {"seg": 2, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1}, {"kind": "place", "pos": 3, "conf": "low"}]},
             {"seg": 3, "events": [{"kind": "reveal"}]})
    r0 = run_game(game, index, jud, n0=4)
    r = run_game(game, index, jud, n0=4, widen=1)
    check("10 넓히기", (r0["summary"]["branches_after"], r["summary"]["branches_after"], r["turns"][0]["in_slots"], r["turns"][1]["in_slots"],
                       r["options"]["widened_events"], "options" in r0), (1, 3, [4], [2, 3, 4], 1, False))

    # 11) --sort-filter: R [1,2,3]. 구간1 draw 4, discard 1(9p), place [1|3] → 가 [4,2,3] / 나 [2,3,4]
    #     구간2 draw 5, discard D(9m). 구간3 draw 6, discard 1(4s), place 3 → 가 [2,3,6] / 나 [3,4,6]. 구간4 론 1s 2s 3s
    #     가: 2=1s 3=2s 6=3s 4=4s 1=9p → 1순 [9p 1s 2s] 1/1, 2·3순 [4s 1s 2s] 1/2 → 3/5
    #     나: 3=1s 4=2s 6=3s 2=4s 1=9p → 1순 [9p 4s 1s] 0/1, 2·3순 [4s 1s 2s] 1/2 → 2/5. 최고 = 가 하나, 시작 {9p 1s 2s}
    game, index = _fake(["1s", "2s", "3s"], None, [["9p"], ["9m"], ["4s"], []], result="ron")
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1}, {"kind": "place", "pos": [1, 3]}]},
             {"seg": 2, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D"}]},
             {"seg": 3, "events": [{"kind": "draw"}, {"kind": "discard", "what": 1}, {"kind": "place", "pos": 3}]},
             {"seg": 4, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=3, sort_filter=True)
    sf = r["sort_filter"]
    check("11 정렬 거르기", (r["summary"]["branches_after"], r["start"][0]["distinct"], sf["best"], sf["best_pairs"], sf["best_branches"],
                          sf["start"][0]["confirmed_tiles"], sf["turns"][0]["in_slots"],
                          [(m["t"], m["seg"], m["slot"], m["left"], m["right"]) for m in sf["mismatch_first"]]),
          (2, 2, 0.6, "3/5", 1, ["9p", "1s", "2s"], [1], [(2, 2, 1, "4s", "1s"), (3, 3, 1, "4s", "1s")]))

    # 12) D 를 버린 가지의 place = 마지막 칸 패를 옮김. R [1,2,3], draw 4, discard [3, D](9m), place 1
    #     R가지: 3 버림, 4 를 1칸 → (4,1,2), 들어간 칸 1.  D가지: 4 버림, 마지막 칸 3 을 1칸으로 → (3,1,2), 들어간 칸 없음
    #     (고치기 전에는 D가지가 (1,2,3) 그대로). R 후보가 마지막 칸이 아니면([2, D]) 지금처럼 넘기고 경고.
    #     끝 가림 + place 1: 가 D 버림 → (3,1,2) / 나 3 버림·4 가 끝 칸 → (1,2,4) → 4 를 1칸 → (4,1,2), 들어간 칸 1
    def rows(evs):
        game, index = _fake(["1p", "2p", "3p"], None, [["9m"]], result="ron")
        errs, warns = [], []
        plan = build_plan(index, _j({"seg": 1, "events": evs}), errs, warns)
        eng = Engine(game, index, plan, 3)
        eng.warns = warns + eng.warns
        return sorted(R for R, _, _ in eng.run()), eng.warns
    got, _ = rows([{"kind": "draw"}, {"kind": "discard", "what": [3, "D"]}, {"kind": "place", "pos": 1}])
    check("12 마지막 칸 옮김", got, [(3, 1, 2), (4, 1, 2)])
    got, w = rows([{"kind": "draw"}, {"kind": "discard", "what": [2, "D"]}, {"kind": "place", "pos": 1}])
    check("12 마지막 칸 아님", (got, any("마지막 칸이 아님" in x for x in w)), ([(1, 2, 3), (4, 1, 3)], True))
    got, _ = rows([{"kind": "draw"}, {"kind": "discard", "what": "D", "end_hidden": True}, {"kind": "place", "pos": 1}])
    check("12 끝 가림", got, [(3, 1, 2), (4, 1, 2)])
    game, index = _fake(["1p", "2p", "3p"], None, [["9m"], []], result="ron")
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": [3, "D"]}, {"kind": "place", "pos": 1}]},
             {"seg": 2, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=3)
    check("12 들어간 칸", (r["turns"][0]["in_slots"], r["turns"][0]["mode"]), ([1, None], "둘 다"))
    jud = _j({"seg": 1, "events": [{"kind": "draw"}, {"kind": "discard", "what": "D", "end_hidden": True}, {"kind": "place", "pos": 1}]},
             {"seg": 2, "events": [{"kind": "reveal"}]})
    r = run_game(game, index, jud, n0=3)
    check("12 끝 가림 들어간 칸", r["turns"][0]["in_slots"], [1, None])
    print(f"자체 시험 {ok}건 통과")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game", nargs="?")
    ap.add_argument("judgments", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--use-rules", action="store_true")
    ap.add_argument("--name")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--widen-place", type=int, default=0, help="place.pos·move.to 후보를 양쪽으로 K칸 넓힘(conf high 한 값은 그대로)")
    ap.add_argument("--sort-filter", action="store_true", help="정렬 점수 최고 가지만 남긴 요약 블록을 더 냄(참고용)")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.game or not a.judgments:
        ap.error("판 id 와 판정 파일이 필요함")
    od = hc.OUT / a.game
    game = hc.jload(od / "game.json")
    index = hc.jload(od / "index.json")
    jud, meta, pre = load_judgments(a.judgments, a.game)
    n0 = game.get("start_tiles")
    if n0 is None:
        n0s = {hc.jload(p).get("start_tiles") for p in a.judgments} - {None}
        n0 = n0s.pop() if len(n0s) == 1 else 13
    res = run_game(game, index, jud, n0=n0, use_rules=a.use_rules, pre_errors=pre, widen=a.widen_place, sort_filter=a.sort_filter)
    res["judge_files"] = meta
    name = a.name or "+".join(Path(p).stem for p in a.judgments)
    if a.use_rules:
        name += "_rules"
    if a.widen_place:
        name += f"_w{a.widen_place}"
    if a.sort_filter:
        name += "_sort"
    outd = Path(a.out) if a.out else od
    outd.mkdir(parents=True, exist_ok=True)
    hc.jsave(outd / f"replay2_{name}.json", res)
    txt = to_text(res, "판정 " + ", ".join(Path(p).name for p in a.judgments))
    (outd / f"replay2_{name}.txt").write_text(txt, encoding="utf-8")
    print(txt)
    print(f"\n→ {outd / f'replay2_{name}.json'}")


if __name__ == "__main__":
    main()
