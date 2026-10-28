"""판독 시간을 줄이고 정확도를 올릴 조건을 같은 갤러리 사진(장면 5개 × 2장)으로 잰다. 로컬에서 Gemini 를 직접 부른다.

  python -I experiments/speed/bench.py scene  [--runs 2]                 한 장면의 호출(자리·강 끝 3·리치봉·도라)을 동시에 보내 호출별 지연
  python -I experiments/speed/bench.py seat   --cond 이름 [--runs 3]      자리 판독 정확도·지연(조건은 CONDS)

결과는 results/<모드>_<조건>.json 에 쌓이고(같은 파일에 덧붙임), 표는 표준 출력.
자리 크롭·정답은 tile_tool/tool_loop.py 와 같다(grid5_scenes, TRUTH).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from app import observe as ob  # noqa: E402

ROOT = Path(__file__).parent
G = ROOT.parent / "field_20261024" / "grid5_scenes"
OUT = ROOT / "results"

TRUTH = {
    "A": ("hand_top.jpg", "3p 3p 5p 5p 4m 5m 6m 6s 7s 8s", ["4s 4s 4s 4s"]),
    "B": ("hand_right.jpg", "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p", ["6z 6z 6z"]),
    "C": ("hand_left.jpg", "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z", []),
    "D": ("hand_bottom.jpg", "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z", ["6m 7m 8m"]),
    "E": ("hand_left.jpg", "1z 1z 1z 7m 8m 9m 1s 2s 3s 7s 8s 7z 7z", []),
}
PHOTOS = {"A": ["k20_1", "k24_1"], "B": ["k25_1", "k28_1"], "C": ["k15_1", "k26_1"], "D": ["k12_1", "k16_1"], "E": ["k00_1", "k04_1"]}

# 이 실험들이 v2 로 잰 자리 판독 프롬프트(서버 SEAT_PROMPT_V2 를 v3a 로 바꾸기 전, 2026-10-25). 지난 조건을 그대로 다시 재기 위해 고정.
SEAT_PROMPT_V2_OLD = f"""이 사진은 리치마작 테이블에서 한 플레이어 자리(앞의 손패와 그 오른쪽 테이블 모서리까지)를 그 사람 쪽에서 본 방향으로 세운 것입니다. 보이는 것만 적습니다. 리치·론·도라 여부 같은 판단은 하지 않습니다.

- face_up: 이 사람의 손패 줄(보통 사진 아래쪽, 10~14장)이 앞면으로 눕혀져 그림이 보이면 true.
  세워져 있거나 뒷면(연보라)만 보이면 false 이고, 그때 tiles·separate_tile 은 비웁니다.
- tiles: 앞면으로 깐 손패 줄. 왼쪽부터. 떨어진 한 장과 울기 묶음은 제외합니다.
- separate_tile: 손패 줄 끝에서 조금 떨어뜨려 놓은 한 장(없으면 null).
- melds: 손패 줄 오른쪽, 테이블 모서리까지 따로 놓인 앞면 3~4장 묶음 전부(퐁·치·깡). 묶음마다 패를 왼쪽부터 적고,
  옆으로 눕힌 패의 위치(sideways)와 뒤집힌 패의 위치(face_down)를 0부터 적습니다. 뒤집힌 패는 같은 묶음의 앞면 패와 같은 것으로 적습니다.
- loose: 손패 줄·울기 묶음에 속하지 않고 1~3장만 따로 놓인 앞면 패(도라 표시패 등). 패산 더미 바로 옆에 붙어 있어도 앞면이면 적습니다.
- 뒷면(연보라)이 보이는 패산 더미, 테이블 가운데 쪽의 버림패 줄, 사진 가장자리에 걸려 반 이상 잘린 패는 적지 않습니다.

장수: 앞면 손패라면 tiles 와 울기 묶음(깡은 4장이지만 3장으로 셈)을 합치면 반드시 13장이고,
화료패 1장(separate_tile)을 더하면 14장입니다. 다 적은 뒤 합이 맞는지 확인하고, 안 맞으면 사진을 다시 세어 고칩니다.

{ob.NOTATION}

