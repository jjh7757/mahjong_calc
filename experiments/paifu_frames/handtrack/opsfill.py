"""행동(동사 줄)을 정답으로 주면 코드가 칸 번호를 채울 수 있나 — 상한 재기(2026-11-18, 계획서 3단계 "추가 19"). Gemini 호출 없음.

사용자 제안(11-18): "밀다 · 손에 들다 · 버리다 같은 행동을 분류하는 LLM 과 2칸 · 4칸 같은 수를 다루는 LLM 을 따로".
세션 의견: 수는 LLM 말고 코드(칸 틀 도구)가 → 그러면 행동 LLM 이 완벽할 때 코드가 수를 얼마나 맞히는지가 이 구조의 상한이다.

  python -X utf8 opsfill.py check                 # 동작 정답(사용자 칸 동작 · slotsim.DEMO · 메모에서 옮겨 적은 것)을 굴려 정답 값과 같은지
  python -X utf8 opsfill.py run [--v2] [--tau 0] [--dir] [--ids a,b] [--show]   # 동사 줄만 주고 채워서 채점 → _work/opsfill_1118/result[_v2][_dir][_tauN].json

방법: 정답 동작 목록에서 숫자 · 미는 쪽을 지운 동사 줄(draw · pick · place · move · swap · push · discard · tidy, 손에 쥠 = drawh · discardh)에
들어갈 수 있는 모든 칸 번호를 채워 굴리고, 걸음마다의 칸 참/빔을 slotgrid.track 의 프레임별 칸 상태(F 참 / E 빔 / ? 모름)에 순서를 지켜 맞댄다
(프레임마다 어느 걸음의 모습인지 — 뒤로 못 감, 안 보인 걸음은 건너뜀, 또렷이 보인 칸이 어긋나면 1점). 가장 낮은 점수의 채움들이 내는
결과(종류 · 원래 몇 번째 버림 k · 뽑은 패 자리 j)가 하나뿐이고 정답이면 "맞음", 여럿이면 "못 정함", 하나뿐인데 틀리면 "조용한 틀림".
칸은 -1 ~ N+2(-1 은 칸 틀 도구에 없어 늘 "모름"). 고정본 slotgrid.py · slotsim.py 는 불러 쓰기만 한다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import slotgrid as sg  # noqa: E402
import slotsim as ss  # noqa: E402
import turncut as tc  # noqa: E402

OUT = hc.WORK / "opsfill_1118"
D = 99
PUSH_K = (1, 2)
NODE_CAP = 1_500_000
INF = 1e9
# v1 = 계획서 "추가 19" 에 미리 적은 방식. v2(--v2) = v1 결과를 본 뒤 모형의 흠 넷을 고친 것(본 판을 보고 고침 — 시험 아님):
#   ① tidy 뒤 줄이 놓이는 자리를 0 · 1 · 2번 칸 시작 가운데서 고름(실제로는 왼쪽 끝에 붙인 채 0 ~ 12 에 남기도 한다)
#   ② 한 장도 안 보인 걸음은 0.5점(공짜로 건너뛰면 "1번을 버리고 5번을 1번으로" 같은 채움이 정답과 같은 점수가 된다)
#   ③ move 는 든 순간(두 칸 다 빔)을 거쳐도 된다  ④ 칸 -1 은 줄 덩어리가 거기까지 뻗었으면 참, 0번 칸이 보이면 빔
EPS = 0.0
MID = False
TIDY_OFF = (1,)
NEG1 = False
CARRY = 0.0   # 추가 21(--carry W): 가려진 칸을 직전에 본 값으로 메우고 어긋나면 W 점. 0 = 모름(v1 · v2)

# 사용자 메모(truth_final 의 note)를 세션이 칸 동작으로 옮겨 적은 것 — check 에서 굴려 정답 값(kind · k_id · j_closed)과 같아야 쓴다.
MEMO_OPS = {
    "r16_d01": "draw 14; discard 13; push 11 R; move 14 11; tidy",      # 13패 버림 → 11 · 12패 오른쪽으로 밀어 11칸에 쯔모패
    "r16_d03": "draw 14; discard 9; tidy",
    "r16_d04": "draw 14; discard 12; tidy",
    "r16_d06": "draw 14; discard 13; tidy",
    "r16_d12": "draw 14; discard 12; tidy",
    "r17_d03": "draw 0; discard 7; push 4 R; move 0 4; tidy",           # 왼쪽 끝에 두고 버림 → 오른쪽으로 밀어 칸 확보 → 쯔모패 넣음
    "r17_d08": "draw 14; discard 12; push 5 R; move 14 5; tidy",        # 12번째 버림 → 5번째부터 오른쪽으로 밀어 5번째에
    "r17_d10": "draw 0; discard 13; tidy",                              # 메모 없음 — HANDOFF 의 "왼쪽 끝 붙임"
    "r19_d03": "draw 14; discard 13; tidy",
    "r19_d04": "draw 14; discard 11; tidy",
    "r19_d03b": "draw 14; pick 13; push 14 L; discard hand; push 4 R; move 14 4; tidy",   # 13번째를 들고 쯔모패를 왼쪽으로 밀어 정리 → 든 패 버림 → 쯔모패를 4번째에
}
NO_OPS = {"r12_d06": "메모 없음", "r19_d07": "메모대로 굴리면 정답 값과 다름"}
GAMES = ["r12_131655", "r16_135321", "r17_140450", "r19_142013", "r13_132644"]
LAST = {"r12_131655": "r12_d06", "r16_135321": "r16_d16", "r17_140450": "r17_d11", "r19_142013": "r19_d07", "r13_132644": "r13_d09"}   # 리치 선언 차례까지


# ------------------------------------------------------------------ 가벼운 칸 모형(slotsim 과 같은 규칙, 칸 -1 ~ n+2)
def parse(text: str) -> list:
    out = []
    for raw in text.replace("\n", ";").split(";"):
        w = raw.split()
        if not w:
            continue
        op, a = w[0].lower(), w[1:]
        if op == "draw":
            out.append(("drawh", ()) if a[0] == "hand" else ("draw", (int(a[0]),)))
        elif op == "discard":
            out.append(("discardh", ()) if a[0] == "hand" else ("discard", (int(a[0]),)))
        elif op == "pick":
            out.append(("pick", (int(a[0]),)))
        elif op == "place":
            out.append(("place", (int(a[0]), (D if a[1] == "D" else int(a[1])) if len(a) > 1 else None)))
        elif op in ("move", "swap"):
            out.append((op, (int(a[0]), int(a[1]))))
        elif op == "push":
            out.append(("push", (int(a[0]), a[1].upper(), int(a[2]) if len(a) > 2 else 1)))
        elif op == "tidy":
            out.append(("tidy", ()))
        else:
            raise ValueError(raw)
    return out


def apply(st, verb: str, args, n: int):
    """st = (cells, held, disc) — cells[i] 는 칸 i-1(칸 -1 ~ n+2). 못 하는 동작이면 None."""
    cells, held, disc = st
    C = len(cells)
    c = list(cells)
    if verb == "draw":
        s = args[0] + 1
        if c[s]:
            return None
        c[s] = D
        return tuple(c), held, disc
    if verb == "drawh":
        return cells, held + (D,), disc
    if verb == "pick":
        s = args[0] + 1
        if not c[s]:
            return None
        t, c[s] = c[s], 0
        return tuple(c), held + (t,), disc
    if verb == "place":
        s, t = args[0] + 1, args[1]
        if c[s] or not held:
            return None
        if t is None:
            if len(held) != 1:
                return None
            t = held[0]
        if t not in held:
            return None
        h = list(held)
        h.remove(t)
        c[s] = t
        return tuple(c), tuple(h), disc
    if verb == "move":
        x, y = args[0] + 1, args[1] + 1
        if not c[x] or c[y]:
            return None
        c[y], c[x] = c[x], 0
        return tuple(c), held, disc
    if verb == "swap":
        x, y = args[0] + 1, args[1] + 1
        if not c[x] or not c[y]:
            return None
        c[x], c[y] = c[y], c[x]
        return tuple(c), held, disc
    if verb == "push":
        f, side, k = args[0] + 1, args[1], args[2]
        d = 1 if side == "R" else -1
        if not c[f]:
            return None
        run = [f]
        while 0 <= run[-1] + d < C and c[run[-1] + d]:
            run.append(run[-1] + d)
        for _ in range(k):
            head = run[-1] + d
            if not 0 <= head < C or c[head]:
                return None
            for s in reversed(run):
                c[s + d], c[s] = c[s], 0
            run = [s + d for s in run]
        return tuple(c), held, disc
    if verb == "discard":
        s = args[0] + 1
        if disc is not None or not c[s]:
            return None
        t, c[s] = c[s], 0
        return tuple(c), held, t
    if verb == "discardh":
        if disc is not None or len(held) != 1:
            return None
        return cells, (), held[0]
    if verb == "tidy":
        o = [x for x in c if x]
        off = args[0] if args else 1
        if len(o) > n + 1 or off + 1 + len(o) > C:
            return None
        return tuple([0] * (off + 1) + o + [0] * (C - off - 1 - len(o))), held, disc
    raise ValueError(verb)


def succ(st, verb: str, n: int, side: str | None = None) -> list:
    """그 동사에 들어갈 수 있는 모든 숫자(칸 번호 -1 ~ n+2) → [(args, 새 상태)]."""
    cells, held, _ = st
    C = len(cells)
    full = [i - 1 for i in range(C) if cells[i]]
    empty = [i - 1 for i in range(C) if not cells[i]]
    if verb in ("drawh", "discardh"):
        cand = [()]
    elif verb == "tidy":
        cand = [(o,) for o in TIDY_OFF]
    elif verb == "draw":
        cand = [(s,) for s in empty]
    elif verb in ("pick", "discard"):
        cand = [(s,) for s in full]
    elif verb == "place":
        cand = [(s, t) for s in empty for t in sorted(set(held))]
    elif verb == "move":
        cand = [(a, b) for a in full for b in empty]
    elif verb == "swap":
        cand = [(a, b) for i, a in enumerate(full) for b in full[i + 1:]]
    elif verb == "push":
        cand = [(f, d, k) for f in full for d in ((side,) if side else ("L", "R")) for k in PUSH_K]
    else:
        raise ValueError(verb)
    out, seen = [], set()
    for a in cand:
        s2 = apply(st, verb, a, n)
        if s2 is not None and (a, s2) not in seen:
            seen.add((a, s2))
            out.append((a, s2))
    return out


def start(n: int):
    return tuple([0, 0] + list(range(1, n + 1)) + [0, 0]), (), None


def result(st, n: int):
    cells, held, disc = st
    o = [x for x in cells if x]
    if held or disc is None or len(o) != n:
        return None
    if disc == D:
        return ("tsumogiri", None, None)
    return ("hand", disc, o.index(D) + 1)


def bits(st):
    cells, held, disc = st
    return tuple(1 if x else 0 for x in cells), len(held), disc is not None


def bstate(st):
    """참/빔만 남긴 상태(같은 규칙으로 굴릴 수 있게 값 1 로)."""
    b, h, d = bits(st)
    return b, (1,) * h, (1 if d else None)


# ------------------------------------------------------------------ 프레임과 맞대기
class Obs:
    def __init__(self, tr: list):
        m = {"F": 1, "E": 0, "?": -1}
        neg = lambda f: -1 if not NEG1 else 1 if any(a <= -1 <= b for a, b in f["spans"]) else 0 if f["st"][0] != "?" else -1  # noqa: E731
        self.O = np.array([[neg(f)] + [m[x] for x in f["st"]] for f in tr], dtype=np.int8)   # 칸 -1 은 칸 틀 도구에 없다 → v1 은 늘 모름
        self.W = (self.O != -1).astype(np.float64)       # 칸마다 어긋남 무게: 또렷이 본 칸 1 · 모름 0
        if CARRY:                                        # 추가 21: 모름 = 그 칸을 마지막으로 또렷이 본 값, 어긋나면 CARRY 점
            last = np.full(self.O.shape[1], -1, np.int8)
            for g in range(len(self.O)):
                seen = self.O[g] != -1
                last[seen] = self.O[g][seen]
                fill_ = (~seen) & (last != -1)
                self.O[g][fill_] = last[fill_]
                self.W[g][fill_] = CARRY
        self.F = len(tr)
        self._mc: dict = {}

    def mc(self, b: tuple) -> np.ndarray:
        """Mc[g] = 프레임 0 ~ g-1 을 칸 모양 b 로 설명할 때의 어긋남 합(길이 F+1)."""
        v = self._mc.get(b)
        if v is None:
            mis = (self.W * (self.O != np.array(b, dtype=np.int8))).sum(1)
            v = self._mc[b] = np.concatenate([[0.0], np.cumsum(mis)])
        return v


def fwd(A: np.ndarray, m: np.ndarray, eps: float) -> np.ndarray:
    """A[g] = 프레임 0 ~ g-1 을 앞 걸음들에 맞댄 점수 → 이 걸음(칸 모양의 Mc = m)까지. 프레임을 하나도 안 받으면 eps."""
    X = np.minimum.accumulate(A - m)
    return np.minimum(A + eps, m + np.concatenate([[INF], X[:-1]]))


def through(m: np.ndarray, eps: float, Cn: np.ndarray) -> np.ndarray:
    """V[g] = 프레임 g ~ 끝을 이 걸음과 그 뒤(Cn)에 맞댄 가장 낮은 점수."""
    Y = np.minimum.accumulate((m + Cn)[::-1])[::-1]
    return np.minimum(Cn + eps, np.concatenate([Y[1:], [INF]]) - m)


def mid_bits(st, verb: str, args):
    """move 의 든 순간(떠난 칸도 놓을 칸도 빔) — v2 에서만."""
    if not MID or verb != "move":
        return None
    b = list(bits(st)[0])
    b[args[0] + 1] = 0
    return tuple(b)


def steps_of(seq: list, n: int):
    """숫자까지 적힌 동작 줄 → [(칸 모양, 건너뛸 때 점수)] (못 굴리면 None)."""
    st = start(n)
    out = [(bits(st)[0], EPS)]
    for v, x in seq:
        mb = mid_bits(st, v, x)
        st = apply(st, v, x, n)
        if st is None:
            return None
        if mb:
            out.append((mb, 0.0))
        out.append((bits(st)[0], EPS))
    return out


def path_cost(obs: Obs, steps: list) -> float:
    A = np.full(obs.F + 1, INF)
    A[0] = 0.0
    for b, e in steps:
        A = fwd(A, obs.mc(b), e)
    return float(A[-1])


def shifted(seq: list, o: int) -> list:
    """정답 동작의 tidy 를 o번 칸 시작으로 두고 그 뒤 칸 번호를 같이 옮긴다."""
    out, d = [], 0
    for v, x in seq:
        if v == "tidy":
            out.append((v, (o,)))
            d = o - 1
        elif v in ("draw", "pick", "discard"):
            out.append((v, (x[0] + d,)))
        elif v == "place":
            out.append((v, (x[0] + d, x[1])))
        elif v in ("move", "swap"):
            out.append((v, (x[0] + d, x[1] + d)))
        elif v == "push":
            out.append((v, (x[0] + d, x[1], x[2])))
        else:
            out.append((v, x))
    return out


def fill(verbs: list, sides: list, n: int, obs: Obs, tau: float):
    """동사 줄을 채운다 → (가장 낮은 점수, {결과: (점수, 채움 예)}, 본 마디 수, 잘렸나)."""
    L, F = len(verbs), obs.F
    memo: dict = {}

    def back(i: int, bst) -> np.ndarray:
        """걸음 i 의 칸 모양 bst 부터 프레임 g ~ 끝을 맞대는 가장 낮은 점수(길이 F+1)."""
        key = (i, bst)
        v = memo.get(key)
        if v is not None:
            return v
        Cn = np.full(F + 1, INF)
        if i == L:
            b, h, d = bst
            if (not h) and d is not None and sum(b) == n:
                Cn[F] = 0.0
        else:
            seen = set()
            for a, s2 in succ(bst, verbs[i], n, sides[i]):
                s2, mb = bstate(s2), mid_bits(bst, verbs[i], a)
                if (s2, mb) in seen:
                    continue
                seen.add((s2, mb))
                e = back(i + 1, s2)
                Cn = np.minimum(Cn, through(obs.mc(mb), 0.0, e) if mb else e)
        v = memo[key] = through(obs.mc(bst[0]), EPS, Cn)
        return v

    s0 = start(n)
    best = float(back(0, bstate(s0))[0])
    if best >= INF / 2:
        return None, {}, 0, False
    A0 = np.full(F + 1, INF)
    A0[0] = 0.0
    res: dict = {}
    nodes, capped = 0, False
    visited = set()
    stack = [(0, s0, fwd(A0, obs.mc(bits(s0)[0]), EPS), [])]
    while stack:
        i, st, A, path = stack.pop()
        nodes += 1
        if nodes > NODE_CAP:
            capped = True
            break
        if i == L:
            r = result(st, n)
            if r is not None and A[-1] <= best + tau + 1e-6 and (r not in res or A[-1] < res[r][0]):
                res[r] = (float(A[-1]), path)
            continue
        for a, s2 in succ(st, verbs[i], n, sides[i]):
            mb = mid_bits(st, verbs[i], a)
            e = back(i + 1, bstate(s2))
            if mb:
                e = through(obs.mc(mb), 0.0, e)
            if float(np.min(A + e)) > best + tau + 1e-6:
                continue
            A2 = fwd(fwd(A, obs.mc(mb), 0.0), obs.mc(bits(s2)[0]), EPS) if mb else fwd(A, obs.mc(bits(s2)[0]), EPS)
            key = (i + 1, s2, A2.tobytes())
            if key in visited:
                continue
            visited.add(key)
            stack.append((i + 1, s2, A2, path + [(verbs[i], a)]))
    return best, res, nodes, capped


# ------------------------------------------------------------------ 자료
def frames_of(gid: str, t: dict, det: dict):
    n = t["n_calc"]
    w0, w1 = sg.window(t)
    frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
    an = sg.anchor(frs, n)
    return (sg.track(frs, n, an) if an else None), n


def load_all():
    truth = dict(hc.jload(tc.BASE / "truth_final.json"))
    r13 = hc.jload(hc.WORK / "slotgrid_1117" / "truth_r13.json")
    truth.update(r13)
    ops = {k: (v["ops"], "사용자") for k, v in r13.items() if v.get("ops")}
    ops.update({tid: (o, "DEMO") for _, tid, o in ss.DEMO if tid})
    ops.update({k: (v, "메모") for k, v in MEMO_OPS.items()})
    reads = {}
    for name in ("read_look.json", "read_r13_look.json"):
        f = hc.WORK / "slotgrid_1117" / name
        if f.exists():
            reads.update({r["id"]: r for r in hc.jload(f)["rows"]})
    turns = []
    for gid in GAMES:
        for t in tc.turns_of(gid):
            turns.append((gid, t))
            if t["id"] == LAST[gid]:
                break
    return truth, ops, reads, turns


def fmt_ops(path: list) -> str:
    def one(v, a):
        if v == "drawh":
            return "draw hand"
        if v == "discardh":
            return "discard hand"
        if v == "place":
            return f"place {a[0]} {'D' if a[1] == D else a[1]}"
        if v == "push":
            return f"push {a[0]} {a[1]}" + (f" {a[2]}" if a[2] != 1 else "")
        if v == "tidy":
            return "tidy" + (f"@{a[0]}" if a and a[0] != 1 else "")
        return " ".join([v] + [str(x) for x in a])
    return "; ".join(one(v, a) for v, a in path)


def cmd_check(_a):
    truth, ops, _, turns = load_all()
    bad = 0
    for gid, t in turns:
        tid = t["id"]
        u = truth[tid]
        if u["kind"] != "hand":
            continue
        if tid not in ops:
            print(f"  {tid:9s} 동작 정답 없음 — {NO_OPS.get(tid, '?')}")
            continue
        text, src = ops[tid]
        r = ss.run_ops(text, t["n_calc"]).result()
        st = start(t["n_calc"])
        for v, a in parse(text):
            st = apply(st, v, a, t["n_calc"])
            if st is None:
                break
        mine = result(st, t["n_calc"]) if st else None
        ok = (r["kind"], r["k_id"], r["j_closed"]) == (u["kind"], u.get("k_id"), u.get("j_closed")) == mine
        bad += not ok
        print(f"  {tid:9s} [{src}] {text}  → slotsim {r['kind'][:1]} {r['k_id']} {r['j_closed']} · 가벼운 모형 {mine} · 정답 {u.get('k_id')} {u.get('j_closed')} {'같음' if ok else '**다름**'}")
    print("다름", bad)


def cmd_run(a):
    global EPS, MID, TIDY_OFF, NEG1, CARRY
    if a.v2:
        EPS, MID, TIDY_OFF, NEG1 = 0.5, True, (0, 1, 2), True
    CARRY = a.carry
    truth, ops, reads, turns = load_all()
    ids = set(a.ids.split(",")) if a.ids else None
    dets: dict = {}
    rows, n_tsumo = [], 0
    for gid, t in turns:
        tid = t["id"]
        u = truth[tid]
        if ids and tid not in ids:
            continue
        if u["kind"] != "hand":
            n_tsumo += 1
            continue
        rd = reads.get(tid)
        look_ok = bool(rd and rd.get("kind") == "hand" and rd.get("k") == u["k_id"] and rd.get("j") == u["j_closed"])
        if tid not in ops:
            rows.append({"id": tid, "verdict": "동작 없음", "look_ok": look_ok})
            print(f"  {tid:9s} 동작 정답 없음({NO_OPS.get(tid, '?')}) — 뺌 · 줄글 읽기 {'✓' if look_ok else '✗'}")
            continue
        if gid not in dets:
            dets[gid] = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
        tr, n = frames_of(gid, t, dets[gid])
        if tr is None:
            rows.append({"id": tid, "verdict": "틀 없음", "look_ok": look_ok})
            print(f"  {tid:9s} 시작 줄을 못 잡음")
            continue
        obs = Obs(tr)
        seq = parse(ops[tid][0])
        verbs = [v for v, _ in seq]
        sides = [x[1] if (v == "push" and a.dir) else None for v, x in seq]
        t_cost = min(path_cost(obs, sp) for sp in (steps_of(shifted(seq, o), n) for o in TIDY_OFF) if sp)
        best, res, nodes, capped = fill(verbs, sides, n, obs, a.tau)
        want = ("hand", u["k_id"], u["j_closed"])
        keys = sorted(res, key=lambda r: (res[r][0], str(r)))
        if capped:
            verdict = "못 정함(잘림)"
        elif len(keys) == 1:
            verdict = "맞음" if keys[0] == want else "조용한 틀림"
        else:
            verdict = "못 정함"
        kind = "끝 붙임" if len(verbs) == 3 else "끼움 · 옮김"
        row = {"id": tid, "src": ops[tid][1], "verbs": " ".join(verbs), "class": kind, "frames": obs.F, "best": best, "truth_cost": t_cost, "n_results": len(keys),
               "truth_in": want in res, "verdict": verdict, "capped": capped, "nodes": nodes, "look_ok": look_ok,
               "results": [{"k": r[1], "j": r[2], "kind": r[0], "cost": res[r][0], "ops": fmt_ops(res[r][1])} for r in keys[:12]]}
        rows.append(row)
        show = " ".join(f"{r[1]}·{r[2]}" if r[0] == "hand" else "쯔모기리" for r in keys[:8]) + (" …" if len(keys) > 8 else "")
        print(f"  {tid:9s} [{ops[tid][1]:3s}] {' '.join(verbs):55s} 프레임 {obs.F:3d} · 최저 {best:5.1f} · 정답 동작 {t_cost:5.1f} · 결과 {len(keys):3d}가지"
              f"{'(잘림)' if capped else ''} · 정답 {want[1]}·{want[2]} {'안에 있음' if want in res else '**없음**'} → {verdict} | 줄글 {'✓' if look_ok else '✗'}"
              + (f"\n      후보: {show}" if a.show or len(keys) > 1 or verdict == "조용한 틀림" else ""))
        if a.show:
            for r in keys[:4]:
                print(f"      {r[1]}·{r[2]}  {res[r][0]:.1f}점  {fmt_ops(res[r][1])}")
    done = [r for r in rows if "verbs" in r]
    for name, sel in (("전체", done), ("끝 붙임", [r for r in done if r["class"] == "끝 붙임"]), ("끼움 · 옮김", [r for r in done if r["class"] != "끝 붙임"])):
        if not sel:
            continue
        und = [r["n_results"] for r in sel if r["verdict"].startswith("못 정함")]
        print(f"{name}: {len(sel)}차례 · 맞음 {sum(r['verdict'] == '맞음' for r in sel)} · 조용한 틀림 {sum(r['verdict'] == '조용한 틀림' for r in sel)} · 못 정함 {len(und)}"
              f"(정답이 후보 안 {sum(r['truth_in'] for r in sel if r['verdict'].startswith('못 정함'))}"
              + (f" · 후보 수 중앙 {float(np.median(und)):.0f} · 최대 {max(und)}" if und else "") + f") · 같은 차례 줄글 읽기 맞음 {sum(r['look_ok'] for r in sel)}")
    print(f"쯔모기리 {n_tsumo}차례는 행동을 주면 숫자가 없어 거저 맞음 · 동작 정답이 없어 뺀 차례 {sum(r['verdict'] == '동작 없음' for r in rows)}")
    OUT.mkdir(parents=True, exist_ok=True)
    name = "result" + ("_v2" if a.v2 else "") + ("_dir" if a.dir else "") + (f"_tau{a.tau:g}" if a.tau else "") + (f"_carry{a.carry:g}" if a.carry else "") + ".json"
    if not ids:
        hc.jsave(OUT / name, {"v2": a.v2, "eps": EPS, "carry": a.carry, "tidy_off": TIDY_OFF, "tau": a.tau, "dir": a.dir, "push_k": PUSH_K, "tsumogiri": n_tsumo, "rows": rows})
        print("→", OUT / name)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check")
    p = sp.add_parser("run")
    p.add_argument("--tau", type=float, default=0.0, help="가장 낮은 점수에서 이만큼까지는 같은 점수로 친다")
    p.add_argument("--dir", action="store_true", help="미는 쪽(L/R)도 정답으로 준다")
    p.add_argument("--v2", action="store_true", help="v1 결과를 본 뒤 고친 모형(tidy 자리 · 안 보인 걸음 0.5점 · move 든 순간 · 칸 -1)")
    p.add_argument("--carry", type=float, default=0.0, help="추가 21: 가려진 칸 = 직전에 본 값, 어긋나면 이 점수(0 = 모름)")
    p.add_argument("--ids")
    p.add_argument("--show", action="store_true")
    a = ap.parse_args()
    {"check": cmd_check, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
