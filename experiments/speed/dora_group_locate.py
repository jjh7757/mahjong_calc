"""도라 산(왕패 상자)을 못 잡은 판의 도라 찾기 (2): 화료 사진 전체에서 펠트 위 앞면 도라 표시패 묶음 상자를 찾고, 원본에서 잘라 읽는다.
사용자 제안(2026-10-29 "화료자 손패 구역뿐 아니라 다른 영역도"). (1) 가운데 칸 도라 크롭을 넓히는 앱 흐름과 같은 시각에 비교.

  python -I -X utf8 experiments/speed/dora_group_locate.py [--runs 3]

B·C·D 는 사용자가 도라 표시패를 장면마다 다른 곳(B 가운데 위, C 왼쪽 L자 끝, D 오른쪽 아래 펠트)에 놓은 연출이라 이 경우를 재기에 맞다.
찾기 = 사진 긴 변 1568, gemini-3.8-flash 생각 low. 읽기 = 상자를 50% 넓혀 원본에서 자른 것, 기본 생각(서버 /v2/dora 와 같은 설정).
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
from bench import call  # noqa: E402

from app import observe as ob  # noqa: E402

ROOT = Path(__file__).parent
PHOTOS = ROOT.parent / "field_20261024" / "kakao_photos"
OUT = ROOT / "results"

# 정답: 도라 표시패 묶음 상자(0~1000 [ymin, xmin, ymax, xmax])·표시패
TRUTH = {
    "k25": ([133, 300, 176, 345], ["1z", "7m"]),
    "k28": ([156, 312, 194, 354], ["1z", "7m"]),
    "k15": ([618, 214, 691, 250], ["7m", "6s"]),
    "k26": ([620, 210, 690, 249], ["7m", "6s"]),
    "k12": ([639, 655, 697, 744], ["4p", "4p", "7m"]),
    "k16": ([640, 658, 694, 744], ["4p", "4p", "7m"]),
}

LOCATE_PROMPT = """이 사진은 리치마작 자동탁 전체를 위에서 찍은 것입니다. 도라 표시패가 놓인 곳을 찾습니다.

- 도라 표시패: 앞면(그림이 보이게)으로 놓인 패 1~6장의 작은 묶음. 패산(뒷면이 보이는 더미) 위나 바로 옆, 또는 펠트 위에 따로 놓입니다.
- 다음은 도라 표시패가 아닙니다: 각 자리 앞의 손패 줄(10~14장), 가운데 기기 둘레의 버림패(강) 줄, 뒷면만 보이는 패산,
  테이블 가장자리의 울기 묶음. 울기 묶음은 퐁·치·깡 모양(같은 패 3~4장, 또는 같은 종류 숫자가 이어진 3장)이고 보통 한 장이 옆으로
  눕혀져 있습니다. 이 모양이 아닌 앞면 패 묶음은 테이블 모서리 근처에 있어도 도라 표시패입니다.
- box_2d: 도라 표시패 묶음 전체를 감싸는 상자 [ymin, xmin, ymax, xmax], 사진 크기를 0~1000 으로 본 정수. 없으면 found=false, box_2d 는 빈 배열."""

LOCATE_SCHEMA = {
    "type": "object",
    "properties": {"found": {"type": "boolean"}, "box_2d": {"type": "array", "items": {"type": "integer"}},
                   "notes": {"type": "string"}},
    "required": ["found", "box_2d"],
}

READ_PROMPT = f"""이 사진은 리치마작 테이블에서 도라 표시패 묶음 부분만 확대한 것입니다. 보이는 것만 적습니다.

- indicators: 앞면(그림이 보이게)으로 놓인 패 전부. 패가 옆으로 눕혀지거나 거꾸로 놓였을 수 있으니 그림을 바로 세워 놓고 읽습니다.
- 뒷면(단색)만 보이는 패, 사진 가장자리에 걸려 반 이상 잘린 패는 적지 않습니다. 없으면 빈 배열입니다.

{ob.NOTATION}

각 패의 확신도(0~1)를 적어 주세요."""
PAD = 0.5


def jpeg(im: Image.Image, side: int | None = None) -> bytes:
    im = im.copy()
    if side:
        im.thumbnail((side, side))
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=90)
    return b.getvalue()


def cover(p: list[int], t: list[int]) -> float:
    i = max(0, min(p[2], t[2]) - max(p[0], t[0])) * max(0, min(p[3], t[3]) - max(p[1], t[1]))
    return i / ((t[2] - t[0]) * (t[3] - t[1]))


def one(photo: str, run: int, full: Image.Image, data: bytes) -> dict:
    loc = call(data, LOCATE_PROMPT, LOCATE_SCHEMA, "gemini-3.8-flash", "low", None)
    row = {"photo": photo, "run": run, "locate_s": loc["s"]}
    if "error" in loc:
        return {**row, "error": loc["error"], "ok": False}
    box = loc["data"].get("box_2d") or []
    if not loc["data"].get("found") or len(box) != 4 or box[0] >= box[2] or box[1] >= box[3]:
        return {**row, "box": None, "ok": False, "notes": (loc["data"].get("notes") or "")[:120]}
    tb, tt = TRUTH[photo]
    p = int(max(box[2] - box[0], box[3] - box[1]) * PAD) + 10
    y0, x0, y1, x1 = max(0, box[0] - p), max(0, box[1] - p), min(1000, box[2] + p), min(1000, box[3] + p)
    w, h = full.size
    crop = full.crop((x0 * w // 1000, y0 * h // 1000, x1 * w // 1000, y1 * h // 1000))
    rd = call(jpeg(crop), READ_PROMPT, ob.DORA_SCHEMA_V2, "gemini-3.8-flash", "default", None)
    tiles = [] if "error" in rd else [t["tile"] for t in ob.normalize_dora_v2(rd["data"])["indicators"]]
    return {**row, "box": box, "cover": round(cover([y0, x0, y1, x1], tb), 2), "read_s": rd["s"], "dora": tiles,
            "ok": sorted(tiles) == sorted(tt), "total_s": round(loc["s"] + rd["s"], 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    fulls = {p: Image.open(PHOTOS / f"{p}.jpg") for p in TRUTH}
    for im in fulls.values():
        im.load()
    data = {p: jpeg(im, 1568) for p, im in fulls.items()}
    jobs = [(p, r) for r in range(1, a.runs + 1) for p in TRUTH]
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(lambda j: one(j[0], j[1], fulls[j[0]], data[j[0]]), jobs))
    OUT.mkdir(exist_ok=True)
    (OUT / "dora_group_locate.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = [r["total_s"] for r in rows if "total_s" in r] or [0]
    p90 = sorted(tot)[int(0.9 * (len(tot) - 1))]
    print(f"찾음(정답 덮음≥0.9) {sum(r.get('cover', 0) >= 0.9 for r in rows)}/{len(rows)}, 도라 정답 {sum(r['ok'] for r in rows)}/{len(rows)}"
          f" | 찾기+읽기 {statistics.median(tot):.1f}/{p90:.1f}/{max(tot):.1f}초")
    for s in ("k25 k28", "k15 k26", "k12 k16"):
        rs = [r for r in rows if r["photo"] in s.split()]
        print(f"  {s}: 도라 정답 {sum(r['ok'] for r in rs)}/{len(rs)}")
    for r in rows:
        if not r["ok"]:
            print(f"  {r['photo']}#{r['run']} 상자 {r.get('box')} 덮음 {r.get('cover')} 읽음 {r.get('dora')} {r.get('error', '')[:80]} {r.get('notes', '')}")


if __name__ == "__main__":
    main()
