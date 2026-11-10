"""역할 모델 변형용 기본 입력 v2 — 초안(draft.json)에 검토(role_v2_review.json)를 반영해 학습용 정답(labels_v2.json)과 그림을 만든다(2026-11-08).

labels_v2.json[이름] = side·size·image·kind·items(앞면 상자·역할, other 포함)·backs·x(서버 토큰 11칸, 앞면 → 뒷면 순)·y(역할 번호, other·뒷면 -1).
10-31 쓰기 10장(라벨 검토 끝난 labels.json)은 role_set.scene_tokens 로 같은 모양으로 넣는다(source=labels.json).

  python -X utf8 experiments/tile_classifier/role_v2_apply.py     → data/role/v2/labels_v2.json, data/role/base_review/v2_inputs_*.jpg
"""
import json, math, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "speed"))
import role_set as rs  # noqa: E402
import seat_grow as sg  # noqa: E402

V2 = HERE / "data" / "role" / "v2"
OUTD = HERE / "data" / "role" / "base_review"
ROLES = rs.ROLES
KEEP1031 = ["20261031_123140", "20261031_132954", "20261031_133826", "20261031_134815", "20261031_143104", "20261031_165043",
            "20261031_171505", "20261031_183627"]  # 165614·181209 는 11-09 표시패 4장 짝 합성본으로 draft.json 쪽(role_v2_pair_synth2.py)


def img2tok(box, size, grid, side):
    """상자(원본 픽셀) → 토큰의 u·v·폭·높이(서버 roles.tokens 의 축 상자 계산과 같은 식)."""
    W, H = size; x1, x2, y1, y2 = (grid[k] / 1000 for k in ("x1", "x2", "y1", "y2")); fw, fh = x2 - x1, y2 - y1
    x, y, w, h = box
    u, v, swap = rs.turn(((x + w / 2) / W - x1) / fw, ((y + h / 2) / H - y1) / fh, side)
    bw, bh = w / W / fw, h / H / fh
    return (u, v, bh, bw) if swap else (u, v, bw, bh)


def overlaps_face(b, faces, thr=0.4):
    """뒷면 상자가 앞면 상자와 크게 겹치면(겹친 넓이 / 뒷면 넓이 > thr) 같은 패를 두 번 잡은 것."""
    for f in faces:
        ix = min(b[0] + b[2], f[0] + f[2]) - max(b[0], f[0]); iy = min(b[1] + b[3], f[1] + f[3]) - max(b[1], f[1])
        if ix > 0 and iy > 0 and ix * iy / (b[2] * b[3]) > thr:
            return True
    return False


def apply(name, d, rv):
    items = [dict(box=list(it["box"]), role=it["role"], owner="winner" if it["role"] in ("hand", "meld", "loose") else None) for it in d["items"]]
    x = [list(r) for r in d["tokens"]]
    nf = len(items)
    face_x, back_x = x[:nf], x[nf:]
    backs = [list(b) for b in d["backs"]]
    for k, r in rv.get("role", {}).items():
        items[int(k)]["role"] = r
    for i in rv.get("other", []):
        items[i]["role"] = "other"
    for i in rv.get("meld_other", []):
        items[i]["role"] = "meld"; items[i]["owner"] = "other"  # 다른 사람 울기도 울기(11-08 사용자 결정) — 누구 것인지는 owner 로만 남김
    for k, nb in rv.get("fix_box", {}).items():  # 검출 상자가 패의 반쪽만 덮은 것 → 패 전체로(토큰 u·v·크기도 다시)
        i = int(k); row = list(face_x[i])
        u0, v0, _, _ = img2tok(items[i]["box"], d["size"], d["grid"], d["side"]); u1, v1, bw, bh = img2tok(nb, d["size"], d["grid"], d["side"])
        row[0] += u1 - u0; row[1] += v1 - v0; row[6] += u1 - u0; row[7] += v1 - v0
        row[2], row[3], row[5] = bw * 10, bh * 10, float(bw > bh * 1.15)
        face_x[i] = row; items[i]["box"] = list(nb)
    drop = set(rv.get("delete", []))
    for i in rv.get("to_back", []):
        row = list(face_x[i]); row[4] = 1.0  # 뒷면 플래그
        back_x.append(row); backs.append(items[i]["box"]); drop.add(i)
    for a, b in rv.get("merge", []):
        ba, bb = items[a]["box"], items[b]["box"]
        x0, y0 = min(ba[0], bb[0]), min(ba[1], bb[1]); x1, y1 = max(ba[0] + ba[2], bb[0] + bb[2]), max(ba[1] + ba[3], bb[1] + bb[3])
        items[a]["box"] = [x0, y0, x1 - x0, y1 - y0]
        ra, rb = face_x[a], face_x[b]
        row = list(ra); row[0] = (ra[0] + rb[0]) / 2; row[1] = (ra[1] + rb[1]) / 2; row[6] = (ra[6] + rb[6]) / 2; row[7] = (ra[7] + rb[7]) / 2
        # 크기: 같은 울기의 다른 패(가로·세로가 같은 쪽) 중앙값
        same = [face_x[j] for j, it in enumerate(items) if it["role"] == items[a]["role"] and j not in (a, b)]
        if same:
            row[2] = float(np.median([s[2] for s in same])); row[3] = float(np.median([s[3] for s in same])); row[5] = float(row[2] > row[3] * 1.15)
        face_x[a] = row; drop.add(b)
    keep = [i for i in range(nf) if i not in drop]
    added_x = []
    for a in rv.get("add", []):  # 검출기가 놓친 앞면(가림 등) 더하기: 토큰은 like 상자를 복사해 위치·크기만 새 상자로(11-09 144348)
        j = a["like"]; row = list(face_x[j])
        u0, v0, _, _ = img2tok(items[j]["box"], d["size"], d["grid"], d["side"]); u1, v1, bw, bh = img2tok(a["box"], d["size"], d["grid"], d["side"])
        row[0] += u1 - u0; row[1] += v1 - v0; row[6] += u1 - u0; row[7] += v1 - v0
        row[2], row[3], row[5] = bw * 10, bh * 10, float(bw > bh * 1.15)
        added_x.append(row); items.append(dict(box=list(a["box"]), role=a["role"], owner=a.get("owner"))); keep.append(len(items) - 1)
    face_x = face_x + added_x
    items = [items[i] for i in keep]; face_x = [face_x[i] for i in keep]
    fb = [it["box"] for it in items]
    kb = [j for j, b in enumerate(backs) if not overlaps_face(b, fb)]  # 앞면과 겹친 뒷면 상자 버림(133826 같은 경우)
    n_drop_back = len(backs) - len(kb)
    backs = [backs[j] for j in kb]; back_x = [back_x[j] for j in kb]
    y = [ROLES.index(it["role"]) if it["role"] in ROLES else -1 for it in items] + [-1] * len(back_x)
    return dict(side=d["side"], size=d["size"], image=d["image"], kind=d["kind"], source="draft+review", items=items, backs=backs,
                x=face_x + back_x, y=y, n_face=len(items), roles=[it["role"] for it in items] + ["back"] * len(back_x), dropped_backs=n_drop_back)


