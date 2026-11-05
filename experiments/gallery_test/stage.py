"""태블릿 갤러리용 정답 있는 사진(평가 26장 = sg.eval_scenes(), 가림·사용자 문제 제외)을 순번 이름으로 모으고 정답표를 만든다(2026-11-05).
  python -I -X utf8 experiments/gallery_test/stage.py <출력 폴더>   → <출력>/test_NN_<사진>.jpg, experiments/gallery_test/answers.md
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/speed"))
import flow_visit as fv  # noqa: E402
import seat_grow as sg  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
truth = json.loads((ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]
SIDE = {"bottom": "아래", "right": "오른쪽", "top": "위", "left": "왼쪽"}
rows = ["# 태블릿 갤러리 정답 사진 26장 (2026-11-05)", "",
        "갤러리 이름 `test_NN_<사진>.jpg`. 화료자 자리는 사진 방향 기준. B·C·D 는 갤러리 연출 사진(측정 테스트의 대국 정보 기준 점수), 매장은 10/31 truth.json.", "",
        "| 번호 | 사진 | 화료자 | 손패(사진에 보이는 것) | 울기 | 화료패 | 론/쯔모 | 표시패 | 점수 |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
for i, s in enumerate(sg.eval_scenes(), 1):
    short = s["name"][-6:] if s["set"] == "visit" else s["name"]
    name = f"test_{i:02d}_{short}.jpg"
    shutil.copy2(s["path"], out / name)
    if s["set"] == "visit":
        t = truth.get(s["name"])
        lab = ROOT / "experiments/visit_20261031/captures" / s["name"] / "label.json"
        if t is None:  # truth.json 에 없는 장면은 그때 앱 기록(label.json, 대국에 반영한 확정 값)
            j = json.loads(lab.read_text(encoding="utf-8"))
            t = {"win_tile": j["win_tile"], "is_tsumo": j["is_tsumo"], "indicators": None}
        rows.append(f"| {i:02d} | {short} | {SIDE[s['side']]} | {' '.join(s['hand'])} | {' / '.join(s['melds']) or '-'} | {t.get('win_tile')} | {'쯔모' if t.get('is_tsumo') else '론'} | {' '.join(t.get('indicators') or []) or '정답 없음'} | - |")
    else:
        rows.append(f"| {i:02d} | {short} | {SIDE[s['side']]} | {' '.join(s['hand'])} | {' / '.join(s['melds']) or '-'} | - | - | - | {fv.BCD_POINTS[short]} |")
(ROOT / "experiments/gallery_test/answers.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
print(len(list(out.glob("test_*.jpg"))), "장 →", out)
