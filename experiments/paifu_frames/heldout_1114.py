"""11-14 처음 보는 판(2·3반장, r11 제외)에서 판 중 버림 기록기 측정(2026-11-17).

  python -X utf8 heldout_1114.py survey   → 판 목록·격자·선 쪽·프레임 수 조사(results/heldout_1114/survey.json)
  python -X utf8 heldout_1114.py truth    → 정답 강(화료/끝 장면 라벨) → results/heldout_1114/truth_heldout.json, rounds.json
  python -X utf8 heldout_1114.py cmds     → 겹쳐 보기·재생 명령 출력
  python -X utf8 heldout_1114.py score    → results/<판>/dart_overlay.json 채점 → results/heldout_1114/summary.json

기록기·재생·겹쳐 보기·score.py 는 고치지 않는다(측정만).
"""
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "handtrack"))
from score import align  # noqa: E402
from paifu_export import order_river, side_boxes  # noqa: E402  (main() 은 __main__ 일 때만 돈다)

CAP = EXP / "visit_20261114" / "captures"
DR = EXP / "tile_classifier" / "data" / "v1114" / "dr" / "final"
OUT = HERE / "results" / "heldout_1114"
SIDES = ["bottom", "right", "top", "left"]

# rNN → 추적 폴더 시각(들)
ROUNDS = {
    "r08": ["125630"], "r09": ["125949"], "r10": ["130015"], "r12": ["131655"], "r13": ["132644"], "r14": ["133610"],
    "r15": ["134151"], "r16": ["135307", "135321"], "r17": ["140450"], "r18": ["141259"], "r19": ["142013"],
    "r20": ["143236"], "r21": ["144337"],
}


def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def track_info(hms):
    tr = CAP / f"20261114_{hms}_track"
    frames, metas = [], []
    for z in sorted(tr.glob("frames_*.zip")):
        zf = zipfile.ZipFile(z)
        m = json.loads(zf.read("frames.json"))
        metas.append({k: m.get(k) for k in ("round_key", "bottom_seat", "grid", "part")})
        for f in m["frames"]:
            from PIL import Image
            w, h = Image.open(io.BytesIO(zf.read(f["file"]))).size
            frames.append((f["at"][11:19], max(w, h)))
    return tr, frames, metas


def grids_c():
    g = {}
    for k in range(1, 5):
        for tn, v in jl(EXP / "tracking" / "results" / f"rounds2_1114_{k}.json").items():
            g.setdefault(tn, v)
    return g


