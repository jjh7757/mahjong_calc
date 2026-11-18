"""단계로 나눠 묻기 — 마스크 그림(M)을 한 번에 다 주고 답을 받는 대신 세 번 묻는다(2026-11-18 저녁, 계획서 3단계 "추가 32").

r13 2순에서 Gemini 는 색을 사실로 믿고 "색 없는 패 = D" 로 이야기를 맞췄다(117장을 한 번에 훑고, 패를 세지 않음, 생각 2.5 ~ 3.7천 토큰).
사람은 "이상하다 → 그 프레임을 멈추고 확대해 센다" 를 했다. 그 순서를 모델에게 시킨다.

  1단계 찾기:  M 그림 전부 → D 를 줄에 놓는 시각 범위 · 버리는 시각
  2단계 세기:  그 범위 앞뒤 프레임의 손패 줄을 크게 잘라(원본 위 · 색 칠한 것 아래 한 쌍) → 프레임마다 패 수 · 패마다 앉은 숫자
  3단계 답:    2단계 표(글) + 같은 쌍 그림 + 시작 · 끝 프레임 → kind · k · j(답 꼴 · 채점은 sam2img 와 같음)

  python -X utf8 sam2stage.py run --ids r13_d02 [--tag try1]   # → _work/sam2stage_1118/<tag>/<id>.json (단계별 답 · 토큰)
  python -X utf8 sam2stage.py show --ids r13_d02 [--tag try1]  # 단계별 답 보기
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2img as si  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402

OUT = hc.WORK / "sam2stage_1118"
MODEL = si.MODEL
PAD_BEFORE, PAD_AFTER = 1.0, 2.0   # 2단계: 놓는 범위 앞 1초 · 뒤 2초
MAX_PAIRS = 24                     # 2단계 쌍 그림 최대 장수(넘으면 고르게 솎음)
SCALE = 2                          # 잘라 낸 띠를 2배로

_HEAD = si.PROMPT[: si.PROMPT.index("답할 것:")]
_ANS = si.PROMPT[si.PROMPT.index("답할 것:"): si.PROMPT.index("참고:")]
_REF = si.PROMPT[si.PROMPT.index("참고:"): si.PROMPT.index("JSON 으로만 답하라")]

P1 = _HEAD + """이번에는 답(k · j)을 내지 말고, 다음 단계에서 크게 확대해 볼 구간만 찾는다.

답할 것:
- insert_from · insert_to: 뽑은 패 D 를 줄 안이나 줄 끝에 놓는 동작이 일어나는 구간(프레임 앞에 적힌 시각 그대로, 예 "27:47.1"). 손이 D 를 쥐고 줄에 닿기 시작한 프레임 ~ D 를 놓고 손이 줄에서 떨어진 프레임. 손에 가려 정확히 모르면 넉넉하게 잡는다. D 를 줄에 놓지 않고 바로 버렸으면 둘 다 null.
- discard_at: 줄(또는 D)에서 패 한 장이 강으로 나가는 프레임의 시각.
- why: 근거 한두 문장.
JSON 으로만 답하라.
"""

P2 = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 프레임 몇 장이다. 프레임마다 같은 순간을 **두 장**으로 준다:
- 첫째 = 원본(손패 줄 부분만 2배로 크게 자름), 둘째 = 같은 원본에 영상 추적 모델(SAM 2)이 색과 숫자를 칠한 것.
- 그림의 왼쪽 = 그 사람의 왼손 쪽. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 무늬는 안 보인다. 패는 모두 똑같이 생겼다.
- 차례를 시작할 때 줄은 {n}장이고 숫자 1 ~ {n} 은 시작 줄의 왼쪽부터 붙인 번호다. 뽑아 온 패 D 에는 숫자가 없다. 추적은 틀릴 수 있다 — 숫자가 옆 패로 옮겨 붙거나, 한 패에 숫자 둘이 겹치거나, 숫자 없는 패가 생긴다.

할 일 — 프레임마다 따로, **원본 그림에서** 줄에 선 패를 왼쪽부터 한 장씩 센다:
- 손가락 · 손등에 반쯤 가린 패도 가장자리 · 흰 면 · 색 띠가 조금이라도 보이면 센다. 손에 들려 줄 위로 들린 패는 줄에 넣지 않는다(held 에 적는다).
- 줄이 둘로 갈라져 있으면 왼쪽 무리부터 이어서 센다.
- 그다음 둘째 그림에서, 센 패마다 그 위에 앉은 숫자를 적는다(없으면 "-", 둘이면 "4/5").

답(JSON): frames = [{{t: 프레임 시각, tiles: 센 패 수, sure: 센 수를 확신하면 true, held: 손에 들린 패 수, labels: 왼쪽부터 패마다 숫자 목록, note: 가린 곳 · 이상한 점 한 줄}}]
"""

