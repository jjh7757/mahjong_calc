"""8b-1 채점(metrics 표 1-101)을 새 구역표 로더(table_frame.py + assets/table_frame/zones.json)로 다시 — 8b "할 일 2" 확인(2026-11-06).

기준점 = 8b-1 결과 wall_frame.json 의 est(사진마다 c·θ·u·D, carry 는 rise 기준점을 사진 크기로 옮긴 것) 그대로, 정답 패 = wall_frame.truth_tiles
(사람 역할 라벨·B·C·D 펠트 규칙), 채점 = wall_frame.score(표 1-40 방식). 구역 판정만 wall_frame.zone_frame 대신 table_frame.TableZones 로
바꿔, 표 1-101 의 틀린 수(개발 10·테스트 7·색 바꾼 7·carry 0·재색칠 10)가 그대로 나오는지 본다. 안 나오면 로더 버그 — 상수는 안 맞춘다(검토 ⑤).
더해서 표시패가 제 칸(가운데 또는 왕패 칸 dead_wall)에 드는 수(검토 ④ 기준 ≥ 저장 격자 19/26).

wall_frame.py·결과·라벨은 아직 본 체크아웃에만 있다(커밋 전) — 그 폴더를 읽기만 한다(WALL_FRAME_DIR, 바이트코드 안 씀).
  python -I -X utf8 experiments/zone_points/table_frame_score.py      → experiments/zone_points/results/table_frame_score.json(커밋 안 함)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WF_DIR = Path(os.environ.get("WALL_FRAME_DIR", "C:/Users/jjh7757/dev/mahjong_calc/experiments/zone_points"))
sys.path.insert(0, str(HERE))
import table_frame as tf  # noqa: E402

if not (HERE / "wall_frame.py").exists():
    sys.path.insert(1, str(WF_DIR))
import wall_frame as wf  # noqa: E402

OUT = HERE / "results" / "table_frame_score.json"


def classify(tz: tf.TableZones, pts) -> tuple[list[str], list[str]]:
    """wall_frame.zone_frame 과 같은 뜻(큰 칸 = 바람개비, 세부 = 기기·강·손패 띠·울기 모서리)을 구역표로."""
    big, fine = [], []
    for x, y in pts:
        b = tz.zone_of(x, y)
        big.append(b)
        if b == "center":
            qx, qy = tz.to_frame(x, y)
            s = ("bottom" if qy >= 0 else "top") if abs(qy) >= abs(qx) else ("right" if qx >= 0 else "left")
            if tz.inside("device", s, x, y) and max(abs(qx), abs(qy)) < tz.D:
                fine.append("device")
            elif tz.inside("river", s, x, y):
                fine.append("river")
            else:
                fine.append("center_other")
        elif tz.inside("hand", b, x, y):
            fine.append("hand")
        elif tz.inside("corner", b, x, y):
            fine.append("meld")
        else:
            fine.append("seat_other")
    return big, fine


def dora_cells(tz: tf.TableZones, tiles, big) -> dict:
    out = {"n": 0, "center": 0, "dead_wall": 0, "center_or_dead_wall": 0, "dora_search": 0, "dead_wall_and_hand": 0}
    for t, b in zip(tiles, big):
        if t["role"] != "dora":
            continue
        x, y = t["x"], t["y"]
        dw = any(tz.inside("dead_wall", s, x, y) for s in tf.SIDES)
        out["n"] += 1
        out["center"] += b == "center"
        out["dead_wall"] += dw
        out["center_or_dead_wall"] += b == "center" or dw
        out["dora_search"] += tz.inside("dora_search", "bottom", x, y)
        out["dead_wall_and_hand"] += dw and any(tz.inside("hand", s, x, y) for s in tf.SIDES)
    return out


def main() -> None:
    table = tf.ZoneTable.load()
    res = json.loads((WF_DIR / "results" / "wall_frame.json").read_text(encoding="utf-8"))
    sizes = {k: v["size"] for k, v in json.loads(wf.CACHE.read_text(encoding="utf-8")).items()}
    T = wf.truth_tables()
    rows, dora, diff_fine = {}, {}, 0
    for key, r in res["rows"].items():
        if "zones_frame" not in r:
            continue
        geo = r["geo"]
        tiles = wf.truth_tiles(T, geo)
        pts = [(t["x"], t["y"]) for t in tiles]
        e = r["est"]
        if e.get("ok"):
            W, H = sizes[geo if key.startswith("carry/") else key]
            frame = tf.TableFrame(cx=e["c"][0], cy=e["c"][1], theta=e["theta"], u=e["u"], D=e["D"], size=(W, H),
                                  source="device" if e.get("src") == "device" else "wall")
            tz = tf.TableZones(table, frame, W, H)
            big, fine = classify(tz, pts)
            dora[key] = {"set": r["set"], **dora_cells(tz, tiles, big)}
            # 8b-1 의 zone_frame 과 점마다 같은지(로더 확인)
            import numpy as np  # noqa: PLC0415

            ob, of = wf.zone_frame(np.array(pts, float), e)
            diff_fine += sum(a != b for a, b in zip(ob, big)) + sum(a != b for a, b in zip(of, fine))
        else:
            big, fine = ["none"] * len(tiles), ["none"] * len(tiles)
        rows[key] = {"set": r["set"], "geo": geo, "est": e, "zones_frame": wf.score(tiles, big, fine), "zones_saved": r.get("zones_saved")}
    summ = wf.summarize(rows)
    old = res["summary"]
    keys = ("photos", "right", "wrong", "photos_wrong", "dora_center", "dora_n", "hand", "meld", "river", "seatrule", "hand_band", "meld_corner", "river_box")
    table_rows = []
    for st, s in summ.items():
        if "zones_frame" not in s:
            continue
        new, was = s["zones_frame"], old[st]["zones_frame"]
        same = all(new[k] == was[k] for k in keys)
        ds = [d for d in dora.values() if d["set"] == st]
        dsum = {k: sum(d[k] for d in ds) for k in ("n", "center", "dead_wall", "center_or_dead_wall", "dora_search", "dead_wall_and_hand")}
        saved = old[st].get("zones_saved", {})
        table_rows.append({"set": st, "same_as_8b1": same, "new": {k: new[k] for k in keys}, "old_wrong": was["wrong"],
                           "dora": dsum, "dora_saved_center": [saved.get("dora_center"), saved.get("dora_n")]})
        print(f"{st:12s} 틀린 {new['wrong']:3d}({new['photos_wrong']}) 제 구역 {new['right']}/{new['right'] + new['wrong']} · 8b-1 {was['wrong']} "
              f"{'같음' if same else '다름!'} · 표시패 가운데 {dsum['center']}/{dsum['n']} → 가운데∪왕패 칸 {dsum['center_or_dead_wall']}/{dsum['n']}"
              f"(왕패 칸 {dsum['dead_wall']}, 그중 손패 띠와 겹침 {dsum['dead_wall_and_hand']}, 탐색 칸 {dsum['dora_search']}) · 저장 격자 가운데 {saved.get('dora_center')}/{saved.get('dora_n')}")
    print("점마다 8b-1 zone_frame 과 다른 판정(큰 칸 + 세부):", diff_fine)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"zones": str(tf.ZONES), "wall_frame": str(WF_DIR / "results" / "wall_frame.json"), "point_diffs": diff_fine,
                               "sets": table_rows, "dora_per_photo": dora}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
