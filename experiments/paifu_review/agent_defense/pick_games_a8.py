"""복기 에이전트 지시문 a8 측정 준비 — 판 고르기 + 사실표 만들기(설계서 docs/review_agent_foldspot_scores_design_1123.md 8-2절).

  python -X utf8 experiments/paifu_review/agent_defense/pick_games_a8.py        (저장소 뿌리에서)

고르는 규칙(답을 보기 전에 고정, 2026-11-23 밤):
- pick_games_a7.py 의 후보 · 씨 · 섞은 순서를 그대로 다시 만든다(그 모듈을 import — 고치지 않음). 다시 만든 순서에서 a7 이 쓴 국
  (fa1 · fa2 = 민 국 1 · 2번째, fa3 · fa4 · ga3 · ga4 = 접은 국 1 ~ 4번째)이 results/agent_1123a7/picked_a7.json 과 같은지 먼저 확인한다.
- F2: 민 국 3번째부터 fb1 · fb2, 접은 국 5번째부터 fb3 · fb4. a7 과 같은 확인(그 차례 버림 = pf 줄 · fold_spot 객체 · stance pushed /
  folded), 안 맞거나 도구가 거절하면 건너뛰고 다음 후보. 판은 a7 의 판 · 서로와 겹치지 않게.
- G2: gc1 · gc2 = assets/paifu_h3/ 이름 순 셋째 · 넷째(도구가 거절하거나 game.scores 가 null 이면 그다음), gc3 · gc4 = 접은 국 섞은 순서에서
  fb3 · fb4 다음(7 · 8번째부터, 판 안 겹침, 도구 거절 · scores null 이면 건너뜀), gd1 = assets/paifu/r11_130921.json(점수 없음).
- N: 수비 6 = fb1 ~ fb4 · gc3 · gc4 각각에서 defense 가 있고 fold_spot 이 null 이고 stance 가 null 이 아닌 차례 중 가장 이른 것
  (남의 리치 뒤 첫 그런 차례). 없으면 그 판은 건너뛰고, 같은 묶음(fb 또는 gc)의 다른 판에서 둘째 그런 차례를 쓴다.
  총평 4 = assets/paifu/ 의 r11_130921 · r12_131655 · r13_132644 · r14_133610(점수 없음, 사실표 3).
출력: results/agent_1123a8/facts/<익명 id 또는 판 이름>.json · picked_a8.json(판 ID 는 여기에만) · facts/_tried/(건너뛴 후보 사실표).
"""
import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pick_games_a7 as a7  # noqa: E402

PR = a7.PR
ROOT = a7.ROOT
OUT = os.path.join(PR, 'results', 'agent_1123a8')
FACTS = os.path.join(OUT, 'facts')
TRIED = os.path.join(FACTS, '_tried')
A7_PICKED = os.path.join(PR, 'results', 'agent_1123a7', 'picked_a7.json')
N_STORE = ['r11_130921', 'r12_131655', 'r13_132644', 'r14_133610']


def rel(p: str) -> str:
    return os.path.relpath(p, ROOT).replace('\\', '/')


def key(c: dict) -> tuple:
    return (c['game'], c['kyoku'], c['seat'])


def n_turns(f: dict) -> list[dict]:
    """defense 가 있고 fold_spot 이 null 이고 stance 가 null 이 아닌 차례(차례 순)."""
    out = []
    for t in f['turns']:
        df = t.get('defense')
        if df and df.get('fold_spot') is None and df.get('stance') is not None:
            out.append({'turn': t['turn'], 'discard': t['discard'], 'level': df['actual']['level'], 'rank': df['actual']['rank'],
                        'of': df['actual']['of'], 'stance': df['stance'], 'fold_spot': df.get('fold_spot'), 'safest': df['safest'],
                        'efficient': df.get('efficient'), 'genbutsu': t.get('genbutsu'), 'riichi_winds': t.get('riichi_winds')})
    return out


def first_other_riichi(f: dict) -> str | None:
    """앱 review_chat.dart _firstOtherRiichi 와 같은 뜻(사실표 others 의 첫 riichi)."""
    for o in f.get('others', []):
        if o['kind'] == 'riichi':
            return o['wind']
    return None


