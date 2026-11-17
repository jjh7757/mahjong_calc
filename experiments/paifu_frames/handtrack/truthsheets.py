"""두 번째 읽기(사용자 답을 안 본 판정자)용 프레임 묶음 — truthprep 이 뽑은 프레임을 구간마다 격자 그림으로(2026-11-17, 계획서 "추가 8").

  python -X utf8 truthsheets.py <판 id> [--parts 3]
→ _work/testtruth_1116/second/sheets/<판>/s<구간>_<nn>.jpg  (버림·뒤 구간은 초당 10장, 앞 구간은 초당 5장)
→ _work/testtruth_1116/second/tasks_<판>_<몫>.json            (판정자 한 명 몫: 차례 목록 + 그림 경로. 답·자동 판정은 안 들어간다)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import stripview as sv  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
COLS, ROWS, CELL_W = 2, 8, 860


def sheet(gid: str, mss: list[int], out: Path, head: str) -> None:
    ims = [Image.open(BASE / "frames" / gid / f"{ms}.jpg") for ms in mss]
    w0, h0 = ims[0].size
    ch = round(h0 * CELL_W / w0)
    rows = (len(ims) + COLS - 1) // COLS
    W, H = COLS * CELL_W + (COLS - 1) * 6, 34 + rows * (ch + 4)
    im = Image.new("RGB", (W, H), (20, 20, 20))
    d = ImageDraw.Draw(im)
    d.text((6, 4), head, fill=(255, 255, 255), font=sv.font(20))
    for n, (ms, f) in enumerate(zip(mss, ims)):  # 위 → 아래, 이어서 오른쪽 열
        c, r = n // rows, n % rows
        x, y = c * (CELL_W + 6), 34 + r * (ch + 4)
        im.paste(f.resize((CELL_W, ch), Image.LANCZOS), (x, y))
        d.rectangle([x, y, x + 104, y + 26], fill=(0, 0, 0))
        d.text((x + 4, y + 2), hc.hms(ms)[3:], fill=(255, 255, 0), font=sv.font(19))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=88)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("--parts", type=int, default=3)
    a = ap.parse_args()
    g = next(x for x in hc.jload(BASE / "turns.json")["games"] if x["id"] == a.game)
    # 구간마다 가장 촘촘하게 필요한 간격(버림·뒤 = 1, 앞 = 2)
    step: dict = {}
    frames: dict = {}
    for t in g["turns"]:
        for s in t["segs"]:
            step[s["seg"]] = min(step.get(s["seg"], 2), 2 if s["role"] == "앞" else 1)
            frames.setdefault(s["seg"], set()).update(s["frames"])
    files: dict = {}
    for seg in sorted(frames):
        mss = sorted(frames[seg])[::step[seg]]
        per = COLS * ROWS
        files[seg] = []
        for n in range(0, len(mss), per):
            part = mss[n:n + per]
            f = BASE / "second" / "sheets" / a.game / f"s{seg:02d}_{n // per + 1:02d}.jpg"
            sheet(a.game, part, f, f"{a.game[:3]} 구간 {seg} · {hc.hms(part[0])[3:]}~{hc.hms(part[-1])[3:]} · 초당 {10 // step[seg]}장 · 위→아래, 이어서 오른쪽 열 · 왼쪽 = 그 사람 왼손 쪽")
            files[seg].append(str(f))
    turns = [{"id": t["id"], "label": t.get("label", str(t["i"])), "river_tile": t["tile"], "row_after": t["n_calc"], "repeat": t.get("repeat", False),
              "discards_in_own_seg": t["same_seg"],
              "segs": [{"seg": s["seg"], "role": s["role"], "t0": s["t0"], "sheets": files[s["seg"]],
                        "frames": [[hc.hms(ms)[3:], str(BASE / "frames" / a.game / f"{ms}.jpg")] for ms in sorted(frames[s["seg"]])]} for s in t["segs"]]} for t in g["turns"]]
    n = len(turns)
    size = -(-n // a.parts)
    for k in range(a.parts):
        part = turns[k * size:(k + 1) * size]
        if part:
            hc.jsave(BASE / "second" / f"tasks_{a.game[:3]}_{'ABCDEFGH'[k]}.json", {"game": a.game, "part": "ABCDEFGH"[k], "turns": part})
            print("몫", "ABCDEFGH"[k], [t["label"] for t in part], "그림", len({f for t in part for s in t["segs"] for f in s["sheets"]}))
    print("그림 합", sum(len(v) for v in files.values()))


if __name__ == "__main__":
    main()
