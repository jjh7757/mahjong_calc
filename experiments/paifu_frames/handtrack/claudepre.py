"""claudeagent.py 의 변형 — 첫 메시지에 칸 틀 도구가 본 "사건 구간" 을 미리 잘라 넣기(2026-11-19 밤, 계획서 3단계 "추가 54").

c1 기록에서 Opus 는 고르게 나눈 6프레임 view → strip 으로 사건 구간 찾기 → view · zoom 확인 → 답 순서로 읽었고, 비용 대부분이
"언제 · 어디" 를 찾는 strip 이었다. 칸 틀 도구(slotgrid.track)가 그 구간을 이미 알므로 첫 메시지에 ① 6프레임 ② 사건 글 ③ 빈 칸 둘레 raw strip 을 넣는다.
지시문(system) · 도구 5개 · effort · 단계 · 상한 · 채점은 claudeagent 그대로 — 이 파일은 claudeagent.first_content 와 run_one 만 갈아 끼운다(기존 파일은 안 고침).

  python -X utf8 claudepre.py dry --ids hard8                    # API 없이: 사건 글 · 그림 장수 · 크기 · 토큰 어림, _work/claudeagent_1119/dry_pre/<id>/
  python -X utf8 claudepre.py run --ids hard8 --tag p1 [--workers 4] [--effort high] [--max-steps 60] [--max-usd 5] …   # tag c1 · c2 거부
  python -X utf8 claudepre.py score --ids hard8 --tag p1         # claudeagent 채점 그대로 + c1 과 나란히(c1 은 읽기만)
  python -X utf8 claudepre.py selftest --ids hard8               # API 없이 저장 점검(pre 를 가짜 결과에 붙여 hc.jsave → 다시 읽기), _work/claudeagent_1119/selftest_pre/
run 은 차례마다 API 전에 pre 를 만들고 json 직렬화를 검사하며, 끝나는 즉시 그 스레드에서 저장한다(11-19 고침 — pre 의 numpy int64 로 저장이 죽어 5차례 답을 잃음).
결과 _work/claudeagent_1119/<tag>/<id>.json(claudeagent 결과 + "pre": 사건 · strip 인자 · 넣은 그림 장수). 정답 · 다른 판독 답은 첫 메시지에 안 넣음.

프레임 축: 칸 틀(검출 캐시 det_<판>.json, 초당 약 5장)의 프레임 ms → 저장된 앞으로 추적 track.json 의 frames(= Turn 의 번호) 중 가장 가까운 번호.
strip 후보: Turn 프레임 길이(b − a + 1)가 STRIP_RUN_MAX(40)를 넘는 빈 칸 · 가림 구간은 뺌(줄 밀림 · 끝 상태일 가능성이 높음 — 사건 글에는 남김).
  빈 칸 구간이 있는데 후보가 다 빠지면 strip 없음(안내 글도 뺌). 빈 칸 구간이 아예 없을 때만 40 이하 가림 중 가장 긴 것 하나.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import claudeagent as ca  # noqa: E402
import geminiagent as ga  # noqa: E402
import htcommon as hc  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402
import sam2verify as sv  # noqa: E402
import slotgrid as sg  # noqa: E402
import slotroute as sr  # noqa: E402

E_JOIN = 3          # 같은 칸의 빈 칸 run 이 이 프레임 수 이내로 떨어져 있으면 하나로
EDGE_MIN = 2        # 끝 바깥 칸 'F' run 은 2프레임 이상
COV_MIN = 3         # 가림 run 은 3프레임 이상
MAX_LINES = 20      # 사건 글 줄 수 한도(넘으면 긴 구간부터)
N_STRIPS = 3        # 빈 칸 구간 strip 은 길이 순 셋까지
STRIP_PAD = 4       # strip 앞뒤 프레임
STRIP_ROWS_MAX = 12  # strip 한 구간의 줄 수 한도
SLOT_PAD = 2        # strip x = 그 칸 ± 2칸
Y_PAD = 1.5         # strip y = 줄 가운데 ± 1.5 × hh
EVEN = 6            # 고르게 나눈 프레임 수
STRIP_RUN_MAX = 40  # strip 후보 구간의 Turn 프레임 길이 한도(넘으면 줄 밀림 · 끝 상태로 보고 strip 을 안 붙임)
PROTECTED = {"c1", "c2"}
HEAD = ("아래는 코드(검출 상자로 칸을 센 것)가 본 것이다 — 틀릴 수 있으니 원본으로 확인하라. "
        "칸 번호 = 차례 시작 줄 왼쪽부터 1 ~ {n}, {n1} = 줄 오른쪽 끝 바깥, {n2} = 그 한 칸 더 바깥, 0 = 왼쪽 끝 바깥. "
        "줄이 통째로 한 칸 밀리면 한쪽 끝 칸이 비고 반대쪽 끝 바깥 칸에 패가 선 것으로 적힌다 — 그런 줄은 패가 나간 것이 아닐 수 있다.")
STRIP_NOTE = "위 strip 이 코드가 본 사건 구간을 덮는다. 넓은 strip 을 다시 부르기보다 더 확인할 곳만 도구로 보라."
PRE: dict = {}      # tid → 첫 메시지에 넣은 것(run_one 결과에 덧붙임)


# ------------------------------------------------------------------ 사건
def events(tid: str) -> dict:
    """칸 틀 도구의 사건 → Turn 프레임 번호 구간. 정답 · 판독 답 안 씀."""
    gid, t = s1.turn_of(tid)
    n = t["n_calc"]
    det = {int(k): v for k, v in hc.jload(sg.OUT / f"det_{gid}.json").items()}
    w0, w1 = sg.window(t)
    frs = [(ms, det[ms]) for ms in sorted(det) if w0 <= ms <= w1]
    fwd = hc.jload(s1.OUT / f"{tid}_t_xpu" / "track.json")
    fr = np.array(fwd["frames"], np.int64)
    out = {"n": n, "anchor": None, "events": [], "axis": {}}
    an = sg.anchor(frs, n)
    if an is None:
        out["why"] = "시작 줄 없음"
        return out
    tr = sg.track(frs, n, an)
    ms = [f["ms"] for f in tr]
    out["anchor"] = hc.mss(an[4])
    step_t = float(np.median(np.diff(fr))) if len(fr) > 1 else 0.0
    out["axis"] = {"slot_frames": len(ms), "slot_step_ms": float(np.median(np.diff(ms))) if len(ms) > 1 else 0.0,
                   "turn_frames": len(fr), "turn_step_ms": step_t,
                   "slot_frames_in_turn": sum(fr[0] <= x <= fr[-1] for x in ms),
                   "common": len(set(ms) & set(int(x) for x in fr))}
    half = step_t / 2

    def to_turn(a, b):
        """slotgrid 프레임 번호 구간 → Turn 번호 구간(밖이면 None)."""
        ma, mb = ms[a], ms[b]
        if mb < fr[0] - half or ma > fr[-1] + half:
            return None
        ia = int(np.argmin(np.abs(fr - ma)))
        ib = int(np.argmin(np.abs(fr - mb)))
        return ia, ib

    ev = []
    for i in range(1, n + 1):
        rr = sr.runs([f["st"][i] == "E" for f in tr])
        merged = []
        for a, b in rr:
            if merged and a - merged[-1][1] - 1 <= E_JOIN:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        for a, b in merged:
            ev.append({"type": "empty", "slot": i, "sa": a, "sb": b})
    for i in (n + 1, n + 2, 0):
        for a, b in sr.runs([f["st"][i] == "F" for f in tr]):
            if b - a + 1 >= EDGE_MIN:
                ev.append({"type": "edge", "slot": i, "sa": a, "sb": b})
    for a, b in sr.runs([f["cov"] is not None for f in tr]):
        if b - a + 1 >= COV_MIN:
            cs = [tr[k]["cov"] for k in range(a, b + 1)]
            lo, hi = int(min(c[0] for c in cs)), int(max(c[1] for c in cs))   # track 의 cov 는 줄 양 끝 한 칸 밖까지(-1 · n+3 도 나옴) → 글은 0 ~ n+2 로 자름
            ev.append({"type": "cover", "lo": max(0, lo), "hi": min(n + 2, hi), "lo_raw": lo, "hi_raw": hi, "sa": a, "sb": b})
    for e in ev:
        tt = to_turn(e["sa"], e["sb"])
        if tt is None:
            e["drop"] = True
            continue
        e["a"], e["b"] = tt
        e["t0"], e["t1"] = hc.mss(ms[e["sa"]]), hc.mss(ms[e["sb"]])
    out["events"] = sorted([e for e in ev if not e.get("drop")], key=lambda e: (e["a"], e["b"]))
    out["dropped"] = sum(bool(e.get("drop")) for e in ev)
    return to_py(out)


def to_py(x):
    """numpy 값 · 튜플 → 순수 파이썬(json 으로 저장되게). dict 키는 str/int 로."""
    if isinstance(x, dict):
        return {(k if isinstance(k, (str, int)) and not isinstance(k, bool) else str(to_py(k))): to_py(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_py(v) for v in x]
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, np.ndarray):
        return to_py(x.tolist())
    return x


def event_line(e: dict, n: int) -> str:
    if e["type"] == "empty":
        what = f"{e['slot']}번 칸이 비어 보임"
    elif e["type"] == "edge":
        what = f"{e['slot']}번 칸({'n+1' if e['slot'] == n + 1 else 'n+2' if e['slot'] == n + 2 else '왼쪽 끝 바깥'})에 패가 서 있음"
    else:
        what = f"손 · 소매가 칸 {e['lo']} ~ {e['hi']} 를 덮음"
    return f"프레임 {e['a']:03d} ~ {e['b']:03d}: {what}"


def event_text(ev: dict) -> str:
    n = ev["n"]
    head = HEAD.format(n=n, n1=n + 1, n2=n + 2)
    es = ev["events"]
    if not es:
        return head + "\n코드가 본 사건 없음" + (f"({ev['why']})" if ev.get("why") else "")
    keep = es
    more = 0
    if len(es) > MAX_LINES:
        keep = sorted(sorted(es, key=lambda e: -(e["b"] - e["a"]))[:MAX_LINES], key=lambda e: (e["a"], e["b"]))
        more = len(es) - MAX_LINES
    return head + "\n" + "\n".join(event_line(e, n) for e in keep) + (f"\n… 외 {more}개" if more else "")


# ------------------------------------------------------------------ strip 인자
def slot_x(p: dict, j: int, n: int) -> tuple:
    """칸 j(0 ~ n+2)의 x 범위 — plan.a_boxes(band2 시점 [x0, y0, x1, y1], 왼쪽부터) 로. 끝 바깥은 패 폭만큼 밀어 냄."""
    bs = sorted(p["a_boxes"], key=lambda b: b[0])
    w = float(np.median([b[2] - b[0] for b in bs]))
    if 1 <= j <= n:
        return bs[j - 1][0], bs[j - 1][2]
    if j > n:
        return bs[-1][0] + (j - n) * w, bs[-1][2] + (j - n) * w
    return bs[0][0] - w, bs[0][2] - w


def strip_args(T, p: dict, a: int, b: int, lo: int, hi: int) -> dict:
    F = len(T.rows)
    n = T.n
    st, en = max(0, a - STRIP_PAD), min(F - 1, b + STRIP_PAD)
    step = max(1, math.ceil((en - st + 1) / STRIP_ROWS_MAX))
    x0 = slot_x(p, max(0, lo - SLOT_PAD), n)[0]
    x1 = slot_x(p, min(n + 2, hi + SLOT_PAD), n)[1]
    yc = float(np.median([(bb[1] + bb[3]) / 2 for bb in p["a_boxes"]]))
    return {"start": st, "end": en, "step": step, "x0": int(max(0, round(x0))), "x1": int(min(T.W, round(x1))),
            "y0": int(max(0, round(yc - Y_PAD * p["hh"]))), "y1": int(min(T.H, round(yc + Y_PAD * p["hh"]))), "kind": "raw"}


# ------------------------------------------------------------------ 첫 메시지
_orig_first = ca.first_content


BODY: dict = {}     # tid → 만든 첫 메시지(run_one_pre 가 API 전에 만들어 둔 것을 run_one 이 그대로 받음)


def first_content_pre(T) -> list:
    if T.tid in BODY:
        return BODY[T.tid]
    base = _orig_first(T)
    assert base[-1].get("type") == "text" and base[-1]["text"] == ca.FIRST_TAIL, "claudeagent.first_content 꼴이 바뀜"
    body = list(base[:-1])
    F = len(T.rows)
    p = hc.jload(s1.OUT / f"{T.tid}_t_xpu" / "track.json")["plan"]
    # ① 고르게 나눈 6장
    even = [round(q * (F - 1) / (EVEN + 1)) for q in range(1, EVEN + 1)]
    body.append({"type": "text", "text": f"고르게 나눈 프레임 {EVEN}장(color):"})
    for i in even:
        body.append({"type": "text", "text": f"프레임 {i:03d} {T.rows[i][1]} color"})
        body.append(ca.img_block(ga.jpg(T.img(i, "color"))))
    # ② 사건 글
    ev = events(T.tid)
    body.append({"type": "text", "text": event_text(ev)})
    # ③ strip
    short = lambda e: e["b"] - e["a"] + 1 <= STRIP_RUN_MAX  # noqa: E731
    emp = [e for e in ev["events"] if e["type"] == "empty"]
    pick = sorted(sorted([e for e in emp if short(e)], key=lambda e: -(e["b"] - e["a"]))[:N_STRIPS], key=lambda e: (e["a"], e["b"]))
    strips = []
    if pick:
        for e in pick:
            strips.append((e, strip_args(T, p, e["a"], e["b"], e["slot"], e["slot"]),
                           f"{e['slot']}번 칸 둘레"))
    elif not emp:   # 빈 칸 구간이 아예 없을 때만 가림(3 ~ 40프레임) 하나. 빈 칸이 있는데 다 길어서 빠졌으면 strip 없음
        cov = [e for e in ev["events"] if e["type"] == "cover" and short(e)]
        if cov:
            e = max(cov, key=lambda e: (e["b"] - e["a"], -e["a"]))
            strips.append((e, strip_args(T, p, e["a"], e["b"], e["lo"], e["hi"]), f"칸 {e['lo']} ~ {e['hi']} 둘레"))
    used = []
    for e, args, where in strips:
        imgs = ga.strip_images(T, args)
        body.append({"type": "text", "text": f"프레임 {args['start']:03d} ~ {args['end']:03d}, {where}(raw strip): " + " | ".join(d for d, _ in imgs)})
        body += [ca.img_block(x) for _, x in imgs]
        used.append({"for": {k: e[k] for k in ("type", "slot", "lo", "hi", "a", "b") if k in e}, "args": args, "images": len(imgs)})
    # ④
    body.append({"type": "text", "text": (STRIP_NOTE + "\n\n" if used else "") + ca.FIRST_TAIL})
    PRE[T.tid] = to_py({"events": ev, "even": even, "strips": used,
                        "images": sum(b["type"] == "image" for b in body), "added_images": sum(b["type"] == "image" for b in body) - sum(b["type"] == "image" for b in base)})
    return body


_orig_run_one = ca.run_one


def build_pre(tid: str) -> dict:
    """첫 메시지를 만들어 BODY · PRE 에 두고, pre 가 json 으로 저장되는지 검사(실패하면 예외 — API 를 부르기 전)."""
    BODY.pop(tid, None)
    BODY[tid] = first_content_pre(ga.Turn(tid))
    json.dumps(PRE[tid], ensure_ascii=False)
    return PRE[tid]


def run_one_pre(tid: str, a, client) -> dict:
    pre = build_pre(tid)                       # API 전에: 만들기 · 직렬화 검사
    r = _orig_run_one(tid, a, client)          # 안에서 first_content(= BODY[tid]) 를 받음
    r["pre"] = pre
    r["variant"] = "claudepre"
    return r


def install():
    ca.first_content = first_content_pre
    ca.run_one = run_one_pre


# ------------------------------------------------------------------ 명령
def cmd_dry(a):
    install()
    od = ca.OUT / "dry_pre"
    rows = []
    for tid in sv.ids_of(a.ids):
        T = ga.Turn(tid)
        body = ca.first_content(T)
        d = od / tid
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.jpg"):
            f.unlink()
        txt, k, sizes, tok = [], 0, [], 0.0
        for b in body:
            if b["type"] == "text":
                txt.append(b["text"])
            else:
                raw = base64.standard_b64decode(b["source"]["data"])
                w, h = Image.open(io.BytesIO(raw)).size
                (d / f"{k:02d}.jpg").write_bytes(raw)
                txt.append(f"[그림 {k:02d} {w}×{h}]")
                sizes.append(f"{w}×{h}")
                tok += w * h / 750
                k += 1
        (d / "first.txt").write_bytes(("\n".join(txt) + "\n").encode("utf-8"))
        P = PRE[tid]
        ax = P["events"]["axis"]
        print(f"\n[{tid}] 줄 {T.n}장 · 프레임 {len(T.rows)} · 시작 줄 {P['events']['anchor']} · 축: 칸 틀 {ax.get('slot_frames')}장(간격 {ax.get('slot_step_ms')}ms, 차례 안 {ax.get('slot_frames_in_turn')} · 같은 ms {ax.get('common')}) / 차례 {ax.get('turn_frames')}장(간격 {ax.get('turn_step_ms')}ms) · 밖이라 버린 사건 {P['events'].get('dropped', 0)}")
        print(f"  고르게 나눈 프레임 {P['even']}")
        print("  " + event_text(P["events"]).replace("\n", "\n  "))
        for s in P["strips"]:
            print(f"  strip {s['for']} → {s['args']} · 그림 {s['images']}장")
        print(f"  그림 {k}장(그중 더한 것 {P['added_images']}) [{', '.join(sizes)}] · 토큰 어림 {tok:,.0f}")
        rows.append((tid, k, P["added_images"], len(P["events"]["events"]), len(P["strips"]), tok))
    print("\n차례 | 그림(더한 것) | 사건 수 | strip 구간 | 토큰 어림(가로×세로/750 합)")
    for tid, k, add, ne, ns, tok in rows:
        print(f"{tid:9s} | {k:2d}({add:2d}) | {ne:3d} | {ns} | {tok:,.0f}")
    print(f"합 토큰 어림 {sum(r[5] for r in rows):,.0f} · 그림 저장 {od}")


def save_result(od: Path, r: dict):
    """한 차례 결과를 바로 저장. 실패하면 default=str 로 다시 쓰고 오류를 찍음(다른 차례 답은 안 잃음)."""
    f = od / f"{r['id']}.json"
    try:
        hc.jsave(f, r)
    except Exception as e:  # noqa: BLE001
        print(f"  ! {r['id']} 저장 실패 {type(e).__name__}: {e} — default=str 로 다시 씀", flush=True)
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def cmd_run(a):
    """claudeagent.cmd_run 과 같은 일 — 다만 차례가 끝나는 즉시 그 스레드에서 저장."""
    import time
    from concurrent.futures import ThreadPoolExecutor
    if a.tag in PROTECTED:
        raise SystemExit(f"tag {a.tag} 는 claudeagent 결과 — 다른 tag 로(예: p1)")
    install()
    client = ca.make_client()
    if client is None:
        print("ANTHROPIC_API_KEY 가 .env 에 없음")
        return
    od = ca.OUT / a.tag
    od.mkdir(parents=True, exist_ok=True)
    ids = [t for t in sv.ids_of(a.ids) if a.force or not (od / f"{t}.json").exists()]
    print(f"{len(ids)}차례 · {a.model} · effort {a.effort} · 단계 {a.max_steps} · 차례당 {a.max_usd}달러 · 나란히 {a.workers} · claudepre", flush=True)

    def one(t):
        try:
            r = run_one_pre(t, a, client)
        except Exception as e:  # noqa: BLE001  (pre 만들기 · 검사 실패 — API 전)
            print(f"  ! {t} 실패(저장 안 함) {type(e).__name__}: {e}", flush=True)
            return None
        r["at"] = hc.hms(int(time.time() * 1000), date=True)
        save_result(od, r)
        print(r["id"], r.get("kind"), r.get("k"), r.get("j"), f"단계 {r.get('steps')}", f"{r.get('s')}초", f"약 {r.get('usd')}달러", r.get("error", ""), flush=True)
        return r["id"]

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, ids))


def cmd_selftest(a):
    """API 없이 저장 점검: pre 를 만들고 run_one 꼴의 가짜 결과를 hc.jsave 로 써 본 뒤 다시 읽어 pre 가 같은지."""
    install()
    od = ca.OUT / "selftest_pre"
    od.mkdir(parents=True, exist_ok=True)
    ok = 0
    ids = sv.ids_of(a.ids)
    for tid in ids:
        try:
            pre = build_pre(tid)
            fake = {"id": tid, "model": a.model, "effort": a.effort, "src": a.src, "steps": 0, "s": 0.0,
                    "usage": {"in": 0, "cache_read": 0, "cache_write": 0, "out": 0, "calls": 0, "max_ctx": 0}, "log": [],
                    "kind": None, "k": None, "j": None, "error": "selftest", "usd": 0.0, "pre": pre, "variant": "claudepre", "at": "selftest"}
            hc.jsave(od / f"{tid}.json", fake)
            back = hc.jload(od / f"{tid}.json")
            same = back["pre"] == pre
            ok += same
            print(f"{tid:9s} 저장 · 다시 읽기 {'같음' if same else '**다름**'} · 사건 {len(pre['events']['events'])} · strip {len(pre['strips'])} · 그림 {pre['images']}")
        except Exception as e:  # noqa: BLE001
            print(f"{tid:9s} **실패** {type(e).__name__}: {e}")
    print(f"selftest {ok}/{len(ids)} 통과 · {od}")


def tool_counts(r: dict) -> dict:
    c = {}
    for x in r.get("log", []):
        if x.get("tool"):
            c[x["tool"]] = c.get(x["tool"], 0) + 1
    return c


def cmd_score(a):
    print(f"== {a.tag}(claudeagent 채점 그대로)")
    ca.cmd_score(a)
    truth = s1.truth_all()
    ids = sv.ids_of(a.ids)
    print(f"\n== {a.tag} 와 {a.base} 나란히")
    print(f"{'차례':9s} | {a.tag}: 맞음 · 단계 · strip/view/zoom · 캐시 쓰기 · 달러 | {a.base}: 맞음 · 단계 · strip/view/zoom · 캐시 쓰기 · 달러")
    tot = {a.tag: [0, 0, 0, 0.0], a.base: [0, 0, 0, 0.0]}
    for tid in ids:
        cells = []
        for tag in (a.tag, a.base):
            f = ca.OUT / tag / f"{tid}.json"
            if not f.exists():
                cells.append("없음")
                continue
            r = hc.jload(f)
            ok = m.right(m.norm(r), truth[tid])
            tc = tool_counts(r)
            cw = (r.get("usage") or {}).get("cache_write", 0)
            tot[tag][0] += ok
            tot[tag][1] += r.get("steps") or 0
            tot[tag][2] += cw
            tot[tag][3] += r.get("usd") or 0
            cells.append(f"{'✓' if ok else '✗'}{'?' if r.get('unsure') else ''} · {r.get('steps')} · {tc.get('strip', 0)}/{tc.get('view', 0)}/{tc.get('zoom', 0)} · {cw:,} · {r.get('usd')}")
        print(f"{tid:9s} | {cells[0]} | {cells[1]}")
    for tag, (ok, st, cw, usd) in tot.items():
        print(f"합 {tag}: 맞음 {ok}/{len(ids)} · 단계 {st} · 캐시 쓰기 {cw:,} · {usd:.2f}달러")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "score", "dry", "selftest"):
        q = sp.add_parser(name)
        q.add_argument("--ids", default="hard8")
        q.add_argument("--tag", default="p1")
        if name in ("run", "dry", "selftest"):   # claudeagent.main 과 같은 인자
            q.add_argument("--model", default=ca.MODEL, choices=sorted(ca.PRICE))
            q.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
            q.add_argument("--max-tokens", type=int, default=32000)
            q.add_argument("--show-thinking", action="store_true")
            q.add_argument("--src", default="opusread_1118")
        if name == "run":
            q.add_argument("--max-steps", type=int, default=60)
            q.add_argument("--max-usd", type=float, default=5.0)
            q.add_argument("--workers", type=int, default=1)
            q.add_argument("--force", action="store_true")
        if name == "score":
            q.add_argument("--base", default="c1", help="나란히 볼 claudeagent 결과(읽기만)")
    a = ap.parse_args()
    if hasattr(a, "src"):   # claudeagent.main 과 같게 — Turn 과 check 도구가 같은 재료 폴더를 보게
        ca.SRC = ga.SRC = hc.WORK / a.src
        if not ca.SRC.is_dir():
            raise SystemExit(f"재료 폴더 없음: {ca.SRC}")
    {"run": cmd_run, "score": cmd_score, "dry": cmd_dry, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
