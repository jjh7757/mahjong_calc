"""debug_153311.py 이어서: 눕힌 4p 상자를 분류기에 그대로(read2, 손패 경로) / 90°·270° 돌려(read_any2, 떼어 둔 패 후보 경로) 넣은 확률.
  python -I -X utf8 experiments/speed/debug_153311b.py
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import robust_suite as R  # noqa: E402
from app import local_read as lr  # noqa: E402
from app import roles  # noqa: E402
from app.recognizer import prepare_image  # noqa: E402

N = "20261107_153311"
sys.stdout.reconfigure(encoding="utf-8")
meta = json.loads((R.RB / "meta.json").read_text(encoding="utf-8"))
s = next(x for x in R.scenes("dev") if x["name"] == N)
reader = lr.LocalReader(threads=2)
out_dir = HERE / "results" / "debug_153311"
out_dir.mkdir(exist_ok=True)
for v in ["orig", "rc_gray", "blur1", "blur2"]:
    jpeg = prepare_image(Path(meta[v][N]["src"]).read_bytes(), 4080)
    rgb = lr.decode_rgb(jpeg)
    for tag, net in (("v3r15d", roles.RoleNet(roles.ROLE_MODEL)), ("v3r15dfix", roles.RoleNet(R.MODELS / "tile-roles-v3r15dfix.onnx"))):
        o = roles.read_roles(reader, jpeg, s["side"], s["grid"], "hybrid", net=net)
        sep = o.get("separate_tile")
        print(f"{v:8s} {tag:9s} 손패 {len(o['tiles'])}장 끝 {o['tiles'][-1]['tile']}  떼어 둔 패 {sep and (sep['tile'], sep.get('from', '틀 안 fr.separate → read2'))}")
    b = next(r["box"] for r in o["roles"] if r["box"][0] > 2600 and 2400 < r["box"][1] < 2450)
    im = lr.cut(rgb, tuple(b))
    im.save(out_dir / f"{v}_crop.png")
    for k in (0, 1, 3):
        p = reader.probs([im.rotate(90 * k, expand=True)])[0]
        top = np.argsort(-p)[:3]
        print(f"   상자 {b} 크롭 {im.size} 회전 {90 * k:3d}°: " + " · ".join(f"{lr.CLASSES[i]} {p[i]:.3f}" for i in top))
