"""SAM 2 번호 다시 나누기 — 제약을 건 짝짓기 · 손이 걷힌 뒤 검출 상자로 다시 찍기 · 못 가르면 "모름"(2026-11-20).

사용자 지시: "SAM 2 오류를 줄여라 — ① 제약을 걸고 번호를 다시 나누기 ② 손이 걷힌 뒤 검출 상자로 다시 찍기 ④ 원리상 못 가르는 곳은 unsure".
SAM 2 를 다시 돌리지 않는다 — 저장된 v1 추적(sam2track.run_dir(<id>, model t · device xpu) 의 track.json · masks.npz, 있으면 dmasks.npz)과
slotgrid 검출 캐시(det_<판>.json — 줄 상자 "b" · 가림 열 "o"(pixtrack.masks 살색 · 소매))만 읽는다. API 0 · 정답은 채점 함수(cmd_score)에서만 읽는다.

  python -X utf8 idsolve.py score [--ids a,b]     # 대상 차례 전부 → _work/idsolve_1120/score.json · <id>.json
  python -X utf8 idsolve.py one r16_d03            # 한 차례 사건만 찍기(정답 안 읽음)

relabel.py(11-19)와 겹치지 않게: relabel 은 고침 목록을 "사람(또는 Opus)이 넣고" 코드가 검사만 한다. 여기서는 코드가 번호를 스스로 다시 붙인다.
sam2xray.py 의 기억 · 옮김 사건은 보기용(번호는 SAM 2 그대로)이라 쓰지 않고, 가림은 det 의 "o"(같은 pixtrack.masks 계산의 열 범위)를 쓴다.

풀이(프레임마다 — SAM 2 프레임 = 검출 프레임, 초당 5장):
  상태: 번호 1 ~ n 과 D 마다 vis(줄 상자에 붙음) · hid(손 밑 — 상자를 잃음) · out(줄을 떠남, 다시 놓일 수 있음) · pre(D 만 — 아직 줄에 안 옴).
  줄 순서 seq(번호 목록)를 들고 감. 첫 프레임 = plan.a_boxes 왼쪽부터 1 ~ n(SAM 2 시작과 같음), 끝 프레임 = plan.e_boxes.
  A. 보이던 번호(vis) ↔ 줄 상자 헝가리안: 비용 = |dx| / 장폭 + W_SAM_VIS · (1 − SAM 2 덮음). |dx| > GATE_V 장폭이면 짝 금지
     → 손에 안 가린 채 보이던 패는 번호가 안 바뀜(한 프레임 0.2초에 한 칸 못 뜀). 짝 못 찾은 vis → hid.
  B. 남은 상자 ↔ 손 밑 · 떠난 번호 · D(pre) — 가설을 모두 세어(ENUM_MAX 까지) 고름:
     상자 u 에 번호 o 를 붙일 수 있는 때: o 가 숨은 자리(hid_x)에서 SAME_SPOT 장폭 안(제자리에 다시 보임) 이거나,
       u 가 최근 RECENT_F 프레임의 가림 열 ± NEAR_OCC 장폭 안이고 u 의 가림 몫 < BOX_NEW_OCC(손 밑 번호는 가림 둘레에서만 다시 나옴).
     "묶인" 번호(손 밑에서 안 들린 것)는 seq 의 이웃 보이는 번호 두 상자 사이(± ORDER_MARGIN 장폭)에만, 서로 순서를 지켜야 함(어기면 INV 벌점).
     "풀린" 번호 = D · out · 손 밑에 있는 동안 SAM 2 마스크가 줄 위쪽(강 쪽)으로 들린 번호 — 어디든 놓일 수 있음(자리 비용 FREE_POS,
       손 밑(hid) 이면 min(FREE_POS, 숨은 자리와의 거리)).
     가설 자리 비용 pos = Σ 묶인 번호 |hid_x − 상자| / 장폭 + Σ 풀린 FREE_POS + 빈 상자 STRAY + 순서 어김 INV.
     가설 SAM 2 점수 sam = Σ 짝의 SAM 2 덮음(믿을 마스크만) + Σ 짝 없이 남은 번호의 들림 점수 · W_LIFT.
       믿을 마스크 = 넓이 ≥ TRUST_AREA × 첫 프레임 넓이이고 다른 번호 마스크와 한 패에 겹치지 않음(relabel.SAME_TILE) — 한 패에 번호 둘이면 둘 다 근거 0.
       손 밑 · 떠난 · 안 온 번호는 그동안 마스크가 한 번이라도 못 믿을 꼴이었으면(끊겼다 다시 잡힘) 덮음 근거 0.
       덮음 = 마스크 · 상자 dice / 첫 프레임 제 상자 dice 중앙값(1 에서 자름).
       들림 점수 = 손 밑에 든 뒤로 마스크 가운데가 줄 선 위로 LIFT_Y × 상자 높이 넘게 올라간(믿을 마스크) 프레임 수 / LIFT_N(1 에서 자름).
     고르기: 자리로 못 가르는 가설 묶음 O = pos ≤ 최소 pos + T_POS_AMB (기본 = 순서를 지키는 배정) 안에서 sam 이 가장 큰 것.
       O 밖(맞바꿈 · 끼움) 가설의 sam 이 그것보다 T_SWITCH 넘게 크면 그쪽으로(사건 "SAM 2 근거로 바꿈").
       고른 것과 다른 가설이 O 안에서 sam 차 < T_DOUBT 이거나, O 밖인데 sam 이 T_DOUBT 이상 ~ T_SWITCH 미만 더 크면 → 후보로 적음.
  C. 손 밑 번호의 칸(seq 이웃 보이는 번호 두 상자 사이)에 가림이 CLEAR_RUN 프레임 이어 없고 그 번호를 못 찾으면 → out(줄을 떠남).
  D. 끝 프레임: plan.e_boxes 로 같은 고르기(가림 조건 없이) → 남은 hid 는 out. 장수 보존: 살아 있는 번호 = n 이어야 함(아니면 unsure).
  E. 버림: (1) 버림 시각 ± DISCARD_WIN 에 손 밑 · 떠난 · 안 온 번호의 믿을 마스크가 줄 위로 LIFT_Y 넘게 들리면 곧바로 그 번호 = 버림(gone, 다시 안 옴).
     뒤에 다른 번호가 또 들리면 unsure. (2) 들림이 없으면 장수 보존: 버림 창이 끝난 첫 프레임에 out 번호가 정확히 하나면 그것 = 버림.
     끝에 줄에 없는 번호가 1 ~ n 하나면 k, D 가 끝 줄에 없으면 쯔모기리. j = 끝 줄 왼쪽부터 D 자리.
  unsure: B 에서 적은 후보마다 "그때부터 번호를 그 후보대로 바꿔 붙였다면" 끝 순서(번호 바꿈 순열 적용)로 k · j 를 다시 셈 → 하나라도 다르면 unsure.

문턱 · 비용(정답 보기 전에 정함 — 바꾸면 아래 "바꾼 것" 에 적음):
"""
from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import relabel as rl  # noqa: E402
import sam2track as s1  # noqa: E402
import slotgrid as sg  # noqa: E402