def from_labels(name, edit=None):
    labels = json.loads((rs.OUT / rs.LABELS).read_text(encoding="utf-8"))
    backs = json.loads(rs.BACKS.read_text(encoding="utf-8")); R = json.loads(rs.RECTS.read_text(encoding="utf-8"))
    grids = {s["name"]: s["grid"] for s in sg.scenes()}
    rec = labels[name]
    edit = edit or {}
    items = [dict(it) for it in rec["items"]]
    for it in items:
        it["owner"] = "winner" if it["role"] in ("hand", "meld", "loose") else None
    for i in edit.get("meld_other", []):
        items[i]["role"] = "meld"; items[i]["owner"] = "other"  # 다른 사람 울기도 울기(11-08 사용자 결정)
    for k, r in edit.get("role", {}).items():
        items[int(k)]["role"] = r
        items[int(k)]["owner"] = "winner" if r in ("hand", "meld", "loose") else items[int(k)].get("owner")
    bk = list(backs.get(name, []))
    for i in edit.get("to_back", []):
        bk.append(items[i]["box"])
    drop = set(edit.get("delete", [])) | set(edit.get("to_back", []))
    items = [it for i, it in enumerate(items) if i not in drop]
    items += [dict(box=a["box"], role="meld" if a["role"] == "meld_other" else a["role"], owner="other" if a["role"] == "meld_other" else None)
              for a in edit.get("add", [])]
    rec = dict(rec, items=items)
    fb = [it["box"] for it in items]; n0 = len(bk)
    bk = [b for b in bk if not overlaps_face(b, fb)]
    x, y = rs.scene_tokens(rec, grids[name], bk, True, "rot", rs.scene_rects(name, R))
    return dict(side=rec["side"], size=rec["size"], image=str(HERE.parent / "visit_20261031" / "captures" / name / "original.jpg"), kind="photo",
                source="labels.json", items=[dict(box=it["box"], role=it["role"], owner=it.get("owner")) for it in rec["items"]], backs=bk, dropped_backs=n0 - len(bk),
                x=[[round(float(v), 5) for v in r] for r in x], y=[int(v) for v in y], n_face=len(rec["items"]),
                roles=[it["role"] for it in rec["items"]] + ["back"] * (len(x) - len(rec["items"])))


COL = {"hand": "blue", "meld": "cyan", "river": "orange", "wall": "red", "pair": "magenta", "loose": "yellow", "other": (90, 90, 90), "back": (90, 90, 90)}


