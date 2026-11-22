"""에이전트 문제지 240개 — 설계서 docs/mxplainer_fit_design_1121.md 13절 (2026-11-22).

검증 40판의 주 묶음(preds_val.jsonl 의 15,994결정)에서 구간 8개(버리기 전 샹텐 ≤0 / 1 / 2 / 3+ × riskSeats 비었음 / 있음)
마다 30결정을 random.Random(20261122) 로 뽑고(구간 안 결정을 (game, kyoku, seat, k) 순 정렬 뒤 sample), 240결정을 같은
난수로 섞어 d001 ~ d240 · 20개씩 12묶음. 결정마다 천봉 로그의 그 국을 mortal_local.to_mjai(log, seat) 로 바꿔 hero 의 k 번째
버림 직전까지 재생해 hero 가 볼 수 있는 것만 적는다. 후보 표는 joined 의 candidates 에서, 패 번호 순.

넣지 않는 것: s42 의 어떤 값 · 실제 버린 패와 그 뒤 사건 · b0Order · mhBest · mhForwardBest · mhOrder · recommendBackward ·
preds_val 의 pick · 판 ID · 국 번호(로그 칸) · 자리 번호. 열쇠는 private/ 에(문제지 폴더 batches/ 와 따로).

쓰기: python -X utf8 agent_packets.py [--out-dir experiments/paifu_review/results/mxfit/agent1]
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import split  # noqa: E402
from mortal_local import to_mjai  # noqa: E402

S1 = ROOT / 'experiments' / 'paifu_review' / 'results' / 'mxfit' / 'stage1'
SEED = 20261122
PER_BIN = 30
BATCH = 20
BINS = [f'{s}/{t}' for s in ('0', '1', '2', '3+') for t in ('없음', '있음')]
HONOR = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}
REL = {0: '나', 1: '하가', 2: '대면', 3: '상가'}
WIND = '동남서북'
FORBIDDEN_WORDS = ('s42', 'S42', 'Mortal', 'mortal', 'mhBest', 'mhForwardBest', 'mhOrder', 'b0Order', 'recommendBackward',
                   'topAction', 'pickF', 'pickU', 'actual', 'B0', 'B1', 'B2', 'gm-')


def code(m: str) -> str:
    """mjai 패 → 문제지 표기(적5 = 0)."""
    if m in HONOR:
        return HONOR[m]
    if m.endswith('r'):
        return '0' + m[1]
    return m


def fold(c: str) -> str:
    return ('5' + c[1]) if c[0] == '0' else c


def tkey(c: str):
    n = int(c[0])
    return ('mpsz'.index(c[1]), 5 if n == 0 else n, 0 if n == 0 else 1)


def bin_of(r: dict) -> str:
    sh = r['shantenBefore']
    s = '0' if sh <= 0 else ('3+' if sh >= 3 else str(sh))
    return f"{s}/{'있음' if r.get('riskSeats') else '없음'}"


def dora_of(ind: str) -> str:
    n, s = int(fold(ind)[0]), ind[1]
    if s == 'z':
        if n <= 4:
            return f'{n % 4 + 1}z'
        return f'{(n - 5 + 1) % 3 + 5}z'
    return f'{n % 9 + 1}{s}'


def replay(events: list[dict], hero: int, k: int) -> dict:
    """hero 의 k 번째(0부터) 버림 직전까지 재생. 그 버림은 actual 로만 돌려준다(검사용)."""
    st = {'hand': [], 'rivers': [[] for _ in range(4)], 'melds': [[] for _ in range(4)], 'riichi': {},
          'kyotaku': 0, 'delta': [0] * 4, 'tsumo': 0, 'drawn': None, 'lastHero': None, 'pendingReach': set()}
    hd = 0
    start = None
    for i, e in enumerate(events):
        t = e['type']
        if t == 'start_kyoku':
            start = e
            st['hand'] = [code(x) for x in e['tehais'][hero]]
            st['kyotaku'] = e['kyotaku']
        elif t == 'tsumo':
            st['tsumo'] += 1
            if e['actor'] == hero:
                st['drawn'] = code(e['pai'])
                st['hand'].append(st['drawn'])
                st['lastHero'] = 'tsumo'
        elif t == 'reach':
            if e['actor'] == hero and hd == k:
                return _done(st, start, events, i, hero)
            st['pendingReach'].add(e['actor'])
        elif t == 'dahai':
            a = e['actor']
            if a == hero and hd == k:
                return _done(st, start, events, i, hero)
            c = code(e['pai'])
            r = a in st['pendingReach']
            st['pendingReach'].discard(a)
            st['rivers'][a].append({'t': c, 'tg': e['tsumogiri'], 'r': r, 'called': False})
            if a == hero:
                st['hand'].remove(c)
                hd += 1
                st['drawn'] = None
                st['lastHero'] = 'dahai'
        elif t == 'reach_accepted':
            a = e['actor']
            st['riichi'][a] = len(st['rivers'][a])  # 선언패 = 그 자리의 이 번째(1부터) 버림
            st['kyotaku'] += 1
            st['delta'][a] -= 1000
        elif t in ('chi', 'pon', 'daiminkan'):
            st['rivers'][e['target']][-1]['called'] = True
            tiles = [code(x) for x in e['consumed']] + [code(e['pai'])]
            st['melds'][e['actor']].append({'kind': {'chi': '치', 'pon': '퐁', 'daiminkan': '깡'}[t],
                                            'tiles': sorted(tiles, key=tkey), 'from': e['target']})
            if e['actor'] == hero:
                for x in e['consumed']:
                    st['hand'].remove(code(x))
                st['lastHero'] = 'call'
                st['drawn'] = None
    raise ValueError(f'hero 의 {k}번째 버림에 닿지 못함(버림 {hd}개)')


def _done(st, start, events, i, hero):
    actual = None
    for e in events[i:]:
        if e['type'] == 'dahai' and e['actor'] == hero:
            actual = code(e['pai'])
            break
    st['start'] = start
    st['actual'] = actual
    return st


def fmt(v, nd):
    if v is None:
        return '-'
    if nd == 0:
        return f'{round(float(v)):d}'
    return f'{float(v):.{nd}f}'


def packet(did: str, r: dict, st: dict, hero: int) -> str:
    s0 = st['start']
    oya = s0['oya']
    rel = lambda p: REL[(p - hero) % 4]  # noqa: E731
    order = [hero, (hero + 1) % 4, (hero + 2) % 4, (hero + 3) % 4]
    ind = code(s0['dora_marker'])
    L = [f'## {did}']
    L.append(f"국: {WIND['ESWN'.index(s0['bakaze'])]}{s0['kyoku']}국 {s0['honba']}본장 · 공탁 리치봉 {st['kyotaku']} · "
             f'도라 표시패 {ind} (도라 {dora_of(ind)})')
    oya_s = '나' if oya == hero else rel(oya)
    L.append(f"나: {WIND[(hero - oya) % 4]}가 · 친은 {oya_s} · 내 {r['k'] + 1}번째 버림 차례 · 남은 패산 {70 - st['tsumo']}장")
    pts = [s0['scores'][p] + st['delta'][p] for p in range(4)]
    rank = {p: i + 1 for i, p in enumerate(sorted(range(4), key=lambda p: (-pts[p], (p - oya) % 4)))}
    L.append('점수: ' + ' · '.join(
        f"{rel(p)} {pts[p]:,} ({rank[p]}위{', 친' if p == oya and p != hero else ''})" for p in order))
    hand = list(st['hand'])
    drawn = st['drawn']
    hand.remove(drawn)
    L.append(f"내 손패(뽑은 패 포함): {' '.join(sorted(hand, key=tkey))} + 뽑은 패 {drawn}")

    def meld_s(m):
        return f"{m['kind']} {' '.join(m['tiles'])}"
    hm = st['melds'][hero]
    L.append('내 울기: ' + (' · '.join(meld_s(m) for m in hm) if hm else '없음'))
    L.append('버림패(왼쪽이 먼저, * = 쯔모기리, R = 리치 선언패, ^ = 남이 울어 감):')
    for p in order:
        rv = st['rivers'][p]
        cells = [x['t'] + ('*' if x['tg'] else '') + ('R' if x['r'] else '') + ('^' if x['called'] else '') for x in rv]
        L.append(f"  {rel(p)}: {' '.join(cells) if cells else '(없음)'}")
    om = [f'{rel(p)} {meld_s(m)}' for p in order[1:] for m in st['melds'][p]]
    L.append('남의 울기: ' + (' · '.join(om) if om else '없음'))
    rs = [f'{rel(p)}(자기 {st["riichi"][p]}번째 버림에서 선언)' for p in order[1:] if p in st['riichi']]
    L.append('리치: ' + (' · '.join(rs) if rs else '없음'))
    L.append('후보(엔진 계산값, 패 번호 순):')
    L.append('| 버릴 패 | 장수 | 버린 뒤 샹텐 | 유효패(장) | 개량 평균(장) | 속도 | 화료율(%) | 국수지(점) | 방총 위험(%) | 모두에게 안전 | 도라 |')
    L.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
    for c in sorted(r['candidates'], key=lambda c: tkey(c['tile'])):
        tl = c['tile'] + (' (적5 포함)' if c.get('red') else '')
        ag = fmt(c['agariRate'], 1) if c['shanten'] == 0 else '-'
        sa = '-' if c['safeAll'] is None else ('예' if c['safeAll'] else '아니오')
        L.append(f"| {tl} | {c['n']} | {fmt(c['shanten'], 0)} | {fmt(c['waits'], 0)} | {fmt(c['improve'], 1)} | "
                 f"{fmt(c['speed'], 1)} | {ag} | {fmt(c['roundPoint'], 0)} | {fmt(c['risk'], 2)} | {sa} | {fmt(c['dora'], 0)} |")
    return '\n'.join(L) + '\n'


HEADER = """# 문제지 {b:02d} / 12 (결정 {n}개)

