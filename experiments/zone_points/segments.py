"""매장 사진·프레임을 카메라 설치 구간으로 나누고 구간별 중앙값을 8점 라벨 후보로 만든다(2026-11-02, API 없음). propose.py 다음에.
같은 구간이면 탁자 위치가 같으므로 손이 가린 사진도 다른 프레임 값으로 채운다. 갤러리는 구간 없이 사진 값 그대로.
  python -I experiments/zone_points/segments.py
결과 tile_classifier/data/zone_points/segments.json: segs(구간 번호·시각·장수·felt·device·mad), items(이름 → 구간 번호 또는 null)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[1] / "tile_classifier" / "data" / "zone_points"
NEAR = 0.012  # 사진 폭 대비, 긴 변 1020 에서 약 12px
AGREE = 3  # 네 모서리 중 이만큼 가까우면 같은 위치
CONFIRM = 3  # 이만큼 잇따라 달라야 새 구간


def when(name: str, r: dict) -> str:
    if r["kind"] == "frame":
        return r["at"].replace(":", "")
    return name[9:]


def agree(q: np.ndarray, med: np.ndarray) -> bool:
    return int((np.abs(q - med).max(1) < NEAR).sum()) >= AGREE


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    seq = sorted(((when(n, r), n) for n, r in rows.items() if r["part"] != "gal" and r["felt"]), key=lambda t: t[0])
    segs: list[list[str]] = []
    cur: list[str] = []
    pend: list[str] = []
    q_of = lambda n: np.array(rows[n]["felt"])
    med_of = lambda names: np.median(np.stack([q_of(n) for n in names[-40:]]), 0)
    for _, n in seq:
        if not cur:
            cur = [n]
            continue
        if agree(q_of(n), med_of(cur)):
            cur.append(n)
            pend = []
            continue
        pend.append(n)
        if len(pend) >= CONFIRM and all(agree(q_of(p), med_of(pend)) for p in pend):
            segs.append(cur)
            cur, pend = pend, []
        elif len(pend) > 8:
            pend = pend[-CONFIRM:]  # 움직이는 중인 프레임은 어느 구간에도 안 넣는다
    if cur:
        segs.append(cur)
    out_segs, items = [], {n: None for n in rows if rows[n]["part"] != "gal"}
    for names in segs:
        if len(names) < 3:
            continue
        i = len(out_segs)
        felt = np.stack([q_of(n) for n in names])
        devs = [np.array(rows[n]["device"]) for n in names if rows[n]["device"]]
        dev = np.median(np.stack(devs), 0) if devs else None
        out_segs.append({"id": i, "start": when(names[0], rows[names[0]]), "end": when(names[-1], rows[names[-1]]), "n": len(names),
                         "photos": [n for n in names if rows[n]["kind"] == "photo"],
                         "felt": np.round(np.median(felt, 0), 5).tolist(), "device": None if dev is None else np.round(dev, 5).tolist(),
                         "mad_felt": round(float(np.median(np.abs(felt - np.median(felt, 0)))), 5), "n_device": len(devs), "sample": names[len(names) // 2]})
        for n in names:
            items[n] = i
    (DATA / "segments.json").write_text(json.dumps({"segs": out_segs, "items": items}, ensure_ascii=False, indent=0), encoding="utf-8")
    print("구간", len(out_segs), "구간 안", sum(v is not None for v in items.values()), "구간 밖", sum(v is None for v in items.values()))
    for s in out_segs:
        print(s["id"], s["start"], s["end"], "n", s["n"], "사진", len(s["photos"]), "mad", s["mad_felt"], "기기", s["n_device"])
    print("구간 밖 사진", [n for n, v in items.items() if v is None and rows[n]["kind"] == "photo"])


if __name__ == "__main__":
    main()
