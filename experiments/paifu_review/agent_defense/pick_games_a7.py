"""복기 에이전트 지시문 a7 · 사실표 3 측정 준비 — 판 고르기 + 사실표 만들기(설계서 docs/review_agent_foldspot_scores_design_1123.md 5절).

  python -X utf8 experiments/paifu_review/agent_defense/pick_games_a7.py        (저장소 뿌리에서)

고르는 규칙(답을 보기 전에 고정, 2026-11-23 밤):
- 묶음 F(접는 자리, 새 안 본 판 4국): 후보 = results/pushfold/test2_rows.jsonl(시험 2 200판의 결정 줄) 중 규칙 R3 이 잡은 줄을
  (판, 국, 자리)로 묶은 국. 그 국의 "첫 접는 자리" = R3 줄 중 k 가 가장 작은 것(차례 번호 N = k + 1).
  - 뺌: 깡 든 국(tenhou6_features.dart hasKan 과 같은 검사) · hero 가 그 국에서 리치한 국(hero 버림 칸에 'r' 로 시작하는 값) ·
    이미 복기 에이전트 측정에 쓴 판(results/agent_defense/picked.json).
  - 두 묶음: 첫 접는 자리에서 player == 'push'(민 국) / player == 'fold'(접은 국). 'mid' 는 어느 묶음에도 안 넣음.
  - 각 묶음을 (판, 국, 자리) 순으로 정렬 → random.Random(20261123) 하나로 민 국 묶음, 접은 국 묶음 순서로 섞음.
  - 앞에서부터, 판이 겹치지 않게 민 국 2(fa1 · fa2) · 접은 국 2(fa3 · fa4). 후보마다 tool/tenhou6_agent_facts.dart 로 사실표를
    만들고 확인: 그 차례(turn N)의 버림이 pf 줄의 actualTile 과 같고 · defense.fold_spot 이 객체이고 · stance 가 pushed(민 국) /
    folded(접은 국). 안 맞거나 도구가 거절하면 그 후보는 건너뛰고(까닭을 picked_a7.json 의 skipped 에) 다음 후보.
- 묶음 G(점수): ga1 · ga2 = assets/paifu_h3/ 이름 순 앞 둘(tool/paifu_agent_facts.dart — 앱과 같은 엔진 켬 리뷰),
  ga3 · ga4 = F 의 "접은 국" 섞은 순서에서 F 에 쓴 마지막 후보 다음부터, F 의 판 · 서로와 판이 안 겹치는 둘(도구가 거절하거나
  game.scores 가 null 이면 건너뜀 — 접는 자리 확인은 하지 않음). gb1 = assets/paifu/r19_142013.json(점수 없는 판).
- 묶음 H(되돌아보기): agent_questions_1123_tone.json 의 판을 새 앱(사실표 3)으로 다시 만듦 — 천봉 dx1..dx4 는 picked.json 의
  판 · 국 · 자리로 tenhou6_agent_facts.dart, 매장 판은 assets/paifu/<이름>.json 을 paifu_agent_facts.dart 로.
  원래 쓰던 판 2 사실표(dx = results/agent_defense/facts/, 매장 = mahjong-recognizer-a5 의 tests/fixtures/agent_facts/ —
  a5 · a6 두 서버가 같은 fixture 를 썼다고 보고 a5 쪽을 읽음; mahjong-recognizer-review 는 읽지 않음)와
  version · game.scores · defense.fold_spot 을 뺀 나머지가 같은지 대조해 compare_h.json 에 적는다.

출력: results/agent_1123a7/facts/<익명 id 또는 판 이름>.json(들여쓰기 2칸) · picked_a7.json(판 ID 는 여기에만) · compare_h.json ·
      facts/_tried/<묶음>_<번호>.json(확인하다 건너뛴 후보의 사실표).
"""
import json
import os
import random
import shutil
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)  # experiments/paifu_review
ROOT = os.path.dirname(os.path.dirname(PR))
sys.path.insert(0, os.path.join(PR, 'mxfit'))
import split  # noqa: E402