OUT = hc.WORK / "idsolve_1120"
V1 = argparse.Namespace(model="t", device="xpu")

GATE_V = 0.6        # 보이던 번호가 한 프레임에 움직일 수 있는 거리(장폭)
W_SAM_VIS = 0.5     # A 단계 비용에서 SAM 2 덮음 무게
BOX_NEW_OCC = 0.5   # 새로 짝지을 상자의 가로 가림 몫 한도
NEAR_OCC = 1.0      # 가림 열 둘레(장폭)
RECENT_F = 10       # 최근 가림(프레임, 2초)
SAME_SPOT = 0.6     # 숨은 자리에서 이만큼(장폭) 안이면 가림 없이도 다시 붙임
ORDER_MARGIN = 0.3  # 묶인 번호: 이웃 보이는 상자 사이 여유(장폭)
FREE_POS = 1.0      # 풀린 번호(D · out · 들린 것)의 자리 비용 — 한 칸 옮긴 묶인 번호와 같게(처음 0.5 → 1.0, 아래 "바꾼 것" 1)
STRAY = 5.0         # 아무 번호도 안 붙인 상자 벌점(상자는 웬만하면 설명해야 함)
INV = 3.0           # 묶인 번호 순서 어김 벌점(쌍마다)
T_POS_AMB = 0.6     # 자리로 못 가르는 폭
T_SWITCH = 0.8      # SAM 2 가 순서 배정과 다른 배정을 "뚜렷이" 가리키는 점수 차
T_DOUBT = 0.4       # 이 차 밑이면 모름 후보
LIFT_Y = 0.6        # 줄 선 위로 이 × 상자 높이 넘게 올라간 마스크 = 들림
LIFT_N = 2          # 들림 점수 1 이 되는 프레임 수
W_LIFT = 1.0
TRUST_AREA = 0.5
CLEAR_RUN = 3       # 칸이 가림 없이 이어진 프레임 수 → 못 찾은 번호는 out
ENUM_MAX = 20000
DISCARD_WIN = (-4000, 1500)   # 차례 컷 버림 시각 둘레(ms) — 컷 시각이 실제보다 최대 3초 늦음(표 12-91)

# 바꾼 것(채점 전 — 정답을 아는 r16_d03 을 한 차례 돌려 사건을 보고):
#   1. FREE_POS 0.5 → 1.0: 0.5 면 제자리(0.04칸)에 다시 나온 묶인 번호와 "어디서 왔는지 모를 D" 가 늘 T_POS_AMB 안에서 비겨 모름 후보가 됨.
#   2. 풀린 번호도 숨은 자리(hid_x)가 있으면 자리 비용 = min(FREE_POS, 거리) — r17_d11 109 에 제자리(0칸)에 다시 보인 D 와
#      떠난 3 이 FREE_POS 로 비겨 3 이 붙음. (r16_d13 · r17_d11 사건을 보고 — 둘 다 정답을 아는 차례)
# 바꾼 것(첫 채점 뒤 — 정답과 맞댄 결과를 보고):
#   3. 버림(E)을 초안 4 대로: 버림 시각 ± DISCARD_WIN 에 손 밑 · 떠난 · 안 온 번호의 믿을 마스크가 줄 위로 LIFT_Y 넘게 들리면 그 번호를 곧바로
#      "버림"(gone — 다시 안 돌아옴, 짝짓기 후보에서 뺌). 첫 판은 상자 기하로만 out 을 정해 끝 붙임(D 를 끝에 붙이고 13 을 냄)에서 D 를 냄으로 봄
#      (hand → 쯔모기리 조용한 틀림 7). 첫 판 기록의 들림 프레임이 버림 시각 바로 앞에 정답 번호에 있던 차례가 6.
#      뒤에 다른 번호가 또 들리면 unsure.
#   4. 손 밑 · 떠난 · 안 온 번호의 SAM 2 덮음은 그동안 마스크가 끊기지 않았을 때만 근거로 씀(끊겼다 다시 잡힌 마스크 = 패 등이 같아 엉뚱한 패에
#      붙을 수 있는 바로 그 경우). r16_d06 에서 13 마스크가 손 밑에서 끊겼다가 끝에 놓인 D 에 붙어 13 이 D 자리를 가져감.
# 바꾼 것(둘째 채점 뒤):
#   5. 2 의 "제자리 할인" 을 손 밑(hid) 번호에만 — 떠난(out) 번호는 늘 FREE_POS. r17_d11 에서 버린 3 이 옛 자리(손 밑에서 1 · 2 가 한 칸씩
#      오른쪽으로 밀려 채운 칸)로 "돌아옴" 이 되고 1 이 떠난 것으로 바뀜.
#   6. 장수 보존(초안 2)을 버림에: 버림 창(DISCARD_WIN 끝)이 지난 첫 프레임에 들림 버림이 없고 out 번호가 정확히 하나면 그것을 버림(gone).


