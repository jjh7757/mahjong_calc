"""탁자 사실표(table_facts) 독립 대조 — Python 표준 라이브러리만.

Dart 구현(lib/paifu/table_facts.dart · tool/table_facts.dart)을 보지 않고 같은 정의 글로 따로 계산해
Dart 출력과 칸마다 맞춘다.

  python -I -X utf8 experiments/paifu_review/agent_defense/table_facts_check.py compute
  python -I -X utf8 experiments/paifu_review/agent_defense/table_facts_check.py compare experiments/paifu_review/results/table_facts/dart

compute: assets/paifu/*.json + assets/paifu_h3/*.json → results/table_facts/py/<같은 이름>.json
compare: <dart폴더>/<같은 이름>.json 과 칸마다 대조. level 은 계산하지 않고 ① 다섯 말 중 하나인지
         ② Dart level 로 장면 고르기를 다시 해 Dart scenes_by_seat 와 같은지만 본다.

정의에서 글 그대로 따른 곳(모호 — 바꾸지 않음):
- 자리 바람 = (seat − dealer) mod 4 → 동남서북. 그래서 game.dealer_wind 는 늘 "동".
- 울기로 가져간 버림 = call 의 from 자리가 그 call 바로 앞에 한 마지막 버림. kakan(from=자기)도 글 그대로
  자기 마지막 버림을 강에서 빼고, 묶음 4장을 더한다(앞 pon 3장과 겹침). → 아래 KAKAN_LITERAL.
- 적5(0m·0p·0s)는 5 로 바꿔 셈하고 출력에도 5 로 쓴다.
- risky_after_riichi 정렬의 "매우 높음 먼저" 는 그 버림에서 조건(genbutsu false · 높음 이상)을 채운 R 들 중 가장 높은 level.
- deal_in 은 X 의 버림 중 tile == win_tile 인 마지막 것.
- result 가 없는 패보(r20)는 game.result = null.
"""
import glob
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
OUT_PY = os.path.join(ROOT, 'experiments', 'paifu_review', 'results', 'table_facts', 'py')
WINDS = ['동', '남', '서', '북']
LEVELS = ['안전', '낮음', '보통', '높음', '매우 높음']
LEVEL_RANK = {l: i for i, l in enumerate(LEVELS)}
KAKAN_LITERAL = False  # 11-24 정의 고침(세션): kakan/ankan · from 이 자기 자리면 강에서 안 빼고 새로 보인 장만 더함, from 은 null. True 는 처음 글 그대로(참고용).


def norm(t):
    if t is None:
        return None
    if isinstance(t, dict):  # 혹시 {"tile":..,"red":..} 꼴
        t = t.get('tile') or t.get('code')
    t = str(t)
    if len(t) == 2 and t[0] == '0' and t[1] in 'mps':
        return '5' + t[1]
    return t


def suit_num(t):
    return int(t[0]), t[1]


def source_files():
    fs = sorted(glob.glob(os.path.join(ROOT, 'assets', 'paifu', '*.json')))
    fs += sorted(glob.glob(os.path.join(ROOT, 'assets', 'paifu_h3', '*.json')))
    return fs


