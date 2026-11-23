"""패 위치(칸 번호)로 손패 추정 — hero 손패로 먼저 재기 (계획서 docs/hand_infer_plan_1120.md).

외부 API 없음, 순수 계산. 다시 돌리기:
    python experiments/paifu_frames/handinfer/posinfer.py            # 전체(격자 · LOGO · 표)
    python experiments/paifu_frames/handinfer/posinfer.py --tiebreak right   # 중복 패 대응을 반대로 골라 민감도

구조(누설 막기):
  build_observation(paifu)  hero 줄(정답)에서 "칸 ↔ 미지수 번호" 만 뽑는다. 내보내는 것은 미지수 번호 줄 ·
                            버린/울기로 나간 미지수와 그 공개 패 · k · j · 쯔모기리뿐. 패 종류는 공개된 것만.
  build_public(paifu, e)    사건 e 까지의 공개 정보: 네 자리 강 · 울기 · 도라 표시패, hero 버림과 쯔모기리 표시.
                            hero 의 hand · draw.tile 을 읽지 않는다.
  infer(obs_t, pub_t, ...)  위 두 개만 받는다(시점 t 까지 잘라 준 것). 깁스 표본.
  evaluate                  정답(hero hand)은 여기서만 읽는다.
"""
import argparse
import itertools
import json
import math
import os
import sys
import time
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PAIFU_DIR = os.path.join(ROOT, 'assets', 'paifu')
OUT_DIR = os.path.join(ROOT, 'experiments', 'paifu_frames', 'results', 'handinfer')
GAMES = ['L16_135321', 'r11_130921', 'r12_131655', 'r13_132644',
         'r15_134151', 'r16_135321', 'r17_140450', 'r19_142013']

BETAS = [0.25, 0.5, 1.0, 2.0, 4.0]
GAMMAS = [0.1, 0.25, 0.5, 1.0, 2.0]
CHAINS = 2
BURN = 200
KEEP = 300          # 사슬마다 → 표본 600

SUITS = 'mpsz'


# ---------------------------------------------------------------- 패 번호
def tid(code):
    if code[0] == 'X':              # 누설 검사용 가짜 패(서로 다른 이름)
        return 100 + int(code[1:])
    n = int(code[0])
    if n == 0:
        n = 5                       # 적5 는 5
    s = SUITS.index(code[1])
    return s * 9 + n - 1


def tname(t):
    if t >= 100:
        return f'X{t - 100}'
    return f'{t % 9 + 1}{SUITS[t // 9]}'


def suit_of(t):
    return t // 9


# ---------------------------------------------------------------- 관찰 만들기
def _lcs_map(rem_types, new_types, right):
    """rem(남은 미지수들의 종류) 와 new 줄의 최장 공통 부분열. 반환: new 칸 i → rem 번호(맞춘 것만), 길이."""
    a, b = rem_types, new_types
    if right:
        a, b = a[::-1], b[::-1]
    n, m = len(a), len(b)
    L = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            L[i][j] = L[i + 1][j + 1] + 1 if a[i] == b[j] else max(L[i + 1][j], L[i][j + 1])
    i = j = 0
    pairs = []
    while i < n and j < m:
        if a[i] == b[j] and L[i][j] == L[i + 1][j + 1] + 1:
            pairs.append((i, j)); i += 1; j += 1
        elif L[i + 1][j] >= L[i][j + 1]:
            i += 1
        else:
            j += 1
    if right:
        pairs = [(n - 1 - x, m - 1 - y) for x, y in pairs]
    return {y: x for x, y in pairs}, L[0][0]


def decode_transition(old, remove_types, new_types, must_remove=None, must_keep=None,
                      prefer_remove=None, right=False):
    """old: [(var, type)]. remove_types: 나간 패 종류들(공개). new_types: 새 줄(정답 종류).
    나간 미지수 고르기 × 남은 것의 새 칸 대응을 '가장 적게 움직인'(LCS 최대) 것으로 정한다.
    반환: (나간 old 번호들, new 칸별 var 줄, 움직인 var 들)."""
    cand_lists = []
    for rt in sorted(set(remove_types)):
        idx = [i for i, (_, t) in enumerate(old) if t == rt]
        cand_lists.append(list(itertools.combinations(idx, remove_types.count(rt))))
    best = None
    for combo in itertools.product(*cand_lists):
        rm = tuple(sorted(i for c in combo for i in c))
        if must_remove is not None and must_remove not in rm:
            continue
        if must_keep is not None and must_keep in rm:
            continue
        rem = [old[i] for i in range(len(old)) if i not in rm]
        if len(rem) != len(new_types):
            continue
        mp, score = _lcs_map([t for _, t in rem], new_types, right)
        # 나머지는 종류별로 차례대로 짝짓기
        used = set(mp.values())
        free_rem = [x for x in range(len(rem)) if x not in used]
        if right:
            free_rem = free_rem[::-1]
        slots = [y for y in range(len(new_types)) if y not in mp]
        if right:
            slots = slots[::-1]
        ok = True
        for y in slots:
            pick = next((x for x in free_rem if rem[x][1] == new_types[y]), None)
            if pick is None:
                ok = False
                break
            free_rem.remove(pick)
            mp[y] = pick
        if not ok:
            continue
        pref = 1 if (prefer_remove is not None and prefer_remove in rm) else 0
        tb = tuple(-i for i in rm) if right else rm
        key = (score, pref, tuple(-x for x in tb))
        if best is None or key > best[0]:
            row = [rem[mp[y]][0] for y in range(len(new_types))]
            moved = [rem[mp[y]][0] for y in slots]
            best = (key, rm, row, moved)
    if best is None:
        raise ValueError('줄 변화를 설명할 수 없음')
    return best[1], best[2], best[3]


def build_observation(paifu, right=False):
    """hero 줄에서 칸 ↔ 미지수 대응만 뽑는다. 내보내는 obs 에 숨은 패 종류는 없다.
    obs['steps'][i]: ev(사건 번호) · kind(start/turn/call) · row(미지수 번호 줄) · reveal{var: 공개 패} ·
                     drawn(뽑은 미지수 또는 None) · tsumogiri · k · j · moved(k·j 밖으로 움직인 미지수)."""
    hero = paifu['hero']
    cur = None                       # [(var, type)] — type 은 대응 찾기에만 쓰고 obs 로 내보내지 않음
    nvar = 0
    steps = []
    drawn = None
    truth_types = {}                 # 자체 검사 용(밖으로 내보내지만 infer 에는 안 넘김)
    for e_i, e in enumerate(paifu['events']):
        if e.get('seat') != hero:
            continue
        hand = e.get('hand')
        if e['type'] == 'draw':
            if hand is None:
                if cur is not None:
                    raise ValueError('손패 줄이 중간에 끊김')
                continue
            ht = [tid(x) for x in hand]
            if cur is None:
                cur = []
                for t in ht:
                    cur.append((nvar, t)); truth_types[nvar] = t; nvar += 1
                steps.append(dict(ev=e_i, kind='start', row=[v for v, _ in cur], reveal={}, drawn=None))
            elif [t for _, t in cur] != ht:
                raise ValueError(f'뽑기 전 줄이 앞 줄과 다름 ev{e_i}')
            drawn = (nvar, tid(e['tile'])); truth_types[nvar] = drawn[1]; nvar += 1
        elif e['type'] == 'discard':
            if hand is None:
                if cur is not None:
                    raise ValueError('손패 줄이 중간에 끊김')
                continue
            dt = tid(e['tile'])
            old = list(cur) + ([drawn] if drawn is not None else [])
            ts = e.get('tsumogiri')
            di = len(cur) if drawn is not None else None
            rm, row, moved = decode_transition(
                old, [dt], [tid(x) for x in hand],
                must_remove=di if ts is True else None,
                must_keep=di if ts is False else None,
                prefer_remove=di if ts is None else None, right=right)
            dvar = old[rm[0]][0]
            k = rm[0] + 1 if rm[0] != di else None     # 뽑은 패를 버렸으면 k 없음(쯔모기리)
            j = None
            if drawn is not None and drawn[0] in row:
                # j: 뽑은 패가 선 자리를 '버리기 전 번호' 로(빈칸도 한 칸)
                pos = row.index(drawn[0])
                left = row[pos - 1] if pos > 0 else None
                j = 1 if left is None else [v for v, _ in old].index(left) + 2
            steps.append(dict(ev=e_i, kind='turn', row=row, reveal={dvar: e['tile']},
                              drawn=drawn[0] if drawn is not None else None,
                              tsumogiri=(dvar == (drawn[0] if drawn else None)),
                              tsumogiri_given=ts, k=k, j=j,
                              moved=[v for v in moved if v != (drawn[0] if drawn else None)],
                              riichi=bool(e.get('riichi'))))
            cur = [(v, truth_types[v]) for v in row]
            drawn = None
        elif e['type'] == 'call':
            if hand is None:
                continue
            ht = [tid(x) for x in hand]
            if cur is None:
                cur = []
                for t in ht:
                    cur.append((nvar, t)); truth_types[nvar] = t; nvar += 1
                steps.append(dict(ev=e_i, kind='start', row=[v for v, _ in cur], reveal={}, drawn=None,
                                  note='울기 직후 줄이 첫 줄(울기 전 줄 모름)'))
            else:
                mt = [tid(x) for x in e['tiles']]
                mt.remove(tid(e['tiles'][0]))       # 가져온 한 장은 강에서 옴(첫 칸으로 가정)
                rm, row, moved = decode_transition(list(cur), mt, ht, right=right)
                steps.append(dict(ev=e_i, kind='call', row=row,
                                  reveal={cur[i][0]: tname(cur[i][1]) for i in rm},
                                  meld_pos=[i + 1 for i in rm], drawn=None, moved=moved))
                cur = [(v, truth_types[v]) for v in row]
    obs = dict(game=paifu['id'], hero=hero, steps=steps, nvar=nvar)
    return obs, truth_types


