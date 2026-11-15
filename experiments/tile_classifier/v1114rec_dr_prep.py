"""녹화 프레임(rec1496) 검출·역할 눈 확인 준비 + 초안 수 세기(2026-11-15, 녹화 세트 2단계 5). v1114rec_draft.py 다음에(v1114rec_sheets.py 뒤면 패 종류 몫도 센다).

v1114_dr_prep.py 와 같은 꼴:
  data/v1114rec/dr/review/_FORMAT.json + 판마다 빈 review/<판>.json(이미 있으면 건드리지 않음). 그림 칸에 flags(+ between) 와 phase(play|end) 가 더 있다.
  data/v1114rec/dr/shares.json   검출·역할 눈 확인 5몫(판 단위, 그림 수·상자 수 비슷하게 — v1114rec_sheets.balance).
  data/v1114rec/dr/counts.json   검출·역할 초안 수(정확도 아님), part·split 별.
  data/v1114rec/draft/_summary.json  패 종류 초안 수(그림·앞면·뒷면·실물 패·SPLIT·LOW·NB?·이웃 라벨 붙은 상자), part·split 별.
  python -X utf8 experiments/tile_classifier/v1114rec_dr_prep.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from v1114rec_sheets import balance  # noqa: E402

R = HERE / "data" / "v1114rec"
DR = R / "dr"
NAMES = ("S1", "S2", "S3", "S4", "S5")

FORMAT = {
    "what": "녹화 프레임(rec1496) 검출·역할 눈 확인 결과. 판마다 review/<판 id>.json 하나. 확인 그림 sheets/<판>/<그림 이름>/{det_all,det_q1..q4,role}.jpg 와 "
            "초안 draft/<판>.json 을 보고 채운다. 도우미 v1114rec_dr_fit.py(add·addbox·nudge·near·refit·drop·restore·flip·role·ok·flag·phase·note·seen·show·status)가 "
            "이 파일을 대신 고쳐 준다. 꼴은 기존 data/v1114/dr/review/_FORMAT.json 과 같고 그림 칸에 phase 와 flags 의 between 이 더 있다.",
    "coords": "모든 좌표 = 녹화 프레임 원래 픽셀(1496×1496). 확인 그림 가장자리 눈금도 1496 좌표(det_all 은 1배, 조각 det_q* 는 2배로 키운 그림, role 은 4/3배).",
    "top": {"round": "판 id", "reviewer": "검토한 에이전트 이름(예: S1)", "done": "판의 모든 그림을 seen 으로 했으면 true",
            "images": "{그림 id: 아래 칸} — 판의 고른 그림이 모두 미리 들어 있다(빼지 말 것)"},
    "image": {
        "seen": "① 이 그림의 모든 상자(앞면·뒷면)와 놓친 패를 다 봤으면 true. 모든 그림에 필요(flags·phase 를 먼저 정해야 함)",
        "flags": "② 그림 단위 표시. null = 아직 안 정함. [] = 정상. 그 밖은 목록: blur(흔들림 — 패 무늬가 번짐), occluded(큰 가림 — 손·팔이 탁자의 큰 부분을 덮음), "
                 "not_table(탁자 아님), between(대국 중이 아님: 빈 탁자·배패 중·패를 밀어 넣는 중·카메라 거치 중). 초안 짐작은 draft images[].flags_guess"
                 "(occluded 짐작은 살색 비율이라 많이 잡힌다 — 그림을 보고 정함). 표시가 있어도 상자 확인은 한다(목록에서 빼지 않음)",
        "phase": "③ play(판 중 — 강·울기·패산, 손패는 세워 둠) | end(공개 장면 — 화료·유국으로 손패를 펼침). between 이어도 가까운 쪽을 적는다. "
                 "초안 힌트 = draft images[].phase_hint(다 = 녹화 판 나눔에서 정한 값, 나 = 없음)",
        "box_edits": "④ 초안 상자 고침 {상자 번호(문자열): {op, note}}. op = drop(상자 지움: 패 아님·두 번 잡힘·반쪽) / restore(지운 상자를 되살림) / "
                      "flip(앞면 ↔ 뒷면) / refit(다시 맞춤 — rect·pts·box·fit 이 같이 들어감, 도우미로). 고칠 게 없는 상자는 적지 않는다",
        "adds": "⑤ 놓친 패 [{aid: a1…, cls: face|back, click: [x, y], rect, pts, box, fit: mask|axis|manual, role, seat, note}] — 도우미 add 로 만든다. "
                "앞면은 role·seat 도 채운다. add 가 엉뚱하게 맞추면 near <그림> x y 로 이웃 상자 크기·각도를 보고 addbox <그림> cx cy w h 각도 face|back "
                "[--role --seat] 로 회전 상자를 그대로 넣고(fit=manual), nudge <그림> <번호> dx dy [dw dh d각도] 로 다듬는다. 확인 그림 fitcheck/<판>/<그림>__<명령>_<번호>.jpg 를 꼭 열어 본다",
        "roles": "⑥ 앞면 역할·주인 고침 {상자 번호: {role, seat, note}} — 초안(draft boxes[].role_draft: 나는 이웃 라벨이 있으면 그것, 없으면 규칙)이 맞으면 적지 않는다"
                 "(seen=true 면 그대로 받아들인 것). role.jpg 빨간 꼬리표(규칙·모델 갈림)·보라 꼬리표(규칙·이웃 라벨 갈림)는 꼭 보고, 초안이 틀리면 맞는 값을 적는다",
        "notes": "⑦ 그림 메모(애매한 상자·판단 근거)",
    },
    "labels": {
        "detection": [
            "종류 0 앞면 = 무늬 면이 위로 보이는 패(강·펼친 손패·울기·도라 표시패·떼어 둔 화료패). 종류 1 뒷면 = 뒷면 색(이 매장은 연보라·분홍)이 보이는 패: "
            "패산(2단도 위에서 보이는 패 하나마다 상자 하나), 세운 손패(한 장에 하나), 안깡 양끝 뒷면.",
            "상자 하나 = 패 하나. 두 장을 묶은 상자·패 없는 상자는 고친다. 상자는 위에서 보이는 면에 맞게(회전 상자), 5° 미만 기울기는 축 상자도 됨.",
            "뚜렷이 절반 넘게 보일 때만 상자(손·팔·사진 끝에 가린 패 포함, 손에 들린 패 포함), 보이는 부분에 맞춤.",
            "탁자 밖(서랍·바닥·기기 판·점수 화면)의 물체, 흰 종이·카드·리치봉, 태블릿·휴대폰 화면 속 패는 패가 아님. 탁자 흰 테두리 위에 놓인 패(모서리 울기 등)는 패다.",
            "녹화는 1496 이라 패가 작다(긴 변 약 65px) — 붙은 패·패산 상자 나눔은 조각 그림(det_q*, 2배)에서 본다.",
            "이 초안에는 지운 상자가 없다(기존 세트와 달리 분류기 세트 not_tile 결과가 아직 없음) — 패 아닌 상자는 drop 한다.",
        ],
        "roles": [
            "역할은 앞면만: hand(펼친 손패) meld(울기 — 남의 울기도 meld, 주인으로만 구분) river(강) wall(패산 위 표시패) pair(화료자 쪽으로 옮긴 표시패 짝) "
            "loose(떼어 둔 화료패) other(그 밖·누구 것인지 모름).",
            "주인 seat = 사진 기준 자리 bottom(아래) right(오른쪽) top(위) left(왼쪽): hand·loose = 든 사람, meld = 운 사람(울기는 운 사람의 오른손 쪽 모서리), "
            "river = 버린 사람(줄 위치·가로세로로 — 패 그림의 똑바로·거꾸로는 근거가 못 됨). wall·pair·other 는 주인 없음(-).",
            "판 중 프레임(phase play): 펼친 손패가 없는 게 보통(유국 텐파이 공개면 hand). 짝·떼어 둔 패는 보통 없음.",
            "공개 장면(phase end, draft format end): 화료자 = draft images[].winner(다 = 녹화 판 메모의 '… 자리 공개'). 탁자 위 표시패는 2장 이상일 때만 pair, "
            "펠트 위 낱장 1장은 loose(떼어 둔 화료패). 이 판들은 정답 기록이 없다 — 사진에 보이는 대로.",
            "왕패·표시패 위치는 주사위로 정해진다 — 선(친) 위치만으로 정하지 말 것. 패산 위에 앞면으로 뒤집힌 표시패 = wall.",
            "나(mid)의 이웃 라벨(nb_role·nb_seat)은 1분쯤 앞·뒤 그림의 눈 확인 끝난 값을 자리로 옮긴 것 — 그 사이 패가 옮겨졌으면 틀린다(보라 꼬리표).",
        ],
    },
    "example": {"round": "r01_112804", "reviewer": "S1", "done": False, "images": {"r01_112804/mid_1794624295353": {
        "seen": True, "flags": [], "phase": "play", "box_edits": {"40": {"op": "drop", "note": "흰 테두리 반사 — 패 아님"}},
        "adds": [{"aid": "a1", "cls": "back", "click": [1505, 800], "rect": [[1505, 800], [40, 55], 0.0], "pts": [], "box": [], "fit": "mask", "role": None, "seat": None, "note": ""}],
        "roles": {"12": {"role": "river", "seat": "left", "note": "리치 선언패(가로)"}}, "notes": ""}}},
}


def empty_image() -> dict:
    return {"seen": False, "flags": None, "phase": None, "box_edits": {}, "adds": [], "roles": {}, "notes": ""}


def main():
    (DR / "review").mkdir(parents=True, exist_ok=True)
    (DR / "review" / "_FORMAT.json").write_text(json.dumps(FORMAT, ensure_ascii=False, indent=1), encoding="utf-8")
    rounds = []
    tot = Counter()
    by = Counter()
    rule_roles, role_draft, flags = Counter(), Counter(), Counter()
    for p in sorted((DR / "draft").glob("[rn]*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        rid = d["round"]
        rp = DR / "review" / f"{rid}.json"
        if not rp.exists():
            rp.write_text(json.dumps({"round": rid, "part": d["part"], "reviewer": None, "done": False,
                                      "images": {im["id"]: empty_image() for im in d["images"]}}, ensure_ascii=False, indent=1), encoding="utf-8")
        nb = 0
        for im in d["images"]:
            keep = [b for b in im["boxes"] if b["status"] == "keep"]
            f = [b for b in keep if b["cls"] == "face"]
            bk = [b for b in keep if b["cls"] == "back"]
            nb += len(keep)
            g = (im["part"], im["split"])
            for kk, v in (("images", 1), ("face", len(f)), ("back", len(bk)), ("quad_face_added", sum(b["src"] == "quad" for b in f)),
                          ("split_role", sum("role" in b["split"] for b in f)), ("split_seat", sum("seat" in b["split"] for b in f)),
                          ("split_nb", sum("nb" in b["split"] for b in f)), ("nb_role_boxes", sum(bool(b.get("nb_role")) for b in f)),
                          ("nb_tile_boxes", sum(bool(b.get("nb_tile")) for b in f)), ("format_end", int(im["format"] == "end")),
                          ("setup", int(bool(im.get("setup")))), ("quad_face_white_drop", im["counts"]["quad_face_white_drop"]),
                          ("back_on_face_drop", im["counts"]["back_on_face_drop"])):
                by[(g, kk)] += v
                tot[kk] += v
            for b in f:
                rule_roles[f"{b['rule']['role']}/{b['rule']['seat'] or '-'}"] += 1
                role_draft[f"{b['role_draft']['role']}/{b['role_draft']['seat'] or '-'}"] += 1
            for x in (im["flags_guess"] or ["normal"]):
                flags[x] += 1
            tot[f"device_{im['device']['src']}"] += 1
            tot[f"winner_src_{im.get('winner_src')}"] += int(im["format"] == "end")
        rounds.append({"round": rid, "part": d["part"], "splits": d["splits"], "images": len(d["images"]), "boxes": nb})
    groups = [("mid", "train"), ("mid", "dev"), ("new", "train"), ("new", "dev")]
    keys = ("images", "face", "back", "quad_face_added", "split_role", "split_seat", "split_nb", "nb_tile_boxes", "nb_role_boxes", "format_end", "setup")
    counts = {"_note": "검출·역할 초안 수(정확도 아님). 좌표 1496. split_nb = 규칙 역할과 이웃 라벨이 다른 앞면, nb_* = 이웃 라벨이 붙은 앞면(나만). v1114rec_dr_prep.py",
              "totals": dict(tot), "by_part_split": {f"{a}/{b}": {k: by[((a, b), k)] for k in keys} for a, b in groups},
              "by_part": {a: {k: sum(by[((a, b), k)] for b in ("train", "dev")) for k in keys} for a in ("mid", "new")},
              "rule_role_seat": dict(rule_roles.most_common()), "role_draft_role_seat": dict(role_draft.most_common()), "flags_guess": dict(flags)}
    (DR / "counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=1), encoding="utf-8")
    sizes = {r["round"]: r for r in rounds}
    sh = balance(sizes, NAMES, ("images", "boxes"))
    for n in NAMES:
        sh[n]["detail"] = [{k: r[k] for k in ("round", "part", "images", "boxes")} for r in rounds if r["round"] in sh[n]["rounds"]]
    (DR / "shares.json").write_text(json.dumps({"_note": "검출·역할 눈 확인 5몫(판 단위, 한 판은 한 몫에만). boxes = 초안 상자(앞면+뒷면). v1114rec_dr_prep.py", "shares": sh},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    # 패 종류 초안 수
    ts = Counter()
    tby = Counter()
    for p in sorted((R / "draft").glob("[rn]*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        dd = json.loads((DR / "draft" / p.name).read_text(encoding="utf-8"))
        backs = {im["id"]: sum(b["cls"] == "back" for b in im["boxes"]) for im in dd["images"]}
        for im in d["images"]:
            g = (im["part"], im["split"])
            for kk, v in (("images", 1), ("face_boxes", len(im["boxes"])), ("back_boxes", backs[im["id"]]),
                          ("nb_tile_boxes", sum(bool(b.get("nb_tile")) for b in im["boxes"])), ("nb_q_boxes", sum(b["nb_q"] for b in im["boxes"])),
                          ("nb_conflict_boxes", sum(b["nb_conflict"] for b in im["boxes"])), ("small_crop_upscaled", sum(b["crop_long"] < 96 for b in im["boxes"])),
                          ("x2_read_differs", sum(b["t_x2"] != b["t"] for b in im["boxes"])),
                          ("nb_agree_1496", sum(bool(b.get("nb_tile")) and b["t"] == b["nb_tile"] for b in im["boxes"])),
                          ("nb_agree_x2", sum(bool(b.get("nb_tile")) and b["t_x2"] == b["nb_tile"] for b in im["boxes"]))):
                tby[(g, kk)] += v
        # 실물 패는 판 안 그림의 split 이 섞일 수 있어(나) 첫 그림의 split 로 셈
        sp = {im["id"]: im["split"] for im in d["images"]}
        for t in d["tracks"]:
            g = (d["part"], sp[t["first"]])
            for kk, v in (("tracks", 1), ("split", int(t["split"])), ("low", int(t["low"])), ("nb_q", int(t["nb_q"])),
                          ("draft_src_nb", int(t["draft_src"] == "nb")), ("draft_differs_cls", int(t["draft"] != t["cls_draft"]))):
                tby[(g, kk)] += v
    tkeys = ("images", "face_boxes", "back_boxes", "tracks", "split", "low", "nb_q", "draft_src_nb", "draft_differs_cls", "nb_tile_boxes", "nb_q_boxes",
             "nb_conflict_boxes", "nb_agree_1496", "nb_agree_x2", "small_crop_upscaled", "x2_read_differs")
    run = json.loads((R / "draft" / "_summary_run.json").read_text(encoding="utf-8")) if (R / "draft" / "_summary_run.json").exists() else {}
    tsum = {"_note": "패 종류 초안 수(정확도 아님). tracks = 실물 패, nb_q = NB?(분류기·이웃 라벨 다름) 실물 패, nb_*_boxes = 이웃 라벨 붙은 앞면 상자(나만), "
                     "nb_agree_1496/x2 = 이웃 라벨과 1496 크롭 읽기/2배 크롭 읽기가 같은 상자 수, small_crop_upscaled = 크롭 긴 변 96 미만이라 키워 읽은 상자. "
                     "v1114rec_dr_prep.py (그림별·판별 실행 기록은 _summary_run.json)",
            "models": run.get("models"), "how": run.get("how"),
            "totals": {k: sum(tby[(g, k)] for g in groups) for k in tkeys},
            "by_part_split": {f"{a}/{b}": {k: tby[((a, b), k)] for k in tkeys} for a, b in groups},
            "by_part": {a: {k: sum(tby[((a, b), k)] for b in ("train", "dev")) for k in tkeys} for a in ("mid", "new")}}
    (R / "draft" / "_summary.json").write_text(json.dumps(tsum, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"dr": counts["by_part_split"], "tile": tsum["by_part_split"]}, ensure_ascii=False, indent=1))
    for n in NAMES:
        print(n, sh[n]["rounds"], sh[n]["images"], sh[n]["boxes"])


if __name__ == "__main__":
    main()
