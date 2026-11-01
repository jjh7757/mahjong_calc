"""화료자 쪽 테이블 절반을 통째로 읽으면 떼어 둔 패·모서리 울기를 잡나(2026-11-01, 10-31 매장 오후 손패 정답 3/15).

같은 순간에 두 조건을 나란히 보낸다.
  seat  운영 /v2/seat, 지금 앱과 같은 크롭(격자 + 가운데 쪽 40)과 문구.
  half  격자 가운데 선부터 화료자 쪽 테이블 끝까지(폭 전체). 문구·스키마는 이 사진에 맞게 고침: 강·옆 사람 모서리를 설명하고,
        떼어 둔 패를 여러 장 받는다(separate_tiles). Gemini 직접 3번 읽기 + 다수결, 3.8 Flash low, ULTRA_HIGH, 확대 3토막 + 참고표.

  python -I -X utf8 experiments/speed/wide_seat.py [--runs-bcd 2] [--runs-visit 1] [--only 142535]
  python -I -X utf8 experiments/speed/wide_seat.py --show
결과 experiments/speed/results/wide_seat.json. 채점 정답은 seat_grow.scenes(B·C·D TRUTH, 매장 truth.json·label.json).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ENV = Path(r"C:\Users\jjh7757\Downloads\부트캠프\.env")
if "GEMINI_API_KEY" not in os.environ:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402
import seat_grow as sg  # noqa: E402

from app import observe as ob  # noqa: E402
from app.recognizer import REF_SHEET, prepare_image, zoom_strips  # noqa: E402

OUT = Path(__file__).parent / "results" / "wide_seat.json"
TRUTH_FILE = sg.VISIT.parent / "truth.json"

_r = ob._must_replace
HALF_PROMPT = _r(ob.SEAT_PROMPT_V2,
                 "한 플레이어 자리(앞의 손패와 그 오른쪽 테이블 모서리까지)를 그 사람 쪽에서 본 방향으로 세운 것입니다.",
                 "화료한 플레이어 쪽 테이블 절반을 그 사람 쪽에서 본 방향으로 세운 것입니다. 사진 아래쪽이 이 사람 자리이고, 위쪽 가운데가 자동 탁자 기기,"
                 " 그 둘레에 줄지어 놓인 패가 버림패(강)입니다. 단색 뒷면 줄은 패산이나 옆 사람 손패입니다.")
_i, _j = HALF_PROMPT.index("- tiles:"), HALF_PROMPT.index("{NOTATION}") if "{NOTATION}" in HALF_PROMPT else HALF_PROMPT.index(ob.NOTATION)
HALF_PROMPT = HALF_PROMPT[:_i] + """- tiles: 사진 아래쪽, 이 사람 앞의 앞면 손패 줄. 왼쪽부터. 손으로 벌려 틈이 있거나, 줄이 휘었거나, 여러 덩어리로 나뉘어 있어도 모두 손패 줄입니다. 떨어뜨려 놓은 패와 울기 묶음은 제외합니다.
- separate_tiles: 손패 줄에서 떨어뜨려 놓은 이 사람의 패(화료패, 보여 주려고 앞으로 내민 패 등). 줄의 오른쪽·앞·뒤 어디든 이 사람 앞쪽의 낱장이면 적습니다. 보통 0~3장.
- melds: 사진 오른쪽 아래 테이블 모서리에 놓인 앞면 3~4장 묶음 전부(퐁·치·깡). 무늬 없는 흰 패 3장(5z)도 묶음입니다. 왼쪽 아래 모서리의 묶음은 옆 사람 것이라 적지 않습니다.
  묶음마다 패를 왼쪽부터 적고, 옆으로 눕힌 패의 위치(sideways)와 뒤집힌 패의 위치(face_down)를 0부터 적습니다. 뒤집힌 패는 같은 묶음의 앞면 패와 같은 것으로 적습니다.
