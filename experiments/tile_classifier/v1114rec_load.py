"""11-14 헤드 녹화 프레임 세트(data/v1114rec, 화질 rec1496) 로더(2026-11-15). v1114_load.py 와 같은 쓰임새·같은 함수 이름 꼴.
기존 학습·평가 스크립트(train.py·role_v2_train.py 등)와 v1114_load.py 는 고치지 않고 불러 쓰기만 한다.

세트: 그림 세 갈래(part) — pair = 기존 v1114 189장과 같은 순간의 녹화 프레임(186장, 라벨은 기존 것 ×0.5) · mid = 기존 판 안 새 순간(49장) ·
  new = 녹화만 있는 판 n01~n08(72장). 좌표는 모두 녹화 원래 픽셀 1496(기존 v1114 는 2992 — 섞으려면 기존 좌표 × 0.5).
  나눔은 탁자 장면(scene_round) 기준이고 기존 v1114 와 같은 규칙(pair 는 기존 split_final 그대로) — 두 세트를 합쳐도 같은 scene_round 는 한쪽에만
  (data/v1114rec/summary.json split_with_v1114).

★ 이름 겹침: pair 그림 이름은 v1114 와 **같다**("r04_120417/120417_f0047_120639", "r04_120417/win_121254" — 같은 순간의 녹화 프레임).
  mid 는 "r04_120417/mid_<ms>", new 는 "n03_150528/new_<ms>". 그래서 v1114_load.role_fold(pair 이름) 은 "v1114_*" 를, 이 모듈 role_fold 는
  "v1114rec_*" 를 돌려준다(split 은 같다). 두 세트 장면을 한 목록에 섞을 때는 이름만으로 어느 세트인지 알 수 없으니 장면의 fold 칸(만들 때 정해짐)을 쓰고,
  같은 이름 = 같은 순간이라 한쪽만 쓸지(중복) 정할 것. 검출 그림 파일 이름(<판>__<그림>.jpg)도 pair 는 기존 det 과 같다.
★ 겹 경고: role_v2_train.fold_of 는 r##·n## 이름을 기존 겹(1107pm 시험 겹 등)으로 보낸다 — 이 세트 장면의 겹은 반드시 role_fold() 로.
분류기: 크롭은 키우지 않아 긴 변 약 65px(48~85) — v1114_load 의 q1496 과 같이 cls_dataset(small_up=96) 이 서버 read_small 처럼 키운다.
  part 칸: 목록 파일 칸 part 는 split(기존 꼴), 갈래는 rec_part. 여기 items 에서는 part = 갈래(pair|mid|new), split = train|dev.
  pair 와 mid 는 같은 판·같은 탁자라 같은 실물 패가 두 unit 으로 들어간다(크롭 summary limits).
역할: role_scenes(drop_pre_game=True) 면 pair 의 강 0장(pre_game) 그림도 걸러 mid·new 와 같은 기준이 된다(mid·new 는 이미 뺐다).
  앞면 tile = 패 종류(pair 기존 값 · mid·new 크롭 세트 확정 라벨, 없으면 None), tile_src = v1114|crops|None.

  python -X utf8 experiments/tile_classifier/v1114rec_load.py check     # 세 세트를 실제로 읽어 수를 summary 들과 맞댐(다르면 종료 코드 1)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import v1114_load as vl  # noqa: E402  (ClsDataset·small_upscale·SMALL_TILE·_scene 꼴·roles 를 그대로 씀)
from v1114_load import SMALL_TILE, ClsDataset, roles  # noqa: E402,F401

R = HERE / "data" / "v1114rec"
Q = "rec1496"
SPLITS = ("train", "dev")
PARTS = ("pair", "mid", "new")
NAME_RE = re.compile(r"^(r|n)\d{2}_\d{6}/")
CLASSES = vl.CLASSES
ROLES = vl.ROLES


def _json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _parts(parts) -> tuple:
    parts = (parts,) if isinstance(parts, str) else tuple(parts)
    assert set(parts) <= set(PARTS), parts
    return parts


# ------------------------------------------------------------------ 분류기
def cls_items(split: str, parts=PARTS, u1: bool = False) -> list[dict]:
    """crops/rec1496/{split}[_u1].json → 크롭마다 {path(절대), tile, label(train.CLASSES 번호), id, part(pair|mid|new), round, scene_round, unit,
    rot, turn, w, h, q, split, v1114_crop_id}. rot = 자른 뒤 돌린 90° 반시계 횟수(분류기가 읽은 방향 — 거꾸로 선 크롭이 섞일 수 있음, 180° 증강을 쓸 것).
    u1 = 실물 패(unit)당 한 장(녹화 크롭이 가장 또렷한 것). _u1 은 part 마다 따로 골랐다(pair·mid 의 같은 패가 두 장일 수 있음)."""
    parts = _parts(parts)
    lst = _json(R / "crops" / Q / f"{split}{'_u1' if u1 else ''}.json")
    return [{"path": R / "crops" / Q / x["file"], "tile": x["tile"], "label": CLASSES.index(x["tile"]), "id": x["id"], "part": x["rec_part"],
             "round": x["round"], "scene_round": x["scene_round"], "unit": x["unit"], "rot": x["turn"] // 90 % 4, "turn": x["turn"],
             "w": x["w"], "h": x["h"], "q": Q, "split": split, "v1114_crop_id": x.get("v1114_crop_id")} for x in lst if x["rec_part"] in parts]


def cls_dataset(split: str, aug="obb", small_up: int | None = SMALL_TILE, u1: bool = False, parts=PARTS) -> ClsDataset:
    """예: ds = cls_dataset("train"); x, y = ds[0]. 평가는 aug=None. 키우지 않으려면 small_up=None. aug 는 v1114_load.ClsDataset 과 같음."""
    return ClsDataset(cls_items(split, parts, u1), aug, small_up)


# ------------------------------------------------------------------ 검출
def det_dirs() -> dict:
    """{"train": {"images", "labels"}, "dev": {...}} 절대 경로(det/rec1496). 라벨 = YOLO OBB "종류 x1 y1 … x4 y4"(0~1, 0 앞면 · 1 뒷면).
    파일 이름 = <판>__<그림 이름>.jpg(pair 는 기존 v1114 det 과 같은 이름). 갈래는 이름으로: n## = new, "__mid_" = mid, 그 밖 = pair.
    주의: ultralytics 로 이 폴더를 직접 읽으면 labels/ 옆에 labels.cache 를 쓴다."""
    return {sp: {"images": R / "det" / Q / sp / "images", "labels": R / "det" / Q / sp / "labels"} for sp in SPLITS}


def det_part(stem: str) -> str:
    return "new" if stem.startswith("n") else ("mid" if "__mid_" in stem else "pair")


def det_yaml(out: str | Path | None = None) -> Path:
    """out 이 없으면 det/rec1496/data.yaml(path 는 만들 때의 이 PC 절대 경로)을 돌려준다. out(.yaml 파일 또는 폴더 → data_rec1496.yaml)이 있으면
    path 를 지금 절대 경로로 다시 쓴 yaml 을 써서 돌려준다. 기존 det_build.py --obb --backs 입력 꼴(build_input)은 이 세트에 없다(det/summary.json build_input)."""
    src = R / "det" / Q / "data.yaml"
    if out is None:
        return src
    out = Path(out)
    if out.suffix not in (".yaml", ".yml"):
        out = out / f"data_{Q}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"path: {(R / 'det' / Q).resolve().as_posix()}\ntrain: train/images\nval: dev/images\nnames:\n  0: face\n  1: back\n", encoding="utf-8")
    return out


# ------------------------------------------------------------------ 역할
_SPLIT_OF: dict | None = None


def is_v1114rec(name: str) -> bool:
    """이 세트 꼴 이름인지(r##_… 또는 n##_…). pair 이름은 v1114 와 같으니 이것만으로 세트를 가를 수 없다(머리말)."""
    return bool(NAME_RE.match(name))


def _split_of() -> dict:
    global _SPLIT_OF
    if _SPLIT_OF is None:
        _SPLIT_OF = {x["id"]: sp for sp in SPLITS for x in _json(R / "role" / f"labels_{sp}.json")["images"]}
    return _SPLIT_OF


def role_fold(name: str) -> str:
    """겹 이름. 이 세트 역할 장면 이름이면 늘 "v1114rec_train"/"v1114rec_dev".
    r##·n## 꼴인데 이 세트에 없는 이름은 KeyError(role_v2_train.fold_of 로 보내면 기존 겹에 섞이므로). 그 밖의 이름은 fold_of 그대로."""
    if is_v1114rec(name):
        sp = _split_of().get(name)
        if sp is None:
            raise KeyError(f"v1114rec 역할 세트에 없는 이름: {name}")
        return f"v1114rec_{sp}"
    import role_v2_train as t
    return t.fold_of(name)


def _scene(name, W, H, grid, side, faces, backs, meta) -> dict:
    """v1114_load._scene 과 같은 계산(그쪽은 겹을 v1114_load.role_fold 로 정해 mid·new 이름에서 KeyError 라 여기서 다시 씀)."""
    x = roles.tokens([tuple(f["box"]) for f in faces], W, H, grid, side, roles.FEAT_ROT,
                     [None if f["pts"] is None else np.array(f["pts"], float) for f in faces] if faces else None,
                     [(tuple(b), None if p is None else np.array(p, float)) for b, p in backs])
    y = [vl._role_idx(f["role"]) for f in faces] + [-1] * len(backs)
    return dict(name=name, W=W, H=H, grid=grid, side=side, x=x, y=y, n_face=len(faces), roles=[f["role"] for f in faces],
                owners=[f.get("owner") for f in faces], seats=[f.get("seat") for f in faces], boxes=[list(f["box"]) for f in faces],
                tiles=[f.get("tile") for f in faces], tile_srcs=[f.get("tile_src") for f in faces], fold=role_fold(name), **meta)


def role_scenes(split: str, kind: str = "all", parts=PARTS, drop_pre_game: bool = False, side: str | None = None) -> list[dict]:
    """역할 장면 → [{name, W, H, grid, side, x(N×11 토큰), y(역할 번호, 뒷면 -1), n_face, roles, owners, seats, boxes, tiles, tile_srcs, fold,
    part, phase, kind, winner, pre_game, …}]. kind "all" = labels_{split}.json, "play" = frames_play_{split}.json(뒷면은 축 상자뿐),
    "win" = win_{split}.json(화료 사진 pair + new 공개 장면; x 는 저장 값, x_rebuilt 에 다시 만든 값). side 는 v1114_load.role_scenes 와 같음.
    drop_pre_game: pair 의 pre_game(판 중·강 앞면 0) 그림도 뺀다(mid·new 는 이미 빠져 있음)."""
    parts = _parts(parts)
    out = []
    if kind == "all":
        for im in _json(R / "role" / f"labels_{split}.json")["images"]:
            if im["part"] not in parts or (drop_pre_game and im["pre_game"]):
                continue
            W, H = im["size"]
            win = im["winner"]
            faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": vl._owner(it["role"], it["seat"], win),
                      "tile": it.get("tile"), "tile_src": it.get("tile_src")} for it in im["items"]]
            backs = [(b["box"], b["pts"]) for b in im["backs"]]
            out.append(_scene(im["id"], W, H, im["grid_est"], side or win or "bottom", faces, backs,
                              {"part": im["part"], "phase": im["phase"], "kind": im["kind"], "format": im["format"], "winner": win,
                               "pre_game": im["pre_game"], "between": im["between"], "scene_round": im["scene_round"], "image": R / im["image"]}))
    elif kind == "play":
        for fr in _json(R / "role" / f"frames_play_{split}.json")["frames"]:
            if fr["part"] not in parts or (drop_pre_game and fr["pre_game"]):
                continue
            W, H = fr["size"]
            faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": None,
                      "tile": it.get("tile"), "tile_src": it.get("tile_src")} for it in fr["items"]]
            out.append(_scene(fr["name"], W, H, fr["grid"], side or "bottom", faces, [(b, None) for b in fr["backs"]],
                              {"part": fr["part"], "phase": fr["phase"], "kind": "frame", "winner": None, "pre_game": fr["pre_game"],
                               "between": fr["between"], "scene_round": fr["round_key"], "image": R / fr["image"],
                               "score": [bool(it.get("score", True)) for it in fr["items"]]}))
    elif kind == "win":
        uni = {x["id"]: x for x in _json(R / "role" / f"labels_{split}.json")["images"]}
        for name, s in _json(R / "role" / f"win_{split}.json").items():
            u = uni[name]
            if s["part"] not in parts or (drop_pre_game and u["pre_game"]):
                continue
            W, H = s["size"]
            faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": it["owner"],
                      "tile": it.get("tile"), "tile_src": it.get("tile_src")} for it in s["items"]]
            assert [b["box"] for b in u["backs"]] == s["backs"], name
            sd = side or s["side"]
            sc = _scene(name, W, H, s["grid"], sd, faces, [(b["box"], b["pts"]) for b in u["backs"]],
                        {"part": s["part"], "phase": "end", "kind": s["kind"], "winner": s["side"], "pre_game": u["pre_game"],
                         "scene_round": u["scene_round"], "image": Path(s["image"])})
            sc["x_rebuilt"] = sc["x"]
            if sd == s["side"]:
                sc["x"] = np.array(s["x"], np.float32)
                sc["y_saved"] = list(s["y"])
            out.append(sc)
    else:
        raise ValueError(kind)
    return out


