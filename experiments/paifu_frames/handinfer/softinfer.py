"""부드러운 정렬 모델 Q — 진짜 칸 번호 8판 (계획서 docs/hand_infer_plan_1120.md 9절).

외부 API 없음, 순수 계산. 다시 돌리기(저장소 뿌리에서):
    python -I -X utf8 experiments/paifu_frames/handinfer/softinfer.py check     # DP == 무차별 대입 · 하드 극한 == C*mix 우도
    python -I -X utf8 experiments/paifu_frames/handinfer/softinfer.py run       # 123차례 + 텐파이 시점(L16 · r18 · r14) 표본
    python -I -X utf8 experiments/paifu_frames/handinfer/softinfer.py leak      # 누설 검사
    python -I -X utf8 experiments/paifu_frames/handinfer/softinfer.py r16       # 손으로 확인할 예(r16 13 · 16 걸음)
    python -I -X utf8 experiments/paifu_frames/handinfer/softinfer.py report    # LOGO · 표 · 판정 → summary.md
결과: experiments/paifu_frames/results/handinfer/soft/

Q(9절 정의를 이렇게 구현):
  관찰은 posinfer.obs_upto 와 같은 줄들(연이어 같은 줄 하나로) + 줄마다 나이 age = 지금 차례 수 − 그 줄(같은 줄 덩어리의 마지막)
  차례 수. 끝 붙임 표시(7절 P 의 flags, waitsuit_eval.real_obs_at 와 같은 규칙)를 그대로 쓴다: 표시된 미지수는 그 줄들의
  제약에서 빠지고, 지금 줄에서 표시된 칸은 늘 자유(어긋남 확률 1). (첫 실행은 표시 없이 돌렸다 — r16 손 확인에서 끝에
  붙였다 버린 공개 패의 경계가 어긋남 칸으로만 흡수되는 것을 보고 "P 와 같은 관찰" 로 고침. 그 결과는 *_noflag 파일.)
  가능도(키 k 마다):
    지금 줄 칸마다 독립으로 어긋남(확률 ε) / 사슬(1 − ε). 사슬 칸은 키 순위 비내림(자패 7종은 한 순위 — C*mix 와 같음).
    어긋남 칸은 사슬 · 경계 · 뒤집힘 제약에서 빠지고 남은 패에서 자유롭게 뽑힘.
    벌점(어긴 제약 하나당 δ_age = δ0 + (1 − δ0)(1 − λ^age), 같은 짝이 여러 줄에 있으면 가장 젊은 줄의 나이):
      · 미지수 ↔ 공개 패 경계(과거 줄에서 공개 패가 왼쪽 → 미지수 순위 ≥, 오른쪽 → ≤) — 사슬 칸만.
      · 공개 ↔ 공개 순서(키만으로 정해짐) — 키 우도에 곱함.
      · 미지수 ↔ 미지수 뒤집힘(과거 줄 a 앞 b, 지금 b 앞 a): 사슬에서 둘의 순위가 다르면 벌점(같으면 두 줄 모두 정렬).
  정확한 식: P(x, O | k) ∝ ε^|O|(1 − ε)^(m − |O|) · Π C(u_t, c_t) / C(N, m − |O|) · 1[사슬 정렬] · 벌점 · (어긋남 칸은
  남은 패에서 초기하) — c 는 사슬 장수. 칸 단위 DP(상태: 칸 n · 지금 순위 묶음 κ · 그 묶음 장수 c · 어긋남 수 o ·
  지금 묶음이 시작된 칸 s)로 정확히 더하고 뒤에서부터 표본을 뽑는다.
  근사한 곳(하나): 뒤집힘 짝 (b 앞칸, a 뒷칸)에서 a 가 사슬이면 "지금 묶음 시작 칸 s > b 칸" 일 때 벌점 — b 칸이 어긋남이어도
  (원래는 빠져야 함) 벌점이 붙을 수 있다. 단, 첫 사슬 묶음(앞이 모두 어긋남)은 s = 0 으로 두어 벌점 없음. check 에서
  무차별 대입으로 근사 규칙 == DP(정확 일치), 원래 규칙과의 차이를 적는다.
  자패 묶음 안 순서는 고르게 아무 순서(자패 7종을 순위 하나로 — C*mix 의 C(u_자패, c) 와 같은 셈).
  키 48개는 Q 우도 × 고른 사전으로 섞는다(정답 키 안 줌). 텐파이를 아는 시점은 텐파이 표본만(거부, 채택 수 기록).
  QB = Q 표본에 B 의 기울기 exp(−γ Σ c_t s_t) 를 중요도 가중(자기 정규화, ESS 기록).
  A · B = 남은 패에서 정확 표본(B 는 기울인 초기하, 종류별 DP 로 정확 표본). C*mix = posinfer.cstar_infer(키 섞음, 가정 깨짐 → A).
"""
import itertools
import json
import math
import os
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import posinfer as PI  # noqa: E402
import waitsuit as W  # noqa: E402
import waitsuit_eval as E  # noqa: E402
from posinfer import KEYS, RANK, key_name, tid, tname  # noqa: E402

OUT = os.path.join(PI.OUT_DIR, 'soft')
EPSS = (0.01, 0.03, 0.1, 0.25)
D0S = (0.03, 0.15, 0.5, 0.8)
FLAGS = True          # 7절 P 와 같은 끝 붙임 표시(뽑은 패가 새 줄 맨 끝 → 그 줄들에서 제약 빼고, 지금 줄이면 자유 칸)
LAMS = (0.7, 0.9, 1.0)
QGRID = [(e, d, l) for e in EPSS for d in D0S for l in LAMS]
GAMMAS = (0.1, 0.25, 0.5, 1.0, 2.0)
N_S = 2000            # 텐파이 조건 없는 차례 표본 수
N_ACC = 1000          # 텐파이 표본 목표 채택 수
MAXDRAW = 400_000     # Q: 이만큼 뽑아도 채택 30 미만이면 10 배까지
MAXDRAW_A = 2_000_000  # A · B: 4 배까지
CHUNK = 50_000
EXTRA = ['r18_141259', 'r14_133610']
NK = len(KEYS)


def cfg_name(p):
    return f'{p[0]}|{p[1]}|{p[2]}'


# ================================================================ 관찰(나이 포함)
def q_obs(obs, step_i, flags=None):
    """obs_upto 와 같은 줄 + 줄 나이 + (flags) 끝 붙임 표시(waitsuit_eval.real_obs_at 와 같은 규칙: 뽑은 패가 새 줄
    맨 끝에 서면 표시, 그 뒤 옮겨지거나 버려지면 지움). 숨은 종류는 받지 않는다(obs 의 줄 · 공개 패 · 걸음 종류만).
    rows: [(줄, 표시 미지수 목록)] — 줄이나 표시가 바뀔 때마다 새 덩어리."""
    flags = FLAGS if flags is None else flags
    runs, reveal, tau, fl = [], {}, 0, set()
    for si, st in enumerate(obs['steps'][:step_i + 1]):
        if st['kind'] == 'turn':
            tau += 1
        if si > 0 and flags:
            fl -= set(st.get('moved') or [])
            for v in st['reveal']:
                fl.discard(v)
            d = st.get('drawn')
            if d is not None and st['row'] and st['row'][-1] == d:
                fl.add(d)
        reveal.update({v: tid(t) for v, t in st['reveal'].items()})
        key = (list(st['row']), sorted(fl))
        if runs and runs[-1][0] == key:
            runs[-1][1] = tau
        else:
            runs.append([key, tau])
    return dict(rows=[(r, f) for (r, f), _ in runs], ages=[tau - t for _, t in runs], reveal=reveal,
                cur=list(obs['steps'][step_i]['row']), flags=sorted(fl))


def q_structs(qo):
    """키와 무관한 제약 재료. bnd: (칸, 공개 종류, 'lo'|'hi', 나이, 공개 미지수 번호), rr: (앞 종류, 뒤 종류, 나이),
    flp: (b 칸, a 칸, 나이) — 과거 줄 a 앞 b 였는데 지금 b 가 앞(b 칸 < a 칸)."""
    rv, cur = qo['reveal'], qo['cur']
    pos = {v: i for i, v in enumerate(cur)}
    bnd, rr, flp = {}, {}, {}

    def put(d, k, age):
        d[k] = min(d.get(k, 10 ** 9), age)
    for (r0, ex), age in zip(qo['rows'], qo['ages']):
        exs = set(ex)
        r = [v for v in r0 if v not in exs]
        for i in range(len(r)):
            a = r[i]
            for b in r[i + 1:]:
                ra, rb = a in rv, b in rv
                if ra and rb:
                    put(rr, (a, b), age)
                elif ra:
                    put(bnd, (pos[b], a, 'lo'), age)
                elif rb:
                    put(bnd, (pos[a], b, 'hi'), age)
                elif pos[a] > pos[b]:
                    put(flp, (pos[b], pos[a]), age)
    return dict(m=len(cur), free=sorted(pos[v] for v in qo.get('flags', [])), bnd=sorted((p, rv[v], s, age, v) for (p, v, s), age in bnd.items()),
                rr=sorted((rv[a], rv[b], age) for (a, b), age in rr.items()),
                flp=sorted((pb, pa, age) for (pb, pa), age in flp.items()))


