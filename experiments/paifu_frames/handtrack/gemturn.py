"""한 차례(버림 하나)를 Gemini 에 통째로 읽히기 — 종류 · 나간 칸 · 들어간 칸(2026-11-17, 계획서 3단계 "추가 9" — 방법·기준은 결과 전에 적음).
사용자 "제미나이 읽기도 시도해봐". 재료는 사람이 확인 페이지에서 본 것과 같은 차례 묶음(truthprep), 초당 5장.

  python -X utf8 gemturn.py count <판 id>                 # 호출 없이 프레임 수만
  python -X utf8 gemturn.py run <판 id> [--rep 1]          # → _work/gemturn_1117/answers/<판>_<모델>_r<회>.json
  python -X utf8 gemturn.py score <판 id>                  # 사용자 정답(k_orig · j_closed)과 채점
요청에는 프레임 · 시각 · 구간 경계 · 줄 장수만 들어간다(정답 · 강 패 종류 · 화소 판정 없음).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemframes as gf  # noqa: E402
import htcommon as hc  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
OUT = hc.WORK / "gemturn_1117"
STEP = 2  # 초당 5장

PROMPT = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 연속 프레임이다. 프레임은 시간 순서이고 각 그림 앞에 시각(분:초)을 적었다.
그림은 그 사람 시점으로 돌려져 있다: 그림의 왼쪽 = 그 사람의 왼손 쪽. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 무늬는 안 보인다. 줄 아래쪽의 흰 띠는 탁자 테두리다.
다른 사람의 팔이나 소매가 줄 위를 지나가기도 한다 — 줄 아래쪽에 앉은 이 사람의 손 동작만 본다.

프레임은 이 사람의 **한 차례**(패산에서 한 장을 뽑아 오고, 한 장을 강에 버림)와 그 앞뒤다. 손이 움직인 구간만 이어 붙였고 구간이 바뀌는 곳에 표시를 넣었다:
"버림 구간" 에서 이 차례의 버림이 일어난다. "앞 구간" 은 그 전의 손 움직임(뽑기가 여기 있을 수 있다), "뒤 구간" 은 버린 뒤 다음에 뽑기 전까지의 손 움직임(뽑은 패를 다시 집어 옮기는 일이 여기 있을 수 있다. 다음 차례의 뽑기가 끝에 보이면 무시한다).
이 차례를 시작할 때 줄은 {n}장이다. 뽑아 온 패를 D 라고 부르자.

답할 것:
- kind: "tsumogiri" = D 를 그대로 버림(줄의 패는 안 바뀜. D 를 줄 끝에 잠깐 붙였다가 그 패를 버려도, 줄에 안 대고 쥔 채 버려도 쯔모기리) / "hand" = 줄에 있던 패를 버리고 D 가 줄에 남음 / "unseen" = 가려서 알 수 없음.
- k (hand 일 때만): 버린 패가 원래 줄 {n}장에서 왼쪽부터 몇 번째였나(1 ~ {n}). D 는 세지 않는다 — D 를 먼저 줄에 끼운 뒤 버렸더라도 D 를 뺀 번호로 답한다.
- j (hand 일 때만): 이 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째에 서 있나(1 ~ {n}). 끝에 그대로 두었으면 {n}.

참고:
- 깨끗한(손이 안 닿은) 프레임에서 패를 하나씩 센다. 손가락이 줄 위에 얹혀 끊겨 보이는 것은 빈칸이 아니다 — 사이로 초록 펠트가 보여야 빈칸이다.
- D 를 끝에 붙여 두고 한 장을 버린 뒤 그대로 두는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 나서 버리는 사람이 다 있다.
- 넣는 순간이 손에 가려지면, 제자리에 그대로 남은 패가 왼쪽·오른쪽에 몇 장인지와 손이 옮긴 패가 몇 장인지로 따진다. 버린 패가 빠진 빈자리와 D 를 넣으려고 벌린 틈을 헷갈리지 말 것.

JSON 으로만 답하라: steps = 본 것을 시각과 함께 짧게(3~6문장), kind, k, j(해당 없으면 null), confidence = "high" 또는 "low".
"""
SCHEMA = {"type": "OBJECT", "properties": {
    "steps": {"type": "STRING"}, "kind": {"type": "STRING", "enum": ["tsumogiri", "hand", "unseen"]},
    "k": {"type": "INTEGER", "nullable": True}, "j": {"type": "INTEGER", "nullable": True},
    "confidence": {"type": "STRING", "enum": ["high", "low"]}}, "required": ["steps", "kind", "k", "j", "confidence"]}
ROLE = {"앞": "앞 구간", "버림": "버림 구간", "뒤": "뒤 구간"}


def turns_of(gid: str) -> list:
    return next(x for x in hc.jload(BASE / "turns.json")["games"] if x["id"] == gid)["turns"]


def frames_of(t: dict) -> list:
    return [(s["role"], ms) for s in t["segs"] for ms in s["frames"][::STEP]]


