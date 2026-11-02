"""사진 좌표 고정 격자 대 펠트 좌표 틀(2026-11-02, API 없음). 패 상자 가운데를 라벨 펠트로 나눠 강(d < 0.27)·바깥(d > 0.30)으로 가른 뒤, 강은 가운데 칸 안, 바깥은 칸 밖이어야 맞는 것으로 친다.
설치 하나 빼기: 나머지 설치로 값을 정하고 뺀 설치에서 잰다.
  python -X utf8 experiments/zone_points/fixed_grid.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones as z  # noqa: E402
from propose import DATA  # noqa: E402
from zone_bounds import seat_coords, side_of  # noqa: E402


def load_rows() -> list[dict]:
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    boxes = json.loads((DATA.parent / "det" / "boxes_final.json").read_text(encoding="utf-8"))
    rows = []
    for n, b in boxes.items():
        if n not in labels:
            continue
        r = labels[n]
        W, H = r["size"]
        inv = np.linalg.inv(z.to_image(r["felt"]))
        for x, y, w, h in b["boxes"]:
            px, py = (x + w / 2) / W, (y + h / 2) / H
            c = z.project(inv, [[px, py]])[0]
            side = side_of(*c)
            _, d = seat_coords(c[0], c[1], side)
            kind = "river" if d < 0.27 else "outer" if d > 0.30 else None
            if kind:
                rows.append(dict(photo=n, setup=r["setup"], side=side, kind=kind, x=px * 1000, y=py * 1000, d=float(d)))
    return rows


def wrong(g: dict, t: dict) -> bool:
    inside = g["x1"] < t["x"] < g["x2"] and g["y1"] < t["y"] < g["y2"]
    return inside != (t["kind"] == "river")


def best_line(rows: list[dict], side: str, axis: str, inner_sign: int) -> int:
    """그 변 패만으로 선 하나: 강 패가 선 안쪽, 바깥 패가 선 바깥쪽이 가장 많이 맞는 값(같으면 범위 가운데)."""
    sel = [t for t in rows if t["side"] == side]
    vals = np.arange(50, 951, 5)
    errs = []
    for v in vals:
        e = 0
        for t in sel:
            inside = (t[axis] - v) * inner_sign > 0
            e += inside != (t["kind"] == "river")
        errs.append(e)
    errs = np.array(errs)
    return int(np.median(vals[errs == errs.min()]))


def fit_fixed(rows: list[dict]) -> dict:
    return dict(x1=best_line(rows, "left", "x", 1), x2=best_line(rows, "right", "x", -1), y1=best_line(rows, "top", "y", 1), y2=best_line(rows, "bottom", "y", -1))


def score(rows: list[dict], grid_of_photo) -> tuple[int, int, int, int]:
    photos = sorted({t["photo"] for t in rows})
    bad_photos = 0
    bad = 0
    for p in photos:
        e = sum(wrong(grid_of_photo(p), t) for t in rows if t["photo"] == p)
        bad += e
        bad_photos += e > 0
    return bad, len(rows), bad_photos, len(photos)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = load_rows()
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    setups = sorted({t["setup"] for t in rows})
    print("패", len(rows), "설치", setups)
    # 1. 전부로 맞춘 고정 격자: 가장 유리한 값
    g = fit_fixed(rows)
    print("\n[사진 좌표 고정 격자, 전부로 맞춤(가장 유리)]", g, "틀린 패 %d/%d, 틀린 사진 %d/%d" % score(rows, lambda p: g))
    print(" 기본 격자 280,745,173,713:", "틀린 패 %d/%d, 틀린 사진 %d/%d" % score(rows, lambda p: z.INITIAL))
    # 2. 설치 하나 빼기
    print("\n[설치 하나 빼기] 사진 좌표 고정 / 펠트 좌표(경계 = 나머지 설치 강 끝 최대와 바깥 시작 최소의 가운데)")
    tot = np.zeros(8, int)
    for s in setups:
        tr = [t for t in rows if t["setup"] != s]
        te = [t for t in rows if t["setup"] == s]
        gf = fit_fixed(tr)
        a = score(te, lambda p: gf)
        rv = max(t["d"] for t in tr if t["kind"] == "river")
        ou = min(t["d"] for t in tr if t["kind"] == "outer")
        reach = (rv + ou) / 2
        old = z.RIVER
        z.RIVER = reach
        cache = {p: z.grid_of(labels[p]["felt"]) for p in {t["photo"] for t in te}}
        b = score(te, lambda p: cache[p])
        z.RIVER = old
        tot += np.array([*a, *b])
        print(f" {s}: 고정 {gf['x1']},{gf['x2']},{gf['y1']},{gf['y2']} 틀린 패 {a[0]}/{a[1]} 사진 {a[2]}/{a[3]} | 펠트 {reach:.3f} 틀린 패 {b[0]}/{b[1]} 사진 {b[2]}/{b[3]}")
    print(" 합계: 고정 틀린 패 %d/%d 사진 %d/%d | 펠트 틀린 패 %d/%d 사진 %d/%d" % tuple(tot))
    # 3. 설치마다 그을 수 있는 선 범위
    print("\n[설치마다 틀린 패 0 으로 그을 수 있는 선 범위(0~1000)] 왼쪽 x1 / 오른쪽 x2 / 위 y1 / 아래 y2")
    for s in setups:
        cells = []
        for side, axis, sign in (("left", "x", 1), ("right", "x", -1), ("top", "y", 1), ("bottom", "y", -1)):
            te = [t for t in rows if t["setup"] == s and t["side"] == side]
            rv = [t[axis] for t in te if t["kind"] == "river"]
            ou = [t[axis] for t in te if t["kind"] == "outer"]
            if sign > 0:
                lo, hi = max(ou) if ou else 0, min(rv) if rv else 1000
            else:
                lo, hi = max(rv) if rv else 0, min(ou) if ou else 1000
            cells.append(f"{lo:4.0f}~{hi:4.0f}{'' if lo < hi else ' 불가'}")
        print(f" {s:4s} " + " / ".join(cells))


if __name__ == "__main__":
    main()
