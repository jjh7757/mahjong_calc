"""11-14 자료 라벨 초안(2026-11-15, 1단계 C). v1114_collect.py·v1114_quality.py 다음에.

고른 2992 그림(프레임·화료 사진)마다:
  검출 = 격자 없이 사진 전체 회전 상자 검출(`LocalReader.detect_full`, ondevice.overlay 와 같은 검출) — 2반장(13:07~14:27)은 저장 격자가
         실제 탁자와 어긋나 있어서 격자를 전혀 쓰지 않는다. 안깡 뒷면 상자(`obb.is_kan_back`)는 앞면이 아니라 뺀다.
  분류 = 운영 분류기(서버 기본 `tile-cls-mnv3s-v3.onnx`), 회전 상자로 세운 크롭(`lr.cut`) → 상자 모양에 맞는 방향 후보 중 확신이 가장 높은 것
         (overlay·read_any2 와 같은 규칙). 크롭 긴 변이 96 미만이면 긴 변 96 으로 BICUBIC 키워 읽음(cls_2040_plan 의 키워 읽기 정의).
  실물 패 = 같은 판 안 그림들을 시간순으로 놓고, 그림 사이 카메라 밀림(상자 중심 차의 최빈값)을 뺀 뒤 중심 거리 < 패 짧은 변 × 0.5 인
         앞 실물 패에 잇는다(욕심 매칭, 가까운 쌍부터). 못 이으면 새 실물 패.
  실물 패 초안 = 읽기의 확신도 합 투표. 표시: split(그림마다 1순위가 갈림), low(투표 이긴 종류의 평균 확신 < LOW).
  화료 사진 정답 대조(label.json 이 그 사진에 있거나, 같은 판 다른 사진에 있으면 sibling 으로 참고만):
    - 사진 단위 모자람: 정답(손패+울기+표시패, 4장 울기는 2장만 보여도 되게)의 종류별 수 > 사진 초안 종류별 수 → 종류 목록
    - 상자 단위 어긋남: 화료 사진에서 7장 이상 나란히 붙은 패 줄(펼친 손패 후보, 강 한 줄은 6장)의 초안 종류가 정답 손패+울기+뒷도라보다
      많으면 그 수만큼(확신 낮은 것부터) 상자에 label_mismatch. 정답으로 덮어쓰지 않는다.
      (처음엔 "화료 사진에서 처음 보인 실물 패" 로 잡았는데, 마지막 프레임이 이미 손패를 펼친 뒤라 0장이 나와서 줄 찾기로 바꿈.)
  카메라 밀림은 받쳐 주는 상자가 4개 미만이거나 양쪽 상자 수 작은 쪽의 30% 미만이면 0 으로 본다.
  python -X utf8 experiments/tile_classifier/v1114_draft.py [판 id ...]
결과 data/v1114/draft/<판 id>.json, data/v1114/draft/_summary.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
from app import local_read as lr  # noqa: E402
from app import obb  # noqa: E402

sys.path.insert(0, str(HERE))
from v1114_split import image_rel  # noqa: E402

CAP = ROOT / "experiments" / "visit_20261114" / "captures"
OUT = HERE / "data" / "v1114"
LOW = 0.8
LINK = 0.5  # 중심 거리 / 패 짧은 변
MAX_SHIFT = 400  # 그림 사이 카메라 밀림 찾는 범위(px, 2992 기준)
MIN_SUPPORT = 4
EXPIRE = 2  # 실물 패를 이을 때 마지막으로 보인 뒤 몇 장까지 기다리나
SCALE_TOL = 0.06
MOVE_BREAK = 0.5  # 그림 사이 밀림이 패 짧은 변의 이 배수를 넘으면 잇지 않음
HAND_RUN = 7  # 화료 사진에서 이만큼 이상 나란히 붙은 패 줄 = 펼친 손패 후보(강 한 줄은 6장)


def runs(boxes: list[dict]) -> list[list[int]]:
    """나란히 붙은 패 줄(축 상자 기준): 짧은 변 방향으로 0.7~1.35 짧은 변만큼, 긴 변 방향으로 0.35 긴 변 안에 있는 이웃끼리 묶음."""
    n = len(boxes)
    par = list(range(n))

    def f(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    geo = []
    for b in boxes:
        x, y, w, h = b["box"]
        geo.append((x + w / 2, y + h / 2, w < h, min(w, h), max(w, h)))
    for i in range(n):
        for j in range(i + 1, n):
            a, c = geo[i], geo[j]
            if a[2] != c[2]:
                continue
            s, L = (a[3] + c[3]) / 2, (a[4] + c[4]) / 2
            dx, dy = abs(a[0] - c[0]), abs(a[1] - c[1])
            ds, dl = (dx, dy) if a[2] else (dy, dx)
            if 0.7 * s <= ds <= 1.35 * s and dl < 0.35 * L:
                par[f(i)] = f(j)
    g: dict = {}
    for i in range(n):
        g.setdefault(f(i), []).append(i)
    return sorted(g.values(), key=len, reverse=True)


def sharp(im: Image.Image) -> float:
    y = np.asarray(im.convert("L"), np.float32)
    if y.shape[0] < 3 or y.shape[1] < 3:
        return 0.0
    lap = y[1:-1, 2:] + y[1:-1, :-2] + y[2:, 1:-1] + y[:-2, 1:-1] - 4 * y[1:-1, 1:-1]
    return float(lap.var())


def read_image(reader: lr.LocalReader, path: Path) -> list[dict]:
    jpeg = path.read_bytes()
    out = []
    with obb.session():
        rgb = lr.decode_rgb(jpeg)
        boxes = reader.detect_full(jpeg, rgb)
        crops, owner = [], []
        info = []
        for b in boxes:
            if obb.is_kan_back(b):
                continue
            im = lr.cut(rgb, b)
            if max(im.size) < lr.SMALL_TILE:
                s = lr.SMALL_TILE / max(im.size)
                im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)
            ts = (0, 2) if b[3] > 1.15 * b[2] else (1, 3) if b[2] > 1.15 * b[3] else (0, 1, 2, 3)
            k0 = len(info)
            rect = obb.rect_of(rgb, b)
            info.append({"b": b, "rect": rect, "det": obb.score_of(rgb, b), "ts": ts, "sharp": sharp(im)})
            for k in ts:
                crops.append(im.rotate(90 * k, expand=True))
                owner.append((k0, k))
        best: dict = {}
        for s in range(0, len(crops), 64):
            p = reader.probs(crops[s:s + 64])
            for j, row in enumerate(p):
                i, k = owner[s + j]
                if i not in best or row.max() > best[i][0].max():
                    best[i] = (row, k)
    for i, d in enumerate(info):
        row, k = best[i]
        t, c, t2, c2 = lr.top2(row)
        rc = d["rect"]
        out.append({"i": i, "box": [int(v) for v in d["b"]],
                    "rect": [[round(float(rc[0][0]), 1), round(float(rc[0][1]), 1)], [round(float(rc[1][0]), 1), round(float(rc[1][1]), 1)], round(float(rc[2]), 2)] if rc is not None else None,
                    "det": None if d["det"] is None else round(float(d["det"]), 3), "t": t, "c": c, "t2": t2, "c2": c2, "rot": k, "sharp": round(d["sharp"], 1)})
    return out


def center(b) -> tuple[float, float]:
    return b[0] + b[2] / 2, b[1] + b[3] / 2


def shift_between(prev: np.ndarray, cur: np.ndarray, tile: float) -> tuple[float, float, int]:
    """앞 실물 패 위치들(prev N×2)과 이 그림 상자 중심(cur M×2) 사이의 카메라 밀림. 중심 차를 패 반 크기 칸으로 세어 최빈 칸 → 그 칸 둘레 중앙값."""
    if len(prev) == 0 or len(cur) == 0:
        return 0.0, 0.0, 0
    d = (cur[:, None, :] - prev[None, :, :]).reshape(-1, 2)
    d = d[(np.abs(d) < MAX_SHIFT).all(1)]
    if len(d) == 0:
        return 0.0, 0.0, 0
    bw = tile / 2
    keys = np.floor(d / bw).astype(int)
    cnt = Counter(map(tuple, keys))
    # 이웃 칸까지 더한 수로
    score = {k: sum(cnt.get((k[0] + a, k[1] + b), 0) for a in (-1, 0, 1) for b in (-1, 0, 1)) for k in cnt}
    kbest = max(score, key=score.get)
    zero = max((score.get(k, 0) for k in ((0, 0), (-1, 0), (0, -1), (-1, -1))), default=0)
    if zero >= 0.8 * score[kbest]:
        sel = (np.abs(d) < bw * 1.5).all(1)
    else:
        c = (np.array(kbest) + 0.5) * bw
        sel = (np.abs(d - c) < bw * 1.5).all(1)
    if sel.sum() < max(MIN_SUPPORT, 0.3 * min(len(prev), len(cur))):
        return 0.0, 0.0, int(sel.sum())  # 받쳐 주는 상자가 적으면 밀림 없음으로
    m = np.median(d[sel], axis=0)
    return float(m[0]), float(m[1]), int(sel.sum())


def link(images: list[dict]) -> list[dict]:
    """시간순 그림들의 상자를 실물 패로 잇는다. images[k]["boxes"][j]["track"] 를 채우고 tracks 를 돌려준다."""
    tracks: list[dict] = []
    last_size = [None]
    for k, img in enumerate(images):
        bs = img["boxes"]
        tile = float(np.median([min(b["box"][2], b["box"][3]) for b in bs])) if bs else 70.0
        # 바로 앞 EXPIRE 장 안에 보인 실물 패만 잇는다(판 첫 프레임에 남은 앞 판 패가 이번 판 같은 자리 패와 이어지던 것 막기)
        live = [ti for ti, t in enumerate(tracks) if t["apps"][-1][0] >= k - EXPIRE]
        if k > 0 and images[k - 1].get("prev_round_scene") and not img.get("prev_round_scene"):
            live = []  # 앞 판 탁자 → 이번 판 탁자로 넘어가는 곳은 잇지 않는다
            img["scene_break"] = True
        # 카메라 줌·높이가 바뀌어 패 크기가 달라졌으면(앞 그림과 중앙 긴 변 6% 넘게 차이) 잇지 않는다(11-14 12:55~12:58 카메라 옮김)
        size = float(np.median([max(b["box"][2], b["box"][3]) for b in bs])) if len(bs) >= 5 else None
        if size is not None and last_size[0] is not None and abs(size / last_size[0] - 1) > SCALE_TOL:
            live = []
            img["scale_break"] = round(size / last_size[0], 3)
        if size is not None:
            last_size[0] = size
        prev = np.array([tracks[ti]["pos"] for ti in live]) if live else np.zeros((0, 2))
        cur = np.array([center(b["box"]) for b in bs]) if bs else np.zeros((0, 2))
        dx, dy, sup = shift_between(prev, cur, tile)
        img["shift"] = [round(dx, 1), round(dy, 1), sup]
        if (dx * dx + dy * dy) ** 0.5 > MOVE_BREAK * tile:
            # 카메라가 크게 밀렸으면 잇지 않는다: 강 패가 패 간격으로 늘어서 있어 밀림 최빈값이 한 칸 어긋나 엉뚱한 패끼리 이어졌다(r08 12:57)
            live = []
            img["move_break"] = True
            dx = dy = 0.0
        img["n_boxes"] = len(bs)
        pairs = []
        for j, b in enumerate(bs):
            cx, cy = center(b["box"])
            lim = LINK * min(b["box"][2], b["box"][3])
            for ti in live:
                t = tracks[ti]
                dd = ((cx - dx - t["pos"][0]) ** 2 + (cy - dy - t["pos"][1]) ** 2) ** 0.5
                if dd < lim:
                    pairs.append((dd, j, ti))
        pairs.sort()
        used_b, used_t = set(), set()
        for dd, j, ti in pairs:
            if j in used_b or ti in used_t:
                continue
            used_b.add(j)
            used_t.add(ti)
            bs[j]["track"] = tracks[ti]["tid"]
        # 이 그림 기준으로 모든 실물 패 위치를 옮긴다(카메라 밀림 누적)
        for t in tracks:
            t["pos"] = (t["pos"][0] + dx, t["pos"][1] + dy)
        for j, b in enumerate(bs):
            if j in used_b:
                t = next(t for t in tracks if t["tid"] == b["track"])
                t["pos"] = center(b["box"])
                t["apps"].append((k, j))
            else:
                tid = f"{len(tracks) + 1:03d}"
                tracks.append({"tid": tid, "pos": center(b["box"]), "apps": [(k, j)]})
                b["track"] = tid
    return tracks


def label_expect(lab: dict) -> tuple[Counter, Counter]:
    """(사진에 보여야 할 종류 수 — 4장 울기는 2장, 손패·울기·뒷도라 묶음)."""
    vis, hand = Counter(), Counter()
    for t in lab.get("closed", []):
        vis[t] += 1
        hand[t] += 1
    for m in lab.get("melds", []):
        ts = re.findall(r"[0-9][mpsz]", m)
        for i, t in enumerate(ts):
            hand[t] += 1
            if len(ts) < 4 or i < 2:
                vis[t] += 1
    for t in lab.get("dora_indicators", []) + lab.get("ura_indicators", []):
        vis[t] += 1
    for t in lab.get("ura_indicators", []):
        hand[t] += 1
    return vis, hand


def mark_prev_scene(prev: dict | None, images: list[dict], split: str) -> list[dict]:
    """이 판 고른 그림의 앞쪽이 바로 앞 판의 마지막 그림(대개 화료 사진)과 같은 탁자인가(판 첫 프레임은 앞 판 화료 직후라 탁자가 아직 안 치워짐):
    같은 자리(밀림 뺀 중심 거리 < LINK·짧은 변)에 같은 초안 종류인 상자가 그 그림 상자의 절반 이상이고 10개 이상이면 표시.
    앞에서부터 처음 아닌 그림이 나오면 멈춘다. 빼지 않고 그림에 prev_round_scene 만 단다."""
    out = []
    if not prev or not prev["last"]["boxes"]:
        return out
    last = prev["last"]
    pa = np.array([center(x["box"]) for x in last["boxes"]])
    for im in images:
        if im["kind"] != "frame" or len(im["boxes"]) < 10:
            break
        cur = np.array([center(x["box"]) for x in im["boxes"]])
        tile = float(np.median([min(x["box"][2], x["box"][3]) for x in im["boxes"]]))
        dx, dy, _ = shift_between(pa, cur, tile)
        same = 0
        for x in im["boxes"]:
            cx, cy = center(x["box"])
            lim = LINK * min(x["box"][2], x["box"][3])
            for y in last["boxes"]:
                yx, yy = center(y["box"])
                if ((cx - dx - yx) ** 2 + (cy - dy - yy) ** 2) ** 0.5 < lim and y["t"] == x["t"]:
                    same += 1
                    break
        if not (same >= 10 and same >= 0.5 * len(im["boxes"])):
            break
        im["prev_round_scene"] = {"round": prev["round"], "image": last["id"], "same": same, "of": len(im["boxes"]), "cross_split": prev["split"] != split}
        out.append({"image": im["id"], "split": split, "prev_round": prev["round"], "prev_split": prev["split"], "prev_image": last["id"],
                    "same": same, "of": len(im["boxes"])})
    return out


def main():
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    want = set(sys.argv[1:])
    reader = lr.LocalReader(threads=4)
    (OUT / "draft").mkdir(parents=True, exist_ok=True)
    summary = {"model": {"det": Path(reader.seat_model).name, "cls": Path(reader.cls_model).name}, "low": LOW, "link": LINK, "rounds": {}}
    t_all = time.time()
    summary["prev_round_scene"] = []
    order = [r["id"] for r in man["rounds"]]
    prev = None
    for ri, r in enumerate(man["rounds"]):
        if want and r["id"] not in want:
            prev = None
            continue
        its = sorted([it for it in man["items"] if it["round"] == r["id"] and it["selected"]], key=lambda it: it["at"])
        if not its:
            continue
        t0 = time.time()
        images = []
        for it in its:
            p = OUT / image_rel(it, "q2992")  # v1114_split.py 뒤면 옮긴 자리
            images.append({"id": it["id"], "name": it["name"], "kind": it["kind"], "at": it["at"], "src": it["src_dir"],
                           "path": p.relative_to(OUT).as_posix(), "boxes": read_image(reader, p),
                           "reshoot_of": it.get("reshoot_of"), "has_label": it.get("has_label", False), "label_sibling": it.get("label_sibling")})
        if prev is None and ri > 0:
            pp = OUT / "draft" / f"{order[ri - 1]}.json"
            if pp.exists():
                pd = json.loads(pp.read_text(encoding="utf-8"))
                prev = {"round": pd["round"], "split": pd["split"], "last": pd["images"][-1]}
        prs = mark_prev_scene(prev, images, r["split"])
        summary["prev_round_scene"] += prs
        tracks = link(images)
        prev = {"round": r["id"], "split": r["split"], "last": images[-1]}
        win_k = {k for k, im in enumerate(images) if im["kind"] == "win"}
        out_tracks = []
        for t in tracks:
            reads = [images[k]["boxes"][j] for k, j in t["apps"]]
            votes = Counter()
            for b in reads:
                votes[b["t"]] += b["c"]
            draft = max(votes, key=votes.get)
            win_reads = [b["c"] for b in reads if b["t"] == draft]
            best_k, best_j = max(t["apps"], key=lambda kj: images[kj[0]]["boxes"][kj[1]]["sharp"])
            tops = Counter(b["t"] for b in reads)
            out_tracks.append({"tid": t["tid"], "draft": draft, "share": round(votes[draft] / sum(votes.values()), 3),
                               "conf": round(float(np.mean(win_reads)), 3), "n": len(reads), "reads": dict(tops),
                               "split": len(tops) > 1, "low": float(np.mean(win_reads)) < LOW,
                               "first": images[t["apps"][0][0]]["id"], "last": images[t["apps"][-1][0]]["id"],
                               "only_win": all(k in win_k for k, _ in t["apps"]),
                               "prev_round_scene": all(images[k].get("prev_round_scene") for k, _ in t["apps"]),
                               "best": {"image": images[best_k]["id"], "i": best_j},
                               "apps": [{"image": images[k]["id"], "i": j} for k, j in t["apps"]], "label_mismatch": []})
        by_tid = {t["tid"]: t for t in out_tracks}
        checks = []
        for k in sorted(win_k):
            im = images[k]
            src = im["src"] if im["has_label"] else im["label_sibling"]
            if not src:
                continue
            lab = json.loads((CAP / src / "label.json").read_text(encoding="utf-8"))
            vis, hand = label_expect(lab)
            got = Counter(b["t"] for b in im["boxes"])
            missing = {t: n - got.get(t, 0) for t, n in vis.items() if n > got.get(t, 0)}
            rs = [r_ for r_ in runs(im["boxes"]) if len(r_) >= HAND_RUN]
            new = [im["boxes"][i] for r_ in rs for i in r_]
            newc = Counter(b["t"] for b in new)
            excess = {t: n - hand.get(t, 0) for t, n in newc.items() if n > hand.get(t, 0)}
            marked = []
            for t, n in excess.items():
                for b in sorted([b for b in new if b["t"] == t], key=lambda b: b["c"])[:n]:
                    b["label_mismatch"] = True
                    marked.append(b["i"])
                    by_tid[b["track"]]["label_mismatch"].append({"image": im["id"], "i": b["i"], "draft": t, "label_src": "own" if im["has_label"] else "sibling",
                                                                 "why": "화료 사진의 긴 패 줄(펼친 손패 후보)에 있는데 정답 손패·울기에 이 종류가 모자람"})
            checks.append({"image": im["id"], "label_src": "own" if im["has_label"] else "sibling", "label_dir": src,
                           "label_tiles": {"closed": lab.get("closed"), "melds": lab.get("melds"), "dora": lab.get("dora_indicators"), "ura": lab.get("ura_indicators")},
                           "hand_runs": [len(r_) for r_ in rs], "hand_run_draft": dict(newc), "missing_in_photo": missing, "excess_in_runs": excess,
                           "marked_boxes": marked})
        cnt = {"images": len(images), "boxes": sum(len(im["boxes"]) for im in images), "tracks": len(out_tracks),
               "split_tracks": sum(t["split"] for t in out_tracks), "low": sum(t["low"] for t in out_tracks),
               "label_mismatch_tracks": sum(bool(t["label_mismatch"]) for t in out_tracks),
               "label_mismatch_boxes": sum(len(t["label_mismatch"]) for t in out_tracks),
               "missing_in_photo": sum(sum(c["missing_in_photo"].values()) for c in checks),
               "single": sum(t["n"] == 1 for t in out_tracks), "prev_round_scene_tracks": sum(t["prev_round_scene"] for t in out_tracks),
               "prev_round_scene_cross_split_tracks": sum(t["prev_round_scene"] for t in out_tracks
                                                          if images[0].get("prev_round_scene", {}).get("cross_split")),
               "sec": round(time.time() - t0, 1)}
        res = {"round": r["id"], "split": r["split"], "round_name": r["round"], "model": summary["model"], "low": LOW, "link": LINK,
               "counts": cnt, "label_checks": checks, "tracks": out_tracks, "images": images}
        (OUT / "draft" / f"{r['id']}.json").write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
        summary["rounds"][r["id"]] = {"split": r["split"], **cnt}
        print(r["id"], r["split"], cnt, [im["shift"] for im in images], flush=True)
    if not want:
        tot = Counter()
        for v in summary["rounds"].values():
            for k in ("images", "boxes", "tracks", "split_tracks", "low", "label_mismatch_tracks", "label_mismatch_boxes", "missing_in_photo", "single",
                      "prev_round_scene_tracks", "prev_round_scene_cross_split_tracks"):
                tot[(v["split"], k)] += v[k]
        summary["by_split"] = {s: {k: tot[(s, k)] for (ss, k) in tot if ss == s} for s in ("train", "dev")}
        summary["sec"] = round(time.time() - t_all, 1)
        (OUT / "draft" / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(summary["by_split"], ensure_ascii=False))


if __name__ == "__main__":
    main()
