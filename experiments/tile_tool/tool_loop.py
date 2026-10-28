"""자리 판독에 '확대 + 참고 그림' 도구를 쥐여 주면 정확도가 오르는지 잰다. 로컬에서 Gemini 를 직접 부른다.

도구 inspect_tiles(box, candidates): 자리 크롭(원본 해상도)에서 box 를 잘라 크게 키운 그림과,
후보 패마다 이 매장 패(AMOS) 실물 참고 그림을 돌려준다. 참고 그림은 시험하는 장면이 아닌 다른 장면에서 자른 것만 쓴다.

python experiments/tile_tool/tool_loop.py [--runs 3]   (결과: tool_results.json, 표는 표준 출력)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys
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
# 도구 없음/있음 둘 다 돌릴지. 보강 효과만 볼 때는 도구 있음만(--tool-only).
TOOLS = (False, True)
G = ROOT.parent / "field_20261024" / "grid5_scenes"
MODEL = "gemini-3.8-flash"
CODES = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + [f"{n}z" for n in range(1, 8)] + ["0m", "0p", "0s"]

# 장면별 정답(손패 줄 + 떨어진 한 장은 합쳐 비교, 울기 묶음).
TRUTH = {
    "A": ("hand_top.jpg", "3p 3p 5p 5p 4m 5m 6m 6s 7s 8s", ["4s 4s 4s 4s"]),
    "B": ("hand_right.jpg", "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p", ["6z 6z 6z"]),
    "C": ("hand_left.jpg", "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z", []),
    "D": ("hand_bottom.jpg", "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z", ["6m 7m 8m"]),
    "E": ("hand_left.jpg", "1z 1z 1z 7m 8m 9m 1s 2s 3s 7s 8s 7z 7z", []),
}
PHOTOS = {"A": ["k20_1", "k24_1"], "B": ["k25_1", "k28_1"], "C": ["k15_1", "k26_1"], "D": ["k12_1", "k16_1"], "E": ["k00_1", "k04_1"]}


NO_MORE = False
# --fix: 실패 분석(2026-10-25)에서 나온 세 가지를 코드가 강제한다.
#  1) 모델이 준 확대 상자를 사방 50%씩 넓히고 최소 크기를 둔다(안깡 윗절반만 보고 2삭으로 읽던 것).
#  2) 후보에 같은 수패의 이웃(n±3, 5 면 적5)을 더한다(9삭을 확대해 놓고 후보에 9삭이 없던 것).
#  3) 첫 판독 뒤 통수·삭수가 있으면 자리 크롭을 세 토막으로 나눠 원본 해상도로 다시 보여 주고 참고 그림과 대조해
#     고치게 한다(틀린 7삭을 확대조차 안 하던 것).
FIX = False
VERIFY = True
EXPAND = True
BOX_PAD = 0.5
BOX_MIN = 150


def expand_candidates(cands: list[str]) -> tuple[list[str], set[str]]:
    """모델 후보 + 같은 수패 이웃. 돌려주는 집합은 모델이 직접 준 후보."""
    own = set(cands)
    out = list(cands)
    for c in cands:
        if c[1] in "ps" and c[0] != "0":
            n = int(c[0])
            for m in range(max(1, n - 3), min(9, n + 3) + 1):
                out.append(f"{m}{c[1]}")
            if 2 <= n <= 8:
                out.append(f"0{c[1]}")
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq[:10], own


def library() -> dict[str, list[tuple[str, Path]]]:
    """패 → [(장면, 그림)]. tiles_raw(손패에서 자른 것)와 river_ok.txt 에 남긴 강 패."""
    lib: dict[str, list[tuple[str, Path]]] = {}
    for p in sorted((ROOT / "tiles_raw").glob("*.png")):
        lib.setdefault(p.stem.split("_")[-1], []).append((p.name[0], p))
    # 강 패(river_ok.txt), 10/24 카메라 헤드 촬영 기록에서 보강한 패(more_ok.txt, 장면 Q). 사람이 확인한 것만.
    # --no-more 이면 보강분을 빼고(보강 전과 비교용).
    for list_name, folder in (("river_ok.txt", "river_raw"), ("more_ok.txt", "more_raw")):
        ok = ROOT / list_name
        if not ok.exists() or (list_name == "more_ok.txt" and NO_MORE):
            continue
        for line in ok.read_text(encoding="utf-8").split():
            name, code = line.split(":")
            lib.setdefault(code, []).append((name[0], ROOT / folder / name))
    return lib


def jpeg(im: Image.Image, q: int = 90) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=q)
    return buf.getvalue()


INSPECT = types.FunctionDeclaration(
    name="inspect_tiles",
    description="사진의 한 부분을 원본 해상도로 크게 키운 그림과, 후보 패마다 이 패 세트의 실물 참고 그림을 돌려준다. "
    "통수·삭수처럼 무늬 개수가 헷갈리는 패를 확인할 때 쓴다.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "box": {"type": "array", "items": {"type": "integer"},
                    "description": "확대할 곳 [ymin, xmin, ymax, xmax], 처음 받은 사진 기준 0~1000. 패 1~4장 정도"},
            "candidates": {"type": "array", "items": {"type": "string", "enum": CODES},
                           "description": "헷갈리는 후보 패(2~4개). 예: [\"6s\", \"7s\", \"9s\"]"},
        },
        "required": ["box", "candidates"],
    },
)

TOOL_NOTE = """
도구: 통수·삭수처럼 무늬 개수가 헷갈리는 패가 있으면 inspect_tiles 로 그 부분을 크게 보고 후보 패의 실물 참고 그림과 비교하세요.
여러 장을 한 번에 봐도 됩니다. 최대 3번까지 부를 수 있습니다. 다 확인했으면 JSON 으로 답합니다."""


def run_once(scene: str, photo: str, use_tool: bool, lib, seed: int) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    crop_name = TRUTH[scene][0]
    full = Image.open(G / scene / photo / crop_name).convert("RGB")
    first = full.copy()
    first.thumbnail((3072, 3072))
    part = types.Part.from_bytes(data=jpeg(first), mime_type="image/jpeg")
    part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_ULTRA_HIGH")
    prompt = ob.SEAT_PROMPT_V2 + (TOOL_NOTE if use_tool else "")
    contents = [types.Content(role="user", parts=[part, types.Part.from_text(text=prompt)])]
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ob.SEAT_SCHEMA_V2,
        thinking_config=types.ThinkingConfig(thinking_level="low"),
        tools=[types.Tool(function_declarations=[INSPECT])] if use_tool else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True) if use_tool else None,
    )
    rnd = random.Random(seed)
    t0 = time.perf_counter()
    calls, tin, tout = [], 0, 0
    for _ in range(5):
        r = client.models.generate_content(model=MODEL, contents=contents, config=cfg)
        um = r.usage_metadata
        tin += um.prompt_token_count or 0
        tout += (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
        fcs = r.function_calls or []
        if not fcs or len(calls) >= 3:
            break
        contents.append(r.candidates[0].content)
        resp_parts = []
        for fc in fcs:
            a = dict(fc.args or {})
            box = a.get("box") or [0, 0, 1000, 1000]
            cands = [c for c in (a.get("candidates") or []) if c in CODES][:4]
            calls.append({"box": box, "candidates": cands})
            W, H = full.size
            y0, x0, y1, x1 = [max(0, min(1000, int(v))) for v in (box + [0, 0, 1000, 1000])[:4]]
            if x1 <= x0 or y1 <= y0:
                y0, x0, y1, x1 = 0, 0, 1000, 1000
            if FIX:
                h, w = y1 - y0, x1 - x0
                ph, pw = max(h * BOX_PAD, (BOX_MIN - h) / 2), max(w * BOX_PAD, (BOX_MIN - w) / 2)
                y0, y1 = max(0, round(y0 - ph)), min(1000, round(y1 + ph))
                x0, x1 = max(0, round(x0 - pw)), min(1000, round(x1 + pw))
            z = full.crop((x0 * W / 1000, y0 * H / 1000, x1 * W / 1000, y1 * H / 1000))
            scale = 768 / max(z.size)
            z = z.resize((max(1, round(z.width * scale)), max(1, round(z.height * scale))), Image.LANCZOS)
            images = [types.FunctionResponsePart.from_bytes(data=jpeg(z), mime_type="image/jpeg")]
            labels = ["확대한 부분"]
            own = set(cands)
            if FIX and EXPAND:
                cands, own = expand_candidates(cands)
            for c in cands:
                refs = [p for s, p in lib.get(c, []) if s != scene]  # 같은 장면 패는 쓰지 않는다
                rnd.shuffle(refs)
                for p in refs[:2 if c in own else 1]:
                    images.append(types.FunctionResponsePart.from_bytes(data=jpeg(Image.open(p)), mime_type="image/jpeg"))
                    labels.append(f"참고: {c}")
                if not refs:
                    labels.append(f"참고: {c} (이 패 세트의 그림 없음)")
            resp_parts.append(types.Part.from_function_response(
                name="inspect_tiles", response={"images_in_order": labels}, parts=images))
        contents.append(types.Content(role="user", parts=resp_parts))
    try:
        d = ob.normalize_seat_v2(json.loads(r.text))
    except Exception as e:  # noqa: BLE001
        d = {"tiles": [], "separate_tile": None, "melds": [], "error": str(e)}
    first_read = None
    if FIX and VERIFY and use_tool:
        d, first_read, vin, vout = verify(client, full, d, scene, lib, rnd)
        tin += vin
        tout += vout
    hand = [t["tile"] for t in d["tiles"]] + ([d["separate_tile"]["tile"]] if d.get("separate_tile") else [])
    melds = sorted(" ".join(sorted(m["tiles"])) for m in d["melds"] if len(m["tiles"]) in (3, 4))
    truth_hand, truth_melds = TRUTH[scene][1].split(), sorted(" ".join(sorted(m.split())) for m in TRUTH[scene][2])
    return {
        "scene": scene, "photo": photo, "tool": use_tool, "hand": hand, "melds": melds,
        "hand_ok": sorted(hand) == sorted(truth_hand), "melds_ok": melds == truth_melds,
        "calls": calls, "s": round(time.perf_counter() - t0, 1), "in": tin, "out": tout,
        "first_read": first_read,
    }


VERIFY_PROMPT = """아래는 리치마작 한 자리(손패 + 오른쪽 모서리)를 그 사람 쪽에서 본 사진을 왼쪽부터 세 토막으로 나눠 원본 해상도로 크게 보여 준 것입니다
(토막끼리 조금 겹칩니다). 그 뒤에는 이 패 세트의 실물 참고 그림이 이름표와 함께 있습니다.