def role_det_scenes(split: str, side: str = "bottom", include_unmatched: bool = True, parts=PARTS, drop_pre_game: bool = False) -> list[dict]:
    """role/det_input/rec1496/labels_{split}.json(녹화 프레임에서 운영 검출기 tile-obb-r8 을 돌린 상자에 최종 라벨 역할을 옮긴 것) → role_scenes 꼴.
    include_unmatched: 라벨과 안 맞은 헛검출도 입력에 넣음(앞면 y = -1, roles "unmatched"). 놓친 라벨(missed)은 입력에 없다. tile 은 없다(None)."""
    parts = _parts(parts)
    img = {x["id"]: x for sp in SPLITS for x in _json(R / "role" / f"labels_{sp}.json")["images"]}
    out = []
    for im in _json(R / "role" / "det_input" / Q / f"labels_{split}.json")["images"]:
        u = img[im["id"]]
        if im["part"] not in parts or (drop_pre_game and u["pre_game"]):
            continue
        W, H = im["size"]
        win = im["winner"]
        faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": vl._owner(it["role"], it["seat"], win)}
                 for it in im["items"]]
        backs = [(b["box"], b["pts"]) for b in im["backs"]]
        if include_unmatched:
            for e in im["unmatched"]:
                if e["cls"] == "face":
                    faces.append({"box": e["box"], "pts": e["pts"], "role": "unmatched", "seat": None, "owner": None})
                else:
                    backs.append((e["box"], e["pts"]))
        sd = side if side != "winner" else (win or "bottom")
        out.append(_scene(im["id"], W, H, im["grid_est"], sd, faces, backs,
                          {"part": im["part"], "phase": im["phase"], "kind": im["kind"], "winner": win, "pre_game": u["pre_game"],
                           "scene_round": im["scene_round"], "q": Q, "image": R / u["image"], "missed": im["missed"]}))
    return out


