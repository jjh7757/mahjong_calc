"""헤드 폰 녹화 프레임(1496², 초당 약 10장)에 앱의 겹쳐 보기(`ondevice.overlay`)를 돌려 overlay_dump.json 꼴로 받아 둔다(2026-11-23).

`overlay_dump.py`(태블릿 추적 프레임 zip)의 헤드 녹화 판이다. 판 구간을 3.0초 눈금으로 나누고 눈금마다 가장 가까운 녹화 프레임을 고른다.
결과는 `replay_recorder.dart`(앱 버림 기록기)에 그대로 넣는다 — 실행 · 채점은 `headrec_run.py`.

  python -X utf8 experiments/paifu_frames/headrec_dump.py defs                       → headrec_rounds.json(검증 4판 + 3반장 n01~n08) 만들기
  python -X utf8 experiments/paifu_frames/headrec_dump.py dump <판 정의.json> [판 id …] [--mode ab|c2x|reveal] [--force]
     ab     → <판>/overlay_dump.json      : 1496 그대로 겹쳐 보기(t · tc = 방식 A) + 같은 상자를 read_small 로 키워 읽은 t2 · tc2(방식 B)
     c2x    → <판>/overlay_dump_c2x.json  : 프레임을 2배(2992, BICUBIC · JPEG q95)로 키운 뒤 겹쳐 보기(방식 C, t2 · tc2 도 키운 그림에서)
     reveal → <판>/reveal_overlay.json    : t_reveal + 2.0초 · + 4.0초 두 장에 겹쳐 보기(1496 그대로, t · tc · t2 · tc2 · r · s)
     reveal_c2x → <판>/reveal_overlay_c2x.json : 같은 두 장을 2배로 키워(방식 C)
  판 id 를 안 주면 정의 파일의 판 전부. 이미 있는 출력은 건너뛴다(--force 면 다시).
  출력 폴더: results/han3_1123/<판 id>/ (--out 으로 바꿈). 녹화 폴더 --rec, 날짜 --date(기본 2026-11-14), 눈금 --step(기본 3.0).

판 정의 파일 꼴(README 와 같음):
  {"<판 id>": {"t_from": "HH:MM:SS[.f]", "t_to": "HH:MM:SS[.f]", "t_reveal": "HH:MM:SS[.f]"(선택, reveal 에 필요),
               "first_discard": "top"(선택, 선 후보와 견줄 자리), "truth_key": "h13_132644"(선택, 2반장 검증 채점용), "note": "…"}, …}
  "_" 로 시작하는 키는 설명으로 보고 건너뛴다. 시각은 현지(KST) 시각, 날짜는 --date.
  판 목록 꼴 {"rounds": [{"id", "t_start", "t_end_play", "t_reveal", "note", "dealer_side": {"first": …}}]}(v1114rec/new/rounds.json ·
  results/han3_1123/rounds_p.json)도 그대로 받는다 → t_from = t_start − 15초, t_to = t_reveal − 0.3초(from_rounds_list).
격자(겹쳐 보기 역할 · 자리 나눔): 줄 격자 x1 264 · x2 783 · y1 259 · y2 777(1000분율), 리치봉 구역 424,425,618,622 — 2 · 3반장 공통(추적 프레임과 같은 화각).
"""
import argparse
import bisect
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXP = HERE.parent
REC = EXP / "visit_20261114" / "head_rec" / "rec_20261114_125617"
OUT = HERE / "results" / "han3_1123"
KST = timezone(timedelta(hours=9))
GRID = {"x1": 264, "x2": 783, "y1": 259, "y2": 777, "sticks": [424, 425, 618, 622]}
VAL = ["h13_132644", "h15_134151", "h17_140450", "h18_141259"]
SIDE_KO = {"아래": "bottom", "오른쪽": "right", "위": "top", "왼쪽": "left"}


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o, indent=None):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=indent))


def hms_of(iso):
    """'2026-11-14T14:47:48.500+09:00' · '2026-11-14T13:26:30.822877' → 'HH:MM:SS.fff'."""
    return iso[11:23] if len(iso) >= 23 else iso[11:19]