보이는 패 수를 먼저 세고 그 수만큼 정확히 나열하세요. 각 패의 확신도(0~1)를 적어 주세요."""

BASE = {"model": "gemini-3.8-flash", "thinking": "low", "res": "ULTRA_HIGH", "max_side": 3072, "crop": None,
        "prompt": "seat", "schema": "seat", "max_out": None}
# 자리 판독 조건. 바꾼 것만 적는다.
CONDS = {
    "base": {},
    "minimal": {"thinking": "minimal"},
    "medium": {"thinking": "medium"},
    "high": {"thinking": "high"},
    "off": {"thinking": "off"},
    "b256": {"thinking": "b256"},
    "b1024": {"thinking": "b1024"},
    "high_res": {"res": "HIGH"},
    "lite": {"model": "gemini-3.5-flash-lite"},
    "pro": {"model": "gemini-3.1-pro-preview"},
    "er2": {"model": "gemini-robotics-er-2-preview", "thinking": "default"},
    "argon": {"model": "gemini-4-argon"},
    "35flash": {"model": "gemini-3.5-flash"},
    "cap800": {"max_out": 800},
    # 한 호출에 전체 + 코드가 자른 확대 토막(원본 해상도). zoom_res 는 토막의 이미지 해상도 수준.
    "zoom3": {"zoom": 3},
    "zoom3u": {"zoom": 3, "zoom_res": "ULTRA_HIGH"},
    "zoom4u": {"zoom": 4, "width": 0.32, "zoom_res": "ULTRA_HIGH"},
    "ref": {"ref": True},
    "zoom3u_ref": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": True},
    "zr_full": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "full"},
    "zr_full_u": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "full", "ref_res": "ULTRA_HIGH"},
    # 다른 패 세트(집 패, 정면 사진)로 만든 통수·삭수 표. 매장 패와 무늬 색·모양이 다르다.
    "zr_set2": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2"},
    "zr_set2_v3": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3"},
    "zr_set2_v3a": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a"},
    "37_zr": {"model": "gemini-3.7-flash", "zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": True},
    "37_zr_min": {"model": "gemini-3.7-flash", "thinking": "minimal", "zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": True},
    "36_zr": {"model": "gemini-3.6-flash", "zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": True},
    "36_zr_min": {"model": "gemini-3.6-flash", "thinking": "minimal", "zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": True},
    "zr_med": {"thinking": "medium", "zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": True},
    "35_zoom3u": {"model": "gemini-3.5-flash", "zoom": 3, "zoom_res": "ULTRA_HIGH"},
    "35_zoom3u_ref": {"model": "gemini-3.5-flash", "zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": True},
    # 장수 힌트(2026-10-26): 서버 /v2/seat(439e035) 와 같은 조건 + 기기가 셌다고 치는 앞면 장수·울기 묶음 수.
    # v3a_now 는 같은 시간대에 다시 잰 기준. hint 는 정답 장수(상한 효과), hint_off1 은 손패 줄 +1(틀린 힌트에 끌려가나).
    "v3a_now": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a"},
    "v3a_hint": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a", "hint": 0},
    "v3a_hint_off1": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a", "hint": 1},
    # 프롬프트 최적화(2026-10-26 밤): 지금 서버(05eaec0 = v3a_norule)에서 한 가지씩만 바꾼 변형. 사진 특정 문구는 넣지 않는다(평가 6장 과적합 방지).
    "opt_guide": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a", "norule": True, "guide": True},
    "opt_front": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a", "norule": True, "front": True},
    "opt_nocount": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a", "norule": True, "nocount": True},
    # 지금 서버(439e035) 자리 판독에서 "손패 + 울기 = 13장, 화료패 더해 14장" 장수 규칙 문단만 뺀 것(배포 전 뺄지 확인, 2026-10-26).
    "v3a_norule": {"zoom": 3, "zoom_res": "ULTRA_HIGH", "ref": "set2", "v3": "v3a", "norule": True},
}

# 장면별 (손패 쪽 줄 앞면 장수, 울기 묶음 수). TRUTH 에서 센 값.
HINT_COUNTS = {s: (len(TRUTH[s][1].split()), len(TRUTH[s][2])) for s in TRUTH}

HINT_NOTE = """

