"""LLM 이 SAM 2 기록을 근거로 읽기 — 줄글만(L) / SAM 2 기록만(S) / 둘 다(LS)(2026-11-18, 계획서 3단계 "추가 25"). Gemini 호출 없음.

SAM 2 v2(sam2track2.py)의 저장된 track.json 을 글로 풀어, 칸 틀 줄글(slotgrid look)과 같은 꼴의 "정답 모르는 읽는 쪽" 글 파일을 만든다.
읽는 쪽은 하위 에이전트(글 파일 하나만 읽고 답 파일 하나만 씀). 답 꼴 · 채점 셈은 표 12-39(slotgrid score)와 같다.

  python -X utf8 sam2llm.py make [--device xpu]     # → _work/sam2llm_1118/blind_{L,S,LS}.txt (내용은 화면에 안 찍음)
  python -X utf8 sam2llm.py score [--reader gem]    # read_<팔>_r<회>.json 채점 + 저장된 줄글 읽기 · SAM 2 코드 판정과 나란히
  python -X utf8 sam2llm.py gem [--dry]             # 같은 글을 Gemini 가 차례마다 읽기(계획서 추가 26) → read_gem_<팔>_r<회>.json
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2track as s1  # noqa: E402
import sam2track2 as s2  # noqa: E402
import slotgrid as sg  # noqa: E402
import slotgrid_guide as gd  # noqa: E402

OUT = hc.WORK / "sam2llm_1118"
IDS = s2.HARD8
ARMS = ("L", "S", "LS")
ALL_ARMS = ARMS + ("S3", "LS3")     # S3 · LS3 = 경로 · 뜀 · 둘째 기록을 넣은 글(추가 27)

SAM_GUIDE = """
## SAM 2 추적 기록 — 이 글의 꼴
- 차례 시작 줄의 패 N장에 **물체 번호 1 ~ N**(왼쪽부터 = 시작 칸 번호)을 붙이고, 영상 분할 추적 모델(SAM 2)이 프레임마다 각 물체의 마스크(그 패라고 본 화소 덩어리)를 따라간 기록이다. 패 뒷면이 모두 같아서 **추적이 틀릴 수 있다** — 물체 번호가 실제 그 패라는 보장은 없다.
- **자리** = 칸 번호 단위의 가로 위치. 3.0 = 3번 칸 한가운데, 0.0 = 0번 칸(줄 왼쪽 끝 바로 옆) 한가운데, 14.0 = 14번 칸. 틀은 차례 시작 줄에 박아 두고 안 움직인다(프레임 줄글의 칸 틀과 같은 틀).
- **닻** = 손이 줄에서 떨어져 줄의 상자가 모두 깨끗이 보인 프레임. 닻마다 적는 것:
  - `줄 상자 13개 — 자리 …` = 검출기가 그 프레임에서 본 줄 상자들의 자리(왼쪽부터). 상자는 "거기 패가 있다" 일 뿐 어느 패인지는 모른다.
  - `닻 직전 마스크` = 그 닻 바로 앞 프레임에서 각 물체 마스크의 자리. `4@5.0` = 물체 4 의 마스크가 자리 5.0 에 있음. `안 보임` = 마스크가 거의 없음. `(앞)` · `(뒤)` = 줄에서 대국자 쪽 · 먼 쪽으로 벗어나 있음.
  - `마스크 없는 상자` = 어느 물체의 마스크도 안 앉은 줄 상자. `한 상자에 둘` = 두 물체의 마스크가 같은 상자에 겹쳐 앉음.
  - `코드 배정` = 닻에서 코드가 물체 ↔ 상자를 다시 맞춘 결과. 규칙: 구간 안에서 들린(줄에서 벗어난) 물체는 마스크가 있는 상자에, 안 들린 물체는 **앞 닻의 왼쪽 → 오른쪽 순서 그대로** 남은 상자에. 줄 장수가 물체 수보다 하나 적으면 "나감 후보"(마스크가 온전히 못 앉았거나, 들린 채 다른 물체와 겹친 물체) 하나를 뺀다. 물체 없는 상자가 하나 남으면 그 상자를 **뽑은 패 D** 로 잡는다. `못 정함` 이면 코드는 배정을 안 바꾸고 추적을 그대로 이어 간다.
  - 코드는 배정한 닻에서 **추적을 새로 시작한다**(각 물체를 배정한 상자에 다시 붙임). 그러니 코드 배정이 틀리면 그 뒤 기록의 번호도 그 틀림을 이어받는다.
