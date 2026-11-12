"""겹쳐 보기 두 결과(원본 4080 그대로 / 2040 키워 읽기)가 다른 상자를 사진으로 나란히 보여 준다(2026-11-12, metrics 표 4-9 검토용).

  python -X utf8 experiments/ondevice/overlay_diff_sheet.py [fold|prod] [A 태그=1112b_full] [B 태그=1112b_s2040_up]
다른 것 = ① 종류가 다른 상자 ② 한쪽에만 있는 상자 ③ 원본 상자 하나에 2040 상자가 여럿 ④ 화료자 손패·울기·떼어 둔 패의 역할·자리가 바뀐 상자.
그림 experiments/ondevice/build/overlay_diff/<models>/<번호>_<장면>.jpg + sheet_<k>.jpg(왼쪽 = 원본, 오른쪽 = 2040 을 2배로 키운 것, 빨강 = 다른 상자).
"""
import io
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
sys.path.insert(0, str(ROOT / "experiments/speed"))
import robust_suite as rs  # noqa: E402

RES = ROOT / "experiments/ondevice/results"
VIEW = 520  # 한쪽 그림 한 변(px)
WIN = ("hand", "meld", "loose")


def iou(a, b) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-12)


def shrink(im: Image.Image, long_side: int = 2040) -> Image.Image:
    """overlay_score.shrink 와 같은 줄이기(JPEG 85 로 저장했다 다시 읽음)."""
    k = max(im.size) / long_side
    if k > 1:
        im = im.reduce(round(k)) if abs(k - round(k)) < 0.05 else im.resize((round(im.width / k), round(im.height / k)), Image.BOX)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def diffs(a: dict, b: dict) -> list[dict]:
    side, out = a["side"], []
    ta, tb = a["tiles"], b["tiles"]
    hit = {}
    for j, y in enumerate(tb):
        ms = [i for i, x in enumerate(ta) if iou(x["b"], y["b"]) > 0.5]
        if not ms:
            out.append({"why": f"2040 에만 있음: {y['t']} {y['tc']} {y['r']}/{y['s']}", "box": y["b"]})
            continue
        i = max(ms, key=lambda i: iou(ta[i]["b"], y["b"]))
        hit.setdefault(i, []).append(j)
    for i, x in enumerate(ta):
        js = hit.get(i, [])
        if not js:
            if not any(iou(x["b"], y["b"]) > 0.5 for y in tb):
                out.append({"why": f"원본에만 있음: {x['t']} {x['tc']} {x['r']}/{x['s']}", "box": x["b"]})
            continue
        if len(js) > 1:
            out.append({"why": f"원본 1상자({x['t']}) → 2040 {len(js)}상자({' '.join(tb[j]['t'] for j in js)})", "box": x["b"]})
            continue
        y = tb[js[0]]
        if x["t"] != y["t"]:
            out.append({"why": f"종류 {x['t']}({x['tc']}) → {y['t']}({y['tc']}), 역할 {x['r']}/{x['s']} → {y['r']}/{y['s']}", "box": x["b"]})
        elif (x["r"], x["s"]) != (y["r"], y["s"]) and ((x["r"] in WIN and (x["s"] == side or x["r"] == "loose")) or (y["r"] in WIN and (y["s"] == side or y["r"] == "loose"))):
            out.append({"why": f"{x['t']} 역할 {x['r']}/{x['s']} → {y['r']}/{y['s']}(화료자 {side})", "box": x["b"]})
    return out


def panel(im: Image.Image, tiles: list, box, font, zoom_tiles: float = 9.0) -> Image.Image:
    W, H = im.size
    cx, cy = (box[0] + box[2] / 2) * W, (box[1] + box[3] / 2) * H
    half = max(box[2] * W, box[3] * H) * zoom_tiles / 2
    x0, y0 = cx - half, cy - half
    crop = im.crop((round(x0), round(y0), round(x0 + 2 * half), round(y0 + 2 * half))).resize((VIEW, VIEW), Image.BICUBIC)
    k = VIEW / (2 * half)
    d = ImageDraw.Draw(crop)
    for t in tiles:
        bx, by, bw, bh = t["b"]
        r = [(bx * W - x0) * k, (by * H - y0) * k, ((bx + bw) * W - x0) * k, ((by + bh) * H - y0) * k]
        if r[2] < 0 or r[3] < 0 or r[0] > VIEW or r[1] > VIEW:
            continue
        red = iou(t["b"], box) > 0.3
        d.rectangle(r, outline=(255, 40, 40) if red else (60, 220, 255), width=4 if red else 2)
        d.text((r[0] + 2, r[1] - 20 if r[1] > 22 else r[3] + 2), f"{t['t']} {t['r'][0]}{t['s'][0]}", fill=(255, 60, 60) if red else (255, 255, 0), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    return crop


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    models = sys.argv[1] if len(sys.argv) > 1 else "fold"
    ta, tb = (sys.argv[2] if len(sys.argv) > 2 else "1112b_full"), (sys.argv[3] if len(sys.argv) > 3 else "1112b_s2040_up")
    A = json.loads((RES / f"overlay_score_{models}_{ta}.json").read_text(encoding="utf-8"))["scenes"]
    B = json.loads((RES / f"overlay_score_{models}_{tb}.json").read_text(encoding="utf-8"))["scenes"]
    out = ROOT / "experiments/ondevice/build/overlay_diff" / models
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.jpg"):
        f.unlink()
    font, cap = ImageFont.truetype("malgun.ttf", 17), ImageFont.truetype("malgun.ttf", 20)
    paths = {s["name"]: s["path"] for s in rs.scenes("dev")}
    rows, n = [], 0
    for name in A:
        ds = diffs(A[name], B[name])
        if not ds:
            continue
        full = ImageOps.exif_transpose(Image.open(paths[name])).convert("RGB")
        small = shrink(full)
        for dd in ds:
            n += 1
            left, right = panel(full, A[name]["tiles"], dd["box"], font), panel(small, B[name]["tiles"], dd["box"], font)
            row = Image.new("RGB", (VIEW * 2 + 12, VIEW + 64), (25, 25, 25))
            row.paste(left, (0, 64))
            row.paste(right, (VIEW + 12, 64))
            d = ImageDraw.Draw(row)
            d.text((6, 4), f"{n}. {name}  장면 판정 {'O' if A[name]['ok'] else 'X'} → {'O' if B[name]['ok'] else 'X'}", fill=(255, 255, 255), font=cap)
            d.text((6, 32), dd["why"], fill=(255, 200, 80), font=cap)
            d.text((VIEW - 150, 4), "왼쪽 원본(4080)", fill=(160, 160, 160), font=font)
            d.text((VIEW * 2 - 170, 4), "오른쪽 2040 키워 읽기", fill=(160, 160, 160), font=font)
            row.save(out / f"{n:02d}_{name}.jpg", quality=90)
            rows.append(row)
            print(n, name, dd["why"])
    for k in range(0, len(rows), 3):
        part = rows[k:k + 3]
        sheet = Image.new("RGB", (part[0].width, sum(r.height + 8 for r in part)), (0, 0, 0))
        y = 0
        for r in part:
            sheet.paste(r, (0, y))
            y += r.height + 8
        sheet.save(out / f"sheet_{k // 3 + 1}.jpg", quality=88)
    print("다른 상자", n, "→", out)


if __name__ == "__main__":
    main()
