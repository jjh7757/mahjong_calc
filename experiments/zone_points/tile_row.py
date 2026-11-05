"""펠트 없이 패 상자만으로 화료자 손패 줄을 찾을 수 있나. 사진 통째 검출 → 가장 긴 곧은 사슬 → 나머지 패 중앙값 기준 자리.
  python tile_row.py <출력 폴더> [r2|fb|fb2]
r2 = 앞면 1종 2회차(fold_a·fold_b), fb = 앞면·뒷면 2종 1차(kaggle_out_fb, 오전 fold_am·오후 fold_pm·k fold_k, 다른 탁자 final), fb2 = 같은 2종 2차 라벨(kaggle_out_fb2). 손패 줄은 앞면만 쓴다."""
import json, sys, glob
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from ultralytics import YOLO

ROOT = Path(r"C:\Users\jjh7757\dev\mahjong_calc\experiments")
sys.path.insert(0, str(ROOT / "speed"))
sys.path.insert(0, str(ROOT / "tile_classifier"))
sys.path.insert(0, str(ROOT / "yolo"))
import seat_grow as sg

OUT = Path(sys.argv[1])
FB = len(sys.argv) > 2 and sys.argv[2] in ("fb", "fb2")
if FB:
    DIR = ROOT / "tile_classifier/data/det" / ("kaggle_out_fb2" if sys.argv[2] == "fb2" else "kaggle_out_fb") / "out"
    M = {k: YOLO(str(DIR / f"{v}.pt"), task="detect") for k, v in (("am", "fold_am"), ("pm", "fold_pm"), ("k", "fold_k"), ("other", "final"))}
else:
    DIR = sorted(glob.glob(str(ROOT / "tile_classifier/data/det/kaggle_out_r2/**/fold_a.pt"), recursive=True))
    DIR = Path(DIR[0]).parent if DIR else ROOT / "tile_classifier/data/det/kaggle_out/out"
    A, B = YOLO(str(DIR / "fold_a.pt"), task="detect"), YOLO(str(DIR / "fold_b.pt"), task="detect")
    M = {"am": B, "pm": A, "k": A, "other": A}
print("model", DIR)
BACKS = {}  # 그림용 뒷면 상자


def detect(model, im, conf=0.25):
    r = model.predict(np.asarray(im)[:, :, ::-1], imgsz=1280, conf=conf, verbose=False, device="cpu")[0]
    b = np.array(r.boxes.xyxy.tolist()).reshape(-1, 4)
    cls = np.array(r.boxes.cls.tolist(), int)
    BACKS["last"] = b[cls == 1]
    return b[cls == 0]


def longest_chain(b):
    c = (b[:, :2] + b[:, 2:]) / 2
    wh = b[:, 2:] - b[:, :2]
    s = np.median(np.minimum(wh[:, 0], wh[:, 1])) if len(b) else 0
    best = []
    for i in range(len(b)):
        for j in range(i + 1, len(b)):
            d = c[j] - c[i]
            L = np.hypot(*d)
            if L < 1e-6 or L > s * 8:
                continue
            u = d / L
            n = np.array([-u[1], u[0]])
            off = np.abs((c - c[i]) @ n)
            idx = np.where(off < 0.35 * s)[0]
            if len(idx) <= len(best):
                continue
            order = idx[np.argsort((c[idx] - c[i]) @ u)]
            t = (c[order] - c[i]) @ u
            run, cur = [order[0]], [order[0]]
            for k in range(1, len(order)):
                if t[k] - t[k - 1] < 2.0 * s:
                    cur.append(order[k])
                else:
                    cur = [order[k]]
                if len(cur) > len(run):
                    run = list(cur)
            if len(run) > len(best):
                best = run
    return best, s


def side_of(c, row):
    rest = np.delete(c, row, axis=0)
    if not len(rest):
        return None, None
    m = np.median(rest, axis=0)
    v = c[row].mean(axis=0) - m
    return ("right" if v[0] > 0 else "left") if abs(v[0]) > abs(v[1]) else ("bottom" if v[1] > 0 else "top"), m


def draw(im, b, row, name):
    im = im.copy()
    im.thumbnail((1400, 1400))
    k = im.width / W
    dr = ImageDraw.Draw(im)
    for x in BACKS.get("last", []):
        dr.rectangle([v * k for v in x], outline=(60, 140, 255), width=1)
    for i, x in enumerate(b):
        dr.rectangle([v * k for v in x], outline=(255, 40, 40) if i in row else (255, 230, 0), width=3 if i in row else 1)
    im.save(OUT / f"{name}.jpg", quality=85)


labels = json.loads((ROOT / "tile_classifier/data/zone_points/labels.json").read_text(encoding="utf-8"))
rows = []
for s in sg.eval_scenes():
    if s["hand"] is None:
        continue
    n = s["name"]
    am = n.startswith("2026") and n < "20261031_14"
    im = Image.open(s["path"]).convert("RGB")
    W, H = im.size
    b = detect(M["k" if not n.startswith("2026") else "am" if am else "pm"], im)
    row, ts = longest_chain(b)
    c = (b[:, :2] + b[:, 2:]) / 2
    side, m = side_of(c, row)
    closed = len(s["hand"])
    dev = None
    key = n if n in labels else None
    if key and labels[key].get("device"):
        d = np.array(labels[key]["device"]).mean(axis=0) * [W, H]
        dev = float(np.hypot(*(d - m)) / ts) if m is not None else None
    rows.append(dict(name=n, part="bcd" if not n.startswith("2026") else "am" if am else "pm", det=len(b), row=len(row), closed=closed, side=side, truth=s["side"],
                     ok_side=side == s["side"], near=abs(len(row) - closed) <= 1, center_err=dev))
    print(n, "det", len(b), "row", len(row), "closed", closed, "side", side, s["side"], "centerErr", None if dev is None else round(dev, 1), flush=True)
    draw(im, b, row, n)

print("== 평가 장면", len(rows))
for p in ("bcd", "am", "pm", None):
    r = [x for x in rows if p is None or x["part"] == p]
    if r:
        ce = [x["center_err"] for x in r if x["center_err"] is not None]
        print(p or "all", len(r), "자리 맞음", sum(x["ok_side"] for x in r), "자리+장수±1", sum(x["ok_side"] and x["near"] for x in r), "장수 정확", sum(x["ok_side"] and x["row"] == x["closed"] for x in r),
              "가운데 오차(패폭) 중앙", round(float(np.median(ce)), 1) if ce else None, "최대", round(max(ce), 1) if ce else None)
(OUT / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

print("== 다른 탁자")
for rel in ("vlm/samples_real/table1.jpg", "vlm/samples_real/table2.jpg", "vlm/samples_phone/phone_shot1.jpg", "vlm/samples_broadcast/full.jpg",
            "vlm/samples_real2/chuuren.jpg", "vlm/samples_real2/kokushi.jpg", "vlm/samples_real_crop/discards_center.jpg", "vlm/samples_real_crop/hand_right.jpg"):
    im = Image.open(ROOT / rel).convert("RGB")
    W, H = im.size
    for label, conf in (("0.25", 0.25), ("0.10", 0.10)):
        b = detect(M["other"], im, conf)
        row, ts = longest_chain(b)
        c = (b[:, :2] + b[:, 2:]) / 2
        side, m = side_of(c, row)
        print(rel, "conf", label, "det", len(b), "back", len(BACKS["last"]), "row", len(row), "side", side, flush=True)
        if label == "0.25":
            draw(im, b, row, "other_" + Path(rel).stem)
