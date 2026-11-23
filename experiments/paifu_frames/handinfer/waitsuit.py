"""대기 수트 추정 — 칸 번호(습관 흉내)가 리치 대기 수트를 더 잘 맞히게 하나 (계획서 docs/hand_infer_plan_1120.md 7절).

외부 API 없음, 순수 계산. 자료는 tenhou_fetch.py(내려받기) → tenhou_parse.py(리치 기록) 결과.
다시 돌리기(저장소 뿌리에서, 순서대로):
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py habits     # 우리 8판에서 습관 매개변수 세기
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py sample dev  # 개발 판 표본(A·B·P·PB)
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py sample test # 시험 판 표본
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py leak        # 누설 검사
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py real        # r18 · r14 방향 확인
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py real2       # 2반장 r16(리치) · L16(1z 퐁 · 유국 텐파이) + r18 그대로 확인
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py report      # S 학습(개발 판만) · γ·ε 고르기 · 채점 · 판정
    python -I -X utf8 experiments/paifu_frames/handinfer/waitsuit.py example H2  # 손으로 확인할 예 하나

구조(누설 막기):
  simulate(rec 의 숨은 부분, 습관, 키)  → 물리 줄 기록 phys(미지수 번호만) + 정답 종류(따로)
  make_obs(phys, 공개 종류)              → 관찰(줄 · 끝 붙임 표시 · 공개 패). 숨은 종류를 받지 않는다.
  pub_info(rec['pub'])                   → 남은 패 수 · 리치한 사람 버림(쯔모기리) · 강 읽기 특징
  sample_A / sample_P(관찰, 공개)        → 텐파이 조건 표본. 습관 · 키 · 정답은 안 받는다.
  채점은 rec['hid'] 의 정답 대기로만.
"""
import json
import math
import os
import sys
import time
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import posinfer as PI  # noqa: E402
from posinfer import (KEYS, RANK, YAO, _sflag, dp_sample, dp_table, fast_waits, heuristic_score,  # noqa: E402
                      key_name, tid, tname)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OUT = os.path.join(ROOT, 'experiments', 'paifu_frames', 'results', 'handinfer', 'waitsuit')
REC = os.path.join(OUT, 'riichi_records.json')

SPLIT_SEED = 20261121
N_DEV = 200
HABITS = ['H1', 'H2', 'H3']
H_GAMES = {'H1': ['r12_131655', 'r17_140450', 'r19_142013'],
           'H2': ['r16_135321', 'r13_132644'],
           'H3': ['r11_130921', 'r15_134151', 'L16_135321']}
GAMMAS = [0.0, 0.1, 0.25, 0.5, 1.0, 2.0]
N_ACC = 400          # 텐파이 표본 목표 수
BATCH = 4000
MAXDRAW = 400_000    # P: 이만큼 뽑아도 채택 30 미만이면 10 배까지 더
MAXDRAW_A = 2_000_000  # A: 사전 뽑기가 싸서 크게(채택 30 미만이면 4 배까지)
SUITN = 'mpsz'


# ================================================================ 습관 매개변수(우리 8판)
def _rank_key(R, t):
    return (R[t], t)


