"""판독기 F — 한 차례를 **칸 동작 목록**으로 읽힌다(2026-11-17, 계획서 3단계 "추가 14", 사용자 제안 "LLM 출력도 이 형식으로").
입력은 B(gemturn)와 같다(같은 차례 묶음 · 온 줄 · 초당 5장). 출력만 slotsim 의 동작 목록이고, 종류 · 패 번호 · 뽑은 패 자리는 코드가 굴려서 낸다.

  python -X utf8 opsread.py count <판 id…>
  python -X utf8 opsread.py run <판 id> [--ids a,b] [--ver 1]      # → _work/opsread_1117/v<ver>/<판>.json (리치 뒤 규칙 차례는 안 부름)
  python -X utf8 opsread.py score <판 id…> [--ver 1]               # 호출 없음 — 정답, 저장된 B · A 답과 나란히
요청에는 프레임 · 시각 · 구간 경계 · 줄 장수만 들어간다(정답 · 다른 판독기 답 · 패 종류 없음).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import endmove as em  # noqa: E402
import gemframes as gf  # noqa: E402
import gemturn as gt  # noqa: E402
import htcommon as hc  # noqa: E402
import slotsim as ss  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
OUT = hc.WORK / "opsread_1117"
MODEL = "gemini-3.8-flash"

V1 = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 연속 프레임이다. 프레임은 시간 순서이고 각 그림 앞에 시각(분:초)을 적었다.
그림은 그 사람 시점으로 돌려져 있다: 그림의 왼쪽 = 그 사람의 왼손 쪽. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 무늬는 안 보인다. 줄 아래쪽의 흰 띠는 탁자 테두리다.
다른 사람의 팔이나 소매가 줄 위를 지나가기도 한다 — 줄 아래쪽에 앉은 이 사람의 손 동작만 본다.

프레임은 이 사람의 **한 차례**(패산에서 한 장을 뽑아 오고, 한 장을 강에 버림)와 그 앞뒤다. 손이 움직인 구간만 이어 붙였고 구간이 바뀌는 곳에 표시를 넣었다:
"버림 구간" 에서 이 차례의 버림이 일어난다. "앞 구간" 은 그 전의 손 움직임(뽑기가 여기 있을 수 있다), "뒤 구간" 은 버린 뒤 다음에 뽑기 전까지의 손 움직임(뽑은 패를 다시 집어 옮기는 일이 여기 있을 수 있다. 다음 차례의 뽑기가 끝에 보이면 무시한다).
이 차례를 시작할 때 줄은 {n}장이다. 뽑아 온 패를 D 라고 부르자.

이 차례의 손 동작을 **칸 위의 동작 목록**으로 적어라. 답(무엇을 버렸고 D 가 어디에 섰는지)은 이 목록을 그대로 굴려서 계산한다.

칸:
- 차례를 시작할 때 손패 {n}장이 왼쪽부터 1 ~ {n}번 칸에 서 있다.
- {n1}번 칸 = 줄 오른쪽 끝 바로 옆. 뽑은 패를 오른쪽 끝에 붙이면 여기다.
- 0번 칸 = 줄 왼쪽 끝 바로 옆. 뽑은 패를 왼쪽 끝에 붙이면 여기다(손패의 번호는 밀리지 않는다).
- {n2}번 칸 = {n1}번 칸의 오른쪽 임시칸.
- 칸 번호는 **그 동작을 하는 순간의 줄**에서 센다. 패가 빠진 빈칸도 한 칸이다(빈칸 오른쪽 패들의 번호는 그대로다).

동작(op):
- "draw": 뽑은 패 D 를 칸 a 에 놓음. 줄에 대지 않고 손에 쥐고 있으면 a = null.
- "pick": 칸 a 의 패를 집어 듦(줄에서 빼 손에 쥐거나 줄 아래로 끌어냄).
- "place": 손에 든 패를 빈 칸 a 에 놓음. 손에 든 패가 둘 이상이면 tile 에 어느 패인지 적는다("D", 또는 차례를 시작할 때의 번호 "1" ~ "{n}").
- "move": 칸 a 의 패를 빈 칸 b 로 옮김(집어서 바로 놓음).
- "swap": 칸 a 와 칸 b 의 패를 맞바꿈.
- "push": 칸 a 의 패와, 그 패에 dir 쪽으로 빈칸 없이 붙어 있는 패들을 한꺼번에 dir("L" = 왼쪽, "R" = 오른쪽) 쪽으로 b 칸(보통 1) 밂 — 패를 끼울 자리를 벌릴 때.
- "discard": 칸 a 의 패를 강에 버림. 손에 든 패를 버리면 a = null. 한 차례에 한 번뿐이다.
- "tidy": 빈칸을 메워 줄을 왼쪽부터 1번 칸에 빈칸 없이 붙임. 밀어서 정리하는 것은 어느 쪽으로 밀었든 tidy 하나로 적는다. tidy 뒤의 칸 번호는 정리된 줄에서 다시 센다.

예({n}장일 때):
- D 를 오른쪽 끝에 붙이고 5번째 패를 버린 뒤 밀어 정리: draw a={n1} → discard a=5 → tidy
- D 를 쥔 채 그대로 버림: draw a=null → discard a=null. D 를 끝에 붙였다가 그 패를 버림: draw a={n1} → discard a={n1}
- D 를 오른쪽 끝에 붙였다가, 8번 칸부터 오른쪽으로 밀어 자리를 내고 D 를 8번 칸에 끼운 뒤 2번째 패를 버림: draw a={n1} → push a=8 dir=R b=1 → move a={n2} b=8 → discard a=2 → tidy
- D 를 왼쪽 끝에 붙이고 맨 오른쪽 패를 버림: draw a=0 → discard a={n} → tidy
- D 를 끝에 붙이고 3번째 패를 버려 정리한 뒤, D 의 왼쪽 패를 빼서 D 의 오른쪽에 붙임: draw a={n1} → discard a=3 → tidy → move a={nm1} b={n1} → tidy

주의:
- 뽑기 · 버림과 상관없이 줄 안의 패를 빼서 다른 자리에 놓거나 맞바꾸는 동작도 빠짐없이 적는다. 버릴 패를 먼저 줄 끝으로 빼 두었다가 버리는 사람, 끝에 붙인 D 의 옆 패를 D 오른쪽으로 넘기는 사람이 있다.
- 손가락으로 줄을 가지런히 누르기만 하는 것은 적지 않는다.
- 깨끗한(손이 안 닿은) 프레임에서 패를 하나씩 센다. 손가락이 줄 위에 얹혀 끊겨 보이는 것은 빈칸이 아니다 — 사이로 초록 펠트가 보여야 빈칸이다.
- 넣는 순간이 손에 가려지면, 제자리에 그대로 남은 패가 왼쪽 · 오른쪽에 몇 장인지와 손이 옮긴 패가 몇 장인지로 따진다. 버린 패가 빠진 빈자리와 D 를 넣으려고 벌린 틈을 헷갈리지 말 것.
- 손에 가려 어느 칸인지 한 칸으로 못 정했으면 가장 그럴듯한 값을 넣고 unsure = true.

JSON 으로만 답하라: steps = 본 것을 시각과 함께 짧게(3~6문장), ops = 동작 목록(일어난 순서대로. 각 동작에 op 와 필요한 a · b · dir · tile, t = 그 동작의 시각 분:초), unsure = true / false.
"""
PROMPTS = {1: V1}
SCHEMA = {"type": "OBJECT", "properties": {
    "steps": {"type": "STRING"},
    "ops": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "op": {"type": "STRING", "enum": ["draw", "pick", "place", "move", "swap", "push", "discard", "tidy"]},
        "a": {"type": "INTEGER", "nullable": True}, "b": {"type": "INTEGER", "nullable": True},
        "dir": {"type": "STRING", "enum": ["L", "R"], "nullable": True}, "tile": {"type": "STRING", "nullable": True},
        "t": {"type": "STRING"}}, "required": ["op", "t"]}},
    "unsure": {"type": "BOOLEAN"}}, "required": ["steps", "ops", "unsure"]}


