"""YOLO 먼저 + 검사 통과만 반영, 나머지는 Gemini — 하이브리드가 몇 장을 자동으로 처리하는지 잰다(2026-10-26).

1) 검출 좌표 저장: run_yolo.py 의 모델로 자리 크롭(seat)·전경(table) 10장씩 돌려 (패, 확신도, 중심)을 results/dets_*.json 에.
2) 후처리: 가까운 검출끼리 이어 덩어리를 만들고(패 간격 = 최근접 거리 중앙값),
   가장 큰 덩어리 = 손패, 나머지 덩어리 중 퐁·치·깡 모양(엎은 패 2장 + 같은 패 2장 = 안깡)만 울기, 그 밖은 버림.
3) 검사(앱의 장수·화료 검사와 같은 뜻): 같은 패 5장 이상이면 실패, 손패 + 울기×3 이 13장이면 텐파이(대기패 1개 이상),
   14장이면 화료 형태여야 통과. 통과하면 자동 반영, 아니면 Gemini 자리 판독(95%, 중앙 6.4초)으로 넘긴다.
4) 정답(손패 + 울기, 안깡 4장)과 다중집합으로 비교: 자동 반영 중 정답/틀린 채 반영, Gemini 로 넘긴 수.

python -I hybrid.py [--rerun]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_yolo as ry  # noqa: E402

OUT = ry.HERE / "results"
GEMINI_ACC, GEMINI_SEC = 0.95, 6.4  # 확대 토막 + 참고표 자리 판독 57/60, 중앙 6.4초(problem_log 16)

# ---------------------------------------------------------------- 패 모양 검사
SUITS = "mpsz"


def norm(t: str) -> str:
    return "5" + t[1] if t[0] == "0" else t


def counts34(tiles: list[str]) -> list[int]:
    c = [0] * 34
    for t in tiles:
        t = norm(t)
        c[SUITS.index(t[1]) * 9 + int(t[0]) - 1] += 1
    return c


def _sets(c: list[int], i: int = 0) -> bool:
    """c 를 몸통 없이 전부 슌쯔·커쯔로 나눌 수 있나."""
    while i < 34 and c[i] == 0:
        i += 1
    if i == 34:
        return True
    if c[i] >= 3:
        c[i] -= 3
        ok = _sets(c, i)
        c[i] += 3
        if ok:
            return True
    if i < 27 and i % 9 <= 6 and c[i + 1] and c[i + 2]:
        c[i] -= 1; c[i + 1] -= 1; c[i + 2] -= 1
        ok = _sets(c, i)
        c[i] += 1; c[i + 1] += 1; c[i + 2] += 1
        if ok:
            return True
    return False


def is_win(c: list[int], n_melds: int) -> bool:
    if sum(c) + 3 * n_melds != 14:
        return False
    for i in range(34):
        if c[i] >= 2:
            c[i] -= 2
            ok = _sets(c)
            c[i] += 2
            if ok:
                return True
    if n_melds == 0:
        if sum(1 for x in c if x == 2) == 7:
            return True
        yao = [0, 8, 9, 17, 18, 26] + list(range(27, 34))
        if all(c[i] >= 1 for i in yao) and sum(c[i] for i in yao) == 14:
            return True
    return False


def waits(c: list[int], n_melds: int) -> list[int]:
    out = []
    for i in range(34):
        if c[i] >= 4:
            continue
        c[i] += 1
        if is_win(c, n_melds):
            out.append(i)
        c[i] -= 1
    return out


def check(hand: list[str], melds: list[list[str]]) -> tuple[bool, str]:
    all_tiles = hand + [t for m in melds for t in m]
    if max(counts34(all_tiles), default=0) > 4:
        return False, "같은 패 5장 이상"
    c = counts34(hand)
    n = len(hand) + 3 * len(melds)
    if n == 13:
        return (True, "텐파이") if waits(c, len(melds)) else (False, "13장인데 대기패 없음")
    if n == 14:
        return (True, "화료형") if is_win(c, len(melds)) else (False, "14장인데 화료형 아님")
    return False, f"{n}장"


# ---------------------------------------------------------------- 후처리
def meld_of(group: list[str]) -> list[str] | None:
    """덩어리가 울기 모양이면 울기 패 목록(안깡은 4장), 아니면 None."""
    face = [t for t in group if t != "back"]
    backs = len(group) - len(face)
    if backs == 2 and len(face) == 2 and norm(face[0]) == norm(face[1]):
        return face + face  # 안깡: 가운데 두 장만 보임
    if backs:
        return None
    if len(face) in (3, 4) and len({norm(t) for t in face}) == 1:
        return face  # 퐁·깡
    if len(face) == 3 and all(t[1] != "z" for t in face) and len({t[1] for t in face}) == 1:
        ns = sorted(int(norm(t)[0]) for t in face)
        if ns[1] == ns[0] + 1 and ns[2] == ns[1] + 1:
            return face  # 치
    return None


def split(dets: list[dict], line_merge: bool = False) -> tuple[list[str], list[list[str]], int]:
    """손패, 울기들, 버린 패 수.
    line_merge: 울기 모양이 아닌 덩어리라도 손패 줄의 연장선 위(줄에서 패 간격 절반 이내)에 있으면 손패에 붙인다
    (손패를 두 무더기로 떨어뜨려 눕힌 경우 — 매장 사진 아래 자리 6s 1s 3s)."""
    if not dets:
        return [], [], 0
    pts = np.array([[d["x"], d["y"]] for d in dets])
    if len(pts) == 1:
        return [dets[0]["t"]], [], 0
    dist = np.linalg.norm(pts[:, None] - pts[None], axis=2)
    np.fill_diagonal(dist, np.inf)
    pitch = np.median(dist.min(1))
    link = dist < pitch * 1.6
    comp, groups = [-1] * len(dets), []
    for s in range(len(dets)):
        if comp[s] >= 0:
            continue
        stack, g = [s], []
        comp[s] = len(groups)
        while stack:
            i = stack.pop()
            g.append(i)
            for j in np.nonzero(link[i])[0]:
                if comp[j] < 0:
                    comp[j] = len(groups)
                    stack.append(j)
        groups.append(g)
    groups.sort(key=len, reverse=True)
    main = groups[0]
    # 손패 줄 순서: 덩어리의 주축(PCA) 방향
    p = pts[main] - pts[main].mean(0)
    axis = np.linalg.svd(p, full_matrices=False)[2][0]
    main = [main[k] for k in np.argsort(p @ axis)]
    melds, dropped, extra = [], 0, []
    mean = pts[main].mean(0)
    for g in groups[1:]:
        m = meld_of([dets[i]["t"] for i in g])
        if m:
            melds.append(m)
        elif line_merge and all(abs((pts[i] - mean) @ np.array([-axis[1], axis[0]])) < pitch * 0.5 for i in g):
            extra += g
        else:
            dropped += len(g)
    if extra:
        main = sorted(main + extra, key=lambda i: (pts[i] - mean) @ axis)
    hand = [dets[i]["t"] for i in main if dets[i]["t"] != "back"]
    return hand, melds, dropped


# ---------------------------------------------------------------- 검출 저장
def collect(rerun: bool) -> dict:
    path = OUT / "dets_hybrid.json"
    if path.exists() and not rerun:
        return json.loads(path.read_text(encoding="utf-8"))
    res: dict[str, dict[str, list]] = {}
    models = {"haselab": ry.HaseLab(), "nikmomo-s": ry.Nikmomo("s"), "nikmomo-m": ry.Nikmomo("m")}
    for name, m in models.items():
        for key, img_path, _ in list(ry.seat_items()) + list(ry.table_items()):
            img = ry.imread(img_path)
            if key.startswith("table/"):
                if name != "haselab":
                    continue
                dets, _, _ = m.predict_table(img, ry.WINNER_SIDE[key.split("/")[1]])
            else:
                if name == "haselab":
                    continue  # 자리 크롭을 패 모델에 바로 넣으면 거의 못 찾음(README)
                dets, _ = m.predict(img)
            dets = ry.dedupe(dets)
            res.setdefault(name, {})[key] = [dict(t=d[0], c=round(float(d[1]), 3), x=float(d[2][0]), y=float(d[2][1])) for d in dets]
            print(name, key, len(dets), flush=True)
    path.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", action="store_true")
    a = ap.parse_args()
    det = collect(a.rerun)
    truth = {f"{s}/{p}": t.split() for s, (_, t) in ry.SEAT_TRUTH.items() if s in ry.EVAL_SCENES for p in ry.SEAT_PHOTOS[s]}

    combos = [("nikmomo-s", "seat"), ("nikmomo-m", "seat"), ("haselab", "table")]
    lines = []
    per = {}
    for model, kind in combos:
        rows = []
        for sp, want in truth.items():
            dets = det[model][f"{kind}/{sp}"]
            hand, melds, dropped = split(dets)
            ok, why = check(hand, melds)
            got = hand + [t for m in melds for t in m]
            right = Counter(got) == Counter(want)
            rows.append(dict(sp=sp, ok=ok, why=why, right=right, hand=hand, melds=melds, dropped=dropped,
                             naive=Counter(t for t in (d["t"] for d in dets) if t != "back") == Counter(want)))
        per[model] = rows
        lines.append(f"\n## {model} ({kind})")
        for r in rows:
            tag = ("자동 반영 · 정답" if r["right"] else "자동 반영 · **틀림**") if r["ok"] else f"Gemini 로 ({r['why']})"
            lines.append(f"- {r['sp']}: {tag} | 손패 {' '.join(r['hand'])}"
                         f"{' | 울기 ' + ' / '.join(' '.join(m) for m in r['melds']) if r['melds'] else ''}"
                         f"{' | 버림 %d장' % r['dropped'] if r['dropped'] else ''}"
                         f"{' (후처리 전엔 오답)' if r['right'] and not r['naive'] else ''}")

    def summary(rows, scenes):
        rs = [r for r in rows if r["sp"][0] in scenes]
        auto = [r for r in rs if r["ok"]]
        good = sum(r["right"] for r in auto)
        bad = len(auto) - good
        fb = len(rs) - len(auto)
        exp_right = good + fb * GEMINI_ACC
        exp_sec = (len(auto) * 0.5 + fb * (0.5 + GEMINI_SEC)) / len(rs)
        post = sum(r["right"] for r in rs)
        return (f"{len(rs)}장 중 자동 반영 {len(auto)}(정답 {good}, 틀림 {bad}), Gemini 로 {fb} | 후처리 뒤 손패 정답 {post}/{len(rs)}"
                f" | 기대 정답 {exp_right:.1f}/{len(rs)}({100*exp_right/len(rs):.0f}%), 기대 시간 평균 {exp_sec:.1f}초, Gemini 호출 {100*fb/len(rs):.0f}%")

    head = ["# 하이브리드 측정 결과", "", "| 모델 | 세트 | 결과 |", "| --- | --- | --- |"]
    for model, kind in combos:
        for scenes, label in ((ry.EVAL_SCENES, "B·C·D 6장"),):
            head.append(f"| {model} ({kind}) | {label} | {summary(per[model], scenes)} |")

    # 두 모델이 둘 다 통과하고 같은 답이면 반영
    a_rows, b_rows = per["nikmomo-s"], per["haselab"]
    agree = []
    for ra, rb in zip(a_rows, b_rows):
        same = ra["ok"] and rb["ok"] and Counter(ra["hand"] + sum(ra["melds"], [])) == Counter(rb["hand"] + sum(rb["melds"], []))
        agree.append(dict(sp=ra["sp"], ok=same, right=same and ra["right"], hand=ra["hand"], melds=ra["melds"]))
    for scenes, label in ((ry.EVAL_SCENES, "B·C·D 6장"),):
        head.append(f"| nikmomo-s + haselab 일치 | {label} | {summary(agree, scenes)} |")
    text = "\n".join(head + lines) + "\n"
    (OUT / "hybrid.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