def draw(title, s, font):
    U0, U1, V0, V1, S = -0.45, 1.65, -0.5, 1.45, 170
    Wc, Hc = int((U1 - U0) * S), int((V1 - V0) * S)
    P = lambda u, v: ((u - U0) * S, 30 + (v - V0) * S)
    im = Image.new("RGB", (Wc, Hc + 30), (20, 90, 50)); d = ImageDraw.Draw(im)
    d.rectangle((0, 0, Wc, 28), fill="white"); d.text((5, 3), title, font=font, fill=(0, 0, 0))
    d.rectangle((*P(0, 0), *P(1, 1)), outline="black", width=2)
    nf = s["n_face"]
    for i, (row, lab) in enumerate(zip(s["x"], s["roles"])):
        u, v, w, h = row[0], row[1], row[2] / 10, row[3] / 10
        t = math.atan2(row[9], row[10]) / 2; cs, sn = math.cos(t), math.sin(t)
        pts = [P(u + dx * cs - dy * sn, v + dx * sn + dy * cs) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
        d.polygon(pts, fill=(200, 200, 230) if row[4] else "white", outline=COL[lab], width=1 if lab in ("other", "back") else 3)
        if i < nf and s["items"][i].get("owner") == "other" and lab == "meld":
            d.line([pts[0], pts[2]], fill=COL["meld"], width=2)  # 다른 사람 울기 = 대각선
    for g in s.get("kan_groups", []):  # 깡 묶음 = 분홍 테
        idx = list(g["face_index"]) + [nf + j for j in g["back_index"]]
        ps = [P(s["x"][k][0], s["x"][k][1]) for k in idx]
        x0 = min(p[0] for p in ps) - 12; y0 = min(p[1] for p in ps) - 12; x1 = max(p[0] for p in ps) + 12; y1 = max(p[1] for p in ps) + 12
        d.rectangle((x0, y0, x1, y1), outline=(255, 60, 200), width=3)
    r0 = s["x"][0]; cx, cy = P(r0[0] - r0[6], r0[1] - r0[7]); d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill="black")
    return im


def main():
    D = json.loads((V2 / "draft.json").read_text(encoding="utf-8"))
    RV = json.loads((HERE / "role_v2_review.json").read_text(encoding="utf-8"))
    out = {n: from_labels(n, RV.get("_labels_edits", {}).get(n)) for n in KEEP1031}
    for n, d in D.items():
        out[n] = apply(n, d, RV.get(n, {}))
    for n, groups in RV.get("_kan", {}).items():  # 깡 묶음 표시(역할은 그대로 울기, 뒷면은 뒷면)
        if n.startswith("_") or n not in out:
            continue
        s_ = out[n]; s_["kan_groups"] = []
        for g in groups:
            fi = [i for i, it in enumerate(s_["items"]) if it["box"] in g["faces"]]
            bi = [j for j, b in enumerate(s_["backs"]) if b in g["backs"]]
            assert len(fi) == len(g["faces"]) and len(bi) == len(g["backs"]), (n, fi, bi)
            for i in fi:
                s_["items"][i]["kan"] = len(s_["kan_groups"])
            s_["kan_groups"].append(dict(type=g["type"], owner=g["owner"], face_index=fi, back_index=bi))
    for n, f in RV.get("_flags", {}).items():
        if n in out:
            out[n]["flags"] = f
    (V2 / "labels_v2.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 19)
    groups = [("10-31 쓰기(기존 라벨)", KEEP1031), ("합성으로 살린 7장", [n for n in D if D[n]["kind"] == "composite"]),
              ("라벨만 고쳐 살린 10-31 3장", ["20261031_170105", "20261031_164501", "20261031_171245"]),
              ("11-07 쓰기 22장", [n for n in D if n.startswith("20261107") and D[n]["kind"] == "photo"])]
    for gi, (gname, names) in enumerate(groups):
        cells = []
        for n in names:
            s = out[n]; cnt = {r: s["roles"].count(r) for r in ROLES}
            mo = sum(1 for it in s["items"] if it["role"] == "meld" and it.get("owner") == "other")
            tag = f"{n[2:]} {s['side'][0].upper()} 손{cnt['hand']} 울{cnt['meld'] - mo}+남{mo} 표{cnt['wall']} 짝{cnt['pair']} 떼{cnt['loose']}"
            cells.append(draw(tag, s, font))
        cols = 4; rows = (len(cells) + cols - 1) // cols; cw, ch = cells[0].size
        S = Image.new("RGB", (cols * (cw + 8), 40 + rows * (ch + 8)), "white"); dd = ImageDraw.Draw(S)
        dd.text((8, 8), f"{gname} — 색: 파랑 손패 · 하늘 울기 · 주황 강 · 빨강 패산 위 표시패 · 자홍 탁자 위 짝 · 노랑 떼어 둔 화료패 · 회색 테두리 역할 없음",
                font=ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 22), fill=(0, 0, 0))
        for i, c in enumerate(cells):
            S.paste(c, ((i % cols) * (cw + 8), 40 + (i // cols) * (ch + 8)))
        S.save(OUTD / f"v2_inputs_{gi + 1}.jpg", quality=85)
        print(gname, len(names), S.size)
    tot = {r: sum(s["roles"].count(r) for s in out.values()) for r in ROLES + ["other"]}
    tot["meld 중 다른 사람"] = sum(1 for s in out.values() for it in s["items"] if it["role"] == "meld" and it.get("owner") == "other")
    print("장면", len(out), "역할 합계", tot)


if __name__ == "__main__":
    main()
