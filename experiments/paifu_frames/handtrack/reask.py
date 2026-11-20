"""갈림 구간 다시 묻기(2026-11-20, 사용자 "컨텍스트 엔지니어링으로 문제를 해결할수 없을까" → "해봐").

첫 읽기(opusread_1118 · firstturn_1120)에서 "확신하고 틀릴 수 있는 차례" 를 정답 없이 걸러,
그 몇 초만 0.1초 간격 · 확대 그림 + 가설 둘 이상(줄 상태로 적음, 순서는 섞음) + 정렬 습관 근거를 주고 하나만 다시 묻는다.

  python -X utf8 reask.py flag     # 다섯 판에서 의심 차례 걸기(정렬 어긋남이 늘고, 이웃 맞바꿈 하나로 줄일 수 있는 차례)
  python -X utf8 reask.py prep     # 항목마다 reask_1120/<항목>/ 에 frames/ · sheets/ · TASK.md, 가설 글자 열쇠는 _key.json(항목 폴더 밖)
  python -X utf8 reask.py score    # answer.json 을 열쇠 · 확인된 답과 견줌

걸기 규칙(정답 안 씀): rebuild_opus --full 로 끝에서 거꾸로 셀 때 시작 줄의 정렬 어긋남이 끝 줄보다 늘고,
그 차례 끝 줄 순서에서 이웃 둘을 맞바꾸면 어긋남이 줄어드는 차례. 대안 가설 = 그 맞바꿈들.
1순 두 칸 후보(firstturn_1120 의 unsure)도 같은 꼴로 넣는다.
"""
from __future__ import annotations

import argparse
import hashlib
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import rebuild_opus as ro  # noqa: E402
from replay import key  # noqa: E402

ROOT = hc.WORK / "reask_1120"
BOX = [350, 400, 1300, 760]          # 대국자 시점으로 돌린 그림(1496 × 760)에서 손패 줄 둘레
GAMES = ["r12_131655", "r16_135321", "r17_140450", "r19_142013", "r13_132644"]
HOUR = {"r16": "13", "r17": "14", "r13": "13", "r19": "14", "r12": "13"}


def bad(row, sch):
    ks = [key(v, sch) for v in row]
    return sum(1 for i in range(len(row) - 1) if ks[i] is not None and ks[i + 1] is not None and ks[i] > ks[i + 1])


def flag():
    out = []
    for g in GAMES:
        recs, sch = ro.rebuild(g, "full")
        prev = None
        for x in reversed(recs):
            after_bad = bad(x["after"], sch)
            if x["src"].startswith("Opus") and x["sort_bad"] > after_bad and x.get("order"):
                o = x["order"]
                alts = []
                for k in range(len(o) - 1):
                    o2 = o[:]
                    o2[k], o2[k + 1] = o2[k + 1], o2[k]
                    try:
                        b, _ = ro.back(x["after"], o2, x["river"])
                    except ValueError:
                        continue
                    if bad(b, sch) < x["sort_bad"]:
                        alts.append(o2)
                if alts:
                    out.append({"game": g, "id": x["id"], "opus": o, "alts": alts, "bad": x["sort_bad"], "after_bad": after_bad})
                    print(f"{x['id']}: 어긋남 끝 {after_bad} → 시작 {x['sort_bad']} · 대안 {len(alts)}")
            prev = x
    return out


# 구간 · 구간 첫 프레임의 줄(첫 읽기 답의 번호, 왼쪽부터) — 첫 읽기 answer.json 의 why 에 적힌 동작 시각에서 잡음(정답 안 봄)
TURN_WIN = {
    "r16_d13": ("13:59:05.5", "13:59:11.5", ["D", "1", "13", "3", "4", "5", "6", "7", "8", "9", "10", "11", "2"]),
    "r17_d08": ("14:07:54.5", "14:08:00.0", ["1", "2", "3", "4", "D", "5", "6", "7", "8", "9", "10", "11", "13"]),
    "r13_d04": ("13:28:43.5", "13:28:49.0", [str(i) for i in range(1, 14)] + ["D"]),
    "r13_d05": ("13:29:24.0", "13:29:31.5", ["1", "2", "3", "4", "5", "6", "7", "9", "10", "11", "12", "13", "D"]),
}

