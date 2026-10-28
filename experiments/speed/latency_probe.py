"""자리 판독 지연이 튀는 이유 쪼개 보기(2026-10-26 저녁, 사용자 요청).

같은 자리 판독 요청(지금 서버와 같은 입력·프롬프트)을 **스트리밍**으로 보내
  ttft  = 보낸 뒤 첫 답 글자가 오기까지(대기 + 입력 처리 + 생각)
  gen   = 첫 글자 뒤 끝까지(답 출력)
로 나누고, 같은 시간대에 동시 요청 수를 바꿔(1개 / 3개 / 6개) 번갈아 보낸다. 실제 시각을 남겨 느린 요청이 같은 순간에 몰리는지 본다.
SDK 재시도 로그도 켠다(재시도 옵션을 안 주면 재시도하지 않는 것이 SDK 기본).

  python experiments/speed/latency_probe.py [--loops 10]     결과 results/latency_probe.json(덧붙임)
  python experiments/speed/latency_probe.py --show
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import bench as b

OUT = b.OUT / "latency_probe.json"
logging.basicConfig(level=logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.INFO)
logging.getLogger("google_genai._api_client").setLevel(logging.INFO)

PHOTOS = [(s, p) for s in "BCD" for p in b.PHOTOS[s]]


def build(scene: str, photo: str):
    c = {**b.BASE, **b.CONDS["v3a_norule"]}
    path = b.G / scene / photo / b.TRUTH[scene][0]
    data = b.load(path, c["max_side"], c["crop"])
    prompt = b.SEAT_PROMPT_V3A
    rule = prompt[prompt.index("장수: 앞면 손패라면"):]
    prompt = prompt.replace(rule[:rule.index("\n\n") + 2], "")
    extra = [b.image_part(z, c["zoom_res"]) for z in b.zoom_strips(path, c["zoom"], c.get("width", 0.4))]
    prompt += b.ZOOM_NOTE.format(n=c["zoom"])
    extra.append(b.image_part(b.ref_sheet_set2(), None))
    prompt += b.REF_NOTE
    return [b.image_part(data, c["res"]), *extra, prompt], b.SEAT_SCHEMA_V3A, c


INPUTS = {}
_clients = {}


def client():
    """스레드마다 하나, 요청 시간 제한 90초(없으면 멈춘 스트림을 끝없이 기다린다 — 2026-10-26 첫 시도가 15분 멈춤)."""
    import os
    import threading

    from google import genai
    from google.genai import types

    k = threading.get_ident()
    if k not in _clients:
        _clients[k] = genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=types.HttpOptions(timeout=90_000))
    return _clients[k]


def one(scene: str, photo: str, mode: str, group: int, nonce: str | None = None) -> dict:
    from google.genai import types

    contents, schema, c = INPUTS[(scene, photo)]
    if nonce:  # 맨 앞에 요청 번호를 붙여 똑같은 요청이 아니게(자동 캐시의 앞부분이 달라짐)
        contents = [f"요청 번호 {nonce}", *contents]
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema,
                                      thinking_config=b.thinking_config(c["thinking"]))
    t_wall = time.time()
    t0 = time.perf_counter()
    first = None
    text, um, err = "", None, None
    try:
        for ch in client().models.generate_content_stream(model=c["model"], contents=contents, config=cfg):
            if ch.text and first is None:
                first = time.perf_counter() - t0
            text += ch.text or ""
            um = ch.usage_metadata or um
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"[:200]
    total = time.perf_counter() - t0
    row = {"mode": mode, "group": group, "scene": scene, "photo": photo, "t_wall": round(t_wall, 2),
           "total": round(total, 2), "ttft": round(first, 2) if first is not None else None,
           "think": getattr(um, "thoughts_token_count", 0) or 0 if um else None,
           "out": getattr(um, "candidates_token_count", 0) or 0 if um else None,
           "cached": getattr(um, "cached_content_token_count", 0) or 0 if um else None, "error": err}
    try:
        row.update(b.judge(scene, json.loads(text)))
    except Exception:  # noqa: BLE001
        pass
    return row


def burst(mode: str, n: int, group: int, photo=None) -> list[dict]:
    picks = [photo or random.choice(PHOTOS)] * n if mode != "mixed6" else random.sample(PHOTOS, 2) * 3
    nonces = [f"{group}-{i}-{random.randrange(10**6)}" if mode.startswith("nonce3") else None for i in range(n)]
    with ThreadPoolExecutor(n) as ex:
        rows = list(ex.map(lambda a: one(a[0][0], a[0][1], mode, group, a[1]), zip(picks, nonces)))
    print(f"[{mode:6s}] " + " ".join(f"{r['total']:.0f}({r['ttft'] or 0:.0f}|{r['think']}|c{r['cached']})" for r in rows),
          flush=True)
    return rows


def show(rows: list[dict]) -> None:
    ok = [r for r in rows if not r["error"] and r["ttft"] is not None]
    print(f"\n요청 {len(rows)}개, 오류 {sum(1 for r in rows if r['error'])}")
    print(f"{'동시':8s} {'수':>4s} {'전체 중앙/p90/최대':>20s} {'첫 글자 중앙/p90':>18s} {'출력 중앙':>8s} {'생각>0':>7s} {'생각0인데 15초+':>14s}")
    for mode in ("single", "triple", "mixed6", "same3", "nonce3", "same3p", "nonce3p"):
        rs = [r for r in ok if r["mode"] == mode]
        if not rs:
            continue
        t = sorted(r["total"] for r in rs)
        f = sorted(r["ttft"] for r in rs)
        g = [r["total"] - r["ttft"] for r in rs]
        print(f"{mode:8s} {len(rs):4d} {statistics.median(t):6.1f} / {t[int(.9 * len(t))]:5.1f} / {t[-1]:5.1f}   "
              f"{statistics.median(f):6.1f} / {f[int(.9 * len(f))]:5.1f}   {statistics.median(g):6.1f}   "
              f"{sum(r['think'] > 0 for r in rs):5d}   {sum(r['think'] == 0 and r['total'] > 15 for r in rs):6d}"
              f"   캐시 쓴 요청 {sum((r.get('cached') or 0) > 0 for r in rs)}")
    # 생각 0 인데 느린 요청: 대기(ttft)인가 출력(gen)인가, 같은 순간에 몰렸나
    slow0 = sorted([r for r in ok if r["think"] == 0 and r["total"] > 12], key=lambda r: r["t_wall"])
    print(f"\n생각 0 인데 12초 넘은 요청 {len(slow0)}개 (시각 순):")
    t_start = min(r["t_wall"] for r in ok)
    for r in slow0:
        same = [x for x in ok if x["group"] == r["group"] and x is not r]
        print(f"  +{r['t_wall'] - t_start:6.0f}s {r['mode']:6s} 전체 {r['total']:5.1f} 첫글자 {r['ttft']:5.1f} 출력 {r['total'] - r['ttft']:4.1f}"
              f"  같은 묶음 다른 요청: {[round(x['total']) for x in same]}")
    th = [r for r in ok if r["think"] > 0]
    if th:
        print(f"\n생각한 요청 {len(th)}개: 첫 글자까지 / 생각 토큰 → 토큰당 "
              f"{statistics.median((r['ttft'] - 4) / r['think'] * 1000 for r in th):.1f}ms(기본 4초 빼고)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loops", type=int, default=10)
    ap.add_argument("--modes", default="single,triple,mixed6", help="번갈아 보낼 묶음(same3·nonce3 = 같은 요청 3개 / 앞에 번호 붙인 3개)")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--paired", type=int, default=0,
                    help="사진을 맞춘 쌍: 사진 6장을 이만큼 돌며 같은 사진으로 same3p·nonce3p 를 바로 이어(순서 무작위) 보낸다")
    a = ap.parse_args()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    if not a.show:
        for s, p in PHOTOS:
            INPUTS[(s, p)] = build(s, p)
        group = max([r["group"] for r in old], default=0)
        new = []
        for _ in range(a.paired):
            for photo in random.sample(PHOTOS, len(PHOTOS)):
                for mode in random.sample(["same3p", "nonce3p"], 2):
                    group += 1
                    new += burst(mode, 3, group, photo)
                    OUT.write_text(json.dumps(old + new, ensure_ascii=False, indent=1), encoding="utf-8")
        for _ in range(a.loops if not a.paired else 0):
            order = a.modes.split(",")
            random.shuffle(order)
            for mode in order:
                group += 1
                new += burst(mode, {"single": 1, "triple": 3, "mixed6": 6, "same3": 3, "nonce3": 3}[mode], group)
                OUT.write_text(json.dumps(old + new, ensure_ascii=False, indent=1), encoding="utf-8")  # 묶음마다 저장
        old += new
    show(old)


if __name__ == "__main__":
    main()
