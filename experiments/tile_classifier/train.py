"""패 크롭 분류기 기준값(2026-11-01, 노트북 CPU). build_crops.py 다음에.

모델: torchvision MobileNetV3 Small(ImageNet 사전학습) 37종. 나누기 두 가지:
  세트 분리  B·C·D / 매장 오전 / 매장 오후 중 하나를 빼고 학습, 3 시드
  장면 분리  장면 하나(같은 손패의 사진은 함께)를 빼고 학습, 1 시드 — 같은 날 사진이 학습에 있어 낙관적
비교(학습 없음, 같은 크롭): YOLO11 s(운영 모델)의 패 종류 출력, HaseLab ResNet-50(로컬 실험만).
채점: 패 단위, 사진 단위(라벨된 패가 전부 맞음). 학습에 없는 종류의 패는 따로 센다.
  python -I experiments/tile_classifier/train.py [--base]
결과 experiments/tile_classifier/data/results.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image
from torch import nn
from torchvision import transforms as T

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CROPS = DATA / "crops"
sys.path.insert(0, str(HERE.parents[0] / "yolo"))
sys.path.insert(0, r"C:\Users\jjh7757\dev\mahjong-recognizer")

CLASSES = [f"{n}{s}" for s in "mps" for n in range(1, 10)] + ["0m", "0p", "0s"] + [f"{n}z" for n in range(1, 8)]
SIZE = int(__import__("os").environ.get("CLS_SIZE", "128"))  # 2026-11-10 해상도 실험: 서버 local_read.CLS_SIZE 와 같게(experiments/speed/imgsz_run.py)
EPOCHS = 40
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
SAME_HAND = {"k25": "B", "k28": "B", "k15": "C", "k26": "C", "k12": "D", "k16": "D"}


def square(im: Image.Image, size: int = SIZE) -> Image.Image:
    im = im.copy()
    im.thumbnail((size, size))
    out = Image.new("RGB", (size, size), (114, 114, 114))
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


AUG = T.Compose([T.RandomAffine(8, translate=(0.06, 0.06), scale=(0.9, 1.1), fill=114), T.ColorJitter(0.25, 0.25, 0.2, 0.02),
                 T.RandomApply([T.GaussianBlur(3, (0.3, 1.2))], 0.3), T.ToTensor(), T.Normalize(MEAN, STD)])
PLAIN = T.Compose([T.ToTensor(), T.Normalize(MEAN, STD)])

# 7-1(2026-11-06): 세운 크롭(harvest.py --obb) 용 증강. 입력은 정사각형으로 만들기 전 원래 크기 크롭 —
# JPEG 품질 지터는 서버가 받는 사진처럼 패 해상도에서(128 로 줄이기 전), 180° 회전은 강 끝 거꾸로 놓인 패(90° 는 서버가 돌려 읽으므로 안 넣음),
# ±8° 회전·밝기·대비·흐림은 AUG 그대로, 색상 지터 0.02 그대로(빨강 보존), 채도 지터 OBB_SAT(적5·보통 5 빨강 비율이 증강 뒤에도 안 겹치는지 --red-check 로 확인).
OBB_SAT = (1.0, 1.2)  # 채도는 올리기만(계획서 7-1 "채도는 낮추지 않기"). 0.2·0·올리기만 비교는 data/harvest_obb/red_check_pct.json — 차이는 잡음 수준, 겹침은 밝기·대비·이동 몫
OBB_JPEG = (60, 95)
OBB_P_JPEG, OBB_P_ROT180 = 0.5, 0.5


def _jpeg(im: Image.Image) -> Image.Image:
    import io
    import random

    if random.random() >= OBB_P_JPEG:
        return im
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=random.randint(*OBB_JPEG))
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _rot180(im: Image.Image) -> Image.Image:
    import random

    return im.rotate(180) if random.random() < OBB_P_ROT180 else im


def obb_pil(sat: float = OBB_SAT) -> T.Compose:
    return T.Compose([T.Lambda(_jpeg), T.Lambda(_rot180), T.Lambda(square), T.RandomAffine(8, translate=(0.06, 0.06), scale=(0.9, 1.1), fill=114),
                      T.ColorJitter(0.25, 0.25, sat, 0.02), T.RandomApply([T.GaussianBlur(3, (0.3, 1.2))], 0.3)])


AUG_OBB = T.Compose([obb_pil(), T.ToTensor(), T.Normalize(MEAN, STD)])
# 2026-11-07(metrics 표 6 11-07 저녁 줄): 운영 cls4 는 AUG 만이라 180° 뒤집은 만수를 2m 으로 확신 → 서버 read_any(강 끝)가 바로 놓인 3만을
# 2만으로 고름. --synth-pre --rot180 = 사전학습·미세 조정 모두 정사각형 크롭을 확률 OBB_P_ROT180 로 180° 돌린 뒤 AUG(같은 라벨).
AUG_R180 = T.Compose([T.Lambda(_rot180), *AUG.transforms])


def train(items: list[dict], images: dict, seed: int, aug=None, init: dict | None = None) -> nn.Module:
    """aug 없으면 AUG(images = 정사각형 크롭). AUG_OBB 면 images = 원래 크기 크롭.
    init(7-2): 사전학습 가중치. 주면 ImageNet 가중치로 만든 뒤 덮어쓴다(난수 흐름은 init 없을 때와 같다) — 나머지 학습은 그대로."""
    import random

    aug = aug or AUG
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    net = torchvision.models.mobilenet_v3_small(weights=torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    net.classifier[3] = nn.Linear(net.classifier[3].in_features, len(CLASSES))
    if init is not None:
        net.load_state_dict(init)
    freq = Counter(x["tile"] for x in items)
    prob = np.array([1 / freq[x["tile"]] for x in items])
    prob /= prob.sum()
    opt = torch.optim.AdamW(net.parameters(), lr=5e-4, weight_decay=0.01)
    steps = max(1, len(items) // 32)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, EPOCHS * steps)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    net.train()
    for _ in range(EPOCHS):
        for _ in range(steps):
            idx = np.random.choice(len(items), 32, p=prob)
            x = torch.stack([aug(images[items[i]["file"]]) for i in idx])
            y = torch.tensor([CLASSES.index(items[i]["tile"]) for i in idx])
            opt.zero_grad()
            loss_fn(net(x), y).backward()
            opt.step()
            sched.step()
    return net.eval()


def predict(net: nn.Module, items: list[dict], images: dict) -> list[str]:
    with torch.no_grad():
        x = torch.stack([PLAIN(images[i["file"]]) for i in items])
        return [CLASSES[k] for k in net(x).argmax(1).tolist()]


def score(items: list[dict], preds: list[str], seen: set[str] | None = None) -> dict:
    ok = [p == x["tile"] for p, x in zip(preds, items)]
    scenes: dict[str, bool] = {}
    for good, x in zip(ok, items):
        scenes[x["scene"]] = scenes.get(x["scene"], True) and good
    unseen = [i for i, x in enumerate(items) if seen is not None and x["tile"] not in seen]
    return dict(n=len(items), ok=sum(ok), scenes=len(scenes), scene_ok=sum(scenes.values()), unseen=len(unseen), unseen_ok=sum(ok[i] for i in unseen),
                wrong=[(x["file"], x["tile"], p) for p, x, good in zip(preds, items, ok) if not good])


def baselines(items: list[dict]) -> dict:
    import run_yolo as ry
    m = ry.Nikmomo("s")
    y11 = []
    for x in items:
        bgr = np.asarray(Image.open(CROPS / x["file"]).convert("RGB"))[:, :, ::-1]
        ch, cw = bgr.shape[:2]
        S = max(ch, cw) * 8  # 패가 입력의 약 1/8 이 되게 회색 바탕 가운데에. 크롭을 꽉 채우면 학습 때 크기와 달라 거의 못 읽는다(첫 측정 1/259)
        canvas = np.full((S, S, 3), 114, np.uint8)
        canvas[(S - ch) // 2:(S - ch) // 2 + ch, (S - cw) // 2:(S - cw) // 2 + cw] = bgr
        d, _ = m.predict(canvas, conf=0.05)
        y11.append(max(d, key=lambda t: t[1])[0] if d else "없음")
    h = ry.HaseLab()
    with torch.no_grad():
        tf = T.Compose([T.Resize((224, 224)), T.ToTensor(), T.Normalize(MEAN, STD)])
        xs = torch.stack([tf(Image.open(CROPS / x["file"]).convert("RGB")) for x in items])
        hl = [ry.HASE_CLASSES[k] for b in xs.split(16) for k in h.net(b).argmax(1).tolist()]
    return {"YOLO11 s 패 종류": y11, "HaseLab ResNet-50": hl}


def report(label: str, s: dict) -> None:
    print(f"{label}: 패 {s['ok']}/{s['n']} ({100 * s['ok'] / s['n']:.1f}%) 사진 {s['scene_ok']}/{s['scenes']}" + (f" 학습에 없는 종류 {s['unseen']}장" if s["unseen"] else ""), flush=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    images = {x["file"]: square(Image.open(CROPS / x["file"]).convert("RGB")) for x in index}
    print("크롭", len(index), "장면", len({x["scene"] for x in index}), "없는 종류", [c for c in CLASSES if c not in {x["tile"] for x in index}], flush=True)
    res: dict = {"holdout": [], "scene": []}
    t0 = time.perf_counter()

    for name, preds in baselines(index).items():
        res[name] = {}
        for p in ("bcd", "am", "pm"):
            v = [(x, q) for x, q in zip(index, preds) if x["part"] == p]
            s = score([a for a, _ in v], [b for _, b in v])
            res[name][p] = s
            report(f"{name} {p}", s)
    print("기준 비교 끝", round(time.perf_counter() - t0), "초", flush=True)
    if "--base" in sys.argv:  # 학습 없이 비교만(결과 파일은 안 건드림)
        return

    for p in ("bcd", "am", "pm"):
        for seed in (0, 1, 2):
            tr = [x for x in index if x["part"] != p]
            te = [x for x in index if x["part"] == p]
            t1 = time.perf_counter()
            net = train(tr, images, seed)
            s = score(te, predict(net, te, images), {x["tile"] for x in tr})
            s.update(part=p, seed=seed, secs=round(time.perf_counter() - t1))
            res["holdout"].append(s)
            report(f"세트 분리 {p} 시드 {seed} ({s['secs']}초)", s)
            (DATA / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    groups = sorted({SAME_HAND.get(x["scene"], x["scene"]) for x in index})
    for g in groups:
        tr = [x for x in index if SAME_HAND.get(x["scene"], x["scene"]) != g]
        te = [x for x in index if SAME_HAND.get(x["scene"], x["scene"]) == g]
        s = score(te, predict(train(tr, images, 0), te, images), {x["tile"] for x in tr})
        s.update(group=g, part=te[0]["part"])
        res["scene"].append(s)
        report(f"장면 분리 {g}", s)
        (DATA / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("== 요약")
    for p in ("bcd", "am", "pm"):
        v = [s for s in res["holdout"] if s["part"] == p]
        print(f"세트 분리 {p}: 패 {statistics.mean(s['ok'] for s in v):.1f}/{v[0]['n']}, 사진 {statistics.mean(s['scene_ok'] for s in v):.1f}/{v[0]['scenes']}, 학습에 없는 종류 {v[0]['unseen']}장")
    tot, ok = sum(s["n"] for s in res["scene"]), sum(s["ok"] for s in res["scene"])
    un, un_ok = sum(s["unseen"] for s in res["scene"]), sum(s["unseen_ok"] for s in res["scene"])
    print(f"장면 분리: 패 {ok}/{tot} ({100 * ok / tot:.1f}%), 학습에 있는 종류만 {ok - un_ok}/{tot - un} ({100 * (ok - un_ok) / (tot - un):.1f}%), 사진 {sum(s['scene_ok'] for s in res['scene'])}/{sum(s['scenes'] for s in res['scene'])}")
    print("장면 분리 틀린 패", Counter((w[1], w[2]) for s in res["scene"] for w in s["wrong"]).most_common(25))
    print("총", round(time.perf_counter() - t0), "초")


# ---------------------------------------------------------------- 7-1(2026-11-06): 세운 크롭으로 다시 학습
OBB = DATA / "harvest_obb"
MODELS = HERE / "server_bench" / "models"
FIVES = ["0m", "5m", "0p", "5p", "0s", "5s"]
RECOGNIZER_S7 = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer-s7")  # feat/cls-alt worktree(signals.red_ratio)


def obb_index() -> tuple[list[dict], dict]:
    """harvest.py --obb 결과. images = 원래 크기 크롭(AUG_OBB 가 JPEG 지터 뒤 정사각형으로 만든다). part bcd·am·pm(B·C·D·오전·오후)."""
    idx = json.loads((OBB / "index.json").read_text(encoding="utf-8"))
    # 2026-11-10: index.json 은 11-06 에 만들어 11-08 라벨 고침(review.FIX — 거꾸로 놓인 만수 2m → 3m·1m 4장)이 빠져 있었다.
    # 라벨은 늘 지금 원본 라벨(data/index.json·review.extra)을 따른다(ref 로 찾음, metrics 표 1-154).
    sys.path.insert(0, str(HERE))
    import review as rw

    cur = {x["file"]: x["tile"] for x in json.loads((DATA / "index.json").read_text(encoding="utf-8"))}
    cur.update({x["file"]: x["tile"] for x in rw.extra()})
    for x in idx:
        x["tile"] = cur.get(x["ref"], x["tile"])
        x["file"] = "o_" + x["file"]
        x["scene"] = x["photo"]
    return idx, {x["file"]: Image.open(OBB / "crops" / x["file"][2:]).convert("RGB") for x in idx}


def red_check(n_aug: int = 30) -> dict:
    """증강이 적5 를 보통 5 처럼 만들지 않는지: 0x·5x 크롭마다 증강을 n_aug 번 입혀 서버 signals.red_ratio 를 잰다(정사각형 회색 바탕은 잉크 아님)."""
    import random

    sys.path.insert(0, str(RECOGNIZER_S7))
    from app import signals as sg

    idx, images = obb_index()
    random.seed(0)
    torch.manual_seed(0)
    out = {}
    for sat in (OBB_SAT,):
        pil = obb_pil(sat)
        d: dict = {}
        for x in idx:
            if x["tile"] not in FIVES:
                continue
            im = images[x["file"]]
            raw = sg.red_ratio(im)
            aug = [sg.red_ratio(pil(im)) for _ in range(n_aug)]
            aug = [r for r in aug if r is not None]
            k = d.setdefault(x["tile"], {"raw": [], "aug": []})
            if raw is not None:
                k["raw"].append(raw)
            k["aug"] += aug
        res = {}
        for c in "mps":
            r0, r5 = d.get(f"0{c}", {"raw": [], "aug": []}), d.get(f"5{c}", {"raw": [], "aug": []})
            res[c] = {"적5 최소 원본": min(r0["raw"], default=None), "보통5 최대 원본": max(r5["raw"], default=None),
                      "적5 최소 증강": min(r0["aug"], default=None), "보통5 최대 증강": max(r5["aug"], default=None),
                      "적5 증강 1%": float(np.percentile(r0["aug"], 1)) if r0["aug"] else None,
                      "보통5 증강 99%": float(np.percentile(r5["aug"], 99)) if r5["aug"] else None,
                      "적5 크롭": len(r0["raw"]), "보통5 크롭": len(r5["raw"]), "증강 수": n_aug}
            res[c]["겹침"] = (res[c]["적5 최소 증강"] is not None and res[c]["보통5 최대 증강"] is not None
                            and res[c]["적5 최소 증강"] <= res[c]["보통5 최대 증강"])
        out[f"sat{sat}"] = res
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (OBB / "red_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def export(net: nn.Module, path: Path) -> None:
    torch.onnx.export(net.eval(), torch.zeros(1, 3, SIZE, SIZE), path, input_names=["x"], output_names=["y"],
                      dynamic_axes={"x": {0: "n"}, "y": {0: "n"}}, opset_version=17, dynamo=False)


def onnx_pred(path: Path, ims: list[Image.Image]) -> list[str]:
    """서버 LocalReader._tensor 와 같은 전처리(square + ImageNet 정규화)로 ONNX 1순위."""
    import onnxruntime as ort

    sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    out = []
    for i in range(0, len(ims), 64):
        x = np.stack([PLAIN(square(im)).numpy() for im in ims[i:i + 64]])
        out += [CLASSES[k] for k in sess.run(None, {sess.get_inputs()[0].name: x})[0].argmax(1)]
    return out


def five_confusion(truth: list[str], pred: list[str]) -> dict:
    """패 단위 혼동 행렬의 0x↔5x 칸(7-1 기준 d)."""
    c = Counter((t, p) for t, p in zip(truth, pred) if t in FIVES or p in FIVES)
    return {"적5→5": sum(c[(f"0{s}", f"5{s}")] for s in "mps"), "5→적5": sum(c[(f"5{s}", f"0{s}")] for s in "mps"),
            "칸": {f"{t}→{p}": n for (t, p), n in sorted(c.items()) if t != p}}


def holdout_eval(tags=("cls", "cls_s1", "cls2", "cls2_s1")) -> dict:
    """나눔 분류기 전(cls_<part>.onnx, 축 크롭으로 학습) · 후(cls2_<part>{,_s1}.onnx)를 같은 홀드아웃 크롭 두 벌로:
    세운 크롭(harvest_obb, 운영 입력과 같은 모양) part == 나눔, 옛 축 크롭(data/index.json part + review.extra half) == 나눔."""
    sys.path.insert(0, str(HERE))
    import review as rw

    idx, images = obb_index()
    base = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    add = rw.extra()
    old_imgs = {x["file"]: Image.open(CROPS / x["file"]).convert("RGB") for x in base}
    old_imgs.update({x["file"]: Image.open(x["path"]).convert("RGB") for x in add})
    res: dict = {}
    for crops in ("obb", "axis"):
        for tag in tags:
            truth, pred, per = [], [], {}
            for part in ("bcd", "am", "pm"):
                if crops == "obb":
                    held = [x for x in idx if x["part"] == part]
                    ims = [images[x["file"]] for x in held]
                else:
                    held = [x for x in base if x["part"] == part] + [x for x in add if x["half"] == part]
                    ims = [old_imgs[x["file"]] for x in held]
                name = tag.replace("_s1", "") + f"_{part}" + ("_s1" if tag.endswith("_s1") else "")
                path = MODELS / f"{name}.onnx"
                if not path.exists():
                    continue
                p = onnx_pred(path, ims)
                t = [x["tile"] for x in held]
                per[part] = f"{sum(a == b for a, b in zip(p, t))}/{len(t)}"
                truth += t
                pred += p
            if truth:
                res[f"{crops}/{tag}"] = {"패": f"{sum(a == b for a, b in zip(pred, truth))}/{len(truth)}", "나눔별": per, **five_confusion(truth, pred),
                                         "틀린 것": Counter(f"{a}→{b}" for a, b in zip(truth, pred) if a != b).most_common(12)}
    return res


def main_obb() -> None:
    """  python -I -X utf8 experiments/tile_classifier/train.py --obb [--only bcd,am,pm,all] [--seeds 0,1] [--eval-only] [--red-check]
    나눔 cls2_<part>(part 가 아닌 세운 크롭으로) · 전부 cls2_all, 씨드 0 = 주 분류기, 씨드 1 = 두 번째 분류기(_s1, 불확실성 S3).
    결과 data/cls2_*.pt, server_bench/models/cls2_*.onnx, data/harvest_obb/results.json(학습 기록 + 홀드아웃 전·후)."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--obb", action="store_true")
    ap.add_argument("--only", default="bcd,am,pm,all")
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--red-check", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    if a.red_check:
        red_check()
        return
    out_p = OBB / "results.json"
    res = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {}
    res.setdefault("train", {})
    if not a.eval_only:
        idx, images = obb_index()
        for part in a.only.split(","):
            for seed in (int(s) for s in a.seeds.split(",")):
                name = f"cls2_{part}" + (f"_s{seed}" if seed else "")
                dst = MODELS / f"{name}.onnx"
                if dst.exists():
                    print("있음(재학습 안 함)", dst, flush=True)
                    continue
                pool = idx if part == "all" else [x for x in idx if x["part"] != part]
                t0 = time.perf_counter()
                net = train(pool, images, seed, AUG_OBB)
                torch.save(net.state_dict(), DATA / f"{name}.pt")
                export(net, dst)
                res["train"][name] = dict(n=len(pool), seed=seed, secs=round(time.perf_counter() - t0), sat=OBB_SAT, jpeg=list(OBB_JPEG),
                                          p_jpeg=OBB_P_JPEG, p_rot180=OBB_P_ROT180, epochs=EPOCHS, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
                print(name, res["train"][name], flush=True)
                out_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    res["holdout"] = holdout_eval()
    res["holdout_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res["holdout"], ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- 7-2(2026-11-06): 장면 합성 사전학습 → 운영과 같은 미세 조정
SYNTH = DATA / "synth"
SYN_EPOCHS = 2  # 합성 크롭(풀마다 약 2.4만 장)을 두 번 — 미세 조정(40 에폭 × 1,550장)과 비슷한 걸음 수
SYN_POOL = {"bcd": "nobcd", "am": "b", "pm": "a", "all": "all"}  # 홀드아웃 사진 재료를 뺀 풀(scene_synth.POOLS)


def pretrain_synth(pool: str, seed: int, aug=None) -> dict:
    """scene_synth.py cls 크롭(data/synth/cls_<pool>.npz, 128 정사각형)으로 ImageNet 가중치에서 SYN_EPOCHS 에폭. 증강·손실·최적화는 train() 과 같다(종류 균형 뽑기)."""
    import random

    aug = aug or AUG
    d = np.load(SYNTH / f"cls_{pool}.npz")
    X, Y = d["x"], d["y"].astype(int)
    torch.manual_seed(1000 + seed)
    np.random.seed(1000 + seed)
    random.seed(1000 + seed)
    net = torchvision.models.mobilenet_v3_small(weights=torchvision.models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    net.classifier[3] = nn.Linear(net.classifier[3].in_features, len(CLASSES))
    freq = Counter(Y.tolist())
    prob = np.array([1 / freq[y] for y in Y])
    prob /= prob.sum()
    opt = torch.optim.AdamW(net.parameters(), lr=5e-4, weight_decay=0.01)
    steps = SYN_EPOCHS * (len(Y) // 32)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)
    net.train()
    for _ in range(steps):
        idx = np.random.choice(len(Y), 32, p=prob)
        # 합성 크롭은 128 정사각형으로 저장돼 있다 — SIZE 가 다르면 그 크기로(128 보다 크면 늘린 것이라 실제 크롭보다 흐림)
        x = torch.stack([aug(Image.fromarray(X[i]) if SIZE == 128 else Image.fromarray(X[i]).resize((SIZE, SIZE), Image.BILINEAR)) for i in idx])
        y = torch.tensor(Y[idx])
        opt.zero_grad()
        loss_fn(net(x), y).backward()
        opt.step()
        sched.step()
    return {k: v.clone() for k, v in net.state_dict().items()}


def main_synth() -> None:
    """  python -I -X utf8 experiments/tile_classifier/train.py --synth-pre [--only bcd,am,pm,all] [--seeds 0,1] [--tag cls4 --seed-offset 10]
    7-2a(2026-11-06): --tag·--seed-offset 로 같은 설정을 새 씨드로(cls4 = 주 10·두 번째 11, 사전학습 난수 1000 + 씨드). 결과는 data/synth/results_<tag>.json.
    cls3_<part>{,_s1}: 합성 사전학습 + 운영 cls_<part>(det_eval.classifiers)·cls_all(prep_deploy)·_s1(prep_alt_cls) 과 같은 묶음·씨드·AUG 로 미세 조정.
    결과 server_bench/models/cls3_*.onnx, data/cls3_*.pt, data/synth/results.json(학습 기록 + 홀드아웃 전 cls·후 cls3)."""
    import argparse

    sys.path.insert(0, str(HERE))
    import review as rw

    ap = argparse.ArgumentParser()
    ap.add_argument("--synth-pre", action="store_true")
    ap.add_argument("--only", default="bcd,am,pm,all")
    ap.add_argument("--seeds", default="0,1")
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--tag", default="cls3")
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--rot180", action="store_true", help="사전학습·미세 조정에 180° 뒤집기(AUG_R180, 2026-11-07 cls5)")
    ap.add_argument("--red5", action="store_true", help="11-06·11-07 매장 5 계열 크롭(red5_harvest.py, data/red5/labels.json 검토 반영)을 모든 묶음에 더함(2026-11-10 cls7)")
    a = ap.parse_args()
    aug = AUG_R180 if a.rot180 else AUG
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    out_p = SYNTH / ("results.json" if a.tag == "cls3" else f"results_{a.tag}.json")
    res = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {}
    res.setdefault("train", {})
    if not a.eval_only:
        base = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
        add = rw.extra()
        images = {x["file"]: square(Image.open(CROPS / x["file"]).convert("RGB")) for x in base}
        images.update({x["file"]: square(Image.open(x["path"]).convert("RGB")) for x in add})
        if a.red5:  # 11-06·11-07 사진은 개발(B·C·D·10-31)·테스트(10-24) 어느 나눔에도 없어 모든 묶음에 넣는다
            rd = DATA / "red5"
            lab = json.loads((rd / "labels.json").read_text(encoding="utf-8"))
            red = [dict(file="r_" + r["file"], path=rd / "crops" / r["file"], tile=lab["fix"].get(str(r["id"]), r["pred"]), photo=r["photo"], half="new")
                   for r in json.loads((rd / "index.json").read_text(encoding="utf-8"))
                   if str(r["id"]) not in lab["drop"] and lab["fix"].get(str(r["id"]), r["pred"]) in ("5m", "5p", "5s", "0m", "0p", "0s")]
            images.update({x["file"]: square(Image.open(x["path"]).convert("RGB")) for x in red})
            add = add + red
            print("red5 더함", len(red), Counter(x["tile"] for x in red), flush=True)
        for part in a.only.split(","):
            if part == "all":
                pool = base + add
            else:  # det_eval.classifiers·prep_alt_cls 와 같은 묶음
                pool = [x for x in base if x["part"] != part] + [x for x in add if x["half"] != part and (part != "bcd" or x["half"] != "other")]
            for k in (int(s) for s in a.seeds.split(",")):
                name = f"{a.tag}_{part}" + (f"_s{k}" if k else "")
                seed = a.seed_offset + k
                dst = MODELS / f"{name}.onnx"
                if dst.exists():
                    print("있음(재학습 안 함)", dst, flush=True)
                    continue
                t0 = time.perf_counter()
                init = pretrain_synth(SYN_POOL[part], seed, aug)
                t1 = time.perf_counter()
                net = train(pool, images, seed, aug, init=init)
                torch.save(net.state_dict(), DATA / f"{name}.pt")
                export(net, dst)
                res["train"][name] = dict(n=len(pool), seed=seed, synth_pool=SYN_POOL[part], synth_epochs=SYN_EPOCHS,
                                          synth_n=int(len(np.load(SYNTH / f"cls_{SYN_POOL[part]}.npz")["y"])), pre_secs=round(t1 - t0),
                                          secs=round(time.perf_counter() - t1), epochs=EPOCHS, rot180=a.rot180, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
                print(name, res["train"][name], flush=True)
                out_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    res["holdout"] = holdout_eval(("cls", "cls_s1", a.tag, f"{a.tag}_s1"))
    res["holdout_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out_p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res["holdout"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if "--synth-pre" in sys.argv:
        main_synth()
    else:
        main_obb() if "--obb" in sys.argv or "--red-check" in sys.argv else main()
