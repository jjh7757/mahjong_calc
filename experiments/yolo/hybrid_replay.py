"""YOLO26 먼저, 검사 실패면 Gemini — 저장된 값으로 다시 채점(2026-11-01). API·모델 호출 없음.

YOLO26: dets_rot90.json 에 새 묶기(visit_yolo26.assemble) + 검사(hybrid.check, 장수·텐파이/화료형).
Gemini: seat_grow.json 폭 40(/v2/seat 3번 + 만장일치). 자동 = 만장일치 + 같은 검사, 아니면 확인.
정답: seat_grow.scenes()(B·C·D, visit_20261031/truth.json, label.json). 화료자 자리는 기록값을 준다.
시간: YOLO 는 rows.json rot90 의 노트북 값(매장만), 차례로 부른다고 보고 YOLO + Gemini 를 더한다.
  python -I experiments/yolo/hybrid_replay.py
결과 experiments/yolo/results/visit1031/hybrid_replay.json
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
import hybrid as hy  # noqa: E402
import seat_grow as sg  # noqa: E402
import visit_yolo26 as vy  # noqa: E402

OUT = HERE / "results" / "visit1031"
SETS = [("B·C·D", lambda n: not n.startswith("2026")), ("오전", lambda n: n.startswith("2026") and n < "20261031_14"), ("오후", lambda n: n.startswith("2026") and n >= "20261031_14")]


def same(hand: list[str], melds: list[str], s: dict) -> bool:
    key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    return sorted(hand) == sorted(s["hand"]) and key(melds) == key(s["melds"])


def one_short(hand: list[str], melds: list[str], s: dict) -> bool:
    """정답보다 손패 한 장만 모자라고 다른 차이는 없다(떼어 둔 패를 놓친 경우)."""
    return any(same(hand, melds, dict(s, hand=s["hand"][:i] + s["hand"][i + 1:])) for i in range(len(s["hand"])))


def replay() -> list[dict]:
    truth = {s["name"]: s for s in sg.scenes()}
    dets = json.loads((OUT / "dets_rot90.json").read_text(encoding="utf-8"))
    yolo_s = {r["name"]: r["s"] for r in json.loads((OUT / "rows.json").read_text(encoding="utf-8")) if r["mode"] == "rot90"}
    rows = []
    for g in json.loads(sg.OUT.read_text(encoding="utf-8")):
        gem = g["by_grow"].get("40")
        if gem is None:
            continue
        if g["name"] in sg.EXCLUDED:
            continue  # 가림·사용자 문제 사진은 채점에서 뺌
        n, s = g["name"], truth[g["name"]]
        known = s["hand"] is not None
        v = dets[n]
        hand, melds, _ = vy.assemble(v["dets"])
        y_melds = [" ".join(m) for m in melds]
        y_pass = bool(hand) and hy.check(hand, melds)[0]
        g_hand = (gem.get("hand") or "").split() + ([gem["sep"]] if gem.get("sep") else [])
        g_melds = gem.get("melds") or []
        g_pass = bool(g_hand) and bool(gem.get("unanimous")) and hy.check(g_hand, [m.split() for m in g_melds])[0]
        y_ok = same(hand, y_melds, s) if known else None
        g_ok = same(g_hand, g_melds, s) if known else None
        reg = [d["c"] for d in v["dets"] if d["reg"] == 0 and d["t"] != "back"]
        rows.append({"name": n, "run": g["run"], "known": known, "y_pass": y_pass, "y_ok": y_ok, "g_pass": g_pass, "g_ok": g_ok,
                     "y_short": known and one_short(hand, y_melds, s), "g_short": known and one_short(g_hand, g_melds, s),
                     "y_s": yolo_s.get(n), "g_s": gem.get("s"), "note": v["note"], "y_min_c": min(reg, default=None),
                     "y_hand": " ".join(hand), "y_melds": y_melds, "g_hand": " ".join(g_hand), "g_melds": g_melds,
                     "truth": " ".join(s["hand"]) if known else None, "truth_melds": s["melds"] if known else None})
    return rows


def tally(rows: list[dict], how: str) -> dict:
    t = dict(n=len(rows), known=sum(r["known"] for r in rows), auto=0, auto_ok=0, auto_bad=0, auto_short=0, auto_unknown=0, ask=0, answer_ok=0, gem=0, secs=[])
    for r in rows:
        if how == "yolo":
            auto, ok, short, used = r["y_pass"], r["y_ok"], r["y_short"], 0
        elif how == "gemini":
            auto, ok, short, used = r["g_pass"], r["g_ok"], r["g_short"], 1
        elif r["y_pass"]:
            auto, ok, short, used = True, r["y_ok"], r["y_short"], 0
        else:
            auto, ok, short, used = r["g_pass"], r["g_ok"], r["g_short"], 1
        t["gem"] += used
        t["answer_ok"] += bool(ok)
        if r["y_s"] is not None and r["g_s"] is not None:  # YOLO 시간이 있는 매장만, 세 방식 같은 사진으로
            t["secs"].append({"yolo": r["y_s"], "gemini": r["g_s"]}.get(how, r["y_s"] + (r["g_s"] if used else 0)))
        if auto:
            t["auto"] += 1
            t["auto_ok" if ok else "auto_bad" if ok is False else "auto_unknown"] += 1
            t["auto_short"] += bool(ok is False and short)
        else:
            t["ask"] += 1
    return t


def line(label: str, t: dict) -> str:
    s = sorted(t["secs"])
    when = f"{statistics.median(s):.1f} / {s[min(len(s) - 1, int(.9 * len(s)))]:.1f} / {s[-1]:.1f}" if s else "—"
    return (f"{label}: {t['n']}회(정답 있음 {t['known']}) 자동 {t['auto']}(정답 {t['auto_ok']}, 틀림 {t['auto_bad']} 중 한 장만 빠짐 {t['auto_short']}, 정답 모름 {t['auto_unknown']}) "
            f"확인 {t['ask']} | 답 맞음 {t['answer_ok']}/{t['known']} | Gemini 쓴 회 {t['gem']} | 시간 {when}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = replay()
    (OUT / "hybrid_replay.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for label, f in SETS:
        part = [r for r in rows if f(r["name"])]
        print(f"-- {label}")
        for how, name in (("gemini", "Gemini 단독"), ("yolo", "YOLO 단독"), ("hybrid", "YOLO 먼저")):
            print(line(name, tally(part, how)))
    print("-- 전체")
    for how, name in (("gemini", "Gemini 단독"), ("yolo", "YOLO 단독"), ("hybrid", "YOLO 먼저")):
        print(line(name, tally(rows, how)))
    print("-- 틀린 자동 반영(방식별)")
    for r in rows:
        if r["y_pass"] and r["y_ok"] is False:
            print("YOLO", r["name"][-6:], "한 장만 빠짐" if r["y_short"] else "그 밖", "|", r["y_hand"], r["y_melds"], "| 정답", r["truth"], r["truth_melds"])
        if r["g_pass"] and r["g_ok"] is False:
            print("Gemini", r["name"][-6:], "한 장만 빠짐" if r["g_short"] else "그 밖", "|", r["g_hand"], r["g_melds"], "| 정답", r["truth"], r["truth_melds"])
    print("-- YOLO 검사 실패 사진(Gemini 로 넘어감)")
    for r in rows:
        if not r["y_pass"]:
            print(r["name"][-6:], r["note"], "| YOLO", r["y_hand"], r["y_melds"], "| Gemini", "자동" if r["g_pass"] else "확인", "맞음" if r["g_ok"] else "틀림", "| 정답", r["truth"], r["truth_melds"])


if __name__ == "__main__":
    main()
