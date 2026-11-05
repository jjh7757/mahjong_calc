"""서버 함수 답이 고치기 전·후 같은지: 개발 세트(eval_scenes) 전부 read_roles·read_wall·read_seat_app 답을 저장/대조(시간 값 뺌).
  python -X utf8 same_out.py save <파일> | compare <파일>
"""
import io, json, sys
from pathlib import Path
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong_calc\experiments\speed")
from PIL import Image
from app import local_read as lr, roles
from app.recognizer import prepare_image
import seat_grow as sg


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in ("ms", "rss_mb", "latency_ms")}
    if isinstance(o, list):
        return [strip(v) for v in o]
    return o


rd = lr.LocalReader()
out = {}
for s in sg.eval_scenes():
    raw = Path(s["path"]).read_bytes()
    j = prepare_image(raw, 4080)
    r = {"roles": strip(roles.read_roles(rd, j, s["side"], s["grid"])), "wall": strip(rd.read_wall(j))}
    for _ in range(2):  # 같은 바이트를 다시 줘도(캐시) 답이 같아야 한다
        assert strip(roles.read_roles(rd, j, s["side"], s["grid"])) == r["roles"], s["name"]
    c = sg.crop(Image.open(io.BytesIO(raw)).convert("RGB"), sg.seat_box(s["grid"], s["side"], 40), s["side"])
    b = io.BytesIO(); c.save(b, "JPEG", quality=92)
    r["seat"] = strip(rd.read_seat_app(prepare_image(b.getvalue(), 3072), sg.hand_frac(s["grid"], s["side"])))
    out[s["name"]] = r
mode, f = sys.argv[1], Path(sys.argv[2])
if mode == "save":
    f.write_text(json.dumps(out, ensure_ascii=False, sort_keys=True), encoding="utf8")
    print("저장", len(out))
else:
    old = json.loads(f.read_text(encoding="utf8"))
    new = json.loads(json.dumps(out, ensure_ascii=False, sort_keys=True))
    diff = [k for k in old if old[k] != new.get(k)]
    print("장면", len(old), "다른 장면", diff)