DART = r'C:\Users\jjh7757\flutter\bin\dart.bat'
SEED = 20261123
N_TEST2 = 200
OUT = os.path.join(PR, 'results', 'agent_1123a7')
FACTS = os.path.join(OUT, 'facts')
TRIED = os.path.join(FACTS, '_tried')
PF_ROWS = os.path.join(PR, 'results', 'pushfold', 'test2_rows.jsonl')
OLD_PICKED = os.path.join(PR, 'results', 'agent_defense', 'picked.json')
OLD_DX = os.path.join(PR, 'results', 'agent_defense', 'facts')
OLD_STORE = r'C:\Users\jjh7757\dev\mahjong-recognizer-a5\tests\fixtures\agent_facts'
H_STORE = ['r19_142013', 'L16_135321', 'r11_130921', 'r12_131655', 'r15_134151', 'r16_135321', 'r13_132644',
           'r18_141259', 'r20_143236', 'r17_140450']
H_DX = ['dx1', 'dx2', 'dx3', 'dx4']
LIMIT = 200 * 1024  # 서버 사실표 한도(압축 JSON bytes)


_TEST2: set[str] = set()


def test2_path(game: str) -> str:
    """pushfold/pf_s42.test2_path 와 같음(그 모듈은 s42_batch 를 불러 무거워 여기서 다시 씀). 판 목록은 한 번만 만든다
    (split.test599_games 가 부를 때마다 10MB 기록을 다시 읽음)."""
    if not _TEST2:
        _TEST2.update(split.test599_games()[:N_TEST2])
    if game not in _TEST2:
        raise ValueError(f'시험 2(599판 앞 200판) 밖의 판: {game}')
    return str(split.LOGS / f'{game}.json')


def has_kan(log: list) -> bool:
    for p in range(4):
        if any(isinstance(t, str) and 'm' in t for t in log[5 + 3 * p]):
            return True
        if any(isinstance(d, str) and ('a' in d or 'k' in d) for d in log[6 + 3 * p]):
            return True
    return False


def hero_riichi(log: list, seat: int) -> bool:
    return any(isinstance(d, str) and d.startswith('r') for d in log[6 + 3 * seat])


def dart(args: list, out: str) -> tuple[bool, str]:
    r = subprocess.run([DART, 'run', *args, out], cwd=ROOT, capture_output=True)
    err = r.stderr.decode('utf-8', 'replace').strip()
    if r.returncode != 0 or not os.path.exists(out):
        return False, f'rc {r.returncode}: {err[-400:]}'
    return True, err[-300:]


def load(path: str) -> dict:
    return json.load(open(path, encoding='utf-8'))


