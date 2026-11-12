"""2040 사본 크롭 만들기(2026-11-12, 계획서 `docs/cls_2040_plan_1112.md` 3-1, 1단계 "만들기"). API·학습 없음.

운영 분류기 cls6 의 미세 조정 재료(실제 축 크롭 1,548장 = data/index.json 259 + review.extra() 1,289)마다 원본 사진을
`overlay_score.shrink(data, 2040)` 과 같은 함수로 줄이고(exif_transpose → 긴 변 ÷ 2040 이 정수에 가까우면 Image.reduce, 아니면 BOX → JPEG 85),
원본 상자에 실제 줄인 비율을 곱해 원래 자른 코드(build_crops.cut / harvest.cut, 여유 PAD 0.12, 자리 크롭 돌림·harvest 돌림 turn 포함)로 다시 자른다.
라벨·나눔은 원본 것을 그대로 물려받는다(새 라벨 없음).

  python -I -X utf8 experiments/tile_classifier/half_crops.py build    # 자르기 재현 확인(1,548장 전부) → 사본(PNG) → index.json·report.json
  python -I -X utf8 experiments/tile_classifier/half_crops.py check    # 사후 검증(수·라벨·나눔·사본 크기·shrink 같음·원본과 닮음 지표) → report.json "check"
  python -I -X utf8 experiments/tile_classifier/half_crops.py sheets   # 독립 검토용 확인 그림(원본 | 2040 사본 | 키운 사본) → sheets/*.jpg·manifest.json

원본 사진 읽기는 원래 자를 때와 같게 `Image.open(p).convert("RGB")`(build_crops·harvest 는 exif_transpose 를 안 했다). 쓰인 사진 49장은
EXIF 방향 태그가 없거나 1 이라 shrink 의 exif_transpose 와 좌표가 같다 — build 가 사진마다 확인하고, 1 이 아니면 그 사진의 크롭을 뺀다.
결과 experiments/tile_classifier/data/half/{crops/*.png, index.json, report.json, sheets/}(커밋 안 함). 기존 data/ 파일은 읽기만.
"""
from __future__ import annotations

import ast
import io
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build_crops as bc  # noqa: E402  (bc.cut, bc.sg = seat_grow: crop·KAKAO·VISIT)
import harvest as hv  # noqa: E402  (hv.cut, hv._unrotate, hv.EXP)
import review as rw  # noqa: E402  (rw.extra)

sg = bc.sg
DATA = HERE / "data"
OUT = Path(os.environ.get("HALF_OUT") or DATA / "half")  # HALF_OUT: 코드 시험용 다른 곳(기본 data/half)
CROPS = OUT / "crops"
SHEETS = OUT / "sheets"
LONG = 2040
SMALL_TILE = 96  # 서버 app.local_read.SMALL_TILE(= CLS_SIZE 128 × 3 // 4), 계획서 2절 키워 읽기
MAX_DIFF = 2.0  # 재현 확인: 크기 같고 평균 화소 차(RGB 절댓값) ≤ 2
STOP_FRAC = 0.05  # 안 맞는 것이 이보다 많으면 사본을 안 만들고 멈춘다
OVERLAY = ROOT / "experiments/ondevice/overlay_score.py"


def shrink(data: bytes, long_side: int) -> tuple[bytes, tuple[int, int]]:
    """experiments/ondevice/overlay_score.py 의 shrink 를 글자 그대로 옮긴 것(그 파일은 ondevice·robust_suite 를 불러 무겁다).
    check 가 그 파일의 함수와 결과 바이트가 같은지 사진마다 대조한다."""
    import io
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    k = max(im.size) / long_side
    if k > 1:
        im = im.reduce(round(k)) if abs(k - round(k)) < 0.05 else im.resize((round(im.width / k), round(im.height / k)), Image.BOX)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), im.size