def habit_params():
    """우리 8판 정답 줄(posinfer.build_observation, left)에서 습관별로 센다. 키는 판마다 sortedness() 가 고른 것."""
    per_game = {}
    for g in PI.GAMES:
        p = PI.load(g)
        obs, tt = PI.build_observation(p)
        so, kn, ki = PI.sortedness(p)
        R = RANK[ki]
        kept = tail = last_ok = off = 0
        offsets = []
        tail_live = {}           # var → 노출 차례 수
        tidied = exposure = censored = 0
        init_out = init_n = 0
        for st in obs['steps']:
            if st['kind'] == 'start':
                rr = [R[tt[v]] for v in st['row']]
                # 가장 긴 비내림 부분열
                best = [1] * len(rr)
                for i in range(len(rr)):
                    for j in range(i):
                        if rr[j] <= rr[i]:
                            best[i] = max(best[i], best[j] + 1)
                init_out += len(rr) - max(best)
                init_n += len(rr)
                continue
            if st['kind'] != 'turn':
                continue
            # 끝 붙임 패: 이번 차례에 옮겨졌나 / 버려졌나 / 그대로
            moved = set(st.get('moved') or [])
            for v in list(tail_live):
                if v in st['reveal']:
                    censored += 1; del tail_live[v]
                elif v in moved:
                    tidied += 1; exposure += 1; del tail_live[v]
                else:
                    exposure += 1
            row = st['row']
            d = st['drawn']
            if d is None or d not in row:
                continue
            kept += 1
            i = row.index(d)
            lft = R[tt[row[i - 1]]] if i > 0 else -1
            rgt = R[tt[row[i + 1]]] if i < len(row) - 1 else 99
            ok = lft <= R[tt[d]] <= rgt
            last = i == len(row) - 1
            if last and ok:
                last_ok += 1
            elif last:
                tail += 1
                tail_live[d] = 0
            elif not ok:
                off += 1
                others = [R[tt[v]] for v in row if v != d]
                okpos = [q for q in range(len(others) + 1)
                         if (q == 0 or others[q - 1] <= R[tt[d]]) and (q == len(others) or R[tt[d]] <= others[q])]
                offsets.append(min(abs(i - q) for q in okpos) if okpos else 3)
        censored += len(tail_live)
        per_game[g] = dict(key=kn, sorted=round(so, 3), kept=kept, tail=tail, last_ok=last_ok, off=off,
                           offsets=offsets, tidied=tidied, exposure=exposure, censored=censored,
                           init_out=init_out, init_n=init_n)
    hp = {}
    for h, gs in H_GAMES.items():
        a = {k: sum(per_game[g][k] for g in gs) for k in ('kept', 'tail', 'last_ok', 'off', 'tidied', 'exposure',
                                                          'censored', 'init_out', 'init_n')}
        offs = sum((per_game[g]['offsets'] for g in gs), [])
        q_tail = a['tail'] / max(1, a['kept'] - a['last_ok'])
        q_off = a['off'] / max(1, a['kept'])
        hz = a['tidied'] / a['exposure'] if a['exposure'] else 0.0
        hp[h] = dict(games=gs, **a, q_tail=round(q_tail, 3), q_off=round(q_off, 3), tidy_hazard=round(hz, 3),
                     init_mis=round(a['init_out'] / a['init_n'], 3), offsets=offs or [1])
    keys = sorted(set(per_game[g]['key'] for g in PI.GAMES))
    kidx = [next(i for i in range(len(KEYS)) if key_name(i) == k) for k in keys]
    freq = {h: len(gs) / len(PI.GAMES) for h, gs in H_GAMES.items()}
    # 습관 정의(결과 전 고정): H1 은 흉내 매개변수 0(완전 정렬). H2 · H3 은 센 값.
    hp['H1'].update(q_tail=0.0, q_off=0.0, tidy_hazard=0.0, init_mis=0.0)
    return dict(per_game=per_game, habits=hp, keys=keys, key_idx=kidx, freq=freq)


