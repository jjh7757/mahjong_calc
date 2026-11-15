"""해상도별 패산 표시패 읽기를 지금 모델로 다시(2026-11-12). metrics 표 1-53 (1) 을 운영 모델·나눔 모델(cls6·det_r8·v3r15d)로.

표 1-53 은 11-03 모델(cls_am/pm·det_fold 1회차)로 잰 값이다(2040 6/8, 놓친 2장은 "없음"). 받고 있는 헤드 녹화 2040 으로 표시패를 읽어도 되는지 보려고
같은 장면(10-31 리치 아닌 화료 원본, 평가 제외 뺌)을 원본 / 2040 면적 평균 JPEG 85(헤드 녹화 방식, overlay_score.shrink 와 같음) / 2040 LANCZOS JPEG 90
(표 1-53 방식)으로 줄여 서버 read_wall(작은 상자는 read_small 로 키워 읽음, 확신 0.7 미만은 답 없음)을 그대로 부른다.

  python -X utf8 experiments/tile_classifier/dora_resolution_now.py [fold|prod]
결과 experiments/tile_classifier/data/dora_rounds/resolution_now_<models>.json
"""
import io
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("ROBUST_CLS", "cls6")
os.environ.setdefault("ROBUST_SEAT", "det_r8")
os.environ.setdefault("ROBUST_ROLE", "tile-roles-v3r15d")
sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
sys.path.insert(0, str(ROOT / "experiments/speed"))
import robust_suite as rs  # noqa: E402

TRUTH = json.loads((ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]


def jpeg(im: Image.Image, q: int) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return buf.getvalue()


def variants(path: str) -> dict:
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    k = max(im.size) / 2040
    avg = im.reduce(round(k)) if abs(k - round(k)) < 0.05 else im.resize((round(im.width / k), round(im.height / k)), Image.BOX)
    lan = im.resize((round(im.width / k), round(im.height / k)), Image.LANCZOS)
    return {"원본": Path(path).read_bytes(), "2040 평균 q85": jpeg(avg, 85), "2040 LANCZOS q90": jpeg(lan, 90)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    models = sys.argv[1] if len(sys.argv) > 1 else "fold"
    rd = rs.Readers(models, 4)
    rows, score = {}, {}
    for s in rs.scenes("dev"):
        t = TRUTH.get(s["name"])
        if not t or t["riichi"]:
            continue
        (reader, _), files = rd.get(s["name"])
        row = {}
        for label, data in variants(s["path"]).items():
            o = reader.read_wall(data)
            got = o["indicators"][0]["tile"] if o["indicators"] else None
            k = "맞음" if got in t["indicators"] else ("없음" if got is None else "틀림")
            score.setdefault(label, {"맞음": 0, "틀림": 0, "없음": 0})[k] += 1
            row[label] = {"got": got, "판정": k, "conf": o["conf"], "box": o["box"], "sides": o["sides"], "faces": o["faces"], "size": o["size"]}
        rows[s["name"]] = {"want": t["indicators"], "cls": files["cls"], **row}
        print(s["name"][-6:], "정답", t["indicators"], " | ".join(
            f"{k}: {v['got']}({v['conf']:.2f}, {'상자 ' + str(min(v['box'][2:])) + 'px' if v['box'] else '상자 없음'}) {v['판정']}" for k, v in row.items()), flush=True)
    print(models, len(rows), "장", score)
    out = ROOT / f"experiments/tile_classifier/data/dora_rounds/resolution_now_{models}.json"
    out.write_text(json.dumps({"_meta": {"models": models, "recognizer": rs.git_sha(), "at": time.strftime("%Y-%m-%d %H:%M:%S")}, "score": score, "scenes": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", out)


if __name__ == "__main__":
    main()
