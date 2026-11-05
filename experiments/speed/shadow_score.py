"""앱 흐름 로그의 자체 모델 그림자 답(`local_shadow`)을 채점한다(2026-11-02, API 없음). 다음 매장 사진은 이 스크립트에 새 로그·정답을 넣는다.
  python -I -X utf8 experiments/speed/shadow_score.py <로그>...
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "yolo"))
import hybrid as hy  # noqa: E402
import hybrid_replay as hr  # noqa: E402
import seat_grow as sg  # noqa: E402


def q(a: list) -> str:
    a = sorted(a)
    return f"{a[len(a) // 2] / 1000:.2f} / {a[min(len(a) - 1, int(.9 * len(a)))] / 1000:.2f} / {a[-1] / 1000:.2f}" if a else "—"


scenes = {(s["name"] if s["set"] == "bcd" else s["name"][-6:]): s for s in sg.eval_scenes() if s["hand"] is not None}  # 가림 사진 뺌
rows = []
for p in sys.argv[1:]:
    for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        i = line.find("TIMING {")
        if i >= 0:
            rows.append(json.loads(line[i + 7:]))
seat, river, rss = [], [], []
pending = errors = n = have = framed = ok = auto = bad = 0
for r in rows:
    for k, v in (r.get("local_shadow") or {}).items():
        if v.get("pending"):
            pending += 1
        elif v.get("error"):
            errors += 1
        else:
            rss.append(v.get("rss_mb") or 0)
            (seat if k.startswith("seat_") else river).append(v["ms"]["total"])
    s = scenes.get(r["photo"])
    if s is None:
        continue
    n += 1
    v = (r.get("local_shadow") or {}).get(f"seat_{s['side']}")
    if v and "framed" in v:
        have += 1
        framed += v["framed"]
        y = hr.same(v["hand"], v["melds"], s)
        a = bool(v["hand"]) and not v["block"] and hy.check(v["hand"], [m.split() for m in v["melds"]])[0]
        ok += y
        auto += a
        bad += a and not y
print(f"그림자 자리 {len(seat)}번 {q(seat)} / 강 {len(river)}번 {q(river)} / 안 끝남 {pending} / 오류 {errors} / 최대 메모리 {max(rss, default=0)}MB, 처음 값 {rss[:3]}")
print(f"채점 {n}회, 답 있음 {have}, 틀 {framed}, 맞음 {ok}, 자동 {auto}(틀림 {bad})")
