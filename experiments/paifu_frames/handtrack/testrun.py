"""들어간 칸 규칙(inplace v5)을 처음 보는 시험 판에 돌리기(2026-11-16, 계획서 3단계 "추가 5" — 절차는 결과 전에 적음).

  python -X utf8 testrun.py run            # 차례 만들기 → pixtrack 거르기 → inplace 자동 조건 A. 답은 파일에만(화면에는 수만)
  python -X utf8 testrun.py strips         # 표본 차례의 프레임 띠(답 없음) → _work/testrun_1116/strips/
  python -X utf8 testrun.py reveal <읽기 json>   # 가린 읽기 {"id": j|"tsumogiri"|null}와 규칙 답 맞대기
차례 = 손 움직임 구간 중 화료자 강이 1장 늘고 울기 장수가 그대로인 구간. N 은 창 첫머리의 손 안 닿은 덩어리 합.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beforeafter as ba  # noqa: E402
import htcommon as hc  # noqa: E402
import inplace as ip  # noqa: E402
import pixtrack as pt  # noqa: E402

GAMES = ["r02_114700", "r04_120417", "r11_130921", "r14_133610", "r19_142013", "n02_145625", "n05_151953", "n07_153010"]
OUT = hc.WORK / "testrun_1116"
MAX_SAMPLE = 12


def turns_of(gid: str) -> list:
    sg = hc.jload(hc.OUT / gid / "segments.json")
    rs = hc.jload(hc.OUT / gid / "river_states.json")["segments"]
    out = []
    for a in sg["active"]:
        r = rs.get(str(a["seg"]))
        if not r or "river_count" not in r or r["river_count"][1] - r["river_count"][0] != 1 or r["meld_count"][0] != r["meld_count"][1]:
            continue
        out.append({"id": f"{gid[:3]}_s{a['seg']:02d}", "game": gid, "seg": a["seg"], "ms_before": a["ms0"] - ba.PAD_MS, "ms_after": a["ms1"] + ba.PAD_MS,
                    "t0": a["t0"], "t1": a["t1"], "river_new": r.get("river_new")})
    return out


def row_n(frames: list) -> int | None:
    for f in frames[:15]:
        rs = f["runs"]
        if rs and all(not r["hl"] and not r["hr"] for r in rs):
            tot = sum(r["n"] for r in rs)
            if abs(tot - round(tot)) <= 0.3:
                return round(tot)
    return None


def cmd_run(a):
    rows = []
    for gid in GAMES:
        try:
            R = pt.Row(gid)
        except Exception as e:  # noqa: BLE001
            print(gid, "줄 잡기 실패:", type(e).__name__, e)
            continue
        ts = turns_of(gid)
        c = Counter()
        for t in ts:
            frames = [ip.analyse(R, ms) for ms in hc.frame_range(t["ms_before"], t["ms_after"])]
            n = row_n(frames)
            t.update(n=n, frames=len(frames), pitch=round(R.pitch, 1))
            if n is None or not (4 <= n <= 13):
                t.update(mode="N 못 잼", j=None)
                c["N 못 잼"] += 1
                rows.append(t)
                continue
            pj = pt.judge_turn(R, t, n)
            i0 = ip.lift_start(R, frames, n)
            res = ip.judge(R, frames[max(0, i0 - 1):], n)
            j = res["j"] if res["j"] is not None and 1 <= res["j"] <= n else None
            t.update(mode=pj["mode"], k_pix=pj.get("k"), j_pix=pj.get("j"), j=j, how=res["how"], left_hand=res["left_hand"],
                     start=frames[max(0, i0 - 1)]["t"], cl=res["cl"], jg=res["jg"])
            c[pj["mode"]] += 1
            c[pj["mode"] + " · 칸 답함"] += j is not None
            rows.append(t)
        print(f"{gid}  한 장 폭 {R.pitch:.1f}px · 차례 {len(ts)} · " + " · ".join(f"{k} {v}" for k, v in sorted(c.items())))
    # 표본: 거르기(손에서)를 지나 규칙이 답한 차례, 12 넘으면 판을 돌아가며
    cand = {g: [r for r in rows if r["game"] == g and r["mode"] == "손에서" and r["j"] is not None] for g in GAMES}
    sample, i = [], 0
    while len(sample) < MAX_SAMPLE and any(len(v) > i for v in cand.values()):
        for g in GAMES:
            if len(cand[g]) > i and len(sample) < MAX_SAMPLE:
                sample.append(cand[g][i]["id"])
        i += 1
    hc.jsave(OUT / "run.json", {"version": ip.VERSION, "rows": rows, "sample": sample})
    tot = Counter(r["mode"] for r in rows)
    ans = Counter(r["mode"] for r in rows if r["j"] is not None)
    print("합: 차례", len(rows), "·", dict(tot), "· 칸 답함", dict(ans))
    print("표본", len(sample), sample)


def cmd_strips(a):
    import stripview as sv  # noqa: F401
    import subprocess
    d = hc.jload(OUT / "run.json")
    by = {r["id"]: r for r in d["rows"]}
    for i, sid in enumerate(d["sample"], 1):
        r = by[sid]
        t0, t1 = hc.hms(r["ms_before"]), hc.hms(r["ms_after"])
        title = f"시험 {i:02d} · {sid} ({t0[:8]}~) — 줄 {r['n']}장|이 차례에 뽑은 패가 차례 끝에 줄의 왼쪽부터 몇 번째에 서나요? (그대로 버렸으면 '쯔모기리')|위 → 아래, 이어서 오른쪽 열이 시간 순서. 왼쪽 = 그 사람 왼손 쪽."
        subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).with_name("stripview.py")), r["game"], t0, t1, "--step", "2", "--scale", "1.0",
                        "--cols", "2", "--rows", "40", "--pad", "40", "75", "--title", title, "--out", str(OUT / "strips" / f"{i:02d}_{sid}")], check=True)


def cmd_reveal(a):
    d = hc.jload(OUT / "run.json")
    by = {r["id"]: r for r in d["rows"]}
    reads = hc.jload(a.reads)
    c = Counter()
    for sid in d["sample"]:
        r, mine = by[sid], reads.get(sid, "미읽음")
        if mine in (None, "미읽음", "unreadable"):
            v = "읽기 불가"
        else:
            v = "맞음" if mine == r["j"] else "틀림"
        c[v] += 1
        print(f"{sid} N {r['n']} · 규칙 {r['j']} ({'왼손' if r['left_hand'] else '오른손만'}, 창 {r['start']}~) · 읽기 {mine} → {v}   근거 cl {r['cl'][:6]} jg {r['jg'][:6]}")
    print(dict(c))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("run")
    sp.add_parser("strips")
    r = sp.add_parser("reveal")
    r.add_argument("reads")
    a = ap.parse_args()
    {"run": cmd_run, "strips": cmd_strips, "reveal": cmd_reveal}[a.cmd](a)


if __name__ == "__main__":
    main()