# ---------------------------------------------------------------- 재료 목록
def items() -> list[dict]:
    """학습 코드(train.main_synth)가 쓰는 1,548장: data/index.json(키 file, 나눔 part) + review.extra()(키 h_…/b_…, 나눔 half)."""
    out = []
    for x in json.loads((DATA / "index.json").read_text(encoding="utf-8")):
        s = x["scene"]
        photo = sg.KAKAO / f"{s}.jpg" if not s.startswith("2026") else sg.VISIT / s / "original.jpg"
        out.append(dict(src="base", file=x["file"], tile=x["tile"], part=x["part"], split=x["part"], photo=s, photo_path=photo,
                        stored=DATA / "crops" / x["file"], box=list(x["box"]), side=x["side"], seat_box=list(x["seat_box"]),
                        photo_size_index=list(x["photo"]), kind=x["kind"]))
    hv_rows = {r["file"]: r for r in json.loads((DATA / "harvest/index.json").read_text(encoding="utf-8"))}
    bl_rows = {r["file"]: r for r in json.loads((DATA / "harvest/blank/index.json").read_text(encoding="utf-8"))}
    for x in rw.extra():
        blank = x["file"].startswith("b_")
        r = (bl_rows if blank else hv_rows)[x["file"][2:]]
        assert r["photo"] == x["photo"]
        # harvest.py·harvest_blank.py 는 visit_20261031/captures(+ harvest 는 field_20261024/captures)의 */original.jpg 를 읽었다
        cands = [p for p in (hv.EXP / "visit_20261031/captures" / x["photo"] / "original.jpg", hv.EXP / "field_20261024/captures" / x["photo"] / "original.jpg") if p.exists()]
        out.append(dict(src="blank" if blank else "extra", file=x["file"], tile=x["tile"], half=x["half"], split=x["half"], photo=x["photo"],
                        photo_path=cands[0] if len(cands) == 1 else None, photo_cands=[str(p) for p in cands], stored=Path(x["path"]),
                        box=list(r["box"]), turn=None if blank else int(r["turn"])))
    for i, x in enumerate(out):
        x["idx"] = i
    return out


# ---------------------------------------------------------------- 자르기(원래 코드 그대로)
def seat_rect(seat_box, size) -> tuple[int, int, int, int]:
    """seat_grow.crop 이 자르는 사각형(돌리기 전, 사진 좌표)."""
    w, h = size
    y0, x0, y1, x1 = seat_box
    return round(x0 * w / 1000), round(y0 * h / 1000), round(x1 * w / 1000), round(y1 * h / 1000)


def rotate_box(b, side: str, cw: int, ch: int) -> tuple[int, int, int, int]:
    """harvest._unrotate 의 역: 돌리기 전 자리 크롭 좌표 상자 → seat_grow.crop 이 돌린(rotate(-ROT_CW, expand)) 크롭 좌표."""
    x, y, w, h = b
    r = sg.ROT_CW[side]
    if r == 0:
        return x, y, w, h
    if r == 90:  # 시계 90: (x, y) → (ch - y, x)
        return ch - (y + h), x, h, w
    if r == 180:
        return cw - (x + w), ch - (y + h), w, h
    return y, cw - (x + w), h, w  # 시계 270: (x, y) → (y, cw - x)


def full_box(x: dict, size) -> tuple[int, int, int, int]:
    """base 상자(돌린 자리 크롭 좌표) → 사진 좌표."""
    X0, Y0, X1, Y1 = seat_rect(x["seat_box"], size)
    bx, by, bw, bh = hv._unrotate(x["box"], x["side"], X1 - X0, Y1 - Y0)
    return X0 + bx, Y0 + by, bw, bh


def seat_box_of(x: dict, fb, size) -> tuple[int, int, int, int]:
    """사진 좌표 상자 → 그 크기 사진의 돌린 자리 크롭 좌표(full_box 의 역)."""
    X0, Y0, X1, Y1 = seat_rect(x["seat_box"], size)
    return rotate_box((fb[0] - X0, fb[1] - Y0, fb[2], fb[3]), x["side"], X1 - X0, Y1 - Y0)


def scale_box(b, rx: float, ry: float) -> tuple[int, int, int, int]:
    """상자 모서리(화소 경계)에 비율을 곱해 반올림(반은 올림)."""
    x0, y0 = math.floor(b[0] * rx + 0.5), math.floor(b[1] * ry + 0.5)
    x1, y1 = math.floor((b[0] + b[2]) * rx + 0.5), math.floor((b[1] + b[3]) * ry + 0.5)
    return x0, y0, x1 - x0, y1 - y0


