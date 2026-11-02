"""펠트 판독의 믿을 만함 검사를 개발 자료로 본다(2026-11-02, API 없음). 삼각대 사진은 여기서 안 본다. dart_felt.json·robust.json(derived) 을 읽는다.
맞음 = 라벨 대비 최악 오차 1% 이하, 틀림 = 패 폭(2.2%) 초과. 사이는 세지 않는다.
  python -X utf8 experiments/zone_points/felt_gate.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labels import DROP_SEGS, SAME_AS, moved  # noqa: E402
from propose import DATA  # noqa: E402

CHECKS = [("span", ">=", 0.25), ("device", ">=", 0.25), ("edge", "<=", 0.75), ("outside", "<=", 0.05), ("inside", ">=", 0.30), ("off", "<=", 0.20), ("ratio", "<=", 2.2)]


def err(d: dict, truth: list, vis: list, size: list) -> float:
    W, H = size
    e = (np.array(d["felt"]) - np.array(truth)) * [1.0, H / W]
    m = np.hypot(e[:, 0], e[:, 1])
    return float(m[np.array(vis[:4]) > 0].max())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    dart = json.loads((DATA / "dart_felt.json").read_text(encoding="utf-8"))
    derived = json.loads((DATA / "robust.json").read_text(encoding="utf-8"))["derived"]
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    sg = json.loads((DATA / "segments.json").read_text(encoding="utf-8"))
    segs = {s["id"]: s for s in sg["segs"]}
    extra = json.loads((DATA / "review_lists.json").read_text(encoding="utf-8"))
    items = {n: SAME_AS.get(v, v) for n, v in sg["items"].items()}
    items.update({n: SAME_AS.get(int(v), int(v)) for n, v in extra["rescue"].items()})
    items["20261031_171245"] = 14

    cases = []  # (원천, 이름, 판독, 오차)
    bad_seg, none_seg = [], []
    for n, r in rows.items():
        d = dart[n]
        if r["kind"] == "photo":
            cases.append(("사진", n, d, err(d, labels[n]["felt"], labels[n]["vis"], r["size"]) if d else None))
            continue
        sid = items.get(n)
        if sid is None:
            none_seg.append((n, d))
        elif sid in DROP_SEGS:
            bad_seg.append((n, d))
        elif not moved(n, rows, sid):
            f = labels[n]["felt"] if n in labels else segs[sid]["felt"]
            v = labels[n]["vis"] if n in labels else [2] * 4
            cases.append(("프레임", n, d, err(d, f, v, r["size"]) if d else None))
    for k, part in derived.items():
        if k == "원본":
            continue
        for n, d in part.items():
            cases.append((k, n, d, err(d, labels[n]["felt"], labels[n]["vis"], labels[n]["size"]) if d else None))

    good = [c for c in cases if c[2] and c[3] <= 0.01]
    wrong = [c for c in cases if c[2] and c[3] > 0.022]
    print(f"읽은 판독: 맞음 {len(good)}, 틀림 {len(wrong)}, 못 찾음 {sum(1 for c in cases if not c[2])}")
    print("\n값 분포 p1/p10/p50/p90/p99")
    for key, _, _ in CHECKS:
        g = np.array([c[2][key] for c in good])
        w = np.array([c[2][key] for c in wrong]) if wrong else np.array([np.nan])
        print(f" {key:8s} 맞음 {np.round(np.percentile(g, [1, 10, 50, 90, 99]), 2).tolist()}  틀림 {np.round(np.percentile(w, [1, 10, 50, 90, 99]), 2).tolist()}")
    print("\n검사 하나씩 뺐을 때: 맞음 통과 / 틀림 통과")
    def passes(d, skip=None, over=None):
        for key, op, th in CHECKS:
            if key == skip:
                continue
            t = over[1] if over and over[0] == key else th
            if (op == ">=" and d[key] < t) or (op == "<=" and d[key] > t):
                return False
        return True
    print(f" 전부: {sum(passes(c[2]) for c in good)}/{len(good)} / {sum(passes(c[2]) for c in wrong)}/{len(wrong)}")
    for key, _, _ in CHECKS:
        print(f" {key} 뺌: {sum(passes(c[2], skip=key) for c in good)} / {sum(passes(c[2], skip=key) for c in wrong)}")
    print("\n문턱 흔들기: 맞음 통과 / 틀림 통과")
    for key, vals in (("outside", (0.05, 0.08, 0.12, 0.18, 0.25)), ("inside", (0.2, 0.3, 0.4, 0.5)), ("device", (0.1, 0.15, 0.2, 0.25, 0.3, 0.4)), ("span", (0.15, 0.25, 0.4)), ("edge", (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6))):
        print(f" {key}: " + "  ".join(f"{v}:{sum(passes(c[2], over=(key, v)) for c in good)}/{sum(passes(c[2], over=(key, v)) for c in wrong)}" for v in vals))

    print("\n원천별: 전체, 못 찾음, 통과, 통과 중 1% 넘음, 2.2% 넘음, 통과분 오차 중앙/최대(%)")
    for src in ["사진", "프레임", *[k for k in derived if k != "원본"]]:
        cs = [c for c in cases if c[0] == src]
        ok = [c for c in cs if c[2] and passes(c[2])]
        e = np.array([c[3] for c in ok]) if ok else np.array([np.nan])
        print(f" {src}: {len(cs)}, {sum(1 for c in cs if not c[2])}, {len(ok)}, {int((e > 0.01).sum())}, {int((e > 0.022).sum())}, {np.median(e) * 100:.2f}/{e.max() * 100:.2f}")
    still = sorted(((c[0], c[1][-12:], round(c[3] * 100, 1), {k: round(c[2][k], 2) for k, _, _ in CHECKS}) for c in wrong if passes(c[2])), key=lambda t: -t[2])
    print("\n틀린 채 통과 앞 25:", *still[:25], sep="\n ")
    if bad_seg:
        got = [d for _, d in bad_seg if d and passes(d, skip="edge")]
        print("\n뺀 구간 기기 바깥 띠 값", sorted(round(d["edge"], 2) for d in got))
    print(f"\n뺀 구간 {len(bad_seg)}장 통과 {sum(1 for _, d in bad_seg if d and passes(d))}: {[n for n, d in bad_seg if d and passes(d)][:10]}")
    print(f"구간 밖 {len(none_seg)}장 통과 {sum(1 for _, d in none_seg if d and passes(d))}, 못 찾음 {sum(1 for _, d in none_seg if not d)}")


if __name__ == "__main__":
    main()
