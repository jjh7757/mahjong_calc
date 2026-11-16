"""운영 자리 판독 검출기(tile-obb-r8)의 뒷면 상자로 손패 줄을 잡아 pixtrack 판정·LLM 글에 넣기(2026-11-16, 사용자 "검출기로도 재 봐").

  python -X utf8 dettrack.py detect <판 id…>      # 차례 구간 프레임마다 검출 → _work/det_<판>.json(캐시)
  python -X utf8 dettrack.py run <판 id…> --out <파일>   # pixtrack 규칙 판정(덩어리 = 뒷면 상자 묶음)
  python -X utf8 dettrack.py text <판 id…> --out <폴더>  # LLM 글(llmtext 와 같은 꼴)
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beforeafter as ba  # noqa: E402
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402

REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
sys.path.insert(0, str(REC))
GAP_JOIN = 0.45  # 이웃 뒷면 상자 사이 빈칸이 한 장 폭의 이 비율 이하면 같은 덩어리


def reader():
    from app.local_read import LocalReader
    return LocalReader(threads=8)


def boxes_view(L, rgb, cfg) -> list:
    """뒷면 상자 중 손패 띠(sheet_band) 안의 것 → 대국자 시점 [x0, x1, y0, y1, 점수]."""
    L._sessions()  # 모델 올리기(_seat_raw 는 안 올림)
    _, backs, _, _ = L._seat_raw(rgb)
    x0b, y0b, x1b, y1b = cfg["sheet_band"]
    out = []
    for (x, y, w, h), _rc in backs:
        cx, cy = x + w / 2, y + h / 2
        if not (x0b <= cx <= x1b and y0b <= cy <= y1b):
            continue
        p = [hc.to_view_xy(q, cfg["sheet_band"], cfg["side"]) for q in ((x, y), (x + w, y + h))]
        xs, ys = [a for a, _ in p], [b for _, b in p]
        out.append([round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1)])
    return sorted(out)


def cmd_detect(a):
    L = reader()
    for gid in a.games:
        cfg = hc.config(gid)
        sg = hc.jload(hc.OUT / gid / "segments.json")
        rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
        cache_p = hc.WORK / f"det_{gid}.json"
        cache = hc.jload(cache_p) if cache_p.exists() else {}
        todo = sorted({ms for tr in ba.turns_from_replay(rp, sg) for ms in hc.frame_range(tr["ms_before"], tr["ms_after"])} - {int(k) for k in cache})
        t0 = time.time()
        for i, ms in enumerate(todo):
            cache[str(ms)] = boxes_view(L, hc.load(ms), cfg)
            if i % 200 == 0:
                print(gid, i, len(todo), f"{time.time() - t0:.0f}s", flush=True)
                hc.jsave(cache_p, cache, indent=None)
        hc.jsave(cache_p, cache, indent=None)
        print(gid, "끝", len(todo), "장", f"{time.time() - t0:.1f}s", f"장당 {(time.time() - t0) / max(1, len(todo)) * 1000:.0f}ms")


class DetRow(pt.Row):
    """pt.Row 의 덩어리를 뒷면 상자 묶음으로 바꾼 것(손 가림 열은 pt.Row 와 같은 피부 마스크)."""

    def __init__(self, gid):
        super().__init__(gid)
        self.det = {int(k): v for k, v in hc.jload(hc.WORK / f"det_{gid}.json").items()}
        ws = [b[1] - b[0] for v in self.det.values() for b in v]
        self.pitch = float(np.median(ws)) if ws else self.pitch

    def frame(self, ms: int):
        v = self.view(ms)
        _, sk = self.runs_of(v)
        skin, _, _, _ = pt.masks(v)
        h = self.y1 - self.y0
        skin_col = skin[max(0, self.y0 - h):self.y1 + h // 2].mean(0) > 0.08
        W = len(skin_col)
        near = lambda xx: bool(skin_col[max(0, int(xx) - 4):min(W, int(xx) + 5)].any())  # noqa: E731
        bx = self.det.get(ms, [])
        runs, cur = [], None
        for b in bx:
            if cur and b[0] - cur[1] <= GAP_JOIN * self.pitch:
                cur[1], cur[2] = max(cur[1], b[1]), cur[2] + 1
            else:
                if cur:
                    runs.append(cur)
                cur = [b[0], b[1], 1]
        if cur:
            runs.append(cur)
        out = [{"x0": int(a), "x1": int(b), "n": float(n), "hl": near(a), "hr": near(b)} for a, b, n in runs]
        return {"ms": ms, "t": hc.hms(ms), "runs": out, "bruns": [], "skin": sk}


def cmd_run(a):
    out = []
    for gid in a.games:
        R = DetRow(gid)
        rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
        tmap = {t["t"]: t for t in rp["turns"]}
        n_hand = 13
        for tr in ba.turns_from_replay(rp, R.sg):
            if "call" in " ".join(tr["events"]):
                n_hand = 10
            truth = pt.truth_of(gid, tmap[tr["t"]])
            got = pt.judge_turn(R, tr, n_hand)
            out.append({"game": gid, "t": tr["t"], "segs": tr["segs"], "truth": truth, "got": {k: got.get(k) for k in ("mode", "k", "j")}})
            print(f"{gid} {tr['t']:>2}순  정답 {truth['mode']}/k{truth['k']}/j{truth['j'] or truth['j_cands']}  →  {got['mode']}/k{got['k']}/j{got['j']}")
    hc.jsave(a.out, out)


def cmd_text(a):
    import llmtext as lt
    lt.pt.Row = DetRow  # llmtext.cmd_make 이 pt.Row 를 쓰므로 바꿔 끼움
    lt.cmd_make(a)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("detect")
    d.add_argument("games", nargs="+")
    r = sp.add_parser("run")
    r.add_argument("games", nargs="+")
    r.add_argument("--out", required=True)
    t = sp.add_parser("text")
    t.add_argument("games", nargs="+")
    t.add_argument("--out", required=True)
    a = ap.parse_args()
    {"detect": cmd_detect, "run": cmd_run, "text": cmd_text}[a.cmd](a)


if __name__ == "__main__":
    main()
