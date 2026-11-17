"""판독기 여럿 + 규칙 점검 + 갈린 차례만 사람 — LangGraph 시제품(2026-11-17, 계획서 3단계 "추가 10" — 구조·평가는 새 판을 열기 전에 고정).

  python -X utf8 pgraph.py run <판 id> [--readers AB]     # 판독기 A(도구 쓰는 읽기)·B(한 번 묻기)를 돌리고 그래프를 사람 확인 직전까지
  python -X utf8 pgraph.py score <판 id…>                 # 저장된 읽기로 조합 AB · BC · ABC 채점(정답 truth_final.json, 호출 없음)
판독기: A = Gemini 가 `look`(시각 범위를 초당 10장으로 + 화소로 센 덩어리 장수) 도구를 불러 가며 읽음 / B = gemturn 한 번 묻기 그대로 /
       C = Opus 에이전트 읽기(second/read_*.json — 그래프 밖에서 만든 파일, 있으면 읽기만).
맞춘 숫자 없음: 자동으로 답을 바꾸는 것은 "리치 선언 뒤 버림 = 쯔모기리" 뿐. 판독기들이 같으면 자동 확정, 아니면 사람. 정렬 검사는 적기만 한다.
"""
from __future__ import annotations

import argparse
import io
import json
import operator
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, TypedDict

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemframes as gf  # noqa: E402
import gemturn as gt  # noqa: E402
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402
from replay import key, sort_scheme  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
OUT = hc.WORK / "graph_1117"
MODEL = "gemini-3.8-flash"
MAX_LOOKS, MAX_WIN, WIN_SEC, WIN_FRAMES, OVERVIEW = 3, 3, 2.0, 20, 36

A_PROMPT = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 프레임이다. 각 그림 앞에 시각(분:초)을 적었다.
그림은 그 사람 시점으로 돌려져 있다: 그림의 왼쪽 = 그 사람의 왼손 쪽. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 무늬는 안 보인다. 줄 아래쪽의 흰 띠는 탁자 테두리다.
다른 사람의 팔이나 소매가 줄 위를 지나가기도 한다 — 줄 아래쪽에 앉은 이 사람의 손 동작만 본다.

프레임은 이 사람의 **한 차례**(패산에서 한 장을 뽑아 오고, 한 장을 강에 버림)와 그 앞뒤다. 손이 움직인 구간만 이어 붙였다:
"버림 구간" 에서 이 차례의 버림이 일어난다. "앞 구간" 은 그 전의 손 움직임(뽑기가 여기 있을 수 있다), "뒤 구간" 은 버린 뒤 다음에 뽑기 전까지의 손 움직임(뽑은 패를 다시 집어 옮기는 일이 여기 있을 수 있다. 다음 차례의 뽑기가 끝에 보이면 무시한다).
이 차례를 시작할 때 줄은 {n}장이다. 뽑아 온 패를 D 라고 부르자.

보는 법: 먼저 차례 전체를 성긴 간격으로 보여 준다. 자세히 봐야 할 순간은 `look` 도구로 시각 범위를 정해 초당 10장으로 본다(한 번에 창 {mw}개까지, 창 하나는 {ws:.0f}초 이하, 모두 {ml}번까지). zoom 을 left 나 right 로 주면 줄의 그쪽 절반을 키워 보여 준다.
`look` 이 돌려주는 프레임에는 화소로 센 참고 값이 글로 붙는다: 손이 안 닿은 채 붙어 서 있는 덩어리의 장수 목록과, 손이 닿은 덩어리의 폭(장 단위). 소매나 남의 팔 때문에 틀릴 수 있으니 그림과 맞춰 보고 쓴다.
판단이 서면 `submit` 으로 답한다.