FIRST = {   # 1순 두 칸 후보 — firstturn_1120 answer.json 에서 확실한 부분만 맥락으로, 갈린 부분은 가설로
    "r19_1st": dict(game="r19_142013", win=("14:20:59.0", "14:21:11.0"),
                    context=["14:20:56.3 무렵 이 사람이 뽑은 패 D 를 몸 쪽 줄 오른쪽 끝에 세움.",
                             "14:20:59.5 ~ 00.5: 줄 앞(위)에 따로 서 있던 패 하나(F 라 부름)를 줄 오른쪽 끝에 붙임 → 줄 오른쪽 끝 두 장 = D, F(왼쪽부터).",
                             "14:21:01.0 ~ 01.2: 오른손이 줄 오른쪽 끝 2장(D, F)을 한 덩어리로 집어 뺌.",
                             "14:21:01.7 ~ 02.6: 왼손이 줄을 5장 / 5장으로 벌리고, 들고 있던 2장을 그 틈에 끼움.",
                             "14:21:03.5 이후: 다른 패 하나를 줄 오른쪽 끝에 붙여 13장, 줄 통째로 밀기 · 5번째 패를 빼 보고 같은 자리에 넣기."],
                    question="틈에 끼운 두 장이 왼쪽부터 D, F 인가, F, D 인가? (끝 줄 13장에서 D 가 6번째인가 7번째인가)",
                    hyps={"D 가 6번째": "끼운 두 장이 왼쪽부터 D, F — 덩어리 안 순서 그대로",
                          "D 가 7번째": "끼운 두 장이 왼쪽부터 F, D — 손 안에서 두 장 순서가 뒤집힘"},
                    tiles={"D 가 6번째": "3s", "D 가 7번째": "5s"}),
    "r13_1st": dict(game="r13_132644", win=("13:27:21.0", "13:27:33.0"),
                    context=["13:27:13 무렵 뽑은 패 D 를 14장 줄 맨 오른쪽에 붙임, 15 ~ 16초에 줄 가운데 패 하나를 버림.",
                             "13:27:17 ~ 26: 줄을 몸 쪽 새 줄로 나눠 옮김. 26초 무렵 몸 쪽 새 줄 11장 + 오른쪽 위에 두 장(왼쪽 = 원래 줄의 패 하나(E 라 부름), 오른쪽 = D)이 남음.",
                             "13:27:27.4 ~ 28.3: 오른손 손바닥이 위의 두 장을 함께 덮어 끌어내려 새 줄 오른쪽 끝에 붙임.",
                             "13:27:29.0 ~ 29.1: 줄에 붙은 쪽 1장을 손가락이 빼 감, 바깥쪽 1장은 따로 남음.",
                             "13:27:29.3 ~ 30.3: 빼 간 1장을 줄 왼쪽 끝에 넣음, 30.6 ~ 31.2: 남은 1장을 줄 오른쪽 끝에 밀어 붙여 13장."],
                    question="끝 줄에서 D 는 오른쪽 끝(13번째)인가 왼쪽 끝(1번째)인가? (손바닥 밑에서 두 장 순서가 바뀌었나)",
                    hyps={"D 가 13번째": "손바닥 밑에서 두 장 순서 그대로(E, D) — 빼 간 것은 E, 오른쪽에 남은 것이 D",
                          "D 가 1번째": "손바닥 밑에서 두 장 순서가 바뀜(D, E) — 빼 가서 왼쪽 끝에 넣은 것이 D"},
                    tiles={"D 가 13번째": "1z", "D 가 1번째": "1s"}),
}

# 사람이 확인한 답(채점용) — 이 파일 안에서만, 항목 폴더엔 안 들어감
CONFIRMED = {"r16_d13": ("Opus", "user 11-20 — truth_fix_1120"), "r17_d08": ("정답 메모", "user"), "r19_1st": ("D 가 6번째", "user"), "r13_1st": ("D 가 13번째", "user")}


def shuffled(name, items):
    r = random.Random(int(hashlib.md5(name.encode()).hexdigest(), 16))
    items = list(items)
    r.shuffle(items)
    return items


def frames_for(t0, t1):
    seen, out = set(), []
    for m in hc.frame_range(hc.to_ms(t0), hc.to_ms(t1)):
        if hc.hms(m) not in seen:
            seen.add(hc.hms(m))
            out.append((hc.hms(m), m))
    return out


