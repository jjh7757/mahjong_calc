"""자동 반영 안전장치 후보 두 가지를 개발 세트(갤러리 B·C·D)로 잰다(2026-10-27, problem_log 31 이어서).

매장 테스트 세트에서 리치봉을 놓치고(12:29) 적5를 5로 읽은(14:03) 채 자동 반영됐는데, 판독 확신도에는 신호가 없었다
(리치봉 있으면 늘 0.9·없으면 답 없음, 5 패는 늘 0.99). 그래서 추가 판독으로 잡을 수 있는지 본다.
개발 세트 원본은 판독이 다 맞아 잡을 실수가 없으므로, 사진을 어렵게 바꾼 변형(작게·흐리게·돌림)을 더한다.

  sticks : 리치봉 크롭을 같은 프롬프트(+ 판독 번호 표식 — 같은 요청은 Gemini 가 묶어 같은 답을 준다)로 3번 동시에 읽고
           셋이 같으면 받아들이고 다르면 확인. 한 번 읽기(지금)와 비교.
  fives  : 자리 판독(운영과 같은 요청)과 별도로 "이 손패의 5 패와 빨간 5(적도라) 여부만" 묻는 확대 재확인.
           둘이 다르면 확인.

  python -I experiments/speed/recheck.py sticks [--runs 3]
  python -I experiments/speed/recheck.py fives  [--runs 3]
결과 results/recheck/<모드>.json, 표는 표준 출력. 테스트 세트(매장 15장)는 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402
from google.genai import types  # noqa: E402

from app import observe as ob  # noqa: E402
from app.recognizer import REF_SHEET, prepare_image, zoom_strips  # noqa: E402

OUT = b.OUT / "recheck"
G = b.G  # grid5_scenes
PHOTOS = {"B": ["k25_1", "k28_1"], "C": ["k15_1", "k26_1"], "D": ["k12_1", "k16_1"]}
SIDES = ("bottom", "right", "top", "left")
# 리치봉 정답: 사진에서 기기 홈(또는 그 변 가장자리)에 막대가 보이는 자리(2026-10-27 눈으로 확인)
# (k28 아래는 처음에 비었다고 봤다가 확대해 파란 막대를 확인하고 고침 — 첫 실행의 "틀림 15" 는 정답 쪽 실수였다)
STICKS = {"k25_1": {"left", "bottom"}, "k28_1": {"left", "bottom"}, "k15_1": {"left"}, "k26_1": {"left"},
          "k12_1": {"top", "bottom"}, "k16_1": {"top", "bottom"}}
# 화료자 손패의 5 패: (무늬, 빨간지) — NOTES "갤러리 사진 판독" 정답
SEAT = {"B": "hand_right", "C": "hand_left", "D": "hand_bottom"}
FIVES = {"B": [], "C": [("m", False)], "D": [("m", True)]}


def variant(path: Path, v: str) -> Image.Image:
    im = Image.open(path).convert("RGB")
    W, H = im.size
    if v == "orig":
        return im
    if v == "s50":
        return im.resize((W // 2, H // 2), Image.LANCZOS)
    if v == "s33":
        return im.resize((W // 3, H // 3), Image.LANCZOS)
    if v == "s33blur":
        return im.resize((W // 3, H // 3), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
    if v == "rot15":
        return im.rotate(15, resample=Image.BICUBIC, expand=False, fillcolor=(40, 90, 60))
    raise ValueError(v)


def jpg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def ask(contents: list, schema: dict, res: str | None = None) -> dict:
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                      thinking_config=types.ThinkingConfig(thinking_level="low"))
    try:
        r = b.client().models.generate_content(model="gemini-3.8-flash", contents=contents, config=cfg)
        return json.loads(r.text)
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:200]}


# ---------------------------------------------------------------- 리치봉

def sticks_of(data: dict) -> frozenset | None:
    if "error" in data:
        return None
    n = ob.normalize_sticks_v2(data)
    return frozenset(s for s, v in n["riichi_sticks"].items() if v)


def run_sticks(runs: int, variants: list[str]) -> None:
    jobs = []
    for s, ps in PHOTOS.items():
        for p in ps:
            for v in variants:
                data = jpg(variant(G / s / p / "sticks.jpg", v))
                for run in range(runs):
                    for k in range(3):
                        prompt = ob.STICKS_PROMPT_V2 + f"\n\n(판독 {run * 3 + k + 1})"
                        jobs.append(((p, v, run, k), [b.image_part(data, None), prompt]))
    with ThreadPoolExecutor(12) as ex:
        res = dict(zip([j[0] for j in jobs], ex.map(lambda j: sticks_of(ask(j[1], ob.STICKS_SCHEMA_V2)), jobs)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sticks.json").write_text(json.dumps({"|".join(map(str, k)): sorted(v) if v is not None else None
                                                  for k, v in res.items()}, ensure_ascii=False, indent=0), encoding="utf-8")
    print("리치봉 — 변형별 (장면 6 × 회차) : 한 번 읽기 틀림 | 3번 만장일치: 받아들임(그중 틀림) · 확인")
    tot = Counter()
    for v in variants:
        c = Counter()
        for p in STICKS:
            for run in range(runs):
                three = [res[(p, v, run, k)] for k in range(3)]
                truth = frozenset(STICKS[p])
                c["n"] += 1
                c["single_wrong"] += three[0] != truth
                if None not in three and len(set(three)) == 1:
                    c["accept"] += 1
                    c["accept_wrong"] += three[0] != truth
                else:
                    c["ask"] += 1
                    c["ask_single_wrong"] += three[0] != truth
        tot.update(c)
        print(f"  {v:8s} n={c['n']:2d}  한 번 읽기 틀림 {c['single_wrong']:2d} | 받아들임 {c['accept']:2d}(틀림 {c['accept_wrong']}) · 확인 {c['ask']:2d}"
              f"(그중 한 번 읽기가 틀렸던 것 {c['ask_single_wrong']})")
    print(f"  합계     n={tot['n']}  한 번 읽기 틀림 {tot['single_wrong']} | 받아들임 {tot['accept']}(틀림 {tot['accept_wrong']}) · 확인 {tot['ask']}")


# ---------------------------------------------------------------- 5 패 재확인

FIVES_PROMPT = """이 사진은 리치마작 한 플레이어 자리를 그 사람 쪽에서 본 방향으로 세운 것입니다(첫 사진 = 자리 전체, 다음 사진들 = 같은 사진을 왼쪽부터 확대한 토막).
앞면으로 깐 손패 줄과 울기 묶음에서 숫자 5 패(5만·5통·5삭)만 찾습니다. 다른 패는 보지 않습니다.