표기
- 패: 1m~9m 만수 · 1p~9p 통수 · 1s~9s 삭수 · 1z~7z = 동 남 서 북 백 발 중. 적5 는 0m · 0p · 0s.
- 자리: 하가 = 내 다음 차례, 대면 = 맞은편, 상가 = 내 앞 차례.
- 점수는 그 시점 점수(이 국에서 리치한 사람은 1,000점을 낸 뒤). 순위가 같으면 친에서 가까운 순.
- 후보 표의 5 줄은 적5 와 보통 5 를 한 줄로 묶는다. 적5 를 가지고 있으면 "(적5 포함)".
- 후보 표 칸: 장수 = 손에 든 그 패 장수 · 유효패 = 버린 뒤 샹텐을 줄이는 패 장수 · 개량 평균 = 개량 뒤 평균 유효패 ·
  속도 = 엔진의 속도 점수 · 화료율 = 버린 뒤 텐파이일 때만 · 국수지 = 엔진이 어림한 이 국의 점수 득실 ·
  방총 위험 = 그 패로 남에게 론당할 어림 확률 · 도라 = 그 패가 도라인 겹수(적5 제외). "-" = 값 없음.

"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=str(S1.parent / 'agent1'))
    a = ap.parse_args()
    out = Path(a.out_dir)
    bdir, pdir = out / 'batches', out / 'private'
    bdir.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)
    for f in bdir.iterdir():
        if f.is_file() and f.name.startswith('batch_') and f.suffix == '.md':
            f.unlink()

    val = set(split.val_games())
    keys, pbin = [], {}
    with open(S1 / 'preds_val.jsonl', encoding='utf-8') as f:
        for line in f:
            p = json.loads(line)
            kk = (p['game'], p['kyoku'], p['seat'], p['k'])
            assert p['game'] in val
            keys.append(kk)
            pbin[kk] = p['bin']
    kset = set(keys)
    joined = {}
    with gzip.open(S1 / 'joined.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r['game'] not in val:
                continue
            kk = (r['game'], r['kyoku'], r['seat'], r['k'])
            if kk in kset:
                joined[kk] = r
    assert len(joined) == len(kset) == 15994, (len(joined), len(kset))
    bin_mismatch = sum(bin_of(joined[kk]) != pbin[kk] for kk in kset)

    rng = random.Random(SEED)
    pool = {b: sorted(kk for kk in kset if bin_of(joined[kk]) == b) for b in BINS}
    chosen = []
    for b in BINS:
        chosen += [(kk, b) for kk in rng.sample(pool[b], PER_BIN)]
    rng.shuffle(chosen)

    logs = {}
    key, texts = {}, {}
    chk = {'1_handCounts': [], '2_drawn': [], '3_k': [], '3_heroMelds': [], '3_riichiSeats': [], '3_scores': [],
           '3_wallLeft': [], '4_actual': [], '5_forbidden': [], 'scoresAfterRiichiDiffer': 0}
    for i, (kk, b) in enumerate(chosen):
        did = f'd{i + 1:03d}'
        game, kyoku, seat, k = kk
        r = joined[kk]
        if game not in logs:
            logs[game] = json.loads(split.log_path(game).read_text(encoding='utf-8'))['log']
        log = logs[game][kyoku]
        ev = to_mjai(log, seat)
        st = replay(ev, seat, k)
        batch = i // BATCH + 1
        key[did] = {'game': game, 'kyoku': kyoku, 'seat': seat, 'k': k, 'bin': b, 'batch': batch}
        # ① 손패
        have = Counter(fold(x) for x in st['hand'])
        want = {c['tile']: c['n'] for c in r['candidates']}
        if dict(have) != want:
            chk['1_handCounts'].append({'d': did, 'replay': dict(have), 'joined': want})
        red_have = {x[1] for x in st['hand'] if x[0] == '0'}
        red_want = {c['tile'][1] for c in r['candidates'] if c.get('red')}
        if red_have != red_want:
            chk['1_handCounts'].append({'d': did, 'redReplay': sorted(red_have), 'redJoined': sorted(red_want)})
        # ②
        if st['lastHero'] != 'tsumo' or st['drawn'] is None or fold(st['drawn']) != r['drawn']:
            chk['2_drawn'].append({'d': did, 'replay': st['drawn'], 'last': st['lastHero'], 'joined': r['drawn']})
        # ③
        if len(st['rivers'][seat]) != k:
            chk['3_k'].append({'d': did, 'replay': len(st['rivers'][seat]), 'k': k})
        if len(st['melds'][seat]) != r['heroMelds']:
            chk['3_heroMelds'].append({'d': did, 'replay': len(st['melds'][seat]), 'joined': r['heroMelds']})
        if sorted(st['riichi']) != sorted(r['riichiSeats']):
            chk['3_riichiSeats'].append({'d': did, 'replay': sorted(st['riichi']), 'joined': r['riichiSeats']})
        if list(st['start']['scores']) != list(r['scores']):
            chk['3_scores'].append({'d': did, 'replay': st['start']['scores'], 'joined': r['scores']})
        if any(st['delta']):
            chk['scoresAfterRiichiDiffer'] += 1
        if 70 - st['tsumo'] != r['wallLeft']:
            chk['3_wallLeft'].append({'d': did, 'replay': 70 - st['tsumo'], 'joined': r['wallLeft']})
        # ④
        act = st['actual']
        if act is None or fold(act) != r['actual'] or (act[0] == '0') != bool(r['actualRed']):
            chk['4_actual'].append({'d': did, 'replay': act, 'joined': r['actual'], 'red': r['actualRed']})
        texts[did] = packet(did, r, st, seat)

    # ⑤ 금지 문자열
    games_all = sorted({kk[0] for kk, _ in chosen})
    banned = set(FORBIDDEN_WORDS)
    for g in games_all:
        banned.add(g)
        banned.update(x for x in g.split('-') if len(x) >= 6)
    for did, t in texts.items():
        hit = sorted(w for w in banned if w in t)
        if hit:
            chk['5_forbidden'].append({'d': did, 'hit': hit})

    for b in range(1, len(chosen) // BATCH + 1):
        ids = [f'd{i:03d}' for i in range((b - 1) * BATCH + 1, b * BATCH + 1)]
        body = HEADER.format(b=b, n=len(ids)) + '\n'.join(texts[d] for d in ids)
        hit = sorted(w for w in banned if w in body)
        if hit:
            chk['5_forbidden'].append({'batch': b, 'hit': hit})
        (bdir / f'batch_{b:02d}.md').write_bytes(body.encode('utf-8'))
    extra = [f.name for f in bdir.iterdir() if not (f.name.startswith('batch_') and f.suffix == '.md')]

    (pdir / 'key.json').write_bytes(json.dumps(key, ensure_ascii=False, indent=1).encode('utf-8') + b'\n')
    summary = {k2: (len(v) if isinstance(v, list) else v) for k2, v in chk.items()}
    report = {'seed': SEED, 'perBin': {b: sum(1 for _, x in chosen if x == b) for b in BINS},
              'poolPerBin': {b: len(pool[b]) for b in BINS}, 'binMismatchVsPreds': bin_mismatch,
              'games': len(games_all), 'batchesExtraFiles': extra, 'mismatchCounts': summary, 'mismatches': chk}
    (pdir / 'check.json').write_bytes(json.dumps(report, ensure_ascii=False, indent=1).encode('utf-8') + b'\n')
    print(json.dumps({k2: report[k2] for k2 in ('perBin', 'poolPerBin', 'binMismatchVsPreds', 'games',
                                                'batchesExtraFiles', 'mismatchCounts')}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
