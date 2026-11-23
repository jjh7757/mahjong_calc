"""waitsuit.py 의 채점 · S 학습 · 누설 검사 · 진짜 판 확인 (계획서 7절). waitsuit.py 명령으로 부른다."""
import json
import math
import os
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import posinfer as PI  # noqa: E402
import waitsuit as W  # noqa: E402
from posinfer import fast_waits, tid, tname  # noqa: E402

OUT = W.OUT
CS = [0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0]
NBOOT = 2000
COND = ['A', 'B', 'P', 'PB', 'S', 'SP']
GROUPS = ['H1', 'H2', 'H3', 'mix']


def load_rows(split):
    return [json.loads(x) for x in open(os.path.join(OUT, f'riichi_{split}.jsonl'), encoding='utf-8')]


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def sig(x):
    return 1 / (1 + np.exp(-x))


def y_of(r):
    y = np.zeros(4)
    y[r['wsuits']] = 1
    return y


def top1(ps, y):
    ps = np.asarray(ps)
    m = ps.max()
    tied = np.flatnonzero(np.isclose(ps, m, rtol=0, atol=1e-12))
    return float(y[tied].mean())


def logscore(ps, y):
    p = np.clip(np.asarray(ps, float), 1e-4, 1 - 1e-4)
    return float(np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# ---------------------------------------------------------------- S(종합 기준선) — 개발 판에서만 학습
def s_fit(dev):
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupKFold
    X = np.concatenate([np.array(r['feats']) for r in dev])
    Y = np.concatenate([y_of(r) for r in dev])
    G = np.repeat([r['id'] for r in dev], 4)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = (X - mu) / sd
    gkf = GroupKFold(n_splits=5)
    cv = {}
    oof_best = None
    for C in CS:
        oof = np.zeros(len(Y))
        for tr, te in gkf.split(Xs, Y, G):
            m = LogisticRegression(C=C, max_iter=2000).fit(Xs[tr], Y[tr])
            oof[te] = m.predict_proba(Xs[te])[:, 1]
        p = np.clip(oof, 1e-4, 1 - 1e-4)
        ll = float(np.mean(Y * np.log(p) + (1 - Y) * np.log(1 - p)))
        t1 = float(np.mean([top1(oof[4 * i:4 * i + 4], Y[4 * i:4 * i + 4]) for i in range(len(dev))]))
        cv[C] = dict(logscore=ll, top1=t1)
        if oof_best is None or ll > cv[oof_best[0]]['logscore']:
            oof_best = (C, oof)
    C = oof_best[0]
    model = LogisticRegression(C=C, max_iter=2000).fit(Xs, Y)
    coef = sorted(zip(W.S_FEATS, model.coef_[0]), key=lambda x: -abs(x[1]))
    return dict(C=C, cv=cv, mu=mu, sd=sd, model=model, oof=oof_best[1], coef=coef)


def s_predict(sm, rows):
    X = np.concatenate([np.array(r['feats']) for r in rows])
    return sm['model'].predict_proba((X - sm['mu']) / sm['sd'])[:, 1].reshape(-1, 4)


# ---------------------------------------------------------------- 조건별 확률 · 순위
EPS = [0.0, 0.1, 0.2, 0.3, 0.5]


def rank_of(ratio, waits):
    ratio = np.asarray(ratio)
    best = None
    for t in waits:
        rr = 1 + (ratio > ratio[t]).sum() + ((ratio == ratio[t]).sum() - 1) / 2
        best = rr if best is None else min(best, rr)
    return float(best)


def cond_probs(r, cfg, s_ps):
    """cfg: gB · gPB(γ), eP · ePB · eSP(ε: 칸 번호 가정을 A(PB 는 같은 γ 의 B) 쪽으로 섞는 비율, 개발 판에서 고름).
    P 가 가정 깨짐(또는 텐파이 표본 0)이면 P · PB 는 B, SP 는 S 로 대신."""
    A = r['A']
    gB, gPB = str(cfg['gB']), str(cfg['gPB'])
    if A:
        a0, ra0 = np.array(A['0.0']['ps']), np.array(A['0.0']['ratio'])
        b, rb = np.array(A[gB]['ps']), np.array(A[gB]['ratio'])
    else:
        a0, ra0 = np.full(4, 0.25), np.zeros(34)
        b, rb = a0, ra0
    out = dict(A=a0, B=b)
    rat = dict(A=ra0, B=rb)
    if r['P'] is None:
        out['P'], out['PB'] = b, b
        rat['P'], rat['PB'] = rb, rb
        sp = np.asarray(s_ps)
    else:
        e = cfg['eP']
        p0, rp0 = np.array(r['P']['0.0']['ps']), np.array(r['P']['0.0']['ratio'])
        out['P'] = (1 - e) * p0 + e * a0
        rat['P'] = (1 - e) * rp0 + e * ra0
        e = cfg['ePB']
        bg = (np.array(A[gPB]['ps']), np.array(A[gPB]['ratio'])) if A else (a0, ra0)
        out['PB'] = (1 - e) * np.array(r['P'][gPB]['ps']) + e * bg[0]
        rat['PB'] = (1 - e) * np.array(r['P'][gPB]['ratio']) + e * bg[1]
        e = cfg['eSP']
        sp = sig(logit(np.asarray(s_ps)) + logit((1 - e) * p0 + e * a0) - logit(a0))
    out['S'] = np.asarray(s_ps)
    out['SP'] = sp
    rank = {c: rank_of(rat[c], r['waits']) for c in rat}
    return out, rank


def tune(dev, S_dev):
    """개발 판 로그 점수(습관 섞음)로 γ · ε 고르기. 같으면 작은 값."""
    def dlog(c, cfg):
        return float(np.mean([logscore(cond_probs(r, cfg, s)[0][c], y_of(r)) for r, s in zip(dev, S_dev)]))
    base = dict(gB=0.0, gPB=0.0, eP=0.0, ePB=0.0, eSP=0.0)
    gB = max(W.GAMMAS, key=lambda g: (round(dlog('B', dict(base, gB=g)), 6), -g))
    eP = max(EPS, key=lambda e: (round(dlog('P', dict(base, gB=gB, eP=e)), 6), -e))
    grid, best = {}, None
    for g in W.GAMMAS:
        for e in EPS:
            v = dlog('PB', dict(base, gB=gB, gPB=g, ePB=e))
            grid[f'{g}|{e}'] = v
            if best is None or round(v, 6) > round(best[0], 6):
                best = (v, g, e)
    eSP = max(EPS, key=lambda e: (round(dlog('SP', dict(base, gB=gB, eSP=e)), 6), -e))
    cfg = dict(gB=gB, gPB=best[1], eP=eP, ePB=best[2], eSP=eSP)
    tab = dict(B={g: dlog('B', dict(cfg, gB=g)) for g in W.GAMMAS},
               P={e: dlog('P', dict(cfg, eP=e)) for e in EPS},
               SP={e: dlog('SP', dict(cfg, eSP=e)) for e in EPS}, PB=grid)
    return cfg, tab


def per_riichi(rows, cfg, S):
    res = []
    for r, s_ps in zip(rows, S):
        y = y_of(r)
        ps, rk = cond_probs(r, cfg, s_ps)
        m = {}
        for c in COND:
            m[c] = dict(top1=top1(ps[c], y), log=logscore(ps[c], y))
            if c in rk:
                m[c]['top3'] = float(rk[c] <= 3)
                m[c]['top5'] = float(rk[c] <= 5)
        res.append(dict(id=r['id'], habit=r['habit'], m=m, broken=r['P'] is None))
    return res


def boot_ci(sub, vals, rng, nb=NBOOT):
    """판 단위 부트스트랩(판을 복원 추출, 고른 판의 리치 전부). vals: 리치마다 값."""
    ids = [x['id'] for x in sub]
    gl = sorted(set(ids))
    gi = {g: i for i, g in enumerate(gl)}
    gix = np.array([gi[g] for g in ids])
    S = np.bincount(gix, weights=np.asarray(vals, float), minlength=len(gl))
    N = np.bincount(gix, minlength=len(gl)).astype(float)
    pick = rng.integers(len(gl), size=(nb, len(gl)))
    m = S[pick].sum(1) / N[pick].sum(1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def table(res, games, rng, with_ci=True):
    """조건 × 집단 표."""
    out = {}
    for grp in GROUPS:
        sub = [x for x in res if grp == 'mix' or x['habit'] == grp]
        d = dict(n=len(sub), games=len(set(x['id'] for x in sub)), broken=sum(x['broken'] for x in sub))
        for c in COND:
            e = {}
            for k in ('top1', 'log', 'top3', 'top5'):
                if k not in sub[0]['m'][c]:
                    continue
                e[k] = float(np.mean([x['m'][c][k] for x in sub]))
                if with_ci and k in ('top1', 'log'):
                    e[k + '_ci'] = boot_ci(sub, [x['m'][c][k] for x in sub], rng)
            d[c] = e
        for a, b in (('SP', 'S'), ('PB', 'B'), ('P', 'A')):
            for k in ('top1', 'log'):
                v = float(np.mean([x['m'][a][k] - x['m'][b][k] for x in sub]))
                d[f'{a}-{b}_{k}'] = v
                if with_ci:
                    d[f'{a}-{b}_{k}_ci'] = boot_ci(sub, [x['m'][a][k] - x['m'][b][k] for x in sub], rng)
        out[grp] = d
    return out


def verdict(t, a, b):
    dm = t['mix'][f'{a}-{b}_top1']
    d1 = t['H1'][f'{a}-{b}_top1']
    lm = t['mix'][f'{a}-{b}_log']
    if dm >= 0.05 and d1 >= 0.10 and lm > 0:
        v = '기능 가치 있음'
    elif dm < 0.02 and d1 < 0.05:
        v = '접음'
    else:
        v = '사이 — 사용자에게 물음("정렬하는 사람에게만" 같은 제한 기능?)'
    return (f'{a} − {b}: 섞음 {dm * 100:+.1f}%p, H1 {d1 * 100:+.1f}%p, 로그 점수(섞음) {lm:+.4f} → **{v}**'), v


def fmt_ci(e, k, pct=True):
    v = e[k]
    ci = e.get(k + '_ci')
    if pct:
        s = f'{v * 100:.1f}%'
        if ci:
            s += f' [{ci[0] * 100:.1f}, {ci[1] * 100:.1f}]'
    else:
        s = f'{v:.4f}'
        if ci:
            s += f' [{ci[0]:.4f}, {ci[1]:.4f}]'
    return s


def write_table(P, t, title):
    P(f'\n### {title}\n')
    P('| 집단 | 리치(판) | 가정 깨짐(P→B) | 조건 | 대기 수트 1위 적중 [95% CI] | 로그 점수 [95% CI] | 대기 패 상위 3 | 상위 5 |')
    P('|---|---|---|---|---|---|---|---|')
    for grp in GROUPS:
        d = t[grp]
        for i, c in enumerate(COND):
            e = d[c]
            head = f'| {grp} | {d["n"]}({d["games"]}) | {d["broken"]} |' if i == 0 else '| | | |'
            P(f'{head} {c} | {fmt_ci(e, "top1")} | {fmt_ci(e, "log", False)} | '
              + (f'{e["top3"] * 100:.1f}% | {e["top5"] * 100:.1f}% |' if 'top3' in e else '— | — |'))
    P('\n차이(같은 리치끼리 짝, 판 단위 부트스트랩 95% CI):\n')
    P('| 집단 | SP−S 1위 | SP−S 로그 | PB−B 1위 | PB−B 로그 | P−A 1위 | P−A 로그 |')
    P('|---|---|---|---|---|---|---|')
    for grp in GROUPS:
        d = t[grp]
        cells = []
        for a, b in (('SP', 'S'), ('PB', 'B'), ('P', 'A')):
            v, ci = d[f'{a}-{b}_top1'], d.get(f'{a}-{b}_top1_ci')
            cells.append(f'{v * 100:+.1f}%p' + (f' [{ci[0] * 100:+.1f}, {ci[1] * 100:+.1f}]' if ci else ''))
            v, ci = d[f'{a}-{b}_log'], d.get(f'{a}-{b}_log_ci')
            cells.append(f'{v:+.4f}' + (f' [{ci[0]:+.4f}, {ci[1]:+.4f}]' if ci else ''))
        P(f'| {grp} | ' + ' | '.join(cells) + ' |')


def cmd_report(dev_only=False):
    sys.stdout.reconfigure(encoding='utf-8')
    hp = W.load_hp()
    recs, games, devset = W.load_split()
    dev = load_rows('dev')
    has_test = os.path.exists(os.path.join(OUT, 'riichi_test.jsonl')) and not dev_only
    test = load_rows('test') if has_test else dev[:0]
    dev_games = sorted(set(r['id'] for r in dev))
    test_games = sorted(set(r['id'] for r in test))
    assert not (set(dev_games) & set(test_games))
    lines = []
    P = lines.append
    # ---- S: 개발 판 교차검증
    sm = s_fit(dev)
    S_dev = sm['oof'].reshape(-1, 4)          # 개발 판 숫자는 판 묶음 5겹 바깥 예측
    S_test = s_predict(sm, test) if test else np.zeros((0, 4))
    # ---- γ · ε: 개발 판 로그 점수로
    cfg, tun = tune(dev, S_dev)
    cfg0 = dict(cfg, eP=0.0, ePB=0.0, eSP=0.0)
    rng = np.random.default_rng(7)
    res_dev = per_riichi(dev, cfg, S_dev)
    res_test = per_riichi(test, cfg, S_test)
    res_dev0 = per_riichi(dev, cfg0, S_dev)
    res_test0 = per_riichi(test, cfg0, S_test)
    t_dev = table(res_dev, dev_games, rng)
    t_test = table(res_test, test_games, rng) if test else None
    # ---- 머리
    pst = json.load(open(os.path.join(OUT, 'parse_stats.json'), encoding='utf-8'))
    pk = json.load(open(os.path.join(W.ROOT, 'experiments', 'paifu_frames', 'results', 'handinfer', 'tenhou_raw',
                                     'picked.json'), encoding='utf-8'))
    fpath = os.path.join(W.ROOT, 'experiments', 'paifu_frames', 'results', 'handinfer', 'tenhou_raw', 'fail.json')
    fails = json.load(open(fpath, encoding='utf-8')) if os.path.exists(fpath) else {}
    P('# 대기 수트 추정 — 천봉 패보 + 습관 흉내 (계획서 7절)\n')
    P(f'- 자료: {pk["year"]} 년 鳳凰卓 일별 목록 {pk["days"]}일치, 四鳳南喰赤 ID {pk["n_ids"]}개 → ID 순 · 씨 {pk["seed"]} 로 '
      f'{len(pk["picked"])}판 고름, 받음 {pst["games"]} · 실패 {len(fails)}.')
    P(f'- 파서: 국 {pst["rounds"]}, 리치(텐파이 확인) {pst["riichi_tenpai_ok"]}, 리치 직후 텐파이 아님 '
      f'{pst["riichi_not_tenpai"]}, 국 재생 오류 {pst["round_errors"]}, 리치 전 안깡(제외) {pst["riichi_with_kan_before"]}.')
    P(f'- 나누기(씨 {W.SPLIT_SEED}, 판 단위): 개발 {len(dev_games)}판 리치 {len(dev)} · 시험 {len(test_games)}판 리치 {len(test)}.')
    for nm, rows in (('개발', dev), ('시험', test)):
        if not rows:
            continue
        c = {h: sum(1 for r in rows if r['habit'] == h) for h in W.HABITS}
        lowA = sum(1 for r in rows if r['A_acc'][0] < 30)
        lowP = sum(1 for r in rows if r['P'] is not None and r['P_acc'][0] < 30)
        P(f'  - {nm} 습관별 리치: ' + ', '.join(f'{h} {v}' for h, v in c.items())
          + f'; 텐파이 표본 30 미만 ⚠ A {lowA} · P {lowP}; A 채택 중앙 {int(np.median([r["A_acc"][0] for r in rows]))}'
          + f' · P 채택 중앙 {int(np.median([r["P_acc"][0] for r in rows if r["P"] is not None]))}')
    P('\n## 습관 매개변수(우리 8판 정답 줄에서 셈)\n')
    for h, v in hp['habits'].items():
        P(f'- {h} ({", ".join(g[:3] for g in v["games"])}): 손에 둔 뽑은 패 {v["kept"]}, 끝에 붙임(정렬 자리 아님) {v["tail"]}, '
          f'끝이 곧 정렬 자리 {v["last_ok"]}, 가운데 어긋남 {v["off"]} → 끝 붙임 비율 q_tail {v["q_tail"]}, '
          f'어긋남 q_off {v["q_off"]}; 끝 패 정리 {v["tidied"]}/노출 {v["exposure"]}차례 → 차례당 정리 {v["tidy_hazard"]}; '
          f'배패 줄 어긋남 {v["init_out"]}/{v["init_n"]} = {v["init_mis"]}; 어긋남 거리 {v["offsets"]}')
    P(f'- 키(8판 각 판의 가장 맞는 키, 고르게): {", ".join(hp["keys"])}; 습관 빈도 ' +
      ', '.join(f'{h} {v:.3f}' for h, v in hp['freq'].items()))
    P('\n## S(종합 기준선) — 개발 판만, 판 묶음 5겹 교차검증\n')
    P('특징(수트마다): ' + ', '.join(W.S_FEATS))
    P('\n| C | 교차검증 로그 점수 | 교차검증 1위 적중 |\n|---|---|---|')
    for C, v in sm['cv'].items():
        P(f'| {C}{" ✓" if C == sm["C"] else ""} | {v["logscore"]:.4f} | {v["top1"] * 100:.1f}% |')
    P('\n계수(표준화, 절댓값 상위 10): ' + ', '.join(f'{k} {v:+.3f}' for k, v in sm['coef'][:10]))
    P('\n## γ(강 휴리스틱 세기) · ε(칸 번호 가정을 A 쪽으로 섞는 비율) — 개발 판 로그 점수(습관 섞음)로 고름\n')
    P(f'- 고른 값: {cfg}')
    P('- B 로그 점수 γ별: ' + ', '.join(f'{g}: {v:.4f}' for g, v in tun['B'].items()))
    P('- P 로그 점수 ε별: ' + ', '.join(f'{e}: {v:.4f}' for e, v in tun['P'].items()))
    P('- SP 로그 점수 ε별: ' + ', '.join(f'{e}: {v:.4f}' for e, v in tun['SP'].items()))
    P('- PB 로그 점수(γ|ε) 상위 5: '
      + ', '.join(f'{k}: {v:.4f}' for k, v in sorted(tun['PB'].items(), key=lambda x: -x[1])[:5]))
    if t_test is None:
        t_test = t_dev
        P('\n**시험 판 아직 없음 — 아래 판정은 개발 판 숫자(임시)**')
    else:
        write_table(P, t_test, f'시험 판 ({len(test_games)}판, 한 번 채점)')
    write_table(P, t_dev, f'개발 판 ({len(dev_games)}판; S 는 교차검증 바깥 예측, γ 는 여기서 고름)')
    P('\n## 판정(시험 판, 계획서 7절 기준 그대로)\n')
    v1, k1 = verdict(t_test, 'SP', 'S')
    v2, k2 = verdict(t_test, 'PB', 'B')
    P('- 주 판정 ' + v1)
    P('- 원래 판정 ' + v2)
    for nm, rr0 in (('시험', res_test0), ('개발', res_dev0)):
        if not rr0:
            continue
        cells = []
        for grp in GROUPS:
            sub = [x for x in rr0 if grp == 'mix' or x['habit'] == grp]
            cells.append(f'{grp} ' + ', '.join(
                f'{a}−{b} {np.mean([x["m"][a]["top1"] - x["m"][b]["top1"] for x in sub]) * 100:+.1f}%p'
                f'(로그 {np.mean([x["m"][a]["log"] - x["m"][b]["log"] for x in sub]):+.4f})'
                for a, b in (('SP', 'S'), ('PB', 'B'), ('P', 'A'))))
        P(f'- 참고({nm}, ε = 0 — 칸 번호 가정을 섞지 않은 그대로): ' + '; '.join(cells))
    # 진단
    test = test or dev
    trP = {h: (sum(1 for r in test if r['habit'] == h and r['truth_in_P']), sum(1 for r in test if r['habit'] == h))
           for h in W.HABITS}
    P('\n## 진단\n')
    P('- 정답 줄이 P 가정(표시 패 빼고 정렬, 흉내에 쓴 키에서)을 만족한 리치(시험): '
      + ', '.join(f'{h} {a}/{b}' for h, (a, b) in trP.items()))
    for h in W.HABITS:
        rr = [r for r in test if r['habit'] == h and r['P'] is not None]
        if rr:
            P(f'- {h}: P 의 흉내 키 사후 평균 {np.mean([r["P_oracle_post"] for r in rr]):.3f}, 지금 줄 표시(끝 붙임) 패 평균 '
              f'{np.mean([r["n_tail_cur"] for r in rr]):.2f}, 제약 받는 칸 평균 {np.mean([r["P_info"]["m"] for r in rr]):.2f}')
    P(f'- 리치 순(자기 버림 수) 중앙 {int(np.median([r["n_turn"] for r in test]))}; 대기 수트 수 분포 '
      + str(dict(sorted(Counter_(len(r["wsuits"]) for r in test).items()))))
    real_fp = os.path.join(OUT, 'real.json')
    if os.path.exists(real_fp):
        real = json.load(open(real_fp, encoding='utf-8'))
        P('\n## 진짜 판 방향 확인(채점 아님) — r18 · r14 hero 리치, 정답 줄의 실제 칸\n')
        Sr = s_predict(sm, real)
        P('| 판 | 리치 순 | 정답 대기 | 조건 | 수트 확률 m/p/s/z | 1위 |')
        P('|---|---|---|---|---|---|')
        for r, s in zip(real, Sr):
            ps, rk = cond_probs(r, cfg, s)
            for i, c in enumerate(COND):
                head = f'| {r["id"]} | {r["n_turn"]} | {",".join(tname(t) for t in r["waits"])} |' if i == 0 else '| | | |'
                P(f'{head} {c} | ' + ' / '.join(f'{x:.2f}' for x in ps[c]) + f' | {"mpsz"[int(np.argmax(ps[c]))]}'
                  + (f' (대기 패 순위 {rk[c]:.1f})' if c in rk else '') + ' |')
            P(f'| | | | P 정보 | {r["P_info"].get("key_top")} 제약 칸 {r["P_info"].get("m")} 표시 {r["P_info"].get("nfree")} | |')
    leak_fp = os.path.join(OUT, 'leak.json')
    if os.path.exists(leak_fp):
        lk = json.load(open(leak_fp, encoding='utf-8'))
        P('\n## 누설 검사\n')
        P('- ' + json.dumps(lk['summary'], ensure_ascii=False))
    txt = '\n'.join(lines)
    print(txt)
    with open(os.path.join(OUT, 'summary.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt + '\n')
    json.dump(dict(cfg=cfg, tune={k: {str(a): b for a, b in v.items()} for k, v in tun.items()}, C=sm['C'], cv=sm['cv'], coef=[(k, float(v)) for k, v in sm['coef']],
                   test=t_test, dev=t_dev, verdict_main=k1, verdict_orig=k2),
              open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def Counter_(it):
    from collections import Counter
    return Counter(it)


# ---------------------------------------------------------------- 누설 검사
def cmd_leak(n=40):
    sys.stdout.reconfigure(encoding='utf-8')
    hp = W.load_hp()
    recs, games, dev = W.load_split()
    devr = [r for r in recs if r['id'] in dev][:n]
    out = []
    # 모든 기록: 공개 강의 끝은 그 자리의 리치 선언패(리치 시점에서 잘림)
    cut_ok = all(r['pub']['river'][-1][0] == r['seat'] and r['pub']['river'][-1][3] for r in recs)
    for r in devr:
        habit, ki, sseed = W.assign(r, hp)
        phys, types = W.simulate(r['hid'], habit, ki, hp['habits'], np.random.default_rng(sseed))
        disc = {t['disc'] for t in phys['turns']}
        rev = {v: types[v] for v in disc}
        obs1 = W.make_obs(phys, rev)
        hidden = [v for v in types if v not in disc]
        # 숨은 미지수 종류를 가짜(서로 다른 100+)로 바꾼 정답: 관찰은 같아야 함
        types_f = {v: (100 + v if v in hidden else t) for v, t in types.items()}
        rev_f = {v: types_f[v] for v in disc}
        obs2 = W.make_obs(phys, rev_f)
        same_obs = obs1 == obs2
        no_hidden_in_obs = not (set(obs1['reveal']) & set(obs1['cur']))
        # 숨은 부분(hid)을 가짜로 바꾸고 습관 · 키도 다르게 해서 추정: 공개 · 관찰만 쓰므로 표본이 같아야 함
        r2 = json.loads(json.dumps(r))
        r2['hid'] = dict(haipai=[11] * 13, turns=[], hand=[47] * 13, waits=[0])
        base = 12345
        a = W.infer_all(obs1, r['pub'], r['hid']['waits'], base)
        b = W.infer_all(obs2, r2['pub'], r['hid']['waits'], base)
        same_A = np.array_equal(a['cA'], b['cA'])
        same_P = (a['cP'] is None and b['cP'] is None) or np.array_equal(a['cP'], b['cP'])
        same_F = np.array_equal(a['F'], b['F'])
        out.append(dict(id=r['id'], round=r['round'], seat=r['seat'], habit=habit, obs_same=same_obs,
                        no_hidden_in_obs=no_hidden_in_obs, A_same=bool(same_A), P_same=bool(same_P), F_same=bool(same_F)))
    summ = dict(n=len(out), riichi_cut_ok_all_records=bool(cut_ok),
                **{k: sum(1 for x in out if x[k]) for k in ('obs_same', 'no_hidden_in_obs', 'A_same', 'P_same', 'F_same')})
    print(summ)
    json.dump(dict(summary=summ, rows=out), open(os.path.join(OUT, 'leak.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 손으로 확인할 예
def cmd_example(habit='H2', nth=0):
    sys.stdout.reconfigure(encoding='utf-8')
    hp = W.load_hp()
    recs, games, devset = W.load_split()
    dev = load_rows('dev')
    rows = {(r['id'], r['round'], r['seat']): r for r in dev}
    cand = [r for r in recs if r['id'] in devset and rows.get((r['id'], r['round'], r['seat']), {}).get('habit') == habit
            and rows[(r['id'], r['round'], r['seat'])]['P'] is not None and len(r['pub']['own']) >= 7]
    rec = cand[nth]
    row = rows[(rec['id'], rec['round'], rec['seat'])]
    hb, ki, sseed = W.assign(rec, hp)
    phys, types = W.simulate(rec['hid'], hb, ki, hp['habits'], np.random.default_rng(sseed))
    disc = {t['disc'] for t in phys['turns']}
    obs = W.make_obs(phys, {v: types[v] for v in disc})
    print(f'# 예: {rec["id"]} 국 {rec["round"]} 자리 {rec["seat"]} — 습관 {hb}, 키 {PI.key_name(ki)}')
    print('배패:', ' '.join(tname(W.ttype(c)) for c in rec['hid']['haipai']))
    print('차례(뽑음 → 버림, 쯔모기리):', '; '.join(f'{tname(W.ttype(d))}→{tname(W.ttype(x))}{"(쯔)" if tg else ""}'
                                              for d, x, tg in rec['hid']['turns']))
    print('관찰 줄(* = 버려서 공개, ^ = 끝 붙임 표시로 제약에서 뺌):')
    for rr, ex in obs['rows']:
        print('  ', ' '.join(tname(types[v]) + ('*' if v in obs['reveal'] else '') + ('^' if v in ex else '') for v in rr))
    st = W.p_structs(obs)
    R = PI.RANK[ki]
    lo = np.full(st['m'], -np.inf)
    hi = np.full(st['m'], np.inf)
    for p, t in st['lo']:
        lo[p] = max(lo[p], R[t])
    for p, t in st['hi']:
        hi[p] = min(hi[p], R[t])
    fl = set(obs['flags'])
    cur = [v for v in obs['cur'] if v not in fl]

    def rname(x):
        if not np.isfinite(x):
            return '·'
        # 순위 → 그 키에서의 패 이름(자패는 z)
        ts = [t for t in range(34) if R[t] == x]
        return tname(ts[0]) if len(ts) == 1 else 'z'
    print('지금 줄(제약 받는 칸) 정답 · 흉내 키에서의 경계 [아래, 위]:')
    print('  ', ', '.join(f'{tname(types[v])}[{rname(lo[i])},{rname(hi[i])}]' for i, v in enumerate(cur)),
          '| 자유 칸:', ' '.join(tname(types[v]) for v in obs['flags']))
    print('정답 대기:', [tname(t) for t in rec['hid']['waits']], 'P 키 사후 상위:', row['P_info'].get('key_top'))
    sm = s_fit(dev)
    i = dev.index(row)
    s_ps = sm['oof'].reshape(-1, 4)[i]
    cfg = json.load(open(os.path.join(OUT, 'report.json'), encoding='utf-8'))['cfg'] if os.path.exists(
        os.path.join(OUT, 'report.json')) else dict(gB=0.5, gPB=0.5, eP=0.0, ePB=0.0, eSP=0.0)
    ps, rk = cond_probs(row, cfg, s_ps)
    for c in COND:
        print(f'  {c:3s} m/p/s/z = ' + ' / '.join(f'{x:.2f}' for x in ps[c]) + (f'  대기 패 순위 {rk[c]:.1f}' if c in rk else ''))
    print('강(자기):', ' '.join(tname(t) + ('(쯔)' if tg else '') for t, tg in rec['pub']['own']))


# ---------------------------------------------------------------- 진짜 판(r18 · r14)
def real_obs(paifu):
    o, st, _rs, _tt, _steps = real_obs_at(paifu, None)
    return o, st


def real_obs_at(paifu, target=None):
    """real_obs 를 목표 걸음(target: obs['steps'] 번호, None = 리치 걸음)까지로 일반화.
    울기 걸음의 reveal(손에서 나간 두 장) · moved 처리는 build_observation 그대로 따른다.
    반환 (관찰, 목표 걸음, 줄마다 걸음 번호(진단용), 정답 종류 tt(채점 · 진단 전용), 걸음 목록)."""
    obs, tt = PI.build_observation(paifu)
    steps = obs['steps']
    ri = target if target is not None else next(i for i, st in enumerate(steps) if st.get('riichi'))
    flags = set()
    rows = [(list(steps[0]['row']), frozenset())]
    row_steps = [0]
    reveal = {}
    for si in range(1, ri + 1):
        st = steps[si]
        flags -= set(st.get('moved') or [])
        for v, t in st['reveal'].items():
            reveal[v] = tid(t)
            flags.discard(v)
        row = st['row']
        d = st.get('drawn')
        if d is not None and row and row[-1] == d:
            flags.add(d)
        if row != rows[-1][0] or frozenset(flags) != rows[-1][1]:
            rows.append((list(row), frozenset(flags)))
            row_steps.append(si)
    o = dict(rows=[(r, sorted(f)) for r, f in rows], reveal=reveal, cur=list(rows[-1][0]), flags=sorted(flags))
    return o, steps[ri], row_steps, tt, steps


def real_pub(paifu, ev):
    hero = paifu['hero']
    river, meld, own = [], [], []
    for e in paifu['events'][:ev + 1]:
        if e['type'] == 'discard':
            river.append([e['seat'], tid(e['tile']), bool(e.get('tsumogiri')), bool(e.get('riichi'))])
            if e['seat'] == hero:
                own.append([tid(e['tile']), bool(e.get('tsumogiri'))])
        elif e['type'] == 'call':
            meld += [tid(x) for x in e['tiles'][1:]]
    return dict(river=river, meld_vis=meld, dora=[tid(x) for x in paifu.get('dora_indicators') or []], own=own,
                other_riichi=[])


def cmd_real():
    sys.stdout.reconfigure(encoding='utf-8')
    out = []
    for g in ('r18_141259', 'r14_133610'):
        p = PI.load(g)
        o, st = real_obs(p)
        e = p['events'][st['ev']]
        cnt = np.bincount([tid(x) for x in e['hand']], minlength=34)
        tw = list(fast_waits(tuple(int(x) for x in cnt)))
        pub = real_pub(p, st['ev'])
        res = W.infer_all(o, pub, tw, zlib.crc32(g.encode()))
        out.append(dict(id=g, n_turn=len(pub['own']), waits=tw, wsuits=sorted(set(t // 9 for t in tw)),
                        A=res['A'], P=res['P'], A_acc=res['A_acc'], P_acc=res['P_acc'],
                        P_info={k: v for k, v in res['P_info'].items() if k != 'post'}, feats=res['F'].tolist(),
                        rows=[[tname(tid(x)) for x in e['hand']]], flags=o['flags'], k=st.get('k'), j=st.get('j')))
        print(g, 'waits', [tname(t) for t in tw], 'A', res['A'] and res['A']['0.0']['ps'], 'P',
              res['P'] and res['P']['0.0']['ps'], res['P_info'].get('key_top'), res['A_acc'], res['P_acc'])
    json.dump(out, open(os.path.join(OUT, 'real.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 2반장 같은 판 두 자리(r16 리치 · L16 울기 유국 텐파이)
def _hand_waits(paifu, ev):
    cnt = np.bincount([tid(x) for x in paifu['events'][ev]['hand']], minlength=34)
    return list(fast_waits(tuple(int(x) for x in cnt)))


def first_stay_tenpai(paifu, steps):
    """버림 걸음 중 '버린 뒤 손이 텐파이이고, 그 뒤 모든 버림 뒤에도 텐파이' 인 첫 걸음 번호(정답 hand 로 정함)."""
    idx = [i for i, st in enumerate(steps) if st['kind'] == 'turn']
    ten = {i: bool(_hand_waits(paifu, steps[i]['ev'])) for i in idx}
    for i in idx:
        if all(ten[j] for j in idx if j >= i):
            return i
    return None


def p_diag(o, tt, row_steps, steps, unseen):
    """P 가정 진단(채점 쪽 — 정답 종류 tt 를 씀). 키마다: 관찰자 쪽에서 왜 죽었나(공개-공개 어긋남 / DP 0),
    정답 줄에서 가정(표시 패 빼고 키 순위 비내림)을 깬 짝들. 깬 짝으로 48 키를 덮는 작은 묶음(탐욕)."""
    st = W.p_structs(o)
    rv = o['reveal']
    jun = []
    nd = 0
    for s in steps:
        if s['kind'] == 'turn':
            nd += 1
        jun.append(nd)

    def nm(v):
        return tname(tt[v]) + ('*' if v in rv else '')

    def lab_of(s_i):
        return '첫 줄' if s_i == 0 else (f'{jun[s_i]}순 뒤 줄' + (' (울기 뒤)' if steps[s_i]['kind'] == 'call' else ''))
    kill = {}
    viol = {}
    for k in range(len(PI.KEYS)):
        R = PI.RANK[k]
        if any(R[a] > R[b] for a, b in st['rr']):
            kill[k] = 'rr'
        else:
            lo = np.full(st['m'], -np.inf)
            hi = np.full(st['m'], np.inf)
            for p_, t in st['lo']:
                lo[p_] = max(lo[p_], R[t])
            for p_, t in st['hi']:
                hi[p_] = min(hi[p_], R[t])
            F, _, _ = PI.dp_table(lo, hi, st['eq'], unseen, k)
            kill[k] = 'dp0' if F[0][0] == 0 else None
        vs = {}
        for ri, (r, ex) in enumerate(o['rows']):
            exs = set(ex)
            rr_ = [v for v in r if v not in exs]
            for i in range(len(rr_)):
                for j in range(i + 1, len(rr_)):
                    a, b = rr_[i], rr_[j]
                    if R[tt[a]] > R[tt[b]]:
                        pk = (min(a, b), max(a, b))          # 짝은 미지수 둘(순서 없음): 줄 사이에서 뒤집힌 짝이 양쪽 키를 다 깸
                        if pk not in vs:
                            vs[pk] = (ri, f'{lab_of(row_steps[ri])}: {nm(a)} 앞 {nm(b)}')
        viol[k] = vs
    # 탐욕 덮기: 가장 많은 키에서 가정을 깬 짝부터(같으면 이른 줄)
    left = {k for k in viol if viol[k]}
    cover = []
    while left:
        cnt = {}
        for k in left:
            for pr, info in viol[k].items():
                c_ = cnt.setdefault(pr, [set(), []])
                c_[0].add(k)
                if info[1] not in c_[1]:
                    c_[1].append(info[1])
        pr, (ks, where) = max(cnt.items(), key=lambda x: (len(x[1][0]), -min(viol[k][x[0]][0] for k in x[1][0])))
        cover.append(dict(pair=f'{nm(pr[0])} / {nm(pr[1])}', keys=len(ks), where=where))
        left -= ks
    alone = []                                       # 혼자서 48 키를 다 깨는 짝
    allp = set().union(*[set(v) for v in viol.values()]) if viol else set()
    for pr in sorted(allp):
        if all(pr in viol[k] for k in viol):
            alone.append(dict(pair=f'{nm(pr[0])} / {nm(pr[1])}',
                              where=sorted(set(viol[k][pr][1] for k in viol))))
    # 관찰자 쪽: 미지수 하나를 '끝 붙임처럼' 제약에서 빼면 키가 살아나나 / 앞 줄을 몇 개 버리면 살아나나
    base_alive = alive_keys(o, unseen)
    revive = []
    allv = sorted(set(v for r, _ in o['rows'] for v in r))
    for v in allv:
        o2 = dict(o, rows=[(r, sorted(set(ex) | {v})) for r, ex in o['rows']],
                  flags=sorted(set(o['flags']) | ({v} if v in o['cur'] else set())))
        n2 = alive_keys(o2, unseen)
        if n2 > base_alive:
            rows_in = [lab_of(row_steps[i]) for i, (r, _) in enumerate(o['rows']) if v in r]
            revive.append(dict(tile=nm(v), keys_alive=n2, rows=f'{rows_in[0]} ~ {rows_in[-1]}'))
    prefix = None
    for i in range(1, len(o['rows'])):
        o2 = dict(o, rows=o['rows'][i:])
        n2 = alive_keys(o2, unseen)
        if n2 > 0:
            prefix = dict(drop_rows=i, start=lab_of(row_steps[i]), keys_alive=n2)
            break
    return dict(truth_ok_keys=[PI.key_name(k) for k in viol if not viol[k]],
                kill=dict(Counter_(v or 'alive' for v in kill.values())), cover=cover, alone=alone,
                revive_one_var=revive, revive_drop_prefix=prefix)


def alive_keys(o, unseen):
    """sample_P 와 같은 판정으로 우도 > 0 인 키 수."""
    st = W.p_structs(o)
    n = 0
    for k in range(len(PI.KEYS)):
        R = PI.RANK[k]
        if any(R[a] > R[b] for a, b in st['rr']):
            continue
        lo = np.full(st['m'], -np.inf)
        hi = np.full(st['m'], np.inf)
        for p_, t in st['lo']:
            lo[p_] = max(lo[p_], R[t])
        for p_, t in st['hi']:
            hi[p_] = min(hi[p_], R[t])
        F, _, _ = PI.dp_table(lo, hi, st['eq'], unseen, k)
        n += F[0][0] > 0
    return n


def _ratios(r, cfg):
    """cond_probs 와 같은 식으로 대기 패 비율(A · B · P · PB)."""
    A = r['A']
    gB, gPB = str(cfg['gB']), str(cfg['gPB'])
    a0 = np.array(A['0.0']['ratio'])
    b = np.array(A[gB]['ratio'])
    if r['P'] is None:
        return dict(A=a0, B=b, P=b, PB=b)
    e = cfg['eP']
    p = (1 - e) * np.array(r['P']['0.0']['ratio']) + e * a0
    e = cfg['ePB']
    pb = (1 - e) * np.array(r['P'][gPB]['ratio']) + e * np.array(A[gPB]['ratio'])
    return dict(A=a0, B=b, P=p, PB=pb)


def real_one(g, target, sm, cfg):
    """target: 'riichi'(리치 걸음) 또는 'stay_tenpai'(텐파이가 되어 끝까지 남는 첫 버림 직후)."""
    p = PI.load(g)
    obs0, _ = PI.build_observation(p)
    steps0 = obs0['steps']
    if target == 'riichi':
        ti = next(i for i, st in enumerate(steps0) if st.get('riichi'))
    else:
        ti = first_stay_tenpai(p, steps0)
    o, st, row_steps, tt, steps = real_obs_at(p, ti)
    e = p['events'][st['ev']]
    hand = [tid(x) for x in e['hand']]
    tw = _hand_waits(p, st['ev'])
    pub = real_pub(p, st['ev'])
    n_hand = len(o['cur'])
    assert n_hand == len(hand) and sorted(tt[v] for v in o['cur']) == sorted(hand)
    res = W.infer_all(o, pub, tw, zlib.crc32(g.encode()), n_hand)
    pi = W.pub_info(pub)
    row = dict(id=g, seat=p['hero'], target=target, step=ti, ev=st['ev'], n_turn=len(pub['own']),
               riichi=bool(st.get('riichi')), n_hand=n_hand, s_out_of_dist=not bool(st.get('riichi')),
               s_note=('' if st.get('riichi') else
                       '분포 밖: S 는 리치 선언패 기반으로 배움 — 리치 없음, 목표 시점 버림을 선언패 자리에 넣어 계산'),
               hand=[tname(t) for t in hand],
               melds=[[tname(tid(x)) for x in ev['tiles']] for ev in p['events'][:st['ev'] + 1]
                      if ev['type'] == 'call' and ev['seat'] == p['hero']],
               meld_vis=[tname(t) for t in pub['meld_vis']],
               waits=tw, wait_names=[tname(t) for t in tw], wsuits=sorted(set(t // 9 for t in tw)),
               A=res['A'], P=res['P'], A_acc=res['A_acc'], P_acc=res['P_acc'],
               P_info={k: v for k, v in res['P_info'].items() if k != 'post'}, feats=res['F'].tolist(),
               flags_tiles=[tname(tt[v]) for v in o['flags']], over=pi['over'],
               own=[tname(t) + ('(쯔)' if tg else '') for t, tg in pub['own']])
    s_ps = s_predict(sm, [row])[0]
    ps, rk = cond_probs(row, cfg, s_ps)
    rat = _ratios(row, cfg)
    row['probs'] = {c: [round(float(x), 4) for x in ps[c]] for c in COND}
    row['top1'] = {c: 'mpsz'[int(np.argmax(ps[c]))] for c in COND}
    row['top1_hit'] = {c: top1(ps[c], y_of(row)) for c in COND}
    row['wait_rank'] = rk
    row['top_tiles'] = {c: [(tname(int(t)), round(float(rat[c][t]), 3)) for t in np.argsort(-rat[c], kind='stable')[:6]]
                        for c in rat}
    row['P_broken'] = res['P'] is None
    row['diag'] = p_diag(o, tt, row_steps, steps, pi['unseen'])
    row['rows_obs'] = [' '.join(tname(tt[v]) + ('*' if v in o['reveal'] else '') + ('^' if v in ex else '') for v in r)
                       for r, ex in o['rows']]
    return row


def check_r18(sm, cfg):
    """sample_A 일반화 뒤에도 r18 결과가 real.json 과 같은지(real.json 은 덮어쓰지 않음)."""
    old = {r['id']: r for r in json.load(open(os.path.join(OUT, 'real.json'), encoding='utf-8'))}['r18_141259']
    g = 'r18_141259'
    p = PI.load(g)
    o, st = real_obs(p)
    tw = _hand_waits(p, st['ev'])
    pub = real_pub(p, st['ev'])
    res = W.infer_all(o, pub, tw, zlib.crc32(g.encode()), len(o['cur']))
    new = json.loads(json.dumps(dict(A=res['A'], P=res['P'], feats=res['F'].tolist(), A_acc=res['A_acc'],
                                     P_acc=res['P_acc'])))
    same = {k: new[k] == old[k] for k in new}
    po, _ = cond_probs(old, cfg, s_predict(sm, [old])[0])
    nr = dict(old, **new)
    pn, _ = cond_probs(nr, cfg, s_predict(sm, [nr])[0])
    probs_same = all(np.array_equal(po[c], pn[c]) for c in COND)
    return dict(n_hand=len(o['cur']), same=same, probs_same=bool(probs_same),
                probs={c: [round(float(x), 4) for x in pn[c]] for c in COND})


def cmd_real_hanchan2():
    sys.stdout.reconfigure(encoding='utf-8')
    cfg = json.load(open(os.path.join(OUT, 'report.json'), encoding='utf-8'))['cfg']
    sm = s_fit(load_rows('dev'))
    print('cfg', cfg, 'C', sm['C'])
    chk = check_r18(sm, cfg)
    print('r18 그대로?', chk)
    out = dict(cfg=cfg, C=sm['C'], check_r18=chk, games=[])
    for g, tgt in (('r16_135321', 'riichi'), ('L16_135321', 'stay_tenpai')):
        r = real_one(g, tgt, sm, cfg)
        out['games'].append(r)
        print(f'\n== {g} 자리 {r["seat"]} 목표 {tgt} 걸음 {r["step"]} ev {r["ev"]} 순 {r["n_turn"]} 손 {r["n_hand"]}장 '
              f'{" ".join(r["hand"])} 울기 {r["melds"]} (공개 meld_vis {r["meld_vis"]}) 대기 {r["wait_names"]}')
        if r['s_note']:
            print('  S:', r['s_note'])
        for c in COND:
            print(f'  {c:3s} m/p/s/z ' + ' / '.join(f'{x:.2f}' for x in r['probs'][c]) + f'  1위 {r["top1"][c]}'
                  + (f'  대기 패 순위 {r["wait_rank"][c]:.1f}  상위 {r["top_tiles"][c][:5]}' if c in r['wait_rank'] else ''))
        print('  P 깨짐', r['P_broken'], 'P_info', r['P_info'], '끝 붙임 제외 칸', r['flags_tiles'])
        print('  A 채택/뽑음', r['A_acc'], 'P', r['P_acc'], '4장 넘게 보인 종류 수', r['over'])
        print('  강:', ' '.join(r['own']))
        print('  진단', json.dumps(r['diag'], ensure_ascii=False))
        print('  관찰 줄(* 공개, ^ 끝 붙임 제외):')
        for x in r['rows_obs']:
            print('    ', x)
    json.dump(out, open(os.path.join(OUT, 'real_hanchan2.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