- fives: 찾은 5 패마다 무늬(m=만수, p=통수, s=삭수)와 빨간 5(적도라)인지(red).
  적도라는 숫자 5(만수는 五 글자, 통수는 다섯 원, 삭수는 다섯 막대)가 **빨간색**으로 칠해진 패입니다.
  보통 5 의 만수는 五 가 검은색이고 萬 만 빨갛습니다 — 萬 이 빨간 것은 적도라가 아닙니다.
  통수 보통 5 는 가운데 원만 빨갛고 나머지 넷은 파란/초록입니다. 삭수 보통 5 는 가운데 막대만 빨갛습니다.
- 5 패가 없으면 빈 배열.

각 패의 확신도(0~1)를 적어 주세요."""

FIVES_SCHEMA = {
    "type": "object",
    "properties": {
        "fives": {"type": "array", "items": {"type": "object", "properties": {
            "suit": {"type": "string", "enum": ["m", "p", "s"]}, "red": {"type": "boolean"},
            "confidence": {"type": "number"}}, "required": ["suit", "red", "confidence"]}},
        "notes": {"type": "string"},
    },
    "required": ["fives", "notes"],
}


def seat_contents(data: bytes, prompt: str) -> list:
    j = prepare_image(data, 3072)
    return ([b.image_part(j, "ULTRA_HIGH")] + [b.image_part(z, "ULTRA_HIGH") for z in zoom_strips(j, ob.SEAT_ZOOM_STRIPS)]
            + [b.image_part(REF_SHEET.read_bytes(), None), prompt])


def fives_from_seat(data: dict) -> Counter | None:
    """자리 판독 답 → 손패·울기의 5 패 (무늬, 빨강) 개수."""
    if "error" in data:
        return None
    n = ob.normalize_seat_v2(data)
    codes = [t["tile"] for t in n["tiles"]] + ([n["separate_tile"]["tile"]] if n["separate_tile"] else [])
    codes += [c for m in n["melds"] for c in m["tiles"]]
    return Counter((c[1], c[0] == "0") for c in codes if c[0] in "05" and c[1] in "mps")


def fives_from_check(data: dict) -> Counter | None:
    if "error" in data:
        return None
    return Counter((f["suit"], bool(f["red"])) for f in data.get("fives") or [])


def run_fives(runs: int, variants: list[str]) -> None:
    jobs = []
    for s, ps in PHOTOS.items():
        for p in ps:
            for v in variants:
                data = jpg(variant(G / s / p / f"{SEAT[s]}.jpg", v))
                for run in range(runs):
                    jobs.append(((s, p, v, run, "seat"), seat_contents(data, ob.SEAT_PROMPT_V2 + f"\n\n(판독 {run + 1})"),
                                 ob.SEAT_SCHEMA_V2, fives_from_seat))
                    jobs.append(((s, p, v, run, "check"), seat_contents(data, FIVES_PROMPT + f"\n\n(판독 {run + 1})"),
                                 FIVES_SCHEMA, fives_from_check))
    with ThreadPoolExecutor(12) as ex:
        res = dict(zip([j[0] for j in jobs], ex.map(lambda j: j[3](ask(j[1], j[2])), jobs)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fives.json").write_text(json.dumps({"|".join(map(str, k)): (sorted([list(x), n] for x, n in v.items()) if v is not None else None)
                                                 for k, v in res.items()}, ensure_ascii=False), encoding="utf-8")
    print("5 패 — 변형별 (장면 6 × 회차): 자리 판독 5 패 틀림 | 재확인 틀림 | 둘이 다름(확인) | 자리 틀림을 잡음 · 헛경보")
    tot = Counter()
    for v in variants:
        c = Counter()
        for s, ps in PHOTOS.items():
            truth = Counter(FIVES[s])
            for p in ps:
                for run in range(runs):
                    seat, chk = res[(s, p, v, run, "seat")], res[(s, p, v, run, "check")]
                    c["n"] += 1
                    sw = seat != truth
                    flag = seat is None or chk is None or seat != chk
                    c["seat_wrong"] += sw
                    c["check_wrong"] += chk != truth
                    c["flag"] += flag
                    c["caught"] += sw and flag
                    c["missed"] += sw and not flag
                    c["false_alarm"] += (not sw) and flag
        tot.update(c)
        print(f"  {v:8s} n={c['n']:2d}  자리 틀림 {c['seat_wrong']:2d} | 재확인 틀림 {c['check_wrong']:2d} | 확인 {c['flag']:2d} | "
              f"잡음 {c['caught']} 놓침 {c['missed']} · 헛경보 {c['false_alarm']}")
    print(f"  합계     n={tot['n']}  자리 틀림 {tot['seat_wrong']} | 재확인 틀림 {tot['check_wrong']} | 확인 {tot['flag']} | "
          f"잡음 {tot['caught']} 놓침 {tot['missed']} · 헛경보 {tot['false_alarm']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sticks", "fives"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--variants", default="orig,s50,s33,s33blur,rot15")
    a = ap.parse_args()
    vs = a.variants.split(",")
    (run_sticks if a.mode == "sticks" else run_fives)(a.runs, vs)


if __name__ == "__main__":
    main()
