"""손이 안 가린 프레임 중 줄 장수가 바뀌는 순간만 골라 그림으로 LLM 에 묻기(2026-11-16, 사용자 "손패 갯수가 1개씩 변경되는 그림만 보고,
손으로 가린 경우는 제외하고, llm 에게 판단을 맡기기").

깨끗한 프레임 = 줄 덩어리 어느 끝에도 손·소매가 닿지 않고 띠 안에 가림이 없는 프레임(pixtrack v6 마스크).
고르는 것: 차례의 첫 깨끗한 프레임 + 장수(덩어리 장수 합, 반올림)가 앞 깨끗한 프레임과 달라진 프레임 + 마지막 깨끗한 프레임.
그림마다 시각·장수를 적고, 덩어리 위에 왼쪽부터 칸 번호를 단다(덩어리 폭 ÷ 한 장 폭으로 나눈 자리).

  python -X utf8 keyframes.py make <판 id…> --out <폴더>   # 차례마다 T##.jpg + index.json(정답은 truth.json 따로)
"""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beforeafter as ba  # noqa: E402
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402

SCALE = 1.0  # 1496 녹화 화소 그대로(패 약 40px)


def clean(f: dict) -> bool:
    # 처음엔 "띠 안에 손이 아예 없음" 이었으나 장수가 바뀌는 순간엔 늘 손이 띠에 있어 20차례 중 16차례가 앞뒤 13장 두 장뿐 → 줄 덩어리 끝에 손이 안 닿음
    return bool(f["runs"]) and all(not r["hl"] and not r["hr"] for r in f["runs"] if r["n"] >= 0.5)


def count(f: dict) -> int:
    return int(sum(round(r["n"]) for r in f["runs"] if r["n"] >= 0.5))


def draw(R: pt.Row, f: dict, label: str) -> np.ndarray:
    v = R.view(f["ms"]).copy()
    k = 0
    for r in [r for r in f["runs"] if r["n"] >= 0.5]:
        n = int(round(r["n"]))
        w = (r["x1"] - r["x0"]) / max(1, n)
        for i in range(n):
            k += 1
            cx = int(r["x0"] + w * (i + 0.5))
            cv2.putText(v, str(k), (cx - 6, max(10, R.y0 - 22)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 0), 1)
    bar = np.full((18, v.shape[1], 3), 30, np.uint8)
    cv2.putText(bar, label, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return np.concatenate([bar, v], 0)


def cmd_make(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    idx, truth = [], {}
    for gid in a.games:
        R = pt.Row(gid)
        rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
        tmap = {t["t"]: t for t in rp["turns"]}
        n_hand = 13
        for tr in ba.turns_from_replay(rp, R.sg):
            if "call" in " ".join(tr["events"]):
                n_hand = 10
            T = pt.truth_of(gid, tmap[tr["t"]])
            if not T["mode"]:
                continue
            frs = [R.frame(ms) for ms in hc.frame_range(tr["ms_before"], tr["ms_after"])]
            cl = [f for f in frs if clean(f)]
            pick, last = [], None
            for f in cl:
                c = count(f)
                if last is None or c != last:
                    pick.append(f)
                    last = c
            if cl and pick[-1] is not cl[-1]:
                pick.append(cl[-1])
            tid = f"T{len(idx) + 1:02d}"
            ims = [draw(R, f, f"{hc.hms(f['ms'])[3:]}  {count(f)}장") for f in pick]
            if ims:
                cv2.imwrite(str(out / f"{tid}.jpg"), cv2.cvtColor(np.concatenate(ims, 0), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
            truth[tid] = T
            idx.append({"id": tid, "game": gid, "t": tr["t"], "N": n_hand, "frames": len(frs), "clean": len(cl), "picked": len(pick),
                        "counts": [count(f) for f in pick]})
            print(tid, gid[:3], tr["t"], "프레임", len(frs), "깨끗", len(cl), "고름", len(pick), [count(f) for f in pick])
    hc.jsave(out / "index.json", idx)
    hc.jsave(out / "truth.json", truth)
    print("그림 합", sum(i["picked"] for i in idx), "장")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("make")
    m.add_argument("games", nargs="+")
    m.add_argument("--out", required=True)
    a = ap.parse_args()
    {"make": cmd_make}[a.cmd](a)


if __name__ == "__main__":
    main()
