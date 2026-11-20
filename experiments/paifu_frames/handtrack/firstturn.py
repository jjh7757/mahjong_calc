"""1순(판 구간 앞, 줄 정리 중에 버린 첫 차례)을 넣어 처음 받은 패 묶음까지 복원(2026-11-20, 사용자 "넣어서 복원").

r12 · r17 · r19 · r13 은 화료자가 13장 줄 정지(t_ready) 전에 1순을 버려 차례 목록(truthprep)에 없다. 넷 다 친이 아니라(label · meta)
1순에 한 장 뽑고 한 장 버렸다. 손패는 서 있어 위에서 앞면이 안 보이므로 뽑은 패는 자리로 따라간다:
  배패 = 2순 시작 줄(= t_ready 줄) − (1순에 뽑은 패가 그 줄에서 선 칸) + 1순 버린 패, 쯔모기리면 배패 = 2순 시작 줄.

  python -X utf8 firstturn.py prep      # _work/firstturn_1120/<판>/ — 원본 wide 영역(대국자 시점으로 돌림) 프레임 · frames.txt · TASK.md
  python -X utf8 firstturn.py rebuild   # answer.json + rebuild_opus --full 의 2순 시작 줄 → 배패 묶음
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402

ROOT = hc.WORK / "firstturn_1120"
# 판: (1순 버린 패, 버림이 강에 놓인 대략 시각) — 강 영역 시간순 그림으로 확인(11-20). r13 은 config 메모 13:27:15.4 ~ 16.2.
GAMES = {
    "r12_131655": ("4z", "13:17:48.9"),
    "r17_140450": ("9m", "14:04:16.0"),
    "r19_142013": ("4z", "14:21:03.0"),
    "r13_132644": ("2z", "13:27:16.0"),
}
PRE_MS = 20000      # 버림 20초 전부터
POST_MS = 1500      # t_ready 1.5초 뒤까지

TASK = """# 1순에 뽑은 패 따라가기 — {gid}

## 상황
마작 대국을 위에서 찍은 녹화다. 그림은 화료자(이 사람) 쪽 탁자 절반을 이 사람 시점으로 돌린 것이다 — **그림 아래가 이 사람 몸 쪽**, 손패 줄은 아래쪽에 가로로 선다.
손패는 서 있어서 위에서는 **패 뒷면(색 있는 쪽)만 보이고 앞면은 안 보인다.** 그래서 패의 정체가 아니라 **자리(움직임)** 를 따라가야 한다.

이 사람은 친이 아니다. 패산에서 13장을 가져와(4 · 4 · 4 · 1장) 줄을 세우는 동안 차례가 와서, **패산에서 1장을 뽑고(14장) 1장을 강(그림 위쪽 펠트)에 앞면으로 버렸다.** 버린 패는 그림 위쪽에 앞면이 보이는 패({tile_name})로, 대략 {t_disc} 쯤 강에 놓인다.
그 뒤 손으로 패를 옮기며 줄을 정리하고, **{t_ready} 프레임에서 13장 줄이 정지**한다(폴더의 마지막 프레임은 그 1.5초 뒤 — 그사이 2순이 시작될 수 있으니 끝 줄은 {t_ready} 프레임으로 센다). 이 마지막 줄을 "끝 줄" 이라 하고, 이 사람 시점 **왼쪽부터 1 ~ 13** 으로 번호를 붙인다.

## 물음
1. 1순에 **뽑은 패(D)** 는 어느 순간 패산에서 손으로 들어왔나(프레임 시각).
2. **버린 패는 D 자체였나(쯔모기리), 아니면 원래 손에 있던 13장 중 하나였나?**
3. 쯔모기리가 아니면, D 는 그 뒤 줄 정리를 거쳐 **끝 줄의 몇 번째 칸**(1 ~ 13)에 서 있나. 정리 중 D 를 다른 패와 섞어 옮겼다면 끝까지 따라가라.

## 재료(이 폴더 안만)
- `frames.txt`: 프레임 목록(시각 · 파일 이름). 프레임은 초당 약 10장, `raw/` 에 원본 화소 그대로(돌리기만 함).
- 처음 프레임은 버림 약 20초 전, 마지막 프레임은 끝 줄 정지 뒤다. 뽑기가 처음 프레임보다 앞이라 안 보이면 그렇게 적어라.
- 다른 사람 손 · 팔이 들어오기도 한다. 이 사람 손은 그림 아래(몸 쪽)에서 들어온다.

