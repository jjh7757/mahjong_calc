"""겹침 순간 확인시키기 — 코드가 "두 숫자가 한 패에 겹친 순간" 을 찾고, 그 순간마다 시작 줄 · 원본 · 색 칠한 것을 맞댄 확인 그림을 더 줘서
Gemini 가 그 순간들을 따져 끝 줄의 실제 패 순서를 적게 한다(2026-11-18 저녁, 계획서 3단계 "추가 33").

사용자: 시작 줄 띠와 3.6초 띠를 위아래로 맞대 "이렇게 보면 잘못된 걸 알 수 있을텐데 어떻게 지시해야될까" → "진행해".
겹침은 9차례 모두에서 생긴다(맞힌 차례 포함 — 버린 패 색이 이웃에 옮겨 붙는 흔한 일) → "겹친 뒤로 믿지 마라" 가 아니라 "겹친 순간마다 확인하라".
k · j 는 모델이 적은 끝 줄 순서(end_order)에서 코드가 계산하고(순서가 온전할 때), 모델이 직접 적은 k · j 도 같이 남긴다.

  python -X utf8 sam2verify.py plan  --ids hard8              # 순간 목록 · 그림 만들기 · 입력 토큰 세기(호출 없음)
  python -X utf8 sam2verify.py run   --ids hard8 [--tag v1]   # → _work/sam2verify_1118/<tag>/<id>.json
  python -X utf8 sam2verify.py score --ids hard8 [--tag v1]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2img as si  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2stage as st  # noqa: E402
import sam2track as s1  # noqa: E402

OUT = hc.WORK / "sam2verify_1118"
MODEL = si.MODEL
OVL = 0.5          # 작은 마스크의 50% 넘게 겹치면 "한 패에 겹침"
MAX_MOMENTS = 8
HARD8 = ["r12_d02", "r13_d02", "r16_d01", "r16_d02", "r16_d13", "r16_d16", "r17_d03", "r17_d08"]

_HEAD = si.PROMPT[: si.PROMPT.index("답할 것:")]
_ANS = si.PROMPT[si.PROMPT.index("답할 것:"): si.PROMPT.index("참고:")]
_REF = si.PROMPT[si.PROMPT.index("참고:"): si.PROMPT.index("JSON 으로만 답하라")]

PROMPT_V = _HEAD + """## 확인할 순간(코드가 찾음)
- 패 한 장에는 숫자가 하나만 앉아야 한다. 코드가 프레임마다 마스크를 비교해 **두 숫자가 한 패에 겹친 순간**을 찾았다. 그 순간엔 둘 중 하나가 자기 패를 잃었거나(손 밑에서 숫자가 옆 패로 밀려 앉음), 버리는 패의 색이 이웃 패에 옮겨 붙은 것이다. **겹침은 흔하다** — 추적이 끝까지 맞는 차례에도 생긴다. 그러니 겹쳤다고 숫자를 버리지 말고, 순간마다 확인한다.
- 위 프레임들 뒤에 순간마다 **확인 그림**을 준다. 한 장 = 위 · 가운데 · 아래 세 띠(손패 줄 부분만 크게): 위 = 차례 시작 줄(숫자가 각자 제자리), 가운데 = 그 순간의 원본(색 없음), 아래 = 같은 순간의 색 칠한 것. 순간 하나에 "겹치기 바로 전 · 겹친 첫 프레임 · 겹침이 풀린 프레임" 을 준다.
- 순간마다: 가운데 원본 띠에서 줄에 선 패를 왼쪽부터 한 장씩 센다(손가락 · 손등 밑에 반쯤 가린 패도, 가장자리나 흰 면이 보이면 센다). 손에 들린 패는 따로 센다. 위 띠(시작 줄)와 맞대어, 겹친 두 숫자 중 어느 쪽이 실제 패를 따라온 것인지, 다른 하나의 실제 패는 어디 있는지(강으로 나감 · 숫자 없이 줄에 남음 · 손에 들림)를 정한다. 확인해 보니 숫자가 맞으면 그대로 믿는다.
- 손이 덮은 동안 줄의 패 수는 차례 시작 {n}장 → D 를 줄에 놓으면 {n} + 1 장 → 한 장을 버리면 다시 {n}장이다. 센 패 수가 숫자 수보다 많으면 숫자 없는 패가 있는 것이다 — 그 패가 D 인지, 숫자를 잃은 원래 패인지를 가린다(D 는 손이 패산 쪽에서 들고 온 패다).
- 확인한 것을 이어 붙여 **끝 프레임의 줄을 왼쪽부터 실제 패로** 적는다. 끝 프레임의 숫자 자리를 그대로 옮겨 적지 말고, 확인에서 바로잡은 것을 반영한다.