# ------------------------------------------------------------------ 기존 세트와 함께 쓸 때의 나눔
def split_with_v1114() -> dict:
    """data/v1114(기존)와 data/v1114rec 를 합쳐 학습·개발을 만들 때 같은 탁자 장면(scene_round)이 양쪽 split 에 걸리는지.
    두 세트의 모든 그림 목록(기존: manifest 의 고른 그림·dr/final·crops·role, 녹화: manifest·pairs·dr/final*·crops·role)을 scene_round 로 모아
    split 이 둘 이상인 scene_round 를 센다(0 이어야 함). 판(round) 단위로도 센다(판 첫 그림이 앞 판 탁자면 scene_round 가 앞 판이라 판과 다를 수 있음)."""
    V = vl.V
    rows = []  # (세트, 출처, 그림 id, round, scene_round, split)

    def add(src, name, iid, rnd, sc, sp):
        if sc is not None:
            rows.append((src, name, iid, rnd or iid.split("/", 1)[0], sc, sp))

    for it in _json(V / "manifest.json")["items"]:
        if it.get("scene_round"):
            add("v1114", "manifest", it["id"], it["round"], it["scene_round"], it["split_final"])
    for p in sorted((V / "dr" / "final").glob("r*.json")):
        for im in _json(p)["images"]:
            add("v1114", "dr_final", im["id"], None, im["scene_round"], im["split_final"])
    for x in _json(V / "crops" / "index.json"):
        add("v1114", "crops", x["image"], x["round"], x["scene_round"], x["split"])
    for sp in SPLITS:
        for im in _json(V / "role" / f"labels_{sp}.json")["images"]:
            add("v1114", "role", im["id"], None, im["scene_round"], sp)
    for it in _json(R / "manifest.json")["items"]:
        add("v1114rec", "manifest", it["id"], it["round"], it["scene_round"], it["split"])
    for p in _json(R / "pair" / "pairs.json")["pairs"]:
        add("v1114rec", "pairs", p["id"], p["round"], p["scene_round"], p["split_final"])
    for d in ("final", "final_pair"):
        for p in sorted((R / "dr" / d).glob("[nr]*.json")):
            for im in _json(p)["images"]:
                add("v1114rec", "dr_" + d, im["id"], None, im["scene_round"], im["split_final"])
    for x in _json(R / "crops" / "index.json"):
        add("v1114rec", "crops", x["image"], x["round"], x["scene_round"], x["split"])
    for sp in SPLITS:
        for im in _json(R / "role" / f"labels_{sp}.json")["images"]:
            add("v1114rec", "role", im["id"], None, im["scene_round"], sp)
    sc_sp, rd_sp, sc_set = {}, {}, {}
    for st, src, iid, rnd, sc, sp in rows:
        sc_sp.setdefault(sc, set()).add(sp)
        rd_sp.setdefault(rnd, set()).add(sp)
        sc_set.setdefault(sc, set()).add(st)
    same_id_diff_split = {}
    for st, src, iid, rnd, sc, sp in rows:
        same_id_diff_split.setdefault(iid, set()).add(sp)
    shared = sorted(s for s, v in sc_sp.items() if len(v) > 1)
    return {"rows": len(rows), "rows_by_set_source": dict(Counter(f"{r[0]}|{r[1]}" for r in rows)),
            "scene_rounds": len(sc_sp), "scene_rounds_in_both_sets": sum(len(v) == 2 for v in sc_set.values()),
            "scene_rounds_v1114_only": sorted(s for s, v in sc_set.items() if v == {"v1114"}),
            "scene_rounds_v1114rec_only": sorted(s for s, v in sc_set.items() if v == {"v1114rec"}),
            "scene_round_split": {s: sorted(v)[0] if len(v) == 1 else sorted(v) for s, v in sorted(sc_sp.items())},
            "scene_round_shared_across_split": shared, "scene_round_shared_count": len(shared),
            "rounds_spanning_split": sorted(r for r, v in rd_sp.items() if len(v) > 1),
            "image_ids_with_two_splits": sorted(i for i, v in same_id_diff_split.items() if len(v) > 1)}