def self_check(paifu, obs, truth_types):
    """관찰(미지수 줄)과 정답 종류 대응으로 줄을 다시 만들어 원래 줄과 같은지. 공개된 reveal 이 정답과 같은지."""
    hero = paifu['hero']
    n = 0
    for st in obs['steps']:
        e = paifu['events'][st['ev']]
        rebuilt = [tname(truth_types[v]) for v in st['row']]
        want = [tname(tid(x)) for x in e['hand']]
        assert e['seat'] == hero and rebuilt == want, (st['ev'], rebuilt, want)
        for v, t in st['reveal'].items():
            assert truth_types[v] == tid(t)
        n += 1
    # obs 안의 패 글자는 공개 패(강 · 울기)뿐인지
    pub = set()
    for e in paifu['events']:
        if e['type'] == 'discard':
            pub.add(tname(tid(e['tile'])))
        if e['type'] == 'call':
            pub.update(tname(tid(x)) for x in e['tiles'])
    for st in obs['steps']:
        for t in st['reveal'].values():
            assert tname(tid(t)) in pub
    return n


def obs_upto(obs, step_i):
    """시점(step_i 까지)의 관찰만. 줄은 연이어 같은 것 하나로."""
    rows, reveal = [], {}
    for st in obs['steps'][:step_i + 1]:
        if not rows or rows[-1] != st['row']:
            rows.append(list(st['row']))
        reveal.update({v: tid(t) for v, t in st['reveal'].items()})
    return dict(rows=rows, reveal=reveal, cur=list(obs['steps'][step_i]['row']))


# ---------------------------------------------------------------- 공개 정보
def build_public(paifu, upto_ev):
    hero = paifu['hero']
    vis = np.zeros(34, int)
    for x in paifu.get('dora_indicators') or []:
        vis[tid(x)] += 1
    hero_disc = []
    riichi_done = False
    for e_i, e in enumerate(paifu['events'][:upto_ev + 1]):
        if e['type'] == 'discard':
            vis[tid(e['tile'])] += 1
            if e['seat'] == hero:
                hero_disc.append(dict(tile=tid(e['tile']), tsumogiri=e.get('tsumogiri'),
                                      after_riichi=riichi_done))
                if e.get('riichi'):
                    riichi_done = True
        elif e['type'] == 'call':
            ts = [tid(x) for x in e['tiles']]
            ts.remove(tid(e['tiles'][0]))         # 가져온 패는 이미 강에서 셈
            for t in ts:
                vis[t] += 1
    unseen = 4 - vis
    over = [tname(t) for t in range(34) if unseen[t] < 0]
    return dict(unseen=np.maximum(unseen, 0), over=over, hero_disc=hero_disc)


# ---------------------------------------------------------------- 정렬 키 · 휴리스틱
KEYS = [(perm, asc) for perm in itertools.permutations(range(4)) for asc in (True, False)]


def _rank_table():
    R = np.zeros((len(KEYS), 34))
    for ki, (perm, asc) in enumerate(KEYS):
        for t in range(34):
            s = suit_of(t)
            pos = perm.index(s)
            num = t % 9 + 1
            within = 0 if s == 3 else (num if asc else 10 - num)   # 자패 안 순서는 안 봄
            R[ki, t] = pos * 10 + within
    return R


RANK = _rank_table()


def heuristic_score(hero_disc):
    """B: hero 버림이 많은 수트 · 근처 패일수록 덜 든다. s(t) = Σ w_d · sim(d, t)."""
    s = np.zeros(34)
    for d in hero_disc:
        w = 0.3 if d['tsumogiri'] is True else 1.0
        dt = d['tile']
        for t in range(34):
            if suit_of(t) != suit_of(dt):
                continue
            if suit_of(t) == 3:
                s[t] += w * (1.0 if t == dt else 0.2)
            else:
                dd = abs(t - dt)
                s[t] += w * (1.0 if dd == 0 else 0.7 if dd <= 2 else 0.2)
    return s


# ---------------------------------------------------------------- 추정(깁스)
START_TRIES = 2_000_000


def tenpai_start(pool, nU, rng):
    """텐파이 출발점: 남은 패 더미(A 사전)에서 13장을 고르게 뽑아 텐파이가 나올 때까지 거부. 반환 (패 줄, 뽑은 횟수)."""
    for tries in range(1, START_TRIES + 1):
        pick = pool[rng.choice(len(pool), size=nU, replace=False)]
        if is_tenpai(tuple(int(x) for x in np.bincount(pick, minlength=34))):
            return pick, tries
    raise RuntimeError('텐파이 출발점을 못 찾음')


