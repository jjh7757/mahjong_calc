"""리치가 들어온 차례의 밀기 · 접기 판정 — 1단계(고르기) · 2단계(판정) 채점 (2026-11-23).

설계서: docs/push_fold_design_1122.md (3절 정의 · 4절 R1 ~ R3 · 5절 측정 · 기준). 정의 · 문턱은 설계서 그대로 — 결과를 보고 바꾸지 않는다.
결정 뽑기는 explore_fit140_b.py 와 같은 방식이다(fold · 거르기 · 효율 패 B1 = mhForwardBest or mhBest · 위험 = candidates[].risk).

  python -X utf8 pf_eval.py stage1 [--joined <stage1 joined.jsonl.gz>] [--part select+val] [--out-dir <results/pushfold>]
  python -X utf8 pf_eval.py stage1 --part fit --out-dir <딴 곳>        # 자기 확인: 맞춤 140판(탐색에 쓴 판) — 설계서 2절 숫자와 같아야 함
  python -X utf8 pf_eval.py test2 --joined <results/pushfold/test2_joined.jsonl.gz> [--stage1-json <stage1.json>]
                                                                       # 2단계: 1단계에서 고른 규칙 하나를 한 번 판정

정의(설계서 3절)
  대상 차례 = 주 묶음(afterRiichi 아님 · afterCall 아님 · 후보 패 종류 ≥ 2 · S42 버림 있음) 중 riichiSeats 가 비지 않음.
  위험 = candidates[].risk(%, mixed34), 최소 위험 = 후보(손에 있는 패 종류) 중 가장 낮은 값.
  효율 패 = fold(mhForwardBest or mhBest). 갈리는 차례 = 효율 패 위험 − 최소 위험 ≥ 5.
  어느 패든: 위험 − 최소 위험 ≥ 5 → 밀었다, < 2 → 접었다, 그 사이 → 중간.
  S42 가 접었다 = S42 첫째 버림(s42Discard — 리치 · 화료 · 깡 제외, s42_batch 정의)이 "접었다".
규칙(4절, 모두 대상 차례 · 갈리는 차례에 더해)
  R1 = 버리기 전 2샹텐 이상(shantenBefore ≥ 2) · R2 = R1 그리고 최소 위험 < 1 · R3 = 버리기 전 3샹텐 이상.
지표(5-2절)
  1 규칙이 잡은 결정 중 S42 접음 비율 · 2 넓이(잡음 / 리치 차례 갈리는 결정, 잡음 / 대상 차례 전체)
  3 잡았고 플레이어가 민 결정 중 S42 접음 · 4 잡았고 플레이어가 접은 결정 중 S42 접음
  5 잡았고 플레이어가 민 결정의 Q 손해 중앙 · 평균 — S42 가 접었을 때 / 밀었을 때(중간은 n 만)
  Q 손해 = mxfit/baseline.py 와 같음: Q(s42Discard) − Q(실제 버린 패). 패의 Q 는 그 결정의 Q 중 같은 패로 접히는 것(5m · 5mr)의
  큰 값(baseline.tile_q). 플레이어가 리치했으면 실제 패의 Q 는 tsumo 결정의 "다마로 그 패를 버림" Q(baseline 과 같음).
  구간 = 판 단위 부트스트랩 1,000번, 씨 20261123. 그 판(part)의 판 목록 전체에서 복원 추출(잡은 결정이 없는 판도 뽑힘),
  비율 = 뽑힌 판들의 분자 합 / 분모 합. 분모 0 인 뽑기는 빼고 센다(빠진 수를 적음). 구간 = 2.5 · 97.5 백분위.
1단계 고르기(5-3절 — 결과 보기 전에 코드에 박음)
  지표 1 점 추정 ≥ 0.90 인 후보 중 넓이(리치 차례 갈리는 결정 중 비율) 가장 큰 것. 동률이면 지표 1 점 추정이 큰 것,
  그래도 같으면 번호가 작은 것(R1 < R2 < R3). 하나도 없으면 "없음 → 접음"(시험 판을 열지 않음).
2단계 판정(5-3절): 고른 규칙의 지표 1 점 추정 ≥ 0.90 이고 구간 아래 끝 ≥ 0.87 이면 통과. 넓이가 대상 차례 전체의 5% 미만이면
  "쓸 자리가 너무 적다" 를 따로 적음. 문구(6절): 지표 3 ≥ 0.70 → "접는 것이 맞았습니다.", 미만 → 참고 문구 · 등급 반영 안 함.
  지표 4 ≥ 0.90 → "잘 접었습니다." 를 보임.
"""
from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MX = HERE.parent / 'mxfit'
sys.path.insert(0, str(MX))
import split  # noqa: E402
from baseline import tile_q  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RES = ROOT / 'experiments' / 'paifu_review' / 'results'
STAGE1_JOINED = RES / 'mxfit' / 'stage1' / 'joined.jsonl.gz'
OUT = RES / 'pushfold'

HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}
GAP_SPLIT = 5.0   # 갈리는 차례 · 밀었다
GAP_FOLD = 2.0    # 접었다
RMIN_SAFE = 1.0   # R2 의 최소 위험
PICK_MIN = 0.90   # 1단계: 지표 1 점 추정
PASS_POINT = 0.90  # 2단계: 점 추정
PASS_LOW = 0.87    # 2단계: 구간 아래 끝
NARROW = 0.05      # 넓이(대상 차례 전체 중) 5% 미만이면 따로 적음
WORD_STRONG = 0.70  # 6절: 지표 3
WORD_GOODFOLD = 0.90  # 6절: 지표 4
SEED = 20261123
NB = 1000
RULES = ('R1', 'R2', 'R3')
RULE_TEXT = {'R1': '버리기 전 2샹텐 이상', 'R2': 'R1 그리고 최소 위험 < 1%', 'R3': '버리기 전 3샹텐 이상'}


def fold(t: str) -> str:
    """explore_fit140_b.fold 와 같음."""
    if t in HON:
        return HON[t]
    return ('5' + t[1]) if t[0] == '0' else t[:2]


def rule_hits(sh: int, gb1: float, rmin: float) -> dict[str, bool]:
    split_ = gb1 >= GAP_SPLIT
    return {'R1': split_ and sh >= 2, 'R2': split_ and sh >= 2 and rmin < RMIN_SAFE, 'R3': split_ and sh >= 3}


def label(gap: float) -> str:
    return 'push' if gap >= GAP_SPLIT else ('fold' if gap < GAP_FOLD else 'mid')


def read_joined(path: Path, games: set[str]) -> tuple[list[dict], Counter]:
    """games 에 든 판의 줄만 남긴다. 밖의 판 줄 수를 센다."""
    rows, seen = [], Counter()
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r['game'] not in games:
                seen['outside'] += 1
                continue
            seen['inside'] += 1
            rows.append(r)
    return rows, seen


