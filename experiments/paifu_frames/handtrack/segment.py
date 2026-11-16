"""2단계: features.py 특징으로 손패 띠의 활동 구간 / 정지 구간을 나눈다.

  python -X utf8 segment.py <판 id>
활동 프레임 = 띠에서 앞 프레임 또는 3장 앞과 20단계 넘게 다른 화소가 ACT_DIFF 넘게 있거나, 피부 화소가 ACT_SKIN 넘게 있음
  (손이 띠 위에 가만히 놓여 있어도 활동 — 그동안 줄 상태를 믿을 수 없으므로), 또는 화료자 강 영역에 움직임(RIVER_DIFF)·피부(RIVER_SKIN).
  강 쪽을 더한 까닭: 패산에서 뽑아 손패 줄을 안 건드리고 바로 버리는 쯔모기리(특히 리치 뒤)는 띠에 아무 변화가 없다.
→ 앞뒤로 PAD 장씩 넓히고, 사이 정지가 MERGE_GAP 장 미만이면 붙인다(놓치는 것보다 헛 구간이 낫다는 지시대로 넓게).
판 구간 = config t_ready(손패 정리가 끝난 정지 상태가 시작되는 시각) ~ t_reveal + post_sec. t_ready 앞 프레임은 쓰지 않는다.
결과 results/handtrack/<판>/segments.json:
  {"active": [{seg, i0, i1, t0, t1, ms0, ms1, n, dur, max_skin, max_d1, prev_still, next_still}],
   "still": [{k, i0, i1, t0, t1, ms0, ms1, n, dur}], "params": {...}}
  seg 는 1부터. prev_still/next_still = 앞·뒤 정지 구간 번호(k). 마지막 활동 구간 뒤에 정지가 없으면 next_still null.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

ACT_DIFF = 0.002
ACT_SKIN = 0.003
PAD = 2
MERGE_GAP = 6  # 0.6초 미만 정지는 붙임
RIVER_DIFF = 0.003  # 강 영역 움직임도 활동으로(손패를 안 건드리는 쯔모기리를 놓치지 않으려고)
RIVER_SKIN = 0.01  # r18 강에는 정지 때도 피부색 화소가 0.002 안팎 있다(갈색 무늬)


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def segment(gid: str) -> dict:
    cf = hc.config(gid)
    z = np.load(hc.WORK / f"{gid}_feat.npz")
    ms = z["ms"]
    t_ready = hc.to_ms(cf["t_ready"])
    t_end = hc.to_ms(cf["t_reveal"]) + int(cf.get("post_sec", 4) * 1000)
    keep = (ms >= t_ready) & (ms <= t_end)
    idx = np.flatnonzero(keep)
    ms = ms[idx]
    d1, d3, sk = z["band_d1"][idx], z["band_d3"][idx], z["band_skin"][idx]
    band_act = (d1 > ACT_DIFF) | (d3 > ACT_DIFF) | (sk > ACT_SKIN)
    river_act = (z["river_d1"][idx] > RIVER_DIFF) | (z["river_skin"][idx] > RIVER_SKIN)
    act = band_act | river_act
    act[0] = False  # t_ready 는 정지 상태로 고른 시각
    grown = act.copy()
    for k in range(1, PAD + 1):
        grown[k:] |= act[:-k]
        grown[:-k] |= act[k:]
    grown[0] = False
    still = ~grown
    for a, b in runs(~grown):  # 짧은 정지는 활동으로
        if b - a + 1 < MERGE_GAP and a > 0:
            still[a:b + 1] = False
    act_runs, still_runs = runs(~still), runs(still)
    S = [{"k": k, "i0": a, "i1": b, "t0": hc.hms(int(ms[a])), "t1": hc.hms(int(ms[b])), "ms0": int(ms[a]), "ms1": int(ms[b]), "n": b - a + 1,
          "dur": round((ms[b] - ms[a]) / 1000 + 0.1, 1)} for k, (a, b) in enumerate(still_runs)]
    A = []
    for s, (a, b) in enumerate(act_runs, 1):
        pv = [x["k"] for x in S if x["i1"] == a - 1]
        nx = [x["k"] for x in S if x["i0"] == b + 1]
        A.append({"seg": s, "i0": a, "i1": b, "t0": hc.hms(int(ms[a])), "t1": hc.hms(int(ms[b])), "ms0": int(ms[a]), "ms1": int(ms[b]), "n": b - a + 1,
                  "dur": round((ms[b] - ms[a]) / 1000 + 0.1, 1), "max_skin": round(float(sk[a:b + 1].max()), 3),
                  "max_d1": round(float(d1[a:b + 1].max()), 3),
                  "band_frames": int(band_act[a:b + 1].sum()), "river_frames": int(river_act[a:b + 1].sum()), "prev_still": pv[0] if pv else None, "next_still": nx[0] if nx else None})
    res = {"id": gid, "params": {"ACT_DIFF": ACT_DIFF, "ACT_SKIN": ACT_SKIN, "RIVER_DIFF": RIVER_DIFF, "RIVER_SKIN": RIVER_SKIN, "PAD": PAD, "MERGE_GAP": MERGE_GAP, "DIFF_LEVEL": 20,
                                 "t_ready": cf["t_ready"], "t_end": hc.hms(t_end), "frames": int(len(ms)), "band": cf["band"]},
           "feat_index0": int(idx[0]), "active": A, "still": S}
    hc.jsave(hc.out_dir(gid) / "segments.json", res)
    return res


def main():
    gid = sys.argv[1]
    r = segment(gid)
    A = r["active"]
    d = np.array([a["dur"] for a in A])
    print(f"{gid}: 활동 구간 {len(A)}, 길이 중앙 {np.median(d):.1f}s 최대 {d.max():.1f}s 합 {d.sum():.0f}s / 정지 {len(r['still'])}")
    for a in A:
        print(f"  {a['seg']:3d} {a['t0']}–{a['t1']} {a['dur']:5.1f}s 피부 {a['max_skin']:.3f} d1 {a['max_d1']:.3f} 띠 {a['band_frames']} 강 {a['river_frames']}")


if __name__ == "__main__":
    main()
