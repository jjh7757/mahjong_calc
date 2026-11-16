"""저장된 Gemini 답(gemframes answers/)에서 확신도 · 세 번 일치 · 두 모델 일치가 정답 여부를 알려 주나(2026-11-16 밤, 새 호출 없음).
  python -X utf8 gemagree.py
"""
import sys, json, glob
from collections import Counter
sys.path.insert(0, ".")
import gemframes as g
truth = {t["id"]: t["j"] for t in g.turns()}
ids = list(truth)
A = {}
for f in sorted(glob.glob(str(g.OUT / "answers" / "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    A[(d["model"], d["arm"], d["rep"])] = {r["id"]: r for r in d["rows"]}
print("정답", truth)
# 1) 자기 확신
c = Counter()
for k, rows in A.items():
    for i in ids:
        r = rows[i]
        c[(r.get("confidence"), r["j"] == truth[i])] += 1
print("확신도별(답 72개):", {str(k): v for k, v in sorted(c.items(), key=str)})
# 2) flash 세 번 일치
for arm in "AB":
    un = Counter()
    for i in ids:
        js = [A[("gemini-3.8-flash", arm, r)][i]["j"] for r in (1, 2, 3)]
        same = len(set(js)) == 1
        maj = Counter(js).most_common(1)[0][0]
        un[("세 번 같음" if same else "갈림", maj == truth[i])] += 1
    print("flash", arm, dict(un))
# 3) flash 다수결 vs pro
for arm in "AB":
    x = Counter()
    for i in ids:
        js = [A[("gemini-3.8-flash", arm, r)][i]["j"] for r in (1, 2, 3)]
        maj = Counter(js).most_common(1)[0][0]
        p = A[("gemini-pro-latest", arm, 1)][i]["j"]
        x[("두 모델 같음" if maj == p else "다름", maj == truth[i], p == truth[i])] += 1
    print("flash 다수결 vs pro", arm, {str(k): v for k, v in x.items()})
# 4) 조건 A 와 B (같은 모델, 다른 재료) 일치
x = Counter()
for i in ids:
    a = Counter(A[("gemini-3.8-flash", "A", r)][i]["j"] for r in (1, 2, 3)).most_common(1)[0][0]
    b = Counter(A[("gemini-3.8-flash", "B", r)][i]["j"] for r in (1, 2, 3)).most_common(1)[0][0]
    x[("A·B 같음" if a == b else "다름", b == truth[i])] += 1
print("flash A 다수결 vs B 다수결:", {str(k): v for k, v in x.items()})
for i in ids:
    print(i, truth[i], "flashA", [A[("gemini-3.8-flash", "A", r)][i]["j"] for r in (1, 2, 3)], "flashB", [A[("gemini-3.8-flash", "B", r)][i]["j"] for r in (1, 2, 3)], "proA", A[("gemini-pro-latest", "A", 1)][i]["j"], "proB", A[("gemini-pro-latest", "B", 1)][i]["j"])
