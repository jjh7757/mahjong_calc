"""공개 YOLO 마작 모델을 우리 사진에 CPU 로 돌려 채점한다(2026-10-26).

모델(가중치는 C:/Users/jjh7757/dev/_downloads 에 받아 둠, 저장소에 넣지 않음):
  haselab  HaseLab/mahjong-models (2026-07-31): 패 면 YOLO26n 세그(1클래스) → 네 꼭짓점 투시 변환 224 → ResNet-50 39클래스
  nikmomo  nikmomo/Mahjong-YOLO (YOLO11 s/m, ONNX, MIT): 37클래스 검출. 휴대폰으로 찍은 손패 사진(Kaggle)으로 학습

세트:
  hand   위에서 찍은 눕힌 손패 3장(vlm/samples_real2, samples_real_crop) — Gemini 3.8 Flash 3/3 전부 정답
  seat   거치 5구역의 화료자 자리 크롭 10장(field_20261024/grid5_scenes, 장면 A~E × 사진 2) — Gemini 자리 판독과 같은 입력

채점: 정답과 예측의 다중집합 교집합(맞은 장수), 정답 장수, 예측 장수, 손패 전체 일치 여부.
적도라는 0x 를 5x 와 다르게 센다(loose 열은 같게 셈).

python -I run_yolo.py [--models haselab,nikmomo-s,nikmomo-m] [--sets hand,seat] [--save-vis]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
W = Path("C:/Users/jjh7757/dev/_downloads")

# 정답: tool_loop.py TRUTH(손패 + 울기), vlm labels.json
SEAT_TRUTH = {
    "A": ("hand_top.jpg", "3p 3p 5p 5p 4m 5m 6m 6s 7s 8s 4s 4s 4s 4s"),
    "B": ("hand_right.jpg", "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p 6z 6z 6z"),
    "C": ("hand_left.jpg", "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z"),
    "D": ("hand_bottom.jpg", "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z 6m 7m 8m"),
    "E": ("hand_left.jpg", "1z 1z 1z 7m 8m 9m 1s 2s 3s 7s 8s 7z 7z"),
}
SEAT_PHOTOS = {"A": ["k20", "k24"], "B": ["k25", "k28"], "C": ["k15", "k26"], "D": ["k12", "k16"], "E": ["k00", "k04"]}
# 평가는 B·C·D 만(2026-10-25·26 사용자 결정: 화료패가 사진에 없는 A·E 는 뺀다). A·E 는 기록만 남긴다.
EVAL_SCENES = "BCD"


def expand(code: str) -> list[str]:
    """'19m19p' → ['1m','9m','1p','9p'], 공백 구분 목록도 받는다."""
    if " " in code:
        return code.split()
    out, digits = [], []
    for ch in code:
        if ch.isdigit():
            digits.append(ch)
        else:
            out += [d + ch for d in digits]
            digits = []
    return out


def hand_items():
    for folder in ("samples_real2", "samples_real_crop"):
        labels = json.loads((EXP / "vlm" / folder / "labels.json").read_text(encoding="utf-8"))
        for name, code in labels.items():
            yield f"hand/{name}", EXP / "vlm" / folder / name, expand(code)


def seat_items():
    for scene, (crop, truth) in SEAT_TRUTH.items():
        if scene not in EVAL_SCENES:
            continue
        for p in SEAT_PHOTOS[scene]:
            yield f"seat/{scene}/{p}", EXP / "field_20261024" / "grid5_scenes" / scene / f"{p}_1" / crop, truth.split()


WINNER_SIDE = {"A": "top", "B": "right", "C": "left", "D": "bottom", "E": "left"}


def table_items():
    """전경 원본(4000×3000). 정답은 seat 세트와 같은 화료자 손패 + 울기."""
    for scene, (_, truth) in SEAT_TRUTH.items():
        if scene not in EVAL_SCENES:
            continue
        for p in SEAT_PHOTOS[scene]:
            yield f"table/{scene}/{p}", EXP / "field_20261024" / "kakao_photos" / f"{p}.jpg", truth.split()


def imread(path: Path) -> np.ndarray:
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)


# ---------------------------------------------------------------- HaseLab
HASE_CLASSES = ["0m", "0p", "0s", "0z", "1m", "1p", "1s", "1z", "2m", "2p", "2s", "2z", "3m", "3p", "3s", "3z",
                "4m", "4p", "4s", "4z", "5m", "5p", "5s", "5z", "6m", "6p", "6s", "6z", "7m", "7p", "7s", "7z",
                "8m", "8p", "8s", "9m", "9p", "9s", "back"]


class HaseLab:
    name = "haselab"

    def __init__(self):
        import torch
        import torchvision
        from ultralytics import YOLO

        self.torch = torch
        self.tile = YOLO(str(W / "haselab" / "tile-yolo-26n.pt"))
        net = torchvision.models.resnet50()
        net.fc = torch.nn.Linear(net.fc.in_features, len(HASE_CLASSES))
        # 체크포인트는 {model: timm resnet50 state_dict, classes, val_accuracy 0.981, ...}. timm 키 이름이 torchvision 과 같다.
        ck = torch.load(W / "haselab" / "classifier-resnet50.pt", map_location="cpu", weights_only=True)
        assert ck["classes"] == HASE_CLASSES
        net.load_state_dict(ck["model"])
        self.net = net.eval()
        self.mean = np.array([0.485, 0.456, 0.406], np.float32)
        self.std = np.array([0.229, 0.224, 0.225], np.float32)

    @staticmethod
    def corners(poly: np.ndarray) -> np.ndarray:
        """세그 다각형 → 네 꼭짓점(좌상·우상·우하·좌하). 최소 외접 사각형."""
        box = cv2.boxPoints(cv2.minAreaRect(poly.astype(np.float32)))
        s, d = box.sum(1), np.diff(box, axis=1)[:, 0]
        return np.array([box[s.argmin()], box[d.argmin()], box[s.argmax()], box[d.argmax()]], np.float32)

    def predict(self, img: np.ndarray, conf: float = 0.25, imgsz: int = 1024, cls_min: float = 0.3):
        """패 면 세그 → 분류. 분류 확신도가 [cls_min] 보다 낮은 것(펠트·패산 옆면을 白 으로 읽는 것)은 버린다."""
        r = self.tile.predict(img, conf=conf, imgsz=imgsz, verbose=False, retina_masks=True)[0]
        if r.masks is None:
            return [], []
        polys = r.masks.xy
        crops, centers, sizes = [], [], []
        dst = np.array([[0, 0], [223, 0], [223, 223], [0, 223]], np.float32)
        for poly in polys:
            if len(poly) < 4:
                continue
            c = self.corners(poly)
            # 패는 세로로 긴데 정사각형으로 펴는 것이 README 방식. 가로로 누운 패면 세로가 되게 돌린다.
            w = np.linalg.norm(c[1] - c[0]); h = np.linalg.norm(c[3] - c[0])
            if w > h * 1.15:
                c = np.roll(c, -1, axis=0)  # 90° 회전(위쪽 방향은 모름: 모델이 회전에 강한지 본다)
            m = cv2.getPerspectiveTransform(c, dst)
            crops.append(cv2.warpPerspective(img, m, (224, 224)))
            centers.append(poly.mean(0))
            sizes.append(float(min(w, h)))
        if not crops:
            return [], []
        x = np.stack([cv2.cvtColor(c, cv2.COLOR_BGR2RGB).astype(np.float32) / 255 for c in crops])
        x = (x - self.mean) / self.std
        with self.torch.no_grad():
            p = self.torch.softmax(self.net(self.torch.from_numpy(x.transpose(0, 3, 1, 2)).float()), 1).numpy()
        labels = [HASE_CLASSES[i] for i in p.argmax(1)]
        confs = p.max(1).tolist()
        keep = [i for i, c in enumerate(confs) if c >= cls_min]
        return [(labels[i], confs[i], centers[i], sizes[i]) for i in keep], [crops[i] for i in keep]

    def predict_table(self, full: np.ndarray, winner: str, region_imgsz: int = 1280, tile_imgsz: int = 1024):
        """README 파이프라인: 전경 → 구역 YOLO → self_hand·meld_0 구역 → 패 YOLO → 분류.
        구역 모델은 카메라 쪽 손패(self_hand)만 따로 안다 → 화료자가 아래에 오게 사진을 돌린다."""
        rot = {"bottom": None, "right": cv2.ROTATE_90_CLOCKWISE, "left": cv2.ROTATE_90_COUNTERCLOCKWISE, "top": cv2.ROTATE_180}[winner]
        img = full if rot is None else cv2.rotate(full, rot)
        if not hasattr(self, "region"):
            from ultralytics import YOLO
            self.region = YOLO(str(W / "haselab" / "regions-yolo-26n.pt"))
        r = self.region.predict(img, conf=0.25, imgsz=region_imgsz, verbose=False)[0]
        dets, crops, found = [], [], []
        H, Wd = img.shape[:2]
        for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
            name = self.region.names[int(c)]
            if name not in ("self_hand", "meld_0"):
                continue
            x0, y0, x1, y1 = b.numpy()
            px, py = (x1 - x0) * 0.08, (y1 - y0) * 0.15
            x0, y0, x1, y1 = int(max(0, x0 - px)), int(max(0, y0 - py)), int(min(Wd, x1 + px)), int(min(H, y1 + py))
            found.append(f"{name}:{float(p):.2f}")
            d, cr = self.predict(img[y0:y1, x0:x1], imgsz=tile_imgsz)
            dets += [(lab, cf, ctr + np.array([x0, y0]), sz) for lab, cf, ctr, sz in d]
            crops += cr
        return dets, crops, found


# ---------------------------------------------------------------- nikmomo (ONNX)
class Nikmomo:
    CLASSES = ["1m", "1p", "1s", "1z", "2m", "2p", "2s", "2z", "3m", "3p", "3s", "3z", "4m", "4p", "4s", "4z",
               "5m", "5p", "5s", "5z", "6m", "6p", "6s", "6z", "7m", "7p", "7s", "7z", "8m", "8p", "8s",
               "9m", "9p", "9s", "0m", "0p", "0s"]

    def __init__(self, size: str):
        from ultralytics import YOLO

        self.name = f"nikmomo-{size}"
        self.model = YOLO(str(W / "nikmomo" / f"mahjong-yolo{size}-best.onnx"), task="detect")

    def predict(self, img: np.ndarray, conf: float = 0.25, imgsz: int = 640):
        r = self.model.predict(img, conf=conf, imgsz=imgsz, verbose=False)[0]
        out = []
        for b in r.boxes:
            xyxy = b.xyxy[0].numpy()
            out.append((self.CLASSES[int(b.cls)], float(b.conf), np.array([(xyxy[0] + xyxy[2]) / 2, (xyxy[1] + xyxy[3]) / 2])))
        return out, []


def score(pred: list[str], truth: list[str]):
    loose = lambda xs: Counter(("5" + t[1]) if t[0] == "0" else t for t in xs)
    hit = sum((Counter(pred) & Counter(truth)).values())
    hit_loose = sum((loose(pred) & loose(truth)).values())
    return hit, hit_loose, Counter(pred) == Counter(truth)


def dedupe(items):
    """겹친 세그(같은 패를 두 번 찾음)를 하나로: 중심 거리가 가까운 쌍은 확신도 높은 쪽만 남긴다.
    기준 거리는 패 짧은 변의 절반(HaseLab 세그가 크기를 줌). 크기가 없으면 최근접 거리 중앙값의 절반."""
    if len(items) < 2:
        return items
    pts = np.array([t[2] for t in items])
    d = np.linalg.norm(pts[:, None] - pts[None], axis=2)
    np.fill_diagonal(d, np.inf)
    thr = np.median([t[3] for t in items]) * 0.5 if len(items[0]) > 3 else np.median(d.min(1)) * 0.5
    keep = []
    for i in sorted(range(len(items)), key=lambda i: -items[i][1]):
        if all(np.linalg.norm(pts[i] - pts[j]) >= thr for j in keep):
            keep.append(i)
    return [items[i] for i in sorted(keep)]


def order(items, horizontal: bool):
    """손패 순서대로 보기 좋게: 가로 줄이면 x, 세로 줄이면 y 기준."""
    k = 0 if horizontal else 1
    return sorted(items, key=lambda t: t[2][k])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="haselab,nikmomo-s,nikmomo-m")
    ap.add_argument("--sets", default="hand,seat")
    ap.add_argument("--save-vis", action="store_true")
    ap.add_argument("--dedupe", action="store_true")
    ap.add_argument("--hase-imgsz", type=int, default=1600)  # 자리 크롭(2000~3000px)은 1024 이하에서 패를 거의 못 찾음
    a = ap.parse_args()

    models = []
    for m in a.models.split(","):
        models.append(HaseLab() if m == "haselab" else Nikmomo(m.split("-")[1]))
    items = []
    if "hand" in a.sets:
        items += list(hand_items())
    if "seat" in a.sets:
        items += list(seat_items())
    if "table" in a.sets:
        items += list(table_items())

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    rows = []
    for model in models:
        for key, path, truth in items:
            img = imread(path)
            found = []
            if key.startswith("table/"):
                if model.name != "haselab":
                    continue
                run = lambda: model.predict_table(img, WINNER_SIDE[key.split("/")[1]])
            else:
                kw = {"imgsz": a.hase_imgsz} if model.name == "haselab" else {}
                run = lambda: model.predict(img, **kw) + ([],)
            run()  # 첫 호출 준비 시간 빼기
            t0 = time.perf_counter()
            dets, crops, found = run()
            dt = time.perf_counter() - t0
            h, w = img.shape[:2]
            # 전경은 화료자가 아래에 오게 돌려 읽으므로 손패 줄이 늘 가로다
            if a.dedupe:
                dets = dedupe(dets)
            dets = order(dets, horizontal=w >= h or key.startswith("table/"))
            pred = [d[0] for d in dets if d[0] != "back"]
            hit, hit_loose, exact = score(pred, truth)
            rows.append(dict(model=model.name, item=key, truth=len(truth), pred=len(pred), hit=hit, hit_loose=hit_loose,
                             exact=exact, sec=round(dt, 2), read=" ".join(pred), want=" ".join(truth),
                             backs=sum(d[0] == "back" for d in dets), regions=found,
                             low=[f"{d[0]}:{d[1]:.2f}" for d in dets if d[1] < 0.6]))
            print(f"{model.name:10s} {key:22s} 맞음 {hit:2d}/{len(truth):2d} (적5 무시 {hit_loose:2d}) 예측 {len(pred):2d}장"
                  f" {'정답' if exact else '    '} {dt:5.2f}초 | {' '.join(pred)} {' '.join(found)}", flush=True)
            if a.save_vis and not key.startswith("table/"):  # 전경은 돌린 좌표라 패 띠만 남긴다
                vis = img.copy()
                for lab, cf, c in dets:
                    cv2.putText(vis, lab, (int(c[0]) - 20, int(c[1])), cv2.FONT_HERSHEY_SIMPLEX, max(1, w / 1200), (0, 0, 255), max(2, w // 600))
                cv2.imencode(".jpg", vis)[1].tofile(str(out_dir / f"{model.name}_{key.replace('/', '_')}.jpg"))
            if a.save_vis and crops:
                    strip = np.hstack(crops[:20])
                    cv2.imencode(".jpg", strip)[1].tofile(str(out_dir / f"{model.name}_{key.replace('/', '_')}_tiles.jpg"))
    (out_dir / "rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n요약")
    for model in models:
        for s in a.sets.split(","):
            rs = [r for r in rows if r["model"] == model.name and r["item"].startswith(s)]
            if not rs:
                continue
            T = sum(r["truth"] for r in rs)
            print(f"  {model.name:10s} {s:5s} 패 {sum(r['hit'] for r in rs)}/{T} ({100*sum(r['hit'] for r in rs)/T:.0f}%)"
                  f"  틀리거나 남는 패 {sum(r['pred']-r['hit'] for r in rs)}/{sum(r['pred'] for r in rs)}  적5 무시 {sum(r['hit_loose'] for r in rs)}/{T}  손패 전체 정답 {sum(r['exact'] for r in rs)}/{len(rs)}"
                  f"  중앙 {sorted(r['sec'] for r in rs)[len(rs)//2]:.2f}초")


if __name__ == "__main__":
    sys.exit(main())