def ldelta(age, d0, lam):
    return math.log(d0 + (1 - d0) * (1 - lam ** age))


# ================================================================ 키 하나의 표 · DP
def key_tab(st, k, unseen, prm):
    eps, d0, lam = prm
    R = RANK[k]
    cls = PI._classes(k)
    K = len(cls)
    crank = np.array([r for r, _ in cls])
    u = np.array([sum(int(unseen[t]) for t in ts) for _, ts in cls], float)
    m = st['m']
    LP = np.zeros((m, K))
    for p, t, side, age, _v in st['bnd']:
        ld = ldelta(age, d0, lam)
        LP[p] += ld * ((crank < R[t]) if side == 'lo' else (crank > R[t]))
    FP = np.zeros((m, m + 1))
    for pb, pa, age in st['flp']:
        FP[pa, pb + 1:] += ldelta(age, d0, lam)            # 지금 묶음 시작 s > b 칸이면 벌점
    rr = sum(ldelta(age, d0, lam) for ta, tb, age in st['rr'] if R[ta] > R[tb])
    epsn = np.full(m, float(eps))
    epsn[list(st.get('free', []))] = 1.0                    # 끝 붙임 표시 칸은 늘 자유(7절 P 와 같음)
    return dict(cls=cls, u=u, EL=np.exp(LP), EF=np.exp(FP), rr=rr, flip=bool(st['flp']), epsn=epsn, K=K)


def q_backward(tab, m, N, keep=False):
    """뒤에서부터 B[n][κ, c, o, s](칸 n.. 을 채우는 가중 합, 칸마다 크기 맞춤). 반환 (log Z, 저장)."""
    epsn, u, K = tab['epsn'], tab['u'], tab['K']
    C = O = m + 1
    Sd = m + 1 if tab['flip'] else 1
    ci = np.arange(C)
    ratio = np.maximum(u[:, None] - ci[None, :], 0) / (ci[None, :] + 1)
    term = np.array([1.0 / math.comb(N, m - o) if N >= m - o else 0.0 for o in range(O)])
    Bn = np.broadcast_to(term[None, None, :, None], (K, C, O, Sd)).copy()
    Bs, L = 1.0, 0.0
    store = [None] * (m + 1)
    if keep:
        store[m] = (Bn, Bs)
    for n in range(m - 1, -1, -1):
        eps = epsn[n]
        EL = tab['EL'][n]
        EF = tab['EF'][n] if Sd > 1 else np.ones(1)
        new = np.zeros((K, C, O, Sd))
        new[:, :, :-1, :] += eps * Bn[:, :, 1:, :]
        new[:, :-1, :, :] += (1 - eps) * (ratio[:, :-1, None, None] * EL[:, None, None, None]
                                          * EF[None, None, None, :] * Bn[:, 1:, :, :])
        sn = n if Sd > 1 else 0
        T = (1 - eps) * u[:, None] * EL[:, None] * Bn[:, 1, :, sn]            # [K, O]
        suf = np.zeros_like(T)
        suf[:-1] = np.cumsum(T[::-1], axis=0)[::-1][1:]
        new += EF[sn] * suf[:, None, :, None]
        T0 = (1 - eps) * u * EL * Bn[:, 1, n, 0]                                # 처음 묶음: s = 0
        Bs_new = eps * Bs + T0.sum()
        f = max(float(new.max()), Bs_new)
        if f <= 0:
            return -math.inf, None
        Bn, Bs, L = new / f, Bs_new / f, L + math.log(f)
        if keep:
            store[n] = (Bn, Bs)
    return (math.log(Bs) + L if Bs > 0 else -math.inf), store


def q_forward(tab, store, m, S, rng, unseen, want_path=False):
    """앞에서부터 정확 표본 S 개 → 종류별 장수 [S, 34](+ 칸별 묶음 번호, −1 = 어긋남)."""
    epsn, u, K = tab['epsn'], tab['u'], tab['K']
    ci = np.arange(m + 1)
    ratio = np.maximum(u[:, None] - ci[None, :], 0) / (ci[None, :] + 1)
    kap = np.full(S, -1)
    c = np.zeros(S, int)
    o = np.zeros(S, int)
    s = np.zeros(S, int)
    path = np.zeros((S, m), int)
    for n in range(m):
        eps = epsn[n]
        Bn1, Bs1 = store[n + 1]
        Sd = Bn1.shape[3]
        EL = tab['EL'][n]
        EF = tab['EF'][n] if Sd > 1 else np.ones(1)
        sn = n if Sd > 1 else 0
        st = kap < 0
        ns = ~st
        si = s if Sd > 1 else np.zeros(S, int)
        Wt = np.zeros((S, K + 2))
        snew = np.where(st, 0, sn)
        base = (1 - eps) * u[None, :] * EL[None, :] * Bn1[:, 1, o, snew].T           # [S, K]
        fnew = np.where(st, 1.0, EF[sn])
        Wt[:, 2:] = base * (np.arange(K)[None, :] > kap[:, None]) * fnew[:, None]
        Wt[st, 0] = eps * Bs1
        if ns.any():
            kk, cc, oo, ss = kap[ns], c[ns], o[ns], si[ns]
            Wt[ns, 0] = eps * Bn1[kk, cc, oo + 1, ss]
            Wt[ns, 1] = (1 - eps) * ratio[kk, cc] * EL[kk] * EF[ss] * Bn1[kk, cc + 1, oo, ss]
        cum = np.cumsum(Wt, 1)
        r = rng.random(S) * cum[:, -1]
        ch = (cum <= r[:, None]).sum(1)
        ch = np.minimum(ch, K + 1)
        is_o, is_c, is_n = ch == 0, ch == 1, ch >= 2
        o[is_o] += 1
        path[is_o, n] = -1
        c[is_c] += 1
        path[is_c, n] = kap[is_c]
        newk = ch[is_n] - 2
        s[is_n] = np.where(st[is_n], 0, n)
        kap[is_n] = newk
        c[is_n] = 1
        path[is_n, n] = newk
    cls = tab['cls']
    cnt = np.zeros((S, 34), np.int64)
    ccls = np.zeros((S, K), int)
    for kk in range(K):
        ccls[:, kk] = (path == kk).sum(1)
    for kk, (_, ts) in enumerate(cls):
        if len(ts) == 1:
            cnt[:, ts[0]] = ccls[:, kk]
        else:
            col = np.array([int(unseen[t]) for t in ts], np.int64)
            for v in np.unique(ccls[:, kk]):
                if v == 0:
                    continue
                idx = np.flatnonzero(ccls[:, kk] == v)
                cnt[np.ix_(idx, ts)] = rng.multivariate_hypergeometric(col, int(v), size=len(idx))
    rest = unseen[None, :].astype(np.int64) - cnt
    assert (rest >= 0).all()
    for j in range(int(o.max()) if S else 0):
        act = np.flatnonzero(o > j)
        cum = np.cumsum(rest[act], 1)
        r = rng.random(len(act)) * cum[:, -1]
        t = (cum <= r[:, None]).sum(1)
        cnt[act, t] += 1
        rest[act, t] -= 1
    return (cnt, path, o) if want_path else (cnt, o)


def q_keylike(st, unseen, prm, keep_small=True):
    """48 키 log 우도(Q). 뒤집힘 없는 차례는 표를 들고 있음(작음)."""
    m, N = st['m'], int(unseen.sum())
    ll = np.full(NK, -np.inf)
    tabs, stores = {}, {}
    for k in range(NK):
        tab = key_tab(st, k, unseen, prm)
        keep = keep_small and not tab['flip']
        lz, store = q_backward(tab, m, N, keep=keep)
        ll[k] = lz + tab['rr']
        tabs[k] = tab
        if keep:
            stores[k] = store
    return ll, tabs, stores


