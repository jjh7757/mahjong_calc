"""debug_153311b 이어서: 눕힌 4p 상자가 어느 읽기 함수로 가는지 호출을 가로채 찍는다(read2 = 돌리지 않음, read_turned2·read_any2 = 돌림).
  python -I -X utf8 experiments/speed/debug_153311c.py
"""
import json
import sys
from pathlib import Path

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
log = []
is4p = lambda b: b is not None and b[0] > 2600 and 2400 < b[1] < 2450
orig_cut = lr.cut


def cut_spy(rgb, b):
    if is4p(b):
        log.append(("cut(read2 경로 크롭)", tuple(round(v) for v in b)))
    return orig_cut(rgb, b)


lr.cut = cut_spy
for name in ("read_turned2", "read_any2"):
    f = getattr(reader, name)

    def spy(rgb, b, *a, _f=f, _n=name):
        r = _f(rgb, b, *a)
        if is4p(b):
            log.append((_n, r[:2]))
        return r

    setattr(reader, name, spy)
orig_split = lr.split_frame


def split_spy(rgb, faces, split):
    fr = orig_split(rgb, faces, split)
    log.append(("split_frame", None if fr is None else dict(hand=len(fr.hand), sep=fr.separate is not None and is4p(fr.separate), melds=len(fr.melds),
                                                           in_hand=any(is4p(b) for b in fr.hand), ok=lr.frame_ok(fr, rgb))))
    return fr


lr.split_frame = split_spy
for v in ["orig", "rc_gray", "blur1"]:
    jpeg = prepare_image(Path(meta[v][N]["src"]).read_bytes(), 4080)
    for tag, net in (("v3r15d", roles.RoleNet(roles.ROLE_MODEL)), ("v3r15dfix", roles.RoleNet(R.MODELS / "tile-roles-v3r15dfix.onnx"))):
        log.clear()
        o = roles.read_roles(reader, jpeg, s["side"], s["grid"], "hybrid", net=net)
        role4 = next(r["role"] for r in o["roles"] if is4p(r["box"]))
        sep = o.get("separate_tile")
        print(f"{v:8s} {tag:9s} 4p 역할 {role4:5s} → 손패 {len(o['tiles'])}장 끝 {o['tiles'][-1]['tile']}, 떼어 둔 패 {sep and sep['tile']}")
        for e in log:
            print("     ", e)
