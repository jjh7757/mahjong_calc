"""det.json 에서 한 자리의 프레임별 읽기(강 순서) 보기. python dump_side.py results/R4/det.json bottom 15:42:40 15:43:05"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from paifu_frames import order_tiles
import numpy as np

det = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
hd = float(np.median([d["dev"][2] for d in det]))
for d in det:
    at = d["at"][11:19]
    if len(sys.argv) > 3 and not (sys.argv[3] <= at <= sys.argv[4]):
        continue
    ts = order_tiles([t for t in d["tiles"] if t["side"] == sys.argv[2]], hd)
    print(at, " ".join(f"{t['t']}:{t['c']:.2f}" for t in ts))