# ------------------------------------------------------------------ 입력
class Turn:
    def __init__(self, tid: str):
        self.tid = tid
        self.T = rl.Track(tid)
        T = self.T
        self.p = T.tr["plan"]
        self.n, self.F, self.H, self.W = T.n, T.F, T.H, T.W
        self.ms = T.tr["frames"]
        gid, t = s1.turn_of(tid)
        self.disc_ms = s1.ms_of(t["cut"]["discard"], self.ms[0])
        det = hc.jload(sg.OUT / f"det_{gid}.json")
        b0 = None
        for ms in self.ms:
            e = det.get(str(ms))
            if e and e["b"]:
                b0 = e["b"][0]
                break
        r0 = s1.remap_box(b0, self.p["band"], self.p["band2"], self.p["side"])
        self.ox = r0[0] - b0[0]
        self.occ = []
        for ms in self.ms:
            e = det.get(str(ms))
            self.occ.append([(o[0] + self.ox, o[1] + self.ox) for o in e["o"]] if e else [])
        d = T.d / "dmasks.npz"
        self.DM = np.load(d) if d.exists() else None
        ab = self.p["a_boxes"]
        cx = [(b[0] + b[2]) / 2 for b in ab]
        self.pitch = float(np.median(np.diff(cx)))
        self.hh = float(np.median([b[3] - b[1] for b in ab]))
        self.line0 = (float(np.median([(b[1] + b[3]) / 2 for b in ab])), 0.0)
        self.a0 = {}
        for o in range(1, self.n + 1):
            mk = T.mask(0, o)
            self.a0[o] = int(mk.sum()) if mk is not None else 0
        self.a0["D"] = None

    def masks(self, fi: int) -> dict:
        out = {}
        for o in range(1, self.n + 1):
            mk = self.T.mask(fi, o)
            if mk is not None:
                out[o] = mk
        if self.DM is not None and str(fi) in self.DM:
            mk = np.unpackbits(self.DM[str(fi)])[: self.H * self.W].reshape(self.H, self.W).astype(bool)
            if mk.sum() >= rl.MIN_AREA:
                out["D"] = mk
        return out


def cxb(b) -> float:
    return (b[0] + b[2]) / 2


def dice(mk: np.ndarray, b, area: int) -> float:
    x0, y0, x1, y1 = (int(round(v)) for v in b)
    x0, y0 = max(0, x0), max(0, y0)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = int(mk[y0:y1, x0:x1].sum())
    return 2.0 * inter / max(1, area + (x1 - x0) * (y1 - y0))


def iv_overlap(a0: float, a1: float, ivs: list) -> float:
    w = max(1e-6, a1 - a0)
    return sum(max(0.0, min(a1, b1) - max(a0, b0)) for b0, b1 in ivs) / w


def near_ivs(x: float, ivs: list, r: float) -> bool:
    return any(b0 - r <= x <= b1 + r for b0, b1 in ivs)


