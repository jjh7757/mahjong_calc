"""[평가 밖·참고 — 2026-11-10 부터] 10/24 매장 삼각대 15장(11-10 부터 13장)으로 자리 판독을 잰다(2026-11-04, 노트북, API 없음).
**2026-11-10 사용자 지침: 테스트 세트는 원본 B·C·D + 10-31 + 11-07 만(seat_grow.eval_scenes, robust_suite) — 이 스크립트 결과는
합격 기준·채택 판정에 쓰지 않고 metrics "평가 밖" 표에만 적는다.** (아래는 11-10 전까지의 설명.) 예전: 8회차 최종 판정용.

**이 결과로 규칙·학습을 고치지 않는다.** 합격 기준은 docs/metrics.md 표 1-69 에 미리 적은 것만 쓴다.
정답·장면: experiments/rectify/recheck_test.py TRUTH(NOTES 30), 격자: read_grid_timing_test.dart `_field`(삼각대 위치별, 0~1000 단위).
13:18(131823)은 EXIF 회전이 다른 사진이라 앱 테스트와 같이 뺀다. 검출기는 개발 35장 전부로 학습한 final(테스트 사진은 학습에 없음),
분류기는 운영 것(app/assets, 테스트 사진 학습 안 함).
  규칙 = server_bench/bench.one(자리 크롭), 새 경로 = app.roles.read_roles(hybrid)
  python -I -X utf8 experiments/tile_classifier/server_bench/field_bench.py --det det_final [--obb --rot-cut] [--dry]
결과 data/role/bench/field_<det>[_obb][_rotcut].json. --dry 는 점수를 안 찍고 돌기만 확인.
--rectify(개선 계획 1단계, 2026-11-05): 앱과 같은 규칙으로 편 사진(`tool/rectify_field_test.dart` 가 만든 rectified.jpg,
  _rectifyJob 과 같은 3200px·q92)을 표준 격자(200, 800, 200, 800)로 읽는다. 펠트를 못 찾아 rectified.jpg 가 없으면 원본 + 장면 격자
  (측정 테스트 RECTIFY=true 와 같다).
--seat-det(2026-11-05): 서버 f33d632 의 LocalReader 는 자리 판독에 늘 운영 8회차(`seat_model` = assets/tile-obb-r8.onnx)를 쓴다. 그래서
  `--det det_final` 만 주면 hybrid 는 "8회차 자리 + 2회차 맥락" = 운영 그대로다. `--seat-det none` 이면 자리도 --det 모델(2회차 전부).
자리 채점(2026-11-05): 다섯 장면 모두 론이고 화료패는 방총자 강 끝에 있다(NOTES 촬영별 — 12:29 "위 강 끝 3만으로 론" 등). 자리 판독만
  보는 이 벤치는 화료패를 볼 수 없으므로 TRUTH 손패 맨 끝(화료패)을 뺀 13장을 자리 정답으로 한다(`seat_*`). 예전 채점(14장 정답,
  `rule_ok`·`hyb_ok`·`*_hit`/211)은 비교용으로 그대로 남긴다 — 표 1-69 의 장면 0/15 는 일부가 이 채점 탓.
장면 단위·행별 패(2026-11-05, 개선 계획 2단계): 독립 장면은 5개뿐이라 hybrid 자리 채점을 장면 단위 /5(사진 과반이 맞으면 1)로도 찍고,
  rows 에 사진별 `seat_hit`·`seat_want`(hybrid 자리 채점 패 단위)를 남긴다 — experiments/speed/stats.py 가 장면 묶음 부트스트랩에 쓴다.
서버처럼 q90 재저장(2026-11-05, 개선 계획 4단계 — 3단계 검토 ③ 잣대 버그): `/v2/localroles` 는 받은 사진을 `prepare_image(4080)`(EXIF·긴 변
  4080·JPEG q90 재저장)한 뒤 읽는다. 예전 이 벤치는 원본 바이트를 바로 넘겨 대삼원 3장(떼어 둔 패 `5s` 가 안 붙음)에서 서버보다 3장 낙관
  (9/15 대 6/15)이었다. 이제 hybrid 는 서버와 같은 바이트를 읽는다(규칙 열 `bench.one` 은 자리 크롭 경로라 그대로). 예전 결과는
  `field_det_final_rect_rawbytes.json` 으로 보존. rows 의 hybrid 에 패별 `conf`·`alt`·`conf2`(서버가 내면, 4단계 `feat/cls-alt`)와 서버
  `block` 도 남긴다 — experiments/speed/hand_rules.py score 가 쓴다.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / "speed"))
sys.path.insert(0, str(HERE.parents[1] / "yolo"))
sys.path.insert(0, os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer"))
import hybrid as hy  # noqa: E402
import seat_grow as sg  # noqa: E402
from app import local_read as lr  # noqa: E402
from app import river, roles  # noqa: E402
from app.recognizer import prepare_image  # noqa: E402

_spec = importlib.util.spec_from_file_location("server_bench_bench", HERE / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)
FIELD = HERE.parents[1] / "field_20261024" / "captures"
OUT = HERE.parent / "data" / "role" / "bench"
# 7-1(2026-11-06): LOCAL_CLS_MODEL 을 주면 그 분류기(서버 env 와 같은 이름 — 역할 모델은 LOCAL_ROLE_MODEL, 두 번째 분류기는 LOCAL_ALT_CLS_MODEL 을 서버가 읽음)
CLS = Path(os.environ.get("LOCAL_CLS_MODEL") or Path(os.environ.get("RECOGNIZER_REPO", "C:/Users/jjh7757/dev/mahjong-recognizer")) / "app" / "assets" / "tile-cls-mnv3s.onnx")

STANDARD = dict(x1=200, x2=800, y1=200, y2=800)  # lib/table/rectify.dart standardGrid
GRID_A = dict(x1=300, x2=690, y1=150, y2=830)
GRID_A2 = dict(x1=300, x2=720, y1=150, y2=830)
GRID_B1 = dict(x1=315, x2=760, y1=200, y2=740)
GRID_B2 = dict(x1=355, x2=760, y1=200, y2=740)
SCENES = {  # 장면: (사진들, 격자) — read_grid_timing_test.dart `_field` 와 같다
    "F1229": (["122922"], GRID_A),
    "F1240": (["124007"], GRID_A2),
    "F대삼원": (["125053", "130533", "131210", "132647", "133011", "133620", "134323", "135148"], GRID_A),
    "F1400": (["135912", "140302", "140750", "140918"], GRID_B1),
    "F1434": (["143443"], GRID_B2),
}
# 2026-11-10 사용자 결정: 거치 화면으로 부적합한 사진(seat_grow.USER_ERROR — F1240 모서리에 남은 發 3장, F1434 테두리 위 안깡)은 뺀다
# → 테스트 13장·장면 3개. 예전 값(15장)과 비교할 땐 `FIELD_ALL=1`.
if os.environ.get("FIELD_ALL") != "1":
    SCENES = {k: (ps, g) for k, (ps, g) in ((k, ([p for p in ps if f"20261024_{p}" not in sg.EXCLUDED], g)) for k, (ps, g) in SCENES.items()) if ps}


def truth() -> dict:
    src = (HERE.parents[1] / "rectify" / "recheck_test.py").read_text(encoding="utf-8")
    block = src[src.index("TRUTH = {"):src.index("}\n", src.index("TRUTH = {")) + 1]
    t = eval(block.split("=", 1)[1])  # 상수 dict 리터럴
    # TRUTH 손패는 화료패가 맨 끝(NOTES 촬영별: 론 패 = 방총자 강 끝). seat = 자리에 실제로 있는 13장.
    return {k: dict(side=v[0], hand=v[2].split(), seat=v[2].split()[:-1], melds=[re.sub(r"[\[\]()]", "", m) for m in v[3]]) for k, v in t.items()}


def judge(hand: list[str], melds: list[str], block: bool, s: dict) -> tuple[bool, bool]:
    key = lambda ms: sorted(" ".join(sorted(m.split())) for m in ms)
    ok = bool(hand) and sorted(hand) == sorted(s["hand"]) and key(melds) == key(s["melds"])
    auto = bool(hand) and not block and hy.check(hand, [m.split() for m in melds])[0]
    return ok, auto


def seat_view(s: dict) -> dict:
    """자리 정답(화료패 뺀 13장)으로 바꾼 정답."""
    return dict(s, hand=s["seat"])


def tiles_hit(hand: list[str], melds: list[str], s: dict) -> int:
    """패 단위 맞은 수(손패·울기 합친 다중집합 교집합, 정답 장수가 분모). 0/15 처럼 장면 단위로 판별이 안 될 때 보조."""
    from collections import Counter

    got = Counter(hand + [t for m in melds for t in m.split()])
    want = Counter(s["hand"] + [t for m in s["melds"] for t in m.split()])
    return sum((got & want).values())


def tile_extra(hand_t: list[dict], melds: list[dict]) -> dict:
    """패별 확신도·분류기 2순위(서버 응답에 있으면). hand 와 같은 순서, 울기는 묶음마다 목록."""
    out = {"conf": [t.get("conf") for t in hand_t]}
    if any("alt" in t for t in hand_t):
        out.update(alt=[t.get("alt") for t in hand_t], conf2=[t.get("conf2") for t in hand_t])
    if any("alts" in m for m in melds):
        out.update(meld_alt=[m.get("alts") for m in melds], meld_conf2=[m.get("conf2s") for m in melds])
    return out


def main() -> None:
    print("[평가 밖·참고] 10-24 매장 사진 — 2026-11-10 지침상 판정에 쓰지 않음(테스트 세트 = B·C·D + 10-31 + 11-07)", flush=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--det", required=True, help="server_bench/models/<det>.onnx (예: det_final, det_r7_final)")
    ap.add_argument("--obb", action="store_true")
    ap.add_argument("--rot-cut", action="store_true")
    ap.add_argument("--clean", action="store_true", help="서버 정리(가는 조각 버리기 + 안깡 묶기)")
    ap.add_argument("--dry", action="store_true", help="점수를 안 찍고 돌기만 확인")
    ap.add_argument("--haku2", action="store_true", help="모서리 白 2장 이상이면 퐁 3장(haku_pair.py)")
    ap.add_argument("--corner-fix", action="store_true", help="모서리 탁자 끝 찾기 흔들림 고치기(corner_fix.py)")
    ap.add_argument("--loose-ctx", action="store_true", help="크롭 밖 떼어 둔 화료패를 역할 모델 판단으로(loose_ctx.py)")
    ap.add_argument("--recolored", action="store_true", help="색 바꾼 테스트(make_recolor_test.py, captures_recolor)")
    ap.add_argument("--seat-det", default="server", choices=["server", "none"],
                    help="자리 판독 검출기: server = 서버 기본(운영 8회차 tile-obb-r8), none = --det 모델")
    ap.add_argument("--rectify", action="store_true", help="편 사진(rectified.jpg) + 표준 격자. 없으면 원본 + 장면 격자")
    ap.add_argument("--suffix", default="", help="결과 파일 이름 끝에 붙임(예: _sig — 예전 결과를 덮지 않게, 개선 계획 5단계)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.obb:
        import obb_detect

        obb_detect.install(bench, lr, river, False, a.rot_cut, sliver=a.clean, kan=a.clean)
    if a.loose_ctx:
        import loose_ctx

        loose_ctx.install(roles)
    if a.corner_fix:
        import corner_fix

        corner_fix.install(lr)
    if a.haku2:
        import haku_pair

        haku_pair.install(lr)
    meta = json.loads((HERE / "meta.json").read_text(encoding="utf-8"))
    det_path = HERE / "models" / f"{a.det}.onnx"
    reader = lr.LocalReader(det_model=det_path, cls_model=CLS, **({"seat_model": None} if a.seat_det == "none" else {}))
    det = bench.Det(det_path, 2)
    cls = bench.Cls(CLS, meta, 2)
    T = truth()
    rows, tot = {}, dict(n=0, rule_ok=0, rule_bad=0, hyb_ok=0, hyb_bad=0, want=0, rule_hit=0, hyb_hit=0,
                        seat_want=0, seat_rule_ok=0, seat_rule_bad=0, seat_hyb_ok=0, seat_hyb_bad=0, seat_rule_hit=0, seat_hyb_hit=0, hyb_auto=0)
    rectified = 0
    for scene, (photos, scene_grid) in SCENES.items():
        s = T[scene]
        for ph in photos:
            folder = (FIELD.parent / "captures_recolor" if a.recolored else FIELD) / f"20261024_{ph}"
            path, grid = folder / "original.jpg", scene_grid
            if a.rectify and (folder / "rectified.jpg").exists():
                path, grid = folder / "rectified.jpg", STANDARD
                rectified += 1
            im = Image.open(path).convert("RGB")
            crop = sg.crop(im, sg.seat_box(grid, s["side"], 40), s["side"])
            import io

            buf = io.BytesIO()
            crop.save(buf, "JPEG", quality=92)
            det.memo = {}
            rule = bench.one(buf.getvalue(), det, cls, sg.hand_frac(grid, s["side"]))
            r_ok, r_auto = judge(rule["hand"], rule["melds"], rule["block"], s)
            o = roles.read_roles(reader, prepare_image(path.read_bytes(), 4080), s["side"], grid, "hybrid")
            hand_t = o["tiles"] + ([o["separate_tile"]] if o["separate_tile"] else [])
            hand = [t["tile"] for t in hand_t]
            melds = [" ".join(m["tiles"]) for m in o["melds"]]
            h_ok, h_auto = judge(hand, melds, o.get("block", False), s)
            sv = seat_view(s)
            rs_ok, _ = judge(rule["hand"], rule["melds"], rule["block"], sv)
            hs_ok, _ = judge(hand, melds, o.get("block", False), sv)
            rows[ph] = dict(scene=scene, rectified=path.name == "rectified.jpg", rule=dict(hand=rule["hand"], melds=rule["melds"], ok=r_ok, auto=r_auto),
                            hybrid=dict(hand=hand, melds=melds, ok=h_ok, auto=h_auto, ms=o["ms"], block=o.get("block", False), **tile_extra(hand_t, o["melds"]),
                                        **({"signals": o["signals"]} if "signals" in o else {})),  # 불확실성 신호(개선 계획 5단계)
                            seat_ok=dict(rule=rs_ok, hybrid=hs_ok), seat_hit=tiles_hit(hand, melds, sv),
                            seat_want=len(sv["hand"]) + sum(len(m.split()) for m in sv["melds"]), seat_bad=h_auto and not hs_ok,
                            want_hand=sv["hand"], want_melds=sv["melds"])
            tot["n"] += 1
            tot["want"] += len(s["hand"]) + sum(len(m.split()) for m in s["melds"])
            tot["rule_hit"] += tiles_hit(rule["hand"], rule["melds"], s)
            tot["hyb_hit"] += tiles_hit(hand, melds, s)
            tot["rule_ok"] += r_ok
            tot["rule_bad"] += r_auto and not r_ok
            tot["hyb_ok"] += h_ok
            tot["hyb_bad"] += h_auto and not h_ok
            tot["seat_want"] += len(sv["hand"]) + sum(len(m.split()) for m in sv["melds"])
            tot["seat_rule_hit"] += tiles_hit(rule["hand"], rule["melds"], sv)
            tot["seat_hyb_hit"] += tiles_hit(hand, melds, sv)
            tot["seat_rule_ok"] += rs_ok
            tot["seat_rule_bad"] += r_auto and not rs_ok
            tot["seat_hyb_ok"] += hs_ok
            tot["seat_hyb_bad"] += h_auto and not hs_ok
            tot["hyb_auto"] += h_auto
            if not a.dry:
                print(ph, scene, "규칙", "O" if rs_ok else "X", len(rule["hand"]), "장", "hybrid", "O" if hs_ok else "X", len(hand), "장",
                      "자동" if h_auto else "-", flush=True)
    if a.dry:
        print("돌기 확인:", tot["n"], "장 처리(점수는 안 찍음)")
        return
    tot["rectified"] = rectified
    by: dict = {}
    for r in rows.values():
        by.setdefault(r["scene"], []).append(r["seat_ok"]["hybrid"])
    tot["seat_hyb_scene"] = sum(sum(v) * 2 > len(v) for v in by.values())
    print(f"=== 장면 단위(사진 과반 맞음) hybrid {tot['seat_hyb_scene']}/{len(by)}", {k: f"{sum(v)}/{len(v)}" for k, v in by.items()})
    print(f"=== 자리 채점(화료패 뺀 13장) /{tot['n']}: 규칙 {tot['seat_rule_ok']}(틀린 자동 {tot['seat_rule_bad']}) | hybrid {tot['seat_hyb_ok']}"
          f"(틀린 자동 {tot['seat_hyb_bad']}, 자동 {tot['hyb_auto']}) | 패 단위 규칙 {tot['seat_rule_hit']}/{tot['seat_want']} hybrid {tot['seat_hyb_hit']}/{tot['seat_want']}")
    print(f"--- 테스트 /{tot['n']}(편 사진 {rectified}): 규칙 {tot['rule_ok']}(틀린 자동 반영 {tot['rule_bad']}) | hybrid {tot['hyb_ok']}(틀린 자동 반영 {tot['hyb_bad']})"
          f" | 패 단위 규칙 {tot['rule_hit']}/{tot['want']} hybrid {tot['hyb_hit']}/{tot['want']}")
    tag = a.det + ("_obb" if a.obb else "") + ("_rotcut" if a.rot_cut else "") + ("_clean" if a.clean else "") + ("_haku2" if a.haku2 else "") + ("_cornerfix" if a.corner_fix else "") + ("_loosectx" if a.loose_ctx else "") + ("_recolored" if a.recolored else "") + ("_rect" if a.rectify else "") + ("_seat2" if a.seat_det == "none" else "") + a.suffix
    (OUT / f"field_{tag}.json").write_text(json.dumps(dict(total=tot, rows=rows), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
