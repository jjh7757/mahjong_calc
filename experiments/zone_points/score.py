"""설치 하나 빼기 시험 답의 점 오차를 잰다(2026-11-02, API 없음). kernel/train_pose.py 결과를 kaggle_out/ 에 받은 뒤에.
오차 = 라벨 점까지 거리 / 사진 폭(패 폭은 약 2.2%). vis 2 인 점만. 비교: 더미 = 그 fold 학습 라벨의 좌표 평균, 색 = propose.py 사진별 값.
"모두 1% 안" = 그 사진의 쓰는 점이 전부 1% 안. 색 판독이 못 찾은 장은 분모에 넣고 틀림으로 친다.
  python -I experiments/zone_points/score.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propose import DATA  # noqa: E402

OUT = DATA / "kaggle_out" / "out"
VAL_OF = {"s0": "s1", "s1": "s3", "s3": "s4", "s4": "s5", "s5": "s8", "s8": "s13", "s13": "s14", "s14": "s0", "gal": "s4"}
BCD = {"k25", "k28", "k15", "k26", "k12", "k16"}


def err(pred, r: dict) -> np.ndarray | None:
    """점마다 오차(사진 폭 비율), 안 쓰는 점은 nan."""
    if pred is None:
        return None
    W, H = r["size"]
    t = np.array(r["felt"] + r["device"])
    d = (np.array(pred) - t) * [1.0, H / W]
    e = np.hypot(d[:, 0], d[:, 1])
    e[np.array(r["vis"]) == 0] = np.nan
    return e


def stats(es: list, n: int) -> str:
    good = [e for e in es if e is not None]
    if not good:
        return f"답 0/{n}"
    a = np.stack(good)
    felt, dev = a[:, :4][~np.isnan(a[:, :4])], a[:, 4:][~np.isnan(a[:, 4:])]
    ok = sum(np.nanmax(e) < 0.01 for e in good)
    worst = np.nanmax(a, axis=1)
    return (f"펠트 {np.median(felt) * 100:.2f}/{np.percentile(felt, 90) * 100:.2f}  기기 {np.median(dev) * 100:.2f}/{np.percentile(dev, 90) * 100:.2f}  "
            f"장별 최악 {np.median(worst) * 100:.2f}/{np.percentile(worst, 90) * 100:.2f}/{worst.max() * 100:.2f}  모두 1% 안 {ok}/{n}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    print("칸: 펠트 중앙/p90 · 기기 중앙/p90 · 장별 최악 점 중앙/p90/최대 (사진 폭 %), 패 폭 약 2.2%")
    pool = {"model": [], "dummy": [], "color": []}
    detail = {}
    for fold, val in VAL_OF.items():
        preds = json.loads((OUT / f"preds_{fold}.json").read_text(encoding="utf-8"))
        train = [r for r in labels.values() if r["setup"] not in (fold, val)]
        w = np.stack([np.where((np.array(r["vis"]) > 0)[:, None], np.array(r["felt"] + r["device"]), np.nan) for r in train])
        mean = np.nanmean(w, axis=0)
        names = [n for n, r in labels.items() if r["setup"] == fold]
        m = {n: err(preds[n]["xyn"] if preds.get(n) else None, labels[n]) for n in names}
        d = {n: err(mean, labels[n]) for n in names}
        c = {n: err(rows[n]["felt"] + rows[n]["device"] if rows[n]["felt"] and rows[n]["device"] else None, labels[n]) for n in names}
        conf = [preds[n]["conf"] for n in names if preds.get(n)]
        print(f"\n[{fold}] {len(names)}장, 검증 {val}, 상자 확신 최소 {min(conf):.2f}")
        print(" 모델", stats(list(m.values()), len(names)))
        print(" 더미", stats(list(d.values()), len(names)))
        print(" 색  ", stats(list(c.values()), len(names)))
        if fold == "gal":
            for label, group in (("B·C·D", [n for n in names if n in BCD]), ("A·E", [n for n in names if n not in BCD])):
                print(f" 모델 {label}", stats([m[n] for n in group], len(group)))
        pool["model"] += [(n, e) for n, e in m.items()]
        pool["dummy"] += [(n, e) for n, e in d.items()]
        pool["color"] += [(n, e) for n, e in c.items()]
        detail.update({n: {"setup": fold, "worst": None if e is None else float(np.nanmax(e)), "err": None if e is None else [None if np.isnan(x) else round(float(x), 5) for x in e]} for n, e in m.items()})
    print("\n[전체]")
    for k in ("model", "dummy", "color"):
        print("", k, stats([e for _, e in pool[k]], len(pool[k])))
    (DATA / "score_points.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    worst = sorted(detail.items(), key=lambda t: -(t[1]["worst"] or 9))[:15]
    print("\n가장 나쁜 15장:", [(n, d["setup"], round((d["worst"] or 9) * 100, 2)) for n, d in worst])


if __name__ == "__main__":
    main()
