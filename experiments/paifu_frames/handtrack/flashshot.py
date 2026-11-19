"""쉬움으로 보낸 차례를 도구 루프 없이 Gemini Flash 한 번 부르기로 읽기(2026-11-19, 계획서 3단계 "추가 45").

대상 = routesig.py 규칙(추가 44)이 쉬움으로 보낸 차례(_work/routesig_1119/signals.json 의 route == "쉬움", 26차례).
재료 = geminiagent.Turn 과 같은 것(_work/opusread_1118/<id>/frames.txt 의 color · raw 그림).
그림 고르기 = 코드만(SAM 2 track.json — 정답 · 다른 모델 답은 안 씀):
  시작 프레임 0 · 끝 프레임
  + "들린 순간"(번호 붙은 패의 마스크 y 가 줄 높이에서 GONE_Y · hh 넘게 벗어남, 또는 면적이 첫 프레임의 GONE_AREA 밑으로 준 채 x 가
    첫 프레임에서 패 폭 넘게 움직임)을 이어진 구간으로 묶어(틈 SEG_GAP 장까지 이음) 구간마다 앞 · 시작 · 가운데 · 뒤 프레임(D 가 보이게)
  (구간은 최대 2개 — 넘으면 긴 구간부터 남김) · 모든 프레임은 color · raw 쌍, 늘 10프레임 × 2 = 20장(lift-v3)
  + 남은 몫을 차례 안쪽을 고르게 나눈 프레임(이미 든 프레임은 건너뜀)으로 채움(lift-v2).
  그림 앞 글은 "프레임 번호 · 시각 · color|raw" 만 — 고른 까닭 · 구간은 결과 파일에만(귀띔 막기, lift-v2).
답 = JSON 스키마(kind · k · unsure · why). j 는 쉬움 정의상 끝(n)으로 둠.

  python -X utf8 flashshot.py dry  [--ids a,b]                       # API 없이: 고른 프레임 · 그림 수 · 토큰 · 비용 어림, 차례 셋 그림 저장
  python -X utf8 flashshot.py run  [--ids a,b] [--tag f1] [--workers 8] [--force]
  python -X utf8 flashshot.py score [--tag f1]
결과 _work/flashshot_1119/<tag>/<id>.json · dry 그림 _work/flashshot_1119/dry/<id>/

그림 예시(few-shot, 추가 48): run · dry · score 에 --shots r16_d04,r16_d06,r16_d05(기본 없음 = 위와 똑같음).
  예시 하나 = 그 차례에 pick()(lift-v3)으로 고른 20장(같은 그림 앞 글) + "이 예시의 정답:" JSON(kind · k · unsure false · why=SHOT_NOTES).
  사용자 메시지 앞쪽에 SHOT_INTRO 로 묶어 매 차례 같은 바이트로 둠(그림도 같은 파일에서 읽음), 그 뒤 지금과 같은 대상 차례 메시지.
  지시문(PROMPT)은 그대로. run · score 는 평가 대상에서 예시 차례를 뺌. 예시 정답은 truth_all() 에서 예시 차례만 읽음.
  python -X utf8 flashshot.py dry --shots r16_d04,r16_d06,r16_d05 --ids r19_d03   # 보낼 글 → _work/flashshot_1119/dry_shots/prompt.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import routesig as rs  # noqa: E402
import sam2track as s1  # noqa: E402
from geminiagent import PRICE, Turn  # noqa: E402

OUT = hc.WORK / "flashshot_1119"
MODEL = "gemini-3.8-flash"
DEV_PREFIX, CHK_PREFIX = ("r12", "r16", "r17"), ("r19", "r13")
MAX_IMAGES = 20
SEG_GAP = 2          # 들린 프레임 사이 틈이 이 장 수 이하면 한 구간
SIDE_OFF = 3         # 구간 앞 · 뒤 원본: 구간 시작 3장 앞 · 끝 3장 뒤(0.6초)

IMG_TOKENS = 1100    # HIGH 장당 어림
OUT_TOKENS = (1000, 2500, 5000)   # 생각 + 답 어림(낮음 · 가운데 · 높음)
SEL_VERSION = "lift-v3"

PROMPT = """너는 위에서 내려다본 녹화에서 마작 대국자 한 사람의 **세운 손패 줄**을 한 차례 읽는다. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 **모든 패가 똑같이 생겼다** — 읽는 것은 위치뿐이다.
이 차례 = 패산에서 한 장을 뽑아 오고(뽑은 패 = **D**), 한 장을 강에 버림. 차례를 시작할 때 줄은 **{n}장**이다. 그림은 그 사람 시점(그림 왼쪽 = 그 사람 왼손 쪽, 아래쪽 흰 띠 = 탁자 테두리). 다른 사람 팔이 지나가기도 한다.