def sample_q(qo, unseen, prm, n, tenpai, seed, want_path=False, maxdraw=MAXDRAW):
    """Q 표본. 반환 (cnts 또는 None, 정보). tenpai: 거부(채택 n 또는 maxdraw, 채택 30 미만이면 10 배까지)."""
    rng = np.random.default_rng(seed)
    st = q_structs(qo)
    m, N = st['m'], int(unseen.sum())
    ll, tabs, stores = q_keylike(st, unseen, prm)
    info = dict(m=m, n_bnd=len(st['bnd']), n_rr=len(st['rr']), n_flp=len(st['flp']))
    if not np.isfinite(ll).any():
        info['broken'] = True
        return None, info
    post = np.exp(ll - ll.max())
    post /= post.sum()
    info['post'] = post
    info['broken'] = False
    outs, paths, os_, keys_ = [], [], [], []
    drawn = got = 0
    rnd = 0
    while True:
        if not tenpai and drawn >= n:
            break
        if tenpai and (got >= n or (drawn >= maxdraw and (got >= 30 or drawn >= 10 * maxdraw))):
            break
        D = n if not tenpai else min(CHUNK * (2 ** min(rnd, 3)), 10 * maxdraw - drawn)
        rnd += 1
        kc = rng.multinomial(D, post)
        for k in np.flatnonzero(kc):
            store = stores.get(k)
            if store is None:
                _, store = q_backward(tabs[k], m, N, keep=True)
            left = int(kc[k])
            while left:
                S = min(left, CHUNK)
                left -= S
                res = q_forward(tabs[k], store, m, S, rng, unseen, want_path)
                cn = res[0]
                if tenpai:
                    ok = W.tenpai_batch(cn)
                else:
                    ok = np.ones(S, bool)
                outs.append(cn[ok])
                os_.append(res[-1][ok])
                keys_.append(np.full(int(ok.sum()), k))
                if want_path:
                    paths.append(res[1][ok])
                got += int(ok.sum())
            if tabs[k]['flip']:
                store = None
        drawn += D
    cn = np.concatenate(outs) if outs else np.zeros((0, 34), np.int64)
    info.update(drawn=drawn, accepted=int(len(cn)), mean_out=float(np.concatenate(os_).mean()) if len(cn) else None)
    if tenpai:
        perm = rng.permutation(len(cn))[:n]          # 키 순서로 쌓였으니 섞어서 n 개
    else:
        perm = np.arange(len(cn))
    cn = cn[perm]
    if want_path:
        info['path'] = np.concatenate(paths)[perm]
        info['keys'] = np.concatenate(keys_)[perm]
        info['o'] = np.concatenate(os_)[perm]
    if len(cn) == 0:
        info['no_tenpai'] = True
        return None, info
    return cn, info


# ================================================================ A · B(정확 표본)
def sample_tilt(unseen, m, w, S, rng):
    """P(c) ∝ Π C(u_t, c_t) w_t^c_t, Σc = m. 종류별 DP 로 정확 표본."""
    u = unseen.astype(int)
    G = np.zeros((35, m + 1))
    G[34, 0] = 1.0
    for t in range(33, -1, -1):
        for c in range(0, min(u[t], m) + 1):
            G[t, c:] += math.comb(u[t], c) * w[t] ** c * G[t + 1, :m + 1 - c]
        mx = G[t].max()
        if mx > 0:
            G[t] /= mx          # 줄마다 크기 맞춤(비율만 씀)
    cnt = np.zeros((S, 34), np.int64)
    krem = np.full(S, m)
    for t in range(34):
        cmax = min(u[t], m)
        cs = np.arange(cmax + 1)
        wt = np.array([math.comb(u[t], c) * w[t] ** c for c in cs])
        idx = krem[:, None] - cs[None, :]
        val = np.where(idx >= 0, G[t + 1][np.clip(idx, 0, m)], 0.0) * wt[None, :]
        cum = np.cumsum(val, 1)
        r = rng.random(S) * cum[:, -1]
        ch = np.minimum((cum <= r[:, None]).sum(1), cmax)
        cnt[:, t] = ch
        krem -= ch
    assert (krem == 0).all()
    return cnt


def sample_AB(unseen, m, gamma, hs, n, tenpai, seed, maxdraw=MAXDRAW_A):
    rng = np.random.default_rng(seed)
    w = np.exp(-gamma * hs) if gamma > 0 else np.ones(34)
    if not tenpai:
        return sample_tilt(unseen, m, w, n, rng), dict(drawn=n, accepted=n)
    outs, drawn, got = [], 0, 0
    while got < n:
        if drawn >= maxdraw and (got >= 30 or drawn >= 4 * maxdraw):
            break
        cn = sample_tilt(unseen, m, w, CHUNK * 2, rng)
        drawn += len(cn)
        cn = cn[W.tenpai_batch(cn)]
        outs.append(cn)
        got += len(cn)
    cn = np.concatenate(outs)[:n]
    return (cn if len(cn) else None), dict(drawn=drawn, accepted=got)


