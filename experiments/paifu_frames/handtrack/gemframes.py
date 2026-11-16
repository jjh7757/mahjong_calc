"""프레임 그림을 Gemini 에 줘서 들어간 칸(j)을 묻기(2026-11-16, 계획서 3단계 "추가 3" — 방법·채점은 결과 전에 적음).

  python -X utf8 gemframes.py make                       # 조건 A(차례 전체)·B(넣는 순간만) 프레임 묶음 → _work/gemframes_1116/<조건>/<id>/
  python -X utf8 gemframes.py count --model M            # 호출 없이 입력 토큰만 셈(count_tokens)
  python -X utf8 gemframes.py run --model M --arm A --rep 1   # 9차례 호출 → answers/<모델>_<조건>_r<회>.json
  python -X utf8 gemframes.py score                      # 모든 답 파일 채점
정답은 insert_truth_1116.json(한 칸 9차례). 요청에는 프레임 그림·시각·줄 장수 N 만 들어간다(정답·판 이름 없음).
키: 기존 bench.py 와 같은 .env 의 GEMINI_API_KEY.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beforeafter as ba  # noqa: E402
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402
import stripview as sv  # noqa: E402

OUT = hc.WORK / "gemframes_1116"
SCALE, PAD = 2.0, (40, 75)
# 조건 B: 이 세션이 눈으로 정한 "다시 집는 순간 ~ 줄이 붙을 때" 창(시각만 고름 — 칸은 안 들어감). (판, 구간): (시작, 끝)
B_WIN = {
    ("r18_141259", 6): ("14:13:14.4", "14:13:17.6"),
    ("r18_141259", 8): ("14:13:35.5", "14:13:38.6"),
    ("r18_141259", 11): ("14:14:20.5", "14:14:24.0"),
    ("r18_141259", 20): ("14:16:39.0", "14:16:42.6"),
    ("n03_150528", 2): ("15:06:23.2", "15:06:26.2"),
    ("n03_150528", 4): ("15:06:49.8", "15:06:53.2"),
    ("n03_150528", 7): ("15:07:17.0", "15:07:20.2"),
    ("n03_150528", 11): ("15:07:42.0", "15:07:45.3"),
    ("n03_150528", 35): ("15:11:05.6", "15:11:09.0"),
}

PROMPT = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 연속 프레임이다. 프레임은 시간 순서이고 각 그림 앞에 시각(분:초)을 적었다.
그림은 그 사람 시점으로 돌려져 있다: 그림의 왼쪽 = 그 사람의 왼손 쪽. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 무늬는 안 보인다. 줄 아래쪽의 흰 띠는 탁자 테두리다.

{scope}
이 차례에 그 사람은 패산에서 패 한 장(D 라고 부르자)을 뽑아 왔고, 줄에 원래 있던 패 한 장을 버렸다. 그래서 차례가 끝나면 줄은 다시 {n}장이다.

물음: 차례가 끝났을 때 D 는 줄의 왼쪽부터 몇 번째에 서 있나? (1 ~ {n})

참고 — 사람들이 흔히 하는 동작:
- D 를 줄 오른쪽 끝에 잠시 붙여 두었다가, 한 장을 버린 뒤 D 를 다시 집어 줄 안쪽에 끼워 넣는 일이 많다. 끝에 그대로 두는 사람도 있다.
- 끼울 때 다른 손으로 패 몇 장을 옆으로 밀어 틈을 만들거나, 끝의 패 몇 장을 D 와 함께 쥐었다가 D 를 먼저 내려놓고 나머지를 다시 붙이기도 한다.
- 넣는 순간은 손에 가려지는 일이 많다. 그럴 때는 제자리에 그대로 남은 패가 몇 장인지, 손이 옮긴 패가 몇 장인지 세면 D 가 선 칸을 알 수 있다. 버린 패가 빠진 빈자리와 D 를 넣으려고 벌린 틈을 헷갈리지 말 것.

JSON 으로만 답하라: steps = 본 것을 시각과 함께 짧게(3~6문장), j = D 가 선 칸(정수) 또는 판단할 수 없으면 null, confidence = "high" 또는 "low".
"""
SCOPE = {
    "A": "프레임은 이 차례 전체다(손이 들어오기 전부터 떠난 뒤까지, 초당 약 5장).",
    "B": "프레임은 이 차례의 뒷부분만이다: 한 장을 이미 버린 뒤, D 를 줄에 넣고 줄을 정리하는 약 3초(초당 10장). 첫 프레임에서 줄에는 버린 패가 빠진 빈자리가 있을 수 있다.",
}
SCHEMA = {"type": "OBJECT", "properties": {"steps": {"type": "STRING"}, "j": {"type": "INTEGER", "nullable": True},
                                            "confidence": {"type": "STRING", "enum": ["high", "low"]}},
          "required": ["steps", "j", "confidence"]}


