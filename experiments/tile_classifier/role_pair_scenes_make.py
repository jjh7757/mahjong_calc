"""0단계 장면 목록·표시패 정답 고정(2026-11-16, `docs/role_pair_plan_1116.md` 5절 0단계 1). 학습·판독 없음.

대상 = `seat_grow.eval_scenes()` 40장면(B·C·D 6 + 10-31 20 + 11-07 14, 가림·사용자 문제 뺌).
정답은 저장 정답(B·C·D `dora_group_locate.TRUTH`·`flow_riichi.BCD_YES`, 10-31 `truth.json`/`label.json`, 11-07 `label.json`)을 출발점으로,
**원본 사진을 직접 확대해 본 값**으로 적는다(아래 PHOTO). 저장 정답과 다르거나 확신이 안 서는 장면은 check 에 이유를 적고
`data/user_check_1116/pair_scenes/` 에 그림을 만든다(role_pair_scenes_draw.py).
  table_pair = 패산에서 떼어 펠트 위에 내놓은 앞면 표시패(보통 2장, 순서 무관)
  wall       = 패산 줄 위에 뒤집힌 표시패
  set        = E2(table_pair 있음) | E4(table_pair 없음)
결과 → experiments/tile_classifier/role_pair_scenes.json(이 스크립트가 쓰고, 채점 스크립트는 읽기만).

  python -X utf8 experiments/tile_classifier/role_pair_scenes_make.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "speed"))
import seat_grow as sg  # noqa: E402

OUT = HERE / "role_pair_scenes.json"
TRUTH1031 = json.loads((ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]

# B·C·D: 저장 정답 = dora_group_locate.TRUTH(표시패 묶음), 리치 = flow_riichi.BCD_YES(리치한 자리) 에 화료자 자리가 있나
BCD_STORED = {"k25": ["1z", "7m"], "k28": ["1z", "7m"], "k15": ["7m", "6s"], "k26": ["7m", "6s"], "k12": ["4p", "4p", "7m"], "k16": ["4p", "4p", "7m"]}
BCD_RIICHI = {"k25": {"bottom", "left"}, "k28": {"bottom", "left"}, "k15": {"left"}, "k26": {"left"}, "k12": {"top", "bottom"}, "k16": {"top", "bottom"}}

# 사진 확대로 읽은 값(2026-11-16, 이 세션). (탁자 위 짝, 패산 위, 메모, 사용자 확인 이유 또는 None)
PHOTO = {
    "k25": (["1z", "7m"], [], "연출(사용자가 도라를 왕패 밖으로 옮김, dora_locate.WALL_DORA 주석). 왼쪽 위 펠트에 東·七萬 2장 붙여 둠. 화료자(오른쪽)는 리치 아님", None),
    "k28": (["1z", "7m"], [], "k25 와 같은 배치", None),
    "k15": (["7m", "6s"], [], "七萬·6삭 2장을 왼쪽 아래 패산 끝(뒷면 줄) 바로 옆 펠트 위에 세로로 붙여 둠. dora_locate.WALL_DORA 는 '왕패 옆 원래' 로 적었고 "
            "서버 read_wall 주석은 '진짜 짝(k15·k26)' 으로 적음 — 탁자 위 짝으로 적음",
            "패산 끝에 붙은 2장이라 '탁자 위 짝' 인지 '패산 위' 인지 위치 판단이 갈릴 수 있음"),
    "k26": (["7m", "6s"], [], "k15 와 같은 배치", "k15 와 같음"),
    "k12": (["4p", "4p", "7m"], [], "연출. 오른쪽 아래 펠트에 4통·4통·七萬 3장 나란히(짝 2장이 아니라 3장)", None),
    "k16": (["4p", "4p", "7m"], [], "k12 와 같은 배치", None),
    "20261031_123140": ([], ["5s"], "아래 패산 위 5삭", None),
    "20261031_124654": ([], ["7m"], "리치 화료지만 뒷도라를 안 뒤집음, 왼쪽 패산 위 七萬 1장", None),
    "20261031_125839": ([], ["5m"], "왼쪽 패산 위 伍萬(검은 伍 — 적5 아님). label.json 의 4m 은 틀림(truth.json 이 이미 고침)", None),
    "20261031_130743": ([], ["4z"], "위 패산 위 北", None),
    "20261031_131411": ([], ["4z"], "위 패산 위 北. 오른쪽 위 펠트의 낱장 萬子 1장은 짝 아님(낱장)", None),
    "20261031_132239": ([], ["3p"], "위 패산 위 3통", None),
    "20261031_132954": ([], ["7s"], "위 패산 위 7삭", None),
    "20261031_133030": ([], ["7s"], "132954 와 같은 탁자, 위 패산 위 7삭", None),
    "20261031_133826": (["8m", "4p"], [], "왼쪽 아래 펠트에 八萬·4통 세로로 붙여 둠", None),
    "20261031_134815": ([], ["1z"], "왼쪽 아래 패산 위 東", None),
    "20261031_143104": (["6p", "3s"], [], "오른쪽 아래 펠트에 6통·3삭. 손패 앞 낱장 7삭은 떼어 둔 화료패", None),
    "20261031_164501": ([], ["5p"], "오른쪽 패산 위 5통(적5 아님)", None),
    "20261031_165043": ([], ["9p"], "오른쪽 위 패산 위 9통", None),
    "20261031_165614": ([], ["1z", "5z"], "리치 화료, 오른쪽 패산 위 東·白 2장 나란히(도라 + 깡도라로 보임). 왼쪽 위 낱장 8통은 떼어 둔 화료패", None),
    "20261031_170105": (["5s", "5p"], [], "손패 앞 펠트에 5삭·5통 비스듬히 붙여 둠(적5 아님)", None),
    "20261031_171025": (["7s", "6z"], [], "손패 아래쪽 펠트에 7삭·發 비스듬히", None),
    "20261031_171245": ([], ["7z"], "오른쪽 아래 패산 위 中(손이 가까이 지나가며 흐림, 읽을 수 있음)", None),
    "20261031_171505": ([], ["4m"], "아래 패산 위 四萬. 손패 끝 낱장 三萬은 떼어 둔 화료패", None),
    "20261031_181209": ([], ["7m", "4s"], "리치 화료, 왼쪽 패산 줄 안에 七萬·4삭 2장이 나란히 앞면(펠트 위로 내놓지 않음). 왼쪽 아래 낱장 8삭은 떼어 둔 화료패", None),
    "20261031_183627": (["7s", "4m"], [], "가운데 오른쪽 위 펠트에 7삭·四萬 세로로. 오른쪽 위 낱장 四萬은 떼어 둔 화료패", None),
    "20261107_121515": (["8s", "9s"], [], "아래 펠트에 8삭·9삭", None),
    "20261107_122315": (["7s", "2s"], [], "아래 펠트에 7삭(거꾸로)·2삭 2장. label.json 은 7s 1장만(뒷도라 2s 를 앱 기록에 안 넣음)", "label.json [7s] 와 다름 — 사진은 2장"),
    "20261107_123102": ([], ["2z"], "위 패산 위 南", None),
    "20261107_123721": (["4z", "3m"], [], "왼쪽 아래 펠트에 北·三萬", None),
    "20261107_124650": (["9m", "4m"], [], "왼쪽 펠트에 九萬·四萬", None),
    "20261107_125510": (["5p", "8m"], [], "왼쪽 위 펠트에 5통·八萬(거꾸로)", None),
    "20261107_130623": ([], ["4p"], "위 패산 위 4통", None),
    "20261107_140015": ([], ["4s"], "오른쪽 아래 패산 위 4삭", None),
    "20261107_153029": (["8p", "6z"], [], "왼쪽 손패 끝 옆 펠트에 8통·發 비스듬히 2장. 패산에 앞면 패 없음. label.json 은 [1z] — 사진에 東 표시패가 안 보임",
                        "label.json [1z] 와 다름 — 사진은 8통·發 2장"),
    "20261107_153311": ([], ["6m"], "오른쪽 아래 패산 위 六萬. 손패 오른쪽 눕힌 4통은 떼어 둔 쯔모패", None),
    "20261107_153939": (["6s", "7m"], [], "가운데 오른쪽 아래 펠트에 6삭·七萬. 오른쪽 아래 패산 위에 앞면이 옆(왼쪽)을 향해 기운 패 1장이 있음 — 무늬를 읽을 수 없어 표시패로 안 셈",
                        "패산 위 기운 패 1장(읽을 수 없음)을 표시패가 아닌 것으로 적음"),
    "20261107_154417": (["6p", "6m"], [], "위(화료자) 손패 뒤 펠트에 6통·六萬", None),
    "20261107_154904": (["6m", "1m"], [], "오른쪽 위 펠트에 六萬·一萬(손가락이 가까이 있으나 가리지 않음)", None),
    "20261107_155553": ([], ["6s"], "왼쪽 아래 패산 위 6삭. 아래 자리 손패 줄의 앞면 南 1장은 표시패 아님", None),
}


def stored(s: dict) -> tuple[list[str] | None, bool | None, str]:
    """(저장 표시패 목록 — 위치 구분 없음, 리치, 출처)."""
    n = s["name"]
    if s["set"] == "bcd":
        return BCD_STORED[n], s["side"] in BCD_RIICHI[n], "experiments/speed/dora_group_locate.py TRUTH · flow_riichi.py BCD_YES"
    if n in TRUTH1031 and "indicators" in TRUTH1031[n]:
        t = TRUTH1031[n]
        return list(t["indicators"]), t.get("riichi"), "experiments/visit_20261031/truth.json"
    lab = s["path"].parent / "label.json"
    if lab.exists():
        j = json.loads(lab.read_text(encoding="utf-8"))
        return list(j.get("dora_indicators") or []) + list(j.get("ura_indicators") or []), j.get("riichi"), str(lab.relative_to(ROOT)).replace("\\", "/")
    return None, None, "없음"


def main() -> None:
    rows = []
    for s in sg.eval_scenes():
        n = s["name"]
        pair, wall, memo, check = PHOTO[n]
        st, riichi, src = stored(s)
        same = sorted(st or []) == sorted(pair + wall)
        rows.append({
            "name": n, "set_src": s["set"], "winner": s["side"], "riichi": riichi,
            "table_pair": pair, "wall": wall, "eval": "E2" if pair else "E4",
            "stored": st, "stored_src": src, "stored_same": same,
            "truth_src": "사진 확대(2026-11-16)" + ("" if same else " — 저장 정답과 다름"),
            "memo": memo, "user_check": check,
        })
    assert len(rows) == 40 and set(PHOTO) == {r["name"] for r in rows}, (len(rows), set(PHOTO) ^ {r["name"] for r in rows})
    out = {"_설명": __doc__.split("\n\n")[0], "made": time.strftime("%Y-%m-%d %H:%M:%S"),
           "counts": {"E2": sum(r["eval"] == "E2" for r in rows), "E4": sum(r["eval"] == "E4" for r in rows)},
           "user_check": [r["name"] for r in rows if r["user_check"] or not r["stored_same"]], "scenes": rows}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out["counts"], "확인 목록", out["user_check"])
    for r in rows:
        if not r["stored_same"]:
            print("저장과 다름", r["name"], "저장", r["stored"], "사진", r["table_pair"], r["wall"])


if __name__ == "__main__":
    main()
