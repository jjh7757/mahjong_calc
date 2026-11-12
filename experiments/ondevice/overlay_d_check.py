"""겹쳐 보기 D 경로 PC 확인(실험 5a, 2026-11-12, `docs/role_owner_plan_1111.md` 5단계 "5단계 방법·기준 확정"). 학습 없음, 기기 없음.

세트·준비는 `overlay_score.py --models prod` 와 같다: `rs.scenes("dev")` 40장 + 저장 격자(x1·x2·y1·y2), 운영 모델 조합(`robust_suite.Readers("prod", 4)`,
역할 A = 운영 ONNX tile-roles-v3r15d), 재저장 생략(ondevice.PREP 기본 skip). 장면마다 같은 판독기를 세 번 부른다.
  ① 고치기 전 사본 `build/ondevice_before_d.py` 의 overlay(role 없음)
  ② 고친 `android/app/src/main/python/ondevice.py` 의 overlay(role 없음)
  ③ 고친 ondevice.overlay(role=d) — D ONNX 는 ONDEVICE_ROLE_D = server_bench/models/tile-roles-owner-d.onnx
기준(재기 전에 계획서에 적힌 것):
  (5a-3) ① 과 ② 의 tiles 가 완전히 같음(모든 칸: b·t·tc·r·rc·s), backs·w·h 도 같음 — 40장 모두.
  (5a-2) ③ 의 상자별 답(b·t·r·s)이 표 4-6 운영 조합 D(`results/overlay_score_d_prod_1112.json` 의 scenes[이름].D.tiles, torch role_D_all.pt)와
         40장 모두 같음. tc 도 견줌. rc 는 torch 대 ONNX 라 소수 셋째 자리까지 같으면 됨 — 다른 상자 수·최대 차를 적는다.
  참고: ③ 에 overlay_score.scene_score 를 돌려 표 4-6 운영 D 줄(장면 36/40, 다른 자리 hand 장면 0, 화료자 패 528/528)이 재현되는지.
  시간(PC, 참고): ② 와 ③ 의 ms.roles(같은 구간 = 꼭짓점·뒷면 + 토큰 + 모델; A 4회, D 1회) 중앙 / p90 / 최대. 첫 장면 전에 세 경로를 한 번씩
         돌려 세션을 만들어 둔다(기록 안 함).

  python -X utf8 experiments/ondevice/overlay_d_check.py
결과 experiments/ondevice/results/overlay_d_check_1112.json.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
D_ONNX = ROOT / "experiments" / "tile_classifier" / "server_bench" / "models" / "tile-roles-owner-d.onnx"
os.environ["ONDEVICE_ROLE_D"] = str(D_ONNX)
sys.path.insert(0, str(HERE))
import overlay_score as osc  # noqa: E402  (ROBUST_* 환경 변수·서버·speed·android python 경로, 고친 ondevice 를 import)

import numpy as np  # noqa: E402

ondevice = osc.ondevice
rs = osc.rs
REF = HERE / "results" / "overlay_score_d_prod_1112.json"
OUT = HERE / "results" / "overlay_d_check_1112.json"
BEFORE = HERE / "build" / "ondevice_before_d.py"


def load_before():
    spec = importlib.util.spec_from_file_location("ondevice_before_d", BEFORE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmp_exact(a: dict, b: dict) -> dict:
    ta, tb = a["tiles"], b["tiles"]
    diff = [i for i, (p, q) in enumerate(zip(ta, tb)) if p != q]
    same = len(ta) == len(tb) and not diff and a["backs"] == b["backs"] and a["w"] == b["w"] and a["h"] == b["h"]
    return {"same": same, "n": [len(ta), len(tb)], "backs": [a["backs"], b["backs"]], "diff_idx": diff[:10]}


def cmp_ref(t: list, ref: list) -> dict:
    if len(t) != len(ref):
        return {"same": False, "n": [len(t), len(ref)], "hard": ["상자 수"], "rc_diff": 0, "rc_max": None, "tc_diff": 0}
    hard, rc_n, tc_n, rc_max = [], 0, 0, 0.0
    for i, (p, q) in enumerate(zip(t, ref)):
        bad = [k for k in ("b", "t", "r", "s") if p[k] != q[k]]
        if bad:
            hard.append({"i": i, "keys": bad, "onnx": {k: p[k] for k in bad}, "torch": {k: q[k] for k in bad}})
        tc_n += p["tc"] != q["tc"]
        if p["rc"] != q["rc"]:
            rc_n += 1
            rc_max = max(rc_max, abs(p["rc"] - q["rc"]))
    return {"same": not hard, "n": [len(t), len(ref)], "hard": hard[:10], "rc_diff": rc_n, "rc_max": round(rc_max, 4), "tc_diff": tc_n}


def q3(v) -> dict:
    v = np.asarray(v, float)
    return {"median": round(float(np.median(v)), 1), "p90": round(float(np.percentile(v, 90)), 1), "max": round(float(v.max()), 1), "n": int(len(v))}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    from app import roles

    t_all = time.time()
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    before = load_before()
    assert before.PREP == ondevice.PREP == "skip"
    ref = json.loads(REF.read_text(encoding="utf-8"))["scenes"]
    rd = rs.Readers("prod", 4)
    sset = rs.scenes("dev")
    assert len(sset) == 40 and all(s["name"] in ref for s in sset)

    def bind(name):
        (reader, net), files = rd.get(name)
        ondevice._reader = reader
        before._reader = reader
        roles.role_net = lambda net=net: net
        return files

    # 세션 만들기(기록 안 함)
    s0 = sset[0]
    bind(s0["name"])
    g0 = {k: str(s0["grid"][k]) for k in ("x1", "x2", "y1", "y2")}
    img0 = Path(s0["path"]).read_bytes()
    before.overlay(img0, g0), ondevice.overlay(img0, g0), ondevice.overlay(img0, dict(g0, role="d"))
    d_net = ondevice._get_role_d()
    d_io = {"path": str(d_net.path), "feat": d_net.feat, "inputs": [(i.name, i.shape) for i in d_net._session().get_inputs()],
            "outputs": [o.name for o in d_net._session().get_outputs()], "threads": d_net.threads}
    print("D 세션", d_io, flush=True)

    rows = {}
    for s in sset:
        name = s["name"]
        files = bind(name)
        g = {k: str(s["grid"][k]) for k in ("x1", "x2", "y1", "y2")}
        img = Path(s["path"]).read_bytes()
        oB = json.loads(before.overlay(img, g))
        oA = json.loads(ondevice.overlay(img, g))
        oD = json.loads(ondevice.overlay(img, dict(g, role="d")))
        c3 = cmp_exact(oB, oA)
        c2 = cmp_ref(oD["tiles"], ref[name]["D"]["tiles"])
        sc = osc.scene_score(oD["tiles"], s)
        r = {"set": s["set"], "side": s["side"], "models": files, "n": len(oD["tiles"]), "a5_3": c3, "a5_2": c2,
             "scene": {k: sc[k] for k in ("ok", "hand_ok", "meld_ok", "hit", "want", "other_hand", "other_hand_max")},
             "ref_scene_ok": ref[name]["D"]["ok"], "ms": {"before": oB["ms"], "A": oA["ms"], "D": oD["ms"]}, "tiles_D": oD["tiles"]}
        rows[name] = r
        print(f"{name[-6:]:>6s} 5a-3 {'=' if c3['same'] else '≠ ' + str(c3)} | 5a-2 {'=' if c2['same'] else '≠ ' + str(c2['hard'][:3])} rc다름 {c2['rc_diff']}"
              f" (최대 {c2['rc_max']}) tc다름 {c2['tc_diff']} | 장면 {'O' if sc['ok'] else 'X'} {sc['hit']}/{sc['want']} 헛 {sc['other_hand'] or '-'}"
              f" | roles ms A {oA['ms']['roles']} D {oD['ms']['roles']}", flush=True)

    n3 = sum(r["a5_3"]["same"] for r in rows.values())
    n2 = sum(r["a5_2"]["same"] for r in rows.values())
    rc_n = sum(r["a5_2"]["rc_diff"] for r in rows.values())
    rc_max = max((r["a5_2"]["rc_max"] or 0) for r in rows.values())
    tc_n = sum(r["a5_2"]["tc_diff"] for r in rows.values())
    boxes = sum(r["n"] for r in rows.values())
    scene_ok = sum(r["scene"]["ok"] for r in rows.values())
    oh = sum(r["scene"]["other_hand_max"] > 0 for r in rows.values())
    hit, want = sum(r["scene"]["hit"] for r in rows.values()), sum(r["scene"]["want"] for r in rows.values())
    same_scene_list = sum(r["scene"]["ok"] == r["ref_scene_ok"] for r in rows.values())
    verdict = {
        "5a-3": {"same_scenes": f"{n3}/{len(rows)}", "ok": n3 == len(rows)},
        "5a-2": {"same_scenes": f"{n2}/{len(rows)}", "boxes": boxes, "rc_diff_boxes": rc_n, "rc_max_diff": rc_max, "rc_ok_3dp": rc_max <= 0.001,
                 "tc_diff_boxes": tc_n, "ok": n2 == len(rows) and rc_max <= 0.001},
        "table_4_6_prod_D": {"scenes_ok": f"{scene_ok}/{len(rows)}", "other_hand_scenes": oh, "hit": f"{hit}/{want}",
                             "want": "36/40, 0, 528/528", "per_scene_ok_same_as_ref": f"{same_scene_list}/{len(rows)}",
                             "ok": scene_ok == 36 and oh == 0 and hit == 528 and want == 528},
    }
    timing = {"roles_A_4calls_ms": q3([r["ms"]["A"]["roles"] for r in rows.values()]), "roles_D_1call_ms": q3([r["ms"]["D"]["roles"] for r in rows.values()]),
              "roles_before_ms": q3([r["ms"]["before"]["roles"] for r in rows.values()]),
              "total_A_ms": q3([r["ms"]["A"]["total"] for r in rows.values()]), "total_D_ms": q3([r["ms"]["D"]["total"] for r in rows.values()]),
              "note": "PC 노트북, onnxruntime(진짜) CPU, 역할 세션 스레드 2(RoleNet 기본 — prod 의 A 는 Readers threads 4), 검출·분류 스레드 4. "
                      "ms.roles = 꼭짓점·뒷면 + 토큰 + 모델(A 4회 / D 1회), 같은 구간. 장면마다 before → A → D 순서로 이어서. 표 4-6 의 PC 시간(torch, 토큰 + 모델만)과 구간이 다름"}
    meta = {"started": started, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "secs": round(time.time() - t_all, 1), "recognizer": rs.git_sha(), "prep": ondevice.PREP,
            "models": "prod (robust_suite.Readers('prod', 4), 역할 A = 운영 ONNX)", "d_onnx": str(D_ONNX.relative_to(ROOT)), "d_session": d_io,
            "ref": str(REF.relative_to(ROOT)), "before": str(BEFORE.relative_to(ROOT)),
            "cmd": "python -X utf8 experiments/ondevice/overlay_d_check.py"}
    OUT.write_text(json.dumps({"_meta": meta, "verdict": verdict, "timing": timing, "scenes": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n판정", json.dumps(verdict, ensure_ascii=False))
    print("시간", json.dumps(timing, ensure_ascii=False))
    print("→", OUT, f"{meta['secs']}초")


if __name__ == "__main__":
    main()