참고: 기기가 사진 픽셀로 센 값입니다(틀릴 수 있음). 손패 쪽 줄의 앞면 패 {n}장(떨어진 한 장이 있으면 포함), 오른쪽 모서리 쪽 울기 묶음 {m}개.
이 수에 맞춰 패를 지어내지 말고, 사진에서 센 수와 다르면 사진을 따르세요."""


def jpeg(im: Image.Image, q: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=q)
    return buf.getvalue()


def load(path: Path, max_side: int, crop=None) -> bytes:
    im = Image.open(path).convert("RGB")
    if crop:
        W, H = im.size
        x0, y0, x1, y1 = crop
        im = im.crop((round(x0 * W), round(y0 * H), round(x1 * W), round(y1 * H)))
    im.thumbnail((max_side, max_side))
    return jpeg(im)


def thinking_config(t: str):
    if t == "default":
        return None
    if t == "off":
        return types.ThinkingConfig(thinking_budget=0)
    if t.startswith("b"):  # 생각 토큰 상한: b512
        return types.ThinkingConfig(thinking_budget=int(t[1:]))
    return types.ThinkingConfig(thinking_level=t)


_local = threading.local()


def client():
    # 스레드마다 하나(같은 클라이언트를 여러 조건이 나눠 쓰다 "client has been closed" 가 났다).
    if not hasattr(_local, "c"):
        _local.c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _local.c


def call(data: bytes, prompt: str, schema: dict, model: str, thinking: str, res: str | None, extra=(), max_out=None,
         thoughts: bool = False) -> dict:
    part = types.Part.from_bytes(data=data, mime_type="image/jpeg")
    if res:
        part.media_resolution = types.PartMediaResolution(level=f"MEDIA_RESOLUTION_{res}")
    tc = thinking_config(thinking)
    if thoughts:  # 실패 원인 보기: 모델의 생각 요약을 함께 받는다
        tc = tc or types.ThinkingConfig()
        tc.include_thoughts = True
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                      thinking_config=tc, max_output_tokens=max_out)
    t0 = time.perf_counter()
    try:
        r = client().models.generate_content(model=model, contents=[part, *extra, prompt], config=cfg)
        um = r.usage_metadata
        return {"s": round(time.perf_counter() - t0, 2), "in": um.prompt_token_count or 0,
                "out": um.candidates_token_count or 0, "think": getattr(um, "thoughts_token_count", 0) or 0,
                "data": json.loads(r.text),
                "thoughts": "\n".join(p.text for p in r.candidates[0].content.parts if p.thought and p.text) if thoughts else None}
    except Exception as e:  # noqa: BLE001
        return {"s": round(time.perf_counter() - t0, 2), "error": f"{type(e).__name__}: {e}"[:300]}


# ---------------------------------------------------------------- 장면 호출별 지연

SCENE_KINDS = {
    "last": (ob.LAST_PROMPT_V2, ob.LAST_SCHEMA_V2),
    "sticks": (ob.STICKS_PROMPT_V2, ob.STICKS_SCHEMA_V2),
    "dora": (ob.DORA_PROMPT_V2, ob.DORA_SCHEMA_V2),
    "seat": (SEAT_PROMPT_V2_OLD, ob.SEAT_SCHEMA_V2),
}
WINNER = {"A": "top", "B": "right", "C": "left", "D": "bottom", "E": "left"}


def scene_jobs(scene: str, photo: str):
    d = G / scene / photo
    w = WINNER[scene]
    jobs = [("seat", d / TRUTH[scene][0], True), ("sticks", d / "sticks.jpg", False), ("dora", d / "wall.jpg", False)]
    jobs += [(f"last_{s}", d / f"last_{s}.jpg", False) for s in ("bottom", "right", "top", "left") if s != w]
    return jobs


def run_scene(runs: int) -> None:
    rows = []
    for _ in range(runs):
        for scene, photos in PHOTOS.items():
            for photo in photos:
                jobs = scene_jobs(scene, photo)
                t0 = time.perf_counter()
                with ThreadPoolExecutor(len(jobs)) as ex:
                    futs = {}
                    for name, path, ultra in jobs:
                        p, s = SCENE_KINDS[name.split("_")[0]]
                        data = load(path, 3072 if ultra else 1568)
                        futs[name] = ex.submit(call, data, p, s, BASE["model"], "low", "ULTRA_HIGH" if ultra else None)
                    res = {k: f.result() for k, f in futs.items()}
                wall = round(time.perf_counter() - t0, 2)
                row = {"scene": scene, "photo": photo, "wall": wall,
                       "calls": {k: {x: v.get(x) for x in ("s", "in", "out", "think", "error")} for k, v in res.items()}}
                rows.append(row)
                slow = max(row["calls"].items(), key=lambda kv: kv[1]["s"])
                print(f"{scene} {photo} 전체 {wall:5.1f}s  가장 느림 {slow[0]} {slow[1]['s']}s  "
                      + " ".join(f"{k}={v['s']}" for k, v in row["calls"].items()), flush=True)
    save("scene_base", rows)
    kinds = sorted({k.split("_")[0] for r in rows for k in r["calls"]})
    print("\n호출 종류별 지연(초) 중앙값 / 최대, 출력·생각 토큰 중앙값")
    for kind in kinds:
        cs = [c for r in rows for k, c in r["calls"].items() if k.split("_")[0] == kind]
        print(f"  {kind:7s} {statistics.median(c['s'] for c in cs):5.1f} / {max(c['s'] for c in cs):5.1f}  "
              f"out {statistics.median(c['out'] or 0 for c in cs):.0f} think {statistics.median(c['think'] or 0 for c in cs):.0f}")
    print(f"  장면 전체 {statistics.median(r['wall'] for r in rows):.1f} / {max(r['wall'] for r in rows):.1f}")
    print("  가장 느린 호출이 몇 번:", {k: sum(1 for r in rows if max(r['calls'], key=lambda x: r['calls'][x]['s']).split('_')[0] == k) for k in kinds})


# ---------------------------------------------------------------- 자리 판독

def judge(scene: str, data: dict) -> dict:
    d = ob.normalize_seat_v2(data)
    hand = [t["tile"] for t in d["tiles"]] + ([d["separate_tile"]["tile"]] if d.get("separate_tile") else [])
    melds = sorted(" ".join(sorted(m["tiles"])) for m in d["melds"])
    th, tm = TRUTH[scene][1].split(), sorted(" ".join(sorted(m.split())) for m in TRUTH[scene][2])
    return {"hand": " ".join(hand), "melds": melds, "hand_ok": sorted(hand) == sorted(th), "melds_ok": melds == tm,
            "face_up": d["face_up"]}


ZOOM_NOTE = """

