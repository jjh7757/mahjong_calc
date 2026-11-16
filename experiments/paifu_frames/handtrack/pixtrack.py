"""토큰 없는 픽셀 추적으로 손패 사건 판정(2026-11-16, 계획서 3단계 "추가 2" — 방법·채점은 결과 전에 적음).

프레임마다(초당 10장 전부) 손패 띠를 대국자 시점으로 돌려 줄을 패 덩어리(run)로 나누고 피부(손) 가림 열을 표시한다.
  python -X utf8 pixtrack.py timeline <판 id> <구간 번호…>     # 구간의 프레임별 덩어리 줄글(다듬기용)
  python -X utf8 pixtrack.py run <판 id> [--out 파일]             # 차례마다 판정 → 채점은 score
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

PITCH = 40.0  # 1496 녹화의 세운 패 한 장 폭(px) — 판마다 정지 프레임으로 다시 잼
OCCL = True  # v6: 소매도 가림으로(False = v5)
FLOW_V7 = False  # v7: 4단계 새 틈을 손 닿은 것까지 먼저 봄 — 개발 두 판에서 들어간 칸이 나빠져(metrics 표 12-17) 기본 끔
MIN_GAP = 6  # 이보다 넓은 빈 열이면 덩어리를 끊음(패 사이 어두운 줄은 1~3px)
OLD_TRUTH = False  # True = 11-16 저녁에 고치기 전 들어간 칸 정답(rescore.py 가 전·후 비교에 씀)
INSERT_TRUTH = json.loads((Path(__file__).resolve().parent / "insert_truth_1116.json").read_text(encoding="utf-8"))


def masks(v: np.ndarray):
    hsv = cv2.cvtColor(v, cv2.COLOR_RGB2HSV)
    h, s, val = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    skin = (h >= 3) & (h < 32) & (s > 40) & (val > 70)
    felt = (h >= 35) & (h <= 95) & (s > 50)
    white = (s < 45) & (val > 170)
    back = ((h >= 115) | (h <= 2)) & (s >= 35) & (val > 120) & ~skin  # 보라(r18)·분홍(n03) 등 띠
    if OCCL:
        # v6(11-16 사용자 "가짜 빈칸은 색 덩어리도 똑같지 않냐"): 피부만 손으로 보면 소매(체크무늬)가 줄을 덮어도 손 표시가 없다.
        # 펠트도 패 색(흰 면·등 띠·회색 윗면)도 아닌 화소를 손(가림)으로 더한다. 회색 윗면 = 채도 낮고 밝기 120 이상.
        grey = (s < 45) & (val >= 120)
        top = (h >= 95) & (h < 115) & (val > 110)  # r18 의 푸른 회색 윗면(색상 102~111) — 남색 소매는 더 어둡다
        occ = (~felt & ~white & ~back & ~grey & ~top).astype(np.uint8)
        occ = cv2.morphologyEx(occ, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8)) > 0  # 패 사이 틈·옆면 그림자 같은 가는 것은 지움
        skin = skin | occ
    return skin, felt, white, back


class Row:
    """판 하나의 줄 높이(흰 면 행 범위)를 정지 프레임에서 잡아 두고 프레임마다 덩어리를 뽑는다."""

    def __init__(self, gid: str):
        self.gid = gid
        self.cfg = hc.config(gid)
        self.sg = hc.jload(hc.OUT / gid / "segments.json")
        st = max(self.sg["still"], key=lambda x: x["dur"])
        v = self.view(hc.nearest((st["ms0"] + st["ms1"]) // 2))
        _, felt, white, back = masks(v)
        rows = np.flatnonzero(white.mean(1) > 0.08)
        # 가장 긴 연속 행 묶음 = 흰 면
        best, cur = None, None
        for y in rows:
            cur = [y, y] if cur is None or y != cur[1] + 1 else [cur[0], y]
            if best is None or cur[1] - cur[0] > best[1] - best[0]:
                best = list(cur)
        self.y0, self.y1 = best
        brows = np.flatnonzero(back[:self.y0 + 10].mean(1) > 0.25)
        self.b0, self.b1 = (int(brows.min()), int(brows.max())) if len(brows) else (max(0, self.y0 - 8), self.y0)
        runs = self.runs_of(v)[0]
        ws = [r["x1"] - r["x0"] for r in runs]
        n = sum(max(1, round(w / PITCH)) for w in ws)
        self.pitch = sum(ws) / n if n else PITCH

    def view(self, ms: int) -> np.ndarray:
        return hc.band_crop(hc.load(ms), self.cfg["sheet_band"], self.cfg["side"])

    def runs_of(self, v: np.ndarray, pitch: float | None = None, which: str = "white"):
        skin, felt, white, back = masks(v)
        if which == "back":  # 손가락은 대국자 쪽(아래)에서 와서 먼 쪽 등 띠는 덜 가린다
            ys = slice(self.b0, self.b1 + 1)
            tile_col = back[ys].mean(0) > 0.45
        else:
            # v3: 흰 면만 보면 등 띠가 두꺼운 판(n03 분홍)에서 줄 대부분이 문턱 밑 → 펠트도 손도 아닌 화소
            # v4: 판 도중 줄이 위아래로 옮겨져(n03 15~20px) 고정 행 범위가 어긋남 → 넓은 창에서 열마다 패 화소 수
            ys = slice(max(0, self.y0 - 35), self.y1 + 3)
            tile_col = (~felt[ys] & ~skin[ys]).sum(0) >= 0.6 * (self.y1 - self.y0)
        # 손: 흰 면 행 ± 패 반 장 높이 안의 피부
        h = self.y1 - self.y0
        ys2 = slice(max(0, self.y0 - h), self.y1 + h // 2)
        skin_col = skin[ys2].mean(0) > 0.08
        runs, x = [], 0
        W = len(tile_col)
        while x < W:
            if tile_col[x]:
                a = x
                gap = 0
                while x < W and (tile_col[x] or gap < MIN_GAP):
                    gap = 0 if tile_col[x] else gap + 1
                    x += 1
                b = x - gap
                if b - a >= 12:
                    runs.append((a, b))
            else:
                x += 1
        p = pitch or getattr(self, "pitch", PITCH)
        out = []
        for a, b in runs:
            near = lambda xx: skin_col[max(0, xx - 4):min(W, xx + 5)].any()  # noqa: E731
            out.append({"x0": int(a), "x1": int(b), "n": round((b - a) / p, 2), "hl": bool(near(a)), "hr": bool(near(b))})
        sk = np.flatnonzero(skin_col)
        return [(r["x0"], r["x1"]) for r in out] if pitch == -1 else out, (int(sk.min()), int(sk.max())) if len(sk) else None

    def frame(self, ms: int):
        v = self.view(ms)
        runs, sk = self.runs_of(v)
        bruns, _ = self.runs_of(v, which="back")
        return {"ms": ms, "t": hc.hms(ms), "runs": runs, "bruns": bruns, "skin": sk}


def fmt(fr: dict) -> str:
    def one(rs):
        return " ".join(("(" if r["hl"] else "[") + f"{r['n']:.1f}@{r['x0']}" + (")" if r["hr"] else "]") for r in rs)
    return f"{fr['t']}  흰 {one(fr['runs']):<40} 등 {one(fr['bruns']):<40}" + (f" 손 {fr['skin'][0]}~{fr['skin'][1]}" if fr["skin"] else "")


def cmd_timeline(a):
    R = Row(a.game)
    act = {x["seg"]: x for x in R.sg["active"]}
    print(f"등 띠 {R.b0}~{R.b1}, 줄 높이 {R.y0}~{R.y1}, 한 장 폭 {R.pitch:.1f}px  ( [ ] = 끝이 손에 안 닿음, ( ) = 손에 닿음 )")
    for s in a.segs:
        x = act[int(s)]
        print(f"== 구간 {s} {x['t0']}~{x['t1']}")
        for ms in hc.frame_range(x["ms0"] - 300, x["ms1"] + 300):
            print(fmt(R.frame(ms)))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("timeline")
    t.add_argument("game")
    t.add_argument("segs", nargs="+")
    r = sp.add_parser("run")
    r.add_argument("games", nargs="+")
    r.add_argument("--out")
    c = sp.add_parser("score")
    c.add_argument("file")
    a = ap.parse_args()
    {"timeline": cmd_timeline, "run": cmd_run, "score": cmd_score}[a.cmd](a)



# ------------------------------------------------------------------ 사건 판정
def gaps_of(fr: dict, pitch: float, n_total: int, left0: float | None):
    """프레임 하나의 줄 안 틈(패 0.6~1.6장 폭)마다 (왼쪽 장수, 근거). 왼쪽이 깨끗하면 왼쪽부터, 아니면 오른쪽부터 n_total 로 셈.
    left0 = 손 들어오기 전 줄 왼쪽 끝(줄이 밀리지 않았는지 보는 데 씀)."""
    rs = [r for r in fr["runs"] if r["n"] >= 0.5]
    out = []
    for i in range(len(rs) - 1):
        g = (rs[i + 1]["x0"] - rs[i]["x1"]) / pitch
        if not (0.6 <= g <= 1.6) or rs[i]["hr"] or rs[i + 1]["hl"]:
            continue
        left, right = rs[:i + 1], rs[i + 1:]
        okL = not any(r["hl"] or r["hr"] for r in left) and all(abs(r["n"] - round(r["n"])) <= 0.3 for r in left)
        okR = not any(r["hl"] or r["hr"] for r in right) and all(abs(r["n"] - round(r["n"])) <= 0.3 for r in right)
        if okL and (left0 is None or abs(left[0]["x0"] - left0) <= 0.4 * pitch):
            out.append((int(sum(round(r["n"]) for r in left)), "L"))
        elif okR:
            out.append((n_total - int(sum(round(r["n"]) for r in right)), "R"))  # 오른쪽 장수로(줄 전체 장수를 알 때)
    return out


def judge_turn(R: "Row", tr: dict, n_hand: int) -> dict:
    """한 차례: 손 들어오기 전 ~ 손 떠난 뒤 모든 프레임. 반환: mode(쯔모기리|손에서|모름), k, j(각각 int 또는 None)."""
    frs = [R.frame(ms) for ms in hc.frame_range(tr["ms_before"], tr["ms_after"])]
    base = next((f for f in frs if len(f["runs"]) == 1 and not f["runs"][0]["hl"] and not f["runs"][0]["hr"]), None)
    left0 = base["runs"][0]["x0"] if base else None
    seq = []  # (i, 왼쪽 장수, 근거, 줄 장수 기준)
    for i, f in enumerate(frs):
        # 버리기 전에는 줄 n_hand 장(+ 떨어진 뽑은 패), 버린 뒤 틈 = 빈칸 하나
        for c, how in gaps_of(f, R.pitch, n_hand, left0):
            if 1 <= c <= n_hand - 1:  # 줄 끝 틈(c = n_hand: 오른쪽에 떨어뜨려 둔 뽑은 패)은 빈칸이 아니다(v1 에서 k=14 로 셈 — v2 고침)
                seq.append((i, c, how))
    res = {"n_frames": len(frs), "gaps": [(hc.hms(frs[i]["ms"]), c, h) for i, c, h in seq]}
    if not seq:
        # 줄 안에 빈칸이 한 번도 안 보임 → 쯔모기리로 봄(뽑은 패가 줄에 안 들어감). 손이 줄을 오래 덮었으면 모름
        covered = sum(1 for f in frs if any(r["hl"] or r["hr"] for r in f["runs"]) and len(f["runs"]) >= 1)
        res.update(mode="쯔모기리" if covered <= 0.6 * len(frs) else "모름", k=None, j=None, covered=covered)
        return res
    # 나간 칸: 처음 2프레임 이상 이어진 같은 틈
    k = None
    for (i, c, h), (i2, c2, h2) in zip(seq, seq[1:]):
        if c2 == c and i2 - i <= 3:
            k = c + 1
            k_at = i
            break
    if k is None:
        res.update(mode="손에서", k=None, j=None)
        return res
    # v5: 버리기 전에 뽑은 패를 줄 끝에 붙여 n_hand+1 장 한 덩어리가 된 깨끗한 프레임 → 왼쪽 끝이 그대로면 오른쪽 끝(최종 n_hand 번째),
    #     왼쪽으로 한 장 늘었으면 맨 앞(1)
    j_attach = None
    for f in frs[:k_at]:
        rs = [r for r in f["runs"] if r["n"] >= 0.5]
        if len(rs) == 1 and not rs[0]["hl"] and not rs[0]["hr"] and abs(rs[0]["n"] - (n_hand + 1)) <= 0.3 and left0 is not None:
            if abs(rs[0]["x0"] - left0) <= 0.4 * R.pitch:
                j_attach = n_hand
            elif abs(rs[0]["x0"] - (left0 - R.pitch)) <= 0.4 * R.pitch:
                j_attach = 1
    # v7(11-16 사용자 흐름 "1 상대 버림 → 2 쯔모 → 3 한 자리가 빔(버림) → 4 옆을 밀어 틈을 벌리고 넣고 합침"):
    #  끝에 붙인 14장은 2단계일 뿐 최종 자리가 아니다 → 3단계 뒤 새 틈을 먼저 보고(깨끗한 틈 > 손 닿은 틈), 없을 때만 끝 붙임 자리.
    if not FLOW_V7 and j_attach is not None and k <= n_hand:  # v6 까지: 끝 붙임이 보이면 그 자리
        res.update(mode="손에서", k=k, j=j_attach)
        return res
    later = [(i, c) for i, c, h in seq if i > k_at and c != k - 1]
    j = None
    for (i, c), (i2, c2) in zip(later, later[1:]):
        if c2 == c and i2 - i <= 3:
            j = c + 1
            break
    if j is None and FLOW_V7:
        j = weak_new_gap(R, frs[k_at + 1:], k, n_hand, left0)
        res["j_weak"] = j
    if j is None and FLOW_V7 and j_attach is not None and k <= n_hand:
        j = j_attach
    if j is None:
        # 다른 틈이 안 보이면: 마지막까지 나간 칸 틈이 보이다 닫혔으면 그 자리(j = k), 아니면 모름
        last_k = max(i for i, c, h in seq if c == k - 1)
        tail = frs[last_k + 1:]
        closed_clean = any(len(f["runs"]) == 1 and not f["runs"][0]["hl"] and not f["runs"][0]["hr"] for f in tail)
        j = k if closed_clean and last_k >= len(frs) - 15 else None
    res.update(mode="손에서", k=k, j=j)
    return res


def weak_new_gap(R, frs: list, k: int, n_hand: int, left0) -> int | None:
    """4단계의 새 틈을 손이 닿아 있어도 센다: 왼쪽 덩어리들의 장수가 정수에 가깝고(±0.35) 맨 왼쪽 끝이 줄 시작(left0 ± 0.6장)이면
    그 틈의 왼쪽 장수 c → 들어간 칸 c + 1. 나간 칸 틈(c = k - 1)은 뺌. 같은 c 가 2프레임 이상일 때만, 가장 많이 나온 c."""
    from collections import Counter
    if left0 is None:
        return None
    cnt = Counter()
    for f in frs:
        rs = [r for r in f["runs"] if r["n"] >= 0.3]
        if not rs or abs(rs[0]["x0"] - left0) > 0.6 * R.pitch:
            continue
        acc = 0
        for i in range(len(rs) - 1):
            if abs(rs[i]["n"] - round(rs[i]["n"])) > 0.35:
                break
            acc += round(rs[i]["n"])
            g = (rs[i + 1]["x0"] - rs[i]["x1"]) / R.pitch
            if g >= 0.5 and 1 <= acc <= n_hand - 1 and acc != k - 1:
                cnt[acc] += 1
                break
    best = [c for c, n in cnt.most_common() if n >= 2]
    return best[0] + 1 if best else None


def truth_of(gid: str, t: dict) -> dict:
    """정답: 판정 B 의 한 칸 답 + 사용자 확인(11-16) + 규칙 사건."""
    tr = {"mode": t["mode"] if t["mode"] in ("쯔모기리", "손에서") else None}
    ks = [x for x in t["out_slots"] if isinstance(x, int)]
    js = [x for x in t["in_slots"] if isinstance(x, int)]
    tr["k"] = ks[0] if tr["mode"] == "손에서" and len(ks) == 1 else None
    tr["j"] = js[0] if tr["mode"] == "손에서" and len(js) == 1 else None
    if tr["j"] == 14:  # 판정의 place 14 = 버리기 전 14장 줄의 끝 → 최종 줄의 13번째(v5 채점 고침)
        tr["j"] = 13
    tr["j_cands"] = js if tr["mode"] == "손에서" and len(js) > 1 else None
    tr["src"] = "판정B"
    d = t["discard"][0] if t["discard"] else {}
    if d.get("after_riichi"):
        tr.update(mode="쯔모기리", k=None, j=None, src="규칙(리치 뒤)")
    if d.get("post_call"):
        tr.update(mode="손에서", src="규칙(울기 직후)")
    if gid == "r18_141259" and t["seg"] == 8:
        tr.update(j=3, j_cands=None, src="사용자 확인(11-16)")
    if gid == "n03_150528" and t["seg"] == 17:
        tr.update(mode="쯔모기리", k=None, j=None, src="사용자 확인(11-16)")
    # 11-16 저녁 고침: 위의 j 는 판정의 place(버리기 전 끝 붙임 14 → 13)만 보고 그 뒤 move·shuffle 을 무시해 7 중 5 가 13 이었다.
    # 프레임을 다시 보니 끝에 붙였다가 버린 뒤 다시 집어 안쪽에 넣는다 → insert_truth_1116.json 의 칸으로 덮어씀(OLD_TRUTH=1 이면 옛 정답).
    fx = None if OLD_TRUTH else INSERT_TRUTH.get(gid, {}).get(str(t["seg"]))
    if fx and tr["mode"] == "손에서":
        if fx["firm"]:
            tr.update(j=fx["j"], j_cands=None, src=tr["src"] + " + 들어간 칸 " + {"user": "사용자 확인", "judge": "판정B(옮김 포함)", "frames": "프레임 확인(11-16)"}[fx["src"]])
        else:
            tr.update(j=None, j_cands=fx["cands"])
    return tr


def cmd_run(a):
    import beforeafter as ba
    out = []
    for gid in a.games:
        R = Row(gid)
        rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
        tmap = {t["t"]: t for t in rp["turns"]}
        n_hand = 13
        for tr in ba.turns_from_replay(rp, R.sg):
            t = tmap[tr["t"]]
            if "call" in " ".join(tr["events"]):
                n_hand = 10  # n03 울기 뒤(퐁 3장 빠짐) — 이 판 하나에만 맞춘 값
            truth = truth_of(gid, t)
            got = judge_turn(R, tr, n_hand)
            row = {"game": gid, "t": tr["t"], "segs": tr["segs"], "truth": truth, "got": {k: got.get(k) for k in ("mode", "k", "j")},
                   "gaps": got["gaps"][:30]}
            out.append(row)
            print(f"{gid} {tr['t']:>2}순 구간 {tr['segs']}  정답 {truth['mode']}/k{truth['k']}/j{truth['j'] or truth['j_cands']} ({truth['src']})"
                  f"  →  {got['mode']}/k{got['k']}/j{got['j']}")
    if a.out:
        hc.jsave(a.out, out)


def cmd_score(a):
    rows = hc.jload(a.file)
    c = {"mode_n": 0, "mode_ok": 0, "mode_unk": 0, "k_n": 0, "k_ok": 0, "k_none": 0, "j_n": 0, "j_ok": 0, "j_none": 0, "jc_n": 0, "jc_in": 0, "jc_none": 0}
    for r in rows:
        T, G = r["truth"], r["got"]
        if T["mode"]:
            c["mode_n"] += 1
            c["mode_unk"] += G["mode"] == "모름"
            c["mode_ok"] += G["mode"] == T["mode"]
        if T["mode"] == "손에서" and T["k"]:
            c["k_n"] += 1
            c["k_none"] += G["k"] is None
            c["k_ok"] += G["k"] == T["k"]
        if T["mode"] == "손에서" and T["j"]:
            c["j_n"] += 1
            c["j_none"] += G["j"] is None
            c["j_ok"] += G["j"] == T["j"]
        if T.get("j_cands"):
            c["jc_n"] += 1
            c["jc_none"] += G["j"] is None
            c["jc_in"] += G["j"] in T["j_cands"]
    print(json.dumps(c, ensure_ascii=False))


if __name__ == "__main__":
    main()