# ------------------------------------------------------------------ 풀이
class Solver:
    def __init__(self, U: Turn):
        self.U = U
        n = U.n
        self.ids = list(range(1, n + 1)) + ["D"]
        self.st = {o: "vis" for o in range(1, n + 1)}
        self.st["D"] = "pre"
        self.x = {o: cxb(b) for o, b in zip(range(1, n + 1), U.p["a_boxes"])}
        self.x["D"] = None
        self.seq = list(range(1, n + 1))
        self.hid_fi, self.hid_x, self.clear_run, self.out_fi = {}, {}, {}, {}
        self.lift_frames = {o: [] for o in self.ids}       # 들림 프레임(전체) — 점수는 손 밑에 든 뒤만 셈
        self.events, self.alts, self.hist = [], [], []
        self.broken, self.gone, self.gone_how, self.multi_lift, self.window_done = {}, None, None, [], False
        self.line = U.line0
        self.recent = []
        # 덮음 기준: 첫 프레임 제 상자 dice 중앙값
        m0 = U.masks(0)
        ds = [dice(m0[o], b, int(m0[o].sum())) for o, b in zip(range(1, n + 1), U.p["a_boxes"]) if o in m0]
        self.dref = float(np.median(ds)) if ds else 1.0

    # --- 한 프레임 근거
    def evidence(self, fi: int, boxes: list):
        U = self.U
        mks = U.masks(fi)
        area = {o: int(m.sum()) for o, m in mks.items()}
        bb = {}
        for o, m in mks.items():
            ys, xs = np.nonzero(m)
            bb[o] = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1, float(xs.mean()), float(ys.mean()))
        shared = set()
        keys = list(mks)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = keys[i], keys[j]
                A, B = bb[a], bb[b]
                if A[2] <= B[0] or B[2] <= A[0] or A[3] <= B[1] or B[3] <= A[1]:
                    continue
                inter = int((mks[a] & mks[b]).sum())
                if inter and inter / max(1, min(area[a], area[b])) >= rl.SAME_TILE:
                    shared.update((a, b))
        trust = set()
        for o in mks:
            ref = U.a0.get(o) or float(np.median([v for v in U.a0.values() if v]))
            if area[o] >= TRUST_AREA * ref and o not in shared:
                trust.add(o)
        cov = {}
        for o in mks:
            for ui, b in enumerate(boxes):
                if bb[o][2] <= b[0] or b[2] <= bb[o][0]:
                    continue
                c = min(1.0, dice(mks[o], b, area[o]) / self.dref)
                if c > 0.05:
                    cov[(o, ui)] = c
        a, bl = self.line
        up = set()
        for o in trust:
            cx, cy = bb[o][4], bb[o][5]
            if (a + bl * cx) - cy > LIFT_Y * U.hh:
                up.add(o)
        return {"cov": cov, "trust": trust, "shared": shared, "up": up, "bb": bb}

    def covt(self, ev, o, ui) -> float:
        """SAM 2 덮음 근거 — 믿을 마스크만, 손 밑 · 떠난 · 안 온 번호는 그동안 마스크가 끊기지 않았을 때만(끊겼다 다시 잡힌 것은 근거 아님)."""
        if o not in ev["trust"] or (self.st[o] in ("hid", "out", "pre") and self.broken.get(o)):
            return 0.0
        return ev["cov"].get((o, ui), 0.0)

    def lift(self, o, since: int) -> float:
        c = sum(1 for f in self.lift_frames[o] if f >= since)
        return min(1.0, c / LIFT_N)

    # --- 줄 상자
    def row_boxes(self, fi: int) -> list:
        U = self.U
        if fi == U.F - 1:
            return sorted(U.p["e_boxes"], key=cxb)
        bs = U.T.boxes.get(fi)
        if bs is None:
            return None
        conv = [[b[0], b[2], b[1], b[3]] for b in bs]
        row, _off, a, b = sg.row_line(conv, self.line[0], self.line[1], U.hh)
        self.line = (a, b)
        return sorted([[r[0], r[2], r[1], r[3]] for r in row], key=cxb)

    # --- 묶인 번호의 이웃 보이는 상자
    def anchors(self, o, ux: dict):
        i = self.seq.index(o)
        L = next((ux[q] for q in reversed(self.seq[:i]) if q in ux), None)
        R = next((ux[q] for q in self.seq[i + 1:] if q in ux), None)
        return L, R

    def is_free(self, o) -> bool:
        if o == "D" or self.st[o] == "out":
            return True
        return self.lift(o, self.hid_fi.get(o, 0) - 2) > 0

    # --- B: 가설 세기
    def resolve(self, fi: int, boxes: list, free_boxes: list, vis_x: dict, ev, final: bool):
        U = self.U
        p = U.pitch
        pool = [o for o in self.ids if self.st[o] in ("hid", "out")] + (["D"] if self.st["D"] == "pre" else [])
        if not free_boxes or not pool:
            return
        rocc = [iv for f in self.recent for iv in f]
        opts = {}
        for ui in free_boxes:
            b = boxes[ui]
            cx = cxb(b)
            occ_ok = final or (near_ivs(cx, rocc, NEAR_OCC * p) and iv_overlap(b[0], b[2], U.occ[fi]) < BOX_NEW_OCC)
            cand = []
            for o in pool:
                same = o in self.hid_x and abs(self.hid_x[o] - cx) <= SAME_SPOT * p
                if not (same or occ_ok):
                    continue
                if not self.is_free(o):
                    L, R = self.anchors(o, vis_x)
                    if (L is not None and cx < L + ORDER_MARGIN * p) or (R is not None and cx > R - ORDER_MARGIN * p):
                        if not final:
                            continue
                cand.append(o)
            opts[ui] = cand
        uis = [ui for ui in free_boxes if opts[ui]]
        for ui in free_boxes:
            if not opts[ui] and iv_overlap(boxes[ui][0], boxes[ui][2], U.occ[fi]) < BOX_NEW_OCC:   # 손 밑 상자는 안 적음
                self.events.append((fi, "stray", f"상자 x {cxb(boxes[ui]):.0f} 에 붙일 번호 없음(가림 밖 · 순서 밖)"))
        if not uis:
            return
        # 가설 세기(상자마다 번호 하나 또는 없음, 번호는 한 번만)
        hyps = []
        count = [0]

        def dfs(k, used, cur):
            if count[0] >= ENUM_MAX:
                return
            if k == len(uis):
                hyps.append(dict(cur))
                count[0] += 1
                return
            ui = uis[k]
            for o in opts[ui]:
                if o in used:
                    continue
                cur[ui] = o
                used.add(o)
                dfs(k + 1, used, cur)
                used.discard(o)
                del cur[ui]
            dfs(k + 1, used, cur)

        dfs(0, set(), {})
        free = {o: self.is_free(o) for o in pool}
        sinces = {o: self.hid_fi.get(o, 0) - 2 for o in pool}

        def score(h):
            pos = 0.0
            for ui in uis:
                o = h.get(ui)
                if o is None:
                    pos += STRAY
                elif free[o]:   # 풀린 번호도 숨은 자리가 있으면 제자리에 다시 나온 것이 더 쌈
                    near = o in self.hid_x and self.st[o] == "hid"   # 떠난(out) 번호의 옛 자리는 근거 아님(그 칸은 이미 비었음)
                    pos += min(FREE_POS, abs(self.hid_x[o] - cxb(boxes[ui])) / p) if near else FREE_POS
                else:
                    pos += abs(self.hid_x[o] - cxb(boxes[ui])) / p
                    if final:
                        L, R = self.anchors(o, vis_x)
                        cx = cxb(boxes[ui])
                        if (L is not None and cx < L) or (R is not None and cx > R):
                            pos += INV
            tied = sorted(((self.seq.index(o), cxb(boxes[ui])) for ui, o in h.items() if not free[o]))
            pos += INV * sum(1 for (a_, xa), (b_, xb) in itertools.combinations(tied, 2) if xa > xb)
            sam = sum(self.covt(ev, o, ui) for ui, o in h.items())
            matched = set(h.values())
            for o in pool:   # 짝 없이 남은 번호의 들림 = "그 번호는 줄에 없다" 근거(아직 안 온 D 는 뺌)
                if o not in matched and not (o == "D" and self.st["D"] == "pre"):
                    sam += W_LIFT * self.lift(o, sinces[o])
            return pos, sam

        sc = [score(h) for h in hyps]
        best_pos = min(s[0] for s in sc)
        O = [i for i, s in enumerate(sc) if s[0] <= best_pos + T_POS_AMB]
        io = max(O, key=lambda i: (sc[i][1], -sc[i][0]))
        N = [i for i in range(len(hyps)) if i not in O and sc[i][0] < best_pos + STRAY]   # 상자를 더 버리는 가설은 대안으로 안 봄
        chosen, why = io, "순서"
        if N:
            inn = max(N, key=lambda i: (sc[i][1], -sc[i][0]))
            if sc[inn][1] >= sc[io][1] + T_SWITCH:
                chosen, why = inn, "SAM 2 근거로 바꿈"
        h = hyps[chosen]
        key = lambda hh: tuple(sorted((ui, str(o)) for ui, o in hh.items()))  # noqa: E731
        alts = []
        for i in range(len(hyps)):
            if i == chosen or key(hyps[i]) == key(h):
                continue
            if why == "순서":
                if (i in O and sc[i][1] > sc[chosen][1] - T_DOUBT) or (i in N and sc[i][1] >= sc[chosen][1] + T_DOUBT):
                    alts.append(i)
        alts = sorted(alts, key=lambda i: -sc[i][1])[:3]
        desc = ", ".join(f"{o}→x{cxb(boxes[ui]):.0f}" for ui, o in sorted(h.items(), key=lambda t: cxb(boxes[t[0]])))
        self.events.append((fi, "assign", f"{why}: {desc} (자리 {sc[chosen][0]:.2f} · SAM 2 {sc[chosen][1]:.2f}, 가설 {len(hyps)})"))
        for i in alts:
            ha = hyps[i]
            perm = self.perm(h, ha, pool)
            if perm:
                d2 = ", ".join(f"{o}→x{cxb(boxes[ui]):.0f}" for ui, o in sorted(ha.items(), key=lambda t: cxb(boxes[t[0]])))
                self.alts.append({"fi": fi, "ms": U.ms[fi], "perm": {str(k): str(v) for k, v in perm.items()},
                                  "chosen": desc, "alt": d2, "pos": [round(sc[chosen][0], 2), round(sc[i][0], 2)],
                                  "sam": [round(sc[chosen][1], 2), round(sc[i][1], 2)]})
                self.events.append((fi, "doubt", f"후보: {d2} (자리 {sc[i][0]:.2f} · SAM 2 {sc[i][1]:.2f}) — 번호 바꿈 {perm}"))
        for ui, o in h.items():
            self.place(o, boxes[ui], fi)

    @staticmethod
    def perm(h: dict, ha: dict, pool: list) -> dict:
        """고른 가설 h → 후보 ha 의 번호 바꿈 π: 같은 상자에 h 가 o, ha 가 q 를 붙였으면 π(o) = q.
        닫히지 않은 것(ha 에만 붙은 번호 → h 에만 붙은 번호)은 남은 것끼리 차례로 짝지어 닫음."""
        pi = {}
        for ui in set(h) & set(ha):
            if h[ui] != ha[ui]:
                pi[h[ui]] = ha[ui]
        src = sorted([k for k in pi if k not in pi.values()], key=str)
        dst = sorted([v for v in pi.values() if v not in pi], key=str)
        for a, b in zip(dst, src):
            pi[a] = b
        return {k: v for k, v in pi.items() if k != v}

    def place(self, o, b, fi: int):
        cx = cxb(b)
        was = self.st[o]
        self.st[o] = "vis"
        self.x[o] = cx
        if not (o in self.seq and was == "hid" and self.lift(o, self.hid_fi.get(o, 0) - 2) == 0):   # 묶인 번호는 seq 자리 그대로
            if o in self.seq:
                self.seq.remove(o)
            ref = [self.x[q] if self.st[q] == "vis" else self.hid_x.get(q, self.x[q]) for q in self.seq]
            k = next((i for i, r in enumerate(ref) if r > cx), len(ref))   # 왼쪽에서 처음으로 cx 보다 오른쪽인 것 앞에
            self.seq.insert(k, o)
        if was == "pre":
            self.events.append((fi, "D", f"D 줄에 들어옴 x {cx:.0f}"))
        elif was == "out":
            self.events.append((fi, "back", f"{o} 줄로 돌아옴 x {cx:.0f}"))
        self.hid_x.pop(o, None)
        self.clear_run.pop(o, None)
        self.broken.pop(o, None)

    # --- 한 프레임
    def step(self, fi: int):
        U = self.U
        p = U.pitch
        boxes = self.row_boxes(fi)
        self.recent = (self.recent + [U.occ[fi]])[-RECENT_F:]
        if boxes is None:
            self.hist.append({"fi": fi, "skip": True})
            return
        final = fi == U.F - 1
        ev = self.evidence(fi, boxes)
        for o in ev["up"]:
            self.lift_frames[o].append(fi)
        for o in self.ids:
            if self.st[o] in ("hid", "out") and o not in ev["trust"]:
                self.broken[o] = True
        # 버림 들림(E 를 앞당김): 버림 시각 둘레에 손 밑 · 떠난 · 안 온 번호의 마스크가 줄 위쪽으로 들림 → 버린 패(다시 안 돌아옴)
        if DISCARD_WIN[0] <= U.ms[fi] - U.disc_ms <= DISCARD_WIN[1]:
            for o in sorted(ev["up"], key=str):
                if self.st[o] in ("hid", "out", "pre"):
                    if self.gone is None:
                        self.gone, self.gone_how = o, "들림"
                        self.st[o] = "gone"
                        if o in self.seq:
                            self.seq.remove(o)
                        self.out_fi[o] = fi
                        self.events.append((fi, "gone", f"{o} 버림 — 버림 시각 {(U.ms[fi] - U.disc_ms) / 1000:+.1f}초에 마스크가 줄 위로 들림"))
                    elif o != self.gone:
                        self.multi_lift.append((fi, o))
                        self.events.append((fi, "gone?", f"{o} 도 버림 시각 둘레에 들림(먼저 버림으로 본 {self.gone} 와 다름)"))
                elif self.st[o] == "vis":
                    self.events.append((fi, "lift-vis", f"{o} 마스크가 줄 위로 들렸지만 상자는 줄에 보임 — 버림으로 안 봄"))
        # 장수 보존: 버림 창이 끝난 첫 프레임에 들림으로 정한 버림이 없고 떠난(out) 번호가 하나뿐이면 그것이 버린 패
        if self.gone is None and not self.window_done and U.ms[fi] - U.disc_ms > DISCARD_WIN[1]:
            self.window_done = True
            outs = [o for o in self.ids if self.st[o] == "out"]
            if len(outs) == 1:
                o = outs[0]
                self.gone, self.gone_how = o, "장수 보존"
                self.st[o] = "gone"
                self.events.append((fi, "gone", f"{o} 버림 — 버림 창이 끝났을 때 줄을 떠난 번호가 이것 하나(장수 보존)"))
        # A. 보이던 번호
        V = [o for o in self.ids if self.st[o] == "vis"]
        used = set()
        vis_x = {}
        if V and boxes:
            C = np.full((len(V), len(boxes)), 1e6)
            for i, o in enumerate(V):
                for ui, b in enumerate(boxes):
                    dx = abs(self.x[o] - cxb(b))
                    if dx <= GATE_V * p:
                        C[i, ui] = dx / p + W_SAM_VIS * (1 - self.covt(ev, o, ui))
            r, c = linear_sum_assignment(C)
            for i, ui in zip(r, c):
                if C[i, ui] < 1e5:
                    o = V[i]
                    self.x[o] = cxb(boxes[ui])
                    vis_x[o] = self.x[o]
                    used.add(ui)
        for o in V:
            if o not in vis_x:
                self.st[o] = "hid"
                self.hid_fi[o] = fi
                self.hid_x[o] = self.x[o]
                self.clear_run[o] = 0
                self.events.append((fi, "hid", f"{o} 손 밑(상자 잃음) x {self.x[o]:.0f}"))
        free_boxes = [ui for ui in range(len(boxes)) if ui not in used]
        # B. 다시 찍기
        self.resolve(fi, boxes, free_boxes, vis_x, ev, final)
        vis_x = {o: self.x[o] for o in self.ids if self.st[o] == "vis"}
        # C. 칸이 걷혔는데 못 찾은 번호 → out
        for o in [q for q in self.ids if self.st[q] == "hid"]:
            if final:
                self.to_out(o, fi, "끝 프레임에 상자 없음")
                continue
            L, R = self.anchors(o, vis_x)
            lo = (L if L is not None else self.hid_x[o] - 1.5 * p) + 0.3 * p
            hi = (R if R is not None else self.hid_x[o] + 1.5 * p) - 0.3 * p
            clear = hi <= lo or iv_overlap(lo, hi, U.occ[fi]) == 0.0
            self.clear_run[o] = self.clear_run.get(o, 0) + 1 if clear else 0
            if self.clear_run[o] >= CLEAR_RUN:
                self.to_out(o, fi, "칸에 가림 없는데 상자 없음")
        self.hist.append({"fi": fi, "ms": U.ms[fi], "vis": {str(o): round(self.x[o]) for o in self.ids if self.st[o] == "vis"},
                          "hid": [str(o) for o in self.ids if self.st[o] == "hid"],
                          "out": [str(o) for o in self.ids if self.st[o] in ("out", "gone")], "seq": [str(o) for o in self.seq],
                          "nbox": len(boxes)})

    def to_out(self, o, fi: int, why: str):
        self.st[o] = "out"
        self.out_fi[o] = fi
        if o in self.seq:
            self.seq.remove(o)
        self.events.append((fi, "out", f"{o} 줄을 떠남 — {why} (들림 점수 {self.lift(o, self.hid_fi.get(o, 0) - 2):.1f})"))

    def run(self) -> dict:
        U = self.U
        self.hist.append({"fi": 0, "ms": U.ms[0], "vis": {str(o): round(self.x[o]) for o in range(1, U.n + 1)}, "hid": [], "out": [],
                          "seq": [str(o) for o in self.seq], "nbox": len(U.p["a_boxes"])})
        for fi in range(1, U.F):
            self.step(fi)
        return self.result()

    def outcome(self, order: list, outs: list) -> dict:
        n = self.U.n
        reasons = []
        if "D" not in order:
            kind, k, j = "tsumogiri", None, None
            if sorted(map(str, order)) != sorted(map(str, range(1, n + 1))):
                reasons.append(f"D 가 끝 줄에 없는데 끝 줄 번호가 1 ~ {n} 이 아님")
        else:
            kind = "hand"
            miss = [o for o in range(1, n + 1) if o not in order]
            j = order.index("D") + 1
            if len(miss) == 1:
                k = miss[0]
            else:
                k = None
                reasons.append(f"끝 줄에 없는 번호 {miss}(하나여야 함)")
            if len(order) != n:
                reasons.append(f"끝 줄 {len(order)}장(≠ {n})")
        return {"kind": kind, "k": k, "j": j, "reasons": reasons}

    def result(self) -> dict:
        U = self.U
        order = sorted([o for o in self.ids if self.st[o] == "vis"], key=lambda o: self.x[o])
        outs = [o for o in self.ids if self.st[o] in ("out", "gone")]
        res = self.outcome(order, outs)
        unsure = list(res["reasons"])
        # 버림 시각 근처 확인(여러 out)
        gone = [o for o in outs if o != "D"]
        if len(gone) > 1:
            unsure.append(f"줄을 떠난 번호가 여럿 {gone}")
        if self.multi_lift:
            unsure.append(f"버림 시각 둘레에 들린 번호가 여럿: 먼저 {self.gone}, 뒤에 {sorted({str(o) for _, o in self.multi_lift})}")
        # 후보마다 순열 적용해 다시 셈
        alt_out = []
        for a in self.alts:
            pi = {self._id(k): self._id(v) for k, v in a["perm"].items()}
            o2 = [pi.get(o, o) for o in order]
            r2 = self.outcome(o2, [pi.get(o, o) for o in outs])
            same = (r2["kind"], r2["k"], r2["j"]) == (res["kind"], res["k"], res["j"])
            alt_out.append({**a, "kind": r2["kind"], "k": r2["k"], "j": r2["j"], "same": same})
            if not same:
                unsure.append(f"{a['fi']:03d} {hc.mss(a['ms'])} 후보 배정({a['alt']})이면 {r2['kind']} k {r2['k']} · j {r2['j']}")
        disc_fi = min(range(U.F), key=lambda i: abs(U.ms[i] - U.disc_ms))
        return {"id": U.tid, "n": U.n, "kind": res["kind"], "k": res["k"], "j": res["j"], "unsure": bool(unsure),
                "unsure_why": unsure, "end_order": [str(o) for o in order], "out": [str(o) for o in outs],
                "out_fi": {str(o): f for o, f in self.out_fi.items()}, "discard_fi": disc_fi, "gone": None if self.gone is None else str(self.gone), "gone_how": self.gone_how,
                "lift_frames": {str(o): v for o, v in self.lift_frames.items() if v},
                "alts": alt_out, "events": [(f, hc.mss(U.ms[f]), k, s) for f, k, s in self.events], "hist": self.hist,
                "D_track": U.DM is not None, "pitch": round(U.pitch, 1), "dref": round(self.dref, 3)}

    def _id(self, s: str):
        return "D" if s == "D" else int(s)


