"""헤드 녹화 겹쳐 보기(headrec_dump.py 출력)를 앱 버림 기록기(replay_recorder.dart)에 넣고 채점 · 검사한다(2026-11-23).

  python -X utf8 experiments/paifu_frames/headrec_run.py build              → replay_recorder.dart 를 results/han3_1123/_bin 에 exe 로(소스가 새로우면 다시)
  python -X utf8 experiments/paifu_frames/headrec_run.py rescore            → 기존 추적 프레임 결과(results/<키>/dart_overlay.json)를 이 채점으로 다시 세어 summary.json 과 대조
  python -X utf8 experiments/paifu_frames/headrec_run.py val                → 검증 4판: 추적 프레임(지금 기본값) · A · B · C 재생 + 채점 → results/han3_1123/val_summary.json
  python -X utf8 experiments/paifu_frames/headrec_run.py play <A|B|C> [판 id …] [--defs 판 정의.json] [--bottom-seat 0]
                                                                            → 3반장 판: 선 없이 한 번 → 선 후보 → 그 선으로 다시(dart_overlay.json · _timeline · paifu_rec.json)
                                                                              + 엮임 검사 · 같은 종류 5장 · 울기 · 의심 칸 · river_check.jpg → han3_summary.json(판 id 를 주면 그 판만 덧씀)
방식: A = overlay --min-side 0(1496 그대로, 종류 t) · B = overlay-small(키워 읽은 t2) · C = overlay(2배로 키운 overlay_dump_c2x.json).
채점은 heldout_1114.py score() 와 같은 규칙: 기록기 slots 중 taken_at null 의 tile 을 정답 강과 편집 거리 정렬(score.align) → 맞음 · 틀림(적5↔5 따로) · 빠짐 · 헛것,
눕힌 패는 남은 강 안 위치를 정답 truth_sideways 와 견줌. 엮임 검사 = interleave_check.py 와 같은 규칙(선부터 차례로, 울려 나간 패는 called_by 자리로).
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXP = HERE.parent
OUT = HERE / "results" / "han3_1123"
REC = EXP / "visit_20261114" / "head_rec" / "rec_20261114_125617"
DART = "C:/Users/jjh7757/flutter/bin/dart.bat"
EXE = OUT / "_bin" / "replay_recorder.exe"
SRC = HERE / "replay_recorder.dart"
SIDES = ["bottom", "right", "top", "left"]
KO = {"bottom": "아래", "right": "오른쪽", "top": "위", "left": "왼쪽"}
VAL = ["h13_132644", "h15_134151", "h17_140450", "h18_141259"]
STICKS = "424,425,618,622"
sys.path.insert(0, str(HERE))
from score import align  # noqa: E402

METHOD = {  # (모드, dump 파일, 덧붙일 옵션)
    "A": ("overlay", "overlay_dump.json", ["--min-side", "0"]),
    "B": ("overlay-small", "overlay_dump.json", []),
    "C": ("overlay", "overlay_dump_c2x.json", []),
}


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o, indent=1):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=indent))


def build():
    if EXE.exists() and EXE.stat().st_mtime > SRC.stat().st_mtime:
        return
    EXE.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([DART, "compile", "exe", str(SRC.relative_to(ROOT)), "-o", str(EXE)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(p.stdout + p.stderr)
    print("빌드", EXE)


def replay(mode, dump, dealer, od: Path, extra=(), paifu_bottom=None):
    """기록기 실행 → od/dart_overlay.json(+ _timeline.json) [+ paifu_rec.json] + stdout.txt."""
    build()
    od.mkdir(parents=True, exist_ok=True)
    args = [str(EXE), mode, str(dump), dealer or "none", str(od / "dart_overlay.json")]
    if paifu_bottom is not None:
        args += [str(od / "paifu_rec.json"), str(paifu_bottom)]
    args += ["--sticks", STICKS, *extra]
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    (od / "stdout.txt").write_text(" ".join(args[1:]) + "\n" + p.stdout + p.stderr, encoding="utf-8", newline="\n")
    if p.returncode != 0:
        raise SystemExit(f"기록기 실패 {od}: {p.stdout}{p.stderr}")
    return jl(od / "dart_overlay.json"), p.stdout


# ---------------- 채점(heldout_1114.score 와 같은 규칙) ----------------
def is5(a, b):
    return bool(a and b and a != b and a[1] == b[1] and {a[0], b[0]} == {"0", "5"})


def score_round(pred, rd):
    per, tot, errs = {}, Counter(), []
    for s in SIDES:
        t = rd["truth"][s]
        rem = [x for x in pred[s]["slots"] if x["taken_at"] is None]
        pl = [x["tile"] for x in rem]
        c = Counter(truth=len(t), pred=len(pl))
        for i, j in align(t, pl):
            if i is not None and j is not None:
                if t[i] == pl[j]:
                    c["ok"] += 1
                else:
                    c["wrong"] += 1
                    if is5(t[i], pl[j]):
                        c["red5"] += 1
                    errs.append(f"{s} 정답{i + 1} {t[i]}→{pl[j]}(칸 {rem[j]['i']}, share {rem[j]['share']}, n {rem[j]['n']})")
            elif i is not None:
                c["missed"] += 1
                errs.append(f"{s} 빠짐 정답{i + 1} {t[i]}")
            else:
                c["extra"] += 1
                errs.append(f"{s} 헛것 {pl[j]}(칸 {rem[j]['i']}, {rem[j]['first_at']}~, share {rem[j]['share']}, n {rem[j]['n']})")
        sp = [k + 1 for k, x in enumerate(rem) if x["sideways"]]
        ts = rd["truth_sideways"][s]
        c["side_truth"] = len(ts)
        c["side_hit"] = len(set(sp) & set(ts))
        c["side_false"] = len(set(sp) - set(ts))
        c["taken"] = sum(1 for x in pred[s]["slots"] if x["taken_at"])
        per[s] = dict(c, sideways_pred=sp, sideways_truth=ts)
        tot.update(c)
    return per, dict(tot), errs


def bad(t):
    return t.get("wrong", 0) + t.get("extra", 0) + t.get("missed", 0)


# ---------------- 차례 규칙 엮임(interleave_check.py 와 같은 규칙) ----------------
def interleave(pred, dealer):
    seq = {s: pred[s]["slots"] for s in SIDES}
    p = {s: 0 for s in SIDES}
    cur, steps, notes = dealer, 0, []
    while p[cur] < len(seq[cur]):
        sl = seq[cur][p[cur]]
        p[cur] += 1
        steps += 1
        if sl.get("taken_at"):
            if sl.get("called_by"):
                cur = sl["called_by"]
                continue
            notes.append(f"가져간 자리 모르는 울려 나감 {cur} {sl['tile']}")
        cur = SIDES[(SIDES.index(cur) + 1) % 4]
    left = {s: len(seq[s]) - p[s] for s in SIDES}
    good = all(v == 0 for v in left.values())
    return dict(ok=good, steps=steps, total=sum(len(seq[s]) for s in SIDES), stuck_at=None if good else cur, left=left, notes=notes)


def five(pred):
    c = Counter()
    for s in SIDES:
        for x in pred[s]["slots"]:
            t = x["tile"]
            c[("5" + t[1]) if t[0] == "0" else t] += 1
    return {k: v for k, v in c.items() if v >= 5}


# ---------------- 검증 ----------------
def rescore():
    rounds = jl(HERE / "results" / "heldout_1114" / "rounds.json")
    summ = jl(HERE / "results" / "heldout_1114" / "summary.json")
    allok = True
    for k in VAL:
        per, tot, _ = score_round(jl(HERE / "results" / k / "dart_overlay.json"), rounds[k])
        ref = summ["rounds"][k]["total"]
        mine = {x: tot.get(x, 0) for x in ("truth", "pred", "ok", "wrong", "red5", "missed", "extra")}
        refd = {x: ref.get(x, 0) for x in mine}
        same = mine == refd
        allok &= same
        print(k, "이 채점", mine, "| summary.json", refd, "| 같음" if same else "| 다름")
    print("채점 옮김", "모두 같음" if allok else "다른 판 있음")
    return allok


def val():
    rounds = jl(HERE / "results" / "heldout_1114" / "rounds.json")
    res = {"_note": "2반장 검증 4판(방식 고르기용, 정확도 주장 아님 — 검증 판 프레임이 패 분류기 학습 v1114rec 에 쓰였을 수 있음). "
                    "기록기 = 지금 기본값(옵션 없음, 확정 안 된 칸 지우기 켬). track = 태블릿 추적 프레임(results/<키>/overlay_dump.json, 저장 격자 그대로 겹쳐 보기), "
                    "A · B · C = 헤드 녹화(headrec_dump.py, 줄 격자 264/783/259/777). 고르는 기준: 4판 합계 (틀린 종류 + 헛것 + 빠짐) 최소, 같으면 A → B → C.",
           "rescore_same_as_summary": rescore(), "rounds": {}, "total": {}}
    conds = {"track": None, **{m: METHOD[m] for m in "ABC"}}
    tot = {c: Counter() for c in conds}
    for k in VAL:
        rd = rounds[k]
        res["rounds"][k] = {}
        for c, m in conds.items():
            if c == "track":
                mode, dump, extra = "overlay", HERE / "results" / k / "overlay_dump.json", []
            else:
                mode, fn, extra = m
                dump = OUT / f"val_{k}" / fn
                if not dump.exists():
                    print(k, c, "dump 없음", dump)
                    continue
            pred, _ = replay(mode, dump, rd["dealer_side"], OUT / f"val_{k}" / f"rec_{c}", extra, paifu_bottom=rd["bottom"])
            per, t, errs = score_round(pred, rd)
            il = interleave(pred, rd["dealer_side"])
            nfr = len(jl(dump)["frames"])
            res["rounds"][k][c] = dict(total=t, per_side={s: {x: per[s].get(x, 0) for x in ("truth", "pred", "ok", "wrong", "missed", "extra", "taken")} | {"sideways_pred": per[s]["sideways_pred"], "sideways_truth": per[s]["sideways_truth"]} for s in SIDES},
                                       errors=errs, interleave=il, five=five(pred), frames=nfr)
            tot[c].update(t)
            print(f"{k} {c:5s} 프레임 {nfr:3d} | 맞음 {t.get('ok', 0)}/{t['truth']} 틀림 {t.get('wrong', 0)} 헛것 {t.get('extra', 0)} 빠짐 {t.get('missed', 0)} "
                  f"| 눕힘 {t.get('side_hit', 0)}/{t.get('side_truth', 0)} 헛눕힘 {t.get('side_false', 0)} | 울려나감 {t.get('taken', 0)} | 엮임 {'통과' if il['ok'] else '막힘 ' + str(il['left'])}")
            for e in errs:
                print("      ", e)
    for c in conds:
        t = dict(tot[c])
        t["bad"] = bad(t)
        res["total"][c] = t
    order = ["A", "B", "C"]
    pick = min((c for c in order if c in res["total"] and res["total"][c].get("truth")), key=lambda c: (res["total"][c]["bad"], order.index(c)))
    res["pick"] = pick
    print("합계")
    for c in conds:
        t = res["total"][c]
        print(f"  {c:5s} 맞음 {t.get('ok', 0)}/{t.get('truth', 0)} 틀림 {t.get('wrong', 0)}(적5 {t.get('red5', 0)}) 헛것 {t.get('extra', 0)} 빠짐 {t.get('missed', 0)} "
              f"→ 나쁨 {t['bad']} | 눕힘 {t.get('side_hit', 0)}/{t.get('side_truth', 0)} 헛눕힘 {t.get('side_false', 0)}")
    print("고른 방식", pick)
    wj(OUT / "val_summary.json", res)


# ---------------- 3반장 판 ----------------
def hms_s(h):
    a, b, c = h.split(":")
    return int(a) * 3600 + int(b) * 60 + float(c)


def side_str(slots):
    return " ".join(x["tile"] + ("*" if x["taken_at"] else "") + ("=" if x["sideways"] else "") for x in slots)


def river_check(rid, dump, pred, dealer, bottom_seat, il, out_jpg):
    from PIL import Image, ImageDraw, ImageFont

    last = dump["frames"][-1]
    im = Image.open(REC / last["file"]).convert("RGB")
    W, H = im.size
    PW = 1000
    can = Image.new("RGB", (W + PW, H), (250, 250, 250))
    can.paste(im, (0, 0))
    d = ImageDraw.Draw(can)
    f = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 30)
    fb = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 32)
    y = 20
    d.text((W + 20, y), f"{rid}  사진 {last['at'][11:23]} (공개 직전 마지막 프레임)", font=fb, fill=(0, 0, 0))
    y += 50
    d.text((W + 20, y), f"선 {KO.get(dealer, dealer)} · 엮임 {'통과' if il['ok'] else '막힘'} · * 울려 나감 · = 눕힘", font=f, fill=(60, 60, 60))
    y += 60
    for s in SIDES:
        sl = pred[s]["slots"]
        seat = (bottom_seat + SIDES.index(s)) % 4
        d.text((W + 20, y), f"{KO[s]}(자리 {seat}) {len(sl)}장", font=fb, fill=(150, 0, 0) if s == dealer else (0, 0, 120))
        y += 46
        toks = [x["tile"] + ("*" if x["taken_at"] else "") + ("=" if x["sideways"] else "") for x in sl]
        for i in range(0, len(toks), 9):
            d.text((W + 40, y), " ".join(toks[i:i + 9]), font=f, fill=(0, 0, 0))
            y += 42
        y += 18
    # 그림 위에 자리 이름
    for s, (x, yy) in {"bottom": (W // 2, H - 60), "top": (W // 2, 20), "left": (20, H // 2), "right": (W - 160, H // 2)}.items():
        d.text((x, yy), KO[s], font=fb, fill=(255, 255, 0), stroke_width=3, stroke_fill=(0, 0, 0))
    can.save(out_jpg, quality=90)


def play(method, ids, defs_path, bottom_seat):
    from headrec_dump import load_defs

    dfs = load_defs(defs_path)
    ids = ids or [k for k in dfs if not k.startswith("val_")]
    sp = OUT / "han3_summary.json"
    summ = jl(sp) if sp.exists() else {"_note": "3반장 판 헤드 녹화 → 버림 기록기(headrec_run.py play). 정답 없음 — 숫자는 검사(엮임 · 5장)뿐.", "rounds": {}}
    summ["method"] = method
    mode, fn, extra = METHOD[method]
    for rid in ids:
        d = dfs[rid]
        od = OUT / rid
        dump_p = od / fn
        if not dump_p.exists():
            print(rid, "dump 없음", dump_p)
            continue
        dump = jl(dump_p)
        p0, _ = replay(mode, dump_p, None, od / "rec_none", extra)
        firsts = {s: p0[s]["slots"][0]["first_at"] for s in SIDES if p0[s]["slots"]}
        cand = min(firsts, key=lambda s: firsts[s]) if firsts else None
        ties = [s for s in firsts if firsts[s] == firsts.get(cand)]
        note_fd = d.get("first_discard")
        dealer = cand
        pred, out = replay(mode, dump_p, dealer, od, extra, paifu_bottom=bottom_seat)
        # 기록기는 od/dart_overlay.json · dart_overlay_timeline.json · paifu_rec.json 을 쓴다
        il = interleave(pred, dealer)
        t_start = hms_s(d["t_start"]) if d.get("t_start") else None  # 판 정의의 첫 버림 · 진행 끝(있으면) — 의심 칸 · 참고 선 후보용
        t_end = hms_s(d["t_end_play"]) if d.get("t_end_play") else None
        # 참고 후보: 첫 버림(t_start) 1초 전보다 먼저 보인 칸은 빼고 가장 이른 자리(판 시작 전부터 있던 앞면을 칸으로 잡은 경우)
        cand_after = None
        if t_start is not None:
            fa2 = {}
            for s in SIDES:
                for x in p0[s]["slots"]:
                    if hms_s(x["first_at"]) >= t_start - 1:
                        fa2[s] = x["first_at"]
                        break
            cand_after = min(fa2, key=lambda s: fa2[s]) if fa2 else None
        alt = {}
        for tag, ad in (("note", note_fd), ("after_start", cand_after)):
            if ad and ad != cand and ad not in [a["dealer"] for a in alt.values()]:
                pa, _ = replay(mode, dump_p, ad, od / f"rec_dealer_{ad}", extra, paifu_bottom=bottom_seat)
                alt[tag] = dict(dealer=ad, interleave=interleave(pa, ad), rivers={s: side_str(pa[s]["slots"]) for s in SIDES})
        sus, melds = [], []
        for s in SIDES:
            sl = pred[s]["slots"]
            for k, x in enumerate(sl):
                why = []
                if x["share"] < 0.6:
                    why.append(f"share {x['share']}")
                if x["n"] <= 2:
                    why.append(f"n {x['n']}")
                later = max((y["n"] for y in sl[k + 1:]), default=0)
                if x["n"] > 2 and x["n"] < 0.3 * later:  # 뒤 칸보다 훨씬 적게 보임(먼저 놓인 칸은 더 오래 보여야 함)
                    why.append(f"n {x['n']} < 뒤 칸 최대 {later}의 30%")
                if x["taken_at"] and not x.get("called_by"):
                    why.append("울려 나갔는데 가져간 자리 없음")
                fa = hms_s(x["first_at"])
                if t_end is not None and fa > t_end + 1:
                    why.append(f"처음 본 때 {x['first_at']} > 진행 끝 {d['t_end_play'][:8]}")
                if t_start is not None and fa < t_start - 1:
                    why.append(f"처음 본 때 {x['first_at']} < 첫 버림 {d['t_start'][:8]}")
                if why:
                    sus.append(f"{s} 칸 {x['i']} {x['tile']}: " + ", ".join(why))
                if x.get("called_by") or x.get("meld") or x["taken_at"]:
                    melds.append(dict(side=s, i=x["i"], tile=x["tile"], taken_at=x["taken_at"], called_by=x.get("called_by"), meld=x.get("meld")))
        # 첫 몇 장 강 자리 확인: 첫 3프레임 겹쳐 보기의 river 역할 상자 수 · 리치봉 구역 바깥 띠 안 앞면 수(기록기 sightings 와 비슷)
        early = [dict(at=f["at"][11:23], river=sum(1 for t in f["tiles"] if t["r"] == "river"), faceup=len(f["tiles"])) for f in dump["frames"][:3]]
        paifu_chk = next((ln for ln in out.splitlines() if ln.startswith("패보")), None)
        river_check(rid, dump, pred, dealer, bottom_seat, il, od / "river_check.jpg")
        summ["rounds"][rid] = dict(
            dealer=dealer, dealer_candidate=cand, first_at=firsts, tie=ties if len(ties) > 1 else None, note_first_discard=note_fd,
            note_agrees=(note_fd == cand) if note_fd else None, dealer_candidate_after_start=cand_after, alt_dealers=alt,
            rivers={s: side_str(pred[s]["slots"]) for s in SIDES}, counts={s: len(pred[s]["slots"]) for s in SIDES},
            total=sum(len(pred[s]["slots"]) for s in SIDES), interleave=il, five=five(pred), melds=melds, suspicious=sus,
            early_frames=early, frames=len(dump["frames"]), paifu=paifu_chk, recorder_stdout=out.strip().splitlines()[-6:])
        r = summ["rounds"][rid]
        print(f"== {rid} 선 {dealer}(후보 {cand}, first_at {firsts}, note {note_fd}{' 같음' if r['note_agrees'] else (' 다름' if note_fd else '')}) 프레임 {r['frames']} 버림 {r['total']} {r['counts']}")
        for s in SIDES:
            print(f"   {s:6s} {r['rivers'][s]}")
        print(f"   엮임 {'통과' if il['ok'] else '막힘 ' + str(il['stuck_at']) + ' ' + str(il['left'])} {il['notes']} | 5장↑ {r['five'] or '없음'} | {paifu_chk}")
        print(f"   울기 {melds}")
        print(f"   의심 {sus}")
        print(f"   첫 프레임 {early}")
        for tag, a in alt.items():
            print(f"   {tag} 선 {a['dealer']} 로: 엮임 {'통과' if a['interleave']['ok'] else '막힘 ' + str(a['interleave']['left'])}")
    wj(sp, summ)


def main():
    a = sys.argv[1:]
    cmd = a[0]
    if cmd == "build":
        build()
    elif cmd == "rescore":
        rescore()
    elif cmd == "val":
        val()
    elif cmd == "play":
        defs_path, bs = HERE / "headrec_rounds.json", 0
        if "--defs" in a:
            i = a.index("--defs")
            defs_path = Path(a[i + 1])
            del a[i:i + 2]
        if "--bottom-seat" in a:
            i = a.index("--bottom-seat")
            bs = int(a[i + 1])
            del a[i:i + 2]
        play(a[1], a[2:], defs_path, bs)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
