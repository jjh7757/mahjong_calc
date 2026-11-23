"""추적 기록 프레임마다 앱의 겹쳐 보기(`ondevice.overlay`, 기기 안 판독과 같은 파이썬)를 PC 에서 돌려 그대로 받아 둔다(2026-11-17).

앱의 버림 기록기(`lib/paifu/discard_recorder.dart`)를 실제 겹쳐 보기 출력으로 다시 돌려 보기 위한 입력이다
(`replay_recorder.dart overlay <이 파일>`). 판 정의(track · t0 · t1)는 `truth.json` 에서 읽는다.

  python -X utf8 experiments/paifu_frames/overlay_dump.py R4 [R2 R3a ...] [--truth truth_1114.json]
결과: results/<판>/overlay_dump.json = {"grid": {...}, "frames": [{"file", "at", "w", "h", "tiles": [{"b","t","tc","r","rc","s","t2","tc2"}], "ms"}]}
t · tc = 겹쳐 보기가 낸 종류(프레임 크기 그대로), t2 · tc2 = 같은 상자를 키워 읽은 종류(`read_small`).
"""
import io
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.append(str(ROOT / "android/app/src/main/python"))
import ondevice  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def main():
    reader = ondevice._get_reader()
    args = sys.argv[1:]
    tfile = "truth.json"
    if "--truth" in args:
        i = args.index("--truth")
        tfile = args[i + 1]
        del args[i:i + 2]
    truth = json.loads((HERE / tfile).read_text(encoding="utf-8"))
    for name in args:
        r = truth[name]
        track = (HERE / r["track"]).resolve()
        t0, t1 = r.get("t0"), r.get("t1")
        frames, grid = [], None
        for z in sorted(track.glob("frames_*.zip")):
            zf = zipfile.ZipFile(z)
            meta = json.loads(zf.read("frames.json"))
            grid = grid or meta["grid"]
            for f in meta["frames"]:
                hms = f["at"][11:19]
                if (t0 and hms < t0) or (t1 and hms > t1):
                    continue
                raw = zf.read(f["file"])
                q = {k: str(meta["grid"][k]) for k in ("x1", "x2", "y1", "y2")}
                o = json.loads(ondevice.overlay(raw, q))
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                W, H = im.size
                # 추적 프레임(1020)은 패가 작아 겹쳐 보기의 분류(키우지 않음)가 거의 다 白 으로 읽는다(앱은 원래 크기 4080 프레임을 읽는다).
                # 종류만 `read_small`(키워 읽기, paifu_frames.py 와 같은 길)로 한 번 더 읽어 t2 · tc2 로 같이 둔다.
                rgb = np.asarray(im)
                for t in o["tiles"]:
                    x, y, w, h = t["b"]
                    t["t2"], t["tc2"] = reader.read_small(rgb, (round(x * W), round(y * H), round(w * W), round(h * H)))
                frames.append({"file": f["file"], "at": f["at"], "w": W, "h": H, "tiles": o["tiles"], "ms": o["ms"]})
                print(name, f["file"], len(o["tiles"]), "장", sum(1 for t in o["tiles"] if t["r"] == "river"), "강", o["ms"]["total"], "ms", flush=True)
        out = HERE / "results" / name
        out.mkdir(parents=True, exist_ok=True)
        (out / "overlay_dump.json").write_text(json.dumps({"grid": grid, "frames": frames}, ensure_ascii=False), encoding="utf-8")
        print(name, "→", out / "overlay_dump.json", len(frames), "프레임")


if __name__ == "__main__":
    main()