def cut_one(x: dict, im: Image.Image, box) -> Image.Image:
    """원래 자른 방법: base = seat_grow.crop(자리 크롭, 돌림) → build_crops.cut, extra = harvest.cut → rotate(90·turn, expand), 白 = harvest.cut."""
    if x["src"] == "base":
        rgb = np.asarray(sg.crop(im, x["seat_box"], x["side"]))
        return bc.cut(rgb, tuple(box))
    c = hv.cut(np.asarray(im), tuple(box))
    return c.rotate(90 * x["turn"], expand=True) if x["src"] == "extra" else c


def mad(a: Image.Image, b: Image.Image) -> float:
    return float(np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).mean())


def dist(v: list[float]) -> dict:
    if not v:
        return {}
    s = sorted(v)
    return dict(n=len(s), median=round(statistics.median(s), 3), p90=round(s[min(len(s) - 1, int(0.9 * len(s)))], 3), min=round(s[0], 3), max=round(s[-1], 3))


def up(im: Image.Image) -> Image.Image:
    """키워 읽기 규칙(계획서 2절, 서버 read_small·overlay_score.small_up 과 같은 식): 긴 변 96 미만이면 긴 변 96 으로 BICUBIC."""
    if max(im.size) >= SMALL_TILE:
        return im
    s = SMALL_TILE / max(im.size)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)


def copy_name(file: str) -> str:
    return Path(file).stem + ".png"