def compute_one(d, warn):
    dealer = d['dealer']

    def wind(seat):
        return WINDS[(seat - dealer) % 4]

    dora = [norm(t) for t in (d.get('dora_indicators') or [])]
    events_in = d['events']

    # 상태
    discards_by_seat = {s: [] for s in range(4)}  # 이 사건 직전까지 각 자리 버림(정규화)
    riichi_step = {}  # seat -> 리치 선언 사건 인덱스(events 안)
    after_riichi_discards = {s: [] for s in range(4)}  # R 리치 선언 뒤 누구든 버린 패
    river = {s: [] for s in range(4)}  # 울기로 안 가져간 버림(정규화)
    meld_tiles = []
    out_events = []
    turn = {s: 0 for s in range(4)}

    def visible_count():
        c = {}
        for s in range(4):
            for t in river[s]:
                c[t] = c.get(t, 0) + 1
        for t in meld_tiles:
            c[t] = c.get(t, 0) + 1
        for t in dora:
            c[t] = c.get(t, 0) + 1
        return c

    for idx, e in enumerate(events_in):
        step = idx + 1
        typ = e.get('type')
        if typ == 'discard':
            seat = e['seat']
            tile = norm(e['tile'])
            turn[seat] += 1
            ar = [r for r in range(4) if r != seat and r in riichi_step]
            ar.sort(key=lambda r: (r - dealer) % 4)
            vc = visible_count()
            vs = []
            for r in ar:
                gset = set(discards_by_seat[r]) | set(after_riichi_discards[r])
                genbutsu = tile in gset
                suji = False
                no_chance = False
                if tile[1] in 'mps':
                    n, su = suit_num(tile)
                    def g(k):
                        return f'{k}{su}' in gset
                    if n <= 3:
                        suji = g(n + 3)
                    elif n >= 7:
                        suji = g(n - 3)
                    else:
                        suji = g(n - 3) and g(n + 3)
                    shapes = []
                    if n <= 7:
                        shapes.append((n + 1, n + 2))
                    if n >= 3:
                        shapes.append((n - 2, n - 1))
                    no_chance = all(
                        vc.get(f'{a}{su}', 0) >= 4 or vc.get(f'{b}{su}', 0) >= 4 for a, b in shapes)
                    for a, b in shapes:
                        for k in (a, b):
                            if vc.get(f'{k}{su}', 0) > 4:
                                warn.append(f'step {step}: {k}{su} 보인 장수 {vc[f"{k}{su}"]} > 4')
                v = vc.get(tile, 0)
                if v > 4:
                    warn.append(f'step {step}: {tile} 보인 장수 {v} > 4')
                vs.append({'wind': wind(r), 'genbutsu': genbutsu, 'suji': suji,
                           'no_chance': no_chance, 'visible': v})
            riichi = bool(e.get('riichi'))
            out_events.append({'step': step, 'wind': wind(seat), 'kind': 'discard', 'tile': tile,
                               'turn_of_seat': turn[seat], 'riichi': riichi,
                               'after_riichi_of': [wind(r) for r in ar], 'vs': vs})
            # 상태 갱신(이 사건 뒤)
            discards_by_seat[seat].append(tile)
            river[seat].append(tile)
            for r in riichi_step:
                after_riichi_discards[r].append(tile)
            if riichi:
                if seat in riichi_step:
                    warn.append(f'step {step}: 자리 {seat} 리치 선언 두 번째 — 첫 번째만 씀')
                else:
                    riichi_step[seat] = idx
        elif typ == 'call':
            seat = e['seat']
            frm = e.get('from')
            kind = e.get('kind')
            tiles = [norm(t) for t in (e.get('tiles') or [])]
            out_events.append({'step': step, 'wind': wind(seat), 'kind': 'call', 'call': kind,
                               'from': (wind(frm) if frm is not None and (KAKAN_LITERAL or frm != seat) else None), 'tiles': tiles})
            literal = KAKAN_LITERAL or kind not in ('kakan', 'ankan')
            if frm is not None and literal and (KAKAN_LITERAL or frm != seat):
                if river[frm]:
                    taken = river[frm].pop()
                    if taken not in tiles:
                        warn.append(f'step {step}: {kind} from {frm} 마지막 버림 {taken} 이 묶음 {tiles} 에 없음')
                else:
                    warn.append(f'step {step}: {kind} from {frm} 강에 뺄 버림 없음')
            if kind == 'kakan' and not KAKAN_LITERAL:
                meld_tiles.extend(tiles[:1])
            else:
                meld_tiles.extend(tiles)
        # draw 는 뺀다

    # game
    ss = d.get('start_scores')
    scores = None
    if isinstance(ss, list) and len(ss) == 4:
        scores = {wind(s): ss[s] for s in sorted(range(4), key=lambda s: (s - dealer) % 4)}
    res = d.get('result')
    result = None
    if res:
        result = {'type': res.get('type'),
                  'winner': wind(res['winner']) if res.get('winner') is not None else None,
                  'loser': wind(res['loser']) if res.get('loser') is not None else None,
                  'win_tile': norm(res.get('win_tile'))}
    game = {'round': d.get('round'), 'honba': d.get('honba'), 'dealer_wind': wind(dealer),
            'dora_indicators': dora, 'scores': scores, 'result': result}
    return {'game': game, 'events': out_events}


