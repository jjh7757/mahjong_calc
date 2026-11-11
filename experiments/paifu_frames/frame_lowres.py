"""헤드 화질이 더 떨어지면(2026-11-11, 사용자 "헤드 카메라 성능이 떨어져도 문제 없겠지?"): 12MP 화료 사진(R2·R3a·R4, 강 94장)을
헤드 방식(건너뛰기) / 평균으로 step 4·5·6·8·10 줄여 같은 파이프라인(검출 → read_small). FS_CLS 로 분류기 바꿈. 검출 놓침과 오독을 따로."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
import paifu_frames as pf, frame_split as fs

reader = fs.make_reader()
cap = fs.HERE.parent / "visit_20261107" / "captures"
tot = {}
for name in fs.ROUNDS:
    det = json.loads((fs.HERE / "results" / name / "det.json").read_text(encoding="utf-8"))
    cx, cy, hd = det[-1]["dev"]
    expect = {s: [x[1] for x in fs.tseq(name) if x[0] == s and not x[2]] for s in fs.SIDES}
    full = np.asarray(Image.open(cap / fs.TRUTH[name]["win_photo"] / "original.jpg").convert("RGB"))
    for step in (4, 5, 6, 8, 10):
        for mode in ("skip", "avg"):
            rgb = fs.head_small(full, step, mode)
            k = rgb.shape[1] / 1020
            r = fs.tally(expect, fs.read_scene(reader, rgb, cx * k, cy * k, hd * k), hd * k)
            t = tot.setdefault((step, mode), [0, 0, 0, 0, rgb.shape[1], []])
            for i in range(4):
                t[i] += r[i]
            t[5] += r[4]
print("분류기:", fs.os.environ.get("FS_CLS", "운영(기본)"))
for (step, mode), t in tot.items():
    print(f"  1/{step} {'건너뛰기' if mode == 'skip' else '평균':4s} 긴 변 {t[4]:4d} (패 약 {92 // step}×{116 // step}px)  맞음 {t[0]:2d}/94 오독 {t[1]:2d} 놓침 {t[2]:2d} 헛것 {t[3]}  {' '.join(t[5][:8])}")
(fs.HERE / "results" / f"frame_lowres{fs.TAG}.json").write_text(json.dumps({f"{s}_{m}": t[:5] for (s, m), t in tot.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