## 하는 법
- 그림은 Read 로 연다. 확대 · 여러 장 묶어 보기가 필요하면 Bash 에서 `python -X utf8` 로 PIL 을 써서 `work/` 에만 저장한다(여러 줄 코드는 work/ 에 .py 파일로 써서 돌려라).
- 패 장수를 순간마다 세어 앞뒤가 맞는지 확인하라(뽑기 전 13, 뽑은 뒤 14, 버린 뒤 13). 손에 들린 패 · 손가락 밑 패도 센다.
- 확신이 없으면 그렇다고 적는다. 그럴듯한 이야기로 채우지 말 것.

## 답
같은 폴더에 `answer.json` 하나만 쓴다:
```json
{{"draw_time": "hh:mm:ss.s 또는 null", "tsumogiri": true/false/null, "drawn_slot": 1~13 또는 null,
  "discard_from": "D 또는 원래 줄의 어디(예: 가운데 묶음 오른쪽 끝)", "unsure": true/false,
  "candidates": [가능한 칸들(확신 없을 때)], "evidence": ["시각: 본 것", ...]}}
```
"""

TILE_NAME = {"4z": "북(北)", "9m": "9만(九萬)", "2z": "남(南)"}


def prep():
    for gid, (tile, t_disc) in GAMES.items():
        c = hc.config(gid)
        d = ROOT / gid
        (d / "raw").mkdir(parents=True, exist_ok=True)
        (d / "work").mkdir(exist_ok=True)
        t0 = hc.to_ms(t_disc) - PRE_MS
        t1 = hc.to_ms(c["t_ready"]) + POST_MS
        fr, seen = [], set()
        for m in hc.frame_range(t0, t1):     # 11-20: 파일 이름이 0.1초 단위라 같은 0.1초 두 장을 두 스레드가 같은 파일에 써 깨졌음(r13 3장) → 0.1초에 한 장
            if hc.hms(m) not in seen:
                seen.add(hc.hms(m))
                fr.append(m)

        def one(m):
            p = d / "raw" / f"{hc.hms(m).replace(':', '')}.jpg"
            try:
                Image.open(p).load()
                return p.name
            except Exception:
                pass
            if True:
                Image.fromarray(hc.band_crop(hc.load(m), c["wide"], c["side"])).save(p, quality=92)
            return p.name

        with ThreadPoolExecutor(8) as ex:
            names = list(ex.map(one, fr))
        (d / "frames.txt").write_text("\n".join(f"{hc.hms(m)} raw/{n}" for m, n in zip(fr, names)) + "\n", encoding="utf-8", newline="\n")
        (d / "TASK.md").write_text(TASK.format(gid=gid, tile_name=TILE_NAME[tile], t_disc=t_disc, t_ready=c["t_ready"]),
                                   encoding="utf-8", newline="\n")
        print(gid, len(fr), "프레임", hc.hms(fr[0]), "~", hc.hms(fr[-1]))


def rebuild():
    import rebuild_opus as ro
    rows = []
    uc = ROOT / "user_confirm.json"              # 11-20 사용자가 영상을 보고 정한 칸(unsure 였던 r19 · r13)
    ucd = hc.jload(uc) if uc.exists() else {}
    for gid, (tile, _) in GAMES.items():
        # 11-20 사용자 "안 끼움": r17 8순에 5 · 6번 맞바꿈 없음 → 2순 시작 줄은 정답 쪽(Opus 는 맞바꿈으로 읽어 4 · 5칸이 뒤집힘)
        src = ucd.get("row_src", {}).get(gid, "full")
        recs, _ = ro.rebuild(gid, src)
        first = recs[0]                      # 2순(판 구간 첫 차례)
        row = list(first["before"])
        a = hc.jload(ROOT / gid / "answer.json")
        if gid in ucd:
            a = {**a, "drawn_slot": ucd[gid], "unsure": False, "candidates": [ucd[gid]], "confirmed_by": "사용자"}
        if a.get("tsumogiri"):
            haipai, drawn = list(row), tile
        elif a.get("drawn_slot"):
            s = int(a["drawn_slot"])
            drawn = row[s - 1]
            haipai = row[:s - 1] + row[s:] + [tile]
        else:
            haipai, drawn = None, None
        cands = None
        if a.get("candidates"):
            cands = sorted({row[int(s) - 1] for s in a["candidates"] if str(s).isdigit()})
        rows.append({"game": gid, "turn2_start": row, "turn2_src": src, "discard1": tile, "answer": a, "drawn1": drawn,
                     "haipai": sorted(haipai, key=lambda t: ("mpsz".index(t[1]), t[0])) if haipai else None, "drawn_candidates": cands})
        print(f"== {gid} 2순 시작 줄 {' '.join(row)} | 1순 버림 {tile}")
        print(f"   쯔모기리 {a.get('tsumogiri')} · 뽑은 칸 {a.get('drawn_slot')} → 뽑은 패 {drawn} · unsure {a.get('unsure')} · 후보 {cands}")
        if haipai:
            print(f"   배패 13장: {' '.join(rows[-1]['haipai'])}  (묶음 {dict(Counter(haipai))})")
    hc.jsave(ROOT / "haipai.json", rows)


# 사용자 확인용(11-20 "그림 보고 내가 정함"): 하위 에이전트가 두 장 덩어리 순서를 못 본 구간.
# (영상 창, 촘촘한 묶음 창, 자를 영역 [x0, y0, x1, y1] — prep 의 돌린 그림 좌표)
REVIEW = {
    "r19_142013": ("14:20:52.5", "14:21:11.0", "14:20:59.8", "14:21:03.2", [480, 380, 1300, 760]),
    "r13_132644": ("13:27:10.0", "13:27:39.0", "13:27:26.5", "13:27:30.3", [420, 420, 1300, 760]),
    # r17 8순: Opus 는 원래 5 · 6번 패 맞바꿈(2순 시작 줄 0s 4s), 정답 메모는 맞바꿈 없음(4s 0s) — 뽑은 패 0s / 4s 가 여기서 갈림
    "r17_d08": ("14:07:28.5", "14:08:02.0", "14:07:54.5", "14:08:00.0", [350, 420, 1300, 760]),
    # 11-20 다시 묻기(reask.py): 다시 읽어도 Opus 쪽(6번 패를 5번 앞으로) — 정답 메모(사용자 11-16)엔 이 옮김이 없음
    "r16_d13": ("13:59:04.0", "13:59:12.0", "13:59:06.6", "13:59:08.4", [350, 420, 1300, 760]),
}


def review():
    import cv2
    import numpy as np
    import sys as _s
    names = _s.argv[2:] or list(REVIEW)
    for gid in names:
        v0, v1, s0, s1, box = REVIEW[gid]
        game = next(g for g in [*GAMES, "r17_140450", "r16_135321"] if g.startswith(gid[:3]))
        c = hc.config(game)
        d = ROOT / gid
        out = d / "review"
        out.mkdir(parents=True, exist_ok=True)
        # 11-20: 녹화에서 바로(prep 폴더와 같은 wide 영역 · 같은 돌림), 0.1초에 한 장
        lines, seen = [], set()
        for m in hc.frame_range(hc.to_ms(v0), hc.to_ms(v1)):
            if hc.hms(m) not in seen:
                seen.add(hc.hms(m))
                lines.append((hc.hms(m), m))

        def crop(t, m, scale):
            im = Image.fromarray(hc.band_crop(hc.load(m), c["wide"], c["side"])).crop(box)
            im = im.resize((int(im.width * scale), int(im.height * scale)))
            dr = ImageDraw.Draw(im)
            dr.rectangle([0, 0, 150, 26], fill=(0, 0, 0))
            dr.text((6, 6), t, fill=(255, 255, 0), font_size=18)
            return im

        sel = [(t, f) for t, f in lines if v0 <= t <= v1]
        w, h = crop(*sel[0], 1.5).size
        vw = cv2.VideoWriter(str(out / f"{gid}_slow4x.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 2.5, (w, h))   # 초당 10장 → 2.5장 = 4배 느리게
        for t, f in sel:
            vw.write(cv2.cvtColor(np.asarray(crop(t, f, 1.5)), cv2.COLOR_RGB2BGR))
        vw.release()
        import subprocess                            # mp4v 는 브라우저 · 앱 창에서 안 열려 H.264 로 다시
        import imageio_ffmpeg
        tmp = out / f"{gid}_slow4x.mp4"
        h264 = out / f"{gid}_slow4x_h264.mp4"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(tmp), "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-crf", "20", str(h264)], check=True)
        h264.replace(tmp)
        crit = [(t, f) for t, f in lines if s0 <= t <= s1]
        tiles = [crop(t, f, 1.0) for t, f in crit]
        cols = 3
        tw, th = tiles[0].size
        for k in range(0, len(tiles), 12):          # 12장(4줄 × 3)씩 한 장
            part = tiles[k:k + 12]
            sh = Image.new("RGB", (tw * cols, th * ((len(part) + cols - 1) // cols)), (30, 30, 30))
            for i, im in enumerate(part):
                sh.paste(im, ((i % cols) * tw, (i // cols) * th))
            sh.save(out / f"{gid}_sheet{k // 12 + 1}.jpg", quality=90)
        print(gid, "영상", len(sel), "장", "· 묶음", len(crit), "장 →", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "rebuild", "review"])
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    {"prep": prep, "rebuild": rebuild, "review": review}[a.cmd]()


if __name__ == "__main__":
    main()
