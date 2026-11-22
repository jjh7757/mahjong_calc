"""1단계 맞추기 — 엔진 후보 값의 구간별 가중합(F) · 부드러운 정답 F · 자유 모델 U (2026-11-21, 설계서 11-3 · 11-4).

이 파일은 맞춤 140판 · 고르기 20판만 연다(pack 의 part 가 'val' 인 줄은 읽자마자 버린다). 검증은 eval_val.py.

값(11-3) — make_values() 하나가 맞춤 · 고르기 · 검증 모두에서 만든다.
  지키는 후보 = 버린 뒤 샹텐이 그 차례 최소, 물러나는 후보 = 그보다 큼.
  back · dWaits · dImprove · dNextWaits · dSpeed(지키는 후보끼리 최댓값과의 차, 물러나는 후보 0, ÷10)
  dAgari(지키는 후보 중 버린 뒤 텐파이끼리 화료율 차, ÷10 %p) · dRound(지키는 후보끼리 국수지 차, ÷1000)
  furiten(후리텐 가능성) · backSpeed(물러나는 후보 속도 − 지키는 후보 최고 속도, 지키는 후보 0, ÷10)
  dRisk(위험 − 후보 중 최소 위험, ÷10 %p) · safeAll · dora · red · yakuhai · guestWind · terminal · honor · edge(|n−5|/4)
  null · NaN 은 차를 낼 때 빼고 그 후보 값은 0.

식(11-4) — 구간 = 버리기 전 샹텐(−1·0 / 1 / 2 / 3+) × 위협(riskSeats 비었음 / 있음) = 8.
  점수 = Σ w[구간, 값] × 값, 손실 = 평균 교차 엔트로피 + L2 × Σ w². 맞춤 140판에서 L-BFGS(전체 배치, 0 에서 시작,
  float64, 기울기 최대 < 1e-6 이면 멈춤 · 최대 5,000번). torch 스레드 16 고정(스레드 수가 다르면 끝자리가 다를 수 있음).
  구간에서 맞춤 자료의 값이 늘 0 인 칸은 가중치를 두지 않는다(0 고정).
  L2 ∈ {0, 1e-4, 1e-3, 1e-2} 는 고르기 20판 첫째 일치로(같으면 큰 L2).
  동률: 점수가 같은 후보는 패 번호 순 앞 패(엄격). S42 패가 최고 점수와 1e-9 안이면 "동률 포함".
부드러운 정답: softmax(Q/τ), τ ∈ {0.1, 0.3, 1.0} 을 고르기 20판 첫째 일치로(L2 는 F 에서 고른 값 그대로).
U: 같은 18개 값 + 문맥(샹텐 · 위협 · 자기 버림 번호 · 멘젠 · 친) → 은닉 64 × 2 → 후보 점수 → softmax.
  Adam(전체 배치), 고르기 20판 교차 엔트로피가 가장 낮은 걸음에서 멈춤(25걸음마다 봄, 20번 안 나아지면 끝).
값 묶음 빼기 · 패 성질만 · 구간 없음 F: 같은 맞추기, L2 는 각자 고르기 20판에서.
안정성: 맞춤 140판을 판 단위로 20번 다시 뽑아(씨 20261121) 고른 L2 로 다시 맞춤.

쓰기: python -X utf8 fit.py --pack pack.jsonl.gz --out-dir stage1
산출: weights.json · weights.md · fit_report.json · fit_report.md · u_model.pt
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from pathlib import Path

import numpy as np
import torch

SEED = 20261121
VALUES = ['back', 'dWaits', 'dImprove', 'dNextWaits', 'dSpeed', 'dAgari', 'dRound', 'furiten', 'backSpeed',
          'dRisk', 'safeAll', 'dora', 'red', 'yakuhai', 'guestWind', 'terminal', 'honor', 'edge']
SCALE = {'dWaits': 10.0, 'dImprove': 10.0, 'dNextWaits': 10.0, 'dSpeed': 10.0, 'dAgari': 10.0, 'dRound': 1000.0,
         'backSpeed': 10.0, 'dRisk': 10.0}
UNIT = {'dWaits': '장', 'dImprove': '장', 'dNextWaits': '장', 'dSpeed': '점', 'dAgari': '%p', 'dRound': '점',
        'backSpeed': '점', 'dRisk': '%p'}
GROUPS = {'speed': ['back', 'dWaits', 'dImprove', 'dNextWaits', 'dSpeed', 'backSpeed'],
          'value': ['dAgari', 'dRound', 'furiten'],
          'defense': ['dRisk', 'safeAll'],
          'tile': ['dora', 'red', 'yakuhai', 'guestWind', 'terminal', 'honor', 'edge']}
GROUP_KO = {'speed': '속도', 'value': '타점', 'defense': '수비', 'tile': '패 성질'}
SH_BINS = ['0', '1', '2', '3+']
BINS = [f'{s}/{t}' for s in SH_BINS for t in ('없음', '있음')]  # 샹텐 / 위협
L2_GRID = [0.0, 1e-4, 1e-3, 1e-2]
TAU_GRID = [0.1, 0.3, 1.0]
TIE_EPS = 1e-9
CTX_NAMES = ['shantenBefore/3', 'threat', 'junme/18', 'menzen', 'dealer']

# pack.py 의 CAND_FIELDS 순서
F_TILE, F_SH, F_WAITS, F_IMP, F_NEXT, F_SPEED, F_AGARI, F_ROUND, F_FURI, F_RISK, F_SAFE, F_DORA, F_RED, F_YAKU, \
    F_GUEST, F_TERM, F_HONOR, F_BACKWARD = range(18)


def _num(v) -> float:
    if v is None or isinstance(v, bool):
        return float('nan') if v is None else float(v)
    x = float(v)
    return x if math.isfinite(x) else float('nan')


def _diff_to_max(vals: np.ndarray, sel: np.ndarray) -> np.ndarray:
    """sel 인 후보끼리(NaN 뺌) 최댓값과의 차. 나머지 · NaN 은 0."""
    ok = sel & ~np.isnan(vals)
    out = np.zeros(len(vals))
    if ok.any():
        out[ok] = vals[ok] - vals[ok].max()
    return out


def make_values(cands: list[list]) -> np.ndarray:
    """한 결정의 후보들(pack 의 cands, 패 번호 순) → [후보 수, 18] 값(11-3, 눈금으로 나눈 것)."""
    n = len(cands)
    col = lambda i: np.array([_num(c[i]) for c in cands])  # noqa: E731
    sh = col(F_SH)
    keep = sh == np.nanmin(sh)
    back = ~keep
    X = np.zeros((n, len(VALUES)))
    X[:, 0] = back
    for j, fi in ((1, F_WAITS), (2, F_IMP), (3, F_NEXT), (4, F_SPEED)):
        X[:, j] = _diff_to_max(col(fi), keep)
    X[:, 5] = _diff_to_max(col(F_AGARI), keep & (sh == 0))
    X[:, 6] = _diff_to_max(col(F_ROUND), keep)
    fr = col(F_FURI)
    X[:, 7] = np.where(np.isnan(fr), 0.0, fr)
    sp = col(F_SPEED)
    ks = sp[keep & ~np.isnan(sp)]
    if ks.size:
        ok = back & ~np.isnan(sp)
        X[ok, 8] = sp[ok] - ks.max()
    rk = col(F_RISK)
    okr = ~np.isnan(rk)
    if okr.any():
        X[okr, 9] = rk[okr] - rk[okr].min()
    for j, fi in ((10, F_SAFE), (11, F_DORA), (12, F_RED), (13, F_YAKU), (14, F_GUEST), (15, F_TERM), (16, F_HONOR)):
        v = col(fi)
        X[:, j] = np.where(np.isnan(v), 0.0, v)
    for i, c in enumerate(cands):
        t = c[F_TILE]
        X[i, 17] = 0.0 if t[1] == 'z' else abs(int(t[0]) - 5) / 4.0
    for j, name in enumerate(VALUES):
        X[:, j] /= SCALE.get(name, 1.0)
    return X


def bin_index(shanten_before: int, threat: bool) -> int:
    s = 0 if shanten_before <= 0 else min(shanten_before, 3)
    return s * 2 + int(bool(threat))


def context(row: dict) -> list[float]:
    sb = max(-1, min(6, row['shantenBefore']))
    return [sb / 3.0, float(bool(row['riskSeats'])), row['junme'] / 18.0, float(row['menzen']), float(row['dealer'])]


def load_pack(path: str, parts: set[str]) -> list[dict]:
    out = []
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r['part'] in parts:
                out.append(r)
    return out


class Data:
    """결정들 → 채운 텐서. 후보는 패 번호 순, 빈 칸은 mask=False."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        n = len(rows)
        cmax = max(len(r['cands']) for r in rows)
        D = len(VALUES)
        X = np.zeros((n, cmax, D))
        mask = np.zeros((n, cmax), bool)
        Q = np.full((n, cmax), np.nan)
        y = np.zeros(n, np.int64)
        b = np.zeros(n, np.int64)
        ctx = np.zeros((n, len(CTX_NAMES)))
        for i, r in enumerate(rows):
            c = len(r['cands'])
            X[i, :c] = make_values(r['cands'])
            mask[i, :c] = True
            Q[i, :c] = [np.nan if q is None else q for q in r['q']]
            tiles = [cc[F_TILE] for cc in r['cands']]
            y[i] = tiles.index(r['s42'])
            b[i] = bin_index(r['shantenBefore'], bool(r['riskSeats']))
            ctx[i] = context(r)
        self.X, self.mask, self.Q, self.y, self.bin, self.ctx = X, mask, Q, y, b, ctx
        self.games = [r['game'] for r in rows]
        self.tiles = [[cc[F_TILE] for cc in r['cands']] for r in rows]

    def subset(self, idx: np.ndarray) -> 'Data':
        d = object.__new__(Data)
        d.rows = [self.rows[i] for i in idx]
        for k in ('X', 'mask', 'Q', 'y', 'bin', 'ctx'):
            setattr(d, k, getattr(self, k)[idx])
        d.games = [self.games[i] for i in idx]
        d.tiles = [self.tiles[i] for i in idx]
        return d


