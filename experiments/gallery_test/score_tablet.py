"""drive_tablet.py 결과 채점(2026-11-05). 기록 폴더를 태블릿에서 받아 original.jpg 로 어느 사진인지 정하고
flow_visit.py 와 같은 기준(손패·울기·화료패 = 맞음, 론/쯔모·방총자, 표시패)으로 센다. 점수·자동 반영은 meta 에 없어 안 본다.
  python -X utf8 experiments/gallery_test/score_tablet.py <tag>
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/speed"))
import flow_visit as fv  # noqa: E402
import seat_grow as sg  # noqa: E402

ADB = r"C:\Users\jjh7757\dev\android-sdk\platform-tools\adb.exe"


def thumb(p) -> np.ndarray:
    im = Image.open(p).convert("L")
    if im.width < im.height:  # 기록 원본이 EXIF 회전으로 세워졌을 수 있다
        im = im.rotate(90, expand=True)
    return np.asarray(im.resize((64, 48)), float)


def q(v):
    v = sorted(v)
    return f"{statistics.median(v):.2f} / {v[min(len(v) - 1, int(round(.9 * (len(v) - 1))))]:.2f} / {v[-1]:.2f}"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    tag = sys.argv[1]
    rows = [json.loads(l) for l in (ROOT / f"experiments/speed/results/tablet_gallery_{tag}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    local = ROOT / f"experiments/speed/results/tablet_gallery_{tag}"
    local.mkdir(exist_ok=True)
    scenes = {(s["name"] if s["set"] == "bcd" else s["name"][-6:]): s for s in sg.eval_scenes()}
    refs = {k: thumb(s["path"]) for k, s in scenes.items()}
    tally, times, calls, stages, seen = Counter(), [], {}, {}, Counter()
    for r in rows:
        if not r["record"]:
            print("기록 없음", r)
            tally["기록 없음"] += 1
            continue
        d = local / r["record"]
        if not (d / "meta.json").exists():
            d.mkdir(exist_ok=True)
            for f in ("meta.json", "original.jpg"):
                subprocess.run([ADB, "pull", f"/sdcard/Download/mahjong_calc/{r['record']}/{f}", str(d / f)], capture_output=True)
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        th = thumb(d / "original.jpg")
        photo, err = min(((k, float(np.abs(th - v).mean())) for k, v in refs.items()), key=lambda x: x[1])
        seen[photo] += 1
        t = fv.truth_of(photo, scenes)
        m = meta.get("merge") or {}
        closed = sorted(m.get("closed") or [])
        melds = fv.norm_melds(m.get("melds") or [])
        meld_ok, valid = melds == t["melds"], bool(m.get("hand_valid"))
        cands = m.get("win_candidates") or []
        if t["win"] is None:
            rest = list(closed)
            if m.get("win_tile") in rest and len(closed) + 3 * len(melds) == 14:
                rest.remove(m["win_tile"])
            full, pick = meld_ok and valid and (closed == t["hand"] or rest == t["hand"]), False
        else:
            full = meld_ok and valid and closed == t["closed"] and m.get("win_tile") == t["win"]
            pick = meld_ok and not valid and t["win"] in cands and sorted(closed + [t["win"]]) == t["closed"]
        side_ok = full and t["tsumo"] is not None and bool(m.get("is_tsumo")) == t["tsumo"] and m.get("loser") == t["loser"]
        got = sorted(m.get("dora_indicators") or []) + sorted(m.get("ura_indicators") or [])
        ind_ok = t["inds"] is not None and sorted(got) == sorted(t["inds"])
        part = "BCD" if scenes[photo]["set"] == "bcd" else ("오전" if photo < "14" else "오후")
        tally[(part, "n")] += 1
        tally[(part, "맞음")] += full
        tally[(part, "고르면 맞음")] += pick
        tally[(part, "계산했는데 틀림")] += valid and not full
        tally[(part, "론쯔모까지")] += side_ok
        tally[(part, "표시패")] += ind_ok
        tally[(part, "표시패 정답 있음")] += t["inds"] is not None
        tally[(part, "오류")] += bool(meta.get("error"))
        times.append(r["t_record_s"])
        for k, v in (meta.get("call_ms") or {}).items():
            calls.setdefault("localroles" if k.startswith("roles") else k, []).append(v / 1000)
        calls.setdefault("roles 호출 수", []).append(sum(k.startswith("roles") for k in meta.get("call_ms") or {}))
        for k, v in (meta.get("timings_ms") or {}).items():
            stages.setdefault(k, []).append(v)
        print(f"{r['cell']:2d} {photo:7s} (차 {err:.1f}) {'맞음' if full else '고르면 맞음' if pick else '틀림' if valid else '입력 화면'}"
              f"{' 론쯔모' if side_ok else ''}{' 표시패' if ind_ok else ''} {r['t_record_s']}초 | 손패 {' '.join(m.get('closed') or [])} 울기 {m.get('melds')}"
              f" 화료 {m.get('win_tile')} {'쯔모' if m.get('is_tsumo') else '론'} {m.get('loser')} 표시패 {got} 후보 {cands} | 정답 {t['win']} {t['tsumo']} {t['loser']} {t['inds']}")
    print()
    for part in ("BCD", "오전", "오후"):
        print(part, {k: tally[(part, k)] for k in ("n", "맞음", "고르면 맞음", "계산했는데 틀림", "론쯔모까지", "표시패", "표시패 정답 있음", "오류")})
    print("빠진 사진", sorted(set(scenes) - set(seen)), "두 번 이상", [k for k, v in seen.items() if v > 1])
    print("완료 → 기록(초)", q(times), f"n={len(times)}")
    print("단계 중앙(ms)", {k: statistics.median(v) for k, v in stages.items()})
    print("호출(초)", {k: q(v) for k, v in calls.items()})


if __name__ == "__main__":
    main()
