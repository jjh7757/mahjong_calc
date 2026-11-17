"""시험 8판 정답 만들기 — 버림 하나를 한 차례로 묶고 프레임을 뽑는다(2026-11-16 밤, 계획서 3단계 "추가 8").
자동 판정(pixtrack·inplace·Gemini)의 답은 여기 넣지 않는다 — 확인 페이지에 보이면 안 된다.

  python -X utf8 truthprep.py turns     # _work/testtruth_1116/turns.json (차례 목록)
  python -X utf8 truthprep.py frames    # _work/testtruth_1116/frames/<판>/<ms>.jpg (있는 것은 건너뜀)
차례 = 화료자 강이 한 장 늘어난 것 하나. 그 버림이 놓인 손 움직임 구간 + 앞 구간 2개까지(앞 버림 뒤) + 뒤 구간 2개까지(다음 버림 앞).
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import stripview as sv  # noqa: E402
import testrun as tr  # noqa: E402

OUT = hc.WORK / "testtruth_1116"
SCALE, PAD, EDGE_MS, CTX = 1.5, (40, 75), 300, 2
EXTRA = ["r12_131655", "r17_140450",  # 계획서 "추가 10" 의 시험 판(준비되면 들어온다)
         "r13_132644", "r15_134151",  # 11-17 오후: 유국 판 r13(동3국) · r15(남1국)의 텐파이 공개 자리(둘 다 오른쪽)
         "r16_135321", "L16_135321"]  # 11-17 오후: 유국 판 r16(남2국 1본장)의 텐파이 공개 두 자리 — r16 = 오른쪽, L16 = 왼쪽(차례 id 앞 세 글자로 가름)


def build() -> dict:
    games = []
    for gid in tr.GAMES + [g for g in EXTRA if (hc.OUT / g / "river_states.json").exists()]:
        acts = sorted(hc.jload(hc.OUT / gid / "segments.json")["active"], key=lambda a: a["ms0"])
        rs = hc.jload(hc.OUT / gid / "river_states.json")["segments"]
        disc = []  # (강 순서, 구간 위치, 패, 그 구간 앞 울기 장수)
        for p, a in enumerate(acts):
            r = rs.get(str(a["seg"]))
            if not r or "river_count" not in r:
                continue
            x, y = r["river_count"]
            new = [t.get("tile") if isinstance(t, dict) else str(t) for t in (r.get("river_new") or [])]
            side = [bool(t.get("sideways")) if isinstance(t, dict) else False for t in (r.get("river_new") or [])]
            for n, i in enumerate(range(x + 1, y + 1)):
                disc.append({"i": i, "p": p, "tile": new[n] if n < len(new) and y - x == len(new) else None, "meld": r["meld_count"], "same_seg": y - x,
                             "sideways": side[n] if n < len(side) and y - x == len(side) else False})
        turns = []
        used = set()
        seen: dict = {}  # 같은 강 순서가 두 번 나오면(남이 버림패를 가져가 강이 줄었다가 다시 늚) 둘째부터 b, c … 를 붙인다
        for n, d in enumerate(disc):
            seen[d["i"]] = seen.get(d["i"], 0) + 1
            suf = "" if seen[d["i"]] == 1 else "abcdefgh"[seen[d["i"]] - 1]
            p = d["p"]
            pp = disc[n - 1]["p"] if n else -1
            nx = disc[n + 1]["p"] if n + 1 < len(disc) else len(acts)
            order = [(q, "앞") for q in range(max(pp + 1, p - CTX), p)] + [(p, "버림")] + [(q, "뒤") for q in range(p + 1, min(nx, p + 1 + CTX))]
            segs, last = [], 0
            for q, role in order:
                a = acts[q]
                ms = [m for m in hc.frame_range(a["ms0"] - EDGE_MS, a["ms1"] + EDGE_MS) if m > last]
                if not ms:
                    continue
                last = ms[-1]
                used.update(ms)
                segs.append({"seg": a["seg"], "role": role, "t0": hc.hms(ms[0])[3:], "frames": ms})
            turns.append({"id": f"{gid[:3]}_d{d['i']:02d}{suf}", "label": f"{d['i']}{suf}", "repeat": bool(suf), "game": gid, "i": d["i"], "tile": d["tile"], "sideways": d["sideways"], "meld_tiles": d["meld"],
                          "n_calc": 13 - d["meld"][0] if d["meld"][0] % 3 == 0 else None, "same_seg": d["same_seg"],
                          "more_after": nx - (p + 1) > CTX, "more_before": p - (pp + 1) > CTX, "segs": segs})
        # 11-14 반장: 1반장(11:47~12:33)은 연출용이라 정답에서 뺀다(2026-11-17 사용자). n 판은 14:46 뒤 3반장 쪽.
        han = 3 if gid.startswith("n") else (1 if int(gid.split("_")[1][:2]) < 13 else 2)
        games.append({"id": gid, "han": han, "skip": han == 1, "side": hc.config(gid).get("side"), "first_i": disc[0]["i"] if disc else None, "turns": turns, "n_frames": len(used)})
        print(gid, "차례", len(turns), "프레임", len(used))
    return {"games": games, "scale": SCALE}


def render(gid: str, ms: int, cfg: dict) -> None:
    f = OUT / "frames" / gid / f"{ms}.jpg"
    if f.exists():
        return
    v = hc.band_crop(hc.load(ms), sv.wide_band(cfg, *PAD), cfg["side"])
    im = Image.fromarray(v)
    im.resize((round(im.width * SCALE), round(im.height * SCALE)), Image.LANCZOS).save(f, quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["turns", "frames"])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    d = build()
    hc.jsave(OUT / "turns.json", d)
    print("차례 합", sum(len(g["turns"]) for g in d["games"]), "· 프레임 합", sum(g["n_frames"] for g in d["games"]))
    if a.cmd == "frames":
        for g in d["games"]:
            cfg = hc.config(g["id"])
            (OUT / "frames" / g["id"]).mkdir(parents=True, exist_ok=True)
            ms = sorted({m for t in g["turns"] for s in t["segs"] for m in s["frames"]})
            with ThreadPoolExecutor(6) as ex:
                list(ex.map(lambda m: render(g["id"], m, cfg), ms))
            print(g["id"], "프레임", len(ms), "끝")


if __name__ == "__main__":
    main()
