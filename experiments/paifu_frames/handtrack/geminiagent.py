"""Gemini 에게 Opus 와 같은 "행동" 을 시키기 — 함수 호출로 프레임을 골라 열고 잘라 키우며 읽기(2026-11-18 밤, 계획서 3단계 "추가 40").

Opus 하위 에이전트는 프레임을 스스로 골라 열고 원본을 잘라 키워 17/17(표 12-58). Gemini Flash 는 그림 전부를 한 번에 받아 4/8(표 12-51 ~ 12-56).
차이가 모델이 아니라 행동(다시 들여다보기)인지 본다. 재료 = opusread_1118/<id>/ 와 같은 것(frames.txt · check/), 지식 = TASK.md 와 같은 내용.

도구: view(프레임 번호들, color|raw) · zoom(프레임, x0, x1, [y0, y1], color|raw) · check(확인 그림 이름) · answer(…) — answer 를 부르면 끝.
  python -X utf8 geminiagent.py run --ids r12_d02 [--tag g1] [--max-steps 30] [--think high]
  python -X utf8 geminiagent.py score --ids hard8 [--tag g1]
결과 _work/geminiagent_1118/<tag>/<id>.json(답 · 도구 호출 기록 · 토큰) — 정답 · 다른 판독 답은 안 넣음.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402
import sam2verify as sv  # noqa: E402

OUT = hc.WORK / "geminiagent_1118"
SRC = hc.WORK / "opusread_1118"
MODEL = "gemini-3.8-flash"
# 100만 토큰당 달러: (입력, 출력·생각) — 프롬프트 20만 이하 / 초과. 캐시 입력은 입력의 1/4 로 어림(추가 40 과 같은 셈).
PRICE = {"gemini-3.8-flash": ((0.75, 3.75), (0.75, 3.75)),
         "gemini-3.1-pro-preview": ((2.0, 12.0), (4.0, 18.0))}   # ai.google.dev/gemini-api/docs/pricing (11-19 확인)
MAX_VIEW = 6
STRIP_ROWS, STRIP_MAX = 8, 32   # strip: 한 그림에 8줄, 한 번에 32줄까지(추가 40 g3 — Opus 가 스스로 만든 sheet.py 와 같은 일)

PROMPT = """너는 위에서 내려다본 녹화에서 마작 대국자 한 사람의 **세운 손패 줄**을 한 차례 읽는다. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 **모든 패가 똑같이 생겼다** — 읽는 것은 위치뿐이다.
이 차례 = 패산에서 한 장을 뽑아 오고(뽑은 패 = **D**), 한 장을 강에 버림. 차례를 시작할 때 줄은 **{n}장**이다. 그림은 그 사람 시점(그림 왼쪽 = 그 사람 왼손 쪽, 아래쪽 흰 띠 = 탁자 테두리). 다른 사람 팔이 지나가기도 한다.

## 재료(도구로 본다)
- 프레임 {F}장(초당 5장, 번호 0 ~ {last}). 프레임마다 두 가지 그림이 있다:
  - **color** = 영상 추적 모델(SAM 2)이 첫 프레임에서 줄의 {n}장에 왼쪽부터 숫자 1 ~ {n} 을 붙이고, 그 뒤 프레임마다 "같은 패" 라고 본 곳에 같은 색 · 숫자를 칠한 것. D 에는 숫자가 없다.
  - **raw** = 같은 순간의 원본(색 없음).
- **추적은 틀릴 수 있다:** 손에 들려 혼자 움직이는 패는 대체로 따라간다. 버린 패의 색은 이웃 패로 옮겨 붙는 일이 많다(한 패에 숫자 둘). 손이 줄을 덮은 동안 줄이 밀리거나 패가 끼워지면 숫자가 한 칸씩 밀려 앉거나 옛 자리로 뛰어 돌아온다 — 그러면 끝 프레임의 숫자는 가지런해 보여도 실제 패와 어긋나고, 숫자 없는 패가 D 가 아닐 수 있다.
- **확인 그림**(check): 코드가 찾은 "두 숫자가 한 패에 겹친 순간" 마다 위 = 차례 시작 줄 · 가운데 = 그 순간 원본 · 아래 = 그 순간 색(손패 줄 부분 2배). 겹침은 흔하다(추적이 맞는 차례에도) — 확인할 곳일 뿐이다.