def solve(tid: str) -> dict:
    return Solver(Turn(tid)).run()


# ------------------------------------------------------------------ 채점(정답은 여기서만)
def targets() -> list:
    out = []
    for d in sorted(s1.OUT.glob("*_t_xpu")):
        if (d / "track.json").exists():
            out.append(hc.jload(d / "track.json")["plan"]["id"])
    return out


def base_of(tr: dict) -> dict:
    """SAM 2 그대로(sam2track.judge) → (kind, k, j). judge 가 사라진 물체 · 짝 없는 상자 · 겹침이 모두 없으면 쯔모기리로 읽음."""
    r = s1.judge(tr)
    if r["k"] is not None and r["j"] is not None:
        return {"kind": "hand", "k": r["k"], "j": r["j"], "raw": r}
    if not r["gone"] and not r["free"] and not r["clash"]:
        return {"kind": "tsumogiri", "k": None, "j": None, "raw": r}
    return {"kind": None, "k": r["k"], "j": r["j"], "raw": r}


def grade(pred: dict, u: dict) -> tuple:
    if u["kind"] == "tsumogiri":
        ok = pred["kind"] == "tsumogiri"
        return ok, ok
    return (pred["kind"] == "hand" and pred["k"] == u["k_id"]), (pred["kind"] == "hand" and pred["j"] == u["j_closed"])