def compact_size(d: dict) -> int:
    return len(json.dumps(d, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def fold_turns(f: dict) -> list[dict]:
    out = []
    for t in f['turns']:
        df = t.get('defense')
        if df and isinstance(df.get('fold_spot'), dict):
            out.append({'turn': t['turn'], 'discard': t['discard'], 'stance': df.get('stance'), 'fold_spot': df['fold_spot']})
    return out


def kyoku_candidates() -> tuple[list[dict], list[dict], dict]:
    by = defaultdict(list)
    n_r3 = 0
    with open(PF_ROWS, encoding='utf-8') as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if r['R3']:
                n_r3 += 1
                by[(r['game'], r['kyoku'], r['seat'])].append(r)
    used_old = {p['game'] for p in json.load(open(OLD_PICKED, encoding='utf-8'))}
    stats = {'r3_rows': n_r3, 'kyoku': len(by), 'kan': 0, 'hero_riichi': 0, 'old_overlap': 0, 'mid': 0}
    logs = {}
    push, fold = [], []
    for (game, kyoku, seat), rows in sorted(by.items()):
        if game in used_old:
            stats['old_overlap'] += 1
            continue
        if game not in logs:
            logs[game] = json.load(open(test2_path(game), encoding='utf-8'))
        log = logs[game]['log'][kyoku]
        if has_kan(log):
            stats['kan'] += 1
            continue
        if hero_riichi(log, seat):
            stats['hero_riichi'] += 1
            continue
        rows.sort(key=lambda r: r['k'])
        first = rows[0]
        c = {'game': game, 'kyoku': kyoku, 'seat': seat, 'turn': first['k'] + 1, 'player': first['player'],
             'actualTile': first['actualTile'], 'effTile': first['effTile'], 'shantenBefore': first['shantenBefore'],
             'pf_r3_turns': [{'turn': r['k'] + 1, 'player': r['player'], 'actualTile': r['actualTile']} for r in rows]}
        if first['player'] == 'push':
            push.append(c)
        elif first['player'] == 'fold':
            fold.append(c)
        else:
            stats['mid'] += 1
    stats['push'] = len(push)
    stats['fold'] = len(fold)
    return push, fold, stats


def check_f(f: dict, c: dict, want: str) -> str:
    """확인 통과면 '', 아니면 까닭."""
    t = next((t for t in f['turns'] if t['turn'] == c['turn']), None)
    if t is None:
        return f"사실표에 {c['turn']}번째 차례가 없음"
    if t['discard'] != c['actualTile']:
        return f"{c['turn']}번째 버림 {t['discard']} ≠ pf 줄 {c['actualTile']}"
    df = t.get('defense')
    if not df:
        return f"{c['turn']}번째 defense 가 null"
    if not isinstance(df.get('fold_spot'), dict):
        return f"{c['turn']}번째 fold_spot 이 {df.get('fold_spot')!r}"
    if df.get('stance') != want:
        return f"{c['turn']}번째 stance {df.get('stance')} ≠ {want}(pf player {c['player']})"
    return ''


def main():
    os.makedirs(TRIED, exist_ok=True)
    push, fold, stats = kyoku_candidates()
    rng = random.Random(SEED)
    rng.shuffle(push)
    rng.shuffle(fold)
    print('F 후보:', json.dumps(stats, ensure_ascii=False))
    picked, skipped, used = [], [], set()
    fold_next = 0
    for label, pool, want, ids in (('push', push, 'pushed', ['fa1', 'fa2']), ('fold', fold, 'folded', ['fa3', 'fa4'])):
        idx = 0
        for aid in ids:
            while True:
                if idx >= len(pool):
                    sys.exit(f'F {label} 후보가 모자람({len(pool)}개)')
                c = pool[idx]
                idx += 1
                if c['game'] in used:
                    continue
                tried = os.path.join(TRIED, f'{label}_{idx:02d}.json')
                ok, msg = dart(['tool/tenhou6_agent_facts.dart', test2_path(c['game']), str(c['kyoku']), str(c['seat'])], tried)
                why = ('도구 거절 ' + msg) if not ok else check_f(load(tried), c, want)
                if why:
                    skipped.append(dict(c, bundle='F', group=label, order=idx, reason=why, tried=os.path.relpath(tried, ROOT).replace('\\', '/') if ok else None))
                    print('  건너뜀', label, idx, why)
                    continue
                dst = os.path.join(FACTS, f'{aid}.json')
                shutil.move(tried, dst)
                used.add(c['game'])
                f = load(dst)
                picked.append(dict(c, id=aid, bundle='F', group=label, order=idx, fold_turns=fold_turns(f),
                                   facts=os.path.relpath(dst, ROOT).replace('\\', '/'), bytes=os.path.getsize(dst), compact=compact_size(f)))
                print(' ', aid, label, '섞은 순서', idx, '·', c['turn'], '번째', fold_turns(f))
                break
        if label == 'fold':
            fold_next = idx
    # G: 접은 국 섞은 순서에서 F 다음.
    idx = fold_next
    for aid in ('ga3', 'ga4'):
        while True:
            if idx >= len(fold):
                sys.exit('G 천봉 후보가 모자람')
            c = fold[idx]
            idx += 1
            if c['game'] in used:
                continue
            dst = os.path.join(FACTS, f'{aid}.json')
            ok, msg = dart(['tool/tenhou6_agent_facts.dart', test2_path(c['game']), str(c['kyoku']), str(c['seat'])], dst)
            why = ('도구 거절 ' + msg) if not ok else ('' if load(dst)['game'].get('scores') else 'game.scores 가 null')
            if why:
                skipped.append(dict(c, bundle='G', group='fold', order=idx, reason=why))
                print('  G 건너뜀', idx, why)
                continue
            used.add(c['game'])
            f = load(dst)
            picked.append(dict(c, id=aid, bundle='G', group='fold', order=idx, fold_turns=fold_turns(f),
                               facts=os.path.relpath(dst, ROOT).replace('\\', '/'), bytes=os.path.getsize(dst), compact=compact_size(f)))
            print(' ', aid, 'G 천봉 · 섞은 순서', idx)
            break
    h3 = sorted(n for n in os.listdir(os.path.join(ROOT, 'assets', 'paifu_h3')) if n.endswith('.json'))[:2]
    store = [('ga1', f'assets/paifu_h3/{h3[0]}'), ('ga2', f'assets/paifu_h3/{h3[1]}'), ('gb1', 'assets/paifu/r19_142013.json')]
    for aid, src in store:
        dst = os.path.join(FACTS, f'{aid}.json')
        ok, msg = dart(['tool/paifu_agent_facts.dart', src], dst)
        if not ok:
            sys.exit(f'{aid} 사실표 실패: {msg}')
        f = load(dst)
        picked.append({'id': aid, 'bundle': 'G', 'source': src, 'scores': f['game'].get('scores'), 'fold_turns': fold_turns(f),
                       'facts': os.path.relpath(dst, ROOT).replace('\\', '/'), 'bytes': os.path.getsize(dst), 'compact': compact_size(f)})
        print(' ', aid, src, '점수', 'null' if f['game'].get('scores') is None else '있음')
    # H: 다시 만들기 · 대조.
    old = {p['id']: p for p in json.load(open(OLD_PICKED, encoding='utf-8'))}
    compare = []
    for name in H_DX + H_STORE:
        dst = os.path.join(FACTS, f'{name}.json')
        if name in old:
            p = old[name]
            args = ['tool/tenhou6_agent_facts.dart', str(split.log_path(p['game'])), str(p['kyoku']), str(p['seat'])]
            v2 = os.path.join(OLD_DX, f'{name}.json')
        else:
            args = ['tool/paifu_agent_facts.dart', f'assets/paifu/{name}.json']
            v2 = os.path.join(OLD_STORE, f'{name}.json')
        ok, msg = dart(args, dst)
        if not ok:
            sys.exit(f'H {name} 사실표 실패: {msg}')
        f3, f2 = load(dst), load(v2)
        diffs = diff(strip(f2), strip(f3), '')
        row = {'name': name, 'v2': v2.replace('\\', '/'), 'v2_version': f2.get('version'), 'v3_version': f3.get('version'),
               'scores': f3['game'].get('scores'), 'fold_turns': fold_turns(f3),
               'v2_fold_spot_values': sorted({json.dumps((t.get('defense') or {}).get('fold_spot', '없음'))
                                              for t in f2['turns'] if t.get('defense')}),
               'n_diffs': len(diffs), 'diffs': diffs[:40], 'bytes': os.path.getsize(dst), 'compact': compact_size(f3)}
        compare.append(row)
        print(' H', name, '차이', len(diffs), '· 접는 자리', [x['turn'] for x in row['fold_turns']], '· 점수', 'null' if row['scores'] is None else '있음')
    meta = {'seed': SEED, 'f_stats': stats, 'f_push_order': [(c['game'], c['kyoku'], c['seat']) for c in push[:12]],
            'f_fold_order': [(c['game'], c['kyoku'], c['seat']) for c in fold[:12]]}
    open(os.path.join(OUT, 'picked_a7.json'), 'wb').write(
        json.dumps({'meta': meta, 'picked': picked, 'skipped': skipped}, ensure_ascii=False, indent=1).encode('utf-8'))
    open(os.path.join(OUT, 'compare_h.json'), 'wb').write(json.dumps(compare, ensure_ascii=False, indent=1).encode('utf-8'))
    big = [n for n in os.listdir(FACTS) if n.endswith('.json') and compact_size(load(os.path.join(FACTS, n))) > LIMIT]
    print('200KB 넘는 사실표:', big or '없음')


def strip(f: dict) -> dict:
    """대조에서 뺄 칸: version · game.scores · turns[*].defense.fold_spot."""
    g = json.loads(json.dumps(f))
    g.pop('version', None)
    g['game'].pop('scores', None)
    for t in g['turns']:
        if t.get('defense'):
            t['defense'].pop('fold_spot', None)
    return g


def diff(a, b, path: str) -> list[str]:
    if type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        return [f'{path}: {json.dumps(a, ensure_ascii=False)[:120]} → {json.dumps(b, ensure_ascii=False)[:120]}']
    if isinstance(a, dict):
        out = []
        for k in list(a) + [k for k in b if k not in a]:
            if k not in a:
                out.append(f'{path}.{k}: (없음) → {json.dumps(b[k], ensure_ascii=False)[:120]}')
            elif k not in b:
                out.append(f'{path}.{k}: {json.dumps(a[k], ensure_ascii=False)[:120]} → (없음)')
            else:
                out += diff(a[k], b[k], f'{path}.{k}')
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f'{path}: 길이 {len(a)} → {len(b)}']
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f'{path}[{i}]')
        return out
    return [] if a == b else [f'{path}: {json.dumps(a, ensure_ascii=False)} → {json.dumps(b, ensure_ascii=False)}']


if __name__ == '__main__':
    main()
