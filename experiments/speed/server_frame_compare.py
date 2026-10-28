"""서버 /v2/seat 두 방식을 같은 시각에 나란히: 새 방식(YOLO 틀 + 조각 그림, app/seat.py, 8030) vs 지금 방식(통째 읽기, 8031).
두 서버는 같은 코드에 SEAT_FRAME 만 다르다(launch.json "recognizer" / "recognizer-noframe"). 자리 3번 동시 + 만장일치 그대로.

  python experiments/speed/server_frame_compare.py [--runs 10] [--a http://127.0.0.1:8030] [--b http://127.0.0.1:8031]
  결과 results/server_frame_compare.json (덧붙임), --show 로 요약만

장면마다 두 서버에 같은 크롭을 같은 순간에 보내(Gemini 요청 6개 동시) 시간대 차이를 없앤다. 채점은 bench.TRUTH(손패 + 울기).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

import bench as b

OUT = b.OUT / "server_frame_compare.json"


def post(url: str, jpeg: bytes) -> dict:
    t0 = time.perf_counter()
    r = requests.post(f"{url}/v2/seat", files={"image": ("seat.jpg", jpeg, "image/jpeg")}, timeout=180)
    secs = time.perf_counter() - t0
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text[:100]}", "s": secs}
    return {"data": r.json(), "s": secs}


def judge(scene: str, d: dict) -> dict:
    hand = [t["tile"] for t in d["tiles"]] + ([d["separate_tile"]["tile"]] if d.get("separate_tile") else [])
    melds = sorted(" ".join(sorted(m["tiles"])) for m in d["melds"])
    th, tm = b.TRUTH[scene][1].split(), sorted(" ".join(sorted(m.split())) for m in b.TRUTH[scene][2])
    return {"hand": " ".join(hand), "melds": melds, "ok": sorted(hand) == sorted(th) and melds == tm,
            "unanimous": d["agreement"]["unanimous"], "method": d.get("method"),
            "frame_ms": (d.get("frame") or {}).get("ms"), "in": d["usage"]["input_tokens"],
            "out": d["usage"]["output_tokens"], "server_ms": d["latency_ms"]}


def run(runs: int, a: str, b_url: str) -> list[dict]:
    rows = []
    crops = [(s, p, (b.G / s / p / b.TRUTH[s][0]).read_bytes()) for s in "BCD" for p in b.PHOTOS[s]]
    with ThreadPoolExecutor(2) as ex:
        for i in range(runs):
            for scene, photo, jpeg in crops:
                ra, rb = list(ex.map(lambda u: post(u, jpeg), (a, b_url)))
                for name, r in (("frame", ra), ("whole", rb)):
                    row = {"run": i, "cond": name, "scene": scene, "photo": photo, "s": round(r["s"], 2)}
                    if "error" in r:
                        row["error"] = r["error"]
                    else:
                        row.update(judge(scene, r["data"]))
                    rows.append(row)
                    print(f"{name:5s} {scene} {photo} #{i} {row['s']:5.1f}s {row.get('method') or row.get('error')} "
                          f"{'OK' if row.get('ok') else 'X ' + str(row.get('hand'))}"
                          f"{'' if row.get('unanimous', True) else ' (엇갈림)'}", flush=True)
            time.sleep(2)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    OUT.write_text(json.dumps(old + rows, ensure_ascii=False, indent=0), encoding="utf-8")
    return old + rows


def show(rows: list[dict]) -> None:
    def line(name: str, rs: list[dict]) -> None:
        good = [r for r in rs if "error" not in r]
        if not good:
            print(f"{name}: 없음")
            return
        t = sorted(r["s"] for r in good)
        print(f"{name:28s} 정답 {sum(r['ok'] for r in good)}/{len(good)}  만장일치 {sum(r['unanimous'] for r in good)}  "
              f"중앙 {statistics.median(t):.1f} / p90 {t[int(.9 * (len(t) - 1))]:.1f} / 최대 {t[-1]:.1f}초  "
              f"입력 {statistics.median(r['in'] for r in good) / 1000:.1f}k  오류 {len(rs) - len(good)}  "
              f"틀 {sum(r.get('method') == 'frame' for r in good)}")

    for cond in ("frame", "whole"):
        line(f"{cond} B·C·D", [r for r in rows if r["cond"] == cond])
        for s in "BCD":
            line(f"  {cond} {s}", [r for r in rows if r["cond"] == cond and r["scene"] == s])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--a", default="http://127.0.0.1:8030")
    ap.add_argument("--b", default="http://127.0.0.1:8031")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.show:
        show(json.loads(OUT.read_text(encoding="utf-8")))
    else:
        show(run(args.runs, args.a, args.b))