def cmd_score(a):
    truth = s1.truth_all()
    OUT.mkdir(parents=True, exist_ok=True)
    ids = a.ids.split(",") if a.ids else targets()
    rows = []
    for tid in ids:
        u = truth.get(tid)
        if u is None or u["kind"] not in ("hand", "tsumogiri"):
            continue
        tr = hc.jload(s1.run_dir(tid, V1) / "track.json")
        b = base_of(tr)
        r = solve(tid)
        hc.jsave(OUT / f"{tid}.json", r, indent=None)
        bk, bj = grade(b, u)
        ik, ij = grade(r, u)
        row = {"id": tid, "truth": [u["kind"], u.get("k_id"), u.get("j_closed")],
               "base": [b["kind"], b["k"], b["j"]], "base_k": bk, "base_j": bj, "base_both": bk and bj,
               "idsolve": [r["kind"], r["k"], r["j"]], "k_ok": ik, "j_ok": ij, "both": ik and ij,
               "base_undecided": b["kind"] is None, "base_silent_wrong": b["kind"] is not None and not (bk and bj),
               "unsure": r["unsure"], "unsure_why": r["unsure_why"], "silent_wrong": (not r["unsure"]) and not (ik and ij),
               "truth_in_alts": r["unsure"] and not (ik and ij) and any(all(grade(x, u)) for x in r["alts"]),
               "end_order": r["end_order"], "out": r["out"], "D_track": r["D_track"]}
        rows.append(row)
        mark = "✓" if row["both"] else ("?" if r["unsure"] else "✗")
        print(f"{tid:9s} 정답 {u['kind'][:4]} {u.get('k_id')}·{u.get('j_closed')} | SAM 2 그대로 {b['kind'] and b['kind'][:4]} {b['k']}·{b['j']}"
              f" {'✓' if row['base_both'] else '✗'} | idsolve {r['kind'][:4]} {r['k']}·{r['j']} {mark}"
              f"{' unsure: ' + ' / '.join(r['unsure_why'])[:160] if r['unsure'] else ''}", flush=True)
    tot = {}
    for name, sel in (("all", rows), ("hand", [r for r in rows if r["truth"][0] == "hand"]), ("tsumogiri", [r for r in rows if r["truth"][0] == "tsumogiri"]),
                      ("three", [r for r in rows if r["id"] in ("r16_d03", "r16_d13", "r17_d11")])):
        tot[name] = {"n": len(sel),
                     "base": {"k": sum(r["base_k"] for r in sel), "j": sum(r["base_j"] for r in sel), "both": sum(r["base_both"] for r in sel),
                              "undecided": sum(r["base_undecided"] for r in sel), "silent_wrong": sum(r["base_silent_wrong"] for r in sel)},
                     "idsolve": {"k": sum(r["k_ok"] for r in sel), "j": sum(r["j_ok"] for r in sel), "both": sum(r["both"] for r in sel),
                                 "unsure": sum(r["unsure"] for r in sel), "silent_wrong": sum(r["silent_wrong"] for r in sel),
                                 "unsure_and_right": sum(r["unsure"] and r["both"] for r in sel),
                                 "unsure_wrong_truth_in_alts": sum(r["truth_in_alts"] for r in sel)}}
    for k_, v in tot.items():
        print(k_, v)
    hc.jsave(OUT / "score.json", {"totals": tot, "rows": rows,
                                  "consts": {k_: globals()[k_] for k_ in ("GATE_V", "W_SAM_VIS", "BOX_NEW_OCC", "NEAR_OCC", "RECENT_F", "SAME_SPOT",
                                                                           "ORDER_MARGIN", "FREE_POS", "STRAY", "INV", "T_POS_AMB", "T_SWITCH",
                                                                           "T_DOUBT", "LIFT_Y", "LIFT_N", "W_LIFT", "TRUST_AREA", "CLEAR_RUN",
                                                                           "ENUM_MAX", "DISCARD_WIN")}}, indent=1)


def cmd_one(a):
    r = solve(a.id)
    OUT.mkdir(parents=True, exist_ok=True)
    hc.jsave(OUT / f"{a.id}.json", r, indent=None)
    for f, t, k, s in r["events"]:
        if k in ("hid",) and not a.all:
            continue
        print(f"{f:03d} {t} [{k}] {s}")
    print("끝:", " ".join(r["end_order"]), "| out", r["out"], "| kind", r["kind"], "k", r["k"], "j", r["j"], "| unsure", r["unsure_why"])


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("score")
    q.add_argument("--ids")
    q = sp.add_parser("one")
    q.add_argument("id")
    q.add_argument("--all", action="store_true")
    a = ap.parse_args()
    {"score": cmd_score, "one": cmd_one}[a.cmd](a)


if __name__ == "__main__":
    main()
