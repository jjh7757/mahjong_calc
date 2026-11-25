"""앱 자리 구역(GridZones.seat — paifu.json frames.box · boxes 가 담는 값)이 손패 줄을 담는지 점검(2026-11-25, metrics 표 12-127).

  python -X utf8 experiments/paifu_frames/handzone_check.py          (저장소 루트에서, 읽기만 — 출력은 화면)

견줌: 판별 손 설정(handtrack/config/<판>.json)의 band · sheet_band(원본 1496 좌표) ↔ 그 시각 앱 격자로 만든 자리 구역(0~1000).
앱 격자는 추적 프레임 zip 의 frames.json grid 에서 읽은 값이다(11-14 하루에 여섯 가지 — 아래 둘이 2 · 3반장 시각의 것).
  B: 12:56:30 ~ 14:32(2반장 내내) — 탁자에서 어긋나 있음(리치봉 구역 가운데가 실제 기기보다 오른쪽 위)
  C: 14:32:36 뒤(3반장 — 앱 추적 기록은 14:43 까지뿐이라 그 뒤도 같다고 봄, headrec_dump.py GRID 상수와 같은 값)
자리 구역 = lib/table/grid_zones.dart GridZones.seat(side): 격자선에서 사진 끝까지(손패 변 + 그 사람 오른쪽 모서리).
추적 프레임(2992²)과 헤드 녹화(1496²)는 같은 화각이라 0~1000 좌표를 그대로 쓴다(같은 시각 두 장을 나란히 놓고 봄).
"""
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GB = {"x1": 346, "x2": 852, "y1": 206, "y2": 711}
GC = {"x1": 264, "x2": 783, "y1": 259, "y2": 777}
REC = 1496


def seat(g, s):
    x1, x2, y1, y2 = g["x1"], g["x2"], g["y1"], g["y2"]
    return {"bottom": (x1, y2, 1000, 1000), "right": (x2, 0, 1000, y2), "top": (0, 0, x2, y1), "left": (0, y1, x1, 1000)}[s]


def main():
    w = sys.stdout.buffer.write
    rows = []
    for p in sorted(glob.glob(str(HERE / "handtrack" / "config" / "[rLnp]*.json"))):
        j = json.load(open(p, encoding="utf-8"))
        gid = j["id"]
        if gid[:3] in ("r02", "r04"):   # 오전 판(다른 격자 시각) — 뺌
            continue
        g, gn = (GB, "B") if int(gid.split("_")[1][:4]) < 1432 else (GC, "C")
        for key in ("band", "sheet_band"):
            if key not in j:
                continue
            b = [v * 1000 / REC for v in j[key]]
            s = seat(g, j["side"])
            m = (b[0] - s[0], b[1] - s[1], s[2] - b[2], s[3] - b[3])   # 안쪽 여유(천분율) — 음수 = 밖으로 나감
            rows.append((gid, j["side"], gn, key, min(m), m))
    for r in rows:
        w(f"{r[0]:12s} {r[1]:6s} 격자{r[2]} {r[3]:10s} 최소 여유 {r[4]:6.1f}  (왼 {r[5][0]:.0f} 위 {r[5][1]:.0f} 오 {r[5][2]:.0f} 아래 {r[5][3]:.0f})\n".encode())
    for key in ("band", "sheet_band"):
        for gn in "BC":
            rr = [r for r in rows if r[3] == key and r[2] == gn]
            w(f"{key} 격자{gn}: 안에 듦 {sum(r[4] >= 0 for r in rr)}/{len(rr)}\n".encode())


if __name__ == "__main__":
    main()
