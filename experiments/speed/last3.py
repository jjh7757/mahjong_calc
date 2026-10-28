"""강 끝 판독: 자리별 3호출(지금 /v2/last ×3) vs 사진 3장을 한 호출에 — B·C·D 로 나란히 잰다.

  python experiments/speed/last3.py [--runs 10] [--workers 6]

같은 장면의 두 조건을 같은 순간에 보낸다(시간대 차이를 없애려고). 크롭은 grid5_scenes 의 last_<자리>.jpg(그 자리 쪽으로 세운 가운데 칸),
화료자 자리는 뺀다(앱과 같음). 정답은 크롭을 눈으로 확인한 것(NOTES "16.") — 지난 판독 기록의 다수 답이 틀린 곳이 셋 있었다
(B k28 아래 8삭 → 실제 6삭, C 오른쪽 5통 → 6통, D k12 위 北 → 西).
결과는 results/last3.json 에 덧붙인다.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import bench as b

ob = b.ob
PHOTOS = {"B": ["k25_1", "k28_1"], "C": ["k15_1", "k26_1"], "D": ["k12_1", "k16_1"]}
WINNER = {"B": "right", "C": "left", "D": "bottom"}
TRUTH = {
    "B": {"bottom": "6s", "left": "3s", "top": "7z"},
    "C": {"bottom": "2z", "right": "6p", "top": "3z"},
    "D": {"right": "2z", "top": "3z", "left": "7z"},
}
RON = {"B": "top", "C": "bottom", "D": "right"}  # 화료패(론)를 버린 자리 — 점수에 쓰이는 강 끝

_PER = {k: v for k, v in ob.LAST_SCHEMA_V2["properties"].items() if k != "notes"}
_PER_OBJ = {"type": "object", "properties": _PER, "required": ["last_tile", "tile_count"]}
LAST3_SCHEMA = {
    "type": "object",
    "properties": {"photo1": _PER_OBJ, "photo2": _PER_OBJ, "photo3": _PER_OBJ, "notes": ob.LAST_SCHEMA_V2["properties"]["notes"]},
    "required": ["photo1", "photo2", "photo3", "notes"],
}
LAST3_PROMPT = f"""사진 3장은 리치마작 테이블 가운데의 버림패(강)를 찍은 것으로, 사진마다 서로 다른 플레이어 쪽에서 본 방향으로 세웠습니다. {ob._ONLY_SEE}

사진마다 그 사진의 아래쪽 플레이어 강만 봅니다. 글자가 바로 서 보이는(위아래가 맞는) 패들이 그 사람의 강입니다.
강은 6장씩 줄을 이루고, 첫 줄은 테이블 가운데 쪽(사진 위쪽)이며 다음 줄은 아래쪽 플레이어 쪽(사진 아래쪽)으로 쌓입니다.
각 줄은 왼쪽에서 오른쪽으로 버립니다. 따라서 마지막 패는 **가장 아래 줄의 가장 오른쪽 패**입니다.
그 패가 옆으로 눕혀져 있어도 그대로 마지막 패입니다.

- photo1, photo2, photo3: 첫째·둘째·셋째 사진의 결과. 사진마다 따로 봅니다.
  - last_tile: 그 사진 아래쪽 플레이어 강의 마지막 패 한 장. 그 강이 보이지 않으면 null.
  - tile_count: 그 강의 패 수.
- 옆으로(90도) 또는 거꾸로(180도) 돌아가 보이는 패는 다른 자리의 강이니 보지 않습니다. 가운데 자동탁 기기·패산도 보지 않습니다.

{ob.NOTATION}

