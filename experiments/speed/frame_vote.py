"""프레임 투표(개선 계획 6단계): 같은 판을 찍은 두 프레임의 판독이 같을 때만 자동 반영. 정의·짝·지표는 `FRAME_VOTE.md`(측정 전에 적음).

규칙은 앱 `lib/table/frame_vote.dart` 와 같아야 한다(명세 `test/fixtures/frame_vote.json`).

  python -I -X utf8 experiments/speed/frame_vote.py test          명세 예제를 이 규칙으로 돌린다
  python -I -X utf8 experiments/speed/frame_vote.py score [--detail] 오프라인 시연 (a) B·C·D 같은 판 두 장 (b) 테스트 15장 같은 판 (c) 회귀 세트 프레임 흉내 변형
  python -I -X utf8 experiments/speed/frame_vote.py logs <촬영 기록 폴더>...  앱 촬영 기록(frame_vote.json)을 찍고 Python 규칙으로 다시 판정(노트북 끝까지 확인)

새 모델 실행 없음 — 5단계까지 저장한 결과(회귀 JSON·field_bench JSON·앱 흐름 로그)만 읽는다.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "experiments" / "rectify"))
RES = HERE / "results"
FIXTURE = ROOT / "test" / "fixtures" / "frame_vote.json"
FIELD_JSON = ROOT / "experiments" / "tile_classifier" / "data" / "role" / "bench" / "field_det_final_rect_sig1105.json"

# FRAME_VOTE.md 에 미리 고정한 프레임 흉내 변형(주 결과)과 참고 줄.
FRAME_LIKE = ["orig", "jpeg35", "blur1", "scale08", "ev_m1", "wb_fluo"]
REFERENCE = ["ev_p1"]
BCD_PAIRS = [("k25", "k28"), ("k15", "k26"), ("k12", "k16")]


# ---------------------------------------------------------------- 규칙(frame_vote.dart 와 같아야 한다)
def read_key(r: dict) -> tuple:
    """판독 → 비교 열쇠. 손패 다중집합, 떼어 둔 패, 울기 다중집합(울기 안 정렬 + 안깡 표시)."""
    tiles = tuple(sorted(r.get("tiles") or []))
    melds = tuple(sorted((tuple(sorted(m.get("tiles") or [])), bool(m.get("closed"))) for m in r.get("melds") or []))
    return tiles, r.get("separate"), melds


def vote(a: dict, b: dict | None) -> str:
    """'agree' | 'mismatch' | 'none'(두 번째 판독 없음)."""
    if b is None:
        return "none"
    return "agree" if read_key(a) == read_key(b) else "mismatch"


def test() -> None:
    spec = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bad = 0
    for c in spec["cases"]:
        got = vote(c["a"], c["b"])
        if got != c["want"]:
            bad += 1
            print("틀림", c["name"], "원함", c["want"], "얻음", got)
    print(f"명세 {len(spec['cases']) - bad}/{len(spec['cases'])} 통과")
    sys.exit(1 if bad else 0)


# ---------------------------------------------------------------- 자료 → 판독(read)·맞음(ok)·자동(auto)
def meld_of(s: str) -> dict:
    closed = s.strip().startswith("(")
    return {"tiles": re.sub(r"[\[\]()]", " ", s).split(), "closed": closed}


def robust_item(row: dict) -> dict:
    """회귀 세트 행(서버 hybrid, 떼어 둔 패는 손패에 합쳐 저장)."""
    return {"read": {"tiles": row["hand"], "separate": None, "melds": [meld_of(m) for m in row["melds"]]},
            "ok": bool(row["ok"]), "auto": bool(row["check"]) and not row["block"], "err": row.get("err")}


def field_server_items() -> dict:
    d = json.loads(FIELD_JSON.read_text(encoding="utf-8"))
    out = {}
    for ph, r in d["rows"].items():
        h = r["hybrid"]
        out[ph] = dict(scene=r["scene"], read={"tiles": h["hand"], "separate": None, "melds": [meld_of(m) for m in h["melds"]]},
                       ok=bool(r["seat_ok"]), auto=bool(h["auto"]))
    return out


def app_read(r: dict) -> dict:
    m = r.get("merge") or {}
    return {"tiles": m.get("closed") or [], "separate": m.get("win_tile"), "melds": [meld_of(x) for x in m.get("melds") or []]}


def app_dev_items(log: Path) -> dict:
    """앱 흐름 개발 로그 → (사진, 회차) → 항목. 맞음 = flow_visit 의 완전 맞음."""
    import flow_visit as fv

    recs = {rec["key"][:2]: rec for rec in fv.records([str(log)])}
    out = {}
    for r in fv.read_rows([str(log)]):
        k = (r["photo"], r["run"])
        if k not in recs:
            continue
        auto = r.get("auto_block") is None and "error" not in r
        out[k] = dict(read=app_read(r), ok=bool(recs[k]["complete"]), auto=auto, cautions=r.get("auto_cautions") or [])
    return out


def app_field_items(log: Path) -> dict:
    import summarize_field as sf

    out = {}
    for r in sf.read_rows(str(log)):
        j = sf.judge(r)
        out[r["photo"]] = dict(scene=r["scene"], read=app_read(r), ok=j["ok_hand"] and j["ok_loser"] and j["ok_pts"] is not False,
                               auto=j["auto"], cautions=r.get("auto_cautions") or [])
    return out


# ---------------------------------------------------------------- 짝 채점
def tally(pairs: list[tuple[dict, dict, str]]) -> Counter:
    """pairs = (A, B, 사진 묶음 이름). 짝 단위 + 순서 짝(A 먼저·B 먼저 둘 다) 막는 수."""
    c = Counter()
    blocked_units, bad_units = set(), set()
    for a, b, unit in pairs:
        v = vote(a["read"], b["read"])
        c["짝"] += 1
        if v == "mismatch":
            c["불일치"] += 1
            c["불일치·하나 이상 틀림"] += (not a["ok"]) or (not b["ok"])
            c["불일치·둘 다 틀림"] += (not a["ok"]) and (not b["ok"])
        else:
            c["일치"] += 1
            # 같은 답이면 손패 채점은 같지만 앱 "완전 맞음" 은 방총자·점수도 보아 둘이 다를 수 있다 → 하나라도 틀리면 셈.
            c["일치·둘 다 틀림"] += (not a["ok"]) or (not b["ok"])
            c["일치·둘 다 틀림·자동"] += (a["auto"] and not a["ok"]) or (b["auto"] and not b["ok"])
        for first, second in ((a, b), (b, a)):
            if first["auto"] and not first["ok"]:
                c["순서짝·자동 틀림"] += 1
                bad_units.add(unit)
                if v == "mismatch":
                    c["순서짝·막음"] += 1
                    blocked_units.add(unit)
                else:
                    c["순서짝·못 막음"] += 1
            if first["auto"] and first["ok"]:
                c["순서짝·자동 맞음"] += 1
                c["순서짝·헛막음"] += v == "mismatch"
    c["자동 틀림 사진"] = len(bad_units)
    c["막은 사진"] = len(blocked_units)
    return c


def pct(n: int, d: int) -> str:
    return f"{n}/{d}" + (f" ({100 * n / d:.0f}%)" if d else "")


def show(name: str, c: Counter) -> dict:
    line = {
        "짝": c["짝"],
        "불일치율": pct(c["불일치"], c["짝"]),
        "불일치→하나 이상 틀림": pct(c["불일치·하나 이상 틀림"], c["불일치"]),
        "일치→둘 다 틀림": pct(c["일치·둘 다 틀림"], c["일치"]),
        "일치→둘 다 틀림(자동)": c["일치·둘 다 틀림·자동"],
        "자동 틀림 막음(순서짝)": pct(c["순서짝·막음"], c["순서짝·자동 틀림"]),
        "헛막음(순서짝)": pct(c["순서짝·헛막음"], c["순서짝·자동 맞음"]),
        "막은 사진": f"{c['막은 사진']}/{c['자동 틀림 사진']}",
    }
    print(f"{name:<34}", " · ".join(f"{k} {v}" for k, v in line.items()))
    return {"name": name, **line, "raw": dict(c)}


def robust_pairs(path: Path, variants: list[str], mode: str, detail: bool) -> list:
    d = json.loads(path.read_text(encoding="utf-8"))
    photos = sorted(d["orig"])
    out = []
    combos = list(itertools.combinations(variants, 2)) if mode == "all" else [("orig", v) for v in variants if v != "orig"]
    for ph in photos:
        for v1, v2 in combos:
            r1, r2 = d.get(v1, {}).get(ph), d.get(v2, {}).get(ph)
            if r1 is None or r2 is None:
                continue
            a, b = robust_item(r1), robust_item(r2)
            out.append((a, b, ph))
            if detail and vote(a["read"], b["read"]) == "mismatch":
                print(f"   {path.stem} {ph} {v1}/{v2}  {'O' if a['ok'] else 'X'}{'자' if a['auto'] else ''} {' '.join(sorted(a['read']['tiles']))} |"
                      f" {'O' if b['ok'] else 'X'}{'자' if b['auto'] else ''} {' '.join(sorted(b['read']['tiles']))}")
    return out


def score(a) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    report = {"defs": "FRAME_VOTE.md", "rows": []}
    rows = report["rows"]

    print("(a) B·C·D 같은 판 두 장")
    for models in ("fold", "prod"):
        d = json.loads((RES / f"robust_{models}_1105sig.json").read_text(encoding="utf-8"))["orig"]
        pairs = [(robust_item(d[x]), robust_item(d[y]), x) for x, y in BCD_PAIRS]
        rows.append(show(f"서버 단독 {models} orig", tally(pairs)))
    for models, log in (("fold", "log_flow_base_sigfold0_1105_bcd.txt"), ("prod", "log_flow_base_sig1_1105_bcd.txt")):
        it = app_dev_items(RES / log)
        runs = sorted({k[1] for k in it})
        pairs = [(it[(x, n)], it[(y, n)], x) for x, y in BCD_PAIRS for n in runs if (x, n) in it and (y, n) in it]
        rows.append(show(f"앱 흐름 {models} ({log[14:-4]})", tally(pairs)))

    print("\n(b) 테스트 15장 편 사진 같은 판(대삼원 8장·F1400 4장) — 기록만")
    srv = field_server_items()
    app = app_field_items(RES / "log_flow_base_sig1_1105_field.txt")
    for name, it in (("서버 단독 prod field_bench", srv), ("앱 흐름 prod sig1", app)):
        by = defaultdict(list)
        for ph, x in sorted(it.items()):
            by[x["scene"]].append((ph, x))
        allp = []
        for scene in ("F대삼원", "F1400"):
            ps = [(x, y, scene) for (_, x), (_, y) in itertools.combinations(by[scene], 2)]
            allp += ps
            rows.append(show(f"{name} {scene}", tally(ps)))
        rows.append(show(f"{name} 합", tally(allp)))
        if a.detail:
            for scene in ("F대삼원", "F1400"):
                for ph, x in by[scene]:
                    print(f"   {scene} {ph} {'O' if x['ok'] else 'X'} {'자동' if x['auto'] else ''} {' '.join(sorted(x['read']['tiles']))} 화료 {x['read']['separate']}")

    print("\n(c) 회귀 세트 프레임 흉내 변형", FRAME_LIKE, "(주 = 모든 짝, 보조 = orig 대 나머지)")
    for models in ("fold", "prod"):
        p = RES / f"robust_{models}_1105sig.json"
        rows.append(show(f"서버 단독 {models} 주(모든 짝)", tally(robust_pairs(p, FRAME_LIKE, "all", a.detail))))
        rows.append(show(f"서버 단독 {models} 보조(orig 대)", tally(robust_pairs(p, FRAME_LIKE, "orig", False))))
        rows.append(show(f"서버 단독 {models} 참고 +ev_p1(모든 짝)", tally(robust_pairs(p, FRAME_LIKE + REFERENCE, "all", False))))
    out = RES / "frame_vote.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n→", out)


# ---------------------------------------------------------------- 앱 촬영 기록(노트북 끝까지 확인)
def logs(dirs: list[str]) -> None:
    """앱 촬영 기록 `<시각>/frame_vote.json`(토글 켬일 때만 생김)을 찍고, 같은 두 판독을 이 규칙으로 다시 판정해 앱과 같은지 본다."""
    sys.stdout.reconfigure(encoding="utf-8")
    for d in dirs:
        p = Path(d) / "frame_vote.json"
        if not p.exists():
            print(Path(d).name, "frame_vote.json 없음(토글 끔 또는 자동 반영 대상 아님)")
            continue
        fv = json.loads(p.read_text(encoding="utf-8"))
        a, b = fv.get("first"), fv.get("second")
        again = vote(a, b) if a else None
        print(Path(d).name, fv.get("result"), "| Python 재판정", again, "같음" if again == fv.get("result") else "!! 다름",
              "| 정지", fv.get("still"), "| 전체", fv.get("total_ms"), "ms, 두 번째 localroles", fv.get("second_ms"), "ms", fv.get("reason", ""))
        print("   첫 판독  ", " ".join(sorted(a["tiles"])), a.get("separate"), [" ".join(m["tiles"]) for m in a.get("melds", [])])
        if b:
            print("   두 번째  ", " ".join(sorted(b["tiles"])), b.get("separate"), [" ".join(m["tiles"]) for m in b.get("melds", [])])


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("test")
    s = sub.add_parser("score")
    s.add_argument("--detail", action="store_true")
    lg = sub.add_parser("logs")
    lg.add_argument("dirs", nargs="+")
    a = ap.parse_args()
    if a.cmd == "test":
        test()
    elif a.cmd == "score":
        score(a)
    else:
        logs(a.dirs)


if __name__ == "__main__":
    main()
