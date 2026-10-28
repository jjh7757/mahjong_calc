"""개발 세트 TIMING 로그 → 리치봉 자리별 conf, 도라 표시패 conf·장수, 화료자 손패의 5 패 conf 분포."""
import json
import re
import sys
from collections import Counter

TRUTH = {"B": "12000", "C": "16000", "D": "18000"}
stick, dora, fives, ndora, rows = [], [], [], Counter(), 0
for path in sys.argv[1:]:
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.search(r"TIMING (\{.*\})", line)
        if not m:
            continue
        r = json.loads(m.group(1))
        rows += 1
        ok = r.get("points") == TRUTH.get(r["scene"])
        c = r.get("center_read") or {}
        mg = r.get("merge") or {}
        stick += [(r["photo"], s, c.get("riichi", {}).get(s), v, ok) for s, v in (c.get("riichi_conf") or {}).items()]
        inds = (c.get("hand_side_indicators") if mg.get("riichi") and c.get("hand_side_indicators") else
                (c.get("dora_indicators") or []) + (c.get("ura_dora_indicators") or [])) or c.get("hand_side_indicators") or []
        ndora[(r["scene"], len(inds), mg.get("riichi"))] += 1
        dora += [(r["photo"], t["tile"], t["conf"], ok) for t in inds]
        h = r.get("hand_read") or {}
        tiles = (h.get("tiles") or []) + ([h["win_tile"]] if h.get("win_tile") else [])
        fives += [(r["photo"], t["tile"], t["conf"], ok) for t in tiles if t["tile"][0] in "05" and t["tile"][1] in "mps"]

print("runs", rows)
def hist(vals):
    return dict(sorted(Counter(round(v, 2) for v in vals).items()))
print("리치봉 conf(있음):", hist([v for *_, p, v, ok in stick if p]))
print("리치봉 conf(없음):", hist([v for *_, p, v, ok in stick if not p]))
print("도라 표시패 conf:", hist([v for _, _, v, _ in dora]))
print("도라 장수 (장면, 장수, 리치):", dict(ndora))
print("5 패 conf:", hist([v for _, _, v, _ in fives]), "패:", Counter(t for _, t, _, _ in fives))