def defs():
    """검증 4판(추적 dump 첫 · 끝 프레임 시각) + 3반장 8판(t_start − 15초 ~ t_reveal − 0.3초) → headrec_rounds.json."""
    out = {"_note": "headrec_dump.py defs 로 만듦(2026-11-23). val_* = 2반장 검증(구간 = 추적 overlay_dump 첫 · 끝 프레임, rounds.json 에 t0/t1 없음), "
                    "n0* = 3반장(v1114rec/new/rounds.json: t_from = t_start − 15초, t_to = t_reveal − 0.3초). 시각은 KST."}
    rd = jl(HERE / "results" / "heldout_1114" / "rounds.json")
    for k in VAL:
        fr = jl(HERE / "results" / k / "overlay_dump.json")["frames"]
        r = rd[k]
        out["val_" + k] = {"t_from": r.get("t0") or hms_of(fr[0]["at"]), "t_to": r.get("t1") or hms_of(fr[-1]["at"]),
                           "truth_key": k, "note": r["note"]}
    out.update(from_rounds_list(jl(EXP / "tile_classifier" / "data" / "v1114rec" / "new" / "rounds.json")["rounds"]))
    wj(HERE / "headrec_rounds.json", out, indent=1)
    print("→", HERE / "headrec_rounds.json", len(out) - 1, "판")


def _hms(v):
    """ISO('2026-11-14T14:47:48.500+09:00') 또는 'HH:MM:SS[.f]' → 'HH:MM:SS.fff'."""
    return hms_of(v) if "T" in v else v


def _shift(hms, sec):
    h, m, s = hms.split(":")
    t = int(h) * 3600 + int(m) * 60 + float(s) + sec
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}"


def from_rounds_list(rounds, before=15.0, after_reveal=-0.3):
    """판 목록 꼴(v1114rec/new/rounds.json · results/han3_1123/rounds_p.json: [{"id", "t_start", "t_end_play", "t_reveal", "note", "dealer_side"?}])
    → 이 스크립트의 판 정의 꼴. t_from = t_start − 15초, t_to = t_reveal − 0.3초. 첫 버림 자리 = dealer_side.first(있으면) 또는 note 의 "첫 버림(…)"."""
    out = {}
    for r in rounds:
        ts, tr = _hms(r["t_start"]), _hms(r["t_reveal"])
        fd = None
        ds = r.get("dealer_side")
        if isinstance(ds, dict):
            fd = ds.get("first")
        elif isinstance(ds, str):
            fd = ds
        note = r.get("note") or ""
        i = note.find("첫 버림")
        if fd is None and i >= 0:
            seg = note[i:i + 20]
            for ko, s in SIDE_KO.items():
                if ko in seg:
                    fd = s
                    break
        out[r["id"]] = {"t_from": _shift(ts, -before), "t_to": _shift(tr, after_reveal), "t_reveal": tr, "t_start": ts,
                        "t_end_play": _hms(r["t_end_play"]) if r.get("t_end_play") else None,
                        "first_discard": fd, "result": r.get("result"), "note": note}
    return out


def load_defs(path):
    """판 정의 파일: {"<판 id>": {"t_from", "t_to", …}} 꼴, 또는 {"rounds": [ … ]} 판 목록 꼴(from_rounds_list 로 바꿈)."""
    o = jl(path)
    if isinstance(o.get("rounds"), list):
        return from_rounds_list(o["rounds"])
    return {k: v for k, v in o.items() if not k.startswith("_")}


class Frames:
    """녹화 폴더의 f_<epoch ms>.jpg 목록(시각 순)."""

    def __init__(self, rec: Path):
        self.rec = rec
        ms = []
        with os.scandir(rec) as it:
            for e in it:
                n = e.name
                if n.startswith("f_") and n.endswith(".jpg"):
                    ms.append(int(n[2:-4]))
        ms.sort()
        self.ms = ms

    def nearest(self, t_ms):
        i = bisect.bisect_left(self.ms, t_ms)
        c = [j for j in (i - 1, i) if 0 <= j < len(self.ms)]
        j = min(c, key=lambda j: abs(self.ms[j] - t_ms))
        return self.ms[j]

    def path(self, m):
        return self.rec / f"f_{m}.jpg"


def to_ms(date, hms):
    """'HH:MM:SS[.f]' (KST) → epoch ms."""
    hh, mm, ss = hms.split(":")
    sec = float(ss)
    d = datetime(*map(int, date.split("-")), int(hh), int(mm), int(sec), round((sec - int(sec)) * 1e6), tzinfo=KST)
    return round(d.timestamp() * 1000)


def iso_of(m):
    return datetime.fromtimestamp(m / 1000, KST).replace(tzinfo=None).isoformat(timespec="microseconds")


def ticks(date, t_from, t_to, step):
    a, b = to_ms(date, t_from), to_ms(date, t_to)
    out, t = [], a
    while t <= b + 1:
        out.append(t)
        t += round(step * 1000)
    return out