## 그림
- 이 차례는 프레임 {F}장(초당 5장, 번호 0 ~ {last})이다. 그중 코드가 고른 프레임의 그림 {K}장을 시간순으로 붙였다. 그림마다 앞에 "프레임 번호 · 시각 · color|raw" 글이 있다. 붙이지 않은 프레임은 볼 수 없다.
- 그림은 두 가지다:
  - **color** = 영상 추적 모델(SAM 2)이 첫 프레임에서 줄의 {n}장에 왼쪽부터 숫자 1 ~ {n} 을 붙이고, 그 뒤 프레임마다 "같은 패" 라고 본 곳에 같은 색 · 숫자를 칠한 것. D 에는 숫자가 없다.
  - **raw** = 같은 순간의 원본(색 없음).
- **추적은 틀릴 수 있다:** 손에 들려 혼자 움직이는 패는 대체로 따라간다. 버린 패의 색은 이웃 패로 옮겨 붙는 일이 많다(한 패에 숫자 둘). 손이 줄을 덮은 동안 줄이 밀리거나 패가 끼워지면 숫자가 한 칸씩 밀려 앉거나 옛 자리로 뛰어 돌아온다 — 그러면 끝 프레임의 숫자는 가지런해 보여도 실제 패와 어긋나고, 숫자 없는 패가 D 가 아닐 수 있다.

## 하는 법
- **패는 사라지지 않는다.** 줄의 패 수는 {n} → D 를 줄에 놓으면 {n}+1 → 한 장 버리면 {n}. 손이 덮은 순간에는 원본에서 손가락 밑 패까지 센다. 숫자 하나하나에 대해 "그 패는 지금 실제로 어디 있나" 를 원본에서 확인한다 — 말로 넘기지 않는다.
- D 를 끝에 붙여 두고 한 장을 버리는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 버리는 사람, 버리기 전에 패를 옮기거나 맞바꾸는 사람, 뽑은 패를 그대로 버리는 사람(쯔모기리)이 다 있다. 끝 프레임까지 본다.