def infer(o, pub, beta, gamma, seed, chains=CHAINS, burn=BURN, keep=KEEP, tenpai=False):
    """o: obs_upto 결과, pub: build_public 결과. 반환 samples[S, len(cur)] (패 번호), key 사후 분포, 정보.
    tenpai=True(리치 선언 차례): 상태를 텐파이 집합 안에 묶는 제한 깁스 — 출발점은 남은 패 더미에서 거부 표본으로
    텐파이를 하나 얻고, 칸마다 '그 값으로 바꿔도 텐파이' 인 값들 안에서만 조건부 분포로 뽑는다(목표 분포 =
    해당 조건의 사후 × 1[텐파이], 상태 공간이 칸 하나 바꾸기로 이어져 있다는 가정 — 서로 다른 표본 수를 적어 둔다)."""
    rng = np.random.default_rng(seed)
    cur = o['cur']
    U = list(cur)
    uidx = {v: i for i, v in enumerate(U)}
    allv = sorted(set(v for r in o['rows'] for v in r) | set(o['reveal']))
    for v in U:
        assert v not in o['reveal']
    gidx = {v: i for i, v in enumerate(allv)}
    T = np.zeros(len(allv), int)
    for v, t in o['reveal'].items():
        if v in gidx:
            T[gidx[v]] = t
    # 이웃 짝 모으기(줄마다)
    pc = Counter()
    if beta > 0:
        for r in o['rows']:
            for a, b in zip(r, r[1:]):
                if a in gidx and b in gidx:   # 아는 패끼리 짝도 키 추정에 씀
                    pc[(gidx[a], gidx[b])] += 1
    pa = np.array([p[0] for p in pc], int)
    pb = np.array([p[1] for p in pc], int)
    pm = np.array([pc[p] for p in pc], float)
    left_of = {i: [] for i in range(len(U))}    # v 가 오른쪽: (왼쪽 짝, 횟수)
    right_of = {i: [] for i in range(len(U))}   # v 가 왼쪽: (오른쪽 짝, 횟수)
    for (a, b), m in pc.items():
        va, vb = allv[a], allv[b]
        if vb in uidx:
            left_of[uidx[vb]].append((a, m))
        if va in uidx:
            right_of[uidx[va]].append((b, m))
    lo = {i: (np.array([x for x, _ in l], int), np.array([m for _, m in l], float)) for i, l in left_of.items()}
    ro = {i: (np.array([x for x, _ in l], int), np.array([m for _, m in l], float)) for i, l in right_of.items()}
    ug = np.array([gidx[v] for v in U], int)
    unseen = pub['unseen'].astype(float)
    logB = -gamma * heuristic_score(pub['hero_disc']) if gamma > 0 else np.zeros(34)
    out = []
    keycount = np.zeros(len(KEYS))
    nU = len(U)
    info = dict(start_tries=[])
    if tenpai:
        assert nU == 13, '텐파이 제한은 울기 없는 13장만'
    for c in range(chains):
        # 처음: 남은 패에서 뽑기(휴리스틱 무게 포함 아님), 키는 고르게
        pool = np.repeat(np.arange(34), pub['unseen'])
        if tenpai:
            T[ug], tries = tenpai_start(pool, nU, rng)
            info['start_tries'].append(tries)
        else:
            pick = rng.choice(len(pool), size=nU, replace=False)
            T[ug] = pool[pick]
        cnt = np.bincount(T[ug], minlength=34).astype(float)
        key = rng.integers(len(KEYS))
        for sweep in range(burn + keep):
            Rk = RANK[key]
            for i in range(nU):
                g = ug[i]
                cnt[T[g]] -= 1
                lw = np.log(np.maximum(unseen - cnt, 0) + 1e-300) + logB
                if tenpai:
                    okm = tenpai_moves(tuple(int(x) for x in cnt))
                    assert okm[T[g]]
                    lw = np.where(okm, lw, -np.inf)
                if beta > 0:
                    e = np.zeros(34)
                    la, lm = lo[i]
                    if len(la):
                        e += ((Rk[T[la]][:, None] > Rk[None, :]) * lm[:, None]).sum(0)
                    rb, rm_ = ro[i]
                    if len(rb):
                        e += ((Rk[None, :] > Rk[T[rb]][:, None]) * rm_[:, None]).sum(0)
                    lw = lw - beta * e
                lw -= lw.max()
                p = np.exp(lw); p /= p.sum()
                t = rng.choice(34, p=p)
                T[g] = t
                cnt[t] += 1
            if beta > 0 and len(pa):
                E = ((RANK[:, T[pa]] > RANK[:, T[pb]]) * pm[None, :]).sum(1)
                lk = -beta * E
                lk -= lk.max()
                pk = np.exp(lk); pk /= pk.sum()
                key = rng.choice(len(KEYS), p=pk)
            else:
                key = rng.integers(len(KEYS))
            if sweep >= burn:
                out.append(T[ug].copy())
                keycount[key] += 1
    out = np.array(out)
    if tenpai:
        info['distinct'] = len(set(tuple(np.bincount(s, minlength=34)) for s in out))
        info['all_tenpai'] = all(is_tenpai(tuple(int(x) for x in np.bincount(s, minlength=34))) for s in out)
    return out, keycount / keycount.sum(), info


# ---------------------------------------------------------------- 대기 계산
@lru_cache(maxsize=None)
def _std_complete(c, need_pair):
    i = next((x for x in range(34) if c[x]), None)
    if i is None:
        return not need_pair
    lst = list(c)
    if need_pair and lst[i] >= 2:
        lst[i] -= 2
        if _std_complete(tuple(lst), False):
            return True
        lst[i] += 2
    if lst[i] >= 3:
        lst[i] -= 3
        if _std_complete(tuple(lst), need_pair):
            return True
        lst[i] += 3
    if i < 27 and i % 9 <= 6 and lst[i + 1] and lst[i + 2]:
        lst[i] -= 1; lst[i + 1] -= 1; lst[i + 2] -= 1
        if _std_complete(tuple(lst), need_pair):
            return True
    return False


YAO = [0, 8, 9, 17, 18, 26] + list(range(27, 34))


def complete(c):
    if sum(c) == 14:
        if all(x in (0, 2) for x in c) and sum(1 for x in c if x == 2) == 7:
            return True
        if all(c[t] >= 1 for t in YAO) and sum(c[t] for t in YAO) == 14:
            return True
    return _std_complete(tuple(c), True)


@lru_cache(maxsize=200000)
def waits(c):
    """c: 손패 장수(34). 울기 있으면 장수가 적다(면자 수만큼 줄여 셈). 기준 구현(느림, 채점용)."""
    res = []
    lst = list(c)
    for t in range(34):
        if lst[t] >= 4:
            continue
        lst[t] += 1
        if complete(tuple(lst)) if sum(lst) == 14 else _std_complete(tuple(lst), True):
            res.append(t)
        lst[t] -= 1
    return tuple(res)


# 빠른 텐파이 판정(13장 · 울기 없음 전용). waits() 와 같은 정의(4장 든 종류는 대기 아님 · 치또이 · 국사 포함)를
# 수트별로 나눠 계산한다. fast_check() 로 waits() 와 같은지 무작위 손패로 확인한다.
@lru_cache(maxsize=None)
def _dec(c, need_pair, honor):
    i = next((x for x in range(len(c)) if c[x]), None)
    if i is None:
        return not need_pair
    lst = list(c)
    if need_pair and lst[i] >= 2:
        lst[i] -= 2
        if _dec(tuple(lst), False, honor):
            return True
        lst[i] += 2
    if lst[i] >= 3:
        lst[i] -= 3
        if _dec(tuple(lst), need_pair, honor):
            return True
        lst[i] += 3
    if not honor and i <= 6 and lst[i + 1] and lst[i + 2]:
        lst[i] -= 1; lst[i + 1] -= 1; lst[i + 2] -= 1
        if _dec(tuple(lst), need_pair, honor):
            return True
    return False


@lru_cache(maxsize=None)
def _sflag(c, honor):
    """수트 하나: 0 = 면자만으로 됨, 2 = 면자 + 머리로 됨, None = 안 됨."""
    m = sum(c) % 3
    if m == 1:
        return None
    return m if _dec(c, m == 2, honor) else None


def fast_waits(c):
    c = list(c)
    sl = [tuple(c[0:9]), tuple(c[9:18]), tuple(c[18:27]), tuple(c[27:34])]
    fl = [_sflag(sl[k], k == 3) for k in range(4)]
    n2 = sum(1 for k in range(4) if fl[k] == 2)
    pairs = sum(1 for x in c if x == 2)
    chiitoi_ok = pairs == 6 and sum(1 for x in c if x == 1) == 1 and all(x in (0, 1, 2) for x in c)
    koku_ok = sum(c[t] for t in YAO) == 13 and all(c[t] <= 2 for t in YAO)
    res = []
    for t in range(34):
        if c[t] >= 4:
            continue
        s = t // 9
        nt = list(sl[s]); nt[t - 9 * s] += 1
        f = _sflag(tuple(nt), s == 3)
        ok = f is not None and all(fl[k] is not None for k in range(4) if k != s)
        if ok:
            ok = (n2 - (fl[s] == 2) + (f == 2)) == 1
        if not ok and chiitoi_ok and c[t] == 1:
            ok = True
        if not ok and koku_ok and t in YAO:
            c[t] += 1
            ok = all(c[y] >= 1 for y in YAO)
            c[t] -= 1
        if ok:
            res.append(t)
    return tuple(res)


@lru_cache(maxsize=400000)
def is_tenpai(c):
    return bool(fast_waits(c))


_SUIT_RANGES = [(0, 9), (9, 18), (18, 27), (27, 34)]


