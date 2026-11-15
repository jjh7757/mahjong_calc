"""11-14 자료 눈 확인용 대조표·검토 양식·2단계 몫 나누기(2026-11-15, 1단계 D·E). v1114_draft.py 다음에.

data/v1114/sheets/<판 id>/
  tiles_NN.jpg  실물 패마다 한 칸(4×5 = 20칸/장). 칸 = [왼쪽] 가장 선명한 2992 크롭을 분류기가 읽은 방향으로 세워 크게
                 [오른쪽] 같은 그림의 둘레(패 3배 범위, 원래 방향, 노란 테두리 = 그 상자) / 아래 글: #실물 패 id, 초안 종류, 확신도,
                 n=나온 그림 수, 그림별 읽기 수, 표시. 테두리 색: 빨강 = 정답과 어긋남(LABEL?), 주황 = 그림마다 읽기 갈림(SPLIT),
                 노랑 = 확신 낮음(LOW), 회색 = 표시 없음. 파란 글 PREV = 앞 판 탁자가 남은 그림에서만 보인 패.
                 표시 있는 칸이 앞 장들에 먼저, 그다음 초안 종류 순.
  frames/<그림 이름>.jpg  그림 전체(패 있는 곳만 잘라 긴 변 1800)에 상자와 실물 패 id. 색은 위와 같음.
  index.json    장마다 칸 순서(실물 패 id), 그림 목록, 정답 대조 요약.
data/v1114/review/<판 id>.json  2단계가 채울 빈 양식, review/_FORMAT.json 형식 설명, review/_shares.json 2단계 4대 몫.
  python -X utf8 experiments/tile_classifier/v1114_sheets.py [판 id ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
from app import local_read as lr  # noqa: E402
from app import obb  # noqa: E402

OUT = HERE / "data" / "v1114"
COLS, ROWS = 4, 5
CW, CH = 380, 320  # 칸 크기
TILE_H = 200
FONT = "C:/Windows/Fonts/arial.ttf"
FONTB = "C:/Windows/Fonts/arialbd.ttf"
COLOR = {"label": (220, 30, 30), "split": (255, 140, 0), "low": (230, 200, 0), "none": (150, 150, 150)}
ORDER = {c: i for i, c in enumerate(lr.CLASSES)}


def font(size, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, size)


def flag_of(t: dict) -> str:
    return "label" if t["label_mismatch"] else "split" if t["split"] else "low" if t["low"] else "none"


def crop_tile(rgb: np.ndarray, b: dict) -> Image.Image:
    if b["rect"] is not None:
        (cx, cy), (w, h), a = b["rect"]
        im = obb.upright(rgb, ((cx, cy), (w, h), a), lr.PAD)
    else:
        x, y, w, h = b["box"]
        H, W = rgb.shape[:2]
        px, py = int(w * lr.PAD), int(h * lr.PAD)
        im = Image.fromarray(rgb[max(0, y - py):min(H, y + h + py), max(0, x - px):min(W, x + w + px)])
    return im.rotate(90 * b["rot"], expand=True)


def context(rgb: np.ndarray, b: dict, side: int = 200) -> Image.Image:
    x, y, w, h = b["box"]
    H, W = rgb.shape[:2]
    R = int(max(w, h) * 1.5)
    cx, cy = x + w // 2, y + h // 2
    x0, y0 = max(0, cx - R), max(0, cy - R)
    part = Image.fromarray(rgb[y0:min(H, cy + R), x0:min(W, cx + R)]).copy()
    d = ImageDraw.Draw(part)
    d.rectangle((x - x0, y - y0, x - x0 + w, y - y0 + h), outline=(255, 230, 0), width=3)
    part.thumbnail((side, side))
    return part


class Images:
    def __init__(self, draft):
        self.by = {im["id"]: im for im in draft["images"]}
        self.cache = {}

    def rgb(self, iid):
        if iid not in self.cache:
            if len(self.cache) > 3:
                self.cache.pop(next(iter(self.cache)))
            self.cache[iid] = np.asarray(Image.open(OUT / self.by[iid]["path"]).convert("RGB"))
        return self.cache[iid]


def tile_sheets(draft: dict, imgs: Images, out: Path) -> list[dict]:
    tracks = sorted(draft["tracks"], key=lambda t: ({"label": 0, "split": 1, "low": 2, "none": 3}[flag_of(t)], ORDER.get(t["draft"], 99), t["tid"]))
    # 그림 차례로 크롭을 만들어 두고(그림을 덜 다시 읽게) 칸에 붙인다
    need = {}
    for t in tracks:
        need.setdefault(t["best"]["image"], []).append(t)
    cells = {}
    for iid, ts in need.items():
        rgb = imgs.rgb(iid)
        for t in ts:
            b = imgs.by[iid]["boxes"][t["best"]["i"]]
            cells[t["tid"]] = (crop_tile(rgb, b), context(rgb, b))
    per = COLS * ROWS
    sheets = []
    f1, f2, f3 = font(30, True), font(19), font(19, True)
    for s in range(0, len(tracks), per):
        part = tracks[s:s + per]
        sheet = Image.new("RGB", (COLS * CW, ROWS * CH + 40), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        no = s // per + 1
        d.text((10, 8), f"{draft['round']} ({draft['split']})  tiles {s + 1}-{s + len(part)} / {len(tracks)}   sheet {no}", fill=(0, 0, 0), font=f3)
        for k, t in enumerate(part):
            cx0, cy0 = (k % COLS) * CW, 40 + (k // COLS) * CH
            fl = flag_of(t)
            d.rectangle((cx0 + 3, cy0 + 3, cx0 + CW - 4, cy0 + CH - 4), outline=COLOR[fl], width=6 if fl != "none" else 2)
            tim, ctx = cells[t["tid"]]
            s_ = TILE_H / tim.height
            if tim.width * s_ > 160:
                s_ = 160 / tim.width
            tim = tim.resize((max(1, round(tim.width * s_)), max(1, round(tim.height * s_))), Image.LANCZOS)
            sheet.paste(tim, (cx0 + 12 + (160 - tim.width) // 2, cy0 + 12 + (TILE_H - tim.height) // 2))
            sheet.paste(ctx, (cx0 + 178, cy0 + 12 + (TILE_H - ctx.height) // 2))
            d.text((cx0 + 12, cy0 + TILE_H + 18), f"#{t['tid']}  {t['draft']}  {t['conf']:.2f}", fill=(0, 0, 0), font=f1)
            reads = " ".join(f"{a}x{n}" for a, n in sorted(t["reads"].items(), key=lambda x: -x[1]))
            d.text((cx0 + 12, cy0 + TILE_H + 52), f"n={t['n']}  {reads}"[:34], fill=(40, 40, 40), font=f2)
            tags = [x for x, on in (("LABEL?", bool(t["label_mismatch"])), ("SPLIT", t["split"]), ("LOW", t["low"])) if on]
            if tags:
                d.text((cx0 + 12, cy0 + TILE_H + 74), " ".join(tags), fill=COLOR[fl], font=f3)
            if t.get("prev_round_scene"):
                d.text((cx0 + 250, cy0 + TILE_H + 74), "PREV", fill=(30, 80, 220), font=f3)
        name = f"tiles_{no:02d}.jpg"
        sheet.save(out / name, quality=90)
        sheets.append({"file": name, "tids": [t["tid"] for t in part], "flagged": sum(flag_of(t) != "none" for t in part)})
    return sheets


def frame_sheets(draft: dict, imgs: Images, out: Path) -> list[dict]:
    (out / "frames").mkdir(exist_ok=True)
    by_tid = {t["tid"]: t for t in draft["tracks"]}
    res = []
    fs = font(17, True)
    for im in draft["images"]:
        base = Image.open(OUT / im["path"]).convert("RGB")
        W, H = base.size
        bs = im["boxes"]
        if bs:
            x0 = max(0, min(b["box"][0] for b in bs) - 150)
            y0 = max(0, min(b["box"][1] for b in bs) - 150)
            x1 = min(W, max(b["box"][0] + b["box"][2] for b in bs) + 150)
            y1 = min(H, max(b["box"][1] + b["box"][3] for b in bs) + 150)
        else:
            x0, y0, x1, y1 = 0, 0, W, H
        part = base.crop((x0, y0, x1, y1))
        s = 1800 / max(part.size)
        part = part.resize((round(part.width * s), round(part.height * s)), Image.LANCZOS)
        d = ImageDraw.Draw(part)
        for b in bs:
            t = by_tid[b["track"]]
            fl = "label" if b.get("label_mismatch") else flag_of(t) if flag_of(t) != "label" else "none"
            x, y, w, h = ((b["box"][0] - x0) * s, (b["box"][1] - y0) * s, b["box"][2] * s, b["box"][3] * s)
            d.rectangle((x, y, x + w, y + h), outline=COLOR[fl] if fl != "none" else (0, 200, 255), width=3)
            tb = d.textbbox((x + 2, y + 2), t["tid"], font=fs)
            d.rectangle(tb, fill=(0, 0, 0))
            d.text((x + 2, y + 2), t["tid"], fill=(255, 255, 255), font=fs)
        tag = f"{im['id']}  {im['kind']}  boxes {len(bs)}" + ("  PREV-ROUND TABLE" if im.get("prev_round_scene") else "")
        tb = d.textbbox((8, 8), tag, font=font(24, True))
        d.rectangle(tb, fill=(255, 255, 255))
        d.text((8, 8), tag, fill=(0, 0, 0), font=font(24, True))
        name = Path(im["name"]).stem + ".jpg"
        part.save(out / "frames" / name, quality=88)
        res.append({"file": f"frames/{name}", "image": im["id"], "kind": im["kind"], "boxes": len(bs), "prev_round_scene": bool(im.get("prev_round_scene"))})
    return res


FORMAT = {
    "what": "2단계 눈 확인 결과. 판마다 review/<판 id>.json 하나. 대조표 sheets/<판 id>/tiles_NN.jpg 의 칸(#실물 패 id)을 보고 tracks 의 칸을 채운다.",
    "fields": {
        "reviewer": "검토한 에이전트 이름(예: P1)",
        "done": "판 전체를 다 봤으면 true",
        "tracks[].tid": "실물 패 id(대조표 칸의 #번호, 프레임 그림 상자 위 번호)",
        "tracks[].draft": "초안 종류(바꾸지 말 것 — 참고용)",
        "tracks[].flags": "초안 표시(label = 정답과 어긋남 후보, split = 그림마다 읽기 갈림, low = 확신 낮음, prev = 앞 판 탁자에서만 보임)",
        "tracks[].verdict": "ok = 초안이 맞음 / fix = 초안이 틀림, tile 에 맞는 종류 / not_tile = 앞면 패가 아님(뒷면·세운 패·패 일부만·손·다른 물건) / "
                            "mixed = 한 id 에 다른 패가 섞여 이어짐(프레임 그림에서 확인, per_image 에 그림별 종류) / unsure = 흐림·가림으로 모르겠음(note 필수)",
        "tracks[].tile": "verdict 가 fix 일 때 맞는 종류. 표기는 data/index.json 과 같음: 1m~9m·1p~9p·1s~9s, 적5 = 0m·0p·0s, 자패 1z 동 2z 남 3z 서 4z 북 5z 백 6z 발 7z 중",
        "tracks[].per_image": "verdict 가 mixed 일 때만: {그림 id: 종류 또는 'not_tile'}. 그림 id 는 draft 의 apps[].image",
        "tracks[].note": "자유 메모(짧게)",
        "missed": "상자가 없는데 앞면이 보이는 패(선택): [{image: 그림 id, near_tid: 가까운 실물 패 id, tile: 종류, note}]",
        "image_notes": "그림 전체에 대한 메모(선택): [{image, note}] — 예: 손이 탁자를 가림, 앞 판 탁자, 카메라 움직임",
    },
    "rules": [
        "라벨 대상은 앞면이 보이는 패 전부(강·울기·공개된 손패·도라 표시패). 뒷면·세운 패는 not_tile.",
        "정답(label.json)과 어긋남(LABEL?) 표시는 참고일 뿐이다 — 사진에 보이는 대로 적는다. 정답이 틀렸다고 보이면 note 에 적는다.",
        "적5(빨간 5)와 그냥 5 를 꼭 가른다. 빨간 점·빨간 무늬가 보이면 0m·0p·0s.",
        "칸의 왼쪽 크롭은 분류기가 읽은 방향으로 돌린 것이라 뒤집혀 보일 수 있다. 오른쪽 둘레 그림(노란 테두리)이 원래 방향.",
        "모든 tracks 에 verdict 를 채운다(null 남기지 말 것). 확신 없으면 unsure.",
    ],
}


def review_form(draft: dict, sheets: list[dict]) -> dict:
    where = {tid: sh["file"] for sh in sheets for tid in sh["tids"]}
    order = [tid for sh in sheets for tid in sh["tids"]]
    by = {t["tid"]: t for t in draft["tracks"]}
    rows = []
    for tid in order:
        t = by[tid]
        fl = [x for x, on in (("label", bool(t["label_mismatch"])), ("split", t["split"]), ("low", t["low"]), ("prev", t.get("prev_round_scene"))) if on]
        rows.append({"tid": tid, "draft": t["draft"], "flags": fl, "sheet": where[tid], "verdict": None, "tile": None, "per_image": None, "note": ""})
    return {"round": draft["round"], "split": draft["split"], "reviewer": None, "done": False, "tracks": rows, "missed": [], "image_notes": []}


def shares(sizes: dict, k: int = 4) -> list[dict]:
    """판을 실물 패 수가 비슷하게 k 몫으로(큰 판부터 가장 가벼운 몫에)."""
    bins = [{"agent": f"P{i + 1}", "rounds": [], "tracks": 0, "flagged": 0} for i in range(k)]
    for rid, (n, f) in sorted(sizes.items(), key=lambda x: -x[1][0]):
        b = min(bins, key=lambda b: b["tracks"])
        b["rounds"].append(rid)
        b["tracks"] += n
        b["flagged"] += f
    for b in bins:
        b["rounds"].sort()
    return bins


def main():
    want = set(sys.argv[1:])
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    (OUT / "review").mkdir(parents=True, exist_ok=True)
    (OUT / "review" / "_FORMAT.json").write_text(json.dumps(FORMAT, ensure_ascii=False, indent=1), encoding="utf-8")
    sizes = {}
    for r in man["rounds"]:
        p = OUT / "draft" / f"{r['id']}.json"
        if not p.exists():
            continue
        draft = json.loads(p.read_text(encoding="utf-8"))
        sizes[r["id"]] = (len(draft["tracks"]), sum(flag_of(t) != "none" for t in draft["tracks"]))
        if want and r["id"] not in want:
            continue
        out = OUT / "sheets" / r["id"]
        out.mkdir(parents=True, exist_ok=True)
        imgs = Images(draft)
        sh = tile_sheets(draft, imgs, out)
        fr = frame_sheets(draft, imgs, out)
        idx = {"round": r["id"], "split": r["split"], "round_name": r["round"], "counts": draft["counts"], "tile_sheets": sh, "frame_sheets": fr,
               "label_checks": [{k: c[k] for k in ("image", "label_src", "label_tiles", "missing_in_photo", "excess_in_runs", "hand_runs")} for c in draft["label_checks"]],
               "legend": "테두리 빨강 LABEL? = 정답과 어긋남 후보, 주황 SPLIT = 그림마다 읽기 갈림, 노랑 LOW = 확신 낮음, PREV(파랑) = 앞 판 탁자가 남은 그림에서만 보임"}
        (out / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
        rp = OUT / "review" / f"{r['id']}.json"
        if not rp.exists() or json.loads(rp.read_text(encoding="utf-8")).get("reviewer") is None:
            rp.write_text(json.dumps(review_form(draft, sh), ensure_ascii=False, indent=1), encoding="utf-8")
        print(r["id"], "칸", len(draft["tracks"]), "장", len(sh), "그림", len(fr), flush=True)
    sh = shares(sizes)
    (OUT / "review" / "_shares.json").write_text(json.dumps(sh, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(sh, ensure_ascii=False))


if __name__ == "__main__":
    main()