답할 것:
- checks: 순간마다 {{t: 겹친 첫 프레임 시각, pair: 겹친 두 숫자, tiles: 그 순간 원본에서 센 줄의 패 수, held: 손에 든 패 수, verdict: 어느 숫자가 맞고 다른 하나의 실제 패는 어디인지 한두 문장}}.
- end_order: 끝 프레임 줄({n}장)을 왼쪽부터 — 원래 번호 "1" ~ "{n}" 또는 뽑은 패 "D". 버려진 원래 패의 번호는 빠진다.
""" + _ANS.replace("답할 것:\n", "") + "\n" + _REF + """
JSON 으로만 답하라: steps = 본 것을 시각과 함께, checks, end_order, kind, k, j(해당 없으면 null), unsure, why = 근거 한두 문장.
"""

# v2(추가 34): 순간마다 1 ~ n 과 D 의 패가 각각 어디 있는지 빠짐없이 적게 함 + 한 프레임만 겹친 순간은 뺌.
# v1 에서 r13 2순은 "실제 2번 패는 오른쪽에 서 있다" 로 말만 하고 그 패를 안 찾았다 → 답의 꼴로 "패는 사라지지 않는다" 를 강제.
_V2_A = PROMPT_V.index("- 확인한 것을 이어 붙여")
_V2_B = PROMPT_V.index("답할 것:")
PROMPT_V2 = PROMPT_V[:_V2_A] + """- **패는 사라지지 않는다.** 순간마다 원래 패 1 ~ {n} 과 뽑은 패 D 가 각각 지금 어디 있는지를 **하나도 빠짐없이** 적는다: 줄에 서 있으면 원본 띠에서 왼쪽부터 몇 번째인지, 손에 들렸으면 "손", 강으로 나갔으면 "강", D 를 아직 안 뽑았으면 "없음". 숫자 색이 아니라 **원본 띠의 실제 패**를 기준으로 적는다 — 숫자가 겹치거나 빠진 곳은 바로 앞 깨끗한 프레임과 손의 움직임으로 그 패가 어디 갔는지 따져 정한다.
- 다 적은 뒤 맞춰 본다: 줄 자리 번호가 1 부터 빈 번호 · 겹친 번호 없이 이어지는가, 그 수가 원본에서 센 줄의 패 수와 같은가. 안 맞으면 어느 패를 잘못 놓았는지 다시 보고 고친다. "어떤 패는 오른쪽에 서 있다" 같은 말로 넘기지 말고 그 패의 자리 번호를 적는다.
- 확인 순간들의 자리표를 시간순으로 이어 **끝 프레임의 줄을 왼쪽부터 실제 패로** 적는다. 끝 프레임의 숫자 자리를 그대로 옮겨 적지 않는다.

