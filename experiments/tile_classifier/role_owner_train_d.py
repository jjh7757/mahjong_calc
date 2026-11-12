"""역할 모델 후보 D(역할 + 주인 자리를 한 번에) 학습·채점 코드(2026-11-12, `docs/role_owner_plan_1111.md` 3-4·3-5·4-2 "D 를 하기로 함 + 설정·기준 확정").
기존 파일(role_set·role_v2_train·role_synth_v3·role_owner_train·role_owner_eval)은 import 만 하고 고치지 않는다.

D = SetNet + 주인 머리(Linear d → 4, 사진(= 입력 토큰) 기준 bottom·right·top·left). 손실 = 지금 역할 손실(가중 CE + OTHER_NEG) +
    1.0 × 주인 CE(주인 라벨 있는 상자만, 클래스 무게 없음, label smoothing 0.05).
입력·회전 = R 과 같다: 장면이 묶음에 뽑힐 때마다 0~3 무작위 회전(turn_tokens, 회전 난수는 따로) — 주인 라벨도 같이 돈다(o → (o − k) mod 4).
사전학습 = 생성기 v4(role_synth_v4) 8,000장면 × 씨드 3(씨드 100 + s), 3 epoch, lr 1e-3.
미세 조정 = 실제 33장(연출 뺌, 주인 = labels_v2_owner.json 의 seat 를 화료자 기준으로) + 변형 사본 3(그중 첫째는 "판 중 흉내"),
    + v4 판 중 : 여럿 펼침 = 2 : 1 장면(수 = 그 겹 학습 묶음 장면 수의 절반, 씨드마다 같은 난수열의 앞부분 = 한 번 만들어 고정), 100 epoch, lr 3e-4, 4겹 + 전부.
주인 라벨이 온라인 변형을 따라가는 방법:
  - role_set.batch: 같은 난수·같은 계산을 batch_owner 로 옮겨 주인도 같은 keep 으로 거른다(test 에서 rs.batch 와 X·Y·pad·난수 상태가 같음을 확인).
  - role_v2_train.augment: 고치지 않고 y 자리에 (역할, 주인) 짝을 넣어 부른다 — augment 는 y 값을 읽지 않고 상자와 함께 옮기기만 하므로
    난수 흐름이 그대로이고 주인이 상자를 따라간다(test 에서 x·y 가 그냥 부른 것과 같음, 주인 = 원래 줄 번호 추적으로 확인).

  python -I -X utf8 experiments/tile_classifier/role_owner_train_d.py test      # 단위 테스트(1분 안)
  python -I -X utf8 experiments/tile_classifier/role_owner_train_d.py regress   # 회귀 확인 ②③④(빠름) + ①(v3r15d 4겹 재현, 약 9분) → data/role/owner/regress_d.json
                                                                                # --fast: ②③④만(① 은 이전 결과를 옮겨 적음 — 학습 고리가 안 바뀌었을 때). ②는 legacy 모드
  python -I -X utf8 experiments/tile_classifier/role_owner_train_d.py samples   # 예시 그림 synth_v4_{win,mid,multi}.jpg + real_tokens.jpg
  python -I -X utf8 experiments/tile_classifier/role_owner_train_d.py compare   # v4 와 실제(화료 라벨·프레임-개발) 토큰 통계 → synth_v4_compare.json
  python -I -X utf8 experiments/tile_classifier/role_owner_train_d.py train     # D 사전학습 + 4겹 + 전부 → pre_synth8k_D.pt · role_D_fold_*.pt · role_D_all.pt
  python -I -X utf8 experiments/tile_classifier/role_owner_train_d.py eval      # E1·E3·E4 + A 와 짝 비교 + 판정 → eval_D.json
  (train·eval 의 --smoke DIR: 합성 200장면·1 epoch, 겹 하나·2 epoch 로 끝까지 도는지만. 결과는 DIR 에, 숫자는 안 찍음. eval --smoke 는
   프레임-시험 대신 프레임-개발을 시험 칸에 넣는다 — labels_test.json 을 열지 않음)
로그는 data/role/owner/log_d_<명령>.txt.
"""
from __future__ import annotations

import copy
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import role_owner_eval as roe  # noqa: E402  (v3r15d 환경 변수를 먼저 넣는다)

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

import role_owner_train as rot  # noqa: E402  (Tee·boot·flips·same_as_saved·load_labels — import 만)
import role_set as rs  # noqa: E402
import role_synth_v3 as g3  # noqa: E402
import role_synth_v4 as g4  # noqa: E402
import role_v2_train as t  # noqa: E402

OWN = roe.OWN
V2 = t.V2
ROLES = rs.ROLES
SIDES = roe.SIDES
assert tuple(SIDES) == g4.SIDES
assert t.SHIFT_ON and g3.ROT == "15" and g3.DROP_SAFE and rs.DROP_SAFE and g3.OTHER_NEG and rs.OTHER_NEG and not rs.NONE, "환경 변수가 v3r15d 와 다름"
PRE_ROT_SEED, FT_ROT_SEED, MIX_SEED = 40_000, 50_000, 60_000
OWNER_W, OWNER_LS = 1.0, 0.05
OWNED = ("hand", "meld", "river", "loose")  # 주인을 다는 역할(계획서 3-1)
OWNED_IDX = tuple(ROLES.index(r) for r in OWNED)
STAND_CHEB = 0.58  # 판 중 흉내: 기기 중심에서 체비쇼프 거리 이것 넘는 뒷면 = 세운 손패(계획서 4-2)


# ---------------------------------------------------------------- 모델
class SetNetOwner(rs.SetNet):
    """SetNet + 주인 머리. owner=False 면 가중치 이름·구조가 SetNet 과 같다(예전 가중치를 그대로 읽음). forward = 역할 로짓(SetNet 과 같음),
    forward_both = (역할 로짓, 주인 로짓 또는 None)."""

    def __init__(self, d: int = 64, layers: int = 3, feat: int = rs.FEAT, relbias: bool = False, owner: bool = True):
        assert not relbias, "relbias 는 D 에서 안 씀"
        super().__init__(d, layers, feat, relbias)
        self.has_owner = owner
        if owner:
            self.owner = nn.Linear(d, 4)

    def forward_both(self, x: torch.Tensor, pad: torch.Tensor):
        h = self.enc(self.inp(x), src_key_padding_mask=pad)
        return self.head(h), (self.owner(h) if self.has_owner else None)


def has_owner(net: nn.Module) -> bool:
    return bool(getattr(net, "has_owner", False))


def load_nets_d(path: Path) -> list[nn.Module]:
    nets = []
    for sd in torch.load(path):
        net = SetNetOwner(feat=sd["inp.0.weight"].shape[1], owner="owner.weight" in sd)
        net.load_state_dict(sd)
        nets.append(net.eval())
    return nets


