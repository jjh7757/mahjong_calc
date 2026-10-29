"""도라 산(왕패) 위치를 Gemini 에게 찾게 하기(사용자 제안 2026-10-29: 판 시작 때 사진 전체로 도라를 까는 패산 구역을 잡아 두고,
리치 아닌 화료 때 그 구역만 잘라 도라를 읽기 — 화료 때 구조 잡기를 기다리지 않는다).

사진 전체(긴 변 1568)를 보내 왕패 상자를 받고, 손으로 잡은 정답 상자와 겹침을 잰다. B·C·D 6장 × 조건 × 회차.
Gemini 를 직접 부른다(서버 분당 제한을 피함).

  python -I -X utf8 experiments/speed/dora_locate.py [--runs 3] [--conds low,minimal,er2]

B·C·D 는 사용자가 간이로 연출한 판 끝 사진이라 왕패(연보라 L자 패산)는 6장 모두 왼쪽 아래 한 곳이다 — 이 세트로는 "패산 더미를
손패·강과 구별해 잡는가·몇 초·회차마다 같은가" 만 잰다. 판 시작 장면(네 변에 패산이 다 서 있고 그중 도라를 뒤집은 7줄)은 없다.
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from bench import call  # noqa: E402  (Gemini 직접 호출, .env 키)

from app import observe as ob  # noqa: E402  (bench 가 mahjong-recognizer 를 sys.path 에 넣는다)

ROOT = Path(__file__).parent
PHOTOS = ROOT.parent / "field_20261024" / "kakao_photos"
OUT = ROOT / "results"

# 정답: 왕패(연보라 L자 패산 + 거기 붙은 도라 표시패) 상자, 0~1000 [ymin, xmin, ymax, xmax]. 사진을 보고 손으로.
TRUTH = {
    "k25": [455, 223, 709, 389],
    "k28": [461, 235, 704, 393],
    "k15": [451, 214, 697, 414],
    "k26": [456, 210, 696, 405],
    "k12": [455, 205, 697, 341],
    "k16": [456, 201, 700, 339],
}

LOCATE_PROMPT = """이 사진은 리치마작 자동탁 전체를 위에서 찍은 것입니다. 왕패(도라 표시패를 뒤집어 놓는 패산 부분)가 있는 곳을 찾습니다.

- 패산: 뒷면(단색)이 보이게 2단으로 쌓인 패 더미. 판이 시작될 때는 네 변 앞에 하나씩 서 있고, 판이 진행되면 패를 가져가 짧아지며,
  판 끝에는 왕패와 남은 몇 줄만 한쪽에(모서리를 돌아 ㄱ자로 꺾일 수 있음) 남습니다.
- 왕패: 패산 중 도라 표시패가 앞면으로 뒤집혀 있는 7줄 부분. 판 끝에 남은 패산 더미는 왕패를 포함합니다.
  도라 표시패를 패산 옆으로 내려놓았으면 그 패도 상자에 넣습니다.
- 패산이 아닌 것: 각 자리 앞의 손패 줄(한 줄로 세워져 있거나 앞면으로 눕혀진 10~14장), 가운데 기기 둘레의 버림패(강) 줄,
  테이블 가장자리의 울기 묶음.
- box_2d: 왕패(판 끝이면 남은 패산 더미 전체)를 감싸는 상자 [ymin, xmin, ymax, xmax], 사진 크기를 0~1000 으로 본 정수.
  찾지 못하면 found=false, box_2d 는 빈 배열.
