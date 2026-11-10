"""153311 rc_gray 에서 운영 v3r15d 는 마지막 4p 를 2p 로, v3r15dfix 는 4p 로 읽은 원인 추적(2026-11-10, 사용자 "원인 분석해봐").
robust_suite 와 같은 호출(roles.read_roles hybrid, prod 리더)로 역할 모델만 바꿔 손패 쪽 상자·역할·읽기를 찍는다.
  python -I -X utf8 experiments/speed/debug_153311.py [변형=rc_gray ...]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import robust_suite as R  # noqa: E402  (sys.path 에 서버 저장소를 넣는다)
from app import local_read as lr  # noqa: E402
from app import roles  # noqa: E402
from app.recognizer import prepare_image  # noqa: E402

N = "20261107_153311"
sys.stdout.reconfigure(encoding="utf-8")
meta = json.loads((R.RB / "meta.json").read_text(encoding="utf-8"))
s = next(x for x in R.scenes("dev") if x["name"] == N)
reader = lr.LocalReader(threads=2)
nets = {"v3r15d": roles.RoleNet(roles.ROLE_MODEL, threads=2), "v3r15dfix": roles.RoleNet(R.MODELS / "tile-roles-v3r15dfix.onnx", threads=2)}
print("운영 기본 역할 모델", roles.ROLE_MODEL.name)
for v in sys.argv[1:] or ["orig", "rc_gray", "blur1"]:
    info = meta[v][N]
    jpeg = prepare_image(Path(info["src"]).read_bytes(), 4080)
    for tag, net in nets.items():
        o = roles.read_roles(reader, jpeg, s["side"], s["grid"], "hybrid", net=net)
        mine = [r for r in o["roles"] if r["role"] in ("hand", "loose")]
        mine.sort(key=lambda r: r["box"][0])
        print(f"\n== {v} {tag}  framed={o['framed']} wall_frame={o.get('wall_frame')} cut={o.get('cut')} filled={o.get('filled')}")
        print("   손패", [(t["tile"], round(t["conf"], 3), t.get("alt")) for t in o["tiles"]])
        print("   떼어 둔 패", o.get("separate_tile"))
        print("   손패·loose 역할 상자(x 순):", [(r["box"], r["role"], round(r["conf"], 2), "안" if r["in_seat"] else "밖") for r in mine[-4:]])