사진이 여러 장입니다. 첫 사진은 자리 전체이고, 그 다음 {n}장은 같은 사진을 왼쪽부터 {n}토막으로 나눠(이웃 토막과 조금씩 겹침)
원본 해상도로 크게 보여 준 것입니다. 패 종류(특히 통수·삭수의 무늬 개수)는 확대 토막에서 직접 세어 읽고,
장수·순서·앞면 여부·울기 묶음의 위치는 전체 사진으로 정합니다. 겹친 부분의 패를 두 번 세지 않습니다."""

# 표기법의 통수·삭수 줄을 무늬 배치까지 적은 것(패 그림의 일반 지식, 특정 사진 문구 아님).
NOTATION_GUIDE = ob.NOTATION.replace(
    "- 통수(筒): 1p~9p. 동그라미 개수.",
    "- 통수(筒): 1p~9p. 동그라미 개수. 배치: 1p 큰 원 하나, 2p 위아래 2, 3p 대각선 3, 4p 2×2, 5p 네 모서리 + 가운데,\n"
    "  6p 위 2 + 아래 2×2, 7p 위 대각선 3 + 아래 2×2, 8p 2열 × 4줄, 9p 3×3.",
).replace(
    "- 삭수(索): 1s~9s. 대나무 막대 개수. 1s 는 새 그림.",
    "- 삭수(索): 1s~9s. 대나무 막대 개수. 1s 는 새 그림. 배치: 2s 위아래 2, 3s 위 1 + 아래 2, 4s 2×2,\n"
    "  5s 네 모서리 + 가운데, 6s 2줄 × 3, 7s 위 1 + 아래 2줄 × 3, 8s M·W 모양으로 기울어진 8개, 9s 3줄 × 3.\n"
    "  막대는 줄 수(가로로 몇 줄인지)와 한 줄의 막대 수를 따로 세어 곱합니다.",
)

REF_NOTE = """