- side: 그 패산이 어느 자리 앞인지(bottom/right/top/left, 사진 기준). 두 변에 걸치면 더 긴 쪽."""

LOCATE_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "box_2d": {"type": "array", "items": {"type": "integer"}},
        "side": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["found", "box_2d"],
}

CONDS = {
    "low": {"model": "gemini-3.8-flash", "thinking": "low"},
    "minimal": {"model": "gemini-3.8-flash", "thinking": "minimal"},
    "er2": {"model": "gemini-robotics-er-2-preview", "thinking": "default"},
    # 서버 /v2/wall 프롬프트(블로그 규칙 단서: 7줄·ㄱ자·3번째 줄 앞면, 손패는 1단·패산은 2단)
    "server": {"model": "gemini-3.8-flash", "thinking": "low", "prompt": ob.WALL_PROMPT_V2, "schema": ob.WALL_SCHEMA_V2},
    # 같은 프롬프트, 왕패 한 줄 위에 七萬 을 붙인 합성 사진(make_dora_wall.py — 판 시작 때처럼 도라가 뒤집힌 왕패)
    "synth": {"model": "gemini-3.8-flash", "thinking": "low", "prompt": ob.WALL_PROMPT_V2, "schema": ob.WALL_SCHEMA_V2,
              "synth": True},
}
# 합성 사진의 도라 산 정답: 七萬 을 붙인 세로 일자 줄만(L자 가로 부분 제외, 사용자 2026-10-29 "도라 산은 일자 구역").
# 왕패 정답 상자(TRUTH)를 폭 400 으로 줄인 크롭에서 세로줄 둘레를 손으로 (x0, y0, x1, y1) 고른 뒤 0~1000 으로 바꾼다.
_LINE_CROP = {
    "k25": ((0, 0, 150, 395), 459), "k28": ((0, 0, 155, 405), 461), "k15": ((80, 0, 200, 318), 369),
    "k26": ((80, 0, 205, 320), 369), "k12": ((0, 0, 175, 480), 534), "k16": ((10, 0, 185, 470), 530),
}


def _line_truth(p: str) -> list[int]:
    (cx0, cy0, cx1, cy1), h = _LINE_CROP[p]
    y0, x0, y1, x1 = TRUTH[p]
    fx = lambda c: round(x0 + c / 400 * (x1 - x0))  # noqa: E731
    fy = lambda c: round(y0 + c / h * (y1 - y0))  # noqa: E731
    return [fy(cy0), fx(cx0), fy(cy1), fx(cx1)]


TRUTH_LINE = {p: _line_truth(p) for p in _LINE_CROP}
WALL_DORA_SYNTH = {p: ["7m"] for p in ["k25", "k28", "k15", "k26", "k12", "k16"]}  # C 는 왕패 옆 원래 七萬·6삭 도 크롭에 든다

# 왕패 크롭에서 읽을 도라 표시패 정답. B·D 는 사용자가 도라를 왕패 밖으로 옮겨 둔 연출이라 왕패에는 없다.
WALL_DORA = {"k25": [], "k28": [], "k15": ["7m", "6s"], "k26": ["7m", "6s"], "k12": [], "k16": []}
ROTATE = {"bottom": 0, "right": -90, "top": 180, "left": 90}  # 그 자리 사람이 아래로 오게(PIL 반시계 각도)


def jpeg(im: Image.Image, max_side: int) -> bytes:
    im = im.copy()
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90)
    return buf.getvalue()


def inter(a: list[int], b: list[int]) -> int:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def area(a: list[int]) -> int:
    return (a[2] - a[0]) * (a[3] - a[1])


def one(photo: str, cond: str, run: int, data: bytes) -> dict:
    c = CONDS[cond]
    loc = call(data, c.get("prompt", LOCATE_PROMPT), c.get("schema", LOCATE_SCHEMA), c["model"], c["thinking"], None)
    row = {"photo": photo, "cond": cond, "run": run, "s": loc["s"], "think": loc.get("think"), "in": loc.get("in")}
    if "error" in loc:
        return {**row, "error": loc["error"]}
    d = loc["data"]
    box = d.get("box_2d") or []
    row.update(found=d.get("found"), box=box, side=d.get("side"), notes=(d.get("notes") or "")[:150])
    if not d.get("found") or len(box) != 4 or box[0] >= box[2] or box[1] >= box[3]:
        return {**row, "iou": 0.0, "cover": 0.0}
    t = TRUTH_LINE[photo] if cond == "synth" else TRUTH[photo]
    i = inter(box, t)
    row["iou"] = round(i / (area(box) + area(t) - i), 2)
    row["cover"] = round(i / area(t), 2)  # 정답 넓이 중 찾은 상자에 든 비율
    if cond in ("server", "synth"):  # 앱처럼: 상자를 10% 넓혀 원본에서 자르고 그 자리 쪽으로 세워 /v2/walldora 프롬프트로
        full = (SYNTH if cond == "synth" else FULL)[photo]
        w, h = full.size
        p = int(max(box[2] - box[0], box[3] - box[1]) * 0.1)
        y0, x0, y1, x1 = max(0, box[0] - p), max(0, box[1] - p), min(1000, box[2] + p), min(1000, box[3] + p)
        crop = full.crop((x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000))
        crop = crop.rotate(ROTATE.get(d.get("side") or "bottom", 0), expand=True)
        rd = call(jpeg(crop, 1568), ob.WALLDORA_PROMPT_V2, ob.WALLDORA_SCHEMA_V2, "gemini-3.8-flash", "default", None)
        tiles = [] if "error" in rd else [x["tile"] for x in ob.normalize_dora_v2(rd["data"])["indicators"]]
        truth = (WALL_DORA_SYNTH if cond == "synth" else WALL_DORA)[photo]
        row.update(read_s=rd["s"], wall_dora=tiles, dora_ok=sorted(tiles) == sorted(truth))
    return row


FULL: dict[str, Image.Image] = {}
SYNTH: dict[str, Image.Image] = {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--conds", default="low,minimal,er2")
    a = ap.parse_args()
    conds = a.conds.split(",")
    for p in TRUTH:
        FULL[p] = Image.open(PHOTOS / f"{p}.jpg")
        FULL[p].load()
    data = {p: jpeg(FULL[p], 1568) for p in TRUTH}
    if "synth" in conds:
        for p in TRUTH:
            SYNTH[p] = Image.open(PHOTOS / "synth_wall" / f"{p}.jpg")
            SYNTH[p].load()
        sdata = {p: jpeg(SYNTH[p], 1568) for p in TRUTH}
    jobs = [(p, c, r) for r in range(1, a.runs + 1) for c in conds for p in TRUTH]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda j: one(*j, (sdata if j[1] == "synth" else data)[j[0]]), jobs))
    OUT.mkdir(exist_ok=True)
    out = OUT / "dora_wall_locate.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    p90 = lambda xs: sorted(xs)[int(0.9 * (len(xs) - 1))] if xs else 0  # noqa: E731
    for c in conds:
        rs = [r for r in rows if r["cond"] == c]
        ok = [r for r in rs if "error" not in r]
        s = [r["s"] for r in ok] or [0]
        good = [r for r in rs if r.get("cover", 0) >= 0.8 and r.get("iou", 0) >= 0.5]
        print(f"{c:8s} 잡음(덮음≥0.8·IoU≥0.5) {len(good)}/{len(rs)}, 덮음 중앙 {statistics.median([r.get('cover', 0) for r in rs]):.2f}, "
              f"IoU 중앙 {statistics.median([r.get('iou', 0) for r in rs]):.2f}, 오류 {len(rs) - len(ok)} | "
              f"{statistics.median(s):.1f}/{p90(s):.1f}/{max(s):.1f}초, 생각 중앙 {statistics.median([r.get('think') or 0 for r in ok]) if ok else 0}")
        if c in ("server", "synth"):
            rd = [r["read_s"] for r in rs if "read_s" in r] or [0]
            print(f"         왕패 도라 읽기 정답 {sum(bool(r.get('dora_ok')) for r in rs)}/{len(rs)} "
                  f"(C {sum(bool(r.get('dora_ok')) for r in rs if r['photo'] in ('k15', 'k26'))}/"
                  f"{sum(r['photo'] in ('k15', 'k26') for r in rs)}), 읽기 {statistics.median(rd):.1f}/{p90(rd):.1f}/{max(rd):.1f}초")
        # 회차마다 같은 곳을 주는지: 같은 사진의 상자들 사이 최소 IoU
        for p in TRUTH:
            bs = [r["box"] for r in rs if r["photo"] == p and len(r.get("box") or []) == 4]
            pair = [inter(x, y) / (area(x) + area(y) - inter(x, y)) for i, x in enumerate(bs) for y in bs[i + 1:]]
            if pair and min(pair) < 0.7:
                print(f"    {p}: 회차 사이 IoU 최소 {min(pair):.2f} ({bs})")
    for r in rows:
        if r.get("cover", 0) < 0.8 or r.get("iou", 0) < 0.5:
            t = TRUTH_LINE[r['photo']] if r['cond'] == 'synth' else TRUTH[r['photo']]
            print(f"  {r['cond']:8s} {r['photo']}#{r['run']} 상자 {r.get('box')} 정답 {t} 덮음 {r.get('cover')} "
                  f"IoU {r.get('iou')} {r.get('side')} {r.get('error', '')} {r.get('notes', '')}")
        elif r["cond"] in ("server", "synth") and not r.get("dora_ok"):
            print(f"  {r['cond']:8s} {r['photo']}#{r['run']} 왕패 도라 {r.get('wall_dora')} side {r.get('side')}")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
