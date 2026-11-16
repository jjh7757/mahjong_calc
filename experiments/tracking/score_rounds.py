# replay_rounds.dart 결과(JSON 여러 개)를 모아 "고치기 전" 과 C(격자 + 울기 추적 칸 + 새 일발 판정)를 견준다(2026-11-16).
#   python experiments/tracking/score_rounds.py <captures 폴더> <rounds json>...
# 고치기 전 = 오늘 고치기 전 앱 코드가 했을 것:
#   - 그 격자 구간에 "첫 기준에서 다시 맞춤"(first-regrid, 새로 넣은 동작)이 없었으면 B(예전부터 있던 카메라 이동 재맞춤 포함, 예전 일발 판정)
#   - 있었으면 A(저장 격자 그대로, 예전 일발 판정) — 예전 코드는 그 자리에서 격자를 안 고쳤다.
# 정답 리치 = 그 판 화료 기록(meta.json)의 사진 횡치 리치 자리(merge.riichi_seats_photo). 울기 = 화료자 울기(merge.melds).
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
caps_dir = sys.argv[1]


def winner_melds(cap):
    m = json.load(open(os.path.join(caps_dir, cap, "meta.json"), encoding="utf-8"))
    return len((m.get("merge") or {}).get("melds") or [])


keys = ["전", "C"]
tot = {k: dict(hit=0, false=0, grew=0, ipp=[]) for k in keys}
seats = n_rounds = 0
no_meld = meld = 0
grew_no_meld = {k: 0 for k in keys}
meld_seen = {k: 0 for k in keys}
for f in sys.argv[2:]:
    rounds = json.load(open(f, encoding="utf-8"))
    active, prev_grid = False, None
    for name in sorted(rounds):
        r = rounds[name]
        if r["A"]["grid"] != prev_grid:
            active, prev_grid = False, r["A"]["grid"]
        kinds = [x[1] for x in r["regrids"]]
        if "first-regrid" in kinds:
            active = True
        base = "A" if active else "B"
        note = " ※다시 맞춘 뒤 카메라 이동도 있음" if active and "moved" in kinds else ""
        if not r["captures"]:
            continue
        n_rounds += 1
        truth = set(r["truth_riichi"])
        seats += len(truth)
        melds = winner_melds(r["captures"][-1])
        line = [name[9:15], "정답", ",".join(sorted(truth)) or "-", "화료", r["winner"], f"울기{melds}", "격자", r["regrids"], note]
        w = r["winner"]
        if w and melds == 0:
            no_meld += 1
        elif w:
            meld += 1
        for k, src in zip(keys, [base, "C"]):
            x = r[src]
            if k == "C":
                # 앱의 새 조건(RiverTracker.ippatsuCandidates): 리치 뒤 네 자리 버림 합 3장 이하. 재생 결과에는 이 조건 전 값이 들어 있어 여기서 거른다.
                total = sum(x["discards"].values())
                since = {s: total - x["riichi_at"][s]["total"] for s in x["ippatsu"]}
                x = dict(x, ippatsu=[s for s in x["ippatsu"] if since[s] <= 3], dropped=[f"{s}(리치 뒤 버림 합 {since[s]})" for s in x["ippatsu"] if since[s] > 3],
                         since=since)
            got = set(x["riichi"])
            tot[k]["hit"] += len(got & truth)
            tot[k]["false"] += len(got - truth)
            tot[k]["grew"] += len(x["grew"])
            if x["ippatsu"]:
                tot[k]["ipp"].append(f"{name[9:15]}:{','.join(x['ippatsu'])}")
            if w and melds == 0:
                grew_no_meld[k] += sum(1 for g in x["grew"] if g[1] == w)
            elif w:
                meld_seen[k] += any(g[1] == w for g in x["grew"])
            line.append(f"| {k}({src}) 리치 {','.join(sorted(got)) or '-'} 일발 {','.join(x['ippatsu']) or '-'}"
                        f"(강 {','.join(x['ippatsu_river']) or '-'}, 자기 {','.join(x['self_grew']) or '-'}) 늘어남 {len(x['grew'])}"
                        + (f" 버림합 {x['since']}" if x.get("since") else "") + (f" 뺌 {x['dropped']}" if x.get("dropped") else ""))
        print(*line)
print()
print(f"화료 기록이 있는 판 {n_rounds} · 정답 리치 자리 {seats}")
for k in keys:
    t = tot[k]
    print(f"{k}: 리치 {t['hit']}/{seats} · 헛 리치 {t['false']} · '울기 늘어남' {t['grew']}회 · 일발 후보 {t['ipp']}")
print(f"화료자 울기 0 인 판 {no_meld}: 화료자 모서리 '늘어남'(헛) " + " / ".join(f"{k} {grew_no_meld[k]}" for k in keys))
print(f"화료자 울기 있는 판 {meld}: 화료자 모서리 '늘어남' 을 본 판 " + " / ".join(f"{k} {meld_seen[k]}" for k in keys))
