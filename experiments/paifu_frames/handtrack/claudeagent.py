"""geminiagent.py 의 Claude 판 — 같은 지시문 · 재료 · 도구 5개로 손패 한 차례를 Claude API(Opus 5.5)가 읽게 하기(2026-11-19).

Gemini g3(표 12-62) · Pro(표 12-65)와 모델만 바꿔 견주려는 것: 지시문 = geminiagent.PROMPT(strip 줄 포함 g3 판), 재료 = geminiagent.Turn
(_work/opusread_1118/<id>/frames.txt · check/), 도구 = view · zoom · check · strip · answer(그림 만들기는 geminiagent 것을 그대로 씀),
첫 메시지 · 결과 꼴 · k·j 계산(sam2verify.from_order)도 같다.
refusal 에 fallbacks(다른 모델로 다시 돌리기)는 넣지 않는다 — 한 모델의 읽기를 재는 실험이라 다른 모델이 답하면 숫자가 섞인다.

  python -X utf8 claudeagent.py dry --ids r16_d13                    # API 를 부르지 않는 점검(키 없이 돎)
  python -X utf8 claudeagent.py run --ids r16_d13 [--tag c1] [--model claude-opus-5-5] [--effort high] [--max-steps 60] [--max-usd 5] [--workers 1] [--force] [--src opusread_1118]
  python -X utf8 claudeagent.py score --ids hard8 [--tag c1]
결과 _work/claudeagent_1119/<tag>/<id>.json — 정답 · 다른 판독 답은 안 넣음.

API 쪽은 claude-api 스킬 문서(python/claude-api/README.md · tool-use.md · streaming.md, shared/prompt-caching.md · tool-use-concepts.md ·
model-migration.md "Migrating to Claude Opus 5.5")와 설치된 anthropic 1.15.0 의 타입 정의대로 썼다:
- 수동 루프: 응답 content 전체(thinking 포함)를 assistant 로 그대로 붙이고, 한 응답의 tool_result 는 한 user 메시지에, 오류는 is_error.
- 캐싱: system 마지막 블록에 cache_control + 최상위 cache_control(자동 — 대화 끝 블록으로 따라감). 지시문 · 도구 · 모델 · effort 는 차례 안에서 안 바꿈.
- Opus 5.5: thinking 은 안 줌(= adaptive), 깊이는 output_config.effort, tool_choice 는 auto(기본), temperature · budget_tokens 없음.
- 그림: 요청에 그림이 20장을 넘으면 장마다 3000 화소 넘는 변이 거절됨(vision 문서 "many-image requests") → 긴 변이 LONG_EDGE(2576 —
  Opus 5.5 가 어차피 줄이는 크기)를 넘는 그림만 보내기 전에 줄임. 요청당 그림 600장 · 128MB 한도 앞에서 마지막 단계로 넘어감.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geminiagent as ga  # noqa: E402
import htcommon as hc  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402
import sam2verify as sv  # noqa: E402

OUT = hc.WORK / "claudeagent_1119"
SRC = ga.SRC
MODEL = "claude-opus-5-5"
# 100만 토큰당 달러: (입력, 출력 — 생각 토큰 포함, 캐시 읽기, 캐시 쓰기 5분) — model-migration.md "Pricing" 과 같음
PRICE = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
         "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5)}
MAX_VIEW = ga.MAX_VIEW
LONG_EDGE = 2576            # Opus 5.5 · Sonnet 5.5 의 최대 원래 해상도(긴 변) — 넘는 그림은 API 가 줄임
MAX_IMAGES = 560            # 요청당 600장 한도 앞에서 멈춤
MAX_BYTES = 120 * 2 ** 20   # 요청 128MB 한도 앞에서 멈춤(base64 그림 바이트 합으로 어림)
ENV = "C:/Users/jjh7757/Downloads/부트캠프/.env"
FINAL_TEXT = "볼 수 있는 단계를 다 썼다. 지금까지 본 것으로 answer 를 불러라(확신이 낮으면 unsure 를 true 로)."
NUDGE_TEXT = "도구로 더 보거나, 다 봤으면 answer 를 불러라."
FIRST_TAIL = "도구로 필요한 프레임을 보며 읽고, 다 보면 answer 를 불러라."
FINAL_EXTRA = 2             # 마지막 단계 글을 넣은 뒤 answer 를 기다려 줄 호출 수(Gemini 는 tool_config ANY 로 강제했지만 Opus 5.5 는 forced tool_choice 가 400)


def tool_defs() -> list:
    """geminiagent.decls(strip=True) 와 같은 도구 · 같은 인자 · 같은 순서(strip, view, zoom, check, answer)."""
    kind = {"type": "string", "enum": ["color", "raw"]}
    it = {"type": "integer"}
    nint = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    return [
        {"name": "strip", "description": "같은 영역을 여러 프레임에서 잘라 시간순으로 쌓아 본다",
         "input_schema": {"type": "object", "properties": {"start": it, "end": it, "step": it, "x0": it, "x1": it, "y0": it, "y1": it, "kind": kind},
                          "required": ["start", "end", "step", "x0", "x1", "kind"], "additionalProperties": False}},
        {"name": "view", "description": "프레임 여러 장을 본다",
         "input_schema": {"type": "object", "properties": {"frames": {"type": "array", "items": it}, "kind": kind},
                          "required": ["frames", "kind"], "additionalProperties": False}},
        {"name": "zoom", "description": "한 프레임의 일부를 잘라 3배로 키운다",
         "input_schema": {"type": "object", "properties": {"frame": it, "x0": it, "x1": it, "y0": it, "y1": it, "kind": kind},
                          "required": ["frame", "x0", "x1", "kind"], "additionalProperties": False}},
        {"name": "check", "description": "확인 그림 한 장을 본다",
         "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}},
        {"name": "answer", "description": "답을 낸다(부르면 끝)", "strict": True,
         "input_schema": {"type": "object", "properties": {
             "kind": {"type": "string", "enum": ["hand", "tsumogiri"]}, "k": nint, "j": nint,
             "end_order": {"type": "array", "items": {"type": "string"}}, "unsure": {"type": "boolean"},
             "tracking_errors": {"type": "string"}, "why": {"type": "string"}},
             "required": ["kind", "k", "j", "end_order", "unsure", "tracking_errors", "why"], "additionalProperties": False}},
    ]


def system_text(T: "ga.Turn") -> str:
    """geminiagent.run_one 의 sys_prompt 와 같은 글(strip 줄 포함 = g3)."""
    F = len(T.rows)
    return ga.PROMPT.format(n=T.n, F=F, last=F - 1, mv=MAX_VIEW, W=T.W, H=T.H, sr=ga.STRIP_ROWS, sm=ga.STRIP_MAX)


def fit(b: bytes) -> bytes:
    """긴 변이 LONG_EDGE 를 넘는 jpeg 만 줄임(나머지는 바이트 그대로)."""
    im = Image.open(io.BytesIO(b))
    if max(im.size) <= LONG_EDGE:
        return b
    sc = LONG_EDGE / max(im.size)
    return ga.jpg(im.convert("RGB").resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS))


def img_block(b: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(fit(b)).decode("ascii")}}


def zoom_image(T: "ga.Turn", args: dict) -> tuple:
    """geminiagent.run_one 의 zoom 자르기와 같은 일(거기선 함수가 아니라 줄 안에 있어 같은 식을 옮김)."""
    im = T.img(int(args["frame"]), args.get("kind", "raw"))
    x0, x1 = sorted([max(0, int(args["x0"])), min(im.width, int(args["x1"]))])
    y0 = max(0, int(args.get("y0") or 0))
    y1 = min(im.height, int(args.get("y1") or im.height))
    cr = im.crop((x0, y0, max(x1, x0 + 8), max(y1, y0 + 8)))
    sc = min(3.0, 1600 / max(1, cr.width))
    cr = cr.resize((int(cr.width * sc), int(cr.height * sc)), Image.LANCZOS)
    return f"프레임 {int(args['frame']):03d} 확대 x {x0}~{x1} y {y0}~{y1}", ga.jpg(cr)


def run_tool(T: "ga.Turn", name: str, args: dict) -> list:
    """도구 하나 실행 → [(설명, jpeg 바이트)]. 실패하면 예외(부르는 쪽이 is_error 로)."""
    F = len(T.rows)
    if name == "view":
        fr = [int(x) for x in (args.get("frames") or [])][:MAX_VIEW]
        return [(f"프레임 {i:03d} {T.rows[max(0, min(i, F - 1))][1]} {args.get('kind')}", ga.jpg(T.img(i, args.get("kind", "color")))) for i in fr]
    if name == "zoom":
        return [zoom_image(T, args)]
    if name == "strip":
        return ga.strip_images(T, args)
    if name == "check":
        p = SRC / T.tid / "check" / str(args.get("name"))
        if not p.exists() or p.parent != SRC / T.tid / "check":
            raise FileNotFoundError(f"확인 그림 없음: {args.get('name')}")
        return [(p.name, p.read_bytes())]
    raise ValueError(f"모르는 도구: {name}")


def first_content(T: "ga.Turn") -> list:
    F = len(T.rows)
    lst = "\n".join(f"{i:03d} {t}" for i, t, _, _ in T.rows)
    return [{"type": "text", "text": f"차례를 시작할 때 줄은 {T.n}장. 프레임 {F}장(번호 · 시각):\n{lst}\n\n확인 그림 이름: {', '.join(T.checks) or '없음'}\n\n첫 프레임(color):"},
            img_block(ga.jpg(T.img(0, "color"))),
            {"type": "text", "text": f"끝 프레임 {F - 1}(color):"},
            img_block(ga.jpg(T.img(F - 1, "color"))),
            {"type": "text", "text": FIRST_TAIL}]


def request_kw(T: "ga.Turn", a) -> dict:
    """매 호출에 같은 앞부분: 모델 · system(캐시 지점) · 도구 · effort · 자동 캐싱. messages 는 따로."""
    kw = {"model": a.model, "max_tokens": a.max_tokens,
          "system": [{"type": "text", "text": system_text(T), "cache_control": {"type": "ephemeral"}}],
          "tools": tool_defs(), "output_config": {"effort": a.effort}, "cache_control": {"type": "ephemeral"}}
    if getattr(a, "show_thinking", False):
        kw["thinking"] = {"type": "adaptive", "display": "summarized"}
    return kw


def count_images(msgs: list) -> tuple:
    """대화 안 그림 장수 · base64 바이트 합(요청 한도 어림)."""
    n = size = 0

    def walk(blocks):
        nonlocal n, size
        if not isinstance(blocks, list):
            return
        for b in blocks:
            if isinstance(b, dict):
                if b.get("type") == "image":
                    n += 1
                    size += len(b["source"]["data"])
                elif b.get("type") == "tool_result":
                    walk(b.get("content"))
    for mm in msgs:
        walk(mm.get("content"))
    return n, size


def call(client, kw: dict, msgs: list):
    """스트리밍으로 부르고 최종 메시지. 429 · 5xx · 연결 오류만 바깥 3번(SDK 기본 재시도 2번은 그 안에서). 400 등은 바로 올림."""
    import anthropic
    last = None
    for attempt in range(3):
        try:
            with client.messages.stream(messages=msgs, **kw) as stream:
                return stream.get_final_message()
        except anthropic.APIConnectionError as e:
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code != 429 and e.status_code < 500:
                raise
            last = e
        time.sleep(10 * (attempt + 1))
    raise last


def run_one(tid: str, a, client) -> dict:
    T = ga.Turn(tid)
    kw = request_kw(T, a)
    msgs = [{"role": "user", "content": first_content(T)}]
    p_in, p_out, p_cr, p_cw = PRICE[a.model]
    log, ans, nudges, usd, final = [], None, 0, 0.0, False
    usage = {"in": 0, "cache_read": 0, "cache_write": 0, "out": 0, "calls": 0, "max_ctx": 0}
    res = {"id": tid, "model": a.model, "effort": a.effort, "src": a.src}
    t0 = time.perf_counter()
    step = -1
    while True:
        step += 1
        if step >= a.max_steps + FINAL_EXTRA:   # 마지막 단계 뒤에도 answer 를 안 부르면 끝(Claude 는 answer 를 강제할 수 없어 FINAL_EXTRA 번 더 줌)
            break
        n_img, n_bytes = count_images(msgs)
        why_final = ("단계" if step >= a.max_steps - 1 else "달러" if usd > a.max_usd else
                     "그림 장수" if n_img > MAX_IMAGES else "요청 크기" if n_bytes > MAX_BYTES else None)
        if why_final and not final:   # 마지막 단계: 지금까지 본 것으로 답하게(geminiagent 와 같은 글)
            final = True
            log.append({"step": step, "final": why_final})
            last = msgs[-1]
            if last["role"] == "user":   # tool_result 들 뒤에 글 블록으로(문서: 같은 user 메시지에 덧붙임)
                last["content"].append({"type": "text", "text": FINAL_TEXT})
            else:
                msgs.append({"role": "user", "content": [{"type": "text", "text": FINAL_TEXT}]})
        try:
            r = call(client, kw, msgs)
        except Exception as e:  # noqa: BLE001
            res.update({"error": f"{type(e).__name__}: {e}"[:400]})
            break
        u = r.usage
        ui, ucr, ucw, uo = u.input_tokens or 0, u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0, u.output_tokens or 0
        usage["in"] += ui
        usage["cache_read"] += ucr
        usage["cache_write"] += ucw
        usage["out"] += uo
        usage["calls"] += 1
        usage["max_ctx"] = max(usage["max_ctx"], ui + ucr + ucw)
        usd += (ui * p_in + uo * p_out + ucr * p_cr + ucw * p_cw) * 1e-6
        msgs.append({"role": "assistant", "content": r.content})   # thinking 포함 그대로
        uses = [b for b in r.content if b.type == "tool_use"]
        texts = " ".join(b.text for b in r.content if b.type == "text")
        thinks = " ".join(getattr(b, "thinking", "") or "" for b in r.content if b.type == "thinking")
        ent = {"step": step, "stop": r.stop_reason, "in": ui, "cache_read": ucr, "cache_write": ucw, "out": uo}
        if texts:
            ent["text"] = texts[:300]
        if thinks:
            ent["thinking"] = thinks[:600]
        log.append(ent)
        print(f"  {tid} 단계 {step:02d} {','.join(b.name for b in uses) or r.stop_reason} 누적 {usd:.3f}달러 "
              f"(입력 {ui} · 캐시 읽기 {ucr} · 쓰기 {ucw} · 출력 {uo} · 그림 {n_img}장 {n_bytes / 2 ** 20:.1f}MB)", flush=True)
        if r.stop_reason == "refusal":
            sd = r.stop_details
            res.update({"error": "refusal", "stop_details": {"category": getattr(sd, "category", None), "explanation": getattr(sd, "explanation", None)} if sd else None})
            break
        if r.stop_reason == "max_tokens":   # 잘린 도구 입력은 돌리지 않음 — 단순하게 오류로
            res.update({"error": f"max_tokens({a.max_tokens})"})
            break
        if not uses:
            if final:   # 마지막 단계인데 글로만 답함 → 같은 글로 한 번 더(FINAL_EXTRA 안에서)
                msgs.append({"role": "user", "content": [{"type": "text", "text": FINAL_TEXT}]})
                continue
            nudges += 1
            if nudges > 2:
                break
            msgs.append({"role": "user", "content": [{"type": "text", "text": NUDGE_TEXT}]})
            continue
        results = []
        for b in uses:
            args = dict(b.input or {})
            log.append({"step": step, "tool": b.name, "args": args})
            if b.name == "answer":
                ans = args
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": "받음"})
                continue
            if final:   # 마지막 단계 뒤에는 더 보여 주지 않음
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": "볼 수 있는 단계를 다 썼다 — 이제 answer 만 부를 수 있다.", "is_error": True})
                continue
            try:
                imgs = run_tool(T, b.name, args)
            except Exception as e:  # noqa: BLE001
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(e)[:200], "is_error": True})
                continue
            results.append({"type": "tool_result", "tool_use_id": b.id,
                            "content": [{"type": "text", "text": " | ".join(t for t, _ in imgs)}] + [img_block(x) for _, x in imgs]})
        msgs.append({"role": "user", "content": results})
        if ans is not None:
            break
    res.update({"steps": usage["calls"], "s": round(time.perf_counter() - t0, 1), "usage": usage, "log": log})
    if ans:
        n = T.n
        kj = sv.from_order([str(x) for x in ans.get("end_order") or []], n)
        res.update({"answer": ans, "kind": ans.get("kind"), "unsure": ans.get("unsure"),
                    "k": (kj[0] if kj and ans.get("kind") == "hand" else ans.get("k")), "j": (kj[1] if kj and ans.get("kind") == "hand" else ans.get("j")),
                    "k_model": ans.get("k"), "j_model": ans.get("j"), "order_ok": kj is not None})
    else:
        res.update({"kind": None, "k": None, "j": None})
        res.setdefault("error", "answer 없음")
    res["usd"] = round(usd, 3)
    return res


def make_client():
    from dotenv import load_dotenv
    load_dotenv(ENV)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic
    return anthropic.Anthropic()


def cmd_run(a):
    client = make_client()
    if client is None:
        print("ANTHROPIC_API_KEY 가 .env 에 없음")
        return
    od = OUT / a.tag
    od.mkdir(parents=True, exist_ok=True)
    ids = [t for t in sv.ids_of(a.ids) if a.force or not (od / f"{t}.json").exists()]
    print(f"{len(ids)}차례 · {a.model} · effort {a.effort} · 단계 {a.max_steps} · 차례당 {a.max_usd}달러 · 나란히 {a.workers}", flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda t: run_one(t, a, client), ids):
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
        print(f"{tid:9s} 정답 {truth[tid].get('kind')} {truth[tid].get('k_id')}·{truth[tid].get('j_closed')} | Claude {r.get('kind')} {r.get('k')}·{r.get('j')}{'?' if r.get('unsure') else ''} {'✓' if ok else '✗'} "
              f"| 단계 {r.get('steps')} · 도구 {tools} · {r.get('s')}초 · 약 {r.get('usd')}달러 {r.get('error', '')}")
    print(f"맞음 {T}/{len(ids)} · 답 없음(단계 다 씀) {noans} · 조용한 틀림 {quiet} · 합 약 {usd:.2f}달러")


def cmd_dry(a):
    """API 를 부르지 않고 첫 요청 · 도구 5개를 실제 Turn 으로 만들어 봄. 그림은 claudeagent_1119/dry/ 에."""
    od = OUT / "dry"
    od.mkdir(parents=True, exist_ok=True)
    for tid in sv.ids_of(a.ids):
        T = ga.Turn(tid)
        F = len(T.rows)
        kw = request_kw(T, a)
        msgs = [{"role": "user", "content": first_content(T)}]
        n_img, n_bytes = count_images(msgs)
        body = json.dumps({**kw, "messages": msgs}, ensure_ascii=False)
        print(f"[{tid}] 줄 {T.n}장 · 프레임 {F}장 · 그림 {T.W}×{T.H} · 확인 그림 {len(T.checks)}장")
        print(f"  model {kw['model']} · effort {kw['output_config']['effort']} · max_tokens {kw['max_tokens']} · thinking {kw.get('thinking', '안 줌(adaptive)')} · 최상위 cache_control {kw['cache_control']}")
        print(f"  system {len(kw['system'][0]['text'])}자 (strip 줄 {'있음' if '- `strip(' in kw['system'][0]['text'] else '없음'}) · 도구 {[t['name'] for t in kw['tools']]} · strict {[t['name'] for t in kw['tools'] if t.get('strict')]}")
        print(f"  첫 메시지 블록 {[b['type'] for b in msgs[0]['content']]} · 그림 {n_img}장 base64 {n_bytes} 바이트 · 요청 본문 {len(body.encode('utf-8'))} 바이트")
        for i, b in enumerate(x for x in msgs[0]["content"] if x["type"] == "image"):
            raw = base64.standard_b64decode(b["source"]["data"])
            (od / f"{tid}_first{i}.jpg").write_bytes(raw)
        tests = [("view", {"frames": [0, 50], "kind": "color"}),
                 ("zoom", {"frame": 0, "x0": 0, "x1": T.W // 2, "kind": "raw"}),
                 ("strip", {"start": 40, "end": 60, "step": 1, "x0": 0, "x1": T.W, "kind": "raw"}),
                 ("check", {"name": T.checks[0] if T.checks else "없음.jpg"}),
                 ("check", {"name": "없는그림.jpg"})]
        for name, args in tests:
            try:
                imgs = run_tool(T, name, args)
            except Exception as e:  # noqa: BLE001
                tr = {"type": "tool_result", "tool_use_id": "dry", "content": str(e)[:200], "is_error": True}
                print(f"  {name} {args} → is_error tool_result: {tr['content']}")
                continue
            blocks = [img_block(x) for _, x in imgs]
            sizes = []
            for k, ((desc, raw), blk) in enumerate(zip(imgs, blocks)):
                sent = base64.standard_b64decode(blk["source"]["data"])
                w0, h0 = Image.open(io.BytesIO(raw)).size
                w1, h1 = Image.open(io.BytesIO(sent)).size
                sizes.append(f"{w0}×{h0}" + (f"→{w1}×{h1}" if (w0, h0) != (w1, h1) else "") + f" {len(sent) // 1024}KB")
                (od / f"{tid}_{name}_{k}.jpg").write_bytes(sent)
            print(f"  {name} {args} → 그림 {len(imgs)}장 [{', '.join(sizes)}] · 글 '{' | '.join(t for t, _ in imgs)[:120]}'")
    print(f"그림 저장: {od}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "score", "dry"):
        q = sp.add_parser(name)
        q.add_argument("--ids", default="hard8" if name != "dry" else "r16_d13")
        q.add_argument("--tag", default="c1")
        if name in ("run", "dry"):
            q.add_argument("--model", default=MODEL, choices=sorted(PRICE))
            q.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
            q.add_argument("--max-tokens", type=int, default=32000)
            q.add_argument("--show-thinking", action="store_true", help="thinking display=summarized — 생각 요약을 log 에 남김(값·행동 영향은 문서로 확인 못 함, 기본 끔)")
            q.add_argument("--src", default="opusread_1118", help="읽을 재료 폴더(_work 아래 이름) — frames.txt · check/ (11-19: r19_d04 는 opusread_1119r)")
        if name == "run":
            q.add_argument("--max-steps", type=int, default=60)
            q.add_argument("--max-usd", type=float, default=5.0)
            q.add_argument("--workers", type=int, default=1)
            q.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if hasattr(a, "src"):   # 재료 폴더 바꾸기 — ga.Turn(frames.txt · check 이름)과 이 파일의 check 도구가 같은 폴더를 보게
        global SRC
        SRC = ga.SRC = hc.WORK / a.src
        if not SRC.is_dir():
            raise SystemExit(f"재료 폴더 없음: {SRC}")
    {"run": cmd_run, "score": cmd_score, "dry": cmd_dry}[a.cmd](a)


if __name__ == "__main__":
    main()