# ---------------------------------------------------------------- build
def build() -> None:
    """--repro mad(기본, 계획서 기준: 크기 같고 평균 화소 차 ≤ 2) | bytes(다시 자른 크롭을 JPEG 92 로 저장한 바이트 = 저장된 크롭 파일, 쓰려면 검토자 결정 뒤).
    --repro-only: 재현 확인만 하고 report_repro_<기준>.json 에 적은 뒤 끝(사본·index.json 안 만듦)."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("--repro", choices=("mad", "bytes"), default="mad")
    ap.add_argument("--repro-only", action="store_true")
    a = ap.parse_args()
    repro_mode = a.repro
    sys.stdout.reconfigure(encoding="utf-8")
    its = items()
    by_photo: dict[str, list[dict]] = defaultdict(list)
    for x in its:
        x["status"], x["reason"] = None, None
        if x["photo_path"] is None:
            x["status"], x["reason"] = "dropped", "원본 사진 못 찾음" if not x.get("photo_cands") else "원본 사진 후보 여럿"
            continue
        by_photo[str(x["photo_path"])].append(x)
    # 1) 자르기 재현 확인(사본 전에 전부)
    photo_info = {}
    for p, xs in sorted(by_photo.items()):
        raw = Image.open(p)
        orient = raw.getexif().get(0x0112)
        im = raw.convert("RGB")
        photo_info[p] = dict(size=list(im.size), orient=orient)
        for x in xs:
            x["photo_size"] = list(im.size)
            if orient not in (None, 1):
                x["status"], x["reason"] = "dropped", f"EXIF 방향 {orient}(원래 자를 때는 안 돌림, shrink 는 돌림)"
                continue
            if x["src"] == "base" and list(im.size) != x["photo_size_index"]:
                x["status"], x["reason"] = "dropped", f"사진 크기 다름 {im.size} ≠ index {x['photo_size_index']}"
                continue
            if x["src"] == "base":  # 좌표 옮기기 검사: 사진 좌표 → 같은 크기 자리 크롭 좌표가 저장 상자로 돌아오는가
                x["box_full"] = list(full_box(x, im.size))
                if list(seat_box_of(x, x["box_full"], im.size)) != x["box"]:
                    x["status"], x["reason"] = "dropped", "좌표 옮기기 왕복 안 맞음"
                    continue
            else:
                x["box_full"] = x["box"]
            again = cut_one(x, im, x["box"])
            stored = Image.open(x["stored"]).convert("RGB")
            x["orig_size"] = list(stored.size)
            x["repro_size"] = list(again.size)
            # 참고 지표: 다시 자른 크롭을 원래 저장 설정(JPEG 품질 92, PIL 기본값)으로 저장한 바이트가 저장된 크롭 파일과 같은가
            buf = io.BytesIO()
            again.save(buf, format="JPEG", quality=92)
            x["repro_bytes_same"] = buf.getvalue() == Path(x["stored"]).read_bytes()
            if again.size != stored.size:
                x["status"], x["reason"] = "dropped", "재현 크기 다름"
                continue
            d = mad(again, stored)
            x["repro_diff"] = round(d, 4)
            x["_d"] = d
            if repro_mode == "mad" and d > MAX_DIFF:
                x["status"], x["reason"] = "dropped", "재현 화소 차 > 2"
            if repro_mode == "bytes" and not x["repro_bytes_same"]:
                x["status"], x["reason"] = "dropped", "재현 JPEG 92 바이트 다름"
        print("재현", Path(p).parent.name if Path(p).name == "original.jpg" else Path(p).stem, len(xs),
              "최대 차", max((x.get("repro_diff") or 0) for x in xs), flush=True)
    bad = [x for x in its if x["status"] == "dropped"]
    repro = dict(criterion=repro_mode, checked=len(its), ok=len(its) - len(bad), bad=len(bad), bad_by_reason=dict(Counter(x["reason"] for x in bad)),
                 size_same=sum(x.get("repro_size") == x.get("orig_size") and "orig_size" in x for x in its),
                 jpeg92_bytes_same=sum(bool(x.get("repro_bytes_same")) for x in its),
                 diff_over2=sum(x.get("_d", 0) > MAX_DIFF for x in its),
                 diff_all=dist([x["repro_diff"] for x in its if "repro_diff" in x]),
                 diff_by_src={s: dist([x["repro_diff"] for x in its if x["src"] == s and "repro_diff" in x]) for s in ("base", "extra", "blank")},
                 bad_list=[dict(idx=x["idx"], file=x["file"], reason=x["reason"], diff=x.get("repro_diff"), jpeg92_bytes_same=x.get("repro_bytes_same"),
                                size=x.get("orig_size"), again=x.get("repro_size")) for x in bad])
    print("재현 확인", json.dumps({k: v for k, v in repro.items() if k != "bad_list"}, ensure_ascii=False), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.repro_only:
        (OUT / f"report_repro_{repro_mode}.json").write_text(json.dumps(dict(repro=repro), ensure_ascii=False, indent=1), encoding="utf-8")
        return
    if len(bad) > STOP_FRAC * len(its):
        (OUT / "report.json").write_text(json.dumps(dict(stopped=f"안 맞음 {len(bad)}/{len(its)} > {STOP_FRAC:.0%}", repro=repro), ensure_ascii=False, indent=1), encoding="utf-8")
        print("멈춤: 안 맞는 크롭이 5% 를 넘음 — 사본 안 만듦", flush=True)
        return
    # 2) 2040 사본
    CROPS.mkdir(parents=True, exist_ok=True)
    for p, xs in sorted(by_photo.items()):
        todo = [x for x in xs if x["status"] is None]
        if not todo:
            continue
        W, H = photo_info[p]["size"]
        if max(W, H) <= LONG:
            for x in todo:
                x["status"], x["reason"] = "not_shrunk", f"원본 긴 변 {max(W, H)} ≤ {LONG}"
            continue
        jb, size = shrink(Path(p).read_bytes(), LONG)
        ims = Image.open(io.BytesIO(jb)).convert("RGB")
        assert ims.size == tuple(size)
        rx, ry = ims.width / W, ims.height / H
        photo_info[p].update(shrunk=list(ims.size), ratio=[rx, ry], method="reduce" if abs(max(W, H) / LONG - round(max(W, H) / LONG)) < 0.05 else "BOX")
        for x in todo:
            fb = scale_box(x["box_full"], rx, ry)
            box_s = seat_box_of(x, fb, ims.size) if x["src"] == "base" else fb
            c = cut_one(x, ims, box_s)
            name = copy_name(x["file"])
            c.save(CROPS / name, format="PNG")
            x.update(status="copy", shrunk_size=list(ims.size), ratio=[round(rx, 6), round(ry, 6)], box_full_s=list(fb), box_s=list(box_s),
                     copy_file="crops/" + name, copy_size=list(c.size))
        print("사본", Path(p).parent.name if Path(p).name == "original.jpg" else Path(p).stem, (W, H), "→", ims.size, len(todo), flush=True)
    # 3) index.json·report.json
    keep = ("idx", "src", "file", "tile", "part", "half", "split", "kind", "photo", "photo_size", "box", "box_full", "side", "seat_box", "turn",
            "status", "reason", "orig_size", "repro_diff", "shrunk_size", "ratio", "box_full_s", "box_s", "copy_file", "copy_size")
    rows = []
    for x in its:
        r = {k: x[k] for k in keep if k in x}
        r["photo_path"] = str(Path(x["photo_path"]).relative_to(ROOT)).replace("\\", "/") if x["photo_path"] else None
        rows.append(r)
    (OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    cp = [r for r in rows if r["status"] == "copy"]
    longs = [max(r["copy_size"]) for r in cp]
    rep = dict(
        made="2026-11-12", plan="docs/cls_2040_plan_1112.md 3-1", save_format="PNG(손실 없음)", long_side=LONG, small_tile=SMALL_TILE,
        counts=dict(total=len(rows), copy=len(cp), not_shrunk=sum(r["status"] == "not_shrunk" for r in rows), dropped=sum(r["status"] == "dropped" for r in rows)),
        repro=repro,
        copies_by_split=dict(sorted(Counter(r["split"] for r in cp).items())),
        copies_by_src=dict(Counter(r["src"] for r in cp)),
        copies_by_split_src={f"{s}/{k}": n for (s, k), n in sorted(Counter((r["split"], r["src"]) for r in cp).items())},
        copies_by_tile=dict(sorted(Counter(r["tile"] for r in cp).items())),
        copy_long=dict(median=statistics.median(longs), min=min(longs), max=max(longs), under96=sum(v < SMALL_TILE for v in longs),
                       under96_frac=round(sum(v < SMALL_TILE for v in longs) / len(longs), 4)) if longs else {},
        orig_long=dict(median=statistics.median(max(r["orig_size"]) for r in cp), min=min(max(r["orig_size"]) for r in cp), max=max(max(r["orig_size"]) for r in cp)) if cp else {},
        not_shrunk=[r["file"] for r in rows if r["status"] == "not_shrunk"],
        dropped=[dict(idx=r["idx"], file=r["file"], reason=r["reason"]) for r in rows if r["status"] == "dropped"],
        photos={str(Path(p).relative_to(ROOT)).replace("\\", "/"): v for p, v in sorted(photo_info.items())},
    )
    (OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k not in ("repro", "photos", "not_shrunk", "dropped")}, ensure_ascii=False))


# ---------------------------------------------------------------- check
def overlay_shrink():
    """overlay_score.py 에서 shrink 함수만 떼어 실행(그 파일의 무거운 import 없이)."""
    src = OVERLAY.read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "shrink")
    seg = ast.get_source_segment(src, fn)
    ns: dict = {}
    exec(compile("from __future__ import annotations\n" + seg, str(OVERLAY), "exec"), ns)
    return ns["shrink"], seg


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / d) if d else 0.0


def check() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    rep = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
    errs: list[str] = []
    its = items()
    # 수
    c = Counter(r["status"] for r in rows)
    if len(rows) != len(its) or len(rows) != c["copy"] + c["not_shrunk"] + c["dropped"]:
        errs.append(f"수 안 맞음 rows {len(rows)} items {len(its)} {dict(c)}")
    if len({r["file"] for r in rows}) != len(rows):
        errs.append("file 키 겹침")
    # 라벨·나눔이 지금 원본(data/index.json · review.extra())과 같은가
    cur = {x["file"]: x for x in its}
    lab_bad = [r["file"] for r in rows if r["file"] not in cur or r["tile"] != cur[r["file"]]["tile"]]
    split_bad = [r["file"] for r in rows if r["file"] not in cur or r["split"] != cur[r["file"]]["split"]
                 or r.get("part", r.get("half")) != cur[r["file"]].get("part", cur[r["file"]].get("half"))]
    if lab_bad:
        errs.append(f"라벨 다름 {lab_bad[:10]}")
    if split_bad:
        errs.append(f"나눔 다름 {split_bad[:10]}")
    # shrink 가 overlay_score.shrink 와 같은가(소스 글자 + 사진마다 결과 바이트)
    osh, seg = overlay_shrink()
    import inspect
    import textwrap

    def body(src: str) -> str:  # 문서 문자열을 뺀 함수 몸통의 구문 나무
        fn = ast.parse(textwrap.dedent(src)).body[0]
        b = fn.body[1:] if isinstance(fn.body[0], ast.Expr) and isinstance(fn.body[0].value, ast.Constant) else fn.body
        return ast.dump(ast.Module(body=b, type_ignores=[])) + ast.dump(fn.args)
    same_src = body(inspect.getsource(shrink)) == body(seg)
    photos = sorted({r["photo_path"] for r in rows if r["status"] == "copy"})
    byte_diff = []
    for p in photos:
        data = (ROOT / p).read_bytes()
        if shrink(data, LONG) != osh(data, LONG):
            byte_diff.append(p)
    if byte_diff:
        errs.append(f"shrink 결과 다름 {byte_diff}")
    # 사본 파일·크기, 원본과 닮음(사본을 원본 크롭 크기로 BICUBIC 키워 비교)
    sims = []
    for r in rows:
        if r["status"] != "copy":
            continue
        f = OUT / r["copy_file"]
        if not f.exists():
            errs.append(f"사본 없음 {f.name}")
            continue
        cim = Image.open(f).convert("RGB")
        if list(cim.size) != r["copy_size"]:
            errs.append(f"사본 크기 다름 {f.name}")
        x = cur[r["file"]]
        oim = Image.open(x["stored"]).convert("RGB")
        upc = cim.resize(oim.size, Image.BICUBIC)
        g1 = np.asarray(oim.convert("L"), np.float64)
        g2 = np.asarray(upc.convert("L"), np.float64)
        # 방향 확인: 180° 돌린 사본과의 상관이 더 높으면 방향이 뒤집힌 것
        n0 = ncc(g1, g2)
        n180 = ncc(g1, g2[::-1, ::-1])
        sims.append(dict(idx=r["idx"], file=r["file"], tile=r["tile"], ncc=round(n0, 4), ncc_rot180=round(n180, 4), mad=round(mad(oim, upc), 2),
                         orig=r["orig_size"], copy=r["copy_size"], ratio=r["ratio"][0], aspect_diff=round(abs(r["copy_size"][0] / r["copy_size"][1] - r["orig_size"][0] / r["orig_size"][1]), 3)))
    low = sorted(sims, key=lambda s: s["ncc"])[:30]
    flipped = [s for s in sims if s["ncc_rot180"] > s["ncc"]]
    # 사본 크기 = 원본 크기 × 비율(±2px) 인가
    size_off = [s for s in sims if any(abs(c - o * s["ratio"]) > 2 for c, o in zip(s["copy"], s["orig"]))]
    res = dict(errors=errs, ok=not errs, counts=dict(c), label_same=not lab_bad, split_same=not split_bad, shrink_source_same=same_src,
               shrink_bytes_same=f"{len(photos) - len(byte_diff)}/{len(photos)}", copies_checked=len(sims),
               ncc=dist([s["ncc"] for s in sims]), mad_up=dist([s["mad"] for s in sims]), rot180_higher=len(flipped), rot180_list=flipped[:30],
               size_off_from_half=len(size_off), size_off_list=size_off[:30], low30_ncc=low)
    rep["check"] = res
    (OUT / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("low30_ncc", "rot180_list", "size_off_list")}, ensure_ascii=False, indent=1))
    print("낮은 쪽 10", [(s["idx"], s["file"], s["tile"], s["ncc"], s["mad"]) for s in low[:10]])


# ---------------------------------------------------------------- sheets
def font(size: int, bold: bool = False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "malgun.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def sheets(cols: int = 8, lines: int = 9, pw: int = 80, ph: int = 104) -> None:
    """종류 순서(train.CLASSES — harvest 에서 불러온 tr)로 이어 붙여 한 장 cols×lines(72)칸. 칸 = [원본 | 2040 사본 NEAREST | 키운 사본 NEAREST],
    세 조각은 같은 표시 크기(원본 크롭을 pw×ph 안에 맞춘 크기). 번호 = index.json 의 idx. 종류가 바뀌면 이름 띠 색이 바뀐다."""
    sys.stdout.reconfigure(encoding="utf-8")
    rows = [r for r in json.loads((OUT / "index.json").read_text(encoding="utf-8")) if r["status"] == "copy"]
    cur = {x["file"]: x for x in items()}
    order = {t: i for i, t in enumerate(hv.tr.CLASSES)}
    rows.sort(key=lambda r: (order[r["tile"]], r["idx"]))
    SHEETS.mkdir(parents=True, exist_ok=True)
    for f in SHEETS.glob("sheet_*.jpg"):
        f.unlink()
    gap, lab_h, head_h = 6, 30, 40
    cw = 3 * pw + 2 * 3 + gap * 2
    chh = ph + lab_h + gap
    f_num, f_head = font(22, True), ImageFont.truetype("malgun.ttf", 20) if Path("C:/Windows/Fonts/malgun.ttf").exists() else font(20)
    tones = [(255, 236, 160), (170, 220, 255)]
    per = cols * lines
    manifest = []
    tone_of, k = {}, 0
    for t in sorted({r["tile"] for r in rows}, key=order.get):
        tone_of[t] = tones[k % 2]
        k += 1
    for si in range(0, len(rows), per):
        part = rows[si:si + per]
        n_lines = (len(part) + cols - 1) // cols
        im = Image.new("RGB", (cols * cw + gap, head_h + n_lines * chh + gap), "white")
        d = ImageDraw.Draw(im)
        d.text((gap, 6), f"sheet {si // per:02d}  칸 = [원본 크롭 | 2040 사본(NEAREST 확대) | 키워 읽기(긴 변<96 → 96 BICUBIC) 사본]  번호 = data/half/index.json idx",
               fill="black", font=f_head)
        for i, r in enumerate(part):
            x0, y0 = gap + (i % cols) * cw, head_h + (i // cols) * chh
            o = Image.open(cur[r["file"]]["stored"]).convert("RGB")
            c = Image.open(OUT / r["copy_file"]).convert("RGB")
            s = min(pw / o.width, ph / o.height)
            disp = (max(1, round(o.width * s)), max(1, round(o.height * s)))
            panels = [o.resize(disp, Image.LANCZOS), c.resize(disp, Image.NEAREST), up(c).resize(disp, Image.NEAREST)]
            for j, pnl in enumerate(panels):
                px = x0 + j * (pw + 3) + (pw - disp[0]) // 2
                py = y0 + (ph - disp[1]) // 2
                d.rectangle((x0 + j * (pw + 3) - 1, y0 - 1, x0 + j * (pw + 3) + pw, y0 + ph), outline=(200, 200, 200))
                im.paste(pnl, (px, py))
            d.rectangle((x0 - 1, y0 + ph + 1, x0 + 3 * pw + 6, y0 + ph + lab_h - 2), fill=tone_of[r["tile"]])
            small = "" if max(r["copy_size"]) >= SMALL_TILE else "↑"
            d.text((x0 + 3, y0 + ph + 2), f"#{r['idx']}  {r['tile']}", fill="black", font=f_num)
            d.text((x0 + 3 * pw - 70, y0 + ph + 6), f"{r['copy_size'][0]}x{r['copy_size'][1]}{small}", fill=(90, 90, 90), font=font(15))
        name = f"sheet_{si // per:02d}.jpg"
        im.save(SHEETS / name, quality=92)
        manifest.append(dict(sheet=name, cells=len(part), idx=[r["idx"] for r in part], tiles=dict(Counter(r["tile"] for r in part)),
                             first=f"#{part[0]['idx']} {part[0]['tile']}", last=f"#{part[-1]['idx']} {part[-1]['tile']}"))
        print(name, len(part), manifest[-1]["first"], "~", manifest[-1]["last"], flush=True)
    (SHEETS / "manifest.json").write_text(json.dumps(dict(made="2026-11-12", cells=len(rows), per_sheet=per, sheets=manifest,
                                                          note="칸 순서 = 종류(train.CLASSES) 다음 idx. 아래 회색 글자 = 사본 크기, ↑ = 긴 변 96 미만이라 셋째 조각을 키움"),
                                                     ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"build": build, "check": check, "sheets": sheets}.get(cmd, lambda: print(__doc__))()
