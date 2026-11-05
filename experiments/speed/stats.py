"""두 측정의 차이에 부트스트랩 95% 구간을 붙인다(개선 계획 2단계, 2026-11-05). 계산은 표준 라이브러리만(random·statistics).

  python -I -X utf8 experiments/speed/stats.py diff <측정 A> <측정 B> [--n 1000] [--seed 0]   B − A 의 구간
  python -I -X utf8 experiments/speed/stats.py show <측정>                                     한 측정의 합계

<측정> = 앱 흐름 로그(TIMING 줄) 여러 개를 쉼표로 이은 것, 또는 `server_bench/field_bench.py` 결과 JSON(rows).
  - 개발 세트 로그(B·C·D·매장): `flow_visit.records` 로 채점(맞음 = 손패·울기·화료패, 패 단위 = 손패+울기 다중집합 교집합).
  - 테스트 15장 로그(장면 이름이 F…): `experiments/rectify/summarize_field.records`(손패(울기 포함) 맞음, 패 /211).
  - field_bench JSON: hybrid 자리 채점(화료패 뺀 13장, 패 /196, `seat_hit`·`seat_want` 가 든 2단계 이후 결과).
    여기엔 경고 개념이 없어 "경고 없는 틀린 자동" 자리에 자리 검사(`hy.check`) 통과인데 틀린 수(`seat_bad`)가 들어간다.

재추출은 **묶음 단위**: 같은 판을 찍은 사진들은 독립이 아니라서 묶음째 뽑는다.
  - 테스트 15장 = 장면 5개(F1229·F1240·F대삼원 8장·F1400 4장·F1434).
  - 개발 B·C·D = 장면 글자 B/C/D(같은 판 사진 두 장 × 2회 = 4행), 매장 = 사진 한 장(1행).
짝: 두 측정에 다 있는 (사진, 회차) 만 쓴다(서버 이름은 무시). 묶음을 복원 추출해 지표마다 B − A 를 1,000번 다시 재고
2.5·97.5 백분위를 구간으로 한다. 지표 = 장면 단위(맞은 비율, 행 수를 곱해 '회' 로도), 패 단위(Σ맞은 패 / Σ정답 패),
경고 없는 틀린 자동(비율).

**적는 규칙: 구간이 0 을 포함하면 "같음" 으로 적는다** — 점 추정이 +2 여도 차이가 있다고 쓰지 않는다. 0 을 포함하지 않을 때만
"B 가 높음/낮음". 묶음이 5개뿐인 테스트 15장은 구간이 넓어 거의 늘 "같음" 이고, 그게 이 세트의 해상도다(계획서 0-1 ⑤).
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _ms(v) -> float:
    """field_bench 의 hybrid ms 는 단계별 dict(서버 안 시간 합) 또는 숫자."""
    if isinstance(v, dict):
        return float(sum(x for x in v.values() if isinstance(x, (int, float))))
    return float(v or 0)


def load(spec: str) -> list[dict]:
    """측정 하나 → 행별 기록 [{key, cluster, ok, hit, want, bad_auto, sec}]."""
    paths = [p for p in spec.split(",") if p]
    if len(paths) == 1 and paths[0].endswith(".json"):
        j = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
        out = []
        for ph, r in j["rows"].items():
            if "seat_hit" not in r:
                raise SystemExit(f"{paths[0]}: seat_hit 없음 — 2단계 이후 field_bench.py 로 다시 재야 한다")
            out.append(dict(key=(ph, 1), cluster=r["scene"], ok=bool(r["seat_ok"]["hybrid"]), hit=r["seat_hit"], want=r["seat_want"],
                            bad_auto=bool(r.get("seat_bad")), sec=_ms(r["hybrid"].get("ms")) / 1000))
        return out
    text = "".join(Path(p).read_text(encoding="utf-8", errors="replace") for p in paths)
    if '"scene":"F' in text.replace(" ", ""):
        sys.path.insert(0, str(ROOT / "experiments" / "rectify"))
        import summarize_field as sf

        return [x for p in paths for x in sf.records(p)]
    sys.path.insert(0, str(HERE))
    import flow_visit as fv

    return [dict(x, key=x["key"][:2]) for x in fv.records(paths)]


def totals(recs: list[dict]) -> dict:
    ts = sorted(x["sec"] for x in recs)
    return dict(n=len(recs), ok=sum(x["ok"] for x in recs), hit=sum(x["hit"] for x in recs), want=sum(x["want"] for x in recs),
                bad_auto=sum(x["bad_auto"] for x in recs), clusters=len({x["cluster"] for x in recs}),
                time=(statistics.median(ts), ts[min(len(ts) - 1, int(.9 * len(ts)))], ts[-1]) if ts else None)


def _metrics(pairs: list[tuple[dict, dict]]) -> dict:
    n = len(pairs)
    wa, wb = sum(a["want"] for a, _ in pairs), sum(b["want"] for _, b in pairs)
    return dict(scene=(sum(b["ok"] for _, b in pairs) - sum(a["ok"] for a, _ in pairs)) / n,
                tile=(sum(b["hit"] for _, b in pairs) / wb if wb else 0) - (sum(a["hit"] for a, _ in pairs) / wa if wa else 0),
                bad_auto=(sum(b["bad_auto"] for _, b in pairs) - sum(a["bad_auto"] for a, _ in pairs)) / n)


def bootstrap_diff(a: list[dict], b: list[dict], n: int = 1000, seed: int = 0, level: float = 0.95) -> dict:
    """B − A 의 점 추정과 묶음 부트스트랩 구간. 반환 {지표: dict(est, lo, hi, same)}, 'pairs'·'clusters' 수.
    same = 구간이 0 을 포함(= "같음" 으로 적는다)."""
    bi = {x["key"]: x for x in b}
    groups: dict = {}
    for x in a:
        if x["key"] in bi:
            groups.setdefault(x["cluster"], []).append((x, bi[x["key"]]))
    if not groups:
        raise SystemExit("두 측정에 같은 (사진, 회차) 가 없다")
    names = sorted(groups)
    allp = [p for c in names for p in groups[c]]
    est = _metrics(allp)
    rng = random.Random(seed)
    draws: dict = {k: [] for k in est}
    for _ in range(n):
        pick = [p for c in rng.choices(names, k=len(names)) for p in groups[c]]
        for k, v in _metrics(pick).items():
            draws[k].append(v)
    lo_q, hi_q = (1 - level) / 2, 1 - (1 - level) / 2
    out: dict = dict(pairs=len(allp), clusters=len(names))
    for k, v in est.items():
        d = sorted(draws[k])
        lo, hi = d[int(lo_q * (n - 1))], d[int(round(hi_q * (n - 1)))]
        out[k] = dict(est=v, lo=lo, hi=hi, same=lo <= 0 <= hi)
    return out


def fmt_diff(r: dict, n_rows: int, want: int) -> str:
    """사람이 읽는 한 줄: 장면은 '회'(비율 × 행 수), 패는 %p, 경고 없는 틀린 자동은 '회'."""
    def one(k, scale, unit):
        x = r[k]
        word = "같음" if x["same"] else ("B 가 높음" if x["est"] > 0 else "B 가 낮음")
        return f"{x['est'] * scale:+.1f}{unit} [{x['lo'] * scale:+.1f}, {x['hi'] * scale:+.1f}] {word}"
    return (f"짝 {r['pairs']}행·묶음 {r['clusters']}개 | 장면 단위 {one('scene', n_rows, '회')} | 패 단위 {one('tile', 100, '%p')}"
            f"(≈ {r['tile']['est'] * want:+.0f}장/{want}) | 경고 없는 틀린 자동 {one('bad_auto', n_rows, '회')}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["diff", "show"])
    ap.add_argument("a")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    o = ap.parse_args()
    A = load(o.a)
    ta = totals(A)
    print("A", {k: v for k, v in ta.items() if k != "time"}, "시간 %.2f / %.2f / %.2f" % ta["time"] if ta["time"] else "")
    if o.cmd == "show":
        return
    B = load(o.b)
    tb = totals(B)
    print("B", {k: v for k, v in tb.items() if k != "time"}, "시간 %.2f / %.2f / %.2f" % tb["time"] if tb["time"] else "")
    r = bootstrap_diff(A, B, o.n, o.seed)
    print("B − A", fmt_diff(r, r["pairs"], ta["want"] if ta["n"] == r["pairs"] else round(ta["want"] * r["pairs"] / ta["n"])))
    print(json.dumps({k: v for k, v in r.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
