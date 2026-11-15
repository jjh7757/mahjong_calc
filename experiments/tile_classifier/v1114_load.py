"""11-14 매장 세트(data/v1114) 로더(2026-11-15). 기존 학습·평가 스크립트는 고치지 않고 불러 쓰기만 한다.

왜 따로 두나 — 기존 로더로는 그대로 못 읽는다(2026-11-15 로드 확인):
  분류기  train.obb_index 는 data/harvest_obb 경로가 박혀 있고 x["ref"] 로 라벨을 다시 찾는다(v1114 목록엔 ref 없음 → KeyError),
          part 도 bcd/am/pm 이 아니라 train/dev. frame_train.frame_items 는 side·visit·track 칸이 필요하다.
          v1114 크롭은 키우지 않아(긴 변 130/65/43) train.square(줄이기만)에 그대로 넣으면 q1496·q997 패가 128 판에 작게 놓인다 —
          서버 read_small 은 작은 패를 긴 변 96 으로 키워 읽는다 → cls_dataset(small_up=96) 이 같은 방식으로 키운다.
  검출    det/<q>/{train,dev}/{images,labels} + data.yaml = ultralytics 꼴(통째 그림만, 토막 없음). data.yaml 의 path 는 이 PC 절대 경로.
          캐글 커널(det_kernel_r8/train_det_r8.py)은 평평한 images/labels 와 사진 이름 기반 나눔(part(): "r01_…" 은 문자열 비교로 전부 "pm")을
          가정해 그대로는 안 된다. 기존 방식(토막 2040×1530 + 통째)은 det/build_input/ 을 det_build.py 의 OUT 으로 바꿔 쓴다(det_build_input()).
  역할    role_owner_eval.e3_scenes 는 이름별 검출 캐시(det_cache·frames_rects)로 회전 상자를 찾고, e1_scenes 는 바깥 격자 표(rod.grids)를 찾는다
          → v1114 이름은 KeyError. 여기서는 item 의 pts 와 장면 안의 grid 로 서버 roles.tokens 를 직접 부른다.
          ★ 겹 경고: role_v2_train.fold_of("r04_120417/…") 는 "1107pm"/"1107am" 을 돌려준다 — 기존 **시험 겹(1107pm)** 등에 섞인다.
            v1114 장면의 겹은 반드시 role_fold() 로 정한다(v1114 이름이면 늘 "v1114_train"/"v1114_dev").
좌표: 라벨은 2992 원본 픽셀, 다른 화질은 manifest rules.scale(q1496 0.5, q997 1/3)을 곱한다. 격자 grid 는 0~1000(그림에서 짐작한 grid_est, dora 칸 없음).

  python -X utf8 experiments/tile_classifier/v1114_load.py check     # 세 화질 × 세 세트를 실제로 읽어 수를 summary.json 과 맞댐(다르면 종료 코드 1)
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REC))
import train as tr  # noqa: E402  (CLASSES·square·PLAIN·AUG_OBB·AUG_R180 그대로)
from app import roles  # noqa: E402  (tokens·ROLES 읽기만)

try:  # 서버 read_small 의 키우기 기준(= CLS_SIZE*3//4). frame_train.prep 도 이 값을 쓴다.
    from app.local_read import SMALL_TILE  # noqa: E402
except Exception:  # 못 부르면 서버 app/local_read.py 64행 값(CLS_SIZE 128 → 96)
    SMALL_TILE = 96

V = HERE / "data" / "v1114"
QS = ("q2992", "q1496", "q997")
SPLITS = ("train", "dev")
NAME_RE = re.compile(r"^r\d{2}_\d{6}/")
CLASSES = tr.CLASSES
ROLES = list(roles.ROLES)  # hand meld river wall pair loose — role_set.ROLES 와 같은 순서(check 에서 확인)


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 분류기
def cls_items(q: str, split: str, u1: bool = False) -> list[dict]:
    """crops/<q>/{split}[_u1].json → 크롭마다 {path(절대), tile, label(train.CLASSES 번호), id, round, scene_round, unit, rot, turn, w, h, q, split}.
    rot = 크롭을 자른 뒤 돌린 90° 반시계 횟수(초안 분류기가 읽은 방향 — 거꾸로 선 크롭이 섞일 수 있음, 학습은 180° 뒤집기 증강을 쓸 것)."""
    lst = _json(V / "crops" / q / f"{split}{'_u1' if u1 else ''}.json")
    return [{"path": V / "crops" / q / x["file"], "tile": x["tile"], "label": CLASSES.index(x["tile"]), "id": x["id"], "round": x["round"],
             "scene_round": x["scene_round"], "unit": x["unit"], "rot": x["turn"] // 90 % 4, "turn": x["turn"], "w": x["w"], "h": x["h"],
             "q": q, "split": split} for x in lst]


def small_upscale(im: Image.Image, small_up: int | None = SMALL_TILE) -> Image.Image:
    """긴 변이 small_up 보다 작으면 긴 변 small_up 으로 키운다(BICUBIC, 반올림, 최소 1px) — 서버 LocalReader.read_small·frame_train.prep 과 같은 식.
    차이: 서버는 '상자' 긴 변 < 96 일 때 PAD 를 붙인 크롭을 키우고, 여기서는 이미 PAD 를 붙인 '크롭' 긴 변으로 판단한다."""
    if small_up is None or max(im.size) >= small_up:
        return im
    s = small_up / max(im.size)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)


class ClsDataset:
    """torch Dataset 꼴(__len__·__getitem__ → (텐서 3×SIZE×SIZE, 종류 번호)). 그림은 처음에 다 읽어 둔다(가장 큰 q2992 train 도 수십 MB).
    aug: "obb"(= train.AUG_OBB: JPEG 지터·180°·square·증강, train.py --obb 와 같음) · "r180"(square 뒤 train.AUG_R180, frame_train 과 같음) ·
         None/"plain"(square + train.PLAIN, 평가용) · 함수(키운 원래 크기 PIL 을 받아 텐서를 돌려줌)."""

    def __init__(self, items: list[dict], aug="obb", small_up: int | None = SMALL_TILE):
        self.items = items
        self.small_up = small_up
        self.images = [small_upscale(Image.open(x["path"]).convert("RGB"), small_up) for x in items]
        self.aug = aug

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int):
        im = self.images[i]
        a = self.aug
        if a == "obb":
            x = tr.AUG_OBB(im)
        elif a == "r180":
            x = tr.AUG_R180(tr.square(im))
        elif a in (None, "plain"):
            x = tr.PLAIN(tr.square(im))
        else:
            x = a(im)
        return x, self.items[i]["label"]

    def sample_weights(self) -> np.ndarray:
        """train.train() 과 같은 종류 균형 뽑기 확률(1 / 종류 수, 합 1)."""
        freq = Counter(x["tile"] for x in self.items)
        p = np.array([1 / freq[x["tile"]] for x in self.items])
        return p / p.sum()


def cls_dataset(q: str, split: str, aug="obb", small_up: int | None = SMALL_TILE, u1: bool = False) -> ClsDataset:
    """예: ds = cls_dataset("q997", "train"); x, y = ds[0]. 평가는 aug=None. 키우지 않으려면 small_up=None."""
    return ClsDataset(cls_items(q, split, u1), aug, small_up)


# ------------------------------------------------------------------ 검출
def det_dirs(q: str) -> dict:
    """{"train": {"images", "labels"}, "dev": {...}} 절대 경로. 라벨 = YOLO OBB "종류 x1 y1 … x4 y4"(0~1, 0 앞면 · 1 뒷면).
    주의: ultralytics 로 이 폴더를 직접 읽으면 labels/ 옆에 labels.cache 를 쓴다."""
    return {sp: {"images": V / "det" / q / sp / "images", "labels": V / "det" / q / sp / "labels"} for sp in SPLITS}


def det_yaml(q: str, out: str | Path | None = None) -> Path:
    """path 를 det/<q> 의 지금 절대 경로로 다시 쓴 data.yaml 을 out(.yaml 파일 경로, 아니면 폴더로 보고 그 안 data_<q>.yaml)에 써서 경로를 돌려준다.
    out 이 없으면 쓰지 않고 det/<q>/data.yaml 을 돌려준다(그 파일 path 는 만들 때의 이 PC 절대 경로).
    캐글에 올릴 때: det_kernel_r8 은 평평한 images/labels·이름 기반 나눔이라 그대로 안 된다 — 이 yaml 꼴(train/images, dev/images)로 학습 부분을 바꿔야 한다."""
    src = V / "det" / q / "data.yaml"
    if out is None:
        return src
    out = Path(out)
    if out.suffix not in (".yaml", ".yml"):  # 폴더로 봄
        out = out / f"data_{q}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"path: {(V / 'det' / q).resolve().as_posix()}\ntrain: train/images\nval: dev/images\nnames:\n  0: face\n  1: back\n", encoding="utf-8")
    return out


def det_build_input() -> Path:
    """det_build.py --obb --backs 입력(q2992 만): 이 폴더 = det_build 의 OUT(data/det) 과 같은 배치
    (boxes_final.json, backs/r2/boxes_r2fb.json, obb/rects.json, + split.json 은 나눔용 — det_build 는 안 읽음).
    쓰는 법(기존 data/det 에 안 쓰게): sys.argv = ["det_build.py", "--obb", "--backs"]; import det_build as db;
      db.OUT = det_build_input(); db.DS = <출력 폴더>; db.main()  — DS 는 import 때 OUT 기준으로 정해지므로 반드시 같이 바꾼다.
    det_backs.fixed_faces/fixed_backs 의 고침 표(data/det 감사 결과)는 이름이 달라 v1114 상자에 영향 없음. 토막 2040×1530 은 2992² 에 3×3 으로 맞는다."""
    return V / "det" / "build_input"


# ------------------------------------------------------------------ 역할
_SPLIT_OF: dict | None = None


def is_v1114(name: str) -> bool:
    """v1114 장면 이름("r04_120417/120417_f0047_120639", "r04_120417/win_121254")인지."""
    return bool(NAME_RE.match(name))


def _split_of() -> dict:
    global _SPLIT_OF
    if _SPLIT_OF is None:
        _SPLIT_OF = {x["id"]: sp for sp in SPLITS for x in _json(V / "role" / f"labels_{sp}.json")["images"]}
    return _SPLIT_OF


def role_fold(name: str) -> str:
    """겹 이름. v1114 이름이면 늘 "v1114_train"/"v1114_dev"(역할 세트 나눔 그대로).
    ★ role_v2_train.fold_of 에 v1114 이름을 넣지 말 것 — "1107pm"(기존 시험 겹)·"1107am" 으로 잘못 간다. 그 밖의 이름은 fold_of 그대로."""
    if is_v1114(name):
        sp = _split_of().get(name)
        if sp is None:
            raise KeyError(f"v1114 역할 세트에 없는 이름: {name}")
        return f"v1114_{sp}"
    import role_v2_train as t
    return t.fold_of(name)


def _owner(role: str, seat, winner) -> str | None:
    """v1114_dr_role.py 의 화료 사진 규칙: pair·화료자 자리 hand/loose/meld = winner, 남의 hand/loose/meld = other, 그 밖·판 중 = None."""
    if winner is None:
        return None
    if role == "pair" or (role in ("hand", "loose", "meld") and seat == winner):
        return "winner"
    if role in ("hand", "loose", "meld"):
        return "other"
    return None


def _role_idx(role) -> int:
    """ROLES 번호, other·없음 = -1(labels_v2·win_*.json 의 y 와 같음. role_v2_train.load 는 ROLE_OTHER_NEG=1 이면 other 를 -2 로 바꾼다)."""
    return ROLES.index(role) if role in ROLES else -1


def _scene(name, W, H, grid, side, faces, backs, meta) -> dict:
    """faces = [{box, pts, role, seat, owner}], backs = [(box, pts|None)]. x = roles.tokens(…, FEAT_ROT, 앞면 pts, 뒷면) — 앞면 뒤에 뒷면."""
    x = roles.tokens([tuple(f["box"]) for f in faces], W, H, grid, side, roles.FEAT_ROT,
                     [None if f["pts"] is None else np.array(f["pts"], float) for f in faces] if faces else None,
                     [(tuple(b), None if p is None else np.array(p, float)) for b, p in backs])
    y = [_role_idx(f["role"]) for f in faces] + [-1] * len(backs)
    return dict(name=name, W=W, H=H, grid=grid, side=side, x=x, y=y, n_face=len(faces), roles=[f["role"] for f in faces],
                owners=[f.get("owner") for f in faces], seats=[f.get("seat") for f in faces], boxes=[list(f["box"]) for f in faces],
                fold=role_fold(name), **meta)


def role_scenes(split: str, kind: str = "all", side: str | None = None) -> list[dict]:
    """역할 장면 → [{name, W, H, grid, side, x(N×11 토큰), y(역할 번호, 뒷면 -1), n_face, roles, owners, seats, boxes, fold, phase, kind, winner, …}].
    kind "all" = 통합 labels_{split}.json(판 중·화료, 뒷면 회전 꼭짓점 있음), "play" = frames_play_{split}.json(뒷면은 축 상자뿐),
         "win" = win_{split}.json(x 는 저장된 값 — 그 화료자 side 기준, x_rebuilt 에 통합 파일 뒷면 꼭짓점으로 다시 만든 값).
    side: 토큰 기준 자리. 없으면 화료 사진은 화료자 side(labels_v2_owner 와 같음), 그 밖은 "bottom"(= 사진 기준, e3_scenes 와 같음)."""
    out = []
    if kind == "all":
        for im in _json(V / "role" / f"labels_{split}.json")["images"]:
            W, H = im["size"]
            win = im["winner"]
            faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": _owner(it["role"], it["seat"], win)} for it in im["items"]]
            backs = [(b["box"], b["pts"]) for b in im["backs"]]
            sd = side or win or "bottom"
            out.append(_scene(im["id"], W, H, im["grid_est"], sd, faces, backs,
                              {"phase": im["phase"], "kind": im["kind"], "winner": win, "scene_round": im["scene_round"], "image": V / im["paths"]["q2992"],
                               "paths": {q: V / p for q, p in im["paths"].items()}}))
    elif kind == "play":
        for fr in _json(V / "role" / f"frames_play_{split}.json")["frames"]:
            W, H = fr["size"]
            faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": None} for it in fr["items"]]
            out.append(_scene(fr["name"], W, H, fr["grid"], side or "bottom", faces, [(b, None) for b in fr["backs"]],
                              {"phase": fr["phase"], "kind": "frame", "winner": None, "scene_round": fr["round_key"], "image": V / fr["image"],
                               "score": [bool(it.get("score", True)) for it in fr["items"]]}))
    elif kind == "win":
        uni = {x["id"]: x for x in _json(V / "role" / f"labels_{split}.json")["images"]}
        for name, s in _json(V / "role" / f"win_{split}.json").items():
            W, H = s["size"]
            faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": it["owner"]} for it in s["items"]]
            u = uni[name]
            assert [b["box"] for b in u["backs"]] == s["backs"], name
            sd = side or s["side"]
            sc = _scene(name, W, H, s["grid"], sd, faces, [(b["box"], b["pts"]) for b in u["backs"]],
                        {"phase": "end", "kind": "win", "winner": s["side"], "scene_round": u["scene_round"], "image": Path(s["image"])})
            sc["x_rebuilt"] = sc["x"]
            if sd == s["side"]:
                sc["x"] = np.array(s["x"], np.float32)
                sc["y_saved"] = list(s["y"])
            out.append(sc)
    else:
        raise ValueError(kind)
    return out


def role_det_scenes(q: str, split: str, side: str = "bottom", include_unmatched: bool = True) -> list[dict]:
    """det_input/<q>/labels_{split}.json(그 화질에서 운영 검출기 tile-obb-r8 을 돌린 상자에 최종 라벨 역할을 옮긴 것) → role_scenes 와 같은 꼴.
    좌표는 그 화질 픽셀(W,H = 그 그림 크기). include_unmatched: 라벨과 안 맞은 헛검출도 입력에 넣음(앞면 y = -1, roles "unmatched").
    실제 추론 입력처럼 쓰려면 True. 놓친 라벨(missed)은 입력에 없다."""
    d = _json(V / "role" / "det_input" / q / f"labels_{split}.json")
    out = []
    for im in d["images"]:
        W, H = im["size"]
        win = im["winner"]
        faces = [{"box": it["box"], "pts": it["pts"], "role": it["role"], "seat": it["seat"], "owner": _owner(it["role"], it["seat"], win)} for it in im["items"]]
        backs = [(b["box"], b["pts"]) for b in im["backs"]]
        if include_unmatched:
            for e in im["unmatched"]:
                if e["cls"] == "face":
                    faces.append({"box": e["box"], "pts": e["pts"], "role": "unmatched", "seat": None, "owner": None})
                else:
                    backs.append((e["box"], e["pts"]))
        sd = side if side != "winner" else (win or "bottom")
        out.append(_scene(im["id"], W, H, im["grid_est"], sd, faces, backs,
                          {"phase": im["phase"], "kind": im["kind"], "winner": win, "scene_round": im["scene_round"], "q": q,
                           "image": V / "images" / q / split / (im["id"] + ".jpg"), "missed": im["missed"]}))
    return out


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

    import role_set as rs
    want("ROLES 순서 = role_set.ROLES", ROLES, list(rs.ROLES[:6]))
    print("SMALL_TILE", SMALL_TILE)

    # 분류기
    cs = _json(V / "crops" / "summary.json")
    print("== 분류기 크롭")
    for q in QS:
        for sp in SPLITS:
            it = cls_items(q, sp)
            want(f"{q} {sp} 크롭 수", len(it), cs["by_quality_split"][q][sp]["crops"])
            want(f"{q} {sp} 실물 패(unit) 수", len({x["unit"] for x in it}), cs["by_quality_split"][q][sp]["units"])
            want(f"{q} {sp}_u1 수", len(cls_items(q, sp, u1=True)), cs["u1_counts"][q][sp])
            cnt = Counter(x["tile"] for x in it)
            want(f"{q} {sp} 종류별 수 = summary.tiles", {c: cnt.get(c, 0) for c in CLASSES}, {c: cs["tiles"][c][sp] for c in CLASSES})
            print(f"  {q} {sp} 종류 수 {len(cnt)}")
            missing = [x for x in it if not x["path"].exists()]
            want(f"{q} {sp} 없는 그림", len(missing), 0)
        sub = cls_items(q, "dev")[:64]
        for su in (SMALL_TILE, None):
            ds = ClsDataset(sub, aug="obb", small_up=su)
            import torch
            xb = torch.stack([ds[i][0] for i in range(32)])
            longs = [max(im.size) for im in ds.images]
            print(f"  {q} small_up={su}: 넣기 전 긴 변 중앙 {int(np.median(longs))} (최소 {min(longs)}·최대 {max(longs)}), 배치 {tuple(xb.shape)}")
        xp = torch.stack([ClsDataset(sub[:8], aug=None)[i][0] for i in range(8)])
        print(f"  {q} 평가(plain) 배치 {tuple(xp.shape)}")

    # 검출
    dsm = _json(V / "det" / "summary.json")
    print("== 검출")
    for q in QS:
        for sp in SPLITS:
            dd = det_dirs(q)[sp]
            ims = sorted(dd["images"].glob("*.jpg"))
            labs = sorted(dd["labels"].glob("*.txt"))
            want(f"{q} {sp} 그림 수", len(ims), dsm[f"{q}_{sp}_images"])
            want(f"{q} {sp} 라벨 수", len(labs), dsm[f"{q}_{sp}_labels"])
            c = Counter(l.split()[0] for p in labs for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
            want(f"{q} {sp} 앞면·뒷면 줄", (c["0"], c["1"]), (dsm["counts"][f"{sp}_face"], dsm["counts"][f"{sp}_back"]))
    bi = det_build_input()
    want("build_input 배치", sorted(p.relative_to(bi).as_posix() for p in bi.rglob("*.json")),
         ["backs/r2/boxes_r2fb.json", "boxes_final.json", "obb/rects.json", "split.json"])
    try:
        import ultralytics  # noqa: F401
        from torch.utils.data import DataLoader
        from ultralytics.cfg import get_cfg
        from ultralytics.data import build_yolo_dataset
        from ultralytics.data.utils import check_det_dataset
        tmp = Path(tempfile.mkdtemp(prefix="v1114_det_"))
        try:
            for q in QS:
                y = det_yaml(q, tmp / "yaml")
                data = check_det_dataset(str(y))  # 폴더·이름만 확인(캐시 안 씀)
                want(f"{q} data.yaml nc·names", (data["nc"], dict(data["names"])), (2, {0: "face", 1: "back"}))
                # 한 배치는 사본 4장으로(원본 labels/ 에 labels.cache 를 안 쓰게)
                root = tmp / q
                for sp in SPLITS:
                    for d in ("images", "labels"):
                        (root / sp / d).mkdir(parents=True, exist_ok=True)
                    for p in sorted(det_dirs(q)[sp]["images"].glob("*.jpg"))[:4]:
                        shutil.copy(p, root / sp / "images" / p.name)
                        shutil.copy(det_dirs(q)[sp]["labels"] / (p.stem + ".txt"), root / sp / "labels" / (p.stem + ".txt"))
                (root / "data.yaml").write_text(f"path: {root.as_posix()}\ntrain: train/images\nval: dev/images\nnames:\n  0: face\n  1: back\n", encoding="utf-8")
                d2 = check_det_dataset(str(root / "data.yaml"))
                ds = build_yolo_dataset(get_cfg(overrides=dict(task="obb", imgsz=1280, data=str(root / "data.yaml"))), d2["train"], 2, d2, mode="train", rect=False, stride=32)
                b = next(iter(DataLoader(ds, batch_size=2, collate_fn=ds.collate_fn)))
                print(f"  {q} ultralytics OBB 한 배치(사본 4장): img {tuple(b['img'].shape)} 상자 {tuple(b['bboxes'].shape)}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except ImportError:
        print("  ultralytics 없음 — 데이터셋 한 배치는 건너뜀")

    # 역할
    rsm = _json(V / "role" / "summary.json")["counts"]
    print("== 역할")
    role_tot = Counter()
    for sp in SPLITS:
        al = role_scenes(sp, "all")
        want(f"all {sp} 장면", len(al), rsm[f"{sp}_images"])
        want(f"all {sp} phase play/end", (sum(s["phase"] == "play" for s in al), sum(s["phase"] == "end" for s in al)), (rsm[f"{sp}_play"], rsm[f"{sp}_end"]))
        want(f"all {sp} 앞면·뒷면", (sum(s["n_face"] for s in al), sum(len(s["y"]) - s["n_face"] for s in al)), (rsm[f"{sp}_face"], rsm[f"{sp}_back"]))
        want(f"all {sp} 토큰 모양 (N,11)·N=앞+뒤", all(s["x"].shape == (len(s["y"]), 11) for s in al), True)
        want(f"all {sp} 겹", Counter(s["fold"] for s in al), Counter({f"v1114_{sp}": len(al)}))
        role_tot.update(r for s in al for r in s["roles"])
        xs = np.concatenate([s["x"] for s in al])
        print(f"  all {sp} 토큰 u {xs[:, 0].min():.2f}~{xs[:, 0].max():.2f} v {xs[:, 1].min():.2f}~{xs[:, 1].max():.2f} 크기10 중앙 {np.median(xs[:, 2]):.2f}/{np.median(xs[:, 3]):.2f}")
        pl = role_scenes(sp, "play")
        want(f"play {sp} 장면", len(pl), rsm[f"{sp}_frames_play_file"])
        wn = role_scenes(sp, "win")
        want(f"win {sp} 장면", len(wn), rsm[f"{sp}_win_file"])
        dmax = max(float(np.abs(s["x"] - s["x_rebuilt"]).max()) for s in wn)
        want(f"win {sp} 저장 x vs 다시 만든 x 최대차 < 1e-4", dmax < 1e-4, True)
        print(f"    (최대차 {dmax:.2e})")
        want(f"win {sp} 저장 y = 다시 만든 y", all(s["y"] == s["y_saved"] for s in wn), True)
        print(f"  win {sp} 주인", dict(Counter(o for s in wn for o in s["owners"])))
        for q in QS:
            dt = role_det_scenes(q, sp)
            want(f"det_input {q} {sp} 장면", len(dt), rsm[f"{sp}_images"])
            want(f"det_input {q} {sp} 토큰 모양", all(s["x"].shape == (len(s["y"]), 11) for s in dt), True)
            print(f"    det_input {q} {sp} 앞면 {sum(s['n_face'] for s in dt)}(헛검출 {sum(r == 'unmatched' for s in dt for r in s['roles'])}) 뒷면 {sum(len(s['y']) - s['n_face'] for s in dt)}")
    want("역할별 수(학습+개발) = summary role_*", {r: role_tot[r] for r in ROLES + ["other"]}, {r: rsm.get(f"role_{r}", 0) for r in ROLES + ["other"]})
    import role_v2_train as t
    nm = role_scenes("dev", "win")[0]["name"]
    print(f"  겹 경고 확인: role_v2_train.fold_of({nm!r}) = {t.fold_of(nm)!r} ← 쓰지 말 것, role_fold = {role_fold(nm)!r}")
    print("check", "통과" if ok else "실패")
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        sys.exit(0 if check() else 1)
    print(__doc__)
