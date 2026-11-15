"""11-14 자료 나눔 고치기(2026-11-15, 3단계 A). v1114_draft.py 다음, v1114_crops.py 앞에. 처음부터 다시 돌려도 같은 결과.

규칙(사용자가 정함 — "같은 탁자 장면은 한쪽에만"):
  1. 판 단위: MOVE_TO_DEV 의 판은 개발로(r05_121325 = r04 화료 탁자가 안 치워진 채 그대로 찍힌 판, 사진으로 확인). → 판의 split_final.
  2. 그림 단위 scene_round: draft 그림에 prev_round_scene 이 있으면 그 그림은 앞 판(prev_round_scene.round)의 탁자 → 그 판, 없으면 자기 판.
     그림(과 그 그림에서 나온 크롭)의 split_final = scene_round 판의 split_final(1번 적용 뒤).
     (prev_round_scene 이 가리키는 앞 판 그림이 또 그 앞 판 탁자인 사슬은 따라가지 않는다 — 글자 그대로. 사슬 끝은 scene_root 에 따로 적음.)
  3. 그림 폴더: images/q*/<split_final>/<판>/ — 단 scene_round 의 split 이 자기 판 split_final 과 다르면 images/q*/<앞 판 split>/<앞 판 id>/ 로.
     native/(라벨 없는 실제 저화질 프레임)는 판의 split_final 폴더로.
  4. SCENES: 한 판 안에 두 탁자가 있는 판(r20_143236: 앞 판 보라 패 = f0042 앞의 그림 전부, 새 판 분홍 패 = f0042 이후, 2단계 보고).
     나눔은 그대로, 크롭 목록의 scene 칸으로만 가른다.
manifest.json: items 에 split_final·scene_round·scene_root·folder, rounds 에 split_final 을 더한다(기존 칸 그대로).
draft/<판>.json: images[].path 를 옮긴 자리로 고치고 옮긴 것은 path_was 에 옛 경로.
  python -X utf8 experiments/tile_classifier/v1114_split.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "v1114"
QS = ("q2992", "q1496", "q997")
MOVE_TO_DEV = {"r05_121325": "r04(개발) 화료 탁자가 안 치워진 채 그대로 찍힌 판(사용자가 사진으로 확인, 11-15)"}
# 판 → (둘째 장면이 시작하는 그림 이름 앞부분, 첫 장면 이름, 둘째 장면 이름)
SCENES = {"r20_143236": ("143236_f0042", "a_purple_prev", "b_pink_new")}


def image_folder(it: dict) -> str:
    """images/q*/ 아래 폴더(<split>/<판>). split.py 를 돌리기 전 manifest 면 옛 자리."""
    return it.get("folder") or f"{it['split']}/{it['round']}"


def image_rel(it: dict, q: str) -> str:
    """data/v1114 기준 그림 경로."""
    return f"images/{q}/{image_folder(it)}/{it['name']}"


def native_rel(it: dict) -> str:
    return f"native/{it['native']}/{it.get('split_final') or it['split']}/{it['round']}/{it['name']}"


def scene_of(round_id: str, name: str, at: str, round_items: list[dict]) -> str | None:
    """SCENES 판이면 그림이 첫 장면인가 둘째 장면인가(둘째 장면 첫 그림 시각 기준)."""
    if round_id not in SCENES:
        return None
    pre, a, b = SCENES[round_id]
    t0 = min(it["at"] for it in round_items if it["name"].startswith(pre))
    return f"{round_id}/{b if at >= t0 else a}"


def plan(man: dict) -> tuple[dict, dict]:
    """판 split_final, 그림 id → {scene_round, scene_root, split_final, folder}."""
    rsplit = {r["id"]: ("dev" if r["id"] in MOVE_TO_DEV else r["split"]) for r in man["rounds"]}
    drafts = {}
    for r in man["rounds"]:
        p = OUT / "draft" / f"{r['id']}.json"
        if p.exists():
            drafts[r["id"]] = json.loads(p.read_text(encoding="utf-8"))
    prs = {im["id"]: im.get("prev_round_scene") for d in drafts.values() for im in d["images"]}
    per = {}
    for it in man["items"]:
        if not it["selected"]:
            continue
        pr = prs.get(it["id"])
        sr = pr["round"] if pr else it["round"]
        root, img = sr, pr["image"] if pr else None
        while img and prs.get(img):  # 사슬 끝(참고용)
            root, img = prs[img]["round"], prs[img]["image"]
        sp = rsplit[sr]
        folder = f"{sp}/{sr}" if sp != rsplit[it["round"]] else f"{rsplit[it['round']]}/{it['round']}"
        per[it["id"]] = {"scene_round": sr, "scene_root": root, "split_final": sp, "folder": folder}
    return rsplit, per


def move(src: Path, dst: Path) -> bool:
    if src == dst:
        return False
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()  # 다시 돌린 v1114_quality.py 가 옛 자리에 또 쓴 경우: 같은 내용
    shutil.move(str(src), str(dst))
    try:
        src.parent.rmdir()  # 빈 폴더 정리
    except OSError:
        pass
    return True


def main():
    mp = OUT / "manifest.json"
    man = json.loads(mp.read_text(encoding="utf-8"))
    rsplit, per = plan(man)
    moved, native_moved = [], []
    by_round = {}
    for it in man["items"]:
        by_round.setdefault(it["round"], []).append(it)
    for it in man["items"]:
        old_folder = image_folder(it)
        if it["selected"]:
            it.update(per[it["id"]])
            sc = scene_of(it["round"], it["name"], it["at"], by_round[it["round"]])
            it["scene"] = sc or it["scene_round"]
            for q in QS:
                # 옛 자리 후보: 처음 자리(<split>/<round>)와 지난번 folder
                dst = OUT / "images" / q / it["folder"] / it["name"]
                for f in {old_folder, f"{it['split']}/{it['round']}"}:
                    if move(OUT / "images" / q / f / it["name"], dst) and q == "q2992":
                        moved.append({"image": it["id"], "from": f"images/*/{f}", "to": f"images/*/{it['folder']}",
                                      "scene_round": it["scene_round"], "split_final": it["split_final"]})
                assert dst.exists(), dst
        else:
            it["split_final"] = rsplit[it["round"]]
            it["scene_round"] = None  # 고르지 않은 그림은 장면을 안 봤다
            if it.get("native"):
                dst = OUT / native_rel(it)
                if move(OUT / f"native/{it['native']}/{it['split']}/{it['round']}/{it['name']}", dst):
                    native_moved.append(it["id"])
    for r in man["rounds"]:
        r["split_final"] = rsplit[r["id"]]
        if r["id"] in MOVE_TO_DEV:
            r["split_final_why"] = MOVE_TO_DEV[r["id"]]
    man["rules"]["split_final"] = {
        "move_to_dev": MOVE_TO_DEV, "scenes": {k: list(v) for k, v in SCENES.items()},
        "rule": "그림 scene_round = draft prev_round_scene.round(없으면 자기 판), 그림 split_final = scene_round 판의 split_final. "
                "폴더 images/q*/<split_final>/<판> — scene_round 판 split 이 자기 판과 다르면 <앞 판 split>/<앞 판 id>. v1114_split.py"}
    mp.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    # draft 경로
    items = {it["id"]: it for it in man["items"]}
    fixed = 0
    for p in sorted((OUT / "draft").glob("r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        ch = False
        for im in d["images"]:
            new = image_rel(items[im["id"]], "q2992")
            if im["path"] != new:
                im.setdefault("path_was", im["path"])
                im["path"] = new
                ch = True
                fixed += 1
        if ch:
            p.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")
    # 확인
    for it in man["items"]:
        if it["selected"]:
            for q in QS:
                assert (OUT / image_rel(it, q)).exists(), (q, it["id"])
        elif it.get("native"):
            assert (OUT / native_rel(it)).exists(), it["id"]
    cross = [{"image": it["id"], "round": it["round"], "round_split": rsplit[it["round"]], "scene_round": it["scene_round"], "split_final": it["split_final"]}
             for it in man["items"] if it["selected"] and it["split_final"] != rsplit[it["round"]]]
    print(json.dumps({"round_split_final": {s: [r for r, v in rsplit.items() if v == s] for s in ("train", "dev")},
                      "moved_this_run": moved, "native_moved_this_run": native_moved, "draft_paths_fixed_this_run": fixed,
                      "images_split_differs_from_round": cross,
                      "chains": [{"image": i, "scene_round": v["scene_round"], "scene_root": v["scene_root"]} for i, v in per.items() if v["scene_root"] != v["scene_round"]]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
