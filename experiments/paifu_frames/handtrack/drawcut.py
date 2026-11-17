"""차례 경계를 "내 버림 사이에서 다른 자리 강이 마지막으로 늘어난 때" 로 긋는 규칙을 확인(2026-11-17, 사용자 "쯔모로 구간을 나눠야" → "전체 테이블 화면으로").
네 자리 강 = 앱 버림 기록기 재생 결과(results/h<판>/dart_overlay_v2.json 의 칸별 first_at, 추적 프레임 약 3초 간격).
손패 띠 신호(줄이 한 장 길어짐 = 뽑은 패를 붙임)는 맞대 보는 용도로만 쓴다 — 경계를 긋는 데는 안 쓴다.

  python -X utf8 drawcut.py <판 id> <자리 bottom|right|top|left> [기록기 결과 폴더 이름]
경계 = 윗집(마지막으로 버린 다른 자리)의 버림이 처음 보인 추적 프레임의 **바로 앞 프레임** 시각 — 그 버림보다 늦을 수 없는 시각.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402


def main():
    gid, side = sys.argv[1], sys.argv[2]
    rec = hc.OUT.parent / (sys.argv[3] if len(sys.argv) > 3 else f"h{gid[1:]}")
    d = json.load(open(rec / "dart_overlay_v2.json", encoding="utf-8"))
    ft = [dt.datetime.fromisoformat(f["at"]) for f in json.load(open(rec / "overlay_dump.json", encoding="utf-8"))["frames"]]
    day = ft[0].date()
    z = np.load(hc.WORK / f"{gid}_feat.npz")
    ms, P = z["ms"], hc.jload(hc.OUT / gid / "segments.json")["params"]
    bs = z["band_small"]
    on = (bs > 170).mean(axis=2 if bs.shape[1] > bs.shape[2] else 1) > 0.15
    ext = np.array([(np.where(r)[0][-1] - np.where(r)[0][0] + 1) if r.any() else 0 for r in on])
    rsk, skin = z["river_skin"], z["band_skin"]

    def T(s):
        h, m, x = s.split(":")
        return dt.datetime(day.year, day.month, day.day, int(h), int(m), int(x))

    def frames_of(s):
        i = min(range(len(ft)), key=lambda k: abs((ft[k] - T(s)).total_seconds()))
        return ft[i], ft[max(i - 1, 0)]

    idx = lambda t: int(np.searchsorted(ms, int(t.timestamp() * 1000)))  # noqa: E731
    fm = lambda t: t.strftime("%M:%S.%f")[:7]  # noqa: E731
    ev = sorted((s["first_at"], sd, s["i"], s["tile"], s.get("taken_at")) for sd, v in d.items() for s in v["slots"])
    hero = [e for e in ev if e[1] == side]
    gaps = sorted((b - a).total_seconds() for a, b in zip(ft, ft[1:]))
    print(f"{gid} · {side} · 추적 프레임 {len(ft)}(간격 중앙 {gaps[len(gaps) // 2]:.1f}초 · 최대 {gaps[-1]:.1f}초) · 내 버림 {len(hero)}")
    print("차례 | 사이의 남의 버림 | 경계 | 윗집 버림이 보인 프레임 | 줄이 한 장 길어짐 | 내 버림(강 위 손) | 판정")
    ok = n = 0
    for a, b in zip(hero, hero[1:]):
        mid = [e for e in ev if a[0] < e[0] < b[0] and e[1] != side]
        if not mid:
            print(f" {b[2]:2d}순 | 없음 — 경계 못 그음(추적 시작 전이거나 운 패가 강에 안 찍힘)")
            continue
        seen, prev = frames_of(mid[-1][0])
        bseen, _ = frames_of(b[0])
        i0, i1 = idx(prev), idx(bseen)
        riv = [i for i in range(i0, i1) if rsk[i] > P["RIVER_SKIN"]]
        disc = riv[-1] if riv else i1
        base = int(np.median(ext[max(i0 - 30, 0):i0])) if i0 > 30 else int(np.median(ext[:30]))
        g, run = None, 0
        for i in range(i0, disc):
            run = run + 1 if ext[i] >= base + 7 else 0
            if run >= 5:
                g = i - 4
                break
        # 앞 차례 쪽에 뽑기가 섞여 들지 않았나: 앞 내 버림 뒤 ~ 경계 사이에는 줄이 길어진 채 이어지는 곳이 없어야 한다(버린 빈칸을 메우기 전은 뺌 — 5초 뒤부터)
        aseen, _ = frames_of(a[0])
        j0 = idx(aseen) + 50
        early, run = None, 0
        for i in range(j0, i0):
            # 손이 띠에 있으면 밝은 화소가 줄 끝에 붙어 줄이 길어 보인다 → 살색이 없는 프레임에서만 센다
            run = run + 1 if (ext[i] >= base + 7 and skin[i] < P["ACT_SKIN"]) else 0
            if run >= 10:
                early = i - 9
                break
        good = g is not None and early is None
        n += 1
        ok += good
        print(f" {b[2]:2d}순 | {' '.join(e[1][0] + str(e[2]) + ('(울림)' if e[4] else '') for e in mid):16s} | {fm(prev)} | {fm(seen)} | {hc.hms(int(ms[g]))[3:] if g is not None else '   -   '} | {hc.hms(int(ms[disc]))[3:]} | "
              + ("경계 뒤에 뽑기 한 번" if good else ("**경계 앞에 손 없이 줄이 길어진 곳 " + hc.hms(int(ms[early]))[3:] + "**" if early is not None else "뽑은 패를 줄에 안 붙임(또는 신호 없음)")))
    print(f"경계 뒤에 줄이 길어지고, 경계 앞(앞 버림 5초 뒤부터)에는 손 없이 길어진 곳이 없는 차례: {ok}/{n}")


if __name__ == "__main__":
    main()
