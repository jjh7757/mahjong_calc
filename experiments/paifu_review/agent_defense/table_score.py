"""대국 뒤 복기 대화 1단계 채점 — 설계서 docs/postgame_review_chat_design_1124.md "1단계 상세" 기준.

  python -X utf8 experiments/paifu_review/agent_defense/table_score.py [--fake] [--results 폴더] [--utterances 파일]
                                                                       [--server-repo 서버 worktree] [--out score.json]

table_run_1124.py 의 결과(results/table_1124{_fake}/<id>.json)와 대본 gold 를 맞춘다. **서버 모듈을 import 한다**
(--server-repo, 기본 mahjong-recognizer-table 을 sys.path 에 넣고 app.review_table 의 fill_claims · judge · check_answer 를 부름):
대본 gold 에 서버와 같은 기본값 채우기(패 · 자리)를 하고, 그 gold 주장으로 서버 판정 함수를 다시 불러 기대 판정을 낸다.

① 주장 뽑기 정답: 말마다 (종류, 패, 자리, visible 이면 장수, negated) 묶음이 gold(채운 뒤)와 같은가. gold 가 빈 목록(판정 묻기)이면
   [other] 로 본다(서버가 확인할 주장이 없을 때 내는 것). 종류만 · 주장 단위(정밀 · 재현)도 따로.
② 판정: gold 주장마다 응답 verdicts 에서 같은 주장을 찾아 결과가 기대 판정과 같은가(없으면 "못 뽑음"). 그리고 답 글을
   gold 기준 판정표로 다시 검사해 판정 일치 위반(맞장구 · 뒤집음 · 확인 불가 단정)을 센다. 대본 쓴 쪽의 의도(intent)와
   코드 판정이 다른 주장도 적는다(설계서: 다르면 판정 기준은 코드 쪽).
③ outcome · 재시도 · 뽑기 재시도 · 위반 · 서버 시간(elapsed_s) · 클라이언트 시간 · LLM 호출 · 토큰 · 확인 불가 비율.
"""
import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PR = HERE.parent
SERVER_REPO = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer-table")
AGREE_WORDS = ("맞장구", "뒤집음", "확인 불가인 주장을 단정")


def key(c: dict) -> tuple:
    """주장 비교 묶음: (종류, 패, 자리, visible 이면 장수, negated). negated 가 없으면 거짓(옛 응답 · gold)."""
    return (c.get("type"), c.get("tile"), c.get("wind"), c.get("count") if c.get("type") == "visible" else None,
            bool(c.get("negated")))


def pct(a: int, b: int) -> str:
    return f"{a}/{b}" + (f" ({100 * a / b:.0f}%)" if b else "")