def pick_scenes(events, result, level_of):
    """level_of(ev, vs_entry) -> level 말. 반환 {바람: [{step, why}]}."""
    out = {}
    for w in WINDS:
        picked = []
        seen = set()

        def add(step, why):
            if step in seen or len(picked) >= 5:
                return
            seen.add(step)
            picked.append({'step': step, 'why': why})

        mine = [e for e in events if e['wind'] == w]
        disc = [e for e in mine if e['kind'] == 'discard']
        # 1 deal_in
        if result and result.get('type') == 'ron' and result.get('loser') == w:
            hits = [e for e in disc if e['tile'] == result.get('win_tile')]
            if hits:
                add(hits[-1]['step'], 'deal_in')
        # 2 risky_after_riichi
        cand = []
        for e in disc:
            best = -1
            for v in e.get('vs', []):
                lv = level_of(e, v)
                if not v['genbutsu'] and lv in ('높음', '매우 높음'):
                    best = max(best, LEVEL_RANK[lv])
            if best >= 0:
                cand.append((-best, e['step']))
        cand.sort()
        for _, st in cand[:2]:
            add(st, 'risky_after_riichi')
        # 3 own_riichi
        for e in disc:
            if e['riichi']:
                add(e['step'], 'own_riichi')
        # 4 call
        calls = [e for e in mine if e['kind'] == 'call']
        if calls:
            add(calls[0]['step'], 'call')
        out[w] = picked
    return out


def cmd_compute():
    os.makedirs(OUT_PY, exist_ok=True)
    print(f'{"판":22} {"discard":>7} {"vs붙음":>6} {"call":>4}  경고')
    for f in source_files():
        d = json.load(open(f, encoding='utf-8'))
        warn = []
        r = compute_one(d, warn)
        name = os.path.basename(f)
        with open(os.path.join(OUT_PY, name), 'w', encoding='utf-8', newline='\n') as fo:
            json.dump(r, fo, ensure_ascii=False, indent=1)
        nd = sum(1 for e in r['events'] if e['kind'] == 'discard')
        nv = sum(1 for e in r['events'] if e['kind'] == 'discard' and e['vs'])
        nc = sum(1 for e in r['events'] if e['kind'] == 'call')
        print(f'{name:22} {nd:7} {nv:6} {nc:4}  {"; ".join(warn)}')
    print(f'→ {OUT_PY}')


TILE_FIELDS = {'tile', 'win_tile'}


