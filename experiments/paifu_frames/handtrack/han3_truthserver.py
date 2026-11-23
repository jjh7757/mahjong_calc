"""11-14 3반장 — 확신 낮은 여섯 차례의 손패 정답 입력 페이지(2026-11-23). 내 컴퓨터 안에서만 돈다(127.0.0.1).

  python -X utf8 han3_truthserver.py [포트 8313] [--ans <답 파일>]   # 페이지 띄우기(--ans: 시험용 — 진짜 답 파일 대신 다른 파일에 씀)
  python -X utf8 han3_truthserver.py prep [--force]                  # 프레임 · 차례 목록 만들기(서버를 켤 때 없으면 저절로)
  python -X utf8 han3_truthserver.py compare [--ans <답 파일>]       # 사용자 답과 Opus 답(rawread_han3_1123/<id>/answer.json) 나란히

11-16 ~ 11-17 의 truthserver.py · truthpage.html 을 고치지 않고 그대로 쓴다:
- truthserver 모듈을 import 해 BASE(자료 폴더) · ANS(답 파일)만 바꿔 끼우고, 저장(/save)만 답 기록 파일 이름을 맞추려고 다시 씀
  (기존 서버는 답 파일이 자료 폴더 밖이면 기록을 <답 이름>_log.jsonl 로 씀 — 여기선 답 옆 answers_log.jsonl).
- 페이지는 truthpage.html 을 읽어 보낼 때 글 네 군데만 바꿔 보낸다(PAGE_PATCH — 제목 · 묶음 이름 · 진행 글 · 구간 설명).
  묶음 · 진행 수는 han 2 인 판만 세므로 이 여섯 차례의 판은 han 2 로 적어 넣는다.
- 자료 폴더 = results/han3_1123/review/truth/(turns.json + frames/<판>/<ms>.jpg). 프레임은 차례 창(Opus 가 본 frames.txt 의
  첫 · 끝 시각)의 1초 앞부터 끝까지 초당 10장 전부, review_clips.py 와 같은 자르기(sheet_band + 90px, 그 사람 시점, 2배).
  구간은 둘 — "앞"(창 1초 앞) · "버림"(창 전체, 페이지가 이 구간 첫 프레임에서 연다).
- 답 = results/han3_1123/review/answers_user.json(+ answers_log.jsonl). Opus 답은 페이지에 안 보낸다(사용자가 따로 적게).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import htcommon as hc  # noqa: E402
import slotsim as ss  # noqa: E402
import truthserver as ts  # noqa: E402

IDS = {"n03_d04": "n03_150528", "n04_d04": "n04_151410", "n04_d09": "n04_151410",
       "n05_d09": "n05_151953", "n06_d06": "n06_152545", "n08_d04": "n08_153825"}
H3 = hc.EXP / "paifu_frames" / "results" / "han3_1123"
PREP = H3 / "_prep"
REVIEW = H3 / "review"
TRUTH = REVIEW / "truth"
ANS_DEFAULT = REVIEW / "answers_user.json"
RAW = hc.WORK / "rawread_han3_1123"
PAD = 90          # review_clips.py 와 같음 — 줄 방향 · 앞쪽 여유
PRE_MS = 1000     # 창 1초 앞부터

PAGE_PATCH = [  # (원래 글, 바꾼 글) — 한 번씩만 나와야 한다(truthpage.html 이 바뀌면 멈춤)
    ("<title>시험 판 정답 확인</title>", "<title>3반장 여섯 차례 정답</title>"),
    ('"2반장 — 적을 판"', '"11-14 3반장 — 확인할 여섯 차례"'),
    ("`2반장 적은 차례 ${n} / ${tot}`", "`적은 차례 ${n} / ${tot}`"),
    ("가운데 진한 구간이 그 버림이 일어난 손 움직임, 앞·뒤 구간은 그 전후의 손 움직임이다.",
     "진한 \"버림\" 구간이 이 차례 창 전체(앞 자리 버림이 보이기 직전 ~ 다음 차례 경계)이고, 그 앞 \"앞\" 구간은 창 1초 앞이다. 그림은 초당 10장 전부다."),
]


def page_bytes() -> bytes:
    html = (HERE / "truthpage.html").read_text(encoding="utf-8")
    for old, new in PAGE_PATCH:
        if html.count(old) != 1:
            raise RuntimeError(f"truthpage.html 에서 바꿀 글이 {html.count(old)}번 나옴: {old[:40]}")
        html = html.replace(old, new)
    return html.encode("utf-8")


# ------------------------------------------------------------------ 자료 만들기
def window(tid: str) -> tuple[int, int]:
    """Opus 가 본 창(frames.txt 첫 · 끝 시각) — review_clips.py 와 같은 읽기."""
    ts_ = [re.findall(r"\d\d:\d\d\.\d", ln)[0] for ln in (RAW / tid / "frames.txt").read_text(encoding="utf-8").strip().splitlines()]
    return hc.to_ms("15:" + ts_[0]), hc.to_ms("15:" + ts_[-1])


def cut_turns() -> dict:
    out = {}
    for g in hc.jload(PREP / "turns_cut_han3.json")["games"]:
        for t in g["turns"]:
            if t["id"] in IDS:
                out[t["id"]] = (g, t)
    return out


def prep(force: bool = False):
    import numpy as np  # noqa: F401  (band_crop 가 numpy 배열을 돌려줌)
    from PIL import Image
    cut = cut_turns()
    meta = {g["id"]: g for g in hc.jload(PREP / "turns_han3.json")["games"]}
    games, rows = {}, []
    for tid, gid in IDS.items():
        g, t = cut[tid]
        assert t["game"] == gid, (tid, t["game"], gid)
        t0, t1 = window(tid)
        ms_all = hc.frame_range(t0 - PRE_MS, t1)
        pre, own = [m for m in ms_all if m < t0], [m for m in ms_all if m >= t0]
        c = hc.config(gid)
        side = c["side"]
        b = list(c.get("sheet_band") or c["band"])
        b = [max(0, b[0] - PAD), max(0, b[1] - PAD), min(1496, b[2] + PAD), min(1496, b[3] + PAD)]
        fdir = TRUTH / "frames" / gid
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
        n = t.get("n_calc")
        try:  # 줄 장수 맞춤 확인용으로만 길이를 본다(답 내용은 페이지에 안 보냄)
            n_opus = len(hc.jload(RAW / tid / "answer.json").get("end_order") or [])
        except FileNotFoundError:
            n_opus = None
        warn = "" if n_opus in (None, n) else f"  !! 줄 장수 다름: turns {n} · Opus end_order {n_opus}"
        turn = {"id": tid, "label": t["label"], "repeat": False, "game": gid, "i": t["i"], "tile": t.get("tile"),
                "sideways": t.get("sideways", False), "meld_tiles": t.get("meld_tiles"), "n_calc": n,
                "same_seg": 1,  # 차례 창 하나 = 버림 하나(기존 페이지의 "한 구간에 버림 두 번" 안내를 띄우지 않게)
                "more_after": False, "more_before": False,
                "segs": ([{"seg": 0, "role": "앞", "t0": hc.mss(pre[0]), "frames": pre}] if pre else []) +
                        [{"seg": 1, "role": "버림", "t0": hc.mss(own[0]), "frames": own}],
                "window": [hc.hms(t0), hc.hms(t1)]}
        if gid not in games:
            m0 = meta.get(gid, {})
            games[gid] = {"id": gid, "han": 2, "skip": False, "side": side, "first_i": m0.get("first_i"), "n_frames": 0, "turns": []}
        games[gid]["turns"].append(turn)
        games[gid]["n_frames"] += len(ms_all)
        rows.append((tid, n, len(ms_all), len(pre), hc.hms(ms_all[0]), hc.hms(t0), hc.hms(t1), made, warn))
    hc.jsave(TRUTH / "turns.json", {"games": list(games.values()), "scale": 2,
                                     "note": "han3_truthserver.py prep — 11-14 3반장 확신 낮은 여섯 차례(han 2 로 적은 것은 페이지 묶음용)"})
    print("차례      줄  프레임(앞)  첫 프레임    창 시작      창 끝       새로 그림")
    for tid, n, nf, npre, f0, w0, w1, made, warn in rows:
        print(f"{tid}  {n!s:>3}  {nf:4d}({npre:2d})  {f0}  {w0}  {w1}  {made:4d}{warn}")
    print(f"→ {TRUTH / 'turns.json'}")


# ------------------------------------------------------------------ 서버
class H(ts.H):
    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            return self.send(200, page_bytes(), "text/html; charset=utf-8")
        return super().do_GET()

    def do_POST(self):  # truthserver.H.do_POST 와 같고 기록 파일 이름만 답 옆 answers_log.jsonl
        if self.path != "/save":
            return self.send(404, b"not found", "text/plain")
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            tid, ans = str(d["id"]), d["answer"]
            assert isinstance(ans, dict) and tid in IDS
        except Exception:  # noqa: BLE001
            return self.send(400, b"bad request", "text/plain")
        ans["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with ts.LOCK:
            a = ts.load_answers()
            a[tid] = ans
            tmp = ts.ANS.with_suffix(".tmp")
            tmp.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            tmp.replace(ts.ANS)
            log = ts.ANS.parent / ("answers_log.jsonl" if ts.ANS == ANS_DEFAULT else ts.ANS.stem + "_log.jsonl")
            with open(log, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"id": tid, **ans}, ensure_ascii=False) + "\n")
        self.send(200, b'{"ok":true}', "application/json")


def serve(port: int, ans: Path):
    if not (TRUTH / "turns.json").exists():
        print("프레임이 없어 먼저 만든다(1 ~ 2분)", flush=True)
        prep()
    page_bytes()  # 페이지 글 바꾸기가 되는지 켜기 전에 확인
    ts.BASE, ts.ANS = TRUTH, ans
    ans.parent.mkdir(parents=True, exist_ok=True)
    print(f"http://127.0.0.1:{port}  (답 → {ans})", flush=True)
    ThreadingHTTPServer.request_queue_size = 128
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


# ------------------------------------------------------------------ 대조
KIND = {"tsumogiri": "쯔모기리", "hand": "손에서", "call": "울기 뒤", "unseen": "안 보임", "bad": "구간 이상", None: "안 적음"}


def user_norm(a: dict, n: int) -> dict:
    """페이지 답 → kind · k(원래 줄 번호 = k_id) · j(정리 뒤 D 자리 = j_closed) · order. truthnorm.py 와 같은 읽기:
    칸 동작(ops)이 있으면 slotsim 으로 다시 굴려 정하고(페이지 계산은 안 믿음), 없으면 적힌 값. order 가 없으면
    rebuild_opus.truth_order 와 같이 k · j(+ moves)로 짓는다."""
    kind, n = a.get("kind"), a.get("n") or n
    out = {"kind": kind, "k": None, "j": None, "order": None, "err": None, "n": n}
    if a.get("ops") and kind in ("hand", "tsumogiri"):
        try:
            r = ss.run_ops(a["ops"], n).result()
            out.update(kind=r["kind"], k=r["k_id"], j=r["j_closed"], order=[str(x) for x in r["order"]])
        except ss.SlotError as e:
            out["err"] = f"칸 동작 검산 걸림: {e}"
        return out
    if kind == "hand":
        out.update(k=a.get("k_id", a.get("k_orig", a.get("k"))), j=a.get("j_closed"))
    if a.get("order"):
        out["order"] = [str(x) for x in a["order"]]
    elif kind == "tsumogiri":
        out["order"] = [str(i) for i in range(1, n + 1)]
    elif kind == "hand" and out["k"] and out["j"]:
        lst = [str(i) for i in range(1, n + 1) if i != out["k"]]
        lst.insert(out["j"] - 1, "D")
        for x, y in a.get("moves") or []:
            lst[x - 1], lst[y - 1] = lst[y - 1], lst[x - 1]
        out["order"] = lst
    return out


def compare(ans: Path):
    user = hc.jload(ans) if ans.exists() else {}
    cut = cut_turns()
    print(f"사용자 답: {ans}{'' if ans.exists() else ' (파일 없음)'}")
    print("Opus 답:   " + str(RAW / "<id>" / "answer.json"))
    tally = {"같음": 0, "다름": 0, "아직 없음": 0}
    for tid in IDS:
        n = cut[tid][1].get("n_calc") or 13
        o = hc.jload(RAW / tid / "answer.json")
        eo = [str(x) for x in o.get("end_order") or []]
        oj = o.get("j")
        if o.get("kind") == "hand" and "D" in eo and oj != eo.index("D") + 1:
            print(f"  !! {tid} Opus j={oj} 인데 end_order 의 D 는 {eo.index('D') + 1}번째")
        a = user.get(tid) or {}
        print(f"\n■ {tid}  (줄 {n}장 · 강의 버린 패 {cut[tid][1].get('tile')})")
        print(f"   Opus  : {KIND.get(o.get('kind'), o.get('kind'))}  k={o.get('k')}  j={oj}  끝 줄 {' '.join(eo)}" + ("  (확신 없음)" if o.get("unsure") else ""))
        if not a.get("kind"):
            tally["아직 없음"] += 1
            print("   사용자: 아직 없음" + (f"  (적다 만 동작: {a['ops']})" if a.get("ops") else ""))
            continue
        u = user_norm(a, n)
        print(f"   사용자: {KIND.get(u['kind'], u['kind'])}  k={u['k']}  j={u['j']}  끝 줄 {' '.join(u['order'] or []) or '-'}"
              + ("  (확신 없음)" if a.get("unsure") else "") + (f"  [줄 {u['n']}장으로 적음]" if u["n"] != n else ""))
        if a.get("ops"):
            print(f"           동작: {a['ops']}")
        if u["err"] or a.get("ops_error") or a.get("ops_pending"):
            print(f"           !! {u['err'] or a.get('ops_error') or ('아직: ' + a['ops_pending'])}")
        if a.get("note"):
            print(f"           메모: {a['note']}")
        diff = []
        if u["kind"] != o.get("kind"):
            diff.append("종류")
        else:
            if u["kind"] == "hand":
                if u["k"] != o.get("k"):
                    diff.append("버린 칸 k")
                if u["j"] != oj:
                    diff.append("들어간 칸 j")
            if u["kind"] in ("hand", "tsumogiri") and u["order"] != eo:
                diff.append("끝 줄 순서")
        state = "다름" if diff else "같음"
        tally[state] += 1
        print(f"   → {state}" + (f" ({', '.join(diff)})" if diff else "") + (f"  · 사용자 저장 {a['saved_at']}" if a.get("saved_at") else ""))
    print("\n" + " · ".join(f"{k} {v}" for k, v in tally.items()))


def main():
    args = sys.argv[1:]
    if args and args[0] in ("prep", "compare"):
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        ap.add_argument("--force", action="store_true")
        ap.add_argument("--ans", default=str(ANS_DEFAULT))
        a = ap.parse_args(args)
        return prep(a.force) if a.cmd == "prep" else compare(Path(a.ans).resolve())
    ans = ANS_DEFAULT
    if "--ans" in args:
        i = args.index("--ans")
        ans = Path(args[i + 1]).resolve()
        del args[i:i + 2]
    serve(int(args[0]) if args else 8313, ans)


if __name__ == "__main__":
    main()
