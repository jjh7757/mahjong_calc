"""(11-25, 설계서 8-14 (가)) 강 · 울기 영역을 버림 기록기 덤프에서 — 기본 길 모드(반장 설정에 녹화 틀 frame 이 없음)의 판별 설정 river · meld.

  python -X utf8 experiments/paifu_frames/dump_regions.py make --run <실행 폴더> [--games g1,g2,…] --out <out.json>

관측 = 그 반장 모든 판의 덤프(<실행>/<판>/overlay_dump_c2x.json)에서 판 구간(def t_start ~ t_reveal — t_start 가 없는 판은 t_from) 안 프레임의 패 가운데
  역할 r 이 강(river) / 울기(meld)이고 자리가 그 자리인 것.
  - 덤프 상자 b = [x, y, w, h] 화면 비율, (x, y) = 왼쪽 위(replay_recorder.dart → discard_recorder.sightingsOf 가 중심을 x + w/2 로 셈 ·
    11-25 프레임 한 장에 그려 확인 — results/_setup_dev/f_box_check.jpg). 헤드 녹화 원본(1496²) 좌표 = 비율 × 1496.
  - 울기 · 패산의 자리는 덤프의 s. **강 패의 s 는 늘 "center"** 라(덤프가 자리를 안 적음) 자리는 버림 기록기와 같은 규칙으로 붙인다:
    리치봉 구역 중심에서 본 바람개비 띠(lib/paifu/discard_recorder.dart assignSide · sightingsOf · deviceShareOfSticksZone 0.88 을 옮김).
    띠에 안 드는 강 패는 관측에서 뺌. (명세는 "자리가 그 자리인 것" — 덤프에 강 자리가 없어 기록기 규칙을 씀. 재기 전에 정함.)
상자 = 관측 상자들의 가장자리에서 왼 · 위는 P_LO 백분위, 오른 · 아래는 P_HI 백분위 + 여유(관측 패 짧은 변 중앙값의 절반), 그림 안으로 자름.
관측이 MIN_OBS 개에 못 미치는 자리는 격자로: 강 = 리치봉 구역의 그 자리 쪽 변부터 격자 선까지 · 옆으로 가운데 칸 폭의 LAST_ZONE_BAND
  (lib/table/grid_zones.dart lastZone 의 가운데 · 반폭 셈), 울기 = cornerCell(side).
리치봉 값이 다른 판이 섞인 반장은 값이 같은 판끼리 묶어 따로 낸다(리치봉 = setup/felt_grid.json 의 그 판 used, 없으면 덤프 grid.sticks).
격자(x1 · x2 · y1 · y2) = setup/felt_out.json 의 그 판 헤드 녹화 판독(<접두사><시각>|head) grid, 없으면 덤프 grid — 묶음 안 첫 판 값.
위 수(1 · 99 백분위 · 반 장 · 30개 · 0.6)는 설계서 8-14 가 재기 전에 정한 값 — 재 본 뒤에 고치지 않는다.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HEAD = 1496                 # 헤드 녹화 원본 한 변(handtrack/htcommon.py 머리말)
P_LO, P_HI = 1, 99          # 설계서 8-14 (가)
MARGIN_SHARE = 0.5          # 여유 = 관측 패 짧은 변 중앙값 × 이것
MIN_OBS = 30                # 이보다 적으면 격자
LAST_ZONE_BAND = 0.6        # lib/table/grid_zones.dart lastZoneBand
DEVICE_SHARE = 0.88         # lib/paifu/discard_recorder.dart deviceShareOfSticksZone
SIDES = ["bottom", "right", "top", "left"]
KST = timezone(timedelta(hours=9))
DUMP = "overlay_dump_c2x.json"


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(json.dumps(o, ensure_ascii=False, indent=1).encode("utf-8"))


# ---- 버림 기록기의 자리 붙이기(discard_recorder.dart 를 그대로 옮김)
def to_seat_frame(side: str, dx: float, dy: float) -> tuple:
    return {"bottom": (dx, dy), "right": (-dy, dx), "top": (-dx, -dy), "left": (dy, -dx)}[side]


def assign_side(dx: float, dy: float, hd: float):
    best, best_over, best_v = None, float("inf"), float("inf")
    for s in SIDES:
        u, v = to_seat_frame(s, dx, dy)
        if v < hd * 0.8 or v > hd * 2.6 or u < -hd * 1.3 or u > hd * 1.7:
            continue
        over = max(0.0, abs(u) - hd) if u < 0 else max(0.0, u - hd * 1.05)
        if over < best_over or (over == best_over and v < best_v):
            best_over, best_v, best = over, v, s
    return best


def river_side(b: list, sticks: list, aspect: float = 1.0):
    """b = [x, y, w, h] 비율, sticks = [ymin, xmin, ymax, xmax] 1000분율(앱 GridZones.sticks) — sightingsOf 와 같은 셈."""
    zy0, zx0, zy1, zx1 = [v / 1000 for v in sticks]
    cx, cy = (zx0 + zx1) / 2, (zy0 + zy1) / 2
    hd = ((zx1 - zx0) * aspect + (zy1 - zy0)) / 4 * DEVICE_SHARE
    x, y, w, h = b
    return assign_side((x + w / 2 - cx) * aspect, y + h / 2 - cy, hd)


def to_ms(date: str, t: str) -> int:
    d = datetime.fromisoformat(f"{date}T{t}")
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return int(round(d.timestamp() * 1000))


def frame_ms(f: dict) -> int:
    d = datetime.fromisoformat(f.get("tick") or f["at"])
    if d.tzinfo is None:
        d = d.replace(tzinfo=KST)
    return int(round(d.timestamp() * 1000))


def obs_of(dump_f: Path, sticks: list) -> dict:
    """덤프 한 판 → 관측 목록. 판 구간 = def t_start(없으면 t_from) ~ t_reveal(없으면 t_to)."""
    d = jl(dump_f)
    df = d.get("def") or {}
    fr = d["frames"]
    date = (fr[0].get("tick") or fr[0]["at"])[:10]
    t0_key = "t_start" if df.get("t_start") else "t_from"
    t1_key = "t_reveal" if df.get("t_reveal") else "t_to"
    t0, t1 = to_ms(date, df[t0_key]), to_ms(date, df[t1_key])
    out, n_fr = [], 0
    for f in fr:
        ms = frame_ms(f)
        if not (t0 <= ms <= t1):
            continue
        n_fr += 1
        asp = f["w"] / f["h"]
        for t in f["tiles"]:
            r = t.get("r")
            x, y, w, h = t["b"]
            s = river_side(t["b"], sticks, asp) if r == "river" else t.get("s")
            out.append({"r": r, "s": s, "s_dump": t.get("s"), "ms": ms,
                        "box": [x * HEAD, y * HEAD, (x + w) * HEAD, (y + h) * HEAD], "short": min(w, h) * HEAD})
    return {"obs": out, "frames": n_fr, "frames_all": len(fr), "span": [df[t0_key], df[t1_key]], "span_keys": [t0_key, t1_key], "grid": d.get("grid")}


def grid_box(kind: str, side: str, g: dict) -> list:
    """격자 대신 값(1000분율 → 원본 px [x0, y0, x1, y1]). g = {x1, x2, y1, y2, sticks [ymin, xmin, ymax, xmax]}."""
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    sy0, sx0, sy1, sx1 = g["sticks"]
    if kind == "river":
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        hw, hh = round((x2 - x1) * LAST_ZONE_BAND / 2), round((y2 - y1) * LAST_ZONE_BAND / 2)
        nb = {"bottom": (sy1, cx - hw, y2, cx + hw), "top": (y1, cx - hw, sy0, cx + hw),
              "left": (cy - hh, x1, cy + hh, sx0), "right": (cy - hh, sx1, cy + hh, x2)}[side]
    else:   # cornerCell
        nb = {"bottom": (y2, x2, 1000, 1000), "right": (0, x2, y1, 1000), "top": (0, 0, y1, x1), "left": (y2, 0, 1000, x1)}[side]
    ymin, xmin, ymax, xmax = nb
    return [round(xmin * HEAD / 1000), round(ymin * HEAD / 1000), round(xmax * HEAD / 1000), round(ymax * HEAD / 1000)]


def obs_box(obs: list) -> tuple:
    b = np.array([o["box"] for o in obs], float)
    m = MARGIN_SHARE * float(np.median([o["short"] for o in obs]))
    box = [np.percentile(b[:, 0], P_LO) - m, np.percentile(b[:, 1], P_LO) - m, np.percentile(b[:, 2], P_HI) + m, np.percentile(b[:, 3], P_HI) + m]
    box = [int(round(min(max(v, 0), HEAD))) for v in box]
    return box, round(m, 1)


def felt_grid_of(run: Path, g: str):
    """setup/felt_out.json 의 그 판 헤드 녹화 판독 grid(판 id 의 시각 부분으로 찾음), 없으면 None."""
    f = run / "setup" / "felt_out.json"
    if not f.exists():
        return None
    tail = g.split("_", 1)[1] if "_" in g else g
    for k, v in jl(f).get("jobs", {}).items():
        if k.endswith("|head") and k.split("|")[0].split("_", 1)[-1] == tail and v.get("grid"):
            return v["grid"], f"{(run / 'setup' / 'felt_out.json').as_posix()} jobs[{k}].grid"
    return None


def sticks_of(run: Path, g: str, dump_grid: dict) -> tuple:
    f = run / "setup" / "felt_grid.json"
    if f.exists():
        r = (jl(f).get("rounds") or {}).get(g) or {}
        if r.get("used"):
            return [int(v) for v in str(r["used"]).split(",")], "setup/felt_grid.json used"
    return list(dump_grid["sticks"]), "덤프 grid.sticks"


def make(run: Path, games: list) -> dict:
    per, groups = {}, {}
    for g in games:
        f = run / g / DUMP
        if not f.exists():
            raise SystemExit(f"{g}: 덤프 {f} 없음")
        dg = jl(f)["grid"]
        st, st_from = sticks_of(run, g, dg)
        per[g] = {"sticks": st, "sticks_from": st_from, **obs_of(f, st)}
        groups.setdefault(tuple(st), []).append(g)
    out = {"_note": "dump_regions.py make — 설계서 8-14 (가): 강 · 울기 영역을 버림 기록기 덤프에서(자리마다 상자 하나, 리치봉 값이 같은 판끼리). 좌표 = 헤드 녹화 원본 [x0, y0, x1, y1]",
           "rule": {"P_LO": P_LO, "P_HI": P_HI, "MARGIN_SHARE": MARGIN_SHARE, "MIN_OBS": MIN_OBS, "LAST_ZONE_BAND": LAST_ZONE_BAND, "DEVICE_SHARE": DEVICE_SHARE,
                    "box_format": "덤프 b = [x, y, w, h] 비율 · (x, y) 왼쪽 위", "river_side": "기록기 assignSide(리치봉 구역 중심 바람개비 띠) — 덤프의 강 s 는 center"},
           "run": run.as_posix(), "games": {}, "groups": []}
    for g, v in per.items():
        o = v["obs"]
        out["games"][g] = {"sticks": v["sticks"], "sticks_from": v["sticks_from"], "span": v["span"], "span_keys": v["span_keys"], "frames": v["frames"],
                           "frames_all": v["frames_all"], "river_unassigned": sum(1 for x in o if x["r"] == "river" and x["s"] is None),
                           "n": {f"{r}.{s}": sum(1 for x in o if x["r"] == r and x["s"] == s) for r in ("river", "meld", "wall") for s in SIDES}}
    for st, gs in groups.items():
        fg = felt_grid_of(run, gs[0])
        if fg:
            grid, grid_from = dict(fg[0]), fg[1]
        else:
            grid, grid_from = dict(per[gs[0]]["grid"]), f"{(run / gs[0] / DUMP).as_posix()} grid"
        grid["sticks"] = list(st)
        obs = [x for g in gs for x in per[g]["obs"]]
        sides = {}
        for s in SIDES:
            sides[s] = {}
            for kind in ("river", "meld"):
                o = [x for x in obs if x["r"] == kind and x["s"] == s]
                if len(o) >= MIN_OBS:
                    box, m = obs_box(o)
                    sides[s][kind] = {"box": box, "from": "관측", "n": len(o), "margin": m}
                else:
                    sides[s][kind] = {"box": grid_box(kind, s, grid), "from": "격자", "n": len(o),
                                      "grid_rule": "강 = 리치봉 구역 그 자리 쪽 변 ~ 격자 선 · 옆 가운데 칸 폭 × 0.6" if kind == "river" else "울기 = cornerCell(side)"}
        out["groups"].append({"sticks": list(st), "games": gs, "grid": {k: grid[k] for k in ("x1", "x2", "y1", "y2", "sticks")}, "grid_from": grid_from, "sides": sides})
    return out


def regions_for(res: dict, g: str, side: str) -> dict:
    """make 결과에서 판 g · 손패 주인 자리 side 의 river · meld 상자."""
    grp = next(x for x in res["groups"] if g in x["games"])
    return {k: list(grp["sides"][side][k]["box"]) for k in ("river", "meld")}


def source_of(res: dict, g: str, side: str, kind: str) -> dict:
    """판 g · 자리 side 의 kind 상자 출처(관측 / 격자 · 관측 수 · 묶음 판 수)."""
    grp = next(x for x in res["groups"] if g in x["games"])
    v = grp["sides"][side][kind]
    return {"from": v["from"], "n": v["n"], "group_games": len(grp["games"]), "sticks": grp["sticks"]}


def source_lines(res: dict) -> list:
    """report.md 용 — 자리마다 강 · 울기 상자 출처."""
    L = []
    for grp in res["groups"]:
        L.append(f"- 리치봉 {grp['sticks']} 판 {len(grp['games'])}: " + " · ".join(
            f"{s} 강 {v['river']['box']}({v['river']['from']} {v['river']['n']}) 울기 {v['meld']['box']}({v['meld']['from']} {v['meld']['n']})"
            for s, v in grp["sides"].items()))
    return L


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("make")
    p.add_argument("--run", required=True)
    p.add_argument("--games", help="쉼표로(없으면 실행 설정 hanchan.json 의 games)")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    run = Path(a.run).resolve()
    games = a.games.split(",") if a.games else jl(run / "hanchan.json")["games"]
    res = make(run, games)
    wj(a.out, res)
    for ln in source_lines(res):
        print(ln)


if __name__ == "__main__":
    main()