def cmd_compare(dart_dir):
    if not os.path.isdir(dart_dir):
        print(f'Dart 폴더가 아직 없다: {dart_dir} — 대조하지 않고 끝냄')
        return 0
    stats = {}  # 칸 -> [대조 수, 불일치 수]
    lines = []

    def chk(field, a, b, where):
        s = stats.setdefault(field, [0, 0])
        s[0] += 1
        if field in TILE_FIELDS:
            a2, b2 = norm(a), norm(b)
        elif field in ('tiles', 'dora_indicators') and isinstance(b, list):
            a2, b2 = a, [norm(t) for t in b]
        else:
            a2, b2 = a, b
        if a2 != b2:
            s[1] += 1
            lines.append(f'  {where} {field}: py={json.dumps(a, ensure_ascii=False)} dart={json.dumps(b, ensure_ascii=False)}')

    for f in source_files():
        name = os.path.basename(f)
        df = os.path.join(dart_dir, name)
        if not os.path.exists(df):
            lines.append(f'{name}: Dart 파일 없음')
            stats.setdefault('(파일)', [0, 0])
            stats['(파일)'][0] += 1
            stats['(파일)'][1] += 1
            continue
        d = json.load(open(f, encoding='utf-8'))
        py = compute_one(d, [])
        dt = json.load(open(df, encoding='utf-8'))
        lines.append(f'{name}')
        # game
        pg, dg = py['game'], dt.get('game') or {}
        for k in ('round', 'honba', 'dealer_wind', 'dora_indicators', 'scores'):
            chk('game.' + k if k != 'dora_indicators' else 'dora_indicators', pg[k], dg.get(k), 'game')
        pr, dr = pg['result'], dg.get('result')
        if pr is None or dr is None:
            chk('game.result', pr, dr, 'game')
        else:
            for k in ('type', 'winner', 'loser'):
                chk('result.' + k, pr[k], dr.get(k), 'game')
            chk('win_tile', pr['win_tile'], dr.get('win_tile'), 'game')
        # events
        pe, de = py['events'], dt.get('events') or []
        chk('events.len', len(pe), len(de), 'events')
        dmap = {e.get('step'): e for e in de}
        for e in pe:
            st = e['step']
            x = dmap.get(st)
            where = f'step {st}'
            if x is None:
                chk('event.present', True, False, where)
                continue
            chk('event.present', True, True, where)
            for k in ('wind', 'kind'):
                chk(k, e[k], x.get(k), where)
            if e['kind'] == 'discard':
                chk('tile', e['tile'], x.get('tile'), where)
                for k in ('turn_of_seat', 'riichi', 'after_riichi_of'):
                    chk(k, e[k], x.get(k), where)
                pvs = {v['wind']: v for v in e['vs']}
                dvs = {v.get('wind'): v for v in (x.get('vs') or [])}
                chk('vs.winds', list(pvs), [v.get('wind') for v in (x.get('vs') or [])], where)
                for w, v in pvs.items():
                    y = dvs.get(w)
                    if y is None:
                        continue
                    for k in ('genbutsu', 'suji', 'no_chance', 'visible'):
                        chk(k, v[k], y.get(k), f'{where} vs {w}')
                    s = stats.setdefault('level 다섯 말', [0, 0])
                    s[0] += 1
                    if y.get('level') not in LEVELS:
                        s[1] += 1
                        lines.append(f'  {where} vs {w} level 이상: {y.get("level")!r}')
            else:
                for k in ('call', 'from'):
                    chk(k, e[k], x.get(k), where)
                chk('tiles', e['tiles'], x.get('tiles'), where)
        extra = [s for s in dmap if s not in {e['step'] for e in pe}]
        if extra:
            chk('event.extra', [], sorted(extra, key=str), 'events')
        # scenes — Dart events(그 level)로 다시 고르기
        dart_events = []
        for x in de:
            y = dict(x)
            y['wind'] = x.get('wind')
            if y.get('kind') == 'discard':
                y['tile'] = norm(x.get('tile'))
                y['vs'] = x.get('vs') or []
            dart_events.append(y)
        dres = dg.get('result')
        if dres:
            dres = dict(dres)
            dres['win_tile'] = norm(dres.get('win_tile'))
        mine = pick_scenes(dart_events, dres, lambda ev, v: v.get('level'))
        dsc = dt.get('scenes_by_seat') or {}
        for w in WINDS:
            chk('scenes_by_seat', mine[w], dsc.get(w, []), f'scenes {w}')
        # Python 사실(genbutsu 등) + Dart level 로도 골라 봄(참고: 사실 칸 불일치가 장면에 번지는지)
        lv = {}
        for x in de:
            for v in (x.get('vs') or []):
                lv[(x.get('step'), v.get('wind'))] = v.get('level')
        mine2 = pick_scenes(pe, pr, lambda ev, v: lv.get((ev['step'], v['wind'])))
        for w in WINDS:
            chk('scenes(py사실+dart level)', mine2[w], dsc.get(w, []), f'scenes {w}')

    print('\n'.join(l for l in lines))
    print('\n== 합계: 칸 / 대조 수 / 불일치 수 ==')
    tot = [0, 0]
    for k, (n, m) in stats.items():
        print(f'{k:28} {n:6} {m:6}')
        tot[0] += n
        tot[1] += m
    print(f'{"전체":28} {tot[0]:6} {tot[1]:6}')
    return 1 if tot[1] else 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('compute', 'compare'):
        print(__doc__)
        return 2
    if sys.argv[1] == 'compute':
        cmd_compute()
        return 0
    if len(sys.argv) < 3:
        print('compare <dart폴더>')
        return 2
    return cmd_compare(sys.argv[2])


if __name__ == '__main__':
    sys.exit(main())
