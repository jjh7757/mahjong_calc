"""매장 25장의 격자를 사진마다 맞춘다(2026-11-01, 사용자 요청). 패 종류·정답은 안 쓰고 탁자 모양만 본다. API 호출 없음.

  기기 = 가운데 어두운 덩어리 → 리치봉 상자.
  가운데 칸 = 기기 + 거기서 패 1.2개 틈 안으로 이어지는 패(강) + 패 0.3개 여유.
  손으로 고친 값은 OVERRIDE. 결과 results/fit_grids.json, 확인 그림 results/fit_grids/sheet_*.jpg.

  python -X utf8 experiments/speed/fit_grids.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import wide_seat as ws  # noqa: E402
from wide_seat import sg  # noqa: E402
from app import river as rv  # noqa: E402
from app import seat_wide as sw  # noqa: E402

OUT = ws.OUT.parent / "fit_grids.json"
SHEETS = ws.OUT.parent / "fit_grids"
# 사진을 눈으로 보고 고친 값(sheet_*.jpg). 화료자의 떼어 둔 패·표시패·흩어진 손패가 자리 크롭에 들어오게, 기기를 잘못 잡은 171245 는 직접.
OVERRIDE: dict[str, dict] = {
    "133826": {"x1": 266},  # 표시패 8m·8p 포함
    "134815": {"y2": 800},  # 기운 사진: 오른쪽 모서리 울기가 줄보다 위
    "142535": {"x1": 295},  # 앞으로 내민 0s·5s
    "143104": {"y2": 745},  # 떼어 둔 7s·표시패
    "171245": {"x2": 640, "y1": 290, "y2": 690, "sticks": [425, 400, 625, 555]},
    "172424": {"x2": 680},  # 표시패
    "175951": {"x1": 300, "y1": 350},  # 흩어진 손패
    "183022": {"x1": 320},  # 패산에 일부 가린 줄 왼쪽 끝
}


def device_box(rgb: np.ndarray, seed: tuple[float, float]) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) 원본 픽셀. 어둡고 채도 낮은 덩어리 중 [seed] 에 가장 가까운 큰 것."""
    H, W = rgb.shape[:2]
    s = 1000 / max(H, W)
    small = cv2.resize(rgb, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA)
    # 펠트도 패(흰 면)도 아닌 것. 기기는 광택이 있어 밝은 반사가 섞이므로 닫기로 메운다. 패의 글자는 열기로 지운다.
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0].astype(int) * 2
    felt = (hue >= 70) & (hue <= 200) & (hsv[..., 1] > 60)
    white = (hsv[..., 1] < 60) & (hsv[..., 2] > 130)
    mask = (~felt & ~white).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    n, _, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    best, score = None, 1e18
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if not (0.65 < w / h < 1.5) or not (90 <= w <= 300) or a < 0.5 * w * h:
            continue
        d = abs(cent[i][0] - seed[0] * s) + abs(cent[i][1] - seed[1] * s)
        if d < score:
            best, score = (x, y, x + w, y + h), d
    if best is None:
        raise RuntimeError("기기 못 찾음")
    return tuple(int(v / s) for v in best)