답할 것:
- kind: "tsumogiri" = D 를 그대로 버림(줄의 패는 안 바뀜. D 를 줄 끝에 잠깐 붙였다가 그 패를 버려도, 줄에 안 대고 쥔 채 버려도 쯔모기리) / "hand" = 줄에 있던 패를 버리고 D 가 줄에 남음 / "unseen" = 가려서 알 수 없음.
- k (hand 일 때만): 버린 패가 이 차례를 시작할 때 줄 {n}장에서 왼쪽부터 몇 번째 패였나(1 ~ {n}). D 는 세지 않는다. 버리기 전에 그 패를 다른 자리로 옮겨 두었더라도 옮기기 전 번호로 답한다.
- j (hand 일 때만): 이 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째에 서 있나(1 ~ {n}). 끝에 그대로 두었으면 {n}.
- moves: 뽑기와 상관없이 줄 안의 패를 옮기거나 맞바꾼 동작이 있으면 짧게(없으면 빈 글).
- unsure: 가려서 한 칸으로 못 정했거나 두 가지로 읽히면 true(가장 그럴듯한 값을 넣는다).
- steps: 본 것을 시각과 함께 짧게(3~6문장).

참고:
- 깨끗한(손이 안 닿은) 프레임에서 패를 하나씩 센다. 손가락이 줄 위에 얹혀 끊겨 보이는 것은 빈칸이 아니다 — 사이로 초록 펠트가 보여야 빈칸이다.
- D 를 끝에 붙여 두고 한 장을 버린 뒤 그대로 두는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 나서 버리는 사람이 다 있다.
- 넣는 순간이 손에 가려지면, 제자리에 그대로 남은 패가 왼쪽·오른쪽에 몇 장인지와 손이 옮긴 패가 몇 장인지로 따진다. 버린 패가 빠진 빈자리와 D 를 넣으려고 벌린 틈을 헷갈리지 말 것.
"""


def sec(lab: str) -> float:
    m, s = lab.split(":")
    return int(m) * 60 + float(s)


def all_frames(t: dict) -> list:
    return [(s["role"], ms, hc.hms(ms)[3:]) for s in t["segs"] for ms in s["frames"]]


def img_part(types, gid: str, ms: int, zoom: str = "none"):
    f = BASE / "frames" / gid / f"{ms}.jpg"
    if zoom in ("left", "right"):
        im = Image.open(f)
        w, h = im.size
        cw = int(w * 0.58)
        im = im.crop((0, 0, cw, h) if zoom == "left" else (w - cw, 0, w, h)).resize((w, round(h * w / cw)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        data = buf.getvalue()
    else:
        data = f.read_bytes()
    part = types.Part.from_bytes(data=data, mime_type="image/jpeg")
    part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
    return part


def pixel_note(R, ms: int) -> str:
    if R is None:
        return ""
    try:
        runs = R.runs_of(R.view(ms))[0]
    except Exception:  # noqa: BLE001
        return ""
    clean = [round(r["n"]) for r in runs if not r["hl"] and not r["hr"] and r["n"] >= 0.6]
    touched = [f"{r['n']:.1f}" for r in runs if (r["hl"] or r["hr"]) and r["n"] >= 0.6]
    return f" · 화소 참고: 손 안 닿은 덩어리 {clean}" + (f" · 손 닿은 덩어리 {touched}" if touched else "")


def read_a(client, types, t: dict, R) -> dict:
    """판독기 A — 도구를 쓰는 읽기. look 은 모두 MAX_LOOKS 번, 그 뒤에는 submit 만."""
    n = t["n_calc"] or 13
    fr = all_frames(t)
    stride = max(5, -(-len(fr) // OVERVIEW))
    parts = [A_PROMPT.format(n=n, mw=MAX_WIN, ws=WIN_SEC, ml=MAX_LOOKS), f"차례 전체(프레임 {len(fr)}장 중 {stride}장마다 한 장):"]
    last = None
    for i, (role, ms, lab) in enumerate(fr):
        if role != last:
            parts.append(f"—— {gt.ROLE[role]} 시작({lab}) ——")
            last = role
        if i % stride == 0:
            parts.append(f"프레임 {lab}")
            parts.append(img_part(types, t["game"], ms))
    parts.append(f"위는 성긴 간격이다. 필요한 순간을 look 으로 자세히 본 뒤 submit 으로 답하라. 차례를 시작할 때 줄은 {n}장이다.")
    tool = types.Tool(function_declarations=[
        types.FunctionDeclaration(name="look", description="시각 범위를 초당 10장으로 자세히 본다(화소 참고 값이 같이 붙는다).", parameters={
            "type": "OBJECT", "properties": {"windows": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "t0": {"type": "STRING", "description": "시작 시각 분:초(예 13:15.2)"}, "t1": {"type": "STRING", "description": "끝 시각 분:초"},
                "zoom": {"type": "STRING", "enum": ["none", "left", "right"]}}, "required": ["t0", "t1"]}}}, "required": ["windows"]}),
        types.FunctionDeclaration(name="submit", description="이 차례의 답을 낸다.", parameters={
            "type": "OBJECT", "properties": {"kind": {"type": "STRING", "enum": ["tsumogiri", "hand", "unseen"]},
                                             "k": {"type": "INTEGER", "nullable": True}, "j": {"type": "INTEGER", "nullable": True},
                                             "moves": {"type": "STRING"}, "unsure": {"type": "BOOLEAN"}, "steps": {"type": "STRING"}},
            "required": ["kind", "unsure", "steps"]})])
    contents = [types.Content(role="user", parts=[p if not isinstance(p, str) else types.Part.from_text(text=p) for p in parts])]
    use = {"in": 0, "out": 0, "think": 0}
    looks, log, t0 = 0, [], time.perf_counter()
    for step in range(MAX_LOOKS + 2):
        only_submit = looks >= MAX_LOOKS
        cfg = types.GenerateContentConfig(tools=[tool], tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
            mode="ANY", allowed_function_names=["submit"] if only_submit else ["look", "submit"])))
        r = None
        for attempt in range(3):
            try:
                r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
                break
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(8 * (attempt + 1))
        if r is None:
            return {"id": t["id"], "kind": None, "error": err, "looks": log, **use, "s": round(time.perf_counter() - t0, 1)}
        um = r.usage_metadata
        use["in"] += um.prompt_token_count or 0
        use["out"] += um.candidates_token_count or 0
        use["think"] += getattr(um, "thoughts_token_count", 0) or 0
        fcs = r.function_calls or []
        if not fcs:
            return {"id": t["id"], "kind": None, "error": "도구 호출 없음", "looks": log, **use, "s": round(time.perf_counter() - t0, 1)}
        contents.append(r.candidates[0].content)
        sub = next((fc for fc in fcs if fc.name == "submit"), None)
        if sub is not None:
            a = dict(sub.args)
            return {"id": t["id"], "kind": a.get("kind"), "k": a.get("k"), "j": a.get("j"), "moves": a.get("moves") or "", "unsure": bool(a.get("unsure")),
                    "steps": a.get("steps"), "looks": log, **use, "s": round(time.perf_counter() - t0, 1)}
        resp = []
        for fc in fcs:
            wins = list((fc.args or {}).get("windows") or [])[:MAX_WIN]
            shown, extra = 0, []
            for w in wins:
                try:
                    a0, a1 = sec(w["t0"]), sec(w["t1"])
                except Exception:  # noqa: BLE001
                    continue
                a1 = min(a1, a0 + WIN_SEC)
                pick = [(ms, lab) for _, ms, lab in fr if a0 - 0.05 <= sec(lab) <= a1 + 0.05]
                if len(pick) > WIN_FRAMES:
                    pick = pick[::-(-len(pick) // WIN_FRAMES)]
                zoom = w.get("zoom") or "none"
                extra.append(types.Part.from_text(text=f"—— 창 {w['t0']}~{w['t1']}" + (f" · {zoom} 쪽 확대" if zoom != "none" else "") + f" · {len(pick)}장 ——"))
                for ms, lab in pick:
                    extra.append(types.Part.from_text(text=f"프레임 {lab}{pixel_note(R, ms)}"))
                    extra.append(img_part(types, t["game"], ms, zoom))
                shown += len(pick)
                log.append({"t0": w["t0"], "t1": w["t1"], "zoom": zoom, "frames": len(pick)})
            resp.append(types.Part.from_function_response(name="look", response={"result": f"프레임 {shown}장을 아래에 붙였다. 남은 look {max(0, MAX_LOOKS - looks - 1)}번."}))
            resp += extra
        looks += 1
        contents.append(types.Content(role="user", parts=resp))
    return {"id": t["id"], "kind": None, "error": "단계 초과", "looks": log, **use, "s": round(time.perf_counter() - t0, 1)}


# ------------------------------------------------------------------ 읽기 불러오기(없으면 호출)
def turns_of(gid: str) -> list:
    return gt.turns_of(gid)


def load_a(gid: str, call: bool) -> dict | None:
    f = OUT / gid / "readA.json"
    if f.exists():
        return {r["id"]: r for r in hc.jload(f)["rows"]}
    if not call:
        return None
    from google.genai import types
    ts = turns_of(gid)
    try:
        R = pt.Row(gid)
    except Exception as e:  # noqa: BLE001
        print("화소 줄 잡기 실패 — 화소 참고 없이 감:", type(e).__name__, e)
        R = None
    with ThreadPoolExecutor(3) as ex:
        rows = list(ex.map(lambda t: read_a(gf.client(), types, t, R), ts))
    hc.jsave(f, {"game": gid, "model": MODEL, "at": hc.hms(int(time.time() * 1000), date=True), "rows": rows})
    print(f"A {gid}: 입력 {sum(r['in'] for r in rows):,} · 생각 {sum(r['think'] for r in rows):,} · look {sum(len(r['looks']) for r in rows)}창 · 오류 {sum('error' in r for r in rows)}")
    return {r["id"]: r for r in rows}


def load_b(gid: str, call: bool) -> dict | None:
    f = gt.OUT / "answers" / f"{gid[:3]}_{MODEL}_r1.json"
    if not f.exists():
        if not call:
            return None
        from google.genai import types
        with ThreadPoolExecutor(3) as ex:
            rows = list(ex.map(lambda t: gt.one(gf.client(), types, MODEL, t), turns_of(gid)))
        hc.jsave(f, {"game": gid, "model": MODEL, "rep": 1, "step": gt.STEP, "at": hc.hms(int(time.time() * 1000), date=True), "rows": rows})
        print(f"B {gid}: 입력 {sum(r['in'] for r in rows):,} · 생각 {sum(r['think'] for r in rows):,}")
    return {r["id"]: r for r in hc.jload(f)["rows"]}


def load_c(gid: str) -> dict | None:
    out = {}
    for f in (BASE / "second").glob(f"read_{gid[:3]}_*.json"):
        for t in hc.jload(f)["turns"]:
            k, j = t.get("k"), t.get("j")
            jc = None if (k is None or j is None) else (j if j <= k else (k if j == k + 1 else j - 1))  # 빈칸 둔 번호 → 메운 뒤 번호
            out[t["id"]] = {"id": t["id"], "kind": t.get("kind"), "k": k, "j": jc, "unsure": bool(t.get("unsure")), "steps": t.get("why")}
    return out or None


def norm(a: dict | None) -> dict | None:
    if not a or not a.get("kind"):
        return None
    hand = a["kind"] == "hand"
    return {"kind": a["kind"], "k": a.get("k") if hand else None, "j": a.get("j") if hand else None, "unsure": bool(a.get("unsure"))}


# ------------------------------------------------------------------ 그래프
class S(TypedDict, total=False):
    game: str
    readers: str
    call: bool
    turns: list
    reads: Annotated[dict, operator.or_]
    rules: dict
    decided: dict
    queue: list
    human: dict
    final: dict
    rebuild: dict


def n_turns(s: S) -> dict:
    return {"turns": turns_of(s["game"])}


def n_read(name: str):
    def f(s: S) -> dict:
        if name not in s["readers"]:
            return {"reads": {}}
        d = {"A": lambda: load_a(s["game"], s.get("call", False)), "B": lambda: load_b(s["game"], s.get("call", False)), "C": lambda: load_c(s["game"])}[name]()
        return {"reads": {name: d} if d else {}}
    return f


def n_rules(s: S) -> dict:
    """마작 규칙으로 정해지는 것만: 리치 선언(강의 가로 패) 뒤 버림은 쯔모기리. 울기 직후 버림은 표시(사람에게)."""
    out, riichi, prev_meld = {}, False, None
    for t in s["turns"]:
        m = t["meld_tiles"][1]
        out[t["id"]] = {"after_riichi": riichi, "after_call": prev_meld is not None and m - prev_meld >= 2}
        prev_meld = m
        riichi = riichi or bool(t.get("sideways"))
    return {"rules": out}


def n_reconcile(s: S) -> dict:
    decided, queue = {}, []
    names = [r for r in s["readers"] if r in s["reads"]]
    for t in s["turns"]:
        i, rule = t["id"], s["rules"][t["id"]]
        ans = {r: norm(s["reads"][r].get(i)) for r in names}
        if rule["after_riichi"]:
            decided[i] = {"kind": "tsumogiri", "k": None, "j": None, "src": "규칙(리치 뒤)", "reads": ans}
            continue
        vals = list(ans.values())
        same = len(vals) >= 2 and all(v is not None for v in vals) and all((v["kind"], v["k"], v["j"]) == (vals[0]["kind"], vals[0]["k"], vals[0]["j"]) for v in vals)
        why = []
        if rule["after_call"]:
            why.append("울기 직후")
        if not same:
            why.append("판독기가 갈림" if all(v is not None for v in vals) else "판독기 답 없음")
        elif any(v["unsure"] for v in vals):
            why.append("판독기가 확신 없음")
        elif vals[0]["kind"] == "unseen":
            why.append("안 보임")
        if why:
            queue.append({"id": i, "label": t.get("label"), "why": why, "reads": ans})
        else:
            decided[i] = {**{k: vals[0][k] for k in ("kind", "k", "j")}, "src": "판독기 일치", "reads": ans}
    return {"decided": decided, "queue": queue}


def n_human(s: S) -> dict:
    """갈린 차례만 사람에게. interrupt 로 멈추고, 답({id: {kind,k,j}})을 받아 이어 간다."""
    from langgraph.types import interrupt
    if not s["queue"]:
        return {"human": {}}
    got = interrupt({"game": s["game"], "queue": s["queue"]})
    return {"human": got or {}}


def n_rebuild(s: S) -> dict:
    """끝 손패에서 거꾸로 굴려 정렬이 어긋난 이웃을 적는다(답은 안 고침)."""
    final = {i: {k: d[k] for k in ("kind", "k", "j")} | {"src": d["src"]} for i, d in s["decided"].items()}
    for i, a in (s.get("human") or {}).items():
        final[i] = {"kind": a.get("kind"), "k": a.get("k"), "j": a.get("j"), "src": "사람"}
    game = hc.jload(hc.OUT / s["game"] / "game.json")
    row = list((game.get("final_hand") or {}).get("closed") or [])
    rep = {"complete": all(t["id"] in final for t in s["turns"]) and bool(row), "turns": []}
    if rep["complete"]:
        sch = sort_scheme(row)
        for t in reversed(s["turns"]):
            a, x = final[t["id"]], t["tile"]
            d = x
            if a["kind"] == "hand" and a["k"] and a["j"] and 1 <= a["j"] <= len(row) and 1 <= a["k"] <= len(row):
                d = row[a["j"] - 1]
                rest = row[:a["j"] - 1] + row[a["j"]:]
                row = rest[:a["k"] - 1] + [x] + rest[a["k"] - 1:]
            elif a["kind"] != "tsumogiri":
                rep["complete"] = False
                break
            ks = [key(v, sch) for v in row]
            bad = [f"{row[n]}>{row[n + 1]}" for n in range(len(ks) - 1) if ks[n] is not None and ks[n + 1] is not None and ks[n] > ks[n + 1]]
            rep["turns"].append({"id": t["id"], "draw": d, "discard": x, "hand": list(row), "sort_bad": bad})
        rep["turns"].reverse()
    return {"final": final, "rebuild": rep}


def build():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
    g = StateGraph(S)
    g.add_node("turns", n_turns)
    for r in "ABC":
        g.add_node(f"read_{r}", n_read(r))
    g.add_node("rules", n_rules)
    g.add_node("reconcile", n_reconcile)
    g.add_node("human", n_human)
    g.add_node("rebuild", n_rebuild)
    g.add_edge(START, "turns")
    for r in "ABC":
        g.add_edge("turns", f"read_{r}")
        g.add_edge(f"read_{r}", "rules")
    g.add_edge("rules", "reconcile")
    g.add_edge("reconcile", "human")
    g.add_edge("human", "rebuild")
    g.add_edge("rebuild", END)
    return g.compile(checkpointer=MemorySaver())


def run_graph(gid: str, readers: str, call: bool, human=None) -> dict:
    """그래프를 돌린다. human 이 None 이면 사람 확인 직전에서 멈춘 상태를, 함수면 queue → 답을 받아 끝까지."""
    from langgraph.types import Command
    app = build()
    cfg = {"configurable": {"thread_id": f"{gid}-{readers}"}}
    st = app.invoke({"game": gid, "readers": readers, "call": call}, cfg)
    if "__interrupt__" in st and human is not None:
        q = st["__interrupt__"][0].value["queue"]
        st = app.invoke(Command(resume=human(q)), cfg)
    return st


# ------------------------------------------------------------------ 명령
def cmd_run(a):
    st = run_graph(a.game, a.readers, True)
    q = st["__interrupt__"][0].value["queue"] if "__interrupt__" in st else []
    snap = build  # noqa: F841
    print(f"{a.game} · 판독기 {a.readers} · 차례 {len(st['turns'])} · 자동 확정 {len(st['decided'])} · 사람에게 {len(q)}")
    for d in q:
        print(f"  사람: {d['label']} — {', '.join(d['why'])} · " + " / ".join(f"{r}: {v and (v['kind'], v['k'], v['j'])}" for r, v in d["reads"].items()))
    hc.jsave(OUT / a.game / f"state_{a.readers}.json", {"decided": st["decided"], "queue": q, "rules": st["rules"]})


def right(a: dict | None, u: dict) -> bool:
    if not a or a.get("kind") != u["kind"]:
        return False
    return u["kind"] != "hand" or (a.get("k") == u["k_id"] and a.get("j") == u["j_closed"])


def cmd_score(a):
    truth = hc.jload(BASE / "truth_final.json")
    tot: dict = {}
    for gid in a.games:
        ts = [t for t in turns_of(gid) if t["id"] in truth]
        if not ts:
            print(gid, "정답 없음 — 건너뜀")
            continue
        reads = {"A": load_a(gid, False), "B": load_b(gid, False), "C": load_c(gid)}
        solo = {r: sum(right(norm(d.get(t["id"])), truth[t["id"]]) for t in ts) for r, d in reads.items() if d}
        print(f"\n== {gid} · 차례 {len(ts)} · 판독기 혼자 맞음: " + " · ".join(f"{r} {v}" for r, v in solo.items()))
        for r, v in solo.items():
            tot.setdefault("혼자 " + r, [0, 0])
            tot["혼자 " + r][0] += v
            tot["혼자 " + r][1] += len(ts)
        for combo in ("AB", "BC", "ABC"):
            if any(reads[r] is None for r in combo):
                continue
            st = run_graph(gid, combo, False, human=lambda q: {d["id"]: {"kind": truth[d["id"]]["kind"], "k": truth[d["id"]].get("k_id"), "j": truth[d["id"]].get("j_closed")} for d in q})
            auto = {i: d for i, d in st["decided"].items()}
            ok = sum(right(d, truth[i]) for i, d in auto.items())
            silent = [i for i, d in auto.items() if not right(d, truth[i])]
            rule = sum(d["src"].startswith("규칙") for d in auto.values())
            nq = len(st["human"])
            end = sum(right(st["final"][t["id"]], truth[t["id"]]) for t in ts)
            bad = sum(len(x["sort_bad"]) for x in st["rebuild"]["turns"])
            print(f"  {combo}: 자동 확정 {len(auto)}/{len(ts)}(규칙 {rule}) · 그중 맞음 {ok} · 조용한 틀림 {len(silent)} {silent or ''} · 사람에게 {nq} · 끝 결과 {end}/{len(ts)} · 복원 {'됨' if st['rebuild']['complete'] else '안 됨'}(정렬 어긋난 이웃 {bad})")
            c = tot.setdefault(combo, {"n": 0, "auto": 0, "ok": 0, "silent": 0, "human": 0, "end": 0})
            c["n"] += len(ts); c["auto"] += len(auto); c["ok"] += ok; c["silent"] += len(silent); c["human"] += nq; c["end"] += end
    print("\n합:")
    for k, v in tot.items():
        if isinstance(v, list):
            print(f"  {k}: {v[0]}/{v[1]}")
        else:
            print(f"  {k}: 자동 확정 {v['auto']}/{v['n']} · 그중 맞음 {v['ok']} · 조용한 틀림 {v['silent']} · 사람에게 {v['human']}({v['human'] / v['n']:.0%}) · 끝 결과 {v['end']}/{v['n']}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("game")
    r.add_argument("--readers", default="AB")
    c = sp.add_parser("score")
    c.add_argument("games", nargs="+")
    a = ap.parse_args()
    {"run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
