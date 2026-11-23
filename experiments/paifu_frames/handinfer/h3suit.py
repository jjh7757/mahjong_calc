"""안 본 판으로 수트 구성 재기 — 3반장 11판 (계획서 docs/hand_infer_plan_1120.md 10절).

외부 API 없음, 순수 계산. posinfer · softinfer 는 고치지 않고 import 해서 쓴다. 다시 돌리기(저장소 뿌리에서):
    python -I -X utf8 experiments/paifu_frames/handinfer/h3suit.py all      # check → leak → run(h3 · 2반장) → score
    python -I -X utf8 experiments/paifu_frames/handinfer/h3suit.py score    # 차례별 jsonl 에서 표 · 판정만 다시
결과: experiments/paifu_frames/results/handinfer/h3/

판 목록 · 디렉터리 바꿔 끼우기: posinfer.load(g) 는 모듈 상수 PAIFU_DIR 를 읽고, softinfer.turn_setup · main_turns ·
fake_paifu 쪽도 PI.load · PI.GAMES 를 쓴다. 상수를 덮어쓰면 ProcessPoolExecutor(Windows spawn) 작업 프로세스마다 다시
덮어써야 해서, 여기서는 상수를 건드리지 않고 패보를 직접 읽어(load(dir, g)) 패보 객체를 받는 함수만 부른다:
  PI.build_observation · PI.self_check · PI.obs_upto · PI.build_public · PI.heuristic_score · PI.cstar_infer ·
  PI.sortedness · SI.q_obs · SI.sample_AB · SI.sample_q · SI.sm_metrics · SI.fake_paifu.
조건 · 세기(10절 고정, 9절 실행 results/handinfer/soft/summary_noflag.md 의 "8판 전부" 줄):
  A = 남은 패 정확 표본, B = γ 1.0 기울인 초기하, C*mix = posinfer.cstar_infer(48 키 섞음, 가정 깨짐 → A),
  Q = (ε 0.03, δ0 0.5, λ 1.0), QB = Q(ε 0.1, δ0 0.03, λ 1.0) 표본에 exp(−1.0 · Σ c_t s_t) 중요도 가중.
  관찰은 9절 그 실행과 같게 **끝 붙임 표시 없음**(softinfer.q_obs(flags=False)) — 지금 softinfer.FLAGS 기본값(True)은
  그 실행 뒤에 바뀐 것이고, 세기를 고른 실행은 *_noflag 이다.
  표본 수 · 평활 · 씨 · 텐파이(리치 선언 차례만 텐파이 표본)는 softinfer.run_turn 과 같다(같은 씨 식 — 2반장 판을 다시 돌리면
  turns_noflag.jsonl 과 숫자가 같아야 한다, check 에서 확인).
"""
import json
import os
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import posinfer as PI  # noqa: E402
import softinfer as SI  # noqa: E402
from posinfer import tid, tname  # noqa: E402

ROOT = PI.ROOT
H3_DIR = os.path.join(ROOT, 'assets', 'paifu_h3')
P2_DIR = PI.PAIFU_DIR
H3_GAMES = sorted(f[:-5] for f in os.listdir(H3_DIR) if f.endswith('.json'))
P2_GAMES = list(PI.GAMES)
SETS = {'h3': (H3_DIR, H3_GAMES), 'p2': (P2_DIR, P2_GAMES)}
OUT = os.path.join(PI.OUT_DIR, 'h3')

GAMMA_B = 1.0
Q_PRM = (0.03, 0.5, 1.0)
QB_PRM = (0.1, 0.03, 1.0)
QB_GAMMA = 1.0
FLAGS = False
COND = ['A', 'B', 'Cmix', 'Q', 'QB']
SUITN = 'mpsz'


def load(d, g):
    with open(os.path.join(d, g + '.json'), encoding='utf-8') as f:
        return json.load(f)


def turn_steps(obs):
    return [i for i, s in enumerate(obs['steps']) if s['kind'] == 'turn']


def suits_of(cnt):
    return [int(np.asarray(cnt)[k * 9:(k + 1) * 9].sum()) for k in range(4)]