@lru_cache(maxsize=300000)
def tenpai_moves(c12):
    """12장 장수 c12 에 한 장 t 를 더했을 때 텐파이가 되는 t (34 bool).
    13장 c12+t 가 텐파이 ⟺ 어떤 w 로 c12+t+w(14장, 종류마다 ≤4)가 화료형. 표준형은 수트별로 나눠
    (t·w 가 다른 수트 / 같은 수트) 수트 판정만 조합하고, 치또이 · 국사는 따로. tenpai_moves_ref 와 같은지 확인함."""
    c = list(c12)
    sl = [tuple(c[a:b]) for a, b in _SUIT_RANGES]
    base = [_sflag(sl[k], k == 3) for k in range(4)]
    p1 = [None] * 34
    avail = [set() for _ in range(4)]
    for t in range(34):
        if c[t] >= 4:
            continue
        s = t // 9
        nt = list(sl[s]); nt[t - 9 * s] += 1
        p1[t] = _sflag(tuple(nt), s == 3)
        if p1[t] is not None:
            avail[s].add(p1[t])
    out = np.zeros(34, bool)
    for t in range(34):
        if c[t] >= 4:
            continue
        s1 = t // 9
        ok = False
        # (1) w 가 다른 수트 s2
        if p1[t] is not None:
            for s2 in range(4):
                if s2 == s1:
                    continue
                rest = [base[k] for k in range(4) if k not in (s1, s2)]
                if any(x is None for x in rest):
                    continue
                n2r = sum(1 for x in rest if x == 2) + (p1[t] == 2)
                if any(n2r + (b == 2) == 1 for b in avail[s2]):
                    ok = True
                    break
        # (2) w 가 같은 수트
        if not ok and all(base[k] is not None for k in range(4) if k != s1):
            n2r = sum(1 for k in range(4) if k != s1 and base[k] == 2)
            a, b = _SUIT_RANGES[s1]
            x = t - a
            for y in range(b - a):
                nt = list(sl[s1]); nt[x] += 1; nt[y] += 1
                if nt[y] > 4:
                    continue
                f = _sflag(tuple(nt), s1 == 3)
                if f is not None and n2r + (f == 2) == 1:
                    ok = True
                    break
        if not ok:
            c[t] += 1
            # 치또이: 13장이 6 쌍 + 1 장(모두 ≤2)
            if sum(1 for v in c if v == 2) == 6 and sum(1 for v in c if v == 1) == 1 and max(c) <= 2:
                ok = True
            # 국사: 13장이 모두 요구패, 서로 다른 요구패 ≥ 12
            elif sum(c[y] for y in YAO) == 13 and sum(1 for y in YAO if c[y]) >= 12:
                ok = True
            c[t] -= 1
        out[t] = ok
    return out


def tenpai_moves_ref(c12):
    """기준(느림): 34 가지 t 마다 is_tenpai."""
    out = np.zeros(34, bool)
    lst = list(c12)
    for t in range(34):
        if lst[t] >= 4:
            continue
        lst[t] += 1
        out[t] = is_tenpai(tuple(lst))
        lst[t] -= 1
    return out


def fast_check(n=20000, seed=1):
    """fast_waits == waits 확인: 무작위 13장(벽에서) 과 텐파이에 가까운 손패(완성형 14장에서 한 장 뺌)."""
    rng = np.random.default_rng(seed)
    pool = np.repeat(np.arange(34), 4)
    bad = 0
    for i in range(n):
        if i % 2 == 0:
            h = rng.choice(pool, 13, replace=False)
            c = tuple(int(x) for x in np.bincount(h, minlength=34))
        else:   # 완성형 근처: 무작위 면자 4 + 머리 → 한 장 빼고 한 장 바꿈
            cc = np.zeros(34, int)
            while True:
                cc[:] = 0
                for _ in range(4):
                    if rng.random() < 0.5:
                        t = rng.integers(34); cc[t] += 3
                    else:
                        s = rng.integers(3); x = rng.integers(7); cc[s * 9 + x:s * 9 + x + 3] += 1
                cc[rng.integers(34)] += 2
                if cc.max() <= 4:
                    break
            nz = np.flatnonzero(cc); cc[rng.choice(nz)] -= 1
            if rng.random() < 0.5:
                nz = np.flatnonzero(cc); cc[rng.choice(nz)] -= 1
                t = rng.integers(34)
                if cc[t] < 4:
                    cc[t] += 1
                else:
                    cc[nz[0]] += 1
            c = tuple(int(x) for x in cc)
        if fast_waits(c) != waits(c):
            bad += 1
        # tenpai_moves: 13장에서 한 장 뺀 12장으로, 빠른 판정 == 34 가지 다 해 보기
        if i % 10 == 0:
            cl = list(c); nz = [t for t in range(34) if cl[t]]; cl[nz[int(rng.integers(len(nz)))]] -= 1
            c12 = tuple(cl)
            if not np.array_equal(tenpai_moves(c12), tenpai_moves_ref(c12)):
                bad += 1
    return bad


# ---------------------------------------------------------------- 지표
def summarize(samples, n_hand, unseen):
    S = len(samples)
    cnts = np.zeros((S, 34), int)
    for s in range(S):
        cnts[s] = np.bincount(samples[s], minlength=34)
    return summarize_cnts(cnts, unseen)


def summarize_cnts(cnts, unseen):
    S = len(cnts)
    pge = np.stack([(cnts >= m).mean(0) for m in range(1, 5)], 1)     # P(X_t ≥ m)
    suit_exp = np.array([cnts[:, k * 9:(k + 1) * 9].sum(1).mean() for k in range(4)])
    p1 = ((cnts >= 1).sum(0) + 0.5) / (S + 1)
    p1 = np.where(unseen > 0, p1, 0.0)
    return dict(pge=pge, suit=suit_exp, p1=p1, cnts=cnts)


def top_pick(pge, n):
    vals = [(pge[t, m], -t, -m, t) for t in range(34) for m in range(4)]
    vals.sort(reverse=True)
    pick = np.zeros(34, int)
    for v in vals[:n]:
        pick[v[3]] += 1
    return pick


def metrics(sm, truth_cnt, n_hand):
    pick = top_pick(sm['pge'], n_hand)
    hit = int(np.minimum(pick, truth_cnt).sum())
    ts = np.array([truth_cnt[k * 9:(k + 1) * 9].sum() for k in range(4)])
    suit_err = float(np.abs(sm['suit'] - ts).sum())
    y = truth_cnt >= 1
    p = sm['p1']
    with np.errstate(divide='ignore'):
        ll = np.where(y, np.log(np.maximum(p, 1e-6)), np.log(np.maximum(1 - p, 1e-6)))
    return dict(hit=hit, suit_err=suit_err, logs=float(ll.mean()))


def wait_rank(cnts, true_waits):
    S = len(cnts)
    ratio = np.zeros(34)
    ntenpai = 0
    for s in range(S):
        w = waits(tuple(int(x) for x in cnts[s]))
        if w:
            ntenpai += 1
            for t in w:
                ratio[t] += 1
    ratio /= S
    best = None
    for t in true_waits:
        r = 1 + (ratio > ratio[t]).sum() + ((ratio == ratio[t]).sum() - 1) / 2
        best = r if best is None else min(best, r)
    return float(best), ntenpai


def sortedness(paifu):
    """지표 5: 그 사람의 줄들(같은 줄 하나로)에서 가장 맞는 키로 이웃 짝 중 순서 맞는 비율."""
    rows = []
    for e in paifu['events']:
        if e.get('seat') == paifu['hero'] and e.get('hand'):
            r = [tid(x) for x in e['hand']]
            if not rows or rows[-1] != r:
                rows.append(r)
    best = (0, None)
    for ki in range(len(KEYS)):
        ok = tot = 0
        for r in rows:
            for a, b in zip(r, r[1:]):
                tot += 1
                ok += RANK[ki, a] <= RANK[ki, b]
        if ok / tot > best[0]:
            best = (ok / tot, ki)
    return best[0], key_name(best[1]), best[1]


def key_name(ki):
    perm, asc = KEYS[ki]
    return ''.join(SUITS[p] for p in perm) + ('↑' if asc else '↓')


