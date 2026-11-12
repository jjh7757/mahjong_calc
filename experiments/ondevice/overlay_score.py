"""판 중 패 인식 겹쳐 보기(`ondevice.overlay`) 채점(2026-11-11): 표시용으로만 쓰던 답이 얼마나 맞는지 테스트 세트로 잰다.

입력 = 테스트 세트 원본 40장(`seat_grow.eval_scenes()`: B·C·D + 10-31 + 11-07, 가림·사용자 문제 뺌)과 저장 격자. PC 에서 태블릿과 같은
`android/app/src/main/python/ondevice.py` 를 그대로 부른다(재저장 생략 `skip`). 모델은 robust_suite 와 같게 prod(운영 = 태블릿에 든 것) /
fold(그 사진을 안 배운 조합, B·C·D·10-31 만 — 11-07 은 fold 가 없어 운영 모델).

채점:
  ① 장면(화료자 자리, 40장): 겹쳐 보기의 "화료자 자리 hand + loose" 종류가 정답 손패와, "화료자 자리 meld" 가 정답 울기 패와 같은가(여러 장 묶음 비교).
     다른 자리에 뜬 hand(헛 손패)도 센다 — 화료 자동 감지에 쓰려면 0 이어야 한다.
  ② 상자(역할 라벨 v2 가 원본 사진에 달린 장면만): 라벨 상자마다 IoU > 0.5 인 겹쳐 보기 상자를 찾아 역할·주인을 비교. 라벨에 없는 상자는 헛검출 후보.
  ③ 기기 일치(prod 만): 태블릿에서 돌린 `results/overlay_ov1.json`(15:15, 역할 고르기 고치기 전)과 상자·종류를 비교(역할은 규칙이 달라 안 봄).

  python -X utf8 experiments/ondevice/overlay_score.py --models prod|fold --tag <TAG> [--draw] [--scale 2040]
--scale N: 사진을 긴 변 N 으로 면적 평균 줄여(2배면 2×2 평균 = 헤드 녹화와 같음) JPEG 품질 85 로 다시 저장한 뒤 겹쳐 보기(2026-11-12,
  녹화 2040 프레임으로 겹쳐 보기를 돌려도 되는지). 상자는 0~1 비율이라 채점은 그대로.
--small-up(2026-11-12, `docs/cls_2040_plan_1112.md` 0단계 "키워 읽기"): 분류기에 넣는 크롭의 긴 변이 `lr.SMALL_TILE`(96) 미만이면 긴 변 96 으로
  BICUBIC 키운 뒤 분류(서버 `read_small` 과 같은 규칙), 96 이상은 그대로. `ondevice.py` 는 안 고치고 판독기의 `probs` 를 이 스크립트 안에서 감싼다.
--cls-all <onnx>: 11-07 장면과 prod 조합이 쓰는 분류기(`_all`, 운영 = 서버 `tile-cls-mnv3s-v3.onnx`)를 바꿔 끼운다. 없으면 운영 그대로.
  fold 나눔 분류기 계열은 env `ROBUST_CLS`(기본 cls6).
결과 experiments/ondevice/results/overlay_score_<models>_<TAG>.json, 그림 build/overlay_score/<models>/<이름>.jpg(틀린 장면만).
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("ROBUST_CLS", "cls6")  # 운영 분류기 v3 의 나눔
os.environ.setdefault("ROBUST_SEAT", "det_r8")
os.environ.setdefault("ROBUST_ROLE", "tile-roles-v3r15d")  # 운영 역할 모델의 나눔
REPO = os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")
sys.path.insert(0, REPO)
sys.path.append(str(ROOT / "android/app/src/main/python"))
sys.path.insert(0, str(ROOT / "experiments/speed"))
import ondevice  # noqa: E402
import robust_suite as rs  # noqa: E402

RES = ROOT / "experiments/ondevice/results"
LABELS = ROOT / "experiments/tile_classifier/data/role/v2/labels_v2.json"
COL = {"hand": (255, 220, 0), "meld": (255, 80, 200), "river": (80, 200, 255), "wall": (170, 170, 170), "pair": (255, 140, 0), "loose": (0, 255, 120)}


def iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    i = ix * iy
    return i / (aw * ah + bw * bh - i + 1e-12)


def scene_score(tiles: list, s: dict) -> dict:
    side = s["side"]
    hand = [t["t"] for t in tiles if t["r"] == "hand" and t["s"] == side]
    loose = [t["t"] for t in tiles if t["r"] == "loose"]
    meld = [t["t"] for t in tiles if t["r"] == "meld" and t["s"] == side]
    want_meld = rs.meld_tiles(s["melds"])
    have, want = Counter(hand + loose + meld), Counter(s["hand"] + want_meld)
    other = Counter(t["s"] for t in tiles if t["r"] == "hand" and t["s"] != side)
    hand_ok = Counter(hand + loose) == Counter(s["hand"])
    meld_ok = Counter(meld) == Counter(want_meld)
    return {"hand": hand, "loose": loose, "meld": meld, "want_hand": s["hand"], "want_meld": want_meld,
            "hand_ok": hand_ok, "hand_n_ok": len(hand) + len(loose) == len(s["hand"]), "meld_ok": meld_ok, "meld_n_ok": len(meld) == len(want_meld),
            "ok": hand_ok and meld_ok, "hit": sum((have & want).values()), "want": sum(want.values()),
            "other_hand": dict(other), "other_hand_max": max(other.values(), default=0)}


def box_score(tiles: list, lab: dict, side: str) -> dict:
    W, H = lab["size"]
    used, rows, conf = set(), [], Counter()
    for it in lab["items"]:
        x, y, w, h = it["box"]
        lb = [x / W, y / H, w / W, h / H]
        j = max(range(len(tiles)), key=lambda k: iou(lb, tiles[k]["b"]), default=None)
        if j is None or iou(lb, tiles[j]["b"]) <= 0.5:
            rows.append({"box": lb, "want": it["role"], "owner": it["owner"], "got": None})
            conf[(it["role"], "없음")] += 1
            continue
        used.add(j)
        t = tiles[j]
        role_ok = t["r"] == it["role"]
        # 주인: 손패·울기만 본다(화료자 것이면 화료자 자리, 남의 울기면 다른 자리)
        own_ok = role_ok and (it["owner"] is None or it["role"] not in ("hand", "meld") or (t["s"] == side) == (it["owner"] == "winner"))
        conf[(it["role"], t["r"])] += 1
        rows.append({"box": lb, "want": it["role"], "owner": it["owner"], "got": t["r"], "s": t["s"], "t": t["t"], "role_ok": role_ok, "own_ok": own_ok})
    extra = [{"box": t["b"], "t": t["t"], "tc": t["tc"], "r": t["r"], "s": t["s"]} for k, t in enumerate(tiles) if k not in used]
    return {"n": len(rows), "found": sum(r["got"] is not None for r in rows), "role_ok": sum(bool(r.get("role_ok")) for r in rows),
            "own_ok": sum(bool(r.get("own_ok")) for r in rows), "wrong": [r for r in rows if not r.get("own_ok")], "extra": extra,
            "conf": {f"{a}>{b}": n for (a, b), n in conf.items()}}


def parity(tiles: list, dev: list) -> dict:
    same = diff = 0
    for t in tiles:
        j = max(range(len(dev)), key=lambda k: iou(t["b"], dev[k]["b"]), default=None)
        if j is not None and iou(t["b"], dev[j]["b"]) > 0.5:
            same += t["t"] == dev[j]["t"]
            diff += t["t"] != dev[j]["t"]
    return {"pc": len(tiles), "dev": len(dev), "same": same, "diff": diff}


def draw(path: Path, tiles: list, bs: dict | None, out: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    im = Image.open(path).convert("RGB")
    im.thumbnail((2400, 2400))
    W, H = im.size
    d, f = ImageDraw.Draw(im), ImageFont.truetype("arial.ttf", 22)
    for t in tiles:
        x, y, w, h = t["b"]
        c = COL.get(t["r"], (255, 255, 255))
        d.rectangle([x * W, y * H, (x + w) * W, (y + h) * H], outline=c, width=3)
        d.text((x * W, y * H - 24), f"{t['t']} {t['r'][0]}{t['s'][0]}", fill=c, font=f)
    for r in (bs or {}).get("wrong", []):  # 라벨과 다른 상자: 빨강 + 정답 역할
        x, y, w, h = r["box"]
        d.rectangle([x * W - 4, y * H - 4, (x + w) * W + 4, (y + h) * H + 4], outline=(255, 0, 0), width=4)
        d.text((x * W, (y + h) * H + 2), f"={r['want']}{'/' + r['owner'] if r['owner'] else ''}", fill=(255, 0, 0), font=f)
    for r in (bs or {}).get("extra", []):  # 라벨에 없는 상자: 흰 점선 대신 굵은 흰 테두리
        x, y, w, h = r["box"]
        d.rectangle([x * W - 4, y * H - 4, (x + w) * W + 4, (y + h) * H + 4], outline=(255, 255, 255), width=2)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=85)


def shrink(data: bytes, long_side: int) -> tuple[bytes, tuple[int, int]]:
    """긴 변 [long_side] 로 면적 평균 줄이기(정수 배면 Image.reduce = n×n 평균, 아니면 BOX). JPEG 품질 85."""
    import io
    from PIL import Image, ImageOps

    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    k = max(im.size) / long_side
    if k > 1:
        im = im.reduce(round(k)) if abs(k - round(k)) < 0.05 else im.resize((round(im.width / k), round(im.height / k)), Image.BOX)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), im.size


def small_up(reader) -> None:
    """키워 읽기: 판독기의 probs 를 감싸 긴 변 SMALL_TILE 미만 크롭을 긴 변 SMALL_TILE 로 BICUBIC 키운다. 같은 판독기는 한 번만 감싼다."""
    from PIL import Image

    from app import local_read as lr

    if getattr(reader, "_small_up", False):
        return
    orig = reader.probs

    def probs(ims):
        out = []
        for im in ims:
            if max(im.size) < lr.SMALL_TILE:
                s = lr.SMALL_TILE / max(im.size)
                im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BICUBIC)
            out.append(im)
        return orig(out)

    reader.probs = probs
    reader._small_up = True


class ScoreReaders(rs.Readers):
    """rs.Readers + `--cls-all`: prod 판독기(11-07 장면·prod 조합)의 분류기만 바꿔 끼운다."""

    def __init__(self, models: str, threads: int, cls_all: str | None):
        super().__init__(models, threads)
        self.cls_all = Path(cls_all).resolve() if cls_all else None
        if self.cls_all is not None and not self.cls_all.exists():
            raise SystemExit(f"분류기 없음: {self.cls_all}")

    def get(self, name: str):
        is_prod = self.models == "prod" or not name.startswith(("k", "2026103"))
        if self.cls_all is not None and is_prod and ("prod",) not in self.cache:
            self.cache[("prod",)] = (self.lr.LocalReader(threads=self.threads, cls_model=self.cls_all), self.roles.RoleNet(self.roles.ROLE_MODEL, threads=self.threads))
        rn, files = super().get(name)
        if self.cls_all is not None and is_prod:
            files = {**files, "cls": self.cls_all.name}
        return rn, files


def summary(rows: dict) -> dict:
    out = {}
    for key in ("all", "bcd", "visit", "visit1107"):
        rr = [r for r in rows.values() if key == "all" or r["set"] == key]
        if not rr:
            continue
        bs = [r["box"] for r in rr if r.get("box")]
        conf = Counter()
        for b in bs:
            conf.update(b["conf"])
        out[key] = {"scenes": len(rr), "ok": sum(r["ok"] for r in rr), "hand_ok": sum(r["hand_ok"] for r in rr), "hand_n_ok": sum(r["hand_n_ok"] for r in rr),
                    "meld_ok": sum(r["meld_ok"] for r in rr), "meld_n_ok": sum(r["meld_n_ok"] for r in rr),
                    "hit": sum(r["hit"] for r in rr), "want": sum(r["want"] for r in rr),
                    "other_hand_scenes": sum(r["other_hand_max"] > 0 for r in rr), "other_hand_5plus": sum(r["other_hand_max"] >= 5 for r in rr),
                    "box_scenes": len(bs), "box_n": sum(b["n"] for b in bs), "box_found": sum(b["found"] for b in bs), "box_role_ok": sum(b["role_ok"] for b in bs),
                    "box_own_ok": sum(b["own_ok"] for b in bs), "box_extra": sum(len(b["extra"]) for b in bs),
                    "conf_wrong": {k: n for k, n in sorted(conf.items(), key=lambda kv: -kv[1]) if k.split(">")[0] != k.split(">")[1]}}
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, choices=["prod", "fold"])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--draw", action="store_true")
    ap.add_argument("--scale", type=int, default=0)
    ap.add_argument("--small-up", action="store_true", help="긴 변 SMALL_TILE(96) 미만 크롭을 키워 읽기")
    ap.add_argument("--cls-all", default=None, help="11-07·prod 가 쓰는 _all 분류기 onnx(없으면 운영 그대로)")
    a = ap.parse_args()
    from app import roles

    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    dev_p = RES / "overlay_ov1.json"
    dev = {i["name"]: i["res"]["tiles"] for i in json.loads(dev_p.read_text(encoding="utf-8"))["items"] if i["res"]} if dev_p.exists() else {}
    rd = ScoreReaders(a.models, a.threads, a.cls_all)
    rows = {}
    for s in rs.scenes("dev"):
        (reader, net), files = rd.get(s["name"])
        if a.small_up:
            small_up(reader)  # 캐시된 판독기는 한 번만 감싼다
        ondevice._reader = reader  # overlay 가 쓰는 판독기·역할 모델을 이 장면 것으로
        roles.role_net = lambda net=net: net
        g = {k: str(s["grid"][k]) for k in ("x1", "x2", "y1", "y2")}
        t0 = time.perf_counter()
        data = Path(s["path"]).read_bytes()
        if a.scale:
            data, scaled = shrink(data, a.scale)
        o = json.loads(ondevice.overlay(data, g))
        r = {"set": s["set"], "side": s["side"], "models": files, "n": len(o["tiles"]), "secs": round(time.perf_counter() - t0, 2), **scene_score(o["tiles"], s), "tiles": o["tiles"]}
        lab = labels.get(s["name"])
        if lab and Path(lab["image"]).resolve() == Path(s["path"]).resolve():
            r["box"] = box_score(o["tiles"], lab, s["side"])
        if a.models == "prod" and s["name"] in dev:
            r["parity"] = parity(o["tiles"], dev[s["name"]])
        rows[s["name"]] = r
        b = r.get("box")
        print(f"{s['name'][-6:]:>6s} {s['side']:6s} {'O' if r['ok'] else 'X'} 손패 {'O' if r['hand_ok'] else 'X'} 울기 {'O' if r['meld_ok'] else 'X'} {r['hit']}/{r['want']}"
              f" 헛손패 {r['other_hand'] or '-'}" + (f" 상자 {b['own_ok']}/{b['n']} 못찾음 {b['n'] - b['found']} 라벨밖 {len(b['extra'])}" if b else "")
              + ("" if r["ok"] else f"\n       손패+떼어둔 {' '.join(sorted(r['hand'] + r['loose']))} | 정답 {' '.join(sorted(r['want_hand']))}"
                 f"\n       울기 {' '.join(sorted(r['meld']))} | 정답 {' '.join(sorted(r['want_meld']))}"), flush=True)
        if a.draw and (not r["ok"] or r["other_hand"] or (b and (b["wrong"] or b["extra"]))):
            draw(Path(s["path"]), o["tiles"], b, ROOT / f"experiments/ondevice/build/overlay_score/{a.models}/{s['name']}.jpg")
    sm = summary(rows)
    par = [r["parity"] for r in rows.values() if r.get("parity")]
    if par:
        sm["parity"] = {"scenes": len(par), "pc": sum(p["pc"] for p in par), "dev": sum(p["dev"] for p in par), "same": sum(p["same"] for p in par), "diff": sum(p["diff"] for p in par)}
    sm["scale"] = a.scale
    out = RES / f"overlay_score_{a.models}_{a.tag}.json"
    out.write_text(json.dumps({"_meta": {"models": a.models, "recognizer": rs.git_sha(), "at": time.strftime("%Y-%m-%d %H:%M:%S"), "prep": ondevice.PREP,
                                        "small_up": a.small_up, "cls_all": str(rd.cls_all) if rd.cls_all else None, "ROBUST_CLS": rs.CLS_TAG}, "summary": sm, "scenes": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(sm, ensure_ascii=False, indent=1))
    print("→", out)


if __name__ == "__main__":
    main()