## 도구
- `view(frames, kind)` — 프레임 여러 장(한 번에 {mv}장까지)을 본다. kind = color | raw.
- `zoom(frame, x0, x1, y0, y1, kind)` — 한 프레임의 일부를 잘라 3배로 키워 본다(좌표는 그 프레임 그림의 화소, 그림 크기 {W} × {H}). y0 · y1 을 비우면 높이 전체.
- `check(name)` — 확인 그림 한 장을 본다.
- `strip(start, end, step, x0, x1, y0, y1, kind)` — **같은 영역**을 start ~ end 프레임에서 step 장마다 잘라 시간순으로 위아래로 쌓아 본다(줄마다 왼쪽에 프레임 번호, 한 장에 {sr}줄씩 · 한 번에 {sm}줄까지). 패 하나가 손 밑에서 어떻게 움직였는지 이어서 볼 때 쓴다.
- `answer(...)` — 답을 낸다. 부르면 끝난다.

## 하는 법
- **패는 사라지지 않는다.** 줄의 패 수는 {n} → D 를 줄에 놓으면 {n}+1 → 한 장 버리면 {n}. 손이 덮은 순간에는 원본을 확대해 손가락 밑 패까지 센다. 숫자 하나하나에 대해 "그 패는 지금 실제로 어디 있나" 를 원본에서 확인한다 — 말로 넘기지 않는다.
- 먼저 프레임을 띄엄띄엄 훑어 언제 무슨 일이 있었는지 잡고, 손이 줄을 덮은 구간 · 숫자가 겹치거나 빠진 곳은 앞뒤 프레임을 촘촘히 보고 원본을 확대한다. 서둘러 답하지 말고 의심 가는 곳을 끝까지 본다.
- D 를 끝에 붙여 두고 한 장을 버리는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 버리는 사람, 버리기 전에 패를 옮기거나 맞바꾸는 사람, 뽑은 패를 그대로 버리는 사람(쯔모기리)이 다 있다. 끝 프레임까지 본다.