# ---------------------------------------------------------------- C* · C*mix: "줄은 늘 완전 정렬" 가정의 정확 계산
# 가정: 그 사람의 모든 줄(관찰된 줄 전부)은 키 순위 비내림. 자패 7종은 같은 순위(자패끼리는 아무 순서 허용).
# 관찰된 줄의 짝 제약은 셋뿐이다(줄에 있던 미지수는 지금 줄에 남았거나 공개됐다 — 쯔모기리 패는 줄에 안 들어감):
#   미지수-공개: 칸별 위 · 아래 경계.  미지수-미지수: 지금 줄 순서(비내림) + 과거 줄에서 순서가 뒤집힌 짝이면 같은 순위 강제.
#   공개-공개: 키만으로 정해짐 — 어긋나면 그 키의 우도 0(경계 검사로는 저절로 안 걸림, 따로 검사).
# 사후(멀티셋) ∝ Π C(unseen_t, c_t) × 1[제약]. 자패 묶음은 Σ Π C = C(자패 남은 수, c)(방데르몽드).
def row_constraints(o, ki, reveal_types=None):
    """반환: lo[m], hi[m], eq[m-1](칸 q 와 q+1 같은 순위 강제), rr_bad(공개-공개 어긋난 짝 수), 세부."""
    R = RANK[ki]
    rv = o['reveal'] if reveal_types is None else reveal_types
    cur = o['cur']
    m = len(cur)
    pos = {v: i for i, v in enumerate(cur)}
    lo = np.full(m, -np.inf)
    hi = np.full(m, np.inf)
    eq = np.zeros(max(m - 1, 0), bool)
    rr_bad = 0
    n_ur = n_flip = 0
    for r in o['rows']:
        for ai in range(len(r)):
            a = r[ai]
            for b in r[ai + 1:]:
                ra, rb = a in rv, b in rv
                if ra and rb:
                    rr_bad += R[rv[a]] > R[rv[b]]
                elif ra:
                    lo[pos[b]] = max(lo[pos[b]], R[rv[a]]); n_ur += 1
                elif rb:
                    hi[pos[a]] = min(hi[pos[a]], R[rv[b]]); n_ur += 1
                else:
                    if pos[a] > pos[b]:
                        eq[pos[b]:pos[a]] = True; n_flip += 1
    return lo, hi, eq, int(rr_bad), dict(n_ur=n_ur, n_flip=n_flip)


def _classes(ki):
    """키 순위 순서의 순위 묶음: [(순위, [종류...])]. 수패는 종류마다 하나, 자패 7종은 한 묶음."""
    R = RANK[ki]
    by = {}
    for t in range(34):
        by.setdefault(R[t], []).append(t)
    return [(r, by[r]) for r in sorted(by)]


def dp_table(lo, hi, eq, unseen, ki):
    """뒤에서부터: F[κ][n] = 칸 n.. 을 묶음 κ.. 로 채우는 가중 합(정수, 정확).
    choice[κ][n] = [(c, 가중)] (c 장을 이 묶음에 주는 경우)."""
    cls = _classes(ki)
    K, m = len(cls), len(lo)
    F = [[0] * (m + 1) for _ in range(K + 1)]
    F[K][m] = 1
    choice = [[None] * (m + 1) for _ in range(K)]
    for k in range(K - 1, -1, -1):
        r, types = cls[k]
        u = int(sum(unseen[t] for t in types))
        for n in range(m, -1, -1):
            opts = []
            if F[k + 1][n]:
                opts.append((0, F[k + 1][n]))
            for c in range(1, min(u, m - n) + 1):
                p = n + c - 1                     # 이 묶음의 마지막 칸
                if not (lo[p] <= r <= hi[p]):
                    break                         # 칸 p 가 안 되면 더 긴 묶음도 안 됨
                if p < m - 1 and eq[p]:
                    continue                      # 칸 p 와 p+1 은 같은 순위여야 함 → 여기서 끊을 수 없음
                w = math.comb(u, c) * F[k + 1][n + c]
                if w:
                    opts.append((c, w))
            F[k][n] = sum(w for _, w in opts)
            choice[k][n] = opts
    return F, choice, cls


def dp_sample(F, choice, cls, unseen, n, rng):
    """정확 표본 n 개(종류별 장수 [n, 34])."""
    K = len(cls)
    m = len(F[0]) - 1
    cnts = np.zeros((n, 34), int)
    state = np.zeros(n, int)
    for k in range(K):
        r, types = cls[k]
        groups = [(st, np.flatnonzero(state == st)) for st in np.unique(state)]   # 바꾸기 전에 묶음을 정해 둠
        for st, idx in groups:
            opts = choice[k][st]
            tot = F[k][st]
            cs = np.array([c for c, _ in opts])
            p = np.array([w / tot for _, w in opts], float)
            p /= p.sum()
            pick = cs[rng.choice(len(cs), size=len(idx), p=p)]
            if len(types) == 1:
                cnts[idx, types[0]] = pick
            else:
                col = np.array([unseen[t] for t in types], np.int64)
                for ii, c in zip(idx, pick):
                    if c:
                        cnts[ii, types] = rng.multivariate_hypergeometric(col, int(c))
            state[idx] = st + pick
    assert (state == m).all()
    return cnts


CSTAR_N = 1000
CSTAR_MAXDRAW = 400_000


def cstar_infer(o, pub, ki, tenpai, seed, n=CSTAR_N, maxdraw=CSTAR_MAXDRAW):
    """ki: 키 번호(C*, 오라클) 또는 None(C*mix: 48 키를 DP 우도 × 고른 사전으로 섞음).
    o · pub 은 관찰 · 공개 정보뿐, ki 만 채점 쪽(정답 줄)에서 온다.
    반환 dict(cnts[S,34] 또는 None(가정 깨짐), 정보). tenpai=True 면 DP 표본을 거부해 텐파이만 남김."""
    rng = np.random.default_rng(seed)
    unseen = pub['unseen']
    m = len(o['cur'])
    N = int(unseen.sum())
    keys = [ki] if ki is not None else list(range(len(KEYS)))
    tabs, like = {}, np.zeros(len(keys))
    info = dict(rr_bad={}, Z0={}, rr_only=0)     # rr_only: 경계 DP 로는 우도 > 0 인데 공개-공개 검사로만 0 이 된 키 수
    for i, k in enumerate(keys):
        lo, hi, eq, rr_bad, det = row_constraints(o, k)
        F, ch, cls = dp_table(lo, hi, eq, unseen, k)
        tabs[k] = (F, ch, cls)
        info['n_ur'], info['n_flip'] = det['n_ur'], det['n_flip']
        if rr_bad:
            info['rr_bad'][k] = rr_bad
        if F[0][0] == 0:
            info['Z0'][k] = True
        elif rr_bad:
            info['rr_only'] += 1
        like[i] = 0.0 if (rr_bad or F[0][0] == 0) else F[0][0] / math.comb(N, m)
    info['like'] = like.tolist() if ki is None else float(like[0])
    if like.sum() == 0:
        info['broken'] = True
        return None, info
    info['broken'] = False
    post = like / like.sum()
    if ki is None:
        info['key_post_top'] = sorted(((float(post[i]), key_name(k)) for i, k in enumerate(keys)), reverse=True)[:3]
    out, drawn = [], 0
    batch = n if not tenpai else 5000
    # 텐파이 거부: 채택 n 개 또는 maxdraw 뽑을 때까지. 그때 채택이 30 미만이면 maxdraw×10 까지 더 뽑음(표본 크게).
    while True:
        got = sum(len(x) for x in out)
        if got >= n or (not tenpai and drawn >= n):
            break
        if tenpai and drawn >= maxdraw and (got >= 30 or drawn >= 10 * maxdraw):
            break
        kk = rng.choice(len(keys), size=batch, p=post)
        cn = np.zeros((batch, 34), int)
        for i in np.unique(kk):
            idx = np.flatnonzero(kk == i)
            F, ch, cls = tabs[keys[i]]
            cn[idx] = dp_sample(F, ch, cls, unseen, len(idx), rng)
        drawn += batch
        if tenpai:
            ok = np.array([is_tenpai(tuple(int(x) for x in row)) for row in cn])
            cn = cn[ok]
        out.append(cn)
    cnts = np.concatenate(out) if out else np.zeros((0, 34), int)
    info['drawn'] = drawn
    info['accepted_total'] = int(len(cnts))
    cnts = cnts[:n]
    info['accepted'] = int(len(cnts))
    if tenpai and len(cnts) == 0:
        info['no_tenpai'] = True
        return None, info
    return cnts, info


# ---------------------------------------------------------------- 실행
def configs():
    cs = [('A', 0.0, 0.0)]
    cs += [('B', 0.0, g) for g in GAMMAS]
    cs += [('C', b, 0.0) for b in BETAS]
    cs += [('D', b, g) for b in BETAS for g in GAMMAS]
    return cs


def load(g):
    with open(os.path.join(PAIFU_DIR, g + '.json'), encoding='utf-8') as f:
        return json.load(f)


