"""제자리에 남은 패를 화소로 세어 들어간 칸(j) 찾기(2026-11-16, 계획서 3단계 "추가 4" — 방법·기준은 결과 전에 적음).

  python -X utf8 inplace.py run [--arm B|A] [--verbose] [--out 파일]
생각: 뽑은 패(D)를 넣으려면 줄이 벌어진다. 벌어진 자리의 한쪽은 손이 옮긴 패, 다른 쪽은 제자리에 남은 패.
  - 오른손만(끝의 패 몇 장을 쓸어 냄): 왼쪽에 깨끗이 남은 장수의 최솟값 + 1
  - 왼손이 왼쪽 패를 밂: N − (새로 벌어진 틈 오른쪽 장수)
새 틈 = 두 덩어리 사이가 펠트로 보이고(손가락이 끊은 것이 아님) 창 처음에는 없던 것(버린 자리 빈칸은 옛 틈).
조건 B = gemframes.B_WIN(사람이 고른 창), A = 차례 창에서 "D 를 다시 집는 프레임" 을 규칙이 찾아 거기서부터.
개발 두 판 9차례를 보며 다듬은 규칙이다(시험 아님).
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gemframes as gf  # noqa: E402
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402

FELT_MIN = 3  # 덩어리 사이에 확실한 펠트 열이 이만큼(px) 있어야 진짜 틈(v1 5 → v2 3: 먼 쪽 행 기준으로 바꾸며)
VERSION = "v5"
# v1 → v2(9차례를 보며): ① 옛 틈(버린 자리)이 닫히며 좁아지는 것을 새 틈으로 세던 것 → 옛 틈 범위 안이면 옛 틈
#   ② 옛 틈이 왼쪽으로 넓어지면(왼손이 왼쪽 무리를 뺌) 옛 틈의 오른쪽 끝에서부터 제자리 장수를 셈
#   ③ 펠트 판정을 손가락이 덜 가리는 먼 쪽 행(패 윗면 맨 위 10행)으로도 봄
# v2 → v3: ④ 틈 오른쪽 장수를 셀 때 옛 틈 폭만 뺌(다른 새 틈 폭까지 빼면 손이 옮기는 패 사이의 틈이 우연히 정수가 됨)
# v3 → v4: ⑥ 먼 쪽 행을 줄 전체에서 한 번 잡던 것 → 틈마다 양옆 패에서 따로(n03 은 줄이 기울어 왼쪽 틈마다 펠트로 보임)
#   ⑦ 옛 틈이 왼쪽에서 메워지거나 닫히면 그 뒤로는 기준으로 안 씀(n03 13순: 왼쪽 무리를 밀어 옛 틈을 메운 뒤 다시 벌림)
# v4 → v5: ⑦ 을 고침 — 옛 틈이 오른쪽에서 닫히는 중(끝 정리)에도 버려져 오른손 넣기가 틀림 → 완전히 닫혔을 때만 버리고,
#   왼쪽에서 먹혀 들어온 옛 틈은 '남은 꼬리' 로 두되 넓어짐 판정에는 안 씀. 먼 쪽 행은 양옆 중 덜 가린(더 위) 쪽 기준
#   ⑧ 고르기: 틈 오른쪽 덩어리의 왼쪽 끝이 손에 안 닿은 근거(강함)를 먼저, 없으면 나머지의 최빈값, 동률이면 답 안 함
#   ⑤ '옛 틈이 왼쪽으로 넓어짐' 은 옛 틈 왼쪽 끝보다 더 왼쪽에 펠트가 보일 때만(손이 덮은 것을 넓어진 틈으로 세던 것)


def analyse(R: pt.Row, ms: int) -> dict:
    v = R.view(ms)
    runs, sk = R.runs_of(v)
    skin, felt, _, _ = pt.masks(v)
    ys = slice(max(0, R.y0 - 35), R.y1 + 3)
    fcol = (felt[ys].mean(0) >= 0.9) & (skin[ys].mean(0) <= 0.02)  # 확실한 펠트 열
    scol = skin[slice(max(0, R.y0 - (R.y1 - R.y0)), R.y1 + (R.y1 - R.y0) // 2)].mean(0) > 0.08
    occ = ~felt & ~skin
    runs = [r for r in runs if r["n"] >= 0.3]
    w = int(0.75 * R.pitch)
    brk = []

    def top_of(x0, x1):
        if x1 - x0 < 6:
            return None
        o = occ[:, x0:x1].mean(1)
        ys_ = [y for y in range(max(0, R.y0 - 45), R.y1) if o[y] >= 0.5]
        return ys_[0] if ys_ else None

    for ra, rb in zip(runs, runs[1:]):
        x0, x1 = ra["x1"], rb["x0"]
        fm = fcol[x0:x1]
        tl, tr_ = top_of(max(ra["x0"], x0 - w), x0), top_of(x1, min(rb["x1"], x1 + w))  # v4: 양옆 패의 윗면 맨 위 행
        tops = [t for t in (tl, tr_) if t is not None]
        if tops:
            yt = min(tops)
            ff = felt[yt + 2:yt + 10, x0:x1].mean(0) >= 0.8
            if ff.sum() > fm.sum():
                fm = ff
        brk.append({"x0": x0, "x1": x1, "felt": int(fm.sum()), "fx": (np.flatnonzero(fm) + x0).tolist()})
    return {"ms": ms, "t": hc.hms(ms)[3:], "runs": runs, "brk": brk, "skin": sk, "scol": scol}


def kind_of(b: dict, old: list, p: float):
    """(종류, 옛 틈) — old: 옛 틈 그대로이거나 닫히는 중 / wideL: 옛 틈이 왼쪽으로 넓어짐 / new / finger."""
    for o in old:
        if b["x0"] < o["x1"] and o["x0"] < b["x1"]:  # 겹침
            if b["x0"] >= o["x0"] - 0.35 * p and b["x1"] <= o["x1"] + 0.35 * p:
                return "old", o
            if not o.get("eaten") and b["x0"] < o["x0"] - 0.35 * p and sum(x < o["x0"] - 0.2 * p for x in b["fx"]) >= FELT_MIN:
                return "wideL", o
            return "old", o
    return ("new" if b["felt"] >= FELT_MIN else "finger"), None


def left_hand(f: dict, mid: float) -> bool:
    return bool(f["scol"][:int(mid)].sum() >= 8)


def judge(R: pt.Row, frames: list, n: int, verbose=False) -> dict:
    p = R.pitch
    f0 = frames[0]
    old = [b for b in f0["brk"] if b["felt"] >= FELT_MIN]  # 창 처음부터 있던 틈(버린 자리)
    old0 = [(o["x0"], o["x1"]) for o in old]
    xs = [r["x0"] for r in f0["runs"]] + [r["x1"] for r in f0["runs"]]
    mid = (min(xs) + max(xs)) / 2 if xs else 0
    lh = sum(left_hand(f, mid) for f in frames) >= 2
    cl, jg = [], []
    for f in frames[1:]:
        rs = f["runs"]
        if not rs:
            continue
        for o in list(old):  # v4: 옛 틈이 패로 메워졌거나 왼쪽에서 먹혀 들어오면 버림
            c = (o["x0"] + o["x1"]) / 2
            over = [b for b in f["brk"] if b["x0"] < o["x1"] and o["x0"] < b["x1"]]
            if not over and any(r["x0"] < c < r["x1"] for r in rs):
                old.remove(o)  # 완전히 닫힘
            elif any(b["x0"] >= o["x0"] + 0.35 * p for b in over):
                o["eaten"] = True  # 왼쪽 무리가 옛 틈으로 밀려 들어옴 → 남은 것은 꼬리
        ko = [kind_of(b, old, p) for b in f["brk"]]
        kinds = [k for k, _ in ko]
        # 왼쪽에서부터 깨끗이 남은 장수(옛 틈·손가락 끊김은 넘어감, 새 틈에서 멈춤)
        if not rs[0]["hl"]:
            i, gapw = 0, 0.0
            while i < len(kinds) and kinds[i] not in ("new", "wideL"):
                if kinds[i] == "old":
                    gapw += f["brk"][i]["x1"] - f["brk"][i]["x0"]
                i += 1
            if not rs[i]["hr"]:  # 덩어리 오른쪽 끝이 손에 안 닿은 프레임만
                cnt = (rs[i]["x1"] - rs[0]["x0"] - gapw) / p
                if abs(cnt - round(cnt)) <= 0.3:
                    cl.append((f["t"], round(cnt)))
        # 새 틈 오른쪽 장수(줄 오른쪽 끝이 깨끗할 때만)
        if not rs[-1]["hr"]:
            for gi, kd in enumerate(kinds):
                if kd not in ("new", "wideL"):
                    continue
                feltw = sum(b["x1"] - b["x0"] for b, k2 in zip(f["brk"][gi + 1:], kinds[gi + 1:]) if k2 == "old")
                edge = ko[gi][1]["x1"] if kd == "wideL" else f["brk"][gi]["x1"]  # 옛 틈이 넓어졌으면 제자리 쪽 끝 = 옛 틈의 오른쪽 끝(손에 가려도)
                cnt = (rs[-1]["x1"] - edge - feltw) / p
                if abs(cnt - round(cnt)) <= 0.3 and 1 <= round(cnt) <= n - 1:
                    jg.append((f["t"], n - round(cnt), "강" if kd == "new" and not rs[gi + 1]["hl"] else "약"))
    res = {"left_hand": lh, "cl": cl, "jg": jg, "old": old0}
    if not lh:
        res["j"] = (min(c for _, c in cl) + 1) if cl else None
        res["how"] = "왼쪽에 남은 장수 최솟값 + 1"
    else:
        strong = Counter(j for _, j, w in jg if w == "강")
        c = strong or Counter(j for _, j, w in jg)
        top = c.most_common()
        res["j"] = top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else None  # 동률이면 답 안 함
        res["how"] = "N − 새 틈 오른쪽 장수"
    return res


def lift_start(R: pt.Row, frames: list, n: int) -> int:
    """조건 A: D 를 다시 집은 프레임 찾기 — 손 안 닿은 덩어리 합이 N−1 이고 오른쪽 끝에 손 닿은 한 장 안팎 조각만 있는 마지막 프레임.
    못 찾으면 '왼쪽부터 보이는 장수가 N 근처였다가 0.3초 안에 2장 넘게 줄어든' 마지막 프레임."""
    p, last = R.pitch, None
    for i, f in enumerate(frames):
        rs = f["runs"]
        if not rs:
            continue
        clean = [r for r in rs if not r["hl"] and not r["hr"]]
        rest = [r for r in rs if r["hl"] or r["hr"]]
        tot = sum(r["n"] for r in clean)
        if clean and abs(tot - (n - 1)) <= 0.35 and all(r["n"] <= 1.6 and r["x0"] > clean[-1]["x1"] - 2 for r in rest):
            last = i
    if last is not None:
        return last
    vis = [sum(r["n"] for r in f["runs"]) for f in frames]
    for i in range(len(frames) - 4, 0, -1):
        if vis[i] >= n - 0.4 and min(vis[i + 1:i + 4]) <= vis[i] - 2:
            return i
    return 0


def cmd_run(a):
    Rs, rows = {}, []
    for t in gf.turns():
        gid = t["game"]
        R = Rs.setdefault(gid, pt.Row(gid))
        if a.arm == "B":
            b0, b1 = gf.B_WIN[(gid, t["seg"])]
            mss = hc.frame_range(hc.to_ms(b0), hc.to_ms(b1))
            frames = [analyse(R, ms) for ms in mss]
            start = frames[0]["t"]
        else:
            import glob

            import beforeafter as ba
            sg = hc.jload(hc.OUT / gid / "segments.json")
            rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
            tr = next(x for x in ba.turns_from_replay(rp, sg) if x["segs"][0] == t["seg"])
            allf = [analyse(R, ms) for ms in hc.frame_range(tr["ms_before"], tr["ms_after"])]
            i0 = lift_start(R, allf, t["n"])
            frames = allf[max(0, i0 - 1):]
            start = frames[0]["t"]
        res = judge(R, frames, t["n"], a.verbose)
        ok = "맞음" if res["j"] == t["j"] else ("없음" if res["j"] is None else "틀림")
        rows.append({"id": t["id"], "truth": t["j"], "j": res["j"], "ok": ok, "start": start, "frames": len(frames), **{k: res[k] for k in ("left_hand", "how", "cl", "jg", "old")}})
        print(f"{t['id']} 정답 {t['j']} → {res['j']} [{ok}]  창 {start}~ {len(frames)}장 · 왼손 {'있음' if res['left_hand'] else '없음'} · {res['how']}")
        if a.verbose:
            print("    왼쪽 남은 장수:", res["cl"][:14])
            print("    새 틈 → 칸:", res["jg"][:14], " 옛 틈:", res["old"])
    c = Counter(r["ok"] for r in rows)
    near = sum(r["j"] is not None and abs(r["j"] - r["truth"]) == 1 for r in rows)
    print(f"[{VERSION} · 조건 {a.arm}] 맞음 · 틀림 · 없음 {c['맞음']} · {c['틀림']} · {c['없음']} /{len(rows)}, 한 칸 차 {near}")
    if a.out:
        hc.jsave(a.out, {"version": VERSION, "arm": a.arm, "rows": rows})


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--arm", default="B", choices=["A", "B"])
    r.add_argument("--verbose", action="store_true")
    r.add_argument("--out")
    a = ap.parse_args()
    cmd_run(a)


if __name__ == "__main__":
    main()