# ================================================================ 지표
def sm_metrics(cnts, w, unseen, truth, want_wait=False, true_wsuits=None):
    S = len(cnts)
    if w is None:
        w = np.full(S, 1.0 / S)
    w = w / w.sum()
    ess = 1.0 / float((w ** 2).sum())
    ph = w @ (cnts >= 1)
    p1 = (ess * ph + 0.5) / (ess + 1)
    p1 = np.where(unseen > 0, p1, 0.0)
    suit = np.array([w @ cnts[:, k * 9:(k + 1) * 9].sum(1) for k in range(4)])
    y = truth >= 1
    ll = np.where(y, np.log(np.maximum(p1, 1e-6)), np.log(np.maximum(1 - p1, 1e-6)))
    ts = np.array([truth[k * 9:(k + 1) * 9].sum() for k in range(4)])
    out = dict(logs=float(ll.mean()), suit_err=float(np.abs(suit - ts).sum()), p1=p1.round(5).tolist(),
               suit=suit.round(4).tolist(), ess=round(ess, 1))
    if want_wait:
        WS = np.zeros((S, 4), bool)
        for i, r in enumerate(cnts):
            for t in PI.fast_waits(tuple(int(x) for x in r)):
                WS[i, t // 9] = True
        ps = w @ WS
        y4 = np.zeros(4)
        y4[list(true_wsuits)] = 1
        out['wsuit'] = ps.round(4).tolist()
        out['wsuit_top1'] = E.top1(ps, y4)
    return out


# ================================================================ 한 차례
def turn_setup(g, step_i, tenpai_override=None):
    paifu = PI.load(g)
    obs, tt = PI.build_observation(paifu)
    st = obs['steps'][step_i]
    o = PI.obs_upto(obs, step_i)
    qo = q_obs(obs, step_i)
    q0 = q_obs(obs, step_i, flags=False)
    assert [r for r, _ in q0['rows']] == o['rows'] and qo['cur'] == o['cur'] and qo['reveal'] == o['reveal']
    pub = PI.build_public(paifu, st['ev'])
    tenpai = bool(st.get('riichi')) if tenpai_override is None else tenpai_override
    e = paifu['events'][st['ev']]
    truth = np.bincount([tid(x) for x in e['hand']], minlength=34)
    return paifu, obs, st, o, qo, pub, tenpai, truth


def run_turn(args):
    g, step_i, tag = args             # tag: 'main'(123차례) · 'tp'(텐파이 알려 준 시점, ⑤ 전용)
    t0 = time.time()
    paifu, obs, st, o, qo, pub, tenpai, truth = turn_setup(g, step_i, True if tag == 'tp' else None)
    unseen = pub['unseen']
    m = len(qo['cur'])
    hs = PI.heuristic_score(pub['hero_disc'])
    tw, wsu = None, None
    if tenpai:
        tw = list(PI.fast_waits(tuple(int(x) for x in truth)))
        assert tw, '정답 손이 텐파이가 아님'
        wsu = sorted(set(t // 9 for t in tw))
    res = dict(game=g, step=step_i, ev=st['ev'], tag=tag, n=m, tenpai=tenpai, riichi=bool(st.get('riichi')),
               truth=truth.tolist(), unseen=unseen.tolist(), truth_impossible=int((truth > unseen).sum()),
               waits=[tname(t) for t in tw] if tw else None, wsuits=wsu, cfg={}, acc={})

    def met(cn, w=None):
        return sm_metrics(cn, w, unseen, truth, tenpai, wsu)
    base = zlib.crc32(f'{g}|{step_i}|{tag}'.encode())
    # A · B
    for gm in (0.0,) + GAMMAS:
        cn, inf = sample_AB(unseen, m, gm, hs, N_ACC if tenpai else N_S, tenpai, base + int(gm * 1000) + 1)
        name = 'A' if gm == 0 else f'B|{gm}'
        res['acc'][name] = [inf['accepted'], inf['drawn']]
        res['cfg'][name] = met(cn) if cn is not None else None
    # C*mix
    cn, inf = PI.cstar_infer(o, pub, None, tenpai, base + 7, n=N_ACC if tenpai else N_S)
    if cn is None:
        res['cfg']['Cmix'] = dict(res['cfg']['A'], fallback='A')
    else:
        res['cfg']['Cmix'] = met(cn)
    res['cfg']['Cmix']['broken'] = bool(inf['broken'] or inf.get('no_tenpai', False))
    res['acc']['Cmix'] = [inf.get('accepted_total', inf.get('accepted', 0)), inf.get('drawn', 0)]
    so, okn, okey = PI.sortedness(paifu)       # 진단 전용(오라클 키 사후)
    res['oracle_key'] = okn
    # Q · QB
    for prm in QGRID:
        nm = cfg_name(prm)
        cn, inf = sample_q(qo, unseen, prm, N_ACC if tenpai else N_S, tenpai,
                           base + zlib.crc32(nm.encode()) % 100000)
        res['acc']['Q|' + nm] = [inf.get('accepted', 0), inf.get('drawn', 0)]
        if cn is None:
            res['cfg']['Q|' + nm] = None
            continue
        m_ = met(cn)
        m_['oracle_post'] = float(inf['post'][okey])
        m_['key_top'] = [(key_name(int(i)), round(float(inf['post'][i]), 3)) for i in np.argsort(-inf['post'])[:3]]
        m_['mean_out'] = inf['mean_out']
        res['cfg']['Q|' + nm] = m_
        e = cn @ hs
        for gm in GAMMAS:
            lw = -gm * e
            w = np.exp(lw - lw.max())
            res['cfg'][f'QB|{nm}|{gm}'] = met(cn, w)
    res['info'] = dict(n_bnd=inf['n_bnd'], n_rr=inf['n_rr'], n_flp=inf['n_flp'])
    res['sec'] = round(time.time() - t0, 1)
    return res


def tp_points():
    """⑤ 의 텐파이 시점: (판, 걸음, 꼬리표). 리치 7 은 main 차례 안에 있음 — 여기선 L16 · r18 · r14 만 따로."""
    pts = []
    p = PI.load('L16_135321')
    obs, _ = PI.build_observation(p)
    pts.append(('L16_135321', E.first_stay_tenpai(p, obs['steps']), 'tp'))
    for g in EXTRA:
        p = PI.load(g)
        obs, _ = PI.build_observation(p)
        pts.append((g, next(i for i, s in enumerate(obs['steps']) if s.get('riichi')), 'tp'))
    return pts


def main_turns():
    tasks = []
    for g in PI.GAMES:
        p = PI.load(g)
        obs, _ = PI.build_observation(p)
        tasks += [(g, i, 'main') for i, s in enumerate(obs['steps']) if s['kind'] == 'turn']
    return tasks


def cmd_run(workers, only=None):
    os.makedirs(OUT, exist_ok=True)
    tasks = main_turns() + tp_points()
    if only:
        tasks = [t for t in tasks if t[0].startswith(only)]
    # 무거운 것(텐파이 · 뒤집힘 있는 차례) 먼저
    tasks = [t for t in tasks if t[2] == 'tp'] + [t for t in tasks if t[2] != 'tp'][::-1]   # 텐파이 · 늦은 차례(무거움) 먼저
    fp = os.path.join(OUT, 'turns.jsonl')
    done = set()
    if os.path.exists(fp):
        for line in open(fp, encoding='utf-8'):
            d = json.loads(line)
            done.add((d['game'], d['step'], d['tag']))
    todo = [t for t in tasks if t not in done]
    print(f'차례 {len(tasks)}, 남은 것 {len(todo)}', flush=True)
    t0 = time.time()
    with open(fp, 'a', encoding='utf-8') as f, ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(run_turn, todo)):
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            print(f'  {i + 1}/{len(todo)} {r["game"][:3]} 걸음 {r["step"]} {r["tag"]} {r["sec"]}s '
                  f'(누적 {time.time() - t0:.0f}s)', flush=True)


# ================================================================ 검사: DP == 무차별 대입, 하드 극한 == C*mix
def brute(st, k, unseen, prm, exact_flip):
    """작은 경우 무차별: Σ_x Σ_O 가중. exact_flip=True 면 원래 규칙(b 가 어긋남이면 뒤집힘 벌점 없음)."""
    eps, d0, lam = prm
    R = RANK[k]
    m, N = st['m'], int(unseen.sum())
    types = [t for t in range(34) if unseen[t] > 0]
    tot = 0.0
    for x in itertools.product(types, repeat=m):
        cnt = np.bincount(x, minlength=34)
        if (cnt > unseen).any():
            continue
        pr = np.prod([math.comb(int(unseen[t]), int(cnt[t])) for t in types]) / math.comb(N, m)
        for O in itertools.product((0, 1), repeat=m):
            o = sum(O)
            f = np.bincount([x[i] for i in range(m) if O[i]], minlength=34)
            ff = np.prod([math.perm(int(cnt[t]), int(f[t])) for t in types]) / math.perm(m, o)
            ch = [i for i in range(m) if not O[i]]
            rk = [R[x[i]] for i in ch]
            if any(rk[i] > rk[i + 1] for i in range(len(rk) - 1)):
                continue
            w = eps ** o * (1 - eps) ** (m - o) * pr * ff * _honor_norm([x[i] for i in ch])
            for p, t, side, age, _v in st['bnd']:
                if O[p]:
                    continue
                if (side == 'lo' and R[x[p]] < R[t]) or (side == 'hi' and R[x[p]] > R[t]):
                    w *= d0 + (1 - d0) * (1 - lam ** age)
            for pb, pa, age in st['flp']:
                if O[pa]:
                    continue
                if exact_flip:
                    bad = (not O[pb]) and R[x[pb]] != R[x[pa]]
                else:
                    # 근사 규칙: a 의 묶음이 시작된 사슬 칸 s(첫 묶음이면 0) > b 칸
                    j = ch.index(pa)
                    s0 = j
                    while s0 > 0 and R[x[ch[s0 - 1]]] == R[x[pa]]:
                        s0 -= 1
                    s_ = 0 if s0 == 0 else ch[s0]
                    bad = s_ > pb
                if bad:
                    w *= d0 + (1 - d0) * (1 - lam ** age)
            tot += w
    for ta, tb, age in st['rr']:
        if R[ta] > R[tb]:
            tot *= d0 + (1 - d0) * (1 - lam ** age)
    return tot


def cmd_check():
    sys.stdout.reconfigure(encoding='utf-8')
    rng = np.random.default_rng(5)
    out = dict(brute=[], hard=[], free=[], tenpai_batch10=None)
    # (1) 작은 무차별: 종류 5개 · 칸 4 · 무작위 제약
    for trial in range(6):
        unseen = np.zeros(34, int)
        tys = rng.choice([0, 1, 4, 9, 13, 27, 28], size=4, replace=False)
        for t in tys:
            unseen[t] = int(rng.integers(1, 4))
        m = 4
        st = dict(m=m, bnd=[(int(rng.integers(m)), int(rng.choice(tys)), ['lo', 'hi'][int(rng.integers(2))],
                             int(rng.integers(1, 6)), 900 + i) for i in range(3)],
                  rr=[(int(tys[0]), int(tys[1]), 2)],
                  flp=[(0, 2, 1), (1, 3, 3)] if trial % 2 else [])
        prm = (0.2, 0.1, 0.8)
        for k in (0, 17, 33):
            tab = key_tab(st, k, unseen, prm)
            lz, _ = q_backward(tab, m, int(unseen.sum()))
            dp = math.exp(lz + tab['rr'])
            b_ap = brute(st, k, unseen, prm, exact_flip=False)
            b_ex = brute(st, k, unseen, prm, exact_flip=True)
            out['brute'].append(dict(trial=trial, key=key_name(k), dp=dp, brute_approx=b_ap, brute_exact=b_ex,
                                     rel_err=abs(dp - b_ap) / max(b_ap, 1e-300),
                                     approx_vs_exact=(b_ap - b_ex) / max(b_ex, 1e-300)))
    # (1b) 표본 분포 == 무차별 대입 주변 확률(종류별 기대 장수)
    unseen = np.zeros(34, int)
    for t, c in ((0, 2), (4, 3), (13, 2), (27, 3)):
        unseen[t] = c
    st = dict(m=4, bnd=[(1, 4, 'lo', 2, 901), (3, 13, 'hi', 1, 902)], rr=[], flp=[(0, 2, 1)])
    prm = (0.2, 0.1, 0.8)
    k = 0
    tab = key_tab(st, k, unseen, prm)
    _, store = q_backward(tab, 4, int(unseen.sum()), keep=True)
    cn, _ = q_forward(tab, store, 4, 200000, np.random.default_rng(1), unseen)
    # 무차별 기대 장수(근사 규칙)
    R = RANK[k]
    num = np.zeros(34)
    den = 0.0
    types = [t for t in range(34) if unseen[t]]
    for x in itertools.product(types, repeat=4):
        cnt = np.bincount(x, minlength=34)
        if (cnt > unseen).any():
            continue
        st1 = dict(st)
        w = brute_one(st1, k, unseen, prm, x)
        num += w * cnt
        den += w
    out['sampler'] = dict(sample_mean=cn.mean(0)[types].round(4).tolist(), brute_mean=(num / den)[types].round(4).tolist())
    # (2) 하드 극한(ε → 0, δ0 → 0, λ = 1) 의 키 우도 == C*mix(posinfer) 우도 — 실제 차례 몇 개
    for g, si in (('r12_131655', 7), ('r17_140450', 11), ('r19_142013', 8), ('r13_132644', 9), ('r16_135321', 13)):
        p = PI.load(g)
        obs, _ = PI.build_observation(p)
        o = PI.obs_upto(obs, si)
        qo = q_obs(obs, si, flags=False)   # C*mix 는 끝 붙임 표시 없음
        pub = PI.build_public(p, obs['steps'][si]['ev'])
        _, info = PI.cstar_infer(o, pub, None, False, 1, n=10)
        lk = np.array(info['like'])
        ll, _, _ = q_keylike(q_structs(qo), pub['unseen'], (1e-12, 1e-300, 1.0), keep_small=False)
        q = np.exp(ll)
        al = lk > 0
        mx = max(lk.max(), q.max())
        rel = float(np.max(np.abs(q[al] - lk[al]) / lk[al])) if al.any() else 0.0
        dead_max = float(q[~al].max() / mx) if (~al).any() and mx > 0 else 0.0
        out['hard'].append(dict(game=g, step=si, cmix_alive=int(al.sum()), max_rel_alive=rel,
                                dead_q_over_max=dead_max, ok=bool(rel < 1e-4 and dead_max < 1e-6)))
    # (3) 제약 없음 → Z = 1
    unseen = np.array(PI.build_public(PI.load('r12_131655'), 5)['unseen'])
    st = dict(m=13, bnd=[], rr=[], flp=[])
    zs = []
    for prm in ((0.1, 0.1, 0.9), (0.25, 0.5, 1.0)):
        tab = key_tab(st, 3, unseen, prm)
        zs.append(math.exp(q_backward(tab, 13, int(unseen.sum()))[0]))
    out['free'] = zs
    # (4) 10장(울기) 손에서 묶음 텐파이 판정 == fast_waits
    rngb = np.random.default_rng(9)
    pool = np.repeat(np.arange(34), 4)
    rows = np.array([np.bincount(rngb.choice(pool, 10, replace=False), minlength=34) for _ in range(20000)])
    near = []
    for _ in range(10000):                              # 텐파이 근처(면자 3 + 머리 − 1장)
        c = np.zeros(34, int)
        for _k in range(3):
            if rngb.random() < 0.5:
                c[rngb.integers(34)] += 3
            else:
                s_ = rngb.integers(3); x = rngb.integers(7); c[s_ * 9 + x:s_ * 9 + x + 3] += 1
        c[rngb.integers(34)] += 2
        nz = np.flatnonzero(c); c[rngb.choice(nz)] -= 1
        if c.max() <= 4:
            near.append(c)
    rows = np.concatenate([rows, np.array(near)])
    fast = W.tenpai_batch(rows)
    ref = np.array([bool(PI.fast_waits(tuple(int(x) for x in r))) for r in rows])
    out['tenpai_batch10'] = dict(n=len(rows), tenpai=int(ref.sum()), mismatch=int((fast != ref).sum()))
    for k_, v in out.items():
        print(k_, json.dumps(v, ensure_ascii=False, default=float)[:3000])
    json.dump(out, open(os.path.join(OUT, 'check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              default=float)


def _honor_norm(chain_types):
    """사슬 안 자패 묶음의 순서는 고르게(서로 다른 순서 수로 나눔) — DP 의 자패 한 묶음 C(u_자패, c) 와 같은 셈."""
    hc = np.bincount([t for t in chain_types if t >= 27], minlength=34)[27:]
    return float(np.prod([math.factorial(int(v)) for v in hc]) / math.factorial(int(hc.sum())))


def brute_one(st, k, unseen, prm, x):
    """무차별 대입의 x 하나 가중(근사 규칙, O 에 대해 합)."""
    eps, d0, lam = prm
    R = RANK[k]
    m, N = st['m'], int(unseen.sum())
    types = [t for t in range(34) if unseen[t] > 0]
    cnt = np.bincount(x, minlength=34)
    pr = np.prod([math.comb(int(unseen[t]), int(cnt[t])) for t in types]) / math.comb(N, m)
    tot = 0.0
    for O in itertools.product((0, 1), repeat=m):
        o = sum(O)
        f = np.bincount([x[i] for i in range(m) if O[i]], minlength=34)
        ff = np.prod([math.perm(int(cnt[t]), int(f[t])) for t in types]) / math.perm(m, o)
        ch = [i for i in range(m) if not O[i]]
        rk = [R[x[i]] for i in ch]
        if any(rk[i] > rk[i + 1] for i in range(len(rk) - 1)):
            continue
        w = eps ** o * (1 - eps) ** (m - o) * pr * ff * _honor_norm([x[i] for i in ch])
        for p, t, side, age, _v in st['bnd']:
            if not O[p] and ((side == 'lo' and R[x[p]] < R[t]) or (side == 'hi' and R[x[p]] > R[t])):
                w *= d0 + (1 - d0) * (1 - lam ** age)
        for pb, pa, age in st['flp']:
            if O[pa]:
                continue
            j = ch.index(pa)
            s0 = j
            while s0 > 0 and R[x[ch[s0 - 1]]] == R[x[pa]]:
                s0 -= 1
            s_ = 0 if s0 == 0 else ch[s0]
            if s_ > pb:
                w *= d0 + (1 - d0) * (1 - lam ** age)
        tot += w
    return tot


# ================================================================ 누설 검사
def fake_paifu(paifu, obs, tt, ti):
    """posinfer.leak_test 와 같은 방식: 시점 ti 까지 드러나지 않은 미지수에 서로 다른 가짜 종류(X번호)."""
    revealed = set()
    for st in obs['steps'][:ti + 1]:
        revealed |= set(st['reveal'])
    fake = {v: 100 + v for v in tt if v not in revealed}

    def ftype(v):
        return tname(fake.get(v, tt[v]))
    st_t = obs['steps'][ti]
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
    return p2


def cmd_leak():
    sys.stdout.reconfigure(encoding='utf-8')
    prm = (0.1, 0.15, 0.9)
    out = {}
    for g in PI.GAMES + EXTRA:
        paifu = PI.load(g)
        obs, tt = PI.build_observation(paifu)
        turns = [i for i, s in enumerate(obs['steps']) if s['kind'] == 'turn']
        same = diff = 0
        samp = []
        chk_steps = {turns[-1]} | {i for i in turns if obs['steps'][i].get('riichi')}
        if g == 'L16_135321':
            chk_steps.add(E.first_stay_tenpai(paifu, obs['steps']))
        for ti in turns:
            p2 = fake_paifu(paifu, obs, tt, ti)
            try:
                obs2, _ = PI.build_observation(p2)
                q1, q2 = q_obs(obs, ti), q_obs(obs2, ti)
                ok = q1 == q2
            except Exception:  # noqa
                ok = False
            same += ok
            diff += not ok
            if ok and ti in chk_steps:
                pub = PI.build_public(paifu, obs['steps'][ti]['ev'])
                pub2 = PI.build_public(p2, obs['steps'][ti]['ev'])
                pub_same = all(np.array_equal(pub[k], pub2[k]) if isinstance(pub[k], np.ndarray) else pub[k] == pub2[k]
                               for k in pub)
                tp = bool(obs['steps'][ti].get('riichi')) or (g == 'L16_135321' and ti == max(chk_steps))
                c1, _ = sample_q(q1, pub['unseen'], prm, 200, tp, 11, maxdraw=100_000)
                c2, _ = sample_q(q2, pub2['unseen'], prm, 200, tp, 11, maxdraw=100_000)
                same_q = (c1 is None and c2 is None) or (c1 is not None and c2 is not None and c1.shape == c2.shape
                                                         and bool((c1 == c2).all()))
                samp.append(dict(step=ti, tenpai=tp, pub_same=pub_same, q_same=same_q,
                                 n=None if c1 is None else len(c1)))
        out[g] = dict(turns=len(turns), obs_same=same, obs_diff=diff, samples=samp)
        print(g, out[g], flush=True)
    json.dump(out, open(os.path.join(OUT, 'leak.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


# ================================================================ 손으로 확인(r16)
def cmd_r16(prm=None):
    sys.stdout.reconfigure(encoding='utf-8')
    g = 'r16_135321'
    if prm is None:
        rep = os.path.join(OUT, 'report.json')
        prm = tuple(json.load(open(rep, encoding='utf-8'))['chosen'][g]['Q']) if os.path.exists(rep) else (0.1, 0.15, 0.9)
    paifu = PI.load(g)
    obs, tt = PI.build_observation(paifu)
    so, okn, okey = PI.sortedness(paifu)
    out = dict(prm=prm, oracle_key=okn, steps=[])
    for si in (13, 15, 16):
        st_ = obs['steps'][si]
        qo = q_obs(obs, si)
        pub = PI.build_public(paifu, st_['ev'])
        tenpai = bool(st_.get('riichi'))
        cn, inf = sample_q(qo, pub['unseen'], prm, 1000 if tenpai else 4000, tenpai, 3, want_path=True)
        st = q_structs(qo)
        post = inf['post']
        path, keys = inf['path'], inf['keys']
        cur = [tname(tt[v]) for v in qo['cur']]
        p_out = (path == -1).mean(0)
        # 공개 패별 '어긴 경계 짝' 기대 수(표본에서; 사슬 칸만)
        by_rev = {}
        crank = np.full((NK, 30), np.nan)
        for k in range(NK):
            for ci_, (r_, _) in enumerate(PI._classes(k)):
                crank[k, ci_] = r_
        for p, t, side, age, v in st['bnd']:
            rk = np.where(path[:, p] >= 0, crank[keys, np.maximum(path[:, p], 0)], np.nan)
            Rt = RANK[keys, t]
            bad = (path[:, p] >= 0) & ((rk < Rt) if side == 'lo' else (rk > Rt))
            key_ = f'{tname(t)}(v{v})'
            d = by_rev.setdefault(key_, dict(pairs=0, exp_viol=0.0, ages=set()))
            d['pairs'] += 1
            d['exp_viol'] += float(bad.mean())
            d['ages'].add(age)
        rows = [' '.join(tname(tt[v]) + ('*' if v in qo['reveal'] else '') + ('^' if v in ex else '') for v in r)
                + f'  (나이 {a})' for (r, ex), a in zip(qo['rows'], qo['ages'])]
        rec = dict(step=si, tenpai=tenpai, cur=cur, accepted=inf.get('accepted'), drawn=inf.get('drawn'),
                   key_top=[(key_name(int(i)), round(float(post[i]), 4)) for i in np.argsort(-post)[:5]],
                   oracle_post=round(float(post[okey]), 4), mean_out=inf.get('mean_out'),
                   p_outlier=[(cur[i], round(float(p_out[i]), 3)) for i in range(len(cur))],
                   viol_by_revealed={k: dict(pairs=v['pairs'], exp_viol=round(v['exp_viol'], 2),
                                             ages=sorted(v['ages'])) for k, v in by_rev.items()},
                   rows=rows, n_flp=len(st['flp']), free=[cur[i] for i in st['free']])
        if tenpai and cn is not None:
            e = paifu['events'][st_['ev']]
            truth = np.bincount([tid(x) for x in e['hand']], minlength=34)
            tw = list(PI.fast_waits(tuple(int(x) for x in truth)))
            mm = sm_metrics(cn, None, pub['unseen'], truth, True, sorted(set(t // 9 for t in tw)))
            rec['wsuit'] = mm['wsuit']
            rec['waits'] = [tname(t) for t in tw]
        out['steps'].append(rec)
        print(json.dumps(rec, ensure_ascii=False, default=str), flush=True)
    json.dump(out, open(os.path.join(OUT, 'r16_check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              default=str)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1]
    if cmd == 'check':
        cmd_check()
    elif cmd == 'run':
        cmd_run(max(1, (os.cpu_count() or 2) - 2), sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == 'leak':
        cmd_leak()
    elif cmd == 'r16':
        cmd_r16()
    elif cmd == 'report':
        report()


# ================================================================ 표 · LOGO · 판정
COND = ['A', 'B', 'Cmix', 'Q', 'QB']
BINS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0000001]


def _get(r, c):
    """설정 c 의 지표. 없음(표본 0)이면 A 로 대신(가정 깨짐 표시)."""
    m = r['cfg'].get(c)
    if m is None:
        return dict(r['cfg']['A'], fallback='A', broken=True)
    return m


AVAIL = None


def _cands(cond):
    c = _cands0(cond)
    return [x for x in c if AVAIL is None or x in AVAIL]


def _cands0(cond):
    if cond == 'B':
        return [f'B|{g}' for g in GAMMAS]
    if cond == 'Q':
        return ['Q|' + cfg_name(p) for p in QGRID]
    if cond == 'QB':
        return [f'QB|{cfg_name(p)}|{g}' for p in QGRID for g in GAMMAS]
    return [{'A': 'A', 'Cmix': 'Cmix'}[cond]]


def _gm(rows, c, key='logs', rel=True):
    v = [(_get(r, c)[key] - (r['cfg']['A'][key] if rel else 0)) for r in rows]
    return float(np.mean(v))


def logo(main, games):
    chosen = {}
    by = {g: [r for r in main if r['game'] == g] for g in games}
    for g_out in games + ['ALL']:
        ch = {}
        for cond in COND:
            best = None
            for c in _cands(cond):
                v = float(np.mean([_gm(by[g], c) for g in games if g != g_out]))
                if best is None or round(v, 9) > round(best[0], 9):
                    best = (v, c)
            ch[cond] = best[1]
        chosen[g_out] = ch
    return chosen


def _prm_of(c):
    return [float(x) for x in c.split('|')[1:]]


def _mean_rel(rs, chosen, cond, key):
    if key == 'logs':
        return float(np.mean([_get(r, chosen[r['game']][cond])['logs'] - r['cfg']['A']['logs'] for r in rs]))
    return float(np.mean([_get(r, chosen[r['game']][cond])[key] for r in rs]))


def report():
    sys.stdout.reconfigure(encoding='utf-8')
    rows = [json.loads(x) for x in open(os.path.join(OUT, 'turns.jsonl'), encoding='utf-8')]
    main = sorted([r for r in rows if r['tag'] == 'main'], key=lambda r: (r['game'], r['step']))
    tp = [r for r in rows if r['tag'] == 'tp']
    games = PI.GAMES
    global AVAIL
    AVAIL = set(main[0]['cfg'])
    chosen = logo(main, games)
    L = []
    P = L.append
    P('# 부드러운 정렬 모델 Q — 진짜 칸 번호 8판 (계획서 9절)\n')
    P(f'- 차례 {len(main)}(posinfer 와 같은 차례, 리치 선언 차례 {sum(r["riichi"] for r in main)}개는 텐파이 표본) + 텐파이 '
      f'알려 준 시점 {len(tp)}개(L16 first_stay_tenpai · r18 · r14 리치, ⑤ 전용).')
    P(f'- 표본: 텐파이 조건 없는 차례 {N_S}개(A · B 정확 표본, C*mix · Q DP 정확 표본), 텐파이 차례 채택 목표 {N_ACC} '
      f'(A · B 최대 {MAXDRAW_A:,} → 30 미만이면 4 배, Q 최대 {MAXDRAW:,} → 10 배, C*mix 는 posinfer 그대로). '
      'p1 = (ESS·p̂ + 0.5)/(ESS + 1)(posinfer 와 같은 평활). QB 는 Q 표본 중요도 가중.')
    P(f'- 격자: ε {EPSS} · δ0 {D0S} · λ {LAMS}(27), B · QB 의 γ {GAMMAS}. **판 하나 빼고 고르기**(나머지 7판의 '
      '판 평균 ① 로그 점수 차(A 대비)의 평균이 가장 큰 것).')
    ck = os.path.join(OUT, 'check.json')
    if os.path.exists(ck):
        c = json.load(open(ck, encoding='utf-8'))
        P(f'- 검사: DP == 무차별 대입(근사 규칙) 최대 상대 오차 {max(x["rel_err"] for x in c["brute"]):.1e}; 뒤집힘 근사 규칙 대 '
          f'원래 규칙 차 {min(x["approx_vs_exact"] for x in c["brute"]) * 100:.0f}% ~ 0%(ε 0.2 작은 예); 하드 극한 '
          f'(ε→0 · δ0→0 · λ=1) 키 우도 == C*mix {sum(x["ok"] for x in c["hard"])}/{len(c["hard"])} 차례; 제약 없음 Z = '
          f'{[round(z, 6) for z in c["free"]]}; 표본 평균 == 무차별 {c["sampler"]}; 10장 손 묶음 텐파이 판정 어긋남 '
          f'{c["tenpai_batch10"]["mismatch"]}/{c["tenpai_batch10"]["n"]}.')
    P('\n## 고른 세기(판 하나 빼고)\n')
    P('| 뺀 판 | B γ | Q (ε, δ0, λ) | QB (ε, δ0, λ, γ) |')
    P('|---|---|---|---|')
    for g in games + ['ALL']:
        ch = chosen[g]
        P(f'| {g if g != "ALL" else "(8판 전부 — r18 · r14 용)"} | {_prm_of(ch["B"])[0]} | {tuple(_prm_of(ch["Q"]))} | '
          f'{tuple(_prm_of(ch["QB"]))} |')
    # ---- 판 단위
    P('\n## 판 단위 (판 안 차례 평균) — ① 로그 점수 A 대비 차 · ② 수트 장수 오차 · ④ 가정 깨짐\n')
    P('| 판 | 차례 | 정렬 정도(키) | ① B | ① C*mix | ① Q | ① QB | ② A | ② B | ② C*mix | ② Q | ② QB | ④ C*mix | ④ Q | '
      'Q 정답 키 사후 | Q 어긋남 칸 수 |')
    P('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    per = {}
    allv = {c: dict(l=[], s=[]) for c in COND}
    for g in games:
        rs = [r for r in main if r['game'] == g]
        so, kn, _ = PI.sortedness(PI.load(g))
        v = {}
        for cond in COND:
            c = chosen[g][cond]
            ls = [_get(r, c)['logs'] - r['cfg']['A']['logs'] for r in rs]
            se = [_get(r, c)['suit_err'] for r in rs]
            v[cond] = (float(np.mean(ls)), float(np.mean(se)))
            allv[cond]['l'] += ls
            allv[cond]['s'] += se
        bc = sum(1 for r in rs if r['cfg']['Cmix'].get('broken'))
        qc = chosen[g]['Q']
        bq = sum(1 for r in rs if r['cfg'].get(qc) is None)
        op = float(np.mean([r['cfg'][qc]['oracle_post'] for r in rs if r['cfg'].get(qc)]))
        mo = float(np.mean([r['cfg'][qc]['mean_out'] for r in rs if r['cfg'].get(qc)]))
        per[g] = dict(v=v, broken_cmix=bc, broken_q=bq, so=so, key=kn, oracle_post=op, mean_out=mo, n=len(rs))
        P(f'| {g} | {len(rs)} | {so:.2f} ({kn}) | ' + ' | '.join(f'{v[c][0]:+.4f}' for c in COND[1:]) + ' | '
          + ' | '.join(f'{v[c][1]:.2f}' for c in COND) + f' | {bc} | {bq} | {op:.2f} | {mo:.2f} |')
    n = len(main)
    P(f'| **전체(차례 평균, n={n})** | {n} | | ' + ' | '.join(f'**{np.mean(allv[c]["l"]):+.4f}**' for c in COND[1:]) + ' | '
      + ' | '.join(f'**{np.mean(allv[c]["s"]):.2f}**' for c in COND)
      + f' | {sum(p["broken_cmix"] for p in per.values())} | {sum(p["broken_q"] for p in per.values())} | | |')
    P('| 판 평균의 평균 | | | ' + ' | '.join(f'{np.mean([per[g]["v"][c][0] for g in games]):+.4f}' for c in COND[1:])
      + ' | ' + ' | '.join(f'{np.mean([per[g]["v"][c][1] for g in games]):.2f}' for c in COND) + ' | | | | |')
    P('\n(① 은 34종 "1장 이상" 확률 로그 우도의 34종 평균에서 A 를 뺀 값, 클수록 좋음. ② 는 만 · 통 · 삭 · 자 기대 장수와 실제의 '
      '절대 오차 합, 작을수록 좋음. C*mix 가정 깨짐 차례는 A 로 채점. 정렬 정도는 정답 줄 전체에서 가장 맞는 키의 이웃 짝 비율 — 서술용. '
      'Q 정답 키 사후 · 어긋남 칸 수는 진단(정답 키 = 정렬 정도의 키).)')
    # ---- 판정
    lq, lb = float(np.mean(allv['Q']['l'])), float(np.mean(allv['B']['l']))
    wins_l = sum(1 for g in games if per[g]['v']['Q'][0] > per[g]['v']['B'][0])
    wins_s = sum(1 for g in games if per[g]['v']['Q'][1] < per[g]['v']['B'][1])
    brk = sum(p['broken_q'] for p in per.values())
    ok = brk == 0 and lq > lb and wins_l >= 6 and wins_s >= 6
    why = []
    if brk:
        why.append(f'④ Q 깨짐 {brk}')
    if not lq > lb:
        why.append(f'① 차례 평균 Q {lq:+.4f} ≤ B {lb:+.4f}')
    if wins_l < 6:
        why.append(f'① Q > B 판 {wins_l}/8 < 6')
    if wins_s < 6:
        why.append(f'② Q 수트 오차 < B 판 {wins_s}/8 < 6')
    verdict = ('부드러운 모델이 진짜 칸 번호에서 정보를 건짐 → 다음에 천봉 흉내(+ 버릴 패 빼 두기 습관)로 참고 측정' if ok
               else '기준 못 미침(' + '; '.join(why) + ') → 까닭을 적고 사용자에게 물음')
    P(f'\n## 판정(9절 기준 그대로)\n\n④ Q 깨짐 {brk}차례 · ① 차례 평균 Q {lq:+.4f} vs B {lb:+.4f}(Q − B {lq - lb:+.4f}) · '
      f'① Q > B {wins_l}/8판 · ② Q 수트 오차 < B {wins_s}/8판 → **{verdict}**')
    P(f'\n참고: QB − B ① {np.mean(allv["QB"]["l"]) - lb:+.4f}(QB > B '
      f'{sum(1 for g in games if per[g]["v"]["QB"][0] > per[g]["v"]["B"][0])}/8판, QB 수트 오차 < B '
      f'{sum(1 for g in games if per[g]["v"]["QB"][1] < per[g]["v"]["B"][1])}/8판), Q − C*mix ① '
      f'{lq - np.mean(allv["Cmix"]["l"]):+.4f}(Q > C*mix {sum(1 for g in games if per[g]["v"]["Q"][0] > per[g]["v"]["Cmix"][0])}/8판), '
      f'② Q {np.mean(allv["Q"]["s"]):.2f} vs B {np.mean(allv["B"]["s"]):.2f} vs C*mix {np.mean(allv["Cmix"]["s"]):.2f} '
      f'vs A {np.mean(allv["A"]["s"]):.2f}.')
    full = [g for g in games if per[g]['so'] >= 1.0]
    part = [g for g in games if per[g]['so'] < 1.0]
    for nm, gs in (('완전 정렬(1.00)', full), ('정렬 < 1', part)):
        rs = [r for r in main if r['game'] in gs]
        P(f'- {nm} {", ".join(g[:3] for g in gs)}(차례 {len(rs)}): ① '
          + ', '.join(f'{c} {_mean_rel(rs, chosen, c, "logs"):+.4f}' for c in COND[1:]) + ' · ② '
          + ', '.join(f'{c} {_mean_rel(rs, chosen, c, "suit_err"):.2f}' for c in COND))
    # ---- 보정
    P('\n## ③ 보정 — 34종 "1장 이상" 확률 구간별 실제 비율(남은 패 > 0 인 종류, 123차례 모음, 판마다 고른 설정)\n')
    P('칸: 실제 비율 (구간 안 평균 확률, 개수).\n')
    P('| 조건 | ' + ' | '.join(f'{BINS[i]:.1f}~{min(BINS[i + 1], 1):.1f}' for i in range(5)) + ' | ECE |')
    P('|---|---|---|---|---|---|---|')
    calib = {}
    for cond in COND:
        ps, ys = [], []
        for r in main:
            m_ = _get(r, chosen[r['game']][cond])
            un = np.array(r['unseen'])
            tr = np.array(r['truth'])
            p1 = np.array(m_['p1'])
            sel = un > 0
            ps += p1[sel].tolist()
            ys += (tr[sel] >= 1).astype(float).tolist()
        ps, ys = np.array(ps), np.array(ys)
        cells, ece, cb = [], 0.0, []
        for i in range(5):
            s = (ps >= BINS[i]) & (ps < BINS[i + 1])
            if s.sum():
                cells.append(f'{ys[s].mean():.2f} ({ps[s].mean():.2f}, {int(s.sum())})')
                ece += s.sum() / len(ps) * abs(ys[s].mean() - ps[s].mean())
                cb.append([int(s.sum()), float(ps[s].mean()), float(ys[s].mean())])
            else:
                cells.append('—')
                cb.append([0, None, None])
        calib[cond] = dict(bins=cb, ece=float(ece))
        P(f'| {cond} | ' + ' | '.join(cells) + f' | {ece:.3f} |')
    # ---- 텐파이 시점
    P('\n## ⑤ 텐파이를 아는 시점 — 대기 수트 확률(m / p / s / z) · 1위(서술만)\n')
    P('리치 7 은 그 차례의 텐파이 표본 그대로, L16 (tp) 은 first_stay_tenpai 걸음에 "텐파이" 를 알려 준 표본, r18 · r14 는 Opus 가 '
      '읽은 줄(정답 아님, 방향만) — 세기는 8판 전부로 고른 값. ✓ 1위가 정답 대기 수트, ½ 동률. 채택 수 30 미만 ⚠.\n')
    P('| 판 | 걸음 | 정답 대기(수트) | ' + ' | '.join(COND) + ' | 채택 A/Q/C*mix |')
    P('|---|---|---|---|---|---|---|---|---|')
    tpl = [r for r in main if r['riichi']] + sorted(tp, key=lambda r: r['game'])
    tp_out = []
    for r in tpl:
        g = r['game']
        ch = chosen[g] if g in games else chosen['ALL']
        cells = []
        rec = dict(game=g, step=r['step'], tag=r['tag'], waits=r['waits'], wsuits=r['wsuits'], cond={})
        for cond in COND:
            m_ = _get(r, ch[cond])
            ws = m_.get('wsuit')
            if ws is None:
                cells.append('—')
                continue
            top = 'mpsz'[int(np.argmax(ws))]
            hit = m_['wsuit_top1']
            cells.append('/'.join(f'{x:.2f}' for x in ws) + f' → {top}{" ✓" if hit == 1 else (" ½" if hit > 0 else " ✗")}'
                         + (' (A 대신)' if m_.get('fallback') else ''))
            rec['cond'][cond] = dict(wsuit=ws, top=top, hit=hit, fallback=bool(m_.get('fallback')))
        acc = r['acc']
        qa = acc.get(ch['Q'], [0, 0])

        def fa(x):
            return f'{x[0]}' + (' ⚠' if x[0] < 30 else '')
        cells.append(f'{fa(acc["A"])}/{fa(qa)}/' + ('깨짐' if r['cfg']['Cmix'].get('broken') else fa(acc['Cmix'])))
        P(f'| {g[:3]}{"" if r["tag"] == "main" else " (tp)"} | {r["step"]} | {",".join(r["waits"])} '
          f'({"".join("mpsz"[s] for s in r["wsuits"])}) | ' + ' | '.join(cells) + ' |')
        rec['acc'] = dict(A=acc['A'], Q=qa, Cmix=acc['Cmix'])
        tp_out.append(rec)
    eight = [x for x in tp_out if x['game'] in games]
    P('\n1위 적중(8 사례: 리치 7 + L16): ' + ', '.join(
        f'{c} {sum(x["cond"][c]["hit"] for x in eight if c in x["cond"]):.1f}/{len(eight)}' for c in COND)
      + ' · 정답 대기 수트 확률 평균(여럿이면 큰 쪽): ' + ', '.join(
        f'{c} {np.mean([max(x["cond"][c]["wsuit"][s] for s in x["wsuits"]) for x in eight if c in x["cond"]]):.2f}'
        for c in COND))
    # ---- 격자
    P('\n## 격자(123차례 평균 ① · ②, 세기마다 — 고르기 전 전체)\n')
    for c in _cands('B') + _cands('Q'):
        P(f'- {c}: ① {np.mean([_get(r, c)["logs"] - r["cfg"]["A"]["logs"] for r in main]):+.4f} · ② '
          f'{np.mean([_get(r, c)["suit_err"] for r in main]):.2f} · 깨짐 {sum(1 for r in main if r["cfg"].get(c) is None)}')
    bestqb = sorted(_cands('QB'), key=lambda c: -np.mean([_get(r, c)['logs'] - r['cfg']['A']['logs'] for r in main]))[:5]
    P('- QB 상위 5: ' + '; '.join(
        f'{c} ① {np.mean([_get(r, c)["logs"] - r["cfg"]["A"]["logs"] for r in main]):+.4f}' for c in bestqb))
    P(f'- C*mix: ① {np.mean([_get(r, "Cmix")["logs"] - r["cfg"]["A"]["logs"] for r in main]):+.4f} · ② '
      f'{np.mean([r["cfg"]["Cmix"]["suit_err"] for r in main]):.2f} · 깨짐 {sum(1 for r in main if r["cfg"]["Cmix"].get("broken"))}')
    lk = os.path.join(OUT, 'leak.json')
    if os.path.exists(lk):
        d = json.load(open(lk, encoding='utf-8'))
        tot = sum(v['turns'] for v in d.values())
        sm = sum(v['obs_same'] for v in d.values())
        ss = [s for v in d.values() for s in v['samples']]
        P(f'\n## 누설 검사\n\n숨은 패를 서로 다른 가짜 종류로 바꾼 패보(시점까지 자름): 나이 붙은 관찰 같음 {sm}/{tot} 차례({len(d)}판), '
          f'Q 표본(같은 씨) 같음 {sum(s["q_same"] for s in ss)}/{len(ss)}(마지막 · 리치 · L16 텐파이 걸음, 텐파이 '
          f'{sum(s["tenpai"] for s in ss)}개 포함), 공개 정보 같음 {sum(s["pub_same"] for s in ss)}/{len(ss)}.')
    nf = os.path.join(OUT, 'turns_noflag.jsonl')
    if os.path.exists(nf):
        rows2 = [json.loads(x) for x in open(nf, encoding='utf-8')]
        main2 = [r for r in rows2 if r['tag'] == 'main']
        AVAIL = set(main2[0]['cfg'])
        ch2 = logo(main2, games)
        AVAIL = set(main[0]['cfg'])
        pg = {}
        for g in games:
            rs = [r for r in main2 if r['game'] == g]
            pg[g] = {c: (np.mean([_get(r, ch2[g][c])['logs'] - r['cfg']['A']['logs'] for r in rs]),
                         np.mean([_get(r, ch2[g][c])['suit_err'] for r in rs])) for c in ('B', 'Q', 'QB')}
        lq2 = np.mean([_get(r, ch2[r['game']]['Q'])['logs'] - r['cfg']['A']['logs'] for r in main2])
        lb2 = np.mean([_get(r, ch2[r['game']]['B'])['logs'] - r['cfg']['A']['logs'] for r in main2])
        sq2 = np.mean([_get(r, ch2[r['game']]['Q'])['suit_err'] for r in main2])
        P('\n## 민감도 — 끝 붙임 표시 없이 돌린 첫 실행(격자 ε (0.03, 0.1, 0.25) · δ0 (0.03, 0.15, 0.5) · λ 같음)\n\n'
          f'Q ① {lq2:+.4f} vs B {lb2:+.4f}, Q > B {sum(1 for g in games if pg[g]["Q"][0] > pg[g]["B"][0])}/8판, '
          f'② Q {sq2:.2f}, Q 수트 오차 < B {sum(1 for g in games if pg[g]["Q"][1] < pg[g]["B"][1])}/8판, 깨짐 '
          f'{sum(1 for r in main2 if r["cfg"].get(ch2[r["game"]]["Q"]) is None)}; 판별 ① Q: '
          + ', '.join(f'{g[:3]} {pg[g]["Q"][0]:+.3f}' for g in games) + ' (고른 Q: '
          + ', '.join(sorted(set(ch2[g]['Q'] for g in games))) + ').')
    r16 = os.path.join(OUT, 'r16_check.json')
    if os.path.exists(r16):
        d = json.load(open(r16, encoding='utf-8'))
        P(f'\n## 손으로 확인 — r16(세기 {d["prm"]}, 정답 키 {d["oracle_key"]})\n')
        for s in d['steps']:
            P(f'- 걸음 {s["step"]}{" (리치, 텐파이 표본)" if s["tenpai"] else ""}: 지금 줄 {" ".join(s["cur"])}'
              f' (끝 붙임 자유 칸 {s.get("free")}); 키 사후 상위 '
              f'{s["key_top"][:3]}, 정답 키 {s["oracle_post"]}; 어긋남 칸 평균 {s["mean_out"]:.2f}; 칸별 어긋남 확률 '
              + ', '.join(f'{t} {p:.2f}' for t, p in s['p_outlier'] if p >= 0.15)
              + '; 공개 패별 어긴 경계 짝 기대 수 ' + ', '.join(
                  f'{k} {v["exp_viol"]}/{v["pairs"]}(나이 {v["ages"]})' for k, v in s['viol_by_revealed'].items()
                  if v['exp_viol'] >= 0.3)
              + (f'; 대기 {s.get("waits")} 수트 확률 {s.get("wsuit")}' if s['tenpai'] else ''))
    txt = '\n'.join(L)
    print(txt)
    with open(os.path.join(OUT, 'summary.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(txt + '\n')
    json.dump(dict(chosen={g: {c: (_prm_of(v) if c in ('B', 'Q', 'QB') else v) for c, v in ch.items()}
                           for g, ch in chosen.items()},
                   per_game=per, calib=calib, tenpai=tp_out, verdict=verdict,
                   overall={c: dict(logs=float(np.mean(allv[c]['l'])), suit=float(np.mean(allv[c]['s']))) for c in COND}),
              open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