마지막 사진은 이 패 세트의 통수(1p~9p)·삭수(1s~9s) 실물 참고표입니다(이름표가 위에 있음). 통수·삭수는 참고표와 무늬 개수·배치를 비교해 정합니다.
참고표의 패는 이 자리의 패가 아닙니다."""

# v3(남은 실패 원인 분석 뒤): 1) 앞면 = 그림이 보이면 true(비스듬한 사진에서 연보라 두께를 보고 "세워져 있다" 며 손패를 비우던 것)
# 2) 토막마다 따로 읽어 적고 손패를 정함(전체 사진 첫인상 "2s 한 쌍" 을 토막에서 확인하지 않던 것)
# 3) loose 규칙 하나로(패산 옆 도라 표시패를 적을지 버림패로 볼지 수십 초 고민하던 것)
SEAT_PROMPT_V3 = f"""이 사진은 리치마작 테이블을 위에서 찍은 것으로, 한 플레이어 자리(앞의 손패와 그 오른쪽 테이블 모서리까지)를 그 사람 쪽에서 본 방향으로 세운 것입니다. 보이는 것만 적습니다. 리치·론·도라 여부 같은 판단은 하지 않습니다.

- face_up: 이 사람의 손패 줄(보통 10~14장)의 그림(글자·동그라미·막대)이 사진에 보이면 true.
  비스듬히 찍혀 패 윗변이나 옆에 연보라 두께가 함께 보여도 그림이 보이면 true 입니다(위에서 찍은 사진에서 그림이 보이는 손패는 공개한 손패입니다).
  손패 줄의 그림이 하나도 안 보이고 연보라 뒷면만 보이면 false 이고, 그때 tiles·separate_tile·strip_reads 는 비웁니다.
- strip_reads: 확대 토막마다(첫 토막 0 부터) 그 토막 안에 온전히 보이는 손패 줄의 패를 왼쪽부터 적습니다.
  전체 사진의 인상을 옮기지 말고 그 토막에서 무늬 개수를 직접 세어 읽습니다. 토막 가장자리에서 반 이상 잘린 패는 적지 않습니다.
- tiles: 앞면 손패 줄. 왼쪽부터. strip_reads 의 겹친 부분을 맞춰 한 줄로 이어 정합니다(겹친 패를 두 번 세지 않음).
  패 종류는 strip_reads 를 따르고, 전체 사진은 장수와 순서를 맞추는 데만 씁니다. 떨어진 한 장과 울기 묶음은 제외합니다.
- separate_tile: 손패 줄 끝에서 조금 떨어뜨려 놓은 한 장(없으면 null).
- melds: 손패 줄 오른쪽, 테이블 모서리까지 따로 놓인 앞면 3~4장 묶음 전부(퐁·치·깡). 묶음마다 패를 왼쪽부터 적고,
  옆으로 눕힌 패의 위치(sideways)와 뒤집힌 패의 위치(face_down)를 0부터 적습니다. 뒤집힌 패는 같은 묶음의 앞면 패와 같은 것으로 적습니다.
- loose: 손패 줄·떨어진 한 장·울기 묶음이 아닌 앞면 패는 놓인 곳(패산 옆, 펠트 위, 모서리)과 상관없이 모두 적습니다.
  도라 표시패인지 버림패인지는 가리지 않습니다(앱이 정합니다). 뒷면(연보라)만 보이는 패와 사진 가장자리에서 반 이상 잘린 패만 적지 않습니다.

장수: 앞면 손패라면 tiles 와 울기 묶음(깡은 4장이지만 3장으로 셈)을 합치면 반드시 13장이고,
화료패 1장(separate_tile)을 더하면 14장입니다. 다 적은 뒤 합이 맞는지 확인하고, 안 맞으면 사진을 다시 세어 고칩니다.

{ob.NOTATION}

