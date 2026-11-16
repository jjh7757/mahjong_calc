"""일발 판정의 "리치 뒤 울기·버림" 을 겹쳐 보기(`ondevice.overlay`)로 — 리치가 잡힌 판마다 다시 돌려 본다(2026-11-16, 사용자 "겹쳐 보기로 바꾸기").

리치 구간 = `replay_rounds.dart` 결과(C)의 리치 시점(봉이 처음 보인 프레임)부터 그 판 첫 화료 사진까지.
  기준 읽기 = 봉이 처음 보인 프레임부터 [BASE_WINDOW]초 안의 프레임(최대 [BASE_READS]장) — 앱은 봉이 처음 보일 때·확정될 때 읽는다.
  끝 읽기   = 화료 사진(captures/<시각>/original.jpg).
판정(앱 `lib/table/call_watch.dart` 와 같은 규칙):
  - 강 상자 수: 끝 − 기준(기준 읽기 중 최대) 이 0~3 이어야 한다(한 바퀴). 음수면 모름.
  - 리치한 자리의 강(가운데 기기에서 본 사분면): 끝 − 기준 이 0 이하.
  - 다른 세 자리 울기: 3장 미만은 0장으로 치고(낱장 헛 검출), 끝 > 기준 이면 울기 → 일발 아님.
  - 자기 자리 울기가 2장 이상 늘면 self_grew(화료 사진에 안깡이 있을 때만 일발을 지움 — merge 쪽).

  python -X utf8 experiments/ondevice/overlay_ippatsu_replay.py <captures 폴더> <out.json> <rounds json>...
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.append(str(ROOT / "android/app/src/main/python"))
import ondevice  # noqa: E402

SIDES = ["bottom", "right", "top", "left"]
BASE_WINDOW, BASE_READS, MAX_DISCARDS, MELD_MIN, SELF_GROW = 6, 2, 3, 3, 2


def counts(raw, grid):
    """겹쳐 보기 한 장 → 강 상자 수·자리별 강(사분면)·자리별 울기 상자 수."""
    from PIL import Image
    import io

    q = {k: str(grid[k]) for k in ("x1", "x2", "y1", "y2")}
    tiles = json.loads(ondevice.overlay(raw, q))["tiles"]
    W, H = Image.open(io.BytesIO(raw)).size
    s = grid.get("sticks")
    cx, cy = ((s[1] + s[3]) / 2000, (s[0] + s[2]) / 2000) if s else ((grid["x1"] + grid["x2"]) / 2000, (grid["y1"] + grid["y2"]) / 2000)
    own = dict.fromkeys(SIDES, 0)
    meld = dict.fromkeys(SIDES, 0)
    river = 0
    for t in tiles:
        x, y, w, h = t["b"]
        if t["r"] == "river":
            river += 1
            dx, dy = (x + w / 2 - cx) * W, (y + h / 2 - cy) * H
            own[("bottom" if dy > 0 else "top") if abs(dy) >= abs(dx) else ("right" if dx > 0 else "left")] += 1
        elif t["r"] == "meld" and t["s"] in meld:
            meld[t["s"]] += 1
    return {"river": river, "own": own, "meld": meld, "n": len(tiles)}


def eff(n):
    return n if n >= MELD_MIN else 0


def verdict(side, base, fin):
    d = fin["river"] - base["river"]
    own = fin["own"][side] - base["own"][side]
    calls = [o for o in SIDES if o != side and eff(fin["meld"][o]) > eff(base["meld"][o])]
    self_grew = fin["meld"][side] - base["meld"][side] >= SELF_GROW
    if d < 0:
        v = "unknown"
    elif d > MAX_DISCARDS or own > 0 or calls:
        v = "no"
    else:
        v = "yes"
    return {"verdict": v, "river_diff": d, "own_diff": own, "calls": calls, "self_grew": self_grew}


def main():
    caps, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for f in sys.argv[3:]:
        rounds = json.load(open(f, encoding="utf-8"))
        for name in sorted(rounds):
            r = rounds[name]
            c = r["C"]
            if not r["captures"] or not c["riichi_at"]:
                continue
            frames = {}
            for z in sorted((caps / name).glob("frames_*.zip")):
                zf = zipfile.ZipFile(z)
                for fr in json.loads(zf.read("frames.json").decode("utf-8"))["frames"]:
                    frames[fr["at"][11:19]] = (zf, fr["file"])
            photo = caps / r["captures"][0] / "original.jpg"
            if not photo.exists():
                continue
            fin = counts(photo.read_bytes(), c["grid"])
            for side, ra in c["riichi_at"].items():
                at = ra["at"]
                secs = lambda t: int(t[:2]) * 3600 + int(t[3:5]) * 60 + int(t[6:8])
                ts = [t for t in sorted(frames) if 0 <= secs(t) - secs(at) <= BASE_WINDOW][:BASE_READS]
                reads = [counts(frames[t][0].read(frames[t][1]), c["grid"]) for t in ts]
                if not reads:
                    continue
                base = {
                    "river": max(x["river"] for x in reads),
                    "own": {s: max(x["own"][s] for x in reads) for s in SIDES},
                    "meld": {s: max(x["meld"][s] for x in reads) for s in SIDES},
                }
                v = verdict(side, base, fin)
                pixel = side in c["ippatsu"] and sum(c["discards"].values()) - ra["total"] <= 3
                row = {"round": name, "side": side, "riichi_at": at, "win": r["win"], "winner": r["winner"], "base_frames": ts,
                       "base": base, "final": fin, **v, "pixel": pixel}
                rows.append(row)
                print(name[9:15], side, at, "~", r["win"], "화료", r["winner"], "| 기준", ts, "강", [x["river"] for x in reads], "→ 끝", fin["river"],
                      f"(차 {v['river_diff']}, 자기 강 {v['own_diff']})", "울기 기준", {k: n for k, n in base["meld"].items() if n},
                      "끝", {k: n for k, n in fin["meld"].items() if n}, "→", v["verdict"], "· 픽셀", "yes" if pixel else "no",
                      "· 자기 늘어남" if v["self_grew"] else "")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


main()