## 답(JSON)
- kind: "hand"(줄에 있던 패를 버림) 또는 "tsumogiri"(D 를 그대로 버림, 줄의 패는 안 바뀜)
- k: kind 가 hand 면 버린 패가 원래 줄 {n}장(첫 프레임)에서 왼쪽부터 몇 번째였나(1 ~ {n}, D 는 세지 않음). tsumogiri 면 null
- unsure: 맞을 가능성 70% 밑이면 true
- why: 근거 3 ~ 5문장(프레임 번호와 함께)
"""
PROMPT_SHA = hashlib.sha1(PROMPT.encode("utf-8")).hexdigest()[:12]

# 그림 예시(추가 48) — why 글은 세션이 검토한다(초안).
SHOT_INTRO = "아래는 다른 차례의 예시 3개다(정답 포함). 그다음에 읽을 차례가 온다."
SHOT_NOTES = {
    "r16_d04": "뽑은 패 D 를 먼저 줄 오른쪽 끝(14번째)에 붙이고, 그다음 원래 12번째 패(D 의 두 칸 왼쪽)를 집어 강에 버린 뒤 줄을 닫았다. "
               "버릴 때 줄에는 D 를 포함해 13장이 남으므로 줄 장수만으로는 쯔모기리와 구별되지 않는다 — 집어 든 패가 줄 끝(D)이었는지, "
               "그보다 안쪽의 원래 패였는지를 그 순간의 원본에서 자리로 가른다.",
    "r16_d06": "D 를 줄 오른쪽 끝에 붙인 뒤, 그 바로 왼쪽의 원래 13번째 패를 집어 버렸다. 끝 쪽 두 장 중 어느 것을 집었는지가 답을 가른다 — "
               "끝에 붙인 D 를 그대로 냈다면 쯔모기리다.",
    "r16_d05": "줄의 숫자 붙은 패들이 정리하며 조금 움직였지만, 강으로 간 패는 뽑아 온 D 다. 원래 13장은 끝까지 줄에 남는다 — 쯔모기리.",
}


# ------------------------------------------------------------------ 대상
def target_ids() -> list:
    d = hc.jload(rs.OUTD / "signals.json")
    return [r["id"] for r in d["dev"] + d["check"] if r.get("route") == "쉬움"]


def ids_of(s: str | None) -> list:
    return target_ids() if not s else s.split(",")


# ------------------------------------------------------------------ 그림 고르기(코드만)
def segments(tid: str) -> dict:
    """track.json → 들린 프레임 · 구간. 정답 · LLM 답은 안 읽음."""
    tr = hc.jload(s1.OUT / f"{tid}_t_xpu" / "track.json")
    p, rec = tr["plan"], tr["rec"]
    n, F = p["n"], len(tr["frames"])
    w = float(np.median([b[2] - b[0] for b in p["a_boxes"]]))
    yc = float(np.median([(b[1] + b[3]) / 2 for b in p["e_boxes"]]))
    a0 = {o: rec["0"][str(o)][0] for o in range(1, n + 1)}
    x0 = {o: rec["0"][str(o)][1] for o in range(1, n + 1)}

    def lifted(fi, o):
        a, x, y = rec[str(fi)].get(str(o), [0, None, None])
        if y is not None and abs(y - yc) > s1.GONE_Y * p["hh"]:
            return True
        return a < rs.GONE_AREA * a0[o] and x is not None and x0[o] is not None and abs(x - x0[o]) > w

    who = {fi: [o for o in range(1, n + 1) if lifted(fi, o)] for fi in range(1, F)}
    flagged = [fi for fi in range(1, F) if who[fi]]
    segs = []
    for fi in flagged:
        if segs and fi - segs[-1][1] <= SEG_GAP + 1:
            segs[-1][1] = fi
        else:
            segs.append([fi, fi])
    out = []
    for s, e in segs:
        nums = sorted({o for fi in range(s, e + 1) for o in who.get(fi, [])})
        out.append({"start": s, "end": e, "len": e - s + 1, "nums": nums})
    return {"n": n, "F": F, "segs": out}


def pick(tid: str) -> dict:
    """고른 그림 목록 [(프레임, color|raw, 까닭)] — 시간순 · 같은 프레임은 color 먼저."""
    sg = segments(tid)
    F = sg["F"]
    # lift-v3: 모든 프레임을 color · raw 쌍으로 — 늘 N_FRAMES 프레임 × 2 = MAX_IMAGES 장(그림 짜임새로 구간 유무가 드러나지 않게).
    want: dict = {}   # 프레임 → 까닭(결과 파일에만)

    def add(fi, why):
        fi = max(0, min(F - 1, fi))
        want.setdefault(fi, why)

    nf = MAX_IMAGES // 2
    add(0, "시작 프레임")
    add(F - 1, "끝 프레임")
    segs = sg["segs"]
    per = 4   # 구간마다 앞 · 시작 · 가운데 · 뒤
    room = (nf - 2) // per
    keep = sorted(sorted(segs, key=lambda s: (-s["len"], s["start"]))[:room], key=lambda s: s["start"])
    dropped = [s for s in segs if s not in keep]
    for i, s in enumerate(keep, 1):
        tag = f"움직임 구간 {i}(프레임 {s['start']:03d} ~ {s['end']:03d})"
        add(s["start"] - SIDE_OFF, f"{tag} 앞")
        add(s["start"], f"{tag} 시작")
        add((s["start"] + s["end"]) // 2, f"{tag} 가운데")
        add(s["end"] + SIDE_OFF, f"{tag} 뒤")
    reason = f"구간 {len(segs)}개 중 긴 {len(keep)}개" if keep else "움직임 구간 없음"
    # 남은 몫 = 차례 안쪽을 고르게 나눈 프레임 — 이미 든 프레임과 겹친 점은 건너뜀(점 수를 늘려 가며 빈 점이 모자라지 않을 때까지, 그 빈 점들 가운데서 다시 고르게 고름).
    need = nf - len(want)
    if need > 0:
        free = []
        for m in range(need, F + 1):
            pts = sorted({round(q * (F - 1) / (m + 1)) for q in range(1, m + 1)})
            free = [x for x in pts if x not in want and 0 < x < F - 1]
            if len(free) >= need:
                break
        sel = [free[round(i * (len(free) - 1) / max(1, need - 1))] for i in range(need)] if need > 1 else [free[len(free) // 2]]
        for q, fi in enumerate(sorted(set(sel)), 1):
            add(fi, f"채움: 차례를 고르게 나눔({q}/{need})")
    items = [((fi, kind), why) for fi, why in sorted(want.items()) for kind in ("color", "raw")]
    assert len(want) == nf and len(items) == MAX_IMAGES, (tid, len(want), len(items))
    kinds: dict = {}
    for (fi, kind), _ in items:
        kinds.setdefault(fi, []).append(kind)
    assert all(v == ["color", "raw"] for v in kinds.values()), (tid, "쌍 아닌 프레임")
    return {"n": sg["n"], "F": F, "segs": segs, "kept": keep, "dropped": dropped, "reason": reason,
            "items": [{"frame": fi, "kind": k, "why": why} for (fi, k), why in items]}


def label(T: Turn, it: dict) -> str:
    """그림 앞 글 — 모든 차례 · 모든 그림에서 같은 꼴(고른 까닭은 결과 파일에만, lift-v2)."""
    return f"프레임 {it['frame']:03d} · {T.rows[it['frame']][1]} · {it['kind']}"


def img_bytes(T: Turn, it: dict) -> bytes:
    r = T.rows[it["frame"]]
    return (r[2] if it["kind"] == "color" else r[3]).read_bytes()


def build(tid: str):
    T = Turn(tid)
    pk = pick(tid)
    assert pk["F"] == len(T.rows), (tid, pk["F"], len(T.rows))
    assert pk["n"] == T.n, (tid, pk["n"], T.n)
    sysp = PROMPT.format(n=T.n, F=pk["F"], last=pk["F"] - 1, K=len(pk["items"]))
    head = f"차례를 시작할 때 줄은 {T.n}장. 프레임 {pk['F']}장 중 고른 그림 {len(pk['items'])}장(시간순):"
    tail = "위 그림만 보고 답을 JSON 으로 내라."
    return T, pk, sysp, head, tail


def est_tokens(sysp: str, head: str, tail: str, pk: dict, T: Turn) -> int:
    txt = sysp + head + tail + "".join(label(T, it) for it in pk["items"])
    return int(len(txt) / 1.5) + IMG_TOKENS * len(pk["items"])   # 글은 1.5자 = 1토큰으로 어림


def turn_items(T: Turn, pk: dict, head: str, tail: str) -> list:
    """대상 차례 메시지 = [("text", 글) | ("img", 파일)] — 예시 없을 때 보내던 것과 같은 차례."""
    out = [("text", head)]
    for it in pk["items"]:
        r = T.rows[it["frame"]]
        out += [("text", label(T, it)), ("img", r[2] if it["kind"] == "color" else r[3])]
    return out + [("text", tail)]


# ------------------------------------------------------------------ 그림 예시(추가 48)
def shots_of(s: str | None) -> list:
    if not s:
        return []
    shots = s.split(",")
    miss = [x for x in shots if x not in SHOT_NOTES]
    assert not miss, f"SHOT_NOTES 에 없는 예시: {miss}"
    assert len(set(shots)) == len(shots), f"예시가 겹침: {shots}"
    return shots


def shot_block(shots: list) -> dict:
    """예시 묶음 — 매 차례 같은 바이트(글 · 그림 파일)로 사용자 메시지 앞쪽에 둠. 정답은 예시 차례에서만 truth_all() 을 읽음."""
    if not shots:
        return {"items": [], "sha": None, "shots": [], "tokens": 0, "imgs": 0}
    truth = s1.truth_all()
    items = [("text", SHOT_INTRO)]
    for i, sid in enumerate(shots, 1):
        T, pk, _sysp, head, _tail = build(sid)
        u = truth[sid]
        hand = u["kind"] == "hand"
        assert u["kind"] in ("hand", "tsumogiri") and (not hand or isinstance(u.get("k_id"), int)), (sid, u.get("kind"), u.get("k_id"))
        ans = {"kind": u["kind"], "k": u["k_id"] if hand else None, "unsure": False, "why": SHOT_NOTES[sid]}
        items += [("text", f"예시 {i}. {head}")] + turn_items(T, pk, head, "")[1:-1]
        items.append(("text", "이 예시의 정답:\n" + json.dumps(ans, ensure_ascii=False)))
    txt = [x for t, x in items if t == "text"]
    sha = hashlib.sha1((",".join(shots) + "\n" + "\n".join(txt)).encode("utf-8")).hexdigest()[:12]
    n_img = sum(t == "img" for t, _ in items)
    return {"items": items, "sha": sha, "shots": shots, "tokens": int(sum(map(len, txt)) / 1.5) + IMG_TOKENS * n_img, "imgs": n_img}


# ------------------------------------------------------------------ dry
def cmd_dry_shots(a, shots: list):
    """예시 붙인 꼴의 dry — 보낼 글 전체(prompt.txt) · 그림 수 · 입력 토큰 어림 · shots_sha · 평가 대상 전체 비용 어림. API 안 부름."""
    sb = shot_block(shots)
    ids = [t for t in ids_of(a.ids) if t not in shots]
    evals = [t for t in target_ids() if t not in shots]
    out_of = [x for x in shots if x not in target_ids()]
    pi, po = PRICE[MODEL][0]
    print(f"지시문 sha1 {PROMPT_SHA} · 그림 고르기 {SEL_VERSION} · 모델 {MODEL} · 예시 {','.join(shots)} · shots_sha {sb['sha']}")
    if out_of:
        print(f"  (주의) 쉬움 대상에 없는 예시: {out_of}")
    print(f"예시 묶음: 그림 {sb['imgs']}장 · 입력 약 {sb['tokens']:,d}토큰")
    d = OUT / "dry_shots"
    d.mkdir(parents=True, exist_ok=True)
    for tid in ids:
        T, pk, sysp, head, tail = build(tid)
        ti = est_tokens(sysp, head, tail, pk, T)
        items = sb["items"] + turn_items(T, pk, head, tail)
        n_img = sum(t == "img" for t, _ in items)
        print(f"{tid:9s} n={pk['n']} F={pk['F']:3d} 그림 {n_img}장(예시 {sb['imgs']} + 차례 {len(pk['items'])}) · 입력 약 {ti + sb['tokens']:,d}토큰(예시 {sb['tokens']:,d} + 차례 {ti:,d})")
        lines = [f"지시문 sha1 {PROMPT_SHA} · shots {','.join(shots)} · shots_sha {sb['sha']} · 대상 {tid}", "",
                 "[system_instruction]", sysp, "[user]"]
        for t, x in items:
            lines.append(x if t == "text" else f"  <그림 {x}>")
        fn = d / ("prompt.txt" if len(ids) == 1 else f"prompt_{tid}.txt")
        fn.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        print(f"  저장 {fn}")
    # 평가 대상 전체 비용 어림 — 캐시 없음 / 예시 부분이 매번 캐시(첫 차례 빼고 1/4) 두 꼴.
    tot = 0
    sysps = set()
    for tid in evals:
        T, pk, sysp, head, tail = build(tid)
        tot += est_tokens(sysp, head, tail, pk, T)
        sysps.add(sysp)
    n = len(evals)
    full = tot + n * sb["tokens"]
    cached_in = (tot + sb["tokens"]) * pi + (n - 1) * sb["tokens"] * pi / 4
    for name, cin in (("캐시 없음", full * pi), ("예시 캐시", cached_in)):
        lo, mid, hi = [(cin + n * o * po) * 1e-6 for o in OUT_TOKENS]
        print(f"비용 어림 {n}차례({name}): {lo:.2f} / {mid:.2f} / {hi:.2f}달러(차례당 {lo / n * 100:.1f} / {mid / n * 100:.1f} / {hi / n * 100:.1f}센트)")
    print(f"  입력 합 약 {full:,d}토큰(차례당 {full / n:,.0f}) · 출력(생각 포함) 차례당 {OUT_TOKENS[0]:,d} / {OUT_TOKENS[1]:,d} / {OUT_TOKENS[2]:,d} 어림 · 입력 {pi} · 출력 {po} /100만")
    print(f"  (주의) 채운 지시문(system_instruction)이 {n}차례에서 {len(sysps)}가지 — 프레임 수 F 가 지시문에 들어가 있어, "
          f"system_instruction 이 앞머리에 들면 예시 부분의 암묵 캐시는 같은 지시문 차례끼리만 맞을 수 있음")


def cmd_dry(a):
    shots = shots_of(a.shots)
    if shots:
        return cmd_dry_shots(a, shots)
    ids = ids_of(a.ids)
    sig = {r["id"]: r for r in (lambda d: d["dev"] + d["check"])(hc.jload(rs.OUTD / "signals.json"))}
    print(f"지시문 sha1 {PROMPT_SHA} · 그림 고르기 {SEL_VERSION} · 모델 {MODEL} · 대상 {len(ids)}차례")
    pi, po = PRICE[MODEL][0]
    tot_in = 0
    rows = []
    for tid in ids:
        T, pk, sysp, head, tail = build(tid)
        ti = est_tokens(sysp, head, tail, pk, T)
        tot_in += ti
        segs = " ".join(f"{s['start']}~{s['end']}({s['len']}장·번호{s['nums']})" for s in pk["kept"]) or "-"
        drop = f" · 버린 구간 {len(pk['dropped'])}" if pk["dropped"] else ""
        fr = ",".join(f"{it['frame']}{'c' if it['kind'] == 'color' else 'r'}" for it in pk["items"])
        print(f"{tid:9s} n={pk['n']} F={pk['F']:3d} 그림 {len(pk['items']):2d} · 입력 약 {ti:6,d} | {pk['reason']} | 구간 {segs}{drop}")
        print(f"          고른 프레임 {fr}")
        rows.append((tid, pk))
    lo, mid, hi = [(tot_in * pi + len(ids) * o * po) * 1e-6 for o in OUT_TOKENS]
    print(f"\n합: 입력 약 {tot_in:,d}토큰(차례당 {tot_in / max(1, len(ids)):,.0f}) · 출력(생각 포함) 차례당 {OUT_TOKENS[0]:,d} / {OUT_TOKENS[1]:,d} / {OUT_TOKENS[2]:,d} 어림")
    print(f"비용 어림 {len(ids)}차례: {lo:.2f} / {mid:.2f} / {hi:.2f}달러(차례당 {lo / len(ids) * 100:.1f} / {mid / len(ids) * 100:.1f} / {hi / len(ids) * 100:.1f}센트) — 입력 {pi} · 출력 {po} /100만")
    # 그림 저장(사람이 눈으로 볼 것 — 보낼 그림 고르기와 무관): 쯔모기리 하나 · 끝 붙임 둘(개발 판 하나 · 확인 판 하나).
    # 26차례 모두 SAM 2 judge 끝 상태가 쯔모기리 꼴(사라진 번호 없음)이라 코드 신호로는 못 가름 → 여기서만 정답 난이도(signals.json 의 why)로 고름.
    if a.save:
        save = a.save.split(",")
    else:
        why = {t: sig[t]["why"] for t in ids if t in sig}
        ts = [t for t in ids if why.get(t) == "쯔모기리"][:1]
        ea_dev = [t for t in ids if why.get(t) == "끝 붙임" and t[:3] in DEV_PREFIX][:1]
        ea_chk = [t for t in ids if why.get(t) == "끝 붙임" and t[:3] in CHK_PREFIX][:1]
        save = ts + ea_dev + ea_chk
    gone = [t for t in ids if t in sig and sig[t]["sig"] and sig[t]["sig"]["judge"]["gone"]]
    print(f"SAM 2 judge 끝 상태에 사라진 번호가 있는 차례: {len(gone)}/{len(ids)} {gone}")
    for tid in save:
        T, pk, sysp, head, tail = build(tid)
        d = OUT / "dry" / tid
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.jpg"):
            old.unlink()
        lines = [f"지시문 sha1 {PROMPT_SHA}", "", "[system_instruction]", sysp, "[user]", head]
        for i, it in enumerate(pk["items"]):
            fn = f"{i:02d}_f{it['frame']:03d}_{it['kind']}.jpg"
            (d / fn).write_bytes(img_bytes(T, it))
            lines += [label(T, it), f"  <그림 {fn}>"]
        lines.append(tail)
        (d / "prompt.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        print(f"저장 {d} ({len(pk['items'])}장 + prompt.txt)")


# ------------------------------------------------------------------ run
def schema(types):
    S, Ty = types.Schema, types.Type
    return S(type=Ty.OBJECT, properties={
        "kind": S(type=Ty.STRING, enum=["hand", "tsumogiri"]),
        "k": S(type=Ty.INTEGER, nullable=True),
        "unsure": S(type=Ty.BOOLEAN),
        "why": S(type=Ty.STRING)}, required=["kind", "k", "unsure", "why"], property_ordering=["kind", "k", "unsure", "why"])


def retryable(e: Exception) -> bool:
    code = getattr(e, "code", None)
    return isinstance(code, int) and (code == 429 or 500 <= code < 600)


def run_one(c, tid: str, a, sb: dict | None = None) -> dict:
    from google.genai import types
    sb = sb or shot_block([])
    T, pk, sysp, head, tail = build(tid)
    hi = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
    parts = []
    for t, x in sb["items"] + turn_items(T, pk, head, tail):   # 예시 묶음(있으면, 매 차례 같은 바이트) → 대상 차례
        if t == "text":
            parts.append(types.Part(text=x))
        else:
            ip = types.Part.from_bytes(data=x.read_bytes(), mime_type="image/jpeg")
            ip.media_resolution = hi
            parts.append(ip)
    cfg = types.GenerateContentConfig(system_instruction=sysp, response_mime_type="application/json", response_schema=schema(types))
    res = {"id": tid, "model": MODEL, "prompt_sha": PROMPT_SHA, "sel": SEL_VERSION, "shots": sb["shots"], "shots_sha": sb["sha"],
           "n": T.n, "F": pk["F"], "picked": pk["items"], "segs": pk["segs"], "kept": pk["kept"], "pick_reason": pk["reason"], "tries": 0}
    t0 = time.perf_counter()
    r = err = None
    for attempt in range(4):   # 처음 + 다시 3번(429 · 5xx 만)
        res["tries"] = attempt + 1
        try:
            r = c.models.generate_content(model=MODEL, contents=[types.Content(role="user", parts=parts)], config=cfg)
            break
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:400]
            if attempt == 3 or not retryable(e):
                break
            time.sleep(10 * 2 ** attempt)
    res["s"] = round(time.perf_counter() - t0, 1)
    if r is None:
        res.update({"error": err, "kind": None, "k": None, "j": None, "usd": 0.0})
        return res
    um = r.usage_metadata
    pin = um.prompt_token_count or 0
    cin = getattr(um, "cached_content_token_count", 0) or 0
    out = um.candidates_token_count or 0
    th = getattr(um, "thoughts_token_count", 0) or 0
    pi, po = PRICE[MODEL][1] if pin > 200_000 else PRICE[MODEL][0]
    res["usage"] = {"in": pin, "cached": cin, "out": out, "think": th}
    res["usd"] = round(((pin - cin) * pi + cin * pi / 4 + (out + th) * po) * 1e-6, 5)
    res["text"] = r.text
    try:
        ans = json.loads(r.text or "")
    except Exception as e:  # noqa: BLE001
        res.update({"error": f"JSON 아님: {e}"[:200], "kind": None, "k": None, "j": None})
        return res
    hand = ans.get("kind") == "hand"
    res.update({"answer": ans, "kind": ans.get("kind"), "k": ans.get("k") if hand else None,
                "j": T.n if hand else None, "unsure": bool(ans.get("unsure"))})
    return res


def cmd_run(a):
    shots = shots_of(a.shots)
    if shots and a.tag == "f1":
        sys.exit("--shots 는 f1(예시 없는 결과) 폴더에 쓰지 않음 — --tag 를 따로 주라")
    sb = shot_block(shots)   # 부르기 전에 한 번 만들어 모든 차례에 같은 것을 씀
    import gemframes as gf
    c = gf.client()   # 변수에 잡아 둠(바로 버리면 연결이 닫힘)
    od = OUT / a.tag
    od.mkdir(parents=True, exist_ok=True)
    ids = [t for t in ids_of(a.ids) if t not in shots and (a.force or not (od / f"{t}.json").exists())]
    print(f"지시문 sha1 {PROMPT_SHA} · 예시 {','.join(shots) or '없음'} · shots_sha {sb['sha']} · {len(ids)}차례 → {od}")
    with ThreadPoolExecutor(a.workers) as ex:
        for r in ex.map(lambda t: run_one(c, t, a, sb), ids):
            r["at"] = hc.hms(int(time.time() * 1000), date=True)
            hc.jsave(od / f"{r['id']}.json", r)
            print(r["id"], r.get("kind"), r.get("k"), "unsure" if r.get("unsure") else "", f"{r.get('s')}초", f"{r.get('usd')}달러",
                  f"시도 {r.get('tries')}", r.get("error", ""), flush=True)


# ------------------------------------------------------------------ score
def cmd_score(a):
    truth = s1.truth_all()
    shots = shots_of(a.shots)
    ids = [t for t in ids_of(a.ids) if t not in shots]   # 예시 차례는 평가에서 뺌(추가 48)
    rows = []
    for tid in ids:
        u = truth[tid]
        f = OUT / a.tag / f"{tid}.json"
        r = hc.jload(f) if f.exists() else None
        grp = "쯔모기리" if u.get("kind") == "tsumogiri" else "끝 붙임"
        part = "개발" if tid[:3] in DEV_PREFIX else "확인"
        if r is None or r.get("kind") is None:
            rows.append({"id": tid, "grp": grp, "part": part, "ok": False, "kind_ok": False, "ans": False, "unsure": False, "r": r})
            print(f"{tid:9s} {grp:4s} {part} | 정답 {u.get('kind')} {u.get('k_id')} | {'없음' if r is None else '답 없음 ' + str(r.get('error'))}")
            continue
        kind_ok = r["kind"] == u["kind"]
        ok = kind_ok and (u["kind"] != "hand" or r.get("k") == u.get("k_id"))
        rows.append({"id": tid, "grp": grp, "part": part, "ok": ok, "kind_ok": kind_ok, "ans": True, "unsure": bool(r.get("unsure")), "r": r})
        j_note = "" if u["kind"] != "hand" or u.get("j_closed") == T_n(r) else f" (정답 j {u.get('j_closed')} ≠ n)"
        print(f"{tid:9s} {grp:4s} {part} | 정답 {u['kind']} {u.get('k_id')} | Flash {r['kind']} {r.get('k')}{'?' if r.get('unsure') else ''} "
              f"{'✓' if ok else '✗'}{j_note} | 그림 {len(r.get('picked', []))} · {r.get('s')}초 · {r.get('usd')}달러")

    def line(title, sub):
        if not sub:
            return
        ok = sum(x["ok"] for x in sub)
        kd = sum(x["kind_ok"] for x in sub)
        un = sum(x["unsure"] for x in sub)
        quiet = sum(x["ans"] and not x["ok"] and not x["unsure"] for x in sub)
        print(f"  {title:12s} 맞음 {ok}/{len(sub)} · kind 맞음 {kd} · unsure {un}(그중 맞음 {sum(x['unsure'] and x['ok'] for x in sub)}) · 조용한 틀림 {quiet} · 답 없음 {sum(not x['ans'] for x in sub)}")

    print(f"\n[{a.tag}] 지시문 sha {sorted({x['r'].get('prompt_sha') for x in rows if x['r']}) }")
    if shots:
        print(f"  예시 {','.join(shots)}(평가에서 뺌 → {len(rows)}차례) · 결과 파일의 shots_sha "
              f"{sorted({str(x['r'].get('shots_sha')) for x in rows if x['r']})} · 결과 파일의 shots {sorted({','.join(x['r'].get('shots') or []) or '없음' for x in rows if x['r']})}")
    line("전체", rows)
    for g in ("쯔모기리", "끝 붙임"):
        line(g, [x for x in rows if x["grp"] == g])
    for p in ("개발", "확인"):
        line(f"{p} 판", [x for x in rows if x["part"] == p])
    base = sum(x["grp"] == "쯔모기리" for x in rows)
    print(f"  기준선(늘 쯔모기리) {base}/{len(rows)}")
    tot = sum(x["ok"] for x in rows)
    ea = [x for x in rows if x["grp"] == "끝 붙임"]
    ea_ok = sum(x["ok"] for x in ea)
    if any(not x["ans"] for x in rows):
        verdict = "판정 못 함(답 없는 차례가 있음)"
    elif tot >= len(rows) - 1 and ea_ok == len(ea):
        verdict = f"✅ 쉬운 차례는 짧은 한 번으로 된다(맞음 {tot}/{len(rows)} ≥ {len(rows) - 1} · 끝 붙임 {ea_ok}/{len(ea)})"
    else:
        verdict = f"❌ 안 됨(맞음 {tot}/{len(rows)} · 끝 붙임 {ea_ok}/{len(ea)} — 기준 ≥ {len(rows) - 1} 이고 끝 붙임 전부)"
    print(f"  판정(추가 45 기준): {verdict}")
    if shots:   # 추가 48 기준: 다 맞음 · 조용한 틀림 0 → 고친다 / 하나 틀림 → 효과 없음 / 둘 이상 → 해침
        quiet = sum(x["ans"] and not x["ok"] and not x["unsure"] for x in rows)
        miss = len(rows) - tot
        if any(not x["ans"] for x in rows):
            v48 = "판정 못 함(답 없는 차례가 있음)"
        elif miss == 0 and quiet == 0:
            v48 = "예시가 고친다(다음은 다른 판에서 확인)"
        elif miss == 1:
            v48 = "효과 없음"
        else:
            v48 = "해침(틀린 차례의 why 를 볼 것)"
        print(f"  판정(추가 48 기준): {v48} — 맞음 {tot}/{len(rows)} · 조용한 틀림 {quiet}")
        print("  끝 붙임 차례: " + " · ".join(f"{x['id']} {'✓' if x['ok'] else '✗'}" for x in ea))
    rs_ = [x["r"] for x in rows if x["r"]]
    secs = [r["s"] for r in rs_ if r.get("s") is not None]
    usd = sum(r.get("usd") or 0 for r in rs_)
    if secs:
        print(f"  합 {usd:.3f}달러(차례당 {usd / len(rs_) * 100:.2f}센트) · 차례당 시간 중앙 {float(np.median(secs)):.1f}초 · 최대 {max(secs):.1f}초")
        u = [r["usage"] for r in rs_ if r.get("usage")]
        if u:
            print(f"  토큰 중앙: 입력 {int(np.median([x['in'] for x in u])):,d} · 출력 {int(np.median([x['out'] for x in u])):,d} · 생각 {int(np.median([x['think'] for x in u])):,d}")


def T_n(r: dict) -> int:
    return r.get("n") or 13


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("dry")
    q.add_argument("--ids", default=None)
    q.add_argument("--save", default=None, help="그림을 저장할 차례(기본 = 쯔모기리 꼴 하나 · 끝 붙임 꼴 둘)")
    q.add_argument("--shots", default=None, help="그림 예시 차례(쉼표 목록, 기본 없음)")
    q = sp.add_parser("run")
    q.add_argument("--ids", default=None)
    q.add_argument("--tag", default="f1")
    q.add_argument("--workers", type=int, default=8)
    q.add_argument("--force", action="store_true")
    q.add_argument("--shots", default=None, help="그림 예시 차례(쉼표 목록, 기본 없음) — 평가 대상에서 뺌")
    q = sp.add_parser("score")
    q.add_argument("--ids", default=None)
    q.add_argument("--tag", default="f1")
    q.add_argument("--shots", default=None, help="그림 예시 차례(쉼표 목록, 기본 없음) — 평가 대상에서 뺌")
    a = ap.parse_args()
    {"dry": cmd_dry, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
