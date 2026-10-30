"""강 크롭에서 눕힌 패(리치 선언패)를 YOLO 틀로 찾는지 잰다. Gemini 호출 없음.

사용: python river_sideways.py <mahjong-recognizer 경로> <크롭 묶음 폴더>...
크롭 묶음 = last3yolo_scenes 처럼 `<폴더>/**/last_*.jpg`, 또는 촬영 기록처럼 `<폴더>/**/river_*.jpg`.
정답: B 아래 7통, B 왼쪽 2통, D 위 0s 가 눕힘. NOTES "버림패 전체 읽기" 의 정답 표엔 B 왼쪽이 빠져 있었다(10-30 그림으로 확인).
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from app.river import RiverLocator  # noqa: E402

loc = RiverLocator()
# 자리 전체(B/C/D, 자리) → 눕힌 패가 있나
TRUTH = {("B", "bottom"), ("B", "left"), ("D", "top")}

for root in map(Path, sys.argv[2:]):
    hit = collections.Counter()
    for p in sorted([*root.rglob("last_*.jpg"), *root.rglob("river_*.jpg")]):
        side = p.stem.split("_", 1)[1]
        f, _ = loc.locate(p.read_bytes())
        rel = p.relative_to(root)
        scene = rel.parts[0]
        if f is None:
            print(f"{rel}: 틀 못 잡음")
            hit["none"] += 1
            continue
        side_idx = [i for i, s in enumerate(f.sideways) if s]
        print(f"{rel}: {f.count}장 줄 {[len(r) for r in f.rows]} 눕힘 {side_idx}")
        if scene in ("B", "C", "D"):
            want = (scene, side) in TRUTH
            got = bool(side_idx)
            hit["있음 맞음" if want and got else "놓침" if want else "헛 잡음" if got else "없음 맞음"] += 1
    print(f"== {root.name}: {dict(hit)}")