def run_turn(args):
    g, step_i, right = args
    paifu = load(g)
    obs, _ = build_observation(paifu, right=right)
    st = obs['steps'][step_i]
    o = obs_upto(obs, step_i)
    pub = build_public(paifu, st['ev'])
    tenpai = bool(st.get('riichi'))          # 리치 선언은 공개 — 관찰에서 가져옴
    # ---- 오라클 키(채점 쪽 정보): 정답 줄 전체로 sortedness() 가 고르는 키. C* 에만 넘긴다.
    so, okey_name, okey = sortedness(paifu)
    # ---- 여기부터 정답(채점용)
    e = paifu['events'][st['ev']]
    truth = np.bincount([tid(x) for x in e['hand']], minlength=34)
    n_hand = len(e['hand'])
    is_riichi = bool(e.get('riichi'))
    assert is_riichi == tenpai
    true_w = waits(tuple(int(x) for x in truth)) if is_riichi else None
    res = dict(game=g, step=step_i, ev=st['ev'], n=n_hand, riichi=is_riichi, over=pub['over'],
               truth_impossible=int((truth > pub['unseen']).sum()), k=st.get('k'), j=st.get('j'),
               moved=len(st.get('moved') or []), tsumogiri=st.get('tsumogiri'), cfg={}, info={})
    if is_riichi:
        assert true_w, '정답 리치 손패가 텐파이가 아님'
    for name, b, gm in configs():
        seed = zlib.crc32(f'{g}|{step_i}|{name}|{b}|{gm}'.encode())
        samples, keyp, inf = infer(o, pub, b, gm, seed, tenpai=tenpai)
        sm = summarize(samples, n_hand, pub['unseen'])
        m = metrics(sm, truth, n_hand)
        if is_riichi:
            m['wait_rank'], m['ntenpai'] = wait_rank(sm['cnts'], true_w)
            m['accepted'] = len(samples)
            m['start_tries'] = inf['start_tries']
            m['distinct'] = inf['distinct']
            assert inf['all_tenpai']
        res['cfg'][f'{name}|{b}|{gm}'] = m
    # ---- C*(오라클 키) · C*mix(48 키 섞기). 가정 깨짐이면 A 표본으로 대신 채점.
    A_m = res['cfg']['A|0.0|0.0']
    for name, kk in (('Cstar', okey), ('Cmix', None)):
        seed = zlib.crc32(f'{g}|{step_i}|{name}'.encode())
        cnts, inf = cstar_infer(o, pub, kk, tenpai, seed)
        if cnts is None:
            m = dict(A_m, fallback='A')
        else:
            sm = summarize_cnts(cnts, pub['unseen'])
            m = metrics(sm, truth, n_hand)
            if is_riichi:
                m['wait_rank'], m['ntenpai'] = wait_rank(sm['cnts'], true_w)
                m['distinct'] = len(set(map(tuple, cnts)))
        m['broken'] = inf['broken']
        m['no_tenpai'] = inf.get('no_tenpai', False)
        if is_riichi:
            m['accepted'] = inf.get('accepted_total', 0)
            m['drawn'] = inf.get('drawn', 0)
        res['cfg'][name] = m
        res['info'][name] = {k: v for k, v in inf.items() if k in ('rr_bad', 'n_ur', 'n_flip', 'key_post_top', 'like',
                                                                    'rr_only', 'Z0')
                             and not (k == 'like' and kk is None)}
        if name == 'Cmix':
            res['info'][name]['oracle_key_post'] = (inf['like'][okey] / sum(inf['like'])) if sum(inf['like']) else None
    # 진단(채점 쪽): 정답 손패가 C* 제약을 만족하나(지금 줄의 정답 순위가 경계 · 같은 순위 강제 · 비내림 안에 드나)
    lo, hi, eq, rr_bad, _ = row_constraints(o, okey)
    R = RANK[okey]
    tr = [R[tid(x)] for x in e['hand']]
    sat = (rr_bad == 0 and all(lo[p] <= tr[p] <= hi[p] for p in range(n_hand))
           and all(tr[p] <= tr[p + 1] for p in range(n_hand - 1))
           and all(tr[p] == tr[p + 1] for p in range(n_hand - 1) if eq[p]))
    res['truth_in_cstar'] = bool(sat)
    res['oracle_key'] = okey_name
    if is_riichi:
        res['true_waits'] = [tname(t) for t in true_w]
    return res


