"""뒷면 색을 바꾼 합성 사진의 네 자리 크롭(faceup_recolor_test.dart 가 남김)을 지금 서버 자리 판독과 같은 조건
(bench v3a_norule = 확대 토막 3장 + 참고표, 프롬프트에 "연보라 뒷면")으로 한 번씩 읽어 face_up 이 맞는지 본다.
정답: 화료자 자리(B 오른쪽, C 왼쪽, D 아래)만 true.

  python -I experiments/backcolor/faceup_gemini.py [--colors original,blue,...] [--prompt now|neutral]
결과 experiments/backcolor/results/faceup_<prompt>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "speed"))
import bench as b  # noqa: E402

PHOTOS = {"k25": "B", "k28": "B", "k15": "C", "k26": "C", "k12": "D", "k16": "D"}
WINNER = {"B": "right", "C": "left", "D": "bottom"}
SIDES = ["bottom", "right", "top", "left"]
COLORS = ["original", "blue", "green", "yellow", "orange", "black"]


def seat_prompt(neutral: bool) -> tuple[str, dict]:
    prompt, schema = b.SEAT_PROMPT_V3A, b.SEAT_SCHEMA_V3A
    rule = prompt[prompt.index("장수: 앞면 손패라면"):]
    prompt = prompt.replace(rule[:rule.index("\n\n") + 2], "")  # 지금 서버(05eaec0 이후)는 장수 규칙 없음
    if neutral:
        prompt = neutralize(prompt)
    return prompt + b.ZOOM_NOTE.format(n=3) + b.REF_NOTE, schema


def neutralize(prompt: str) -> str:
    """색 이름 대신 "무늬 없는 단색 뒷면(세트마다 색이 다름)"."""
    return (prompt
            .replace("연보라 두께", "뒷면 색 두께")
            .replace("연보라 뒷면만 보이면", "무늬 없는 단색 뒷면(세트마다 색이 다름: 연보라·파랑·초록·노랑·주황·검정 등)만 보이면")
            .replace("뒷면(연보라)만 보이는 패", "무늬 없는 단색 뒷면만 보이는 패")
            .replace("뒷면(연보라)", "무늬 없는 단색 뒷면"))


def read(path: Path, prompt: str, schema: dict, scene: str | None = None) -> dict:
    c = {**b.BASE, **b.CONDS["v3a_norule"]}
    data = b.load(path, c["max_side"], None)
    extra = [b.image_part(z, c["zoom_res"]) for z in b.zoom_strips(path, 3, 0.4)] + [b.image_part(b.ref_sheet_set2(), None)]
    r = b.call(data, prompt, schema, c["model"], c["thinking"], c["res"], extra=extra)
    out = {"s": r.get("s"), "think": r.get("think"), "error": r.get("error"),
           "face_up": (r.get("data") or {}).get("face_up"), "n_tiles": len((r.get("data") or {}).get("tiles") or [])}
    if scene and "data" in r:  # 화료자 자리면 손패·울기 채점(bench.judge)
        j = b.judge(scene, r["data"])
        out["hand_ok"] = bool(j["hand_ok"] and j["melds_ok"])
        out["hand"] = j["hand"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colors", default=",".join(COLORS))
    ap.add_argument("--prompt", default="now", choices=["now", "neutral"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--winner-only", action="store_true", help="화료자 자리만(손패 판독 비교용)")
    a = ap.parse_args()
    prompt, schema = seat_prompt(a.prompt == "neutral")
    jobs = [(c, p, s) for c in a.colors.split(",") for p in PHOTOS for s in SIDES
            if not a.winner_only or WINNER[PHOTOS[p]] == s]

    def one(job):
        c, p, s = job
        truth = WINNER[PHOTOS[p]] == s
        r = read(HERE / "photos" / c / "seats" / f"{p}_{s}.jpg", prompt, schema, PHOTOS[p] if truth else None)
        r.update(color=c, photo=p, side=s, truth=truth, ok=r["face_up"] == truth)
        print(f"{c:8s} {p} {s:6s} face_up {r['face_up']} (정답 {truth}) {'O' if r['ok'] else 'X'} {r['s']}s", flush=True)
        return r

    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, jobs))
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    f = out / f"faceup_{a.prompt}{'_winner' if a.winner_only else ''}.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    f.write_text(json.dumps(old + rows, ensure_ascii=False, indent=1), encoding="utf-8")
    summarize(rows)


def summarize(rows):
    for c in dict.fromkeys(r["color"] for r in rows):
        rs = [r for r in rows if r["color"] == c]
        win = [r for r in rs if r["truth"]]
        oth = [r for r in rs if not r["truth"]]
        print(f"== {c:8s} 전체 {sum(r['ok'] for r in rs)}/{len(rs)}  화료자 앞면 맞음 {sum(r['ok'] for r in win)}/{len(win)}  "
              f"다른 자리 뒷면 맞음 {sum(r['ok'] for r in oth)}/{len(oth)}  오류 {sum(1 for r in rs if r['error'])}  "
              f"화료자 손패 정답 {sum(1 for r in win if r.get('hand_ok'))}/{len(win)}")


if __name__ == "__main__":
    main()
