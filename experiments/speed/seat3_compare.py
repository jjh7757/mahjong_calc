"""안전장치(같은 요청 3개 동시 + 만장일치 + 앱 검사)를 켠 채로 자리 판독 두 방식 비교(2026-10-26 밤, 사용자 요청).

  지금 방식  bench v3a_norule(확대 토막 3 + 참고표), seat_reads_live.one_read 그대로
  새 방식    C·D = 모자이크 검출(s) + 조각을 한 장 그림으로(seat_yolo --det mosaic --layout sheet),
             B = 검출 실패 → 지금 방식(같은 시각의 지금 방식 B 장면을 씀) + 검출 실패 시간
  검출 시간은 운영 서버 실측(server_seat/server_run.txt: 모자이크 0.90 + 마스크 0.08 + 디코드 0.03초).

  python experiments/speed/seat3_compare.py [--trials 10]     결과 results/seat3_compare.json (덧붙임)
  python experiments/speed/seat3_compare.py --show

장면마다 같은 요청 3개를 같은 순간에 보내고, 세 답이 같고 앱 검사(앞면·장수·같은 패 4장 이하·텐파이/화료형)를 통과하면 자동 반영,
아니면 확인 질문. 장면 시간 = 세 답 중 가장 늦은 것(+ 검출).
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

import bench as b
import policy as P
import seat_reads_live as live
import seat_yolo as sy

OUT = b.OUT / "seat3_compare.json"
DET_OK = 0.899 + 0.082 + 0.027  # 서버 실측(중앙)
DET_FAIL = 0.889 + 0.082 + 0.027

_prep: dict = {}


def prep() -> None:
    sy.DET_MODE = "mosaic"
    dets = sy.detectors(0.04, "s")
    for s in "BCD":
        for p in b.PHOTOS[s]:
            rgb = np.asarray(Image.open(b.G / s / p / b.TRUTH[s][0]).convert("RGB"))
            st, _, used = sy.seat_frame(dets, rgb)
            _prep[p] = (s, rgb, st)
            print(f"{s} {p} 틀 [{used}]", flush=True)


def trial(job) -> dict:
    t, method, scene, photo = job
    sheet = b.ref_sheet_set2()
    if method == "base":
        fn = lambda _: live.one_read(scene, photo)  # noqa: E731
    else:
        _, rgb, st = _prep[photo]
        fn = lambda _: sy.piece_read(scene, photo, rgb, st, "sheet", sheet)  # noqa: E731
    t0 = time.perf_counter()
    with ThreadPoolExecutor(3) as ex:  # 같은 순간 3개(운영 /v2/seat 와 같게)
        reads = list(ex.map(fn, range(3)))
    print(f"{method:5s} {scene} {photo} #{t} {round(time.perf_counter() - t0, 1)}s "
          + " ".join(("O" if P.ok(r) else "x") + f"{r['s']:.0f}" for r in reads if not r.get("error")), flush=True)
    return {"trial": t, "method": method, "scene": scene, "photo": photo, "reads": reads}


def verdict(reads: list[dict]) -> tuple[str, float]:
    chk = P.CHECKS["tenpai"]
    good = [r for r in reads if not r.get("error")]
    t = max(r["s"] for r in reads)
    if len(good) == 3 and len({P.key(r) for r in good}) == 1 and all(chk(r) for r in good):
        return ("auto" if P.ok(good[0]) else "wrong"), t
    return "ask", t


def score(trials: list[dict]) -> None:
    base = [tr for tr in trials if tr["method"] == "base"]
    new = [tr for tr in trials if tr["method"] == "sheet"]
    plans = {
        "지금 방식(B·C·D)": [(tr, 0.0) for tr in base],
        "새 방식(B·C·D)": [(tr, DET_OK) for tr in new] + [(tr, DET_FAIL) for tr in base if tr["scene"] == "B"],
        "  지금 방식 C·D": [(tr, 0.0) for tr in base if tr["scene"] in "CD"],
        "  새 방식 C·D": [(tr, DET_OK) for tr in new],
        "  지금 방식 B": [(tr, 0.0) for tr in base if tr["scene"] == "B"],
        "  새 방식 B": [(tr, DET_FAIL) for tr in base if tr["scene"] == "B"],
    }
    print(f"\n{'':18s} {'장면':>4s} {'자동 반영':>9s} {'틀린 채 반영':>11s} {'확인 질문':>9s}   시간 중앙 / p90 / 최대   단독 읽기 정답")
    for name, rows in plans.items():
        if not rows:
            continue
        v = [verdict(tr["reads"]) for tr, _ in rows]
        t = sorted(tt + d for (_, tt), (_, d) in zip(v, rows))
        reads = [r for tr, _ in rows for r in tr["reads"]]
        n = len(rows)
        cnt = {k: sum(x == k for x, _ in v) for k in ("auto", "wrong", "ask")}
        print(f"{name:18s} {n:4d} {cnt['auto']:4d} ({cnt['auto'] / n:4.0%}) {cnt['wrong']:5d} ({cnt['wrong'] / n:4.1%}) "
              f"{cnt['ask']:4d} ({cnt['ask'] / n:4.0%})   {statistics.median(t):5.1f} / {t[int(.9 * len(t))]:5.1f} / {t[-1]:5.1f}초   "
              f"{sum(P.ok(r) for r in reads)}/{len(reads)}")
    for tr in trials:
        bad = [r for r in tr["reads"] if not P.ok(r)]
        if bad:
            print(f"  {tr['method']:5s} {tr['photo']} #{tr['trial']} {verdict(tr['reads'])[0]:5s} 틀린 읽기 {len(bad)}/3 예 "
                  f"{bad[0].get('hand') or bad[0].get('error', '')[:60]} | {bad[0].get('melds')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4, help="동시에 진행할 장면 수(장면마다 요청 3개)")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    if not a.show:
        prep()
        jobs = [(t, "base", s, p) for t in range(a.trials) for s in "BCD" for p in b.PHOTOS[s]]
        jobs += [(t, "sheet", s, p) for t in range(a.trials) for s in "CD" for p in b.PHOTOS[s] if _prep[p][2] is not None]
        random.Random(1026).shuffle(jobs)  # 두 방식을 같은 시간대에 섞어 보낸다
        with ThreadPoolExecutor(a.workers) as ex:
            new = list(ex.map(trial, jobs))
        old += new
        OUT.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    score(old)


if __name__ == "__main__":
    main()