def dump(d, game, t0, t1):
    c = hc.config(game)
    (d / "frames").mkdir(parents=True, exist_ok=True)
    (d / "sheets").mkdir(exist_ok=True)
    lines, tiles = [], []
    for t, m in frames_for(t0, t1):
        im = Image.fromarray(hc.band_crop(hc.load(m), c["wide"], c["side"])).crop(BOX)
        p = d / "frames" / f"{t.replace(':', '')}.jpg"
        im.save(p, quality=92)
        lines.append(f"{t} {p.as_posix()}")
        s = im.resize((im.width * 2 // 3, im.height * 2 // 3))
        ImageDraw.Draw(s).rectangle([0, 0, 120, 22], fill=(0, 0, 0))
        ImageDraw.Draw(s).text((5, 4), t[3:], fill=(255, 255, 0), font_size=16)
        tiles.append(s)
    (d / "frames.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    tw, th = tiles[0].size
    for k in range(0, len(tiles), 12):
        part = tiles[k:k + 12]
        sh = Image.new("RGB", (tw * 3, th * ((len(part) + 2) // 3)), (30, 30, 30))
        for i, im in enumerate(part):
            sh.paste(im, ((i % 3) * tw, (i // 3) * th))
        sh.save(d / "sheets" / f"sheet{k // 12 + 1:02d}.jpg", quality=88)
    return len(lines), (len(tiles) + 11) // 12


COMMON = """
## 그림
- 위에서 내려다본 녹화를 이 사람 시점으로 돌려 손패 줄 둘레만 자른 것. 그림 왼쪽 = 이 사람 왼손 쪽, 아래쪽 = 몸 쪽.
- 패는 세워져 있어 위에서는 **등(색 띠)과 흰 면만** 보인다 — 모든 패가 똑같이 생겼다. 읽는 것은 위치와 움직임뿐.
- `sheets/sheetNN.jpg`: 0.1초 간격 12장씩(3열, 왼쪽 위에 시각). 먼저 이것으로 흐름을 본다.
- `frames/<시각>.jpg`: 같은 프레임 원래 크기(950 × 360). 갈리는 순간은 반드시 이것을 열어 본다. 필요하면 Python(PIL)으로 더 잘라 키워 봐도 된다(결과는 이 폴더의 work/ 에).
- 다른 사람 팔이 지나가기도 한다.

## 규칙
- **이 폴더 안의 파일만** 연다(`frames.txt` 에 적힌 경로 포함). 다른 폴더 · 다른 판 · 이전 답 파일을 찾거나 열지 않는다(Grep · Glob · ls 로 밖을 뒤지지 않는다).
- 가설 글자의 순서에는 뜻이 없다(섞어 놓음).
- 그림이 근거의 우선이다. 정렬 습관은 그림만으로 가를 수 없을 때만 쓴다. 쓴 경우 `used_sort_prior: true`.
- 그림에서 두 가설을 가르는 장면이 실제로 안 보이면 지어내지 말고 confidence 를 "모름" 으로.

## 답
`answer.json` 을 이 폴더에 쓴다(UTF-8):
```json
{"choice": "A", "confidence": "확실 | 아마 | 모름", "used_sort_prior": false,
 "evidence": [{"time": "hh:mm:ss.s", "saw": "그 프레임에서 본 것"}],
 "why": "가설마다 어느 프레임의 무엇과 맞고 어긋나는지"}
```
"""


def prep(only=None):
    ROOT.mkdir(parents=True, exist_ok=True)
    keyf = {}
    flags = {f["id"]: f for f in flag()}
    for tid, (t0, t1, start) in TURN_WIN.items():
        if only and tid not in only:
            continue
        f = flags[tid]
        recs, sch = ro.rebuild(f["game"], "full")
        x = next(r for r in recs if r["id"] == tid)
        hyps = [("Opus", f["opus"])] + [(f"alt{i + 1}", a) for i, a in enumerate(f["alts"])]
        hyps = shuffled(tid, hyps)
        letters = "ABCD"
        d = ROOT / tid
        n, ns = dump(d, f["game"], t0, t1)
        p = {lab: f"p{i + 1}" for i, lab in enumerate(start)}
        lines = [f"# 손패 줄 한 구간 다시 보기 — {tid}", "",
                 f"녹화 {t0} ~ {t1} (0.1초 간격 {n}장, 묶음 {ns}장). 이 사람은 이 차례에 패를 한 장 뽑고(뽑은 패 = D) 한 장을 강에 버린다.",
                 f"**구간 첫 프레임({t0})의 손패 줄을 왼쪽부터 p1 … p{len(start)} 이라고 부른다**({len(start)}장, 손에 가린 패가 있으면 앞뒤 프레임으로 센다)."
                 + (" 이 구간 안에서 p12 가 강으로 버려진다." if tid == "r13_d04" else ""),
                 f"구간 끝({t1}) 뒤로 이 차례가 끝날 때까지 줄 순서는 바뀌지 않는다.", "",
                 "## 질문", "구간 끝의 줄은 아래 가설 중 어느 것인가?", ""]
        after = x["after"]
        for L, (nm, order) in zip(letters, hyps):
            end = [p[lab] for lab in order]
            b, drawn = ro.back(after, order, x["river"])
            tmap = {lab: after[i] for i, lab in enumerate(order)}
            st = [tmap.get(lab, x["river"]) for lab in start]
            lines += [f"### 가설 {L}", f"- 구간 끝 줄(왼쪽부터): {' '.join(end)}",
                      f"- 이 가설이면 구간 첫 줄의 패: {' '.join(st)}",
                      f"- 이 가설이면 이 차례 시작 손패 줄: {' '.join(b)} (정렬 어긋남 {bad(b, sch)}곳)", ""]
            keyf.setdefault(tid, {})[L] = nm
        moved = [k for k in range(len(hyps[0][1])) if len({h[1][k] for h in hyps}) > 1]
        lines += ["가설끼리 다른 곳: 구간 끝 줄의 " + ", ".join(f"{k + 1}번째" for k in moved) + " 자리.", "",
                  "## 근거로 쓸 수 있는 것: 정렬 습관",
                  f"- 이 차례가 끝난 뒤 줄의 패: {' '.join(after)} (어긋남 {bad(after, sch)}곳)",
                  f"- 이 사람 끝 손패에서 읽은 정렬: 무늬 순서 {sch.get('suit_order')}, 오름차순 {sch.get('ascending')}, "
                  f"이웃 쌍 오름 {sch.get('pairs_up')} · 내림 {sch.get('pairs_down')}"
                  + (" — 내림 쌍이 있어 정렬 습관은 약함" if sch.get("pairs_down") else " — 정렬을 꽤 지키는 사람"),
                  "- 패 이름: m 만수 · p 통수 · s 삭수 · z 자패, 0 = 붉은 5."]
        (d / "TASK.md").write_bytes(("\n".join(lines) + "\n" + COMMON).encode("utf-8"))
        print(tid, n, "장 · 가설", len(hyps))
    for nm, it in FIRST.items():
        if only and nm not in only:
            continue
        d = ROOT / nm
        n, ns = dump(d, it["game"], *it["win"])
        hy = shuffled(nm, list(it["hyps"].items()))
        lines = [f"# 손패 줄 한 구간 다시 보기 — {nm}", "",
                 f"녹화 {it['win'][0]} ~ {it['win'][1]} (0.1초 간격 {n}장, 묶음 {ns}장). 판의 첫 차례: 이 사람이 패산에서 한 장 뽑고(D) 한 장을 버린 뒤 손패 줄을 정리한다.",
                 "", "## 앞선 읽기에서 이미 본 것(믿어도 됨)", *[f"- {c}" for c in it["context"]], "",
                 "## 질문", it["question"], ""]
        for L, (hn, desc) in zip("AB", hy):
            lines += [f"### 가설 {L}", f"- {hn}: {desc}", ""]
            keyf.setdefault(nm, {})[L] = hn
        lines += ["## 근거로 쓸 수 있는 것", "- 두 가설은 패 종류로 가를 수 없다(정렬 습관 근거 없음). 그림만 본다."]
        (d / "TASK.md").write_bytes(("\n".join(lines) + "\n" + COMMON).encode("utf-8"))
        print(nm, n, "장")
    old = hc.jload(ROOT / "_key.json") if (ROOT / "_key.json").exists() else {}
    hc.jsave(ROOT / "_key.json", {**old, **keyf})


def score():
    keyf = hc.jload(ROOT / "_key.json")
    truth = {}
    flags = {f["id"]: f for f in flag()}
    for tid in TURN_WIN:                           # 정답 메모 순서와 같은 가설(r17_d08 은 사용자 확인과 같음)
        g = next(x for x in GAMES if x.startswith(tid[:3]))
        rt, _ = ro.rebuild(g, "truth")
        t = next(r for r in rt if r["id"] == tid)
        f = flags[tid]
        names = {"Opus": f["opus"], **{f"alt{i + 1}": a for i, a in enumerate(f["alts"])}}
        hit = [nm for nm, o in names.items() if o == t["order"]]
        truth[tid] = hit[0] if hit else None
    for nm, (h, _) in CONFIRMED.items():
        if nm in FIRST:
            truth[nm] = h
    for nm in [*TURN_WIN, *FIRST]:
        f = ROOT / nm / "answer.json"
        if not f.exists():
            print(nm, "답 없음")
            continue
        a = hc.jload(f)
        got = keyf[nm].get(a.get("choice"), a.get("choice"))
        src = "사용자" if nm in CONFIRMED else "정답 메모"
        print(f"{nm}: 고름 {a.get('choice')}={got} · {a.get('confidence')} · 정렬 {a.get('used_sort_prior')} | 맞는 답({src}) {truth[nm]} "
              f"→ {'✓' if got == truth[nm] else '✗'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["flag", "prep", "score"])
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    if a.cmd == "flag":
        flag()
    elif a.cmd == "prep":
        prep(a.names or None)
    else:
        score()


if __name__ == "__main__":
    main()