def turns():
    """정답 한 칸 9차례: id, 판, 구간, N, 정답 j, 조건별 프레임 시각."""
    out = []
    for gid in ("r18_141259", "n03_150528"):
        sg = hc.jload(hc.OUT / gid / "segments.json")
        rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
        tmap = {t["t"]: t for t in rp["turns"]}
        n_hand = 13
        for tr in ba.turns_from_replay(rp, sg):
            if "call" in " ".join(tr["events"]):
                n_hand = 10
            T = pt.truth_of(gid, tmap[tr["t"]])
            if T["mode"] != "손에서" or not T["j"]:
                continue
            seg = tr["segs"][0]
            b0, b1 = B_WIN[(gid, seg)]
            out.append({"id": f"{gid[:3]}_t{tr['t']:02d}", "game": gid, "seg": seg, "t": tr["t"], "n": n_hand, "j": T["j"],
                        "A": hc.frame_range(tr["ms_before"], tr["ms_after"])[::2],
                        "B": hc.frame_range(hc.to_ms(b0), hc.to_ms(b1))})
    return out


def render(gid: str, ms: int) -> Image.Image:
    cfg = hc.config(gid)
    v = hc.band_crop(hc.load(ms), sv.wide_band(cfg, *PAD), cfg["side"])
    im = Image.fromarray(v)
    im = im.resize((round(im.width * SCALE), round(im.height * SCALE)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 96, 26], fill=(0, 0, 0))
    d.text((4, 2), hc.hms(ms)[3:], fill=(255, 255, 0), font=sv.font(19))
    return im


def cmd_make(a):
    idx = []
    for t in turns():
        row = {k: t[k] for k in ("id", "game", "seg", "t", "n")}
        for arm in "AB":
            d = OUT / arm / t["id"]
            d.mkdir(parents=True, exist_ok=True)
            for old in d.glob("*.jpg"):
                old.unlink()
            for i, ms in enumerate(t[arm]):
                render(t["game"], ms).save(d / f"{i:03d}_{ms}.jpg", quality=90)
            row[arm] = {"frames": len(t[arm]), "t0": hc.hms(t[arm][0]), "t1": hc.hms(t[arm][-1])}
        idx.append(row)
        print(row)
    hc.jsave(OUT / "index.json", idx)  # 정답 없음


def parts_of(arm: str, t: dict, types):
    ps = [PROMPT.format(scope=SCOPE[arm], n=t["n"])]
    for f in sorted((OUT / arm / t["id"]).glob("*.jpg")):
        ms = int(f.stem.split("_")[1])
        ps.append(f"프레임 {hc.hms(ms)[3:]}")
        part = types.Part.from_bytes(data=f.read_bytes(), mime_type="image/jpeg")
        part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
        ps.append(part)
    ps.append(f"위 프레임을 보고 답하라. 줄은 {t['n']}장이다.")
    return ps


def client():
    from dotenv import load_dotenv
    from google import genai
    load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def cmd_count(a):
    from google.genai import types
    c = client()
    tot = 0
    for arm in a.arms:
        for t in turns():
            r = c.models.count_tokens(model=a.model, contents=parts_of(arm, t, types))
            tot += r.total_tokens
            print(arm, t["id"], r.total_tokens)
    print("합", tot)