def survey():
    gc = grids_c()
    caps = sorted(p.name for p in CAP.iterdir() if p.is_dir() and not p.name.endswith("_track"))
    res = {}
    for rn, hl in ROUNDS.items():
        for hms in hl:
            tr, frames, metas = track_info(hms)
            big = [f for f in frames if f[1] >= 1600]
            c = gc.get(tr.name, {})
            print(rn, tr.name, "프레임", len(frames), "2992:", len(big), frames[0][0] if frames else None, "~", frames[-1][0] if frames else None)
            for m in metas:
                print("   zip", m["part"], m["round_key"], "bottom", m["bottom_seat"], "grid sticks", m["grid"].get("sticks"))
            print("   C:", (c.get("C") or {}).get("grid", {}).get("sticks") if c else None, "win", c.get("win"), "winner", c.get("winner"), "captures", c.get("captures"), "riichi", c.get("truth_riichi"))
            res[tr.name] = dict(rn=rn, n=len(frames), n2992=len(big), t_first=frames[0][0] if frames else None,
                                t_last=frames[-1][0] if frames else None, metas=metas,
                                c_sticks=(c.get("C") or {}).get("grid", {}).get("sticks") if c else None)
    print("--- 사진(추적 아닌) 폴더 ---")
    for cn in caps:
        if cn < "20261114_125":
            continue
        d = CAP / cn
        meta = jl(d / "meta.json") if (d / "meta.json").exists() else {}
        lab = jl(d / "label.json") if (d / "label.json").exists() else None
        g = meta.get("game", {})
        lb = (lab or {}).get("label", lab) or {}
        print(cn, "round", g.get("round"), "dealer", g.get("dealer"), "bottom", g.get("bottom_seat"), "honba", g.get("honba"), "winner_side", meta.get("winner_side"),
              "| label:", {k: lb.get(k) for k in ("round", "winner", "loser", "is_tsumo", "riichi_seats", "win_tile")} if lab else None,
              "melds", lb.get("melds") if lab else None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "survey.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- 채점할 판(측정 전에 정함) ----------
# dealer_side = SIDES[(dealer - bottom_seat) % 4]. 화료 판은 captures/<화료>/meta.json, 유국 판은 round_key 의 국(동N·남N → 선 = N-1)과
# 앞 판 결과(자 화료·유국 → 선 넘어감)로 구한 값, 아래 note 에 근거.
EVAL = {
    "h12_131655": dict(rn="r12", track="131655", src="win", img="win_132536", cap="20261114_132536", dealer=1, bottom=2,
                       sticks=[425, 426, 619, 621], note="동2국 dealer 1 (meta)"),
    "h13_132644": dict(rn="r13", track="132644", src="frame", img="132644_f0187_133548", cap=None, dealer=2, bottom=2,
                       sticks=[424, 425, 618, 622], note="동3국 유국(133550_draw), 선 = 2(동2국은 자리 2 화료 → 선 넘어감). 정답 = 마지막 프레임 라벨 13:35:48"),
    "h14_133610": dict(rn="r14", track="133610", src="win", img="win_133905", cap="20261114_133905", dealer=3, bottom=2,
                       sticks=[424, 425, 618, 622], note="동4국 1본장 dealer 3 (meta). 강 11장뿐"),
    "h15_134151": dict(rn="r15", track="134151", src="frame", img="134151_f0225_135119", cap=None, dealer=0, bottom=2,
                       sticks=[424, 425, 618, 622], note="남1국 유국(135122_draw), 선 = 0. 정답 = 마지막 프레임 라벨 13:51:19 (라벨 flags occluded)"),
    "h16_135321": dict(rn="r16", track="135321", src="frame", img="135321_f0194_140257", cap=None, dealer=1, bottom=2,
                       sticks=[424, 425, 618, 622], note="남2국 1본장 유국(140300·140302_draw), 선 = 1(남2국 2본장 meta dealer 1 로 확인). 정답 = 마지막 프레임 라벨 14:02:57. 앞 3프레임 추적(135307)은 안 씀"),
    "h17_140450": dict(rn="r17", track="140450", src="win", img="win_141043", cap="20261114_141043", dealer=1, bottom=2,
                       sticks=[424, 425, 618, 622], note="남2국 2본장 dealer 1 (meta)"),
    "h18_141259": dict(rn="r18", track="141259", src="win", img="win_141910", cap="20261114_141910", dealer=2, bottom=2,
                       sticks=[424, 425, 618, 622], note="남3국 dealer 2 (meta)"),
    "h19_142013": dict(rn="r19", track="142013", src="win", img="win_142707", cap="20261114_142713", dealer=3, bottom=2,
                       sticks=[424, 425, 618, 622], note="남4국 dealer 3 (meta). 화료 사진 둘(142707·142713) 같은 탁자, 정답은 142707 라벨, label.json 은 142713"),
    "h20_143236": dict(rn="r20", track="143236", src="win", img="win_143404", cap="20261114_143404", dealer=0, bottom=0,
                       sticks=[424, 425, 618, 622], t1="14:34:04", note="3반장 동1국 dealer 0 (meta). 14:34:04 화료 뒤 프레임(다음 국)은 t1 로 자름. 강 20장"),
}
# 참고(합격 판정 밖): r08 은 카메라를 옮기는 중 녹화(프레임마다 격자 다름, 첫 프레임에 강 이미 55장), r10 은 r08 끝 탁자 그대로
REF = {
    "h08_125630": dict(rn="r08", track="125630", src="win", img="win_125839", cap="20261114_125931", dealer=0, bottom=0,
                       sticks=[355, 495, 562, 703], note="참고: 카메라 이동 중, C 격자 = 저장 격자"),
}


# 추적이 지난 국의 끝 탁자(강이 그대로 남은 상태)에서 시작한 판: 탁자가 비는 첫 프레임을 t0 로(한 추적 폴더에 두 국 → 시각으로 나눔).
# 나누지 않은 원래 길이(앱이 실제로 받은 그대로)도 "<판>full" 로 같이 잰다(합격 판정 밖, 따로 보고).
T0 = {"h12_131655": "13:17:04", "h14_133610": "13:36:16", "h19_142013": "14:19:54"}
for _k, _v in T0.items():
    EVAL[_k]["t0"] = _v
FULL = {k.replace("_", "full_", 1): dict(EVAL[k], note=EVAL[k]["note"] + " · t0 없이(지난 국 끝 탁자 포함)") for k in T0}
for _v in FULL.values():
    _v.pop("t0", None)


def cut():
    """원래 길이 겹쳐 보기(<판>full)에서 t0 이전 프레임을 뺀 것 = overlay_dump.py 를 t0 로 돌린 것과 같음(프레임마다 따로 계산)."""
    for k, t0 in T0.items():
        fk = k.replace("_", "full_", 1)
        src = HERE / "results" / fk / "overlay_dump.json"
        d = jl(src)
        d["frames"] = [f for f in d["frames"] if f["at"][11:19] >= t0]
        (HERE / "results" / k).mkdir(parents=True, exist_ok=True)
        (HERE / "results" / k / "overlay_dump.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        print(k, "t0", t0, "프레임", len(d["frames"]))


def dr_image(rn, track, img):
    p = next(DR.glob(f"{rn}_*.json"))
    d = jl(p)
    return next(im for im in d["images"] if im["id"].endswith("/" + img))


def truth_rivers(e):
    im = dr_image(e["rn"], e["track"], e["img"])
    out, used = {}, Counter()
    for s in SIDES:
        bs = side_boxes(im, "river", s)
        for b in bs:
            if not b.get("tile"):
                used["null"] += 1
                b = dict(b, tile=b.get("tile_draft"))
                used["tile_draft"] += 1
        out[s] = order_river([b if b.get("tile") else dict(b, tile=b.get("tile_draft")) for b in bs], s)
    melds = {s: [b["tile"] for b in side_boxes(im, "meld", s)] for s in SIDES}
    return out, melds, dict(used), im


def truth():
    res, rounds = {}, {}
    for name, e in {**EVAL, **FULL, **REF}.items():
        rv, melds, used, im = truth_rivers(e)
        dside = SIDES[(e["dealer"] - e["bottom"]) % 4]
        seq = [f"{s} {x['tile']}" for s in SIDES for x in rv[s]]
        ent = {"track": f"../visit_20261114/captures/20261114_{e['track']}_track", "seq": seq, "taken": []}
        if e.get("t1"):
            ent["t1"] = e["t1"]
        if e.get("t0"):
            ent["t0"] = e["t0"]
        res[name] = ent
        lab = None
        if e.get("cap") and (CAP / e["cap"] / "label.json").exists():
            lab = jl(CAP / e["cap"] / "label.json")
            lab = lab.get("label", lab)
        rs = None
        if lab:
            rs = sorted(SIDES[(s - e["bottom"]) % 4] for s in lab.get("riichi_seats", []))
        rounds[name] = dict(e, dealer_side=dside, truth={s: [x["tile"] for x in rv[s]] for s in SIDES},
                            truth_sideways={s: [i + 1 for i, x in enumerate(rv[s]) if x["sideways"]] for s in SIDES},
                            label_melds=melds, label_meld_str=(lab or {}).get("melds"), riichi_sides=rs, null_used=used,
                            img_flags=im.get("flags"), img_notes=im.get("review_notes"))
        print(name, "선", dside, "강", {s: len(rv[s]) for s in SIDES}, "합", sum(len(rv[s]) for s in SIDES), "null", used,
              "눕힘(라벨)", rounds[name]["truth_sideways"], "riichi(label)", rs, "울기 상자", {k: v for k, v in melds.items() if v})
        for s in SIDES:
            print("    ", s, " ".join(x["tile"] + ("*" if x["sideways"] else "") for x in rv[s]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "truth_heldout.json").write_text(json.dumps({"_note": "11-14 처음 보는 판(2·3반장, r11 제외). 정답 = 화료(또는 유국 판 마지막 프레임) 사진 라벨 v1114 dr/final 의 자리별 강(울려 나간 패 없음), 자리 사이 순서 없음(자리별로 이어 붙임) — heldout_1114.py truth", **res}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "rounds.json").write_text(json.dumps(rounds, ensure_ascii=False, indent=1), encoding="utf-8")


def cmds():
    for name, e in {**EVAL, **FULL, **REF}.items():
        ds = SIDES[(e["dealer"] - e["bottom"]) % 4]
        print(f"dart run experiments/paifu_frames/replay_recorder.dart overlay experiments/paifu_frames/results/{name}/overlay_dump.json {ds} "
              f"experiments/paifu_frames/results/{name}/dart_overlay.json --sticks {','.join(map(str, e['sticks']))}")


def overlay_at(dump, cx, cy, last_n=12):
    """정답 상자 중심(0~1)에 가장 가까운 겹쳐 보기 상자의 종류(t·tc)를 마지막 last_n 장 프레임에서 모음."""
    seen = []
    for f in dump["frames"][-last_n:]:
        if max(f["w"], f["h"]) < 1600:
            continue
        best = None
        for t in f["tiles"]:
            x, y, w, h = t["b"]
            d = ((x + w / 2 - cx) ** 2 + (y + h / 2 - cy) ** 2) ** 0.5
            if d < max(w, h) * 0.6 and (best is None or d < best[0]):
                best = (d, t)
        seen.append(None if best is None else (best[1]["t"], round(best[1]["tc"], 2), best[1]["r"]))
    return seen


def is5(a, b):
    return a and b and a != b and a[1] == b[1] and {a[0], b[0]} == {"0", "5"}


def score():
    rounds = jl(OUT / "rounds.json")
    summ = {"_note": "처음 보는 판 측정(2026-11-17). 정답 = 화료/끝 장면 라벨의 자리별 강(울려 나간 패 없음). 채점 = 기록기 slots 중 taken_at null 의 tile 목록과 편집 거리 정렬. 순서(켄달) 안 냄.",
            "sha1_8": {}, "rounds": {}, "total": {}, "full": {}, "ref": {}}
    tot = Counter()
    errors = []
    for name, rd in rounds.items():
        p = HERE / "results" / name / "dart_overlay.json"
        if not p.exists():
            print(name, "dart_overlay 없음")
            continue
        pred = jl(p)
        dump = jl(HERE / "results" / name / "overlay_dump.json")
        im = dr_image(rd["rn"], rd["track"], rd["img"])
        W = im.get("size", [2992, 2992])[0]
        lab_sorted = {}
        for s in SIDES:
            bs = side_boxes(im, "river", s)
            # order_river 와 같은 순서로 상자 자체를 얻기(중심 좌표용)
            o = order_river([dict(b, tile=(b["id"], b["tile"])) for b in bs], s)
            lab_sorted[s] = [next(b for b in bs if b["id"] == x["tile"][0]) for x in o]
        per = {}
        rc = Counter()
        n2992 = sum(1 for f in dump["frames"] if max(f["w"], f["h"]) >= 1600)
        for s in SIDES:
            t = rd["truth"][s]
            slots = pred[s]["slots"]
            rem = [x for x in slots if x["taken_at"] is None]
            pl = [x["tile"] for x in rem]
            c = Counter(truth=len(t), pred=len(pl))
            for i, j in align(t, pl):
                if i is not None and j is not None:
                    if t[i] == pl[j]:
                        c["ok"] += 1
                        continue
                    c["wrong"] += 1
                    kind = "적5↔5" if is5(t[i], pl[j]) else "종류"
                    if kind == "적5↔5":
                        c["red5"] += 1
                    b = lab_sorted[s][i]
                    ov = overlay_at(dump, b["rect"][0][0] / W, b["rect"][0][1] / W)
                    errors.append(dict(round=name, side=s, kind=kind, truth_pos=i + 1, truth=t[i], pred=pl[j], slot=rem[j],
                                       overlay_last=ov))
                elif i is not None:
                    c["missed"] += 1
                    b = lab_sorted[s][i]
                    ov = overlay_at(dump, b["rect"][0][0] / W, b["rect"][0][1] / W)
                    errors.append(dict(round=name, side=s, kind="빠짐", truth_pos=i + 1, truth=t[i], pred=None, overlay_last=ov))
                else:
                    c["extra"] += 1
                    errors.append(dict(round=name, side=s, kind="헛것", truth_pos=None, truth=None, pred=pl[j], slot=rem[j]))
            taken = [dict(i=x["i"], tile=x["tile"], first_at=x["first_at"], taken_at=x["taken_at"], n=x["n"]) for x in slots if x["taken_at"]]
            side_pred = [x["i"] for x in rem if x["sideways"]]
            side_pos_rem = [k + 1 for k, x in enumerate(rem) if x["sideways"]]
            per[s] = dict(c, taken=taken, sideways_slot=side_pred, sideways_pos_in_remaining=side_pos_rem,
                          truth_sideways_pos=rd["truth_sideways"][s])
            rc.update({k: v for k, v in c.items()})
        n_meld_boxes = sum(len(v) for v in rd["label_melds"].values())
        r = dict(dealer_side=rd["dealer_side"], sticks=rd["sticks"], frames2992=n2992, per_side=per, total=dict(rc),
                 taken_total=sum(len(per[s]["taken"]) for s in SIDES), label_meld_boxes=n_meld_boxes,
                 label_melds=rd["label_melds"], riichi_sides_label=rd["riichi_sides"],
                 sideways_sides_pred=[s for s in SIDES if per[s]["sideways_slot"]],
                 sideways_sides_truthlabel=[s for s in SIDES if rd["truth_sideways"][s]], note=rd["note"])
        key = "ref" if name in REF else ("full" if name in FULL else "rounds")
        summ[key][name] = r
        if name in EVAL:
            tot.update(rc)
        print(f"{name} 선 {rd['dealer_side']:6s} 프레임 {n2992:3d} | " + " | ".join(
            f"{s[0]} {per[s]['truth']}/{per[s].get('ok', 0)}/{per[s].get('missed', 0)}/{per[s].get('extra', 0)}"
            + (f" 틀림{per[s]['wrong']}" if per[s].get("wrong") else "") for s in SIDES)
              + f" | 합 {rc['truth']}/{rc.get('ok', 0)} 빠짐 {rc.get('missed', 0)} 헛것 {rc.get('extra', 0)} 틀림 {rc.get('wrong', 0)}"
              + f" | 울려나감 {r['taken_total']}(라벨 울기 상자 {n_meld_boxes}) | 눕힘 예측 {r['sideways_sides_pred']} 라벨 {r['sideways_sides_truthlabel']} riichi {rd['riichi_sides']}"
              + ("  [참고]" if name in REF else ("  [t0 없이]" if name in FULL else "")))
    nr = len(summ["rounds"])
    summ["total"] = dict(tot, rounds=nr, ok_rate=round(tot["ok"] / tot["truth"], 4) if tot["truth"] else None,
                         extra_per_round=round(tot["extra"] / nr, 2) if nr else None, missed_per_round=round(tot["missed"] / nr, 2) if nr else None)
    T = summ["total"]
    summ["verdict"] = {"a_ok_rate>=0.95": T["ok_rate"] is not None and T["ok_rate"] >= 0.95,
                       "b_extra_per_round<=1": T["extra_per_round"] is not None and T["extra_per_round"] <= 1,
                       "c_missed_per_round<=1": T["missed_per_round"] is not None and T["missed_per_round"] <= 1}
    # t0 없이(앱이 실제로 받은 그대로 — 지난 국 끝 탁자부터): 해당 판을 full 결과로 바꿔 낀 합계
    alt = Counter()
    for name in EVAL:
        fk = name.replace("_", "full_", 1)
        src = summ["full"].get(fk) if fk in summ["full"] else summ["rounds"].get(name)
        if src:
            alt.update(src["total"])
    summ["total_without_t0"] = dict(alt, rounds=nr, ok_rate=round(alt["ok"] / alt["truth"], 4) if alt["truth"] else None,
                                    extra_per_round=round(alt["extra"] / nr, 2) if nr else None,
                                    missed_per_round=round(alt["missed"] / nr, 2) if nr else None)
    summ["measured"] = {"start": "2026-11-17 13:45", "end": "2026-11-17 14:01", "sha1_8": {
        "lib/paifu/discard_recorder.dart": "fc86bcae", "replay_recorder.dart": "05228c27", "overlay_dump.py": "e8fb7c68", "score.py": "711e8ad2"},
        "sha1_same_at_start_and_end": True}
    summ["excluded"] = {
        "r09_125949": "추적 프레임 2장(12:59:46~52)뿐, r08 끝 탁자 그대로 — 화료 라벨 없음",
        "r10_130015": "r08 끝 탁자(강 61장)를 그대로 다시 찍은 것, 녹화 중 버림 없음",
        "r21_144337": "추적 프레임 12장(40초)뿐, 이 국의 끝 사진·라벨 없음(144647 화료는 그 뒤 다른 국이고 추적 없음)",
        "r16 앞 추적 135307": "3프레임, 같은 국의 135321 추적만 씀",
        "r08_125630": "참고로만 잼(판정 밖): 카메라를 옮기는 중 녹화(프레임마다 격자 다름), 첫 프레임에 이미 강 55장, 대국 id 가 2반장과 다름",
    }
    summ["errors"] = errors
    print("합계", T)
    print("t0 없이 합계", summ["total_without_t0"])
    print("판정", summ["verdict"])
    for e in errors:
        print(" ", json.dumps(e, ensure_ascii=False))
    (OUT / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    {"survey": survey, "truth": truth, "cmds": cmds, "score": score, "cut": cut}[sys.argv[1]]()
