"""개발 세트 로그에 구조 검사 후보를 적용해 막히는 횟수를 센다(서버 호출 없음).
R1 표시패 0장 / R2 리치 화료인데 표시패 2장 미만(뒷도라) / R3 리치 아닌데 표시패 > 1 + 깡 수."""
import json
import re
import sys
from collections import Counter

TRUTH = {"B": "12000", "C": "16000", "D": "18000"}
cnt, total, okc = Counter(), 0, 0
for path in sys.argv[1:]:
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.search(r"TIMING (\{.*\})", line)
        if not m:
            continue
        r = json.loads(m.group(1))
        total += 1
        mg = r.get("merge") or {}
        n = len(mg.get("dora_indicators") or [])
        kans = sum(1 for x in mg.get("melds") or [] if len(x.replace("[", "").replace("]", "").replace("(", "").replace(")", "").split()) == 4)
        riichi = bool(mg.get("riichi"))
        hits = [k for k, v in (("R1", n == 0), ("R2", riichi and n < 2), ("R3", not riichi and n > 1 + kans)) if v]
        for h in hits:
            cnt[(h, r["scene"])] += 1
        ok = r.get("points") == TRUTH.get(r["scene"])
        okc += ok
print("runs", total, "correct", okc, dict(sorted(cnt.items())))