# ================================================================ 줄 흉내
def simulate(hid, habit, ki, hp, rng):
    """hid: 배패(번호 13) · 차례 [뽑은 번호, 버린 번호, 쯔모기리]. 반환 phys(미지수 번호만) · types(정답, 채점 · 검사용)."""
    R = RANK[ki]
    prm = hp[habit]
    types, raw = {}, {}
    nv = [0]

    def new(code):
        v = nv[0]; nv[0] += 1
        raw[v] = int(code); types[v] = ttype(code)
        return v

    def sk(v):
        return (R[types[v]], types[v])

    def sorted_pos(body, v):
        idx = 0
        for i, u in enumerate(body):
            if sk(u) <= sk(v):
                idx = i + 1
        return idx

    def off_pos(body, v):
        b = sorted_pos(body, v)
        d = int(rng.choice(prm['offsets'])) or 1
        d *= 1 if rng.random() < 0.5 else -1
        return int(min(max(b + d, 0), len(body)))

    row = sorted((new(c) for c in hid['haipai']), key=sk)
    if prm['init_mis'] > 0:
        for v in list(row):
            if rng.random() < prm['init_mis']:
                row.remove(v)
                row.insert(off_pos(row, v), v)
    tail = []                     # 물리적으로 끝에 붙여 둔 패(H2 · H3)
    phys = dict(start=list(row), turns=[])
    for drw, dsc, tg in hid['turns']:
        moved = []
        if tail and rng.random() < prm['tidy_hazard']:
            body = [v for v in row if v not in tail]
            for v in tail:
                body.insert(sorted_pos(body, v), v)
            moved = list(tail)
            tail = []
            row = body
        d = new(drw)
        if tg:
            phys['turns'].append(dict(drawn=d, tsumogiri=True, disc=d, moved=moved, row=list(row)))
            continue
        body = [v for v in row if v not in tail]
        u = rng.random()
        if u < prm['q_tail']:
            row = body + tail + [d]
            tail.append(d)
        else:
            if u < prm['q_tail'] + prm['q_off']:
                body.insert(off_pos(body, d), d)
            else:
                body.insert(sorted_pos(body, d), d)
            row = body + tail
        cand = [v for v in row if v != d and raw[v] == int(dsc)]
        if not cand:
            cand = [v for v in row if v != d and types[v] == ttype(dsc)]
        x = cand[int(rng.integers(len(cand)))]
        row.remove(x)
        if x in tail:
            tail.remove(x)
        phys['turns'].append(dict(drawn=d, tsumogiri=False, disc=x, moved=moved, row=list(row)))
    return phys, types


