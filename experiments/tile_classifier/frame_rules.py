"""틀 규칙을 하나씩 더해 표 1-22 실패가 얼마나 풀리는지 잰다(2026-11-02, 노트북 CPU, API 없음). 서버 app.seat 는 고치지 않는다.

틀 = st.frame(운영 검사) 먼저, 안 되면 크롭 통째 검출 + structure_split 복사본(split2). 채점은 det_eval.py 와 같다(hr.tally, 저장된 Gemini 폭 40).
규칙(앞 것에 차례로 더함):
  이웃 = 손패 줄보다 패 1.5개 넘게 가운데 쪽 상자는 울기 후보에서 뺀다(크롭 위쪽 이웃 패, k12·132239)
  두단 = 6·8장 덩어리가 위아래로 놓였으면 줄로 나눈다(123140)
  옅음 = 읽을 패의 무늬 기준 0.03 → 0.015(132239·132954·133030 은 세운 패가 0.020~0.024. 눕힌 패만 낮춘 첫 시도는 효과 없음)
  백 = 무늬 없는 상자(<0.01)를 손패 줄 안에선 4장까지, 울기에선 전부 무늬 없을 때만 받는다
  떼어둠 = 13장이면 손패 줄 오른쪽 탁자 위 홀로 놓인 패 1장을 떼어 둔 패로, 2장 이상이면 자동 반영하지 않는다. 돌아간 패라 각도를 바꿔 읽는다
  줄 = 손패 줄 직선 허용 0.25 → 0.30패(165614 가 0.26, 사진 한 장으로 정한 값이라 따로 본다)
규칙을 이 사진들을 보고 정했으므로 일반화 숫자가 아니다.
  python -I experiments/tile_classifier/frame_rules.py [--r2]
결과 data/det/rules.json(--r2 면 rules_r2.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import det_eval as de  # noqa: E402
from det_eval import hr, hy, rv, sg, st, tr  # noqa: E402
from rules_core import ANGLES, ok2, split2, strays  # noqa: E402

DATA = HERE / "data"
STEPS = [("기준", set()), ("+이웃", {"이웃"}), ("+두단", {"이웃", "두단"}), ("+옅음", {"이웃", "두단", "옅음"}),
         ("+백", {"이웃", "두단", "옅음", "백"}), ("+떼어둠", {"이웃", "두단", "옅음", "백", "떼어둠"}),
         ("+줄", {"이웃", "두단", "옅음", "백", "떼어둠", "줄"})]


class Cached:
    """같은 그림을 다시 검출하지 않는다(규칙 단계마다 같은 상자)."""

    def __init__(self, det):
        self.det, self.memo = det, {}

    def detect(self, rgb: np.ndarray, low: bool = False):
        key = (rgb.shape, hash(rgb.tobytes()))
        if key not in self.memo:
            self.memo[key] = self.det.detect(rgb)
        return self.memo[key]


def read_turned(net, rgb: np.ndarray, b, tw: float, th: float) -> str:
    """돌아간 패: 각도마다 패 크기로 잘라 가장 확신 높은 값."""
    cx, cy, r = b[0] + b[2] / 2, b[1] + b[3] / 2, int(max(b[2], b[3], th))
    H, W = rgb.shape[:2]
    part = Image.fromarray(rgb).crop((max(0, int(cx - r)), max(0, int(cy - r)), min(W, int(cx + r)), min(H, int(cy + r))))
    m = part.width / 2, part.height / 2
    box = (int(m[0] - tw / 2), int(m[1] - th / 2), int(m[0] + tw / 2), int(m[1] + th / 2))
    xs = torch.stack([tr.PLAIN(tr.square(part.rotate(ang).crop(box))) for ang in ANGLES])
    with torch.no_grad():
        p = net(xs).softmax(1)
    return tr.CLASSES[int(p.max(0).values.argmax())]


def one_photo(net, rgb: np.ndarray, det, frac: float, o: set) -> dict:
    split = int(rgb.shape[1] * frac)
    a = st.frame(rgb, det, hand_frac=frac)
    faces = rv.dedupe(rv.keep_faces(det.detect(rgb), rv.white_mask(rgb)))
    b = split2(rgb, faces, split, o) if faces else None
    fr = a if a is not None else b if b is not None and ok2(b, rgb, o) else None
    if fr is None:
        return dict(framed=False, hand=[], melds=[], block=False)
    hand, melds = de.read(net, rgb, fr)
    block = False
    if "떼어둠" in o and fr.count == 13 and not fr.separate:
        got = strays(fr, faces, rgb)
        if len(got) == 1:
            hand = hand + [read_turned(net, rgb, got[0], fr.tw, fr.th)]
        elif got:
            block = True
    return dict(framed=True, hand=hand, melds=melds, block=block)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    base = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    nets = de.classifiers(base, de.rw.extra())
    dets = {"a": Cached(de.Det(de.OUT / "fold_a.pt")), "b": Cached(de.Det(de.OUT / "fold_b.pt"))}
    gem: dict[str, list] = {}
    for g in json.loads(sg.OUT.read_text(encoding="utf-8")):
        gem.setdefault(g["name"], []).append(g["by_grow"].get("40") or {})
    scenes = []
    for s in sg.scenes():
        if s["hand"] is None:
            continue
        part = "bcd" if not s["name"].startswith("2026") else "am" if s["name"] < "20261031_14" else "pm"
        rgb = np.asarray(sg.crop(Image.open(s["path"]).convert("RGB"), sg.seat_box(s["grid"], s["side"], 40), s["side"]))
        scenes.append((s, part, rgb))
    out, prev = {}, {}
    for label, o in STEPS:
        rows, now = [], {}
        for s, part, rgb in scenes:
            r = one_photo(nets[part], rgb, dets["b" if part == "am" else "a"], sg.hand_frac(s["grid"], s["side"]), o)
            hand, melds = r["hand"], r["melds"]
            y_pass = bool(hand) and not r["block"] and hy.check(hand, [m.split() for m in melds])[0]
            y_ok = hr.same(hand, melds, s)
            now[s["name"]] = dict(framed=r["framed"], y_pass=y_pass, y_ok=y_ok, hand=" ".join(hand), melds=melds, block=r["block"])
            for gm in gem.get(s["name"], [{}]):
                g_hand = (gm.get("hand") or "").split() + ([gm["sep"]] if gm.get("sep") else [])
                g_melds = gm.get("melds") or []
                rows.append(dict(name=s["name"], known=True, y_pass=y_pass, y_ok=y_ok, y_short=hr.one_short(hand, melds, s), y_s=0.0,
                                 g_pass=bool(g_hand) and bool(gm.get("unanimous")) and hy.check(g_hand, [m.split() for m in g_melds])[0],
                                 g_ok=hr.same(g_hand, g_melds, s), g_short=hr.one_short(g_hand, g_melds, s), g_s=gm.get("s")))
        framed = sum(v["framed"] for v in now.values())
        t, h = hr.tally(rows, "yolo"), hr.tally(rows, "hybrid")
        print(f"[{label}] 틀 {framed}/{len(now)} | 단독 답 {t['answer_ok']}/{t['known']} 자동 {t['auto']}(정답 {t['auto_ok']} 틀림 {t['auto_bad']}) | 먼저 답 {h['answer_ok']}/{h['known']} 자동 {h['auto']}(정답 {h['auto_ok']} 틀림 {h['auto_bad']}) 확인 {h['ask']} Gemini {h['gem']}", flush=True)
        for s, _, _ in scenes:
            n = s["name"]
            v = now[n]
            if prev and (v["framed"], v["y_pass"], v["y_ok"]) != (prev[n]["framed"], prev[n]["y_pass"], prev[n]["y_ok"]):
                print("  ", n[-6:], "틀", prev[n]["framed"], "→", v["framed"], "자동", prev[n]["y_pass"], "→", v["y_pass"], "맞음", prev[n]["y_ok"], "→", v["y_ok"], "|", v["hand"], v["melds"], "| 정답", " ".join(s["hand"]), s["melds"], flush=True)
        prev = now
        out[label] = dict(framed=framed, yolo={k: x for k, x in t.items() if k != "secs"}, hybrid={k: x for k, x in h.items() if k != "secs"}, photos=now)
    (DATA / "det" / ("rules_r2.json" if "--r2" in sys.argv else "rules.json")).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("-- 마지막 단계 틀린 자동")
    for s, _, _ in scenes:
        v = prev[s["name"]]
        if v["y_pass"] and not v["y_ok"]:
            print(s["name"][-6:], v["hand"], v["melds"], "| 정답", " ".join(s["hand"]), s["melds"])


if __name__ == "__main__":
    main()