확신도(0~1)를 적어 주세요."""

MODEL = b.BASE["model"]


def code(t) -> str | None:
    c = ob._code(t)
    return c["tile"] if c else None


def run_separate(crops: dict[str, bytes]) -> dict:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(len(crops)) as ex:
        futs = {s: ex.submit(b.call, d, ob.LAST_PROMPT_V2, ob.LAST_SCHEMA_V2, MODEL, "low", None) for s, d in crops.items()}
        res = {s: f.result() for s, f in futs.items()}
    return {"wall": round(time.perf_counter() - t0, 2),
            "tiles": {s: (code(r["data"].get("last_tile")) if "data" in r else "ERR") for s, r in res.items()},
            "calls": [{k: r.get(k) for k in ("s", "in", "out", "think", "error")} for r in res.values()]}


def run_combined(crops: dict[str, bytes]) -> dict:
    sides = list(crops)
    datas = [crops[s] for s in sides]
    t0 = time.perf_counter()
    r = b.call(datas[0], LAST3_PROMPT, LAST3_SCHEMA, MODEL, "low", None, extra=[b.image_part(d, None) for d in datas[1:]])
    tiles = {s: (code((r["data"].get(f"photo{i + 1}") or {}).get("last_tile")) if "data" in r else "ERR")
             for i, s in enumerate(sides)}
    return {"wall": round(time.perf_counter() - t0, 2), "tiles": tiles,
            "calls": [{k: r.get(k) for k in ("s", "in", "out", "think", "error")}]}


def one(job):
    run, scene, photo = job
    d = b.G / scene / photo
    crops = {s: b.load(d / f"last_{s}.jpg", 1568) for s in TRUTH[scene]}
    with ThreadPoolExecutor(2) as ex:
        fs, fc = ex.submit(run_separate, crops), ex.submit(run_combined, crops)
        out = []
        for cond, f in (("separate", fs), ("combined", fc)):
            r = f.result()
            ok = {s: r["tiles"][s] == t for s, t in TRUTH[scene].items()}
            out.append({"run": run, "scene": scene, "photo": photo, "cond": cond, **r, "ok": ok,
                        "all_ok": all(ok.values()), "ron_ok": ok[RON[scene]]})
    print(f"{scene} {photo} #{run}  " + "  ".join(
        f"{o['cond'][:3]} {o['wall']:5.1f}s {'O' if o['all_ok'] else 'x'} {o['tiles']}" for o in out), flush=True)
    return out


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def summarize(rows: list[dict]) -> None:
    print("\n조건      장면  세 자리 모두  론 패   자리별      시간 중앙 / p90 / 최대   10초 넘음  생각(합) 중앙/최대  입력 토큰")
    for cond in ("separate", "combined"):
        rs = [r for r in rows if r["cond"] == cond]
        n = len(rs)
        sides = sum(len(r["ok"]) for r in rs)
        walls = [r["wall"] for r in rs]
        think = [sum(c.get("think") or 0 for c in r["calls"]) for r in rs]
        tin = [sum(c.get("in") or 0 for c in r["calls"]) for r in rs]
        print(f"{cond:9s} {n:4d}  {sum(r['all_ok'] for r in rs):3d}/{n}  {sum(r['ron_ok'] for r in rs):3d}/{n}  "
              f"{sum(sum(r['ok'].values()) for r in rs):3d}/{sides}  "
              f"{statistics.median(walls):5.1f} / {q(walls, .9):5.1f} / {max(walls):5.1f}   {sum(w > 10 for w in walls):3d}/{n}   "
              f"{statistics.median(think):5.0f}/{max(think):5.0f}   {statistics.median(tin):.0f}")
    print("\n틀린 답(조건·사진·자리: 읽은 것 → 정답)")
    for r in rows:
        for s, good in r["ok"].items():
            if not good:
                print(f"  {r['cond']:9s} {r['photo']} {s:6s}: {r['tiles'][s]} → {TRUTH[r['scene']][s]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--show", action="store_true", help="새로 재지 않고 쌓인 결과만 집계")
    a = ap.parse_args()
    path = b.OUT / "last3.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not a.show:
        jobs = [(r, s, p) for r in range(a.runs) for s, ps in PHOTOS.items() for p in ps]
        with ThreadPoolExecutor(a.workers) as ex:
            new = [o for out in ex.map(one, jobs) for o in out]
        old += new
        path.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
    summarize(old)


if __name__ == "__main__":
    main()