def simulate(ops: list, n: int) -> dict:
    """동작 목록을 굴린다 → {valid, kind, k, j, order, reordered} 또는 {valid: False, err}."""
    r = ss.Row(n)
    try:
        for o in ops or []:
            op, a, b = o.get("op"), o.get("a"), o.get("b")
            if op == "draw":
                r.draw("hand" if a is None else int(a))
            elif op == "pick":
                r.pick(int(a))
            elif op == "place":
                r.place(int(a), (str(o["tile"]).strip() or None) if o.get("tile") is not None else None)
            elif op == "move":
                r.move(int(a), int(b))
            elif op == "swap":
                r.swap(int(a), int(b))
            elif op == "push":
                r.push(int(a), o.get("dir") or "R", int(b) if b else 1)
            elif op == "discard":
                r.discard("hand" if a is None else int(a))
            elif op == "tidy":
                r.tidy()
            else:
                raise ss.SlotError(f"모르는 동작 {op}")
        if len(r.order()) <= n + 1:
            r.tidy()  # 끝에 정리를 안 적었어도 붙여 준다(순서는 안 바뀜)
        res = r.result()
    except (ss.SlotError, TypeError, ValueError) as e:
        return {"valid": False, "err": str(e)[:160]}
    return {"valid": True, "kind": res["kind"], "k": res["k_id"], "j": res["j_closed"], "order": res["order"], "reordered": res["reordered"]}


