"""11-14 매장 실제 대국 자료 목록(2026-11-15, 분류기 크롭 자료 1단계 A).

원자료 `experiments/visit_20261114/captures/` 는 읽기만 한다. 프레임은 zip 을 가리키기만 하고 풀지 않는다(고른 것은 v1114_quality.py 가 푼다).

규칙(사용자가 미리 정함 — 결과를 보고 바꾸지 않는다):
  - 판 = frames.json 의 round_key 가 같은 추적 폴더 묶음. 화료 사진·유국 기록은 meta.game.round(유국은 reveal.round)가 같은 판 중
    첫 프레임 시각이 사진 시각 이하인 가장 늦은 판에 붙인다. 붙을 판이 없으면 사진만으로 된 판을 새로 만든다.
  - 학습/개발: 판을 첫 시각순으로 놓고 2992 프레임 30장 이상인 판만 1번부터 번호 → 4의 배수 번째 = dev, 나머지와 30장 미만 = train.
  - 고름: 판마다 2992 프레임을 시간순 같은 간격으로 최대 8장(마지막 프레임 꼭 포함 — linspace 양 끝), 화료 사진 전부(다시 찍은 것도),
    유국 frame.jpg 는 2992 일 때만.
  - native: 실제로 1496·996 크기로 온 프레임(+ 996 유국 frame.jpg)은 따로 묶음(라벨 없음). 그 밖의 크기(4080×3060)는 목록에만.

  python -X utf8 experiments/tile_classifier/v1114_collect.py
결과 experiments/tile_classifier/data/v1114/manifest.json
"""
from __future__ import annotations

import io
import json
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CAP = ROOT / "experiments" / "visit_20261114" / "captures"
OUT = HERE / "data" / "v1114"
PICK = 8
MIN_FRAMES = 30
NATIVE = {1496: "q1496", 996: "q997"}


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def scan_tracks():
    """추적 폴더 → round_key 별 프레임 목록."""
    by_key: dict[str, dict] = {}
    for d in sorted(CAP.glob("*_track")):
        for z in sorted(d.glob("frames_*.zip")):
            zf = zipfile.ZipFile(z)
            m = json.loads(zf.read("frames.json"))
            key = m["round_key"]
            r = by_key.setdefault(key, {"round_key": key, "track_dirs": [], "frames": [], "grids": []})
            if d.name not in r["track_dirs"]:
                r["track_dirs"].append(d.name)
            if m.get("grid") not in r["grids"]:
                r["grids"].append(m.get("grid"))
            for f in m["frames"]:
                w, h = Image.open(io.BytesIO(zf.read(f["file"]))).size
                r["frames"].append({"kind": "frame", "src_dir": d.name, "zip": z.name, "file": f["file"], "at": f["at"],
                                    "size": [w, h], "why": f.get("why")})
    for r in by_key.values():
        r["frames"].sort(key=lambda f: f["at"])
    return by_key


def round_name(key: str) -> tuple[str, str]:
    """round_key = <반장 id>/<국 이름>/<본장>/<순번>"""
    p = key.split("/")
    return p[0], p[1]


