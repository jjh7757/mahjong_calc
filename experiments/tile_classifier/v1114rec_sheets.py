"""녹화 프레임(rec1496) 패 종류 눈 확인용 대조표·검토 양식·몫 나누기(2026-11-15, 녹화 세트 2단계 3). v1114rec_draft.py 다음에.

v1114_sheets.py 와 같은 꼴. 다른 점: 그림이 1496(패 긴 변 약 65px)이라 칸의 크롭을 키운다(왼쪽 크롭 높이 250px = 패 긴 변 화면 약 200px,
둘레 그림도 220px 로 키움). 나(mid)의 칸에는 초안 출처를 적는다 — 초록 NB(prev|next|both) = 기존 세트 이웃 최종 라벨에서 옮긴 초안,
회색 CLS = 분류기 투표 초안. 보라 테두리 NB? = 분류기 읽기와 이웃 라벨이 다르거나 앞·뒤 이웃이 갈림.
data/v1114rec/sheets/<판>/
  tiles_NN.jpg  실물 패마다 한 칸(4×5 = 20칸/장). [왼쪽] 가장 선명한 1496 크롭을 분류기가 읽은 방향으로 세워 키움 [오른쪽] 같은 그림 둘레(패 3배 범위,
                원래 방향, 노란 테두리 = 그 상자). 글: #실물 패 id, 초안 종류, 확신도(분류기 투표 쪽), 출처, n=나온 그림 수, 그림별 읽기 수, 이웃 라벨, 표시.
                테두리: 보라 = NB?, 주황 = SPLIT(그림마다 읽기 갈림), 노랑 = LOW(확신 < 0.8), 회색 = 표시 없음. 표시 있는 칸이 앞 장에 먼저.
  frames/<그림 이름>.jpg  그림(패 있는 곳만 잘라 긴 변 1800 으로 키움)에 상자와 실물 패 id(초록 바탕 글 = NB 초안). 색은 위와 같음.
  index.json
data/v1114rec/review/<판>.json  빈 양식(이미 reviewer 가 적힌 것은 안 덮음), review/_FORMAT.json, review/_shares.json(3몫, 판 단위, 그림 수·실물 패 수 비슷하게).
  python -X utf8 experiments/tile_classifier/v1114rec_sheets.py [판 id ...]
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

R = HERE / "data" / "v1114rec"
COLS, ROWS = 4, 5
CW, CH = 470, 400
TILE_H, TILE_W = 250, 200
CTX = 220
FONT = "C:/Windows/Fonts/arial.ttf"
FONTB = "C:/Windows/Fonts/arialbd.ttf"
COLOR = {"nbq": (160, 0, 210), "split": (255, 140, 0), "low": (230, 200, 0), "none": (150, 150, 150)}
NBG = (0, 150, 60)
ORDER = {c: i for i, c in enumerate(lr.CLASSES)}
SHARES = ("P1", "P2", "P3")


def font(size, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, size)


def flag_of(t: dict) -> str:
    return "nbq" if t.get("nb_q") else "split" if t["split"] else "low" if t["low"] else "none"


def crop_tile(rgb: np.ndarray, b: dict) -> Image.Image:
    (cx, cy), (w, h), a = b["rect"]
    im = obb.upright(rgb, ((cx, cy), (w, h), a), lr.PAD)
    return im.rotate(90 * b["rot"], expand=True)


def context(rgb: np.ndarray, b: dict, side: int = CTX) -> Image.Image:
    x, y, w, h = b["box"]
    H, W = rgb.shape[:2]
    R_ = int(max(w, h) * 1.5)
    cx, cy = x + w // 2, y + h // 2
    x0, y0 = max(0, cx - R_), max(0, cy - R_)
    part = Image.fromarray(rgb[y0:min(H, cy + R_), x0:min(W, cx + R_)]).copy()
    s = side / max(part.size)
    part = part.resize((max(1, round(part.width * s)), max(1, round(part.height * s))), Image.LANCZOS)
    d = ImageDraw.Draw(part)
    d.rectangle(((x - x0) * s, (y - y0) * s, (x - x0 + w) * s, (y - y0 + h) * s), outline=(255, 230, 0), width=3)
    return part


class Images:
    def __init__(self, draft):
        self.by = {im["id"]: im for im in draft["images"]}
        self.cache = {}

    def rgb(self, iid):
        if iid not in self.cache:
            if len(self.cache) > 3:
                self.cache.pop(next(iter(self.cache)))
            self.cache[iid] = np.asarray(Image.open(R / self.by[iid]["path"]).convert("RGB"))
        return self.cache[iid]

    def box(self, iid, i):
        return next(b for b in self.by[iid]["boxes"] if b["i"] == i)


def src_tag(t: dict) -> str:
    if t.get("draft_src") == "nb":
        return "NB"
    return "CLS"


def tile_sheets(draft: dict, imgs: Images, out: Path) -> list[dict]:
    mid = draft["part"] == "mid"
    tracks = sorted(draft["tracks"], key=lambda t: ({"nbq": 0, "split": 1, "low": 2, "none": 3}[flag_of(t)], ORDER.get(t["draft"], 99), t["tid"]))
    need = {}
    for t in tracks:
        need.setdefault(t["best"]["image"], []).append(t)
    cells = {}
    for iid, ts in need.items():
        rgb = imgs.rgb(iid)
        for t in ts:
            b = imgs.box(iid, t["best"]["i"])
            cells[t["tid"]] = (crop_tile(rgb, b), context(rgb, b), b)
    per = COLS * ROWS
    sheets = []
    f1, f2, f3 = font(30, True), font(19), font(19, True)
    for s in range(0, len(tracks), per):
        part = tracks[s:s + per]
        sheet = Image.new("RGB", (COLS * CW, ROWS * CH + 40), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        no = s // per + 1
        d.text((10, 8), f"{draft['round']} ({draft['part']}, {draft['split']})  tiles {s + 1}-{s + len(part)} / {len(tracks)}   sheet {no}"
                        + ("   green NB = draft from v1114 neighbour label, grey CLS = classifier vote, purple NB? = they disagree" if mid else ""),
               fill=(0, 0, 0), font=f3)
        for k, t in enumerate(part):
            cx0, cy0 = (k % COLS) * CW, 40 + (k // COLS) * CH
            fl = flag_of(t)
            d.rectangle((cx0 + 3, cy0 + 3, cx0 + CW - 4, cy0 + CH - 4), outline=COLOR[fl], width=7 if fl != "none" else 2)
            tim, ctx, b = cells[t["tid"]]
            s_ = TILE_H / tim.height
            if tim.width * s_ > TILE_W:
                s_ = TILE_W / tim.width
            tim = tim.resize((max(1, round(tim.width * s_)), max(1, round(tim.height * s_))), Image.LANCZOS)
            sheet.paste(tim, (cx0 + 12 + (TILE_W - tim.width) // 2, cy0 + 12 + (TILE_H - tim.height) // 2))
            sheet.paste(ctx, (cx0 + 22 + TILE_W, cy0 + 12 + (TILE_H - ctx.height) // 2))
            y = cy0 + TILE_H + 18
            d.text((cx0 + 12, y), f"#{t['tid']}  {t['draft']}", fill=(0, 0, 0), font=f1)
            if mid:
                tag = src_tag(t)
                tb = d.textbbox((cx0 + 210, y + 4), tag, font=f3)
                d.rectangle((tb[0] - 4, tb[1] - 3, tb[2] + 4, tb[3] + 3), fill=NBG if tag == "NB" else (120, 120, 120))
                d.text((cx0 + 210, y + 4), tag, fill=(255, 255, 255), font=f3)
            d.text((cx0 + 300, y + 6), f"cls {t['cls_draft']} {t['conf']:.2f}", fill=(40, 40, 40), font=f2)
            reads = " ".join(f"{a}x{n}" for a, n in sorted(t["reads"].items(), key=lambda x: -x[1]))
            d.text((cx0 + 12, y + 36), f"n={t['n']}  cls reads {reads}"[:44], fill=(40, 40, 40), font=f2)
            if mid:
                nbr = " ".join(f"{a}x{n}" for a, n in sorted(t.get("nb_reads", {}).items(), key=lambda x: -x[1])) or "-"
                d.text((cx0 + 12, y + 58), f"nb labels {nbr}"[:44], fill=NBG if t.get("nb_reads") else (120, 120, 120), font=f2)
            tags = [x for x, on in (("NB?", t.get("nb_q")), ("SPLIT", t["split"]), ("LOW", t["low"])) if on]
            if tags:
                d.text((cx0 + 12, y + 82), " ".join(tags), fill=COLOR[fl], font=f3)
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
        base = Image.open(R / im["path"]).convert("RGB")
        W, H = base.size
        bs = im["boxes"]
        if bs:
            x0 = max(0, min(b["box"][0] for b in bs) - 75)
            y0 = max(0, min(b["box"][1] for b in bs) - 75)
            x1 = min(W, max(b["box"][0] + b["box"][2] for b in bs) + 75)
            y1 = min(H, max(b["box"][1] + b["box"][3] for b in bs) + 75)
        else:
            x0, y0, x1, y1 = 0, 0, W, H
        part = base.crop((x0, y0, x1, y1))
        s = 1800 / max(part.size)
        part = part.resize((round(part.width * s), round(part.height * s)), Image.LANCZOS)
        d = ImageDraw.Draw(part)
        for b in bs:
            t = by_tid[b["track"]]
            fl = flag_of(t)
            x, y, w, h = ((b["box"][0] - x0) * s, (b["box"][1] - y0) * s, b["box"][2] * s, b["box"][3] * s)
            d.rectangle((x, y, x + w, y + h), outline=COLOR[fl] if fl != "none" else (0, 200, 255), width=3)
            tb = d.textbbox((x + 2, y + 2), t["tid"], font=fs)
            d.rectangle(tb, fill=NBG if t.get("draft_src") == "nb" else (0, 0, 0))
            d.text((x + 2, y + 2), t["tid"], fill=(255, 255, 255), font=fs)
        tag = f"{im['id']}  {im['part']}  boxes {len(bs)}" + (f"  phase hint {im['phase_hint']}" if im.get("phase_hint") else "") + ("  SETUP" if im.get("setup") else "")
        tb = d.textbbox((8, 8), tag, font=font(24, True))
        d.rectangle(tb, fill=(255, 255, 255))
        d.text((8, 8), tag, fill=(0, 0, 0), font=font(24, True))
        name = Path(im["name"]).stem + ".jpg"
        part.save(out / "frames" / name, quality=88)
        res.append({"file": f"frames/{name}", "image": im["id"], "boxes": len(bs), "crop_1496": [x0, y0, x1, y1], "scale": round(s, 4)})
    return res


FORMAT = {
    "what": "녹화 프레임(rec1496) 패 종류 눈 확인 결과. 판마다 review/<판 id>.json 하나. 대조표 sheets/<판 id>/tiles_NN.jpg 의 칸(#실물 패 id)을 보고 tracks 의 칸을 채운다. "
            "꼴은 기존 data/v1114/review/_FORMAT.json 과 같고, 나(mid)에 이웃 라벨 칸이 더 있다.",
    "fields": {
        "reviewer": "검토한 에이전트 이름(예: P1)",
        "done": "판 전체를 다 봤으면 true",
        "tracks[].tid": "실물 패 id(대조표 칸의 #번호, 프레임 그림 상자 위 번호)",
        "tracks[].draft": "초안 종류(바꾸지 말 것 — 참고용). 나(mid)는 draft_src 가 nb 면 기존 세트 앞·뒤 이웃 그림의 눈 확인 끝난 라벨을 자리로 옮긴 것, cls 면 분류기 투표",
        "tracks[].draft_src": "nb | cls (참고용)",
        "tracks[].cls_draft": "분류기 투표 1순위(참고용). draft 와 다르면 NB? 표시",
        "tracks[].nb_reads": "이 실물 패 상자들에 옮겨진 이웃 라벨 {종류: 상자 수}(참고용)",
        "tracks[].flags": "초안 표시: nb? = 분류기 읽기와 이웃 라벨이 다름(또는 앞·뒤 이웃이 갈림 — 이웃 자리 맞대기가 어긋났을 수도), split = 그림마다 읽기 갈림, low = 확신 낮음",
        "tracks[].verdict": "ok = 초안(draft)이 맞음 / fix = 초안이 틀림, tile 에 맞는 종류 / not_tile = 앞면 패가 아님(뒷면·세운 패·패 일부만·손·다른 물건) / "
                            "mixed = 한 id 에 다른 패가 섞여 이어짐(프레임 그림에서 확인, per_image 에 그림별 종류) / unsure = 흐림·가림으로 모르겠음(note 필수)",
        "tracks[].tile": "verdict 가 fix 일 때 맞는 종류. 표기: 1m~9m·1p~9p·1s~9s, 적5 = 0m·0p·0s, 자패 1z 동 2z 남 3z 서 4z 북 5z 백 6z 발 7z 중",
        "tracks[].per_image": "verdict 가 mixed 일 때만: {그림 id: 종류 또는 'not_tile'}. 그림 id 는 draft 의 apps[].image",
        "tracks[].note": "자유 메모(짧게)",
        "missed": "상자가 없는데 앞면이 보이는 패(선택): [{image: 그림 id, near_tid: 가까운 실물 패 id, tile: 종류, note}]",
        "image_notes": "그림 전체에 대한 메모(선택): [{image, note}] — 예: 손이 탁자를 가림, 카메라 거치 중, 배패 중",
    },
    "rules": [
        "라벨 대상은 앞면이 보이는 패 전부(강·울기·공개된 손패·도라 표시패). 뒷면·세운 패는 not_tile.",
        "NB(이웃 라벨) 초안도 그대로 믿지 말고 크롭을 본다 — 1분쯤 사이에 패가 옮겨졌거나(강이 늘어남·울기) 카메라 밀림 맞대기가 한 칸 어긋나면 엉뚱한 종류가 붙는다.",
        "적5(빨간 5)와 그냥 5 를 꼭 가른다. 빨간 점·빨간 무늬가 보이면 0m·0p·0s. 녹화는 1496 이라 작다 — 둘레 그림·프레임 그림도 같이 본다.",
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
        fl = [x for x, on in (("nb?", t.get("nb_q")), ("split", t["split"]), ("low", t["low"])) if on]
        rows.append({"tid": tid, "draft": t["draft"], "draft_src": t["draft_src"], "cls_draft": t["cls_draft"], "nb_reads": t.get("nb_reads") or {},
                     "flags": fl, "sheet": where[tid], "verdict": None, "tile": None, "per_image": None, "note": ""})
    return {"round": draft["round"], "part": draft["part"], "split": draft["split"], "reviewer": None, "done": False, "tracks": rows, "missed": [], "image_notes": []}


def balance(sizes: dict, names: tuple, keys: tuple, extra: tuple = ()) -> dict:
    """판 단위 몫 나누기(한 판은 한 몫에만): 큰 판부터 가장 가벼운 몫에(keys 비율 합) → 판 옮기기·맞바꾸기로
    몫마다 keys 비율이 1/k 에서 벗어난 제곱합을 더 못 줄일 때까지 다듬는다. 정해진 순서라 다시 돌려도 같다."""
    k = len(names)
    tot = {q: (sum(v[q] for v in sizes.values()) or 1) for q in keys}
    w = lambda v: sum(v[q] / tot[q] for q in keys)
    asg = {}
    load = {n: {q: 0 for q in keys} for n in names}
    for rid, v in sorted(sizes.items(), key=lambda x: (-w(x[1]), x[0])):
        n = min(names, key=lambda n: (sum(load[n][q] / tot[q] for q in keys), names.index(n)))
        asg[rid] = n
        for q in keys:
            load[n][q] += v[q]

    def cost(ld):
        return sum((ld[n][q] / tot[q] - 1 / k) ** 2 for n in names for q in keys)

    def moved(ld, rid, a, b):
        ld2 = {n: dict(x) for n, x in ld.items()}
        for q in keys:
            ld2[a][q] -= sizes[rid][q]
            ld2[b][q] += sizes[rid][q]
        return ld2

    for _ in range(200):
        best = (cost(load), None)
        rids = sorted(asg)
        for r1 in rids:
            for n in names:
                if n != asg[r1]:
                    c = cost(moved(load, r1, asg[r1], n))
                    if c < best[0] - 1e-12:
                        best = (c, ("move", r1, n))
            for r2 in rids:
                if r2 > r1 and asg[r2] != asg[r1]:
                    c = cost(moved(moved(load, r1, asg[r1], asg[r2]), r2, asg[r2], asg[r1]))
                    if c < best[0] - 1e-12:
                        best = (c, ("swap", r1, r2))
        if best[1] is None:
            break
        if best[1][0] == "move":
            _, r1, n = best[1]
            load = moved(load, r1, asg[r1], n)
            asg[r1] = n
        else:
            _, r1, r2 = best[1]
            a, b = asg[r1], asg[r2]
            load = moved(moved(load, r1, a, b), r2, b, a)
            asg[r1], asg[r2] = b, a
    bins = {n: {"rounds": sorted(r for r, m in asg.items() if m == n)} for n in names}
    for n, b in bins.items():
        for q in tuple(keys) + tuple(extra):
            b[q] = sum(sizes[r][q] for r in b["rounds"])
    return bins


def shares(sizes: dict) -> dict:
    """판 단위 3몫: 그림 수·실물 패 수(칸 수)가 비슷하게."""
    return balance(sizes, SHARES, ("images", "tracks"), ("boxes", "flagged"))


def main():
    want = set(sys.argv[1:])
    (R / "review").mkdir(parents=True, exist_ok=True)
    (R / "review" / "_FORMAT.json").write_text(json.dumps(FORMAT, ensure_ascii=False, indent=1), encoding="utf-8")
    sizes = {}
    for p in sorted((R / "draft").glob("[rn]*.json")):
        draft = json.loads(p.read_text(encoding="utf-8"))
        rid = draft["round"]
        sizes[rid] = {"images": len(draft["images"]), "tracks": len(draft["tracks"]), "boxes": draft["counts"]["boxes"],
                      "flagged": sum(flag_of(t) != "none" for t in draft["tracks"])}
        if want and rid not in want:
            continue
        out = R / "sheets" / rid
        out.mkdir(parents=True, exist_ok=True)
        imgs = Images(draft)
        sh = tile_sheets(draft, imgs, out) if draft["tracks"] else []
        fr = frame_sheets(draft, imgs, out)
        idx = {"round": rid, "part": draft["part"], "split": draft["split"], "counts": draft["counts"], "tile_sheets": sh, "frame_sheets": fr,
               "legend": "테두리 보라 NB? = 분류기와 이웃 라벨이 다름, 주황 SPLIT = 그림마다 읽기 갈림, 노랑 LOW = 확신 낮음. 초록 NB = 이웃 라벨 초안, 회색 CLS = 분류기 초안."}
        (out / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
        rp = R / "review" / f"{rid}.json"
        if not rp.exists() or json.loads(rp.read_text(encoding="utf-8")).get("reviewer") is None:
            rp.write_text(json.dumps(review_form(draft, sh), ensure_ascii=False, indent=1), encoding="utf-8")
        print(rid, "칸", len(draft["tracks"]), "장", len(sh), "그림", len(fr), flush=True)
    if not want:
        sh = shares(sizes)
        (R / "review" / "_shares.json").write_text(json.dumps({"_note": "패 종류 눈 확인 3몫(판 단위, 한 판은 한 몫에만). tracks = 실물 패 수(칸 수), boxes = 앞면 상자 수. v1114rec_sheets.py",
                                                               "shares": sh}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: {kk: v[kk] for kk in ("images", "tracks", "boxes", "flagged")} for k, v in sh.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
