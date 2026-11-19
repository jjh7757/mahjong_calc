"""SAM 2 추적 그림(마스크 겹친 프레임)을 Gemini 에게 주고 읽히기(2026-11-18, 계획서 3단계 "추가 28").

사용자가 처음 물은 꼴 그대로 — 글 요약이 아니라 그림. v1 추적(sam2track.py, 처음 한 번만 붙임)의 마스크를 그 차례의 프레임 전부에 겹쳐 프레임마다 한 장.

  python -X utf8 sam2img.py make                 # 겹친 프레임 → _work/sam2img_1118/frames/<id>/NNNNN.jpg
  python -X utf8 sam2img.py count                # 호출 없이 입력 토큰만 셈(count_tokens)
  python -X utf8 sam2img.py run [--reps 2]       # 차례마다 한 번 → read_gemimg_M_r<회>.json
  python -X utf8 sam2img.py score                # 정답 · 글 팔(표 12-50) · 저장된 A · B · SAM 2 코드와 나란히
요청에는 프레임 그림 · 시각 · 줄 장수 · 안내만 들어간다(정답 없음).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402

OUT = hc.WORK / "sam2img_1118"
IDS = m.IDS
MODEL = "gemini-3.8-flash"
V1 = argparse.Namespace(model="t", device="xpu")
COLORS = [(230, 60, 60), (60, 190, 60), (70, 100, 240), (240, 200, 40), (220, 60, 220), (40, 210, 220), (250, 140, 30),
          (140, 70, 220), (150, 220, 60), (240, 110, 160), (30, 140, 140), (160, 100, 40), (120, 120, 255)]

PROMPT = """위에서 내려다본 카메라로 마작 대국자 한 사람의 세운 손패 줄을 찍은 연속 프레임이다. 프레임은 시간 순서이고 각 그림 앞에 시각(분:초)을 적었다.
그림은 그 사람 시점으로 돌려져 있다: 그림의 왼쪽 = 그 사람의 왼손 쪽. 패는 세워져 있어 위에서는 등(색 띠)과 흰 면만 보이고 무늬는 안 보인다. 줄 아래쪽의 흰 띠는 탁자 테두리다.
다른 사람의 팔이나 소매가 줄 위를 지나가기도 한다 — 줄 아래쪽에 앉은 이 사람의 손 동작만 본다. 그림 위쪽에 따로 놓인 패 줄(패산 등)은 이 사람의 손패가 아니다.

프레임은 이 사람의 **한 차례**(패산에서 한 장을 뽑아 오고, 한 장을 강에 버림)다. 손패 줄이 {n}장으로 붙어 선 시작 모습부터, 버리고 정리해 다시 {n}장으로 붙어 선 끝 모습까지 초당 5장으로 이어져 있다.
이 차례를 시작할 때 줄은 {n}장이다. 뽑아 온 패를 D 라고 부르자.

## 패 위의 색과 숫자
- 각 패 위의 반투명 색과 숫자는 영상 추적 모델(SAM 2)이 칠한 것이다. 첫 프레임에서 줄의 패 {n}장에 **왼쪽부터 1 ~ {n}** 번호를 붙였고, 그 뒤 프레임마다 모델이 "같은 패" 라고 본 곳에 같은 색 · 같은 숫자를 칠했다.
- 뽑아 온 패 D 에는 번호를 붙이지 않았다 — 색이 안 칠해진 패가 D 일 수 있다.
- 패 뒷면이 모두 같아서 **추적은 틀릴 수 있다.** 숫자가 그 패라는 보장은 없다. 이 추적의 버릇:
  - 손에 들려 혼자 움직이는 패는 대체로 따라간다 — 색이 손에 든 패를 따라 **이어서** 옮겨 가면 그 패가 실제로 그리 간 것이다.
  - 버린 패의 색은 사라지지 않고 이웃 패나 다른 패에 옮겨 붙는 일이 많다(한 패에 숫자 둘이 겹쳐 보인다). 겹친 둘 중 하나는 실제로는 줄을 떠난 패다.
  - 손이 덮은 동안 줄이 밀리거나 패가 끼워지면, 덮였던 패의 색은 패를 따라가지 않고 **한 프레임 만에 옛 자리로 뛰어 돌아오는** 일이 많다. 그러면 숫자는 가지런히 앉아 있어도 실제 패와 어긋나 있고, 색 없는 패가 D 가 아닌 자리에 생긴다.
  - 그러니 끝에 색 없는 패가 곧 D 라고 단정하지 말고, 색이 이어서 움직였는지 갑자기 뛰었는지를 프레임을 따라가며 본다. 갑자기 뛰어 옛 자리로 돌아온 숫자가 앉은 패는 D 일 수 있고, 그 숫자의 실제 패는 뛰기 직전에 있던 곳에 색 없이 남아 있을 수 있다.