def main():
    by_key = scan_tracks()
    rounds = sorted(by_key.values(), key=lambda r: r["frames"][0]["at"])
    for r in rounds:
        r["game"], r["round"] = round_name(r["round_key"])
        r["first_at"], r["last_at"] = r["frames"][0]["at"], r["frames"][-1]["at"]
        r["wins"], r["draws"] = [], []

    # 화료 사진·유국
    wins, draws = [], []
    for d in sorted(CAP.iterdir()):
        if not d.is_dir() or d.name.endswith("_track"):
            continue
        if d.name.endswith("_draw"):
            rv = json.loads((d / "reveal.json").read_text(encoding="utf-8"))
            at = datetime.strptime(d.name[:15], "%Y%m%d_%H%M%S").isoformat()
            w, h = Image.open(d / "frame.jpg").size
            draws.append({"kind": "draw", "src_dir": d.name, "file": "frame.jpg", "at": at, "size": [w, h], "round_name": rv.get("round"),
                          "revealed": rv.get("revealed")})
        else:
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            w, h = Image.open(d / "original.jpg").size
            g = m.get("game") or {}
            wins.append({"kind": "win", "src_dir": d.name, "file": "original.jpg", "at": m["time"], "size": [w, h],
                         "round_name": g.get("round"), "winner_side": m.get("winner_side"), "error": m.get("error"),
                         "has_label": (d / "label.json").exists(), "layout_mode": m.get("layout_mode"), "grid_src": m.get("grid_src")})

    def attach(item):
        cand = [r for r in rounds if r["round"] == item["round_name"] and r["first_at"] <= item["at"]]
        if not cand:
            return None
        return max(cand, key=lambda r: r["first_at"])

    orphans = []
    for it in wins + draws:
        r = attach(it)
        if r is None:
            orphans.append(it)
        else:
            (r["wins"] if it["kind"] == "win" else r["draws"]).append(it)
    # 붙을 판이 없는 사진: 같은 국 이름끼리 사진만으로 된 판
    extra: dict[str, dict] = {}
    for it in orphans:
        r = extra.setdefault(it["round_name"], {"round_key": None, "game": None, "round": it["round_name"], "track_dirs": [], "frames": [],
                                                "grids": [], "wins": [], "draws": [], "first_at": it["at"], "last_at": it["at"],
                                                "note": "추적 프레임 없음 — 화료/유국 기록만"})
        (r["wins"] if it["kind"] == "win" else r["draws"]).append(it)
        r["first_at"], r["last_at"] = min(r["first_at"], it["at"]), max(r["last_at"], it["at"])
    rounds = sorted(rounds + list(extra.values()), key=lambda r: r["first_at"])

    # 판 id·나눔
    num = 0
    for i, r in enumerate(rounds, 1):
        t = (r["track_dirs"][0][9:15] if r["track_dirs"] else (r["wins"] + r["draws"])[0]["src_dir"][9:15])
        r["id"] = f"r{i:02d}_{t}"
        n2992 = sum(1 for f in r["frames"] if f["size"] == [2992, 2992])
        r["n_2992"] = n2992
        if n2992 >= MIN_FRAMES:
            num += 1
            r["num30"] = num
            r["split"] = "dev" if num % 4 == 0 else "train"
        else:
            r["num30"] = None
            r["split"] = "train"

    # 항목
    items = []
    for r in rounds:
        big = [f for f in r["frames"] if f["size"] == [2992, 2992]]
        if len(big) <= PICK:
            pick = set(range(len(big)))
        else:
            pick = {int(round(x)) for x in np.linspace(0, len(big) - 1, PICK)}
        assert not big or len(big) - 1 in pick
        bi = 0
        for f in r["frames"]:
            w = f["size"][0]
            it = {**f, "round": r["id"], "split": r["split"], "native": None, "selected": False, "other_size": False}
            if f["size"] == [2992, 2992]:
                it["selected"] = bi in pick
                it["pick_index"] = bi
                bi += 1
            elif f["size"][0] == f["size"][1] and w in NATIVE:
                it["native"] = NATIVE[w]
            else:
                it["other_size"] = True
            stem = f["src_dir"][9:15] + "_" + Path(f["file"]).stem
            it["id"] = f"{r['id']}/{stem}"
            it["name"] = stem + ".jpg"
            items.append(it)
        # 화료 사진: 같은 판·이전 사진이 있으면 다시 찍은 것
        prev = None
        r["wins"].sort(key=lambda x: x["at"])
        for wv in r["wins"]:
            it = {**wv, "round": r["id"], "split": r["split"], "native": None, "selected": wv["size"] == [2992, 2992], "other_size": wv["size"] != [2992, 2992],
                  "reshoot_of": prev, "id": f"{r['id']}/win_{wv['src_dir'][9:]}", "name": f"win_{wv['src_dir'][9:]}.jpg"}
            items.append(it)
            prev = prev or wv["src_dir"]
        for dv in r["draws"]:
            sq = dv["size"][0] == dv["size"][1]
            it = {**dv, "round": r["id"], "split": r["split"], "selected": dv["size"] == [2992, 2992],
                  "native": NATIVE.get(dv["size"][0]) if sq and dv["size"][0] in NATIVE else None,
                  "other_size": dv["size"] != [2992, 2992] and not (sq and dv["size"][0] in NATIVE),
                  "id": f"{r['id']}/draw_{dv['src_dir'][9:15]}", "name": f"draw_{dv['src_dir'][9:15]}.jpg"}
            items.append(it)
    # 같은 판 화료 사진 묶음의 정답(다시 찍은 사진은 형제 사진의 label 을 참고만)
    for r in rounds:
        labs = [w["src_dir"] for w in r["wins"] if w["has_label"]]
        r["label_dirs"] = labs
        r["has_label"] = bool(labs)
    for it in items:
        if it["kind"] == "win":
            sib = [d for d in next(r for r in rounds if r["id"] == it["round"])["label_dirs"] if d != it["src_dir"]]
            it["label_sibling"] = sib[-1] if not it["has_label"] and sib else None

    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids)), "id 겹침"
    table = []
    for r in rounds:
        its = [it for it in items if it["round"] == r["id"]]
        table.append({
            "id": r["id"], "game": r["game"], "round_key": r["round_key"], "round": r["round"], "first_at": r["first_at"], "last_at": r["last_at"],
            "track_dirs": r["track_dirs"], "split": r["split"], "num30": r["num30"],
            "frames": len(r["frames"]), "n_2992": r["n_2992"],
            "n_1496": sum(1 for f in r["frames"] if f["size"] == [1496, 1496]), "n_996": sum(1 for f in r["frames"] if f["size"] == [996, 996]),
            "n_other": sum(1 for f in r["frames"] if f["size"] not in ([2992, 2992], [1496, 1496], [996, 996])),
            "wins": [w["src_dir"] for w in r["wins"]], "draws": [d["src_dir"] for d in r["draws"]],
            "has_label": r["has_label"], "label_dirs": r["label_dirs"],
            "selected": sum(1 for it in its if it["selected"]), "grids": len(r["grids"]), "note": r.get("note"),
        })
    cnt = Counter()
    for it in items:
        cnt[(it["kind"], f"{it['size'][0]}x{it['size'][1]}")] += 1
    counts = {
        "by_kind_size": {f"{k}/{s}": n for (k, s), n in sorted(cnt.items())},
        "rounds": len(table), "train_rounds": sum(1 for t in table if t["split"] == "train"), "dev_rounds": sum(1 for t in table if t["split"] == "dev"),
        "frames_by_split": {s: sum(t["frames"] for t in table if t["split"] == s) for s in ("train", "dev")},
        "frames2992_by_split": {s: sum(t["n_2992"] for t in table if t["split"] == s) for s in ("train", "dev")},
        "selected_by_split": {s: sum(1 for it in items if it["selected"] and it["split"] == s) for s in ("train", "dev")},
        "selected_by_kind": dict(Counter(it["kind"] for it in items if it["selected"])),
        "native_by_split": {s: dict(Counter(it["native"] for it in items if it["native"] and it["split"] == s)) for s in ("train", "dev")},
        "other_size": [it["id"] for it in items if it["other_size"]],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    man = {"made": datetime.now().isoformat(timespec="seconds"), "source": rel(CAP),
           "rules": {"pick_per_round": PICK, "split_min_2992_frames": MIN_FRAMES, "dev_every": 4,
                     "qualities": {"q2992": "원본 그대로", "q1496": "2×2 평균(HeadCamera.average2x2), JPEG 85", "q997": "3픽셀 건너뛰기(HeadCamera.subsample step 3, 짝수 내림 → 996), JPEG 75"},
                     "scale": {"q2992": 1.0, "q1496": 0.5, "q997": 1 / 3}},
           "counts": counts, "rounds": table, "items": items}
    (OUT / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False, indent=1))
    print(f"{'판':12s} {'국':10s} {'시각':17s} {'프레임':>5s} {'2992':>5s} {'1496':>4s} {'996':>4s} {'번호':>4s} split 고름 화료 사진 / 정답")
    for t in table:
        print(f"{t['id']:12s} {t['round']:10s} {t['first_at'][11:19]}~{t['last_at'][11:19]} {t['frames']:5d} {t['n_2992']:5d} {t['n_1496']:4d} {t['n_996']:4d} "
              f"{str(t['num30'] or '-'):>4s} {t['split']:5s} {t['selected']:3d}  {','.join(w[9:] for w in t['wins']) or '-'} / {','.join(w[9:] for w in t['label_dirs']) or '-'}"
              f"{'  유국 ' + ','.join(d[9:15] for d in t['draws']) if t['draws'] else ''}")


if __name__ == "__main__":
    main()