각 패의 확신도(0~1)를 적어 주세요."""

SEAT_SCHEMA_V3 = {
    **ob.SEAT_SCHEMA_V2,
    "properties": {
        "face_up": ob.SEAT_SCHEMA_V2["properties"]["face_up"] | {"description": "손패 줄의 그림이 보이면 true"},
        "strip_reads": {
            "type": "array",
            "description": "확대 토막마다 온전히 보이는 손패 줄의 패(왼쪽부터). face_up 이 false 면 빈 배열",
            "items": {
                "type": "object",
                "properties": {"strip": {"type": "integer"},
                               "tiles": {"type": "array", "items": {"type": "string", "enum": ob.TILE_CODES}}},
                "required": ["strip", "tiles"],
            },
        },
        **{k: v for k, v in ob.SEAT_SCHEMA_V2["properties"].items() if k != "face_up"},
    },
    "required": ["face_up", "strip_reads", "tiles", "separate_tile", "melds", "loose", "notes"],
    # 토막 읽기를 손패보다 먼저 쓰게 한다
    "property_ordering": ["face_up", "strip_reads", "tiles", "separate_tile", "melds", "loose", "notes"],
}

# v3a: v3 에서 토막별 읽기(strip_reads)만 뺀 것 — 앞면 정의·loose 규칙의 효과만 보기(v3 는 생각 토큰이 0 이 됐다).
SEAT_PROMPT_V3A = (SEAT_PROMPT_V3
                   .replace(SEAT_PROMPT_V3[SEAT_PROMPT_V3.index("- strip_reads:"):SEAT_PROMPT_V3.index("- separate_tile:")],
                            "- tiles: 앞면 손패 줄. 왼쪽부터. 떨어진 한 장과 울기 묶음은 제외합니다.\n")
                   .replace("tiles·separate_tile·strip_reads 는", "tiles·separate_tile 은")
                   .replace("각 패의 확신도(0~1)를 적어 주세요.",
                            "보이는 패 수를 먼저 세고 그 수만큼 정확히 나열하세요. 각 패의 확신도(0~1)를 적어 주세요."))  # v2 와 같게
SEAT_SCHEMA_V3A = {**ob.SEAT_SCHEMA_V2, "properties": {**ob.SEAT_SCHEMA_V2["properties"],
                                                       "face_up": SEAT_SCHEMA_V3["properties"]["face_up"]}}

TOOL = ROOT.parent / "tile_tool"


REF_NOTE_FULL = """