def soft_target(d: Data, tau: float) -> np.ndarray:
    q = np.where(d.mask & ~np.isnan(d.Q), d.Q, -np.inf) / tau
    q = q - q.max(axis=1, keepdims=True)
    e = np.exp(q)
    return e / e.sum(axis=1, keepdims=True)


# ---------------------------------------------------------------- F(가중합)
def weight_mask(d: Data, cols: list[int], n_bins: int, bins: np.ndarray) -> np.ndarray:
    """[구간, 값] 에 가중치를 둘지 — 맞춤 자료에서 그 구간의 값이 늘 0 이면 두지 않음. cols 밖의 값도 두지 않음."""
    M = np.zeros((n_bins, len(VALUES)), bool)
    for bi in range(n_bins):
        sel = bins == bi
        if not sel.any():
            continue
        xs = d.X[sel][d.mask[sel]]  # [후보 수, D]
        nz = (np.abs(xs) > 0).any(axis=0)
        M[bi, cols] = nz[cols]
    return M


def scores_np(X: np.ndarray, mask: np.ndarray, bins: np.ndarray, W: np.ndarray) -> np.ndarray:
    s = np.einsum('ncd,nd->nc', X, W[bins])
    return np.where(mask, s, -np.inf)


def fit_linear(d: Data, cols: list[int], l2: float, single_bin: bool = False, target: np.ndarray | None = None,
               sample_w: np.ndarray | None = None, Mfix: np.ndarray | None = None) -> dict:
    """가중합 F 를 맞춘다. target 없으면 S42 첫째(정답 한 패), 있으면 부드러운 정답 분포."""
    torch.manual_seed(SEED)
    n_bins = 1 if single_bin else len(BINS)
    bins = np.zeros(len(d.y), np.int64) if single_bin else d.bin
    M = Mfix if Mfix is not None else weight_mask(d, cols, n_bins, bins)
    X = torch.tensor(d.X, dtype=torch.float64)
    mask = torch.tensor(d.mask)
    bt = torch.tensor(bins)
    bt_g = bt[:, None, None].expand(X.shape[0], X.shape[1], 1)
    Mt = torch.tensor(M, dtype=torch.float64)
    if target is None:
        T = torch.zeros(d.mask.shape, dtype=torch.float64)
        T[torch.arange(len(d.y)), torch.tensor(d.y)] = 1.0
    else:
        T = torch.tensor(target, dtype=torch.float64)
    sw = torch.ones(len(d.y), dtype=torch.float64) if sample_w is None else torch.tensor(sample_w, dtype=torch.float64)
    sw = sw / sw.sum()
    W = torch.zeros((n_bins, len(VALUES)), dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([W], lr=1.0, max_iter=1000, tolerance_grad=1e-7, tolerance_change=1e-12,
                            history_size=50, line_search_fn='strong_wolfe')

    def loss_fn():
        Wm = W * Mt
        # 모든 구간의 점수를 행렬곱으로 낸 뒤 그 결정의 구간만 고른다(= Σ_d X[n,c,d] · Wm[bin[n], d])
        s_all = X @ Wm.T  # [N, C, 구간]
        s = torch.gather(s_all, 2, bt_g).squeeze(-1)
        s = s.masked_fill(~mask, -1e300)
        logp = torch.log_softmax(s, dim=1)
        ce = -(T * torch.where(mask, logp, torch.zeros_like(logp))).sum(1)
        return (sw * ce).sum() + l2 * (Wm ** 2).sum(), (sw * ce).sum()

    def closure():
        opt.zero_grad()
        loss, _ = loss_fn()
        loss.backward()
        return loss

    for _ in range(5):  # max_iter 1,000 을 몇 번 — 기울기가 작아지면 멈춤
        opt.step(closure)
        loss, ce = loss_fn()
        gW, = torch.autograd.grad(loss, W)
        if float((gW * Mt).abs().max()) < 1e-6:
            break
    with torch.no_grad():
        loss, ce = loss_fn()
    Wn = (W.detach() * Mt).numpy().copy()
    return {'W': Wn, 'M': M, 'l2': l2, 'single': single_bin, 'cols': cols, 'loss': float(loss), 'ce': float(ce),
            'gradMax': float((gW * Mt).abs().max())}


def predict_linear(model: dict, d: Data) -> np.ndarray:
    bins = np.zeros(len(d.y), np.int64) if model['single'] else d.bin
    return scores_np(d.X, d.mask, bins, model['W'])


# ---------------------------------------------------------------- 지표
def pick_from_scores(S: np.ndarray) -> np.ndarray:
    """최고 점수 후보(동률이면 패 번호 순 앞 — np.argmax 는 첫 번째를 준다)."""
    return S.argmax(axis=1)


def top2_from_scores(S: np.ndarray) -> np.ndarray:
    order = np.argsort(-S, axis=1, kind='stable')  # 같은 점수는 앞 패 먼저
    return order[:, :2]


def first_match(S: np.ndarray, d: Data) -> float:
    return float((pick_from_scores(S) == d.y).mean())


def ce_of(S: np.ndarray, d: Data) -> float:
    s = S - S.max(axis=1, keepdims=True)
    lse = np.log(np.exp(s).sum(axis=1))
    return float(-(s[np.arange(len(d.y)), d.y] - lse).mean())


# ---------------------------------------------------------------- U(자유 모델)
class UNet(torch.nn.Module):
    def __init__(self, d_in: int):
        super().__init__()
        self.net = torch.nn.Sequential(torch.nn.Linear(d_in, 64), torch.nn.ReLU(), torch.nn.Linear(64, 64),
                                       torch.nn.ReLU(), torch.nn.Linear(64, 1))

    def forward(self, x):
        return self.net(x).squeeze(-1)


def u_inputs(d: Data) -> torch.Tensor:
    n, c, _ = d.X.shape
    ctx = np.broadcast_to(d.ctx[:, None, :], (n, c, d.ctx.shape[1]))
    return torch.tensor(np.concatenate([d.X, ctx], axis=-1), dtype=torch.float32)


def u_scores(net: UNet, d: Data) -> np.ndarray:
    with torch.no_grad():
        s = net(u_inputs(d)).double().numpy()
    return np.where(d.mask, s, -np.inf)


def fit_u(fit: Data, sel: Data, lr: float = 3e-3, max_steps: int = 6000, every: int = 25, patience: int = 20) -> dict:
    torch.manual_seed(SEED)
    net = UNet(len(VALUES) + len(CTX_NAMES))
    xf, mf, yf = u_inputs(fit), torch.tensor(fit.mask), torch.tensor(fit.y)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    best = (float('inf'), 0, None)
    hist = []
    bad = 0
    for step in range(1, max_steps + 1):
        opt.zero_grad()
        s = net(xf).masked_fill(~mf, -1e9)
        loss = torch.nn.functional.cross_entropy(s, yf)
        loss.backward()
        opt.step()
        if step % every == 0:
            S = u_scores(net, sel)
            c = ce_of(S, sel)
            hist.append({'step': step, 'fitCE': float(loss.detach()), 'selCE': c, 'selFirst': first_match(S, sel)})
            if c < best[0] - 1e-6:
                best = (c, step, {k: v.clone() for k, v in net.state_dict().items()})
                bad = 0
            else:
                bad += 1
                if bad >= patience:
                    break
    net.load_state_dict(best[2])
    return {'net': net, 'bestStep': best[1], 'bestSelCE': best[0], 'hist': hist, 'lr': lr}


# ---------------------------------------------------------------- 고르기
def choose_l2(fit: Data, sel: Data, cols: list[int], single: bool = False) -> tuple[dict, list[dict]]:
    rows, best = [], None
    for l2 in L2_GRID:
        m = fit_linear(fit, cols, l2, single_bin=single)
        Sf, Ss = predict_linear(m, fit), predict_linear(m, sel)
        r = {'l2': l2, 'fitFirst': first_match(Sf, fit), 'selFirst': first_match(Ss, sel), 'fitCE': ce_of(Sf, fit),
             'selCE': ce_of(Ss, sel), 'gradMax': m['gradMax'], 'nWeights': int(m['M'].sum())}
        rows.append(r)
        if best is None or r['selFirst'] >= best[1]['selFirst']:  # 같으면 큰 L2(뒤에 오는 것)
            best = (m, r)
    return best[0], rows


def model_json(m: dict) -> dict:
    bins = ['전체'] if m['single'] else BINS
    return {'l2': m['l2'], 'bins': bins, 'values': VALUES, 'scale': [SCALE.get(v, 1.0) for v in VALUES],
            'used': m['M'].astype(int).tolist(), 'weights': m['W'].tolist(),
            'weightsPerNaturalUnit': (m['W'] / np.array([SCALE.get(v, 1.0) for v in VALUES])).tolist(),
            'fitLoss': m['loss'], 'fitCE': m['ce'], 'gradMax': m['gradMax'], 'cols': m['cols']}


def _jsonable(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(type(o).__name__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--n-boot', type=int, default=20)
    a = ap.parse_args()
    torch.set_num_threads(16)
    t_all = time.perf_counter()
    out = Path(a.out_dir)
    rows = load_pack(a.pack, {'fit', 'select'})
    fit = Data([r for r in rows if r['part'] == 'fit'])
    sel = Data([r for r in rows if r['part'] == 'select'])
    assert not ({r['game'] for r in fit.rows} & {r['game'] for r in sel.rows})
    rep = {'n': {'fit': len(fit.y), 'select': len(sel.y)},
           'games': {'fit': len(set(fit.games)), 'select': len(set(sel.games))}, 'secs': {}}
    allc = list(range(len(VALUES)))

    t0 = time.perf_counter()
    F, grid = choose_l2(fit, sel, allc)
    rep['F'] = {'grid': grid, 'chosenL2': F['l2']}
    rep['secs']['F'] = time.perf_counter() - t0

    t0 = time.perf_counter()
    soft = []
    best = None
    for tau in TAU_GRID:
        m = fit_linear(fit, allc, F['l2'], target=soft_target(fit, tau))
        Sf, Ss = predict_linear(m, fit), predict_linear(m, sel)
        r = {'tau': tau, 'l2': F['l2'], 'fitFirst': first_match(Sf, fit), 'selFirst': first_match(Ss, sel),
             'gradMax': m['gradMax']}
        soft.append(r)
        if best is None or r['selFirst'] > best[1]['selFirst']:  # 같으면 작은 τ(앞에 오는 것)
            best = (m, r)
    Fsoft = best[0]
    rep['Fsoft'] = {'grid': soft, 'chosenTau': best[1]['tau'], 'l2': F['l2']}
    rep['secs']['Fsoft'] = time.perf_counter() - t0

    t0 = time.perf_counter()
    variants = {}
    for g, names in GROUPS.items():
        cols = [i for i, v in enumerate(VALUES) if v not in names]
        m, gr = choose_l2(fit, sel, cols)
        variants[f'minus_{g}'] = (m, gr)
    tile_cols = [VALUES.index(v) for v in GROUPS['tile']]
    variants['tile_only'] = choose_l2(fit, sel, tile_cols)
    variants['single_bin'] = choose_l2(fit, sel, allc, single=True)
    rep['variants'] = {k: {'grid': gr, 'chosenL2': m['l2']} for k, (m, gr) in variants.items()}
    rep['secs']['variants'] = time.perf_counter() - t0

    t0 = time.perf_counter()
    U = fit_u(fit, sel)
    rep['U'] = {'bestStep': U['bestStep'], 'bestSelCE': U['bestSelCE'], 'lr': U['lr'],
                'fitFirst': first_match(u_scores(U['net'], fit), fit), 'selFirst': first_match(u_scores(U['net'], sel), sel),
                'hist': U['hist']}
    torch.save(U['net'].state_dict(), out / 'u_model.pt')
    rep['secs']['U'] = time.perf_counter() - t0

    # 안정성: 맞춤 140판 판 단위 다시 뽑기, 고른 L2 · 같은 가중치 칸(M)으로
    t0 = time.perf_counter()
    games = sorted(set(fit.games))
    g_idx = {g: i for i, g in enumerate(games)}
    gi = np.array([g_idx[g] for g in fit.games])
    rng = np.random.default_rng(SEED)
    boots = []
    for _ in range(a.n_boot):
        pick = rng.integers(0, len(games), len(games))
        cnt = np.bincount(pick, minlength=len(games)).astype(float)
        w = cnt[gi]
        keep = w > 0
        sub = fit.subset(np.nonzero(keep)[0])
        m = fit_linear(sub, allc, F['l2'], sample_w=w[keep], Mfix=F['M'])
        boots.append(m['W'])
    B = np.stack(boots)  # [nb, bins, D]
    W0 = F['W']
    stab = []
    for bi, bn in enumerate(BINS):
        for j, v in enumerate(VALUES):
            if not F['M'][bi, j]:
                continue
            w0 = W0[bi, j]
            ws = B[:, bi, j]
            flips = int((np.sign(ws) != np.sign(w0)).sum())
            sd = float(ws.std(ddof=1))
            cv = float(sd / abs(w0)) if abs(w0) > 0 else float('inf')
            stab.append({'bin': bn, 'value': v, 'w': float(w0), 'bootMean': float(ws.mean()), 'bootSd': sd,
                         'bootMin': float(ws.min()), 'bootMax': float(ws.max()), 'signFlips': flips, 'cv': cv,
                         'unstable': bool(flips > 0 or cv > 0.3)})
    rep['stability'] = {'nBoot': a.n_boot, 'seed': SEED, 'rule': '부호 뒤집힘(20번 중 한 번이라도 전체 맞춤과 부호 다름) 또는 '
                        '표준편차 / |전체 맞춤 가중치| > 0.3', 'weights': stab,
                        'nUnstable': sum(s['unstable'] for s in stab), 'nWeights': len(stab)}
    rep['secs']['stability'] = time.perf_counter() - t0

    # 맞춤 · 고르기 숫자(과적합 정도)
    rep['fitSelect'] = {}
    for name, S_f, S_s in (('F', predict_linear(F, fit), predict_linear(F, sel)),
                           ('Fsoft', predict_linear(Fsoft, fit), predict_linear(Fsoft, sel)),
                           ('U', u_scores(U['net'], fit), u_scores(U['net'], sel))):
        rep['fitSelect'][name] = {'fitFirst': first_match(S_f, fit), 'selFirst': first_match(S_s, sel),
                                  'fitCE': ce_of(S_f, fit), 'selCE': ce_of(S_s, sel)}
    for name in ('B0', 'B1', 'B2', 'P'):
        rep['fitSelect'][name] = {'fitFirst': float(np.mean([r['base']['hit'][name] for r in fit.rows])),
                                  'selFirst': float(np.mean([r['base']['hit'][name] for r in sel.rows]))}
    rep['secs']['total'] = time.perf_counter() - t_all

    weights = {'seed': SEED, 'note': '설계서 11-3 · 11-4. 점수 = Σ weights[구간][값] × 값(눈금으로 나눈 것). '
               'weightsPerNaturalUnit = weights ÷ scale(1장 · 1점 · 1%p 당).',
               'binRule': '구간 = 버리기 전 샹텐(−1·0→"0" / 1 / 2 / 3+) × 위협(riskSeats 비었음 "없음" / 있음 "있음"), '
                          'index = 샹텐칸 × 2 + 위협',
               'tieRule': '점수가 같으면 패 번호 순(1m..9m 1p..9p 1s..9s 1z..7z) 앞 패. 동률 포함 = S42 패 점수 ≥ 최고 − 1e-9',
               'F': model_json(F), 'Fsoft': {**model_json(Fsoft), 'tau': rep['Fsoft']['chosenTau']},
               'variants': {k: model_json(m) for k, (m, _) in variants.items()},
               'U': {'file': 'u_model.pt', 'inputs': VALUES + CTX_NAMES, 'hidden': [64, 64], 'bestStep': U['bestStep']}}
    (out / 'weights.json').write_text(json.dumps(weights, ensure_ascii=False, indent=1, default=_jsonable), encoding='utf-8')
    (out / 'fit_report.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=_jsonable), encoding='utf-8')
    write_weights_md(out / 'weights.md', F, rep)
    write_fit_md(out / 'fit_report.md', rep)
    print(json.dumps({k: rep[k] for k in ('n', 'games', 'fitSelect', 'secs')}, ensure_ascii=False, indent=1))
    print('F L2', F['l2'], 'Fsoft τ', rep['Fsoft']['chosenTau'], 'unstable', rep['stability']['nUnstable'], '/',
          rep['stability']['nWeights'])


def write_weights_md(path: Path, F: dict, rep: dict):
    st = {(s['bin'], s['value']): s for s in rep['stability']['weights']}
    L = ['# mxfit 1단계 F 가중치(맞춤 140판, L2 = %g)' % F['l2'], '',
         '점수 = Σ w × 값. 값은 눈금으로 나눈 것(11-3). 빈칸 = 그 구간에서 맞춤 자료의 값이 늘 0 이라 가중치를 안 둠.',
         '† = 불안정(판 단위 20번 다시 뽑기에서 부호 뒤집힘 또는 표준편차/|w| > 0.3) — 해석하지 않음(5-5).', '',
         '## 눈금 단위 w', '', '| 값 (눈금) | ' + ' | '.join(BINS) + ' |', '| --- |' + ' --- |' * len(BINS)]
    for j, v in enumerate(VALUES):
        cells = []
        for bi, bn in enumerate(BINS):
            if not F['M'][bi, j]:
                cells.append('')
                continue
            s = st[(bn, v)]
            cells.append(f"{F['W'][bi, j]:+.3f}{'†' if s['unstable'] else ''}")
        L.append(f"| {v} (÷{SCALE.get(v, 1.0):g}) | " + ' | '.join(cells) + ' |')
    L += ['', '## 자연 단위 w ÷ 눈금(1장 · 1점 · 1%p 당; 0/1 값은 그대로)', '',
          '| 값 (단위) | ' + ' | '.join(BINS) + ' |', '| --- |' + ' --- |' * len(BINS)]
    for j, v in enumerate(VALUES):
        cells = []
        for bi, bn in enumerate(BINS):
            if not F['M'][bi, j]:
                cells.append('')
                continue
            s = st[(bn, v)]
            x = F['W'][bi, j] / SCALE.get(v, 1.0)
            cells.append((f'{x:+.5f}' if abs(x) < 0.01 else f'{x:+.3f}') + ('†' if s['unstable'] else ''))
        L.append(f"| {v} ({UNIT.get(v, '0/1 · 겹수')}) | " + ' | '.join(cells) + ' |')
    L += ['', '## 안정성 목록(불안정만)', '', '| 구간 | 값 | w | 다시 뽑기 평균 | 표준편차 | 최소 ~ 최대 | 부호 뒤집힘 | sd/|w| |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for s in rep['stability']['weights']:
        if s['unstable']:
            L.append(f"| {s['bin']} | {s['value']} | {s['w']:+.3f} | {s['bootMean']:+.3f} | {s['bootSd']:.3f} | "
                     f"{s['bootMin']:+.3f} ~ {s['bootMax']:+.3f} | {s['signFlips']}/20 | {s['cv']:.2f} |")
    L.append('')
    L.append(f"불안정 {rep['stability']['nUnstable']} / 가중치 {rep['stability']['nWeights']}")
    path.write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')


def write_fit_md(path: Path, rep: dict):
    pc = lambda x: f'{100 * x:.1f}%'  # noqa: E731
    L = ['# mxfit 1단계 맞춤 · 고르기 보고', '',
         f"맞춤 {rep['games']['fit']}판 {rep['n']['fit']}결정 · 고르기 {rep['games']['select']}판 {rep['n']['select']}결정", '',
         '## F — L2 고르기(고르기 20판 첫째 일치)', '', '| L2 | 맞춤 첫째 | 고르기 첫째 | 맞춤 CE | 고르기 CE | 가중치 수 | grad max |',
         '| --- | --- | --- | --- | --- | --- | --- |']
    for r in rep['F']['grid']:
        L.append(f"| {r['l2']:g} | {pc(r['fitFirst'])} | {pc(r['selFirst'])} | {r['fitCE']:.4f} | {r['selCE']:.4f} | "
                 f"{r['nWeights']} | {r['gradMax']:.1e} |")
    L += ['', f"고른 L2 = {rep['F']['chosenL2']:g}", '', '## F 부드러운 정답 — τ 고르기', '',
          '| τ | 맞춤 첫째 | 고르기 첫째 |', '| --- | --- | --- |']
    for r in rep['Fsoft']['grid']:
        L.append(f"| {r['tau']:g} | {pc(r['fitFirst'])} | {pc(r['selFirst'])} |")
    L += ['', f"고른 τ = {rep['Fsoft']['chosenTau']:g}(L2 {rep['Fsoft']['l2']:g})", '',
          '## 변형 — L2 각자 고르기', '', '| 변형 | 고른 L2 | 맞춤 첫째 | 고르기 첫째 |', '| --- | --- | --- | --- |']
    for k, v in rep['variants'].items():
        r = next(x for x in v['grid'] if x['l2'] == v['chosenL2'])
        L.append(f"| {k} | {v['chosenL2']:g} | {pc(r['fitFirst'])} | {pc(r['selFirst'])} |")
    L += ['', f"## U — 고르기 CE 가 가장 낮은 걸음 {rep['U']['bestStep']}(lr {rep['U']['lr']:g})", '',
          '## 맞춤 · 고르기 첫째 일치', '', '| | 맞춤 | 고르기 |', '| --- | --- | --- |']
    for k, v in rep['fitSelect'].items():
        L.append(f"| {k} | {pc(v['fitFirst'])} | {pc(v['selFirst'])} |")
    L += ['', '## 시간(초)', '', ' · '.join(f'{k} {v:.0f}' for k, v in rep['secs'].items())]
    path.write_text('\n'.join(L) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
