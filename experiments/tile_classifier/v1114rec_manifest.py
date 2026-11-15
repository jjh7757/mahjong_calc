"""11-14 헤드 녹화 프레임(rec1496) 세트 통합 목록(2026-11-15, 녹화 세트 2단계 1). v1114rec_pair.py·v1114rec_rounds.py(1단계, 다른 에이전트) 다음에.

읽기만: data/v1114rec/mid/picks.json(나 = 기존 판 안 새 순간 49장), data/v1114rec/new/picks.json·new/rounds.json(다 = 녹화만 있는 판 72장).
쓰기: data/v1114rec/manifest.json
  parts = {"mid": {...}, "new": {...}} — 부분마다 설명·장 수. "짝"(pair) 186장은 나중 단계가 parts.pair 와 items 에 더한다(이 스크립트는 pair 를 건드리지 않음,
          다시 돌릴 때 manifest 에 이미 있는 다른 part 의 items 는 그대로 둔다).
  items[] = id · part(mid|new) · round · scene_round · split · phase(나는 null — 눈 확인에서 정함, 다는 picks 의 play|end) · path(data/v1114rec 기준)
          · size · rec_dir · rec_file · ms · at · setup(카메라 거치 중) · scene_decided(계획 세션이 정한 모호 장면) · 나는 prev_id·next_id(기존 세트 이웃)
          · 다는 winner_hint(rounds.json 메모의 "… 자리 공개" → 자리, phase end 에만).
모호 장면 7장의 scene_round·split 은 계획 세션 결정(SCENE_DECIDED)을 여기에 직접 적는다(mid/picks.json 은 다른 에이전트가 고치는 중이라 안 고침).
  python -X utf8 experiments/tile_classifier/v1114rec_manifest.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
R = HERE / "data" / "v1114rec"
KST = timezone(timedelta(hours=9))
MID_REC_ROOT = "experiments/visit_20261114/head_rec"
# 계획 세션 결정(2026-11-15). "prev" = 앞 이웃의 scene_round
SCENE_DECIDED = {
    "r02_114700/mid_1794624443548": ("r02_114700", "train"),
    "r03_115446/mid_1794624918153": ("r03_115446", "train"),
    "r04_120417/mid_1794625490571": ("r04_120417", "dev"),
    "r06_121933/mid_1794626423835": ("r06_121933", "train"),
    "r10_130015/mid_1794628908540": ("prev", "train"),
    "r12_131655/mid_1794629842937": ("r12_131655", "train"),
    "r19_142013/mid_1794633604401": ("r19_142013", "dev"),
}
SETUP = {"r01_112804/mid_1794623624640", "r01_112804/mid_1794623866127"}  # 카메라 거치 중 장면
SEAT_WORD = {"아래": "bottom", "위": "top", "왼쪽": "left", "오른쪽": "right"}


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, KST).isoformat(timespec="milliseconds")


def main():
    mid = json.loads((R / "mid" / "picks.json").read_text(encoding="utf-8"))
    new = json.loads((R / "new" / "picks.json").read_text(encoding="utf-8"))
    rounds = json.loads((R / "new" / "rounds.json").read_text(encoding="utf-8"))
    items = []
    for p in mid["picks"]:
        sr, sp = p.get("scene_round"), p.get("split")
        dec = None
        if p["id"] in SCENE_DECIDED:
            sr, sp = SCENE_DECIDED[p["id"]]
            if sr == "prev":
                sr = p["scene_round_prev"]
            dec = {"scene_round": sr, "split": sp, "by": "계획 세션 2026-11-15", "picks_ambiguous": bool(p.get("scene_ambiguous"))}
        im = Image.open(R / p["path"])
        items.append({"id": p["id"], "part": "mid", "round": p["round"], "scene_round": sr, "split": sp, "phase": None, "path": p["path"],
                      "size": list(im.size), "rec_dir": f"{MID_REC_ROOT}/{p['rec_dir']}", "rec_file": p["rec_file"], "ms": p["rec_ms"], "at": iso(p["rec_ms"]),
                      "setup": p["id"] in SETUP, "scene_decided": dec, "prev_id": p["prev_id"], "next_id": p["next_id"],
                      "prev_ms": p.get("prev_rec_ms"), "next_ms": p.get("next_rec_ms"), "gap_s": p.get("gap_s")})
    rmeta = {r["id"]: r for r in rounds["rounds"]}
    for p in new:
        r = rmeta[p["round"]]
        m = re.search(r"(아래|위|왼쪽|오른쪽) 자리 공개", r.get("note", ""))
        im = Image.open(R / p["path"])
        items.append({"id": p["id"], "part": "new", "round": p["round"], "scene_round": p["scene_round"], "split": p["split"], "phase": p["phase"],
                      "path": p["path"], "size": list(im.size), "rec_dir": rounds["source"], "rec_file": p["rec_file"], "ms": p["ms"], "at": p["at"],
                      "setup": False, "scene_decided": None,
                      "winner_hint": SEAT_WORD[m.group(1)] if (m and p["phase"] == "end") else None,
                      "round_result": r.get("result"), "round_back": r.get("back")})
    for it in items:
        assert it["scene_round"] and it["split"] in ("train", "dev"), it["id"]
        assert (R / it["path"]).exists(), it["path"]
    items.sort(key=lambda it: (it["part"], it["round"], it["ms"]))
    # 판 목록(초안·양식·몫 단위)
    rl = {}
    for it in items:
        e = rl.setdefault(it["round"], {"id": it["round"], "part": it["part"], "images": 0, "splits": set()})
        e["images"] += 1
        e["splits"].add(it["split"])
    rlist = [{**e, "splits": sorted(e["splits"])} for e in sorted(rl.values(), key=lambda e: e["id"])]
    out = R / "manifest.json"
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    keep = [it for it in old.get("items", []) if it.get("part") not in ("mid", "new")]  # 다른 단계가 더한 part(pair 등)는 그대로
    parts = {k: v for k, v in (old.get("parts") or {}).items() if k not in ("mid", "new")}
    parts["mid"] = {"n": sum(it["part"] == "mid" for it in items), "from": "mid/picks.json (v1114rec_pair.py)",
                    "what": "기존 판(r01~r20) 안, 기존 세트 두 프레임 사이 중간 시각의 녹화 프레임. prev_id·next_id = 기존 세트 이웃(data/v1114/dr/final 라벨)."}
    parts["new"] = {"n": sum(it["part"] == "new" for it in items), "from": "new/picks.json·new/rounds.json (v1114rec_rounds.py)",
                    "what": "녹화만 있는 판 n01~n08(14:47~15:47), 판마다 진행 중 8장(play) + 공개 1장(end). 태블릿 기록·정답 없음."}
    man = {"_note": "녹화 프레임(rec1496: 2992 스트림을 기기에서 2×2 평균, JPEG 85, 1496²) 세트 통합 목록. v1114rec_manifest.py. path = data/v1114rec 기준. "
                    "좌표·라벨은 모두 1496 원래 좌표. phase 는 나(mid)는 null(눈 확인에서 정함).",
           "quality": "rec1496", "parts": parts, "rounds": rlist + [r for r in old.get("rounds", []) if r.get("part") not in ("mid", "new")],
           "items": items + keep}
    out.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print("items", len(items), {k: v["n"] for k, v in parts.items()}, "rounds", len(rlist))
    print("split", {(p, s): sum(1 for it in items if it["part"] == p and it["split"] == s) for p in ("mid", "new") for s in ("train", "dev")})


if __name__ == "__main__":
    main()