- **구간** = 닻과 닻 사이(대개 손이 줄을 덮은 동안). 구간 안에서 물체별로 본 것:
  - `들림` = 마스크가 줄에서 패 높이의 0.45배 넘게 벗어난 시각 범위와 방향.
  - `안 보임` = 마스크 넓이가 구간 시작의 30% 밑으로 2장 넘게 이어진 시각 범위(손에 가렸거나 사라짐).
  - `겹침` = 두 물체의 마스크가 한 패 위에 2장 넘게 같이 있던 시각 범위.
  - `경로` = 들린 물체와 뽑은 패 D 의 마스크가 지나간 자리(시각 자리, `앞` · `뒤` = 줄에서 벗어난 쪽).
- 맨 끝 `[코드의 답]` = 위 배정을 이어 코드가 낸 답. 나감이 안 정해졌거나, 뽑은 패를 못 잡았거나, 뽑은 패가 "확신 아님" 이거나, 마지막 닻을 못 정하면 코드는 "못 정함" 으로 둔다.
- 초당 5장.

## 이 추적의 버릇(다른 실행들에서 본 것 — 판단에 쓰라)
- 손에 들려 혼자 움직이는 패는 대체로 따라간다.
- 버린 패의 마스크는 사라지지 않고 **이웃 패나 다른 패에 옮겨 붙는 일이 많다**(겹침 · 엉뚱한 자리의 마스크로 보인다).
- 손이 덮은 동안 줄이 밀리거나 패가 끼워지면, 덮였던 물체의 마스크는 패를 따라가지 않고 **마지막으로 또렷이 보인 자리로 돌아오는 일이 많다.** 그러면 마스크가 상자에 가지런히 앉아 있어도 번호는 어긋나 있고, "마스크 없는 상자" 가 뽑은 패가 아닌 자리에 생긴다.
- 그래서 **한 구간 안에서 나감과 뽑은 패가 같이 정해진 경우**에는 "코드 확신" 이라고 적혀 있어도 뽑은 패 자리를 믿기 어렵다. 줄 상자가 N+1개로 깨끗이 보인 닻에서(아직 아무도 안 나갔을 때) 잡은 뽑은 패는 믿을 만하다.
- 나감(버린 패) 쪽은 뽑은 패 자리보다 잘 맞는 편이지만, 닻 없이 오래 덮인 구간에서는 틀린 적이 있다.

"""


def norm(a):
    if not a or not a.get("kind"):
        return None
    hand = a["kind"] == "hand"
    return {"kind": a["kind"], "k": a.get("k") if hand else None, "j": a.get("j") if hand else None, "unsure": bool(a.get("unsure"))}


def right(a, u) -> bool:
    if not a or a.get("kind") != u["kind"]:
        return False
    return u["kind"] != "hand" or (a.get("k") == u["k_id"] and a.get("j") == u["j_closed"])


def look_text(tid: str) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sg.cmd_look(argparse.Namespace(ids=[tid], raw=False))
    return buf.getvalue()


def spans(flags: list, fr: list, lo: int, need: int = 1) -> list:
    """참인 프레임 묶음 → [(시작 시각, 끝 시각)] (need 장 이상 이어진 것만)."""
    out, st = [], None
    for i, v in enumerate(list(flags) + [False]):
        if v and st is None:
            st = i
        if not v and st is not None:
            if i - st >= need:
                out.append((hc.mss(fr[lo + st]), hc.mss(fr[lo + i - 1])))
            st = None
    return out


def fmt_spans(sp: list) -> str:
    return " · ".join(a if a == b else f"{a}~{b}" for a, b in sp)


SAM_GUIDE3 = SAM_GUIDE + """
## 경로 줄(이 글에 더 들어 있는 것)
- `경로: 물체 2: 27:46.5 2.1 → 27:47.3 0.6(0.1) → [안 보임 …] → 27:48.9 2.0 ⇐다시 나타남(직전 0.4 에서 1.6칸) | 마지막 뜀: 0.4 → 2.0(구간 시작 자리로 돌아옴)` = 그 물체의 마스크가 구간 안에서 지나간 자리. 자리가 0.4칸 넘게 바뀔 때마다 한 점. `(0.1)` = 그때 마스크 넓이가 구간 시작의 몇 배인지(0.75 밑일 때만 — 작으면 손에 많이 가린 것). `앞` · `뒤` = 줄에서 벗어난 쪽.
- `⇐뜀(직전 a 에서 d칸)` = 바로 앞 프레임의 자리 a 에서 한 프레임 만에 d칸(0.7칸 넘게) 옮김. `⇐다시 나타남(직전 a 에서 d칸)` = 안 보이다가, 마지막으로 본 자리 a 에서 d칸 떨어진 곳에 나타남. `마지막 뜀: a → b` = 그 구간의 마지막 뜀 · 다시 나타남의 직전 자리와 뒤 자리. `(구간 시작 자리로 돌아옴)` = b 가 그 물체의 구간 시작 자리와 같음.
- `물체 3 4 5 6: 뜀 없이 다 같이 -1.0칸` = 그 물체들이 끊김 없이 같은 만큼 옮김(줄이 그만큼 밀린 것).
- 경로 줄이 없는 물체는 그 구간에서 제자리(0.4칸 안)에 있었고 뛰지도 않았다.