# ================================================================ 한 차례
def run_turn(args):
    sname, g, step_i = args
    t0 = time.time()
    d = SETS[sname][0]
    paifu = load(d, g)
    obs, _tt = PI.build_observation(paifu)
    st = obs['steps'][step_i]
    o = PI.obs_upto(obs, step_i)
    qo = SI.q_obs(obs, step_i, flags=FLAGS)
    pub = PI.build_public(paifu, st['ev'])
    tenpai = bool(st.get('riichi'))                 # 리치 선언은 공개 — softinfer 와 같음
    unseen = pub['unseen']
    m = len(qo['cur'])
    hs = PI.heuristic_score(pub['hero_disc'])
    n = SI.N_ACC if tenpai else SI.N_S
    base = zlib.crc32(f'{g}|{step_i}|main'.encode())   # softinfer.run_turn 과 같은 씨
    # ---- 여기부터 정답(채점용) — 추정에는 안 넘김
    e = paifu['events'][st['ev']]
    truth = np.bincount([tid(x) for x in e['hand']], minlength=34)
    rec = dict(set=sname, game=g, step=step_i, ev=st['ev'], n=m, riichi=tenpai, guess=bool(e.get('guess')),
               tsumogiri=bool(st.get('tsumogiri')), k=st.get('k'), j=st.get('j'),
               after_call=any(s['kind'] == 'call' for s in obs['steps'][:step_i]),
               truth_suits=suits_of(truth), truth_impossible=int((truth > unseen).sum()),
               exp={}, logs={}, fallback={}, acc={})

    def put(name, cn, w=None, fb=None):
        mm = SI.sm_metrics(cn, w, unseen, truth)
        rec['exp'][name] = mm['suit']
        rec['logs'][name] = mm['logs']
        rec['fallback'][name] = fb
        return mm
    # A · B
    cnA, infA = SI.sample_AB(unseen, m, 0.0, hs, n, tenpai, base + 1)
    cnB, infB = SI.sample_AB(unseen, m, GAMMA_B, hs, n, tenpai, base + int(GAMMA_B * 1000) + 1)
    assert cnA is not None and cnB is not None, '텐파이 표본 0 (A/B)'
    put('A', cnA)
    put('B', cnB)
    rec['acc']['A'], rec['acc']['B'] = [infA['accepted'], infA['drawn']], [infB['accepted'], infB['drawn']]
    # C*mix
    cn, inf = PI.cstar_infer(o, pub, None, tenpai, base + 7, n=n)
    if cn is None:
        put('Cmix', cnA, fb='A')
    else:
        put('Cmix', cn)
    rec['cmix_broken'] = bool(inf['broken'] or inf.get('no_tenpai', False))
    rec['acc']['Cmix'] = [inf.get('accepted_total', inf.get('accepted', 0)), inf.get('drawn', 0)]
    # Q
    nm = SI.cfg_name(Q_PRM)
    cn, inf = SI.sample_q(qo, unseen, Q_PRM, n, tenpai, base + zlib.crc32(nm.encode()) % 100000)
    rec['acc']['Q'] = [inf.get('accepted', 0), inf.get('drawn', 0)]
    rec['q_broken'] = cn is None
    rec['q_info'] = dict(n_bnd=inf['n_bnd'], n_rr=inf['n_rr'], n_flp=inf['n_flp'], mean_out=inf.get('mean_out'),
                         no_tenpai=bool(inf.get('no_tenpai', False)), keys_alive=None)
    if cn is None:
        put('Q', cnA, fb='A')
    else:
        put('Q', cn)
    # QB = Q(QB 세기) 표본 × B 기울기 중요도 가중
    nm = SI.cfg_name(QB_PRM)
    cn, inf = SI.sample_q(qo, unseen, QB_PRM, n, tenpai, base + zlib.crc32(nm.encode()) % 100000)
    rec['acc']['QB'] = [inf.get('accepted', 0), inf.get('drawn', 0)]
    rec['qb_broken'] = cn is None
    if cn is None:
        put('QB', cnA, fb='A')          # softinfer.report 의 _get 과 같음: 설정이 None(표본 0)이면 A 로 채점
        rec['qb_ess'] = None
    else:
        lw = -QB_GAMMA * (cn @ hs)
        w = np.exp(lw - lw.max())
        mm = put('QB', cn, w)
        rec['qb_ess'] = mm['ess']
    rec['sec'] = round(time.time() - t0, 1)
    return rec


def all_tasks(sname):
    d, games = SETS[sname]
    tasks = []
    for g in games:
        obs, _ = PI.build_observation(load(d, g))
        ts = turn_steps(obs)
        rs = [i for i in ts if obs['steps'][i].get('riichi')]
        tasks += [(sname, g, i) for i in rs] + [(sname, g, i) for i in ts if i not in rs]
    return tasks


def cmd_run(workers):
    os.makedirs(OUT, exist_ok=True)
    tasks = all_tasks('h3') + all_tasks('p2')
    rs = [t for t in tasks if _is_riichi(t)]
    tasks = rs + [t for t in tasks if t not in rs]          # 무거운 텐파이 차례 먼저
    t0 = time.time()
    out = {'h3': [], 'p2': []}
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(run_turn, tasks, chunksize=1)):
            out[r['set']].append(r)
            if (i + 1) % 20 == 0 or i + 1 == len(tasks):
                print(f'  {i + 1}/{len(tasks)} (누적 {time.time() - t0:.0f}s)', flush=True)
    for s, rows in out.items():
        rows.sort(key=lambda r: (r['game'], r['step']))
        with open(os.path.join(OUT, f'turns_{s}.jsonl'), 'w', encoding='utf-8', newline='\n') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'run 끝 {time.time() - t0:.0f}s, 차례 h3 {len(out["h3"])} · 2반장 {len(out["p2"])}', flush=True)
    return time.time() - t0


_RCACHE = {}


def _is_riichi(t):
    s, g, i = t
    if (s, g) not in _RCACHE:
        obs, _ = PI.build_observation(load(SETS[s][0], g))
        _RCACHE[(s, g)] = obs
    return bool(_RCACHE[(s, g)]['steps'][i].get('riichi'))


