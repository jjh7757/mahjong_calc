"""마작 규칙 검증기 — Python 판(개선 계획 4단계, 2026-11-05). 명세·예제는 test/fixtures/hand_rules.json 하나이고
lib/table/hand_rules.dart 가 같은 답을 내야 한다. 사진을 보지 않는 규칙서 수준의 사실만 쓴다(V1 같은 패 5장, V2 적5 중복,
V3 화료형 아님 + 분류기 2순위 한 장으로 고쳐짐 = 후보, V4 울기 구성, V5 장수는 기존 흐름 그대로).

  python -I -X utf8 experiments/speed/hand_rules.py test                       fixture 예제 전부 통과 확인
  python -I -X utf8 experiments/speed/hand_rules.py score <파일>... [--detail]  오프라인 재채점

score 입력(파일마다 종류를 알아서 고른다):
  - 회귀 세트 결과 JSON(`robust_suite.py run`, `_meta` 있음): 변형별 + 합계. 서버 단독이라 표시패·강 없음 → V1 은 손패+울기(+떼어 둔 패)만.
  - 테스트 15장 서버 단독(`server_bench/field_bench.py` 결과 `data/role/bench/field_*.json`): 같은 입력 조건, 정답 = 자리 13장.
  - 앱 흐름 로그(`integration_test/read_grid_timing_test.dart` 의 TIMING 줄, .txt): 입력 = 판독 원본 손패·울기 + 병합이 고른 화료패·표시패 +
    강(로컬 경로는 강 끝 패, 론 패 한 장은 뺌). 정답·자동 반영은 개발이면 flow_visit.py, 테스트 15장(F 장면)이면 rectify/summarize_field.py 와 같은 기준.
    로그에 앱이 낸 `hand_rules` 가 있으면 이 파일의 답과 행마다 같은지도 센다(Dart·Python 일치 확인).
지표: 잡은 unsafe(서버 단독: 검사 통과했는데 틀림 / 앱 흐름: 자동 반영인데 틀림·경고 없는 틀린 자동) 중 막은 수, 헛경보(정답인데 막음),
V3 후보 수와 그중 바꾼 결과가 정답인 수. 규칙별(V1·V2·V4) 수도 따로.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURE = ROOT / "test" / "fixtures" / "hand_rules.json"

SUITS = "mpsz"


# ---------------------------------------------------------------- 패
def norm(code: str) -> str:
    return "5" + code[1] if code[0] == "0" else code


def idx(code: str) -> int:
    c = norm(code)
    return SUITS.index(c[1]) * 9 + int(c[0]) - 1


def code_of(i: int) -> str:
    return f"{i % 9 + 1}{SUITS[i // 9]}"


def counts(codes) -> list[int]:
    c = [0] * 34
    for t in codes:
        c[idx(t)] += 1
    return c


def _sets(c: list[int], k: int, i: int = 0) -> bool:
    """c 를 몸통(커쯔·슌쯔) k 개로 정확히 나눌 수 있나."""
    while i < 34 and c[i] == 0:
        i += 1
    if i == 34:
        return k == 0
    if k == 0:
        return False
    if c[i] >= 3:
        c[i] -= 3
        ok = _sets(c, k - 1, i)
        c[i] += 3
        if ok:
            return True
    if i < 27 and i % 9 <= 6 and c[i + 1] and c[i + 2]:
        c[i] -= 1
        c[i + 1] -= 1
        c[i + 2] -= 1
        ok = _sets(c, k - 1, i)
        c[i] += 1
        c[i + 1] += 1
        c[i + 2] += 1
        if ok:
            return True
    return False


TERMINALS = [0, 8, 9, 17, 18, 26, *range(27, 34)]


def complete(c: list[int], melds: int) -> bool:
    """멘젠 부분 c(합 14 − 3 × melds)가 화료형인가: 몸통 + 머리, 울기 0 이면 칠대자·국사무쌍도."""
    if sum(c) != 14 - 3 * melds:
        return False
    for p in range(34):
        if c[p] >= 2:
            c[p] -= 2
            ok = _sets(c, 4 - melds)
            c[p] += 2
            if ok:
                return True
    if melds == 0:
        if sum(1 for x in c if x == 2) == 7:
            return True
        if all(c[t] >= 1 for t in TERMINALS) and sum(c[t] for t in TERMINALS) == 14:
            return True
    return False


def tenpai(c: list[int], melds: int) -> bool:
    for t in range(34):
        if c[t] < 4:
            c[t] += 1
            ok = complete(c, melds)
            c[t] -= 1
            if ok:
                return True
    return False


def form_ok(closed: list[str], melds: int) -> bool:
    """n 14 → 화료형, n 13 → 텐파이(화료패를 모르는 입력)."""
    c = counts(closed)
    n = len(closed) + 3 * melds
    return complete(c, melds) if n == 14 else tenpai(c, melds) if n == 13 else False


# ---------------------------------------------------------------- 검사
def _excess(all_tiles: list[str]) -> list[str]:
    out = []
    c = counts(all_tiles)
    out += [f"V1 {code_of(i)}" for i in range(34) if c[i] > 4]
    red = Counter(t for t in all_tiles if t[0] == "0")
    out += [f"V2 0{s}" for s in "mps" if red[f"0{s}"] > 1]
    return out


def meld_ok(m: dict) -> bool:
    ts, ty = m.get("tiles") or [], m.get("type")
    ns = sorted(idx(t) for t in ts)
    same = len(set(ns)) == 1
    if len(ts) == 4:
        return same and ty in ("kan_open", "kan_closed", None)
    if len(ts) != 3:
        return False
    chi = ns[0] < 27 and ns[0] // 9 == ns[2] // 9 and ns[1] == ns[0] + 1 and ns[2] == ns[0] + 2
    return {"chi": chi, "pon": same, None: chi or same}.get(ty, False)


def check(inp: dict) -> dict:
    hand = list(inp.get("hand") or [])
    win = inp.get("win")
    melds = list(inp.get("melds") or [])
    closed = hand + ([win] if win else [])
    others = [t for m in melds for t in m.get("tiles") or []] + list(inp.get("indicators") or []) + list(inp.get("river") or [])
    n = len(closed) + 3 * len(melds)
    reasons = _excess(closed + others)
    reasons += [f"V4 {' '.join(m.get('tiles') or [])}" for m in melds if not meld_ok(m)]
    if n not in (13, 14):
        reasons.append(f"V5 {n}")
    if any(r[:2] in ("V1", "V2", "V4") for r in reasons):
        return {"kind": "block", "reasons": reasons, "candidate": None, "v3": None}
    if n not in (13, 14) or form_ok(closed, len(melds)):
        return {"kind": "none", "reasons": reasons, "candidate": None, "v3": None}
    alts = list(inp.get("alt") or [None] * len(hand))
    alts = (alts + [None] * len(hand))[: len(hand)] + [inp.get("win_alt") if win else None][: 1 if win else 0]
    found: dict = {}
    for i, (t, a) in enumerate(zip(closed, alts)):
        if not a or norm(a) == norm(t):
            continue
        new = closed[:i] + [a] + closed[i + 1:]
        if _excess(new + others) or not form_ok(new, len(melds)):
            continue
        found.setdefault(tuple(sorted(idx(x) for x in new)), (i, t, a))
    if len(found) == 1:
        i, t, a = next(iter(found.values()))
        return {"kind": "candidate", "reasons": reasons + [f"V3 {t}→{a}"], "candidate": {"index": i, "from": t, "to": a}, "v3": 1}
    return {"kind": "none", "reasons": reasons, "candidate": None, "v3": len(found)}


def passes_server_check(hand: list[str], melds: list[list[str]]) -> bool:
    """서버 단독 채점의 '검사 통과'(experiments/yolo/hybrid.check 와 같은 뜻): 손패+울기 같은 패 4장 이하, 13장 텐파이 / 14장 화료형."""
    if max(counts(hand + [t for m in melds for t in m]), default=0) > 4:
        return False
    return form_ok(hand, len(melds))


def apply(inp: dict, cand: dict) -> list[str]:
    closed = list(inp.get("hand") or []) + ([inp["win"]] if inp.get("win") else [])
    closed[cand["index"]] = cand["to"]
    return closed


# ---------------------------------------------------------------- fixture
def test() -> int:
    d = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = 0
    for c in d["cases"]:
        got = check(c["input"])
        if got != c["expect"]:
            bad += 1
            print("✗", c["name"], "\n   기대", c["expect"], "\n   얻음", got)
    print(f"{len(d['cases']) - bad}/{len(d['cases'])} 통과")
    return 1 if bad else 0


# ---------------------------------------------------------------- 재채점
def _rules(res: dict) -> set[str]:
    return {r[:2] for r in res["reasons"] if r[:2] in ("V1", "V2", "V4")}


class Tally:
    """막음·헛경보·후보를 규칙별로 센다(가중치 w: 회귀 세트 B·C·D 는 2)."""

    def __init__(self) -> None:
        self.c = Counter()

    def add(self, res: dict, w: int, ok: bool, bad: bool, bad_quiet: bool | None = None, auto: bool | None = None, v3_right: bool | None = None) -> None:
        c, rules = self.c, _rules(res)
        c["n"] += w
        c["ok"] += w * ok
        c["bad"] += w * bad
        blocked = res["kind"] == "block"
        c["block"] += w * blocked
        c["caught"] += w * (blocked and bad)
        c["false"] += w * (blocked and ok)
        for r in ("V1", "V2", "V4"):
            c[f"{r} 막음"] += w * (r in rules)
            c[f"{r} 잡음"] += w * (r in rules and bad)
            c[f"{r} 헛경보"] += w * (r in rules and ok)
        if bad_quiet is not None:
            c["bad_quiet"] += w * bad_quiet
            c["caught_quiet"] += w * (blocked and bad_quiet)
        if auto is not None:
            c["auto"] += w * auto
            c["auto_after"] += w * (auto and not blocked)
            c["auto_lost_ok"] += w * (auto and blocked and ok)
        if res["v3"] is not None:
            c["v3 시도"] += w
        if res["kind"] == "candidate":
            c["v3 후보"] += w
            c["v3 정답"] += w * bool(v3_right)
        c["V5"] += w * any(r.startswith("V5") for r in res["reasons"])

    def line(self, label: str, flow: bool = False) -> str:
        c = self.c
        s = (f"{label}: n {c['n']} · 맞음 {c['ok']} · {'틀린 자동' if flow else 'unsafe'} {c['bad']} → 막음 {c['caught']}"
             f" (V1 {c['V1 잡음']} · V2 {c['V2 잡음']} · V4 {c['V4 잡음']}) · 헛경보 {c['false']} (V1 {c['V1 헛경보']} · V2 {c['V2 헛경보']} · V4 {c['V4 헛경보']})"
             f" · 막음 전체 {c['block']} · V3 후보 {c['v3 후보']}/{c['v3 시도']} 시도, 정답 {c['v3 정답']} · V5 {c['V5']}")
        if flow:
            s += f" · 경고 없는 틀린 자동 {c['bad_quiet']} → 막음 {c['caught_quiet']} · 자동 반영 {c['auto']} → {c['auto_after']} (맞는 자동을 막음 {c['auto_lost_ok']})"
        return s


def _key(ms) -> list[str]:
    return sorted(" ".join(sorted(norm(t) for t in m.split())) for m in ms)


def server_input(hand: list[str], melds: list[str], alt=None) -> dict:
    return {"hand": hand, "melds": [{"type": None, "tiles": m.split()} for m in melds], "alt": alt}


def score_robust(path: Path, res: dict, detail: bool) -> None:
    meta = res.get("_meta", {})
    print(f"\n### {path.name} — 회귀 세트, 모델 {meta.get('models')} · 서버 {meta.get('recognizer')} · 입력 = 서버 단독(손패+울기, 표시패·강 없음)")
    tot = Tally()
    for v, rows in res.items():
        if v.startswith("_"):
            continue
        t = Tally()
        for name, r in rows.items():
            inp = server_input(r["hand"], r["melds"], r.get("alt"))
            out = check(inp)
            right = None
            if out["kind"] == "candidate" and "want_hand" in r:
                right = sorted(apply(inp, out["candidate"])) == sorted(r["want_hand"]) and _key(r["melds"]) == _key(r["want_melds"])
            mine = passes_server_check(r["hand"], [m.split() for m in r["melds"]])
            if mine != r["check"]:
                print("  ! 검사 통과 판정이 결과 JSON 과 다름", v, name, mine, r["check"])
            for x in (t, tot):
                x.add(out, r["w"], r["ok"], r["unsafe"], v3_right=right)
            if detail and (out["kind"] != "none" or r["unsafe"]):
                print(f"    {v} {name[-6:]} {'O' if r['ok'] else 'X'}{' UNSAFE' if r['unsafe'] else ''} {out['kind']} {out['reasons']} {' '.join(r['hand'])} {r['melds']}"
                      f"{' 후보 정답' if right else ' 후보 틀림' if right is False else ''}")
        print("  " + t.line(f"`{v}`"))
    print("  " + tot.line("**합계(변형 전부)**"))


def score_field_bench(path: Path, res: dict, detail: bool) -> None:
    print(f"\n### {path.name} — 테스트 15장 서버 단독, 입력 = 손패+울기(+떼어 둔 패), 정답 = 자리 13장")
    t = Tally()
    for ph, r in res["rows"].items():
        h = r["hybrid"]
        inp = server_input(h["hand"], h["melds"], h.get("alt"))
        out = check(inp)
        ok = r["seat_ok"]["hybrid"]
        unsafe = passes_server_check(h["hand"], [m.split() for m in h["melds"]]) and not ok
        right = None
        if out["kind"] == "candidate" and "want_hand" in r:
            right = sorted(apply(inp, out["candidate"])) == sorted(r["want_hand"]) and _key(h["melds"]) == _key(r["want_melds"])
        t.add(out, 1, ok, unsafe, bad_quiet=r.get("seat_bad"), v3_right=right)
        if detail:
            print(f"    {r['scene']} {ph} {'O' if ok else 'X'}{' UNSAFE' if unsafe else ''} {out['kind']} {out['reasons']} {' '.join(h['hand'])} {h['melds']}"
                  f"{' 후보 정답' if right else ' 후보 틀림' if right is False else ''}")
    print("  " + t.line("테스트 15장(서버 단독)"))


def flow_input(r: dict) -> dict:
    """앱 흐름 로그 한 행 → 검사 입력(lib/table/hand_rules.dart handRuleInputOf 와 같은 규칙)."""
    hr = r.get("hand_read") or {}
    m = r.get("merge") or {}
    hand = [t["tile"] for t in hr.get("tiles") or []]
    alt = [t.get("alt") for t in hr.get("tiles") or []]
    if hr.get("win_tile"):
        hand.append(hr["win_tile"]["tile"])
        alt.append(hr["win_tile"].get("alt"))
    melds = [{"type": x.get("type"), "tiles": list(x.get("tiles") or [])} for x in hr.get("melds") or []]
    win = None
    closed = m.get("closed") or []
    if m.get("win_tile") and len(closed) == len(hand) + 1:
        win = m["win_tile"]  # 병합이 손패 밖(강 끝·대기패·고른 패)에서 가져온 화료패
    inds = list(m.get("dora_indicators") or []) + list(m.get("ura_indicators") or [])
    river = [t for ts in ((r.get("center_read") or {}).get("rivers") or {}).values() for t in ts or []]
    if win and not m.get("is_tsumo"):
        for i, t in enumerate(river):  # 론 패는 방총자 강 끝 그 한 장 — 화료패로 셌으니 강에서 뺀다(어느 자리든 합계는 같다)
            if norm(t) == norm(win):
                del river[i]
                break
    return {"hand": hand, "win": win, "melds": melds, "indicators": inds, "river": river, "alt": alt}


def score_flow(path: Path, detail: bool) -> None:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        i = line.find("TIMING {")
        if i >= 0:
            rows.append(json.loads(line[i + 7:]))
    if not rows:
        print(f"\n### {path.name} — TIMING 줄 없음")
        return
    field = rows[0]["scene"].startswith("F")
    sys.path.insert(0, str(HERE))
    if field:
        sys.path.insert(0, str(ROOT / "experiments" / "rectify"))
        import summarize_field as sf

        recs = {r["key"]: r for r in sf.records(str(path))}
        key = lambda r: (r["photo"], r.get("run", 1))  # noqa: E731
        want = lambda r: sorted(sf.TRUTH[r["scene"]][2].split())  # noqa: E731
    else:
        import flow_visit as fv
        import seat_grow as sg

        recs = {r["key"]: r for r in fv.records([str(path)])}
        scenes = {(s["name"] if s["set"] == "bcd" else s["name"][-6:]): s for s in sg.eval_scenes()}
        key = lambda r: (r["photo"], r["run"], r["server"])  # noqa: E731
        want = lambda r: fv.truth_of(r["photo"], scenes)["closed"] if fv.truth_of(r["photo"], scenes)["win"] else None  # noqa: E731
    print(f"\n### {path.name} — 앱 흐름{' 테스트 15장' if field else ' 개발'}, 입력 = 판독 손패·울기 + 병합 화료패·표시패 + 강 끝(론 패 뺌)")
    t = Tally()
    agree = disagree = 0
    for r in rows:
        k = key(r)
        if k not in recs or "error" in r:
            continue
        rec = recs[k]
        inp = flow_input(r)
        out = check(inp)
        if "hand_rules" in r:
            if r["hand_rules"] == out:
                agree += 1
            else:
                disagree += 1
                print("  ! Dart 와 다름", k, r["hand_rules"], out)
        auto = r.get("auto_block") is None if "auto_block_base" not in r else r["auto_block_base"] is None
        bad = auto and not rec["complete"]
        right = None
        if out["kind"] == "candidate":
            w = want(r)
            right = w is not None and sorted(apply(inp, out["candidate"])) == w
        t.add(out, 1, rec["ok"], bad, bad_quiet=rec["bad_auto"] if auto else False, auto=auto, v3_right=right)
        if detail and (out["kind"] != "none" or bad):
            print(f"    {k} {'O' if rec['ok'] else 'X'} {'자동' if auto else '-'}{' 틀린 자동' if bad else ''} {out['kind']} {out['reasons']} | {' '.join(inp['hand'])} + {inp['win']} 울기 {[' '.join(m['tiles']) for m in inp['melds']]} 표시패 {inp['indicators']} 강 {inp['river']}"
                  f"{' 후보 정답' if right else ' 후보 틀림' if right is False else ''}")
    print("  " + t.line("앱 흐름", flow=True) + (f" · Dart 일치 {agree}/{agree + disagree}" if agree + disagree else ""))


def score(paths: list[str], detail: bool) -> None:
    for p in map(Path, paths):
        if p.suffix == ".txt":
            score_flow(p, detail)
            continue
        res = json.loads(p.read_text(encoding="utf-8"))
        if "_meta" in res:
            score_robust(p, res, detail)
        elif "rows" in res and "total" in res:
            score_field_bench(p, res, detail)
        else:
            print(p, "모르는 형식")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["test"]:
        sys.exit(test())
    if sys.argv[1:2] == ["score"]:
        args = [a for a in sys.argv[2:] if a != "--detail"]
        score(args, "--detail" in sys.argv)
    else:
        print(__doc__)
