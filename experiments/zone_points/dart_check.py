"""앱 felt_grid.dart 결과를 라벨·Python 값과 대조한다(2026-11-02, API 없음). tool/felt_grid_check_test.dart 다음에.
오차 = 펠트 모서리가 라벨에서 벗어난 거리 / 사진 폭(%), 사진 밖 점 포함, 장별 최악. 프레임은 구간에 든 것 전부(뺀 구간·움직인 프레임 포함, 뺀 구간은 따로).
  python -I experiments/zone_points/dart_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labels import DROP_SEGS, SAME_AS, moved  # noqa: E402
from propose import DATA  # noqa: E402
from zones import grid_of  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    dart = json.loads((DATA / "dart_felt.json").read_text(encoding="utf-8"))
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    sg = json.loads((DATA / "segments.json").read_text(encoding="utf-8"))
    segs = {s["id"]: s for s in sg["segs"]}
    extra = json.loads((DATA / "review_lists.json").read_text(encoding="utf-8"))
    items = {n: SAME_AS.get(v, v) for n, v in sg["items"].items()}
    items.update({n: SAME_AS.get(int(v), int(v)) for n, v in extra["rescue"].items()})
    items["20261031_171245"] = 14

    def felt_err(d, truth, size):
        W, H = size
        e = (np.array(d["felt"]) - np.array(truth)) * [1.0, H / W]
        return float(np.hypot(e[:, 0], e[:, 1]).max())

    print("[사진] Dart 격자 − Python 격자(zones.py single), 라벨 대비 최악 오차")
    diffs = []
    for n, r in rows.items():
        if r["kind"] != "photo":
            continue
        d = dart[n]
        truth = labels[n]["felt"]
        g = d and d["grid"]
        p = grid_of(r["felt"]) if r["felt"] else None
        dg = max(abs(g[k] - p[k]) for k in ("x1", "x2", "y1", "y2")) if g and p else None
        diffs.append(dg if dg is not None else 999)
        print(f" {n[-6:]} ok={d and d['ok']} span={d and round(d['span'], 2)} dev={d and round(d['device'], 2)} 오차 {felt_err(d, truth, r['size']) * 100:.2f}% 격자차 {dg}")
    print(" 격자 차이 최대", max(diffs), "중앙", float(np.median(diffs)))

    good, bad, none_table = [], [], []
    for n, r in rows.items():
        if r["kind"] != "frame":
            continue
        sid = items.get(n)
        d = dart[n]
        if sid is None:
            none_table.append(d)
            continue
        if sid in DROP_SEGS:
            bad.append((n, d))
            continue
        if moved(n, rows, sid):
            continue
        truth = labels[n]["felt"] if n in labels else segs[sid]["felt"]
        good.append((n, d, felt_err(d, truth, r["size"]) if d else None))
    ok = [g for g in good if g[1] and g[1]["ok"]]
    errs = np.array([g[2] for g in ok])
    print(f"\n[구간 안 프레임] {len(good)}장, 통과 {len(ok)}({len(ok) / len(good) * 100:.0f}%), 통과분 오차 중앙 {np.median(errs) * 100:.2f}% p90 {np.percentile(errs, 90) * 100:.2f}% 최대 {errs.max() * 100:.2f}%, 1% 넘음 {(errs > 0.01).sum()}, 2.2%(패 폭) 넘음 {(errs > 0.022).sum()}")
    print(" 2.2% 넘은 통과 프레임", [(g[0], round(g[2] * 100, 1), round(g[1]["span"], 2), round(g[1]["device"], 2)) for g in sorted(ok, key=lambda t: -t[2]) if g[2] > 0.022][:15])
    for th in (0.15, 0.25, 0.35, 0.45):
        k = [g for g in good if g[1] and g[1]["span"] >= th and g[1]["device"] >= 0.25]
        e = np.array([g[2] for g in k])
        print(f" span≥{th}: 통과 {len(k)}/{len(good)}, 2.2% 넘음 {(e > 0.022).sum()}, 최대 {e.max() * 100:.1f}%")
    for th in (0.1, 0.25, 0.4, 0.55):
        k = [g for g in good if g[1] and g[1]["span"] >= 0.25 and g[1]["device"] >= th]
        e = np.array([g[2] for g in k])
        print(f" 기기≥{th}: 통과 {len(k)}/{len(good)}, 2.2% 넘음 {(e > 0.022).sum()}, 최대 {e.max() * 100:.1f}%")
    dev = np.array([g[1]["device"] for g in good if g[1]])
    print(" 기기 비율 분포 p1/p10/p50", np.round(np.percentile(dev, [1, 10, 50]), 2).tolist())
    print(f"\n[뺀 구간 s2·s6·s7] {len(bad)}장, 통과 {sum(1 for _, d in bad if d and d['ok'])}", [n for n, d in bad if d and d["ok"]][:12])
    print(f"[구간 밖 프레임(이동 중·가림)] {len(none_table)}장, 통과 {sum(1 for d in none_table if d and d['ok'])}, 펠트 없음 {sum(1 for d in none_table if not d)}")


if __name__ == "__main__":
    main()