마지막 사진은 이 패 세트의 실물 참고표입니다(이름표가 위에 있음). 줄마다 만수(1m~9m, 0m=적5만)·통수(1p~9p)·삭수(1s~9s, 0s=적5삭)·자패(1z~7z)입니다.
통수·삭수는 참고표와 무늬 개수·배치를 비교해 정하고, 빨간 5(적도라)인지도 참고표와 비교합니다. 참고표의 패는 이 자리의 패가 아닙니다."""

# 전체 표의 줄: 만수·통수·삭수(1~9 + 적5), 자패. 적5통 그림은 참고 그림에 없어 빈 칸.
FULL_ROWS = [[f"{n}m" for n in range(1, 10)] + ["0m"], [f"{n}p" for n in range(1, 10)] + ["0p"],
             [f"{n}s" for n in range(1, 10)] + ["0s"], [f"{n}z" for n in range(1, 8)]]


def ref_sheet(exclude_scene: str, full: bool = False) -> bytes:
    """참고표 한 장: 통수·삭수 1~9, full 이면 FULL_ROWS. 시험 장면의 패는 쓰지 않는다(tile_tool 참고 그림)."""
    from PIL import ImageDraw, ImageFont
    lib: dict[str, list[Path]] = {}
    for p in sorted((TOOL / "tiles_raw").glob("*.png")):
        if p.name[0] != exclude_scene:
            lib.setdefault(p.stem.split("_")[-1], []).append(p)
    for list_name, folder in (("river_ok.txt", "river_raw"), ("more_ok.txt", "more_raw")):
        for line in (TOOL / list_name).read_text(encoding="utf-8").split():
            name, code = line.split(":")
            if name[0] != exclude_scene:
                lib.setdefault(code, []).append(TOOL / folder / name)
    rows = FULL_ROWS if full else [[f"{n}{s}" for n in range(1, 10)] for s in "ps"]
    cw, ch, lab = 120, 160, 40
    sheet = Image.new("RGB", (cw * max(map(len, rows)), (ch + lab) * len(rows)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30)
    for row, codes in enumerate(rows):
        for i, code in enumerate(codes):
            x, y = i * cw, row * (ch + lab)
            draw.text((x + 35, y + 4), code, fill="black", font=font)
            if lib.get(code):
                # 옆 패가 덜 섞인 것: 세로/가로 비율이 패(약 1.35)에 가깝고 큰 그림
                ims = [Image.open(q).convert("RGB") for q in lib[code]]
                t = min(ims, key=lambda m: abs(m.height / m.width - 1.35) - m.width * m.height / 1e6)
                t.thumbnail((cw - 10, ch - 6))
                sheet.paste(t, (x + (cw - t.width) // 2, y + lab))
    return jpeg(sheet)


def ref_sheet_set2() -> bytes:
    """다른 패 세트(사용자가 보낸 정면 사진, tileset2/cut.py 로 자름)의 통수·삭수 1~9 참고표. 매장 표와 같은 배치.
    패가 40×50px 정도라 칸 크기로 키운다. 같은 패가 4줄 있어 가운데 줄(2) 것을 쓴다."""
    from PIL import ImageDraw, ImageFont
    tiles = ROOT / "tileset2" / "tiles"
    box = {"p": "pin", "s": "sou"}
    cw, ch, lab = 120, 160, 40
    sheet = Image.new("RGB", (cw * 9, (ch + lab) * 2), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30)
    for row, suit in enumerate("ps"):
        for i in range(9):
            code = f"{i + 1}{suit}"
            x, y = i * cw, row * (ch + lab)
            draw.text((x + 35, y + 4), code, fill="black", font=font)
            t = Image.open(tiles / f"{code}_{box[suit]}2.png").convert("RGB")
            s = min((cw - 10) / t.width, (ch - 6) / t.height)
            t = t.resize((round(t.width * s), round(t.height * s)), Image.LANCZOS)
            sheet.paste(t, (x + (cw - t.width) // 2, y + lab))
    return jpeg(sheet)


def zoom_strips(path: Path, n: int, width: float = 0.4) -> list[bytes]:
    im = Image.open(path).convert("RGB")
    W, H = im.size
    step = (1 - width) / (n - 1)
    return [jpeg(im.crop((round(i * step * W), 0, round((i * step + width) * W), H))) for i in range(n)]


def image_part(data: bytes, res: str | None):
    part = types.Part.from_bytes(data=data, mime_type="image/jpeg")
    if res:
        part.media_resolution = types.PartMediaResolution(level=f"MEDIA_RESOLUTION_{res}")
    return part


def run_seat(cond_name: str, runs: int, workers: int, scenes: str, photos: str = "", thoughts: bool = False) -> None:
    c = {**BASE, **CONDS[cond_name]}
    jobs = [(s, p) for _ in range(runs) for s in scenes for p in PHOTOS[s] if not photos or p in photos.split(",")]

    def one(job):
        s, p = job
        path = G / s / p / TRUTH[s][0]
        data = load(path, c["max_side"], c["crop"])
        prompt, schema = {"v3": (SEAT_PROMPT_V3, SEAT_SCHEMA_V3), "v3a": (SEAT_PROMPT_V3A, SEAT_SCHEMA_V3A)}.get(
            c.get("v3"), (SEAT_PROMPT_V2_OLD, ob.SEAT_SCHEMA_V2))
        if c.get("norule"):
            rule = prompt[prompt.index("장수: 앞면 손패라면"):]
            prompt = prompt.replace(rule[:rule.index("\n\n") + 2], "")
        if c.get("guide"):
            prompt = prompt.replace(ob.NOTATION, NOTATION_GUIDE)
        if c.get("nocount"):
            prompt = prompt.replace("보이는 패 수를 먼저 세고 그 수만큼 정확히 나열하세요. ", "")
        extra = []
        notes = ""
        if c.get("zoom"):
            extra += [image_part(z, c.get("zoom_res")) for z in zoom_strips(path, c["zoom"], c.get("width", 0.4))]
            notes += ZOOM_NOTE.format(n=c["zoom"])
        if c.get("ref"):
            full = c["ref"] == "full"
            sheet = ref_sheet_set2() if c["ref"] == "set2" else ref_sheet(s, full)
            extra.append(image_part(sheet, c.get("ref_res")))
            notes += REF_NOTE_FULL if full else REF_NOTE
        if c.get("front"):  # 사진 구성 설명을 맨 끝 대신 첫 문단 바로 뒤에
            i = prompt.index("\n\n")
            prompt = prompt[:i] + notes + prompt[i:]
        else:
            prompt += notes
        if "hint" in c:
            n, m = HINT_COUNTS[s]
            prompt += HINT_NOTE.format(n=n + c["hint"], m=m)
        r = call(data, prompt, schema, c["model"], c["thinking"], c["res"], extra=extra, max_out=c["max_out"],
                 thoughts=thoughts)
        row = {"scene": s, "photo": p, **{k: r.get(k) for k in ("s", "in", "out", "think", "error")}}
        if "data" in r:
            row.update(judge(s, r["data"]))
            row["strip_reads"] = r["data"].get("strip_reads")
            if thoughts:
                row.update(thoughts=r["thoughts"], notes=r["data"].get("notes"))
        return row

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, jobs))
    save(f"{'probe' if thoughts else 'seat'}_{cond_name}", rows)
    summarize(cond_name, rows)


def summarize(name: str, rows: list[dict]) -> None:
    ok = [r for r in rows if r.get("hand_ok") and r.get("melds_ok")]
    per = {s: f"{sum(1 for r in ok if r['scene'] == s)}/{sum(1 for r in rows if r['scene'] == s)}" for s in "ABCDE"
           if any(r["scene"] == s for r in rows)}
    good = [r for r in rows if not r.get("error")]
    errs = len(rows) - len(good)
    t = [r["s"] for r in good] or [0]
    print(f"{name:10s} 정답 {len(ok)}/{len(rows)}  {per}  시간 중앙 {statistics.median(t):.1f}s 최대 {max(t):.1f}s  "
          f"입력 {statistics.mean(r['in'] or 0 for r in good) if good else 0:.0f} 출력 {statistics.mean(r['out'] or 0 for r in good) if good else 0:.0f} "
          f"생각 {statistics.mean(r['think'] or 0 for r in good) if good else 0:.0f}" + (f"  오류 {errs}" if errs else ""))
    for r in rows:
        if r.get("error"):
            print("   오류:", r["scene"], r["photo"], r["error"][:150])
        elif not (r["hand_ok"] and r["melds_ok"]):
            print(f"   틀림 {r['scene']} {r['photo']}: {r['hand']} | {r['melds']}")


def save(name: str, rows: list[dict]) -> None:
    OUT.mkdir(exist_ok=True)
    f = OUT / f"{name}.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    f.write_text(json.dumps(old + rows, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["scene", "seat", "show"])
    ap.add_argument("--cond", default="base")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    # 화료패가 사진에 없는 A·E 는 평가에서 뺀다(2026-10-25 사용자 결정). 지난 결과 파일에는 A·E 행이 남아 있어 show 도 이 장면만 센다.
    ap.add_argument("--scenes", default="BCD")
    ap.add_argument("--photos", default="", help="이 사진만(쉼표), 예: k25_1,k15_1")
    ap.add_argument("--thoughts", action="store_true", help="생각 요약·notes 를 받아 probe_<조건>.json 에")
    a = ap.parse_args()
    if a.mode == "scene":
        run_scene(a.runs)
    elif a.mode == "seat":
        for name in a.cond.split(","):
            run_seat(name, a.runs, a.workers, a.scenes, a.photos, a.thoughts)
    else:  # 쌓인 결과를 조건별로 다시 요약
        for f in sorted(OUT.glob("seat_*.json")):
            rows = [r for r in json.loads(f.read_text(encoding="utf-8")) if r["scene"] in a.scenes]
            if rows:
                summarize(f.stem[5:], rows)


if __name__ == "__main__":
    main()
