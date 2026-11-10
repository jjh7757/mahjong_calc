"""임시 라벨 눈 검토 결과와 2차 학습(2026-11-01, 노트북 CPU, API 없음). harvest.py·harvest_blank.py 다음에.

검토(Claude 가 sheet_* 를 눈으로 봄, 사용자 확인 전): 10-29 이후 upright 사진(id 1447 이상)만 쓴다.
10-24 은 탁자가 약 40° 기울어 임시 라벨을 믿기 어려워 뺐다.
평가는 표 1-18 과 같은 라벨 259장, 세트 분리 3 시드. 시험 세트와 같은 시간대의 사진에서 나온 패는 학습에서 뺀다.
  python -I experiments/tile_classifier/review.py [--count]
결과 data/round2.json, data/model_round2.pt
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import train as tr  # noqa: E402

DATA = HERE / "data"
HV = DATA / "harvest"

FIRST_ID = 1447
FIX = {2613: "4z", 2611: "4z", 2882: "7z", 1769: "3m", 2421: "3m", 1676: "4z", 2291: "4z", 1783: "4z", 2151: "4z", 2134: "4z", 2687: "4z", 1841: "4z",
       1991: "6z", 1817: "6z", 2209: "6z", 2114: "5s", 2591: "9p",  # 2114·2591 은 2차 평가의 틀린 패를 크게 보고 고침(model_round2 는 고치기 전 라벨)
       # 2026-11-07 전수조사(학습 크롭 1,550장, Opus 하위 에이전트 5개, data/label_audit/full_*_review.json): 180° 뒤집힌 三萬·一萬 이
       # 예전 분류기 예측 그대로 2m 으로 붙어 있었음(운영 cls4 의 '뒤집힌 만수 = 2m' 버릇, metrics 표 6 11-07 저녁 줄·표 1-116)
       1959: "3m", 2156: "1m", 2290: "3m", 2424: "3m"}
DROP = {2625, 2681, 2722,
        2778, 2777}  # 2778: 반 넘게 잘린 적5통(63×100, 동그라미 두 개 반) — 2026-11-07 전수조사 unsure, 사용자 결정으로 학습에서 뺌.
                     # 2777: 같은 적5통을 옆에서 자른 조각(80×95, 왼쪽 두 개 반쯤 잘림) — 크기·비율 걸러보기(data/label_audit/cut_suspects.json) 뒤 사용자 결정
UNSURE_OK = {
    "4z": [2383, 2410, 2256, 2015, 2392, 2279, 2485, 2314, 2065, 1948, 2463, 1875, 1943, 2192, 2198, 1482, 2280, 1765, 1692, 2183, 1650, 1797, 1621, 2123, 2796, 2565, 2386,
           2862, 1937, 2194, 2233, 1713, 2801, 2702, 1507, 1480, 1612, 2430, 2487, 2344, 2755],
    "6z": [2102, 2139, 2676, 2637, 2622, 2835, 1984, 2419, 1854, 2885, 1871, 2505, 2514, 1762, 2552, 2143, 2307, 2467, 1822, 2532, 2815, 1772, 2861, 1735, 2579, 2215, 2384,
           2181, 2315, 2310, 2693, 2287, 2879, 2184, 2446, 2224, 2268, 1820, 2098, 1955, 2461, 2477, 2871, 2516, 1890, 2794, 1963],
    "7z": [2635, 2748, 1677, 2507, 1617, 2615, 2597, 2603, 2651, 2438, 2875, 1682, 2345, 2717, 1594, 1476, 1808, 2621, 2223, 2401, 2267, 2158, 2459, 2529, 2705],
    "1z": [1811, 1933, 2092, 2311, 2338, 2431, 2360, 2713, 2513, 2533],
    "1m": [2119, 1953], "2m": [1959, 2156], "3s": [2205, 1462], "5s": [1689, 1731, 1659, 2204], "7s": [2110, 1961, 2411, 2466, 2266], "9m": [1803, 2131],
    "4m": [1878, 1899], "8s": [2779, 1723], "4s": [2385], "5p": [2696], "2z": [2633],
}
BLANK_OK = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 15, 16, 30, 32, 33, 39, 46, 59, 65, 68, 147, 160, 167, 190, 194, 206, 207, 210, 211, 212, 216, 222, 223, 224, 229, 231]


def half(photo: str) -> str:
    if not photo.startswith("20261031_") or photo < "20261031_12":
        return "other"
    return "am" if photo < "20261031_14" else "pm"


def extra() -> list[dict]:
    rows = json.loads((HV / "index.json").read_text(encoding="utf-8"))
    ok = {i: t for t, ids in UNSURE_OK.items() for i in ids}
    out = []
    for r in rows:
        if r["id"] < FIRST_ID or r["dup"] or r["id"] in DROP:
            continue
        if r["conf"] < 0.6 and r["id"] not in ok:
            continue
        tile = FIX.get(r["id"]) or ok.get(r["id"]) or r["pred"]
        out.append(dict(file="h_" + r["file"], path=HV / "crops" / r["file"], tile=tile, photo=r["photo"], half=half(r["photo"])))
    for r in json.loads((HV / "blank/index.json").read_text(encoding="utf-8")):
        if int(r["id"][1:]) in BLANK_OK:
            out.append(dict(file="b_" + r["file"], path=HV / "blank" / r["file"], tile="5z", photo=r["photo"], half=half(r["photo"])))
    return out


def leak_check(add: list[dict]) -> None:
    """학습 추가분 사진이 시험 사진(B·C·D, 같은 사진을 앱으로 다시 읽은 것)과 같은지. 작게 줄인 흑백 그림 차이로 본다."""
    root = HERE.parents[0]
    def thumb(p: Path) -> np.ndarray:
        return np.asarray(Image.open(p).convert("L").resize((64, 48)), np.float32)
    kakao = {p.stem: thumb(p) for p in (root / "field_20261024/kakao_photos").glob("*.jpg")}
    for photo in sorted({x["photo"] for x in add}):
        src = root / "visit_20261031/captures" / photo
        t = thumb(src / "original.jpg")
        best = min(kakao, key=lambda k: np.abs(kakao[k] - t).mean())
        meta = json.loads((src / "meta.json").read_text(encoding="utf-8")) if (src / "meta.json").exists() else {}
        d = float(np.abs(kakao[best] - t).mean())
        if half(photo) == "other" or d < 12:
            print(photo, half(photo), f"가장 닮은 {best} 차이 {d:.1f}", {k: meta.get(k) for k in ("source", "zoom", "mount_height") if k in meta}, flush=True)


def hard(base: list[dict], add: list[dict], images: dict) -> None:
    """같은 시간대의 검토 라벨 전부(낮은 확신·4z·5z 포함)를 빼고 학습해 그것으로 평가. 라벨 259장보다 어려운 패가 들어 있다."""
    out = []
    for part in ("am", "pm"):
        te = [x for x in add if x["half"] == part]
        pool = [x for x in base if x["part"] != part] + [x for x in add if x["half"] != part]
        net = tr.train(pool, images, 0)
        for k in range(0, len(te), 64):
            b = te[k:k + 64]
            with torch.no_grad():
                p = torch.softmax(net(torch.stack([tr.PLAIN(images[x["file"]]) for x in b])), 1)
            for x, q in zip(b, p):
                out.append(dict(file=x["file"], photo=x["photo"], part=part, tile=x["tile"], pred=tr.CLASSES[q.argmax().item()], conf=round(float(q.max()), 3)))
        v = [r for r in out if r["part"] == part]
        print(f"{part}: 학습 {len(pool)}장, 평가 {sum(r['tile'] == r['pred'] for r in v)}/{len(v)}", flush=True)
    (DATA / "round2_hard.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    wrong = [r for r in out if r["tile"] != r["pred"]]
    print("틀린 패", Counter((r["tile"], r["pred"]) for r in wrong).most_common(25))
    c, w = Counter(r["tile"] for r in out), Counter(r["tile"] for r in wrong)
    print("종류별 틀림", {k: f"{w[k]}/{c[k]}" for k in sorted(c) if w[k]})
    cell, cols = 76, 16
    wrong.sort(key=lambda r: -r["conf"])
    s = Image.new("RGB", (cols * cell, (len(wrong) // cols + 1) * (cell + 14)), "white")
    d = ImageDraw.Draw(s)
    src = {x["file"]: x["path"] for x in add}
    for i, r in enumerate(wrong):
        t = Image.open(src[r["file"]])
        t.thumbnail((cell, cell))
        x, y = (i % cols) * cell, (i // cols) * (cell + 14)
        s.paste(t, (x, y))
        d.text((x + 1, y + cell), f"{r['file'][2:-4]} {r['tile']}>{r['pred']}", fill="red")
    s.save(DATA / "round2_hard_wrong.jpg", quality=88)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    torch.set_num_threads(12)
    base = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    add = extra()
    if "--leak" in sys.argv:
        leak_check(add)
        return
    if "--bcd" in sys.argv:  # 10-29·10-31 새벽 기록은 갤러리 B·C·D 를 앱으로 다시 읽은 것(leak_check)이라 빼고 다시 잰다
        clean = [x for x in add if x["half"] != "other"]
        images = {x["file"]: tr.square(Image.open(DATA / "crops" / x["file"]).convert("RGB")) for x in base}
        images.update({x["file"]: tr.square(Image.open(x["path"]).convert("RGB")) for x in clean})
        te = [x for x in base if x["part"] == "bcd"]
        pool = [x for x in base if x["part"] != "bcd"] + clean
        rows = []
        for seed in (0, 1, 2):
            s = tr.score(te, tr.predict(tr.train(pool, images, seed), te, images), {x["tile"] for x in pool})
            s.update(part="bcd", seed=seed, train=len(pool))
            rows.append(s)
            tr.report(f"bcd(겹침 뺌) 시드 {seed} 학습 {len(pool)}장", s)
            print("틀림", s["wrong"], flush=True)
        (DATA / "round2_bcd.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        final = tr.train(base + clean, images, 0)
        torch.save(final.state_dict(), DATA / "model_round2.pt")
        return
    if "--hard" in sys.argv:
        images = {x["file"]: tr.square(Image.open(DATA / "crops" / x["file"]).convert("RGB")) for x in base}
        images.update({x["file"]: tr.square(Image.open(x["path"]).convert("RGB")) for x in add})
        hard(base, add, images)
        return
    c = Counter(x["tile"] for x in add)
    print("추가", len(add), "시간대", Counter(x["half"] for x in add), "합계 종류별", dict(sorted((c + Counter(x["tile"] for x in base)).items())), "없는 종류", [k for k in tr.CLASSES if not (c + Counter(x["tile"] for x in base))[k]], flush=True)
    if "--count" in sys.argv:
        return
    images = {x["file"]: tr.square(Image.open(DATA / "crops" / x["file"]).convert("RGB")) for x in base}
    images.update({x["file"]: tr.square(Image.open(x["path"]).convert("RGB")) for x in add})
    res: list[dict] = []
    t0 = time.perf_counter()
    for part in ("bcd", "am", "pm"):
        te = [x for x in base if x["part"] == part]
        pool = [x for x in base if x["part"] != part] + [x for x in add if x["half"] != part]
        for seed in (0, 1, 2):
            t1 = time.perf_counter()
            net = tr.train(pool, images, seed)
            s = tr.score(te, tr.predict(net, te, images), {x["tile"] for x in pool})
            s.update(part=part, seed=seed, train=len(pool), secs=round(time.perf_counter() - t1))
            res.append(s)
            tr.report(f"{part} 시드 {seed} 학습 {len(pool)}장 ({s['secs']}초)", s)
            (DATA / "round2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("== 요약")
    n = ok = 0
    for part in ("bcd", "am", "pm"):
        v = [s for s in res if s["part"] == part]
        n += sum(s["n"] for s in v)
        ok += sum(s["ok"] for s in v)
        print(f"{part}: 패 {sum(s['ok'] for s in v)}/{sum(s['n'] for s in v)}, 시드별 {[s['ok'] for s in v]}, 사진 {sum(s['scene_ok'] for s in v)}/{sum(s['scenes'] for s in v)}, 학습에 없는 종류 {v[0]['unseen']}")
    print(f"합계 {ok}/{n} ({100 * ok / n:.1f}%)")
    print("틀린 패", Counter((w[1], w[2]) for s in res for w in s["wrong"]).most_common(20))
    final = tr.train(base + add, images, 0)
    torch.save(final.state_dict(), DATA / "model_round2.pt")
    print("총", round(time.perf_counter() - t0), "초")


if __name__ == "__main__":
    main()
