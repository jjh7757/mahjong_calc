"""a5 대 a6 말투 비교 집계(agent_run_1123_tone.py 결과). 판마다: 검증(첫 / 재시도 뒤) · 대체 · 재시도 까닭 · 시간 · 토큰,
그리고 최종 답에 a6 의 새 검사(check_tone)와 따로 쓴 낱말 목록 검사를 건 결과. 도구 결과는 사실표로 다시 만든다.

  python -X utf8 experiments/paifu_review/agent_defense/tone_stats.py [결과 폴더 이름(기본 agent_1123tone)]
"""
import json
import re
import statistics
import sys
from pathlib import Path

SRV = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer-review")
sys.path.insert(0, str(SRV))
from app import review_agent as ra  # noqa: E402

PR = Path(__file__).resolve().parents[1]
APP = PR.parents[1]
RES = PR / "results" / (sys.argv[1] if len(sys.argv) > 1 else "agent_1123tone")
QS = {q["id"]: q for q in json.loads((PR / "agent_questions_1123_tone.json").read_text(encoding="utf-8"))["questions"]}
MINE = ["사실상", "비교적", "무난", "깔끔", "성공적", "승리", "훌륭", "현명", "안타깝", "기록되었", "셈이다", "우선할 수 있었", "볼 수 있다"]


def facts_of(q):
    if q.get("facts"):
        p = Path(q["facts"])
        p = p if p.is_absolute() else APP / p
    else:
        p = SRV / "tests" / "fixtures" / "agent_facts" / f"{q['game']}.json"
    return json.loads(p.read_text(encoding="utf-8"))


for ver in ("a5", "a6"):
    rows = []
    for qid, q in QS.items():
        f = RES / ver / f"{qid}.json"
        if not f.exists():
            rows.append({"id": qid, "missing": True})
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        facts = facts_of(q)
        ev = [{"tool": c["tool"], "args": c.get("args") or {}, "result": ra.run_tool(facts, c["tool"], c.get("args") or {})}
              for c in d.get("tool_calls") or []]
        ans = d.get("answer") or ""
        plain = re.sub(r"\[[^\]]*\]", " ", ans)
        rv = d.get("retry_violations") or []
        rvs = json.dumps(rv, ensure_ascii=False)
        rows.append({
            "id": qid, "set": q.get("set"), "outcome": d.get("outcome"), "retries": d.get("retries", 0),
            "pv": d.get("prompt_version"), "elapsed": d.get("elapsed_s"),
            "in": (d.get("usage") or {}).get("input_tokens") or (d.get("usage") or {}).get("prompt_tokens"),
            "tone": ra.check_tone(ans, ev) if ans else [], "mine": [w for w in MINE if w in plain],
            "new_retry": ("평가 말" in rvs) or ("리치 없는 질문" in rvs), "rv": rv,
        })
    ok = [r for r in rows if not r.get("missing")]
    el = sorted(r["elapsed"] for r in ok if r["elapsed"] is not None)
    print(f"== {ver}: 답 {len(ok)}/{len(rows)} · prompt_version {sorted({r['pv'] for r in ok})}")
    print("  검증(최종 verified)", sum(r["outcome"] == "verified" for r in ok),
          "· 첫 통과", sum(r["outcome"] == "verified" and r["retries"] == 0 for r in ok),
          "· 대체", sum(r["outcome"] == "fallback" for r in ok),
          "· 재시도 있는 답", sum(r["retries"] > 0 for r in ok),
          "· 새 검사 탓 재시도", sum(r["new_retry"] for r in ok))
    if el:
        p90 = el[min(len(el) - 1, int(round(0.9 * (len(el) - 1))))]
        print(f"  서버 시간 중앙 / p90 / 최대 {statistics.median(el):.1f} / {p90:.1f} / {el[-1]:.1f}")
    print("  최종 답에 새 검사 걸림", sum(bool(r["tone"]) for r in ok), "· 낱말 목록 걸림", sum(bool(r["mine"]) for r in ok))
    for r in ok:
        if r["tone"] or r["mine"] or r["retries"] or r["outcome"] != "verified":
            print(f"   {r['id']}: {r['outcome']} 재시도 {r['retries']} 검사 {r['tone']} 목록 {r['mine']} 재시도 까닭 {r['rv']}"[:400])
    for r in rows:
        if r.get("missing"):
            print("   없음:", r["id"])
