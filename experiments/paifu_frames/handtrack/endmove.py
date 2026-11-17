"""패 옮김 점검 판독기 E — "뽑은 패 D 가 아닌 패가 줄에서 빠졌다가 버려지지 않고 줄에 다시 놓였나" 한 가지만 묻는다
(2026-11-17, 계획서 3단계 "추가 12" — 방법 · 기준 · 비용 상한은 돌리기 전에 적음. metrics 표 12-27 의 조용한 틀림을 겨냥).

  python -X utf8 endmove.py count <판 id…>                         # 호출 없이 프레임 · 토큰 어림
  python -X utf8 endmove.py run <판 id> [--ids a,b] [--ver 1] [--step 2] [--crop 0.55]
  python -X utf8 endmove.py score <판 id…> [--ver 1] [--step 2] [--crop 0.55]   # 호출 없음
요청에는 줄의 오른쪽을 자른 프레임 · 시각 · 구간 경계만 들어간다(정답 · 다른 판독기 답 · 패 종류 없음).
E 는 답을 바꾸지 않는다: 판독기 일치로 자동 확정될 차례에서 E 가 yes/unsure 면 사람에게 넘기기만 한다(리치 뒤 규칙 차례는 안 부름).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemframes as gf  # noqa: E402
import gemturn as gt  # noqa: E402
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
OUT = hc.WORK / "endmove_1117"
MODEL = "gemini-3.8-flash"
TOK_PER_IMG = 1100  # 어림(표 12-26 의 B: 프레임당 약 1,090)

HEAD = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 연속 프레임이다. **줄의 오른쪽 부분만 잘라 낸 그림**이다 — 그림 왼쪽 가장자리에서 줄이 잘려 있고, 줄의 오른쪽 끝은 그림 안에 있다. 프레임은 시간 순서이고 각 그림 앞에 시각(분:초)을 적었다.
그림은 그 사람 시점으로 돌려져 있다. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 무늬는 안 보인다. 줄 아래쪽의 흰 띠는 탁자 테두리다.
다른 사람의 팔이나 소매가 줄 위를 지나가기도 한다 — 줄 아래쪽에 앉은 이 사람의 손 동작만 본다.

프레임은 이 사람의 **한 차례**(패산에서 한 장을 뽑아 오고 — 이 패를 D 라 부르자 — 한 장을 강에 버림)와 그 앞뒤다. 손이 움직인 구간만 이어 붙였고 구간이 바뀌는 곳에 표시를 넣었다("앞 구간" · "버림 구간" · "뒤 구간". 뒤 구간 끝에 다음 차례의 뽑기가 보이면 무시한다).
"""

V1 = HEAD + """
물음은 하나다: **D 가 아닌, 원래 줄에 서 있던 패가 줄에서 떨어져 나왔다가 강으로 가지 않고 줄에 다시 놓인 일이 있었는가.**

찾는 동작:
- 줄 끝에 붙여 둔 D 의 옆 패를 손가락으로 아래로 끌어내거나 집어서 D 의 오른쪽(줄 맨 끝)에 다시 붙임 — 그 결과 D 가 맨 끝이 아니게 된다.
- 줄 안의 패 한 장을 빼서 줄의 오른쪽 끝으로 옮겨 놓음(그 패를 나중에 버리더라도 해당한다).
- 이웃한 두 패의 자리를 맞바꿈.
해당하지 않는 것: D 를 줄에 붙이거나 끼우는 것, D 를 다시 집어 다른 자리에 끼우는 것, 패 한 장을 집어 곧바로 강에 버리는 것, 빈칸을 메우려고 패들을 줄 방향으로 밀어 붙이는 것(순서가 안 바뀐다), 손가락으로 줄을 가지런히 누르는 것.

보는 법:
- 줄에서 패가 떨어져 나온 순간을 찾는다: 줄 사이로 초록 펠트가 보이는 빈칸이 새로 생기고, 손 밑이나 줄 아래쪽에 줄에서 벗어난 패가 보인다.
- 떨어져 나온 패가 어디로 갔는지 끝까지 따라간다: 그림 위쪽(강)으로 나가 사라졌는가, 줄에 다시 붙었는가. 다시 붙었다면 줄 맨 오른쪽 끝인가, 원래 빈칸인가, 다른 자리인가.
- D 가 줄 끝에 손이 안 닿은 채 서 있는데 그 왼쪽에 빈칸이 생기고, 나중에 D 의 오른쪽에 패가 붙어 있으면 옮김이다.
- 패 여러 장이 줄에서 빠졌다 다시 붙었는데 손에 가려 순서가 바뀌었는지 못 봤으면 "unsure".

JSON 으로만 답하라: steps = 본 것을 시각과 함께 짧게(3~6문장), moved = "yes" | "no" | "unsure", where = "D 의 오른쪽" | "다른 자리" | "해당 없음", when = 옮김이 일어난 시각(분:초, 없으면 빈 글).
"""
PROMPTS = {1: V1}
SCHEMA = {"type": "OBJECT", "properties": {
    "steps": {"type": "STRING"}, "moved": {"type": "STRING", "enum": ["yes", "no", "unsure"]},
    "where": {"type": "STRING", "enum": ["D 의 오른쪽", "다른 자리", "해당 없음"]}, "when": {"type": "STRING"}},
    "required": ["steps", "moved", "where", "when"]}

