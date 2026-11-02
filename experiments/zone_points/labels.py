"""검토 뒤 8점 라벨을 만든다(2026-11-02, API 없음). propose.py → segments.py 다음에. 고친 근거는 label_review.md.
구간 값(중앙값)을 그 구간의 사진·프레임에 옮기고, 눈으로 본 결과(뺄 구간·같은 설치 합치기·기기 값·안 보이는 점)를 넣는다. 프레임은 구간별로 시각 고르게 뽑는다.
나눔은 시각이 아니라 설치 기준이다(s11 은 13:49~14:20 이라 시각으로 나누면 한 설치가 오전·오후에 섞인다).
  python -I experiments/zone_points/labels.py
결과 tile_classifier/data/zone_points/labels.json: 이름 → group(am·pm·gal)·setup·kind·src·seg·felt·device·vis[8]. vis 0 = 사진 밖·안 보임, 2 = 학습에 씀.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "tile_classifier" / "data" / "zone_points"
# 눈 확인에서 값이 틀린 구간. 움직이는 중이거나 사진 밖 변을 직선으로 잘못 이은 짧은 구간이다.
DROP_SEGS = {2: "탁자 절반이 사진 밖, 기기 없음", 6: "위 변이 사진 밖인데 위 두 점이 펠트 안", 7: "위 변이 사진 밖인데 위 두 점이 펠트 안"}
# 같은 설치인데 펠트 판독이 틀려 구간이 쪼개진 곳: 정합으로 카메라가 같음을 확인(label_review.md 1절).
SAME_AS = {9: 8, 12: 13}
SETUP = {0: "s0", 1: "s1", 3: "s3", 4: "s4", 5: "s5", 8: "s8", 10: "s8", 11: "s13", 13: "s13", 14: "s14"}
PM_FROM_SEG = 11  # 구간 번호 11 부터 오후 묶음
EXTRA_PHOTOS = {"20261031_171245": 14}  # 팔이 오른쪽 변을 가려 구간에서 빠짐, 구간 14 값이 눈으로 맞음
HIDDEN = {"k20": [2, 3], "k24": [2, 3]}  # 아래 변이 사진 밖이라 아래 두 점을 믿을 수 없다
# 반사광이 남색 마스크에서 빠져 변이 안쪽으로 들어온 구간. 펠트 평면의 기기 기준값을 사진 좌표로 옮겨 원본에서 대조한 값.
DEVICE_FIX = {
    3: [[0.4581, 0.3697], [0.5880, 0.3850], [0.5785, 0.5561], [0.4464, 0.5408]],
    11: [[0.4001, 0.4171], [0.5354, 0.4078], [0.5439, 0.5854], [0.4069, 0.5965]],
    13: [[0.4001, 0.4171], [0.5354, 0.4078], [0.5439, 0.5854], [0.4069, 0.5965]],
    14: [[0.4346, 0.4383], [0.5708, 0.4364], [0.5707, 0.6119], [0.4377, 0.6127]],
}


def moved(name: str, rows: dict, sid: int) -> bool:
    """구간 값과 어긋나거나 다른 묶음과 같은 판인 프레임."""
    if sid == 0 and name[:8] == "f122417_" and int(name[8:]) <= 8:
        return True  # 12:25:49 전에 카메라가 움직임
    if sid == 4 and name[:8] == "f125948_" and int(name[8:]) >= 135:
        return True  # 13:09:22 뒤 카메라 안정 근거 없음
    if sid == 11 and rows[name].get("at", "99") < "14:00":
        return True  # 13:49 프레임은 am 사진 134815 와 같은 판
    return False


def sample(names: list[str]) -> list[str]:
    """구간 프레임을 시각 순서로 고르게: 1/4, 최소 10, 최대 40."""
    n = len(names)
    k = min(n, min(40, max(10, n // 4)))
    return [names[round(i * (n - 1) / max(k - 1, 1))] for i in range(k)]


def vis_of(pts: list) -> list[int]:
    return [0 if not (0 <= x <= 1 and 0 <= y <= 1) else 2 for x, y in pts]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = json.loads((DATA / "proposals.json").read_text(encoding="utf-8"))
    sg = json.loads((DATA / "segments.json").read_text(encoding="utf-8"))
    segs = {s["id"]: s for s in sg["segs"]}
    items = {n: SAME_AS.get(v, v) for n, v in sg["items"].items()}
    items.update(EXTRA_PHOTOS)
    extra_path = DATA / "review_lists.json"
    extra = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else {"rescue": {}, "low_tile": {}}
    for n, sid in extra["rescue"].items():
        items[n] = SAME_AS.get(int(sid), int(sid))
    must = set(extra["rescue"]) | set(extra["low_tile"])  # 드문 장면·가림 장면은 뽑기와 상관없이 넣는다

    def entry(n: str, sid: int) -> dict:
        s = segs[sid]
        device = DEVICE_FIX.get(sid, s["device"])
        return {"group": "pm" if sid >= PM_FROM_SEG else "am", "setup": SETUP[sid], "kind": rows[n]["kind"], "src": rows[n]["src"], "seg": sid, "size": rows[n]["size"], "at": rows[n].get("at", n[9:15]),
                "felt": s["felt"], "device": device, "vis": vis_of(s["felt"] + device)}

    out, cut = {}, []
    for sid in segs:
        if sid in DROP_SEGS or sid in SAME_AS:
            continue
        names = [n for n, v in items.items() if v == sid]
        cut += [n for n in names if moved(n, rows, sid)]
        names = [n for n in names if not moved(n, rows, sid)]
        frames = sorted((n for n in names if rows[n]["kind"] == "frame"), key=lambda n: rows[n]["at"])
        chosen = {n for n in names if rows[n]["kind"] == "photo"} | set(sample(frames)) | {n for n in names if n in must}
        for n in sorted(chosen):
            out[n] = entry(n, sid)
    for n, r in rows.items():
        if r["part"] != "gal":
            continue
        vis = vis_of(r["felt"] + r["device"])
        for k in HIDDEN.get(n, []):
            vis[k] = 0
        out[n] = {"group": "gal", "setup": "gal", "kind": "photo", "src": r["src"], "seg": n, "size": r["size"], "at": "", "felt": r["felt"], "device": r["device"], "vis": vis}
    (DATA / "labels.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print("움직임·같은 판으로 뺀 프레임", len(cut), "| 살린 프레임", len(extra["rescue"]), "패 적은 프레임", len(extra["low_tile"]))
    for g in ("am", "pm", "gal"):
        rs = [r for r in out.values() if r["group"] == g]
        print(g, "장", len(rs), "사진", sum(r["kind"] == "photo" for r in rs), "프레임", sum(r["kind"] == "frame" for r in rs), "설치", sorted({r["setup"] for r in rs}))
    print("합계", len(out), "안 보이는 점 있는 장", sum(min(r["vis"]) == 0 for r in out.values()))


if __name__ == "__main__":
    main()