# ------------------------------------------------------------------ 자가 점검
def check() -> bool:
    import shutil
    import tempfile

    ok = True

    def want(tag, got, exp):
        nonlocal ok
        good = got == exp
        ok &= good
        print(("  ok " if good else "  실패 ") + f"{tag}: {got}" + ("" if good else f" (기대 {exp})"))

    print("SMALL_TILE", SMALL_TILE)
    # 분류기
    cs = _json(R / "crops" / "summary.json")
    print("== 분류기 크롭 (rec1496)")
    import torch
    for sp in SPLITS:
        for part in PARTS:
            it = cls_items(sp, (part,))
            want(f"{part} {sp} 크롭 수", len(it), cs["by_part_split"][part][sp]["crops"])
            want(f"{part} {sp} 실물 패(unit) 수", len({x["unit"] for x in it}), cs["by_part_split"][part][sp]["units"])
        it = cls_items(sp)
        want(f"all {sp} 크롭 수", len(it), cs["by_part_split"]["all"][sp]["crops"])
        want(f"all {sp} unit 수", len({x["unit"] for x in it}), cs["by_part_split"]["all"][sp]["units"])
        want(f"{sp}_u1 수", len(cls_items(sp, u1=True)), cs["u1_counts"][sp])
        cnt = Counter(x["tile"] for x in it)
        want(f"{sp} 종류별 수 = summary.tiles", {c: cnt.get(c, 0) for c in CLASSES}, {c: cs["tiles"][c][sp] for c in CLASSES})
        want(f"{sp} 없는 그림", sum(not x["path"].exists() for x in it), 0)
        print(f"  {sp} 종류 수 {len(cnt)} · 적5 0m {cnt.get('0m', 0)} 0p {cnt.get('0p', 0)} 0s {cnt.get('0s', 0)}")
    sub = cls_items("dev")[:64]
    for su in (SMALL_TILE, None):
        ds = ClsDataset(sub, aug="obb", small_up=su)
        xb = torch.stack([ds[i][0] for i in range(32)])
        longs = [max(im.size) for im in ds.images]
        print(f"  small_up={su}: 넣기 전 긴 변 중앙 {int(np.median(longs))} (최소 {min(longs)}·최대 {max(longs)}), 배치 {tuple(xb.shape)}")
        if su:
            want("small_up=96 이면 긴 변 모두 96 이상", min(longs) >= su, True)
    xp = torch.stack([ClsDataset(sub[:8], aug=None)[i][0] for i in range(8)])
    print(f"  평가(plain) 배치 {tuple(xp.shape)}")
    want("cls_dataset 길이 = cls_items", len(cls_dataset("dev", aug=None, parts=("new",))), cs["by_part_split"]["new"]["dev"]["crops"])

    # 검출
    dsm = _json(R / "det" / "summary.json")
    print("== 검출 (det/rec1496)")
    for sp in SPLITS:
        dd = det_dirs()[sp]
        ims = sorted(dd["images"].glob("*.jpg"))
        labs = sorted(dd["labels"].glob("*.txt"))
        want(f"{sp} 그림 수", len(ims), dsm[f"rec1496_{sp}_images"])
        want(f"{sp} 라벨 수", len(labs), dsm[f"rec1496_{sp}_labels"])
        want(f"{sp} 그림 ↔ 라벨 이름", [p.stem for p in ims], [p.stem for p in labs])
        c = Counter()
        bad = 0
        for p in labs:
            pt = det_part(p.stem)
            c[(pt, "images")] += 1
            for ln in p.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                v = ln.split()
                bad += len(v) != 9 or not all(0.0 <= float(z) <= 1.0 for z in v[1:])
                c[(pt, "face" if v[0] == "0" else "back")] += 1
        want(f"{sp} 줄 꼴(9칸·0~1)", bad, 0)
        want(f"{sp} 앞면·뒷면 줄", (sum(c[(p, 'face')] for p in PARTS), sum(c[(p, 'back')] for p in PARTS)),
             (dsm["counts"][f"{sp}_face"], dsm["counts"][f"{sp}_back"]))
        for pt in PARTS:
            want(f"{pt} {sp} 그림·앞면·뒷면", (c[(pt, "images")], c[(pt, "face")], c[(pt, "back")]),
                 tuple(dsm["by_part_split"][f"{pt}_{sp}"][k] for k in ("images", "face", "back")))
    y0 = det_yaml().read_text(encoding="utf-8")
    want("data.yaml path = det/rec1496", f"path: {(R / 'det' / Q).as_posix()}" in y0, True)
    try:
        import ultralytics  # noqa: F401
        from torch.utils.data import DataLoader
        from ultralytics.cfg import get_cfg
        from ultralytics.data import build_yolo_dataset
        from ultralytics.data.utils import check_det_dataset
        tmp = Path(tempfile.mkdtemp(prefix="v1114rec_det_"))
        try:
            data = check_det_dataset(str(det_yaml(tmp / "yaml")))
            want("data.yaml nc·names", (data["nc"], dict(data["names"])), (2, {0: "face", 1: "back"}))
            root = tmp / "copy"
            for sp in SPLITS:
                for d in ("images", "labels"):
                    (root / sp / d).mkdir(parents=True, exist_ok=True)
                for p in sorted(det_dirs()[sp]["images"].glob("*.jpg"))[:4]:
                    shutil.copy(p, root / sp / "images" / p.name)
                    shutil.copy(det_dirs()[sp]["labels"] / (p.stem + ".txt"), root / sp / "labels" / (p.stem + ".txt"))
            (root / "data.yaml").write_text(f"path: {root.as_posix()}\ntrain: train/images\nval: dev/images\nnames:\n  0: face\n  1: back\n", encoding="utf-8")
            d2 = check_det_dataset(str(root / "data.yaml"))
            ds = build_yolo_dataset(get_cfg(overrides=dict(task="obb", imgsz=1280, data=str(root / "data.yaml"))), d2["train"], 2, d2,
                                    mode="train", rect=False, stride=32)
            b = next(iter(DataLoader(ds, batch_size=2, collate_fn=ds.collate_fn)))
            print(f"  ultralytics OBB 한 배치(사본 4장): img {tuple(b['img'].shape)} 상자 {tuple(b['bboxes'].shape)}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except ImportError:
        print("  ultralytics 없음 — 데이터셋 한 배치는 건너뜀")

    # 역할
    rs = _json(R / "role" / "summary.json")
    rsm = rs["counts"]
    print("== 역할")
    role_tot = Counter()
    for sp in SPLITS:
        al = role_scenes(sp, "all")
        want(f"all {sp} 장면", len(al), rsm[f"{sp}_images"])
        for pt in PARTS:
            want(f"all {pt} {sp} 장면", sum(s["part"] == pt for s in al), rsm.get(f"{pt}_{sp}_images", 0))
        want(f"all {sp} phase play/end", (sum(s["phase"] == "play" for s in al), sum(s["phase"] == "end" for s in al)), (rsm[f"{sp}_play"], rsm[f"{sp}_end"]))
        want(f"all {sp} 앞면·뒷면", (sum(s["n_face"] for s in al), sum(len(s["y"]) - s["n_face"] for s in al)), (rsm[f"{sp}_face"], rsm[f"{sp}_back"]))
        want(f"all {sp} 토큰 모양 (N,11)·N=앞+뒤", all(s["x"].shape == (len(s["y"]), 11) for s in al), True)
        want(f"all {sp} 겹", Counter(s["fold"] for s in al), Counter({f"v1114rec_{sp}": len(al)}))
        for pt in PARTS:
            tf = rs["tile_fill"][f"{pt}_{sp}"]
            got = sum(t is not None for s in al if s["part"] == pt for t in s["tiles"])
            want(f"all {pt} {sp} tile 채움", (got, sum(s["n_face"] for s in al if s["part"] == pt)), (tf["filled"], tf["faces"]))
            print(f"    ({pt} {sp} tile 채움 {tf['rate'] * 100:.2f}%)")
        role_tot.update(r for s in al for r in s["roles"])
        npg = len(role_scenes(sp, "all", drop_pre_game=True))
        want(f"all {sp} drop_pre_game 뺀 수 = pair pre_game 남은 수", len(al) - npg, rsm.get(f"pair_{sp}_pre_game_kept", 0))
        pl = role_scenes(sp, "play")
        want(f"play {sp} 장면", len(pl), rsm[f"{sp}_frames_play_file"])
        want(f"play {sp} tile = all 의 같은 장면 tile",
             all(s["tiles"] == next(a for a in al if a["name"] == s["name"])["tiles"] for s in pl), True)
        wn = role_scenes(sp, "win")
        want(f"win {sp} 장면", len(wn), rsm[f"{sp}_win_file"])
        if wn:
            dmax = max(float(np.abs(s["x"] - s["x_rebuilt"]).max()) for s in wn)
            want(f"win {sp} 저장 x vs 다시 만든 x 최대차 < 1e-4", dmax < 1e-4, True)
            want(f"win {sp} 저장 y = 다시 만든 y", all(s["y"] == s["y_saved"] for s in wn), True)
            print(f"  win {sp} 주인", dict(Counter(o for s in wn for o in s["owners"])), "갈래", dict(Counter(s["part"] for s in wn)))
        dt = role_det_scenes(sp)
        want(f"det_input {sp} 장면", len(dt), rsm[f"{sp}_images"])
        want(f"det_input {sp} 토큰 모양", all(s["x"].shape == (len(s["y"]), 11) for s in dt), True)
        print(f"    det_input {sp} 앞면 {sum(s['n_face'] for s in dt)}(헛검출 {sum(r == 'unmatched' for s in dt for r in s['roles'])}) "
              f"뒷면 {sum(len(s['y']) - s['n_face'] for s in dt)}")
    want("역할별 수(학습+개발) = summary role_*", {r: role_tot[r] for r in ROLES + ["other"]}, {r: rsm.get(f"role_{r}", 0) for r in ROLES + ["other"]})
    import role_v2_train as t
    for nm in (role_scenes("dev", "win", parts=("pair",))[0]["name"], role_scenes("train", "all", parts=("new",))[0]["name"]):
        print(f"  겹 경고 확인: role_v2_train.fold_of({nm!r}) = {t.fold_of(nm)!r} ← 쓰지 말 것, role_fold = {role_fold(nm)!r}")
    pn = role_scenes("dev", "win", parts=("pair",))[0]["name"]
    try:
        print(f"  이름 겹침 확인: v1114_load.role_fold({pn!r}) = {vl.role_fold(pn)!r} · 이 모듈 = {role_fold(pn)!r}")
    except KeyError as e:
        print("  이름 겹침 확인: v1114 역할 세트에 없음", e)
    print("== 기존 v1114 와 합칠 때 나눔")
    sw = split_with_v1114()
    want("두 세트 scene_round 가 학습·개발에 함께 걸린 수", sw["scene_round_shared_count"], 0)
    want("같은 그림 id 가 두 split", len(sw["image_ids_with_two_splits"]), 0)
    print(f"  scene_round {sw['scene_rounds']}(두 세트 모두 {sw['scene_rounds_in_both_sets']}) · 판이 두 split 에 걸친 것 {sw['rounds_spanning_split']}")
    print("check", "통과" if ok else "실패")
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        sys.exit(0 if check() else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "splits":
        print(json.dumps(split_with_v1114(), ensure_ascii=False, indent=1))
        sys.exit(0)
    print(__doc__)
