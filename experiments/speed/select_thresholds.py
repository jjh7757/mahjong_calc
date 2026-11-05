"""불확실성 신호 문턱 고르기(개선 계획 5단계, 2026-11-05, 노트북, API 없음). 서버 신호는 feat/cls-alt `app/signals.py`, 앱 적용은 lib/table/read_signals.dart.

신호(자리 판독 하나 = 한 행): S1 margin_min < t1 · S2 det_min < t2 · S3 cls2_diff ≥ t3 · S4 role_diff ≥ t4 · S5 jitter_diff ≥ t5 · S6 빨강 검사 어긋남 ≥ 1. 단순 OR.
문턱 고르기 입력(이것만): 회귀 고정 21변형(orig·felt0 포함) fold·prod 결과 JSON + 개발 32회 앱 흐름 로그. 테스트 15장은 쓰지 않는다.
  잡아야 할 것 = 회귀: unsafe(검사 통과했는데 틀림) 중 기존 장치(서버 block·규칙 V1·V2·V4·확신도 0.7 미만 경고)가 없는 것,
                 앱 흐름: 경고 없는 틀린 자동(flow_visit.records bad_auto).
  헛경보 = 회귀: 맞았고 검사 통과·막힘 없음(지금 자동 반영될 행)인데 신호가 켜짐 / 앱 흐름: 자동 반영이고 완전 맞음인데 신호가 켜짐.
  목표: 잡아야 할 것 전부 + 헛경보 최소(가중치 w: B·C·D 2). 같으면 켜는 신호 수가 적고 느슨한 쪽.
S6 문턱(패 종류별)은 개발 크롭(data/index.json + review.extra 의 5·적5)과 회귀 orig·felt0 의 맞은 행 5 패로 정한다 — 보통 5 최댓값과 적5 최솟값의 가운데.
온도(temp): fold 회귀 행에서 패별 보정 전 확률 상위 5개(LOCAL_SIGNALS_TOP=5)와 행 정답 다중집합으로 패마다 맞음/틀림을 정해 1순위 맞음의 NLL 최소 T.

  python -I -X utf8 experiments/speed/select_thresholds.py temp <robust_fold JSON>                       → results/temperature_tiles.json
  python -I -X utf8 experiments/speed/select_thresholds.py select --robust <fold JSON>,<prod JSON> --flow <로그들(쉼표)> [--temp T]
                                                                                                         → results/thresholds.json
  python -I -X utf8 experiments/speed/select_thresholds.py apply --robust ... --flow ... --field-bench <JSON> --field-flow <로그>
                                                                                                         (고른 문턱을 그대로 적용해 세기만)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RES = HERE / "results"
sys.path.insert(0, str(HERE))
import hand_rules as hr  # noqa: E402

FIVES = {"5m", "5p", "5s", "0m", "0p", "0s"}
UNCERTAIN = 0.7  # 앱 merge.dart uncertainBelow
SIG = ["s1", "s2", "s3", "s4", "s5", "s6"]
NAME = {"s1": "S1 확률 차", "s2": "S2 검출 확신도", "s3": "S3 분류기 2벌", "s4": "S4 역할 3씨드", "s5": "S5 입력 흔들기", "s6": "S6 5 패 빨강"}


# ---------------------------------------------------------------- 온도
def calib_top(top: list, T: float) -> list[float]:
    """상위 5개 확률 → 온도 T 로 보정한 상위 5개(나머지 질량은 남은 32종에 고르게 나눠 같이 보정)."""
    ps = [max(p, 1e-12) for _, p in top]
    rest = max(1e-12, 1 - sum(ps))
    k = 37 - len(ps)
    zs = [p ** (1 / T) for p in ps]
    tot = sum(zs) + k * (rest / k) ** (1 / T)
    return [z / tot for z in zs]


def tile_rows(rows: dict) -> list[tuple[list, bool]]:
    """회귀 한 변형의 행들 → [(상위 5개, 1순위 맞음)]. 행의 패 장수가 정답과 같을 때만, 정답보다 넘친 종류의 패 중 확률 낮은 것부터 틀림."""
    out = []
    for r in rows.values():
        s = r.get("signals") or {}
        tiles = [d for d in (s.get("tiles") or []) + [s.get("separate")] + [x for m in s.get("melds") or [] for x in m] if d and d.get("top")]
        want = Counter(r["want_hand"] + [t for m in r["want_melds"] for t in m.split()])
        if not tiles or len(tiles) != sum(want.values()) or s.get("filled"):
            continue
        have = Counter(d["top"][0][0] for d in tiles)
        bad = Counter({c: max(0, n - want[c]) for c, n in have.items()})
        for d in sorted(tiles, key=lambda d: d["top"][0][1]):
            c = d["top"][0][0]
            wrong = bad[c] > 0
            bad[c] -= wrong
            out.append((d["top"], not wrong))
    return out


def temp(a) -> None:
    res = json.loads(Path(a.file).read_text(encoding="utf-8"))
    data = [x for v, rows in res.items() if not v.startswith("_") for x in tile_rows(rows)]
    n_bad = sum(not ok for _, ok in data)

    def nll(T: float) -> float:
        s = 0.0
        for top, ok in data:
            q = min(max(calib_top(top, T)[0], 1e-9), 1 - 1e-9)
            s -= math.log(q if ok else 1 - q)
        return s / len(data)

    def ece(T: float) -> float:
        bins = [[0, 0.0, 0] for _ in range(10)]
        for top, ok in data:
            q = calib_top(top, T)[0]
            b = bins[min(9, int(q * 10))]
            b[0] += 1
            b[1] += q
            b[2] += ok
        return sum(abs(b[2] - b[1]) for b in bins if b[0]) / len(data)

    grid = [round(0.2 + 0.02 * i, 2) for i in range(141)]  # 0.2~3.0
    losses = {T: nll(T) for T in grid}
    best = min(losses, key=losses.get)
    rel = {}
    for tag, T in (("T1", 1.0), ("T", best)):
        c = Counter()
        for top, ok in data:
            q = calib_top(top, T)[0]
            lo = min(9, int(q * 10)) / 10
            c[(lo, "n")] += 1
            c[(lo, "ok")] += ok
        rel[tag] = {f"{lo:.1f}": [c[(lo, 'n')], c[(lo, 'ok')]] for lo in [i / 10 for i in range(10)] if c[(lo, "n")]}
    # 앱 문턱 0.7(보정 전)이 보정 뒤 어디에 해당하나: 보정 전 1순위 확률이 0.7 근처인 패들의 보정 뒤 값
    near = sorted(calib_top(top, best)[0] for top, _ in data if 0.65 <= top[0][1] <= 0.75)
    out = dict(T=best, n=len(data), wrong=n_bad, nll_T1=round(losses.get(1.0, nll(1.0)), 4), nll_T=round(losses[best], 4), ece_T1=round(ece(1.0), 4),
               ece_T=round(ece(best), 4), reliab=rel, raw07_calibrated=[round(near[len(near) // 2], 3)] if near else [],
               source=Path(a.file).name, note="fold 회귀 21변형 패(장수가 정답과 같은 행만), 1순위 맞음 이진 NLL. 크롭 홀드아웃(temperature.json)은 오답 0 이라 T 가 하한에 붙어 못 씀")
    (RES / "temperature_tiles.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- 행 모으기
def red_flags(sig: dict, red_t: dict) -> int:
    """S6: 5 패로 읽었는데 빨강 비율 ≥ 문턱(적5 같음) 또는 적5 로 읽었는데 < 문턱. 문턱은 색(m·p·s)마다."""
    n = 0
    for x in sig.get("red") or []:
        r, t = x.get("ratio"), x["tile"]
        if r is None or t not in FIVES:
            continue
        th = red_t.get(t[1])
        if th is None:
            continue
        n += (t[0] == "5" and r >= th) or (t[0] == "0" and r < th)
    return n


def margin_min(sig: dict, T: float | None) -> float | None:
    """S1. T 를 주면 패별 상위 5개로 다시 보정(회귀 JSON 을 온도 1 로 돌렸을 때)."""
    if T is None:
        return sig.get("margin_min")
    ds = [d for d in (sig.get("tiles") or []) + [sig.get("separate")] + [x for m in sig.get("melds") or [] for x in m] if d and d.get("top")]
    if not ds:
        return sig.get("margin_min")
    vals = []
    for d in ds:
        q = calib_top(d["top"], T)
        vals.append(q[0] - (q[1] if len(q) > 1 else 0))
    return round(min(vals), 4)


def feats(sig: dict | None, red_t: dict, T: float | None) -> dict | None:
    if not sig:
        return None
    return {"s1": margin_min(sig, T), "s2": sig.get("det_min"), "s3": sig.get("cls2_diff"), "s4": sig.get("role_diff"),
            "s5": sig.get("jitter_diff"), "s6": red_flags(sig, red_t)}


def robust_rows(path: str, red_t: dict, T: float | None) -> list[dict]:
    res = json.loads(Path(path).read_text(encoding="utf-8"))
    models = res["_meta"]["models"]
    out = []
    for v, rows in res.items():
        if v.startswith("_"):
            continue
        for name, r in rows.items():
            rule = hr.check(hr.server_input(r["hand"], r["melds"], r.get("alt")))
            vblock = rule["kind"] == "block"
            uncertain = any(c is not None and c < UNCERTAIN for c in r.get("conf") or []) or any(c is not None and c < UNCERTAIN for c in r.get("meld_conf") or [])
            blocked = r["block"] or vblock
            # 화료패 누락: 읽은 패가 정답의 부분집합이고 한 장 모자람(떼어 둔 화료패를 못 찾아 13장 텐파이로 검사 통과). 읽은 패에 붙는
            # 신호(S1~S6)로는 원리상 못 잡는다 — 따로 센다(앱은 강 끝·대기패로 화료패를 정하고 경고를 단다, 3단계 검토 ⑥).
            have = Counter(r["hand"] + [t for m in r["melds"] for t in m.split()])
            want = Counter(r["want_hand"] + [t for m in r["want_melds"] for t in m.split()])
            missing = r["unsafe"] and sum(have.values()) + 1 == sum(want.values()) and not (have - want)
            quiet = r["unsafe"] and not blocked and not uncertain
            out.append(dict(src=f"robust_{models}", key=f"{v}/{name}", w=r["w"], f=feats(r.get("signals"), red_t, T),
                            must=quiet and not missing, must_missing=quiet and missing, cost=r["ok"] and r["check"] and not blocked,
                            warned_before=r["unsafe"] and not blocked and uncertain, wrong=r["unsafe"] and not blocked))
    return out


def flow_rows(paths: list[str], red_t: dict, T: float | None) -> list[dict]:
    import flow_visit as fv

    recs = {r["key"]: r for r in fv.records(paths)}
    out = []
    for r in fv.read_rows(paths):
        k = (r["photo"], r["run"], r["server"])
        if k not in recs or "error" in r:
            continue
        rec = recs[k]
        auto = r.get("auto_block") is None
        sig = (r.get("hand_read") or {}).get("signals")
        # warned_before(강한 목표용) = 자동인데 손패·울기가 틀렸고 이미 경고가 있음. 표시패·점수만 틀린 것은 손패 신호와 무관해 넣지 않는다
        out.append(dict(src="flow_dev", key=f"{r['photo']}#{r['run']}", w=1, f=feats(sig, red_t, None), must=rec["bad_auto"], cost=auto and rec["complete"],
                        warned_before=auto and not rec["ok"] and not rec["bad_auto"], wrong=auto and not rec["complete"], auto=auto))
    return out


# ---------------------------------------------------------------- 문턱
def fires(f: dict | None, th: dict) -> list[str]:
    if not f:
        return []
    out = []
    if th.get("s1") is not None and f["s1"] is not None and f["s1"] < th["s1"]:
        out.append("s1")
    if th.get("s2") is not None and f["s2"] is not None and f["s2"] < th["s2"]:
        out.append("s2")
    for s in ("s3", "s4", "s5"):
        if th.get(s) is not None and f[s] is not None and f[s] >= th[s]:
            out.append(s)
    if th.get("s6") and f["s6"] >= 1:
        out.append("s6")
    return out


def red_thresholds(robust_paths: list[str]) -> dict:
    """S6 문턱: 개발 크롭(data/index.json + review.extra)과 회귀 orig·felt0 의 맞은 행 5 패(분류 = 정답)의 빨강 비율."""
    sys.path.insert(0, str(Path("C:/Users/jjh7757/dev/mahjong-recognizer-s5")))
    import os

    repo = os.environ.get("RECOGNIZER_REPO")
    if repo:
        sys.path.insert(0, repo)
    from app import signals as sg  # 서버와 같은 함수
    from PIL import Image

    sys.argv, keep = [sys.argv[0], "--r2"], sys.argv
    sys.path.insert(0, str(ROOT / "experiments" / "tile_classifier"))
    import det_eval as de
    from det_eval import rw

    sys.argv = keep
    vals: dict = {c: {"5": [], "0": []} for c in "mps"}
    base = json.loads((de.DATA / "index.json").read_text(encoding="utf-8"))
    for x in base:
        if x["tile"] in FIVES:
            r = sg.red_ratio(Image.open(de.DATA / "crops" / x["file"]).convert("RGB"))
            if r is not None:
                vals[x["tile"][1]][x["tile"][0]].append(("crop", r))
    for x in rw.extra():
        if x["tile"] in FIVES:
            r = sg.red_ratio(Image.open(x["path"]).convert("RGB"))
            if r is not None:
                vals[x["tile"][1]][x["tile"][0]].append(("crop", r))
    for p in robust_paths:
        res = json.loads(Path(p).read_text(encoding="utf-8"))
        for v in ("orig", "felt0"):
            for r in (res.get(v) or {}).values():
                if not r["ok"]:
                    continue
                for x in (r.get("signals") or {}).get("red") or []:
                    if x.get("ratio") is not None:
                        vals[x["tile"][1]][x["tile"][0]].append(("server", x["ratio"]))
    out, info = {}, {}
    for c, d in vals.items():
        lo = max((r for _, r in d["5"]), default=None)
        hi = min((r for _, r in d["0"]), default=None)
        info[c] = {"보통5 최대": lo, "적5 최소": hi, "보통5 수": len(d["5"]), "적5 수": len(d["0"]),
                   "서버 크롭 보통5·적5": [sum(s == "server" for s, _ in d["5"]), sum(s == "server" for s, _ in d["0"])]}
        if lo is not None and hi is not None and lo < hi:
            out[c] = round((lo + hi) / 2, 3)
    return {"thresholds": out, "info": info}


def search(rows: list[dict], target: str = "quiet") -> dict:
    """target quiet = 계획대로(경고 없는 틀린 것만 잡아야 함), all = 경고 있는 틀린 것(손패 틀림)까지 막아야 함(참고용)."""
    rows = [r for r in rows if r["f"] is not None]
    must = [r for r in rows if r["must"] or (target == "all" and r.get("warned_before"))]
    cost = [r for r in rows if r["cost"]]
    cand = {"s1": sorted({r["f"]["s1"] for r in must if r["f"]["s1"] is not None}), "s2": sorted({r["f"]["s2"] for r in must if r["f"]["s2"] is not None})}
    cnt = {s: sorted({r["f"][s] for r in must if r["f"][s] is not None and r["f"][s] >= 1}) for s in ("s3", "s4", "s5")}
    best = None
    import itertools

    for t3 in [None, *cnt["s3"]]:
        for t4 in [None, *cnt["s4"]]:
            for t5 in [None, *cnt["s5"]]:
                for s6 in (False, True):
                    base = {"s3": t3, "s4": t4, "s5": t5, "s6": s6}
                    left = [r for r in must if not fires(r["f"], base)]
                    # S1 문턱 후보: 끄기 또는 남은 잡아야 할 행의 값 바로 위. 그 뒤 남은 것을 S2 로(가장 느슨한 하나)
                    for t1 in [None, *[v + 1e-4 for v in cand["s1"]]]:
                        left2 = [r for r in left if not (t1 is not None and r["f"]["s1"] is not None and r["f"]["s1"] < t1)]
                        if not left2:
                            t2 = None
                        elif all(r["f"]["s2"] is not None for r in left2):
                            t2 = max(r["f"]["s2"] for r in left2) + 1e-4
                        else:
                            continue
                        th = {**base, "s1": t1, "s2": t2}
                        fa = sum(r["w"] for r in cost if fires(r["f"], th))
                        n_on = sum(v not in (None, False) for v in th.values())
                        key = (fa, n_on, t1 or 0, t2 or 0, -(t3 or 99), -(t4 or 99), -(t5 or 99))
                        if best is None or key < best[0]:
                            best = (key, th)
    th = best[1]
    for s in ("s1", "s2"):
        if th[s] is not None:
            th[s] = round(th[s], 4)
    return th


def tally(rows: list[dict], th: dict) -> dict:
    t = Counter()
    for r in rows:
        on = fires(r["f"], th)
        w = r["w"]
        t["n"] += w
        t["must"] += w * r["must"]
        t["must_caught"] += w * (r["must"] and bool(on))
        t["missing"] += w * r.get("must_missing", False)
        t["missing_caught"] += w * (r.get("must_missing", False) and bool(on))
        t["cost_rows"] += w * r["cost"]
        t["false_alarm"] += w * (r["cost"] and bool(on))
        t["wrong"] += w * r["wrong"]
        t["wrong_caught"] += w * (r["wrong"] and bool(on))
        t["no_signals"] += w * (r["f"] is None)
        for s in on:
            t[f"{s} 켜짐"] += w
            t[f"{s} 잡음"] += w * r["must"]
            t[f"{s} 헛경보"] += w * r["cost"]
    return dict(t)


def load(a, T: float | None, red_t: dict) -> dict:
    groups = {}
    for p in [x for x in (a.robust or "").split(",") if x]:
        rr = robust_rows(p, red_t, T)
        groups[rr[0]["src"]] = rr
    if a.flow:
        groups["flow_dev"] = flow_rows([x for x in a.flow.split(",") if x], red_t, None)
    return groups


def select(a) -> None:
    T = a.temp
    red = red_thresholds([x for x in a.robust.split(",") if x])
    red_t = red["thresholds"]
    groups = load(a, T, red_t)
    allrows = [r for g in groups.values() for r in g]
    th = search(allrows, a.target)
    if a.target == "all":
        for r in allrows:
            r["must"] = r["must"] or r.get("warned_before", False)
    out = dict(thresholds=th, red=red, temp_recalc=T, target=a.target, inputs=dict(robust=a.robust, flow=a.flow),
               per_group={k: tally(v, th) for k, v in groups.items()}, total=tally(allrows, th),
               must_rows=[dict(src=r["src"], key=r["key"], f=r["f"], fires=fires(r["f"], th)) for r in allrows if r["must"]],
               false_rows=[dict(src=r["src"], key=r["key"], f=r["f"], fires=fires(r["f"], th)) for r in allrows if r["cost"] and fires(r["f"], th)])
    # 막음/경고 정하기(작업 지시 "틀린 자동을 만든 신호는 막음, 그 밖은 경고"): 위 search 가 켠 신호 = 잡아야 할 행을 잡은 것 = 막음.
    # S6 은 문턱을 search 가 아니라 개발 크롭으로 정했으므로 따로: 개발 입력 전체에서 헛경보 0 이면 경고로 켠다(잡은 틀린 자동이 없으니 막음은 아님).
    s6 = tally(allrows, {"s1": None, "s2": None, "s3": None, "s4": None, "s5": None, "s6": True})
    out["decision"] = {"block": {k: v for k, v in th.items() if v not in (None, False)},
                       "caution": {"s6": red_t} if not th.get("s6") and s6.get("false_alarm", 0) == 0 else {},
                       "s6_alone": {k: s6.get(k, 0) for k in ("s6 켜짐", "false_alarm", "must_caught", "wrong_caught")}}
    print("결정", out["decision"])
    # 신호 하나만 켤 때(같은 문턱) 잡는 수·헛경보 — 어느 신호가 무엇을 하는지
    out["single"] = {s: tally(allrows, {k: (v if k == s else (False if k == "s6" else None)) for k, v in th.items()}) for s in SIG if th.get(s) not in (None, False)}
    (RES / f"thresholds{'' if a.target == 'quiet' else '_' + a.target}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("문턱", th, "\nS6", red)
    for k, v in out["per_group"].items():
        print(k, {x: v.get(x, 0) for x in ("n", "must", "must_caught", "missing", "missing_caught", "cost_rows", "false_alarm", "wrong", "wrong_caught", "no_signals")})
    print("합계", {x: out["total"].get(x, 0) for x in ("must", "must_caught", "cost_rows", "false_alarm")})
    for s, v in out["single"].items():
        print(f"  {NAME[s]} 혼자: 잡음 {v.get('must_caught', 0)}/{v.get('must', 0)} · 헛경보 {v.get('false_alarm', 0)}")
    print("잡아야 할 행", len(out["must_rows"]))
    for r in out["must_rows"]:
        print("  ", r)


def apply(a) -> None:
    sel = json.loads((RES / f"thresholds{'' if a.target == 'quiet' else '_' + a.target}.json").read_text(encoding="utf-8"))
    th, red_t, T = sel["thresholds"], sel["red"]["thresholds"], sel.get("temp_recalc")
    if sel.get("decision", {}).get("caution", {}).get("s6"):
        th = {**th, "s6": True}  # 경고(막음 아님) — 아래 수는 "막거나 경고"
    groups = load(a, T, red_t)
    for k, v in groups.items():
        t = tally(v, th)
        print(k, {x: t.get(x, 0) for x in ("n", "must", "must_caught", "missing", "missing_caught", "cost_rows", "false_alarm", "wrong", "wrong_caught", "no_signals")})
    if a.field_bench:
        res = json.loads(Path(a.field_bench).read_text(encoding="utf-8"))
        t = Counter()
        for ph, r in res["rows"].items():
            h = r["hybrid"]
            f = feats(h.get("signals"), red_t, T)
            ok = r["seat_ok"]["hybrid"]
            unsafe = hr.passes_server_check(h["hand"], [m.split() for m in h["melds"]]) and not ok
            on = fires(f, th)
            t["n"] += 1
            t["unsafe"] += unsafe
            t["unsafe_caught"] += unsafe and bool(on)
            t["unsafe_blocked_before"] += unsafe and h.get("block", False)
            t["false_alarm"] += ok and bool(on)
            t["ok"] += ok
            print(f"  {r['scene']} {ph} {'O' if ok else 'X'}{' UNSAFE' if unsafe else ''} 신호 {on} {f}")
        print("테스트 15장 서버 단독", dict(t))
    if a.field_flow:
        sys.path.insert(0, str(ROOT / "experiments" / "rectify"))
        import summarize_field as sf

        recs = {r["key"]: r for r in sf.records(a.field_flow)}
        t = Counter()
        for r in sf.read_rows(a.field_flow):
            k = (r["photo"], r.get("run", 1))
            if k not in recs or "error" in r:
                continue
            rec = recs[k]
            f = feats((r.get("hand_read") or {}).get("signals"), red_t, None)
            on = fires(f, th)
            auto = r.get("auto_block") is None
            t["n"] += 1
            t["auto"] += auto
            t["bad_auto"] += rec["bad_auto"]
            t["bad_auto_caught"] += rec["bad_auto"] and bool(on)
            t["false_alarm"] += auto and rec["complete"] and bool(on)
            t["auto_after"] += auto and not on
            print(f"  {r['scene']} {r['photo']} {'O' if rec['ok'] else 'X'} {'자동' if auto else '-'}{' 경고없는틀린자동' if rec['bad_auto'] else ''} 신호 {on} {f}")
        print("테스트 15장 앱 흐름", dict(t))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("temp")
    t.add_argument("file")
    for name in ("select", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--robust", default="")
        p.add_argument("--flow", default="")
        p.add_argument("--temp", type=float, default=None, help="회귀 JSON 을 온도 1 로 돌렸으면 이 T 로 S1 을 다시 보정")
        p.add_argument("--target", default="quiet", choices=["quiet", "all"], help="quiet = 계획(경고 없는 틀린 것), all = 경고 있는 손패 틀림까지(참고)")
        if name == "apply":
            p.add_argument("--field-bench", default="")
            p.add_argument("--field-flow", default="")
    a = ap.parse_args()
    {"temp": temp, "select": select, "apply": apply}[a.cmd](a)


if __name__ == "__main__":
    main()
