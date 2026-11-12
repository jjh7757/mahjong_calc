"""판 중 프레임 라벨 확정(2026-11-11, docs/role_owner_plan_1111.md 1단계): 초안 + 눈 확인 3몫 + 독립 검토 + 검증 세션 판정 → labels_{dev,test}.json.

초안 = role_frames_draft.py 의 labels_{dev,test}.draft.json. 눈 확인 = data/role/frames/eye/part{1,2,3}.json(Opus 5.5 중간 3대),
독립 검토 = review/independent_review_frames.json(초안 안 본 17프레임 580상자, 불일치 2 = 0.34%).
눈 확인 보고의 상자 번호는 확인 그림 글자(= 초안 `id`)인데 12프레임에서 `id` 가 목록 순서와 다르다 → 여기서는 **상자 좌표**로 대상을 찾는다.

판정(검증 세션이 확대 그림으로 다시 봄):
  FIX     주인 고침 1: 170310_f0060 왼쪽 강 줄 끝의 리치 선언패를 초안이 bottom 으로 붙임(같은 판 f0069 는 left 로 맞음).
  MERGE   한 패를 위·아래 반쪽으로 잡은 상자 둘 → 온전한 상자 하나(4프레임).
  ADD     상자 없던 白 울기 1장(140304 판Q5 왼위 모서리): f0313 은 눈 확인 3 이 찾음, 같은 판 f0365 는 빈 모서리 프레임(f0285·f0388)과 비교해 더함.
  NOSCORE 라벨을 정할 수 없는 상자 13개 — 입력에는 남기고 채점에서 뺀다(score=false).
  UNFIT   평가 부적합 프레임 1(엄지가 방금 놓는 강 패 앞면을 덮음) → 세트에서 뺀다.
눈 확인이 "모름" 으로 적었지만 초안대로 두고 채점하는 것: 줄이 보통과 반대쪽에서 시작한 강 패(140304_f0440 둘·155125_f0061 둘),
막 던진 강 패(154548_f0017 하나), 140304_f0365 왼위 白(빈 모서리 프레임과 비교해 패로 확인).

  python -I -X utf8 experiments/tile_classifier/role_frames_final.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

F = Path(__file__).resolve().parent / "data" / "role" / "frames"

FIX = {("20261031_170310_f0060", (421, 436, 23, 27)): ("river", "left")}
MERGE = {  # 프레임: (온전한 상자, 역할, 자리) — 이 상자 안에 60% 넘게 든 초안 상자를 지우고 대신 넣는다
    "20261031_133940_f0129": ((895, 598, 26, 33), "meld", "bottom"),
    "20261031_133940_f0132": ((895, 601, 26, 32), "meld", "bottom"),
    "20261107_140304_f0123": ((568, 290, 21, 29), "river", "top"),
    "20261107_155125_f0041": ((588, 494, 24, 31), "river", "bottom"),
}
ADD = {
    "20261107_140304_f0313": ((224, 48, 20, 32), "meld", "top"),
    "20261107_140304_f0365": ((224, 48, 20, 32), "meld", "top"),
}
NOSCORE = {  # (프레임, 초안 상자) : 이유
    ("20261031_141615_f0101", (554, 655, 26, 24)): "손가락에 든 패, 앞면이 보이는지 모름",
    ("20261031_133940_f0108", (206, 699, 33, 27)): "왼아래 흰 면(白 울기로 보이나 셋째 장이 안 보임)",
    ("20261031_133940_f0108", (209, 725, 27, 30)): "왼아래 흰 면",
    ("20261031_133940_f0129", (207, 705, 29, 22)): "왼아래 흰 면",
    ("20261031_133940_f0129", (208, 725, 26, 30)): "왼아래 흰 면",
    ("20261031_133940_f0132", (787, 0, 33, 19)): "사진 위 끝에 잘린 패(초안 other, 독립 검토 meld/right)",
    ("20261107_154029_f0066", (641, 664, 31, 25)): "손패 앞 눕힌 흰 면",
    ("20261031_170310_f0334", (848, 44, 23, 17)): "오른쪽 울기 가운데 줄: 반쪽 상자인지 포갠 가깡인지 모름",
    ("20261031_170310_f0334", (847, 60, 24, 17)): "오른쪽 울기 가운데 줄",
    ("20261107_155125_f0073", (890, 279, 33, 25)): "손패 줄 끝 2장: hand 인지 떼어 둔 패·짝인지 모름",
    ("20261107_155125_f0073", (883, 301, 32, 25)): "손패 줄 끝 2장",
}
NOSCORE_SAME = {  # 같은 패를 다른 프레임에서 뺐으므로 같이 뺀다(상자 번호로 — 이 프레임은 id = 순서)
    "20261031_133940_f0132": (67, 68),
}
UNFIT = {"20261107_154548_f0039": "왼쪽 사람 엄지가 방금 놓는 강 패 앞면을 덮음"}


def near(a, b, tol=2.5) -> bool:
    return all(abs(float(x) - float(y)) <= tol for x, y in zip(a, b))


def inside(a, b) -> float:
    ix = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    return ix * iy / (a[2] * a[3])


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    used = Counter()
    for sp in ("dev", "test"):
        src = json.loads((F / f"labels_{sp}.draft.json").read_text(encoding="utf-8"))
        out, stats = [], Counter()
        for f in src["frames"]:
            name = os.path.basename(f["image"])[:-4]
            if name in UNFIT:
                used["unfit"] += 1
                continue
            items = []
            for it in f["items"]:
                it = dict(it, draft_id=it.get("id"), score=True)
                for (n, box), (role, seat) in FIX.items():
                    if n == name and near(it["box"], box):
                        it.update(role=role, seat=seat, src_label="eye")
                        used["fix"] += 1
                for (n, box), why in NOSCORE.items():
                    if n == name and near(it["box"], box):
                        it.update(score=False, why=why)
                        used["noscore"] += 1
                if name in NOSCORE_SAME and it.get("id") in NOSCORE_SAME[name]:
                    it.update(score=False, why="왼아래 흰 면(같은 판 f0108·f0129 와 같은 패)")
                    used["noscore"] += 1
                items.append(it)
            if name in MERGE:
                box, role, seat = MERGE[name]
                keep = [it for it in items if inside(it["box"], box) <= 0.6]
                assert len(items) - len(keep) == 2, (name, len(items) - len(keep))
                items = keep + [dict(box=list(box), role=role, seat=seat, src="added", score=True, why="반쪽 상자 둘을 합침")]
                used["merge"] += 1
            if name in ADD:
                box, role, seat = ADD[name]
                assert all(inside(it["box"], box) < 0.3 for it in items), name
                items.append(dict(box=list(box), role=role, seat=seat, src="added", score=True, why="검출이 놓친 白 울기 1장"))
                used["add"] += 1
            for i, it in enumerate(items):
                it["id"] = i
                stats[it["role"]] += 1
                stats["noscore"] += not it["score"]
            out.append(dict(f, name=name, items=items))
        note = ("판 중 프레임 역할·주인 라벨 확정본(role_frames_final.py). items[].score=false 는 채점에서 뺀다(입력에는 남김). "
                "id = 목록 순서, draft_id = 초안 확인 그림의 번호.")
        (F / f"labels_{sp}.json").write_text(json.dumps({"_note": note, "frames": out}, ensure_ascii=False), encoding="utf-8")
        print(sp, "프레임", len(out), "상자", sum(len(f["items"]) for f in out), dict(stats))
    want = dict(fix=len(FIX), noscore=len(NOSCORE) + sum(len(v) for v in NOSCORE_SAME.values()), merge=len(MERGE), add=len(ADD), unfit=len(UNFIT))
    print("적용", dict(used), "기대", want)
    assert dict(used) == want, "판정 표의 상자를 초안에서 못 찾음"


if __name__ == "__main__":
    main()
