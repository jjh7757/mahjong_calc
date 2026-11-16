"""모델의 중간 주장을 화소 장수와 맞대는 점검(2026-11-16 밤, 계획서 3단계 "추가 7" — 방법·기준은 결과 전에 적음).
사용자 "모순을 보는 게 아니라 모델이 제대로 순서를 읽었는지 점검하고 싶은데".

  python -X utf8 gemclaims.py run [--model gemini-3.8-flash] [--reps 3]   # 9차례 × 회 → _work/gemclaims_1116/answers/
  python -X utf8 gemclaims.py check [--verbose]                          # 주장 ↔ 화소 대조 + 채점
재료는 gemframes 조건 B 프레임 묶음 그대로. 지시문은 gemframes 의 것에 주장 요구만 더함.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemframes as gf  # noqa: E402
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402

OUT = hc.WORK / "gemclaims_1116"
ARM = "B"
BIG, NEAR_INT, DT_MS = 3, 0.3, 100  # 깨끗한 큰 덩어리: 장수 3 이상 · 정수에서 0.3 안 / 주장 시각 ±0.1초

EXTRA = """
그리고 답의 근거가 된 순간 2~4개를 moments 에 적어라. D 를 넣기 직전, 손이 패를 가장 많이 들거나 옮긴 순간은 꼭 넣는다. 순간마다:
- time = 그 프레임의 시각(프레임 앞에 적힌 그대로, 예 "02:10.5")
- in_place = 그 프레임에서 손이 닿지 않은 채 탁자에 서 있는 패를, 서로 붙어 있는 무리별로 왼쪽부터 센 장수 목록. 무리 사이에 틈(펠트가 보임)이나 손이 있으면 다른 무리다. 예: 왼쪽에 5장, 틈, 4장이면 [5, 4]
- held = 그 프레임에서 손이 들고 있거나 쥐고 옮기는 패 장수(D 포함, 가려져 안 보여도 센다)
"""
PROMPT = gf.PROMPT.replace("JSON 으로만 답하라:", EXTRA.strip() + "\n\nJSON 으로만 답하라: moments = 위 순간들,")
SCHEMA = {"type": "OBJECT", "properties": {
    "moments": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "time": {"type": "STRING"}, "in_place": {"type": "ARRAY", "items": {"type": "INTEGER"}}, "held": {"type": "INTEGER"}},
        "required": ["time", "in_place", "held"]}},
    "steps": {"type": "STRING"}, "j": {"type": "INTEGER", "nullable": True}, "confidence": {"type": "STRING", "enum": ["high", "low"]}},
    "required": ["moments", "steps", "j", "confidence"]}


def parts_of(t: dict, types):
    ps = [PROMPT.format(scope=gf.SCOPE[ARM], n=t["n"])]
    for f in sorted((gf.OUT / ARM / t["id"]).glob("*.jpg")):
        ms = int(f.stem.split("_")[1])
        ps.append(f"프레임 {hc.hms(ms)[3:]}")
        part = types.Part.from_bytes(data=f.read_bytes(), mime_type="image/jpeg")
        part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
        ps.append(part)
    ps.append(f"위 프레임을 보고 답하라. 줄은 {t['n']}장이다.")
    return ps


def one(c, types, model, t):
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA)
    t0 = time.perf_counter()
    err = ""
    for attempt in range(3):
        try:
            r = c.models.generate_content(model=model, contents=parts_of(t, types), config=cfg)
            um = r.usage_metadata
            data = json.loads(r.text)
            return {"id": t["id"], "j": data.get("j"), "confidence": data.get("confidence"), "steps": data.get("steps"), "moments": data.get("moments") or [],
                    "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                    "think": getattr(um, "thoughts_token_count", 0) or 0, "model_version": getattr(r, "model_version", None), "attempt": attempt + 1}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(5 * (attempt + 1))
    return {"id": t["id"], "j": None, "moments": [], "error": err, "s": round(time.perf_counter() - t0, 1), "in": 0, "out": 0, "think": 0}


def cmd_run(a):
    from google.genai import types
    ts = gf.turns()
    for rep in range(1, a.reps + 1):
        f = OUT / "answers" / f"{a.model}_{ARM}_r{rep}.json"
        if f.exists() and not a.force:
            print("있음 — 건너뜀", f.name)
            continue
        with ThreadPoolExecutor(a.workers) as ex:
            rows = list(ex.map(lambda t: one(gf.client(), types, a.model, t), ts))
        hc.jsave(f, {"model": a.model, "arm": ARM, "rep": rep, "at": hc.hms(int(time.time() * 1000), date=True), "rows": rows})
        print(f.name, [(r["id"], r["j"], len(r["moments"]), r.get("error", "")[:40]) for r in rows],
              "입력", sum(r["in"] for r in rows), "출력", sum(r["out"] for r in rows), "생각", sum(r["think"] for r in rows))


def clean_big(runs: list) -> list[int]:
    return [round(r["n"]) for r in runs if not r["hl"] and not r["hr"] and r["n"] >= BIG - NEAR_INT and abs(r["n"] - round(r["n"])) <= NEAR_INT]


def parse_time(s: str):
    m = re.search(r"(\d+):(\d+(?:\.\d+)?)", str(s))
    return (int(m.group(1)), float(m.group(2))) if m else None


def judge_claim(frames: list, claim: dict) -> tuple[str, list]:
    """frames = [(ms, 표시 시각, 덩어리)] → (뒷받침 | 반박 | 확인 불가, 근거)."""
    pt_ = parse_time(claim.get("time"))
    if pt_ is None:
        return "확인 불가", ["시각 못 읽음"]
    near = []
    for ms, lab, runs in frames:
        lm = parse_time(lab)
        if lm[0] == pt_[0] and abs(lm[1] - pt_[1]) * 1000 <= DT_MS + 1:
            near.append((lab, runs))
    model = Counter(claim.get("in_place") or [])
    seen, ok = [], False
    for lab, runs in near:
        big = clean_big(runs)
        if not big:
            continue
        seen.append((lab, big))
        if not (Counter(big) - model):
            ok = True
    if not seen:
        return "확인 불가", []
    return ("뒷받침" if ok else "반박"), seen


def cmd_check(a):
    ts = {t["id"]: t for t in gf.turns()}
    Rs, frames = {}, {}
    for i, t in ts.items():
        R = Rs.setdefault(t["game"], pt.Row(t["game"]))
        frames[i] = [(ms, hc.hms(ms)[3:], R.runs_of(R.view(ms))[0]) for ms in t[ARM]]
    table = Counter()
    rows_out = []
    per_rep = []
    for f in sorted((OUT / "answers").glob("*.json")):
        d = hc.jload(f)
        c = Counter()
        for r in d["rows"]:
            t = ts[r["id"]]
            right = r["j"] == t["j"]
            c["맞음" if right else ("없음" if r["j"] is None else "틀림")] += 1
            vs = [judge_claim(frames[r["id"]], m) for m in r["moments"]]
            kinds = [v for v, _ in vs]
            verdict = "걸림" if "반박" in kinds else ("통과" if "뒷받침" in kinds else "점검 불가")
            table[("맞음" if right else "틀림", verdict)] += 1
            rows_out.append({"file": f.name, "id": r["id"], "truth": t["j"], "j": r["j"], "verdict": verdict,
                             "claims": [{"time": m.get("time"), "in_place": m.get("in_place"), "held": m.get("held"), "v": v, "pix": e} for m, (v, e) in zip(r["moments"], vs)]})
            if a.verbose:
                print(f"{d['rep']} {r['id']} 정답 {t['j']} 답 {r['j']} [{'맞음' if right else '틀림'}] → {verdict}")
                for m, (v, e) in zip(r["moments"], vs):
                    print(f"      {m.get('time')} 제자리 {m.get('in_place')} 든 패 {m.get('held')} → {v} {e}")
        per_rep.append((d["rep"], c["맞음"], c["틀림"], c["없음"], sum(r["in"] for r in d["rows"]), sum(r["think"] for r in d["rows"])))
    for rep, ok, bad, none, tin, tth in per_rep:
        print(f"r{rep}: j 맞음 · 틀림 · 없음 {ok} · {bad} · {none} /9 | 입력 {tin:,} 생각 {tth:,}")
    print("답 판정(j 맞음/틀림 × 점검):")
    for right in ("맞음", "틀림"):
        n = sum(v for (r_, _), v in table.items() if r_ == right)
        print(f"  j {right} {n}: " + " · ".join(f"{k} {table[(right, k)]}" for k in ("걸림", "통과", "점검 불가")))
    nb = sum(v for (r_, _), v in table.items() if r_ == "틀림")
    ng = sum(v for (r_, _), v in table.items() if r_ == "맞음")
    if nb and ng:
        print(f"  틀린 답 중 걸림 {table[('틀림', '걸림')] / nb:.0%} · 맞은 답 중 걸림 {table[('맞음', '걸림')] / ng:.0%}")
    hc.jsave(OUT / "check.json", {"table": {f"{k[0]}|{k[1]}": v for k, v in table.items()}, "rows": rows_out})


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--model", default="gemini-3.8-flash")
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--force", action="store_true")
    c = sp.add_parser("check")
    c.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    {"run": cmd_run, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