def fit(s: dict) -> dict:
    im = Image.open(s["path"]).convert("RGB")
    rgb = np.asarray(im)
    H, W = rgb.shape[:2]
    g = s["grid"]
    try:
        dx0, dy0, dx1, dy1 = device_box(rgb, ((g["x1"] + g["x2"]) / 2000 * W, (g["y1"] + g["y2"]) / 2000 * H))
    except RuntimeError:
        print(s["name"][-6:], "기기 못 찾음: 예전 리치봉 상자로")
        st = g["sticks"]
        dx0, dy0, dx1, dy1 = int(st[1] * W / 1000), int(st[0] * H / 1000), int(st[3] * W / 1000), int(st[2] * H / 1000)
    det = sw_detector()
    faces = sw.detect_all(rgb, det)
    long = statistics.median(max(f[2], f[3]) for f in faces)
    gap = 1.2 * long * 0.75
    x0, y0, x1, y1 = dx0, dy0, dx1, dy1
    left = list(faces)
    changed = True
    while changed:
        changed = False
        for f in left[:]:
            ddx = max(0, max(x0, f[0]) - min(x1, f[0] + f[2]))
            ddy = max(0, max(y0, f[1]) - min(y1, f[1] + f[3]))
            if ddx < gap and ddy < gap and max(f[2], f[3]) < 1.4 * long:
                x0, y0 = min(x0, f[0]), min(y0, f[1])
                x1, y1 = max(x1, f[0] + f[2]), max(y1, f[1] + f[3])
                left.remove(f)
                changed = True
    # 강 쪽 여유는 패 1.5개. 강 끝 크롭(가운데 칸)이 잘리지 않게 넉넉히.
    m = 1.5 * long * 0.75
    out = dict(x1=round((x0 - m) / W * 1000), x2=round((x1 + m) / W * 1000), y1=round((y0 - m) / H * 1000), y2=round((y1 + m) / H * 1000),
               sticks=[round(dy0 / H * 1000), round(dx0 / W * 1000), round(dy1 / H * 1000), round(dx1 / W * 1000)])
    # 화료자 쪽 선은 손패 줄 바로 안쪽으로. 자리 크롭이 커지면 패가 작아져 잘못 읽는다(표 1-5).
    side = s["side"]
    rot = np.asarray(im.rotate(-sg.ROT_CW[side], expand=True))
    rh = rot.shape[0]
    half = rot[rh // 2:]  # 화료자 쪽 절반만
    fr = sw.locate(np.ascontiguousarray(half), det)
    if fr and len(fr.row) >= 4:
        top = (min(f[1] for f in fr.row) - 0.3 * fr.th + rh // 2) / rh  # 돌린 사진 위에서 내려온 비율
        v = round(top * 1000)
        # 자리 크롭은 손패 줄 왼쪽 끝(그 사람 기준)부터 시작하므로, 그 끝 선도 줄 바깥으로(패 1개 여유).
        f = round((fr.row[0][0] - fr.tw) / rot.shape[1] * 1000)
        if side == "bottom":
            out["y2"], out["x1"] = v, min(out["x1"], f)
        elif side == "right":
            out["x2"], out["y2"] = v, max(out["y2"], 1000 - f)
        elif side == "top":
            out["y1"], out["x2"] = 1000 - v, max(out["x2"], 1000 - f)
        else:
            out["x1"], out["y1"] = 1000 - v, min(out["y1"], f)
    else:
        print(s["name"][-6:], "손패 줄 못 찾음: 강 기준 선 그대로")
    return out | OVERRIDE.get(s["name"][-6:], {})


_det = None


def sw_detector():
    global _det
    if _det is None:
        _det = rv.TileDetector(conf=0.04)
    return _det


def box(d, g, W, H, col, width=8):
    x1, x2, y1, y2 = g["x1"] * W / 1000, g["x2"] * W / 1000, g["y1"] * H / 1000, g["y2"] * H / 1000
    d.line((x1, 0, x1, H), fill=col, width=width)
    d.line((x2, 0, x2, H), fill=col, width=width)
    d.line((0, y1, W, y1), fill=col, width=width)
    d.line((0, y2, W, y2), fill=col, width=width)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    SHEETS.mkdir(parents=True, exist_ok=True)
    grids, thumbs = {}, []
    for s in sg.scenes():
        if s["set"] != "visit":
            continue
        k = s["name"][-6:]
        g = fit(s)
        grids[k] = g
        im = Image.open(s["path"]).convert("RGB")
        W, H = im.size
        d = ImageDraw.Draw(im)
        box(d, s["grid"], W, H, (120, 120, 255), 6)  # 예전 격자 파랑
        box(d, g, W, H, (255, 40, 40), 10)  # 맞춘 격자 빨강
        st = g["sticks"]
        d.rectangle((st[1] * W / 1000, st[0] * H / 1000, st[3] * W / 1000, st[2] * H / 1000), outline=(255, 220, 0), width=8)
        d.text((30, 20), f"{k} {s['side']}", fill=(255, 255, 0), font_size=110)
        im.thumbnail((800, 800))
        thumbs.append(im)
        print(k, s["side"], g, "예전", {x: s["grid"][x] for x in ("x1", "x2", "y1", "y2")}, flush=True)
    OUT.write_text(json.dumps(grids, ensure_ascii=False, indent=1), encoding="utf-8")
    for n in range(0, len(thumbs), 6):
        part = thumbs[n:n + 6]
        sheet = Image.new("RGB", (800 * 3, 600 * 2), (20, 20, 20))
        for i, t in enumerate(part):
            sheet.paste(t, ((i % 3) * 800, (i // 3) * 600))
        sheet.save(SHEETS / f"sheet_{n // 6}.jpg", quality=85)


if __name__ == "__main__":
    main()