def probs_d(nets, x: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    """씨드 확률 평균(역할, 주인). role_v2_train.probs_torch 와 같은 입력 만들기."""
    X, _, pad = rs.batch([dict(x=np.asarray(x, np.float32), y=[-1] * len(x))], None)
    pr, po = [], []
    with torch.no_grad():
        for n in nets:
            a, b = n.forward_both(X, pad) if has_owner(n) else (n(X, pad), None)
            pr.append(torch.softmax(a[0], 1).numpy())
            if b is not None:
                po.append(torch.softmax(b[0], 1).numpy())
    return np.mean(pr, 0), (np.mean(po, 0) if po else None)


# ---------------------------------------------------------------- 주인 라벨
def turn_owner(o, k: int) -> np.ndarray:
    """turn_tokens(x, k) 와 짝: 입력 기준 자리 o → (o − k) mod 4(돌려서 아래로 온 자리가 0 = bottom). −1 은 그대로."""
    o = np.asarray(o, np.int64)
    return np.where(o >= 0, (o - k) % 4, -1)


def turned(s: dict, k: int) -> dict:
    return dict(s, x=roe.turn_tokens(s["x"], k), owner=turn_owner(s["owner"], k))


def real_owner(rec: dict) -> list[int]:
    """labels_v2_owner.json 장면 → 토큰(화료자 기준 x) 순서의 주인. seat(사진 기준) → (seat − 화료자 side) mod 4. 주인 없는 역할·뒷면 −1."""
    j = SIDES.index(rec["side"])
    out = []
    for i in range(len(rec["x"])):
        if i < rec["n_face"]:
            it = rec["items"][i]
            if it["role"] in OWNED and it.get("seat") in SIDES:
                out.append((SIDES.index(it["seat"]) - j) % 4)
                continue
        out.append(-1)
    return out


def attach_owner(scenes: list[dict]) -> list[dict]:
    own = json.loads((V2 / "labels_v2_owner.json").read_text(encoding="utf-8"))
    for s in scenes:
        rec = own[s["name"]]
        assert len(rec["x"]) == len(s["x"]) and rec["n_face"] == s["n_face"], s["name"]
        s["owner"] = real_owner(rec)
        s["side"] = rec["side"]
    return scenes


def load_real(path: Path | None = None) -> list[dict]:
    """path 없음 = role_v2_train.load()(지금 라벨, LOOSE_SHIFT·other → −2), 있으면 role_owner_train.load_labels(path). 주인을 붙인다."""
    return attach_owner(t.load() if path is None else rot.load_labels(path))


# ---------------------------------------------------------------- 온라인 변형(rs.batch 를 옮김) · augment 따라가기
def batch_owner(scenes: list[dict], rng: np.random.Generator | None):
    """role_set.batch 와 같은 난수·같은 계산 + 주인 O(빠진 상자는 주인도 같이 빠짐, 패딩 −1)."""
    xs, ys, os_ = [], [], []
    for s in scenes:
        x, y = s["x"], np.array(s["y"])
        o = np.asarray(s["owner"], np.int64) if "owner" in s else np.full(len(x), -1, np.int64)
        if rng is not None:
            keep = rng.random(len(x)) > 0.08
            if rs.DROP_SAFE:
                keep |= (y != 2) & (y != -1)
            if keep.sum() >= 3:
                x, y, o = x[keep], y[keep], o[keep]
            x = x.copy()
            shift = rng.normal(0, 0.015, 2)
            scale = rng.uniform(0.95, 1.05)
            x[:, 0:2] = (x[:, 0:2] - 0.5) * scale + 0.5 + shift + rng.normal(0, 0.004, x[:, 0:2].shape)
            x[:, 2:4] *= rng.uniform(0.9, 1.1)
            x[:, 6:8] += shift
            if x.shape[1] == rs.FEAT_ROT:
                tt = np.arctan2(x[:, 9], x[:, 10]) / 2 + np.radians(rng.normal(0, 1.0) + rng.normal(0, 1.5, len(x)))
                x[:, 9], x[:, 10] = np.sin(2 * tt), np.cos(2 * tt)
        xs.append(torch.tensor(x))
        ys.append(torch.tensor(y))
        os_.append(torch.tensor(o))
    n = max(len(x) for x in xs)
    X = torch.zeros(len(xs), n, xs[0].shape[1])
    Y = torch.full((len(xs), n), -1, dtype=torch.long)
    O = torch.full((len(xs), n), -1, dtype=torch.long)
    pad = torch.ones(len(xs), n, dtype=torch.bool)
    for i, (x, y, o) in enumerate(zip(xs, ys, os_)):
        X[i, : len(x)] = x
        Y[i, : len(y)] = y
        O[i, : len(o)] = o
        pad[i, : len(x)] = False
    return X, Y, O, pad


def augment_owner(s: dict, rng: np.random.Generator) -> dict:
    """role_v2_train.augment 를 그대로 부르되 y 자리에 (역할, 주인) 짝을 넣는다 → 난수 흐름이 같고 주인이 상자를 따라간다."""
    r = t.augment(dict(name=s["name"], x=s["x"], y=list(zip([int(v) for v in s["y"]], [int(v) for v in s["owner"]])), n_face=s["n_face"]), rng)
    return dict(name=r["name"], x=r["x"], y=[a for a, _ in r["y"]], owner=[b for _, b in r["y"]], n_face=r["n_face"])


def imitate_mid(s: dict) -> dict | None:
    """"판 중 흉내"(계획서 4-2): 화료자 기준 토큰에서 손패(hand)·떼어 둔 패(loose)·짝(pair) 앞면을 지우고, 지운 손패마다 같은 중심(같은 칸 0·1·6·7·9·10)에
    뒷면 토큰을 놓는다. 크기 = 그 장면 뒷면 중 기기 중심 체비쇼프 거리 > 0.58(세운 손패)인 것의 줄 방향 길이·줄 가로 길이 중앙값
    (위·아래 자리(|dv| ≥ |du|)는 (폭, 높이), 왼쪽·오른쪽 자리는 (높이, 폭) — 화료자 줄은 아래라 새 뒷면은 폭 = 줄 방향). 그런 뒷면이 3개 미만이면 None."""
    x = np.asarray(s["x"], np.float32)
    y = np.asarray(s["y"])
    o = np.asarray(s["owner"], np.int64)
    back = x[:, 4] == 1
    cheb = np.maximum(np.abs(x[:, 6]), np.abs(x[:, 7]))
    stand = back & (cheb > STAND_CHEB)
    if stand.sum() < 3:
        return None
    vert = np.abs(x[:, 7]) >= np.abs(x[:, 6])
    along = np.where(vert, x[:, 2], x[:, 3])[stand]
    across = np.where(vert, x[:, 3], x[:, 2])[stand]
    bw, bh = float(np.median(along)), float(np.median(across))
    hand = y == ROLES.index("hand")
    drop = hand | (y == ROLES.index("loose")) | (y == ROLES.index("pair"))
    new = x[hand].copy()
    new[:, 2], new[:, 3], new[:, 4] = bw, bh, 1.0
    new[:, 5] = float(bw > bh * 1.15)
    keep = ~drop
    xk, yk, ok = x[keep], y[keep], o[keep]
    face = xk[:, 4] == 0
    xs = np.r_[xk[face], xk[~face], new].astype(np.float32)
    ys = [int(v) for v in yk[face]] + [int(v) for v in yk[~face]] + [-1] * len(new)
    os_ = [int(v) for v in ok[face]] + [int(v) for v in ok[~face]] + [-1] * len(new)
    return dict(name=s["name"] + "#mid", x=xs, y=ys, owner=os_, n_face=int(face.sum()), added_backs=int(len(new)), removed=int(drop.sum()),
                removed_hand=int(hand.sum()), back_size=(bw, bh), n_stand=int(stand.sum()))


def train_set_d(scenes: list[dict], k: int, seed: int, imitate: bool) -> list[dict]:
    """role_v2_train.train_set 과 같은 순서·같은 난수(20_000 + seed). imitate 면 장면마다 첫째 사본을 흉내 장면에서 만든다(흉내 불가면 보통 사본)."""
    rng = np.random.default_rng(20_000 + seed)
    out = [dict(name=s["name"], x=s["x"], y=s["y"], owner=s["owner"], n_face=s["n_face"]) for s in scenes]
    for s in scenes:
        for j in range(k):
            src = s
            if imitate and j == 0:
                m = imitate_mid(s)
                if m is not None:
                    src = m
            out.append(augment_owner(src, rng))
    return out


def mix_scenes(n_train: int, seed: int) -> list[dict]:
    """v4 판 중 : 여럿 펼침 = 2 : 1, 모두 round(n_train / 2). 씨드마다 같은 난수열(MIX_SEED + seed, + 100)의 앞부분 = 한 번 만들어 고정."""
    n = int(round(n_train / 2))
    n_mid = int(round(n * 2 / 3))
    return g4.dataset(n_mid, MIX_SEED + seed, kinds="mid") + g4.dataset(n - n_mid, MIX_SEED + 100 + seed, kinds="multi")


# ---------------------------------------------------------------- 학습 고리
def train_d(scenes: list[dict], epochs: int, seed: int, net: nn.Module | None = None, lr: float = 1e-3,
            rot_rng: np.random.Generator | None = None, owner: bool = True) -> nn.Module:
    """role_owner_train.train(= role_set.train + 뽑힐 때마다 회전)에 주인 손실을 더함. 옵티마이저·스케줄·역할 손실·OTHER_NEG·배치 8·씨드 사용 순서 같음.
    owner=False·rot_rng=None 이면 role_set.train 과 같은 계산(회귀 확인 ①)."""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    if net is None:
        net = SetNetOwner(feat=scenes[0]["x"].shape[1], owner=owner)
    else:
        net = copy.deepcopy(net)
        assert has_owner(net) == owner, "주인 머리 유무가 설정과 다름"
    freq = Counter((6 if (rs.NONE and r == -2) else r) for s in scenes for r in s["y"] if r >= 0 or (rs.NONE and r == -2))
    w = torch.tensor([1 / np.sqrt(max(freq[i], 1)) for i in range(len(ROLES))], dtype=torch.float32)
    w = w / w.mean()
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    loss_fn = nn.CrossEntropyLoss(weight=w, ignore_index=-1, label_smoothing=0.05)
    own_fn = nn.CrossEntropyLoss(ignore_index=-1, label_smoothing=OWNER_LS)
    net.train()
    for _ in range(epochs):
        order = rng.permutation(len(scenes))
        for k in range(0, len(order), 8):
            picked = [scenes[i] for i in order[k:k + 8]]
            if rot_rng is not None:
                picked = [turned(s, int(rot_rng.integers(4))) for s in picked]
            X, Y, O, pad = batch_owner(picked, rng)
            opt.zero_grad()
            if owner:
                logits, ologits = net.forward_both(X, pad)
            else:
                logits, ologits = net(X, pad), None
            logits = logits.reshape(-1, len(ROLES))
            Yf = Y.reshape(-1)
            if rs.NONE:
                Yf = torch.where(Yf == -2, torch.full_like(Yf, 6), Yf)
            loss = loss_fn(logits, Yf.clamp(min=-1))
            neg = Yf == -2
            if rs.OTHER_NEG and neg.any():
                pw = torch.softmax(logits[neg], 1)[:, rs.WIN_IDX].sum(1)
                loss = loss - torch.log((1 - pw).clamp_min(1e-4)).mean()
            if ologits is not None:
                Of = O.reshape(-1)
                if (Of >= 0).any():
                    loss = loss + OWNER_W * own_fn(ologits.reshape(-1, 4), Of)
            loss.backward()
            opt.step()
        sched.step()
    return net.eval()


class Cfg:
    def __init__(self, owner=True, rot=True, mix=True, imitate=True, epochs=100, aug=3):
        self.owner, self.rot, self.mix, self.imitate, self.epochs, self.aug = owner, rot, mix, imitate, epochs, aug

    def __repr__(self):
        return f"Cfg(owner={self.owner}, rot={self.rot}, mix={self.mix}, imitate={self.imitate}, epochs={self.epochs}, aug={self.aug})"


OFF = Cfg(owner=False, rot=False, mix=False, imitate=False)
ON = Cfg()


def finetune_d(pool: list[dict], pre: list, cfg: Cfg, info: dict | None = None) -> list:
    nets = []
    for seed in range(len(pre)):
        ts = train_set_d(pool, cfg.aug, seed, cfg.imitate)
        n_real = len(ts)
        if cfg.mix:
            ts = ts + mix_scenes(n_real, seed)
        if info is not None:
            info.setdefault("n_train", []).append({"seed": seed, "real_and_copies": n_real, "with_mix": len(ts),
                                                   "imitated": sum(1 for s in ts if "#mid" in s["name"])})
        nets.append(train_d(ts, cfg.epochs, seed, pre[seed], 3e-4, np.random.default_rng(FT_ROT_SEED + seed) if cfg.rot else None, cfg.owner))
    return nets


# ---------------------------------------------------------------- 단위 테스트
def _quad(du: float, dv: float) -> int:
    """기기 중심에서 본 방향 → 자리 번호(0 bottom·1 right·2 top·3 left)."""
    if abs(du) > abs(dv):
        return 1 if du > 0 else 3
    return 0 if dv > 0 else 2


def cmd_test() -> dict:
    res = {}
    # 1) 생성기 자리 번호 k ↔ 사진 기준 자리: to_felt 로 자리 좌표 (0, +d) 를 놓으면 k=0 아래·1 오른쪽·2 위·3 왼쪽
    sc = g4.Scene4(np.random.default_rng(0), "rot")
    dirs = []
    for k in range(4):
        u, v = sc.to_felt(0.0, 0.5, k)
        dirs.append(SIDES[_quad(u - sc.su, v - sc.sv)])
    res["to_felt_k"] = dirs
    assert dirs == list(SIDES), dirs
    # 2) SetNetOwner(owner=False) = SetNet: 키·모양 같음, v3r15d 가중치를 읽어 출력이 같음. owner=True 면 키 둘만 더함
    pre = torch.load(rs.OUT / "pre_synth8k_v3r15d.pt")
    k_old = list(rs.SetNet(feat=11).state_dict())
    n0 = SetNetOwner(feat=11, owner=False)
    assert list(n0.state_dict()) == k_old
    n0.load_state_dict(pre[0])
    n0.eval()
    ref = rs.load_nets(rs.OUT / "pre_synth8k_v3r15d.pt")[0]
    s = g4.dataset(3, 5)[0]
    X, _, pad = rs.batch([s], None)
    with torch.no_grad():
        d1 = float((n0(X, pad) - ref(X, pad)).abs().max())
        d2 = float((n0.forward_both(X, pad)[0] - ref(X, pad)).abs().max())
    n1 = SetNetOwner(feat=11, owner=True)
    extra = sorted(set(n1.state_dict()) - set(k_old))
    res["setnet_compat"] = {"keys_same": True, "max_diff_forward": d1, "max_diff_forward_both": d2, "owner_extra_keys": extra}
    assert d1 == 0 and d2 < 1e-6 and extra == ["owner.bias", "owner.weight"]
    # 3) batch_owner = rs.batch(같은 난수 상태에서 X·Y·pad 같음, 끝난 난수 상태 같음), 주인은 원래 줄 번호를 따라감
    syn = g4.dataset(40, 11)
    real = load_real()
    nb = 0
    for trial in range(30):
        r0 = np.random.default_rng(trial)
        pool = syn + real
        picks = [pool[i] for i in r0.choice(len(pool), 8, replace=False)]
        picks = [dict(p, owner=np.arange(len(p["x"]))) for p in picks]  # 주인 칸에 줄 번호를 넣어 추적
        ra, rb = np.random.default_rng(1000 + trial), np.random.default_rng(1000 + trial)
        Xa, Ya, pa = rs.batch(picks, ra)
        Xb, Yb, Ob, pb = batch_owner(picks, rb)
        assert torch.equal(Xa, Xb) and torch.equal(Ya, Yb) and torch.equal(pa, pb)
        assert ra.bit_generator.state == rb.bit_generator.state
        for i, p in enumerate(picks):
            m = ~pb[i]
            src = Ob[i][m].numpy()
            assert np.array_equal(np.array(p["y"])[src], Yb[i][m].numpy())
            assert np.array_equal(p["x"][src, 4], Xb[i][m][:, 4].numpy())
        nb += 1
    res["batch_owner_vs_rs_batch"] = f"{nb}/30 같음"
    # 4) augment_owner: x·y·n_face 가 role_v2_train.augment 와 같음, 주인 = 원래 줄 번호 추적이 맞음(반쪽 쪼개기 = 같은 원래 줄 두 번)
    n_split = n_drop = 0
    for i, s in enumerate(real):
        ra, rb = np.random.default_rng(7 + i), np.random.default_rng(7 + i)
        a = t.augment(s, ra)
        b = augment_owner(dict(s, owner=list(range(len(s["x"])))), rb)
        assert np.array_equal(a["x"], b["x"]) and a["y"] == b["y"] and a["n_face"] == b["n_face"]
        assert ra.bit_generator.state == rb.bit_generator.state
        src = np.array(b["owner"])
        assert [s["y"][j] for j in src] == b["y"]
        assert np.array_equal(s["x"][src, 4], b["x"][:, 4])
        n_split += len(src) - len(set(src.tolist()))
        n_drop += len(s["x"]) - len(set(src.tolist()))
        # 진짜 주인으로도
        c = augment_owner(s, np.random.default_rng(7 + i))
        assert c["owner"] == [s["owner"][j] for j in src]
    res["augment_owner_vs_augment"] = {"scenes": len(real), "split_rows": n_split, "dropped_rows": n_drop}
    # 5) 회전: turn_owner 가 turn_tokens 와 맞물림(기기 중심 방향으로 본 자리 = 주인, 돌리기 전후 같은 비율), 네 번 돌리면 원래대로
    g_ok = g_n = 0
    for s in syn:
        o = np.array(s["owner"])
        m = o >= 0
        for k in range(4):
            x2, o2 = roe.turn_tokens(s["x"], k), turn_owner(o, k)
            q = np.array([_quad(a, b) for a, b in x2[:, 6:8]])
            g_ok += int((q[m] == o2[m]).sum())
            g_n += int(m.sum())
        x4, o4 = s["x"], o
        for _ in range(4):
            x4, o4 = roe.turn_tokens(x4, 1), turn_owner(o4, 1)
        assert np.abs(x4 - s["x"]).max() < 1e-5 and np.array_equal(o4, o)
    res["synth_quadrant_eq_owner_all_k"] = f"{g_ok}/{g_n}"
    # 6) 흉내: 손패·떼어 둔 패·짝 0, 더한 뒷면 = 지운 손패
    m = [imitate_mid(s) for s in real if not s["staged"]]
    ok = [x for x in m if x is not None]
    assert all(not any(v in (0, 4, 5) for v in x["y"]) and x["added_backs"] == x["removed_hand"] for x in ok)
    res["imitate"] = f"{len(ok)}/{len(m)} 장면 만들어짐"
    return res


# ---------------------------------------------------------------- 회귀 확인
def owned_geometry(scenes: list[dict], name: str) -> dict:
    """주인 있는 토큰: 기기 중심 방향(사분면) = 주인인 비율(역할별), 주인 bottom 인 손패의 v·(v − sv) 분포."""
    per = {r: [0, 0] for r in OWNED}
    hv, hdv = [], []
    for s in scenes:
        x, y, o = s["x"], np.asarray(s["y"]), np.asarray(s["owner"])
        for i in np.where(o >= 0)[0]:
            r = ROLES[int(y[i])]
            per[r][1] += 1
            per[r][0] += _quad(float(x[i, 6]), float(x[i, 7])) == int(o[i])
            if r == "hand" and o[i] == 0:
                hv.append(float(x[i, 1]))
                hdv.append(float(x[i, 7]))
    q = lambda a: {"n": len(a), "min": round(min(a), 3), "p05": round(float(np.percentile(a, 5)), 3), "median": round(float(np.median(a)), 3),
                   "max": round(max(a), 3)} if a else {}
    return {"set": name, "quadrant_eq_owner": {r: f"{a}/{b}" for r, (a, b) in per.items() if b}, "bottom_hand_v": q(hv), "bottom_hand_v_minus_sv": q(hdv)}


def regress_fast() -> dict:
    out = {}
    # ② v4 를 화료 1명으로 고정 = v3 dataset(같은 씨드)
    r2 = []
    for seed in (100, 101, 102):
        a = g3.dataset(200, seed)
        b = g4.dataset(200, seed, kinds="win", legacy=True)  # 보완을 끈 legacy 모드(계획서 4-2 "생성기 v4 보완")
        same_x = sum(np.array_equal(p["x"], q["x"]) for p, q in zip(a, b))
        same_y = sum(list(p["y"]) == list(q["y"]) for p, q in zip(a, b))
        r2.append({"seed": seed, "x_same": f"{same_x}/200", "y_same": f"{same_y}/200", "ok": same_x == 200 and same_y == 200})
    out["r2_v4win_eq_v3"] = r2
    print("② v4(화료 1명 고정) = v3:", r2, flush=True)
    # ③ 주인 라벨 회전
    real = load_real()
    own = json.loads((V2 / "labels_v2_owner.json").read_text(encoding="utf-8"))
    hb = hn = side_ok = seat_ok = seat_n = 0
    for s in real:
        o = np.asarray(s["owner"])
        y = np.asarray(s["y"])
        hand = y == 0
        hn += int(hand.sum())
        hb += int((o[hand] == 0).sum())
        j = SIDES.index(s["side"])
        k = (4 - j) % 4
        o0 = turn_owner(o, k)
        side_ok += int((o0[hand] == j).sum())
        items = own[s["name"]]["items"]
        for i, it in enumerate(items):
            if it["role"] in OWNED and it.get("seat") in SIDES:
                seat_n += 1
                seat_ok += int(o0[i]) == SIDES.index(it["seat"])
    syn = g4.dataset(300, 7)
    four = 0
    for s in syn:
        x4, o4 = s["x"], np.asarray(s["owner"])
        for _ in range(4):
            x4, o4 = roe.turn_tokens(x4, 1), turn_owner(o4, 1)
        four += bool(np.abs(x4 - s["x"]).max() < 1e-5 and np.array_equal(o4, s["owner"]))
    rng = np.random.default_rng(3)
    syn_rot = [turned(s, int(rng.integers(4))) for s in syn]
    real_photo = [turned(s, (4 - SIDES.index(s["side"])) % 4) for s in real]
    syn_leg = g4.dataset(300, 7, legacy=True)
    geo = [owned_geometry([s for s in syn if s["kind"] == kd], f"v4 {kd} 생성기 기준(보완 켬)") for kd in g4.KINDS]
    geo += [owned_geometry([s for s in syn_leg if s["kind"] == kd], f"v4 {kd} 생성기 기준(legacy)") for kd in g4.KINDS]
    geo += [owned_geometry(syn_rot, "v4 무작위 회전(보완 켬)"), owned_geometry(real, "실제 41장 화료자 기준"), owned_geometry(real_photo, "실제 41장 사진 기준"),
            owned_geometry([s for s in real if not s["staged"]], "실제 33장(연출 뺌) 화료자 기준")]
    out["r3_owner_rotation"] = {"real_hand_owner_bottom_winner_frame": f"{hb}/{hn}", "real_hand_owner_eq_side_photo_frame": f"{side_ok}/{hn}",
                                "real_owned_eq_label_seat_photo_frame": f"{seat_ok}/{seat_n}", "synth_four_turns_identity": f"{four}/{len(syn)}",
                                "kinds": dict(Counter(s["kind"] for s in syn)), "geometry": geo,
                                "ok": hb == hn and side_ok == hn and seat_ok == seat_n and four == len(syn)}
    print("③ 주인 회전:", {k: v for k, v in out["r3_owner_rotation"].items() if k != "geometry"}, flush=True)
    for gg in geo:
        print("   기하", gg, flush=True)
    # ④ 판 중 흉내(실제 33장)
    pool = [s for s in real if not s["staged"]]
    rows = []
    for s in pool:
        m = imitate_mid(s)
        if m is None:
            rows.append({"name": s["name"], "made": False, "n_stand": int(((np.asarray(s["x"])[:, 4] == 1) & (np.maximum(np.abs(s["x"][:, 6]), np.abs(s["x"][:, 7])) > STAND_CHEB)).sum())})
            continue
        left = Counter(ROLES[v] if v >= 0 else ("other" if v == -2 else "back") for v in m["y"])
        rows.append({"name": s["name"], "made": True, "n_stand": m["n_stand"], "removed_hand": m["removed_hand"], "removed_all": m["removed"],
                     "added_backs": m["added_backs"], "left_hand_loose_pair": left["hand"] + left["loose"] + left["pair"],
                     "back_size_x10": [round(m["back_size"][0], 3), round(m["back_size"][1], 3)],
                     "backs_before": int((np.asarray(s["x"])[:, 4] == 1).sum()), "backs_after": int((m["x"][:, 4] == 1).sum())})
    made = [r for r in rows if r["made"]]
    out["r4_imitate"] = {"made": f"{len(made)}/{len(pool)}", "all_hlp_zero": all(r["left_hand_loose_pair"] == 0 for r in made),
                         "added_eq_removed_hand": all(r["added_backs"] == r["removed_hand"] for r in made),
                         "backs_after_eq_before_plus_added": all(r["backs_after"] == r["backs_before"] + r["added_backs"] for r in made),
                         "removed_hand_total": sum(r["removed_hand"] for r in made), "added_total": sum(r["added_backs"] for r in made),
                         "not_made": [r for r in rows if not r["made"]], "rows": rows}
    print("④ 흉내:", {k: v for k, v in out["r4_imitate"].items() if k != "rows"}, flush=True)
    return out


def regress_slow() -> dict:
    """① 주인 머리·회전·섞기·흉내를 모두 끈 새 고리 + pre_synth8k_v3r15d.pt → cv_nostaged_v3r15d.json 상자별 답 재현(R 의 regress 와 같은 라벨 파일)."""
    t0 = time.time()
    lab = V2 / "labels_v2_before_153311fix.json"
    scenes = load_real(lab)
    pool = [s for s in scenes if not s["staged"]]
    pre = rs.load_nets(rs.OUT / "pre_synth8k_v3r15d.pt")
    cv = json.loads((V2 / "cv_nostaged_v3r15d.json").read_text(encoding="utf-8"))["per"]
    print("① 라벨", lab.name, "장면", len(scenes), "학습 풀", len(pool), "설정", OFF, flush=True)
    tot, diffs, per_fold = Counter(), [], {}
    for fold in t.FOLDS:
        tr = [s for s in pool if s["fold"] != fold]
        te = [s for s in scenes if s["fold"] == fold]
        nets = finetune_d(tr, pre, OFF)
        c = Counter()
        for s in te:
            p = t.probs_torch(nets, s["x"])
            pred = [ROLES[int(i)] for i in p.argmax(1)][: s["n_face"]]
            ref = cv[s["name"]]["pred"]
            assert len(ref) == len(pred)
            for i, (a, b) in enumerate(zip(pred, ref)):
                c["n"] += 1
                c["same"] += a == b
                if a != b:
                    diffs.append((s["name"], i, b, a))
        per_fold[fold] = f"{c['same']}/{c['n']}"
        tot += c
        print("①", fold, "학습", len(tr), "시험", len(te), "같은 상자", per_fold[fold], f"{round(time.time() - t0)}초", flush=True)
    return {"labels": lab.name, "same": f"{tot['same']}/{tot['n']}", "per_fold": per_fold, "diffs": diffs, "ok": tot["same"] == tot["n"], "secs": round(time.time() - t0)}


def cmd_regress(fast: bool = False) -> None:
    """fast = ②③④만 다시(생성기만 바뀌고 학습 고리가 그대로일 때). ① 결과는 이전 regress_d.json 에서 옮기고 그 사실을 적는다."""
    res = {"date": time.strftime("%Y-%m-%d %H:%M")}
    res.update(regress_fast())
    if fast:
        prev = json.loads((OWN / "regress_d.json").read_text(encoding="utf-8"))
        res["r1_v3r15d_reproduce"] = dict(prev["r1_v3r15d_reproduce"], carried_from=prev["date"],
                                          note="학습 고리(train_d·batch_owner·augment_owner·train_set_d) 안 바뀜 — 생성기 보완만이라 ① 다시 안 돌림")
    else:
        res["r1_v3r15d_reproduce"] = regress_slow()
    print("①", {k: v for k, v in res["r1_v3r15d_reproduce"].items() if k != "diffs"}, res["r1_v3r15d_reproduce"]["diffs"][:10], flush=True)
    res["ok"] = (all(r["ok"] for r in res["r2_v4win_eq_v3"]) and res["r3_owner_rotation"]["ok"] and res["r4_imitate"]["all_hlp_zero"]
                 and res["r4_imitate"]["added_eq_removed_hand"] and res["r1_v3r15d_reproduce"]["ok"])
    (OWN / "regress_d.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("회귀 확인 전체", "통과" if res["ok"] else "실패", OWN / "regress_d.json", flush=True)


# ---------------------------------------------------------------- 예시 그림
def frame_panel(sc: dict):
    y, o = [], []
    for i in range(len(sc["x0"])):
        if i < sc["n_face"]:
            lab = sc["labels"][i]
            r = lab["role"]
            y.append(ROLES.index(r) if r in ROLES else -2)
            o.append(SIDES.index(lab["seat"]) if (r in OWNED and lab.get("seat") in SIDES) else -1)
        else:
            y.append(-1)
            o.append(-1)
    return y, o


def cmd_samples() -> None:
    for p in g4.kind_sheets(6, 123, OWN):
        print(p)
    real = [s for s in load_real() if not s["staged"]]
    picks = [real[0], real[20]]
    panels = [(f"실제 화료 {s['name'][-15:]} (화료자 기준, 사진 {s['side']})", s["x"], s["y"], s["owner"]) for s in picks]
    rects_all = json.loads(roe.RECTS_CACHE.read_text(encoding="utf-8"))
    dev, _ = roe.e3_scenes("dev", rects_all)  # 프레임-개발(10-31)만. 시험(11-07)은 열지 않음
    early = next(s for s in dev if s["phase"] == "early")
    late = next(s for s in dev if s["phase"] == "late" and s["name"].split("_f")[0] != early["name"].split("_f")[0])
    for s in (early, late):
        y, o = frame_panel(s)
        panels.append((f"프레임-개발 {s['phase']} {s['name'][-20:]} (사진 기준)", s["x0"], y, o))
    print(g4.sheet(panels, OWN / "real_tokens.jpg", cols=2))


# ---------------------------------------------------------------- 생성기 배치 견주기
def _seatrel(du: float, dv: float, k: int) -> tuple[float, float]:
    """기기 중심 기준 (du, dv) → 자리 k 기준 (옆 x, 앞 d). to_felt 의 역."""
    x, d = du, dv
    for _ in range(k % 4):
        x, d = -d, x
    return x, d


def stand_row(x: np.ndarray, k: int, gap: float = 0.03) -> float | None:
    """사분면 k 의 뒷면(거리 0.3~0.9)을 정렬해 가장 큰 틈(≥ gap)으로 안쪽(패산)·바깥(세운 손패) 줄로 나누고, 바깥 줄(3장 이상)의 거리 중앙값.
    틈이 없으면(한 줄뿐) None. 보완 ③ 의 STAND_D 를 잰 방법과 같다."""
    b = x[:, 4] == 1
    du, dv = x[b, 6], x[b, 7]
    ch = np.maximum(np.abs(du), np.abs(dv))
    qk = np.array([_quad(float(a), float(c)) for a, c in zip(du, dv)], dtype=int)
    v = np.sort(ch[(qk == k) & (ch > 0.3) & (ch < 0.9)])
    if len(v) < 3:
        return None
    g = np.diff(v)
    i = int(np.argmax(g))
    if g[i] < gap or len(v) - i - 1 < 3:
        return None
    return float(np.median(v[i + 1:]))


def token_stats(scenes: list[dict]) -> dict:
    """scenes = [{x, y, owner}] → 자리별 강 장수, 기기 중심 체비쇼프 거리(강·울기·손패·뒷면), 패 크기, 장면당 수."""
    riv_seat, riv_tot = [], []
    dist = {"river": [], "meld": [], "hand": [], "wall_face": [], "back": []}
    river_first = []
    size_short, size_long, back_w, back_h = [], [], [], []
    meld_cx, meld_cd, stand_rows = [], [], []
    cnt = {k: [] for k in ("faces", "backs", "river", "meld", "hand", "wall_face", "pair_loose", "other", "stand_backs", "wall_backs")}
    for s in scenes:
        x, y, o = np.asarray(s["x"]), np.asarray(s["y"]), np.asarray(s["owner"])
        cheb = np.maximum(np.abs(x[:, 6]), np.abs(x[:, 7]))
        face = x[:, 4] == 0
        back = ~face
        riv = face & (y == 2)
        per = [int((riv & (o == k)).sum()) for k in range(4)]
        riv_seat += per
        riv_tot.append(sum(per))
        for r, key in (("river", "river"), ("meld", "meld"), ("hand", "hand")):
            dist[key] += cheb[face & (y == ROLES.index(r))].tolist()
        dist["wall_face"] += cheb[face & (y == 3)].tolist()
        dist["back"] += cheb[back].tolist()
        for k in range(4):
            m = riv & (o == k)
            if m.any():
                river_first.append(float(cheb[m].min()))
            mm = face & (y == 1) & (o == k)
            if mm.any():  # 울기 묶음 중심(자리 기준 옆 x·앞 d 의 평균)
                pts = [_seatrel(float(a), float(b), k) for a, b in x[mm][:, 6:8]]
                meld_cx.append(float(np.mean([p[0] for p in pts])))
                meld_cd.append(float(np.mean([p[1] for p in pts])))
            r = stand_row(x, k)
            if r is not None:
                stand_rows.append(r)
        sz = x[riv][:, 2:4] / 10
        size_short += np.min(sz, 1).tolist()
        size_long += np.max(sz, 1).tolist()
        bs = x[back & (cheb > STAND_CHEB)]
        vert = np.abs(bs[:, 7]) >= np.abs(bs[:, 6])
        back_w += (np.where(vert, bs[:, 2], bs[:, 3]) / 10).tolist()
        back_h += (np.where(vert, bs[:, 3], bs[:, 2]) / 10).tolist()
        cnt["faces"].append(int(face.sum()))
        cnt["backs"].append(int(back.sum()))
        cnt["river"].append(int(riv.sum()))
        cnt["meld"].append(int((face & (y == 1)).sum()))
        cnt["hand"].append(int((face & (y == 0)).sum()))
        cnt["wall_face"].append(int((face & (y == 3)).sum()))
        cnt["pair_loose"].append(int((face & ((y == 4) | (y == 5))).sum()))
        cnt["other"].append(int((face & (y == -2)).sum()))
        cnt["stand_backs"].append(int((back & (cheb > STAND_CHEB)).sum()))
        cnt["wall_backs"].append(int((back & (cheb <= STAND_CHEB)).sum()))

    def q(a, nd=3):
        if not a:
            return None
        a = np.asarray(a, float)
        return {"n": int(len(a)), "p10": round(float(np.percentile(a, 10)), nd), "median": round(float(np.median(a)), nd),
                "p90": round(float(np.percentile(a, 90)), nd), "mean": round(float(a.mean()), nd)}

    hist_edges = [0, 0.3, 0.4, 0.46, 0.52, 0.58, 0.64, 0.7, 0.76, 0.85, 5]
    bh = np.histogram(dist["back"], hist_edges)[0] if dist["back"] else np.zeros(len(hist_edges) - 1)
    return {"n_scenes": len(scenes), "river_per_seat": q(riv_seat, 2), "river_per_seat_hist": dict(Counter(min(v, 25) for v in riv_seat)),
            "river_per_scene": q(riv_tot, 1),
            "dist_cheb": {k: q(v) for k, v in dist.items()}, "river_first_row_cheb_per_seat": q(river_first),
            "back_dist_hist": {f"{a}-{b}": round(float(c) / max(1, len(dist["back"])), 3) for a, b, c in zip(hist_edges[:-1], hist_edges[1:], bh)},
            "river_tile_short_long": [q(size_short), q(size_long)], "stand_back_along_across": [q(back_w), q(back_h)],
            "meld_bundle_center_x": q(meld_cx), "meld_bundle_center_d": q(meld_cd), "stand_row_median_dist": q(stand_rows),
            "per_scene": {k: q(v, 1) for k, v in cnt.items()}}


def cmd_compare() -> None:
    real = [s for s in load_real() if not s["staged"]]
    rects_all = json.loads(roe.RECTS_CACHE.read_text(encoding="utf-8"))
    dev, _ = roe.e3_scenes("dev", rects_all)  # 프레임-개발만
    dev_sc = []
    for s in dev:
        y, o = frame_panel(s)
        dev_sc.append(dict(x=s["x0"], y=y, owner=o, phase=s["phase"]))
    syn = {kd: g4.dataset(400 if kd != "multi" else 200, 777 + i, kinds=kd) for i, kd in enumerate(g4.KINDS)}
    leg = {kd: g4.dataset(400, 777 + i, kinds=kd, legacy=True) for i, kd in enumerate(g4.KINDS) if kd != "multi"}
    groups = {
        "v4_mid_legacy": leg["mid"], "v4_mid": syn["mid"], "dev_not_open(early+mid+late)": [s for s in dev_sc if s["phase"] != "open"],
        "dev_early": [s for s in dev_sc if s["phase"] == "early"], "dev_mid": [s for s in dev_sc if s["phase"] == "mid"],
        "dev_late": [s for s in dev_sc if s["phase"] == "late"],
        "v4_multi": syn["multi"], "dev_open": [s for s in dev_sc if s["phase"] == "open"],
        "v4_win_legacy": leg["win"], "v4_win": syn["win"], "real_win_33": real,
    }
    res = {k: token_stats(v) for k, v in groups.items()}
    (OWN / "synth_v4_compare.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in res.items():
        print(f"\n## {k} (장면 {v['n_scenes']})")
        print("  자리별 강", v["river_per_seat"], "장면 합", v["river_per_scene"])
        print("  거리 강", v["dist_cheb"]["river"], "강 첫 줄", v["river_first_row_cheb_per_seat"])
        print("  거리 울기", v["dist_cheb"]["meld"], "손패", v["dist_cheb"]["hand"], "패산 앞면", v["dist_cheb"]["wall_face"])
        print("  뒷면 거리", v["dist_cheb"]["back"], v["back_dist_hist"])
        print("  강 패 짧은·긴 변", v["river_tile_short_long"], "세운 뒷면 줄방향·가로", v["stand_back_along_across"])
        print("  울기 묶음 중심 x", v["meld_bundle_center_x"], "d", v["meld_bundle_center_d"], "세운 줄 거리", v["stand_row_median_dist"])
        print("  장면당", {kk: (vv["median"] if vv else None) for kk, vv in v["per_scene"].items()})
    print(OWN / "synth_v4_compare.json")


# ---------------------------------------------------------------- 학습
def cmd_train(smoke: str | None) -> None:
    t0 = time.time()
    out_dir = Path(smoke) if smoke else OWN
    out_dir.mkdir(parents=True, exist_ok=True)
    if smoke:
        n_syn, pre_ep, cfg, folds, do_all = 200, 1, Cfg(epochs=2), [t.FOLDS[0]], False
    else:
        reg = json.loads((OWN / "regress_d.json").read_text(encoding="utf-8"))
        assert reg["ok"], "회귀 확인(regress_d.json)이 통과하지 않음 — D 학습을 시작하지 않는다"
        n_syn, pre_ep, cfg, folds, do_all = 8000, 3, ON, list(t.FOLDS), True
    pf = out_dir / "pre_synth8k_D.pt"
    assert not pf.exists(), f"{pf} 가 이미 있음(학습은 한 번)"
    print("설정", cfg, "사전학습 장면", n_syn, "epoch", pre_ep, "겹", folds, flush=True)
    pre = []
    for seed in range(3):
        syn = g4.dataset(n_syn, 100 + seed)
        print("사전학습 씨드", seed, "종류", dict(Counter(s["kind"] for s in syn)), flush=True)
        pre.append(train_d(syn, pre_ep, seed, rot_rng=np.random.default_rng(PRE_ROT_SEED + seed), owner=True))
        print("D 사전학습 씨드", seed, f"{round(time.time() - t0)}초", flush=True)
    torch.save([n.state_dict() for n in pre], pf)
    pre = load_nets_d(pf)
    pool = [s for s in load_real() if not s["staged"]]
    print("미세 조정 풀", len(pool), "(연출 뺌)", flush=True)
    info_all = {}
    for fold in folds:
        tr = [s for s in pool if s["fold"] != fold]
        info = {}
        nets = finetune_d(tr, pre, cfg, info)
        torch.save([n.state_dict() for n in nets], out_dir / f"role_D_fold_{fold}.pt")
        info_all[fold] = info
        print(fold, "학습 실제", len(tr), info["n_train"], f"{round(time.time() - t0)}초", flush=True)
    if do_all:
        info = {}
        nets = finetune_d(pool, pre, cfg, info)
        torch.save([n.state_dict() for n in nets], out_dir / "role_D_all.pt")
        info_all["all"] = info
        print("전부", len(pool), info["n_train"], f"{round(time.time() - t0)}초", flush=True)
    (out_dir / "train_D_info.json").write_text(json.dumps({"cfg": repr(cfg), "n_synth": n_syn, "pre_epochs": pre_ep, "folds": info_all,
                                                             "secs": round(time.time() - t0)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("끝", f"{round(time.time() - t0)}초", flush=True)


# ---------------------------------------------------------------- 채점
class FoldNetsD:
    """겹 → role_D_fold_<겹>.pt(씨드 3). smoke 면 모든 겹을 한 파일로."""

    def __init__(self, d: Path = OWN, only: Path | None = None):
        self.d, self.only, self.nets = d, only, {}

    def path(self, fold: str) -> Path:
        return self.only if self.only is not None else self.d / f"role_D_fold_{fold}.pt"

    def probs(self, fold: str, x: np.ndarray):
        if fold not in self.nets:
            self.nets[fold] = load_nets_d(self.path(fold))
            assert all(has_owner(n) for n in self.nets[fold])
        return probs_d(self.nets[fold], x)


class PredictorD:
    """사진 기준 토큰 x0 1회 → 역할 = 역할 확률 최대(확신 = 최대값 소수 셋째 자리), 주인 = 주인 확률 최대(모든 상자, SIDES 이름)."""

    name = "D"

    def __init__(self, nets: FoldNetsD):
        self.nets = nets

    def __call__(self, sc: dict) -> list[dict]:
        nf = sc["n_face"]
        pr, po = self.nets.probs(sc["fold"], sc["x0"])
        return [{"role": ROLES[int(pr[i].argmax())], "conf": round(float(pr[i].max()), 3), "owner": SIDES[int(po[i].argmax())],
                 "owner_conf": round(float(po[i].max()), 3)} for i in range(nf)]


def e4_owned(e4res: dict, scenes: list[dict]) -> dict:
    """E4 를 계획서 "채점은 hand·meld·loose·river 의 주인" 에 맞춰: 역할은 모든 상자, 주인은 원래 답 역할이 hand·meld·loose·river 인 상자만 비교."""
    n = 3 * sum(s["n_face"] for s in scenes)
    bad = 0
    by_k = Counter()
    for d in e4res["diff"]:
        o, r = d["orig"], d["rot"]
        if o[0] != r[0] or (o[0] in OWNED and o[2] != r[2]):
            bad += 1
            by_k[90 * d["k"]] += 1
    return {"role_owner_owned": f"{n - bad}/{n}", "role_owner_owned_pct": round(100 * (n - bad) / n, 3), "diff_by_k": dict(by_k)}


def rename(b: dict) -> dict:
    return {("D" if k == "R" else k): v for k, v in b.items()}


def cmd_eval(smoke: str | None) -> None:
    t0 = time.time()
    s1all, _ = roe.e1_scenes(all_scenes=True)
    s1 = [s for s in s1all if s["eval"]]
    rects_all = json.loads(roe.RECTS_CACHE.read_text(encoding="utf-8"))
    s3d, _ = roe.e3_scenes("dev", rects_all)
    s3t = s3d if smoke else roe.e3_scenes("test", rects_all)[0]  # smoke: 시험 칸에 개발 프레임(시험 라벨 안 엶)
    saved_A = json.loads((OWN / "eval_A.json").read_text(encoding="utf-8"))
    assert [s["name"] for s in s1] == saved_A["meta"]["e1_scenes"]
    A_rec = {k: {nm: v["boxes"] for nm, v in saved_A["scenes"][k].items()} for k in ("E1", "E3_test", "E3_dev")}
    if smoke:
        A_rec["E3_test"] = A_rec["E3_dev"]
    checks = {}
    if not smoke:  # A 다시 재기(같은 시각 나란히) → eval_A.json 과 같은지
        A = roe.PredictorA(roe.FoldNets())
        a1, a3t, a3d = roe.run_set(s1, A), roe.run_set(s3t, A), roe.run_set(s3d, A)
        checks["A_rerun_vs_eval_A"] = {"E1": rot.same_as_saved(saved_A["scenes"]["E1"], a1), "E3_test": rot.same_as_saved(saved_A["scenes"]["E3_test"], a3t),
                                       "E3_dev": rot.same_as_saved(saved_A["scenes"]["E3_dev"], a3d)}
        print("A 다시 잰 것 = eval_A.json", {k: v["same"] for k, v in checks["A_rerun_vs_eval_A"].items()}, flush=True)
    nets = FoldNetsD(only=(Path(smoke) / f"role_D_fold_{t.FOLDS[0]}.pt") if smoke else None)
    D = PredictorD(nets)
    models = {"E1": {s["name"]: nets.path(s["fold"]).name for s in s1}, "E3_test": sorted({nets.path(s["fold"]).name for s in s3t}),
              "E3_dev": dict(Counter(nets.path(s["fold"]).name for s in s3d))}
    r1, r3t, r3d = roe.run_set(s1, D), roe.run_set(s3t, D), roe.run_set(s3d, D)
    res = {"E1": roe.aggregate(s1, r1, True), "E3_test": roe.aggregate(s3t, r3t, False), "E3_dev": roe.aggregate(s3d, r3d, False)}
    for nm, ss, rr in (("E3_test", s3t, r3t), ("E3_dev", s3d, r3d)):
        res[nm + "_by_phase"] = {ph: roe.aggregate([s for s in ss if s["phase"] == ph], rr, False) for ph in ("early", "mid", "late", "open")}
        res[nm + "_open_vs_not"] = {g_: roe.aggregate([s for s in ss if (s["phase"] == "open") == (g_ == "open")], rr, False)["false_hand"] for g_ in ("open", "not_open")}
    res["E4"] = roe.e4(s1, D, r1)
    res["E4"]["owned"] = e4_owned(res["E4"], s1)
    D_rec = {"E1": r1, "E3_test": r3t, "E3_dev": r3d}
    game = lambda nm: nm.split("_f")[0]
    cmp = {}
    for k in ("E1", "E3_test", "E3_dev"):
        cmp[k] = {"role_owner": rename(rot.boot(A_rec[k], D_rec[k], "ro_ok")), "role_only": rename(rot.boot(A_rec[k], D_rec[k], "role_ok")),
                  "flips_role_owner": rot.flips(A_rec[k], D_rec[k], "ro_ok"), "flips_role": rot.flips(A_rec[k], D_rec[k], "role_ok")}
        if k != "E1":
            cmp[k]["role_owner_game_cluster"] = rename(rot.boot(A_rec[k], D_rec[k], "ro_ok", game))
    sA = saved_A["summary"]
    e1, e3 = res["E1"], res["E3_test"]
    nh = res["E3_test_open_vs_not"]["not_open"]["pred_hand_total"]
    verdict = {
        "d1": dict(ok=e1["role_owner"]["wrong"] < sA["E1"]["role_owner"]["wrong"] and cmp["E1"]["role_owner"]["hi"] < 0,
                   D_wrong=e1["role_owner"]["wrong"], A_wrong=sA["E1"]["role_owner"]["wrong"], ci=[cmp["E1"]["role_owner"]["lo"], cmp["E1"]["role_owner"]["hi"]]),
        "d1b": dict(ok=e1["river_owner"]["A_wrong"] <= e1["river_owner"]["quadrant_wrong"], D_wrong=e1["river_owner"]["A_wrong"],
                    quadrant_wrong=e1["river_owner"]["quadrant_wrong"]),
        "d2": dict(ok=e1["role"]["hand_meld_river_wrong"] <= sA["E1"]["role"]["hand_meld_river_wrong"] + 2, D=e1["role"]["hand_meld_river_wrong"],
                   limit=sA["E1"]["role"]["hand_meld_river_wrong"] + 2),
        "d4": dict(ok=e3["role_owner"]["wrong"] <= sA["E3_test"]["role_owner"]["wrong"] + 2 and nh == 0, D_wrong=e3["role_owner"]["wrong"],
                   limit=sA["E3_test"]["role_owner"]["wrong"] + 2, not_open_pred_hand=nh),
        "d4b": dict(ok=e3["river_owner"]["A_wrong"] <= e3["river_owner"]["quadrant_wrong"], D_wrong=e3["river_owner"]["A_wrong"],
                    quadrant_wrong=e3["river_owner"]["quadrant_wrong"]),
        "d5": dict(ok=res["E4"]["owned"]["role_owner_owned_pct"] >= 99.0, pct=res["E4"]["owned"]["role_owner_owned_pct"],
                   all_boxes_owner_pct_ref=res["E4"]["total"]["role_owner_pct"], role_pct=res["E4"]["total"]["role_pct"]),
    }
    verdict["all"] = all(v["ok"] for v in verdict.values())
    meta = {"date": time.strftime("%Y-%m-%d %H:%M"), "predictor": "D", "smoke": bool(smoke),
            "cmd": "python -I -X utf8 experiments/tile_classifier/role_owner_train_d.py eval",
            "env": {k: __import__("os").environ.get(k) for k in ("ROLE_OTHER_NEG", "ROLE_DROP_SAFE", "ROLE_LOOSE_SHIFT", "ROLE_SYNTH_V3_ROT", "ROLE_EVAL_COMPOSITE")},
            "models": models, "e1_scenes": [s["name"] for s in s1], "secs": None,
            "defs": dict(saved_A["meta"]["defs"],
                         predictor_D="사진 기준 x0 1회 → 역할 argmax(확신 max 소수 셋째 자리), 주인 = 주인 머리 argmax(모든 상자). 강 주인은 aggregate 의 river_owner 'A' 칸에 D 의 답이 들어감",
                         E4_owned="d5 판정: 역할은 모든 상자, 주인은 원래 답 역할이 hand·meld·loose·river 인 상자만(계획서 '채점은 hand·meld·loose·river 의 주인'). 모든 상자 주인 비교는 참고(total.role_owner_pct)",
                         bootstrap="장면 묶음(E1 사진, E3 프레임) 1,000회 seed 0, role_owner_train.boot(stats.bootstrap_diff), D − A 틀린 상자 수. E3 은 판 묶음도 참고로")}
    out = {"meta": meta, "checks": checks, "summary": res, "compare_vs_A": cmp, "verdict": verdict,
           "scenes": {"E1": {s["name"]: {"fold": s["fold"], "winner": s["winner"], "boxes": r1[s["name"]]} for s in s1},
                      "E3_test": {s["name"]: {"fold": s["fold"], "phase": s["phase"], "boxes": r3t[s["name"]]} for s in s3t},
                      "E3_dev": {s["name"]: {"fold": s["fold"], "phase": s["phase"], "boxes": r3d[s["name"]]} for s in s3d}}}
    meta["secs"] = round(time.time() - t0, 1)
    path = (Path(smoke) / "eval_D_smoke.json") if smoke else OWN / "eval_D.json"
    path.write_text(json.dumps(out, ensure_ascii=False, default=float), encoding="utf-8")
    if smoke:  # 숫자는 찍지 않는다(오류 확인용)
        print("smoke eval 끝까지 돎:", sorted(out["summary"]), sorted(verdict), "E1 장면", len(s1), "개발", len(s3d), path, f"{meta['secs']}초", flush=True)
        return
    print(roe.table("E1 화료 상자 — D", res["E1"], True))
    print(roe.table("E3 시험(11-07 오후) — D", res["E3_test"], False))
    for ph, r in res["E3_test_by_phase"].items():
        print(roe.table(f"E3 시험 — {ph} — D", r, False))
    print("E3 시험 헛 hand 펼침/아님", res["E3_test_open_vs_not"])
    print(roe.table("E3 개발(10-31) — D", res["E3_dev"], False))
    for ph, r in res["E3_dev_by_phase"].items():
        print(roe.table(f"E3 개발 — {ph} — D", r, False))
    print("E3 개발 헛 hand 펼침/아님", res["E3_dev_open_vs_not"])
    print("\n## E4 회전 일치 — D", json.dumps(res["E4"]["by_k"], ensure_ascii=False), res["E4"]["total"], res["E4"]["owned"], "다른 상자", len(res["E4"]["diff"]))
    print("\n## D − A", json.dumps(cmp, ensure_ascii=False, indent=1))
    print("\n## 판정", json.dumps(verdict, ensure_ascii=False))
    print(path, f"{meta['secs']}초")


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["test", "regress", "samples", "compare", "train", "eval"])
    ap.add_argument("--smoke", default=None, help="train·eval: 아주 작은 설정으로 끝까지 도는지만(결과는 이 폴더에)")
    ap.add_argument("--fast", action="store_true", help="regress: ②③④만(① 은 이전 결과를 옮겨 적음)")
    a = ap.parse_args()
    OWN.mkdir(parents=True, exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")
    log = (Path(a.smoke) / f"log_d_{a.cmd}.txt") if a.smoke else OWN / f"log_d_{a.cmd}.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = rot.Tee(log)
    torch.set_num_threads(8)
    print(f"=== {a.cmd} 시작 {time.strftime('%Y-%m-%d %H:%M:%S')}" + (" (smoke)" if a.smoke else ""), flush=True)
    if a.cmd == "test":
        print(json.dumps(cmd_test(), ensure_ascii=False, indent=1, default=str))
        print("단위 테스트 통과", flush=True)
    elif a.cmd == "regress":
        cmd_regress(a.fast)
    elif a.cmd == "samples":
        cmd_samples()
    elif a.cmd == "compare":
        cmd_compare()
    elif a.cmd == "train":
        cmd_train(a.smoke)
    else:
        cmd_eval(a.smoke)


if __name__ == "__main__":
    main()