## 둘째 기록 — 처음 한 번만 붙인 추적
- 차례마다 `-- 둘째 SAM 2 추적` 아래에 같은 영상을 **다르게 따라간 기록**이 하나 더 있다: 차례 시작 줄에서 물체 1 ~ N 을 한 번만 붙이고, 닻에서 다시 붙이지 않고 끝까지 이어 간 것이다(코드 배정 없음 · 뽑은 패 물체 D 없음). 닻 시각은 첫째 기록과 같다.
- 첫째 기록은 닻마다 코드 배정대로 다시 붙이므로 코드 배정이 틀리면 그 뒤가 틀어지고, 둘째 기록은 한 번 어긋난 번호가 끝까지 간다. 같은 구간을 두 기록이 다르게 적었으면 그 구간이 추적하기 어려웠다는 뜻이다. 둘이 같은 이야기를 하면 더 믿을 만하다.

## 경로와 뜀 읽는 법
- 마스크가 **넓이를 유지한 채 조금씩 이어서 옮겨 간 경로**(손에 들려 간 패)는 믿을 만하다 — 그 패가 실제로 그리 간 것이다.
- 뜀이 모두 잘못은 아니다 — 손이 패를 빨리 옮기면 한 프레임에 0.7칸 넘게 갈 수 있다(이때는 대개 넓이가 작거나 줄에서 벗어나 있다). **넓이가 온전한 채 구간 시작 자리로 뛰어 돌아온 것**이 "마스크가 다른 패에 다시 붙음" 의 전형이다. 그때 그 물체의 실제 패는 **그 뜀 직전 자리** 근처에 남아 있을 가능성이 크다.
- 그러니 닻에서 "마스크 없는 상자" 가 어떤 물체의 "구간 시작 자리로 돌아온 뜀" 의 직전 자리 근처에 있으면, 그 상자는 뽑은 패가 아니라 그 물체의 패일 수 있다. 그 경우 뽑은 패는 그 물체의 마스크가 뛰어가 앉은 상자 쪽이다.
- 두 물체가 같은 자리로 같이 이어서 옮겨 갔으면(겹침), 손이 이웃한 두 장을 같이 들었거나 한 장이 다른 장에 가린 것이다 — 둘 다 그쪽으로 갔다고 보는 편이 맞을 때가 많다.
- 넓이가 아주 작은(0.3 밑) 채로 지나간 자리는 근거가 약하다.

