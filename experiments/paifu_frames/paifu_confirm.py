"""대국 뒤 자동 패보 — 확인 페이지 하나(설계서 docs/paifu_auto_agent_design_1124.md 8-17 4-②, 2026-11-25 밤). 내 컴퓨터 안에서만(127.0.0.1).

  python -X utf8 experiments/paifu_frames/paifu_confirm.py prep  --run <실행 폴더> [--questions <파일>] [--out <폴더>] [--force]
  python -X utf8 experiments/paifu_frames/paifu_confirm.py serve --run <실행 폴더> [포트 8315] [--ans <답 파일>] [--questions <파일>] [--out <폴더>]
  python -X utf8 experiments/paifu_frames/paifu_confirm.py show  --run <실행 폴더> [--ans <답 파일>] [--questions <파일>]
(저장소 루트에서. 실행 폴더 = paifu_auto.py 의 실행 폴더 — 읽기만, 쓰는 곳은 <실행>/confirm/ 과 답 파일 둘뿐.)

볼 것 = 실행 폴더의 questions.jsonl(먼저) + samples.jsonl(파일 순서). --questions = 시험용 질문 줄 파일(jsonl · json 목록)로 바꿈.
묶음은 paifu_auto.Q_FORMS(질문 id 꼴 표 하나 — apply 와 같은 표)로 가른다:
  A 가린 확인 — 차례 칸(질문 · 표본) = 칸 정답 입력 화면(handtrack/truthpage.html 을 고치지 않고 han3_truthserver.PAGE_PATCH 로 글만 바꿔 보냄,
                길 /turns.json · /answers · /save · /f/<판>/<ms>.jpg). 그림 = read/<차례>/frames.txt 창 1초 앞부터 초당 10장, 판별 설정 sheet_band(없으면 band)
                + 90px 를 그 사람 시점으로 잘라 2배(han3_truthserver.prep 과 같은 셈 — 그 파일의 전역 값은 3반장 설정에 묶여 있어 셈을 옮김).
                판별 설정 길 = 실행 설정 handtrack 칸이 있으면 실행 폴더 handtrack/(ht_redirect), 없으면 공용 자리.
              — 뒷도라(패 34종 + 안 깠다 + 모르겠다) · 해저(예 · 아니오 · 모르겠다) · 강 한 칸 패 종류(패 34종 + 모르겠다) = 새 화면 "그 밖".
                브라우저에는 id · 판 · 자리 · 몇 번째 · 영상 · 코드가 만든 물음 글만(current · candidates · why · impact 는 안 보냄).
  B 후보 고르기 — 지금 값 + 후보를 섞어 정해진 순서로(어느 것이 지금 값인지 안 보임) + 모르겠다 + 메모. why 는 안 보냄.
  C 알림 — 흐름이 걸린 사실(why)을 그대로 보이고 확인함 · 문제 있음 · 모르겠다 + 메모.
근거 영상(차례 칸 말고, clip 칸이 있는 줄만) = <실행>/confirm/<id>.mp4 — clip t0 ~ t1 의 헤드 녹화 초당 10장 전부 · 출력 5fps(2배 느리게) ·
  탁자 전체를 줄이지 않음 · 위 글씨 띠 = id · 시각 · 프레임 번호뿐. 강 한 칸은 고친 기록(_prep/rec/<판>/)의 그 칸에 상자가 있으면 3배 확대 칸을 옆에
  (지금 기록기 칸에는 상자가 없어 탁자 전체만). clip 이 없는 줄은 영상을 만들지 않는다(구간을 지어내지 않음).
답 = <실행>/answers_user.json 한 파일(+ 저장마다 answers_log.jsonl 한 줄 · --ans 로 다른 파일을 주면 <이름>_log.jsonl). 차례 칸 답은 페이지 꼴 그대로,
  그 밖은 {"value", "value_name", "note", "bundle", "saved_at"}. 지금 채운 답(읽기 답)은 브라우저로 보내지 않는다. 반영은 paifu_auto.py apply --answers <답 파일>.
prep 은 confirm/ 아래에만 쓴다 — 있는 그림 · 영상은 다시 안 만들고(--force 면 다시), json 은 글이 바뀔 때만 쓴다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "handtrack"))
sys.path.insert(0, str(HERE))
import hanchan_cfg as hcfg  # noqa: E402
import htcommon as hc  # noqa: E402
import ht_redirect  # noqa: E402
import han3_truthserver as h3ts  # noqa: E402  (PAD · PRE_MS · PAGE_PATCH · page_bytes — 파일은 안 고침)
import han3_checkserver as hcs  # noqa: E402  (_font · BAR · GAP · SRC_FPS_OUT · COLORS · H.send · H.send_file(Range) — 파일은 안 고침)
import paifu_auto as pa  # noqa: E402  (Run · Q_FORMS · q_form · b_options · rec_cell_locate)

PORT = 8315
ZOOM = 3          # 강 칸 확대 배수(칸 상자가 있을 때)
ZOOM_PAD = 40     # 칸 상자 둘레 여유(원본 화소)
SIDE_KO = {"bottom": "아래", "right": "오른쪽", "top": "위", "left": "왼쪽"}
C_CHOICES = [("ok", "확인함"), ("problem", "문제 있음"), ("unknown", "모르겠다")]
HAITEI = [("yes", "예, 마지막 패였다"), ("no", "아니오, 패산이 더 남아 있었다"), ("unknown", "모르겠다")]
B_LABEL = {"ev": "울기 · 리치 사건", "w5_cell": "강 칸(앱 · 헤드 녹화 기록이 다름)", "w5_calls": "울기", "w5_riichi": "리치",
           "rec_cell": "강 칸", "app5_tile": "강 칸 패", "app5_pre": "앱 추적 전 버림", "app5_call": "울기 묶음",
           "app5_call_headonly": "헤드 녹화에만 있는 울기", "app5_call_apponly": "앱 기록에만 있는 울기", "app5_headonly": "헤드 녹화에만 있는 버림",
           "app5_apponly": "앱 기록에만 있는 버림", "app5_riichi": "리치 표시", "app5_hero": "손패 주인", "app5_hero_hand": "손패 주인의 공개 손패", "hero": "손패 주인"}
ID_RE = re.compile(r"^[\w.-]{1,80}$")


# ------------------------------------------------------------------ 작은 도구
def jdump(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=1)


def write_if_changed(p: Path, text: str) -> bool:
    b = text.encode("utf-8")
    if p.exists() and p.read_bytes() == b:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    return True


def read_rows(path: Path) -> list:
    """질문 줄 파일: json 목록 · {"questions": [...]} · jsonl(한 줄에 하나)."""
    t = path.read_text(encoding="utf-8").strip()
    if not t:
        return []
    try:
        o = json.loads(t)
    except json.JSONDecodeError:
        return [json.loads(x) for x in t.splitlines() if x.strip()]
    if isinstance(o, list):
        return o
    return o.get("questions", [o]) if isinstance(o, dict) else []


class Ctx:
    """실행 폴더 하나의 확인 자료 자리."""

    def __init__(self, run: str, out: str | None, questions: str | None):
        self.r = pa.Run(Path(run))
        if self.r.state is None:
            raise SystemExit(f"실행 폴더가 아님(state.json 없음): {run}")
        self.cfg = hcfg.load(self.r.cfg_f, check=False)
        self.cfg.apply_recording(hc)
        if self.cfg.ht_dir:   # S6a 판 = 실행 폴더 handtrack/(흐름이 han3 를 부를 때와 같은 길)
            ht_redirect.install(hc, self.cfg.ht_dir, self.cfg.ht_games)
        self.out = Path(out).resolve() if out else self.r.d / "confirm"
        self.qfile = Path(questions).resolve() if questions else None
        self.rows = self.load_rows()

    def load_rows(self) -> list:
        if self.qfile:
            rows = read_rows(self.qfile)
        else:
            rows = pa.jlines(self.r.d / "questions.jsonl") + [{**q, "sample": True} for q in pa.jlines(self.r.d / "samples.jsonl")]
        seen, out = set(), []
        for q in rows:
            if isinstance(q, dict) and q.get("id") and q["id"] not in seen:
                seen.add(q["id"])
                out.append(q)
        return out


# ------------------------------------------------------------------ 차례 칸 그림(han3_truthserver.prep 과 같은 셈)
def turn_window(ctx: Ctx, tid: str, gid: str):
    f = hc.WORK / ctx.cfg.read_root / tid / "frames.txt"
    if not f.exists():
        return None
    ts_ = [re.findall(r"\d\d:\d\d\.\d", ln)[0] for ln in f.read_text(encoding="utf-8").strip().splitlines()]
    ref = hc.to_ms(hc.config(gid)["t_start"])
    return ctx.cfg.ms_near(ts_[0], ref, hc), ctx.cfg.ms_near(ts_[-1], ref, hc)


def prep_turns(ctx: Ctx, tids: list, force: bool) -> tuple:
    from PIL import Image
    cut, meta = {}, {}
    if ctx.cfg.cut_file.exists():
        for g in hc.jload(ctx.cfg.cut_file)["games"]:
            for t in g["turns"]:
                cut[t["id"]] = (g, t)
    if ctx.cfg.turns_file.exists():
        meta = {g["id"]: g for g in hc.jload(ctx.cfg.turns_file)["games"]}
    games, rows, missing = {}, [], {}
    for tid, is_sample in tids:
        gid = ctx.cfg.game_of(tid)
        if gid is None or tid not in cut:
            missing[tid] = "차례 자르기 파일에 없음" if gid else "이 실행 설정의 판이 아님"
            continue
        w = turn_window(ctx, tid, gid)
        if w is None:
            missing[tid] = "read/<차례>/frames.txt 없음"
            continue
        g, t = cut[tid]
        t0, t1 = w
        ms_all = hc.frame_range(t0 - h3ts.PRE_MS, t1)
        pre, own = [m for m in ms_all if m < t0], [m for m in ms_all if m >= t0]
        c = hc.config(gid)
        side = c["side"]
        b = list(c.get("sheet_band") or c["band"])
        b = [max(0, b[0] - h3ts.PAD), max(0, b[1] - h3ts.PAD), min(1496, b[2] + h3ts.PAD), min(1496, b[3] + h3ts.PAD)]
        fdir = ctx.out / "frames" / gid
        fdir.mkdir(parents=True, exist_ok=True)
        made = 0
        for m in ms_all:
            f = fdir / f"{m}.jpg"
            if f.exists() and not force:
                continue
            im = Image.fromarray(hc.band_crop(hc.load(m), b, side))
            im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
            im.save(f, quality=88)
            made += 1
        turn = {"id": tid, "label": t["label"], "repeat": False, "game": gid, "i": t["i"], "tile": t.get("tile"),
                "sideways": t.get("sideways", False), "meld_tiles": t.get("meld_tiles"), "n_calc": t.get("n_calc"),
                "same_seg": 1, "more_after": False, "more_before": False,
                "segs": ([{"seg": 0, "role": "앞", "t0": hc.mss(pre[0]), "frames": pre}] if pre else []) +
                        [{"seg": 1, "role": "버림", "t0": hc.mss(own[0]), "frames": own}],
                "window": [hc.hms(t0), hc.hms(t1)]}
        if gid not in games:
            m0 = meta.get(gid, {})
            games[gid] = {"id": gid, "han": 2, "skip": False, "side": side, "first_i": m0.get("first_i"), "n_frames": 0, "turns": []}
        games[gid]["turns"].append(turn)
        games[gid]["n_frames"] += len(ms_all)
        rows.append({"id": tid, "game": gid, "sample": is_sample, "frames": len(ms_all), "pre": len(pre), "made": made,
                     "first": hc.hms(ms_all[0]), "window": [hc.hms(t0), hc.hms(t1)], "crop": b, "side": side,
                     "config": pa.rel(ht_redirect.remap(hc.CONFIG / f"{gid}.json"))})
    doc = {"games": list(games.values()), "scale": 2,
           "note": f"paifu_confirm.py prep — {ctx.cfg.label} 확인할 차례(질문 먼저 · 표본, han 2 로 적은 것은 페이지 묶음용)"}
    return doc, rows, missing


# ------------------------------------------------------------------ 그 밖(A 고르기 · B · C) 자료
def _clip(q: dict):
    c = q.get("clip") or {}
    return (c.get("t0"), c.get("t1")) if c.get("t0") and c.get("t1") else None


def cell_zone(ctx: Ctx, q: dict, fm: dict):
    """강 한 칸의 상자(원본 좌표) — 고친 기록(_prep/rec/<판>/dart_overlay.json)의 그 칸에 box · bbox · rect 가 있을 때만. 새 검출은 안 함."""
    if fm["form"] not in ("rec_cell", "app5_tile") or not q.get("game"):
        return None, "강 칸 아님"
    g = q["game"]
    try:
        i, why = pa.rec_cell_locate(ctx.r, g, fm["form"], fm["m"]["side"], fm["m"]["pos"])
        if i is None:
            return None, why
        d = pa.jl(ctx.r.prep / "rec" / g / "dart_overlay.json")
        sl = next((x for x in d[fm["m"]["side"]]["slots"] if x.get("i") == i), None)
    except (OSError, KeyError, ValueError) as e:
        return None, f"고친 기록을 못 읽음({type(e).__name__})"
    if sl is None:
        return None, "칸 없음"
    box = next((sl[k] for k in ("box", "bbox", "rect") if isinstance(sl.get(k), list) and len(sl[k]) == 4), None)
    return (box, None) if box else (None, "고친 기록의 칸에 상자 없음")


def ask_text(q: dict, fm: dict) -> str:
    pre = str(q.get("id", ""))[:3]
    side = fm["m"].get("side")
    if fm["form"] == "ura":
        return f"{pre} 판: 화료 뒤 뒷도라 표시패(첫 장)는 무엇인가요? 뒷도라를 까지 않았으면 '뒷도라를 안 깠다' 를 고르세요."
    if fm["form"] == "haitei":
        return f"{pre} 판: 화료한 뽑기가 패산의 마지막 패(해저)였나요?"
    if fm["bundle"] == "A":   # 강 한 칸 패 종류
        where = f"강의 {fm['m'].get('pos')}번째 칸" if fm["form"] == "rec_cell" else f"헤드 녹화 기준 {fm['m'].get('pos')}번째 버림"
        return f"{pre} 판 {SIDE_KO.get(side, side)} 자리 {where} 패는 무엇인가요?"
    if fm["bundle"] == "B":
        what = B_LABEL.get(fm["form"], fm["form"])
        return f"{pre} 판{(' ' + SIDE_KO.get(side, side) + ' 자리') if side else ''} {what}: 아래 가운데 영상과 맞는 것을 고르세요(순서는 뜻 없음)."
    return f"흐름이 확인을 바란 것({fm['form']}{(' · ' + str(q.get('stage'))) if q.get('stage') else ''}): 아래 글을 읽고 확인해 주세요."


def opt_label(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " · ".join(opt_label(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k} {opt_label(x)}" for k, x in v.items())
    return json.dumps(v, ensure_ascii=False)


def public_item(q: dict, fm: dict, video) -> dict:
    """브라우저에 보내는 칸(정해 둔 것만)."""
    it = {"id": q["id"], "bundle": fm["bundle"], "form": fm["form"], "game": q.get("game"), "video": video, "ask": ask_text(q, fm),
          "sample": bool(q.get("sample"))}
    if fm["bundle"] == "A":
        it.update(side=fm["m"].get("side"), nth=fm["m"].get("pos"),
                  choices={"ura": "tile_none_unknown", "haitei": "yesno_unknown"}.get(fm["form"], "tile_unknown"))
    elif fm["bundle"] == "B":
        it["options"] = [{"v": json.dumps(v, ensure_ascii=False, sort_keys=True), "label": opt_label(v)} for v in pa.b_options(q)]
    else:
        it["why"] = q.get("why") or "(흐름이 적은 글 없음)"
    return it


def make_video(ctx: Ctx, qid: str, t0s: str, t1s: str, zone, force: bool) -> dict:
    """clip t0 ~ t1 의 헤드 녹화 초당 10장 전부 → <confirm>/<id>.mp4(출력 5fps · 탁자 전체를 줄이지 않음 · 위 띠 = id · 시각 · 프레임 번호)."""
    import imageio_ffmpeg
    import numpy as np
    from PIL import Image, ImageDraw
    out = ctx.out / f"{qid}.mp4"
    t0, t1 = hc.to_ms(t0s), hc.to_ms(t1s)
    ms_all = hc.frame_range(t0, t1)
    if not ms_all:
        raise ValueError(f"구간 안 프레임 0 ({t0s} ~ {t1s})")
    info = {"file": out.name, "frames": [hc.hms(m) for m in ms_all], "fps": hcs.SRC_FPS_OUT, "t0": t0s, "t1": t1s, "zone": zone}
    if out.exists() and not force:
        info["made"] = False
        return info
    f_bar, f_zone = hcs._font(26), hcs._font(20)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = out.with_suffix(".part.mp4")
    proc = None
    for k, ms in enumerate(ms_all):
        full = Image.fromarray(hc.load(ms))
        W, H = full.size
        z = None
        if zone:
            x0, y0, x1, y1 = [int(v) for v in zone]
            x0, y0, x1, y1 = max(0, x0 - ZOOM_PAD), max(0, y0 - ZOOM_PAD), min(W, x1 + ZOOM_PAD), min(H, y1 + ZOOM_PAD)
            z = full.crop((x0, y0, x1, y1)).resize(((x1 - x0) * ZOOM, (y1 - y0) * ZOOM), Image.LANCZOS)
            if z.height > H:
                z = z.resize((round(z.width * H / z.height), H), Image.LANCZOS)
            ImageDraw.Draw(full).rectangle([x0, y0, x1, y1], outline=hcs.COLORS[0], width=4)
        cw = hcs._even(W + (hcs.GAP + z.width if z else 0))
        canvas = Image.new("RGB", (cw, hcs._even(hcs.BAR + H)), "black")
        canvas.paste(full, (0, hcs.BAR))
        dc = ImageDraw.Draw(canvas)
        if z:
            canvas.paste(z, (W + hcs.GAP, hcs.BAR))
            dc.text((W + hcs.GAP + 6, hcs.BAR + 4), f"×{ZOOM}", fill=hcs.COLORS[0], font=f_zone)
        dc.text((10, 6), f"{qid}   {hc.hms(ms)}   #{k:03d}", fill="yellow", font=f_bar)
        if proc is None:
            info["size"] = list(canvas.size)
            proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                     "-s", f"{canvas.width}x{canvas.height}", "-r", str(hcs.SRC_FPS_OUT), "-i", "-",
                                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
                                     "-movflags", "+faststart", str(tmp)], stdin=subprocess.PIPE)
        proc.stdin.write(np.asarray(canvas).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg 실패: {qid}")
    tmp.replace(out)
    info["made"] = True
    return info


def prep(ctx: Ctx, force: bool = False, quiet: bool = False) -> dict:
    """confirm/ 아래에 차례 칸 그림 · turns.json · 그 밖 영상 · items.json · manifest.json(브라우저로 안 보냄)."""
    t_start = time.time()
    ctx.out.mkdir(parents=True, exist_ok=True)
    old = pa.jl(ctx.out / "manifest.json") if (ctx.out / "manifest.json").exists() else {}
    old_v = {x["id"]: x.get("video") for x in old.get("items") or []}
    turns, items, man_items, made_v = [], [], [], []
    for q in ctx.rows:
        fm = pa.q_form(q)
        if fm["form"] == "turn_slot":
            turns.append((q["id"], bool(q.get("sample"))))
            continue
        video, vnote, zone = None, None, None
        if fm["bundle"] == "A" and fm["form"] in ("rec_cell", "app5_tile"):
            zone, znote = cell_zone(ctx, q, fm)
        else:
            znote = "확대 칸 없음(이 꼴은 탁자 전체만)"
        c = _clip(q)
        if c is None:
            vnote = "영상 없음(clip 칸 없음)"
        elif not ID_RE.match(q["id"]):
            vnote = "영상 없음(id 를 파일 이름으로 못 씀)"
        else:
            try:
                v = make_video(ctx, q["id"], c[0], c[1], zone, force)
                if "size" not in v:
                    v["size"] = (old_v.get(q["id"]) or {}).get("size")
                video = {k: v[k] for k in ("file", "frames", "fps", "size")}
                vnote = "새로 만듦" if v["made"] else "있음"
                if not quiet:
                    f = ctx.out / v["file"]
                    print(f"{q['id']:32s} {c[0]} ~ {c[1]}  {len(v['frames'])}장 → {f.name} {f.stat().st_size // 1024} KB {v.get('size')} {vnote}", flush=True)
            except (KeyError, ValueError, RuntimeError, OSError) as e:
                vnote = f"영상 못 만듦({type(e).__name__}: {e})"
        items.append(public_item(q, fm, video))
        man_items.append({"id": q["id"], "bundle": fm["bundle"], "form": fm["form"], "input": fm["input"], "form_note": fm["note"],
                          "clip": {"t0": c[0], "t1": c[1]} if c else None, "video": video and {k: video[k] for k in ("file", "fps", "size")},
                          "video_frames": len(video["frames"]) if video else 0, "video_note": "영상 있음" if video else vnote,
                          "zone": zone, "zone_note": znote})
        made_v.append(vnote == "새로 만듦")
    tdoc, trows, tmiss = prep_turns(ctx, turns, force)
    made_json = [n for n, txt in (("turns.json", jdump(tdoc)), ("items.json", jdump({"items": items})))
                 if write_if_changed(ctx.out / n, txt)]
    man = {"_note": "paifu_confirm.py prep — 묶음 · 영상 · 그림 목록(브라우저로 안 보냄)", "run": pa.rel(ctx.r.d),
           "questions": pa.rel(ctx.qfile) if ctx.qfile else "questions.jsonl + samples.jsonl",
           "turns": [{k: v for k, v in x.items() if k != "made"} for x in trows], "turns_missing": tmiss, "items": man_items}
    man_txt = jdump(man)
    made_json += ["manifest.json"] if write_if_changed(ctx.out / "manifest.json", man_txt) else []
    made_frames = sum(x["made"] for x in trows)
    made_videos = sum(made_v)
    if not quiet:
        print("차례                판           표본 프레임(앞)  창 시작 ~ 끝              새로 그림")
        for x in trows:
            print(f"{x['id']:18s} {x['game']:12s} {'표본' if x['sample'] else '질문':4s} {x['frames']:4d}({x['pre']:2d})  {x['window'][0]} ~ {x['window'][1]}  {x['made']:4d}")
        for tid, why in tmiss.items():
            print(f"{tid:18s} 그림 없음 — {why}")
        print(f"그 밖 {len(man_items)}: " + " · ".join(f"{b} {sum(1 for x in man_items if x['bundle'] == b)}" for b in "ABC")
              + f" · 영상 {sum(1 for x in man_items if x['video'])}")
        print(f"새로 만든 것: 그림 {made_frames} · 영상 {made_videos} · json {made_json} ({time.time() - t_start:.1f}s) → {ctx.out}")
    return {"made_frames": made_frames, "made_videos": made_videos, "made_json": made_json, "turns": trows, "items": man_items}


# ------------------------------------------------------------------ 답 파일
LOCK = threading.Lock()
S = {"ctx": None, "ans": None, "ans_default": None, "turn_ids": set(), "items": {}, "media": {}}


def log_path(ans: Path) -> Path:
    return ans.parent / ("answers_log.jsonl" if ans == S["ans_default"] else ans.stem + "_log.jsonl")


def load_answers(ans: Path) -> dict:
    if not ans.exists():
        return {}
    try:
        return json.loads(ans.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_answer(aid: str, rec: dict):
    ans = S["ans"]
    with LOCK:
        a = load_answers(ans)
        a[aid] = rec
        ans.parent.mkdir(parents=True, exist_ok=True)
        tmp = ans.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(a, ensure_ascii=False, indent=1))
        tmp.replace(ans)
        with open(log_path(ans), "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"id": aid, **rec}, ensure_ascii=False) + "\n")


def item_value(it: dict, v):
    """그 밖 답 값 검사 → (저장할 값, 이름). 안 맞으면 ValueError."""
    if it["bundle"] == "A":
        ch = it["choices"]
        names = {"unknown": "모르겠다"}
        if ch == "yesno_unknown":
            names.update({k: n for k, n in HAITEI})
        else:
            names.update({t: hcs.TILE_NAME.get(t, t) for t in pa.TILES34})
            if ch == "tile_none_unknown":
                names["none"] = "뒷도라를 안 깠다"
        if v not in names:
            raise ValueError(v)
        return v, names[v]
    if it["bundle"] == "B":
        if v == "unknown":
            return "unknown", "모르겠다"
        o = next((o for o in it["options"] if o["v"] == v), None)
        if o is None:
            raise ValueError(v)
        return json.loads(o["v"]), o["label"]
    names = dict(C_CHOICES)
    if v not in names:
        raise ValueError(v)
    return v, names[v]


# ------------------------------------------------------------------ 페이지
# 두 화면 맨 위의 같은 모양 탭 둘(덧붙임 11-25 밤 — 사용자가 위 작은 글씨 줄을 못 찾아 "탁자 전체 영상이 없는데?").
# 적은 수 / 전체는 페이지를 낼 때 답 파일에서 셈(탭을 눌러 오가면 새로 셈 — 차례 칸 = kind 가 있는 답, 그 밖 = 저장된 답). 색 · 글꼴은 이 조각 안에서 정함
# (두 화면의 CSS 변수 이름이 달라서). 좁은 창에서도 한 줄: 두 탭이 반씩 · 넘치는 글은 … 으로.
TABS_CSS = """<style>
.cft-tabs{display:flex;flex-wrap:nowrap;gap:8px;padding:10px 16px 0;margin:0 0 10px;border-bottom:2px solid #8a8a84;font:16px/1.3 "Malgun Gothic","Apple SD Gothic Neo",sans-serif}
.cft-tab{flex:1 1 0;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center;padding:10px 12px;border:2px solid #8a8a84;border-bottom:none;
 border-radius:10px 10px 0 0;background:#e9e8e3;color:#1d1d1b;text-decoration:none;font-weight:600;margin-bottom:-2px}
a.cft-tab:hover{background:#dcebe5}
.cft-tab.cft-on{background:#1f6f5c;border-color:#1f6f5c;color:#fff}
.cft-tab.cft-off{opacity:.5}
.cft-tab small{font-weight:400;opacity:.85}
@media (prefers-color-scheme: dark){.cft-tabs{border-bottom-color:#555}.cft-tab{background:#2a2c31;color:#e8e8e4;border-color:#555}a.cft-tab:hover{background:#1f332e}
 .cft-tab.cft-on{background:#57b79f;border-color:#57b79f;color:#111}}
@media (max-width:520px){.cft-tabs{font-size:13px;padding:8px 8px 0;gap:4px}.cft-tab{padding:8px 6px}}
</style>"""


def tab_counts() -> tuple:
    with LOCK:
        a = load_answers(S["ans"]) if S["ans"] else {}
    nt = sum(1 for k in S["turn_ids"] if isinstance(a.get(k), dict) and a[k].get("kind"))
    no = sum(1 for k in S["items"] if k in a)
    return nt, no


def nav_html(here: str) -> str:
    nt, no = len(S["turn_ids"]), len(S["items"])
    dt, do = tab_counts()

    def tab(key, href, label, done, tot):
        txt = f'{label} <small>{done}/{tot}</small>'
        if key == here:
            return f'<span class="cft-tab cft-on" aria-current="page">{txt}</span>'
        if not tot:
            return f'<span class="cft-tab cft-off">{txt}</span>'
        return f'<a class="cft-tab" href="{href}">{txt}</a>'
    return (TABS_CSS + '<div class="cft-tabs" role="tablist">' + tab("turns", "/turns", "손패 칸", dt, nt)
            + tab("other", "/other", "그 밖(해저 · 뒷도라 · 강의 패)", do, no) + "</div>")


def turns_page() -> bytes:
    """차례 칸 화면 = truthpage.html 을 고치지 않고 보낼 때 맨 위(<body> 바로 뒤)에 탭을 끼움(PAGE_PATCH 넷은 han3_truthserver 것 그대로)."""
    html = h3ts.page_bytes().decode("utf-8")
    key = "<body>"
    if html.count(key) != 1:
        raise RuntimeError("truthpage.html 에서 <body> 가 한 번이 아님")
    return html.replace(key, key + nav_html("turns"), 1).encode("utf-8")


OTHER_PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f6f3;--fg:#1d1d1b;--muted:#666;--card:#fff;--line:#d8d8d2;--acc:#1f6feb;--ok:#1a7f37;--sel:#ffd84d}
@media (prefers-color-scheme: dark){:root{--bg:#16171a;--fg:#e8e8e4;--muted:#a0a0a0;--card:#202227;--line:#3a3c42;--acc:#5a9cff;--ok:#3fb950;--sel:#9a7b00}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 "Malgun Gothic","Apple SD Gothic Neo",sans-serif}
a{color:var(--acc)}
.wrap{display:flex;gap:16px;padding:12px 16px;max-width:1900px;margin:0 auto}
nav{flex:0 0 250px}
nav h1{font-size:17px;margin:4px 0 10px}
nav h2{font-size:13px;color:var(--muted);margin:12px 0 6px}
nav ol{list-style:none;padding:0;margin:0}
nav li{padding:6px 9px;border:1px solid var(--line);border-radius:8px;margin-bottom:5px;cursor:pointer;background:var(--card);font-size:13px;word-break:break-all}
nav li.cur{border-color:var(--acc);box-shadow:0 0 0 2px var(--acc) inset}
nav li .ck{color:var(--ok);font-weight:bold;margin-left:4px}
nav .hint{color:var(--muted);font-size:13px;margin-top:10px}
main{flex:1;min-width:0}
h2#title{font-size:19px;margin:4px 0 8px}
.ask{font-weight:bold;margin:6px 0}
.why{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:6px 0}
#vbox{overflow:auto;max-height:78vh;background:#000;border-radius:6px;margin-top:8px}
#vbox.zoomed{cursor:grab}
#vbox.dragging{cursor:grabbing;user-select:none}
#vbox video{width:100%;max-height:78vh;background:#000;display:block}
#vbox.zoomed video{max-width:none;max-height:none}
#seek{flex:1 1 240px;min-width:160px}
.zhint{margin:8px 0 0;padding:6px 10px;border-left:4px solid var(--acc);background:var(--card);font-size:14px}
nav li small{display:block;color:var(--muted);font-size:11px}
.novid{color:var(--muted);margin:8px 0}
.ctl{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0}
button{font:inherit;padding:6px 12px;border-radius:7px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--acc)}
button.on{background:var(--sel);color:#000;border-color:#b89400}
.now{color:var(--muted);margin-left:8px;font-variant-numeric:tabular-nums}
.ans{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:12px}
.tiles{display:grid;grid-template-columns:70px repeat(9,minmax(44px,1fr));gap:5px;align-items:center;max-width:720px}
.tiles .lab{color:var(--muted)}
.tiles button{padding:6px 0}
.extra{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.opts{display:flex;flex-direction:column;gap:6px;align-items:flex-start}
textarea{width:100%;min-height:64px;font:inherit;margin-top:10px;padding:6px;border-radius:7px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
.save{display:flex;gap:10px;align-items:center;margin-top:8px}
.save button{background:var(--acc);color:#fff;border-color:var(--acc);padding:8px 22px}
.msg{color:var(--muted)}
.nav2{display:flex;gap:8px;margin-top:14px}
@media (max-width:800px){.wrap{flex-direction:column}nav{flex:none}.tiles{grid-template-columns:52px repeat(9,1fr)}}
</style></head><body>__NAV__
<div class="wrap">
<nav><h1>__HEADING__</h1><div id="list"></div>
<div class="hint">영상은 실제보다 2배 느리게 만들었습니다(초당 10장 전부). 위 노란 글씨가 그날 시각과 프레임 번호입니다.
흐름이 지금 가진 값은 보여 주지 않습니다(고르기 묶음은 지금 값과 후보를 섞어 정해진 순서로).</div></nav>
<main>
<h2 id="title"></h2>
<div class="ask" id="ask"></div>
<div id="why"></div>
<div class="zhint" id="zhint">탁자 전체 영상입니다 — 아래 <b>확대</b> 단추(2배 · 3배 · 원본 크기)로 키워 보고, 키운 영상은 마우스로 끌어 볼 곳을 옮깁니다.</div>
<div id="vbox"><video id="vid" controls loop muted playsinline preload="auto"></video></div>
<div class="novid" id="novid"></div>
<div class="ctl" id="ctl">
 <button id="play">재생</button>
 <input id="seek" type="range" min="0" max="0" value="0" step="1" title="구간(프레임)">
 <span style="width:12px"></span>
 <span>확대</span>
 <button data-zoom="fit">맞춤</button><button data-zoom="2">2배</button><button data-zoom="3">3배</button><button data-zoom="orig">원본 크기</button>
 <span class="now" id="zinfo"></span>
</div>
<div class="ctl" id="ctl2">
 <span>빠르기</span>
 <button data-rate="0.25">0.25배</button><button data-rate="0.5">0.5배</button><button data-rate="1">1배</button>
 <span style="width:12px"></span>
 <button id="prevf">◀ 한 프레임</button><button id="nextf">한 프레임 ▶</button>
 <span class="now" id="now"></span>
</div>
<div class="ans" id="ans"></div>
<div class="nav2"><button id="prev">← 이전 항목</button><button id="next">다음 항목 →</button></div>
</main></div>
<script>
const GROUPS = [["A","가린 확인"],["B","후보 고르기"],["C","알림 — 흐름이 걸린 사실"]];
const SUITS = [["m","만"],["p","통"],["s","삭"]];
const HONORS = [["1z","동"],["2z","남"],["3z","서"],["4z","북"],["5z","백"],["6z","발"],["7z","중"]];
const HAITEI = [["yes","예, 마지막 패였다"],["no","아니오, 패산이 더 남아 있었다"],["unknown","모르겠다"]];
const CCH = [["ok","확인함"],["problem","문제 있음"],["unknown","모르겠다"]];
let ITEMS = [], ANSWERS = {}, cur = 0, pick = null, rate = 1;
const $ = s => document.querySelector(s);
const vid = $("#vid");
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
// 목록 글(사람이 읽는 말) — 이미 보내는 form · game · side · nth 로만 지음(보내는 칸은 안 늘림)
const SIDE_KO = {bottom:"아래", right:"오른쪽", top:"위", left:"왼쪽"};
const FORM_KO = {ura:"뒷도라", haitei:"해저", rec_cell:"강 칸", app5_tile:"강 칸 패", ev:"울기 · 리치 사건", w5_cell:"강 칸(앱 · 헤드 다름)", w5_calls:"울기",
  w5_riichi:"리치", app5_pre:"앱 추적 전 버림", app5_call:"울기 묶음", app5_call_headonly:"헤드 녹화에만 있는 울기", app5_call_apponly:"앱 기록에만 있는 울기",
  app5_headonly:"헤드 녹화에만 있는 버림", app5_apponly:"앱 기록에만 있는 버림", app5_riichi:"리치 표시", app5_hero:"손패 주인", app5_hero_hand:"손패 주인 공개 손패",
  hero:"손패 주인", app_warn:"앱 기록 경고", app_games:"앱 판 목록", game_app_warn:"앱 기록 경고", s1_rounds:"판 경계", s1_order:"판 순서",
  s1_track_window:"판 구간(추적 창)", s1_gap:"녹화 끊김", s1_outside:"녹화 밖", s1_reveal:"공개 시각", app_bottom:"아래 자리", app_start:"판 시작",
  app_clock:"시계 차", dealer:"선", s5_app_bottom:"아래 자리", app5_round:"국 · 본장", app5_head_primary:"헤드 녹화 기록을 씀", app5_uncertain:"탁자 기록 불확실",
  app5_chk:"탁자 기록 검사", s6a:"손 추적 준비", s6_turns:"차례 수", reveal:"공개 손패", result:"판 결과", unknown_form:"확인할 것"};
function itemLabel(it){
  const pre = it.game ? it.game.slice(0,3) + " 판 " : "";
  const side = it.side ? (SIDE_KO[it.side] || it.side) + " 자리 " : "";
  if (it.form === "rec_cell" && it.bundle === "A") return `${pre}${side}강 ${it.nth}번째`;
  if (it.form === "app5_tile" && it.bundle === "A") return `${pre}${side}${it.nth}번째 버림 패`;
  return `${pre}${FORM_KO[it.form] || it.form}`;
}
function drawList(){
  let h = "";
  for (const [b, label] of GROUPS) {
    const xs = ITEMS.map((it,i)=>[it,i]).filter(([it])=>it.bundle===b);
    if (!xs.length) continue;
    h += `<h2>${b} ${esc(label)} · ${xs.filter(([it])=>ANSWERS[it.id]).length}/${xs.length}</h2><ol>`;
    for (const [it,i] of xs) h += `<li class="${i===cur?'cur':''}" data-i="${i}">${esc(itemLabel(it))}${ANSWERS[it.id]?'<span class="ck">✓</span>':''}<small>${esc(it.id)}</small></li>`;
    h += `</ol>`;
  }
  $("#list").innerHTML = h || "<div class='hint'>확인할 것이 없습니다.</div>";
  document.querySelectorAll("#list li").forEach(li=>li.onclick=()=>show(+li.dataset.i));
}
function btn(v,label){return `<button data-v="${esc(v)}" class="${pick===v?'on':''}">${esc(label)}</button>`}
function drawAns(){
  const it = ITEMS[cur]; let h = "";
  if (it.bundle === "A" && it.choices !== "yesno_unknown") {
    h += `<div class="tiles">`;
    for (const [s,n] of SUITS){ h += `<span class="lab">${n}</span>`; for(let i=1;i<=9;i++) h += btn(i+s, i+n); }
    h += `<span class="lab">자패</span>` + HONORS.map(([v,n])=>btn(v,n)).join("") + `</div><div class="extra">`;
    if (it.choices === "tile_none_unknown") h += btn("none","뒷도라를 안 깠다");
    h += btn("unknown", it.choices === "tile_none_unknown" ? "영상으로는 모르겠다" : "모르겠다") + `</div>`;
  } else if (it.bundle === "A") {
    h += `<div class="extra">` + HAITEI.map(([v,n])=>btn(v,n)).join("") + `</div>`;
  } else if (it.bundle === "B") {
    h += `<div class="opts">` + it.options.map(o=>btn(o.v,o.label)).join("") + btn("unknown","모르겠다") + `</div>`;
  } else {
    h += `<div class="extra">` + CCH.map(([v,n])=>btn(v,n)).join("") + `</div>`;
  }
  const a = ANSWERS[it.id] || {};
  h += `<textarea id="note" placeholder="메모(본 것 · 기억나는 것 · 확신 정도 등, 비워도 됩니다)">${esc(a.note||"")}</textarea>`;
  h += `<div class="save"><button id="save">저장</button><span class="msg" id="msg">${a.saved_at?('저장됨 '+esc(a.saved_at)+' — '+esc(a.value_name||'')):'아직 저장 안 함'}</span></div>`;
  $("#ans").innerHTML = h;
  document.querySelectorAll("#ans button[data-v]").forEach(b=>b.onclick=()=>{pick=b.dataset.v; const n=$("#note").value; drawAns(); $("#note").value=n;});
  $("#save").onclick = save;
}
function keyOf(it, a){ if(!a) return null; if(it.bundle!=="B") return a.value ?? null; if(a.value==="unknown") return "unknown";
  const o = it.options.find(o=>o.label===a.value_name); return o ? o.v : null; }
function show(i){
  if (!ITEMS.length) return;
  cur = i; const it = ITEMS[i];
  $("#title").textContent = itemLabel(it) + ` (${it.id})` + (it.sample ? " · 표본" : "");
  $("#ask").textContent = it.ask;
  $("#why").innerHTML = it.bundle === "C" ? `<div class="why">${esc(it.why)}</div>` : "";
  setZoom("fit");   // 항목을 바꾸면 맞춤으로(같은 항목 안에서는 확대 · 보던 곳이 재생 · 한 프레임 넘기기에도 남음)
  $("#zhint").style.display = it.video ? "" : "none";
  if (it.video) { vbox.style.display = ""; $("#ctl").style.display = ""; $("#ctl2").style.display = ""; $("#novid").textContent = ""; vid.src = "/media/" + encodeURIComponent(it.video.file); vid.playbackRate = rate;
    seek.max = it.video.frames.length - 1; seek.value = 0; }
  else { vid.removeAttribute("src"); vid.load(); vbox.style.display = "none"; $("#ctl").style.display = "none"; $("#ctl2").style.display = "none"; $("#novid").textContent = "영상 없음(흐름이 이 줄에 구간을 적지 않음)"; }
  pick = keyOf(it, ANSWERS[it.id]);
  drawList(); drawAns(); tick();
  $("#prev").disabled = i===0; $("#next").disabled = i===ITEMS.length-1;
}
function fps(){const v=ITEMS[cur]&&ITEMS[cur].video; return (v&&v.fps)||5}
function tick(){
  const v = ITEMS[cur] && ITEMS[cur].video; if(!v) { $("#now").textContent = ""; return; }
  const k = Math.min(v.frames.length-1, Math.max(0, Math.floor(vid.currentTime*fps()+1e-3)));
  $("#now").textContent = `#${String(k).padStart(3,"0")}  ${v.frames[k]||""}  (${v.frames.length}장)`;
  if (!seeking) seek.value = k;
}
vid.addEventListener("timeupdate", tick); vid.addEventListener("seeked", tick);
vid.addEventListener("loadedmetadata", ()=>{vid.playbackRate = rate; if (zoom !== "fit") setZoom(zoom);});
// 영상 밖 재생 · 구간(키운 영상에서는 브라우저 기본 조작 줄이 아래로 밀려 안 보이므로)
const vbox = $("#vbox"), seek = $("#seek");
let seeking = false, zoom = "fit", drag = null;
function playLabel(){ $("#play").textContent = vid.paused ? "재생" : "멈춤"; }
vid.addEventListener("play", playLabel); vid.addEventListener("pause", playLabel);
$("#play").onclick = ()=>{ if (vid.paused) vid.play(); else vid.pause(); };
seek.addEventListener("input", ()=>{ seeking = true; vid.currentTime = (+seek.value + 0.5) / fps(); });
seek.addEventListener("change", ()=>{ seeking = false; });
// 확대: 맞춤(칸 폭에 맞춤) · 2배 · 3배(맞춤 폭의 배수) · 원본 크기(영상 화소 그대로). 키우면 칸 안에서 스크롤 · 끌기로 볼 곳을 옮김.
function setZoom(z){
  const cx = vid.clientWidth ? (vbox.scrollLeft + vbox.clientWidth / 2) / vid.clientWidth : 0.5;
  const cy = vid.clientHeight ? (vbox.scrollTop + vbox.clientHeight / 2) / vid.clientHeight : 0.5;
  zoom = z;
  const fitW = vbox.clientWidth || vid.clientWidth;
  if (z === "fit") { vid.style.width = ""; vbox.classList.remove("zoomed"); vid.controls = true; }
  else {
    const w = z === "orig" ? (vid.videoWidth || fitW) : fitW * +z;
    vid.style.width = Math.round(w) + "px"; vbox.classList.add("zoomed"); vid.controls = false;
  }
  document.querySelectorAll("button[data-zoom]").forEach(x=>x.classList.toggle("on", x.dataset.zoom === z));
  vbox.scrollLeft = cx * vid.clientWidth - vbox.clientWidth / 2;
  vbox.scrollTop = cy * vid.clientHeight - vbox.clientHeight / 2;
  $("#zinfo").textContent = z === "fit" ? "" : `영상 폭 ${vid.clientWidth}px · 끌어서 옮김`;
}
document.querySelectorAll("button[data-zoom]").forEach(b=>b.onclick=()=>setZoom(b.dataset.zoom));
vbox.addEventListener("mousedown", e=>{
  if (zoom === "fit" || e.button !== 0) return;
  drag = {x: e.clientX, y: e.clientY, l: vbox.scrollLeft, t: vbox.scrollTop};
  vbox.classList.add("dragging"); e.preventDefault();
});
window.addEventListener("mousemove", e=>{ if (!drag) return; vbox.scrollLeft = drag.l - (e.clientX - drag.x); vbox.scrollTop = drag.t - (e.clientY - drag.y); });
window.addEventListener("mouseup", ()=>{ if (drag) { drag = null; vbox.classList.remove("dragging"); } });
function step(d){
  const v = ITEMS[cur].video; if(!v) return;
  vid.pause();
  const f = fps(), k = Math.floor(vid.currentTime*f + 1e-3) + d;
  vid.currentTime = (Math.min(v.frames.length-1, Math.max(0,k)) + 0.5) / f;
}
$("#prevf").onclick = ()=>step(-1); $("#nextf").onclick = ()=>step(1);
document.querySelectorAll("button[data-rate]").forEach(b=>b.onclick=()=>{
  rate = +b.dataset.rate; vid.playbackRate = rate;
  document.querySelectorAll("button[data-rate]").forEach(x=>x.classList.toggle("on", x===b));
});
document.querySelector('button[data-rate="1"]').classList.add("on");
$("#prev").onclick = ()=>cur>0 && show(cur-1);
$("#next").onclick = ()=>cur<ITEMS.length-1 && show(cur+1);
document.addEventListener("keydown", e=>{ if(e.target.tagName==="TEXTAREA") return; if(e.key===",") step(-1); else if(e.key===".") step(1); });
async function save(){
  const it = ITEMS[cur];
  if(pick===null){ $("#msg").textContent = "먼저 답을 하나 고르세요"; return; }
  const body = {id: it.id, answer: {value: pick, note: $("#note").value}};
  try{
    const r = await fetch("/save", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
    if(!r.ok) throw new Error(r.status);
    const j = await r.json(); ANSWERS[it.id] = j.answer; drawList();
    $("#msg").textContent = "저장됨 " + j.answer.saved_at + " — " + (j.answer.value_name||"");
  }catch(e){ $("#msg").textContent = "저장 실패: " + e; }
}
(async()=>{
  try{ ITEMS = (await (await fetch("/api/items")).json()).items; }catch(e){ ITEMS = []; }
  try{ ANSWERS = await (await fetch("/api/answers")).json(); }catch(e){ ANSWERS = {}; }
  const order = {A:0,B:1,C:2};
  ITEMS = ITEMS.map((it,i)=>[it,i]).sort((x,y)=>order[x[0].bundle]-order[y[0].bundle]||x[1]-y[1]).map(x=>x[0]);
  drawList(); show(0);
})();
</script></body></html>
"""


def other_page() -> bytes:
    cfg = S["ctx"].cfg
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    return (OTHER_PAGE.replace("__TITLE__", esc(f"{cfg.label} 확인 — 그 밖"), 1).replace("__HEADING__", esc(f"{cfg.label} — 그 밖 확인"), 1)
            .replace("__NAV__", nav_html("other"), 1).encode("utf-8"))


class H(hcs.H):
    """han3_checkserver.H 의 send · send_file(Range) · do_HEAD 를 물려받고 길만 바꿈."""

    def do_GET(self):
        path = self.path.split("?")[0]
        out = S["ctx"].out
        if path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/turns" if S["turn_ids"] else "/other")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/turns":
            return self.send(200, turns_page(), "text/html; charset=utf-8")
        if path == "/other":
            return self.send(200, other_page(), "text/html; charset=utf-8")
        if path == "/turns.json":
            f = out / "turns.json"
            return self.send(200, f.read_bytes() if f.exists() else b'{"games": []}', "application/json")
        if path == "/answers":   # 차례 칸 화면 몫 — 사용자가 이 페이지에서 적은 차례 답만(읽기 답은 안 보냄)
            with LOCK:
                a = {k: v for k, v in load_answers(S["ans"]).items() if k in S["turn_ids"]}
            return self.send(200, json.dumps(a, ensure_ascii=False).encode("utf-8"), "application/json")
        if path == "/api/items":
            f = out / "items.json"
            return self.send(200, f.read_bytes() if f.exists() else b'{"items": []}', "application/json; charset=utf-8")
        if path == "/api/answers":
            with LOCK:
                a = {k: v for k, v in load_answers(S["ans"]).items() if k in S["items"]}
            return self.send(200, json.dumps(a, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        if path.startswith("/f/"):
            parts = path.split("/")
            if len(parts) == 4 and parts[2].replace("_", "").isalnum() and parts[3].replace(".jpg", "").isdigit():
                f = out / "frames" / parts[2] / parts[3]
                if f.exists():
                    return self.send(200, f.read_bytes(), "image/jpeg")
            return self.send(404, b"not found", "text/plain")
        if path.startswith("/media/"):
            from urllib.parse import unquote
            name = unquote(path[len("/media/"):])
            if name not in S["media"] or not (out / name).exists():
                return self.send(404, b"not found", "text/plain")
            return self.send_file(out / name, "video/mp4")
        return self.send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/save":
            return self.send(404, b"not found", "text/plain")
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            aid, ans = str(d["id"]), d["answer"]
            assert isinstance(ans, dict)
            if aid in S["turn_ids"]:   # 차례 칸 화면: 페이지 꼴 그대로(truthserver 와 같음)
                rec = {**ans, "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                save_answer(aid, rec)
                return self.send(200, b'{"ok":true}', "application/json")
            it = S["items"][aid]
            v, name = item_value(it, ans.get("value"))
            note = str(ans.get("note") or "")[:4000]
        except Exception:  # noqa: BLE001
            return self.send(400, b"bad request", "text/plain")
        rec = {"value": v, "value_name": name, "note": note, "bundle": it["bundle"], "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        save_answer(aid, rec)
        self.send(200, json.dumps({"ok": True, "answer": rec}, ensure_ascii=False).encode("utf-8"), "application/json")


def setup(ctx: Ctx, ans: Path | None):
    h3ts.configure(ctx.cfg)   # PAGE_PATCH(제목 · 묶음 이름 글)을 이 실행 설정으로 — 이 모듈 전역만 바뀜, 파일은 그대로
    S["ctx"] = ctx
    S["ans_default"] = ctx.r.d / "answers_user.json"
    S["ans"] = Path(ans).resolve() if ans else S["ans_default"]
    tdoc = json.loads((ctx.out / "turns.json").read_text(encoding="utf-8")) if (ctx.out / "turns.json").exists() else {"games": []}
    S["turn_ids"] = {t["id"] for g in tdoc["games"] for t in g["turns"]}
    items = json.loads((ctx.out / "items.json").read_text(encoding="utf-8"))["items"] if (ctx.out / "items.json").exists() else []
    S["items"] = {it["id"]: it for it in items}
    S["media"] = {it["video"]["file"] for it in items if it.get("video")}


def serve(ctx: Ctx, port: int, ans: Path | None):
    prep(ctx)   # 있는 것은 다시 안 만듦
    setup(ctx, ans)
    turns_page()
    other_page()
    print(f"http://127.0.0.1:{port}  (차례 칸 {len(S['turn_ids'])} · 그 밖 {len(S['items'])} · 답 → {S['ans']}, 기록 → {log_path(S['ans'])})", flush=True)
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def show(ctx: Ctx, ans: Path | None):
    setup(ctx, ans)
    a = load_answers(S["ans"])
    print(f"답 파일: {S['ans']}{'' if S['ans'].exists() else ' (없음)'}")
    lp = log_path(S["ans"])
    if lp.exists():
        print(f"기록: {lp} ({sum(1 for _ in lp.open(encoding='utf-8'))}줄)")
    groups = {"A 차례 칸": sorted(S["turn_ids"]), "A 그 밖": [k for k, it in S["items"].items() if it["bundle"] == "A"],
              "B 후보 고르기": [k for k, it in S["items"].items() if it["bundle"] == "B"],
              "C 알림": [k for k, it in S["items"].items() if it["bundle"] == "C"]}
    for g, ids in groups.items():
        print(f"\n■ {g} — 적은 수 {sum(1 for k in ids if k in a)} / {len(ids)}")
        for k in ids:
            x = a.get(k)
            if not x:
                print(f"   {k}: 아직 없음")
            elif g == "A 차례 칸":
                print(f"   {k}: {x.get('kind')} k_id={x.get('k_id')} k_pos={x.get('k_pos')} j={x.get('j_closed')} 끝 줄 {' '.join(x.get('order') or []) or '-'}"
                      + (f" !! {x.get('ops_error') or x.get('ops_pending')}" if x.get("ops_error") or x.get("ops_pending") else "")
                      + (f" · 메모 {x['note']}" if x.get("note") else "") + f" · 저장 {x.get('saved_at')}")
            else:
                print(f"   {k}: {x.get('value_name')} ({json.dumps(x.get('value'), ensure_ascii=False)})" + (f" · 메모 {x['note']}" if x.get("note") else "")
                      + f" · 저장 {x.get('saved_at')}")
    other = [k for k in a if k not in S["turn_ids"] and k not in S["items"] and not k.startswith("_")]
    if other:
        print(f"\n이 페이지 목록에 없는 답 {len(other)}: {', '.join(other)}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "serve", "show"):
        p = sp.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--questions", help="시험용: 질문 줄 파일(jsonl · json 목록) — 실행 폴더의 questions.jsonl · samples.jsonl 대신")
        p.add_argument("--out", help="시험용: 자료 폴더(기본 <실행>/confirm)")
        if name == "prep":
            p.add_argument("--force", action="store_true")
        if name in ("serve", "show"):
            p.add_argument("--ans", help="시험용: 답 파일(기본 <실행>/answers_user.json)")
        if name == "serve":
            p.add_argument("port", nargs="?", type=int, default=PORT)
    a = ap.parse_args()
    ctx = Ctx(a.run, a.out, a.questions)
    if a.cmd == "prep":
        prep(ctx, a.force)
    elif a.cmd == "serve":
        serve(ctx, a.port, a.ans)
    else:
        show(ctx, a.ans)


if __name__ == "__main__":
    main()
