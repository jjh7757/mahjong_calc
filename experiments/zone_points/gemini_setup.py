"""Gemini 자동 맞추기(운영 `/v2/setup`)를 펠트 판독과 같은 사진으로 잰다(2026-11-02, 사용자 질문). 사진마다 1회, 응답 → 격자는 앱 proposeGrid 와 같은 규칙.
재료 사진 35장 + 다른 탁자가 찍힌 비스듬한 사진 4장. 키는 .recognizer_key.
  python -X utf8 experiments/zone_points/gemini_setup.py [그림 앞이름]
결과 tile_classifier/data/zone_points/gemini_setup.json: 이름 → s·grid(없으면 null)·raw
"""
from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propose import DATA, ROOT, load  # noqa: E402

URL = "https://mahjong.ai-agent-develop.cloud/v2/setup"
SIDES = ("bottom", "right", "top", "left")
STRIP_MARGIN, STICKS_PAD = 1.5, 0.5  # grid_zones.dart setupStripMargin·setupSticksPad
OTHERS = ["experiments/vlm/samples_real/table1.jpg", "experiments/vlm/samples_real/table2.jpg", "experiments/vlm/samples_phone/phone_shot1.jpg", "experiments/vlm/samples_broadcast/full.jpg"]


def propose_grid(setup: dict) -> dict | None:
    """앱 proposeGrid 와 같다. 상자 = [ymin, xmin, ymax, xmax]."""
    seats = setup.get("seats") or {}
    hand, melds = {}, {}
    for s in SIDES:
        j = seats.get(s) or {}
        if not j.get("hand"):
            return None
        hand[s], melds[s] = j["hand"], j.get("melds")
    device = setup.get("device")
    if not device:
        return None
    lens = sorted((hand[s][3] - hand[s][1] if s in ("bottom", "top") else hand[s][2] - hand[s][0]) / 13 for s in SIDES)
    u = (lens[1] + lens[2]) / 2

    def seat_box(s: str) -> list:
        h, m = hand[s], melds[s]
        at_row = bool(m) and {"bottom": m[0] >= h[0] - u, "top": m[2] <= h[2] + u, "left": m[3] <= h[3] + u, "right": m[1] >= h[1] - u}[s] if m else False
        return h if not at_row else [min(h[0], m[0]), min(h[1], m[1]), max(h[2], m[2]), max(h[3], m[3])]

    margin = STRIP_MARGIN * u
    y2, y1 = round(seat_box("bottom")[0] - margin), round(seat_box("top")[2] + margin)
    x2, x1 = round(seat_box("right")[1] - margin), round(seat_box("left")[3] + margin)
    if not (0 < x1 < x2 < 1000 and 0 < y1 < y2 < 1000):
        return None
    p = STICKS_PAD * u
    c = lambda v: max(0, min(1000, round(v)))
    return {"x1": x1, "x2": x2, "y1": y1, "y2": y2, "sticks": [c(device[0] - p), c(device[1] - p), c(device[2] + p), c(device[3] + p)]}


def post(jpeg: bytes, key: str) -> dict:
    bound = uuid.uuid4().hex
    body = (f'--{bound}\r\nContent-Disposition: form-data; name="image"; filename="setup.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode() + jpeg + f"\r\n--{bound}--\r\n".encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": f"multipart/form-data; boundary={bound}", "X-API-Key": key, "User-Agent": "mahjong-calc-experiment"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def one(args) -> tuple[str, dict]:
    name, src, key = args
    im = load(src).convert("RGB")
    im.thumbnail((1568, 1568))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    t0 = time.time()
    try:
        raw = post(b.getvalue(), key)
        return name, {"s": round(time.time() - t0, 1), "grid": propose_grid(raw), "raw": raw}
    except Exception as e:  # noqa: BLE001
        return name, {"s": round(time.time() - t0, 1), "grid": None, "error": str(e)[:200]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    key = (ROOT / ".recognizer_key").read_text(encoding="utf-8").strip()
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    jobs = [(n, r["src"], key) for n, r in rows.items() if r["kind"] == "photo"]
    jobs += [(Path(p).stem, str(ROOT / p), key) for p in OTHERS]
    with ThreadPoolExecutor(3) as ex:
        out = dict(ex.map(one, jobs))
    (DATA / "gemini_setup.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    for n, r in out.items():
        print(n[-14:], r["s"], r["grid"] and [r["grid"][k] for k in ("x1", "x2", "y1", "y2")], r.get("error", ""))
    ts = sorted(r["s"] for r in out.values())
    print("격자 나옴", sum(bool(r["grid"]) for r in out.values()), "/", len(out), f"시간 중앙 {ts[len(ts) // 2]} p90 {ts[int(0.9 * len(ts))]} 최대 {ts[-1]}", "오류", sum("error" in r for r in out.values()))
    if len(sys.argv) > 1:
        names = [Path(p).stem for p in OTHERS] + ["20261031_131411", "20261031_142535", "20261031_143104", "20261031_171245"]
        srcs = {j[0]: j[1] for j in jobs}
        sh = Image.new("RGB", (4 * 480, 2 * 360))
        for i, n in enumerate(names):
            im = load(srcs[n]).convert("RGB").resize((480, 360))
            d = ImageDraw.Draw(im)
            r = out[n]
            seats = (r.get("raw") or {}).get("seats") or {}
            for s in SIDES:
                for key_, col in (("hand", (255, 230, 0)), ("melds", (255, 120, 0))):
                    b = (seats.get(s) or {}).get(key_)
                    if b:
                        d.rectangle((b[1] * 0.48, b[0] * 0.36, b[3] * 0.48, b[2] * 0.36), outline=col, width=2)
            dev = (r.get("raw") or {}).get("device")
            if dev:
                d.rectangle((dev[1] * 0.48, dev[0] * 0.36, dev[3] * 0.48, dev[2] * 0.36), outline=(255, 0, 255), width=2)
            g = r["grid"]
            if g:
                for x in (g["x1"], g["x2"]):
                    d.line((x * 0.48, 0, x * 0.48, 360), fill=(255, 255, 255))
                for y in (g["y1"], g["y2"]):
                    d.line((0, y * 0.36, 480, y * 0.36), fill=(255, 255, 255))
            d.rectangle((0, 0, 170, 12), fill="black")
            d.text((2, 0), f"{n[-12:]} grid={'O' if g else 'X'}", fill="white")
            sh.paste(im, ((i % 4) * 480, (i // 4) * 360))
        sh.save(sys.argv[1] + ".jpg", quality=85)


if __name__ == "__main__":
    main()
