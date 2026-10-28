"""자리 판독 몇 번 읽기가 안전한가 — 실측(2026-10-26, 사용자 요청: "3번을 2번으로 줄이면 실제로 얼마나 틀리나").

운영 서버(/v2/seat, SEAT_READS=3)와 똑같이 같은 요청 3개를 **같은 순간에** 보내고(같은 순간의 오답 상관까지 담기게),
그 세 답으로 정책을 함께 채점한다. 프롬프트·입력은 지금 서버(05eaec0 이후 = bench 조건 v3a_norule).

  python experiments/speed/seat_reads_live.py [--trials 15]      결과 results/seat_reads_live.json (덧붙임)
  python experiments/speed/seat_reads_live.py --show

정책(앱 검사 = 앞면·장수 13~14·같은 패 5장 이하 + 13장 텐파이/14장 화료형, policy.CHECKS["tenpai"]):
  one    보낸 첫 요청 답 하나. 검사 통과면 반영.
  two    보낸 첫 두 요청 답이 같고 검사 통과면 반영, 아니면 확인 질문(시간 = 두 답 중 늦은 것).
  three  세 답이 모두 같고 검사 통과면 반영(지금 운영).
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import bench as b
import policy as P

OUT = b.OUT / "seat_reads_live.json"
COND = "v3a_norule"


def one_read(scene: str, photo: str) -> dict:
    c = {**b.BASE, **b.CONDS[COND]}
    path = b.G / scene / photo / b.TRUTH[scene][0]
    data = b.load(path, c["max_side"], c["crop"])
    prompt, schema = b.SEAT_PROMPT_V3A, b.SEAT_SCHEMA_V3A
    rule = prompt[prompt.index("장수: 앞면 손패라면"):]
    prompt = prompt.replace(rule[:rule.index("\n\n") + 2], "")
    extra = [b.image_part(z, c["zoom_res"]) for z in b.zoom_strips(path, c["zoom"], c.get("width", 0.4))]
    prompt += b.ZOOM_NOTE.format(n=c["zoom"])
    extra.append(b.image_part(b.ref_sheet_set2(), None))
    prompt += b.REF_NOTE
    r = b.call(data, prompt, schema, c["model"], c["thinking"], c["res"], extra=extra)
    row = {"scene": scene, "photo": photo, **{k: r.get(k) for k in ("s", "in", "out", "think", "error")}}
    if "data" in r:
        row.update(b.judge(scene, r["data"]))
    return row


def trial(job) -> dict:
    t, scene, photo = job
    t0 = time.perf_counter()
    with ThreadPoolExecutor(3) as ex:  # 같은 순간 3개
        reads = list(ex.map(lambda _: one_read(scene, photo), range(3)))
    print(f"{scene} {photo} #{t} {round(time.perf_counter() - t0, 1)}s "
          + " ".join(("O" if P.ok(r) else "x") + f"{r['s']:.0f}" for r in reads if not r.get("error")), flush=True)
    return {"trial": t, "scene": scene, "photo": photo, "reads": reads}


def score(trials: list[dict]) -> None:
    chk = P.CHECKS["tenpai"]
    res = {k: {"auto": 0, "wrong": 0, "ask": 0, "t": []} for k in ("one", "two", "three")}
    usable = [tr for tr in trials if len([r for r in tr["reads"] if not r.get("error")]) == 3]
    for tr in usable:
        rs = tr["reads"]
        for name, k in (("one", 1), ("two", 2), ("three", 3)):
            sub = rs[:k]
            res[name]["t"].append(max(r["s"] for r in sub))
            same = len({P.key(r) for r in sub}) == 1 and all(chk(r) for r in sub)
            if same:
                res[name]["auto"] += 1
                res[name]["wrong"] += not P.ok(sub[0])
            else:
                res[name]["ask"] += 1
    n = len(usable)
    reads = [r for tr in usable for r in tr["reads"]]
    print(f"\n장면 {n}개(사진 6장 × 시행), 읽기 {len(reads)}번 중 단독 정답 {sum(P.ok(r) for r in reads)} "
          f"({sum(P.ok(r) for r in reads) / max(1, len(reads)):.1%})")
    print(f"{'정책':8s} {'자동 반영':>10s} {'틀린 채 반영':>14s} {'확인 질문':>10s} {'자리 판독 시간 중앙 / p90':>22s}")
    for name, v in res.items():
        t = sorted(v["t"])
        print(f"{name:8s} {v['auto']:4d} ({v['auto'] / n:5.1%}) {v['wrong']:4d} ({v['wrong'] / n:5.2%}) "
              f"{v['ask']:4d} ({v['ask'] / n:5.1%})   {statistics.median(t):5.1f} / {t[int(.9 * len(t))]:5.1f}초")
    wrong_photos = {}
    for tr in usable:
        for r in tr["reads"]:
            if not P.ok(r):
                wrong_photos.setdefault(tr["photo"], []).append(r.get("hand"))
    for p, hs in wrong_photos.items():
        print(f"  틀린 읽기 {p}: {len(hs)}번 — 예 {hs[0]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=15)
    ap.add_argument("--workers", type=int, default=4, help="동시에 진행할 시행 수(시행마다 요청 3개)")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    if not a.show:
        jobs = [(t, s, p) for t in range(a.trials) for s in "BCD" for p in b.PHOTOS[s]]
        with ThreadPoolExecutor(a.workers) as ex:
            new = list(ex.map(trial, jobs))
        old += new
        OUT.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    score(old)


if __name__ == "__main__":
    main()