첫 판독 결과(JSON):
{first}

첫 판독의 통수(p)·삭수(s) 패를 한 장도 빠짐없이 확대 토막에서 찾아, 무늬(동그라미·막대) 개수와 배치를 직접 세고
참고 그림과 비교해 맞는지 확인하세요. 울기 묶음의 패도 확인합니다. 패가 토막 경계에 걸쳐 있으면 옆 토막에서 온전한 모습을 봅니다.
틀렸으면 고치고, 만수·자패·장수·순서는 확대 토막에서 분명히 틀린 게 아니면 그대로 둡니다.
고친 전체 결과를 같은 JSON 형식으로 답하세요."""


def verify(client, full: Image.Image, d: dict, scene: str, lib, rnd) -> tuple[dict, dict, int, int]:
    """통수·삭수가 있으면 세 토막 확대 + 참고 그림으로 다시 확인시킨다. (고친 결과, 첫 결과, 토큰)."""
    codes = [t["tile"] for t in d.get("tiles", [])] + [c for m in d.get("melds", []) for c in m["tiles"]]
    if d.get("separate_tile"):
        codes.append(d["separate_tile"]["tile"])
    suits = sorted({c[1] for c in codes if c[1] in "ps"})
    if not suits:
        return d, d, 0, 0
    W, H = full.size
    parts = []
    for i in range(3):
        x0 = round(W * 0.3 * i)
        seg = full.crop((x0, 0, min(W, x0 + round(W * 0.4)), H))
        p = types.Part.from_bytes(data=jpeg(seg), mime_type="image/jpeg")
        p.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_ULTRA_HIGH")
        parts += [types.Part.from_text(text=f"토막 {i + 1}/3"), p]
    for suit in suits:
        for n in list(range(1, 10)) + [0]:
            c = f"{n}{suit}"
            refs = [p for s, p in lib.get(c, []) if s != scene]
            if not refs:
                continue
            parts += [types.Part.from_text(text=f"참고: {c}"),
                      types.Part.from_bytes(data=jpeg(Image.open(rnd.choice(refs))), mime_type="image/jpeg")]
    first = {k: d.get(k) for k in ("face_up", "tiles", "separate_tile", "melds", "loose")}
    parts.append(types.Part.from_text(text=VERIFY_PROMPT.format(first=json.dumps(first, ensure_ascii=False))))
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=ob.SEAT_SCHEMA_V2,
                                      thinking_config=types.ThinkingConfig(thinking_level="low"))
    r = client.models.generate_content(model=MODEL, contents=[types.Content(role="user", parts=parts)], config=cfg)
    um = r.usage_metadata
    vin = um.prompt_token_count or 0
    vout = (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
    try:
        fixed = ob.normalize_seat_v2(json.loads(r.text))
    except Exception:  # noqa: BLE001
        return d, d, vin, vout
    first_hand = [t["tile"] for t in d["tiles"]]
    return fixed, {"tiles": first_hand, "melds": [m["tiles"] for m in d["melds"]]}, vin, vout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--scenes", default="BCD")  # 화료패가 사진에 없는 A·E 는 평가에서 뺀다(2026-10-25 사용자 결정)
    ap.add_argument("--no-more", action="store_true", help="10/24 촬영 기록 보강분을 빼고")
    ap.add_argument("--out", default="tool_results.json")
    ap.add_argument("--tool-only", action="store_true")
    ap.add_argument("--fix", action="store_true", help="상자 넓히기·후보 확장·통수삭수 확인 강제")
    ap.add_argument("--no-verify", action="store_true", help="--fix 에서 확인 강제(2단계 판독)만 뺀다")
    ap.add_argument("--no-expand", action="store_true", help="--fix 에서 후보 자동 확장만 뺀다")
    args = ap.parse_args()
    global NO_MORE, TOOLS, FIX, VERIFY, EXPAND
    VERIFY = not args.no_verify
    EXPAND = not args.no_expand
    NO_MORE = args.no_more
    FIX = args.fix
    if args.tool_only:
        TOOLS = (True,)
    lib = library()
    print("참고 그림:", {c: len(v) for c, v in sorted(lib.items())}, flush=True)
    jobs = [(s, p, tool, i) for s in args.scenes for p in PHOTOS[s] for tool in TOOLS for i in range(args.runs)]
    results = []
    with ThreadPoolExecutor(8) as ex:
        for res in ex.map(lambda j: run_once(j[0], j[1], j[2], lib, seed=j[3]), jobs):
            results.append(res)
            print(f"{res['scene']} {res['photo']} tool={int(res['tool'])} hand={'O' if res['hand_ok'] else 'X'} "
                  f"meld={'O' if res['melds_ok'] else 'X'} {res['s']}s calls={len(res['calls'])} "
                  f"{' '.join(res['hand'])} {res['melds']}", flush=True)
    (ROOT / args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n| 장면 | 도구 없음 손패·울기 | 도구 있음 손패·울기 | 도구 호출 평균 | 시간 중앙값 없음/있음 |")
    for s in args.scenes:
        row = []
        for tool in (False, True):
            rs = [r for r in results if r["scene"] == s and r["tool"] == tool]
            ok = sum(r["hand_ok"] and r["melds_ok"] for r in rs)
            row.append((ok, len(rs), sum(len(r["calls"]) for r in rs) / max(1, len(rs)), sorted(r["s"] for r in rs)[len(rs) // 2]))
        print(f"| {s} | {row[0][0]}/{row[0][1]} | {row[1][0]}/{row[1][1]} | {row[1][2]:.1f} | {row[0][3]}s / {row[1][3]}s |")


if __name__ == "__main__":
    main()
