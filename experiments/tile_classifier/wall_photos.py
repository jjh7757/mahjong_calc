"""화료 원본 사진(4080×3060)에서 도라 표시패 찾기·읽기(2026-11-02, API 없음). 표 1-35. wall_frames.py 규칙을 그대로 쓴다.

정답 = visit_20261031/truth.json indicators(표 1-29 와 같은 19장). 그 시간대를 학습하지 않은 나눔 모델, 찾기는 통째 검출 1번, 읽기는 원본 크기 상자.
패산 = 앞뒤에 뒷면 색이 붙은 앞면 패. 탁자 = 뒷면이 안 붙고 이웃이 없는 2장 이하 덩어리(강·손패 덩어리는 3장 이상이라 빠진다).
  python -I -X utf8 experiments/tile_classifier/wall_photos.py
결과 data/wall_frames/photos.json, photos_overlay.jpg
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wall_frames as wf  # noqa: E402
from rules_core import st  # noqa: E402
from app import local_read as lr  # noqa: E402

V = wf.ROOT / "experiments" / "visit_20261031"
OCCLUDED = {"20261031_172424", "20261031_174020"}  # 가림 사진은 평가 제외(10-31 결정)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    scenes = json.loads((V / "truth.json").read_text(encoding="utf-8"))["scenes"]
    readers = {"a": lr.LocalReader(det_model=wf.MODELS / "det_fold_a.onnx", cls_model=wf.MODELS / "cls_pm.onnx"),
               "b": lr.LocalReader(det_model=wf.MODELS / "det_fold_b.onnx", cls_model=wf.MODELS / "cls_am.onnx")}
    res, tiles = {}, []
    for name, s in sorted(scenes.items()):
        want = s.get("indicators")
        if not want:
            continue
        rgb = np.asarray(Image.open(V / "captures" / name / "original.jpg").convert("RGB"))
        rd = readers["b" if name < "20261031_14" else "a"]
        t0 = time.perf_counter()
        faces = rd.detect(rgb)
        t1 = time.perf_counter()
        wall = wf.candidates(rgb, faces)
        flanked = {tuple(c["box"]) for c in wall}
        tw = statistics.median(min(f[2], f[3]) for f in faces) if faces else 1
        groups = st.cluster(faces, tw * 0.5, tw * 0.5)
        table = [tuple(int(v) for v in f) for g in groups if len(g) <= 2 for f in g if tuple(int(v) for v in f) not in flanked]
        pairs = [[rd.read_any(rgb, f)[0] for f in g] for g in groups if len(g) == 2]
        t2 = time.perf_counter()
        wall_read = [dict(box=c["box"], sides=c["sides"], score=c["score"], read=rd.read_any(rgb, c["box"])) for c in wall]
        table_read = [dict(box=list(b), read=rd.read_any(rgb, b)) for b in table]
        t3 = time.perf_counter()
        top = wall_read[0]["read"][0] if wall_read else None
        two = [w["read"][0] for w in wall_read if w["sides"] == 2]
        # 답: 리치면 딱 2장 묶음이 하나일 때 그 둘, 묶음이 없으면 패산 맨 위 한 장, 여럿이면 답 없음(확인). 리치 아니면 패산 맨 위 한 장.
        if s.get("riichi"):
            answer = pairs[0] if len(pairs) == 1 else ([top] if not pairs and top else None)
        else:
            answer = [top] if top else None
        res[name] = dict(want=want, riichi=s.get("riichi"), occluded=name in OCCLUDED, faces=len(faces), wall=wall_read, table=table_read, top=top, both_sides=two, pairs=pairs, answer=answer,
                         ok=bool(answer) and sorted(answer) == sorted(want), det_ms=round((t1 - t0) * 1000), rule_ms=round((t2 - t1) * 1000), read_ms=round((t3 - t2) * 1000))
        print(name[-6:], "리치" if s.get("riichi") else "    ", "정답", want, "| 패산", [(w["read"][0], w["sides"], w["read"][1]) for w in wall_read], "| 탁자", [t["read"][0] for t in table_read], "| ms", res[name]["det_ms"], res[name]["rule_ms"], res[name]["read_ms"], flush=True)
        im = Image.fromarray(rgb)
        d = ImageDraw.Draw(im)
        for w in wall_read:
            b = w["box"]
            d.rectangle((b[0], b[1], b[0] + b[2], b[1] + b[3]), outline="red", width=10)
        for t in table_read:
            b = t["box"]
            d.rectangle((b[0], b[1], b[0] + b[2], b[1] + b[3]), outline="yellow", width=10)
        im = im.resize((680, 510))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 330, 14), fill="black")
        d.text((2, 1), f"{name[-6:]} {'R' if s.get('riichi') else '-'} {want} {[w['read'][0] for w in wall_read]}", fill="white")
        tiles.append(im)
    (wf.OUT / "photos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    sheet = Image.new("RGB", (4 * 680, ((len(tiles) + 3) // 4) * 510))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % 4) * 680, (k // 4) * 510))
    sheet.save(wf.OUT / "photos_overlay.jpg", quality=88)
    non = [r for r in res.values() if not r["riichi"]]
    print("리치 아닌 화료", len(non), "맨 위 후보가 정답", sum([r["top"]] == r["want"] for r in non))
    gem = {r["name"]: r for r in json.loads((HERE / "data" / "det" / "other_reads.json").read_text(encoding="utf-8"))["ind"]}
    for name, r in sorted(res.items()):
        g = gem.get(name, {})
        r["gemini"], r["gem_ok"] = g.get("gemini"), g.get("gem_ok")
        print(name[-6:], "리치" if r["riichi"] else "    ", "가림" if r["occluded"] else "    ", "정답", r["want"], "| 답", r["answer"], "OK" if r["ok"] else ("없음" if not r["answer"] else "틀림"), "| 2장 묶음", r["pairs"], "| Gemini", r["gemini"], r["gem_ok"])
    for label, f in (("전체", lambda r: True), ("가림 제외", lambda r: not r["occluded"]), ("리치 아님·가림 제외", lambda r: not r["occluded"] and not r["riichi"]), ("리치·가림 제외", lambda r: not r["occluded"] and r["riichi"])):
        rs = [r for r in res.values() if f(r)]
        print(label, len(rs), "자체 맞음", sum(r["ok"] for r in rs), "틀림", sum(bool(r["answer"]) and not r["ok"] for r in rs), "답 없음", sum(not r["answer"] for r in rs), "| Gemini 맞음", sum(bool(r["gem_ok"]) for r in rs))
    (wf.OUT / "photos.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("시간 중앙 검출", statistics.median(r["det_ms"] for r in res.values()), "규칙", statistics.median(r["rule_ms"] for r in res.values()), "읽기", statistics.median(r["read_ms"] for r in res.values()))
    print(collections.Counter(len(r["wall"]) for r in res.values()))


if __name__ == "__main__":
    main()
