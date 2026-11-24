"""복기 대화 평가용: 장면마다 '그 사람이 그 순간 볼 수 있던 공개 탁자' 를 글로 만든다(11-24).

입력: experiments/paifu_review/table_scenes_1124.json (game · wind · step · why) + assets/paifu*/<game>.json 패보.
출력: experiments/paifu_review/table_scene_texts_1124.json  {"sc01": "…", …}

- 장면 걸음 step = 패보 events 의 0부터 인덱스 + 1. 그 사건은 장면 자리의 버림이다.
- 걸음 직전까지 네 자리 강(버린 순서, 리치 선언패 표시, 울려 간 패는 강에서 빼고 울기 묶음으로),
  울기 묶음, 도라 표시패, 리치한 자리 · 선언패 · 리치 뒤 버려진 패, 이번에 버린 패(방총이면 론 맞음).
- 손패는 넣지 않는다(장면 자리의 손패도). 탁자 사실표 · 엔진 값은 쓰지 않는다. 표준 라이브러리만.

쓰기: python experiments/paifu_review/agent_defense/table_scene_text.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCENES = ROOT / "experiments/paifu_review/table_scenes_1124.json"
OUT = ROOT / "experiments/paifu_review/table_scene_texts_1124.json"

WINDS = "동남서북"
HONOR = {"1z": "동", "2z": "남", "3z": "서", "4z": "북", "5z": "백", "6z": "발", "7z": "중"}


def load_game(game: str) -> dict:
    for sub in ("assets/paifu", "assets/paifu_h3"):
        p = ROOT / sub / f"{game}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(game)


def name(t: str) -> str:
    if t in HONOR:
        return f"{t}({HONOR[t]})"
    if t[0] == "0":
        return f"{t}(적5)"
    return t


def dora_of(ind: str) -> str:
    n, s = ind[0], ind[1]
    n = 5 if n == "0" else int(n)
    if s == "z":
        if n <= 4:
            return f"{n % 4 + 1}z"
        return f"{(n - 5 + 1) % 3 + 5}z"
    return f"{n % 9 + 1}{s}"


def wind_of(seat: int, dealer: int) -> str:
    return WINDS[(seat - dealer) % 4]


def build(sc: dict) -> str:
    g = load_game(sc["game"])
    ev = g["events"]
    dealer = g["dealer"]
    k = sc["step"] - 1
    cur = ev[k]
    assert cur["type"] == "discard", (sc, cur)
    seat = cur["seat"]
    assert wind_of(seat, dealer) == sc["wind"], (sc, seat, dealer)

    rivers: list[list[dict]] = [[] for _ in range(4)]  # {"tile", "riichi", "taken_by"}
    melds: list[list[dict]] = [[] for _ in range(4)]
    riichi: dict[int, dict] = {}  # seat -> {"tile", "after": [(seat, tile)]}
    last_discard_seat = None
    for e in ev[:k]:
        t = e["type"]
        if t == "discard":
            s = e["seat"]
            rivers[s].append({"tile": e["tile"], "riichi": bool(e.get("riichi")), "taken_by": None})
            for rs, info in riichi.items():
                info["after"].append((s, e["tile"]))
            if e.get("riichi"):
                riichi[s] = {"tile": e["tile"], "after": []}
            last_discard_seat = s
        elif t == "call":
            s, kind = e["seat"], e["kind"]
            if kind == "kakan":
                for m in melds[s]:
                    if m["kind"] == "pon" and m["tiles"][0][1] == e["tiles"][0][1] and m["tiles"][0][0] == e["tiles"][0][0]:
                        m["kind"] = "kakan"
                        m["tiles"] = list(e["tiles"])
                        break
                else:
                    melds[s].append({"kind": kind, "tiles": list(e["tiles"]), "from": None, "taken": None})
                continue
            frm = e.get("from")
            taken = None
            if frm is not None and frm != s and rivers[frm]:
                rivers[frm][-1]["taken_by"] = s
                taken = rivers[frm][-1]["tile"]
            melds[s].append({"kind": kind, "tiles": list(e["tiles"]), "from": frm, "taken": taken})

    kind_ko = {"pon": "퐁", "chi": "치", "kan": "깡", "kakan": "가깡", "ankan": "안깡", "call": "울기"}
    lines = []
    lines.append(f"[{g.get('title', g['id'])} · {g['round']} {g.get('honba', 0)}본장 · 패보 {g['id']} · {sc['step']}번째 걸음]")
    lines.append(f"나: {sc['wind']}가(자리 {seat}). 친은 동(자리 {dealer}).")
    inds = g.get("dora_indicators") or []
    if inds:
        lines.append("도라 표시패: " + ", ".join(f"{name(i)} → 도라 {name(dora_of(i))}" for i in inds) + " (2장째부터는 깡 · 뒷도라일 수 있음 — 패보 기록 그대로)")
    else:
        lines.append("도라 표시패: 기록 없음")
    lines.append("강(버린 순서, [리치]=리치 선언패, (→X 울림)=X 자리가 가져가 강에 없음):")
    order = [(dealer + i) % 4 for i in range(4)]
    for s in order:
        items = []
        for r in rivers[s]:
            txt = name(r["tile"])
            if r["riichi"]:
                txt = "[리치]" + txt
            if r["taken_by"] is not None:
                txt += f"(→{wind_of(r['taken_by'], dealer)} 울림)"
            items.append(txt)
        tag = " ← 나" if s == seat else ""
        lines.append(f"  {wind_of(s, dealer)}(자리 {s}){tag}: " + (" ".join(items) if items else "(없음)"))
    ml = []
    for s in order:
        for m in melds[s]:
            src = f", {wind_of(m['from'], dealer)}에게서 {name(m['taken'])}" if m.get("taken") else ""
            ml.append(f"{wind_of(s, dealer)} {kind_ko.get(m['kind'], m['kind'])} [{' '.join(name(x) for x in m['tiles'])}]{src}")
    lines.append("울기: " + ("; ".join(ml) if ml else "없음"))
    if riichi:
        for rs, info in riichi.items():
            aft = " ".join(f"{wind_of(s2, dealer)}:{name(t2)}" for s2, t2 in info["after"])
            lines.append(f"리치: {wind_of(rs, dealer)}(자리 {rs}) — 선언패 {name(info['tile'])}. 리치 뒤 버려진 패(론 없이 지나감): " + (aft if aft else "없음"))
    else:
        lines.append("리치: 아무도 안 함")
    res = g.get("result") or {}
    now = f"이번에 내가 버린 패: {name(cur['tile'])}"
    if cur.get("riichi"):
        now += " (리치 선언)"
    if sc.get("why") == "deal_in" and res.get("type") == "ron" and res.get("loser") == seat:
        w = res["winner"]
        now += f" → {wind_of(w, dealer)}(자리 {w})에게 론을 맞음(방총)"
        if (res.get("flags") or {}).get("riichi") or w in riichi:
            now += ", 리치 화료"
        elif w not in riichi:
            now += ", 리치 없는 화료(다마 또는 울기)"
    lines.append(now + ".")
    return "\n".join(lines)


def main() -> int:
    scenes = json.loads(SCENES.read_text(encoding="utf-8"))["scenes"]
    out = {sc["id"]: build(sc) for sc in scenes}
    OUT.write_bytes((json.dumps(out, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    if "--print" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        for k, v in out.items():
            print(f"== {k}\n{v}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
