"""3번 동시 읽기에서 '두 답 일치 → 먼저 보여 주기, 셋째 답 → 확정' 을 쌓인 실측으로 시뮬레이션 (추가 호출 없음).

장면 시간 = max(자리 판독 정책 시간, 작은 호출들). 작은 호출(강 끝 3·리치봉·도라)은 scene_base.json 의 실측 장면에서 뽑는다.
"""
import json, random, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import policy as P

R = Path(__file__).parent / "results"
rows = [r for n in ("seat_zr_set2_v3a", "seat_v3a_now") for r in json.loads((R / f"{n}.json").read_text(encoding="utf-8"))
        if not r.get("error") and r["scene"] in "BCD"]
by = defaultdict(list)
for r in rows:
    by[r["photo"]].append(r)
small = [max(v["s"] for k, v in sc["calls"].items() if k != "seat") for sc in
         json.loads((R / "scene_base.json").read_text(encoding="utf-8"))]
chk = P.CHECKS["tenpai"]  # 앱이 할 수 있는 검사: 장수·텐파이/화료 형태
rnd = random.Random(7)
N = 20000
stats = defaultdict(list)
cnt = Counter()
for _ in range(N):
    photo = rnd.choice(sorted(by))
    rs = sorted(rnd.sample(by[photo], 3), key=lambda r: r["s"])
    sm = rnd.choice(small)
    t3 = rs[-1]["s"]
    keys = [P.key(r) for r in rs]
    unanimous = len(set(keys)) == 1 and chk(rs[0])
    # 1) 지금: 만장일치(셋 다 기다림)
    stats["U3"].append(max(t3, sm))
    cnt["U3_auto"] += unanimous
    cnt["U3_wrong"] += unanimous and not P.ok(rs[0])
    # 2) 한 번 읽기(참고)
    stats["one"].append(max(rs[0]["s"] if False else rnd.choice(rs)["s"], sm))
    # 3) 먼저 보여 주기: 검사 통과한 두 답이 같아지는 순간 보여 주고, 셋째가 오면 확정
    seen = Counter(); shown = None
    for r in rs:
        if not chk(r):
            continue
        seen[P.key(r)] += 1
        if seen[P.key(r)] == 2:
            shown = r; break
    if shown is not None:
        cnt["P_shown"] += 1
        stats["P_show"].append(max(shown["s"], sm))
        stats["P_gap"].append(max(t3, sm) - max(shown["s"], sm))  # 보여 준 뒤 확정까지
        if unanimous:
            cnt["P_confirm"] += 1
        else:
            cnt["P_revoke"] += 1  # 보여 줬는데 셋째가 달라 '확인' 으로 바뀜
            cnt["P_revoke_shown_right"] += P.ok(shown)
        cnt["P_shown_wrong"] += not P.ok(shown)
    else:
        stats["P_show"].append(max(t3, sm))  # 일치 없음 → 셋 다 와서 확인 질문


def q(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(p * len(xs)))]


print(f"사진 {len(by)}장, 사진당 판독 {min(map(len, by.values()))}~{max(map(len, by.values()))}회, 작은 호출 장면 {len(small)}개, 뽑기 {N}")
for k, label in [("one", "한 번 읽기(참고, 안전장치 없음)"), ("U3", "지금: 3번 + 만장일치"), ("P_show", "먼저 보여 주기(2개 일치 순간)")]:
    xs = stats[k]
    print(f"{label:28s} 장면 중앙 {statistics.median(xs):5.1f}  p90 {q(xs, .9):5.1f}  최대 {max(xs):5.1f}")
print(f"만장일치 자동 {cnt['U3_auto']/N:.1%}, 그중 틀림 {cnt['U3_wrong']/N:.2%}")
print(f"먼저 보여 줌 {cnt['P_shown']/N:.1%}: 셋째도 같아 확정 {cnt['P_confirm']/N:.1%}, 셋째가 달라 확인으로 바뀜 {cnt['P_revoke']/N:.1%}"
      f"(그중 보여 준 답이 맞았던 것 {cnt['P_revoke_shown_right']/max(1,cnt['P_revoke']):.0%}), 보여 준 답이 틀림 {cnt['P_shown_wrong']/N:.2%}")
g = stats["P_gap"]
print(f"보여 준 뒤 확정까지 추가 대기: 중앙 {statistics.median(g):.1f}  p90 {q(g,.9):.1f}  최대 {max(g):.1f}초, 10초 안 {sum(x<=10 for x in g)/len(g):.1%}")