def op_text(ops: list) -> str:
    out = []
    for o in ops or []:
        a, b = o.get("a"), o.get("b")
        x = {"draw": f"draw {'hand' if a is None else a}", "pick": f"pick {a}", "place": f"place {a}" + (f" {o['tile']}" if o.get("tile") else ""),
             "move": f"move {a} {b}", "swap": f"swap {a} {b}", "push": f"push {a} {o.get('dir')}" + (f" {b}" if b and b != 1 else ""),
             "discard": f"discard {'hand' if a is None else a}", "tidy": "tidy"}.get(o.get("op"), str(o.get("op")))
        out.append(x)
    return "; ".join(out)


def one(c, types, t: dict, ver: int) -> dict:
    n = t["n_calc"] or 13
    ps = [PROMPTS[ver].format(n=n, n1=n + 1, n2=n + 2, nm1=n - 1)]
    for s in t["segs"]:
        ps.append(f"—— {gt.ROLE[s['role']]} 시작({hc.hms(s['frames'][0])[3:]}) ——")
        for ms in s["frames"][::gt.STEP]:
            ps.append(f"프레임 {hc.hms(ms)[3:]}")
            part = types.Part.from_bytes(data=(BASE / "frames" / t["game"] / f"{ms}.jpg").read_bytes(), mime_type="image/jpeg")
            part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
            ps.append(part)
    ps.append(f"위 프레임을 보고 답하라. 차례를 시작할 때 줄은 {n}장이다.")
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA)
    t0, err, nf = time.perf_counter(), "", len(gt.frames_of(t))
    for attempt in range(3):
        try:
            r = c.models.generate_content(model=MODEL, contents=ps, config=cfg)
            um, d = r.usage_metadata, json.loads(r.text)
            return {"id": t["id"], "n": n, "ops": d.get("ops") or [], "unsure": bool(d.get("unsure")), "steps": d.get("steps"), "sim": simulate(d.get("ops") or [], n),
                    "frames": nf, "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                    "think": getattr(um, "thoughts_token_count", 0) or 0, "attempt": attempt + 1}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(8 * (attempt + 1))
    return {"id": t["id"], "n": n, "ops": None, "error": err, "sim": {"valid": False, "err": "답 없음"}, "frames": nf, "s": round(time.perf_counter() - t0, 1), "in": 0, "out": 0, "think": 0}


def load(gid: str, ver: int) -> dict:
    f = OUT / f"v{ver}" / f"{gid}.json"
    return {r["id"]: r for r in hc.jload(f)["rows"]} if f.exists() else {}


def as_read(r: dict | None) -> dict | None:
    """F 답을 pgraph.norm 이 받는 꼴로. 검산에 걸렸거나 답이 없으면 None(= 사람에게)."""
    if not r or not (r.get("sim") or {}).get("valid"):
        return None
    s = r["sim"]
    return {"kind": s["kind"], "k": s["k"], "j": s["j"], "unsure": bool(r.get("unsure"))}


def cmd_count(a):
    for gid in a.games:
        ts = gt.turns_of(gid)
        rule = em.rule_turns(ts)
        n = sum(len(gt.frames_of(t)) for t in ts if t["id"] not in rule)
        print(f"{gid}: 리치 뒤 아닌 차례 {len(ts) - len(rule)} · 프레임 {n} · 어림 {n * em.TOK_PER_IMG * 0.75e-6:.2f}달러(입력만)")


def cmd_run(a):
    from google.genai import types
    gid = a.game
    ts = gt.turns_of(gid)
    rule, have = em.rule_turns(ts), load(gid, a.ver)
    want = [t for t in ts if t["id"] not in rule and (not a.ids or t["id"] in a.ids.split(","))]
    todo = [t for t in want if (have.get(t["id"]) or {}).get("ops") is None]
    print(f"{gid} · v{a.ver} · 부를 차례 {len(todo)}(이미 있음 {len(want) - len(todo)})")
    if todo:
        with ThreadPoolExecutor(3) as ex:
            rows = list(ex.map(lambda t: one(gf.client(), types, t, a.ver), todo))
        for r in rows:
            have[r["id"]] = r
        order = {t["id"]: n for n, t in enumerate(ts)}
        hc.jsave(OUT / f"v{a.ver}" / f"{gid}.json", {"game": gid, "model": MODEL, "ver": a.ver, "step": gt.STEP, "at": hc.hms(int(time.time() * 1000), date=True),
                                                     "rows": sorted(have.values(), key=lambda r: order[r["id"]])})
        print(f"  새 호출: 입력 {sum(r['in'] for r in rows):,} · 출력+생각 {sum(r['out'] + r['think'] for r in rows):,} · {em.dollars(rows):.2f}달러 · 오류 {sum('error' in r for r in rows)}"
              f" · 검산 걸림 {sum(not r['sim']['valid'] for r in rows)} · 호출 최대 {max(r['s'] for r in rows):.0f}초")


MOVE_DEV = {"r11_d03", "r11_d09", "r12_d02", "r12_d06", "r14_d02", "r17_d11", "r19_d07"}  # 표 12-30 의 고친 옮김 표지


def cmd_score(a):
    import pgraph as pg
    truth = hc.jload(BASE / "truth_final.json")
    tot = {"n": 0, "F": 0, "B": 0, "bad": 0, "bad_wrong": 0, "nA": 0, "A": 0, "FA": 0, "mv": 0, "mvF": 0, "mvB": 0, "unsure": 0}
    pair = {k: {"n": 0, "auto": 0, "silent": 0, "human": 0, "who": []} for k in ("A+B", "A+F", "B+F", "B+F(전체)")}

    def add(name, x, y, u, i):
        p = pair[name]
        p["n"] += 1
        same = x is not None and y is not None and (x["kind"], x["k"], x["j"]) == (y["kind"], y["k"], y["j"]) and not x["unsure"] and not y["unsure"] and x["kind"] != "unseen"
        if same:
            p["auto"] += 1
            if not pg.right(x, u):
                p["silent"] += 1
                p["who"].append(i[-7:])
        else:
            p["human"] += 1

    for gid in a.games:
        ts = [t for t in gt.turns_of(gid) if t["id"] in truth]
        rule, F = em.rule_turns(gt.turns_of(gid)), load(gid, a.ver)
        A, B = pg.load_a(gid, False), pg.load_b(gid, False)
        print(f"\n== {gid} · v{a.ver} · F 비용 {em.dollars(F.values()):.2f}달러")
        for t in ts:
            i, u = t["id"], truth[t["id"]]
            if i in rule or i not in F:
                continue
            f, nf = F[i], pg.norm(as_read(F[i]))
            nb, na = pg.norm((B or {}).get(i)), pg.norm((A or {}).get(i)) if A else None
            okf, okb = pg.right(nf, u), pg.right(nb, u)
            tot["n"] += 1
            tot["F"] += okf
            tot["B"] += okb
            tot["unsure"] += bool(f.get("unsure"))
            if not f["sim"]["valid"]:
                tot["bad"] += 1
            if i in MOVE_DEV:
                tot["mv"] += 1
                tot["mvF"] += okf
                tot["mvB"] += okb
            add("B+F(전체)", nb, nf, u, i)
            if A:
                tot["nA"] += 1
                tot["A"] += pg.right(na, u)
                tot["FA"] += okf
                add("A+B", na, nb, u, i)
                add("A+F", na, nf, u, i)
                add("B+F", nb, nf, u, i)
            show = lambda v: "-" if v is None else f"{v['kind'][:1]} {v['k']} {v['j']}" + ("?" if v["unsure"] else "")  # noqa: E731
            sim = f["sim"]
            print(f"  {i:9s}{' 옮김' if i in MOVE_DEV else '     '} 정답 {u['kind'][:1]} {u.get('k_id')} {u.get('j_closed')} | F {show(nf) if sim['valid'] else '검산 걸림: ' + sim['err'][:40]} {'✓' if okf else '✗'}"
                  + (" 순서 바뀜" if sim.get("reordered") else "") + f" | B {show(nb)} {'✓' if okb else '✗'}" + (f" | A {show(na)} {'✓' if pg.right(na, u) else '✗'}" if A else "") + f"  [{op_text(f.get('ops'))}]")
    n = tot["n"]
    print(f"\n합(v{a.ver}, {n}차례): F 혼자 {tot['F']} · B 혼자 {tot['B']} · F 검산 걸림 {tot['bad']} · F unsure {tot['unsure']} · 옮김 차례 {tot['mv']} 중 F {tot['mvF']} · B {tot['mvB']}")
    if tot["nA"]:
        print(f"  A 가 있는 {tot['nA']}차례: A {tot['A']} · F {tot['FA']}")
    for k, p in pair.items():
        if p["n"]:
            print(f"  짝 {k:9s}({p['n']}차례): 자동 {p['auto']} · 조용한 틀림 {p['silent']} {p['who'] or ''} · 사람 {p['human']}({p['human'] / p['n']:.0%})")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "run", "score"):
        p = sp.add_parser(name)
        p.add_argument("game" if name == "run" else "games", **({} if name == "run" else {"nargs": "+"}))
        p.add_argument("--ver", type=int, default=1)
        if name == "run":
            p.add_argument("--ids", default="")
    a = ap.parse_args()
    {"count": cmd_count, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
