"""白 을 학습 없이 코드로 찾는 실험(2026-11-02, 노트북, API 없음). 규칙은 서버 app/local_read.py `fill`. 시험 사진을 학습하지 않은 나눔 모델만.

뒷면이 색 있는 패 세트에서는 무늬 없는 흰 앞면 = 白 이라, 위치만 찾으면 종류가 정해진다. 틀이 실패하고 장수가 모자랄 때만 시도한다.
  빈칸: 손패 줄 간격으로 빠진 칸(틈·양 끝)을 계산해, 흰 면 0.7 이상·무늬 0.01 미만이면 白 으로 넣는다(seat_wide.fill_row 와 같은 생각).
  모서리: 3장이 모자라면 탁자 끝(펠트 아래쪽 경계)이 오른쪽 모서리에서 패 3장 폭만큼 올라와 있고, 그 안이 희고 무늬가 없을 때 白 퐁으로 본다.
채운 답은 자동 반영하지 않는다(block). 규칙을 실패 사진을 보고 정했으므로 회복 수는 일반화 숫자가 아니다.
헛발동 검사: 틀을 잡은 사진에서 무늬 패 상자를 일부러 지워 장수를 모자라게 만들어도 채우지 않아야 한다(지운 1장씩 / 손패 끝 3장 / 울기 묶음).
  python -I -X utf8 experiments/tile_classifier/server_bench/blank_fill.py
결과 data/det/blank_fill.json
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.argv = [sys.argv[0], "--r2"]
from rules_core import rv, st  # noqa: E402
from app import local_read as lr  # noqa: E402
from det_eval import hr, hy, sg  # noqa: E402


def read_filled(r: lr.LocalReader, rgb: np.ndarray, fr: st.SeatFrame) -> tuple[list, list]:
    def one(b) -> str:
        return "5z" if st.ink(rgb, b) < lr.BLANK else r.read([lr.cut(rgb, b)])[0][0]

    hand = [one(b) for b in fr.hand] + ([one(fr.separate)] if fr.separate else [])
    melds = [" ".join("5z" if st.ink(rgb, b) < lr.BLANK else r.read_meld_tile(rgb, b)[0] for b in m) for m in fr.melds]
    return hand, melds


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    truth = {s["name"]: s for s in sg.eval_scenes() if s["hand"] is not None}
    readers: dict = {}
    rows = []
    neg = {"1장": [0, 0], "손패 끝 3장": [0, 0], "울기 묶음": [0, 0]}
    fires = []
    secs = []
    for p in meta["photos"]:
        s = truth.get(p["name"])
        if s is None:
            continue
        k = (p["det"], p["part"])
        r = readers.setdefault(k, lr.LocalReader(det_model=HERE / "models" / f"det_fold_{p['det']}.onnx", cls_model=HERE / "models" / f"cls_{p['part']}.onnx"))
        jpg = (HERE / "crops" / f"{p['name']}.jpg").read_bytes()
        base = r.read_seat(jpg, p["frac"], fill_blank=False)
        rgb = np.asarray(Image.open(HERE / "crops" / f"{p['name']}.jpg").convert("RGB"))
        faces = rv.dedupe(rv.keep_faces(r.detect(rgb), rv.white_mask(rgb)))
        split = int(rgb.shape[1] * p["frac"])
        w = 2 if not p["name"].startswith("2026") else 1
        b_pass = bool(base["hand"]) and not base["block"] and hy.check(base["hand"], [m.split() for m in base["melds"]])[0]
        row = dict(name=p["name"], w=w, base_framed=base["framed"], base_pass=b_pass, base_ok=hr.same(base["hand"], base["melds"], s), filled=False)
        if not base["framed"]:
            t0 = time.perf_counter()
            fr, added = lr.fill(rgb, faces, split)
            secs.append(time.perf_counter() - t0)
            if fr is not None:
                hand, melds = read_filled(r, rgb, fr)
                row.update(filled=True, added=len(added), hand=" ".join(hand), melds=melds, ok=hr.same(hand, melds, s),
                           shape=hy.check(hand, [m.split() for m in melds])[0])
                print(p["name"][-6:], "채움", len(added), " ".join(hand), melds, "맞음", row["ok"], "형태", row["shape"], "| 정답", " ".join(s["hand"]), s["melds"], flush=True)
            else:
                print(p["name"][-6:], "채우지 않음", flush=True)
        else:
            fr0 = lr.split_frame(rgb, faces, split)
            inked = lambda b: st.ink(rgb, b) >= lr.BLANK

            def trial(kind: str, gone: list) -> None:
                neg[kind][0] += 1
                got, added = lr.fill(rgb, [f for f in faces if f not in gone], split)
                if got is not None:
                    neg[kind][1] += 1
                    fires.append(dict(photo=p["name"], kind=kind, gone=gone, added=added))
                    print("  헛발동", p["name"][-6:], kind, gone, "→", added, flush=True)

            for b in fr0.hand:
                if inked(b):
                    trial("1장", [b])
            if len(fr0.hand) >= 3 and all(inked(b) for b in fr0.hand[-3:]):
                trial("손패 끝 3장", list(fr0.hand[-3:]))
            for m in fr0.melds:
                if all(inked(b) for b in m):
                    trial("울기 묶음", list(m))
        rows.append(row)
    n = sum(x["w"] for x in rows)
    fixed = [x for x in rows if x["filled"]]
    print(f"\n{n}회 | 기존 틀 {sum(x['base_framed'] for x in rows)}/{len(rows)}, 기존 자동 {sum(x['w'] * x['base_pass'] for x in rows)}(틀림 {sum(x['w'] * (x['base_pass'] and not x['base_ok']) for x in rows)})")
    print(f"채운 사진 {len(fixed)}: 맞음 {sum(x['ok'] for x in fixed)}, 틀림 {sum(not x['ok'] for x in fixed)} (전부 자동 반영 안 함)")
    print("헛발동(시험 수 → 채움):", neg)
    if secs:
        print(f"채우기 시간 중앙 {statistics.median(secs) * 1000:.0f}ms, 최대 {max(secs) * 1000:.0f}ms")
    (HERE.parent / "data" / "det" / "blank_fill.json").write_text(json.dumps(dict(rows=rows, neg=neg, fires=fires), ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
