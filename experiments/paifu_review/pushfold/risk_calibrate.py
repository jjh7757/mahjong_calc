"""엔진 "방총 위험 %" 보정표 — 설계서 docs/risk_calibration_design_1123.md 1 ~ 4절 그대로 (2026-11-23).

  python -X utf8 experiments/paifu_review/pushfold/risk_calibrate.py fit    # 개발 200판(stage1)으로 보정표 + 개발 판 검사
  python -X utf8 experiments/paifu_review/pushfold/risk_calibrate.py test   # 시험 200판(stage2) 한 번 채점(table.json 을 읽기만 함)

다시 재기(설계서 8절, 11-23 — 고친 기준 ② = max(1.0%p, 2×SE), 새 시험 599판):
  ... risk_calibrate.py sim599      # 시험 판 열기 전: 개발 행에서 보정값을 참 확률로 두고 1,000번 뽑아 ①②③ 통과 비율(R · C)
  ... risk_calibrate.py joincheck   # stage2 features 에 join599 규칙(afterRiichi 빼기)을 적용하면 stage2 joined 와 같은지
  (값 뽑기) run_features.py --test599 --gzip --dill <stage3/bin/...dill> --out-dir results/mxfit/stage3/features
  ... risk_calibrate.py join599     # stage3 features → stage3/joined.jsonl.gz (S42 없이, stage2 joined 와 같은 차례 고르기)
  ... risk_calibrate.py sim599v3    # 9절 열기 전 점검: 개발 200판 판 단위 599판 복원 추출 1,000번, ② = max(1, 3×SE) → sim599_v3.json
  ... risk_calibrate.py test599     # 새 시험 599판 한 번 채점(table.json 읽기만, 9절 판정, go 는 sim599_v3.json)
                                    #   → test599_rows.jsonl · test599_eval.json · summary_test599.md

결과: experiments/paifu_review/results/riskcal/
  table.json      R · C 보정표(점 목록 + 덩어리별 버림 · 방총)
  dev_rows.jsonl  개발 판 대상 차례(엔진 값 · 보정 값 · 방총)
  dev_eval.json   개발 판 측정 · 검사
  test_rows.jsonl 시험 판 대상 차례(검토 쪽이 다시 계산하는 용)
  test_eval.json  시험 판 측정 · 판정
  summary.md      표와 판정

정의(설계서 1절):
  대상 차례 = riskSeats 가 비지 않음 + 내가 리치 중 아님(afterRiichi 거짓 — joined 는 이미 리치 뒤 차례를 뺌)
  R = riichiSeats 가 비지 않음 · C = riichiSeats 가 빔(울기 위협만)
  방총 = 그 버림이 그 국의 내 마지막 버림(k == 버림 줄 길이 − 1) · 결과 和了 · 방총자가 나(리치 안 한 자리에게도 셈)
  값 = 실제 버린 패의 candidates[].risk(%) — 표 16-11 스크립트(risk_calibration.py)와 같은 방식
보정(2절): safeAll 버림은 따로(보정 0). 나머지는 엔진 값 → 방총 PAV(같은 엔진 값은 한 묶음, 평균이 같거나 거꾸로면 합침
  → 덩어리 평균이 엄격히 증가). 그다음 왼쪽(엔진 값 작은 쪽)부터 덩어리를 차례로 합쳐 버림 200개 이상이 되면 닫고,
  끝에 남은 200개 미만은 바로 앞 덩어리에 합친다. 점 = (덩어리 엔진 평균, 덩어리 방총률). 사이는 직선, 첫 점 아래는
  첫 점 값(= 엔진 0 이 든 덩어리의 실측), 마지막 점 위는 마지막 점 값(np.interp 의 양 끝 고정과 같음).
측정(3절): 구간 0 · 0~1 · 1~3 · 3~5 · 5~8 · 8~12 · 12~18 · 18+(0 은 < 0.0001), ECE = 예측값 순으로 같은 개수 10 구간
  (동률은 엔진 값 → 원래 줄 순서로 정렬), Brier = (예측 − 실제)² 평균(확률 단위), 부트스트랩 = 판 단위 1,000번, 씨 20261123.
  safeAll 버림도 대상 차례에 들어간다(보정 전 = 엔진 값, 보정 후 = 0).
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(PR, 'mxfit'))
import split  # noqa: E402

OUT = os.path.join(PR, 'results', 'riskcal')
JOINED = {'dev': os.path.join(PR, 'results', 'mxfit', 'stage1', 'joined.jsonl.gz'),
          'test': os.path.join(PR, 'results', 'mxfit', 'stage2', 'joined.jsonl.gz'),
          'test599': os.path.join(PR, 'results', 'mxfit', 'stage3', 'joined.jsonl.gz')}
LOGP = {'dev': split.log_path, 'test': split.test200_path, 'test599': split.test599_path}
SIM_N = 1000
SIM_SEED = 20261126
SIM_MIN_PASS = 0.80
HON = {'E': '1z', 'S': '2z', 'W': '3z', 'N': '4z', 'P': '5z', 'F': '6z', 'C': '7z'}
MIN_BLOCK = 200
BINS = ((0, 0.0001), (0.0001, 1), (1, 3), (3, 5), (5, 8), (8, 12), (12, 18), (18, 1e9))
BOOT_N = 1000
BOOT_SEED = 20261123
N_ECE = 10
# 표 16-11(개발 200판, 남이 리치한 차례) — 구간: (버림, 방총, 엔진 평균 %)
T1611 = {'0': (7398, 10, 0.00), '0~1': (1152, 7, 0.46), '1~3': (1554, 20, 2.02), '3~5': (1160, 41, 3.89),
         '5~8': (1205, 40, 6.41), '8~12': (1076, 84, 9.78), '12~18': (768, 72, 14.52), '18+': (398, 58, 23.36)}


def fold(t):
    if t in HON:
        return HON[t]
    return ('5' + t[1]) if t[0] == '0' else t[:2]


def bin_name(lo, hi):
    lo = 0 if lo < 0.001 else lo
    return '0' if hi <= 0.0001 else (f'{lo:g}~{hi:g}' if hi < 1e8 else f'{lo:g}+')


# ---------------------------------------------------------------- 자료
def load(stage):
    rows = defaultdict(list)
    with gzip.open(JOINED[stage], 'rt', encoding='utf-8') as f:
        for i, line in enumerate(f):
            r = json.loads(line)
            r['_i'] = i
            rows[r['game']].append(r)
    if stage == 'test':
        allowed = set(split.test200_games())
        assert set(rows) <= allowed, '시험 200판 밖의 판'
    if stage == 'test599':
        allowed = set(split.test599_games())
        assert set(rows) <= allowed, '새 시험 599판 밖의 판'
    recs = []
    cnt = defaultdict(int)
    for game, rs in rows.items():
        log = json.load(open(LOGP[stage](game), encoding='utf-8'))['log']
        for r in rs:
            cnt['joined'] += 1
            if r.get('afterRiichi'):
                cnt['afterRiichi'] += 1
                continue
            rs_, ri = r.get('riskSeats') or [], r.get('riichiSeats') or []
            if not rs_:
                if ri:
                    cnt['riichi_but_no_riskSeats'] += 1
                continue
            kind = 'R' if ri else 'C'
            kyoku = log[r['kyoku']]
            seat = r['seat']
            n_disc = len(kyoku[6 + 3 * seat])
            res = kyoku[-1]
            last = r['k'] == n_disc - 1
            dealt = False
            if last and res and res[0] == '和了':
                for i in range(2, len(res), 2):
                    info = res[i]
                    if info[0] != info[1] and info[1] == seat:
                        dealt = True
            act = fold(r['actual'])
            cands = [c for c in r['candidates'] if fold(c['tile']) == act]
            assert cands, (game, r['kyoku'], seat, r['k'])
            risk = cands[0].get('risk') or 0.0
            if r.get('riskOfActual') is not None and abs(r['riskOfActual'] - risk) > 1e-9:
                cnt['riskOfActual_diff'] += 1
            if stage == 'test599':  # 덤 검사(새 판만 — 기존 셈 칸은 그대로)
                cnt['riskOfActual_missing'] += r.get('riskOfActual') is None
                cnt['riskOfActual_same'] += r.get('riskOfActual') is not None and abs(r['riskOfActual'] - risk) <= 1e-9
                cnt['actual_cands_risk_disagree'] += len({c.get('risk') or 0.0 for c in cands}) > 1
            safe = any(c.get('safeAll') for c in cands)
            recs.append(dict(game=game, kyoku=r['kyoku'], kyokuNum=r['kyokuNum'], honba=r['honba'], seat=seat, k=r['k'],
                             kind=kind, nRiichi=len(ri), riskSeats=rs_, riichiSeats=ri, actual=r['actual'],
                             safeAll=bool(safe), engine=float(risk), dealt=bool(dealt), lastDiscard=bool(last),
                             result=(res[0] if res else None), _i=r['_i']))
    return recs, dict(cnt)


# ---------------------------------------------------------------- 보정표
def pav_blocks(x, y):
    """같은 x 는 한 묶음. 평균이 앞 덩어리보다 크지 않으면 합침 → 평균 엄격 증가."""
    ux, inv = np.unique(x, return_inverse=True)
    n = np.bincount(inv).astype(float)
    s = np.bincount(inv, weights=y.astype(float))
    sx = np.bincount(inv, weights=x)
    blocks = []  # [n, dealt, sumx, xmin, xmax]
    for j in range(len(ux)):
        blocks.append([n[j], s[j], sx[j], ux[j], ux[j]])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][0] >= blocks[-1][1] / blocks[-1][0]:
            b = blocks.pop()
            a = blocks[-1]
            a[0] += b[0]; a[1] += b[1]; a[2] += b[2]; a[4] = b[4]
    return blocks


def merge_min(blocks, m=MIN_BLOCK):
    out, cur = [], None
    for b in blocks:
        if cur is None:
            cur = list(b)
        else:
            cur[0] += b[0]; cur[1] += b[1]; cur[2] += b[2]; cur[4] = b[4]
        if cur[0] >= m:
            out.append(cur)
            cur = None
    if cur is not None:
        if out:
            a = out[-1]
            a[0] += cur[0]; a[1] += cur[1]; a[2] += cur[2]; a[4] = cur[4]
        else:
            out.append(cur)
    return out


def build_table(recs):
    ns = [r for r in recs if not r['safeAll']]
    x = np.array([r['engine'] for r in ns])
    y = np.array([r['dealt'] for r in ns], dtype=float)
    pav = pav_blocks(x, y)
    blk = merge_min(pav)
    blocks = [dict(n=int(b[0]), dealt=int(b[1]), x_min=float(b[3]), x_max=float(b[4]), x_mean=float(b[2] / b[0]),
                   rate=float(100 * b[1] / b[0])) for b in blk]
    pts = [[b['x_mean'], b['rate']] for b in blocks]
    safe = [r for r in recs if r['safeAll']]
    return dict(points=pts, blocks=blocks, n_pav_blocks=len(pav), n_nonsafe=len(ns), n_dealt_nonsafe=int(y.sum()),
                safe_n=len(safe), safe_dealt=int(sum(r['dealt'] for r in safe)),
                safe_engine_max=float(max((r['engine'] for r in safe), default=0.0)))


def apply_table(tab, engine, safe):
    xs = np.array([p[0] for p in tab['points']])
    ys = np.array([p[1] for p in tab['points']])
    v = np.interp(np.asarray(engine, dtype=float), xs, ys)
    return np.where(np.asarray(safe), 0.0, v)


# ---------------------------------------------------------------- 측정
def ece(pred, y, eng, idx):
    """pred·y 는 % 와 0/1. 예측 순(동률: 엔진 값 → 원래 줄) 같은 개수 10 구간, 버림 수 가중 |예측 평균 − 실측|(%p)."""
    order = np.lexsort((idx, eng, pred))
    tot = 0.0
    for ch in np.array_split(order, N_ECE):
        if len(ch):
            tot += len(ch) * abs(pred[ch].mean() - 100 * y[ch].mean())
    return tot / len(pred)


def brier(pred, y):
    return float(np.mean((pred / 100 - y) ** 2))


def metrics(eng, cal, y, idx):
    return dict(n=int(len(y)), dealt=int(y.sum()), actual=float(100 * y.mean()), engine_mean=float(eng.mean()),
                cal_mean=float(cal.mean()), ece_before=float(ece(eng, y, eng, idx)), ece_after=float(ece(cal, y, eng, idx)),
                brier_before=brier(eng, y), brier_after=brier(cal, y))


def bin_masks(eng):
    return [(bin_name(lo, hi), (eng >= lo) & (eng < hi)) for lo, hi in BINS]


def evaluate(recs, tab, boot=True):
    eng = np.array([r['engine'] for r in recs])
    safe = np.array([r['safeAll'] for r in recs])
    y = np.array([r['dealt'] for r in recs], dtype=float)
    idx = np.array([r['_i'] for r in recs])
    cal = apply_table(tab, eng, safe)
    out = dict(overall=metrics(eng, cal, y, idx))
    bins = []
    for name, m in bin_masks(eng):
        if not m.any():
            bins.append(dict(bin=name, n=0))
            continue
        bins.append(dict(bin=name, n=int(m.sum()), dealt=int(y[m].sum()), actual=float(100 * y[m].mean()),
                         engine_mean=float(eng[m].mean()), cal_mean=float(cal[m].mean()), safe_n=int(safe[m].sum())))
    out['bins'] = bins
    # 덤(판정에 안 씀): safeAll 뺀 나머지만
    ns = ~safe
    out['nonsafe_overall'] = metrics(eng[ns], cal[ns], y[ns], idx[ns]) if ns.any() else None
    # 동률 확인: 엔진 값이 서로 다른데 보정 값이 같은 쌍(safeAll 빼고) · 순서 뒤집힘
    ue = np.unique(eng[ns])
    uc = apply_table(tab, ue, np.zeros(len(ue), bool))
    out['order'] = dict(distinct_engine_nonsafe=int(len(ue)), distinct_cal_nonsafe=int(len(np.unique(uc))),
                        order_violations=int(np.sum(np.diff(uc) < -1e-12)))
    # ECE 의 동률 순서 민감도(덤): 동률 안 순서를 무작위로 20번
    rng = np.random.default_rng(BOOT_SEED + 1)
    alt = []
    for _ in range(20):
        rnd = rng.permutation(len(y))
        alt.append((ece(eng, y, eng, rnd), ece(cal, y, eng, rnd)))
    alt = np.array(alt)
    out['ece_tie_shuffle'] = dict(before_min=float(alt[:, 0].min()), before_max=float(alt[:, 0].max()),
                                  after_min=float(alt[:, 1].min()), after_max=float(alt[:, 1].max()))
    if boot:
        out['boot'] = bootstrap(recs, eng, cal, y, idx)
    return out, cal


def bootstrap(recs, eng, cal, y, idx):
    games = sorted(set(r['game'] for r in recs))
    gi = {g: i for i, g in enumerate(games)}
    gidx = np.array([gi[r['game']] for r in recs])
    rows_of = [np.flatnonzero(gidx == i) for i in range(len(games))]
    masks = bin_masks(eng)
    rng = np.random.default_rng(BOOT_SEED)
    acc = defaultdict(list)
    for _ in range(BOOT_N):
        pick = rng.integers(0, len(games), len(games))
        ii = np.concatenate([rows_of[p] for p in pick])
        e, c, yy, ix = eng[ii], cal[ii], y[ii], idx[ii]
        for name, m in masks:
            mm = m[ii]
            if mm.any():
                acc['actual:' + name].append(100 * yy[mm].mean())
                acc['diffcal:' + name].append(c[mm].mean() - 100 * yy[mm].mean())
        acc['actual'].append(100 * yy.mean())
        acc['ece_before'].append(ece(e, yy, e, ix))
        acc['ece_after'].append(ece(c, yy, e, ix))
        acc['brier_diff'].append(brier(c, yy) - brier(e, yy))
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)), len(v)] for k, v in acc.items()}


def judge(ev):
    o = ev['overall']
    big = [b for b in ev['bins'] if b['n'] >= 300]
    c1 = o['ece_after'] <= 0.5 and o['ece_after'] < o['ece_before']
    c2 = all(abs(b['cal_mean'] - b['actual']) <= 1.0 for b in big)
    c3 = o['brier_after'] < o['brier_before']
    if not big:
        verdict = '판정 불가'
    else:
        verdict = '채택' if (c1 and c2 and c3) else '불채택'
    return dict(c1=c1, c2=c2, c3=c3, bins_ge300=[b['bin'] for b in big],
                worst_bin_diff=max((abs(b['cal_mean'] - b['actual']) for b in big), default=None), verdict=verdict)


# ---------------------------------------------------------------- 출력
def row_out(r, c):
    d = {k: v for k, v in r.items() if k != '_i'}
    d['joinedLine'] = r['_i']
    d['cal'] = round(float(c), 6)
    return d


def write_rows(path, recs, cals):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for r, c in zip(recs, cals):
            f.write(json.dumps(row_out(r, c), ensure_ascii=False) + '\n')


def fmt_bins(ev, ci=True):
    bt = ev.get('boot', {})
    lines = ['| 엔진 값 구간 | 버림 | 방총 | 실제 방총률 | 엔진 평균 | 보정 평균 | 보정 − 실측 | 엔진 − 실측 | 실제 95% 구간(판 부트스트랩) |',
             '|---|---|---|---|---|---|---|---|---|']
    for b in ev['bins']:
        if not b['n']:
            lines.append(f"| {b['bin']} | 0 | – | – | – | – | – | – | – |")
            continue
        c = bt.get('actual:' + b['bin'])
        cis = f'{c[0]:.2f} ~ {c[1]:.2f}%' if (ci and c) else '–'
        lines.append(f"| {b['bin']} | {b['n']:,} | {b['dealt']} | {b['actual']:.2f}% | {b['engine_mean']:.2f}% | "
                     f"{b['cal_mean']:.2f}% | {b['cal_mean'] - b['actual']:+.2f} | {b['engine_mean'] - b['actual']:+.2f} | {cis} |")
    return '\n'.join(lines)


def fmt_overall(ev):
    o = ev['overall']
    bt = ev.get('boot', {})
    def ci(k, s=1.0, f='{:.2f}'):
        c = bt.get(k)
        return f' ({f.format(c[0] * s)} ~ {f.format(c[1] * s)})' if c else ''
    return '\n'.join([
        '| 지표 | 보정 전 | 보정 후 |', '|---|---|---|',
        f"| ECE(%p, 같은 개수 10 구간) | {o['ece_before']:.3f}{ci('ece_before', f='{:.3f}')} | {o['ece_after']:.3f}{ci('ece_after', f='{:.3f}')} |",
        f"| Brier | {o['brier_before']:.6f} | {o['brier_after']:.6f} (차 {o['brier_after'] - o['brier_before']:+.6f}{ci('brier_diff', f='{:+.6f}')}) |",
        f"| 예측 평균 / 실측 | {o['engine_mean']:.3f}% / {o['actual']:.3f}% | {o['cal_mean']:.3f}% / {o['actual']:.3f}% |",
        f"| 버림 · 방총 | {o['n']:,} · {o['dealt']} | |"])


def fmt_table(name, tab):
    lines = [f"**{name} 보정표** — 비안전 버림 {tab['n_nonsafe']:,}(방총 {tab['n_dealt_nonsafe']}), PAV 덩어리 {tab['n_pav_blocks']} → 200개 이상으로 합쳐 {len(tab['blocks'])}; "
             f"safeAll {tab['safe_n']:,}(방총 {tab['safe_dealt']}, 엔진 값 최대 {tab['safe_engine_max']:.3f}%)",
             '', '| # | 엔진 값 범위 | 버림 | 방총 | 점: 엔진 평균 → 실측 |', '|---|---|---|---|---|']
    for i, b in enumerate(tab['blocks']):
        lines.append(f"| {i + 1} | {b['x_min']:.3f} ~ {b['x_max']:.3f} | {b['n']:,} | {b['dealt']} | {b['x_mean']:.4f}% → {b['rate']:.4f}% |")
    return '\n'.join(lines)


# ---------------------------------------------------------------- 실행
def cmd_fit():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    recs, cnt = load('dev')
    R = [r for r in recs if r['kind'] == 'R']
    C = [r for r in recs if r['kind'] == 'C']
    tR = build_table(R)
    tC = build_table(C)
    c_uses_r = len(tC['blocks']) < 3
    table = dict(design='docs/risk_calibration_design_1123.md', made='2026-11-23', source='mxfit/stage1 개발 200판',
                 min_block=MIN_BLOCK, unit='%', interp='점 사이 직선, 첫 점 아래 = 첫 점 y, 마지막 점 위 = 마지막 점 y, safeAll = 0',
                 R=tR, C=(tR if c_uses_r else tC), C_own=tC, C_uses_R=c_uses_r)
    # 검사: 비감소
    checks = {}
    for k in ('R', 'C'):
        t = table[k]
        ys = [p[1] for p in t['points']]
        xs = [p[0] for p in t['points']]
        grid = np.linspace(0, 100, 100001)
        g = apply_table(t, grid, np.zeros(len(grid), bool))
        checks[k] = dict(points_y_nondecreasing=all(b >= a for a, b in zip(ys, ys[1:])),
                         points_x_increasing=all(b > a for a, b in zip(xs, xs[1:])),
                         grid_nondecreasing=bool(np.all(np.diff(g) >= -1e-12)),
                         min_block=min(b['n'] for b in t['blocks']))
    evR, calR = evaluate(R, table['R'])
    evC, calC = evaluate(C, table['C'])
    # 표 16-11 대조(R 보정 전 구간 표)
    cmp1611 = []
    for b in evR['bins']:
        n0, d0, e0 = T1611[b['bin']]
        cmp1611.append(dict(bin=b['bin'], now=(b['n'], b['dealt'], round(b['engine_mean'], 2)), t1611=(n0, d0, e0),
                            same=(b['n'] == n0 and b['dealt'] == d0 and abs(round(b['engine_mean'], 2) - e0) < 0.006)))
    with open(os.path.join(OUT, 'table.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(table, f, ensure_ascii=False, indent=1)
    write_rows(os.path.join(OUT, 'dev_rows.jsonl'), R + C, list(calR) + list(calC))
    # 덤(판정 기준은 안 바꿈): 보정 값이 참 확률이라 치고 방총을 뽑았을 때 ECE 가 얼마나 나오나(표본 잡음 바닥), 개발 행으로 200번
    floor = {}
    rng = np.random.default_rng(BOOT_SEED + 2)
    for k, rs, cal in (('R', R, calR), ('C', C, calC)):
        eng = np.array([r['engine'] for r in rs])
        idx = np.array([r['_i'] for r in rs])
        masks = [m for _, m in bin_masks(eng) if m.sum() >= 300]
        sims, c2 = [], []
        for _ in range(200):
            ys = (rng.random(len(cal)) < cal / 100).astype(float)
            sims.append(ece(cal, ys, eng, idx))
            c2.append(all(abs(cal[m].mean() - 100 * ys[m].mean()) <= 1.0 for m in masks))
        floor[k] = dict(mean=float(np.mean(sims)), p95=float(np.percentile(sims, 95)), share_le_0p5=float(np.mean(np.array(sims) <= 0.5)),
                        c2_pass_share=float(np.mean(c2)))
    dev = dict(counts=cnt, n_R=len(R), n_C=len(C), dealt_R=sum(r['dealt'] for r in R), dealt_C=sum(r['dealt'] for r in C),
               checks=checks, cmp1611=cmp1611, ece_noise_floor=floor, R=evR, C=evC, judge_R_dev=judge(evR), judge_C_dev=judge(evC), secs=time.time() - t0)
    with open(os.path.join(OUT, 'dev_eval.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(dev, f, ensure_ascii=False, indent=1)
    print(f"개발: 대상 R {len(R)}(방총 {dev['dealt_R']}) · C {len(C)}(방총 {dev['dealt_C']}) · {cnt}")
    print('표 16-11 대조:', all(c['same'] for c in cmp1611), [c for c in cmp1611 if not c['same']])
    print('비감소 검사:', checks, '· C 가 R 표 씀:', c_uses_r)
    for k, ev in (('R', evR), ('C', evC)):
        o = ev['overall']
        print(f"{k} 개발 ECE {o['ece_before']:.3f} → {o['ece_after']:.3f} · Brier {o['brier_before']:.6f} → {o['brier_after']:.6f} · "
              f"평균 {o['engine_mean']:.3f}/{o['cal_mean']:.3f} vs {o['actual']:.3f}")
    print('ECE 잡음 바닥(완벽 보정 가정, 200번):', floor)
    print(f'{time.time() - t0:.1f}초')


def cmd_test():
    t0 = time.time()
    tp = os.path.join(OUT, 'test_rows.jsonl')
    if os.path.exists(tp) and '--again' not in sys.argv:
        sys.exit('시험 판은 이미 채점함(test_rows.jsonl 있음) — 설계서: 한 번만')
    table = json.load(open(os.path.join(OUT, 'table.json'), encoding='utf-8'))
    dev = json.load(open(os.path.join(OUT, 'dev_eval.json'), encoding='utf-8'))
    recs, cnt = load('test')
    R = [r for r in recs if r['kind'] == 'R']
    C = [r for r in recs if r['kind'] == 'C']
    evR, calR = evaluate(R, table['R'])
    evC, calC = evaluate(C, table['C'])
    jR, jC = judge(evR), judge(evC)
    write_rows(tp, R + C, list(calR) + list(calC))
    res = dict(counts=cnt, n_R=len(R), n_C=len(C), dealt_R=sum(r['dealt'] for r in R), dealt_C=sum(r['dealt'] for r in C),
               n_games=len(set(r['game'] for r in recs)), R=evR, C=evC, judge_R=jR, judge_C=jC,
               boot=dict(n=BOOT_N, seed=BOOT_SEED, unit='판'), secs=time.time() - t0)
    with open(os.path.join(OUT, 'test_eval.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    write_summary(table, dev, res)
    for k, ev, j in (('R', evR, jR), ('C', evC, jC)):
        o = ev['overall']
        print(f"{k} 시험: {o['n']} 버림 · 방총 {o['dealt']} · ECE {o['ece_before']:.3f} → {o['ece_after']:.3f} · "
              f"Brier {o['brier_before']:.6f} → {o['brier_after']:.6f} · 평균 {o['engine_mean']:.3f}/{o['cal_mean']:.3f} vs {o['actual']:.3f} · {j}")
    print(f'{time.time() - t0:.1f}초')


def write_summary(table, dev, res):
    L = ['# 엔진 방총 위험 % 보정 — 1단계 측정 결과 (2026-11-23)', '',
         '설계서 `docs/risk_calibration_design_1123.md` 1 ~ 4절 그대로. 스크립트 `experiments/paifu_review/pushfold/risk_calibrate.py` '
         '(`fit` → `test`). 시험 판(stage2)은 보정표를 만든 뒤 한 번 채점.', '',
         '## 판정', '',
         '| 묶음 | ① ECE ≤ 0.5%p 이고 보정 전보다 작음 | ② 300개 이상 구간마다 |보정 − 실측| ≤ 1.0%p | ③ Brier 감소 | 판정 |',
         '|---|---|---|---|---|']
    for k in ('R', 'C'):
        j, o = res['judge_' + k], res[k]['overall']
        L.append(f"| {k} | {'예' if j['c1'] else '아니오'} ({o['ece_before']:.3f} → {o['ece_after']:.3f}) | "
                 f"{'예' if j['c2'] else '아니오'} (최대 {j['worst_bin_diff']:.2f}%p, 구간 {', '.join(j['bins_ge300'])}) | "
                 f"{'예' if j['c3'] else '아니오'} ({o['brier_before']:.6f} → {o['brier_after']:.6f}) | **{j['verdict']}** |")
    L += ['', f"C 보정표: {'개발 판 덩어리가 셋 미만이라 R 표를 씀' if table['C_uses_R'] else 'C 자체 표(덩어리 ' + str(len(table['C']['blocks'])) + '개)'}", '']
    for k in ('R', 'C'):
        L += [f'## 시험 판 {k}(위협 {"리치 하나 이상" if k == "R" else "울기만"}) — 보정 전 · 후', '', fmt_overall(res[k]), '',
              fmt_bins(res[k]), '']
        ns = res[k]['nonsafe_overall']
        if ns:
            L += [f"덤(판정에 안 씀) safeAll 뺀 {ns['n']:,}개: ECE {ns['ece_before']:.3f} → {ns['ece_after']:.3f}, "
                  f"Brier {ns['brier_before']:.6f} → {ns['brier_after']:.6f}, 평균 {ns['engine_mean']:.3f}/{ns['cal_mean']:.3f}% vs 실측 {ns['actual']:.3f}%.", '']
        ts = res[k]['ece_tie_shuffle']
        od = res[k]['order']
        L += [f"동률 순서를 무작위로 바꾼 ECE 20번(덤): 보정 전 {ts['before_min']:.3f} ~ {ts['before_max']:.3f}, 보정 후 {ts['after_min']:.3f} ~ {ts['after_max']:.3f}. "
              f"순서: 비안전 엔진 값 {od['distinct_engine_nonsafe']:,}종 → 보정 값 {od['distinct_cal_nonsafe']:,}종, 뒤집힘 {od['order_violations']}.", '']
    L += ['## 보정표(개발 200판, table.json)', '', fmt_table('R', table['R']), '', fmt_table('C', table['C_own']), '']
    L += ['## 검사', '',
          f"- 개발 판 대상: R {dev['n_R']:,}(방총 {dev['dealt_R']}) · C {dev['n_C']:,}(방총 {dev['dealt_C']}). 셈: {dev['counts']}",
          f"- 표 16-11 대조(개발 R 보정 전 구간 표 버림 · 방총 · 엔진 평균): {'모두 같음' if all(c['same'] for c in dev['cmp1611']) else '다름 ' + str([c for c in dev['cmp1611'] if not c['same']])}",
          f"- 비감소: {dev['checks']}"]
    for k in ('R', 'C'):
        o = dev[k]['overall']
        L.append(f"- 개발 판에 보정 적용 {k}: ECE {o['ece_before']:.3f} → {o['ece_after']:.3f}%p, Brier {o['brier_before']:.6f} → {o['brier_after']:.6f}, "
                 f"평균 {o['engine_mean']:.3f} → {o['cal_mean']:.3f}% vs 실측 {o['actual']:.3f}%")
    L += [f"- 시험 판: {res['n_games']}판, R {res['n_R']:,}(방총 {res['dealt_R']}) · C {res['n_C']:,}(방총 {res['dealt_C']}). 셈: {res['counts']}",
          f"- 부트스트랩: 판 단위 {res['boot']['n']}번, 씨 {res['boot']['seed']}",
          f"- 덤(기준 안 바꿈) ECE 잡음 바닥 — 개발 행에서 보정 값을 참 확률로 두고 방총을 200번 뽑아 잰 ECE: "
          + ' · '.join(f"{k} 평균 {v['mean']:.3f} · 95분위 {v['p95']:.3f} · 0.5 이하 비율 {100 * v['share_le_0p5']:.0f}% · 같은 가정에서 기준 ② 통과 비율 {100 * v['c2_pass_share']:.0f}%" for k, v in dev['ece_noise_floor'].items()),
          '- 부트스트랩 ECE 구간은 위로 치우친다(같은 판이 겹쳐 뽑혀 잡음이 커짐) — 점 값이 구간 밖일 수 있음, 판정은 점 값으로.', '',
          '## 개발 판 R 구간 표(보정 전 · 후, 참고)', '', fmt_bins(dev['R']), '',
          '## 개발 판 C 구간 표(보정 전 · 후, 참고)', '', fmt_bins(dev['C']), '']
    with open(os.path.join(OUT, 'summary.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L))


# ================================================================ 다시 재기(설계서 8절, 11-23)
def thr_v2(cal_mean, n, mult=2):
    """고친 기준 ② 문턱(%p): max(1.0, mult × SE), SE = √(p(1 − p)/n), p = 그 구간 보정 평균.
    mult 2 = 8절, 3 = 9절."""
    p = cal_mean / 100
    return max(1.0, mult * 100 * float(np.sqrt(max(p * (1 - p), 0.0) / n)))


def judge_v3(ev):
    """설계서 9절 기준 ①②③ — ② = max(1.0%p, 3×SE). ① · ③ 은 judge() 와 같다."""
    return judge_v2(ev, mult=3)


def judge_v2(ev, mult=2):
    """설계서 8절 기준 ①②③ — ② 만 고침(max(1.0%p, 2×SE)). ① · ③ 은 judge() 와 같다. mult=3 이면 9절."""
    o = ev['overall']
    big = [b for b in ev['bins'] if b['n'] >= 300]
    c1 = o['ece_after'] <= 0.5 and o['ece_after'] < o['ece_before']
    per = [dict(bin=b['bin'], n=b['n'], diff=b['cal_mean'] - b['actual'], thr=thr_v2(b['cal_mean'], b['n'], mult),
                ok=abs(b['cal_mean'] - b['actual']) <= thr_v2(b['cal_mean'], b['n'], mult)) for b in big]
    c2 = all(x['ok'] for x in per)
    c3 = o['brier_after'] < o['brier_before']
    verdict = '판정 불가' if not big else ('통과' if (c1 and c2 and c3) else '못 미침')
    return dict(c1=c1, c2=c2, c3=c3, bins_ge300=[b['bin'] for b in big], c2_bins=per, verdict=verdict,
                worst_excess=max((abs(x['diff']) - x['thr'] for x in per), default=None))


def _chunks(pred, eng, idx):
    return np.array_split(np.lexsort((idx, eng, pred)), N_ECE)


def _ece_fast(chunks, pred, y, n):
    return sum(len(ch) * abs(pred[ch].mean() - 100 * y[ch].mean()) for ch in chunks if len(ch)) / n


def cmd_sim599():
    """시험 판을 열기 전 — 개발 행(R · C)에서 보정값을 참 확률로 두고 방총을 SIM_N 번 뽑아 ①②③ 통과 비율."""
    t0 = time.time()
    table = json.load(open(os.path.join(OUT, 'table.json'), encoding='utf-8'))
    recs, cnt = load('dev')
    rng = np.random.default_rng(SIM_SEED)
    out = dict(n_sim=SIM_N, seed=SIM_SEED, min_pass=SIM_MIN_PASS, source='개발 200판(stage1) 행, table.json 보정값 = 참 확률',
               counts=cnt)
    for k in ('R', 'C'):
        rs = [r for r in recs if r['kind'] == k]
        eng = np.array([r['engine'] for r in rs])
        safe = np.array([r['safeAll'] for r in rs])
        idx = np.array([r['_i'] for r in rs])
        cal = apply_table(table[k], eng, safe)
        n = len(rs)
        big = [(name, m, float(cal[m].mean()), int(m.sum())) for name, m in bin_masks(eng) if m.sum() >= 300]
        thr = {name: thr_v2(cm, nn) for name, _, cm, nn in big}
        ch_c, ch_e = _chunks(cal, eng, idx), _chunks(eng, eng, idx)
        p1 = p2 = p3 = pall = p2old = pall_old = 0
        fail_bins = defaultdict(int)
        eces = []
        for it in range(SIM_N):
            ys = (rng.random(n) < cal / 100).astype(float)
            ea, eb = _ece_fast(ch_c, cal, ys, n), _ece_fast(ch_e, eng, ys, n)
            if it == 0:
                assert abs(ea - ece(cal, ys, eng, idx)) < 1e-9 and abs(eb - ece(eng, ys, eng, idx)) < 1e-9
            c1 = ea <= 0.5 and ea < eb
            diffs = {name: abs(cm - 100 * ys[m].mean()) for name, m, cm, _ in big}
            c2 = all(diffs[nm] <= thr[nm] for nm in diffs)
            c2o = all(d <= 1.0 for d in diffs.values())
            for nm in diffs:
                fail_bins[nm] += diffs[nm] > thr[nm]
            c3 = brier(cal, ys) < brier(eng, ys)
            p1 += c1
            p2 += c2
            p3 += c3
            pall += c1 and c2 and c3
            p2old += c2o
            pall_old += c1 and c2o and c3
            eces.append(ea)
        out[k] = dict(n_rows=n, expected_dealt=float(cal.sum() / 100), actual_dealt_dev=int(sum(r['dealt'] for r in rs)),
                      bins_ge300=[dict(bin=nm, n=nn, cal_mean=cm, thr=thr[nm]) for nm, _, cm, nn in big],
                      pass_c1=p1 / SIM_N, pass_c2=p2 / SIM_N, pass_c3=p3 / SIM_N, pass_all=pall / SIM_N,
                      pass_c2_old_fixed1=p2old / SIM_N, pass_all_old=pall_old / SIM_N,
                      c2_fail_by_bin={nm: v / SIM_N for nm, v in fail_bins.items()},
                      ece_after_mean=float(np.mean(eces)), ece_after_p95=float(np.percentile(eces, 95)))
        print(f"{k}: 행 {n:,} · ① {p1 / SIM_N:.3f} · ② {p2 / SIM_N:.3f} · ③ {p3 / SIM_N:.3f} · 모두 {pall / SIM_N:.3f} "
              f"(옛 ② 고정 1%p: ② {p2old / SIM_N:.3f} · 모두 {pall_old / SIM_N:.3f}) · ② 구간별 실패 {dict(fail_bins)} · "
              f"문턱 {thr}")
    out['go'] = all(out[k]['pass_all'] >= SIM_MIN_PASS for k in ('R', 'C'))
    out['secs'] = time.time() - t0
    with open(os.path.join(OUT, 'sim599.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('시험 판 열어도 됨(R · C 모두 80% 이상):', out['go'], f"· {out['secs']:.1f}초")


SIM3_SEED = 20261129
SIM3_GAMES = 599
SIM3_MIN_PASS = 0.90


def cmd_sim599v3():
    """설계서 9절 열기 전 점검 — 개발 200판에서 판 단위로 599판 복원 추출(R · C 같은 뽑기) → 보정값을 참 확률로 방총 뽑기
    → ①②(max(1.0, 3×SE), n · p 는 그 가짜 자료의 구간 값)③. SIM_N 번, 씨 SIM3_SEED, 한 번만."""
    t0 = time.time()
    op = os.path.join(OUT, 'sim599_v3.json')
    if os.path.exists(op):
        sys.exit('9절 점검은 이미 돌림(sim599_v3.json 있음) — 한 번만')
    table = json.load(open(os.path.join(OUT, 'table.json'), encoding='utf-8'))
    recs, cnt = load('dev')
    games = sorted(set(r['game'] for r in recs))
    assert len(games) == 200
    gi = {g: i for i, g in enumerate(games)}
    rng = np.random.default_rng(SIM3_SEED)
    D = {}
    for k in ('R', 'C'):
        rs = [r for r in recs if r['kind'] == k]
        eng = np.array([r['engine'] for r in rs])
        safe = np.array([r['safeAll'] for r in rs])
        cal = apply_table(table[k], eng, safe)
        gidx = np.array([gi[r['game']] for r in rs])
        D[k] = dict(eng=eng, cal=cal, rows_of=[np.flatnonzero(gidx == i) for i in range(len(games))],
                    acc=defaultdict(int), fail_bins=defaultdict(int), nbig=[], nrows=[])
    for it in range(SIM_N):
        pick = rng.integers(0, len(games), SIM3_GAMES)
        for k in ('R', 'C'):
            d = D[k]
            ii = np.concatenate([d['rows_of'][p] for p in pick])
            eng, cal = d['eng'][ii], d['cal'][ii]
            n = len(ii)
            ys = (rng.random(n) < cal / 100).astype(float)
            idx = np.arange(n)  # 동률 순서: 이어 붙인 차례 순
            ea, eb = ece(cal, ys, eng, idx), ece(eng, ys, eng, idx)
            c1 = ea <= 0.5 and ea < eb
            c2 = True
            nb = 0
            for name, m in bin_masks(eng):
                nn = int(m.sum())
                if nn < 300:
                    continue
                nb += 1
                cm = float(cal[m].mean())
                bad = abs(cm - 100 * ys[m].mean()) > thr_v2(cm, nn, 3)
                d['fail_bins'][name] += bad
                c2 = c2 and not bad
            c3 = brier(cal, ys) < brier(eng, ys)
            a = d['acc']
            a['c1'] += c1
            a['c2'] += c2
            a['c3'] += c3
            a['all'] += c1 and c2 and c3
            d['nbig'].append(nb)
            d['nrows'].append(n)
    out = dict(design='docs/risk_calibration_design_1123.md 9절', n_sim=SIM_N, seed=SIM3_SEED, games_per_sim=SIM3_GAMES,
               min_pass=SIM3_MIN_PASS, source='개발 200판(stage1) 판 단위 복원 추출 599판(R · C 같은 뽑기), table.json 보정값 = 참 확률',
               c2_rule='max(1.0%p, 3×SE), SE = √(p(1−p)/n), p · n = 가짜 자료 구간의 보정 평균 · 버림 수', counts=cnt)
    for k in ('R', 'C'):
        d = D[k]
        a = d['acc']
        out[k] = dict(pass_c1=a['c1'] / SIM_N, pass_c2=a['c2'] / SIM_N, pass_c3=a['c3'] / SIM_N, pass_all=a['all'] / SIM_N,
                      c2_fail_by_bin={nm: v / SIM_N for nm, v in d['fail_bins'].items()},
                      rows_median=float(np.median(d['nrows'])), bins_ge300_min=int(min(d['nbig'])), bins_ge300_max=int(max(d['nbig'])))
        print(k, out[k])
    out['go'] = all(out[k]['pass_all'] >= SIM3_MIN_PASS for k in ('R', 'C'))
    out['secs'] = time.time() - t0
    with open(op, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('9절: 599판 열어도 됨(R · C 모두 90% 이상):', out['go'], f"· {out['secs']:.1f}초")


def _joined_rows_from_features(feat_dir):
    """stage2 joined 와 같은 차례 고르기: features 줄 중 afterRiichi 아닌 것, 열쇠 (game, kyoku, seat, k) 순.
    (stage1 · stage2 join_report: features 에만 있는 줄은 모두 afterRiichi, S42 에만 있는 줄 0, actual 어긋남 0.
    깡 든 국은 tenhou6_features.dart 가 이미 뺀다 — summary.kanSkipped.)"""
    import join as mxjoin  # mxfit/join.py
    feats, summaries = mxjoin.read_features(feat_dir)
    fa = {}
    dup = 0
    for r in feats:
        dup += mxjoin.key(r) in fa
        fa[mxjoin.key(r)] = r
    keep = [fa[k] for k in sorted(fa) if not fa[k].get('afterRiichi')]
    rep = dict(featuresRows=len(feats), duplicateKeys=dup, afterRiichi=len(fa) - len(keep), joined=len(keep),
               games=len(summaries), kyokus=sum(s['kyokus'] for s in summaries),
               kanSkipped=sum(s['kanSkipped'] for s in summaries), kyokuSeats=sum(s['kyokuSeats'] for s in summaries),
               errors=sum(s['errors'] for s in summaries), errorList=[e for s in summaries for e in s['errorList']])
    return keep, rep


def cmd_joincheck():
    """stage2 features 에 같은 규칙을 적용 → stage2 joined(s42 칸 뺀 것)와 줄 순서까지 같은지."""
    from pathlib import Path
    st2 = os.path.join(PR, 'results', 'mxfit', 'stage2')
    keep, rep = _joined_rows_from_features(Path(os.path.join(st2, 'features')))
    n = same = 0
    first_diff = None
    with gzip.open(os.path.join(st2, 'joined.jsonl.gz'), 'rt', encoding='utf-8') as f:
        for i, line in enumerate(f):
            j = json.loads(line)
            j.pop('s42', None)
            n += 1
            if i < len(keep) and keep[i] == j:
                same += 1
            elif first_diff is None:
                first_diff = i
    ok = n == len(keep) == same
    res = dict(stage2_joined=n, rebuilt=len(keep), same_rows_in_order=same, first_diff=first_diff, ok=ok, report=rep)
    with open(os.path.join(OUT, 'joincheck_stage2.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != 'report'}, ensure_ascii=False),
          {k: v for k, v in rep.items() if k != 'errorList'})
    if not ok:
        sys.exit(1)


def cmd_join599():
    from pathlib import Path
    st3 = os.path.join(PR, 'results', 'mxfit', 'stage3')
    keep, rep = _joined_rows_from_features(Path(os.path.join(st3, 'features')))
    games = {r['game'] for r in keep}
    assert games <= set(split.test599_games()), '새 시험 599판 밖의 판'
    rep['gamesWithRows'] = len(games)
    rep['gamesMissing'] = sorted(set(split.test599_games()) - games)
    with gzip.open(JOINED['test599'], 'wt', encoding='utf-8', newline='\n', compresslevel=6) as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    with open(os.path.join(st3, 'join_report.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k not in ('errorList',)}, ensure_ascii=False))


def fmt_bins_v2(ev, mult=3):
    bt = ev.get('boot', {})
    lines = [f'| 엔진 값 구간 | 버림 | 방총 | 실측 | 엔진 평균 | 보정 평균 | 보정 − 실측 | 엔진 − 실측 | ② 문턱 max(1, {mult}×SE) | ② | 실측 95% 구간(판 부트) | 보정 − 실측 95% 구간(판 부트) |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for b in ev['bins']:
        if not b['n']:
            lines.append(f"| {b['bin']} | 0 | – | – | – | – | – | – | – | – | – | – |")
            continue
        c = bt.get('actual:' + b['bin'])
        d = bt.get('diffcal:' + b['bin'])
        th = thr_v2(b['cal_mean'], b['n'], mult)
        diff = b['cal_mean'] - b['actual']
        mark = ('✓' if abs(diff) <= th else '✗') if b['n'] >= 300 else '(300 미만)'
        cs = f'{c[0]:.2f} ~ {c[1]:.2f}%' if c else '–'
        ds = f'{d[0]:+.2f} ~ {d[1]:+.2f}' if d else '–'
        lines.append(f"| {b['bin']} | {b['n']:,} | {b['dealt']} | {b['actual']:.2f}% | {b['engine_mean']:.2f}% | {b['cal_mean']:.2f}% | "
                     f"{diff:+.2f} | {b['engine_mean'] - b['actual']:+.2f} | {th:.2f} | {mark} | {cs} | {ds} |")
    return '\n'.join(lines)


def cmd_test599():
    """새 시험 599판 한 번 채점 — 판정은 설계서 9절(② = max(1.0, 3×SE)). 열기 전 점검은 9절 sim599_v3.json 의 go 를 본다
    (8절 sim599.json 의 go=false 는 그대로 둠). 참고: 8절 ②(2×SE) · 1단계 ②(고정 1%p) · 799판 합친 지표."""
    t0 = time.time()
    tp = os.path.join(OUT, 'test599_rows.jsonl')
    if os.path.exists(tp):
        sys.exit('새 시험 599판은 이미 채점함(test599_rows.jsonl 있음) — 설계서 8 · 9절: 한 번만')
    sim = json.load(open(os.path.join(OUT, 'sim599_v3.json'), encoding='utf-8'))
    if not sim.get('go'):
        sys.exit('9절 점검 통과율 90% 미만 — 시험 판을 열지 않는다(설계서 9절)')
    table = json.load(open(os.path.join(OUT, 'table.json'), encoding='utf-8'))
    recs, cnt = load('test599')
    R = [r for r in recs if r['kind'] == 'R']
    C = [r for r in recs if r['kind'] == 'C']
    evR, calR = evaluate(R, table['R'])
    evC, calC = evaluate(C, table['C'])
    write_rows(tp, R + C, list(calR) + list(calC))
    res = dict(counts=cnt, n_games=len(set(r['game'] for r in recs)), n_R=len(R), n_C=len(C),
               dealt_R=sum(r['dealt'] for r in R), dealt_C=sum(r['dealt'] for r in C),
               R=evR, C=evC, judge_R=judge_v3(evR), judge_C=judge_v3(evC),
               ref_v2_R=judge_v2(evR), ref_v2_C=judge_v2(evC),
               ref_old_c2_R=judge(evR), ref_old_c2_C=judge(evC), boot=dict(n=BOOT_N, seed=BOOT_SEED, unit='판'))
    # 참고(판정에 안 씀): 첫 시험 200 + 새 599 = 799판. 줄 번호(_i, ECE 동률 순서에만 쓰임)는 두 파일을 이어 붙인 순서로.
    old, _ = load('test')
    ref = {}
    shift = 1 + max((r['_i'] for r in old), default=0)
    for k, rs in (('R', R), ('C', C)):
        o = [r for r in old if r['kind'] == k]
        comb = o + [dict(r, _i=r['_i'] + shift) for r in rs]
        ev, _ = evaluate(comb, table[k])
        ref[k] = dict(n_games=len(set(r['game'] for r in comb)), ev=ev, judge_v3=judge_v3(ev), judge_v2=judge_v2(ev),
                      judge_old=judge(ev))
    res['ref799'] = ref
    res['secs'] = time.time() - t0
    with open(os.path.join(OUT, 'test599_eval.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    write_summary599(sim, res)
    for k in ('R', 'C'):
        o, j = res[k]['overall'], res['judge_' + k]
        print(f"{k} 새 시험: {o['n']} 버림 · 방총 {o['dealt']} · ECE {o['ece_before']:.3f} → {o['ece_after']:.3f} · "
              f"Brier {o['brier_before']:.6f} → {o['brier_after']:.6f} · 평균 {o['engine_mean']:.3f}/{o['cal_mean']:.3f} vs {o['actual']:.3f} · "
              f"①{j['c1']} ②{j['c2']} ③{j['c3']} → {j['verdict']} (8절 2×SE: {res['ref_v2_' + k]['verdict']}, 1단계: {res['ref_old_c2_' + k]['verdict']})")
    print(f"{res['secs']:.1f}초")


def write_summary599(sim, res):
    jr, jc = res['judge_R'], res['judge_C']
    both = jr['verdict'] == '통과' and jc['verdict'] == '통과'
    one = (jr['verdict'] == '통과') != (jc['verdict'] == '통과')
    final = '둘 다 통과 → 앱 2단계(6절)' if both else ('하나만 통과 → 사용자에게 묻기' if one else '둘 다 못 미침 → 접기')
    L = ['# 엔진 방총 위험 % 보정 — 다시 재기(새 시험 599판) 결과 (2026-11-23)', '',
         '설계서 `docs/risk_calibration_design_1123.md` 9절 기준(② = max(1.0%p, 3×SE)). 보정표는 1단계 `table.json`(개발 200판)을 읽기만 함. '
         '스크립트 `experiments/paifu_review/pushfold/risk_calibrate.py`(`sim599v3` → `joincheck` → `join599` → `test599`). 새 시험 판은 한 번 채점.', '',
         f'## 판정(9절): **{final}**', '',
         '| 묶음 | ① ECE ≤ 0.5%p 이고 보정 전보다 작음 | ② 300개 이상 구간마다 |보정 − 실측| ≤ max(1.0%p, 3×SE) | ③ Brier 감소 | 판정 |',
         '|---|---|---|---|---|']
    for k in ('R', 'C'):
        j, o = res['judge_' + k], res[k]['overall']
        bad = [f"{x['bin']} {x['diff']:+.2f}/{x['thr']:.2f}" for x in j['c2_bins'] if not x['ok']]
        c2s = f"{len(j['c2_bins'])}구간, " + ('넘은 구간 ' + '; '.join(bad) if bad else '모두 문턱 안')
        L.append(f"| {k} | {'예' if j['c1'] else '아니오'} ({o['ece_before']:.3f} → {o['ece_after']:.3f}) | "
                 f"{'예' if j['c2'] else '아니오'} ({c2s}) | "
                 f"{'예' if j['c3'] else '아니오'} ({o['brier_before']:.6f} → {o['brier_after']:.6f}) | **{j['verdict']}** |")
    L += ['', '## 열기 전 점검(9절 — 개발 200판에서 판 단위 599판 복원 추출, 보정값 = 참 확률)', '',
          f"{sim['n_sim']}번, 씨 {sim['seed']}. 문턱 {100 * sim['min_pass']:.0f}%. (8절 점검 sim599.json: R 79.8% · C 84.6%, go=false — 그대로 둠)", '',
          '| 묶음 | ① | ② (3×SE) | ③ | ①②③ 모두 |', '|---|---|---|---|---|']
    for k in ('R', 'C'):
        s = sim[k]
        L.append(f"| {k} | {100 * s['pass_c1']:.1f}% | {100 * s['pass_c2']:.1f}% | {100 * s['pass_c3']:.1f}% | **{100 * s['pass_all']:.1f}%** |")
    for k in ('R', 'C'):
        L += ['', f'## 새 시험 판 {k}(위협 {"리치 하나 이상" if k == "R" else "울기만"}) — 보정 전 · 후', '', fmt_overall(res[k]), '',
              fmt_bins_v2(res[k], 3), '']
        ns = res[k]['nonsafe_overall']
        if ns:
            L += [f"덤(판정에 안 씀) safeAll 뺀 {ns['n']:,}개: ECE {ns['ece_before']:.3f} → {ns['ece_after']:.3f}, "
                  f"Brier {ns['brier_before']:.6f} → {ns['brier_after']:.6f}, 평균 {ns['engine_mean']:.3f}/{ns['cal_mean']:.3f}% vs 실측 {ns['actual']:.3f}%.", '']
        ts, od = res[k]['ece_tie_shuffle'], res[k]['order']
        L += [f"동률 순서 무작위 ECE 20번(덤): 보정 전 {ts['before_min']:.3f} ~ {ts['before_max']:.3f}, 보정 후 {ts['after_min']:.3f} ~ {ts['after_max']:.3f}. "
              f"순서: 비안전 엔진 값 {od['distinct_engine_nonsafe']:,}종 → 보정 값 {od['distinct_cal_nonsafe']:,}종, 뒤집힘 {od['order_violations']}.", '']
    L += ['## 참고(판정에 안 씀)', '', '### 다른 ② 를 같은 599판에 적용', '']
    for k in ('R', 'C'):
        j2, j1 = res['ref_v2_' + k], res['ref_old_c2_' + k]
        bad2 = [f"{x['bin']} {x['diff']:+.2f}/{x['thr']:.2f}" for x in j2['c2_bins'] if not x['ok']]
        L.append(f"- {k}: 8절 ②(2×SE) {'예' if j2['c2'] else '아니오'}{' (넘은 구간 ' + '; '.join(bad2) + ')' if bad2 else ''} → {j2['verdict']} · "
                 f"1단계 ②(고정 1%p) {'예' if j1['c2'] else '아니오'}(최대 {j1['worst_bin_diff']:.2f}%p) → {j1['verdict']}")
    L += ['', '### 첫 시험 200판 + 새 599판 = 799판', '']
    for k in ('R', 'C'):
        r = res['ref799'][k]
        o, jv = r['ev']['overall'], r['judge_v3']
        L += [f"**{k}** — {r['n_games']}판, 버림 {o['n']:,} · 방총 {o['dealt']}. 9절 기준: ①{'예' if jv['c1'] else '아니오'} "
              f"②{'예' if jv['c2'] else '아니오'} ③{'예' if jv['c3'] else '아니오'} → {jv['verdict']} · 8절 기준 → {r['judge_v2']['verdict']} · "
              f"1단계 기준 → {r['judge_old']['verdict']}", '',
              fmt_overall(r['ev']), '', fmt_bins_v2(r['ev'], 3), '']
    L += ['## 검사', '',
          f"- 새 시험 판: 행이 있는 판 {res['n_games']} · R {res['n_R']:,}(방총 {res['dealt_R']}) · C {res['n_C']:,}(방총 {res['dealt_C']}). 셈: {res['counts']}",
          f"- 부트스트랩: 판 단위 {res['boot']['n']}번, 씨 {res['boot']['seed']} (ECE 구간은 위로 치우침 — 판정은 점 값으로)",
          '- 방총 판정 · 구간 · ECE · Brier · 보정 적용은 1단계와 같은 함수(load · evaluate · apply_table). ② 만 judge_v3(3×SE)로.', '']
    with open(os.path.join(OUT, 'summary_test599.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L))


CMDS = {'fit': lambda: cmd_fit(), 'test': lambda: cmd_test(), 'sim599': lambda: cmd_sim599(), 'sim599v3': lambda: cmd_sim599v3(),
        'joincheck': lambda: cmd_joincheck(), 'join599': lambda: cmd_join599(), 'test599': lambda: cmd_test599()}

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        sys.exit(__doc__)
    CMDS[sys.argv[1]]()