def parts_of(t: dict, types):
    n = t["n_calc"] or 13
    ps = [PROMPT.format(n=n)]
    last = None
    for s in t["segs"]:
        ps.append(f"—— {ROLE[s['role']]} 시작({hc.hms(s['frames'][0])[3:]}) ——")
        for ms in s["frames"][::STEP]:
            ps.append(f"프레임 {hc.hms(ms)[3:]}")
            part = types.Part.from_bytes(data=(BASE / "frames" / t["game"] / f"{ms}.jpg").read_bytes(), mime_type="image/jpeg")
            part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
            ps.append(part)
    ps.append(f"위 프레임을 보고 답하라. 차례를 시작할 때 줄은 {n}장이다.")
    return ps


def one(c, types, model, t):
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA)
    t0 = time.perf_counter()
    err = ""
    for attempt in range(3):
        try:
            r = c.models.generate_content(model=model, contents=parts_of(t, types), config=cfg)
            um = r.usage_metadata
            d = json.loads(r.text)
            return {"id": t["id"], "kind": d.get("kind"), "k": d.get("k"), "j": d.get("j"), "confidence": d.get("confidence"), "steps": d.get("steps"),
                    "frames": len(frames_of(t)), "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                    "think": getattr(um, "thoughts_token_count", 0) or 0, "attempt": attempt + 1}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(8 * (attempt + 1))
    return {"id": t["id"], "kind": None, "k": None, "j": None, "error": err, "frames": len(frames_of(t)), "s": round(time.perf_counter() - t0, 1), "in": 0, "out": 0, "think": 0}


def cmd_count(a):
    ts = turns_of(a.game)
    n = [len(frames_of(t)) for t in ts]
    print(a.game, "차례", len(ts), "프레임", sum(n), "차례당", min(n), "~", max(n))


def cmd_run(a):
    from google.genai import types
    ts = turns_of(a.game)
    f = OUT / "answers" / f"{a.game[:3]}_{a.model}_r{a.rep}.json"
    if f.exists() and not a.force:
        print("있음 — 건너뜀", f.name)
        return
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(lambda t: one(gf.client(), types, a.model, t), ts))
    hc.jsave(f, {"game": a.game, "model": a.model, "rep": a.rep, "step": STEP, "at": hc.hms(int(time.time() * 1000), date=True), "rows": rows})
    print(f.name, "입력", sum(r["in"] for r in rows), "출력", sum(r["out"] for r in rows), "생각", sum(r["think"] for r in rows), "오류", sum("error" in r for r in rows))


def cmd_score(a):
    ans = hc.jload(BASE / "truth_final.json")  # truthnorm.py — 패 자체 k_id · 버리는 순간 자리 k_pos · 끝난 뒤 뽑은 패 자리 j_closed
    ts = turns_of(a.game)
    for f in sorted((OUT / "answers").glob(f"{a.game[:3]}_*.json")):
        d = hc.jload(f)
        by = {r["id"]: r for r in d["rows"]}
        c = Counter()
        print(f"== {f.name} ({d['at']}) 입력 {sum(r['in'] for r in d['rows']):,} · 생각 {sum(r['think'] for r in d['rows']):,} · 초 중앙 {sorted(r['s'] for r in d['rows'])[len(d['rows']) // 2]}")
        print("차례 | 정답(종류 k j) | 답(종류 k j, 확신) | 판정 | 본 것")
        for t in ts:
            u, r = ans.get(t["id"]) or {}, by.get(t["id"]) or {}
            tk = u.get("k_id") if u.get("kind") == "hand" else None
            tj = u.get("j_closed") if u.get("kind") == "hand" else None
            kind_ok = r.get("kind") == u.get("kind")
            c["종류 맞음"] += kind_ok
            whole = kind_ok
            v = ["종류 " + ("✓" if kind_ok else "✗")]
            if u.get("kind") == "hand":
                c["손에서(정답)"] += 1
                kok, jok = kind_ok and r.get("k") == tk, kind_ok and r.get("j") == tj
                c["나간 칸 맞음"] += kok
                c["나간 칸 — 자리만 맞음(패는 다름)"] += bool(kind_ok and not kok and r.get("k") == u.get("k_pos"))
                c["들어간 칸 맞음"] += jok
                c["들어간 칸 한 칸 차"] += bool(kind_ok and r.get("j") is not None and abs(r["j"] - tj) == 1)
                whole = kok and jok
                v += ["k " + ("✓" if kok else "✗"), "j " + ("✓" if jok else "✗")]
            c["차례 전체 맞음"] += whole
            c["확신 high"] += r.get("confidence") == "high"
            c["확신 high 인데 틀림"] += r.get("confidence") == "high" and not whole
            print(f"{t.get('label', t['i']):>3} | {u.get('kind')} {tk or ''}{'(자리 ' + str(u['k_pos']) + ')' if u.get('k_pos') not in (None, tk) else ''} {tj or ''}{' ?' if u.get('status') == 'fixed' else ''} | {r.get('kind')} {r.get('k') or ''} {r.get('j') or ''} {r.get('confidence') or ''} | {' '.join(v)} | {(r.get('steps') or r.get('error') or '')[:150]}")
        print(f"차례 {len(ts)} · " + " · ".join(f"{k} {v}" for k, v in c.items()))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "run", "score"):
        p = sp.add_parser(name)
        p.add_argument("game")
        if name == "run":
            p.add_argument("--model", default="gemini-3.8-flash")
            p.add_argument("--rep", type=int, default=1)
            p.add_argument("--workers", type=int, default=3)
            p.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"count": cmd_count, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
