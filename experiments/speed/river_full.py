"""버림패(강) 전체 읽기: YOLO26 검출로 잡은 그 사람 강의 틀(river_yolo.py locate 가 쓴 rivers.json) + 패 종류는 Gemini.
강마다 찾은 패를 버린 순서대로 번호를 붙여 한 그림으로 만들고, 장면의 강 3개 + 참고표를 한 호출로 읽는다(2026-10-26).

  python experiments/speed/river_yolo.py locate          먼저(틀·그림)
  python experiments/speed/river_full.py [--runs 5]      결과 results/river_full.json

정답 TRUTH 는 크롭을 눈으로 보고 적은 것(NOTES "18."). * = 옆으로 눕힌 패(리치 선언패). 같은 장면의 사진 두 장은 같은 판.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import bench as b  # noqa: E402
import last3 as l3  # noqa: E402

ob = b.ob
RIV = ROOT / "results" / "river_yolo"

TRUTH = {
    "B": {"bottom": "1z 5z 7s 7z 7p* 5s 8s 7s 3p 9m 7p 3s 2m 8p 6m 9m 6s",
          "left": "2z 1z 2z 6s 8p 4z 1p 2p 2z 7z 6m 7p 7m 2s 4s 3s",
          "top": "5z 9m 4z 1p 8p 2m 1z 6z 1p 2s 1s 0s 8s 4p 7s 5p 3z 7z"},
    "C": {"bottom": "1z 5z 7s 7z 7p 5s 8s 7s 3p 9m 7p 3s 2m 8p 6m 9m 2z",
          "right": "5z 3m 4z 8m 1s 3z 4z 3z 3m 5s 2s 7p 8s 2p 2s 6p 6p",
          "top": "5z 8p 4z 1p 8p 2m 9p 6z 1p 2s 1s 0s 8s 4p 7s 5p 3z"},
    "D": {"right": "5z 3m 4z 8m 1s 3z 4z 3z 3m 5s 2s 7p 8s 2p 2s 6p 2z",
          "top": "5z 8p 4z 1p 8p 2m 9p 6z 1p 2s 1s 0s* 8s 4p 7s 5p 3z",
          "left": "1p 1s 2z 6s 8p 4z 2p 2s 4s 7z 6m 7p 3s 3s 6s 7z"},
}
SCENE_OF = {p: s for s, ps in l3.PHOTOS.items() for p in ps}

PROMPT = """사진 {n}장은 각각 리치마작 한 플레이어의 버림패(강)를 버린 순서대로 한 장씩 잘라 붙인 것입니다. 칸 아래에 번호(1부터)가 있습니다.
{keys}: 첫째·둘째·셋째 사진마다, 번호 순서대로 각 칸의 패 종류를 적습니다. 칸 수와 같은 개수를 적고, 칸을 건너뛰거나 더하지 않습니다.
옆으로 눕혀 붙인 칸도 그 패의 종류를 적습니다. 칸 가장자리에 이웃 패가 조금 걸려 있으면 가운데 패만 봅니다.

{notation}