# 본 판에서 정답 메모로 추린 "옮김 있는 차례"(계획서 추가 12). 새 판은 derive_pos 로 뽑고 사람이 메모를 다시 본다.
POS_DEV = {"r11_d09", "r12_d02", "r14_d02", "r17_d11", "r19_d07"}
DEV = ("r11_130921", "r12_131655", "r14_133610", "r17_140450", "r19_142013")
MOVE_RE = re.compile(r"교환|맞바꿈|맞바꾸|바꿈|바꾸|바꿔|옮겨|옮김|옮기")


def arm_of(a) -> str:
    return f"v{a.ver}_s{a.step}_c{int(a.crop * 100)}"


def rule_turns(ts: list) -> set:
    """리치 선언(가로 패) 뒤 차례 — pgraph.n_rules 와 같은 규칙."""
    out, riichi = set(), False
    for t in ts:
        if riichi:
            out.add(t["id"])
        riichi = riichi or bool(t.get("sideways"))
    return out


def frames_of(t: dict, step: int) -> list:
    return [(s["role"], ms) for s in t["segs"] for ms in s["frames"][::step]]


def img(types, gid: str, ms: int, crop: float):
    im = Image.open(BASE / "frames" / gid / f"{ms}.jpg")
    w, h = im.size
    im = im.crop((w - int(w * crop), 0, w, h))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
    part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
    return part


def parts_of(t: dict, types, ver: int, step: int, crop: float) -> list:
    ps = [PROMPTS[ver]]
    for s in t["segs"]:
        ps.append(f"—— {gt.ROLE[s['role']]} 시작({hc.hms(s['frames'][0])[3:]}) ——")
        for ms in s["frames"][::step]:
            ps.append(f"프레임 {hc.hms(ms)[3:]}")
            ps.append(img(types, t["game"], ms, crop))
    ps.append("위 프레임을 보고 답하라.")
    return ps


