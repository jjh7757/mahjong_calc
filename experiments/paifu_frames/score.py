"""패보 채점. python score.py results/<name>/slot.json truth.json <name>

- 자리별 강(울어 간 패 포함, 순서대로): 정답과 편집 거리 정렬 → 장수 맞음, 패 맞음(같은 자리 순번 정렬 뒤 같은 패), 빠짐·헛것.
- 울어 감: (자리, 패) 짝이 정답에 있는가.
- 한 판 순서: 예측 interleave 를 정답 seq 와 맞춰(자리별 k번째 버림끼리) 앞뒤 순서가 같은 쌍의 비율(켄달).
"""
import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paifu_frames import SIDES, interleave  # noqa: E402


def align(a: list, b: list):
    """편집 거리 정렬(대치 비용: 같은 패 0, 다른 패 1). 반환 [(i|None, j|None)]."""
    n, m = len(a), len(b)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        D[i][0] = i
    for j in range(m + 1):
        D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1))
    i, j, out = n, m, []
    while i or j:
        if i and j and D[i][j] == D[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1):
            out.append((i - 1, j - 1)); i -= 1; j -= 1
        elif i and D[i][j] == D[i - 1][j] + 1:
            out.append((i - 1, None)); i -= 1
        else:
            out.append((None, j - 1)); j -= 1
    return out[::-1]


def main():
    pred = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    truth = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))[sys.argv[3]]
    tseq = [(x.split()[0], x.split()[1].rstrip("*"), x.endswith("*")) for x in truth["seq"]]
    tot = {"truth": 0, "pred": 0, "matched": 0, "tile_ok": 0, "missed": 0, "extra": 0}
    per = {}
    for s in SIDES:
        t = [x[1] for x in tseq if x[0] == s]
        p = [r["tile"] for r in pred[s]["slots"]]
        al = align(t, p)
        m = sum(1 for i, j in al if i is not None and j is not None)
        ok = sum(1 for i, j in al if i is not None and j is not None and t[i] == p[j])
        miss = sum(1 for i, j in al if j is None)
        extra = sum(1 for i, j in al if i is None)
        per[s] = f"정답 {len(t)} 예측 {len(p)} 패맞음 {ok} 빠짐 {miss} 헛것 {extra}  정답[{' '.join(t)}] 예측[{' '.join(p)}]"
        for k, v in (("truth", len(t)), ("pred", len(p)), ("matched", m), ("tile_ok", ok), ("missed", miss), ("extra", extra)):
            tot[k] += v
    tk = {(x[0], x[1]) for x in tseq if x[2]}
    pk = {(s, r["tile"]) for s in SIDES for r in pred[s]["slots"] if r["taken_at"]}
    # 한 판 순서: 자리별 k번째 버림으로 맞춰 켄달
    pi = interleave(pred)
    pk_pos = {}
    cnt = {s: 0 for s in SIDES}
    for idx, (at, kind, s, r) in enumerate(e for e in pi if e[1] == "discard"):
        pk_pos[(s, cnt[s])] = idx
        cnt[s] += 1
    cnt = {s: 0 for s in SIDES}
    tpos = {}
    for idx, x in enumerate(tseq):
        tpos[(x[0], cnt[x[0]])] = idx
        cnt[x[0]] += 1
    common = [k for k in tpos if k in pk_pos]
    agree = sum(1 for a, b in combinations(common, 2) if (tpos[a] - tpos[b]) * (pk_pos[a] - pk_pos[b]) > 0)
    pairs = len(common) * (len(common) - 1) // 2
    print(f"== {sys.argv[3]} ({Path(sys.argv[1]).name})")
    for s in SIDES:
        print(f"  {s:6s} {per[s]}")
    print(f"  강 합계: 정답 {tot['truth']}장, 예측 {tot['pred']}장, 패까지 맞음 {tot['tile_ok']}/{tot['truth']}, 빠짐 {tot['missed']}, 헛것 {tot['extra']}")
    print(f"  울어 감: 정답 {sorted(tk)} / 예측 {sorted(pk)} → 맞음 {len(tk & pk)}/{len(tk)}, 헛것 {len(pk - tk)}")
    print(f"  한 판 순서(켄달 쌍 일치): {agree}/{pairs} = {agree / max(1, pairs):.3f}")
    return {"tile_ok": tot["tile_ok"], "truth": tot["truth"], "missed": tot["missed"], "extra": tot["extra"],
            "taken_ok": len(tk & pk), "taken": len(tk), "taken_extra": len(pk - tk), "order": round(agree / max(1, pairs), 3)}


if __name__ == "__main__":
    r = main()
    print(json.dumps(r, ensure_ascii=False))