def main():
    os.makedirs(TRIED, exist_ok=True)
    push, fold, stats = a7.kyoku_candidates()
    rng = random.Random(a7.SEED)
    rng.shuffle(push)
    rng.shuffle(fold)
    old = json.load(open(A7_PICKED, encoding='utf-8'))['picked']
    want = {p['id']: p for p in old if p.get('order')}
    checks = [('fa1', push, 1), ('fa2', push, 2), ('fa3', fold, 1), ('fa4', fold, 2), ('ga3', fold, 3), ('ga4', fold, 4)]
    for aid, pool, order in checks:
        if key(pool[order - 1]) != key(want[aid]) or want[aid]['order'] != order:
            sys.exit(f'섞은 순서가 a7 과 다름: {aid}')
    print('a7 섞은 순서 다시 만듦 — fa1 ~ fa4 · ga3 · ga4 자리 같음. 후보', json.dumps(stats, ensure_ascii=False))
    used = {p['game'] for p in old if p.get('game')}
    picked, skipped = [], []

    def take(pool, start, ids, bundle, label, check):
        idx = start
        for aid in ids:
            while True:
                if idx >= len(pool):
                    sys.exit(f'{bundle} {label} 후보가 모자람')
                c = pool[idx]
                idx += 1
                if c['game'] in used:
                    skipped.append(dict(c, bundle=bundle, group=label, order=idx, reason='판이 이미 쓰임(a7 또는 이번)'))
                    continue
                tried = os.path.join(TRIED, f'{bundle}_{label}_{idx:02d}.json')
                ok, msg = a7.dart(['tool/tenhou6_agent_facts.dart', a7.test2_path(c['game']), str(c['kyoku']), str(c['seat'])], tried)
                why = ('도구 거절 ' + msg) if not ok else check(a7.load(tried), c)
                if why:
                    skipped.append(dict(c, bundle=bundle, group=label, order=idx, reason=why, tried=rel(tried) if ok else None))
                    print('  건너뜀', bundle, label, idx, why)
                    continue
                dst = os.path.join(FACTS, f'{aid}.json')
                shutil.move(tried, dst)
                used.add(c['game'])
                f = a7.load(dst)
                picked.append(dict(c, id=aid, bundle=bundle, group=label, order=idx, fold_turns=a7.fold_turns(f), n_turns=n_turns(f),
                                   first_riichi=first_other_riichi(f), scores=f['game'].get('scores'),
                                   facts=rel(dst), bytes=os.path.getsize(dst), compact=a7.compact_size(f)))
                print(' ', aid, bundle, label, '섞은 순서', idx, '· 접는 자리', [(x['turn'], x['stance']) for x in a7.fold_turns(f)])
                break
        return idx

    take(push, 2, ['fb1', 'fb2'], 'F2', 'push', lambda f, c: a7.check_f(f, c, 'pushed'))
    nxt = take(fold, 4, ['fb3', 'fb4'], 'F2', 'fold', lambda f, c: a7.check_f(f, c, 'folded'))
    take(fold, nxt, ['gc3', 'gc4'], 'G2', 'fold', lambda f, c: '' if f['game'].get('scores') else 'game.scores 가 null')
    # 매장 3반장 셋째 · 넷째(거절 · 점수 없음이면 그다음).
    h3 = sorted(n for n in os.listdir(os.path.join(ROOT, 'assets', 'paifu_h3')) if n.endswith('.json'))
    i = 2
    for aid in ('gc1', 'gc2'):
        while True:
            if i >= len(h3):
                sys.exit('매장 3반장 후보가 모자람')
            src = f'assets/paifu_h3/{h3[i]}'
            i += 1
            dst = os.path.join(FACTS, f'{aid}.json')
            ok, msg = a7.dart(['tool/paifu_agent_facts.dart', src], dst)
            why = ('도구 거절 ' + msg) if not ok else ('' if a7.load(dst)['game'].get('scores') else 'game.scores 가 null')
            if why:
                skipped.append({'bundle': 'G2', 'source': src, 'reason': why})
                print('  건너뜀', src, why)
                continue
            f = a7.load(dst)
            picked.append({'id': aid, 'bundle': 'G2', 'source': src, 'scores': f['game'].get('scores'), 'fold_turns': a7.fold_turns(f),
                           'n_turns': n_turns(f), 'facts': rel(dst), 'bytes': os.path.getsize(dst), 'compact': a7.compact_size(f)})
            print(' ', aid, src)
            break
    for aid, src in [('gd1', 'assets/paifu/r11_130921.json')] + [(n, f'assets/paifu/{n}.json') for n in N_STORE]:
        dst = os.path.join(FACTS, f'{aid}.json')
        ok, msg = a7.dart(['tool/paifu_agent_facts.dart', src], dst)
        if not ok:
            sys.exit(f'{aid} 사실표 실패: {msg}')
        f = a7.load(dst)
        picked.append({'id': aid, 'bundle': 'G2' if aid == 'gd1' else 'N', 'source': src, 'scores': f['game'].get('scores'),
                       'fold_turns': a7.fold_turns(f), 'facts': rel(dst), 'bytes': os.path.getsize(dst), 'compact': a7.compact_size(f)})
        print(' ', aid, src, '점수', 'null' if f['game'].get('scores') is None else '있음')
    # N 수비 6: 판마다 첫 그런 차례. 없으면 같은 묶음 다른 판의 둘째.
    by = {p['id']: p for p in picked}
    n_pick, n_skip = [], []
    for group in (['fb1', 'fb2', 'fb3', 'fb4'], ['gc3', 'gc4']):
        missing = [g for g in group if not by[g]['n_turns']]
        for g in group:
            if by[g]['n_turns']:
                n_pick.append({'game': g, 'nth': 1, **by[g]['n_turns'][0]})
        for g in missing:
            n_skip.append({'game': g, 'reason': 'defense 있고 fold_spot null · stance 있는 차례 없음'})
            alt = next((h for h in group if h not in missing and len(by[h]['n_turns']) >= 2
                        and not any(x['game'] == h and x['nth'] == 2 for x in n_pick)), None)
            if alt is None:
                sys.exit(f'N: {g} 대신 쓸 둘째 차례가 없음')
            n_pick.append({'game': alt, 'nth': 2, 'instead_of': g, **by[alt]['n_turns'][1]})
    for x in n_pick:
        print('  N', x['game'], f"{x['nth']}번째 그런 차례", x['turn'], x['discard'], x['level'], f"{x['rank']}/{x['of']}", x['stance'], 'fold_spot', x['fold_spot'])
    meta = {'seed': a7.SEED, 'f_stats': stats, 'reproduced_a7_order': True}
    open(os.path.join(OUT, 'picked_a8.json'), 'wb').write(json.dumps(
        {'meta': meta, 'picked': picked, 'skipped': skipped, 'n_defense': n_pick, 'n_skipped': n_skip},
        ensure_ascii=False, indent=1).encode('utf-8'))
    big = [n for n in os.listdir(FACTS) if n.endswith('.json') and a7.compact_size(a7.load(os.path.join(FACTS, n))) > a7.LIMIT]
    print('200KB 넘는 사실표:', big or '없음')


if __name__ == '__main__':
    main()
