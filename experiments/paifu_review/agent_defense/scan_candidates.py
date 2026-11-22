"""복기 에이전트 수비 확장 2단계 평가 재료 후보 — 검증 40판에서 남이 리치한 뒤 hero 버림이 3번 이상인 (판, 국, 자리).

  python -X utf8 experiments/paifu_review/agent_defense/scan_candidates.py     (저장소 뿌리에서)

설계서 docs/paifu_review_agent_defense_design_1122.md 3절. 판 고르기는 사람이 한다 — 이 스크립트는 후보 목록만 낸다(사실표는 안 만듦).

- 판: 맞추기 실험의 검증 40판(split.val_games() = 개발 200판 ID 순 뒤 40). 로그는 split.log_path 로만 연다(시험 판은 열지 않음).
- 버림: results/mxfit/stage1/joined.jsonl.gz 의 줄(= hero 가 고른 버림, hero 리치 뒤 버림은 joined 에 없음) 중
  riichiSeats(남의 리치)가 비지 않은 것. 이것이 3번 이상인 국 · 자리만.
  참고로 hero 리치 뒤 버림(고를 수 없는 차례) 중 남의 리치가 있는 것의 수(n_forced)는 같은 폴더 features/<판>.jsonl.gz 에서 센다.
- 방총: pushfold/risk_calibration.py 와 같은 판정 — 국 결과가 和了 이고 [화료자, 방총자, …] 쌍 중 방총자가 그 자리 · 화료자가 아님.
  dealt_on_choice: 방총이고 그 국 hero 마지막 버림(k = 버림 수 − 1)이 위 고른 버림 줄에 있음(고른 패로 쏘임).
- 깡: tool/tenhou6_features.dart hasKan 과 같은 판정(뽑기 줄에 m · 버림 줄에 a · k 든 문자열). 깡 든 국은 뺀다
  (값 뽑기가 이미 건너뛰어 joined 에 없지만 다시 확인해 kan_skipped 로 센다).

출력: results/agent_defense/candidates.json — {"summary": {...}, "candidates": [줄, ...]}.
"""
import gzip
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PR, 'mxfit'))
import split  # noqa: E402

D = os.path.join(PR, 'results', 'mxfit', 'stage1')
OUT = os.path.join(PR, 'results', 'agent_defense', 'candidates.json')
MIN_DISCARDS = 3


def has_kan(kyoku: list) -> bool:
    for p in range(4):
        if any(isinstance(t, str) and 'm' in t for t in kyoku[5 + 3 * p]):
            return True
        if any(isinstance(d, str) and ('a' in d or 'k' in d) for d in kyoku[6 + 3 * p]):
            return True
    return False


def result_of(kyoku: list, seat: int) -> tuple[bool, bool, str]:
    """(그 자리가 방총, 그 자리가 화료, 결과 이름)."""
    res = kyoku[-1]
    if not res or res[0] != '和了':
        return False, False, (res[0] if res else '')
    dealt = won = False
    for i in range(2, len(res), 2):  # [점수 변화], [화료자, 방총자, …] 가 되풀이(더블 론)
        info = res[i]
        if info[0] == seat:
            won = True
        if info[0] != info[1] and info[1] == seat:
            dealt = True
    return dealt, won, '和了'


def main():
    val = split.val_games()
    vset = set(val)
    rows = defaultdict(list)  # (game, kyoku, seat) → joined 줄(남의 리치가 있는 고른 버림)
    with gzip.open(os.path.join(D, 'joined.jsonl.gz'), 'rt', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r['game'] not in vset or not r.get('riichiSeats') or r.get('afterRiichi'):
                continue
            rows[(r['game'], r['kyoku'], r['seat'])].append(r)

    forced = Counter()  # hero 리치 뒤 버림 중 남의 리치가 있는 것
    for game in val:
        path = os.path.join(D, 'features', f'{game}.jsonl.gz')
        if not os.path.exists(path):
            continue
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line in f:
                r = json.loads(line)
                if 'summary' in r:
                    continue
                if r.get('afterRiichi') and r.get('riichiSeats'):
                    forced[(r['game'], r['kyoku'], r['seat'])] += 1

    logs = {}
    cands, kan_skipped = [], 0
    for key in sorted(k for k, v in rows.items() if len(v) >= MIN_DISCARDS):
        game, ki, seat = key
        if game not in logs:
            logs[game] = json.load(open(split.log_path(game), encoding='utf-8'))['log']
        kyoku = logs[game][ki]
        if has_kan(kyoku):
            kan_skipped += 1
            continue
        rs = sorted(rows[key], key=lambda r: r['k'])
        dealt, won, res = result_of(kyoku, seat)
        n_disc = len(kyoku[6 + 3 * seat])
        cands.append({
            'game': game, 'kyoku': ki, 'kyokuNum': rs[0]['kyokuNum'], 'honba': rs[0]['honba'], 'seat': seat,
            'n_discards': len(rs),
            'turns': [r['k'] + 1 for r in rs],                 # hero 몇 번째 버림(1부터) = 사실표 turn
            'shanten': [r['shantenBefore'] for r in rs],       # 버리기 전(뽑은 패 포함) 샹텐
            'riichi_seats': sorted({s for r in rs for s in r['riichiSeats']}),
            'n_forced': forced[key],
            'dealt_in': dealt,
            'dealt_on_choice': dealt and rs[-1]['k'] == n_disc - 1,
            'won': won,
            'result': res,
            'kan': False,
        })

    def sh_bucket(c):
        return min(max(min(c['shanten']), 0), 2)  # 그 국 수비 버림 중 가장 낮은 샹텐: 0 텐파이 · 1 · 2 이상

    summary = {
        'val_games': len(val),
        'games_with_candidates': len({c['game'] for c in cands}),
        'candidates': len(cands),
        'kan_skipped': kan_skipped,
        'dealt_in': sum(c['dealt_in'] for c in cands),
        'dealt_on_choice': sum(c['dealt_on_choice'] for c in cands),
        'not_dealt_in': sum(not c['dealt_in'] for c in cands),
        'won': sum(c['won'] for c in cands),
        'n_discards': dict(sorted(Counter(min(c['n_discards'], 10) for c in cands).items())),
        'min_shanten(0=텐파이,2=2이상)': dict(sorted(Counter(sh_bucket(c) for c in cands).items())),
        'discard_shanten(전체 버림)': dict(sorted(Counter(min(max(s, 0), 3) for c in cands for s in c['shanten']).items())),
        'dealt_by_min_shanten': {str(b): {'dealt': sum(c['dealt_in'] for c in cands if sh_bucket(c) == b),
                                          'not': sum(not c['dealt_in'] for c in cands if sh_bucket(c) == b)}
                                 for b in (0, 1, 2)},
        'with_forced': sum(c['n_forced'] > 0 for c in cands),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'summary': summary, 'candidates': cands}, f, ensure_ascii=False, indent=1)
        f.write('\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f'→ {OUT}')


if __name__ == '__main__':
    main()