P3 = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 것이다. 이 사람의 **한 차례**(패산에서 한 장을 뽑아 오고, 한 장을 강에 버림)를 보고 버린 칸 · 뽑은 패가 들어간 칸을 정한다.
이 차례를 시작할 때 줄은 {n}장이다. 뽑아 온 패를 D 라고 부르자. 패는 세워져 있어 위에서는 등만 보이고 모두 똑같이 생겼다. 그림의 왼쪽 = 그 사람의 왼손 쪽.

주는 것:
1. 시작 프레임(색 · 숫자 칠한 것) — 줄 {n}장에 왼쪽부터 숫자 1 ~ {n}. 숫자는 영상 추적 모델(SAM 2)이 프레임마다 "같은 패" 라고 본 곳에 칠한 것이고, D 에는 숫자가 없다.
2. D 를 줄에 놓는 순간 앞뒤 프레임을 크게 자른 쌍(원본 · 색 칠한 것).
3. 앞 단계에서 그 프레임들을 하나씩 세어 적은 표(아래) — 프레임마다 줄에 선 패 수와 패마다 앉은 숫자.
4. 끝 프레임(색 · 숫자 칠한 것) — 버리고 정리해 다시 {n}장.

추적은 틀릴 수 있다. 특히 손이 줄을 덮은 동안 숫자가 한 칸씩 밀려 앉으면, 끝 프레임에서 숫자는 가지런해 보여도 실제 패와 어긋나 있고 "숫자 없는 패" 가 D 가 아닐 수 있다.
그래서 이렇게 판단한다:
- D 를 줄에 놓은 뒤 버리기 전까지 줄은 {n} + 1 장이어야 한다. 표에서 그 순간 패 수가 숫자 수보다 많으면, 숫자 없는 패가 D 인지 · 번호를 잃은 원래 패인지를 그 프레임 그림에서 가린다(D 는 손이 들고 와서 놓은 패다).
- 그 순간 D 가 왼쪽부터 몇 번째 패인지 정한 뒤, 그 뒤 프레임에서 D 와 이웃 패가 어떻게 움직였는지(버린 패가 빠진 틈 · 정리)를 따라 끝 줄에서의 자리를 정한다. 끝 프레임의 숫자 자리를 그대로 믿지 않는다.

앞 단계 표:
{table}