## 답(answer 도구)
- kind: "hand"(줄에 있던 패를 버림) 또는 "tsumogiri"(D 를 그대로 버림, 줄의 패는 안 바뀜)
- k: 버린 패가 원래 줄 {n}장에서 왼쪽부터 몇 번째였나(D 는 세지 않음, tsumogiri 면 null)
- j: 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째인가(끝 그대로면 {n}, tsumogiri 면 null)
- end_order: 끝 줄 왼쪽부터 실제 패 — 원래 번호 "1" ~ "{n}" 또는 "D"(tsumogiri 면 "1" ~ "{n}")
- unsure: 맞을 가능성 70% 밑이면 true · tracking_errors: 추적이 틀린 곳과 근거(프레임 번호) · why: 근거 3 ~ 5문장(프레임 번호와 함께)
"""


def decls(types, strip: bool = False):
    S = types.Schema
    T = types.Type
    extra = [types.FunctionDeclaration(name="strip", description="같은 영역을 여러 프레임에서 잘라 시간순으로 쌓아 본다",
                                       parameters=S(type=T.OBJECT, properties={"start": S(type=T.INTEGER), "end": S(type=T.INTEGER), "step": S(type=T.INTEGER),
                                                                              "x0": S(type=T.INTEGER), "x1": S(type=T.INTEGER), "y0": S(type=T.INTEGER), "y1": S(type=T.INTEGER),
                                                                              "kind": S(type=T.STRING, enum=["color", "raw"])},
                                                    required=["start", "end", "step", "x0", "x1", "kind"]))] if strip else []
    return [types.Tool(function_declarations=extra + [
        types.FunctionDeclaration(name="view", description="프레임 여러 장을 본다",
                                  parameters=S(type=T.OBJECT, properties={"frames": S(type=T.ARRAY, items=S(type=T.INTEGER)), "kind": S(type=T.STRING, enum=["color", "raw"])}, required=["frames", "kind"])),
        types.FunctionDeclaration(name="zoom", description="한 프레임의 일부를 잘라 3배로 키운다",
                                  parameters=S(type=T.OBJECT, properties={"frame": S(type=T.INTEGER), "x0": S(type=T.INTEGER), "x1": S(type=T.INTEGER),
                                                                         "y0": S(type=T.INTEGER), "y1": S(type=T.INTEGER), "kind": S(type=T.STRING, enum=["color", "raw"])},
                                               required=["frame", "x0", "x1", "kind"])),
        types.FunctionDeclaration(name="check", description="확인 그림 한 장을 본다",
                                  parameters=S(type=T.OBJECT, properties={"name": S(type=T.STRING)}, required=["name"])),
        types.FunctionDeclaration(name="answer", description="답을 낸다(부르면 끝)",
                                  parameters=S(type=T.OBJECT, properties={
                                      "kind": S(type=T.STRING, enum=["hand", "tsumogiri"]), "k": S(type=T.INTEGER, nullable=True), "j": S(type=T.INTEGER, nullable=True),
                                      "end_order": S(type=T.ARRAY, items=S(type=T.STRING)), "unsure": S(type=T.BOOLEAN),
                                      "tracking_errors": S(type=T.STRING), "why": S(type=T.STRING)},
                                      required=["kind", "k", "j", "end_order", "unsure", "tracking_errors", "why"])),
    ])]


class Turn:
    def __init__(self, tid: str):
        self.tid = tid
        d = SRC / tid
        self.rows = []
        for ln in (d / "frames.txt").read_text(encoding="utf-8").splitlines():
            i, t, col, raw = ln.split(" ")
            self.rows.append((int(i), t, Path(col), Path(raw)))
        self.checks = sorted(p.name for p in (d / "check").glob("*.jpg")) if (d / "check").exists() else []
        self.n = s1.turn_of(tid)[1]["n_calc"]
        self.W, self.H = Image.open(self.rows[0][2]).size

    def img(self, i: int, kind: str) -> Image.Image:
        r = self.rows[max(0, min(i, len(self.rows) - 1))]
        return Image.open(r[2] if kind == "color" else r[3]).convert("RGB")


def strip_images(T: "Turn", args: dict) -> list:
    """같은 영역을 start ~ end 에서 step 장마다 잘라 위아래로 쌓은 그림들(한 그림 STRIP_ROWS 줄)."""
    from PIL import ImageDraw, ImageFont
    F = len(T.rows)
    st, en, sp = int(args["start"]), int(args["end"]), max(1, int(args.get("step") or 1))
    st, en = max(0, min(st, F - 1)), max(0, min(en, F - 1))
    idx = list(range(min(st, en), max(st, en) + 1, sp))[:STRIP_MAX]
    x0, x1 = sorted([max(0, int(args["x0"])), min(T.W, int(args["x1"]))])
    y0 = max(0, int(args.get("y0") or 0))
    y1 = min(T.H, int(args.get("y1") or T.H))
    x1, y1 = max(x1, x0 + 8), max(y1, y0 + 8)
    sc = min(3.0, 1500 / (x1 - x0))
    cw, ch = int((x1 - x0) * sc), int((y1 - y0) * sc)
    try:
        font = ImageFont.truetype("malgunbd.ttf", 22)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    out = []
    for g in range(0, len(idx), STRIP_ROWS):
        part = idx[g:g + STRIP_ROWS]
        sheet = Image.new("RGB", (cw + 70, len(part) * (ch + 4)), (255, 255, 255))
        dr = ImageDraw.Draw(sheet)
        for r, i in enumerate(part):
            crop = T.img(i, args.get("kind", "raw")).crop((x0, y0, x1, y1)).resize((cw, ch), Image.LANCZOS)
            sheet.paste(crop, (70, r * (ch + 4)))
            dr.text((4, r * (ch + 4) + ch // 2 - 11), f"{i:03d}", fill=(0, 0, 0), font=font)
        out.append((f"strip {args.get('kind', 'raw')} 프레임 {part[0]:03d}~{part[-1]:03d}(간격 {sp}) x {x0}~{x1} y {y0}~{y1}", jpg(sheet)))
    return out


def jpg(im: Image.Image, q: int = 88) -> bytes:
    b = io.BytesIO()
    im.save(b, "JPEG", quality=q)
    return b.getvalue()


def run_one(tid: str, a) -> dict:
    import gemframes as gf
    from google.genai import types
    c = gf.client()
    motion2 = getattr(a, "variant", "base") == "motion2"
    if motion2:   # 11-19 밤 "m2b 모델만 flash로 바꿔서": claudeagent motion2 와 같은 지시문 · 사건 목록 · 떠 있는 숫자 표시 그림
        import claudeagent as ca
        T = ca.FloatTurn(tid)
    else:
        T = Turn(tid)
    F = len(T.rows)
    base_prompt = ca.PROMPT_MOTION2 if motion2 else PROMPT
    sys_prompt = base_prompt.format(n=T.n, F=F, last=F - 1, mv=MAX_VIEW, W=T.W, H=T.H, sr=STRIP_ROWS, sm=STRIP_MAX)
    if not a.strip:   # g1 · g2 와 같은 글(strip 줄 없이)
        sys_prompt = "\n".join(ln for ln in sys_prompt.split("\n") if not ln.startswith("- `strip("))
    kw = {"thinking_config": types.ThinkingConfig(thinking_level=a.think)} if a.think else {}
    cfg = types.GenerateContentConfig(system_instruction=sys_prompt, tools=decls(types, a.strip), **kw)
    hi = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")

    def ipart(data: bytes):
        p = types.Part.from_bytes(data=data, mime_type="image/jpeg")
        p.media_resolution = hi
        return p

    lst = "\n".join(f"{i:03d} {t}" for i, t, _, _ in T.rows)
    if motion2:
        lst += f"\n\n칸 틀 사건 목록(코드가 패 검출로 만든 것):\n{ca.events_text(T)}"   # claudeagent.first_content 와 같은 글
    first = [f"차례를 시작할 때 줄은 {T.n}장. 프레임 {F}장(번호 · 시각):\n{lst}\n\n확인 그림 이름: {', '.join(T.checks) or '없음'}\n\n첫 프레임(color):", ipart(jpg(T.img(0, 'color'))),
             f"끝 프레임 {F - 1}(color):", ipart(jpg(T.img(F - 1, 'color'))), "도구로 필요한 프레임을 보며 읽고, 다 보면 answer 를 불러라."]
    contents = [types.Content(role="user", parts=[types.Part(text=x) if isinstance(x, str) else x for x in first])]
    model = a.gmodel
    p_lo, p_hi = PRICE[model]
    log, usage, ans, nudges = [], {"in": 0, "cached": 0, "out": 0, "think": 0, "calls": 0, "max_prompt": 0}, None, 0
    usd = 0.0
    t0 = time.perf_counter()
    last_cfg = types.GenerateContentConfig(system_instruction=sys_prompt, tools=decls(types, a.strip), **kw,
                                           tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=["answer"])))
    for step in range(a.max_steps):
        final = step == a.max_steps - 1
        if final:   # 단계를 다 쓰면 지금까지 본 것으로 답하게(답 없음 방지)
            contents.append(types.Content(role="user", parts=[types.Part(text="볼 수 있는 단계를 다 썼다. 지금까지 본 것으로 answer 를 불러라(확신이 낮으면 unsure 를 true 로).")]))
        for attempt in range(3):
            try:
                r = c.models.generate_content(model=model, contents=contents, config=last_cfg if final else cfg)
                break
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(8 * (attempt + 1))
        else:
            return {"id": tid, "error": err, "log": log, "usage": usage, "steps": step}
        um = r.usage_metadata
        usage["in"] += um.prompt_token_count or 0
        usage["cached"] += getattr(um, "cached_content_token_count", 0) or 0
        usage["out"] += um.candidates_token_count or 0
        usage["think"] += getattr(um, "thoughts_token_count", 0) or 0
        usage["calls"] += 1
        pin, cin = um.prompt_token_count or 0, getattr(um, "cached_content_token_count", 0) or 0
        usage["max_prompt"] = max(usage["max_prompt"], pin)
        pi, po = p_hi if pin > 200_000 else p_lo
        usd += ((pin - cin) * pi + cin * pi / 4 + ((um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)) * po) * 1e-6
        cand = r.candidates[0].content
        contents.append(cand)
        fcs = [p.function_call for p in (cand.parts or []) if p.function_call]
        if not fcs:
            nudges += 1
            log.append({"step": step, "text": (r.text or "")[:300]})
            if nudges > 2:
                break
            contents.append(types.Content(role="user", parts=[types.Part(text="도구로 더 보거나, 다 봤으면 answer 를 불러라.")]))
            continue
        resp = []
        for fc in fcs:
            args = dict(fc.args or {})
            log.append({"step": step, "tool": fc.name, "args": args})
            imgs = []
            if fc.name == "answer":
                ans = args
                resp.append(types.Part(function_response=types.FunctionResponse(name="answer", id=fc.id, response={"result": "받음"})))
                continue
            try:
                if fc.name == "view":
                    fr = [int(x) for x in (args.get("frames") or [])][:MAX_VIEW]
                    imgs = [(f"프레임 {i:03d} {T.rows[min(i, F - 1)][1]} {args.get('kind')}", jpg(T.img(i, args.get("kind", "color")))) for i in fr]
                elif fc.name == "zoom":
                    im = T.img(int(args["frame"]), args.get("kind", "raw"))
                    x0, x1 = sorted([max(0, int(args["x0"])), min(im.width, int(args["x1"]))])
                    y0 = max(0, int(args.get("y0") or 0))
                    y1 = min(im.height, int(args.get("y1") or im.height))
                    cr = im.crop((x0, y0, max(x1, x0 + 8), max(y1, y0 + 8)))
                    sc = min(3.0, 1600 / max(1, cr.width))
                    cr = cr.resize((int(cr.width * sc), int(cr.height * sc)), Image.LANCZOS)
                    imgs = [(f"프레임 {int(args['frame']):03d} 확대 x {x0}~{x1} y {y0}~{y1}", jpg(cr))]
                elif fc.name == "strip":
                    imgs = strip_images(T, args)
                elif fc.name == "check":
                    p = SRC / tid / "check" / str(args.get("name"))
                    imgs = [(p.name, p.read_bytes())] if p.exists() else []
                    if not imgs:
                        raise FileNotFoundError(f"확인 그림 없음: {args.get('name')}")
            except Exception as e:  # noqa: BLE001
                resp.append(types.Part(function_response=types.FunctionResponse(name=fc.name, id=fc.id, response={"error": str(e)[:200]})))
                continue
            parts = [types.FunctionResponsePart(inline_data=types.FunctionResponseBlob(mime_type="image/jpeg", data=b)) for _, b in imgs]
            resp.append(types.Part(function_response=types.FunctionResponse(name=fc.name, id=fc.id, response={"result": " | ".join(t for t, _ in imgs)}, parts=parts)))
        contents.append(types.Content(role="user", parts=resp))
        if ans is not None:
            break
    res = {"id": tid, "model": model, "think_level": a.think, "steps": usage["calls"], "s": round(time.perf_counter() - t0, 1), "usage": usage, "log": log,
           "variant": getattr(a, "variant", "base"), "strip": a.strip}
    if motion2:
        res["events"] = ca.EVENTS.get(tid)
    if ans:
        n = T.n
        kj = sv.from_order([str(x) for x in ans.get("end_order") or []], n)
        res.update({"answer": ans, "kind": ans.get("kind"), "unsure": ans.get("unsure"),
                    "k": (kj[0] if kj and ans.get("kind") == "hand" else ans.get("k")), "j": (kj[1] if kj and ans.get("kind") == "hand" else ans.get("j")),
                    "k_model": ans.get("k"), "j_model": ans.get("j"), "order_ok": kj is not None})
    else:
        res.update({"kind": None, "k": None, "j": None, "error": "answer 없음"})
    # 값: 부를 때마다 PRICE(프롬프트 20만 넘으면 위 칸) — Flash 는 앞 셈(입력 0.75 · 캐시 1/4 · 출력 3.75)과 같음
    res["usd"] = round(usd, 3)
    return res


def cmd_run(a):
    od = OUT / a.tag
    od.mkdir(parents=True, exist_ok=True)
    ids = [t for t in sv.ids_of(a.ids) if a.force or not (od / f"{t}.json").exists()]
    if getattr(a, "variant", "base") == "motion2":   # 사건 목록은 스레드 전에(claudeagent.events_text 주의 — redirect_stdout)
        import claudeagent as ca
        for t in ids:
            ca.EVENTS[t] = ca.events_text(Turn(t))
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda t: run_one(t, a), ids):
            r["at"] = hc.hms(int(time.time() * 1000), date=True)
            hc.jsave(od / f"{r['id']}.json", r)
            print(r["id"], r.get("kind"), r.get("k"), r.get("j"), f"단계 {r.get('steps')}", f"{r.get('s')}초", f"약 {r.get('usd')}달러", r.get("error", ""), flush=True)


def cmd_score(a):
    truth = s1.truth_all()
    T = quiet = noans = 0
    usd = 0.0
    ids = sv.ids_of(a.ids)
    for tid in ids:
        f = OUT / a.tag / f"{tid}.json"
        if not f.exists():
            print(tid, "없음")
            continue
        r = hc.jload(f)
        ok = m.right(m.norm(r), truth[tid])
        T += ok
        if r.get("kind") is None:
            noans += 1
        else:
            quiet += (not ok) and not r.get("unsure")
        usd += r.get("usd") or 0
        tools = {}
        for x in r.get("log", []):
            if x.get("tool"):
                tools[x["tool"]] = tools.get(x["tool"], 0) + 1
        print(f"{tid:9s} 정답 {truth[tid].get('kind')} {truth[tid].get('k_id')}·{truth[tid].get('j_closed')} | Gemini {r.get('kind')} {r.get('k')}·{r.get('j')}{'?' if r.get('unsure') else ''} {'✓' if ok else '✗'} "
              f"| 단계 {r.get('steps')} · 도구 {tools} · {r.get('s')}초 · 약 {r.get('usd')}달러 {r.get('error', '')}")
    print(f"맞음 {T}/{len(ids)} · 답 없음(단계 다 씀) {noans} · 조용한 틀림 {quiet} · 합 약 {usd:.2f}달러")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "score"):
        q = sp.add_parser(name)
        q.add_argument("--ids", default="hard8")
        q.add_argument("--tag", default="g1")
        if name == "run":
            q.add_argument("--max-steps", type=int, default=30)
            q.add_argument("--think", default=None)
            q.add_argument("--workers", type=int, default=4)
            q.add_argument("--force", action="store_true")
            q.add_argument("--strip", action="store_true", help="strip 도구를 더함(g3)")
            q.add_argument("--gmodel", default=MODEL, choices=sorted(PRICE), help="p1 = gemini-3.1-pro-preview(추가 42)")
            q.add_argument("--variant", default="base", choices=["base", "motion2"], help="motion2 = claudeagent m2b 와 같은 지시문 · 사건 목록 · 떠 있는 숫자 그림(11-19 밤)")
    a = ap.parse_args()
    {"run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
