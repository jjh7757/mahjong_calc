"""사용자 답(answers_user.json) + 대조에서 정한 고침(OVERRIDES) → 채점에 쓰는 정답 한 벌(2026-11-17, 계획서 "추가 8").

  python -X utf8 truthnorm.py            # → _work/testtruth_1116/truth_final.json
차례마다:
  kind      tsumogiri | hand | call
  k_id      버린 패가 **차례를 시작할 때 줄**에서 왼쪽부터 몇 번째 패였나(패 자체 — 손패를 번호로 따라갈 때 필요한 값)
  k_pos     버리는 순간 줄에서 몇 번째 자리였나(뽑은 패는 빼고 셈). 버리기 전에 패를 옮겼으면 k_id 와 다르다
  j_closed  차례가 끝났을 때 뽑은 패가 줄(N장)에서 몇 번째에 서 있나
  ops       (11-17 칸 판부터) 0 ~ N+2 칸 위 동작 — 있으면 slotsim.py 로 다시 굴려 kind · k_id · k_pos · j_closed 를 정한다(페이지 계산은 안 믿음)
  status    slot(칸 판으로 적은 답 — OVERRIDES 보다 앞섬) | ops_error | confirmed(사용자 답 = 둘째 읽기) | fixed(메모·둘째 읽기·확대·정렬 검사로 고침, 사용자 확인 대기) | user_confirmed
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import slotsim as ss  # noqa: E402

BASE = hc.WORK / "testtruth_1116"
OVERRIDES = {
    "r11_d09": {"k_id": 12, "k_pos": 11, "j_closed": 5, "status": "user_confirmed",
                "why": "뽑은 패를 5번째에 끼운 뒤 12·13번째(끼운 패 포함 번호)를 맞바꾸고 12번째를 버림 — 맞바꿈은 사용자 메모 + 11-17 확인(둘째 읽기는 놓침). 자리로는 11번째, 패로는 원래 12번째."},
    "r14_d02": {"kind": "hand", "k_id": 9, "k_pos": 13, "j_closed": 13, "status": "confirmed",
                "why": "9번째 패를 빼서 뽑은 패 오른쪽 맨 끝에 두었다가 그 패를 버림, 뽑은 패는 끝 그대로 — 사용자 메모와 둘째 읽기가 같음(사용자는 칸을 비워 둠)."},
    "r19_d03": {"kind": "hand", "k_id": 13, "k_pos": 13, "j_closed": 13, "status": "user_confirmed",
                "why": "2·3번째 버림이 한 구간에 있음. 사용자 메모 '둘째: 쯔모패 14번째에 두고 13번째 패 버림' = 둘째 읽기(손에서 13, 확신 없음). 종류 칸만 쯔모기리로 골라져 있음. 정렬 검사로는 두 쪽 다 성립. → 사용자 확인(11-17): 그 구간에 버림이 두 번 — 첫째 쯔모기리(2번째 버림), 둘째가 14번째에 두고 13번째 패 버림(3번째 버림)."},
    "r19_d07": {"k_id": 6, "k_pos": 13, "j_closed": 7, "status": "user_confirmed",
                "why": "6번째 패를 끝으로 빼 두었다가 버림(사용자 메모 = 둘째 읽기). 버린 뒤 24:56.7~24:58.5 끝의 뽑은 패를 다시 집어 7번째에 끼움 — 둘째 읽기 + 확대(왼쪽 6장·틈) + 정렬 검사(7번째면 어긋남 0, 끝 그대로면 4). 처음 사용자 답은 끝 그대로(14). → 사용자 확인(11-17): 버리고 나서 뽑은 패를 다시 7번째에 끼운 것이 맞음."},
    # ── 시험 판 r12(11-17 사용자 답 13차례, 둘째 읽기와 12 같음 · 1 갈림)
    "r12_d03b": {"k_id": 13, "k_pos": 13, "j_closed": 1, "status": "confirmed",
                 "why": "사용자 메모 '쯔모패 1번칸에 넣고 14번째 패 버림' = 먼저 넣고 버림인데 그 칸을 안 켬(나간 칸 14 는 끼운 패까지 센 번호 → 원래 13번째). 둘째 읽기도 '맨 왼쪽에 먼저 끼우고 원래 13번째(맨 오른쪽)를 버림'. 적는 법만 다르고 내용은 같음. 거꾸로 복원해도 4s(맨 오른쪽)가 나가고 2m 이 1번째 — 정렬 어긋남 0."},
    # ── 시험 판 r17(11-17 사용자 답 11차례, 둘째 읽기와 8 같음 · 3 갈림)
    "r17_d03": {"k_id": 7, "k_pos": 7, "j_closed": 4, "status": "confirmed",
                "why": "사용자 메모 '쯔모패 1번칸에 두고 8번패 버림 … 쯔모패가 있던 칸을 1번이라고 하면' = 왼쪽 끝에 붙인 뽑은 패를 1번으로 센 번호 → 원래 7번째. 둘째 읽기도 원래 7번째(빈칸 왼쪽에 뽑은 패 + 6장, 오른쪽 6장). 들어간 칸 4 는 둘 다 같음. 정렬 검사: 7이면 판 전체 어긋남 9(모두 4z>1z 한 쌍 — 자패 놓는 버릇), 8이면 11."},
    "r17_d10": {"k_id": 13, "k_pos": 13, "j_closed": 1, "status": "confirmed",
                "why": "사용자 14 · 1(메모 없음) — r12 3b순과 같은 적는 법(왼쪽 끝에 먼저 붙인 뽑은 패까지 센 번호, 먼저 넣고 버림 칸 안 켬). 둘째 읽기 '왼쪽 끝에 먼저 붙이고 원래 13번째(오른쪽 끝)를 버림'. 버린 패 1z 가 복원한 줄의 13번째와 맞음."},
    "r17_d11": {"status": "confirmed",
                "why": "값은 사용자 답 그대로(3번째 버림, 뽑은 패는 메운 뒤 11번째). 둘째 읽기는 '오른쪽 끝 3장을 한꺼번에 뺐다 붙임 — 손 밑이라 순서 못 봄, 후보 14 · 13 · 12'(확신 없음)로 사용자 답이 후보 안. 세션이 프레임 확대(09:09.97~09:11.8): 뽑은 패는 붙인 자리에 손 안 닿은 채 서 있고(09:10.16~10.36) 원래 12 · 13번째가 줄에서 아래로 빠져 그 오른쪽으로 돌아가 붙음 → 뽑은 패 · 12 · 13 순서 — 사용자 메모와 같음. 복원하면 9s 를 뽑아 9s 9s 옆에 두고 4z 4z 를 오른쪽으로 넘긴 것(정렬 맞음)."},
    # ── 유국 판 r16(오른쪽 자리, 11-17 사용자 답 18차례 — 둘째 읽기는 아직 없음. 메모를 풀어 쓴 값, 사용자 확인 대기 = fixed)
    #    거꾸로 복원하면 매 순 손패가 s · p · m · 자패 순으로 놓이고 어긋난 이웃은 "끝에 세워 둔 직전 뽑은 패" 뿐.
    "r16_d04": {"k_id": 12, "k_pos": 12, "j_closed": 13, "status": "fixed",
                "why": "3 · 4순이 한 구간(버림 두 번). 칸에는 첫 버림 값(9 · 14)이 그대로 들어 있고 메모 '두번째 버림: 쯔모패 14 → 12번패 버림 → 패 정리해서 13위치' 가 이 차례."},
    "r16_d07": {"kind": "tsumogiri", "k_id": None, "k_pos": None, "j_closed": None, "status": "fixed",
                "why": "6 · 7순이 한 구간. 칸에는 첫 버림 값(손에서 13)이 들어 있고 메모 '두번째 버림: 쯔모기리' 가 이 차례."},
    "r16_d08": {"k_id": 12, "k_pos": 12, "j_closed": 1, "status": "fixed",
                "why": "메모 '쯔모패 1 → 13패 버리고 14패 왼쪽으로 밀어서 정리' — 14패가 있으려면 왼쪽 끝에 붙인 뽑은 패를 1번으로 센 번호(r12 3b순 · r17 3 · 10순과 같은 적는 법) → 원래 12번째. 복원하면 9m(8m 옆)이 나가고 끝의 2p 가 남음; 원래 13번째로 보면 2p 가 m 사이에 낌."},
    "r16_d13": {"k_id": 12, "k_pos": 12, "j_closed": 1, "status": "fixed", "moves": [[3, 13]],
                "why": "12 · 13순이 한 구간. 칸에는 첫 버림 값(12 · 14)이 들어 있고 메모 '두번째 버림: 쯔모패 1 → 3번째 패 15번째로 이동 → 14번째 패 3번째로 이동 → 15번째 왼쪽으로 밀어서 14 → 13 버림' 이 이 차례(뽑은 패를 1번으로 센 번호). 풀면: 뽑은 패는 왼쪽 끝(1번째), 원래 12번째를 버림, **원래 13번째가 원래 2번째 자리로 · 원래 2번째가 맨 끝으로**(차례 끝 줄에서 3번째 ↔ 13번째 맞바꿈과 같음 — moves). 복원: 1s 를 뽑아 왼쪽 끝, 12순에 뽑은 3s 를 3s 옆으로, 겹친 2s 를 끝으로 빼 둠(16순 리치 선언 때 그 2s 를 버림). 맞바꿈을 빼면 12순에 뽑은 패가 3s 가 아니라 2s 가 됨. **종류 · 패 번호 · 들어간 칸만으로는 이 옮김을 못 적는다.**"},
    "r16_d16": {"k_id": 13, "k_pos": 13, "j_closed": 8, "status": "fixed",
                "why": "먼저 넣고 버림인데 나간 칸이 빔. 메모 '쯔모패 14 → 7로 이동 → 7, 8번 패 위치 교환 → 14번패 버림' → 뽑은 패는 8번째, 버린 것은 원래 13번째(끝에 빼 둔 2s). 복원: 7s 를 6s 앞에 넣었다가 맞바꿔 6s 7s 8s."},
}


def main():
    ans = hc.jload(BASE / "answers_user.json")
    out = {}
    for g in hc.jload(BASE / "turns.json")["games"]:
        if g["han"] != 2:
            continue
        if not all((ans.get(t["id"]) or {}).get("kind") or t["id"] in OVERRIDES for t in g["turns"]):
            continue  # 다 적지 않은 판은 정답에 넣지 않는다(11-17 — 적는 중인 판이 섞여 들어가지 않게)
        for t in g["turns"]:
            a = ans.get(t["id"]) or {}
            row = {"game": g["id"], "label": t.get("label", str(t["i"])), "tile": t["tile"], "kind": a.get("kind"), "status": "confirmed", "note": a.get("note") or ""}
            if a.get("ops") and a.get("kind") in ("hand", "tsumogiri"):
                n = a.get("n") or t.get("n_calc") or 13
                try:
                    res = ss.run_ops(a["ops"], n).result()
                    row.update(kind=res["kind"], ops=a["ops"], n=n, order=res["order"], reordered=res["reordered"])
                    if res["kind"] == "hand":
                        row.update(k_id=res["k_id"], k_pos=res["k_pos"] if res["k_pos"] is not None else res["k_id"], j_closed=res["j_closed"])
                except ss.SlotError as e:
                    row.update(status="ops_error", ops=a["ops"], ops_error=str(e))
                    print(f"!! {t['id']} 칸 동작 검산 걸림: {e}  ({a['ops']})")
            elif a.get("kind") == "hand":
                k = a.get("k_orig", a.get("k"))
                row.update(k_id=a.get("discard_tile_orig", k), k_pos=k, j_closed=a.get("j_closed"))
            ov = OVERRIDES.get(t["id"], {})
            if a.get("ops") and ov:  # 칸 판으로 다시 적은 답이 예전 번호 답을 고친 것(OVERRIDES)보다 앞선다
                diff = {k: (ov[k], row.get(k)) for k in ("kind", "k_id", "j_closed") if k in ov and ov[k] != row.get(k)}
                if diff:
                    print(f"** {t['id']} 칸 판 답이 예전 고침과 다름(고침, 칸 판): {diff}")
                row["status"] = row["status"] if row["status"] == "ops_error" else "slot"
            else:
                row.update(ov)
            out[t["id"]] = row
    hc.jsave(BASE / "truth_final.json", out)
    for i, r in out.items():
        print(i, r["kind"], r.get("k_id", ""), r.get("k_pos", ""), r.get("j_closed", ""), r["status"])


if __name__ == "__main__":
    main()