""" + PROMPT_V[_V2_B:].replace(
    "- checks: 순간마다 {{t: 겹친 첫 프레임 시각, pair: 겹친 두 숫자, tiles: 그 순간 원본에서 센 줄의 패 수, held: 손에 든 패 수, verdict: 어느 숫자가 맞고 다른 하나의 실제 패는 어디인지 한두 문장}}.",
    "- checks: 순간마다 {{t: 겹친 첫 프레임 시각(그 순간의 확인 그림 중 '겹친 첫 프레임' 기준), pair: 겹친 두 숫자, tiles: 그 순간 원본에서 센 줄의 패 수, where: 패마다 자리 [{{tile: \"1\" ~ \"{n}\" 또는 \"D\", at: 줄 자리 번호(1 부터) 또는 \"손\" · \"강\" · \"없음\"}}] — {n} + 1 개 모두, verdict: 겹친 두 숫자 중 어느 쪽이 맞았고 다른 하나의 실제 패는 어디인지 한두 문장}}.")
assert "where: 패마다 자리" in PROMPT_V2

SCHEMA = {"type": "OBJECT", "properties": {
    "steps": {"type": "STRING"},
    "checks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "t": {"type": "STRING"}, "pair": {"type": "STRING"}, "tiles": {"type": "INTEGER"}, "held": {"type": "INTEGER"}, "verdict": {"type": "STRING"}},
        "required": ["t", "pair", "tiles", "held", "verdict"]}},
    "end_order": {"type": "ARRAY", "items": {"type": "STRING"}},
    "kind": {"type": "STRING", "enum": ["tsumogiri", "hand"]},
    "k": {"type": "INTEGER", "nullable": True}, "j": {"type": "INTEGER", "nullable": True},
    "unsure": {"type": "BOOLEAN"}, "why": {"type": "STRING"}},
    "required": ["steps", "checks", "end_order", "kind", "k", "j", "unsure", "why"]}


SCHEMA_V2 = {"type": "OBJECT", "properties": {
    "steps": {"type": "STRING"},
    "checks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "t": {"type": "STRING"}, "pair": {"type": "STRING"}, "tiles": {"type": "INTEGER"},
        "where": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"tile": {"type": "STRING"}, "at": {"type": "STRING"}}, "required": ["tile", "at"]}},
        "verdict": {"type": "STRING"}},
        "required": ["t", "pair", "tiles", "where", "verdict"]}},
    "end_order": {"type": "ARRAY", "items": {"type": "STRING"}},
    "kind": {"type": "STRING", "enum": ["tsumogiri", "hand"]},
    "k": {"type": "INTEGER", "nullable": True}, "j": {"type": "INTEGER", "nullable": True},
    "unsure": {"type": "BOOLEAN"}, "why": {"type": "STRING"}},
    "required": ["steps", "checks", "end_order", "kind", "k", "j", "unsure", "why"]}
VER = {"v1": (PROMPT_V, SCHEMA, 1), "v2": (PROMPT_V2, SCHEMA_V2, 2)}   # (프롬프트, 스키마, 순간으로 칠 최소 겹침 프레임 수)


def ids_of(s: str) -> list:
    return HARD8 if s == "hard8" else (si.NEW17 if s == "new17" else s.split(","))


def overlaps(tid: str) -> dict:
    """프레임마다 겹친 숫자 쌍. 캐시 = <v1 폴더>/overlaps.json."""
    d = s1.run_dir(tid, si.V1)
    f = d / "overlaps.json"
    if f.exists():
        return hc.jload(f)
    tr = hc.jload(d / "track.json")
    H, W = tr["shape"]
    n = tr["plan"]["n"]
    M = np.load(d / "masks.npz")
    rows = []
    for fi in range(len(tr["frames"])):
        mk = {}
        for o in range(1, n + 1):
            k = f"{fi}_{o}"
            if k in M:
                a = np.unpackbits(M[k])[: H * W].reshape(H, W).astype(bool)
                if a.sum() >= 50:
                    mk[o] = a
        pairs = []
        os_ = sorted(mk)
        for i, o1 in enumerate(os_):
            for o2 in os_[i + 1:]:
                if (mk[o1] & mk[o2]).sum() > OVL * min(mk[o1].sum(), mk[o2].sum()):
                    pairs.append([o1, o2])
        rows.append(pairs)
    out = {"id": tid, "ovl": OVL, "rows": rows}
    hc.jsave(f, out, indent=None)
    return out


def moments(tid: str, min_len: int = 1) -> list:
    """겹친 쌍마다 이어진 구간 → 순간 [첫 프레임, 풀린 프레임, 쌍]. 첫 프레임이 같은 것끼리 묶고 시간순 앞 MAX_MOMENTS 개."""
    rows = overlaps(tid)["rows"]
    F = len(rows)
    eps = []
    open_ = {}
    for fi, prs in enumerate(rows + [[]]):
        cur = {tuple(p) for p in prs}
        for p in list(open_):
            if p not in cur:
                eps.append((open_.pop(p), fi, p))
        for p in cur:
            open_.setdefault(p, fi)
    by_start: dict = {}
    for s, e, p in sorted(eps):
        if e - s < min_len:      # e = 풀린 첫 프레임 → 겹친 프레임 수 = e - s
            continue
        by_start.setdefault(s, []).append((e, p))
    out = []
    for s in sorted(by_start):
        e = max(x[0] for x in by_start[s])
        out.append({"start": s, "end": min(e, F - 1), "pairs": [list(x[1]) for x in by_start[s]]})
    return out[:MAX_MOMENTS]


def font(sz=26):
    try:
        return ImageFont.truetype("malgunbd.ttf", sz)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def check_image(tid: str, fi: int, title: str) -> bytes:
    top = st.row_crop(tid, 0, "M")
    mid = st.row_crop(tid, fi, "raw")
    bot = st.row_crop(tid, fi, "M")
    w, h = top.size
    bar = 40
    im = Image.new("RGB", (w, bar + 3 * h + 8), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    dr.text((8, 6), title, fill=(200, 0, 0), font=font())
    im.paste(top, (0, bar))
    im.paste(mid, (0, bar + h + 4))
    im.paste(bot, (0, bar + 2 * h + 8))
    for y, lab in ((bar, "시작 줄"), (bar + h + 4, "그 순간 원본"), (bar + 2 * h + 8, "그 순간 색")):
        dr.text((w - 8, y + 4), lab, fill=(255, 255, 0), font=font(22), anchor="ra", stroke_width=3, stroke_fill=(0, 0, 0))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=88)
    return b.getvalue()


def check_parts(tid: str, types, min_len: int = 1) -> tuple[list, list]:
    meta = hc.jload(si.frame_dir(tid, "M") / "meta.json")
    labs = [hc.mss(ms) for ms in meta["frames"]]
    ps, info = [], []
    for k, mo in enumerate(moments(tid, min_len), 1):
        pr = " · ".join(f"{a}·{b}" for a, b in mo["pairs"])
        for role, fi in (("겹치기 바로 전", mo["start"] - 1), ("겹친 첫 프레임", mo["start"]), ("겹침이 풀린 프레임", mo["end"])):
            if fi < 0:
                continue
            title = f"확인 {k} — {labs[mo['start']]} 숫자 {pr} 한 패에 겹침 · 이 그림 = {role} {labs[fi]}"
            ps += [title, st.img_part(types, check_image(tid, fi, title))]
        info.append({"k": k, "t": labs[mo["start"]], "pairs": mo["pairs"], "frames": [mo["start"] - 1, mo["start"], mo["end"]]})
    return ps, info


def contents(tid: str, types, ver: str = "v1") -> tuple[list, list]:
    prompt, _, min_len = VER[ver]
    base = si.parts_of(tid, types, "M")
    n = hc.jload(si.frame_dir(tid, "M") / "meta.json")["n"]
    base[0] = prompt.format(n=n)
    cps, info = check_parts(tid, types, min_len)
    return base[:-1] + ["## 확인 그림"] + cps + [f"위 프레임과 확인 그림을 보고 답하라. 차례를 시작할 때 줄은 {n}장이다."], info


def from_order(order: list, n: int):
    """끝 줄 순서 → (k, j). 온전하지 않으면 None."""
    if not order or len(order) != n or order.count("D") != 1:
        return None
    nums = [int(x) for x in order if x != "D" and str(x).isdigit()]
    if len(nums) != n - 1 or len(set(nums)) != n - 1 or any(not 1 <= x <= n for x in nums):
        return None
    k = next(x for x in range(1, n + 1) if x not in nums)
    return k, order.index("D") + 1


def run_one(tid: str, a) -> dict:
    import gemframes as gf
    from google.genai import types
    c = gf.client()
    cs, info = contents(tid, types, a.ver)
    kw = {"thinking_config": types.ThinkingConfig(thinking_level=a.think)} if a.think else {}
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=VER[a.ver][1], **kw)
    t0, err = time.perf_counter(), ""
    for attempt in range(3):
        try:
            r = c.models.generate_content(model=a.gmodel, contents=cs, config=cfg)
            um = r.usage_metadata
            d = json.loads(r.text)
            n = hc.jload(si.frame_dir(tid, "M") / "meta.json")["n"]
            kj = from_order(d.get("end_order") or [], n)
            res = {"id": tid, "ver": a.ver, "model": a.gmodel, "think_level": a.think, "model_version": getattr(r, "model_version", None), "moments": info, "raw": d, "kind": d.get("kind"), "k_model": d.get("k"), "j_model": d.get("j"),
                   "order_ok": kj is not None, "unsure": d.get("unsure"), "why": d.get("why"),
                   "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                   "think": getattr(um, "thoughts_token_count", 0) or 0, "attempt": attempt + 1}
            res["k"], res["j"] = (kj if (kj and d.get("kind") == "hand") else (d.get("k"), d.get("j")))
            return res
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(8 * (attempt + 1))
    return {"id": tid, "error": err, "kind": None, "k": None, "j": None, "in": 0, "out": 0, "think": 0}


def cmd_plan(a):
    import gemframes as gf
    from google.genai import types
    c = gf.client()
    tot = 0
    od = OUT / "plan"
    od.mkdir(parents=True, exist_ok=True)
    for tid in ids_of(a.ids):
        cs, info = contents(tid, types, a.ver)
        r = c.models.count_tokens(model=a.gmodel, contents=cs)
        tot += r.total_tokens
        print(tid, f"순간 {len(info)}개:", " | ".join(f"{x['t']} {x['pairs']}" for x in info), f"→ {r.total_tokens:,} 토큰", flush=True)
        if a.save:
            for x in info:
                Image.open(io.BytesIO(check_image(tid, x["frames"][1], f"{tid} 확인 {x['k']} {x['t']} {x['pairs']}"))).save(od / f"{tid}_m{x['k']}.jpg")
    print(f"합 {tot:,} 토큰 → 입력 약 {tot * 0.75e-6:.2f}달러(생각 · 출력 따로)")


def cmd_run(a):
    od = OUT / a.tag
    od.mkdir(parents=True, exist_ok=True)
    ids = [t for t in ids_of(a.ids) if a.force or not (od / f"{t}.json").exists()]
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda t: run_one(t, a), ids):
            r["at"] = hc.hms(int(time.time() * 1000), date=True)
            hc.jsave(od / f"{r['id']}.json", r)
            print(r["id"], r.get("kind"), r.get("k"), r.get("j"), "order_ok" if r.get("order_ok") else "", r.get("error", "")[:80], flush=True)
    cmd_score(a)


def cmd_score(a):
    truth = s1.truth_all()
    od = OUT / a.tag
    T = Tm = quiet = 0
    usage = {"in": 0, "out": 0, "think": 0}
    ids = ids_of(a.ids)
    for tid in ids:
        f = od / f"{tid}.json"
        if not f.exists():
            print(tid, "없음")
            continue
        r = hc.jload(f)
        u = truth[tid]
        ok = m.right(m.norm(r), u)
        okm = m.right(m.norm({"kind": r.get("kind"), "k": r.get("k_model"), "j": r.get("j_model")}), u)
        T += ok
        Tm += okm
        quiet += (not ok) and not r.get("unsure")
        for k in usage:
            usage[k] += r.get(k, 0) or 0
        order = (r.get("raw") or {}).get("end_order")
        print(f"{tid:8s} 정답 {u['k_id']}·{u['j_closed']} | 순서→ {r.get('k')}·{r.get('j')}{'?' if r.get('unsure') else ''} {'✓' if ok else '✗'} "
              f"| 모델 k·j {r.get('k_model')}·{r.get('j_model')} {'✓' if okm else '✗'} | 순간 {len(r.get('moments', []))} | 끝 순서 {order}")
    usd = usage["in"] * 0.75e-6 + (usage["out"] + usage["think"]) * 3.75e-6
    print(f"맞음(끝 순서에서 계산) {T}/{len(ids)} · 모델이 적은 k·j {Tm}/{len(ids)} · 조용한 틀림 {quiet} | 입력 {usage['in']:,} · 출력 {usage['out']:,} · 생각 {usage['think']:,} → 약 {usd:.2f}달러")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "score"):
        q = sp.add_parser(name)
        q.add_argument("--ids", default="hard8")
        q.add_argument("--tag", default="v1")
        q.add_argument("--ver", default="v1", choices=["v1", "v2"])
        q.add_argument("--gmodel", default=MODEL, help="예 gemini-3.1-pro-preview")
        q.add_argument("--think", default=None, help="생각 수준 low | high (없으면 모델 기본값)")
        if name == "plan":
            q.add_argument("--save", action="store_true")
        if name == "run":
            q.add_argument("--workers", type=int, default=4)
            q.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"plan": cmd_plan, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