"""


def path_lines(R, objs, a0, y0, g0, f1, fr, pos, hh, nm) -> list:
    """움직였거나 뛴 물체의 경로 줄(계획서 추가 27). 넓이 ≥ 0.1 인 프레임만 자리로 치고, 0.7칸 넘는 옮김을 뜀 · 다시 나타남으로 표시."""
    solo, plain = [], {}
    for o in objs:
        if not a0.get(o):
            continue
        toks, last, pv, hid0, first, before, dev, odd = [], None, None, None, None, None, 0.0, False
        for f in range(g0, f1 + 1):
            r = R(f, o)
            if r is None or r[1] is None or r[0] < 0.1 * a0[o]:
                if hid0 is None:
                    hid0 = f
                continue
            x, ar = pos(r[1]), r[0] / a0[o]
            off = "" if y0.get(o) is None or abs(r[2] - y0[o]) <= s2.LIFT_Y * hh else ("앞" if r[2] > y0[o] else "뒤")
            gap = (f - pv[0]) if pv else 1
            d = abs(x - pv[1]) if pv else 0.0
            jump = pv is not None and d >= 0.7
            if first is None:
                first = x
            dev = max(dev, abs(x - first))
            if hid0 is not None and pv is not None and f - hid0 >= 2:
                toks.append(f"[안 보임 {hc.mss(fr[hid0])}~{hc.mss(fr[f - 1])}]")
                odd = True
            if last is None or abs(x - last[0]) >= 0.4 or off != last[1] or jump:
                s = f"{hc.mss(fr[f])} {x:.1f}{off}" + (f"({ar:.1f})" if ar < 0.75 else "")
                if jump:
                    s += f" ⇐{'뜀' if gap == 1 else '다시 나타남'}(직전 {pv[1]:.1f} 에서 {d:.1f}칸)"
                    before = (pv[1], x, ar)
                if off:
                    odd = True
                toks.append(s)
                last = (x, off)
            hid0 = None
            pv = (f, x)
        if pv is None:
            continue
        if hid0 is not None and f1 - hid0 + 1 >= 2:
            toks.append(f"[안 보임 {hc.mss(fr[hid0])}~구간 끝]")
            odd = True
        if before is None and dev < 0.4:
            continue
        if before is None and not odd:
            plain[o] = (round(pv[1] - first, 1), toks)      # 뜀 없이 옮기기만 함 — 같은 만큼 옮긴 것끼리 묶는다
            continue
        if len(toks) > 22:
            toks = toks[:11] + ["…"] + toks[-10:]
        solo.append(f"  경로: 물체 {nm(o)}: " + " → ".join(toks) + ("" if before is None else f" | 마지막 뜀: {before[0]:.1f} → {before[1]:.1f}" + ("(구간 시작 자리로 돌아옴)" if abs(before[1] - first) < 0.4 else "")))
    groups = {}
    for o, (dv, _) in plain.items():
        groups.setdefault(dv, []).append(o)
    out = []
    for dv, os_ in sorted(groups.items()):
        if len(os_) >= 4:
            out.append(f"  경로: 물체 {' '.join(nm(o) for o in os_)}: 뜀 없이 다 같이 {dv:+.1f}칸")
        else:
            out += [f"  경로: 물체 {nm(o)}: " + " → ".join(plain[o][1]) for o in os_]
    return out + solo


def raw_text(tid: str, a) -> str:
    """둘째 기록 = v1 추적(sam2track.py — 처음 한 번만 붙이고 끝까지 이어 감)을 v2 와 같은 닻 시각으로 끊어 적는다."""
    tr = hc.jload(s1.run_dir(tid, a) / "track.json")
    p, fr, rec = tr["plan"], tr["frames"], tr["rec"]
    n, hh = p["n"], p["hh"]
    left0 = p["a_boxes"][0][0]
    P = (p["a_boxes"][-1][2] - left0) / n
    pos = lambda x: (x - left0) / P + 0.5  # noqa: E731
    R = lambda f, o: rec[str(f)].get(str(o))  # noqa: E731
    objs = list(range(1, n + 1))
    a0 = {o: R(0, o)[0] for o in objs}
    an = s2.anchors(p, fr)
    L = [f"-- 둘째 SAM 2 추적(처음 한 번만 붙임 · 닻에서 다시 안 붙임 · 코드 배정 없음 · D 없음) · 물체 1 ~ {n} = 차례 시작 줄의 왼쪽부터"]
    for i in range(1, len(an)):
        g0, f1 = an[i - 1]["fi"], an[i]["fi"]
        y0 = {o: (R(g0, o)[2] if R(g0, o)[2] is not None else R(0, o)[2]) for o in objs}
        ev = path_lines(R, objs, a0, y0, g0, f1, fr, pos, hh, str)
        L.append(f"[구간 {hc.mss(fr[g0])} ~ {hc.mss(fr[f1])}]" + ("" if ev else " 움직이거나 뛴 물체 없음"))
        L += ev
        bs = an[i]["boxes"]
        bx = [pos((b[0] + b[2]) / 2) for b in bs]
        by = [(b[1] + b[3]) / 2 for b in bs]
        seat, items = {}, []
        for o in objs:
            r = R(f1, o)
            if r is None or r[1] is None or r[0] < 0.3 * a0[o]:
                items.append(f"{o}@안 보임")
                continue
            x = pos(r[1])
            q = int(np.argmin([abs(x - v) for v in bx]))
            off = "" if abs(r[2] - by[q]) <= 0.5 * hh else ("(앞)" if r[2] > by[q] else "(뒤)")
            items.append(f"{o}@{x:.1f}{off}")
            if abs(x - bx[q]) <= 0.5 and not off:
                seat.setdefault(q, []).append(o)
        emp = [f"{bx[q]:.1f}" for q in range(len(bs)) if q not in seat]
        dup = [f"{bx[q]:.1f}에 " + "·".join(str(o) for o in v) for q, v in sorted(seat.items()) if len(v) > 1]
        L.append(f"[닻 {hc.mss(fr[f1])}] 줄 상자 {len(bs)}개 — 마스크: " + " ".join(items))
        L.append("  마스크 없는 상자: " + (" ".join(emp) if emp else "없음") + (" | 한 상자에 둘: " + ", ".join(dup) if dup else ""))
    return "\n".join(L) + "\n"


def sam_text(tid: str, a, rich: bool = False) -> str:
    d = s2.run_dir(tid, a)
    tr = hc.jload(d / "track.json")
    p, fr, rec, log = tr["plan"], tr["frames"], tr["rec"], tr["anchors"]
    n, hh = p["n"], p["hh"]
    NEW = n + 1
    left0 = p["a_boxes"][0][0]
    P = (p["a_boxes"][-1][2] - left0) / n
    pos = lambda x: (x - left0) / P + 0.5  # noqa: E731
    nm = lambda o: "D" if o == NEW else str(o)  # noqa: E731
    boxes = {x["fi"]: x["boxes"] for x in s2.anchors(p, fr)}
    R = lambda f, o: rec[str(f)].get(str(o))  # noqa: E731
    L = [f"-- SAM 2 추적 기록 · 물체 1 ~ {n} = 차례 시작 줄의 왼쪽부터 · D = 코드가 뽑은 패로 잡은 물체(잡은 뒤에만 나옴)",
         f"[닻 {hc.mss(fr[0])}] 시작 줄: 줄 상자 {n}개 — 자리 " + " ".join(f"{pos((b[0] + b[2]) / 2):.1f}" for b in p["a_boxes"]) + f" · 물체 1 ~ {n} 을 이 상자들에 붙임"]
    for i in range(1, len(log)):
        e, prev = log[i], log[i - 1]
        f0, f1 = e["seg_start"], e["fi"]            # 통계는 마지막으로 배정한 닻부터(코드와 같은 구간)
        g0 = prev["fi"]                             # 글로 적는 구간은 바로 앞 닻부터
        objs = [int(o) for o in rec[str(f0)]]
        a0 = {o: R(f0, o)[0] for o in objs}
        y0 = {o: R(f0, o)[2] for o in objs}
        ev = []
        lifted_any = []
        for o in objs:
            rows = [R(f, o) for f in range(g0, f1 + 1)]
            lift = [r is not None and r[2] is not None and a0[o] > 0 and r[0] >= s2.LIFT_A * a0[o] and abs(r[2] - y0[o]) > s2.LIFT_Y * hh for r in rows]
            if any(lift):
                lifted_any.append(o)
                side = "앞" if np.mean([r[2] - y0[o] for r, v in zip(rows, lift) if v]) > 0 else "뒤"
                mx = max(abs(r[2] - y0[o]) for r, v in zip(rows, lift) if v) / hh
                ev.append(f"  들림: 물체 {nm(o)} {fmt_spans(spans(lift, fr, g0))} ({side}쪽으로 패 높이의 {mx:.1f}배까지)")
        hid = []
        for o in objs:
            rows = [R(f, o) for f in range(g0, f1 + 1)]
            h = [r is None or a0[o] == 0 or r[0] < 0.3 * a0[o] for r in rows]
            sp = spans(h, fr, g0, need=2)
            if sp:
                hid.append(f"{nm(o)} {fmt_spans(sp)}")
        if hid:
            ev.append("  안 보임: 물체 " + " / ".join(hid))
        co = []
        for i1, o1 in enumerate(objs):
            for o2 in objs[i1 + 1:]:
                fl = []
                for f in range(g0, f1 + 1):
                    A, B = R(f, o1), R(f, o2)
                    fl.append(bool(A and B and A[1] is not None and B[1] is not None and A[0] >= s2.CO_A * a0[o1] and B[0] >= s2.CO_A * a0[o2]
                                   and abs(A[1] - B[1]) <= s2.CO_X * P and abs(A[2] - B[2]) <= s2.CO_Y * hh))
                sp = spans(fl, fr, g0, need=2)
                if sp:
                    co.append(f"{nm(o1)}+{nm(o2)} {fmt_spans(sp)}")
        if co:
            ev.append("  겹침: " + " / ".join(co))
        if rich:
            ev += path_lines(R, objs, a0, y0, g0, f1, fr, pos, hh, nm)
        for o in ([] if rich else sorted(set(lifted_any) | ({NEW} if NEW in objs else set()))):
            pts, last = [], None
            for f in range(g0, f1 + 1):
                r = R(f, o)
                if r is None or r[1] is None or r[0] < 0.3 * a0[o]:
                    continue
                off = "" if abs(r[2] - y0[o]) <= s2.LIFT_Y * hh else ("앞" if r[2] > y0[o] else "뒤")
                cur = (round(pos(r[1]), 1), off)
                if last is None or abs(cur[0] - last[0]) >= 0.4 or cur[1] != last[1]:
                    pts.append(f"{hc.mss(fr[f])} {cur[0]:.1f}{off}")
                    last = cur
            if len(pts) > 16:
                pts = pts[:8] + ["…"] + pts[-7:]
            if len(pts) > 1:
                ev.append(f"  경로: 물체 {nm(o)} " + " → ".join(pts))
        L.append(f"[구간 {hc.mss(fr[g0])} ~ {hc.mss(fr[f1])}]" + ("" if ev else " 들림 · 안 보임 · 겹침 없음"))
        L += ev
        bs = boxes[f1]
        bx = [pos((b[0] + b[2]) / 2) for b in bs]
        by = [(b[1] + b[3]) / 2 for b in bs]
        fq = f1 if i == len(log) - 1 else max(f1 - 1, f0)
        seat, items = {}, []
        for o in objs:
            r = R(fq, o)
            if r is None or r[1] is None or a0[o] == 0 or r[0] < 0.3 * a0[o]:
                items.append(f"{nm(o)}@안 보임")
                continue
            x = pos(r[1])
            q = int(np.argmin([abs(x - v) for v in bx]))
            off = "" if abs(r[2] - by[q]) <= 0.5 * hh else ("(앞)" if r[2] > by[q] else "(뒤)")
            items.append(f"{nm(o)}@{x:.1f}{off}")
            if abs(x - bx[q]) <= 0.5 and not off:
                seat.setdefault(q, []).append(o)
        L.append(f"[닻 {hc.mss(fr[f1])}] 줄 상자 {len(bs)}개 — 자리 " + " ".join(f"{v:.1f}" for v in bx))
        L.append("  닻 직전 마스크: " + " ".join(items))
        emp = [f"{bx[q]:.1f}" for q in range(len(bs)) if q not in seat]
        dup = [f"{bx[q]:.1f}에 " + "·".join(nm(o) for o in v) for q, v in sorted(seat.items()) if len(v) > 1]
        L.append("  마스크 없는 상자: " + (" ".join(emp) if emp else "없음") + (" | 한 상자에 둘: " + ", ".join(dup) if dup else ""))
        if e["valid"]:
            s = []
            if e.get("gone") is not None:
                s.append(f"나감 = 물체 {nm(e['gone'])}")
            if e.get("new_box") is not None:
                s.append(f"뽑은 패 D = 자리 {bx[e['new_box']]:.1f} 의 상자(코드 {'확신' if e.get('conf') else '확신 아님'})")
            if e.get("lifted"):
                s.append("들린 것으로 본 물체 " + " ".join(nm(o) for o in e["lifted"]))
            if e.get("n_fix"):
                s.append(f"마스크와 다른 상자에 앉힌 물체 {e['n_fix']}개")
            s.append("배정 뒤 왼쪽부터 " + " ".join(nm(o) for o in e["order"]))
            L.append("  코드 배정: " + " · ".join(s))
        else:
            why = e["why"]
            for o in sorted(set(objs), reverse=True):   # 까닭 글 안의 물체 번호 N+1 → D
                if o == NEW:
                    why = why.replace(str(NEW), "D")
            L.append(f"  코드 배정: 못 정함 — {why} (배정을 안 바꾸고 추적을 이어 감)")
    r = tr["result"]
    if r["removed"] is not None and r["has_new"] and r["new_conf"] and r["final_ok"]:
        L.append("[코드의 답] " + ("kind tsumogiri" if r["removed"] == NEW else f"kind hand · k {r['k']} · j {r['j']}"))
    else:
        why = "나감을 못 정함" if r["removed"] is None else "뽑은 패를 못 잡음" if not r["has_new"] else "뽑은 패가 확신 아님" if not r["new_conf"] else "마지막 닻을 못 정함"
        part = [f"나감 = 물체 {nm(r['removed'])}"] if r["removed"] is not None else []
        if r["has_new"] and r["final_ok"]:
            part.append(f"뽑은 패 D 는 끝 줄의 {r['end_order'].index(NEW) + 1}번째(확신 {'있음' if r['new_conf'] else '아님'})")
        L.append(f"[코드의 답] 못 정함 — {why}" + (" · 참고: " + " · ".join(part) if part else ""))
    return "\n".join(L) + "\n"


def blocks(a) -> dict:
    """팔 → (안내문, {차례: 글})."""
    look = {t: look_text(t) for t in IDS}
    sam = {t: sam_text(t, a) for t in IDS}
    return {"L": (gd.COMMON + gd.LOOK, look),
            "S": (gd.COMMON + SAM_GUIDE, {t: look[t].split("\n", 1)[0] + "\n" + sam[t] for t in IDS}),
            "LS": (gd.COMMON + gd.LOOK + SAM_GUIDE, {t: look[t] + sam[t] for t in IDS}),
            **rich_blocks(a, look)}


def rich_blocks(a, look: dict) -> dict:
    """경로 · 뜀 · 둘째 기록(v1 추적)을 넣은 글(계획서 추가 27)."""
    sam3 = {t: sam_text(t, a, rich=True) + raw_text(t, a) for t in IDS}
    return {"S3": (gd.COMMON + SAM_GUIDE3, {t: look[t].split("\n", 1)[0] + "\n" + sam3[t] for t in IDS}),
            "LS3": (gd.COMMON + gd.LOOK + SAM_GUIDE3, {t: look[t] + sam3[t] for t in IDS})}


def cmd_make(a):
    OUT.mkdir(parents=True, exist_ok=True)
    for k, (guide, body) in blocks(a).items():
        v = guide + "# 차례들\n\n" + "\n".join(body[t] for t in IDS)
        with open(OUT / f"blind_{k}.txt", "w", encoding="utf-8", newline="\n") as f:
            f.write(v)
        print(f"blind_{k}.txt: {len(v):,}자 · 차례 {len(IDS)}")


GEM_MODEL = "gemini-3.8-flash"
GEM_SCHEMA = {"type": "OBJECT", "properties": {
    "steps": {"type": "STRING"}, "kind": {"type": "STRING", "enum": ["tsumogiri", "hand"]},
    "k": {"type": "INTEGER", "nullable": True}, "j": {"type": "INTEGER", "nullable": True},
    "unsure": {"type": "BOOLEAN"}, "why": {"type": "STRING"}}, "required": ["steps", "kind", "k", "j", "unsure", "why"]}
GEM_TAIL = """
## 답하는 법
- 아래 차례 **하나**에 답한다. 주어진 것은 이 글뿐이다(그림 · 다른 자료 없음).
- steps 에 따져 본 과정을 먼저 적고(시각 순으로 무슨 일이 있었다고 보는지), 그다음 kind · k · j · unsure · why 를 채운다.
- 모르겠으면 가장 그럴듯한 답을 내고 unsure 를 true 로 둔다.

