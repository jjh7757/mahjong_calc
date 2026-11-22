"""Mortal-S42 일괄 채점 — tenhou6 판 × 국 × 자리 → hero 버림 결정마다 JSON 한 줄 (2026-11-21, 설계서 7절 2번).

mortal_local.py 의 to_mjai · decode · ACTION_NAMES 를 가져다 쓴다(복사 아님). 엔진은 프로세스마다 한 번만 읽는다.
깡이 든 국은 tool/tenhou6_features.dart 와 같은 규칙으로 건너뛴다(뽑기 줄에 'm' 든 문자열, 버림 줄에 'a' · 'k' 든 문자열).

줄 맞추기(k): hero 의 dahai 사건을 차례로 센다(리치 뒤 버림 포함 — 값 뽑기 쪽 k 와 같은 셈). 그 dahai 바로 앞의
hero tsumo / chi / pon 사건에서 나온 결정을 붙인다. 리치면 tsumo 결정이 본 결정이고 reach 사건의 결정이 reachQ.
hero 리치 성립 뒤 버림은 결정이 없어 줄을 내지 않는다.

쓰기:
  python -X utf8 s42_batch.py --stage0 [--first N] --procs P --threads T --out s42.jsonl --timing timing.json
  python -X utf8 s42_batch.py --games id1,id2 ...
  python -X utf8 s42_batch.py --dev ...        # 1단계: 개발 200판 전체
  python -X utf8 s42_batch.py --test200 ...    # 2단계: 시험 200판(split.test200_path 로만 연다)
  python -X utf8 s42_batch.py --dev --mask scores|tsumogiri|both ...   # 입력 가림(0단계, 설계서
                                               # docs/paifu_fill_scores_tsumogiri_design_1122.md 3절) — mask_events()
  python -X utf8 s42_batch.py --selftest       # mask_events() 자기 검사(엔진 없이, 개발 앞 2판의 to_mjai 도 씀)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # experiments/paifu_review (mortal_local)
sys.path.insert(0, str(HERE))
from mortal_local import ACTION_NAMES, MORTAL, decode, to_mjai  # noqa: E402,F401
import split  # noqa: E402

HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}
TILE_ACTIONS = set(ACTION_NAMES[:37])  # 34 종류 + 적5 셋
NON_DISCARD = {'Riichi', 'Chi(low)', 'Chi(mid)', 'Chi(high)', 'Pon', 'Kan', 'Hora', 'Ryukyoku', 'Pass'}


def code(mjai_tile: str) -> str:
    """mjai 패 → 우리 코드(적5 는 5 로 접음)."""
    if mjai_tile in HON:
        return HON[mjai_tile]
    return mjai_tile[:2]


def has_kan(log: list) -> bool:
    for p in range(4):
        if any(isinstance(t, str) and 'm' in t for t in log[5 + 3 * p]):
            return True
        if any(isinstance(d, str) and ('a' in d or 'k' in d) for d in log[6 + 3 * p]):
            return True
    return False


MASKS = ('scores', 'tsumogiri', 'both')


def mask_events(events: list[dict], hero: int, mask: str | None) -> tuple[list[dict], int]:
    """to_mjai 사건 목록 → 가린 새 목록 · 바뀐 사건 수. 입력 목록 · 사건은 고치지 않는다(바뀌는 사건만 복사).

    - scores: start_kyoku 의 scores 를 네 자리 25000, kyotaku 를 0 으로(본장은 그대로). 바뀌면 1 로 센다.
    - tsumogiri: hero 아닌 actor 의 dahai 중, 그 actor 가 reach 를 선언한 뒤의 버림(선언패 자체는 빼고 그 다음 버림부터)은
      그대로, 그 밖은 tsumogiri = False(지금 변환의 기본 "손에서 냄"). hero 의 dahai 는 그대로. 값이 바뀐 dahai 수를 센다.
    - both: 둘 다. None: 그대로(같은 목록의 얕은 복사, 0).
    """
    if mask is not None and mask not in MASKS:
        raise ValueError(f'모르는 가림 {mask}')
    do_scores = mask in ('scores', 'both')
    do_tg = mask in ('tsumogiri', 'both')
    out: list[dict] = []
    changed = 0
    declared = [False] * 4   # 그 자리가 reach 를 냈다(선언패 앞)
    after = [False] * 4      # 선언패를 이미 냈다 → 그 뒤 버림은 그대로
    for e in events:
        typ = e.get('type')
        if do_scores and typ == 'start_kyoku':
            ne = dict(e)
            ne['scores'] = [25000, 25000, 25000, 25000]
            ne['kyotaku'] = 0
            if ne['scores'] != list(e['scores']) or ne['kyotaku'] != e['kyotaku']:
                changed += 1
            out.append(ne)
            continue
        if typ == 'reach':
            declared[e['actor']] = True
        if typ == 'dahai':
            a = e['actor']
            keep = a == hero or after[a]
            if declared[a] and not after[a]:
                after[a] = True  # 이 dahai 가 선언패 — 가리고, 다음 버림부터 그대로
            if do_tg and not keep:
                if e.get('tsumogiri'):
                    ne = dict(e)
                    ne['tsumogiri'] = False
                    out.append(ne)
                    changed += 1
                    continue
        out.append(e)
    return out, changed


def _selftest() -> None:
    """mask_events() 자기 검사. 엔진 없이 돈다."""
    syn = [
        {'type': 'start_game', 'names': ['A', 'B', 'C', 'D']},
        {'type': 'start_kyoku', 'bakaze': 'E', 'dora_marker': '1m', 'kyoku': 1, 'honba': 2, 'kyotaku': 1, 'oya': 0,
         'scores': [30000, 20000, 26000, 23000], 'tehais': [['?'] * 13] * 4},
        {'type': 'tsumo', 'actor': 0, 'pai': '1m'}, {'type': 'dahai', 'actor': 0, 'pai': '1m', 'tsumogiri': True},
        {'type': 'tsumo', 'actor': 1, 'pai': '?'}, {'type': 'dahai', 'actor': 1, 'pai': '2m', 'tsumogiri': True},
        {'type': 'tsumo', 'actor': 2, 'pai': '?'}, {'type': 'reach', 'actor': 2},
        {'type': 'dahai', 'actor': 2, 'pai': '3m', 'tsumogiri': True}, {'type': 'reach_accepted', 'actor': 2},
        {'type': 'tsumo', 'actor': 3, 'pai': '?'}, {'type': 'dahai', 'actor': 3, 'pai': '4m', 'tsumogiri': False},
        {'type': 'tsumo', 'actor': 0, 'pai': '5m'}, {'type': 'dahai', 'actor': 0, 'pai': '5m', 'tsumogiri': True},
        {'type': 'tsumo', 'actor': 1, 'pai': '?'}, {'type': 'dahai', 'actor': 1, 'pai': '6m', 'tsumogiri': True},
        {'type': 'tsumo', 'actor': 2, 'pai': '?'}, {'type': 'dahai', 'actor': 2, 'pai': '7m', 'tsumogiri': True},
    ]
    orig = json.dumps(syn)
    same, n0 = mask_events(syn, 0, None)
    assert same == syn and n0 == 0
    s, ns = mask_events(syn, 0, 'scores')
    assert s[1]['scores'] == [25000] * 4 and s[1]['kyotaku'] == 0 and s[1]['honba'] == 2 and ns == 1
    assert [x for i, x in enumerate(s) if i != 1] == [x for i, x in enumerate(syn) if i != 1]
    t, nt = mask_events(syn, 0, 'tsumogiri')
    tg = [(x['actor'], x['pai'], x['tsumogiri']) for x in t if x['type'] == 'dahai']
    # hero(0) 그대로 · 1 은 가림 · 2 의 선언패(3m)는 가림 · 2 의 리치 뒤(7m)는 그대로 · 3 은 원래 False
    assert tg == [(0, '1m', True), (1, '2m', False), (2, '3m', False), (3, '4m', False), (0, '5m', True),
                  (1, '6m', False), (2, '7m', True)], tg
    assert nt == 3 and t[1] == syn[1]
    b, nb = mask_events(syn, 0, 'both')
    assert nb == 4 and b[1]['scores'] == [25000] * 4
    assert json.dumps(syn) == orig, '입력 목록이 바뀜'
    # 실제 판: 개발 앞 2판(split.dev_games()[:2])의 모든 국 · 자리
    tot = {'kyokuSeats': 0, 'dahai': 0, 'tsumogiriChanged': 0, 'heroDahai': 0, 'afterReachKept': 0}
    for g in split.dev_games()[:2]:
        for log in json.loads(split.log_path(g).read_text(encoding='utf-8'))['log']:
            if has_kan(log):
                continue
            for seat in range(4):
                ev = to_mjai(log, seat)
                assert mask_events(ev, seat, None)[0] == ev
                mt, n = mask_events(ev, seat, 'tsumogiri')
                assert len(mt) == len(ev)
                diff = 0
                reached, decl_done = [False] * 4, [False] * 4
                for x, y in zip(ev, mt):
                    if x['type'] == 'reach':
                        reached[x['actor']] = True
                    if x != y:
                        diff += 1
                        assert x['type'] == 'dahai' and x['actor'] != seat and x['tsumogiri'] and not y['tsumogiri']
                        assert {k: v for k, v in x.items() if k != 'tsumogiri'} == {k: v for k, v in y.items() if k != 'tsumogiri'}
                    if x['type'] == 'dahai':
                        tot['dahai'] += 1
                        if x['actor'] == seat:
                            tot['heroDahai'] += 1
                            assert x == y, 'hero dahai 가 바뀜'
                        elif decl_done[x['actor']]:
                            tot['afterReachKept'] += 1
                            assert x == y, '리치 뒤 dahai 가 바뀜'
                        if reached[x['actor']]:
                            decl_done[x['actor']] = True
                assert diff == n
                tot['tsumogiriChanged'] += n
                ms, n2 = mask_events(ev, seat, 'scores')
                assert n2 in (0, 1) and sum(x != y for x, y in zip(ev, ms)) == n2
                tot['kyokuSeats'] += 1
    print('자기 검사 통과', json.dumps(tot, ensure_ascii=False))


_ENGINE = None
_LOAD_SECS = None
_MASK = None


def _init(threads: int, mask: str | None = None):
    global _ENGINE, _LOAD_SECS, _MASK
    _MASK = mask
    import torch
    torch.set_num_threads(threads)
    sys.path.insert(0, str(MORTAL))
    from inference import load_engine  # noqa: E402
    t0 = time.perf_counter()
    _ENGINE = load_engine('cpu')
    _LOAD_SECS = time.perf_counter() - t0


def _decision(meta: dict) -> dict:
    cands = decode(meta)
    q = {n: v for n, v in cands}
    top = max(cands, key=lambda x: x[1])[0]
    best = None
    for n, v in cands:
        if n in NON_DISCARD or n not in TILE_ACTIONS:
            continue
        c = code(n)
        if best is None or v > best[1]:
            best = (c, v)
    return {'q': q, 'topAction': top, 's42Discard': best[0] if best else None,
            's42DiscardQ': best[1] if best else None, 'shanten': meta.get('shanten')}


def run_kyoku_seat(game: str, ki: int, log: list, seat: int) -> tuple[list[dict], dict]:
    from inference import Session  # noqa: E402  (_init 이 MORTAL 을 경로에 넣음)
    t0 = time.perf_counter()
    events = to_mjai(log, seat)
    masked = 0
    if _MASK is not None:
        events, masked = mask_events(events, seat, _MASK)
    s = Session(_ENGINE, seat)
    rows = []
    dec_secs = []
    pending = None   # (trigger, decision, secs)
    reach_dec = None
    k = 0
    hero_reached = False
    reach_seen = False  # 이 dahai 바로 앞 hero 사건이 reach
    for e in events:
        t1 = time.perf_counter()
        r = s.react(e)
        dt = time.perf_counter() - t1
        meta = r.get('meta') if r else None
        if meta is not None:
            dec_secs.append(dt)
        if e.get('actor') != seat:
            continue
        typ = e['type']
        if typ in ('tsumo', 'chi', 'pon'):
            pending = (typ, _decision(meta) if meta else None, dt if meta else None)
            reach_dec = None
            reach_seen = False
        elif typ == 'reach':
            reach_dec = _decision(meta) if meta else None
            reach_seen = True
        elif typ == 'dahai':
            riichi_decl = reach_seen
            if not hero_reached:
                trig, dec, secs = pending if pending else (None, None, None)
                row = {'game': game, 'kyoku': ki, 'seat': seat, 'k': k, 'trigger': trig,
                       'actual': code(e['pai']), 'actualRiichi': riichi_decl,
                       'q': dec['q'] if dec else None, 'topAction': dec['topAction'] if dec else None,
                       's42Discard': dec['s42Discard'] if dec else None,
                       's42DiscardQ': dec['s42DiscardQ'] if dec else None,
                       'reachQ': reach_dec['q'] if reach_dec else None,
                       'shanten': dec['shanten'] if dec else None, 'secs': secs}
                rows.append(row)
            if riichi_decl:
                hero_reached = True
            k += 1
            pending = None
            reach_dec = None
            reach_seen = False
    info ={'game': game, 'kyoku': ki, 'seat': seat, 'secs': time.perf_counter() - t0,
            'decisions': len(dec_secs), 'decSecs': dec_secs, 'rows': len(rows)}
    if _MASK is not None:
        info['maskChanged'] = masked
    return rows, info


def _path_fn(which: str):
    """'dev' → split.log_path(개발 판만), 'test200' → split.test200_path(시험 200판만)."""
    return {'dev': split.log_path, 'test200': split.test200_path}[which]


def run_task(task: tuple) -> dict:
    """한 판의 한 국(네 자리). 작업 단위를 국으로 잘게 해 프로세스 여럿에 고르게 나눈다.
    task = (game, ki) 또는 (game, ki, which) — which 는 _path_fn 의 열쇠(없으면 'dev')."""
    game, ki = task[0], task[1]
    which = task[2] if len(task) > 2 else 'dev'
    t_cpu = time.process_time()
    t_wall = time.perf_counter()
    log = json.loads(_path_fn(which)(game).read_text(encoding='utf-8'))['log'][ki]
    rows, infos, errors = [], [], []
    kan = 0
    if has_kan(log):
        kan = 1
    else:
        for seat in range(4):
            try:
                r, info = run_kyoku_seat(game, ki, log, seat)
            except Exception as err:  # 변환 · 엔진 오류는 그 국 · 자리를 오류로 센다
                errors.append(f'{game} 국 {ki} 자리 {seat}: {type(err).__name__}: {err}')
                continue
            rows.extend(r)
            infos.append(info)
    return {'game': game, 'kyoku': ki, 'rows': rows, 'infos': infos, 'errors': errors, 'kyokus': 1,
            'kanSkipped': kan, 'cpu': time.process_time() - t_cpu, 'wall': time.perf_counter() - t_wall,
            'loadSecs': _LOAD_SECS, 'pid': os.getpid()}


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def stats(xs: list[float]) -> dict:
    return {'n': len(xs), 'median': statistics.median(xs) if xs else None, 'p90': pct(xs, 0.9),
            'max': max(xs) if xs else None, 'sum': sum(xs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage0', action='store_true')
    ap.add_argument('--dev', action='store_true', help='개발 200판 전체(1단계)')
    ap.add_argument('--test200', action='store_true', help='시험 200판(2단계, 설계서 12절) — split.test200_path 로만 연다')
    ap.add_argument('--games')
    ap.add_argument('--first', type=int)
    ap.add_argument('--procs', type=int, default=1)
    ap.add_argument('--threads', type=int, default=16)
    ap.add_argument('--out')
    ap.add_argument('--timing')
    ap.add_argument('--mask', choices=MASKS, help='입력 가림(없으면 지금과 같음) — mask_events() 참고')
    ap.add_argument('--selftest', action='store_true', help='mask_events() 자기 검사만 하고 끝')
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return
    if a.mask and a.test200:
        raise SystemExit('--mask 는 개발 판에만(0단계 설계서: 시험 판은 열지 않음)')
    if a.test200:
        games, which = split.test200_games(), 'test200'
    else:
        games = split.stage0_games() if a.stage0 else (split.dev_games() if a.dev else a.games.split(','))
        which = 'dev'
    if a.first:
        games = games[:a.first]
    allowed = set(split.test200_games()) if which == 'test200' else set(split.dev_games())
    assert all(g in allowed for g in games), '개발 200판(또는 --test200 이면 시험 200판) 밖의 판'
    path_fn = _path_fn(which)
    tasks = [(g, ki) if which == 'dev' else (g, ki, which) for g in games
             for ki in range(len(json.loads(path_fn(g).read_text(encoding='utf-8'))['log']))]
    t0 = time.perf_counter()
    results = []
    if a.procs == 1:
        _init(a.threads, a.mask)
        results = [run_task(t) for t in tasks]
    else:
        # 국 단위로 잘게 나눠 chunksize 1 로 돌린다(판 단위면 판 수보다 많은 프로세스가 놀았음).
        with ProcessPoolExecutor(a.procs, initializer=_init, initargs=(a.threads, a.mask)) as ex:
            results = list(ex.map(run_task, tasks, chunksize=1))
    wall = time.perf_counter() - t0
    results.sort(key=lambda r: (r['game'], r['kyoku']))
    if a.out:
        with open(a.out, 'w', encoding='utf-8', newline='\n') as f:
            for r in results:
                for row in r['rows']:
                    f.write(json.dumps(row, ensure_ascii=False) + '\n')
    ks = [i['secs'] for r in results for i in r['infos']]
    dec = [x for r in results for i in r['infos'] for x in i['decSecs']]
    loads = sorted({(r['pid'], r['loadSecs']) for r in results})
    timing = {'procs': a.procs, 'threads': a.threads, 'games': len(games), 'wall': wall,
              'cpu': sum(r['cpu'] for r in results),
              'modelLoad': [x for _, x in loads], 'kyokuSeat': stats(ks), 'decision': stats(dec),
              'rows': sum(len(r['rows']) for r in results),
              'kyokus': sum(r['kyokus'] for r in results), 'kanSkipped': sum(r['kanSkipped'] for r in results),
              'errors': sum(len(r['errors']) for r in results),
              'errorList': [e for r in results for e in r['errors']]}
    if a.mask:
        timing['mask'] = a.mask
        timing['maskChanged'] = sum(i.get('maskChanged', 0) for r in results for i in r['infos'])
    print(json.dumps({k: v for k, v in timing.items() if k != 'errorList'}, ensure_ascii=False))
    for e in timing['errorList']:
        print('  오류', e)
    if a.timing:
        Path(a.timing).write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
