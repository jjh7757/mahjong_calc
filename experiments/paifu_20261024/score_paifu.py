"""전체 패를 깐 사진 한 장의 판독(scripts/pipeline.py 의 summary.json)을 사람이 만든 정답(truth_*.json)과 비교한다.

패보 복원 관점에서 본다: 네 자리 손패(울기 포함), 네 자리 강(버린 순서), 도라 표시패.
- 손패: 패 묶음(multiset) 기준 맞은 장수. 울기를 울기로 읽었는지 따로.
- 강: 패 묶음 기준 맞은 장수와, 순서까지 맞은 장수(같은 칸에 같은 패), 순서를 거꾸로 읽었는지.
- 정합성: 같은 패가 5장 이상이면 판독이 틀린 것. 사람 확인 없이 잡을 수 있는 오류.

용법: python score_paifu.py summary.json truth.json [rivers.json]
  rivers.json(river_crops.py 결과)을 주면 강은 그것으로 바꿔 채점한다.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

SIDES = ['bottom', 'right', 'top', 'left']


def norm(c: str) -> str:
    return '5' + c[1] if c and c[0] == '0' else c


def overlap(a: list[str], b: list[str]) -> int:
    return sum((Counter(map(norm, a)) & Counter(map(norm, b))).values())


def same_pos(a: list[str], b: list[str]) -> int:
    return sum(1 for x, y in zip(map(norm, a), map(norm, b)) if x == y)


def rows_swapped(a: list[str]) -> list[str]:
    return a[6:] + a[:6]


def rows_reversed(a: list[str]) -> list[str]:
    return list(reversed(a[:6])) + list(reversed(a[6:12])) + list(reversed(a[12:]))


def pred_hand(r: dict) -> tuple[list[str], list[list[str]]]:
    closed = [t['tile'] for t in r['tiles']]
    if r.get('win_tile'):
        closed.append(r['win_tile']['tile'])
    melds = [[m['type'], *m['tiles']] for m in r.get('melds', [])]
    return closed, melds


def all_tiles(closed: list[str], melds: list[list[str]]) -> list[str]:
    return closed + [t for m in melds for t in m[1:]]


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    s = json.load(open(sys.argv[1], encoding='utf-8'))
    t = json.load(open(sys.argv[2], encoding='utf-8'))
    res = s['results']
    center = dict(res.get('center', {}))
    if len(sys.argv) > 3:
        center['rivers'] = json.load(open(sys.argv[3], encoding='utf-8'))['rivers']
        print(f'(강은 {sys.argv[3]} 로 채점)')

    print('| 구역 | 정답 장수 | 판독 장수 | 패 맞음 | 순서까지 맞음 | 비고 |')
    print('|---|---|---|---|---|---|')
    tot_true = tot_hit = 0
    seen: list[str] = []
    for side in SIDES:
        tr = t['hands'][side]
        t_all = all_tiles(tr['closed'], tr['melds'])
        r = res.get(f'hand_{side}')
        if r is None:
            print(f'| 손패 {side} | {len(t_all)} | - | 0 | - | 못 읽음 |')
            tot_true += len(t_all)
            continue
        pc, pm = pred_hand(r)
        p_all = all_tiles(pc, pm)
        seen += p_all
        hit = overlap(p_all, t_all)
        tot_true += len(t_all)
        tot_hit += hit
        meld_note = ''
        if tr['melds'] or pm:
            tm = sorted(m[0] + ':' + ' '.join(sorted(map(norm, m[1:]))) for m in tr['melds'])
            ppm = sorted(m[0] + ':' + ' '.join(sorted(map(norm, m[1:]))) for m in pm)
            meld_note = '울기 맞음' if tm == ppm else f'울기 정답 {tm} / 판독 {ppm}'
        miss = sorted((Counter(map(norm, t_all)) - Counter(map(norm, p_all))).elements())
        extra = sorted((Counter(map(norm, p_all)) - Counter(map(norm, t_all))).elements())
        diff = f'빠짐 {" ".join(miss)} / 더 읽음 {" ".join(extra)}' if miss or extra else ''
        print(f'| 손패 {side} | {len(t_all)} | {len(p_all)} | {hit} | - | {"; ".join(x for x in (meld_note, diff) if x)} |')

    riv_true = riv_hit = riv_pos = 0
    p_rivers = center.get('rivers', {})
    for side in SIDES:
        tr = t['rivers'][side]
        pr = p_rivers.get(side, [])
        seen += pr
        hit = overlap(pr, tr)
        pos = same_pos(pr, tr)
        notes = []
        if pos < hit:
            alt = {'줄마다 거꾸로': same_pos(rows_reversed(pr), tr), '두 줄 바뀜': same_pos(rows_swapped(pr), tr)}
            best = max(alt, key=alt.get)
            if alt[best] > pos:
                notes.append(f'{best} 읽음({best} 보정 시 {alt[best]}장 제자리)')
        riv_true += len(tr)
        riv_hit += hit
        riv_pos += pos
        print(f'| 강 {side} | {len(tr)} | {len(pr)} | {hit} | {pos} | {"; ".join(notes)} |')

    pd = [d['tile'] for d in center.get('dora_indicators', [])]
    td = t.get('dora_indicators', [])
    print(f'| 도라 표시패 | {len(td)} | {len(pd)} | {overlap(pd, td)} | - | 정답 {td} / 판독 {pd} |')

    print()
    print(f'손패 {tot_hit}/{tot_true} ({round(100 * tot_hit / tot_true)}%), '
          f'강 패 {riv_hit}/{riv_true} ({round(100 * riv_hit / riv_true)}%), '
          f'강 순서까지 {riv_pos}/{riv_true} ({round(100 * riv_pos / riv_true)}%)')

    seen += pd
    over = {k: v for k, v in Counter(map(norm, seen)).items() if v > 4}
    print(f'판독 전체 {len(seen)}장, 5장 이상 나온 패(판독 오류 확정): {over or "없음"}')
    if t.get('wall_remaining') is not None:
        print(f'정답 기준 남은 벽패 {t["wall_remaining"]} = 136 - 14(왕패) - 보이는 패 {136 - 14 - t["wall_remaining"]}장(도라 표시패 제외)')


if __name__ == '__main__':
    main()
