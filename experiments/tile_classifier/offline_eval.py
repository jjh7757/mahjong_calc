"""촬영 기록(<시각>/original.jpg + meta.json)을 노트북에서 자체 모델로 읽어 Gemini 답과 나란히 남긴다(2026-11-02, API 없음). 운영 서버에 부담이 없다.
다음 매장 사진의 첫 시험이다. 서버 app/local_read.py(배포 모델 tile-yolo26n·tile-cls-mnv3s)를 그대로 쓰고, 격자는 meta.json 의 값, 화료자는 기록값.
  python -I -X utf8 experiments/tile_classifier/offline_eval.py <captures 폴더> [--truth truth.json]
결과 <captures 폴더>/local_eval.json. truth.json(visit_20261031 형식)을 주면 손패·강 끝을 채점한다.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "speed"))
sys.path.insert(0, str(HERE.parent / "yolo"))
from rules_core import rv  # noqa: E402,F401  서버 코드 경로를 잡는다
from app import local_read as lr  # noqa: E402
import hybrid as hy  # noqa: E402
import hybrid_replay as hr  # noqa: E402
import other_reads as o  # noqa: E402
import seat_grow as sg  # noqa: E402

SIDES = ["bottom", "right", "top", "left"]


def jpeg(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def grids_in(captures: Path) -> list[dict]:
    """촬영 기록 옆 _track 폴더의 격자들(seat_grow.visit_grids 와 같은 규칙, 날짜만 안 묶음)."""
    seen, out = set(), []
    for t in sorted(captures.glob("*_track")):
        cands = []
        for f in sorted(t.glob("setup_*.json")):
            j = json.loads(f.read_text(encoding="utf-8"))
            cands += [j.get("grid_before"), j.get("grid_proposed")]
        for z in sorted(t.glob("frames_*.zip")):
            with zipfile.ZipFile(z) as zf:
                cands.append(json.loads(zf.read("frames.json")).get("grid"))
        for g in cands:
            if g and (g["x1"], g["x2"], g["y1"], g["y2"]) not in seen:
                seen.add((g["x1"], g["x2"], g["y1"], g["y2"]))
                out.append(g)
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", type=Path)
    ap.add_argument("--truth", type=Path)
    a = ap.parse_args()
    truth = json.loads(a.truth.read_text(encoding="utf-8"))["scenes"] if a.truth else {}
    reader = lr.LocalReader()
    grids = grids_in(a.captures)
    rows = []
    for d in sorted(p for p in a.captures.iterdir() if p.is_dir() and not p.name.endswith("_track")):
        meta_f, photo = d / "meta.json", d / "original.jpg"
        if not meta_f.exists() or not photo.exists() or d.name in sg.OCCLUDED:
            continue
        m = json.loads(meta_f.read_text(encoding="utf-8"))
        side = m.get("winner_side")
        im = Image.open(photo).convert("RGB")
        g = sg.find_grid(grids, d, side, im.size) if side else None
        if not side or not g:
            print(d.name, "화료자·격자 없음, 건너뜀")
            continue
        seat = reader.read_seat(jpeg(sg.crop(im, sg.seat_box(g, side, 40), side)), sg.hand_frac(g, side))
        others = [s for s in SIDES if s != side]
        rivers = reader.read_rivers([jpeg(sg.crop(im, o.last_zone(g, s), s)) for s in others])["rivers"]
        row = dict(name=d.name, side=side, seat=seat, rivers={s: r for s, r in zip(others, rivers)}, gemini_merge=m.get("merge"))
        t = truth.get(d.name)
        if t:
            melds = t["melds"]
            s = dict(hand=t["hand"].split(), melds=melds)
            row["ok"] = hr.same(seat["hand"], seat["melds"], s)
            row["auto"] = bool(seat["hand"]) and not seat["block"] and hy.check(seat["hand"], [x.split() for x in seat["melds"]])[0]
            if t.get("is_tsumo") is False and t.get("loser") is not None:
                got = row["rivers"].get(SIDES[t["loser"]])
                row["ron_ok"] = bool(got) and got["tile"] == t.get("win_tile")
        rows.append(row)
        print(d.name, "틀", seat["framed"], " ".join(seat["hand"]), seat["melds"], "맞음", row.get("ok"), "자동", row.get("auto"), "론 패", row.get("ron_ok"), flush=True)
    (a.captures / "local_eval.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    judged = [r for r in rows if "ok" in r]
    print(f"{len(rows)}장, 틀 {sum(r['seat']['framed'] for r in rows)}, 채점 {len(judged)}, 맞음 {sum(r['ok'] for r in judged)}, 자동 {sum(r['auto'] for r in judged)}(틀림 {sum(r['auto'] and not r['ok'] for r in judged)}), 론 패 {sum(r.get('ron_ok', False) for r in judged)}/{sum('ron_ok' in r for r in judged)}")


if __name__ == "__main__":
    main()