def extract(rows: list[dict]) -> tuple[list[dict], dict]:
    """3절 대상 차례 → 결정 행. 거른 줄은 사유별로(앞 사유부터 하나만) 센다."""
    excl = Counter()
    out = []
    for r in rows:
        s = r.get('s42') or {}
        if r.get('afterRiichi'):
            excl['afterRiichi(내가 리치 뒤)'] += 1
            continue
        if r.get('afterCall'):
            excl['afterCall(울기 직후 버림)'] += 1
            continue
        if not s or not s.get('s42Discard'):
            excl['S42 버림 없음'] += 1
            continue
        if len(r['candidates']) < 2:
            excl['후보 1종류'] += 1
            continue
        if not r.get('riichiSeats'):
            excl['남 리치 없음(리치 차례 아님)'] += 1
            continue
        cs = r['candidates']
        risk = {fold(c['tile']): (c.get('risk') or 0.0) for c in cs}
        rmin = min(risk.values())
        b1 = fold(r['mhForwardBest'] or r['mhBest'])
        sd = fold(s['s42Discard'])
        act = fold(r['actual'])
        miss = [n for n, t in (('효율 패', b1), ('S42 버림', sd), ('실제 버림', act)) if t not in risk]
        if miss:
            excl['후보에 없는 패(' + '·'.join(miss) + ')'] += 1
            continue
        tq = tile_q(s['q']) if s.get('q') else {}
        sq = s['s42Discard']
        sq = HON.get(sq, sq[:2])
        qloss = (tq[sq] - tq[act]) if (sq in tq and act in tq) else None
        sh = r['shantenBefore']
        gb1, gs, ga = risk[b1] - rmin, risk[sd] - rmin, risk[act] - rmin
        hits = rule_hits(sh, gb1, rmin)
        out.append({'game': r['game'], 'kyoku': r['kyoku'], 'seat': r['seat'], 'k': r['k'],
                    'shantenBefore': sh, 'riskMin': rmin,
                    'effTile': b1, 'effRisk': risk[b1], 's42Tile': sd, 's42Risk': risk[sd],
                    'actualTile': act, 'actualRisk': risk[act],
                    'gapEff': gb1, 'gapS42': gs, 'gapActual': ga,
                    'split': gb1 >= GAP_SPLIT, 's42': label(gs), 'player': label(ga),
                    'qLoss': qloss, **hits})
    return out, dict(excl)


