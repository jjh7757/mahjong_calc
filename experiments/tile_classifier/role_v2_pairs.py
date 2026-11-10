"""labels_v2 42장을 '사진(화료자가 아래로 오게 돌림) | 역할 모델 입력' 쌍으로 그린다(사용자 눈 확인용, 2026-11-08).
  python -X utf8 experiments/tile_classifier/role_v2_pairs.py → data/role/base_review/pairs_XX.jpg"""
import json, sys
from pathlib import Path
import cv2
from PIL import Image, ImageDraw, ImageFont
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_v2_apply as ap  # noqa: E402
L = json.loads((HERE / "data/role/v2/labels_v2.json").read_text(encoding="utf-8"))
OUT = HERE / "data/role/base_review"
ROT = {"bottom": None, "right": cv2.ROTATE_90_CLOCKWISE, "top": cv2.ROTATE_180, "left": cv2.ROTATE_90_COUNTERCLOCKWISE}
f = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 22); fb = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 28)
order = ap.KEEP1031 + [n for n in L if n not in ap.KEEP1031]
pairs = []
for n in order:
    s = L[n]
    im = cv2.imread(s["image"])
    C = {"hand": (255, 70, 0), "meld": (255, 230, 0), "river": (0, 150, 255), "wall": (0, 0, 255), "pair": (255, 0, 255), "loose": (0, 255, 255), "other": (255, 255, 255)}  # BGR
    for b in s["backs"]:
        cv2.rectangle(im, (b[0], b[1]), (b[0] + b[2], b[1] + b[3]), (150, 150, 150), 5)
    for it in s["items"]:
        x, y, w, h = it["box"]
        cv2.rectangle(im, (x, y), (x + w, y + h), C[it["role"]], 6 if it["role"] == "river" else 11)
        if it.get("owner") == "other" and it["role"] == "meld":
            cv2.line(im, (x, y), (x + w, y + h), C["meld"], 5)
    for g in s.get("kan_groups", []):
        bx = [s["items"][i]["box"] for i in g["face_index"]] + [s["backs"][j] for j in g["back_index"]]
        cv2.rectangle(im, (min(b[0] for b in bx) - 14, min(b[1] for b in bx) - 14), (max(b[0] + b[2] for b in bx) + 14, max(b[1] + b[3] for b in bx) + 14), (200, 60, 255), 10)
    if ROT[s["side"]] is not None:
        im = cv2.rotate(im, ROT[s["side"]])
    inp = ap.draw("", s, f); H = 560
    inp = inp.resize((int(inp.width * H / inp.height), H))
    ph = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)); ph = ph.resize((int(ph.width * H / ph.height), H))
    kind = {"composite": "합성본", "photo": "원본"}[s["kind"]]
    src = "기존 라벨" if s["source"] == "labels.json" else "새 라벨"
    c = Image.new("RGB", (max(ph.width + inp.width + 10, 1310), H + 76), "white"); d = ImageDraw.Draw(c)
    d.text((6, 6), f"{n} · 화료자 {s['side']}(아래로 돌림) · {kind} · {src}", font=fb, fill=(0, 0, 0))
    d.text((6, 42), ("검토 필요: " + s["flags"]) if s.get("flags") else "", font=f, fill=(200, 0, 0))
    c.paste(ph, (0, 76)); c.paste(inp, (ph.width + 10, 76)); pairs.append(c)
per = 4
for k in range(0, len(pairs), per):
    grp = pairs[k:k + per]; W = max(p.width for p in grp)
    S = Image.new("RGB", (W * 2 + 20, ((len(grp) + 1) // 2) * (grp[0].height + 16) + 50), "white"); d = ImageDraw.Draw(S)
    d.text((8, 8), "각 쌍: 왼쪽 사진 위 라벨 · 오른쪽 역할 모델 입력(둘 다 화료자가 아래) — 파랑 손패 · 하늘 울기(누구 것이든) · 주황 강 · 빨강 패산 위 표시패 · 자홍 탁자 위 짝 · 노랑 떼어 둔 화료패 · 흰·회색 테두리 = 역할 없음 · 회색/보라 = 뒷면 · 대각선 = 다른 사람 울기 · 분홍 테 = 깡 묶음", font=f, fill=(0, 0, 0))
    for i, p in enumerate(grp):
        S.paste(p, ((i % 2) * (W + 20), 50 + (i // 2) * (grp[0].height + 16)))
    S.save(OUT / f"pairs_{k // per + 1:02d}.jpg", quality=82)
print(len(pairs), "쌍,", (len(pairs) + per - 1) // per, "장")
