"""검출·역할 2단계 준비(2026-11-15, 검출·역할 세트 1단계 D·E·F). v1114_dr_draft.py 다음에.

D. data/v1114/dr/review/_FORMAT.json(양식 설명) + 판마다 빈 review/<판>.json(이미 있으면 건드리지 않음 — --force 도 없음, 지우고 다시).
E. 2단계 몫 넷(판 단위, 그림 수·상자 수가 비슷하게 — 그림 비율 + 상자 비율 합이 가장 작은 몫에 큰 판부터) → dr/shares.json
F. 초안 수 세기(정확도 아님) → dr/counts.json, 화면에도.
  python -X utf8 experiments/tile_classifier/v1114_dr_prep.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DR = HERE / "data" / "v1114" / "dr"
NAMES = ("S1", "S2", "S3", "S4")

FORMAT = {
    "what": "검출·역할 2단계 눈 확인 결과. 판마다 review/<판 id>.json 하나. 확인 그림 sheets/<판>/<그림 이름>/{det_all,det_q1..q4,role}.jpg 와 "
            "초안 draft/<판>.json 을 보고 채운다. 가장 쉬운 방법은 도우미 v1114_dr_fit.py(add·refit·drop·restore·flip·role·flag·note·seen) — 이 파일을 대신 고쳐 준다.",
    "top": {"round": "판 id", "reviewer": "검토한 에이전트 이름(예: S1)", "done": "판의 모든 그림을 seen 으로 했으면 true",
            "images": "{그림 id: 아래 칸} — 판의 고른 그림이 모두 미리 들어 있다(빼지 말 것)"},
    "image": {
        "seen": "① 이 그림의 모든 상자(앞면·뒷면·지운 상자)와 놓친 패를 다 봤으면 true. 모든 그림에 필요",
        "flags": "② 그림 단위 표시. null = 아직 안 정함. [] = 정상. 그 밖은 목록: blur(흔들림 — 패 무늬가 번짐), occluded(큰 가림 — 손·팔이 탁자의 큰 부분을 덮음), "
                 "not_table(탁자 아님 — 점수표 종이 등). 초안 짐작은 draft images[].flags_guess. 표시가 있어도 상자 확인은 한다(목록에서 빼지 않음)",
        "box_edits": "③ 초안 상자 고침 {상자 번호(문자열): {op, note}}. op = drop(상자 지움: 패 아님·두 번 잡힘·반쪽) / restore(지운 초안 앞면 = 회색 점선 x 를 되살림) / "
                      "flip(앞면 ↔ 뒷면) / refit(다시 맞춤 — rect·pts·box·fit 이 같이 들어감, 도우미로). 고칠 게 없는 상자는 적지 않는다",
        "adds": "④ 놓친 패 [{aid: a1…, cls: face|back, click: [x, y](준 점), rect, pts, box, fit: mask|axis|manual, role, seat, note}] — 도우미 add 로 만든다. "
                "앞면은 role·seat 도 채운다. 손에 들린·손가락에 가린 패처럼 add 가 엉뚱하게 맞추면 near <그림> x y 로 이웃 상자 크기·각도를 보고 "
                "addbox <그림> cx cy w h 각도 face|back [--role --seat] 로 회전 상자를 그대로 넣고(fit=manual), nudge <그림> <번호> dx dy [dw dh d각도] 로 다듬는다"
                "(초안 상자에 nudge 하면 box_edits 의 refit 으로 남음). 확인 그림 fitcheck/<판>/<그림>__{addbox,nudge}_<번호>.jpg 를 꼭 열어 본다",
        "roles": "⑤ 앞면 역할·주인 고침 {상자 번호: {role, seat, note}} — 초안(draft boxes[].rule)이 맞으면 적지 않는다(seen=true 면 그대로 받아들인 것). "
                 "규칙·모델이 갈린 상자(role.jpg 빨간 꼬리표, draft split)는 꼭 보고 맞는 쪽을 적거나(규칙이 맞으면 적지 않음) 둘 다 틀리면 고친 값",
        "notes": "⑥ 그림 메모(애매한 상자·판단 근거)",
    },
    "labels": {
        "detection": [
            "종류 0 앞면 = 무늬 면이 위로 보이는 패(강·펼친 손패·울기·도라 표시패·떼어 둔 화료패). 종류 1 뒷면 = 뒷면 색(이 매장은 연보라·분홍)이 보이는 패: "
            "패산(2단도 위에서 보이는 패 하나마다 상자 하나), 세운 손패(한 장에 하나), 안깡 양끝 뒷면.",
            "상자 하나 = 패 하나. 두 장을 묶은 상자·패 없는 상자·종류 틀린 상자는 고친다. 상자는 위에서 보이는 면에 맞게(회전 상자), 5° 미만 기울기는 축 상자도 됨.",
            "손·팔에 가린 패: 절반 넘게 보이면 상자, 아니면 없음. 사진 끝에서 잘린 패도 같은 기준(절반 넘게 보이면 상자).",
            "탁자 밖(서랍·바닥·기기 판·점수 화면)의 물체, 흰 종이·카드·리치봉은 패가 아님. 탁자 흰 테두리 위에 놓인 패(모서리 울기 등)는 패다.",
            "분류기 세트에서 unsure(종류 못 읽음)·가림으로 뺀 상자라도 패가 보이면 남긴다.",
        ],
        "roles": [
            "역할은 앞면만: hand(펼친 손패) meld(울기 — 남의 울기도 meld, 주인으로만 구분) river(강) wall(패산 위 표시패) pair(화료자 쪽으로 옮긴 표시패 짝) "
            "loose(떼어 둔 화료패) other(그 밖·누구 것인지 모름).",
            "주인 seat = 사진 기준 자리 bottom(아래) right(오른쪽) top(위) left(왼쪽): hand·loose = 든 사람, meld = 운 사람(울기는 운 사람의 오른손 쪽 모서리), "
            "river = 버린 사람(줄 위치·가로세로로 — 패 그림의 똑바로·거꾸로는 근거가 못 됨). wall·pair·other 는 주인 없음(-).",
            "판 중 프레임(format frame): 펼친 손패가 없는 게 보통(유국 텐파이 공개면 hand). 짝·떼어 둔 패는 보통 없음.",
            "화료 사진(format win): 화료자 = draft images[].winner. 탁자 위 표시패는 2장 이상(리치 화료의 도라+뒷도라)일 때만 pair, 펠트 위 낱장 1장은 loose(떼어 둔 화료패).",
            "왕패·표시패 위치는 주사위로 정해진다 — 선(친) 위치만으로 정하지 말 것. 패산 위에 앞면으로 뒤집힌 표시패 = wall.",
            "정답(label.json)과 어긋남(role.jpg 빨간 고리, draft label_mismatch·label_check.issues)은 참고일 뿐 — 사진에 보이는 대로 적는다.",
        ],
    },
    "example": {"round": "r01_112804", "reviewer": "S1", "done": False, "images": {"r01_112804/win_114614": {
        "seen": True, "flags": [], "box_edits": {"28": {"op": "drop", "note": "흰 테두리 위 리치봉 홈 덮개 — 패 아님"}},
        "adds": [{"aid": "a1", "cls": "back", "click": [3010, 1600], "rect": [[3010, 1600], [80, 110], 0.0], "pts": [], "box": [], "fit": "mask", "role": None, "seat": None, "note": ""}],
        "roles": {"12": {"role": "river", "seat": "left", "note": "리치 선언패(가로)"}}, "notes": ""}}},
}


def main():
    (DR / "review").mkdir(parents=True, exist_ok=True)
    (DR / "review" / "_FORMAT.json").write_text(json.dumps(FORMAT, ensure_ascii=False, indent=1), encoding="utf-8")
    rounds = []
    tot = Counter()
    roles_rule, roles_model, seats_rule, rs_rule = Counter(), Counter(), Counter(), Counter()
    flags = Counter()
    by_split = Counter()
    label_imgs, label_issue_imgs = 0, 0
    for p in sorted((DR / "draft").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        rid = d["round"]
        rp = DR / "review" / f"{rid}.json"
        if not rp.exists():
            rp.write_text(json.dumps({"round": rid, "reviewer": None, "done": False,
                                      "images": {im["id"]: {"seen": False, "flags": None, "box_edits": {}, "adds": [], "roles": {}, "notes": ""} for im in d["images"]}},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        nb = 0
        for im in d["images"]:
            keep = [b for b in im["boxes"] if b["status"] == "keep"]
            f = [b for b in keep if b["cls"] == "face"]
            bk = [b for b in keep if b["cls"] == "back"]
            nb += len(keep)
            sp = im["split_final"]
            by_split[(sp, "images")] += 1
            by_split[(sp, "face")] += len(f)
            by_split[(sp, "back")] += len(bk)
            tot["images"] += 1
            tot["face"] += len(f)
            tot["back"] += len(bk)
            tot["draft_face_in"] += sum(1 for b in im["boxes"] if b.get("src") == "v1114" or b.get("src") == "from_face")
            tot["dropped_face"] += sum(1 for b in im["boxes"] if b["status"] == "drop")
            tot["face_to_back"] += sum(1 for b in bk if b["src"] == "from_face")
            tot["quad_face_added"] += sum(1 for b in f if b["src"] == "quad")
            tot["quad_face_white_drop"] += im["counts"]["quad_face_white_drop"]
            tot["back_on_face_drop"] += im["counts"]["back_on_face_drop"]
            tot["face_kept_unsure"] += sum(1 for b in f if b.get("verdict") == "unsure")
            tot["face_kept_not_in_crops"] += sum(1 for b in f if b["src"] == "v1114" and b.get("tile_src") != "crops")
            for b in f:
                roles_rule[b["rule"]["role"]] += 1
                seats_rule[b["rule"]["seat"] or "-"] += 1
                rs_rule[f"{b['rule']['role']}/{b['rule']['seat'] or '-'}"] += 1
                if b.get("model"):
                    roles_model[b["model"]["role"]] += 1
                for s in b.get("split") or []:
                    tot[f"split_{s}"] += 1
                if b.get("label_mismatch"):
                    tot["label_mismatch_boxes"] += 1
            if im.get("label_check"):
                label_imgs += 1
                label_issue_imgs += bool(im["label_check"]["issues"])
                tot["label_issues"] += len(im["label_check"]["issues"])
            fl = im["flags_guess"] or ["normal"]
            for x in fl:
                flags[x] += 1
            flags["(any flag)"] += bool(im["flags_guess"])
            tot[f"format_{im['format']}"] += 1
            tot[f"device_{im['device']['src']}"] += 1
        rounds.append({"round": rid, "split_final": d["split_final"], "images": len(d["images"]), "boxes": nb})
    # E. 몫 넷
    TI, TB = sum(r["images"] for r in rounds), sum(r["boxes"] for r in rounds)
    shares = {n: {"rounds": [], "images": 0, "boxes": 0} for n in NAMES}
    for r in sorted(rounds, key=lambda r: -(r["images"] / TI + r["boxes"] / TB)):
        n = min(NAMES, key=lambda n: shares[n]["images"] / TI + shares[n]["boxes"] / TB)
        shares[n]["rounds"].append(r["round"])
        shares[n]["images"] += r["images"]
        shares[n]["boxes"] += r["boxes"]
    for n in NAMES:
        shares[n]["rounds"].sort()
        shares[n]["detail"] = [r for r in rounds if r["round"] in shares[n]["rounds"]]
    (DR / "shares.json").write_text(json.dumps({"_note": "2단계 몫(판 단위). boxes = 초안의 남긴 상자(앞면+뒷면). v1114_dr_prep.py", "shares": shares},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {"_note": "초안 수(정확도 아님). v1114_dr_prep.py", "totals": dict(tot),
              "by_split": {s: {k: by_split[(s, k)] for k in ("images", "face", "back")} for s in ("train", "dev")},
              "rule_roles": dict(roles_rule), "rule_seats": dict(seats_rule), "rule_role_seat": dict(rs_rule), "model_roles": dict(roles_model),
              "label_check": {"images_with_label": label_imgs, "images_with_issue": label_issue_imgs},
              "flags_guess": dict(flags)}
    (DR / "counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False, indent=1))
    for n in NAMES:
        print(n, shares[n]["rounds"], shares[n]["images"], shares[n]["boxes"])


if __name__ == "__main__":
    main()
