"""사용자 규칙(2026-11-01): 손패 근처 탁자 위 표시패는 리치 화료의 도라 + 뒷도라라 2장 이상 → 펠트 위 외톨이 낱장 = 떼어 둔 패.
wide_pieces.json 의 저장된 답(같은 순간)에 규칙을 적용해 다시 채점한다. API 호출 없음, 낱장 자리만 YOLO 로 다시 잡는다.

  운영 답이 13장 + 검사 통과이고 외톨이가 하나이며 더해 화료형이면 → 그 패를 떼어 둔 패로 더한다.
  운영 답이 검사 실패면 → 조각 읽기 답. 줄 + 울기 + 외톨이로 13·14 가 검사를 통과하면 그것, 아니면 wide_pieces.assemble 결과.

  python -X utf8 experiments/speed/wide_lone.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wide_pieces as wp  # noqa: E402
from wide_pieces import rv, sg, st, vc  # noqa: E402


def lone_flags(rgb, loc) -> list[bool]:
    """낱장마다 외톨이인가: 다른 낱장과 패 0.45개 안에 안 붙고, 좌우가 펠트(왕패 위 표시패는 옆이 패산이라 아님)."""
    tw, th = loc["tw"], loc["th"]
    groups = st.cluster(loc["singles"], tw * 0.45, th * 0.5)
    alone = {g[0] for g in groups if len(g) == 1}
    felt = st.felt_mask(rgb)
    out = []
    for x in loc["singles"]:
        ok = x in alone
        if ok:
            w = max(4, int(tw * 0.4))
            y0, y1 = x[1], x[1] + x[3]
            left = felt[y0:y1, max(0, x[0] - w):x[0]]
            right = felt[y0:y1, x[0] + x[2]:x[0] + x[2] + w]
            ok = left.size > 0 and right.size > 0 and left.mean() > 0.5 and right.mean() > 0.5
        out.append(ok)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads(wp.OUT.read_text(encoding="utf-8"))
    scenes = {s["name"]: s for s in sg.scenes()}
    locs = {}
    tally = {}
    for r in rows:
        s = scenes[r["name"]]
        if r["name"] not in locs:
            rgb = wp.half_rgb(s)
            loc = wp.locate(rgb)
            locs[r["name"]] = (loc, lone_flags(rgb, loc) if loc else [])
        loc, flags = locs[r["name"]]
        seat, pc = r["seat"], r["pieces"]
        melds_key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
        truth = sorted(s["hand"]), melds_key(s["melds"])
        nr = len(pc.get("row") or [])
        n_box = len(loc["singles"]) if loc else 0
        read = (pc.get("singles") or [])[:n_box]
        lone = [t for t, f in zip(read, flags) if f and t]

        ts = seat.get("hand", []) + seat.get("sep", [])
        n = len(ts) + 3 * len(seat.get("melds", []))
        valid = (n == 14 and vc.is_win(ts)) or (n == 13 and bool(vc.waits(ts)))
        if valid:
            ans = (ts, seat["melds"])
            src = "seat"
            if n == 13 and len(lone) == 1 and vc.is_win(ts + lone):
                ans = (ts + lone, seat["melds"])
                src = "seat+외톨이"
        elif pc.get("row") and all(pc["row"]):
            melds = pc["melds"]
            hand = pc["row"] + lone
            m = 3 * len(melds)
            if (len(hand) + m == 14 and vc.is_win(hand)) or (len(hand) + m == 13 and vc.waits(hand)):
                ans, src = (hand, melds), "pieces+외톨이"
            elif pc.get("decided"):
                ans, src = (pc["row"] + pc["sep"], melds), "pieces"
            else:
                ans, src = None, "없음"
        else:
            ans, src = None, "없음"
        part = "BCD" if r["set"] == "bcd" else "오전" if r["name"] < "20261031_14" else "오후"
        t = tally.setdefault(part, Counter())
        t["n"] += 1
        if ans is None:
            t["none"] += 1
            verdict = "답 없음"
        else:
            good = sorted(ans[0]) == truth[0] and melds_key(ans[1]) == truth[1]
            t["ok" if good else "wrong"] += 1
            verdict = "맞음" if good else f"틀림 {' '.join(ans[0])} {ans[1]}"
        print(r["name"][-6:], src, "외톨이", lone, verdict)
    print()
    for part, t in tally.items():
        print(part, f"정답 {t['ok']}/{t['n']} 틀린 답 {t['wrong']} 답 없음 {t['none']}")


if __name__ == "__main__":
    main()