답할 것:
- kind: "tsumogiri" = D 를 그대로 버림(줄의 패는 안 바뀜) / "hand" = 줄에 있던 패를 버리고 D 가 줄에 남음.
- k (hand 일 때만, 아니면 null): 버린 패가 원래 줄 {n}장에서 왼쪽부터 몇 번째였나(1 ~ {n}). D 는 세지 않는다 — D 를 먼저 줄에 끼운 뒤 버렸더라도 D 를 뺀 번호로 답한다.
- j (hand 일 때만, 아니면 null): 이 차례가 끝났을 때 D 가 줄({n}장)의 왼쪽부터 몇 번째에 서 있나(1 ~ {n}). 끝에 그대로 두었으면 {n}.
- unsure: 답이 맞을 가능성을 70% 밑으로 보면 true.

참고:
- 깨끗한(손이 안 닿은) 프레임에서 패를 하나씩 센다. 손가락이 줄 위에 얹혀 끊겨 보이는 것은 빈칸이 아니다 — 사이로 초록 펠트가 보여야 빈칸이다.
- D 를 끝에 붙여 두고 한 장을 버린 뒤 그대로 두는 사람, 버린 뒤 D 를 다시 집어 안쪽에 끼우는 사람, D 를 먼저 안쪽에 끼우고 나서 버리는 사람이 다 있다.
- 넣는 순간이 손에 가려지면, 제자리에 그대로 남은 패가 왼쪽·오른쪽에 몇 장인지와 손이 옮긴 패가 몇 장인지로 따진다. 버린 패가 빠진 빈자리와 D 를 넣으려고 벌린 틈을 헷갈리지 말 것.

