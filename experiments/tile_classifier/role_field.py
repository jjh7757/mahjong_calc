"""테스트 세트(10-24 삼각대 15장)로 역할 모델 대 규칙 한 번 비교(2026-11-04, 노트북 CPU, API 없음). metrics 표 1-59.

테스트 사진은 탁자가 약 25° 기울고 원근이 있어 개발 세트(10-31 위에서 내려다본 사진)와 카메라가 다르다. 재료를 전부 새로 만든다:
  build  : 앞면 상자(검출기 final.pt, det_relabel.detect) · 펠트·기기 네 모서리(zone_points/propose 색 방법) · 뒷면 상자(det_backs.one)
           · 규칙 역할 라벨(role_label.label_scene, 격자는 read_grid_timing_test.dart 의 삼각대 위치별 값) → data/role/field/{boxes,labels}.json, check/<이름>.jpg
  review : data/role/field/review.json(독립 검토 수정) 을 labels.json 에 반영(rule 칸은 규칙 원값)
  score  : 합성 사전학습 가중치(pre_synth8k.pt)를 실제 25장 전부로 미세 조정한 모델로 15장 예측. 좌표는 펠트 네 모서리 호모그래피로 0~1
           (격자 직사각형은 기운 사진에 안 맞는다). 규칙 원값과 나란히 채점, pred/<이름>.jpg

  python -I -X utf8 experiments/tile_classifier/role_field.py build|review|score
  python -I -X utf8 experiments/tile_classifier/role_field.py score rot [pre_synth8k_rot.pt]   # 회전 상자 특징(2026-11-05): 8회차 검출 회전 상자로 기울기, score_rot.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "zone_points"))
sys.path.insert(0, str(HERE.parent / "speed"))
ROOT = HERE.parents[1]
OUT = HERE / "data" / "role" / "field"
CAP = ROOT / "experiments" / "field_20261024" / "captures"
ROLES = ["hand", "meld", "river", "wall", "pair", "loose"]
COLORS = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow", "other": "gray"}

# read_grid_timing_test.dart SET=field: 삼각대 위치별 격자(1000 분율)와 화료자 자리, 정답 장수(NOTES "촬영별")
GA = dict(x1=300, x2=690, y1=150, y2=830)
GA2 = dict(x1=300, x2=720, y1=150, y2=830)
GB1 = dict(x1=315, x2=760, y1=200, y2=740)
GB2 = dict(x1=355, x2=760, y1=200, y2=740)
SCENES = {
    "122922": dict(grid=GA, side="right", riichi=True, hand=13, meld=0),
    "124007": dict(grid=GA2, side="top", riichi=False, hand=10, meld=3),  # 검토: 뒷면 3 + 앞면 10 + 發 퐁
    **{t: dict(grid=GA, side="top", riichi=False, hand=10, meld=3) for t in ("125053", "130533", "131210", "132647", "133011", "133620", "134323", "135148")},
    **{t: dict(grid=GB1, side="left", riichi=False, hand=13, meld=0) for t in ("135912", "140302", "140750", "140918")},
    "143443": dict(grid=GB2, side="left", riichi=False, hand=10, meld=4),
}


def build() -> None:
    import det_backs
    import det_relabel
    import propose
    from ultralytics import YOLO

    (OUT / "check").mkdir(parents=True, exist_ok=True)
    model = YOLO(str(HERE / "data/det/kaggle_out_r2/out/final.pt"))
    boxes = {}
    for t, sc in SCENES.items():
        name = f"20261024_{t}"
        path = CAP / name / "original.jpg"
        im = Image.open(path).convert("RGB")
        W, H = im.size
        s = 1020 / max(W, H)
        small = np.asarray(im.resize((round(W * s), round(H * s))))
        h, w = small.shape[:2]
        felt = propose.felt_quad(small)
        dev = propose.device_quad(small, felt) if felt is not None else None
        norm = lambda q: None if q is None else [[round(float(x) / w, 5), round(float(y) / h, 5)] for x, y in q]
        bs = det_relabel.detect(model, im)
        faces = [[round(x0), round(y0), round(x1 - x0), round(y1 - y0)] for x0, y0, x1, y1, _ in bs]
        rec = dict(path=str(path), size=[W, H], boxes=faces, conf=[round(b[4], 3) for b in bs], felt=norm(felt), device=norm(dev), **sc)
        rec["backs"] = det_backs.one(name, rec, rec["felt"], rec["device"]) if rec["felt"] else []
        boxes[name] = rec
        print(name, "앞면", len(faces), "뒷면", len(rec["backs"]), "펠트", rec["felt"] is not None, "기기", rec["device"] is not None, flush=True)
    (OUT / "boxes.json").write_text(json.dumps(boxes), encoding="utf-8")
    label(boxes)


def label(boxes: dict) -> None:
    """규칙 라벨(role_label.label_scene). 격자는 삼각대 값, 리치봉 상자 없음."""
    import role_label as rl

    out = {}
    for name, rec in boxes.items():
        rl.BOXES[name] = rec
        rl.TRUTH[name] = dict(riichi=rec["riichi"])
        im = Image.open(rec["path"]).convert("RGB")
        items = rl.label_scene(dict(name=name, grid=dict(rec["grid"]), side=rec["side"]), np.asarray(im))
        for it in items:
            it["rule"] = it["role"]
        out[name] = dict(path=rec["path"], size=rec["size"], side=rec["side"], riichi=rec["riichi"], items=items)
        d = ImageDraw.Draw(im)
        for i, it in enumerate(items):
            x, y, w, h = it["box"]
            d.rectangle((x, y, x + w, y + h), outline=COLORS[it["role"]], width=5)
            d.text((x, y - 28), f"{i}", fill=COLORS[it["role"]])
        for x, y, w, h in rec["backs"]:
            d.rectangle((x, y, x + w, y + h), outline=(200, 200, 230), width=2)
        if rec["felt"]:
            d.polygon([(px * rec["size"][0], py * rec["size"][1]) for px, py in rec["felt"]], outline="lime", width=4)
        im.resize((im.width // 2, im.height // 2)).save(OUT / "check" / f"{name}.jpg", quality=80)
        print(name, rec["side"], {r: sum(1 for it in items if it["role"] == r) for r in ROLES + ["other"]}, flush=True)
    (OUT / "labels.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def review() -> None:
    labels = json.loads((OUT / "labels.json").read_text(encoding="utf-8"))
    rv = json.loads((OUT / "review.json").read_text(encoding="utf-8"))
    n = 0
    for name, m in rv.items():
        for k, v in m.items():
            it = labels[name]["items"][int(k)]
            if it["role"] != v:
                it["role"], it["reviewed"] = v, True
                n += 1
    (OUT / "labels.json").write_text(json.dumps(labels, ensure_ascii=False), encoding="utf-8")
    print("수정", n)


def homography(felt: list, W: int, H: int) -> np.ndarray:
    src = np.array([[x * W, y * H] for x, y in felt], np.float32)
    dst = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def field_rects() -> dict:
    """테스트 15장을 8회차 회전 상자 검출기(server_bench/models/det_r8_final.onnx, 테스트 사진은 학습에 없음)로 검출한 회전 상자
    {사진: {"faces": [(축 상자, 회전 상자)], "backs": [...]}} — 회전 상자 특징(role_set --feat rot)의 기울기·패 크기용. data/role/field/rects_r8.json 에 저장·재사용."""
    cache = OUT / "rects_r8.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    sys.path.insert(0, str(HERE / "server_bench"))
    import onnxruntime as ort
    import obb_detect as od

    sess = ort.InferenceSession(str(HERE / "server_bench" / "models" / "det_r8_final.onnx"), providers=["CPUExecutionProvider"])
    boxes = json.loads((OUT / "boxes.json").read_text(encoding="utf-8"))
    out = {}
    for name, rec in boxes.items():
        rgb = np.asarray(Image.open(rec["path"]).convert("RGB"))
        x, r, left, top = od.letterbox(rgb)
        o = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
        H, W = rgb.shape[:2]
        out[name] = {"faces": [(list(b), [list(rc[0]), list(rc[1]), rc[2]]) for b, rc in od.decode(o, r, left, top, W, H)],
                     "backs": [(list(b), [list(rc[0]), list(rc[1]), rc[2]]) for b, rc in od.decode(o, r, left, top, W, H, cls=1)]}
        print(name, "r8 앞면", len(out[name]["faces"]), "뒷면", len(out[name]["backs"]), flush=True)
    cache.write_text(json.dumps(out), encoding="utf-8")
    return out


def tokens(rec: dict, labels_rec: dict, backs: bool = True, feat: str = "old", rects: dict | None = None) -> tuple[np.ndarray, list[int]]:
    """role_set.scene_tokens 과 같은 9칸(또는 --feat rot 11칸) 벡터. 좌표는 펠트 호모그래피, 크기는 펠트 폭(픽셀 평균)으로 나눔.
    rot 특징의 패 크기·기울기는 rects(field_rects, 8회차 검출)에서 IoU 로 찾은 회전 상자로 — 그림 축 기준(삼각대 사진은 평면 회전이 거의 없다)."""
    import role_set as rs

    W, H = rec["size"]
    M = homography(rec["felt"], W, H)
    f = np.array([[x * W, y * H] for x, y in rec["felt"]])
    fw = (np.linalg.norm(f[1] - f[0]) + np.linalg.norm(f[2] - f[3])) / 2
    fh = (np.linalg.norm(f[3] - f[0]) + np.linalg.norm(f[2] - f[1])) / 2

    def warp(x: float, y: float) -> tuple[float, float]:
        p = cv2.perspectiveTransform(np.array([[[x, y]]], np.float32), M)[0, 0]
        return float(p[0]), float(p[1])

    if rec.get("device"):
        d = np.array(rec["device"]).mean(axis=0)
        su, sv = warp(d[0] * W, d[1] * H)
    else:
        su, sv = 0.5, 0.5
    su, sv, _ = rs.turn(su, sv, rec["side"])
    rows, labs = [], []
    faces = [it["box"] for it in labels_rec["items"]]
    bks = rec["backs"] if backs else []
    rr = rects or {"faces": [], "backs": []}
    fr = rs.match_rects(faces, rr["faces"]) if feat == "rot" else [None] * len(faces)
    br = rs.match_rects(bks, rr["backs"]) if feat == "rot" else [None] * len(bks)
    allb = [(b, it["role"], False, r) for b, it, r in zip(faces, labels_rec["items"], fr)] + [(b, None, True, r) for b, r in zip(bks, br)]
    for (x, y, w, h), role, back, rect in allb:
        u, v = warp(x + w / 2, y + h / 2)
        u, v, swap = rs.turn(u, v, rec["side"])
        if feat == "rot":
            # 삼각대 사진은 탁자가 그림 안에서 12~26° 돌아 있고 원근이 있어, 꼭짓점을 펠트 호모그래피로 보낸 뒤 펠트 축 기준으로 크기·기울기를 잰다
            src =cv2.boxPoints(((float(rect[0][0]), float(rect[0][1])), (float(rect[1][0]), float(rect[1][1])), float(rect[2]))) if rect is not None \
                else np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float32)
            wp = cv2.perspectiveTransform(src.reshape(1, -1, 2).astype(np.float32), M)[0]
            bw, bh, tilt = rs.tile_geom(None, wp)  # 펠트 = 1 단위
        else:
            pw, ph, tilt = rs.tile_geom((x, y, w, h), rect)
            bw, bh = pw / fw, ph / fh
        if swap:
            bw, bh = bh, bw
        rows.append(rs.feat_row(u, v, bw, bh, back, su, sv, tilt, feat))
        labs.append(-1 if back or role not in ROLES else ROLES.index(role))
    return np.array(rows, np.float32).reshape(-1, rs.feat_dim(feat)), labs


def score() -> None:
    import torch

    import role_set as rs
    import seat_grow as sg

    torch.set_num_threads(8)
    feat = sys.argv[2] if len(sys.argv) > 2 else "old"  # score [old|rot] [사전학습 파일]
    pre_file = sys.argv[3] if len(sys.argv) > 3 else ("pre_synth8k_rot.pt" if feat == "rot" else "pre_synth8k.pt")
    boxes = json.loads((OUT / "boxes.json").read_text(encoding="utf-8"))
    labels = json.loads((OUT / "labels.json").read_text(encoding="utf-8"))
    rects_dev = json.loads(rs.RECTS.read_text(encoding="utf-8")) if feat == "rot" else None
    rects_field = field_rects() if feat == "rot" else {}
    # 학습: 개발 세트 25장 전부(검토 뒤 라벨) + 합성 사전학습 가중치
    dev_labels = json.loads((rs.OUT / rs.LABELS).read_text(encoding="utf-8"))  # ROLE_LABELS=labels_obb.json(7-1)
    tag = __import__("os").environ.get("ROLE_TAG", "")  # 7-1: 출력 이름 뒤에(role_all_rot<tag>.pt·score_rot<tag>.json), 기존 가중치를 덮지 않게
    dev_backs = json.loads(rs.BACKS.read_text(encoding="utf-8"))
    grids = {s["name"]: s["grid"] for s in sg.scenes()}
    tr = []
    for name, rec in dev_labels.items():
        x, y = rs.scene_tokens(rec, grids[name], dev_backs.get(name, []), True, feat, rs.scene_rects(name, rects_dev))
        tr.append(dict(name=name, x=x, y=y))
    pre = rs.load_nets(rs.OUT / pre_file)
    assert pre[0].feat == rs.feat_dim(feat), (pre_file, pre[0].feat, feat)
    bend = int(__import__("os").environ.get("ROLE_BEND", "0"))  # 2026-11-07: 휜 손패 사본 수(role_set.add_bent, role_set.py --bend 와 같은 것)
    trs = [rs.add_bent(tr, bend, seed, set(getattr(sg, "EXCLUDED", ()))) if bend and feat == "rot" else tr for seed in range(len(pre))]
    if bend:
        print("휜 손패 사본 더함", len(trs[0]) - len(tr), flush=True)
    nets = [rs.train(trs[seed], 100, seed, pre[seed], 3e-4) for seed in range(len(pre))]
    print("미세 조정 끝", len(nets), "특징", feat, pre_file, "bend", bend, flush=True)
    torch.save([n.state_dict() for n in nets], rs.OUT / f"role_all{'_rot' if feat == 'rot' else ''}{tag}.pt")  # 뒷면 포함·실제 25장 전부 미세 조정
    (OUT / "pred").mkdir(parents=True, exist_ok=True)
    from collections import Counter

    conf = {r: Counter() for r in ROLES}
    rconf = {r: Counter() for r in ROLES}
    per = {}
    for name, rec in boxes.items():
        lab = labels[name]
        x, y = tokens(rec, lab, True, feat, rects_field.get(name))
        s = dict(name=name, x=x, y=y)
        votes = [rs.predict(n, s) for n in nets]
        pred = [Counter(v[i][0] for v in votes).most_common(1)[0][0] for i in range(len(x))]
        items = lab["items"]
        c_m, c_r = Counter(pred[: len(items)]), Counter(it["rule"] for it in items)
        ok = Counter()
        for i, it in enumerate(items):
            if it["role"] not in ROLES:
                continue
            conf[it["role"]][pred[i]] += 1
            rconf[it["role"]][it["rule"]] += 1
            ok["model"] += pred[i] == it["role"]
            ok["rule"] += it["rule"] == it["role"]
            ok["n"] += 1
        hand_ok = lambda c: c["hand"] in (rec["hand"], rec["hand"] + 1)
        per[name] = dict(n=ok["n"], model=ok["model"], rule=ok["rule"], model_hand=c_m["hand"], rule_hand=c_r["hand"], model_meld=c_m["meld"], rule_meld=c_r["meld"],
                         truth_hand=rec["hand"], truth_meld=rec["meld"], model_truth=hand_ok(c_m) and c_m["meld"] == rec["meld"], rule_truth=hand_ok(c_r) and c_r["meld"] == rec["meld"])
        print(name, rec["side"], f"라벨 대비 모델 {ok['model']}/{ok['n']} 규칙 {ok['rule']}/{ok['n']} | 손패 정답 {rec['hand']} 모델 {c_m['hand']} 규칙 {c_r['hand']} | 울기 정답 {rec['meld']} 모델 {c_m['meld']} 규칙 {c_r['meld']}", flush=True)
        im = Image.open(rec["path"]).convert("RGB")
        d = ImageDraw.Draw(im)
        for i, (it, p) in enumerate(zip(items, pred)):
            bx, by, bw, bh = it["box"]
            d.rectangle((bx, by, bx + bw, by + bh), outline=COLORS[p], width=6)
            if p != it["role"] and it["role"] in ROLES:
                d.rectangle((bx - 8, by - 8, bx + bw + 8, by + bh + 8), outline="red", width=4)
                d.text((bx, by - 30), f"{i} {p}", fill="red")
        im.resize((im.width // 2, im.height // 2)).save(OUT / "pred" / f"{name}.jpg", quality=80)
    tot = {r: f"{conf[r][r]}/{sum(conf[r].values())}" for r in ROLES}
    rtot = {r: f"{rconf[r][r]}/{sum(rconf[r].values())}" for r in ROLES}
    n = sum(p["n"] for p in per.values())
    print("합계 모델", tot, f"{sum(p['model'] for p in per.values())}/{n}")
    print("합계 규칙", rtot, f"{sum(p['rule'] for p in per.values())}/{n}")
    print("혼동 모델", {r: dict(conf[r]) for r in ROLES})
    print("truth 손패·울기 장수 둘 다: 모델", sum(p["model_truth"] for p in per.values()), "규칙", sum(p["rule_truth"] for p in per.values()), f"/{len(per)}")
    (OUT / f"score{'_rot' if feat == 'rot' else ''}{tag}.json").write_text(json.dumps(dict(feat=feat, pre_file=pre_file, per=per, model=tot, rule=rtot, confusion={r: dict(c) for r, c in conf.items()}), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"build": build, "review": review, "score": score, "label": lambda: label(json.loads((OUT / "boxes.json").read_text(encoding="utf-8")))}[sys.argv[1]]()
