"""칸 상태 모형 — 한 차례의 손 동작을 칸(0 ~ N+2) 위에서 굴린다(2026-11-17, 사용자 제안: "0 · 15 임시칸, 1~14 손패칸, 칸마다 찼는지").

  python -X utf8 slotsim.py demo                      # 사용자 예 + 오늘 문제였던 차례들을 굴려 정답(truth_final)과 맞대기
  python -X utf8 slotsim.py run "draw 14; push 8 R; move 15 8; discard 2; tidy" [--n 13]

칸: 1 ~ N = 차례를 시작할 때 손패(왼쪽부터), N+1 = 뽑은 패를 오른쪽 끝에 붙이는 칸 · 0 = 왼쪽 끝에 붙이는 칸, -1 과 N+2 = 양 끝 임시칸.
손패가 13장이면 -1 ~ 15(11-17 처음엔 0 ~ 15 — 왼쪽에 붙이는 사람 때문에 -1 을 더함, 예전 번호는 그대로 맞음).
칸에는 패 이름이 들어간다: 차례 시작 때 번호 "1" ~ "N", 뽑은 패 "D". 찼는지(0/1)는 여기서 나온다(bits).
패 이름은 차례가 끝날 때까지 안 바뀐다 — 밀려서 칸이 달라져도 "원래 몇 번째 패" 는 그대로 따라간다.
"손"(held) = 집어 들어 어느 칸에도 없는 패. 두 장을 한꺼번에 빼는 동작도 임시칸을 늘리지 않고 적는다.

동작(칸 번호는 그 순간 보이는 칸):
  draw <칸>            뽑은 패 D 를 빈 칸에 놓음. "draw hand" 는 줄에 안 대고 손에 쥠
  pick <칸>            그 칸의 패를 손에 듦
  place <칸> [패]      손의 패를 빈 칸에 놓음(손에 둘 이상이면 패 이름을 적음)
  move <칸> <칸>       pick + place
  swap <칸> <칸>       두 칸의 패를 맞바꿈
  push <칸> L|R [k]    그 칸에서 시작해 미는 쪽으로 붙어 있는 패들을 한꺼번에 k 칸(기본 1) 밂 — 가는 칸이 비어 있어야 함
  discard <칸>|hand    그 칸의 패(또는 손에 든 한 장)를 강에 버림 — 차례에 한 번
  tidy                 줄을 순서 그대로 왼쪽부터 1번 칸에 붙임(빈칸 메움)
규칙을 어기면(찬 칸에 놓기, 빈 칸에서 집기, 버림 두 번, 끝났는데 손에 패가 남음 …) SlotError — 검산 노드가 쓸 것.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


LO = -1   # 맨 왼쪽 칸 번호(11-17 사용자: 뽑은 패를 왼쪽 끝 0 에 붙이는 사람도 있으니 왼쪽에도 임시칸 -1)


class SlotError(ValueError):
    pass


class Row:
    def __init__(self, n: int = 13):
        self.n = n
        self.cells: dict = {i: None for i in range(LO, n + 3)}   # 칸 번호 → 패(-1 ~ N+2, 넣은 차례대로 = 왼쪽부터)
        for i in range(1, n + 1):
            self.cells[i] = str(i)
        self.held: list = []
        self.drawn = False
        self.discarded: str | None = None
        self.k_pos: int | None = None       # 버리는 순간 줄(뽑은 패 D 는 빼고)에서 몇 번째였나 — 손에 든 패를 버리면 None
        self.steps: list = [("시작", self.snapshot())]

    # ------------------------------------------------------------ 보기
    def snapshot(self) -> dict:
        return {"cells": list(self.cells.values()), "held": list(self.held)}

    def bits(self) -> list:
        return [0 if c is None else 1 for c in self.cells.values()]

    def order(self) -> list:
        return [c for c in self.cells.values() if c is not None]

    def _chk(self, s: int):
        if not LO <= s <= self.n + 2:
            raise SlotError(f"칸 {s} 은 없다({LO} ~ {self.n + 2})")

    def _done(self, name: str):
        self.steps.append((name, self.snapshot()))

    # ------------------------------------------------------------ 동작
    def draw(self, to):
        if self.drawn:
            raise SlotError("뽑기가 두 번")
        self.drawn = True
        if to == "hand":
            self.held.append("D")
        else:
            self._chk(to)
            if self.cells[to] is not None:
                raise SlotError(f"draw: 칸 {to} 이 차 있다({self.cells[to]})")
            self.cells[to] = "D"
        self._done(f"draw {to}")

    def pick(self, frm: int, log=True):
        self._chk(frm)
        if self.cells[frm] is None:
            raise SlotError(f"pick: 칸 {frm} 이 비어 있다")
        self.held.append(self.cells[frm])
        self.cells[frm] = None
        if log:
            self._done(f"pick {frm}")

    def place(self, to: int, tile: str | None = None, log=True):
        self._chk(to)
        if self.cells[to] is not None:
            raise SlotError(f"place: 칸 {to} 이 차 있다({self.cells[to]})")
        if tile is None:
            if len(self.held) != 1:
                raise SlotError(f"place: 손에 든 패가 {len(self.held)}장 — 어느 패인지 적어야 한다")
            tile = self.held[0]
        if tile not in self.held:
            raise SlotError(f"place: 손에 {tile} 이 없다(손: {self.held})")
        self.held.remove(tile)
        self.cells[to] = tile
        if log:
            self._done(f"place {to} {tile}")

    def move(self, frm: int, to: int):
        self.pick(frm, log=False)
        self.place(to, self.held[-1], log=False)
        self._done(f"move {frm} {to}")

    def swap(self, a: int, b: int):
        self._chk(a), self._chk(b)
        if self.cells[a] is None or self.cells[b] is None:
            raise SlotError(f"swap: 칸 {a} · {b} 중 빈 칸이 있다")
        self.cells[a], self.cells[b] = self.cells[b], self.cells[a]
        self._done(f"swap {a} {b}")

    def push(self, frm: int, side: str, k: int = 1):
        self._chk(frm)
        d = {"R": 1, "L": -1}[side.upper()]
        if self.cells[frm] is None:
            raise SlotError(f"push: 칸 {frm} 이 비어 있다")
        run = [frm]
        while LO <= run[-1] + d <= self.n + 2 and self.cells[run[-1] + d] is not None:
            run.append(run[-1] + d)
        for _ in range(k):
            head = run[-1] + d
            if not LO <= head <= self.n + 2:
                raise SlotError(f"push: 칸 {run[-1]} 의 패가 줄 밖으로 나간다")
            if self.cells[head] is not None:
                raise SlotError(f"push: 칸 {head} 이 차 있어 못 민다")
            for s in reversed(run):
                self.cells[s + d], self.cells[s] = self.cells[s], None
            run = [s + d for s in run]
        self._done(f"push {frm} {side.upper()}" + (f" {k}" if k != 1 else ""))

    def discard(self, frm):
        if self.discarded is not None:
            raise SlotError("버림이 두 번")
        if frm == "hand":
            if len(self.held) != 1:
                raise SlotError(f"discard hand: 손에 든 패가 {len(self.held)}장")
            self.discarded = self.held.pop()
        else:
            self._chk(frm)
            if self.cells[frm] is None:
                raise SlotError(f"discard: 칸 {frm} 이 비어 있다")
            row = [c for c in self.cells.values() if c not in (None, "D")]
            self.k_pos = row.index(self.cells[frm]) + 1 if self.cells[frm] != "D" else None
            self.discarded, self.cells[frm] = self.cells[frm], None
        self._done(f"discard {frm}")

    def tidy(self):
        o = self.order()
        if len(o) > self.n + 1:
            raise SlotError(f"tidy: 줄에 {len(o)}장")
        self.cells = {i: (o[i - 1] if 1 <= i <= len(o) else None) for i in range(LO, self.n + 3)}
        self._done("tidy")

    # ------------------------------------------------------------ 끝
    def result(self) -> dict:
        """차례가 끝난 뒤의 값 — 지금 정답 형식(kind · k_id · j_closed)과 줄 순서."""
        if not self.drawn:
            raise SlotError("뽑기가 없다")
        if self.discarded is None:
            raise SlotError("버림이 없다")
        if self.held:
            raise SlotError(f"끝났는데 손에 패가 남았다: {self.held}")
        o = self.order()
        if len(o) != self.n:
            raise SlotError(f"끝났는데 줄이 {len(o)}장(있어야 할 것 {self.n})")
        if self.discarded == "D":
            moved = o != [str(i) for i in range(1, self.n + 1)]
            return {"kind": "tsumogiri", "k_id": None, "k_pos": None, "j_closed": None, "order": o, "reordered": moved}
        k = int(self.discarded)
        base = [("D" if x == "D" else x) for x in o]
        plain = [str(i) for i in range(1, self.n + 1) if i != k]          # 옮김이 없을 때 남는 패의 순서
        return {"kind": "hand", "k_id": k, "k_pos": self.k_pos, "j_closed": o.index("D") + 1, "order": base, "reordered": [x for x in o if x != "D"] != plain}


def run_ops(text: str, n: int = 13) -> Row:
    """"draw 14; push 8 R; move 15 8; discard 2; tidy" 꼴의 글을 굴린다."""
    r = Row(n)
    for raw in text.replace("\n", ";").split(";"):
        w = raw.split()
        if not w:
            continue
        op, a = w[0].lower(), w[1:]
        num = lambda x: x if x == "hand" else int(x)  # noqa: E731
        try:
            if op == "draw":
                r.draw(num(a[0]))
            elif op == "pick":
                r.pick(int(a[0]))
            elif op == "place":
                r.place(int(a[0]), a[1] if len(a) > 1 else None)
            elif op == "move":
                r.move(int(a[0]), int(a[1]))
            elif op == "swap":
                r.swap(int(a[0]), int(a[1]))
            elif op == "push":
                r.push(int(a[0]), a[1], int(a[2]) if len(a) > 2 else 1)
            elif op == "discard":
                r.discard(num(a[0]))
            elif op == "tidy":
                r.tidy()
            else:
                raise SlotError(f"모르는 동작: {raw.strip()}")
        except (IndexError, KeyError) as e:
            raise SlotError(f"동작을 못 읽음: {raw.strip()}") from e
    return r


def show(r: Row) -> str:
    w = max(2, len(str(r.n + 2)))
    out = ["칸      " + " ".join(f"{i:>{w}}" for i in range(LO, r.n + 3))]
    for name, s in r.steps:
        out.append(f"{name:<14.14s}" + " ".join(f"{(c or '·'):>{w}}" for c in s["cells"]) + (f"   손: {' '.join(s['held'])}" if s["held"] else ""))
        out.append(" " * 14 + " ".join(f"{(0 if c is None else 1):>{w}}" for c in s["cells"]))
    return "\n".join(out)


# 사용자 예와 오늘(11-17) 문제였던 차례. 동작은 사용자 메모 · 프레임 확인대로 새 번호(왼쪽에 붙인 뽑은 패 = 0번 칸)로 옮겨 적은 것.
DEMO = [
    ("사용자 예(11-17): 14에 놓고 8부터 밀어 8에 끼움, 2번 버림", None, "draw 14; push 8 R; move 15 8; discard 2; tidy"),
    ("r16_d08 왼쪽 끝에 붙이고 12번 버림", "r16_d08", "draw 0; discard 12; tidy"),
    ("r16_d13 왼쪽 끝 · 2번을 끝으로 빼고 13번을 그 자리에 · 12번 버림", "r16_d13", "draw 0; move 2 14; move 13 2; discard 12; tidy"),
    ("r16_d16 14에서 집어 7에 끼우고 7 ↔ 8 맞바꿈 · 14번 칸 버림", "r16_d16", "draw 14; pick 14; push 7 R; place 7; swap 7 8; discard 14; tidy"),
    ("r16_d02 12번 버림 · 정리 뒤 12 ↔ 13 맞바꿈", "r16_d02", "draw 14; discard 12; tidy; swap 12 13"),
    ("r17_d11 12 · 13번을 빼고 뽑은 패를 12로 · 둘을 그 오른쪽에 · 3번 버림", "r17_d11", "draw 14; pick 12; pick 13; move 14 12; place 13 12; place 14 13; discard 3; tidy"),
    ("r12_d02 5번 버림 · 13번을 뽑은 패 오른쪽으로", "r12_d02", "draw 14; discard 5; move 13 15; tidy"),
    ("r14_d02 9번을 뽑은 패 오른쪽에 두었다가 그 패를 버림", "r14_d02", "draw 14; move 9 15; tidy; discard 14"),
    ("r12_d03b 왼쪽 끝에 붙이고 13번 버림", "r12_d03b", "draw 0; discard 13; tidy"),
    ("쯔모기리(끝에 붙였다 그 패를 버림)", "r12_d03", "draw 14; discard 14"),
    ("틀린 동작: 찬 칸에 끼움", None, "draw 14; move 14 8; discard 2"),
    ("틀린 동작: 버림이 없음", None, "draw 14; tidy"),
]


def cmd_demo(_a):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import htcommon as hc
    truth = hc.jload(hc.WORK / "testtruth_1116" / "truth_final.json")
    ok = 0
    for n, (name, tid, ops) in enumerate(DEMO):
        print(f"\n[{name}]  {ops}")
        try:
            r = run_ops(ops)
            res = r.result()
        except SlotError as e:
            print("  → 검산에 걸림:", e)
            continue
        if n == 0:
            print(show(r))
        line = f"  → {res['kind']} · 원래 {res['k_id']}번째 버림 · 뽑은 패 {res['j_closed']}번째" + (" · 다른 패 순서도 바뀜" if res["reordered"] else "") + f" · 끝 줄 {' '.join(res['order'])}"
        if tid:
            u = truth[tid]
            same = (res["kind"], res["k_id"], res["j_closed"]) == (u["kind"], u.get("k_id"), u.get("j_closed"))
            if res["kind"] == "hand" and res["k_pos"] is not None and res["k_pos"] != u.get("k_pos"):
                line += f"   (버리는 순간 자리 {res['k_pos']} ≠ 정답 k_pos {u.get('k_pos')})"
            ok += same
            line += f"   | 정답({tid}) {u['kind']} {u.get('k_id')} {u.get('j_closed')} {'같음' if same else '**다름**'}"
        print(line)
    print(f"\n정답과 맞댄 {sum(1 for _, t, _ in DEMO if t)}차례 중 같음 {ok}")


def cmd_run(a):
    r = run_ops(a.ops, a.n)
    print(show(r))
    print(r.result())


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("demo")
    p = sp.add_parser("run")
    p.add_argument("ops")
    p.add_argument("--n", type=int, default=13)
    a = ap.parse_args()
    {"demo": cmd_demo, "run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