JSON 으로만 답하라: steps = 본 것을 시각과 함께(색 · 숫자가 어떻게 움직였는지 포함), kind, k, j(해당 없으면 null), unsure, why = 근거 한두 문장.
"""


# 대조 팔 N(계획서 추가 29) = 같은 프레임에서 마스크만 뺀 것. 프롬프트는 "패 위의 색과 숫자" 절만 빼고 글자까지 같다.
_A, _B = PROMPT.index("## 패 위의 색과 숫자"), PROMPT.index("답할 것:")
_S = "steps = 본 것을 시각과 함께(색 · 숫자가 어떻게 움직였는지 포함)"
assert _S in PROMPT
PROMPT_N = (PROMPT[:_A] + PROMPT[_B:]).replace(_S, "steps = 본 것을 시각과 함께")
PROMPTS = {"M": PROMPT, "N": PROMPT_N}

# 영상 팔 V(계획서 추가 30) = N 과 같은 잘라 낸 원본 프레임을 초당 5장 mp4 한 편으로. 프롬프트는 PROMPT_N 에서 낱장 → 영상 꼴 말만 바꿈.
_V_SWAPS = [
    ("찍은 연속 프레임이다. 프레임은 시간 순서이고 각 그림 앞에 시각(분:초)을 적었다.",
     "찍은 짧은 영상이다(초당 5장 그대로 — 프레임을 솎지 않음). 영상 안의 시각은 이 차례 시작부터 잰 것이다."),
    ("그림은 그 사람 시점으로 돌려져 있다: 그림의 왼쪽", "영상은 그 사람 시점으로 돌려져 있다: 화면의 왼쪽"),
    ("그림 위쪽에 따로 놓인", "화면 위쪽에 따로 놓인"),
]
PROMPT_V = PROMPT_N
for _a, _b in _V_SWAPS:
    assert _a in PROMPT_V
    PROMPT_V = PROMPT_V.replace(_a, _b)
PROMPTS["V"] = PROMPT_V
# 마스크 + D 팔(계획서 추가 31) = M 그림에 뽑은 패 D 의 추적(sam2dtrack.py)을 더 칠한 것. 프롬프트는 PROMPT 에서 "D 에는 번호를 안 붙였다" 한 줄만 D 설명으로 바꿈.
_D_OLD = "- 뽑아 온 패 D 에는 번호를 붙이지 않았다 — 색이 안 칠해진 패가 D 일 수 있다.\n"
_D_NEW = ("- 뽑아 온 패 D 도 따로 따라갔다: D 가 줄 끝에 처음 한 장 더 붙은 프레임부터 **흰색으로 칠하고 검은 테두리 · 빨간 글자 D** 를 붙였다(그 전 프레임에는 D 표시가 없다). D 표시도 추적이라 틀릴 수 있다.\n"
          "- D 를 줄에 넣은 뒤 버리기 전까지 줄의 패는 {n} + 1 장이다. 패 수가 번호 수보다 많거나, 한 패에 숫자와 D 가 겹치거나, 색 없는 패가 있으면 어딘가 번호가 한 칸 밀려 앉은 것이다 — "
          "그 패와 이웃 패의 색이 어떻게 이어져 왔는지 프레임을 따라가 어느 표시가 실제 패를 따라온 것인지 가린다. 색 없는 패는 번호를 잃은 원래 패일 수 있다.\n")
assert _D_OLD in PROMPT
PROMPT_D = PROMPT.replace(_D_OLD, _D_NEW)
PROMPTS["D"] = PROMPT_D
CLOSE = {"M": "위 프레임을 보고 답하라.", "N": "위 프레임을 보고 답하라.", "V": "위 영상을 보고 답하라.", "D": "위 프레임을 보고 답하라."}
VIDEO_FPS = 5

# 추가 30 — 안 본 17차례(r19 4순은 끝 줄 없음으로 뺌). 끼움 · 옮김 6, 나머지는 끝 붙임 쪽(표 12-43).
NEW17 = ["r12_d03b", "r12_d06", "r16_d03", "r16_d04", "r16_d06", "r16_d08", "r16_d12", "r17_d10", "r17_d11",
         "r19_d03", "r19_d03b", "r19_d07", "r13_d03", "r13_d04", "r13_d05", "r13_d08", "r13_d09"]
INSERT6 = {"r17_d11", "r19_d03b", "r13_d05", "r13_d09", "r12_d06", "r19_d07"}


def ids_of(a) -> list:
    if not getattr(a, "ids", None):
        return list(IDS)
    return list(NEW17) if a.ids == "new17" else a.ids.split(",")


def frame_dir(tid: str, arm: str = "M") -> Path:
    return OUT / {"M": "frames", "N": "frames_raw", "V": "video", "D": "frames_d"}[arm] / tid


def make_raw(ids):
    """대조 팔: v1 실행이 잘라 둔 같은 프레임을 마스크 없이 품질 90 으로 다시 저장."""
    for tid in ids:
        d = s1.run_dir(tid, V1)
        tr = hc.jload(d / "track.json")
        fd = frame_dir(tid, "N")
        fd.mkdir(parents=True, exist_ok=True)
        for fi in range(len(tr["frames"])):
            Image.open(d / "frames" / f"{fi:05d}.jpg").convert("RGB").save(fd / f"{fi:05d}.jpg", quality=90)
        hc.jsave(fd / "meta.json", {"id": tid, "n": tr["plan"]["n"], "frames": tr["frames"], "shape": tr["shape"]}, indent=None)
        print(tid, len(tr["frames"]), "장(마스크 없음)", flush=True)


def make_video(ids):
    """영상 팔 V: v1 실행이 잘라 둔 같은 원본 프레임(품질 95)을 초당 5장 H.264 mp4 한 편으로(crf 18, 홀수 변은 가장자리 한 줄 복제)."""
    import imageio_ffmpeg
    for tid in ids:
        d = s1.run_dir(tid, V1)
        tr = hc.jload(d / "track.json")
        H, W = tr["shape"]
        H2, W2 = H + H % 2, W + W % 2
        fd = frame_dir(tid, "V")
        fd.mkdir(parents=True, exist_ok=True)
        w = imageio_ffmpeg.write_frames(str(fd / "clip.mp4"), (W2, H2), fps=VIDEO_FPS, codec="libx264", quality=None,
                                        pix_fmt_out="yuv420p", macro_block_size=1, output_params=["-crf", "18"])
        w.send(None)
        for fi in range(len(tr["frames"])):
            im = np.asarray(Image.open(d / "frames" / f"{fi:05d}.jpg").convert("RGB"))
            if im.shape[:2] != (H2, W2):
                im = np.pad(im, ((0, H2 - im.shape[0]), (0, W2 - im.shape[1]), (0, 0)), mode="edge")
            w.send(np.ascontiguousarray(im))
        w.close()
        mb = (fd / "clip.mp4").stat().st_size / 1e6
        hc.jsave(fd / "meta.json", {"id": tid, "n": tr["plan"]["n"], "frames": tr["frames"], "shape": [H2, W2], "fps": VIDEO_FPS, "crf": 18, "mb": round(mb, 2)}, indent=None)
        print(tid, len(tr["frames"]), "장 → 영상", f"{W2}x{H2}", f"{mb:.2f}MB", flush=True)


def cmd_make(a):
    ids = ids_of(a)
    if a.arm == "N":
        return make_raw(ids)
    if a.arm == "V":
        return make_video(ids)
    try:
        font = ImageFont.truetype("arialbd.ttf", 15)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    for tid in ids:
        d = s1.run_dir(tid, V1)
        tr = hc.jload(d / "track.json")
        H, W = tr["shape"]
        M = np.load(d / "masks.npz")
        n, F = tr["plan"]["n"], len(tr["frames"])
        DM = np.load(d / "dmasks.npz") if a.arm == "D" else None
        fd = frame_dir(tid, a.arm)
        fd.mkdir(parents=True, exist_ok=True)
        for fi in range(F):
            ov = np.asarray(Image.open(d / "frames" / f"{fi:05d}.jpg")).astype(np.float32)
            cents = []
            for o in range(1, n + 1):
                key = f"{fi}_{o}"
                if key not in M:
                    continue
                mk = np.unpackbits(M[key])[: H * W].reshape(H, W).astype(bool)
                if not mk.any():
                    continue
                ov[mk] = 0.5 * ov[mk] + 0.5 * np.array(COLORS[(o - 1) % len(COLORS)], np.float32)
                ys, xs = np.nonzero(mk)
                cents.append((o, xs.mean(), ys.mean()))
            dc = None
            if DM is not None and str(fi) in DM:
                dk = np.unpackbits(DM[str(fi)])[: H * W].reshape(H, W).astype(bool)
                if dk.any():
                    ov[dk] = 0.35 * ov[dk] + 0.65 * np.array((255, 255, 255), np.float32)
                    inner = dk.copy()
                    inner[1:, :] &= dk[:-1, :]
                    inner[:-1, :] &= dk[1:, :]
                    inner[:, 1:] &= dk[:, :-1]
                    inner[:, :-1] &= dk[:, 1:]
                    edge = dk & ~inner
                    for _ in range(1):  # 테두리 두께 2px
                        e2 = edge.copy()
                        e2[1:, :] |= edge[:-1, :]
                        e2[:, 1:] |= edge[:, :-1]
                        edge = e2 & dk
                    ov[edge] = 0
                    ys, xs = np.nonzero(dk)
                    dc = (xs.mean(), ys.mean())
            img = Image.fromarray(ov.astype(np.uint8))
            dr = ImageDraw.Draw(img)
            seen = {}
            for o, x, y in cents:
                k = (round(x / 14), round(y / 14))
                off = seen.get(k, 0)
                seen[k] = off + 1
                dr.text((x, y - 15 * off), str(o), fill=(255, 255, 255), font=font, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
            if dc is not None:   # D 글자는 숫자와 겹쳐도 보이게 마스크 중심보다 위에
                dr.text((dc[0], dc[1] - 17), "D", fill=(230, 0, 0), font=font, anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255))
            img.save(fd / f"{fi:05d}.jpg", quality=90)
        hc.jsave(fd / "meta.json", {"id": tid, "n": n, "frames": tr["frames"], "shape": [H, W]}, indent=None)
        print(tid, F, "장", f"{W}x{H}", flush=True)


def parts_of(tid: str, types, arm: str = "M"):
    meta = hc.jload(frame_dir(tid, arm) / "meta.json")
    n = meta["n"]
    if arm == "V":
        part = types.Part(inline_data=types.Blob(data=(frame_dir(tid, arm) / "clip.mp4").read_bytes(), mime_type="video/mp4"),
                          video_metadata=types.VideoMetadata(fps=VIDEO_FPS))
        part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
        return [PROMPTS[arm].format(n=n), part, f"{CLOSE[arm]} 차례를 시작할 때 줄은 {n}장이다."]
    ps = [PROMPTS[arm].format(n=n)]
    for i, ms in enumerate(meta["frames"]):
        ps.append(f"프레임 {hc.mss(ms)}")
        part = types.Part.from_bytes(data=(frame_dir(tid, arm) / f"{i:05d}.jpg").read_bytes(), mime_type="image/jpeg")
        part.media_resolution = types.PartMediaResolution(level="MEDIA_RESOLUTION_HIGH")
        ps.append(part)
    ps.append(f"위 프레임을 보고 답하라. 차례를 시작할 때 줄은 {n}장이다.")
    return ps


def cmd_count(a):
    import gemframes as gf
    from google.genai import types
    c = gf.client()
    for arm in (a.arms.split(",") if a.arms else [a.arm]):
        tot = nft = 0
        for tid in ids_of(a):
            r = c.models.count_tokens(model=a.gmodel, contents=parts_of(tid, types, arm))
            nf = len(hc.jload(frame_dir(tid, arm) / "meta.json")["frames"])
            tot += r.total_tokens
            nft += nf
            print(arm, tid, nf, "장", f"{r.total_tokens:,} 토큰 ({r.total_tokens / nf:.0f}/장)", flush=True)
        print(f"[{arm}] 합 {nft:,}장 {tot:,} 토큰 ({tot / nft:.0f}/장) → 1번 읽기 입력 약 {tot * 0.75e-6:.2f}달러", flush=True)


def cmd_run(a):
    import gemframes as gf
    from google.genai import types
    cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=m.GEM_SCHEMA)

    def one(job):
        tid, arm = job if isinstance(job, tuple) else (job, a.arm)
        t0, err = time.perf_counter(), ""
        for attempt in range(3):
            try:
                c = gf.client()
                r = c.models.generate_content(model=a.gmodel, contents=parts_of(tid, types, arm), config=cfg)
                um = r.usage_metadata
                d = json.loads(r.text)
                return {"id": tid, "kind": d.get("kind"), "k": d.get("k"), "j": d.get("j"), "unsure": d.get("unsure"), "why": d.get("why"), "steps": d.get("steps"),
                        "s": round(time.perf_counter() - t0, 1), "in": um.prompt_token_count or 0, "out": um.candidates_token_count or 0,
                        "think": getattr(um, "thoughts_token_count", 0) or 0, "model_version": getattr(r, "model_version", None), "attempt": attempt + 1}
            except Exception as e:  # noqa: BLE001
                err = f"{type(e).__name__}: {e}"[:300]
                time.sleep(8 * (attempt + 1))
        return {"id": tid, "kind": None, "k": None, "j": None, "unsure": True, "error": err, "s": round(time.perf_counter() - t0, 1), "in": 0, "out": 0, "think": 0}

    if a.tag:
        return run_tagged(a, one)
    ids = a.ids.split(",") if a.ids else IDS
    for rep in range(1, a.reps + 1):
        f = m.OUT / f"read_gemimg_{a.arm}_r{rep}.json"
        if f.exists() and not a.force:
            print("있음 — 건너뜀", f.name)
            continue
        with ThreadPoolExecutor(a.workers) as ex:
            rows = list(ex.map(one, ids))
        if a.ids:
            print("(일부 차례만 — 저장 안 함)", [(r["id"], r["kind"], r["k"], r["j"], r.get("unsure"), r.get("error", "")[:80], r["in"], r["think"]) for r in rows])
            return
        hc.jsave(f, {"reader": f"gemimg_{a.arm}_r{rep}", "model": a.gmodel, "at": hc.hms(int(time.time() * 1000), date=True), "rows": rows})
        print(f"gemimg {a.arm} r{rep}: " + " ".join(f"{r['id'][:3]}{r['id'][-2:]}={r['k']}·{r['j']}{'?' if r.get('unsure') else ''}{'!' if r.get('error') else ''}" for r in rows)
              + f" | 입력 {sum(r['in'] for r in rows):,} · 출력 {sum(r['out'] for r in rows):,} · 생각 {sum(r['think'] for r in rows):,}", flush=True)


def tagged_file(tag: str, arm: str, rep: int) -> Path:
    return m.OUT / f"read_gemimg_{tag}_{arm}_r{rep}.json"


def run_tagged(a, one):
    """추가 30: 여러 팔을 한 실행에서 차례마다 번갈아 부르고 팔마다 따로 저장(옛 read_gemimg_{M,N}_r*.json 은 안 건드림)."""
    ids, arms = ids_of(a), a.arms.split(",") if a.arms else [a.arm]
    for rep in range(1, a.reps + 1):
        todo = [arm for arm in arms if a.force or not tagged_file(a.tag, arm, rep).exists()]
        if not todo:
            print("있음 — 건너뜀", a.tag, rep)
            continue
        jobs = [(tid, arm) for tid in ids for arm in todo]
        t0 = hc.hms(int(time.time() * 1000), date=True)
        with ThreadPoolExecutor(a.workers) as ex:
            rows = list(ex.map(one, jobs))
        for arm in todo:
            rr = [dict(r, arm=arm) for (tid, ar), r in zip(jobs, rows) if ar == arm]
            hc.jsave(tagged_file(a.tag, arm, rep), {"reader": f"gemimg_{a.tag}_{arm}_r{rep}", "model": a.gmodel, "at": t0, "arms_together": todo, "rows": rr})
            print(f"{a.tag} {arm} r{rep}: " + " ".join(f"{r['id'][:3]}{r['id'][-3:]}={r['k']}·{r['j']}{'?' if r.get('unsure') else ''}{'!' if r.get('error') else ''}" for r in rr)
                  + f" | 입력 {sum(r['in'] for r in rr):,} · 출력 {sum(r['out'] for r in rr):,} · 생각 {sum(r['think'] for r in rr):,}", flush=True)


def score_tagged(a):
    """추가 30 채점: 팔 · 회마다 맞음 / unsure / 조용한 틀림, 끼움 · 옮김 6 과 끝 붙임 쪽 따로, 팔끼리 갈림으로 거르기."""
    truth = s1.truth_all()
    ids, arms = ids_of(a), a.arms.split(",") if a.arms else ["M", "N", "V"]
    reads = {}
    for arm in arms:
        for rep in (1, 2, 3):
            f = tagged_file(a.tag, arm, rep)
            if f.exists():
                reads[(arm, rep)] = {r["id"]: r for r in hc.jload(f)["rows"]}
    show = lambda v: "-" if v is None else (f"{v['k']}·{v['j']}" if v["kind"] == "hand" else "쯔모")  # noqa: E731
    tot = {k: {"T": 0, "quiet": 0, "unsure": 0, "err": 0, "T_ins": 0, "T_end": 0} for k in reads}
    usage = {k: {"in": 0, "out": 0, "think": 0} for k in reads}
    for tid in ids:
        u = truth[tid]
        cells = []
        for key, rows in reads.items():
            raw = rows.get(tid) or {}
            r = m.norm(raw)
            ok, un = m.right(r, u), bool(raw.get("unsure"))
            t = tot[key]
            t["T"] += ok
            t["quiet"] += (not ok) and not un
            t["unsure"] += un
            t["err"] += bool(raw.get("error"))
            t["T_ins" if tid in INSERT6 else "T_end"] += ok
            for k in usage[key]:
                usage[key][k] += raw.get(k, 0) or 0
            cells.append(f"{key[0]}{key[1]} {show(r)}{'?' if un else ''}{'✓' if ok else '✗'}")
        ans = "쯔모" if u["kind"] != "hand" else f"{u['k_id']}·{u['j_closed']}"
        print(f"{tid:9s}{'끼' if tid in INSERT6 else '  '} 정답 {ans} | " + " | ".join(cells))
    n_ins = sum(t in INSERT6 for t in ids)
    for key, t in tot.items():
        us = usage[key]
        usd = us["in"] * 0.75e-6 + (us["out"] + us["think"]) * 3.75e-6
        print(f"{key[0]} r{key[1]}: 맞음 {t['T']}/{len(ids)} (끼움 {t['T_ins']}/{n_ins} · 끝 붙임 {t['T_end']}/{len(ids) - n_ins}) · unsure {t['unsure']} · 조용한 틀림 {t['quiet']} · 오류 {t['err']}"
              f" | 입력 {us['in']:,} · 출력 {us['out']:,} · 생각 {us['think']:,} → 약 {usd:.2f}달러")
    # 갈림 거르기(조언의 "어려운 차례만 상위 모델로" 를 0달러로 어림): 같은 회의 팔 답이 갈리거나 하나라도 unsure 면 "넘김"
    for rep in (1, 2, 3):
        ks = [k for k in reads if k[1] == rep]
        if len(ks) < 2:
            continue
        for base in [k[0] for k in ks]:
            sent = kept = kept_wrong = sent_wrong = 0
            for tid in ids:
                rs = [reads[k].get(tid) or {} for k in ks]
                ans = {json.dumps(m.norm(r), sort_keys=True) for r in rs}
                flag = len(ans) > 1 or any(r.get("unsure") for r in rs)
                ok = m.right(m.norm(reads[(base, rep)].get(tid)), truth[tid])
                if flag:
                    sent += 1
                    sent_wrong += not ok
                else:
                    kept += 1
                    kept_wrong += not ok
            print(f"r{rep} 팔 {'·'.join(k[0] for k in ks)} 갈림/unsure 넘김 {sent} (그 안 {base} 틀림 {sent_wrong}) · 남김 {kept} (그 안 {base} 틀림 {kept_wrong})")


def cmd_score(a):
    if getattr(a, "tag", None):
        return score_tagged(a)
    truth = s1.truth_all()
    reads = {}
    for arm, nm in (("M", "그림"), ("N", "민")):       # M = 마스크 겹친 프레임, N = 마스크 없는 같은 프레임(대조)
        for rep in (1, 2, 3):
            f = m.OUT / f"read_gemimg_{arm}_r{rep}.json"
            if f.exists():
                reads[f"{nm}{rep}"] = {r["id"]: r for r in hc.jload(f)["rows"]}
    text = {}
    for arm in ("L", "LS", "LS3"):
        for rep in (1, 2):
            f = m.OUT / f"read_gem_{arm}_r{rep}.json"
            if f.exists():
                text[(arm, rep)] = {r["id"]: r for r in hc.jload(f)["rows"]}
    ab = {}
    try:
        import pgraph as pg
        import slotgrid as sg
        for tid in IDS:
            gid = sg.game_of(tid)
            for nm, fn in (("A", pg.load_a), ("B", pg.load_b)):
                try:
                    ab[(nm, tid)] = (fn(gid, False) or {}).get(tid)
                except Exception:  # noqa: BLE001
                    ab[(nm, tid)] = None
    except Exception as e:  # noqa: BLE001
        print("저장된 A · B 답을 못 읽음:", type(e).__name__, str(e)[:120])
    show = lambda v: "-" if v is None else (f"{v['k']}·{v['j']}" if v["kind"] == "hand" else "쯔모")  # noqa: E731
    tot = {rep: {"T": 0, "sure_T": 0, "quiet": 0, "unsure": 0, "err": 0} for rep in reads}
    usage = {"in": 0, "out": 0, "think": 0}
    tt = {k: 0 for k in text}
    tab = {"A": 0, "B": 0}
    for tid in IDS:
        u = truth[tid]
        cells = []
        for rep, rows in reads.items():
            raw = rows.get(tid) or {}
            r = m.norm(raw)
            ok, un = m.right(r, u), bool(raw.get("unsure"))
            t = tot[rep]
            t["T"] += ok
            t["sure_T"] += ok and not un
            t["quiet"] += (not ok) and not un
            t["unsure"] += un
            t["err"] += bool(raw.get("error"))
            for k in usage:
                usage[k] += raw.get(k, 0) or 0
            cells.append(f"{rep} {show(r)}{'?' if un else ''}{'✓' if ok else '✗'}")
        tx = []
        for k, rows in text.items():
            ok = m.right(m.norm(rows.get(tid)), u)
            tt[k] += ok
            tx.append(f"{k[0]}{k[1]}{'✓' if ok else '✗'}")
        sb = []
        for nm in ("A", "B"):
            v = m.norm(ab.get((nm, tid)))
            ok = m.right(v, u)
            tab[nm] += ok
            sb.append(f"{nm} {show(v)}{'✓' if ok else '✗'}")
        print(f"{tid:8s} 정답 {u['k_id']}·{u['j_closed']} | " + " | ".join(cells) + " || 글 " + " ".join(tx) + " || 저장 " + " · ".join(sb))
    for rep, t in tot.items():
        print(f"{rep}: 맞음 {t['T']}/8 (unsure 아닌 맞음 {t['sure_T']}) · unsure {t['unsure']} · 조용한 틀림 {t['quiet']} · 오류 {t['err']}")
    for nm in ("그림", "민"):
        ks = [k for k in tot if k.startswith(nm)]
        if ks:
            print(f"{nm} 합: 맞음 {sum(tot[k]['T'] for k in ks)}/{8 * len(ks)} · unsure {sum(tot[k]['unsure'] for k in ks)} · 조용한 틀림 {sum(tot[k]['quiet'] for k in ks)}")
    print("글 팔(표 12-50): " + " · ".join(f"{k[0]} r{k[1]} {v}/8" for k, v in tt.items()) + f" | 저장된 A {tab['A']}/8 · B {tab['B']}/8")
    usd = usage["in"] * 0.75e-6 + (usage["out"] + usage["think"]) * 3.75e-6
    print(f"토큰: 입력 {usage['in']:,} · 출력 {usage['out']:,} · 생각 {usage['think']:,} → 약 {usd:.2f}달러")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("make", "count", "run", "score"):
        q = sp.add_parser(name)
        q.add_argument("--gmodel", default=MODEL)
        q.add_argument("--arm", default="M", choices=["M", "N", "V", "D"], help="M = 마스크 겹친 프레임 · N = 마스크 없는 같은 프레임(대조) · V = 같은 원본 프레임 영상(추가 30) · D = M + 뽑은 패 추적(추가 31)")
        q.add_argument("--ids", help="쉼표 목록 또는 new17(추가 30). 없으면 어려운 8")
        q.add_argument("--tag", help="추가 30 꼴 실행 — 답 파일 read_gemimg_<tag>_<팔>_r<회>.json")
        q.add_argument("--arms", help="쉼표 목록(count · run --tag · score --tag) 예: M,N,V")
        if name == "run":
            q.add_argument("--reps", type=int, default=2)
            q.add_argument("--workers", type=int, default=4)
            q.add_argument("--force", action="store_true")
    a = ap.parse_args()
    {"make": cmd_make, "count": cmd_count, "run": cmd_run, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