def ttype(c):
    c = int(c)
    if c in (51, 52, 53):
        return (c - 51) * 9 + 4
    return (c // 10 - 1) * 9 + c % 10 - 1


def make_obs(phys, rev):
    """phys: 미지수 번호 줄 기록. rev: 공개된(버린) 미지수 → 종류. 숨은 미지수의 종류는 받지 않는다.
    끝 붙임 표시: 뽑은 패가 새 줄의 맨 끝에 서면 표시, 그 뒤 옮겨지거나 버려지면 지움(관찰자가 볼 수 있는 것만)."""
    flags = set()
    rows = [(list(phys['start']), frozenset())]
    reveal = {}
    for t in phys['turns']:
        flags -= set(t['moved'])
        reveal[t['disc']] = rev[t['disc']]
        flags.discard(t['disc'])
        row = t['row']
        if not t['tsumogiri'] and row and row[-1] == t['drawn']:
            flags.add(t['drawn'])
        if row != rows[-1][0] or frozenset(flags) != rows[-1][1]:
            rows.append((list(row), frozenset(flags)))
    cur = rows[-1][0]
    return dict(rows=[(r, sorted(f)) for r, f in rows], reveal=reveal, cur=list(cur), flags=sorted(flags))


# ================================================================ 공개 정보 · 강 읽기 특징
def pub_info(pub):
    vis = np.zeros(34, int)
    for s, t, tg, r in pub['river']:
        vis[t] += 1
    for t in pub['meld_vis']:
        vis[t] += 1
    for t in pub['dora']:
        vis[t] += 1
    unseen = np.maximum(4 - vis, 0)
    hero_disc = [dict(tile=t, tsumogiri=bool(tg)) for t, tg in pub['own']]
    return dict(vis=vis, unseen=unseen, hero_disc=hero_disc, hs=heuristic_score(hero_disc), over=int((vis > 4).sum()))


def _cls(t):
    n = t % 9 + 1
    return 'term' if (t >= 27 or n in (1, 9)) else ('28' if n in (2, 8) else 'mid')


S_FEATS = ['is_z', 'n_disc', 'n_te', 'n_tg', 'frac_disc', 'rt_in', 'rt_term', 'rt_28', 'rt_mid', 'rt_tg',
           'lt_in', 'lt_term', 'lt_28', 'lt_mid', 'early_out', 'alive_all', 'alive_ry', 'hanpai',
           'unseen_frac', 'logitA', 'n_turn', 'logitA_z', 'alive_z']


def s_features(pub, pi, a_suit):
    """수트마다 강 읽기 특징(리치 선언까지의 공개 정보만). a_suit: A(텐파이 조건)의 수트 확률."""
    own = pub['own']
    n = len(own)
    vis = pi['vis']
    unseen = pi['unseen']
    river_own = set(t for t, _ in own)
    rt, rtg = own[-1]
    te = [t for t, tg in own[:-1] if not tg]
    lt = te[-1] if te else None
    tot_unseen = max(1, unseen.sum())
    F = np.zeros((4, len(S_FEATS)))
    for s in range(4):
        rng_ = range(s * 9, s * 9 + (7 if s == 3 else 9))
        ins = [t for t, _ in own if t // 9 == s]
        f = dict(is_z=float(s == 3), n_disc=len(ins), n_te=sum(1 for t, tg in own if t // 9 == s and not tg),
                 n_tg=sum(1 for t, tg in own if t // 9 == s and tg), frac_disc=len(ins) / n)
        f['rt_in'] = float(rt // 9 == s)
        for c in ('term', '28', 'mid'):
            f['rt_' + c] = f['rt_in'] * float(_cls(rt) == c)
        f['rt_tg'] = f['rt_in'] * float(bool(rtg))
        f['lt_in'] = float(lt is not None and lt // 9 == s)
        for c in ('term', '28', 'mid'):
            f['lt_' + c] = f['lt_in'] * float(lt is not None and _cls(lt) == c)
        f['early_out'] = (sum(1 for t, tg in own[:6] if not tg and t // 9 == s and t % 9 + 1 in (1, 2, 8, 9))
                          if s < 3 else 0.0)
        # 대기 모양: 현물(자기 강 = 후리텐) · 벽(필요한 패 · 대기 패가 다 보임)으로 막힌 것 빼고 산 비율
        alive = tot = ry_alive = 0
        if s < 3:
            b = s * 9
            shapes = []
            for a in range(1, 7):                    # 양면 (a+1, a+2) 대기 a, a+3  (번호 0 기준)
                shapes.append(('ry', [b + a, b + a + 1], [b + a - 1, b + a + 2]))
            for a in range(0, 7):                    # 간짱
                shapes.append(('ka', [b + a, b + a + 2], [b + a + 1]))
            shapes.append(('pe', [b + 0, b + 1], [b + 2]))
            shapes.append(('pe', [b + 7, b + 8], [b + 6]))
            for a in range(9):                       # 단기 · 샨폰
                shapes.append(('ta', [b + a], [b + a]))
            for kind, held, wt in shapes:
                tot += 1
                if kind == 'ta':          # 단기 · 샨폰: 그 패가 2장 이상 남아 있고 후리텐 아님
                    ok = unseen[held[0]] >= 2 and held[0] not in river_own
                else:                     # 들고 있을 패가 남아 있고, 대기 패가 후리텐 아니고, 대기 패가 하나라도 남음
                    ok = (all(unseen[h] >= 1 for h in held) and not any(w in river_own for w in wt)
                          and any(unseen[w] >= 1 for w in wt))
                alive += ok
                if kind == 'ry':
                    ry_alive += ok
            f['alive_all'] = alive / tot
            f['alive_ry'] = ry_alive / 6
            f['alive_z'] = 0.0
        else:
            al = sum(1 for t in rng_ if t not in river_own and unseen[t] >= 2)
            f['alive_all'] = al / 7
            f['alive_ry'] = 0.0
            f['alive_z'] = al / 7
        hp_ = 0
        if s < 3:
            for x, y in zip(te, te[1:]):
                if x // 9 == s and y // 9 == s and abs(x - y) <= 2:
                    hp_ += 1
        f['hanpai'] = hp_
        f['unseen_frac'] = sum(unseen[t] for t in rng_) / tot_unseen
        pa = min(max(a_suit[s], 1e-4), 1 - 1e-4)
        f['logitA'] = math.log(pa / (1 - pa))
        f['n_turn'] = n
        f['logitA_z'] = f['logitA'] * f['is_z']
        F[s] = [f[k] for k in S_FEATS]
    return F


# ================================================================ 빠른 텐파이 판정(묶음)
_P5 = 5 ** np.arange(9)
_SC = [dict(), dict()]


def _suit_info(code, honor):
    d = _SC[honor]
    r = d.get(code)
    if r is None:
        L = 7 if honor else 9
        c = [(code // 5 ** i) % 5 for i in range(L)]
        f = _sflag(tuple(c), honor)
        am = 0
        for x in range(L):
            if c[x] >= 4:
                continue
            c[x] += 1
            g = _sflag(tuple(c), honor)
            c[x] -= 1
            if g == 0:
                am |= 1
            elif g == 2:
                am |= 2
        r = (-1 if f is None else f, am)
        d[code] = r
    return r


def tenpai_batch(cnts):
    S = len(cnts)
    fl = np.zeros((S, 4), int)
    am = np.zeros((S, 4), int)
    for s in range(4):
        L = 7 if s == 3 else 9
        codes = cnts[:, s * 9:s * 9 + L] @ _P5[:L]
        u, inv = np.unique(codes, return_inverse=True)
        info = np.array([_suit_info(int(x), s == 3) for x in u])
        fl[:, s] = info[inv, 0]
        am[:, s] = info[inv, 1]
    valid = fl >= 0
    is2 = fl == 2
    ok = np.zeros(S, bool)
    for s in range(4):
        oth = [k for k in range(4) if k != s]
        vo = valid[:, oth].all(1)
        n2o = is2[:, oth].sum(1)
        ok |= vo & ((((am[:, s] & 1) > 0) & (n2o == 1)) | (((am[:, s] & 2) > 0) & (n2o == 0)))
    chi = ((cnts == 2).sum(1) == 6) & ((cnts == 1).sum(1) == 1) & (cnts.max(1) <= 2)
    y = cnts[:, YAO]
    kok = (y.sum(1) == 13) & (y.max(1) <= 2) & ((y > 0).sum(1) >= 12)
    return ok | chi | kok


def tenpai_batch_check(n=40000, seed=3):
    rng = np.random.default_rng(seed)
    pool = np.repeat(np.arange(34), 4)
    rows = np.array([np.bincount(rng.choice(pool, 13, replace=False), minlength=34) for _ in range(n)])
    # 텐파이 근처도 섞기: 완성형에서 한 장 빼기
    near = []
    for _ in range(n // 2):
        c = np.zeros(34, int)
        while True:
            c[:] = 0
            for _k in range(4):
                if rng.random() < 0.5:
                    c[rng.integers(34)] += 3
                else:
                    s = rng.integers(3); x = rng.integers(7); c[s * 9 + x:s * 9 + x + 3] += 1
            c[rng.integers(34)] += 2
            if c.max() <= 4:
                break
        nz = np.flatnonzero(c); c[rng.choice(nz)] -= 1
        if rng.random() < 0.3:
            nz = np.flatnonzero(c); c[rng.choice(nz)] -= 1
            t = rng.integers(34)
            c[t if c[t] < 4 else nz[0]] += 1
        near.append(c.copy())
    rows = np.concatenate([rows, np.array(near)])
    rows = rows[rows.max(1) <= 4]          # 생성기가 가끔 만드는 5장짜리(불가능한 손)는 뺌
    fast = tenpai_batch(rows)
    ref = np.array([bool(fast_waits(tuple(int(x) for x in r))) for r in rows])
    return int((fast != ref).sum()), int(ref.sum()), len(rows)


# ================================================================ 표본
def _accumulate(gen, seed, n_acc=N_ACC, maxdraw=MAXDRAW, ext=10):
    """gen(rng, k) → [k,34] 표본(사전). 텐파이만 남김. maxdraw 까지 뽑고, 채택 30 미만이면 ext 배까지 더.
    반환 (채택 표본, 뽑은 수, 채택 수)."""
    rng = np.random.default_rng(seed)
    out, drawn, got = [], 0, 0
    while got < n_acc:
        if drawn >= maxdraw and (got >= 30 or drawn >= ext * maxdraw):
            break
        c = gen(rng, BATCH)
        drawn += BATCH
        c = c[tenpai_batch(c)]
        out.append(c)
        got += len(c)
    cn = np.concatenate(out) if out else np.zeros((0, 34), int)
    return cn[:n_acc], drawn, int(got)


def sample_A(unseen, seed, n_hand=13):
    """n_hand: 숨은 손 장수(울기 있으면 13 − 3×울기 수). 기본 13 = 리치 손(기존 동작 그대로)."""
    col = unseen.astype(np.int64)

    def gen(rng, k):
        return rng.multivariate_hypergeometric(col, n_hand, size=k)
    return _accumulate(gen, seed, maxdraw=MAXDRAW_A, ext=4)


def p_structs(obs):
    """키와 무관한 제약 재료: 지금 줄에서 표시 안 된 미지수(제약 받는 칸) 순서, 공개-공개 짝, 공개-미지수 경계 짝, 뒤집힌 짝."""
    rv = obs['reveal']
    fl = set(obs['flags'])
    cur_c = [v for v in obs['cur'] if v not in fl]
    pos = {v: i for i, v in enumerate(cur_c)}
    rr, lo_p, hi_p = set(), set(), set()
    eq = np.zeros(max(len(cur_c) - 1, 0), bool)
    for r, ex in obs['rows']:
        exs = set(ex)
        rr_ = [v for v in r if v not in exs]
        for ai in range(len(rr_)):
            a = rr_[ai]
            for b in rr_[ai + 1:]:
                ra, rb = a in rv, b in rv
                if ra and rb:
                    rr.add((rv[a], rv[b]))
                elif ra:
                    if b in pos:
                        lo_p.add((pos[b], rv[a]))
                elif rb:
                    if a in pos:
                        hi_p.add((pos[a], rv[b]))
                else:
                    if a in pos and b in pos and pos[a] > pos[b]:
                        eq[pos[b]:pos[a]] = True
    return dict(m=len(cur_c), nfree=len(obs['cur']) - len(cur_c), rr=sorted(rr), lo=sorted(lo_p), hi=sorted(hi_p),
                eq=eq)


def sample_P(obs, unseen, seed):
    """P: 48 키를 DP 우도로 섞은 '완전 정렬(표시 패 빼고)' 가정의 정확 표본 + 표시 패는 남은 패에서 자유롭게, 텐파이만.
    반환 (표본 또는 None(가정 깨짐), 정보)."""
    st = p_structs(obs)
    m, nfree = st['m'], st['nfree']
    N = int(unseen.sum())
    tabs, like = {}, np.zeros(len(KEYS))
    for k in range(len(KEYS)):
        R = RANK[k]
        if any(R[a] > R[b] for a, b in st['rr']):
            continue
        lo = np.full(m, -np.inf)
        hi = np.full(m, np.inf)
        for p, t in st['lo']:
            lo[p] = max(lo[p], R[t])
        for p, t in st['hi']:
            hi[p] = min(hi[p], R[t])
        F, ch, cls = dp_table(lo, hi, st['eq'], unseen, k)
        if F[0][0] == 0:
            continue
        tabs[k] = (F, ch, cls)
        like[k] = F[0][0] / math.comb(N, m)
    info = dict(m=m, nfree=nfree, n_rr=len(st['rr']), n_lo=len(st['lo']), n_hi=len(st['hi']),
                n_eq=int(st['eq'].sum()), keys_alive=int((like > 0).sum()))
    if like.sum() == 0:
        info['broken'] = True
        return None, 0, 0, info
    info['broken'] = False
    post = like / like.sum()
    info['key_top'] = [(key_name(int(i)), round(float(post[i]), 3)) for i in np.argsort(-post)[:3]]
    keys = np.flatnonzero(post > 0)
    pk = post[keys] / post[keys].sum()

    def gen(rng, kk):
        ksel = keys[rng.choice(len(keys), size=kk, p=pk)]
        cn = np.zeros((kk, 34), np.int64)
        for k in np.unique(ksel):
            idx = np.flatnonzero(ksel == k)
            F, ch, cls = tabs[int(k)]
            cn[idx] = dp_sample(F, ch, cls, unseen, len(idx), rng)
        if nfree:
            rest = unseen[None, :] - cn
            for i in range(kk):
                cn[i] += rng.multivariate_hypergeometric(rest[i].astype(np.int64), nfree)
        return cn
    cn, drawn, got = _accumulate(gen, seed)
    info.update(drawn=drawn, accepted=got, post=post.round(4).tolist())
    if len(cn) == 0:
        info['no_tenpai'] = True
        return None, drawn, got, info
    return cn, drawn, got, info


def summarize(cn, hs, true_waits):
    """γ 마다: 수트별 '대기 있음' 확률(평활), 정답 대기의 최고 순위(동순위 가운데). γ=0 이 무가중."""
    W = np.zeros((len(cn), 34), bool)
    for i, r in enumerate(cn):
        for t in fast_waits(tuple(int(x) for x in r)):
            W[i, t] = True
    WS = np.stack([W[:, s * 9:s * 9 + (7 if s == 3 else 9)].any(1) for s in range(4)], 1)
    e = cn @ hs
    out = {}
    for g in GAMMAS:
        lw = -g * e
        w = np.exp(lw - lw.max())
        w /= w.sum()
        ess = 1.0 / (w ** 2).sum()
        ps = (ess * (w @ WS) + 0.5) / (ess + 1)
        ratio = w @ W
        best = None
        for t in true_waits:
            r = 1 + (ratio > ratio[t]).sum() + ((ratio == ratio[t]).sum() - 1) / 2
            best = r if best is None else min(best, r)
        out[str(g)] = dict(ps=ps.round(5).tolist(), rank=float(best), ess=round(float(ess), 1),
                           ratio=ratio.round(5).tolist())
    return out


# ================================================================ 한 리치
def infer_all(obs, pub, tw, base, n_hand=13):
    """추정 전부: 관찰(obs) · 공개(pub) 만 쓴다. tw(정답 대기)는 summarize 의 순위 채점에만 쓰인다.
    n_hand: A 표본 장수(관찰 줄 길이 len(obs['cur']) 를 넘김, 기본 13). P 는 줄 길이로 저절로 맞음."""
    pi = pub_info(pub)
    cA, dA, gA = sample_A(pi['unseen'], base + 1, n_hand)
    resA = summarize(cA, pi['hs'], tw) if len(cA) else None
    cP, dP, gP, infP = sample_P(obs, pi['unseen'], base + 2)
    resP = summarize(cP, pi['hs'], tw) if cP is not None else None
    a_suit = resA['0.0']['ps'] if resA else [0.25] * 4
    F = s_features(pub, pi, a_suit)
    return dict(A=resA, P=resP, P_info=infP, F=F, A_acc=[gA, dA], P_acc=[gP, dP], cA=cA, cP=cP)


def assign(rec, hp):
    rng = np.random.default_rng(zlib.crc32(f'{rec["id"]}|{rec["round"]}|{rec["seat"]}|habit'.encode()))
    f = hp['freq']
    habit = HABITS[rng.choice(3, p=[f[h] for h in HABITS])]
    ki = hp['key_idx'][int(rng.integers(len(hp['key_idx'])))]
    return habit, ki, int(rng.integers(2 ** 31))


def run_riichi(args):
    rec, hp = args
    t0 = time.time()
    habit, ki, sseed = assign(rec, hp)
    phys, types = simulate(rec['hid'], habit, ki, hp['habits'], np.random.default_rng(sseed))
    rev = {}
    for t in phys['turns']:
        rev[t['disc']] = types[t['disc']]
    obs = make_obs(phys, rev)
    # 검사: 흉내 끝 줄 = 정답 손패
    assert sorted(types[v] for v in obs['cur']) == sorted(ttype(c) for c in rec['hid']['hand'])
    pi = pub_info(rec['pub'])
    tw = rec['hid']['waits']
    base = zlib.crc32(f'{rec["id"]}|{rec["round"]}|{rec["seat"]}'.encode())
    res = infer_all(obs, rec['pub'], tw, base)
    resA, resP, infP, F = res['A'], res['P'], res['P_info'], res['F']
    gA, dA, gP, dP = res['A_acc'] + res['P_acc']
    # 정답 줄이 P 가정(표시 패 빼고 정렬, 습관 키에서)을 만족하나 — 채점 쪽 진단
    R = RANK[ki]
    st = p_structs(obs)
    fl = set(obs['flags'])
    cc = [R[types[v]] for v in obs['cur'] if v not in fl]
    sat = (all(R[a] <= R[b] for a, b in st['rr']) and all(cc[p] >= R[t] for p, t in st['lo'])
           and all(cc[p] <= R[t] for p, t in st['hi']) and all(cc[i] <= cc[i + 1] for i in range(len(cc) - 1))
           and all(cc[i] == cc[i + 1] for i in range(len(cc) - 1) if st['eq'][i]))
    nt = len(rec['pub']['own'])
    return dict(id=rec['id'], round=rec['round'], seat=rec['seat'], habit=habit, key=key_name(ki), n_turn=nt,
                waits=tw, wsuits=sorted(set(t // 9 for t in tw)), over=pi['over'],
                A=resA, A_acc=[gA, dA], P=resP, P_acc=[gP, dP], P_info={k: v for k, v in infP.items() if k != 'post'},
                P_oracle_post=(infP.get('post') or [0] * 48)[ki], truth_in_P=bool(sat),
                n_tail_cur=len(obs['flags']), feats=F.round(5).tolist(), sec=round(time.time() - t0, 2))


# ================================================================ 실행
def load_split():
    recs = json.load(open(REC, encoding='utf-8'))
    games = sorted(set(r['id'] for r in recs))
    rng = np.random.default_rng(SPLIT_SEED)
    perm = [games[i] for i in rng.permutation(len(games))]
    dev = set(perm[:N_DEV])
    return recs, games, dev


def cmd_habits():
    hp = habit_params()
    json.dump(hp, open(os.path.join(OUT, 'habit_params.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for h, v in hp['habits'].items():
        print(h, {k: v[k] for k in ('games', 'kept', 'tail', 'last_ok', 'off', 'q_tail', 'q_off', 'tidied', 'exposure',
                                    'censored', 'tidy_hazard', 'init_out', 'init_n', 'init_mis', 'offsets')})
    print('키:', hp['keys'], '빈도:', hp['freq'])
    for g, v in hp['per_game'].items():
        print(' ', g, v)


def load_hp():
    return json.load(open(os.path.join(OUT, 'habit_params.json'), encoding='utf-8'))


def cmd_sample(split, workers, limit=None):
    hp = load_hp()
    bad, n1, n = tenpai_batch_check()
    print(f'묶음 텐파이 판정 == fast_waits: 어긋남 {bad}/{n} (텐파이 {n1})', flush=True)
    assert bad == 0
    recs, games, dev = load_split()
    sel = [r for r in recs if (r['id'] in dev) == (split == 'dev')]
    if limit:
        sel = sel[:limit]
    fp = os.path.join(OUT, f'riichi_{split}.jsonl')
    done = set()
    if os.path.exists(fp):
        for line in open(fp, encoding='utf-8'):
            d = json.loads(line)
            done.add((d['id'], d['round'], d['seat']))
    todo = [r for r in sel if (r['id'], r['round'], r['seat']) not in done]
    print(f'{split}: 판 {len(set(r["id"] for r in sel))}, 리치 {len(sel)}, 남은 것 {len(todo)}', flush=True)
    t0 = time.time()
    with open(fp, 'a', encoding='utf-8') as f, ProcessPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(run_riichi, [(r, hp) for r in todo], chunksize=4)):
            f.write(json.dumps(res, ensure_ascii=False) + '\n')
            if i % 100 == 0:
                f.flush()
                print(f'  {i + 1}/{len(todo)} {time.time() - t0:.0f}s', flush=True)
    print(f'끝 {time.time() - t0:.0f}s', flush=True)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1]
    if cmd == 'habits':
        cmd_habits()
    elif cmd == 'sample':
        lim = int(sys.argv[3]) if len(sys.argv) > 3 else None
        cmd_sample(sys.argv[2], max(1, (os.cpu_count() or 2) - 2), lim)
    elif cmd == 'leak':
        import waitsuit_eval as E
        E.cmd_leak()
    elif cmd == 'real':
        import waitsuit_eval as E
        E.cmd_real()
    elif cmd == 'real2':
        import waitsuit_eval as E
        E.cmd_real_hanchan2()
    elif cmd == 'report':
        import waitsuit_eval as E
        E.cmd_report(dev_only=len(sys.argv) > 2 and sys.argv[2] == 'dev')
    elif cmd == 'example':
        import waitsuit_eval as E
        E.cmd_example(sys.argv[2] if len(sys.argv) > 2 else 'H2', int(sys.argv[3]) if len(sys.argv) > 3 else 0)


if __name__ == '__main__':
    main()
