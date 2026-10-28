"""seat3_scenes(자리 판독 3번 동시 + 만장일치) 결과를 채점한다.

  python -I experiments/field_20261024/score_seat3.py [폴더=seat3_scenes]

두 단계로 본다.
- 자리 판독: 화료자 자리의 손패·울기가 맞는가, 서버의 세 답이 모두 같았는가(앱 경고 "…번 읽어 …번만 같았습니다" 가 없음).
  만장일치인데 틀림 = 자리 판독만 보면 틀린 채 통과.
- 앱 기준 자동 반영 = 만장일치이고 점수까지 계산됨(장수가 안 맞거나 화료 형태가 아니면 앱이 입력 화면으로 돌려보낸다).
  틀린 채 반영 = 자동 반영인데 점수가 틀림.
정답: B·C·D 의 점수까지(NOTES "갤러리 사진 판독" 표). 화료패가 사진에 없는 A·E 는 평가에서 뺀다(2026-10-25 사용자 결정).
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent
TRUTH = {
    # 장면: (화료자, 손패(떨어진 한 장 포함, 강에서 온 화료패 제외), 울기, 점수)
    "B": ("right", "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p", ["6z 6z 6z"], 12000),
    "C": ("left", "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z", [], 16000),
    "D": ("bottom", "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z", ["6m 7m 8m"], 18000),
}


def hand_of(trace_obs: dict, side: str) -> tuple[Counter, list[str]]:
    p = trace_obs["players"][side]
    tiles = list(p["hand"]["tiles"]) + ([p["hand"]["separate_tile"]] if p["hand"]["separate_tile"] else [])
    melds = sorted(" ".join(sorted(m["tiles"])) for m in p["melds"])
    return Counter(tiles), melds


def main() -> None:
    folder = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "seat3_scenes")
    rows = []
    for f in sorted(folder.glob("*/*/result.json")):
        scene = f.parent.parent.name
        if scene not in TRUTH:  # 화료패가 사진에 없는 A·E 는 평가에서 뺀다(2026-10-25 사용자 결정)
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        side, hand, melds, points = TRUTH[scene]
        obs = d.get("observation")
        disagree = [w for w in d.get("warnings", []) if "번 읽어" in w]
        ok_side = d.get("winner_side") == side
        ok_hand = False
        if obs and ok_side:
            got, got_melds = hand_of(obs, side)
            ok_hand = got == Counter(hand.split()) and got_melds == sorted(" ".join(sorted(m.split())) for m in melds)
        m = re.search(r" (\d{3,6}) \[", d.get("score") or "")
        got_points = int(m.group(1)) if m else None
        ok = ok_hand and (points is None or got_points == points)
        rows.append({"scene": scene, "run": f.parent.name, "ok": ok, "ok_hand": ok_hand, "unanimous": not disagree,
                     "auto": not disagree and "error" not in d and got_points is not None,
                     "side": d.get("winner_side"), "points": got_points, "ms": d.get("total_ms"),
                     "read_ms": (d.get("timings_ms") or {}).get("read"), "disagree": disagree, "error": d.get("error")})
    print(f"자리 판독: 손패·울기 정답 {sum(r['ok_hand'] for r in rows)}/{len(rows)}, 만장일치 {sum(r['unanimous'] for r in rows)}, "
          f"만장일치인데 틀림 {sum(r['unanimous'] and not r['ok_hand'] for r in rows)}, "
          f"엇갈림 {sum(not r['unanimous'] for r in rows)}(그중 다수 답이 정답 {sum(not r['unanimous'] and r['ok_hand'] for r in rows)})")
    auto_ok = sum(r["auto"] and r["ok"] for r in rows)
    auto_bad = [r for r in rows if r["auto"] and not r["ok"]]
    ask = [r for r in rows if not r["auto"]]
    print(f"{folder.name}: {len(rows)}회  정답 {sum(r['ok'] for r in rows)}  |  자동 반영 {auto_ok + len(auto_bad)} "
          f"(그중 틀림 {len(auto_bad)})  확인 묻기 {len(ask)}")
    ms = [r["ms"] for r in rows if r["ms"]]
    if ms:
        print(f"  전체 시간 중앙 {statistics.median(ms) / 1000:.1f}초, 최대 {max(ms) / 1000:.1f}초")
    for s in TRUTH:
        rs = [r for r in rows if r["scene"] == s]
        if rs:
            print(f"  {s}: 정답 {sum(r['ok'] for r in rs)}/{len(rs)}  손패 {sum(r['ok_hand'] for r in rs)}  "
                  f"만장일치 {sum(r['unanimous'] for r in rs)}  자동 {sum(r['auto'] for r in rs)}  "
                  f"시간 {', '.join(f'{r['ms'] / 1000:.1f}' for r in rs if r['ms'])}초")
    for r in rows:
        if not r["ok"] or not r["unanimous"]:
            print(f"   {r['scene']} {r['run']}: {'정답' if r['ok'] else '틀림'}(손패 {'맞음' if r['ok_hand'] else '틀림'}) "
                  f"{'만장일치' if r['unanimous'] else '엇갈림'} {'자동' if r['auto'] else '확인'} "
                  f"화료자 {r['side']} 점수 {r['points']} {r['error'] or ''} {' '.join(r['disagree'])[:200]}")


if __name__ == "__main__":
    main()
