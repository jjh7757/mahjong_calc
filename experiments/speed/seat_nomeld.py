"""울기를 미리 읽어 두면(판 상태 추적) 화료 때 자리 판독이 빨라지나: 울기 모서리를 뺀 자리 크롭과 지금 크롭을 나란히.

  python -I -X utf8 experiments/speed/seat_nomeld.py read --runs 15
  python -I -X utf8 experiments/speed/seat_nomeld.py stats

울기가 있는 장면 B·D(사진 4장)만. 요청은 운영 자리 판독 한 번과 같고(seat_focus.seat_request 와 같은 구성) 사진·문구만 다르다.
  base      지금 크롭, 지금 문구. 손패 + 울기가 모두 맞아야 정답.
  nomeld    손패 끝과 울기 사이에서 오른쪽을 잘라낸 크롭, 지금 문구. 손패가 맞고 울기를 지어내지 않아야(빈 배열) 정답.
  nomeld_p  위 크롭 + "울기는 이미 읽었고 이 사진에 없음" 한 줄.
자르는 위치는 장면마다 손으로 정했다(판 상태 추적이 울기 위치를 알고 있다고 치는 것). B 0.79, D 0.65(크롭 폭 비율).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import bench as b  # noqa: E402
import seat_focus as sf  # noqa: E402

from app import observe as ob  # noqa: E402
from app.recognizer import REF_SHEET, prepare_image, zoom_strips  # noqa: E402

OUT = b.OUT / "seat_nomeld"
SEATS = {"B": "hand_right", "D": "hand_bottom"}
CUT = {"B": 0.79, "D": 0.65}
NOTE = "\n\n이 자리의 울기 묶음은 이미 따로 읽었고 이 사진에서는 잘라 냈습니다. melds 는 빈 배열로 둡니다."

# 사용자 지적(2026-10-27): nomeld·nomeld_p 는 울기를 잘라 낸 사진에 울기가 있는 사진용 문구("오른쪽 모서리까지",
# "손패 줄 보통 10~14장", melds 칸)를 그대로 써서 지시와 사진이 어긋났다 → 손패만 읽는 문구·스키마를 따로 짠다.
# 운영 SEAT_PROMPT_V2 에서 울기 관련 줄만 바꾸고 나머지(앞면 정의·loose·표기법·토막·참고표 안내)는 그대로.
HAND_PROMPT = ob.SEAT_PROMPT_V2.replace(
    "한 플레이어 자리(앞의 손패와 그 오른쪽 테이블 모서리까지)를 그 사람 쪽에서 본 방향으로 세운 것입니다.",
    "한 플레이어 앞의 손패 줄을 그 사람 쪽에서 본 방향으로 세운 것입니다. 이 사람의 울기 묶음(퐁·치·깡)은 이미 따로 읽었고,"
    " 놓여 있던 오른쪽 모서리는 사진에서 잘라 냈습니다. 그래서 손패 줄은 13장보다 적을 수 있습니다(울기 묶음 하나당 3장 적음).",
).replace(
    "이 사람의 손패 줄(보통 10~14장)의", "이 사람의 손패 줄의",
)
_i = HAND_PROMPT.index("- melds:")
_j = HAND_PROMPT.index("- loose:")
HAND_PROMPT = HAND_PROMPT[:_i] + HAND_PROMPT[_j:]
HAND_PROMPT = (HAND_PROMPT
               .replace("- loose: 손패 줄·떨어진 한 장·울기 묶음이 아닌", "- loose: 손패 줄·떨어진 한 장이 아닌")
               .replace("떨어진 한 장과 울기 묶음은 제외합니다.", "떨어진 한 장은 제외합니다.")
               .replace("장수·순서·앞면 여부·울기 묶음의 위치는", "장수·순서·앞면 여부는")
               .replace("첫 사진은 자리 전체이고", "첫 사진은 손패 줄 전체이고"))
assert "울기 묶음(퐁·치·깡)" in HAND_PROMPT and HAND_PROMPT.count("울기") == 2, HAND_PROMPT
HAND_SCHEMA = {**ob.SEAT_SCHEMA_V2,
               "properties": {k: v for k, v in ob.SEAT_SCHEMA_V2["properties"].items() if k != "melds"},
               "required": [k for k in ob.SEAT_SCHEMA_V2["required"] if k != "melds"]}
# hand_n: 판 상태 추적이 아는 울기 수로 손패 장수까지 알려 준다(정답 장수가 아니라 울기 수에서 나오는 값).
COUNT_NOTE = ("\n\n이 사람의 울기 묶음은 {m}개입니다. 그래서 손패 줄은 {n}장이고, 화료패를 손패 줄 끝에서 떨어뜨려 놓았으면"
              " 그 한 장(separate_tile)이 더 있습니다.")


def image(cond: str, s: str, p: str) -> bytes:
    im = Image.open(b.G / s / p / f"{SEATS[s]}.jpg").convert("RGB")
    if cond != "base":
        im = im.crop((0, 0, round(im.width * CUT[s]), im.height))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def request(cond: str, data: bytes, thoughts: bool = False, scene: str = "") -> dict:
    jpg = prepare_image(data, 3072)
    extra = [b.image_part(z, "ULTRA_HIGH") for z in zoom_strips(jpg, ob.SEAT_ZOOM_STRIPS)]
    extra.append(b.image_part(REF_SHEET.read_bytes(), None))
    schema = ob.SEAT_SCHEMA_V2
    if cond in ("hand", "hand_n"):
        prompt, schema = HAND_PROMPT, HAND_SCHEMA
        if cond == "hand_n":
            m = len(b.TRUTH[scene][2])
            prompt += COUNT_NOTE.format(m=m, n=13 - 3 * m)
    else:
        prompt = ob.SEAT_PROMPT_V2 + (NOTE if cond == "nomeld_p" else "")
    r = b.call(jpg, prompt, schema, "gemini-3.8-flash", "low", "ULTRA_HIGH", extra=extra, thoughts=thoughts)
    if "data" in r:
        r["data"].setdefault("melds", [])
    return r


def probe(n: int) -> None:
    """울기를 뺀 크롭에서 무엇을 생각하나: 생각 요약을 받아 생각한 것만 앞부분을 보여 준다."""
    jobs = [(s, p) for _ in range(n) for s in SEATS for p in b.PHOTOS[s]]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda j: (j, request("nomeld", image("nomeld", *j), thoughts=True)), jobs))
    out = []
    for (s, p), r in res:
        if r.get("think"):
            out.append({"scene": s, "photo": p, "think": r["think"], "thoughts": r.get("thoughts")})
            print(f"== {s} {p} think {r['think']}\n{(r.get('thoughts') or '')[:1500]}\n")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"생각한 호출 {len(out)}/{len(res)}")


def read(conds: list[str], runs: int, workers: int, tag: str) -> None:
    imgs = {(c, s, p): image(c, s, p) for c in conds for s in SEATS for p in b.PHOTOS[s]}
    jobs = [(c, s, p) for _ in range(runs) for s in SEATS for p in b.PHOTOS[s] for c in conds]

    def one(job):
        c, s, p = job
        r = request(c, imgs[job], scene=s)
        row = {"cond": c, "scene": s, "photo": p, **{k: r.get(k) for k in ("s", "in", "out", "think", "error")}}
        if "data" in r:
            j = b.judge(s, r["data"])
            if c != "base":  # 울기는 잘라 냈으니 지어내지 않았는지만 본다
                j["melds_ok"] = j["melds"] == []
            row.update(j)
        ok = row.get("hand_ok") and row.get("melds_ok")
        print(f"{c:9s} {s} {p} {row['s']}s think {row.get('think')} "
              f"{'OK' if ok else row.get('error') or 'X ' + str(row.get('hand')) + ' ' + str(row.get('melds'))}", flush=True)
        return row

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, jobs))
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{tag}.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    f.write_text(json.dumps(old + rows, ensure_ascii=False, indent=1), encoding="utf-8")
    sf.stats_rows(old + rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["read", "stats", "show", "probe", "prompt"])
    ap.add_argument("--conds", default="base,nomeld,nomeld_p")
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tag", default="read")
    a = ap.parse_args()
    if a.mode == "read":
        read(a.conds.split(","), a.runs, a.workers, a.tag)
    elif a.mode == "probe":
        probe(a.runs)
    elif a.mode == "prompt":
        print(HAND_PROMPT)
    elif a.mode == "show":  # 잘라 낸 크롭을 눈으로 확인
        OUT.mkdir(parents=True, exist_ok=True)
        for s in SEATS:
            for p in b.PHOTOS[s]:
                (OUT / f"{s}_{p}_nomeld.jpg").write_bytes(image("nomeld", s, p))
    else:
        for f in sorted(OUT.glob("*.json")):
            print("==", f.stem)
            sf.stats_rows(json.loads(f.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
