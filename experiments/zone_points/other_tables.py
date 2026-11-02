"""다른 탁자 점검 표(2026-11-02, API 없음). tool/felt_grid_other_test.dart 다음에. 이 결과로 규칙을 고치지 않는다.
  python -X utf8 experiments/zone_points/other_tables.py [그림 앞이름]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zones as z  # noqa: E402
from propose import DATA  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    prefix = sys.argv[1] if len(sys.argv) > 1 else None
    d = json.loads((DATA / "other_tables.json").read_text(encoding="utf-8"))
    labels = json.loads((DATA / "labels.json").read_text(encoding="utf-8"))
    print("[① 다른 탁자가 찍혔을 수 있는 사진]")
    names = list(d["real"])
    for n in names:
        r = d["real"][n]
        print(f" {Path(n).parent.name}/{Path(n).name[:34]}: {'못 찾음' if r.get('none') else 'ok=%s span=%.2f dev=%.2f edge=%.2f out=%.2f in=%.2f' % (r['ok'], r['span'], r['device'], r['edge'], r['outside'], r['inside'])}")
    if prefix and names:
        cols, tw, th = 5, 400, 300
        sh = Image.new("RGB", (cols * tw, ((len(names) + cols - 1) // cols) * th))
        for i, n in enumerate(names):
            im = Image.open(n).convert("RGB").resize((tw, th))
            dr = ImageDraw.Draw(im)
            r = d["real"][n]
            if not r.get("none"):
                draw = lambda q, c: dr.polygon([(x * tw, y * th) for x, y in q], outline=c)
                draw(r["felt"], (255, 230, 0))
                draw(z.polygons(r["felt"])["device"], (255, 0, 255))
            dr.rectangle((0, 0, 200, 12), fill="black")
            dr.text((2, 0), f"{Path(n).name[:22]} ok={r.get('ok', False)}", fill="white")
            sh.paste(im, ((i % cols) * tw, (i // cols) * th))
        sh.save(f"{prefix}.jpg", quality=85)
        print(" 그림", f"{prefix}.jpg")
    print("\n[② 편집한 탁자, 사진 12장] 통과, 틀린 채 통과(라벨 대비 2.2% 초과), 통과분 오차 최대(%), 못 찾음, 거절 이유")
    for k, rows in d["edited"].items():
        ok, wrong, emax, none = 0, 0, 0.0, 0
        why = {}
        for n, r in rows.items():
            if not r:
                none += 1
                continue
            if r["ok"]:
                ok += 1
                lab = labels[n]
                W, H = lab["size"]
                e = (np.array(r["felt"]) - np.array(lab["felt"])) * [1.0, H / W]
                m = float(np.hypot(e[:, 0], e[:, 1])[np.array(lab["vis"][:4]) > 0].max())
                emax = max(emax, m)
                wrong += m > 0.022
            else:
                for key, bad in (("span", r["span"] < 0.25), ("기기", r["device"] < 0.25), ("기기 바깥", r["edge"] > 0.75), ("바깥", r["outside"] > 0.05), ("안쪽", r["inside"] < 0.30), ("밖", r["off"] > 0.20), ("변 비", r["ratio"] > 2.2)):
                    if bad:
                        why[key] = why.get(key, 0) + 1
        print(f" {k}: 통과 {ok}/{len(rows)}, 틀린 채 통과 {wrong}, 최대 {emax * 100:.2f}, 못 찾음 {none}, {why}")


if __name__ == "__main__":
    main()