class Runner:
    def __init__(self):
        sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
        sys.path.append(str(ROOT / "android/app/src/main/python"))
        import ondevice  # noqa: E402
        import numpy as np  # noqa: E402
        from PIL import Image  # noqa: E402

        self.ondevice, self.np, self.Image = ondevice, np, Image
        self.reader = ondevice._get_reader()

    def frame(self, raw: bytes, grid, scale=1):
        """겹쳐 보기 1장 + 상자마다 read_small(t2 · tc2). scale=2 면 그림을 2배로 키운 뒤(방식 C)."""
        Image, np = self.Image, self.np
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        t_up = 0.0
        if scale != 1:
            t0 = time.perf_counter()
            im = im.resize((im.width * scale, im.height * scale), Image.BICUBIC)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=95)
            raw = buf.getvalue()
            t_up = (time.perf_counter() - t0) * 1000
        q = {k: str(grid[k]) for k in ("x1", "x2", "y1", "y2")}
        o = json.loads(self.ondevice.overlay(raw, q))
        W, H = im.size
        rgb = np.asarray(im)
        t0 = time.perf_counter()
        for t in o["tiles"]:
            x, y, w, h = t["b"]
            t["t2"], t["tc2"] = self.reader.read_small(rgb, (round(x * W), round(y * H), round(w * W), round(h * H)))
        o["ms"]["small"] = round((time.perf_counter() - t0) * 1000)
        if scale != 1:
            o["ms"]["upscale"] = round(t_up)
        return W, H, o


def dump(args):
    dfs = load_defs(args.defs)
    ids = args.ids or list(dfs)
    fr = Frames(Path(args.rec))
    print("녹화 프레임", len(fr.ms), iso_of(fr.ms[0]), "~", iso_of(fr.ms[-1]), flush=True)
    runner = None
    for rid in ids:
        d = dfs[rid]
        od = Path(args.out) / rid
        name = {"ab": "overlay_dump.json", "c2x": "overlay_dump_c2x.json", "reveal": "reveal_overlay.json",
                "reveal_c2x": "reveal_overlay_c2x.json"}[args.mode]
        if (od / name).exists() and not args.force:
            print(rid, name, "있음 → 건너뜀", flush=True)
            continue
        if args.mode.startswith("reveal"):
            if not d.get("t_reveal"):
                print(rid, "t_reveal 없음 → reveal 건너뜀")
                continue
            tr = to_ms(args.date, d["t_reveal"])
            tl = [tr + 2000, tr + 4000]
        else:
            tl = ticks(args.date, d["t_from"], d["t_to"], args.step)
        runner = runner or Runner()
        frames, seen = [], set()
        t_all = time.perf_counter()
        for tk in tl:
            m = fr.nearest(tk)
            if m in seen:
                continue
            seen.add(m)
            raw = fr.path(m).read_bytes()
            W, H, o = runner.frame(raw, GRID, 2 if args.mode.endswith("c2x") else 1)
            ent = {"file": f"f_{m}.jpg", "at": iso_of(m), "tick": iso_of(tk), "dt_ms": m - tk, "w": W, "h": H,
                   "tiles": o["tiles"], "ms": o["ms"]}
            if args.mode.startswith("reveal"):
                ent["offset_s"] = round((tk - tr) / 1000, 1)
            frames.append(ent)
            print(rid, args.mode, ent["at"][11:23], f"dt {m - tk:+d}ms", len(o["tiles"]), "장",
                  sum(1 for t in o["tiles"] if t["r"] == "river"), "강", o["ms"]["total"], "ms", flush=True)
        src = Path(args.rec).resolve()
        out = {"grid": GRID, "source": src.relative_to(ROOT).as_posix() if src.is_relative_to(ROOT) else str(src),
               "def": d, "mode": args.mode, "step_s": args.step, "made": datetime.now().isoformat(timespec="seconds"),
               "wall_s": round(time.perf_counter() - t_all, 1), "frames": frames}
        wj(od / name, out)
        print(rid, "→", od / name, len(frames), "프레임", out["wall_s"], "초", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["defs", "dump"])
    ap.add_argument("defs", nargs="?", default=str(HERE / "headrec_rounds.json"))
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--mode", choices=["ab", "c2x", "reveal", "reveal_c2x"], default="ab")
    ap.add_argument("--rec", default=str(REC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--date", default="2026-11-14")
    ap.add_argument("--step", type=float, default=3.0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "defs":
        defs()
    else:
        dump(a)


if __name__ == "__main__":
    main()
