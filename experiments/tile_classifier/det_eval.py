"""YOLO26n 검출기 + 자체 분류기로 화료자 손패를 Gemini 없이 읽어 표 1-17 과 같은 방식으로 채점한다(2026-11-02, 노트북 CPU, API 없음).

입력: 앱과 같은 자리 크롭(폭 40). 화료자 자리는 기록값을 준다.
틀: A = 서버 st.frame 을 검출기만 바꿔 그대로(모자이크, 운영 검사), B = 크롭 통째 검출 + st.structure_split + 운영 검사. A 를 먼저, 안 되면 B.
모델: 시험 사진을 학습에 안 쓴 것만. 검출기 오후·B·C·D = fold_a, 오전 = fold_b. 분류기는 그 시간대를 뺀 라벨로 학습(B·C·D 는 겹침 기록도 뺌), data/cls_<부분>.pt 로 저장.
자동 = 틀 + 장수·텐파이/화료형 검사 통과. YOLO 먼저 = 자동 아니면 저장된 Gemini 폭 40 으로 넘김(hybrid_replay.py 와 같은 계산).
  python -I experiments/tile_classifier/det_eval.py [--strict] [--r2|--r3]
결과 data/det/eval.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "yolo"))
sys.path.insert(0, str(HERE.parent / "speed"))
import harvest as hv  # noqa: E402
import hybrid as hy  # noqa: E402
import hybrid_replay as hr  # noqa: E402
import review as rw  # noqa: E402
import seat_grow as sg  # noqa: E402
import train as tr  # noqa: E402
from harvest import rv, st  # noqa: E402

DATA = HERE / "data"
OUT = DATA / "det" / ("kaggle_out_r3" if "--r3" in sys.argv else "kaggle_out_r2" if "--r2" in sys.argv else "kaggle_out") / "out"  # --r2 = 2회차, --r3 = 3회차(白 증강) 검출기
RELAX = "--strict" not in sys.argv  # --strict = 운영 모양 검사까지(A 또는 B)


class Det:
    """st.frame 이 부르는 detect 를 YOLO26 으로. 패 종류는 안 쓴다."""

    def __init__(self, path: Path, conf: float = 0.25):
        self.model = YOLO(str(path), task="detect")
        self.conf = conf

    def detect(self, rgb: np.ndarray, low: bool = False) -> list[tuple[int, int, int, int]]:
        r = self.model.predict(rgb[:, :, ::-1], imgsz=1280, conf=self.conf, verbose=False, device="cpu")[0]
        return [(int(x0), int(y0), int(x1 - x0), int(y1 - y0)) for x0, y0, x1, y1 in r.boxes.xyxy.tolist() if x1 - x0 >= 2 and y1 - y0 >= 2]


def classifiers(base: list[dict], add: list[dict]) -> dict:
    nets = {}
    images = None
    for part in ("bcd", "am", "pm"):
        f = DATA / f"cls_{part}.pt"
        net = tr.torchvision.models.mobilenet_v3_small()
        net.classifier[3] = tr.nn.Linear(net.classifier[3].in_features, len(tr.CLASSES))
        if f.exists():
            net.load_state_dict(torch.load(f, map_location="cpu", weights_only=True))
            nets[part] = net.eval()
            continue
        if images is None:
            images = {x["file"]: tr.square(Image.open(DATA / "crops" / x["file"]).convert("RGB")) for x in base}
            images.update({x["file"]: tr.square(Image.open(x["path"]).convert("RGB")) for x in add})
        pool = [x for x in base if x["part"] != part] + [x for x in add if x["half"] != part and (part != "bcd" or x["half"] != "other")]
        trained = tr.train(pool, images, 0)
        torch.save(trained.state_dict(), f)
        nets[part] = trained
        print("분류기", part, len(pool), flush=True)
    return nets


def frames(rgb: np.ndarray, det: Det, frac: float):
    a = st.frame(rgb, det, hand_frac=frac)
    faces = rv.dedupe(rv.keep_faces(det.detect(rgb), rv.white_mask(rgb)))
    b = st.structure_split(rgb, faces, int(rgb.shape[1] * frac)) if faces else None
    b = b if b is not None and st.valid(b) and st.safe_ok(b, rgb) else None
    return a, b


def read(net, rgb: np.ndarray, fr) -> tuple[list[str], list[str]]:
    def upright(b) -> str:  # 자리 크롭은 이미 그 사람 쪽으로 세웠다. 뒤집어 보면 三 을 二 로 읽는다(k15·k26)
        with torch.no_grad():
            return tr.CLASSES[net(tr.PLAIN(tr.square(hv.cut(rgb, b))).unsqueeze(0)).argmax(1).item()]

    def one(b) -> str:  # 울기는 눕힌 패가 있어 방향을 고른다
        return hv.label(net, hv.cut(rgb, b), b[2], b[3])[0] if b[2] > 1.15 * b[3] else upright(b)
    hand = [upright(b) for b in fr.hand] + ([upright(fr.separate)] if fr.separate else [])
    return hand, [" ".join(one(b) for b in m) for m in fr.melds]


def relaxed(net, rgb: np.ndarray, det: Det, frac: float):
    """C = 운영 모양 검사(safe_ok, YOLO11 상자의 흔들림을 막으려고 만든 값)를 빼고, 장수·패 모양 검사로만. 울기 후보가 넘치면
    (k12 의 표시패 묶음) 울기 묶음 중 장수·텐파이/화료형을 맞추는 조합이 하나일 때만 받는다."""
    faces = rv.dedupe(rv.keep_faces(det.detect(rgb), rv.white_mask(rgb)))
    fr = st.structure_split(rgb, faces, int(rgb.shape[1] * frac)) if faces else None
    if fr is None:
        return [], []
    hand, melds = read(net, rgb, fr)
    fits = []
    for mask in range(1 << len(melds)):
        ms = [m for i, m in enumerate(melds) if mask >> i & 1]
        if hy.check(hand, [m.split() for m in ms])[0]:
            fits.append(ms)
    return (hand, fits[0]) if len(fits) == 1 else (hand, melds)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    base = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    nets = classifiers(base, rw.extra())
    dets = {"a": Det(OUT / "fold_a.pt"), "b": Det(OUT / "fold_b.pt")}
    gem = {}
    for g in json.loads(sg.OUT.read_text(encoding="utf-8")):
        gem.setdefault(g["name"], []).append(g["by_grow"].get("40") or {})
    rows = []
    for s in sg.eval_scenes():
        if s["hand"] is None:
            continue
        name = s["name"]
        part = "bcd" if not name.startswith("2026") else "am" if name < "20261031_14" else "pm"
        im = Image.open(s["path"]).convert("RGB")
        rgb = np.asarray(sg.crop(im, sg.seat_box(s["grid"], s["side"], 40), s["side"]))
        t0 = time.perf_counter()
        det = dets["b" if part == "am" else "a"]
        frac = sg.hand_frac(s["grid"], s["side"])
        a, b = frames(rgb, det, frac)
        fr = a or b
        hand, melds = read(nets[part], rgb, fr) if fr else ([], [])
        if RELAX:
            hand, melds = relaxed(nets[part], rgb, det, frac)
        secs = time.perf_counter() - t0
        y_pass = bool(hand) and hy.check(hand, [m.split() for m in melds])[0]
        y_ok = hr.same(hand, melds, s)
        print(name[-6:], part, "틀", "A" if a else "", "B" if b else "", "검사", y_pass, "맞음", y_ok, f"{secs:.1f}초", "|", " ".join(hand), melds, "" if y_ok else f"| 정답 {' '.join(s['hand'])} {s['melds']}", flush=True)
        for gm in gem.get(name, [{}]):
            g_hand = (gm.get("hand") or "").split() + ([gm["sep"]] if gm.get("sep") else [])
            g_melds = gm.get("melds") or []
            rows.append(dict(name=name, known=True, frame_a=bool(a), frame_b=bool(b), y_pass=y_pass, y_ok=y_ok, y_short=hr.one_short(hand, melds, s), y_s=round(secs, 2),
                             g_pass=bool(g_hand) and bool(gm.get("unanimous")) and hy.check(g_hand, [m.split() for m in g_melds])[0], g_ok=hr.same(g_hand, g_melds, s),
                             g_short=hr.one_short(g_hand, g_melds, s), g_s=gm.get("s"), y_hand=" ".join(hand), y_melds=melds, truth=" ".join(s["hand"]), truth_melds=s["melds"]))
        (DATA / "det" / "eval.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for label, f in hr.SETS + [("전체", lambda n: True)]:
        part = [r for r in rows if f(r["name"])]
        names = {r["name"]: r for r in part}
        print(f"-- {label}: 사진 {len(names)}, 틀 A {sum(r['frame_a'] for r in names.values())} B {sum(r['frame_b'] for r in names.values())} 둘 중 {sum(r['frame_a'] or r['frame_b'] for r in names.values())}")
        for how, n in (("gemini", "Gemini 단독"), ("yolo", "새 검출기 단독"), ("hybrid", "새 검출기 먼저")):
            print(hr.line(n, hr.tally(part, how)))
    print("시간(새 검출기 + 분류기, 노트북 CPU) 중앙", statistics.median(r["y_s"] for r in rows))


if __name__ == "__main__":
    main()
