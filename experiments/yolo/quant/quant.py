"""YOLO26 구역·패 모델과 ResNet-50 을 int8(정적, QDQ, 채널별 가중치)로 양자화하고 fp32 와 비교한다(2026-10-26).

보정(calibration) 사진은 평가에 안 쓰는 갤러리 A·E(k20·k24·k00·k04), 평가는 B·C·D(사용자 결정).
  구역 모델: A·E 4장 × (그대로 + 90° 회전 4) = 20장
  패 모델: A·E 화료자 손패 구역(구역 모델로 찾음) 크롭 + 거치 5구역 자리 크롭
  ResNet-50: 위 구역에서 fp32 패 모델이 찾은 패 크롭

비교(B·C·D):
  격자     auto_grid 선 4개가 fp32 와 같은가(선 차이)
  구역     5방향 구역 상자: fp32 상자를 int8 이 같은 클래스·IoU≥0.5 로 찾은 비율, 확신도 차
  패       화료자 손패 구역에서 패 상자: 같은 비율(IoU≥0.5), 개수
  분류     같은 패 크롭(fp32 패 모델이 찾은 것)에 ResNet-50 fp32 vs int8 1등 일치율
  끝까지   int8 만으로 구역 → 패 → 분류 한 손패가 정답과 맞은 장수(fp32 와 나란히)

python -I quant.py [--method minmax|percentile] [--skip-quant]
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
import onnxruntime as ort
from onnxruntime.quantization import CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType, quantize_static
from onnxruntime.quantization.shape_inference import quant_pre_process

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "server_bench"))
import bench as B  # noqa: E402  (letterbox·detect·auto_grid 를 서버 측정과 같은 코드로)

B.RECT = True  # 직사각형 입력(동적 ONNX). 정사각형 고정은 가는 손패 크롭에서 패를 못 찾았다.

ONNX = Path("C:/Users/jjh7757/dev/_downloads/onnx")
EXP = HERE.parent.parent
PHOTOS = EXP / "field_20261024" / "kakao_photos"
G5 = EXP / "field_20261024" / "grid5_scenes"
CAL = {"A": (["k20", "k24"], "top", "hand_top.jpg"), "E": (["k00", "k04"], "left", "hand_left.jpg")}
EVAL = {"B": (["k25", "k28"], "right", "hand_right.jpg"), "C": (["k15", "k26"], "left", "hand_left.jpg"),
        "D": (["k12", "k16"], "bottom", "hand_bottom.jpg")}
TRUTH = {"B": "7z 1m 1m 1m 9s 9s 9s 9p 9p 9p 6z 6z 6z", "C": "1z 1z 1z 1m 2m 3m 4m 5m 6m 7m 8m 9m 2z",
         "D": "1m 2m 3m 4m 0m 6m 7m 8m 9m 2z 6m 7m 8m"}
CLASSES = ["0m", "0p", "0s", "0z", "1m", "1p", "1s", "1z", "2m", "2p", "2s", "2z", "3m", "3p", "3s", "3z",
           "4m", "4p", "4s", "4z", "5m", "5p", "5s", "5z", "6m", "6p", "6s", "6z", "7m", "7p", "7s", "7z",
           "8m", "8p", "8s", "9m", "9p", "9s", "back"]


def imread(p: Path):
    return cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)


def sess(p: Path):
    return ort.InferenceSession(str(p), providers=["CPUExecutionProvider"])


def winner_region(region, img, side):
    """화료자가 아래에 오게 돌린 사진과 그 사진의 self_hand + 손패 쪽 meld_0 을 감싼 상자."""
    rot = img if B.ROT[side] is None else cv2.rotate(img, B.ROT[side])
    bx = B.boxes_of(B.detect(region, rot, 1280, 14))
    hand = max(bx.get("self_hand", []), key=lambda q: q[0], default=None)
    if hand is None:
        return rot, None
    disc = max(bx.get("discard_0", []), key=lambda q: q[0], default=None)
    lim = disc[1][3] if disc else rot.shape[0] * 0.6
    hb = hand[1]; hh = hb[3] - hb[1]
    melds = [b for p, b in bx.get("meld_0", []) if p > 0.3 and (b[1] + b[3]) / 2 > lim and b[3] >= hb[1] - 0.5 * hh]
    u = B.union([hb] + melds)
    x0, y0, x1, y1 = [int(v) for v in u]
    return rot, (max(0, x0), max(0, y0), min(rot.shape[1], x1), min(rot.shape[0], y1))


def patches(crop, dets):
    out = []
    for _, _, b in dets:
        x0, y0, x1, y1 = [int(v) for v in b]
        pc = crop[max(0, y0):max(y0 + 1, y1), max(0, x0):max(x0 + 1, x1)]
        out.append(cv2.resize(pc, (224, 224))[:, :, ::-1].astype(np.float32) / 255)
    if not out:
        return np.zeros((0, 3, 224, 224), np.float32)
    x = (np.stack(out) - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    return x.transpose(0, 3, 1, 2).astype(np.float32)


class Reader(CalibrationDataReader):
    def __init__(self, name, arrays):
        self.name, self.it = name, iter(arrays)

    def get_next(self):
        a = next(self.it, None)
        return None if a is None else {self.name: a}


def head_nodes(path: Path) -> list[str]:
    """YOLO 출력층(마지막 모듈)에서 가지 conv 를 뺀 나머지 + 가지의 마지막 1×1 conv: 양자화하지 않는다.
    상자 좌표(0~1280)·확신도(0~1)·마스크 계수가 한 텐서로 합쳐져 한 눈금 int8 이면 확신도가 0 으로 뭉개졌다(첫 시도 0/152)."""
    import re
    import onnx
    names = [n.name for n in onnx.load(str(path)).graph.node]
    mods = [int(m.group(1)) for n in names if (m := re.match(r"/model\.(\d+)/", n))]
    if not mods:
        return []
    last = max(mods)
    pre = f"/model.{last}/"
    return [n for n in names if n.startswith(pre) and (not re.match(rf"{re.escape(pre)}(cv\d\.\d+|proto)/", n)
                                                         or re.search(r"cv\d\.\d\.2/", n))]


def quantize(src: Path, dst: Path, input_name: str, arrays, method):
    pre = dst.with_suffix(".pre.onnx")
    quant_pre_process(str(src), str(pre), skip_symbolic_shape=True)
    quantize_static(str(pre), str(dst), Reader(input_name, arrays), quant_format=QuantFormat.QDQ, per_channel=True,
                    nodes_to_exclude=head_nodes(src),
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8,
                    calibrate_method=CalibrationMethod.Percentile if method == "percentile" else CalibrationMethod.MinMax)
    pre.unlink(missing_ok=True)


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
    return ix * iy / u if u > 0 else 0


def match(ref, got, by_class=True):
    """ref 상자 중 got 이 IoU≥0.5(같은 클래스) 로 찾은 비율, 그때 확신도 차 평균."""
    hit, dconf = 0, []
    used = set()
    for c, p, b in ref:
        best, bj = 0, None
        for j, (c2, p2, b2) in enumerate(got):
            if j in used or (by_class and c2 != c):
                continue
            v = iou(b, b2)
            if v > best:
                best, bj = v, j
        if best >= 0.5:
            hit += 1; used.add(bj); dconf.append(abs(p - got[bj][1]))
    return hit, len(ref), (float(np.mean(dconf)) if dconf else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="minmax")
    ap.add_argument("--skip-quant", action="store_true")
    ap.add_argument("--quant", default="region,tile,cls", help="int8 로 바꿀 모델(나머지는 fp32 그대로)")
    ap.add_argument("--extra-cal", type=int, default=0, help="구역 모델 보정에 더할 매장 거치 사진 수")
    ap.add_argument("--tag", default="", help="int8 파일 이름 꼬리표")
    a = ap.parse_args()
    out = HERE / "models"  # 끝나면 C:/Users/jjh7757/dev/_downloads/onnx/int8/ 로 옮겨 둠(저장소 밖)
    out.mkdir(exist_ok=True)
    f32 = {k: ONNX / f for k, f in (("region", "regions-yolo-26n-dyn.onnx"), ("tile", "tile-yolo-26n-dyn.onnx"), ("cls", "classifier-resnet50.onnx"))}
    qset = set(a.quant.split(","))
    i8 = {k: (out / v.name.replace(".onnx", f".int8-{a.method}{a.tag}.onnx") if k in qset else v) for k, v in f32.items()}
    s32 = {k: sess(v) for k, v in f32.items()}

    if not a.skip_quant:
        # ---- 보정 데이터(A·E)
        reg_cal, tile_cal, cls_cal = [], [], []
        # percentile 보정은 입력 크기가 섞이면 동작하지 않는다(onnxruntime) → 보정 입력만 정사각형으로
        B.RECT = a.method != "percentile"
        for s, (ps, side, crop_name) in CAL.items():
            for p in ps:
                img = imread(PHOTOS / f"{p}.jpg")
                for rot in B.ROT.values():
                    im = img if rot is None else cv2.rotate(img, rot)
                    reg_cal.append(B.letterbox(im, 1280)[0])
                rimg, box = winner_region(s32["region"], img, side)
                crops = [imread(G5 / s / f"{p}_1" / crop_name)]
                if box:
                    crops.append(rimg[box[1]:box[3], box[0]:box[2]])
                for c in crops:
                    tile_cal.append(B.letterbox(c, 1024)[0])
                    dets = B.detect(s32["tile"], c, 1024, 1)
                    cls_cal += list(patches(c, dets)[:, None])
        # 구역 모델 보정에 평가 밖 매장 거치 사진(10/24 카메라 헤드)을 더한다: A·E 4장만으로는 B 왼쪽 선이 41 어긋났다
        if a.extra_cal:
            caps = sorted((EXP / "field_20261024" / "captures").glob("20261024_*/original.jpg"))[:a.extra_cal]
            for cp in caps:
                img = imread(cp)
                for rot in B.ROT.values():
                    im = img if rot is None else cv2.rotate(img, rot)
                    reg_cal.append(B.letterbox(im, 1280)[0])
        B.RECT = True
        print(f"보정: 구역 {len(reg_cal)}장, 패 {len(tile_cal)}장, 분류 {len(cls_cal)}장", flush=True)
        for k, arr, name in (("region", reg_cal, "images"), ("tile", tile_cal, "images"), ("cls", cls_cal, "x")):
            if k not in qset or i8[k].exists():
                continue
            t = time.perf_counter()
            quantize(f32[k], i8[k], name, arr, a.method)
            print(f"  {k}: {f32[k].stat().st_size / 2**20:.1f}MB → {i8[k].stat().st_size / 2**20:.1f}MB ({time.perf_counter() - t:.0f}초)", flush=True)

    s8 = {k: sess(v) for k, v in i8.items()}
    auto = json.loads((HERE.parent / "results" / "auto_grid" / "auto_grid.json").read_text(encoding="utf-8"))
    rep = dict(method=a.method, quant=sorted(qset), grid=[], region=[0, 0, []], tile=[0, 0, []], cls=[0, 0], hand={"fp32": [0, 0], "int8": [0, 0]}, pc_time={})
    t_reg = {"fp32": [], "int8": []}; t_tile = {"fp32": [], "int8": []}; t_cls = {"fp32": [], "int8": []}
    for s, (ps, side, crop_name) in EVAL.items():
        for p in ps:
            img = imread(PHOTOS / f"{p}.jpg")
            g32 = B.auto_grid(s32["region"], img, [])
            tt = []
            g8 = B.auto_grid(s8["region"], img, tt)
            diff = {k: g8[k] - g32[k] for k in g32} if g8 and g32 else None
            rep["grid"].append(dict(photo=f"{s}/{p}", fp32=g32, int8=g8, diff=diff))
            # 구역 상자 5방향
            for rot in B.ROT.values():
                im = img if rot is None else cv2.rotate(img, rot)
                t = time.perf_counter(); r32 = B.detect(s32["region"], im, 1280, 14); t_reg["fp32"].append(time.perf_counter() - t)
                t = time.perf_counter(); r8 = B.detect(s8["region"], im, 1280, 14); t_reg["int8"].append(time.perf_counter() - t)
                h, n, dc = match(r32, r8)
                rep["region"][0] += h; rep["region"][1] += n; rep["region"][2].append(dc)
            # 화료자 손패 구역의 패 + 분류
            rimg, box = winner_region(s32["region"], img, side)
            if not box:
                continue
            crop = rimg[box[1]:box[3], box[0]:box[2]]
            t = time.perf_counter(); d32 = B.detect(s32["tile"], crop, 1024, 1); t_tile["fp32"].append(time.perf_counter() - t)
            t = time.perf_counter(); d8 = B.detect(s8["tile"], crop, 1024, 1); t_tile["int8"].append(time.perf_counter() - t)
            h, n, dc = match(d32, d8, by_class=False)
            rep["tile"][0] += h; rep["tile"][1] += n; rep["tile"][2].append(dc)
            x = patches(crop, d32)
            if len(x):
                t = time.perf_counter(); y32 = s32["cls"].run(None, {"x": x})[0]; t_cls["fp32"].append(time.perf_counter() - t)
                t = time.perf_counter(); y8 = s8["cls"].run(None, {"x": x})[0]; t_cls["int8"].append(time.perf_counter() - t)
                rep["cls"][0] += int((y32.argmax(1) == y8.argmax(1)).sum()); rep["cls"][1] += len(x)
            # 끝까지(각자 자기 모델로): 구역 → 패 → 분류, 확신도 0.3 미만·back 은 버림 → 정답과 다중집합 교집합
            for key, ss in (("fp32", s32), ("int8", s8)):
                ri, bb = winner_region(ss["region"], img, side)
                if not bb:
                    continue
                c2 = ri[bb[1]:bb[3], bb[0]:bb[2]]
                dd = B.detect(ss["tile"], c2, 1024, 1)
                xx = patches(c2, dd)
                labels = []
                if len(xx):
                    pr = ss["cls"].run(None, {"x": xx})[0]
                    e = np.exp(pr - pr.max(1, keepdims=True)); pr = e / e.sum(1, keepdims=True)
                    labels = [CLASSES[i] for i, c in zip(pr.argmax(1), pr.max(1)) if c >= 0.3 and CLASSES[i] != "back"]
                want = TRUTH[s].split()
                rep["hand"][key][0] += sum((Counter(labels) & Counter(want)).values()); rep["hand"][key][1] += len(want)
            print(f"{s}/{p}: 격자 차 {diff}", flush=True)

    med = lambda v: round(float(np.median(v)), 3) if v else None  # noqa: E731
    rep["pc_time"] = {k: {"region": med(t_reg[k]), "tile": med(t_tile[k]), "cls_batch": med(t_cls[k])} for k in ("fp32", "int8")}
    rep["region_match"] = f"{rep['region'][0]}/{rep['region'][1]}"; rep["region_dconf"] = round(float(np.mean(rep["region"][2])), 3)
    rep["tile_match"] = f"{rep['tile'][0]}/{rep['tile'][1]}"; rep["tile_dconf"] = round(float(np.mean(rep["tile"][2])), 3)
    rep["cls_agree"] = f"{rep['cls'][0]}/{rep['cls'][1]}"
    rep["grid_same"] = sum(1 for g in rep["grid"] if g["diff"] and all(v == 0 for v in g["diff"].values()))
    rep["grid_maxdiff"] = max((max(abs(v) for v in g["diff"].values()) for g in rep["grid"] if g["diff"]), default=None)
    for k in ("region", "tile", "cls"):
        rep.pop(k)
    (HERE / f"quant_{a.method}{a.tag}_{'-'.join(sorted(qset))}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SUMMARY " + json.dumps({k: v for k, v in rep.items() if k != "grid"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