def boot(ds: list[dict], games: list[str], num, den) -> dict:
    """판 단위 부트스트랩: 비율 = Σ분자 / Σ분모."""
    by_n = defaultdict(float)
    by_d = defaultdict(float)
    for d in ds:
        if den(d):
            by_d[d['game']] += 1
            if num(d):
                by_n[d['game']] += 1
    n_arr = np.array([by_n[g] for g in games])
    d_arr = np.array([by_d[g] for g in games])
    tot_d = d_arr.sum()
    point = float(n_arr.sum() / tot_d) if tot_d else None
    rng = np.random.default_rng(SEED)
    vals, zero = [], 0
    for _ in range(NB):
        idx = rng.integers(0, len(games), len(games))
        dd = d_arr[idx].sum()
        if dd == 0:
            zero += 1
            continue
        vals.append(n_arr[idx].sum() / dd)
    ci = [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None
    return {'num': int(n_arr.sum()), 'den': int(tot_d), 'rate': point, 'ci95': ci, 'bootZeroDen': zero}


def qstats(xs: list[float]) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {'n': 0, 'median': None, 'mean': None}
    return {'n': len(xs), 'median': float(statistics.median(xs)), 'mean': float(np.mean(xs))}


def evaluate(ds: list[dict], games: list[str]) -> dict:
    n_all = len(ds)
    n_split = sum(d['split'] for d in ds)
    res = {'targets': n_all, 'splitDecisions': n_split, 'games': len(games),
           'gamesWithTargets': len({d['game'] for d in ds}), 'rules': {}}
    for R in RULES:
        caught = [d for d in ds if d[R]]
        pushed = [d for d in caught if d['player'] == 'push']
        m = {
            'caught': len(caught),
            'm1_s42Fold': boot(ds, games, lambda d: d['s42'] == 'fold', lambda d: d[R]),
            'm2_breadthSplit': (len(caught) / n_split) if n_split else None,
            'm2_breadthAll': (len(caught) / n_all) if n_all else None,
            'm3_pushedS42Fold': boot(ds, games, lambda d: d['s42'] == 'fold', lambda d: d[R] and d['player'] == 'push'),
            'm4_foldedS42Fold': boot(ds, games, lambda d: d['s42'] == 'fold', lambda d: d[R] and d['player'] == 'fold'),
            'm5_qLossPushed': {
                's42Fold': qstats([d['qLoss'] for d in pushed if d['s42'] == 'fold']),
                's42Push': qstats([d['qLoss'] for d in pushed if d['s42'] == 'push']),
                's42Mid': qstats([d['qLoss'] for d in pushed if d['s42'] == 'mid']),
                'qLossMissing': sum(1 for d in pushed if d['qLoss'] is None),
            },
            'playerLabels': dict(Counter(d['player'] for d in caught)),
            's42Labels': dict(Counter(d['s42'] for d in caught)),
        }
        res['rules'][R] = m
    res['qLossAllTargets'] = qstats([d['qLoss'] for d in ds])
    return res


def pick(res: dict) -> dict:
    """5-3절 1단계 — 지표 1 ≥ 0.90 인 후보 중 넓이(갈리는 결정 중) 최대. 동률: 지표 1 큰 것 → 번호 작은 것."""
    ok = [R for R in RULES if res['rules'][R]['m1_s42Fold']['rate'] is not None
          and res['rules'][R]['m1_s42Fold']['rate'] >= PICK_MIN]
    if not ok:
        return {'chosen': None, 'eligible': [], 'verdict': '없음 → 접음(시험 판을 열지 않음)'}
    ok.sort(key=lambda R: (-res['rules'][R]['m2_breadthSplit'], -res['rules'][R]['m1_s42Fold']['rate'], RULES.index(R)))
    return {'chosen': ok[0], 'eligible': ok, 'verdict': f'{ok[0]} 고름'}


def judge(m: dict) -> dict:
    """5-3절 2단계 판정 + 6절 문구."""
    m1 = m['m1_s42Fold']
    passed = m1['rate'] is not None and m1['ci95'] is not None and m1['rate'] >= PASS_POINT and m1['ci95'][0] >= PASS_LOW
    m3, m4 = m['m3_pushedS42Fold']['rate'], m['m4_foldedS42Fold']['rate']
    return {'pass': passed, 'narrow': (m['m2_breadthAll'] or 0) < NARROW,
            'pushWording': None if m3 is None else ('접는 것이 맞았습니다.' if m3 >= WORD_STRONG else
                                                     '보통은 접는 자리입니다(참고 · 등급 반영 안 함)'),
            'showGoodFold': None if m4 is None else m4 >= WORD_GOODFOLD}


def pct(x) -> str:
    return '-' if x is None else f'{100 * x:.1f}%'


def ci(b: dict) -> str:
    return '-' if b['ci95'] is None else f"{pct(b['ci95'][0])} ~ {pct(b['ci95'][1])}"


def q(x) -> str:
    return '-' if x is None else f'{x:.2f}'


def md(title: str, res: dict, excl: dict, extra: list[str]) -> str:
    L = [f'# {title}', '', f"판 {res['games']}판(대상 차례 있는 판 {res['gamesWithTargets']}) · 대상 차례(리치 차례) {res['targets']} · "
         f"그중 갈리는 결정 {res['splitDecisions']} ({pct(res['splitDecisions'] / res['targets'] if res['targets'] else None)})", '',
         '거른 줄(앞 사유부터 하나만): ' + ' · '.join(f'{k} {v}' for k, v in excl.items()), '',
         f'부트스트랩: 판 단위 {NB}번, 씨 {SEED}.', '',
         '| 규칙 | 조건 | 잡음 | 지표 1 S42 접음 (95% 구간) | 넓이: 갈리는 결정 중 | 넓이: 리치 차례 전체 중 | 지표 3 민 것 중 S42 접음 (구간) | 지표 4 접은 것 중 S42 접음 (구간) |',
         '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for R in RULES:
        m = res['rules'][R]
        m1, m3, m4 = m['m1_s42Fold'], m['m3_pushedS42Fold'], m['m4_foldedS42Fold']
        L.append(f"| {R} | {RULE_TEXT[R]} | {m['caught']} | {m1['num']}/{m1['den']} = {pct(m1['rate'])} ({ci(m1)}) | "
                 f"{pct(m['m2_breadthSplit'])} | {pct(m['m2_breadthAll'])} | {m3['num']}/{m3['den']} = {pct(m3['rate'])} ({ci(m3)}) | "
                 f"{m4['num']}/{m4['den']} = {pct(m4['rate'])} ({ci(m4)}) |")
    L += ['', '## 지표 5 — 잡았고 플레이어가 민 결정의 Q 손해(Q(S42 버림) − Q(실제), baseline.py 와 같은 정의)', '',
          '| 규칙 | S42 접음: n · 중앙 · 평균 | S42 밂: n · 중앙 · 평균 | S42 중간: n · 중앙 · 평균 | Q 없음 |', '| --- | --- | --- | --- | --- |']
    for R in RULES:
        m5 = res['rules'][R]['m5_qLossPushed']
        cell = lambda s: f"{s['n']} · {q(s['median'])} · {q(s['mean'])}"  # noqa: E731
        L.append(f"| {R} | {cell(m5['s42Fold'])} | {cell(m5['s42Push'])} | {cell(m5['s42Mid'])} | {m5['qLossMissing']} |")
    qa = res['qLossAllTargets']
    L += ['', f"(참고) 대상 차례 전체 플레이어 Q 손해: n {qa['n']} · 중앙 {q(qa['median'])} · 평균 {q(qa['mean'])}", '',
          '## 잡은 결정의 라벨', '', '| 규칙 | 플레이어 밂 · 접음 · 중간 | S42 밂 · 접음 · 중간 |', '| --- | --- | --- |']
    for R in RULES:
        m = res['rules'][R]
        f = lambda c: f"{c.get('push', 0)} · {c.get('fold', 0)} · {c.get('mid', 0)}"  # noqa: E731
        L.append(f"| {R} | {f(m['playerLabels'])} | {f(m['s42Labels'])} |")
    return '\n'.join(L + [''] + extra) + '\n'


def write_rows(path: Path, ds: list[dict], part_of=None):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for d in ds:
            o = dict(d)
            if part_of:
                o['part'] = part_of(d['game'])
            f.write(json.dumps(o, ensure_ascii=False) + '\n')


def cmd_stage1(a):
    s1 = split.stage1_split()
    parts = a.part.split('+')
    assert all(p in s1 for p in parts), f'모르는 part: {a.part}'
    games = sorted(g for p in parts for g in s1[p])
    rows, seen = read_joined(Path(a.joined), set(games))
    ds, excl = extract(rows)
    res = evaluate(ds, games)
    res['part'] = a.part
    res['joined'] = str(a.joined)
    res['joinedLines'] = dict(seen)
    res['excluded'] = excl
    res['pick'] = pick(res)
    for R in RULES:
        res['rules'][R]['narrow'] = (res['rules'][R]['m2_breadthAll'] or 0) < NARROW
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = a.tag or ('stage1' if a.part == 'select+val' else f'stage1_{a.part.replace("+", "_")}')
    (out / f'{tag}.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    part_map = {g: p for p, gs in s1.items() for g in gs}
    write_rows(out / f'{tag}_rows.jsonl', ds, part_map.__getitem__)
    pk = res['pick']
    extra = ['## 1단계 고르기(5-3절)', '',
             f"- 지표 1 ≥ 90% 인 후보: {', '.join(pk['eligible']) or '없음'}",
             f"- 결과: **{pk['verdict']}**",
             '- 동률 처리(결과 보기 전 코드에 박음): 넓이(갈리는 결정 중) 같으면 지표 1 큰 것, 그래도 같으면 번호 작은 것.']
    for R in RULES:
        if res['rules'][R]['narrow']:
            extra.append(f'- {R}: 넓이가 리치 차례 전체의 5% 미만 — 쓸 자리가 너무 적다.')
    text = md(f'밀기 · 접기 1단계 — part {a.part}', res, excl, extra)
    (out / f'{tag}.md').write_text(text, encoding='utf-8', newline='\n')
    print(text)


def cmd_test2(a):
    if a.selftest_dev:  # 코드 길 확인용: 시험 2 대신 개발 select+val 60판(시험 판은 안 엶)
        s1 = split.stage1_split()
        t2 = sorted(s1['select'] + s1['val'])
    else:
        t2 = split.test599_games()[:200]
    rows, seen = read_joined(Path(a.joined), set(t2))
    if seen.get('outside') and not a.selftest_dev:
        raise SystemExit(f"시험 2 200판 밖의 줄 {seen['outside']} — 맞붙인 파일이 잘못됨")
    s1 = json.loads(Path(a.stage1_json).read_text(encoding='utf-8'))
    chosen = a.rule or s1['pick']['chosen']
    if chosen is None:
        raise SystemExit('1단계에서 고른 규칙이 없음(접음) — 시험 판을 채점하지 않는다')
    ds, excl = extract(rows)
    res = evaluate(ds, t2)
    res['part'] = 'selftest-dev(select+val)' if a.selftest_dev else 'test2'
    res['joined'] = str(a.joined)
    res['joinedLines'] = dict(seen)
    res['excluded'] = excl
    res['chosen'] = chosen
    res['judge'] = judge(res['rules'][chosen])
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'test2.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    write_rows(out / 'test2_rows.jsonl', ds)
    j = res['judge']
    m1 = res['rules'][chosen]['m1_s42Fold']
    extra = ['## 2단계 판정(5-3절 · 6절) — 고른 규칙 하나만 판정, 나머지 규칙 줄은 참고', '',
             f'- 고른 규칙: {chosen}({RULE_TEXT[chosen]})',
             f"- 지표 1 {pct(m1['rate'])}, 구간 아래 끝 {pct(m1['ci95'][0] if m1['ci95'] else None)} → "
             f"**{'통과' if j['pass'] else '접음'}**(기준: 점 추정 ≥ 90% · 아래 끝 ≥ 87%)",
             f"- 넓이 5% 미만(쓸 자리가 너무 적다): {'예' if j['narrow'] else '아니오'}",
             f"- 민 것 문구(지표 3 기준 70%): {j['pushWording']}",
             f"- '잘 접었습니다.' 보임(지표 4 ≥ 90%): {j['showGoodFold']}"]
    text = md('밀기 · 접기 2단계 — ' + ('자기 확인(개발 select+val — 시험 판 아님)' if a.selftest_dev else '시험 2(안 연 599판의 ID 순 앞 200판)'), res, excl, extra)
    (out / 'test2.md').write_text(text, encoding='utf-8', newline='\n')
    print(text)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p1 = sub.add_parser('stage1')
    p1.add_argument('--joined', default=str(STAGE1_JOINED))
    p1.add_argument('--part', default='select+val', help="stage1_split 의 part 를 + 로: 'select+val'(1단계) · 'fit'(자기 확인)")
    p1.add_argument('--out-dir', default=str(OUT))
    p1.add_argument('--tag')
    p2 = sub.add_parser('test2')
    p2.add_argument('--joined', required=True)
    p2.add_argument('--stage1-json', default=str(OUT / 'stage1.json'))
    p2.add_argument('--rule', choices=RULES, help='보통은 비움(stage1.json 의 고른 규칙)')
    p2.add_argument('--out-dir', default=str(OUT))
    p2.add_argument('--selftest-dev', action='store_true', help='판 목록을 개발 select+val 로(코드 길 확인용, --out-dir 은 딴 곳)')
    a = ap.parse_args()
    {'stage1': cmd_stage1, 'test2': cmd_test2}[a.cmd](a)


if __name__ == '__main__':
    main()