def one(c, types, model, arm, t):
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=SCHEMA)
    t0 = time.perf_counter()
    for attempt in range(3):
        try:
            r = c.models.generate_content(model=model, contents=parts_of(arm, t, types), config=cfg)
            um = r.usage_metadata
            data = json.loads(r.text)
            return {"id": t["id"], "j": data.get("j"), "confidence": data.get("confidence"), "steps": data.get("steps"),
                    "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                    "think": getattr(um, "thoughts_token_count", 0) or 0, "model_version": getattr(r, "model_version", None), "attempt": attempt + 1}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"[:300]
            time.sleep(5 * (attempt + 1))
    return {"id": t["id"], "j": None, "error": err, "s": round(time.perf_counter() - t0, 1), "in": 0, "out": 0, "think": 0}


def cmd_run(a):
    from google.genai import types
    ts = turns()
    for arm in a.arms:
        for rep in range(a.rep0, a.rep0 + a.reps):
            f = OUT / "answers" / f"{a.model}_{arm}_r{rep}.json"
            if f.exists() and not a.force:
                print("있음 — 건너뜀", f.name)
                continue
            with ThreadPoolExecutor(a.workers) as ex:
                rows = list(ex.map(lambda t: one(client(), types, a.model, arm, t), ts))
            hc.jsave(f, {"model": a.model, "arm": arm, "rep": rep, "at": hc.hms(int(time.time() * 1000), date=True), "rows": rows})
            print(f.name, [(r["id"], r["j"], r.get("error", "")[:40]) for r in rows])


def cmd_score(a):
    truth = {t["id"]: t for t in turns()}
    ids = list(truth)
    groups = {}
    for f in sorted((OUT / "answers").glob("*.json")):
        d = hc.jload(f)
        groups.setdefault((d["model"], d["arm"]), []).append(d)
    res = []

    def cnt(ans):  # ans: id → j
        ok = sum(ans[i] == truth[i]["j"] for i in ids)
        none = sum(ans[i] is None for i in ids)
        near = sum(ans[i] is not None and abs(ans[i] - truth[i]["j"]) == 1 for i in ids)
        return ok, len(ids) - ok - none, none, near

    for (model, arm), ds in groups.items():
        per = []
        for d in ds:
            ans = {r["id"]: r["j"] for r in d["rows"]}
            c = cnt(ans)
            tin, tout, tth = (sum(r[k] for r in d["rows"]) for k in ("in", "out", "think"))
            secs = sorted(r["s"] for r in d["rows"])
            errs = sum("error" in r for r in d["rows"])
            per.append({"rep": d["rep"], "at": d["at"], "score": c, "in": tin, "out": tout, "think": tth, "s_med": secs[len(secs) // 2], "s_max": secs[-1],
                        "errors": errs, "ans": ans, "model_version": d["rows"][0].get("model_version")})
            print(f"{model} {arm} r{d['rep']} ({d['at']}): 맞음·틀림·없음 {c[0]} · {c[1]} · {c[2]} /{len(ids)}, 한 칸 차 {c[3]} | 토큰 입력 {tin:,} 출력 {tout:,} 생각 {tth:,} | 초 중앙 {secs[len(secs) // 2]} 최대 {secs[-1]} | 오류 {errs}")
        row = {"model": model, "arm": arm, "reps": per}
        if len(ds) >= 3:
            maj = {}
            for i in ids:
                v, n = Counter(p["ans"][i] for p in per).most_common(1)[0]
                maj[i] = v if n >= 2 else None
            row["majority"] = {"score": cnt(maj), "ans": maj}
            c = row["majority"]["score"]
            print(f"{model} {arm} 다수결: {c[0]} · {c[1]} · {c[2]} /{len(ids)}, 한 칸 차 {c[3]}")
        print("   차례별(정답 ← 답들): " + ", ".join(f"{i} {truth[i]['j']}←{'/'.join(str(p['ans'][i]) for p in per)}" for i in ids))
        res.append(row)
    hc.jsave(OUT / "score.json", res)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("make")
    c = sp.add_parser("count")
    c.add_argument("--model", default="gemini-3.8-flash")
    c.add_argument("--arms", default="AB")
    r = sp.add_parser("run")
    r.add_argument("--model", default="gemini-3.8-flash")
    r.add_argument("--arms", default="AB")
    r.add_argument("--reps", type=int, default=1)
    r.add_argument("--rep0", type=int, default=1)
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--force", action="store_true")
    sp.add_parser("score")
    a = ap.parse_args()
    {"make": cmd_make, "count": cmd_count, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