""" + _ANS.replace("답할 것:", "답할 것:") + """
JSON 으로만 답하라: steps = 판단 과정(표의 어느 프레임에서 무엇을 셌는지 포함), kind, k, j(해당 없으면 null), unsure, why = 근거 한두 문장.
"""

S1 = {"type": "OBJECT", "properties": {"insert_from": {"type": "STRING", "nullable": True}, "insert_to": {"type": "STRING", "nullable": True},
                                       "discard_at": {"type": "STRING", "nullable": True}, "why": {"type": "STRING"}},
      "required": ["insert_from", "insert_to", "discard_at", "why"]}
S2 = {"type": "OBJECT", "properties": {"frames": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "t": {"type": "STRING"}, "tiles": {"type": "INTEGER"}, "sure": {"type": "BOOLEAN"}, "held": {"type": "INTEGER"},
    "labels": {"type": "ARRAY", "items": {"type": "STRING"}}, "note": {"type": "STRING"}},
    "required": ["t", "tiles", "sure", "held", "labels", "note"]}}}, "required": ["frames"]}


def sec_of(label: str | None):
    if not label:
        return None
    mm = re.search(r"(\d+):(\d+(?:\.\d+)?)", label)
    return int(mm.group(1)) * 60 + float(mm.group(2)) if mm else None


def nearest(labels_sec: list, s: float) -> int:
    # 분이 넘어가는 경계(59 → 00)는 이 차례들 안에서 없다고 봄 — 있으면 차이가 커서 드러난다
    return int(np.argmin([abs(x - s) for x in labels_sec]))


def jpg(im: Image.Image, q: int = 90) -> bytes:
    b = io.BytesIO()
    im.save(b, "JPEG", quality=q)
    return b.getvalue()


def row_crop(tid: str, fi: int, arm: str) -> Image.Image:
    tr = hc.jload(s1.run_dir(tid, si.V1) / "track.json")
    a = tr["plan"]["a_boxes"]
    yc = float(np.median([(b[1] + b[3]) / 2 for b in a]))
    hh = float(np.median([b[3] - b[1] for b in a]))
    src = (s1.run_dir(tid, si.V1) / "frames" / f"{fi:05d}.jpg") if arm == "raw" else (si.frame_dir(tid, "M") / f"{fi:05d}.jpg")
    im = Image.open(src).convert("RGB")
    y0, y1 = max(0, int(yc - 1.4 * hh)), min(im.height, int(yc + 1.4 * hh))
    c = im.crop((0, y0, im.width, y1))
    return c.resize((c.width * SCALE, c.height * SCALE), Image.LANCZOS)


def call(c, types, contents, schema):
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema)
    t0, err = time.perf_counter(), ""
    for attempt in range(3):
        try:
            r = c.models.generate_content(model=MODEL, contents=contents, config=cfg)
            um = r.usage_metadata
            return json.loads(r.text), {"s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                                        "think": getattr(um, "thoughts_token_count", 0) or 0, "attempt": attempt + 1}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(8 * (attempt + 1))
    raise RuntimeError(err)


def img_part(types, data: bytes):
    p = types.Part.from_bytes(data=data, mime_type="image/jpeg")
    p.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
    return p


def run_one(c, types, tid: str) -> dict:
    meta = hc.jload(si.frame_dir(tid, "M") / "meta.json")
    n, fl = meta["n"], meta["frames"]
    labs = [hc.mss(ms) for ms in fl]
    secs = [sec_of(x) for x in labs]
    res = {"id": tid, "model": MODEL}
    # 1단계 — M 팔과 같은 그림 전부(같은 parts_of 를 쓰되 맺음만 다름)
    ps = si.parts_of(tid, types, "M")
    ps[0] = P1.format(n=n)
    ps[-1] = "위 프레임을 보고 구간만 답하라."
    a1, u1 = call(c, types, ps, S1)
    res["s1"], res["u1"] = a1, u1
    s_from, s_to, s_dis = sec_of(a1.get("insert_from")), sec_of(a1.get("insert_to")), sec_of(a1.get("discard_at"))
    if s_from is None:   # 놓는 동작이 없다고 봄 → 버림 둘레를 대신 크게 본다
        s_from = s_to = s_dis if s_dis is not None else secs[len(secs) // 2]
    if s_to is None or s_to < s_from:
        s_to = s_from
    i0, i1 = nearest(secs, s_from - PAD_BEFORE), nearest(secs, s_to + PAD_AFTER)
    pick = list(range(i0, i1 + 1))
    if len(pick) > MAX_PAIRS:
        pick = sorted({pick[round(k * (len(pick) - 1) / (MAX_PAIRS - 1))] for k in range(MAX_PAIRS)})
    res["pairs"] = [labs[i] for i in pick]
    # 2단계 — 크게 자른 쌍
    ps = [P2.format(n=n)]
    pair_parts = []
    for i in pick:
        pair_parts += [f"프레임 {labs[i]} — 원본", img_part(types, jpg(row_crop(tid, i, "raw"))),
                       f"프레임 {labs[i]} — 색 칠한 것", img_part(types, jpg(row_crop(tid, i, "M")))]
    ps += pair_parts + ["위 프레임마다 세어 답하라."]
    a2, u2 = call(c, types, ps, S2)
    res["s2"], res["u2"] = a2, u2
    table = "\n".join(f"- {f.get('t')}: 패 {f.get('tiles')}장{'' if f.get('sure') else '(불확실)'} · 손에 든 패 {f.get('held')} · 숫자 {' '.join(f.get('labels') or [])} · {f.get('note', '')}"
                      for f in a2.get("frames", []))
    # 3단계 — 표 + 시작 · 쌍 · 끝
    ps = [P3.format(n=n, table=table), f"1. 시작 프레임 {labs[0]}", si.parts_of(tid, types, "M")[2], "2. 크게 자른 쌍"]
    ps += pair_parts + [f"4. 끝 프레임 {labs[-1]}", si.parts_of(tid, types, "M")[-2], "위를 보고 답하라."]
    a3, u3 = call(c, types, ps, m.GEM_SCHEMA)
    res["s3"], res["u3"] = a3, u3
    res.update({"kind": a3.get("kind"), "k": a3.get("k"), "j": a3.get("j"), "unsure": a3.get("unsure"), "why": a3.get("why")})
    tot = {k: sum(res[u][k] for u in ("u1", "u2", "u3")) for k in ("in", "out", "think")}
    res["usage"] = tot
    res["usd"] = round(tot["in"] * 0.75e-6 + (tot["out"] + tot["think"]) * 3.75e-6, 3)
    return res


def cmd_run(a):
    import gemframes as gf
    from google.genai import types
    c = gf.client()
    od = OUT / a.tag
    od.mkdir(parents=True, exist_ok=True)
    truth = s1.truth_all()
    for tid in a.ids.split(","):
        f = od / f"{tid}.json"
        if f.exists() and not a.force:
            print("있음 — 건너뜀", f)
            continue
        r = run_one(c, types, tid)
        r["at"] = hc.hms(int(time.time() * 1000), date=True)
        hc.jsave(f, r)
        u = truth[tid]
        ok = m.right(m.norm(r), u)
        print(f"{tid}: 1단계 {r['s1'].get('insert_from')}~{r['s1'].get('insert_to')} 버림 {r['s1'].get('discard_at')} | 쌍 {len(r['pairs'])}장 | "
              f"답 {r['kind']} {r['k']}·{r['j']}{'?' if r.get('unsure') else ''} — 정답 {u['k_id']}·{u['j_closed']} {'✓' if ok else '✗'} | {r['usage']} 약 {r['usd']}달러", flush=True)


def cmd_show(a):
    for tid in a.ids.split(","):
        r = hc.jload(OUT / a.tag / f"{tid}.json")
        print("== 1단계", json.dumps(r["s1"], ensure_ascii=False))
        print("== 2단계")
        for fr in r["s2"].get("frames", []):
            print("  ", json.dumps(fr, ensure_ascii=False))
        print("== 3단계", json.dumps(r["s3"], ensure_ascii=False))
        print("토큰", r["usage"], r["usd"], "달러")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "show"):
        q = sp.add_parser(name)
        q.add_argument("--ids", required=True)
        q.add_argument("--tag", default="try1")
        if name == "run":
            q.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"run": cmd_run, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