def leak_test(right, infer_check=True):
    """누설 검사. 시점 t 마다: t 까지 드러나지 않은 미지수에 엉뚱한 종류를 넣은 가짜 패보(사건은 t 까지 자름)를
    만들어 관찰을 다시 뽑고, obs_upto(t) 가 원래와 같은지 본다. 판마다 마지막 차례 하나는 같은 씨로 infer 를
    돌려 표본이 똑같은지도 본다(같으면 추정이 숨은 종류를 못 본다는 뜻).
    가짜는 미지수마다 다른 이름(X번호)이라 중복이 없다 — 관찰이 같으면 칸 ↔ 미지수 대응이 숨은 종류와 무관하다는 뜻."""
    out = {}
    for g in GAMES:
        paifu = load(g)
        obs, tt = build_observation(paifu, right=right)
        turns = [i for i, st in enumerate(obs['steps']) if st['kind'] == 'turn']
        same = diff = 0
        inf_same = riichi_same = None
        okey = sortedness(paifu)[2]        # 오라클 키: C* 가 정답에서 받는 유일한 값(가짜 패보에도 같은 키를 줌)
        for ti in turns:
            st_t = obs['steps'][ti]
            revealed = set()
            for st in obs['steps'][:ti + 1]:
                revealed |= set(st['reveal'])
            fake = {v: 100 + v for v in tt if v not in revealed}     # 서로 다른 가짜 이름
            ftype = lambda v: tname(fake.get(v, tt[v]))   # noqa
            p2 = json.loads(json.dumps(paifu))
            p2['events'] = p2['events'][:st_t['ev'] + 1]
            by_ev = {st['ev']: st for st in obs['steps'][:ti + 1]}
            prev_row = None
            for i, e in enumerate(p2['events']):
                if e.get('seat') != p2['hero'] or e.get('hand') is None:
                    continue
                if e['type'] == 'draw':
                    row = by_ev[i]['row'] if (i in by_ev and by_ev[i]['kind'] == 'start') else prev_row
                    e['hand'] = [ftype(v) for v in row]
                    nxt = next(s for s in obs['steps'] if s['ev'] > i and s['kind'] == 'turn')
                    e['tile'] = ftype(nxt['drawn'])
                    prev_row = row
                else:
                    e['hand'] = [ftype(v) for v in by_ev[i]['row']]
                    prev_row = by_ev[i]['row']
            try:
                obs2, _ = build_observation(p2, right=right)
                o1, o2 = obs_upto(obs, ti), obs_upto(obs2, ti)
                ok = o1 == o2
            except Exception:  # noqa
                ok = False
            same += ok
            diff += not ok
            is_r = bool(st_t.get('riichi'))
            if infer_check and ok and (ti == turns[-1] or is_r):
                pub = build_public(paifu, st_t['ev'])
                pub2 = build_public(p2, st_t['ev'])
                same_pub = all(np.array_equal(pub[k], pub2[k]) if isinstance(pub[k], np.ndarray) else pub[k] == pub2[k]
                               for k in pub)
                s1, _, _ = infer(o1, pub, 1.0, 0.5, 7, burn=20, keep=30, tenpai=is_r)
                s2, _, _ = infer(o2, pub2, 1.0, 0.5, 7, burn=20, keep=30, tenpai=is_r)
                chk = dict(pub_same=same_pub, infer=bool((s1 == s2).all()))
                for nm, kk in (('Cstar', okey), ('Cmix', None)):
                    c1, _ = cstar_infer(o1, pub, kk, is_r, 11, n=200, maxdraw=40000)
                    c2, _ = cstar_infer(o2, pub2, kk, is_r, 11, n=200, maxdraw=40000)
                    chk[nm] = (c1 is None and c2 is None) or (c1 is not None and c2 is not None
                                                             and c1.shape == c2.shape and bool((c1 == c2).all()))
                if ti == turns[-1]:
                    inf_same = chk
                if is_r:
                    riichi_same = chk
        out[g] = dict(turns=len(turns), obs_same=same, obs_diff=diff, last=inf_same, riichi=riichi_same)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument('--tiebreak', choices=['left', 'right'], default='left')
    ap.add_argument('--workers', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument('--games', default=','.join(GAMES))
    ap.add_argument('--report-only', action='store_true', help='turns_<tag>.json 에서 표만 다시 만듦')
    args = ap.parse_args()
    right = args.tiebreak == 'right'
    games = args.games.split(',')
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.report_only:
        with open(os.path.join(OUT_DIR, f'turns_{args.tiebreak}.json'), encoding='utf-8') as f:
            d = json.load(f)
        report(d['results'], d['obs_info'], games, args.tiebreak, d.get('leak'), d.get('fast_check'))
        return
    t0 = time.time()
    bad = fast_check()
    print(f'빠른 텐파이 판정 == waits(): 어긋남 {bad}/20000', flush=True)
    assert bad == 0
    # 관찰 · 자체 검사
    obs_info = {}
    tasks = []
    for g in games:
        p = load(g)
        obs, tt = build_observation(p, right=right)
        n = self_check(p, obs, tt)
        turns = [i for i, st in enumerate(obs['steps']) if st['kind'] == 'turn']
        obs_info[g] = dict(steps=n, turns=len(turns),
                           kj=[(st['ev'], st.get('k'), st.get('j'), st.get('tsumogiri'), st.get('tsumogiri_given'),
                                len(st.get('moved') or [])) for st in obs['steps'] if st['kind'] != 'start'],
                           sorted=sortedness(p))
        tasks += [(g, i, right) for i in turns if obs['steps'][i].get('riichi')]     # 무거운 리치 차례 먼저
        tasks += [(g, i, right) for i in turns if not obs['steps'][i].get('riichi')]
        with open(os.path.join(OUT_DIR, f'obs_{g}_{args.tiebreak}.json'), 'w', encoding='utf-8') as f:
            json.dump(obs, f, ensure_ascii=False)
    print(f'관찰 자체 검사 통과: {sum(v["steps"] for v in obs_info.values())} 걸음, 차례 {len(tasks)}', flush=True)
    lt = leak_test(right)
    print('누설 검사(숨은 종류 바꿔 관찰 다시 만들기):', lt, flush=True)
    results = []
    with ProcessPoolExecutor(args.workers) as ex:
        for r in ex.map(run_turn, tasks):
            results.append(r)
    print(f'표본 끝 {time.time() - t0:.0f}s', flush=True)
    with open(os.path.join(OUT_DIR, f'turns_{args.tiebreak}.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(obs_info=obs_info, leak=lt, results=results, fast_check=bad,
                       params=dict(betas=BETAS, gammas=GAMMAS, chains=CHAINS, burn=BURN, keep=KEEP,
                                   cstar_n=CSTAR_N, cstar_maxdraw=CSTAR_MAXDRAW, start_tries=START_TRIES)),
                  f, ensure_ascii=False, indent=1, default=lambda x: x.item() if hasattr(x, 'item') else str(x))
    report(results, json.loads(json.dumps(obs_info, default=lambda x: x.item() if hasattr(x, 'item') else str(x))),
           games, args.tiebreak, lt, bad)


def game_mean(results, cfg, metric, g):
    v = [r['cfg'][cfg][metric] for r in results if r['game'] == g]
    return float(np.mean(v))


def logo_pick(results, cname, games, g_out):
    cands = [f'{n}|{b}|{gm}' for n, b, gm in configs() if n == cname]
    best = None
    for c in cands:
        hit = np.mean([game_mean(results, c, 'hit', g) for g in games if g != g_out])
        ls = np.mean([game_mean(results, c, 'logs', g) for g in games if g != g_out])
        key = (round(hit, 9), round(ls, 9))
        if best is None or key > best[0]:
            best = (key, c)
    return best[1]


NAMES = ['A', 'B', 'C', 'D', 'C*', 'C*mix']


def report(results, obs_info, games, tag, leak=None, fast_bad=None):
    lines = []
    P = lines.append
    chosen = {}
    for g in games:
        chosen[g] = {'A': 'A|0.0|0.0', 'C*': 'Cstar', 'C*mix': 'Cmix'}
        for n in 'BCD':
            chosen[g][n] = logo_pick(results, n, games, g)
    P(f'# 손패 추정 결과 v2 (tiebreak={tag})\n')
    P('v2 변경: 리치 선언 차례는 모든 조건에서 텐파이 조건 표본(A~D 제한 깁스, C*·C*mix DP 표본 거부). '
      'C* = **오라클 키**(정답 줄 전체로 sortedness() 가 고른 키, 채점 쪽 정보) + "줄은 늘 완전 정렬" 가정의 정확 DP 표본. '
      'C*mix = 같은 DP 를 48 키 모두 돌려 DP 우도(÷C(남은 패, 장수)) × 고른 사전으로 섞음(정답 키 안 줌). '
      'C*·C*mix 가 "가정 깨짐"(우도 0)인 차례는 A 표본으로 대신 채점.\n')
    if fast_bad is not None:
        P(f'빠른 텐파이 판정 == waits() 확인: 무작위 20,000 손패 중 어긋남 {fast_bad}')
    if leak:
        P('누설 검사(숨은 종류를 가짜로 바꾼 패보): ' + '; '.join(
            f'{g[:3]} 관찰 같음 {v["obs_same"]}/{v["turns"]}, 마지막 차례 {v.get("last")}, 리치 차례 {v.get("riichi")}'
            for g, v in leak.items()))
    P('')
    P('LOGO 로 고른 설정(판마다): ' + '; '.join(
        f'{g[:3]} B={chosen[g]["B"]} C={chosen[g]["C"]} D={chosen[g]["D"]}' for g in games))
    P('')
    P('## 판 단위 13장 적중(판 안 차례 평균)\n')
    P('| 판 | 차례 | 장수 | 정렬 정도(오라클 키) | A | B | C | D | C*(오라클) | C*mix | 가정 깨짐 C*/C*mix | 정답이 C* 제약 안 |')
    P('|---|---|---|---|---|---|---|---|---|---|---|---|')
    tot = {n: dict(hit=[], suit=[], logs=[]) for n in NAMES}
    riichi = {n: [] for n in NAMES}
    per_game_hit = {n: {} for n in NAMES}
    sub = {}
    broken_tot = {'Cstar': 0, 'Cmix': 0}
    for g in games:
        rs = [r for r in results if r['game'] == g]
        vals = {}
        for n in NAMES:
            c = chosen[g][n]
            h = [r['cfg'][c]['hit'] for r in rs]
            s = [r['cfg'][c]['suit_err'] for r in rs]
            ls = [r['cfg'][c]['logs'] - r['cfg']['A|0.0|0.0']['logs'] for r in rs]
            wr = [r['cfg'][c]['wait_rank'] for r in rs if r['riichi']]
            vals[n] = (np.mean(h), np.mean(s), np.mean(ls), wr[0] if wr else None)
            tot[n]['hit'] += h; tot[n]['suit'] += s; tot[n]['logs'] += ls
            per_game_hit[n][g] = np.mean(h)
            if wr:
                riichi[n].append(wr[0])
        sub[g] = vals
        so, key = obs_info[g]['sorted'][:2]
        nh = sorted(set(r['n'] for r in rs))
        bs = sum(1 for r in rs if r['cfg']['Cstar']['broken'])
        bm = sum(1 for r in rs if r['cfg']['Cmix']['broken'])
        broken_tot['Cstar'] += bs; broken_tot['Cmix'] += bm
        tin = sum(1 for r in rs if r['truth_in_cstar'])
        P(f'| {g} | {len(rs)} | {"/".join(map(str, nh))} | {so:.2f} ({key}) | '
          + ' | '.join(f'{vals[n][0]:.2f}' for n in NAMES) + f' | {bs}/{bm} | {tin}/{len(rs)} |')
    nt = len(tot['A']['hit'])
    P(f'| **전체(차례 모아 평균, n={nt})** | {nt} | | | '
      + ' | '.join(f'**{np.mean(tot[n]["hit"]):.2f}**' for n in NAMES)
      + f' | {broken_tot["Cstar"]}/{broken_tot["Cmix"]} | {sum(1 for r in results if r["truth_in_cstar"])}/{nt} |')
    P('| 판 평균의 평균 | | | | ' + ' | '.join(f'{np.mean(list(per_game_hit[n].values())):.2f}' for n in NAMES) + ' | | |')
    P('')
    P('## 판 단위 수트 오차 · 로그 점수(A 대비)\n')
    P('| 판 | 수트오차 ' + '/'.join(NAMES) + ' | 로그차 ' + '/'.join(NAMES[1:]) + ' |')
    P('|---|---|---|')
    for g in games:
        v = sub[g]
        P(f'| {g} | ' + '/'.join(f'{v[n][1]:.2f}' for n in NAMES) + ' | '
          + '/'.join(f'{v[n][2]:+.3f}' for n in NAMES[1:]) + ' |')
    P('| 전체 | ' + '/'.join(f'{np.mean(tot[n]["suit"]):.2f}' for n in NAMES) + ' | '
      + '/'.join(f'{np.mean(tot[n]["logs"]):+.3f}' for n in NAMES[1:]) + ' |')
    P('')
    P('## 리치 선언 차례(텐파이 조건 표본)\n')
    P('표본: A~D 는 제한 깁스(사슬 2 × 300 = 600, 모두 텐파이; 괄호 = 서로 다른 손패 수, 출발점 거부 횟수), '
      'C*·C*mix 는 DP 정확 표본을 텐파이만 남김(채택/뽑음, 최대 %d 장 사용). 30 미만은 ⚠.\n' % CSTAR_N)
    P('| 판 | 정답 대기 | 대기 순위 ' + '/'.join(NAMES) + ' | 13장 적중 ' + '/'.join(NAMES)
      + ' | A·B·C·D 서로 다른 손패 | 출발점 거부(A) | C* 채택/뽑음 | C*mix 채택/뽑음 | C*mix 의 오라클 키 사후 |')
    P('|---|---|---|---|---|---|---|---|---|')
    for g in games:
        rr = [r for r in results if r['game'] == g and r['riichi']]
        if not rr:
            P(f'| {g} | (리치 없음) | — | — | — | — | — | — | — |')
            continue
        r = rr[0]
        cf = {n: r['cfg'][chosen[g][n]] for n in NAMES}

        def acc(m):
            if m.get('fallback'):
                return '가정 깨짐→A'
            a = m.get('accepted', 0)
            return f'{a}/{m.get("drawn", 0)}' + (' ⚠' if a < 30 else '')
        mp = r['info']['Cmix'].get('oracle_key_post')
        P(f'| {g} | {",".join(r["true_waits"])} | ' + '/'.join(f'{cf[n]["wait_rank"]:.1f}' for n in NAMES) + ' | '
          + '/'.join(str(cf[n]['hit']) for n in NAMES) + ' | '
          + '/'.join(str(cf[n].get('distinct')) for n in 'ABCD') + ' | '
          + str(cf['A'].get('start_tries')) + ' | ' + acc(cf['C*']) + ' | ' + acc(cf['C*mix']) + ' | '
          + (f'{mp:.2f}' if mp is not None else '—') + ' |')
    nr = len(riichi['A'])
    P('')
    P(f'리치 대기 상위3/상위5 판 수({nr}판): ' + '; '.join(
        f'{n} {sum(1 for x in riichi[n] if x <= 3)}/{sum(1 for x in riichi[n] if x <= 5)}' for n in NAMES))
    nb = sum(1 for r in results if r['riichi'] and r['cfg']['Cstar']['broken'])
    P(f'"가정 깨짐" 차례: C* {broken_tot["Cstar"]} / C*mix {broken_tot["Cmix"]} (전체 {nt} 차례 중, 리치 차례 중 C* {nb})')
    ro = [r['info']['Cmix'].get('rr_only', 0) for r in results]
    z0 = [len(r['info']['Cmix'].get('Z0', {})) for r in results]
    rb = [len(r['info']['Cmix'].get('rr_bad', {})) for r in results]
    P(f'C*mix 키 우도 0 의 원인(차례 평균, 48 키 중): 경계 DP 합 0 {np.mean(z0):.1f}, 공개-공개 어긋남 {np.mean(rb):.1f}, '
      f'그중 경계 DP 로는 > 0 인데 공개-공개 검사로만 0 이 된 키 {np.mean(ro):.1f}(이런 키가 있는 차례 {sum(1 for x in ro if x)}/{nt}) '
      f'→ 공개-공개 순서는 경계 검사로 저절로 안 걸리는 경우가 있어 따로 곱함.')
    full = [g for g in games if obs_info[g]['sorted'][0] >= 1.0]
    if full:
        fr = [r for r in results if r['game'] in full]
        P(f'\n완전 정렬 판만(정렬 정도 1.00: {", ".join(g[:3] for g in full)}, 차례 {len(fr)}; 판별 참고 — 판정은 위 전체 숫자로): '
          + '; '.join(f'{n} {np.mean([r["cfg"][chosen[r["game"]][n]]["hit"] for r in fr]):.2f}' for n in NAMES)
          + ' | 리치 상위3 ' + ', '.join(
              f'{n} {sum(1 for r in fr if r["riichi"] and r["cfg"][chosen[r["game"]][n]]["wait_rank"] <= 3)}' for n in NAMES))
        pr = [r for r in results if r['game'] not in full]
        P(f'정렬 < 1 판({len(games) - len(full)}판, 차례 {len(pr)}): '
          + '; '.join(f'{n} {np.mean([r["cfg"][chosen[r["game"]][n]]["hit"] for r in pr]):.2f}' for n in NAMES)
          + f' (C* 가정 깨짐 {sum(1 for r in pr if r["cfg"]["Cstar"]["broken"])}/{len(pr)} 차례는 A 로 채점)')
    tin_f = [r for r in results if not r['truth_in_cstar']]
    P(f'정답이 C* 제약 밖인 차례 {len(tin_f)}/{nt}: ' + ', '.join(sorted(set(r["game"][:3] for r in tin_f))))
    # ---- 판정
    mh = {n: np.mean(tot[n]['hit']) for n in NAMES}
    r3 = {n: sum(1 for x in riichi[n] if x <= 3) for n in NAMES}
    diff = mh['C'] - mh['B']
    wins = sum(1 for g in games if per_game_hit['C'][g] > per_game_hit['B'][g])
    if diff >= 2 and wins >= 6 and r3['C'] - r3['B'] >= 2:
        verdict = '칸 번호 가치 있음'
    elif diff <= 0.5 and abs(r3['C'] - r3['B']) <= 1:
        verdict = '접음'
    else:
        verdict = '애매'
    P(f'\n판정 (가) 계획서 4절(C 대 B): C−B 적중 {diff:+.2f}장, C>B {wins}/{len(games)}판, '
      f'리치 상위3 C {r3["C"]} vs B {r3["B"]} → **{verdict}**')
    ds = mh['C*'] - mh['B']
    dm = mh['C*mix'] - mh['B']
    winss = sum(1 for g in games if per_game_hit['C*'][g] > per_game_hit['B'][g])
    if ds < 1 and r3['C*'] - r3['B'] <= 1:
        v2 = '칸 번호 정보 자체가 약함 → 접음 확정'
    elif ds >= 2:
        v2 = (f'C* ≥ B + 2장 — C*mix−B {dm:+.2f}장 · C−B {diff:+.2f}장이 작으면 추정기(키 찾기) 문제, 이어서 고침')
    else:
        v2 = '추가 기준의 두 경우 어디에도 안 듦(C*−B 가 +1 ~ +2장 사이이거나 리치 상위3 차 ≥ 2)'
    P(f'판정 (나) 5절 추가 기준(C* 대 B): C*−B 적중 {ds:+.2f}장(C*>B {winss}/{len(games)}판), '
      f'리치 상위3 C* {r3["C*"]} vs B {r3["B"]}(차 {r3["C*"] - r3["B"]:+d}) → **{v2}**. '
      f'참고 C*mix−B {dm:+.2f}장, 리치 상위3 C*mix {r3["C*mix"]}.')
    # ---- 격자
    P('\n## 격자(설정별 판 평균의 평균 적중 · 차례 평균 로그차 · 리치 상위3)')
    for c in [f'{n}|{b}|{gm}' for n, b, gm in configs()] + ['Cstar', 'Cmix']:
        hm = np.mean([game_mean(results, c, 'hit', g) for g in games])
        ls = np.mean([r['cfg'][c]['logs'] - r['cfg']['A|0.0|0.0']['logs'] for r in results])
        rr3 = sum(1 for r in results if r['riichi'] and r['cfg'][c]['wait_rank'] <= 3)
        P(f'- {c}: 적중 {hm:.3f}, 로그차 {ls:+.4f}, 리치 상위3 {rr3}')
    txt = '\n'.join(lines)
    print(txt)
    with open(os.path.join(OUT_DIR, f'summary_{tag}.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt + '\n')


if __name__ == '__main__':
    main()
