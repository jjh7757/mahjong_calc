"""사용자 정답(answers_user.json)으로 한 판의 손패를 끝에서 거꾸로 복원(2026-11-17, 사용자 "r11 은 그럼 패보 복구된 거니").

  python -X utf8 rebuild.py <판 id>
끝 손패(공개 순서 = 줄 순서라고 봄) + 강 기록(버린 패 종류) + 차례별 답(종류 · 나간 칸 · 들어간 칸 · 먼저 넣고 버림 · 옮김)만 쓴다.
시작 손패는 쓰지 않는다. 답에 없는 옮김(보지 않은 구간 포함)이 있었다면 그 앞 차례들은 틀린다 — 정렬이 맞는지를 간접 검사로 같이 찍는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
from replay import key, sort_scheme  # noqa: E402

BASE = hc.WORK / "testtruth_1116"


def main():
    gid = sys.argv[1]
    game = hc.jload(hc.OUT / gid / "game.json")
    fh = game["final_hand"]
    g = next(x for x in hc.jload(BASE / "turns.json")["games"] if x["id"] == gid)
    ans = hc.jload(BASE / "answers_user.json")
    row = list(fh["closed"])
    print(f"{gid} · 결과 {game.get('result')} · 끝 손패(줄 순서) {' '.join(row)} · 화료패 {fh.get('win_tile')} · 울기 {fh.get('melds')}")
    print(f"녹화 전 버림 {g['first_i'] - 1}장 — 그 차례들은 복원 밖")
    sch = sort_scheme(row)
    out = []
    for t in reversed(g["turns"]):
        a = ans.get(t["id"]) or {}
        x = t["tile"]
        after = list(row)
        if a.get("kind") == "tsumogiri":
            out.append((t, "쯔모기리", x, x, list(row), after, None))
            continue
        if a.get("kind") != "hand" or a.get("k") is None or a.get("j") is None:
            print(f"  {t['id']}: 답이 '{a.get('kind')}' — 여기서 멈춤(이 앞은 복원 못 함)")
            break
        if a.get("insert_first"):
            r14 = row[:a["k"] - 1] + [x] + row[a["k"] - 1:]          # 버린 패를 보이는 번호 자리에 되돌림
            for m in reversed(a.get("moves") or []):
                i, j = m["swap"]
                r14[i - 1], r14[j - 1] = r14[j - 1], r14[i - 1]      # 맞바꿈 되돌림
            d = r14.pop(a["j"] - 1)                                   # 끼운 뽑은 패를 뺌
            row = r14
            how = f"뽑은 패를 {a['j']}번째에 끼운 뒤 {a['k']}번째(끼운 패 포함)를 버림" + (" · 옮김 있음" if a.get("moves") else "")
        else:
            jc = a.get("j_closed")
            d = row[jc - 1]
            rest = row[:jc - 1] + row[jc:]
            row = rest[:a["k"] - 1] + [x] + rest[a["k"] - 1:]
            how = f"{a['k']}번째를 버림 · 뽑은 패는 {'끝에 그대로' if a['j'] == len(row) + 1 else str(a['j']) + '번째(빈칸 둔 번호)'}"
        out.append((t, "손에서", d, x, list(row), after, how))
    print("순 | 종류 | 뽑은 패 | 버린 패 | 뽑기 전 손패(줄 순서) | 정렬 어긋난 이웃 쌍")
    for t, kind, d, x, before, after, how in reversed(out):
        ks = [key(v, sch) for v in before]
        bad = [f"{before[i]}>{before[i + 1]}" for i in range(len(ks) - 1) if ks[i] is not None and ks[i + 1] is not None and ks[i] > ks[i + 1]]
        print(f"{t.get('label', t['i']):>3} | {kind} | {d} | {x} | {' '.join(before)} | {' '.join(bad) or '-'}" + (f"   ← {how}" if how else ""))
    print("정렬 읽기(끝 손패에서):", sch)


if __name__ == "__main__":
    main()