def one(c, types, t: dict, ver: int, step: int, crop: float) -> dict:
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA)
    t0, err, n = time.perf_counter(), "", len(frames_of(t, step))
    for attempt in range(3):
        try:
            r = c.models.generate_content(model=MODEL, contents=parts_of(t, types, ver, step, crop), config=cfg)
            um, d = r.usage_metadata, json.loads(r.text)
            return {"id": t["id"], "moved": d.get("moved"), "where": d.get("where"), "when": d.get("when"), "steps": d.get("steps"), "frames": n,
                    "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                    "think": getattr(um, "thoughts_token_count", 0) or 0, "attempt": attempt + 1}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(8 * (attempt + 1))
    return {"id": t["id"], "moved": None, "error": err, "frames": n, "s": round(time.perf_counter() - t0, 1), "in": 0, "out": 0, "think": 0}


def load(gid: str, arm: str) -> dict:
    f = OUT / arm / f"{gid}.json"
    return {r["id"]: r for r in hc.jload(f)["rows"]} if f.exists() else {}


def flag(r: dict | None) -> bool | None:
    """E 가 사람에게 넘기라고 하는가. 답이 없으면 None(이때도 사람에게)."""
    if not r or not r.get("moved"):
        return None
    return r["moved"] in ("yes", "unsure")


def dollars(rows) -> float:
    return sum(r.get("in", 0) for r in rows) * 0.75e-6 + sum(r.get("out", 0) + r.get("think", 0) for r in rows) * 3.75e-6


def cmd_count(a):
    tot = 0
    for gid in a.games:
        ts = gt.turns_of(gid)
        rule = rule_turns(ts)
        n = [len(frames_of(t, a.step)) for t in ts if t["id"] not in rule]
        tot += sum(n)
        print(f"{gid}: 리치 뒤 아닌 차례 {len(n)} · 프레임 {sum(n)}(초당 {10 // a.step}장) · 어림 {sum(n) * TOK_PER_IMG:,} 토큰 = {sum(n) * TOK_PER_IMG * 0.75e-6:.2f}달러")
    print(f"합 프레임 {tot} · 어림 {tot * TOK_PER_IMG * 0.75e-6:.2f}달러(입력만)")


def cmd_run(a):
    from google.genai import types
    arm, gid = arm_of(a), a.game
    ts = gt.turns_of(gid)
    rule = rule_turns(ts)
    have = load(gid, arm)
    want = [t for t in ts if t["id"] not in rule and (not a.ids or t["id"] in a.ids.split(","))]
    todo = [t for t in want if not (have.get(t["id"]) or {}).get("moved")]
    print(f"{gid} · {arm} · 부를 차례 {len(todo)}(이미 있음 {len(want) - len(todo)}) · 프레임 {sum(len(frames_of(t, a.step)) for t in todo)}")
    if todo:
        with ThreadPoolExecutor(3) as ex:
            rows = list(ex.map(lambda t: one(gf.client(), types, t, a.ver, a.step, a.crop), todo))
        for r in rows:
            have[r["id"]] = r
        order = {t["id"]: n for n, t in enumerate(ts)}
        hc.jsave(OUT / arm / f"{gid}.json", {"game": gid, "model": MODEL, "arm": arm, "at": hc.hms(int(time.time() * 1000), date=True),
                                             "rows": sorted(have.values(), key=lambda r: order[r["id"]])})
        print(f"  새 호출: 입력 {sum(r['in'] for r in rows):,} · 출력+생각 {sum(r['out'] + r['think'] for r in rows):,} · {dollars(rows):.2f}달러 · 오류 {sum('error' in r for r in rows)}"
              f" · 호출 최대 {max(r['s'] for r in rows):.0f}초")
    # 답은 찍지 않는다(가린 판에서도 쓰려고) — score 로 본다.


def derive_pos(gid: str, truth: dict, ans: dict) -> set:
    """새 판의 옮김 차례 후보: 정답에서 패 번호 ≠ 자리 번호이거나 사용자 메모에 옮김 · 맞바꿈 말이 있는 차례."""
    out = set()
    for i, u in truth.items():
        if u.get("game") != gid:
            continue
        if (u.get("k_id") is not None and u.get("k_id") != u.get("k_pos")) or MOVE_RE.search((ans.get(i) or {}).get("note") or ""):
            out.add(i)
    return out


def cmd_score(a):
    import pgraph as pg
    arm = arm_of(a)
    truth, ans = hc.jload(BASE / "truth_final.json"), hc.jload(BASE / "answers_user.json")
    tot = {"pos": 0, "hit": 0, "neg": 0, "fa": 0, "none": 0}
    comb = {"n": 0, "auto": 0, "silent": 0, "human": 0, "rule": 0, "base_silent": 0, "base_human": 0}
    for gid in a.games:
        ts = [t for t in gt.turns_of(gid) if t["id"] in truth]
        rule, E = rule_turns(gt.turns_of(gid)), load(gid, arm)
        pos = (POS_DEV if gid in DEV else derive_pos(gid, truth, ans)) & {t["id"] for t in ts}
        A, B = pg.load_a(gid, False), pg.load_b(gid, False)
        print(f"\n== {gid} · {arm} · 차례 {len(ts)}(규칙 {len([t for t in ts if t['id'] in rule])}) · 옮김 차례 {sorted(pos)} · E 비용 {dollars(E.values()):.2f}달러")
        for t in ts:
            i, u = t["id"], truth[t["id"]]
            if i in rule:
                if A and B:
                    comb["n"] += 1
                    comb["rule"] += 1
                continue
            e, f = E.get(i), flag(E.get(i))
            if f is None:
                tot["none"] += 1
            if i in pos:
                tot["pos"] += 1
                tot["hit"] += f is not False
            else:
                tot["neg"] += 1
                tot["fa"] += f is not False
            mark = ("잡음" if f is not False else "놓침") if i in pos else ("헛 경보" if f is not False else "")
            line = f"  {i:9s} {'옮김' if i in pos else '    '} E={(e or {}).get('moved') or '없음':6s} {(e or {}).get('where') or '':8s} {mark}"
            if A and B:
                na, nb = pg.norm(A.get(i)), pg.norm(B.get(i))
                same = na is not None and nb is not None and (na["kind"], na["k"], na["j"]) == (nb["kind"], nb["k"], nb["j"]) and not na["unsure"] and na["kind"] != "unseen"
                ok = same and pg.right(na, u)
                comb["n"] += 1
                comb["base_silent"] += same and not ok
                comb["base_human"] += not same
                if same and f is False:
                    comb["auto"] += 1
                    comb["silent"] += not ok
                else:
                    comb["human"] += 1
                line += f" | A=B {'같음' if same else '갈림'}" + ("" if not same else (" 맞음" if ok else " **틀림**")) + (" → 사람" if (not same or f is not False) else " → 자동")
            print(line)
    print(f"\n합({arm}): 옮김 {tot['hit']}/{tot['pos']} 잡음 · 헛 경보 {tot['fa']}/{tot['neg']}" + (f" · 답 없음 {tot['none']}" if tot["none"] else ""))
    if comb["n"]:
        n = comb["n"]
        print(f"  A+B(E 없이): 조용한 틀림 {comb['base_silent']} · 사람 {comb['base_human']}/{n}({comb['base_human'] / n:.0%})")
        print(f"  A+B+E: 자동 {comb['auto'] + comb['rule']}/{n}(규칙 {comb['rule']}) · 조용한 틀림 {comb['silent']} · 사람 {comb['human']}/{n}({comb['human'] / n:.0%})")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "run", "score"):
        p = sp.add_parser(name)
        p.add_argument("game" if name == "run" else "games", **({} if name == "run" else {"nargs": "+"}))
        p.add_argument("--ver", type=int, default=1)
        p.add_argument("--step", type=int, default=2)
        p.add_argument("--crop", type=float, default=0.55)
        if name == "run":
            p.add_argument("--ids", default="")
    a = ap.parse_args()
    {"count": cmd_count, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
