"""Mortal-S42 로컬 채점 — tenhou.net/6 JSON 한 국을 mjai 이벤트로 바꿔 한 자리 시점으로 먹이고,
그 자리의 결정마다 Q 값 · 확률(softmax(Q/τ))을 적는다. (2026-11-20)

다른 자리 배패 · 뽑은 패는 '?' 로 가린다(tenhou6 에 지어 채운 패가 있어도 안 씀).
런타임: C:\\Users\\jjh7757\\dev\\mortal-s42 (AGPL 런타임 · Apache-2.0 가중치, 로컬 실험만).

쓰기: python mortal_local.py <tenhou6.json> <seat> [--tau 0.1] [--top 5] [--events out.jsonl]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

MORTAL = Path(r'C:\Users\jjh7757\dev\mortal-s42')

HONORS = {41: 'E', 42: 'S', 43: 'W', 44: 'N', 45: 'P', 46: 'F', 47: 'C'}
ACTION_TILES = [f'{n}{s}' for s in 'mps' for n in range(1, 10)] + list('ESWNPFC') + ['5mr', '5pr', '5sr']
ACTION_NAMES = ACTION_TILES + ['Riichi', 'Chi(low)', 'Chi(mid)', 'Chi(high)', 'Pon', 'Kan', 'Hora', 'Ryukyoku', 'Pass']


def tile(code: int) -> str:
    if code in (51, 52, 53):
        return '5' + 'mps'[code - 51] + 'r'
    if code in HONORS:
        return HONORS[code]
    return f'{code % 10}{"mps"[code // 10 - 1]}'


def split_call(s: str):
    """'4646p46' → ('p', 칸 위치 4, [46,46,46], 부른 패 46)."""
    for i, ch in enumerate(s):
        if ch.isalpha():
            letter, pos = ch, i
            break
    nums = s[:pos] + s[pos + 1:]
    tiles = [int(nums[k:k + 2]) for k in range(0, len(nums), 2)]
    called = int(s[pos + 1:pos + 3])
    return letter, pos, tiles, called


def to_mjai(log: list, hero: int) -> list[dict]:
    (kidx, honba, kyotaku), scores, doras, _ura = log[0], log[1], log[2], log[3]
    hai = [log[4 + 3 * p] for p in range(4)]
    takes = [log[5 + 3 * p] for p in range(4)]
    discs = [log[6 + 3 * p] for p in range(4)]
    oya = kidx % 4
    ev = [{'type': 'start_game', 'names': ['A', 'B', 'C', 'D']},
          {'type': 'start_kyoku', 'bakaze': 'ESWN'[kidx // 4], 'dora_marker': tile(doras[0]),
           'kyoku': kidx % 4 + 1, 'honba': honba, 'kyotaku': kyotaku, 'oya': oya, 'scores': scores,
           'tehais': [[tile(t) for t in hai[p]] if p == hero else ['?'] * 13 for p in range(4)]}]
    ti, di = [0] * 4, [0] * 4
    actor, called_in = oya, False
    while True:
        drawn = None
        if not called_in:
            if ti[actor] >= len(takes[actor]):
                break  # 유국 등
            t = takes[actor][ti[actor]]
            ti[actor] += 1
            if isinstance(t, str):
                raise ValueError(f'순서 어긋남: 자리 {actor} 의 뽑기 자리에 울기 {t}')
            drawn = t
            ev.append({'type': 'tsumo', 'actor': actor, 'pai': tile(t) if actor == hero else '?'})
        if di[actor] >= len(discs[actor]):
            break  # 쯔모 화료
        d = discs[actor][di[actor]]
        di[actor] += 1
        reach = False
        if isinstance(d, str):
            if not d.startswith('r'):
                raise ValueError(f'지원 안 하는 버림 표기 {d}(깡)')
            reach, d = True, int(d[1:])
            ev.append({'type': 'reach', 'actor': actor})
        if d == 60:
            pai, tg = drawn, True
        else:
            pai, tg = d, False
        ev.append({'type': 'dahai', 'actor': actor, 'pai': tile(pai), 'tsumogiri': tg})
        # 울기 찾기(퐁 · 깡이 치보다 먼저)
        caller = None
        for off in (1, 2, 3):
            p = (actor + off) % 4
            if ti[p] < len(takes[p]) and isinstance(takes[p][ti[p]], str):
                letter, pos, tiles_, called = split_call(takes[p][ti[p]])
                src = {0: 3, 2: 2, 4: 1, 6: 1}[pos] if letter != 'c' else 3
                norm = lambda x: {51: 15, 52: 25, 53: 35}.get(x, x)  # noqa: E731
                if (p + src) % 4 == actor and norm(called) == norm(pai):
                    if caller is None or letter != 'c':
                        caller = (p, letter, tiles_, called)
        if reach:
            # 이 버림으로 론이 나면 성립 안 함
            ended = all(ti[q] >= len(takes[q]) for q in range(4) if q != actor) and caller is None
            if not (ended and di[actor] >= len(discs[actor])):
                ev.append({'type': 'reach_accepted', 'actor': actor})
        if caller:
            p, letter, tiles_, called = caller
            ti[p] += 1
            consumed = list(tiles_)
            consumed.remove(called)
            kind = {'c': 'chi', 'p': 'pon', 'm': 'daiminkan'}[letter]
            ev.append({'type': kind, 'actor': p, 'target': actor, 'pai': tile(called),
                       'consumed': [tile(x) for x in consumed]})
            actor, called_in = p, True
            continue
        nxt = (actor + 1) % 4
        if ti[nxt] >= len(takes[nxt]):
            break  # 이 버림으로 론(또는 유국)
        actor, called_in = nxt, False
    return ev


def decode(meta: dict) -> list[tuple[str, float]]:
    bits, q = meta['mask_bits'], meta['q_values']
    idx = [i for i in range(46) if bits >> i & 1]
    assert len(idx) == len(q), (len(idx), len(q))
    return [(ACTION_NAMES[i], v) for i, v in zip(idx, q)]


def actual_of(trigger: dict, after: list[dict], hero: int) -> str:
    """결정 뒤 실제로 hero 가 한 것."""
    for e in after:
        if e.get('actor') != hero:
            if trigger['type'] == 'dahai' and trigger['actor'] != hero:
                return 'Pass'  # 남의 버림 뒤 hero 가 아무것도 안 함
            continue
        t = e['type']
        if t == 'dahai':
            return e['pai']
        if t == 'reach':
            return 'Riichi'
        if t in ('pon', 'chi', 'daiminkan'):
            return {'pon': 'Pon', 'daiminkan': 'Kan'}.get(t, 'Chi')
        if t == 'tsumo':
            return 'Pass'
    return 'Hora'  # 사건이 끝났는데 hero 결정이 남음 = 화료(론 · 쯔모)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('seat', type=int)
    ap.add_argument('--tau', type=float, default=0.1)
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--events')
    a = ap.parse_args()

    sys.path.insert(0, str(MORTAL))
    from inference import load_engine, Session  # noqa: E402

    data = json.loads(Path(a.log).read_text(encoding='utf-8'))
    engine = load_engine('cpu')
    rows = []
    for log in data['log']:
        events = to_mjai(log, a.seat)
        if a.events:
            Path(a.events).write_text('\n'.join(json.dumps(e) for e in events) + '\n', encoding='utf-8')
        s = Session(engine, a.seat)
        left = 70
        for i, e in enumerate(events):
            if e['type'] == 'tsumo':
                left -= 1
            r = s.react(e)
            if r is None or 'meta' not in r:
                continue
            cands = decode(r['meta'])
            mx = max(v for _, v in cands)
            z = sum(math.exp((v - mx) / a.tau) for _, v in cands)
            cands = sorted(((n, v, math.exp((v - mx) / a.tau) / z * 100) for n, v in cands), key=lambda x: -x[1])
            act = actual_of(e, events[i + 1:], a.seat)
            names = [n for n, _, _ in cands]
            rank = names.index(act) + 1 if act in names else None
            p_act = cands[rank - 1][2] if rank else None
            rows.append({'left': left, 'trigger': f"{e['type']}:{e.get('actor')}:{e.get('pai', '')}",
                         'actual': act, 'rank': rank, 'n': len(cands), 'p_actual': p_act,
                         'shanten': r['meta'].get('shanten'), 'top': cands[:a.top]})
            # 리치를 실제로 했으면 리치 선언패 결정은 reach 이벤트에서 다시 나옴(위 루프가 처리)
    for k, row in enumerate(rows, 1):
        top = ' '.join(f'{n}/{v:.2f}/{p:.1f}' for n, v, p in row['top'])
        rk = f"#{row['rank']}/{row['n']}" if row['rank'] else '?'
        pa = f"{row['p_actual']:.3g}%" if row['p_actual'] is not None else '-'
        print(f"{k:2d} (x{row['left']}) sh{row['shanten']} {row['trigger']:<14} 실제 {row['actual']:<6} {rk:<6} {pa:<8} | {top}")


if __name__ == '__main__':
    main()
