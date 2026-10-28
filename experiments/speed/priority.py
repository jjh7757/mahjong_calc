"""Gemini Priority 등급(service_tier=priority)이 자리 판독 시간(특히 생각 없이 늦는 대기열 몫)을 줄이나.

  python -I experiments/speed/priority.py probe                 짧은 요청 하나로 등급이 받아지는지(응답 헤더 x-gemini-service-tier)
  python -I experiments/speed/priority.py read --runs 17        B·C·D 자리 판독을 standard / priority 섞어 같은 시각에
  python -I experiments/speed/priority.py stats

요청은 운영 서버(131275a) 자리 판독 한 번과 같다(seat_focus.seat_request 와 같은 사진·프롬프트). 등급만 다르다.
결과 results/priority/<tag>.json. 한도를 넘은 priority 요청은 standard 로 내려가므로 응답 헤더의 실제 등급을 같이 적는다.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402
from google.genai import types  # noqa: E402

from app import observe as ob  # noqa: E402
from app.recognizer import REF_SHEET, prepare_image, zoom_strips  # noqa: E402

OUT = b.OUT / "priority"
SEATS = {"B": "hand_right", "C": "hand_left", "D": "hand_bottom"}


def call(contents, schema, tier: str | None, model: str = "gemini-3.8-flash") -> dict:
    cfg = types.GenerateContentConfig(response_mime_type="application/json" if schema else None,
                                      response_schema=schema, thinking_config=types.ThinkingConfig(thinking_level="low"),
                                      service_tier=tier)
    t0 = time.perf_counter()
    try:
        r = b.client().models.generate_content(model=model, contents=contents, config=cfg)
        um = r.usage_metadata
        h = dict(r.sdk_http_response.headers or {}) if r.sdk_http_response else {}
        return {"s": round(time.perf_counter() - t0, 2), "in": um.prompt_token_count or 0,
                "out": um.candidates_token_count or 0, "think": getattr(um, "thoughts_token_count", 0) or 0,
                "served": h.get("x-gemini-service-tier"), "text": r.text,
                "server_ms": h.get("server-timing")}
    except Exception as e:  # noqa: BLE001
        return {"s": round(time.perf_counter() - t0, 2), "error": f"{type(e).__name__}: {e}"[:400]}


def probe() -> None:
    for tier in (None, "standard", "priority"):
        r = call(["1+1 은? 숫자만."], None, tier)
        print(tier, {k: v for k, v in r.items() if k != "text"}, (r.get("text") or "")[:20])


def seat_contents(s: str, p: str) -> list:
    jpg = prepare_image((b.G / s / p / f"{SEATS[s]}.jpg").read_bytes(), 3072)
    return ([b.image_part(jpg, "ULTRA_HIGH")] + [b.image_part(z, "ULTRA_HIGH") for z in zoom_strips(jpg, ob.SEAT_ZOOM_STRIPS)]
            + [b.image_part(REF_SHEET.read_bytes(), None), ob.SEAT_PROMPT_V2])


def read(runs: int, workers: int, tag: str) -> None:
    contents = {(s, p): seat_contents(s, p) for s in SEATS for p in b.PHOTOS[s]}
    jobs = [(t, s, p) for _ in range(runs) for s in SEATS for p in b.PHOTOS[s] for t in ("standard", "priority")]

    def one(job):
        t, s, p = job
        r = call(contents[(s, p)], ob.SEAT_SCHEMA_V2, t)
        row = {"tier": t, "scene": s, "photo": p, **{k: r.get(k) for k in ("s", "in", "out", "think", "served", "error")}}
        if r.get("text"):
            try:
                row.update(b.judge(s, json.loads(r["text"])))
            except Exception as e:  # noqa: BLE001
                row["error"] = f"parse: {e}"[:200]
        ok = row.get("hand_ok") and row.get("melds_ok")
        print(f"{t:8s} served={row.get('served')} {s} {p} {row['s']}s think {row.get('think')} "
              f"{'OK' if ok else row.get('error') or 'X ' + str(row.get('hand'))}", flush=True)
        return row

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, jobs))
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{tag}.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    f.write_text(json.dumps(old + rows, ensure_ascii=False, indent=1), encoding="utf-8")
    stats(old + rows)


def group(runs: int, tag: str) -> None:
    """운영처럼 같은 요청 3개 묶음을 등급마다 하나씩 동시에. 첫 측정(read)에서 내용이 같은 standard·priority 요청이
    같이 늦어(29.08 / 29.09초) 서로 묶여 처리됐다 → 두 묶음은 프롬프트 끝 표식(A/B, 등급과 무작위 짝)으로 다른 요청으로 만든다.
    자리 판독 시간 = 묶음 셋 중 가장 늦은 답."""
    import random
    contents = {(s, p): seat_contents(s, p) for s in SEATS for p in b.PHOTOS[s]}
    rows = []
    for i in range(runs):
        for s in SEATS:
            for p in b.PHOTOS[s]:
                marks = random.sample(["A", "B"], 2)
                jobs = [(t, m) for t, m in zip(("standard", "priority"), marks) for _ in range(3)]
                base = contents[(s, p)]
                t0 = time.perf_counter()
                with ThreadPoolExecutor(6) as ex:
                    res = list(ex.map(lambda j: (j, call(base[:-1] + [base[-1] + f"\n\n(판독 요청 {j[1]})"],
                                                         ob.SEAT_SCHEMA_V2, j[0])), jobs))
                for t in ("standard", "priority"):
                    rs = [r for (tt, _), r in res if tt == t]
                    good = [r for r in rs if not r.get("error")]
                    reads = []
                    for r in good:
                        try:
                            reads.append(b.judge(s, json.loads(r["text"])))
                        except Exception:  # noqa: BLE001
                            pass
                    row = {"tier": t, "scene": s, "photo": p, "mark": marks[0 if t == "standard" else 1],
                           "s": max(r["s"] for r in rs), "each": [r["s"] for r in rs], "think": [r.get("think") for r in rs],
                           "served": sorted({r.get("served") for r in good}, key=str), "errors": len(rs) - len(good),
                           "ok": sum(1 for x in reads if x["hand_ok"] and x["melds_ok"]),
                           "unanimous_ok": len(reads) == 3 and all(x["hand_ok"] and x["melds_ok"] for x in reads)}
                    rows.append(row)
                    print(f"{i} {t:8s} {s} {p} 묶음 {row['s']:5.1f}s {row['each']} think {row['think']} "
                          f"정답 {row['ok']}/3 {row['served']}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{tag}.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    f.write_text(json.dumps(old + rows, ensure_ascii=False, indent=1), encoding="utf-8")
    group_stats(old + rows)


def group_stats(rows: list[dict]) -> None:
    for t in ("standard", "priority"):
        rs = [r for r in rows if r["tier"] == t]
        if not rs:
            continue
        g = [r["s"] for r in rs]
        each = [x for r in rs for x in r["each"]]
        z = [x for r in rs for x, th in zip(r["each"], r["think"]) if not th]
        print(f"{t:8s} 묶음 {len(rs)}개: 묶음 시간 중앙 {statistics.median(g):.1f} p90 {pct(g, .9):.1f} 최대 {max(g):.1f}s, "
              f"20초 넘음 {sum(1 for x in g if x > 20)}  | 호출 {len(each)}개 중앙 {statistics.median(each):.1f} p90 {pct(each, .9):.1f}s, "
              f"생각 0 인데 10초 넘음 {sum(1 for x in z if x > 10)}/{len(z)}  | 만장일치 정답 {sum(r['unanimous_ok'] for r in rs)}/{len(rs)} "
              f"읽기 정답 {sum(r['ok'] for r in rs)}/{3 * len(rs)}  등급 {sorted({x for r in rs for x in r['served']}, key=str)}")
    for m in ("A", "B"):
        rs = [r for r in rows if r.get("mark") == m]
        if rs:
            print(f"  (표식 {m} 쪽 묶음 시간 중앙 {statistics.median(r['s'] for r in rs):.1f}, 표식 영향 확인)")


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(math.ceil(q * len(v))) - 1)]


def stats(rows: list[dict]) -> None:
    for t in ("standard", "priority"):
        rs = [r for r in rows if r["tier"] == t]
        if not rs:
            continue
        good = [r for r in rs if not r.get("error")]
        ok = sum(1 for r in good if r.get("hand_ok") and r.get("melds_ok"))
        s = [r["s"] for r in good]
        z = [r["s"] for r in good if not r["think"]]  # 생각 0 = 대기열·처리 몫만
        served = {}
        for r in good:
            served[r.get("served")] = served.get(r.get("served"), 0) + 1
        print(f"{t:8s} 정답 {ok}/{len(rs)}  중앙 {statistics.median(s):.1f} p90 {pct(s, .9):.1f} 최대 {max(s):.1f}s  "
              f"생각한 호출 {len(good) - len(z)}/{len(good)}  | 생각 0 인 호출 {len(z)}개: 중앙 {statistics.median(z):.1f} "
              f"p90 {pct(z, .9):.1f} 최대 {max(z):.1f}s, 10초 넘음 {sum(1 for x in z if x > 10)}  실제 등급 {served}"
              + (f"  오류 {len(rs) - len(good)}" if len(rs) > len(good) else ""))
        for r in rs:
            if r.get("error"):
                print("   오류:", r["error"][:200])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["probe", "read", "group", "stats"])
    ap.add_argument("--runs", type=int, default=17)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tag", default="read")
    a = ap.parse_args()
    if a.mode == "probe":
        probe()
    elif a.mode == "read":
        read(a.runs, a.workers, a.tag)
    elif a.mode == "group":
        group(a.runs, a.tag if a.tag != "read" else "group")
    else:
        for f in sorted(OUT.glob("*.json")):
            print("==", f.stem)
            rows = json.loads(f.read_text(encoding="utf-8"))
            (group_stats if "each" in rows[0] else stats)(rows)


if __name__ == "__main__":
    main()