# ================================================================ 검사 2 · 3: 관찰 만들기 · 정답
def cmd_check():
    os.makedirs(OUT, exist_ok=True)
    res = dict(games={}, noflag_repro=None)
    for g in H3_GAMES:
        p = load(H3_DIR, g)
        rec = dict()
        try:
            obs, tt = PI.build_observation(p)
            nst = PI.self_check(p, obs, tt)            # 미지수 줄 + 정답 종류 → 원래 줄과 같음 · 공개 패 == 정답
            rec['build'] = 'ok'
            rec['self_check_steps'] = nst
        except Exception as ex:  # noqa
            rec['build'] = f'실패: {ex!r}'
            res['games'][g] = rec
            continue
        obsR, ttR = PI.build_observation(p, right=True)
        turns = turn_steps(obs)
        hero = p['hero']
        bad_k, bad_j, ts_mis, moved, lr_diff, ncall_t = [], [], [], [], [], 0
        hero_ev = [i for i, e in enumerate(p['events']) if e.get('seat') == hero]
        nohand = [i for i in hero_ev if p['events'][i].get('hand') is None]
        for i in turns:
            st = obs['steps'][i]
            if not st['tsumogiri'] and st['k'] is None:
                bad_k.append(st['ev'])
            if st['drawn'] is not None and not st['tsumogiri'] and st['j'] is None:
                bad_j.append(st['ev'])
            if st['drawn'] is None:
                ncall_t += 1                                  # 울기 직후 버림(뽑은 패 없음 → j 없음이 맞음)
            tg = st.get('tsumogiri_given')
            if tg is not None and bool(tg) != bool(st['tsumogiri']):
                ts_mis.append(st['ev'])
            if st.get('moved'):
                moved.append((st['ev'], len(st['moved'])))
            sr = obsR['steps'][i]
            if (st['k'], st['j']) != (sr['k'], sr['j']):
                lr_diff.append(dict(ev=st['ev'], left=(st['k'], st['j']), right=(sr['k'], sr['j'])))
        calls = [dict(ev=s['ev'], meld_pos=s['meld_pos']) for s in obs['steps'] if s['kind'] == 'call']
        # 정답 수트 장수 == hand 칸(검사 3): 관찰 미지수 줄 × 정답 종류로 다시 센 것과 hand 칸에서 센 것
        tr_mis = 0
        for i in turns:
            st = obs['steps'][i]
            a = suits_of(np.bincount([tt[v] for v in st['row']], minlength=34))
            b = suits_of(np.bincount([tid(x) for x in p['events'][st['ev']]['hand']], minlength=34))
            tr_mis += a != b
        # 끝 손패 == result.hand(화료자가 hero 인 판만, 서술)
        fin = None
        r = p.get('result') or {}
        last = obs['steps'][turns[-1]]
        if r.get('winner') == hero and r.get('hand'):
            fin = sorted(tname(tt[v]) for v in last['row']) == sorted(tname(tid(x)) for x in r['hand'])
        rec.update(turns=len(turns), guess_turns=sum(1 for i in turns if p['events'][obs['steps'][i]['ev']].get('guess')),
                   riichi_turns=sum(1 for i in turns if obs['steps'][i].get('riichi')),
                   tsumogiri_turns=sum(1 for i in turns if obs['steps'][i]['tsumogiri']),
                   k_missing=bad_k, j_missing=bad_j, tsumogiri_flag_mismatch=ts_mis, moved=moved,
                   left_right_kj_diff=lr_diff, after_call_discards=ncall_t, calls=calls, hero_events_without_hand=nohand,
                   truth_suit_mismatch=tr_mis, final_row_eq_result_hand=fin, sortedness=PI.sortedness(p)[:2],
                   sortedness_noguess=sortedness_noguess(p)[:2], result=r.get('type'))
        res['games'][g] = rec
        print(g, json.dumps({k: v for k, v in rec.items() if k not in ('moved', 'left_right_kj_diff', 'calls')},
                            ensure_ascii=False), flush=True)
    # 9절 실행(noflag)과 같은 계산인지: 손 안 댄 2반장 판(r12 · r17, 파일이 11-20 그대로) 몇 차례를 다시 돌려 숫자 비교
    nf = os.path.join(PI.OUT_DIR, 'soft', 'turns_noflag.jsonl')
    if os.path.exists(nf):
        old = {}
        for line in open(nf, encoding='utf-8'):
            dd = json.loads(line)
            if dd['tag'] == 'main' and dd['game'] in ('r12_131655', 'r17_140450') and dd['step'] in (3, 7, 11):
                old[(dd['game'], dd['step'])] = dd
        cmp_ = []
        for (g, s), dd in sorted(old.items()):
            r = run_turn(('p2', g, s))
            pair = dict(A='A', B=f'B|{GAMMA_B}', Cmix='Cmix', Q='Q|' + SI.cfg_name(Q_PRM),
                        QB=f'QB|{SI.cfg_name(QB_PRM)}|{QB_GAMMA}')
            diff = {c: float(np.max(np.abs(np.array(r['exp'][c]) - np.array(dd['cfg'][pc]['suit']))))
                    for c, pc in pair.items() if dd['cfg'].get(pc)}
            cmp_.append(dict(game=g, step=s, riichi=r['riichi'], max_abs_diff=diff))
            print('noflag 재현', g, s, diff, flush=True)
        res['noflag_repro'] = cmp_
    json.dump(res, open(os.path.join(OUT, 'checks.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              default=lambda x: x.item() if hasattr(x, 'item') else str(x))
    return res


def sortedness_noguess(paifu):
    """서술용 덧붙임: posinfer.sortedness 와 같은 식에서 guess 줄만 뺀 것."""
    p2 = dict(paifu)
    p2['events'] = [e for e in paifu['events'] if not e.get('guess')]
    return PI.sortedness(p2)


# ================================================================ 검사 1: 누설
def _leak_one(args):
    g, ti, check_samples = args
    p = load(H3_DIR, g)
    obs, tt = PI.build_observation(p)
    p2 = SI.fake_paifu(p, obs, tt, ti)
    out = dict(game=g, step=ti)
    try:
        obs2, _ = PI.build_observation(p2)
        o1, o2 = PI.obs_upto(obs, ti), PI.obs_upto(obs2, ti)
        q1, q2 = SI.q_obs(obs, ti, flags=FLAGS), SI.q_obs(obs2, ti, flags=FLAGS)
        out['obs_same'] = bool(o1 == o2 and q1 == q2)
    except Exception as ex:  # noqa
        out['obs_same'] = False
        out['err'] = repr(ex)
        return out
    if not (check_samples and out['obs_same']):
        return out
    ev = obs['steps'][ti]['ev']
    pub, pub2 = PI.build_public(p, ev), PI.build_public(p2, ev)
    out['pub_same'] = all(np.array_equal(pub[k], pub2[k]) if isinstance(pub[k], np.ndarray) else pub[k] == pub2[k]
                          for k in pub)
    tp = bool(obs['steps'][ti].get('riichi'))
    out['tenpai'] = tp

    def same(a, b):
        return (a is None and b is None) or (a is not None and b is not None and a.shape == b.shape
                                             and bool((a == b).all()))
    c1, _ = PI.cstar_infer(o1, pub, None, tp, 11, n=200, maxdraw=40000)
    c2, _ = PI.cstar_infer(o2, pub2, None, tp, 11, n=200, maxdraw=40000)
    out['Cmix_same'] = same(c1, c2)
    for nm, prm in (('Q', Q_PRM), ('QB', QB_PRM)):
        c1, _ = SI.sample_q(q1, pub['unseen'], prm, 200, tp, 11, maxdraw=100_000)
        c2, _ = SI.sample_q(q2, pub2['unseen'], prm, 200, tp, 11, maxdraw=100_000)
        out[nm + '_same'] = same(c1, c2)
    hs1, hs2 = PI.heuristic_score(pub['hero_disc']), PI.heuristic_score(pub2['hero_disc'])
    out['B_same'] = bool(np.array_equal(hs1, hs2))
    return out


def cmd_leak(workers):
    tasks = []
    for g in H3_GAMES:
        obs, _ = PI.build_observation(load(H3_DIR, g))
        ts = turn_steps(obs)
        chk = {ts[-1]} | {i for i in ts if obs['steps'][i].get('riichi')}
        # 울기 판은 울기 바로 뒤 버림 차례도 표본 비교
        for ci, s in enumerate(obs['steps']):
            if s['kind'] == 'call':
                nxt = [j for j in ts if j > ci]
                if nxt:
                    chk.add(nxt[0])
        tasks += [(g, i, i in chk) for i in ts]
    with ProcessPoolExecutor(workers) as ex:
        rows = list(ex.map(_leak_one, tasks, chunksize=1))
    json.dump(rows, open(os.path.join(OUT, 'leak.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ns = [r for r in rows if 'pub_same' in r]
    print(f'누설: 관찰 같음 {sum(r["obs_same"] for r in rows)}/{len(rows)}, 표본 비교 {len(ns)} 차례 — '
          + ', '.join(f'{c} {sum(r[c + "_same"] for r in ns)}/{len(ns)}' for c in ('Cmix', 'Q', 'QB', 'B'))
          + f', 공개 같음 {sum(r["pub_same"] for r in ns)}/{len(ns)}', flush=True)
    return rows


# ================================================================ 채점 · 표 · 판정
def turn_metrics(r, c):
    """차례 하나 · 조건 하나: ① 만통삭 오차 ② 네 수트 오차 ③ 가장 많은 수패 수트 1위 적중(None = 수패 0장) ④ 수트별 ±1."""
    t = np.array(r['truth_suits'], float)
    e = np.array(r['exp'][c], float)
    ad = np.abs(e - t)
    if t[:3].max() > 0:
        top = int(np.argmax(e[:3]))
        hit = float(t[top] == t[:3].max())
    else:
        hit = None
    return dict(e3=float(ad[:3].sum()), e4=float(ad.sum()), top1=hit, w1=[float(x <= 1.0) for x in ad])


def agg(rows, c):
    ms = [turn_metrics(r, c) for r in rows]
    t1 = [m['top1'] for m in ms if m['top1'] is not None]
    w = np.array([m['w1'] for m in ms]) if ms else np.zeros((0, 4))
    return dict(n=len(ms), e3=float(np.mean([m['e3'] for m in ms])) if ms else float('nan'),
                e4=float(np.mean([m['e4'] for m in ms])) if ms else float('nan'),
                top1=float(np.mean(t1)) if t1 else float('nan'), top1_n=len(t1),
                w1_mps=float(w[:, :3].mean()) if len(w) else float('nan'),
                w1_suit=[float(x) for x in w.mean(0)] if len(w) else [float('nan')] * 4)


def load_rows(s):
    fp = os.path.join(OUT, f'turns_{s}.jsonl')
    return [json.loads(x) for x in open(fp, encoding='utf-8')]


def noflag_rows():
    """9절 실행(turns_noflag.jsonl)의 같은 고정 세기를 이 파일 형식으로 다시 꺼냄(2반장 비교의 다른 출처)."""
    nf = os.path.join(PI.OUT_DIR, 'soft', 'turns_noflag.jsonl')
    if not os.path.exists(nf):
        return None
    pair = dict(A='A', B=f'B|{GAMMA_B}', Cmix='Cmix', Q='Q|' + SI.cfg_name(Q_PRM),
                QB=f'QB|{SI.cfg_name(QB_PRM)}|{QB_GAMMA}')
    out = []
    for line in open(nf, encoding='utf-8'):
        d = json.loads(line)
        if d['tag'] != 'main':
            continue
        r = dict(game=d['game'], step=d['step'], truth_suits=suits_of(d['truth']), exp={})
        for c, pc in pair.items():
            m = d['cfg'].get(pc)
            r['exp'][c] = (m if m is not None else d['cfg']['A'])['suit']
        out.append(r)
    return out


def verdict(d, wins):
    if d <= -0.5 and wins >= 7:
        return '칸 번호가 수트 구성을 좁힘(이 판들에서)'
    if d >= -0.2 or wins <= 5:
        return '안 좁힘'
    return '사이'


def f2(x):
    return '—' if x is None or (isinstance(x, float) and np.isnan(x)) else f'{x:.2f}'


def cmd_score(run_sec=None, leak=None, checks=None):
    L = []
    P = L.append
    h3 = load_rows('h3')
    p2 = load_rows('p2')
    if checks is None and os.path.exists(os.path.join(OUT, 'checks.json')):
        checks = json.load(open(os.path.join(OUT, 'checks.json'), encoding='utf-8'))
    tf = os.path.join(OUT, 'timing.json')
    if run_sec is not None:
        json.dump(dict(run=run_sec), open(tf, 'w', encoding='utf-8'), ensure_ascii=False)
    elif os.path.exists(tf):
        run_sec = json.load(open(tf, encoding='utf-8'))['run']
    if leak is None and os.path.exists(os.path.join(OUT, 'leak.json')):
        leak = json.load(open(os.path.join(OUT, 'leak.json'), encoding='utf-8'))
    srt = {}
    for g in H3_GAMES:
        srt[g] = PI.sortedness(load(H3_DIR, g))[:2]
    sc = [r for r in h3 if not r['guess']]
    ng = len(h3) - len(sc)
    P('# 안 본 판으로 수트 구성 재기 — 3반장 11판 (계획서 10절)\n')
    P(f'- 조건 · 세기(10절 고정): A · B(γ {GAMMA_B}) · C\\*mix(posinfer, tiebreak left) · Q (ε, δ0, λ) = {Q_PRM} · '
      f'QB = Q{QB_PRM} 표본 × B 기울기 γ {QB_GAMMA}. 관찰은 세기를 고른 9절 실행과 같게 끝 붙임 표시 없음. 표본 수 · 평활 · 씨 · '
      f'리치 선언 차례 텐파이 표본은 softinfer 그대로(조건 없는 차례 {SI.N_S}, 텐파이 채택 목표 {SI.N_ACC}).')
    P(f'- 차례: hero 버림 직후(posinfer 의 kind == "turn", 쯔모기리 포함) {len(h3)}차례 중 `guess: true` **{ng}차례 뺌** → '
      f'채점 {len(sc)}차례(리치 선언 {sum(r["riichi"] for r in sc)} · 쯔모기리 {sum(r["tsumogiri"] for r in sc)} · '
      f'울기 뒤 {sum(r["after_call"] for r in sc)}). 장수는 닫힌 손(울기 패 뺀 지금 줄) 기준.')
    P('- 지표: ① 만 · 통 · 삭 기대 장수와 실제의 절대 오차 합(주) ② 자패까지 네 수트 ③ 가장 많은 수패 수트 1위 적중'
      '(동률 정답은 어느 하나) ④ 수트마다 ±1장 안 비율(만 · 통 · 삭 평균) ⑤ 정답 줄 정렬 정도(posinfer.sortedness).')
    if run_sec is not None:
        P(f'- 실행: `python -I -X utf8 experiments/paifu_frames/handinfer/h3suit.py all` — {run_sec}')
    P('')
    # ---- 판별 표
    P('## 판별 — ① 만 · 통 · 삭 오차 (차례 평균)\n')
    P('| 판 | 채점 차례 (뺀 guess) | 장수 | 정렬 정도(키) | A | B | C\\*mix | Q | QB | QB − B | Q − B |')
    P('|---|---|---|---|---|---|---|---|---|---|---|')
    per = {}
    for g in H3_GAMES:
        rs = [r for r in sc if r['game'] == g]
        gx = sum(1 for r in h3 if r['game'] == g and r['guess'])
        a = {c: agg(rs, c) for c in COND}
        per[g] = a
        nh = sorted(set(r['n'] for r in rs))
        P(f'| {g} | {len(rs)} ({gx}) | {"/".join(map(str, nh))} | {srt[g][0]:.2f} ({srt[g][1]}) | '
          + ' | '.join(f2(a[c]['e3']) for c in COND) + f' | {a["QB"]["e3"] - a["B"]["e3"]:+.2f} | '
          f'{a["Q"]["e3"] - a["B"]["e3"]:+.2f} |')
    tot = {c: agg(sc, c) for c in COND}
    gm = {c: float(np.mean([per[g][c]['e3'] for g in H3_GAMES])) for c in COND}
    P(f'| **11판 차례 평균 (n={len(sc)})** | {len(sc)} ({ng}) | | | ' + ' | '.join(f'**{tot[c]["e3"]:.2f}**' for c in COND)
      + f' | **{tot["QB"]["e3"] - tot["B"]["e3"]:+.2f}** | {tot["Q"]["e3"] - tot["B"]["e3"]:+.2f} |')
    P('| 판 평균의 평균 | | | | ' + ' | '.join(f'{gm[c]:.2f}' for c in COND)
      + f' | {gm["QB"] - gm["B"]:+.2f} | {gm["Q"] - gm["B"]:+.2f} |')
    P('')
    P('## 판별 — ② 네 수트 오차 · ③ 1위 적중 · ④ ±1장 안(만통삭)\n')
    P('| 판 | ② ' + ' / '.join(COND) + ' | ③ ' + ' / '.join(COND) + ' | ④ ' + ' / '.join(COND) + ' |')
    P('|---|---|---|---|')
    for g in H3_GAMES:
        a = per[g]
        P(f'| {g} | ' + ' / '.join(f2(a[c]['e4']) for c in COND) + ' | '
          + ' / '.join(f2(a[c]['top1']) for c in COND) + ' | ' + ' / '.join(f2(a[c]['w1_mps']) for c in COND) + ' |')
    P('| **11판 차례 평균** | ' + ' / '.join(f'**{tot[c]["e4"]:.2f}**' for c in COND) + ' | '
      + ' / '.join(f'**{tot[c]["top1"]:.2f}**' for c in COND) + ' | '
      + ' / '.join(f'**{tot[c]["w1_mps"]:.2f}**' for c in COND) + ' |')
    P('| 판 평균의 평균 | ' + ' / '.join(f2(np.mean([per[g][c]['e4'] for g in H3_GAMES])) for c in COND) + ' | '
      + ' / '.join(f2(np.mean([per[g][c]['top1'] for g in H3_GAMES if not np.isnan(per[g][c]['top1'])])) for c in COND)
      + ' | ' + ' / '.join(f2(np.mean([per[g][c]['w1_mps'] for g in H3_GAMES])) for c in COND) + ' |')
    P(f'\n③ 분모: 수패가 1장 이상인 차례 {tot["A"]["top1_n"]}/{len(sc)}. ④ 수트별(만 / 통 / 삭 / 자) 11판 차례 평균: '
      + '; '.join(f'{c} ' + '/'.join(f'{x:.2f}' for x in tot[c]['w1_suit']) for c in COND) + '.')
    # ---- 정렬 정도로 나눔
    full = [g for g in H3_GAMES if srt[g][0] >= 1.0]
    part = [g for g in H3_GAMES if srt[g][0] < 1.0]
    P('\n## 정렬 정도로 나눔 (⑤)\n')
    P('| 묶음 | 판 | 차례 | ① ' + ' / '.join(COND) + ' | QB − B ① | QB < B 판 | ② ' + ' / '.join(COND) + ' | ③ QB / B |')
    P('|---|---|---|---|---|---|---|---|')
    for nm, gs in (('정렬 정도 1.00', full), ('정렬 정도 < 1', part)):
        rs = [r for r in sc if r['game'] in gs]
        if not rs:
            P(f'| {nm} | (없음) | 0 | | | | | |')
            continue
        a = {c: agg(rs, c) for c in COND}
        w = sum(1 for g in gs if per[g]['QB']['e3'] < per[g]['B']['e3'])
        P(f'| {nm} | {", ".join(gs)} | {len(rs)} | ' + ' / '.join(f2(a[c]['e3']) for c in COND)
          + f' | {a["QB"]["e3"] - a["B"]["e3"]:+.2f} | {w}/{len(gs)} | ' + ' / '.join(f2(a[c]['e4']) for c in COND)
          + f' | {f2(a["QB"]["top1"])} / {f2(a["B"]["top1"])} |')
    if checks:
        P('\n정렬 정도는 posinfer.sortedness 그대로(guess 줄 포함). 덧붙임 — guess 줄을 뺀 값: ' + ', '.join(
            f'{g[3:]} {checks["games"][g]["sortedness_noguess"][0]:.2f}' for g in H3_GAMES)
          + '. (151953 은 guess 줄 하나 때문에 0.99 → 빼면 1.00 이지만 묶음은 정의대로 posinfer 값으로 나눔.)')
    # ---- 판정
    d = tot['QB']['e3'] - tot['B']['e3']
    wins = sum(1 for g in H3_GAMES if per[g]['QB']['e3'] < per[g]['B']['e3'])
    ties = sum(1 for g in H3_GAMES if per[g]['QB']['e3'] == per[g]['B']['e3'])
    v = verdict(d, wins)
    P('\n## 판정 (10절 기준 그대로)\n')
    P(f'QB − B ① 차례 평균 **{d:+.2f}장**, QB < B 판 **{wins}/11**(같음 {ties}) → **{v}**')
    P('\n(기준: 좁힘 = 차례 평균 ≤ −0.5 이고 QB < B 판 ≥ 7. 안 좁힘 = ≥ −0.2 이거나 QB < B 판 ≤ 5. 그 사이 = 사이. '
      '11판 · Opus 정답이라 "된다" 가 아니라 "이 판들에서" 까지만.)')
    # ---- 깨짐 · 검사
    P('\n## 검사\n')
    qb = sum(1 for r in sc if r['q_broken'])
    qbb = sum(1 for r in sc if r['qb_broken'])
    cb = sum(1 for r in sc if r['cmix_broken'])
    P(f'- (4) Q "가정 깨짐(표본 0)": Q 세기 {qb}/{len(sc)} 차례 · QB 세기 {qbb}/{len(sc)} 차례(guess 포함 전체 '
      f'{sum(1 for r in h3 if r["q_broken"])}/{sum(1 for r in h3 if r["qb_broken"])} / {len(h3)}). 참고 C\\*mix 깨짐(→ A 로 채점) '
      f'{cb}/{len(sc)}. QB ESS 중앙 {np.median([r["qb_ess"] for r in sc if r["qb_ess"]]):.0f} · 최소 '
      f'{min(r["qb_ess"] for r in sc if r["qb_ess"]):.0f}.')
    tp = [r for r in sc if r['riichi']]
    if tp:
        P(f'- 리치 선언 차례 {len(tp)}개 텐파이 채택 수(A / B / C\\*mix / Q / QB): ' + '; '.join(
            f'{r["game"][3:]}#{r["step"]} ' + '/'.join(str(r['acc'][c][0]) for c in COND) for r in tp))
    if leak:
        ns = [r for r in leak if 'pub_same' in r]
        P(f'- (1) 누설: 숨은 패(그 시점까지 안 드러난 미지수)를 서로 다른 가짜 종류(X번호)로 바꾼 h3 패보(시점까지 자름, '
          f'softinfer.fake_paifu = posinfer.leak_test 방식)로 관찰을 다시 뽑음 — obs_upto · q_obs 같음 '
          f'{sum(r["obs_same"] for r in leak)}/{len(leak)} 차례. 같은 씨 표본 비교 {len(ns)} 차례(판마다 마지막 · 리치 선언 · '
          f'울기 바로 뒤 버림, 텐파이 {sum(r.get("tenpai", False) for r in ns)}): 공개 정보 같음 '
          f'{sum(r["pub_same"] for r in ns)}/{len(ns)}, C\\*mix {sum(r["Cmix_same"] for r in ns)}/{len(ns)}, Q '
          f'{sum(r["Q_same"] for r in ns)}/{len(ns)}, QB {sum(r["QB_same"] for r in ns)}/{len(ns)}, B 휴리스틱 '
          f'{sum(r["B_same"] for r in ns)}/{len(ns)} 같음.')
    if checks:
        gs = checks['games']
        P(f'- (2) 관찰 만들기: 11판 모두 posinfer.build_observation 성공 '
          f'{sum(1 for x in gs.values() if x.get("build") == "ok")}/11, self_check(미지수 줄 × 정답 종류 == 원래 줄, 공개 패 == 정답) '
          f'통과. 손에서 낸 차례 중 k 없음 {sum(len(x["k_missing"]) for x in gs.values())}, 뽑은 패가 남은 차례 중 j 없음 '
          f'{sum(len(x["j_missing"]) for x in gs.values())}, 쯔모기리 표시와 복원 어긋남 '
          f'{sum(len(x["tsumogiri_flag_mismatch"]) for x in gs.values())}. 울기 직후 버림(뽑은 패 없음 → j 없음이 정상) '
          f'{sum(x["after_call_discards"] for x in gs.values())}. k · j 밖으로 움직인 미지수가 있는 차례(정리) '
          f'{sum(len(x["moved"]) for x in gs.values())}. 같은 종류 중복 때문에 left/right tiebreak 로 k · j 가 달라지는 차례 '
          f'{sum(len(x["left_right_kj_diff"]) for x in gs.values())}(left 를 씀 — 10절 지정).')
        P(f'- (3) 정답 수트 장수: 관찰 미지수 줄 × 정답 종류로 센 것과 hero `hand` 칸에서 센 것이 다른 차례 '
          f'{sum(x["truth_suit_mismatch"] for x in gs.values())}; jsonl 의 truth_suits 도 채점 때 hand 칸에서 다시 셈(아래). '
          f'끝 줄 == result.hand(hero 화료 판): '
          + ', '.join(f'{g[3:]} {x["final_row_eq_result_hand"]}' for g, x in gs.items() if x['final_row_eq_result_hand'] is not None)
          + '.')
        nr = checks.get('noflag_repro')
        if nr:
            mx = max(max(x['max_abs_diff'].values()) for x in nr)
            P(f'- 9절 실행과 같은 계산인지: 2반장 r12 · r17 의 {len(nr)} 차례를 이 스크립트로 다시 돌려 turns_noflag.jsonl 의 '
              f'같은 세기 기대 장수와 비교 — 최대 절대 차 {mx:.4g}.')
    # 검사 3 다시: jsonl truth_suits == 패보 hand 칸
    mis = 0
    for r in h3:
        e = load(H3_DIR, r['game'])['events'][r['ev']]
        mis += suits_of(np.bincount([tid(x) for x in e['hand']], minlength=34)) != r['truth_suits']
    P(f'- jsonl truth_suits 와 패보 hand 칸 다시 센 것 어긋남 {mis}/{len(h3)}.')
    # ---- 2반장 비교
    P('\n## 비교용 — 2반장 8판 (같은 고정 세기, 판정에 안 씀)\n')
    P('세기를 고른 판이라 평가 밖. (가) 이 스크립트로 지금 assets/paifu 를 다시 돌린 것, (나) 9절 실행 turns_noflag.jsonl 의 같은 '
      '세기를 다시 채점한 것(r13 · r15 · r19 는 11-21 22:21 에 파일이 다시 쓰여 (나)는 옛 판).\n')
    P('| 출처 | 차례 | ① ' + ' / '.join(COND) + ' | QB − B ① | QB < B 판 | ② ' + ' / '.join(COND) + ' | ③ '
      + ' / '.join(COND) + ' | ④ ' + ' / '.join(COND) + ' |')
    P('|---|---|---|---|---|---|---|---|')

    def line(nm, rows):
        a = {c: agg(rows, c) for c in COND}
        games = sorted(set(r['game'] for r in rows))
        w = sum(1 for g in games if agg([r for r in rows if r['game'] == g], 'QB')['e3']
                < agg([r for r in rows if r['game'] == g], 'B')['e3'])
        P(f'| {nm} | {len(rows)} | ' + ' / '.join(f2(a[c]['e3']) for c in COND) + f' | {a["QB"]["e3"] - a["B"]["e3"]:+.2f} | '
          f'{w}/{len(games)} | ' + ' / '.join(f2(a[c]['e4']) for c in COND) + ' | '
          + ' / '.join(f2(a[c]['top1']) for c in COND) + ' | ' + ' / '.join(f2(a[c]['w1_mps']) for c in COND) + ' |')
    line('(가) 다시 돌림 · 전 차례', p2)
    line('(가) 다시 돌림 · guess 뺌', [r for r in p2 if not r['guess']])
    nf = noflag_rows()
    if nf:
        line('(나) turns_noflag 다시 채점 · 전 차례', nf)
    P('\n(9절 표의 ② 는 판마다 LOGO 로 고른 세기 — 여기 (가)·(나)는 "8판 전부" 줄 하나로 고정한 값이라 9절 표와 조금 다를 수 있다.)')
    P('\n2반장 판별 ① (다시 돌림 · 전 차례): ' + '; '.join(
        f'{g[:3]} ' + '/'.join(f2(agg([r for r in p2 if r["game"] == g], c)['e3']) for c in ('B', 'Q', 'QB'))
        for g in P2_GAMES) + ' (B/Q/QB)')
    P('\n## 파일\n')
    P('- `turns_h3.jsonl` · `turns_p2.jsonl`: 차례마다 set · game · step · ev · n(닫힌 손 장수) · riichi · guess · tsumogiri · '
      'k · j · after_call · truth_suits [만, 통, 삭, 자] · exp{조건: [만, 통, 삭, 자] 기대 장수} · logs · fallback · acc '
      '[채택, 뽑음] · q_broken · qb_broken · cmix_broken · qb_ess. 지표는 truth_suits 와 exp 만으로 다시 계산된다.')
    P('- `checks.json`(검사 2 · 3 · 9절 재현), `leak.json`(검사 1), `run.log`.')
    txt = '\n'.join(L)
    print(txt)
    with open(os.path.join(OUT, 'summary.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt + '\n')
    json.dump(dict(verdict=v, qb_minus_b=d, wins=wins, overall={c: tot[c] for c in COND},
                   per_game={g: per[g] for g in H3_GAMES}, guess_excluded=ng, scored=len(sc)),
              open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'all'
    workers = max(1, (os.cpu_count() or 2) - 2)
    if cmd == 'check':
        cmd_check()
    elif cmd == 'leak':
        cmd_leak(workers)
    elif cmd == 'run':
        cmd_run(workers)
    elif cmd == 'score':
        cmd_score()
    elif cmd == 'all':
        t0 = time.time()
        ck = cmd_check()
        lk = cmd_leak(workers)
        rs = cmd_run(workers)
        tot = time.time() - t0
        cmd_score(run_sec=f'전체 {tot:.0f}초(표본 run {rs:.0f}초, 작업 프로세스 {workers}개)', leak=lk, checks=ck)


if __name__ == '__main__':
    main()