- loose: 위 셋에 들지 않는 앞면 낱장 중 강이 아닌 것(패산 위의 앞면 패, 펠트 위에 내놓은 도라·뒷도라 표시패 등). 기기 둘레 강의 패는 적지 않습니다.

손패 줄 + 떨어뜨린 패 + 울기×3 은 모두 13장 또는 14장입니다. 리치 화료 뒤에는 도라·뒷도라 표시패 두 장을 나란히 펠트에 내놓기도 합니다. 손패 장수가 이미 찼다면 그 두 장은 loose 입니다.

""" + HALF_PROMPT[_j:]
HALF_PROMPT = _r(HALF_PROMPT, "첫 사진은 자리 전체이고", "첫 사진은 테이블 절반 전체이고")
HALF_PROMPT = _r(HALF_PROMPT, "장수·순서·앞면 여부·울기 묶음의 위치는", "장수·순서·앞면 여부·떨어뜨린 패·울기 묶음의 위치는")

_props = dict(ob.SEAT_SCHEMA_V2["properties"])
del _props["separate_tile"]
_props["separate_tiles"] = {"type": "array", "description": "손패 줄에서 떨어뜨려 놓은 이 사람의 패. 없으면 빈 배열", "items": ob.SEAT_SCHEMA_V2["properties"]["tiles"]["items"]}
HALF_SCHEMA = {**ob.SEAT_SCHEMA_V2, "properties": _props,
               "required": [("separate_tiles" if k == "separate_tile" else k) for k in ob.SEAT_SCHEMA_V2["required"]]}


def half_box(g: dict, side: str) -> tuple[int, int, int, int]:
    my, mx = (g["y1"] + g["y2"]) // 2, (g["x1"] + g["x2"]) // 2
    return {"bottom": (my, 0, 1000, 1000), "right": (0, mx, 1000, 1000), "top": (0, 0, my, 1000), "left": (0, 0, 1000, mx)}[side]


def read_half(jpg: bytes) -> dict:
    prep = prepare_image(jpg, 4080)
    extra = [b.image_part(z, "ULTRA_HIGH") for z in zoom_strips(prep, ob.SEAT_ZOOM_STRIPS)] + [b.image_part(REF_SHEET.read_bytes(), None)]
    r = b.call(prep, HALF_PROMPT, HALF_SCHEMA, "gemini-3.8-flash", "low", "ULTRA_HIGH", extra=extra)
    if "data" not in r:
        return {"error": str(r.get("error"))[:200]}
    d = r["data"]
    n = ob.normalize_seat_v2({**d, "separate_tile": None})
    return {"hand": [t["tile"] for t in n["tiles"]], "sep": [c["tile"] for c in (ob._code(x) for x in d.get("separate_tiles") or []) if c],
            "melds": [" ".join(m["tiles"]) for m in n["melds"]], "loose": [t["tile"] for t in n["loose"]], "face_up": n["face_up"]}


def key(r: dict) -> tuple:
    return tuple(sorted(r["hand"] + r["sep"])), tuple(sorted(" ".join(sorted(m.split())) for m in r["melds"]))


def run_half(jpg: bytes) -> dict:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(3) as ex:
        reads = list(ex.map(read_half, [jpg] * 3))
    secs = time.perf_counter() - t0
    ok = [r for r in reads if "error" not in r]
    if not ok:
        return {"error": reads[0]["error"], "s": round(secs, 1)}
    top, n = Counter(key(r) for r in ok).most_common(1)[0]
    chosen = next(r for r in ok if key(r) == top)
    return {**chosen, "s": round(secs, 1), "unanimous": n == 3, "reads": ok}


def run_seat(s: dict, im: Image.Image) -> dict:
    jpg = sg.jpeg(sg.crop(im, sg.seat_box(s["grid"], s["side"], 40), s["side"]))
    res = sg.post(jpg, sg.hand_frac(s["grid"], s["side"]))
    if "error" in res:
        return {"error": res["error"], "s": round(res["s"], 1)}
    d = res["data"]
    return {"hand": [t["tile"] for t in d.get("tiles") or []], "sep": [d["separate_tile"]["tile"]] if d.get("separate_tile") else [],
            "melds": [" ".join(m["tiles"]) for m in d.get("melds") or []], "loose": [t["tile"] for t in d.get("loose") or []],
            "unanimous": (d.get("agreement") or {}).get("unanimous"), "method": d.get("method"), "s": round(res["s"], 1)}


def judge(s: dict, r: dict) -> dict:
    if "error" in r:
        return {"ok": False, "row_ok": False, "count_ok": False}
    n = len(r["hand"]) + len(r["sep"]) + 3 * len(r["melds"])
    out = {"count_ok": n in (13, 14), "n": n}
    if s["hand"] is not None:
        melds = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
        out["ok"] = sorted(r["hand"] + r["sep"]) == sorted(s["hand"]) and melds(r["melds"]) == melds(s["melds"])
    return out


def main(a) -> None:
    rows = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    for s in sg.scenes():
        if a.only and a.only not in s["name"]:
            continue
        im = Image.open(s["path"]).convert("RGB")
        half = sg.jpeg(sg.crop(im, half_box(s["grid"], s["side"]), s["side"]))
        for i in range(a.runs_bcd if s["set"] == "bcd" else a.runs_visit):
            with ThreadPoolExecutor(2) as ex:
                f1, f2 = ex.submit(run_seat, s, im), ex.submit(run_half, half)
                seat, hf = f1.result(), f2.result()
            row = {"name": s["name"], "set": s["set"], "side": s["side"], "run": i, "at": time.strftime("%H:%M:%S"),
                   "seat": {**seat, **judge(s, seat)}, "half": {**hf, **judge(s, hf)}}
            rows.append(row)
            OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            print(s["name"][-6:], s["side"], {c: (row[c].get("ok"), row[c].get("n"), row[c].get("s"), row[c].get("error")) for c in ("seat", "half")}, flush=True)
            time.sleep(a.sleep)


def show() -> None:
    rows = json.loads(OUT.read_text(encoding="utf-8"))
    truth = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))["scenes"]
    parts = [("B·C·D", lambda r: r["set"] == "bcd"), ("매장 오전", lambda r: r["set"] == "visit" and r["name"] < "20261031_14"),
             ("매장 오후", lambda r: r["set"] == "visit" and r["name"] >= "20261031_14")]
    for label, f in parts:
        part = [r for r in rows if f(r)]
        for c in ("seat", "half"):
            v = [r[c] for r in part]
            if not v:
                continue
            t = sorted(x["s"] for x in v)
            ind = [Counter(truth[r["name"]]["indicators"]) - Counter(r[c].get("loose") or []) for r in part if r["name"] in truth]
            print(f"{label} {c}: 정답 {sum(1 for x in v if x.get('ok'))}/{len(v)} 장수 {sum(1 for x in v if x.get('count_ok'))} 만장일치 {sum(1 for x in v if x.get('unanimous'))}"
                  f" 오류 {sum(1 for x in v if 'error' in x)} 시간 {statistics.median(t):.1f} / {t[min(len(t) - 1, int(.9 * len(t)))]:.1f} / {t[-1]:.1f}"
                  + (f" 표시패가 loose 에 다 있음 {sum(1 for i in ind if not i)}/{len(ind)}" if ind else ""))
    print("-- 사진별")
    for r in rows:
        if r["set"] == "visit":
            h = r["half"]
            print(r["name"][-6:], "seat", r["seat"].get("ok"), r["seat"].get("method"), "| half", h.get("ok"), " ".join(h.get("hand", [])), "sep", h.get("sep"), h.get("melds"), "loose", h.get("loose"), "만장", h.get("unanimous"), h.get("error", ""))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runs-bcd", type=int, default=2)
    p.add_argument("--runs-visit", type=int, default=1)
    p.add_argument("--only", default="")
    p.add_argument("--sleep", type=float, default=8)
    p.add_argument("--show", action="store_true")
    a = p.parse_args()
    show() if a.show else main(a)