def q(vals: list[float]) -> str:
    if not vals:
        return "-"
    s = sorted(vals)
    p90 = s[min(len(s) - 1, int(round(0.9 * (len(s) - 1))))]
    return f"{statistics.median(s):.2f} / {p90:.2f} / {s[-1]:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--results", type=Path)
    ap.add_argument("--utterances", type=Path, default=PR / "table_utterances_1124.json")
    ap.add_argument("--server-repo", type=Path, default=SERVER_REPO)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    sys.path.insert(0, str(args.server_repo))
    from app import review_table as rt  # noqa: E402 — 서버 판정 함수를 그대로 쓴다

    res_dir = args.results or PR / "results" / ("table_1124_fake" if args.fake else "table_1124")
    files = sorted(p for p in res_dir.glob("*.json") if p.name != "score.json")
    if not files:
        print(f"결과가 없다: {res_dir}")
        return 1
    utt_by_id = {}
    if args.utterances.is_file():
        utt_by_id = {u["id"]: u for u in json.loads(args.utterances.read_text(encoding="utf-8"))["utterances"]}

    rows = []
    ext_ok = ext_type_ok = 0
    c_tp = c_gold = c_resp = 0
    v_total = v_ok = v_missing = 0
    agree_viol: list[tuple] = []
    intent_diff: list[tuple] = []
    outcomes, kinds_fail = Counter(), Counter()
    retries = ext_retries = ext_fallback = 0
    final_viol: Counter = Counter()
    retry_viol: Counter = Counter()
    elapsed, client, llm, tok_in, tok_out = [], [], [], [], []
    results_all: Counter = Counter()
    by_kind: dict[str, Counter] = {}
    n_negated: Counter = Counter()
    n = 0
    for p in files:
        rec = json.loads(p.read_text(encoding="utf-8"))
        u = utt_by_id.get(rec["utterance"]["id"], rec["utterance"])
        sc = rec["scene"]
        resp = rec.get("response")
        if rec.get("status") != 200 or not isinstance(resp, dict):
            outcomes[f"HTTP {rec.get('status')}"] += 1
            continue
        n += 1
        facts = json.loads((PR / "results" / "table_facts" / "dart" / f"{sc['game']}.json").read_text(encoding="utf-8"))
        wind, step = sc["wind"], sc["step"]
        gold_raw = [{"type": g["type"], "tile": rt.norm(g.get("tile")) if g.get("tile") else None,
                     "wind": g.get("wind"), **({"count": g.get("count")} if g["type"] == "visible" else {}),
                     "negated": bool(g.get("negated"))}
                    for g in (u.get("gold") or [])]
        gold = rt.fill_claims(facts, wind, step, gold_raw)
        resp_claims = resp.get("claims") or []
        gk, rk = Counter(map(key, gold)), Counter(map(key, resp_claims))
        ok = gk == rk
        ext_ok += ok
        ext_type_ok += Counter(c["type"] for c in gold) == Counter(c["type"] for c in resp_claims)
        c_tp += sum((gk & rk).values())
        c_gold += sum(gk.values())
        c_resp += sum(rk.values())
        bk = by_kind.setdefault(u.get("kind", "?"), Counter())
        bk["n"] += 1
        bk["extract_ok"] += ok
        # ② 판정
        expected = rt.judge(facts, wind, step, gold)
        resp_v = {key(v["claim"]): v["result"] for v in resp.get("verdicts") or []}
        for g, ev in zip(gold, expected):
            v_total += 1
            got = resp_v.get(key(g))
            if got is None:
                v_missing += 1
            elif got == ev["result"]:
                v_ok += 1
        for gi, it, exp in zip(gold_raw, u.get("intent") or [], expected if gold_raw else []):  # 같은 차례(채우기는 순서를 지킴)
            if it.get("result") and it["result"] != exp["result"]:
                intent_diff.append((u["id"], gi["type"], gi.get("tile"), gi.get("wind"), it["result"], exp["result"]))
        e = rt.scene_event(facts, step)
        ans = resp.get("answer") or ""
        gold_check = [x for x in rt.check_answer(ans, expected, rt.norm(e["tile"]), e["turn_of_seat"])
                      if any(w in x for w in AGREE_WORDS)]
        if gold_check:
            agree_viol.append((u["id"], resp.get("outcome"), gold_check))
            bk["gold_agree_viol"] += 1
        # ③
        outcomes[resp.get("outcome")] += 1
        if resp.get("outcome") != "verified":
            kinds_fail[u.get("kind", "?")] += 1
        retries += resp.get("retries") or 0
        ex = resp.get("extract") or {}
        ext_retries += ex.get("retries") or 0
        ext_fallback += bool(ex.get("fallback"))
        for x in resp.get("violations") or []:
            final_viol[x.split(":")[0]] += 1
        for vs in resp.get("retry_violations") or []:
            for x in vs:
                retry_viol[x.split(":")[0]] += 1
        for v in resp.get("verdicts") or []:
            results_all[v["result"]] += 1
        elapsed.append(resp.get("elapsed_s") or 0.0)
        client.append(rec.get("client_s") or 0.0)
        us = resp.get("usage") or {}
        llm.append(us.get("llm_calls") or 0)
        tok_in.append(us.get("input_tokens") or 0)
        tok_out.append(us.get("output_tokens") or 0)
        n_negated["gold"] += sum(1 for c in gold if c.get("negated"))
        n_negated["resp"] += sum(1 for c in resp_claims if c.get("negated"))
        n_negated["both"] += sum(1 for c in (gk & rk).elements() if c[4])
        rows.append({"id": u["id"], "kind": u.get("kind"), "extract_ok": ok, "gold": [key(c) for c in gold],
                     "resp": [key(c) for c in resp_claims], "outcome": resp.get("outcome"), "retries": resp.get("retries"),
                     "gold_agree_viol": gold_check})

    print(f"결과 {res_dir} · 응답 {n}개(HTTP 오류 {sum(v for k, v in outcomes.items() if str(k).startswith('HTTP'))})")
    print(f"① 주장 뽑기 정답(종류 · 패 · 자리 · 장수 · negated, 채운 뒤): {pct(ext_ok, n)} · 종류만 {pct(ext_type_ok, n)} · "
          f"주장 단위 정밀 {pct(c_tp, c_resp)} · 재현 {pct(c_tp, c_gold)}")
    print(f"   negated 주장: gold {n_negated['gold']} · 응답 {n_negated['resp']} · 같음 {n_negated['both']}")
    for k, c in sorted(by_kind.items()):
        print(f"   {k:12} 뽑기 {pct(c['extract_ok'], c['n'])} · gold 기준 판정 일치 위반 {c['gold_agree_viol']}")
    print(f"② 판정(gold 주장 기준 서버 판정과 같음): {pct(v_ok, v_total)} · 못 뽑음 {v_missing}")
    print(f"   gold 기준 판정표로 다시 검사한 답의 판정 일치 위반: {len(agree_viol)}개")
    for x in agree_viol:
        print(f"     {x[0]} ({x[1]}): {' / '.join(x[2])}")
    print(f"   대본 의도와 코드 판정이 다른 주장: {len(intent_diff)}개")
    for x in intent_diff:
        print(f"     {x[0]} {x[1]} tile={x[2]} wind={x[3]}: 의도 {x[4]} → 코드 {x[5]}")
    print(f"③ outcome {dict(outcomes)} · 답 재시도 {retries} · 뽑기 재시도 {ext_retries} · 뽑기 대체(other) {ext_fallback}")
    print(f"   검증 안 된 말의 종류: {dict(kinds_fail) or '없음'}")
    print(f"   마지막 위반(대체 답): {dict(final_viol) or '없음'}")
    print(f"   재시도를 부른 위반: {dict(retry_viol) or '없음'}")
    print(f"   판정 결과 분포: {dict(results_all)} · 확인 불가 비율 {pct(results_all['확인 불가'], sum(results_all.values()))}")
    print(f"   서버 시간 중앙/p90/최대 {q(elapsed)}초 · 클라이언트 {q(client)}초")
    print(f"   LLM 호출 합 {sum(llm)} (말당 {q([float(x) for x in llm])}) · 토큰 입력 {sum(tok_in)} · 출력 {sum(tok_out)}")
    out = args.out or res_dir / "score.json"
    summary = {"n": n, "extract_ok": ext_ok, "extract_type_ok": ext_type_ok, "claim_tp": c_tp, "claim_gold": c_gold,
               "claim_resp": c_resp, "negated": dict(n_negated), "verdict_ok": v_ok, "verdict_total": v_total, "verdict_missing": v_missing,
               "gold_agree_viol": agree_viol, "intent_diff": intent_diff, "outcomes": dict(outcomes),
               "retries": retries, "extract_retries": ext_retries, "extract_fallback": ext_fallback,
               "final_violations": dict(final_viol), "retry_violations": dict(retry_viol), "results": dict(results_all),
               "elapsed_s": elapsed, "client_s": client, "llm_calls": llm, "tokens_in": sum(tok_in),
               "tokens_out": sum(tok_out), "rows": rows, "scored_with": "server app.review_table import (" +
               str(args.server_repo) + ")"}
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