마지막 사진은 이 패 세트의 통수(1p~9p)·삭수(1s~9s) 실물 참고표입니다(이름표가 위에 있음). 통수·삭수는 참고표와 무늬 개수·배치를 비교해 정합니다.
참고표는 답에 넣지 않습니다."""


def sheet(img, rows) -> bytes:
    """강 패를 줄마다 한 줄로, 칸 아래 1부터 번호. 눕힌 패는 그대로(가로)."""
    lines, k = [], 1
    for row in rows:
        cells = []
        for x, y, w, h in row:
            c = img[max(0, y):y + h, max(0, x):x + w]
            c = cv2.resize(c, (max(1, int(c.shape[1] * 140 / max(1, c.shape[0]))), 140))
            cell = np.full((180, max(130, c.shape[1] + 10), 3), 255, np.uint8)
            cell[:140, 5:5 + c.shape[1]] = c
            cv2.putText(cell, str(k), (8, 172), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
            cells.append(cell)
            k += 1
        lines.append(np.hstack(cells))
    w = max(l.shape[1] for l in lines)
    im = np.vstack([cv2.copyMakeBorder(l, 0, 8, 0, w - l.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)) for l in lines])
    return cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--model", default="haselab", help="river_yolo.py locate 에 준 모델(결과 폴더)")
    a = ap.parse_args()
    global RIV
    if a.model != "haselab":
        RIV = ROOT / "results" / f"river_yolo_{a.model}"
    rivers = json.loads((RIV / "rivers.json").read_text(encoding="utf-8"))
    sheets, structure = {}, {}
    for key, v in rivers.items():
        photo, side = key.rsplit("_", 1)
        scene = SCENE_OF[photo]
        img = cv2.imread(str(b.G / scene / photo / f"last_{side}.jpg"))
        sheets[key] = sheet(img, v["rows"])
        (RIV / "full").mkdir(exist_ok=True)
        (RIV / "full" / f"{key}.jpg").write_bytes(sheets[key])
        truth = TRUTH[scene][side].split()
        got_side = [b[2] > 1.15 * b[3] for r in v["rows"] for b in r]
        structure[key] = {"n": len(got_side), "n_truth": len(truth), "count_ok": len(got_side) == len(truth),
                          "sideways_ok": got_side == [t.endswith("*") for t in truth] if len(got_side) == len(truth) else False}
    print("구조:", sum(s["count_ok"] for s in structure.values()), "/", len(structure), "장수 맞음,",
          sum(s["sideways_ok"] for s in structure.values()), "가로 패까지 맞음")
    for k, s in structure.items():
        if not s["sideways_ok"]:
            print(f"  {k}: 찾은 {s['n']}장 / 정답 {s['n_truth']}장  가로 {'맞음' if s['sideways_ok'] else '틀림'}")

    per = {"type": "object", "properties": {"tiles": {"type": "array", "items": {"type": "string", "enum": ob.TILE_CODES}}},
           "required": ["tiles"]}

    def one(job):
        run_i, photo = job
        scene = SCENE_OF[photo]
        sides = list(TRUTH[scene])
        keys = [f"photo{i + 1}" for i in range(len(sides))]
        datas = [sheets[f"{photo}_{s}"] for s in sides]
        schema = {"type": "object", "properties": {**{k: per for k in keys}, "notes": {"type": "string"}}, "required": keys}
        r = b.call(datas[0], PROMPT.format(n=len(sides), keys=", ".join(keys), notation=ob.NOTATION), schema, l3.MODEL, "low",
                   None, extra=[b.image_part(d, None) for d in datas[1:]] + [b.image_part(b.ref_sheet_set2(), None)])
        out = {"run": run_i, "photo": photo, "scene": scene, "wall": r["s"], "think": r.get("think"), "rivers": {}}
        for s, k in zip(sides, keys):
            got = (r.get("data") or {}).get(k, {}).get("tiles", []) if "data" in r else []
            truth = [t.rstrip("*") for t in TRUTH[scene][s].split()]
            pos = sum(g == t for g, t in zip(got, truth)) if len(got) == len(truth) else 0
            out["rivers"][s] = {"got": got, "exact": got == truth, "pos_ok": pos, "n": len(truth),
                                "structure_ok": structure[f"{photo}_{s}"]["count_ok"]}
        print(f"{photo} #{run_i} {r['s']:5.1f}s " + " ".join(f"{s}:{v['pos_ok']}/{v['n']}" for s, v in out["rivers"].items()), flush=True)
        return out

    jobs = [(r, p) for r in range(a.runs) for p in SCENE_OF]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(one, jobs))
    (ROOT / "results" / ("river_full.json" if a.model == "haselab" else f"river_full_{a.model}.json")).write_text(json.dumps({"structure": structure, "reads": rows}, ensure_ascii=False, indent=1),
                                                      encoding="utf-8")
    rv = [v for r in rows for v in r["rivers"].values()]
    ok_struct = [v for v in rv if v["structure_ok"]]
    w = sorted(r["wall"] for r in rows)
    print(f"\n강 {len(rv)}개 읽기: 통째 정답 {sum(v['exact'] for v in rv)}/{len(rv)}  "
          f"(구조 맞은 강만 {sum(v['exact'] for v in ok_struct)}/{len(ok_struct)}, 패 단위 {sum(v['pos_ok'] for v in ok_struct)}/{sum(v['n'] for v in ok_struct)})  "
          f"호출 시간 중앙 {statistics.median(w):.1f} / p90 {w[int(.9 * len(w))]:.1f}초")
    from collections import Counter
    errs = Counter()
    for r in rows:
        for s, v in r["rivers"].items():
            if v["structure_ok"] and not v["exact"]:
                truth = [t.rstrip("*") for t in TRUTH[r["scene"]][s].split()]
                for i, (g, t) in enumerate(zip(v["got"], truth)):
                    if g != t:
                        errs[(r["scene"], s, i + 1, t, g)] += 1
    for (sc, s, i, t, g), n in sorted(errs.items(), key=lambda kv: -kv[1]):
        print(f"  {sc} {s} {i}번: {t} → {g} ×{n}")


if __name__ == "__main__":
    main()