# 차례

"""


def gem_prompt(guide: str, body: str) -> str:
    """에이전트용 '지킬 것'(파일 하나만 읽기 · 답 파일 쓰기) 절을 빼고 차례 하나짜리 요청으로."""
    head, rest = guide.split("## 지킬 것", 1)
    after = rest.split("\n## ", 1)
    more = ("\n## " + after[1]) if len(after) > 1 else ""
    return head.rstrip() + "\n" + more + GEM_TAIL + body


def cmd_gem(a):
    import json
    import time
    from concurrent.futures import ThreadPoolExecutor

    import gemframes as gf
    from google.genai import types
    bl = blocks(a)
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=GEM_SCHEMA)

    def one(job):
        arm, tid = job
        text = gem_prompt(bl[arm][0], bl[arm][1][tid])
        t0, err = time.perf_counter(), ""
        for attempt in range(3):
            try:
                c = gf.client()     # 변수에 잡아 둔다 — 바로 이어 부르면 요청 전에 클라이언트가 닫힌다("client has been closed")
                r = c.models.generate_content(model=a.gmodel, contents=[text], config=cfg)
                um = r.usage_metadata
                d = json.loads(r.text)
                return {"id": tid, "kind": d.get("kind"), "k": d.get("k"), "j": d.get("j"), "unsure": d.get("unsure"), "why": d.get("why"), "steps": d.get("steps"),
                        "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                        "think": getattr(um, "thoughts_token_count", 0) or 0, "model_version": getattr(r, "model_version", None), "attempt": attempt + 1}
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(8 * (attempt + 1))
        return {"id": tid, "kind": None, "k": None, "j": None, "unsure": True, "error": err, "s": round(time.perf_counter() - t0, 1), "in": 0, "out": 0, "think": 0}

    if a.dry:
        for arm in a.arms.split(','):
            print(arm, [len(gem_prompt(bl[arm][0], bl[arm][1][t])) for t in IDS])
        return
    todo = [(arm, rep) for rep in (1, 2) for arm in a.arms.split(",") if a.force or not (OUT / f"read_gem_{arm}_r{rep}.json").exists()]
    for arm, rep in todo:
        with ThreadPoolExecutor(a.workers) as ex:
            rows = list(ex.map(one, [(arm, t) for t in IDS]))
        hc.jsave(OUT / f"read_gem_{arm}_r{rep}.json", {"reader": f"gem_{arm}_r{rep}", "model": a.gmodel, "at": hc.hms(int(time.time() * 1000), date=True), "rows": rows})
        print(f"gem {arm} r{rep}: " + " ".join(f"{r['id'][:3]}{r['id'][-2:]}={r['k']}·{r['j']}{'?' if r.get('unsure') else ''}{'!' if r.get('error') else ''}" for r in rows)
              + f" | 입력 {sum(r['in'] for r in rows):,} · 출력 {sum(r['out'] for r in rows):,} · 생각 {sum(r['think'] for r in rows):,}", flush=True)


def cmd_score(a):
    truth = s1.truth_all()
    old = {}
    for name in ("read_look.json", "read_r13_look.json"):
        f = sg.OUT / name
        if f.exists():
            old.update({r["id"]: r for r in hc.jload(f)["rows"]})
    code = {r["id"]: r for r in hc.jload(s2.OUT / "score_t_xpu.json")} if (s2.OUT / "score_t_xpu.json").exists() else {}
    pre = "" if a.reader == "agent" else f"{a.reader}_"
    reads = {}
    usage = {"in": 0, "out": 0, "think": 0}
    for arm in ALL_ARMS:
        for rep in (1, 2):
            f = OUT / f"read_{pre}{arm}_r{rep}.json"
            if f.exists():
                reads[(arm, rep)] = {r["id"]: r for r in hc.jload(f)["rows"]}
                for r in reads[(arm, rep)].values():
                    for u in usage:
                        usage[u] += r.get(u, 0) or 0
    show = lambda v: "-" if v is None else (f"{v['k']}·{v['j']}" if v["kind"] == "hand" else "쯔모")  # noqa: E731
    tot = {k: {"T": 0, "sure_T": 0, "quiet": 0, "unsure": 0, "n": 0} for k in reads}
    out = []
    for tid in IDS:
        u = truth[tid]
        cells = []
        for k, rows in reads.items():
            r = norm(rows.get(tid))
            ok = right(r, u)
            un = bool((rows.get(tid) or {}).get("unsure"))
            t = tot[k]
            t["n"] += 1
            t["T"] += ok
            t["sure_T"] += ok and not un
            t["quiet"] += (not ok) and not un
            t["unsure"] += un
            cells.append(f"{k[0]}{k[1]} {show(r)}{'?' if un else ''}{'✓' if ok else '✗'}")
        o = norm(old.get(tid))
        c = code.get(tid, {})
        line = f"{tid:8s} 정답 {u['k_id']}·{u['j_closed']} | " + " | ".join(cells) + f" || 옛 줄글 {show(o)}{'✓' if right(o, u) else '✗'} · SAM 코드 {c.get('k')}·{c.get('j')} {c.get('verdict', '')}"
        print(line)
        out.append(line)
    for k, t in tot.items():
        print(f"{k[0]} r{k[1]}: 맞음 {t['T']}/{t['n']} (unsure 아닌 맞음 {t['sure_T']}) · unsure {t['unsure']} · 조용한 틀림 {t['quiet']}")
    for arm in ALL_ARMS:
        ks = [k for k in tot if k[0] == arm]
        if ks:
            print(f"{arm} 합: 맞음 {sum(tot[k]['T'] for k in ks)}/{sum(tot[k]['n'] for k in ks)} · unsure 아닌 맞음 {sum(tot[k]['sure_T'] for k in ks)} · unsure {sum(tot[k]['unsure'] for k in ks)} · 조용한 틀림 {sum(tot[k]['quiet'] for k in ks)}")
    if usage["in"]:
        usd = usage["in"] * 0.75e-6 + (usage["out"] + usage["think"]) * 3.75e-6
        print(f"토큰: 입력 {usage['in']:,} · 출력 {usage['out']:,} · 생각 {usage['think']:,} → 약 {usd:.2f}달러(입력 0.75 · 출력 3.75 / 100만)")
    hc.jsave(OUT / ("score.json" if a.reader == "agent" else f"score_{a.reader}.json"), {"usage": usage, "tot": {f"{k[0]}_r{k[1]}": v for k, v in tot.items()}, "lines": out})


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("make")
    m.add_argument("--model", default="t")
    m.add_argument("--device", default="xpu")
    sc = sp.add_parser("score")
    sc.add_argument("--reader", default="agent", help="agent(하위 에이전트 답 read_<팔>_r<회>) | gem(read_gem_<팔>_r<회>)")
    g = sp.add_parser("gem")
    g.add_argument("--model", default="t")
    g.add_argument("--device", default="xpu")
    g.add_argument("--gmodel", default=GEM_MODEL)
    g.add_argument("--workers", type=int, default=4)
    g.add_argument("--dry", action="store_true")
    g.add_argument("--force", action="store_true")
    g.add_argument("--arms", default=",".join(ARMS))
    a = ap.parse_args()
    {"make": cmd_make, "score": cmd_score, "gem": cmd_gem}[a.cmd](a)


if __name__ == "__main__":
    main()
