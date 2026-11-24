"""앱 촬영 기록 → 한 반장의 판 목록 · 네 자리 버림 출처 · 판 결과(2026-11-24, 자동 패보 설계서 8-5 · 8-6 절 W1 · W2 · W3).

설계서 8-6 "원래 방식"(paifu_examples.py 머리말 — 버림 = 저장된 추적 프레임에 앱 기록기 재생, 결과 = label.json)을 자동 흐름의 입력으로 만든다.

  python -X utf8 experiments/paifu_frames/app_record.py collect  --captures <촬영 기록 폴더> --from HH:MM:SS --to HH:MM:SS [--date YYYY-MM-DD] [--out <app_rounds.json>]
  python -X utf8 experiments/paifu_frames/app_record.py collect  --hanchan <반장 설정 json> [--out …]          # 설정의 app_record 칸 · recording.date
  python -X utf8 experiments/paifu_frames/app_record.py build    --hanchan <반장 설정 json> --out <폴더> [--exe <replay_recorder.exe>] [--force-dump]
                                                                 # W1 + W2: <폴더>/app_rounds.json · <폴더>/app/<판>/(paifu_app.json · dart_app.json)
  python -X utf8 experiments/paifu_frames/app_record.py check-assets --rounds <app_rounds.json> [--assets assets/paifu] [--out <json>]   # 판 결과 ↔ 앱 예시
  python -X utf8 experiments/paifu_frames/app_record.py form-test --out <폴더> [--exe …]          # W2 ① 꼴 시험(대역 = results/h1x_*/paifu_rec.json 을 paifu.json 꼴로)
(저장소 루트에서. 읽기만 하는 폴더: 촬영 기록 · results/<키>/overlay_dump.json — 쓰는 곳은 --out 아래뿐)

W1 판 모으기(collect) — 촬영 기록 폴더의 `<YYYYMMDD_HHMMSS>[_draw|_track]` 중 날짜가 같고 폴더 시각이 [from, to] 인 것:
  - 화료 폴더: meta.json(game.round · honba · dealer · bottom_seat · names, merge, error) · label.json(대국에 반영 때 확정한 값) · paifu.json(있으면)
  - 유국 폴더(_draw): chosen.json(tenpai_seats · canceled_or_abortive) · reveal.json(round · honba · revealed) · paifu.json(있으면)
  - 추적 폴더(_track): frames_##.zip 의 frames.json(round_key "<대국 id>/<국 이름>/<본장>/<판 순번>", 프레임 시각 · bottom_seat · names)
  시각 순으로 이어진 같은 국 · 본장(국 이름의 첫 낱말 + 본장, 추적 폴더는 round_key 의 대국 id 도 같을 때)끼리 한 판으로 묶고,
  여러 폴더를 하나로 줄이는 규칙(REDUCE_RULE):
  - 화료: label.json 이 있는 것 중 마지막(폴더 시각) → 없으면 merge.winner 가 있는 것 중 마지막(결과 없음 표시) → 없으면 마지막.
  - 유국: chosen.json 이 있는 것 중 마지막 → 없으면 마지막(텐파이 모름).
  - 추적: 프레임 수가 가장 많은 것(같으면 뒤의 것). 다른 것은 dropped 에 까닭과 함께.
  - 한 판에 화료 폴더와 유국 폴더가 둘 다 있으면 label.json 이 있는 화료를 쓰고 경고.
  선(dealer): 화료 폴더 meta.json game.dealer. 유국 판은 국 이름에서(동/남 n국 → 자리 n−1 — 동1국 선이 자리 0 인 앱 자리 번호) · 앞뒤 판과 맞는지 검사.
  아래 자리: meta.json game.bottom_seat → 없으면 frames.json bottom_seat.
  닻 시각(태블릿 시계 — 헤드 녹화 시계와 다름, "근처" 만 가리킴): end = 화료 · 유국 폴더 시각(찍은 뒤 저장 시각, 공개보다 6 ~ 43초 늦음),
    end_saved = label.json · meta.json time, track_first/last = 추적 프레임 처음 · 끝, discard_first/last = 앱 버림 사건 at(W2 뒤).
  국 진행 검사: 앞 판 결과(화료자 · 텐파이)로 다음 국 · 본장을 셈해 앱 값과 다르면 warnings.

W2 네 자리 버림 출처(build): ① 판 폴더에 paifu.json → 그 사건(at 포함) ② 없고 추적 프레임 zip 이 있으면 앱 기록기(replay_recorder.exe overlay)를
  그 추적의 겹쳐 보기 출력에 재생(paifu_examples.replay 와 같은 인자: 선 쪽 · 아래 자리 · --sticks). 겹쳐 보기 출력은 results/<키>/overlay_dump.json 중
  프레임 이름이 그 추적 zip 에 있는 것 가운데 프레임이 가장 많은 것(2반장 = paifu_examples.GAMES 가 고른 키와 같음 — h12full · h14full · h19full),
  없으면 overlay_dump.py 와 같은 꼴로 zip 에서 새로 만든다(<out>/app/<판>/overlay_dump.json, ondevice 겹쳐 보기 — 판마다 1 ~ 3분).
  ③ 둘 다 없으면 헤드 녹화 재생(지금 흐름 — paifu_auto S3). --sticks 는 설정 app_record.sticks_by_track(추적 폴더 시각) → app_record.sticks → recorder.sticks.

W3 판 결과(result_read 꼴 — paifu_auto S5 ~ S9 가 읽는 꼴, results/han3_1123/RESULT_TASK.md): to_result_read(). 화료 = label.json 값(자리 → 사진 쪽),
  리치 칸(river_index) · 남은 강(rivers_final) · 울기의 준 자리는 W2 앱 사건에서. 유국 = chosen.json 텐파이 자리(공개 손패는 영상에서 — paifu_auto S4 꾸러미).
"""
from __future__ import annotations

import argparse
import copy
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RES = HERE / "results"
KST = timezone(timedelta(hours=9))
SIDES = ["bottom", "right", "top", "left"]
WINDS = ["동", "남", "서", "북"]
DEFAULT_STICKS = "424,425,618,622"
REDUCE_RULE = ("화료: label.json 있는 폴더 중 마지막 → 없으면 merge.winner 있는 것 중 마지막(결과 없음) → 없으면 마지막 · "
               "유국: chosen.json 있는 것 중 마지막 → 없으면 마지막 · 추적: 프레임 수 최대(같으면 뒤) · 화료 · 유국 폴더가 같이 있으면 label 있는 화료")


# ------------------------------------------------------------------ 작은 도구
def jl(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o, indent=1):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False, indent=indent))


def rel(p) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _p(v) -> Path:
    p = Path(v)
    return p if p.is_absolute() else ROOT / p


def norm(t):
    return ("5" + t[1]) if t and t[0] == "0" else t


def ms_of(date: str, hms: str) -> int:
    hh, mm, ss = hms.split(":")
    sec = float(ss)
    d = datetime(*map(int, date.split("-")), int(hh), int(mm), int(sec), round((sec - int(sec)) * 1e6), tzinfo=KST)
    return round(d.timestamp() * 1000)


def hms_of(ms: int, digits=1) -> str:
    d = datetime.fromtimestamp(ms / 1000, KST)
    if digits == 0:
        return d.strftime("%H:%M:%S")
    return d.strftime("%H:%M:%S") + "." + f"{d.microsecond:06d}"[:digits]


def iso_hms(iso: str) -> str:
    """'2026-11-14T13:16:38.304567' → '13:16:38.304'."""
    return iso[11:23] if len(iso) >= 23 else iso[11:19]


def side_of(seat: int, bottom: int) -> str:
    return SIDES[(seat - bottom) % 4]


def round_base(label: str) -> str:
    """'남2국 1본장' → '남2국'."""
    return (label or "").split()[0] if label else ""


def kyoku_index(base: str):
    """'남2국' → 4 + 1 = 5(동1국 = 0). 모르면 None."""
    if len(base) >= 3 and base[0] in WINDS and base.endswith("국") and base[1:-1].isdigit():
        return WINDS.index(base[0]) * 4 + int(base[1:-1]) - 1
    return None


def parse_meld(s) -> dict:
    """label.json 의 울기: '[5z 5z 5z]'(남의 패) · '(5z 5z 5z 5z)'(안깡) 또는 패 목록(paifu_examples.parse_meld 와 같은 규칙)."""
    if isinstance(s, list):
        tiles, closed = s, False
    else:
        closed = s.strip().startswith("(")
        tiles = s.strip("[]() ").split()
    same = all(t.replace("0", "5") == tiles[0].replace("0", "5") for t in tiles)
    kind = ("ankan" if closed else "kan") if len(tiles) == 4 else ("pon" if same else "chi")
    return {"kind": kind, "tiles": tiles}


# ------------------------------------------------------------------ W1 판 모으기
def _folder_time(name: str):
    """'20261114_131625[_draw|_track]' → ('20261114', '13:16:25', 꼬리)."""
    parts = name.split("_")
    if len(parts) < 2 or len(parts[0]) != 8 or len(parts[1]) != 6 or not (parts[0] + parts[1]).isdigit():
        return None
    t = parts[1]
    return parts[0], f"{t[:2]}:{t[2:4]}:{t[4:]}", (parts[2] if len(parts) > 2 else "")


def _read_folder(d: Path, kind: str) -> dict:
    it = {"folder": d.name, "kind": kind, "time": _folder_time(d.name)[1], "files": sorted(x.name for x in d.iterdir() if x.is_file())}
    for f in ("meta.json", "label.json", "chosen.json", "reveal.json", "paifu.json", "track.json"):
        if (d / f).exists():
            try:
                it[f.split(".")[0]] = jl(d / f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                it.setdefault("errors", []).append(f"{f}: {e}")
    if kind == "track":
        zs = []
        for z in sorted(d.glob("frames_*.zip")):
            try:
                m = json.loads(zipfile.ZipFile(z).read("frames.json"))
            except (KeyError, zipfile.BadZipFile, json.JSONDecodeError) as e:
                it.setdefault("errors", []).append(f"{z.name}: {e}")
                continue
            fr = m.get("frames") or []
            zs.append({"zip": z.name, "round_key": m.get("round_key"), "part": m.get("part"), "reason": m.get("reason"), "n": len(fr),
                       "first": fr[0]["at"] if fr else None, "last": fr[-1]["at"] if fr else None, "files": [f["file"] for f in fr],
                       "bottom_seat": m.get("bottom_seat"), "names": m.get("names"), "grid": m.get("grid")})
        it["zips"] = zs
    # 국 · 본장 열쇠
    key, label, gid = None, None, None
    if kind == "win":
        src = it.get("label") or (it.get("meta") or {}).get("game") or {}
        label = src.get("round")
        honba = src.get("honba")
        if label is not None and honba is not None:
            key = (round_base(label), int(honba))
    elif kind == "draw":
        src = it.get("reveal") or it.get("paifu") or {}
        label = src.get("round")
        honba = src.get("honba")
        if label is not None and honba is not None:
            key = (round_base(label), int(honba))
    else:
        rk = next((z["round_key"] for z in it.get("zips") or [] if z.get("round_key")), None)
        if rk:
            ps = rk.split("/")
            if len(ps) >= 3:
                gid, label = ps[0], ps[1]
                key = (round_base(label), int(ps[2]))
        elif it.get("track"):
            label = it["track"].get("round")
            key = (round_base(label), 0) if label else None
    it["key"], it["round_label"], it["game_key"] = key, label, gid
    return it


def scan(captures: Path, date: str, t_from: str, t_to: str) -> list:
    """[from, to] 안 촬영 기록 폴더들(시각 순)."""
    ymd = date.replace("-", "")
    out = []
    for d in sorted(captures.iterdir()):
        if not d.is_dir():
            continue
        ft = _folder_time(d.name)
        if not ft or ft[0] != ymd or not (t_from <= ft[1] <= t_to):
            continue
        tail = ft[2]
        kind = {"": "win", "draw": "draw", "track": "track"}.get(tail)
        if kind is None:
            continue
        out.append(_read_folder(d, kind))
    return out


def _pick_end(wins: list, draws: list, warn: list):
    """같은 판의 화료 · 유국 폴더 → (고른 것, 끝 종류, 고른 까닭, dropped)."""
    dropped = []
    w_lab = [w for w in wins if w.get("label")]
    w_mer = [w for w in wins if ((w.get("meta") or {}).get("merge") or {}).get("winner") is not None]
    d_ch = [d for d in draws if d.get("chosen")]
    if wins and draws:
        warn.append(f"한 판에 화료 폴더 {[w['folder'] for w in wins]} 와 유국 폴더 {[d['folder'] for d in draws]} 가 같이 있음 — label 있는 화료를 씀")
    if w_lab:
        pick, end, why = w_lab[-1], "win", "label.json 있는 화료 폴더 중 마지막"
    elif draws and d_ch:
        pick, end, why = d_ch[-1], "draw", "chosen.json 있는 유국 폴더 중 마지막"
    elif w_mer:
        pick, end, why = w_mer[-1], "win", "label.json 없음 — merge.winner 있는 화료 폴더 중 마지막(결과 없음)"
    elif wins:
        pick, end, why = wins[-1], "win", "label.json · merge.winner 없음 — 마지막 화료 폴더(결과 없음)"
    elif draws:
        pick, end, why = draws[-1], "draw", "chosen.json 없음 — 마지막 유국 폴더(텐파이 모름)"
    else:
        return None, "unknown", "화료 · 유국 폴더 없음", dropped
    for x in wins + draws:
        if x is pick:
            continue
        if x.get("kind") == "win":
            r = "label.json 없음" if not x.get("label") else "같은 국의 뒤 화료 폴더가 있음"
            if (x.get("meta") or {}).get("error"):
                r += f" · meta.error {x['meta']['error']}"
        else:
            r = "chosen.json 없음" if not x.get("chosen") else "같은 국의 뒤 유국 폴더가 있음"
        dropped.append({"folder": x["folder"], "why": r})
    return pick, end, why, dropped


def _app_result(end: str, pick: dict | None, bottom: int):
    """앱 값(자리 번호) — 화료 = label.json, 유국 = chosen.json."""
    if pick is None:
        return None, None
    if end == "win":
        lab = pick.get("label")
        if not lab:
            mg = (pick.get("meta") or {}).get("merge") or {}
            return ({"type": None, "winner": mg.get("winner"), "recorded": False,
                     "note": "label.json 없음(대국에 반영 안 함) — 화료자만 meta.merge 에서, 끝 손패 · 표시패는 쓰지 않음"}, None)
        closed = list(lab["closed"])
        return ({"type": "tsumo" if lab["is_tsumo"] else "ron", "winner": lab["winner"], "loser": lab.get("loser"),
                 "win_tile": lab["win_tile"], "closed": closed, "hand": closed[:-1] if closed and closed[-1] == lab["win_tile"] else None,
                 "melds_raw": list(lab.get("melds") or []), "melds": [parse_meld(m) for m in lab.get("melds") or []],
                 "riichi": bool(lab.get("riichi")), "riichi_seats": list(lab.get("riichi_seats") or []), "red_count": lab.get("red_count"),
                 "dora_indicators": list(lab.get("dora_indicators") or []), "ura_indicators": list(lab.get("ura_indicators") or []),
                 "recorded": True}, "label.json")
    ch = pick.get("chosen")
    rv = pick.get("reveal") or {}
    if not ch:
        return {"type": "draw", "tenpai": None, "revealed_sides": rv.get("revealed"), "recorded": False}, None
    return ({"type": "draw", "tenpai": sorted(int(s) for s in ch.get("tenpai_seats") or []), "canceled_or_abortive": bool(ch.get("canceled_or_abortive")),
             "revealed_sides": list(rv.get("revealed") or []), "tenpai_sides": [side_of(int(s), bottom) for s in sorted(ch.get("tenpai_seats") or [])],
             "recorded": True}, "chosen.json")


def collect(captures, date: str, t_from: str, t_to: str, ids: list | None = None, id_prefix: str = "a") -> dict:
    """W1: 촬영 기록 폴더 → 판 목록(시간 순). ids 를 주면 판 id 를 그 순서로(수가 다르면 warnings)."""
    captures = _p(captures)
    items = scan(captures, date, t_from, t_to)
    # 이어진 폴더끼리 묶는다: 국 · 본장이 바뀌거나, 추적 폴더의 대국 id(round_key 첫 칸)가 바뀌면 새 판(같은 국 · 본장이 떨어져 다시 나오면 경고)
    groups, loose, seen = [], [], set()
    for it in items:
        k = it["key"]
        if k is None:
            loose.append({"folder": it["folder"], "why": "국 · 본장을 못 읽음"})
            continue
        cur = groups[-1] if groups else None
        cur_gk = next((x["game_key"] for x in cur[1] if x.get("game_key")), None) if cur else None
        if cur is None or cur[0] != k or (it.get("game_key") and cur_gk and it["game_key"] != cur_gk):
            groups.append((k, [it], []))
            if k in seen:
                groups[-1][2].append(f"같은 국 · 본장 {k} 이 앞에서 끊겼다가 다시 나옴(다른 대국 · 다시 찍기?) — 따로 한 판으로 둠")
            seen.add(k)
        else:
            cur[1].append(it)
    # 아래 자리: 판 안 meta.json game.bottom_seat → frames.json bottom_seat → 없으면(유국 폴더 · paifu.json 만 있는 판) 가장 가까운 판의 값
    def bottom_of(g):
        for x in g:
            b = ((x.get("meta") or {}).get("game") or {}).get("bottom_seat")
            if b is not None:
                return b
        for x in g:
            for z in x.get("zips") or []:
                if z.get("bottom_seat") is not None:
                    return z["bottom_seat"]
        return None
    bottoms = [bottom_of(g) for _, g, _ in groups]
    known = [i for i, b in enumerate(bottoms) if b is not None]
    rounds = []
    for gi, (k, g, warn0) in enumerate(groups):
        warn = list(warn0)
        tracks = [x for x in g if x["kind"] == "track"]
        wins = [x for x in g if x["kind"] == "win"]
        draws = [x for x in g if x["kind"] == "draw"]
        track = max(tracks, key=lambda x: (sum(z["n"] for z in x.get("zips") or []), x["time"])) if tracks else None
        pick, end, why, dropped = _pick_end(wins, draws, warn)
        for t in tracks:
            if t is not track:
                dropped.append({"folder": t["folder"], "why": f"같은 국의 다른 추적 폴더가 프레임이 더 많음({sum(z['n'] for z in t.get('zips') or [])} < "
                                                          f"{sum(z['n'] for z in track.get('zips') or [])})"})
        meta_game = ((pick or {}).get("meta") or {}).get("game") or {}
        z0 = (track or {}).get("zips") or [{}]
        bottom, bottom_src = bottoms[gi], "meta.json game.bottom_seat · frames.json bottom_seat"
        if bottom is None and known:
            j = min(known, key=lambda j: (abs(j - gi), j))
            bottom, bottom_src = bottoms[j], f"이 판 폴더에 없음 — 가장 가까운 판({groups[j][1][0]['folder']})의 값"
            warn.append(f"아래 자리를 이웃 판에서 가져옴({bottom})")
        elif bottom is None:
            bottom, bottom_src = 0, "모름 — 0"
            warn.append("아래 자리를 몰라 0 으로 둠")
        ki = kyoku_index(k[0])
        dealer = meta_game.get("dealer")
        dealer_src = "meta.json game.dealer"
        if dealer is None:
            dealer = (ki % 4) if ki is not None else None
            dealer_src = "국 이름(동/남 n국 → 자리 n−1)"
        elif ki is not None and dealer != ki % 4:
            warn.append(f"meta 선 {dealer} ≠ 국 이름의 선 {ki % 4}")
        res, res_src = _app_result(end, pick, bottom)
        label = (pick or {}).get("label") or {}
        tfirst = min((z["first"] for z in (track or {}).get("zips") or [] if z.get("first")), default=None)
        tlast = max((z["last"] for z in (track or {}).get("zips") or [] if z.get("last")), default=None)
        paifu_json = next((x["folder"] for x in ([pick] if pick else []) + [x for x in g if x is not pick] if x and x.get("paifu")), None)
        rounds.append({
            "id": None, "round": k[0], "honba": k[1], "round_label": (pick or track or {}).get("round_label") or k[0],
            "kyoku_index": ki, "dealer": dealer, "dealer_source": dealer_src, "bottom_seat": bottom, "bottom_source": bottom_src,
            "dealer_side": side_of(dealer, bottom) if dealer is not None else None,
            "names": meta_game.get("names") or z0[0].get("names") or (track or {}).get("track", {}).get("names"),
            "game_key": (track or {}).get("game_key"), "end": end, "result": res, "result_source": res_src,
            "anchors": {"end": (pick or {}).get("time"), "end_folder": (pick or {}).get("folder"),
                        "end_saved": iso_hms(label["time"]) if label.get("time") else (iso_hms(pick["meta"]["time"]) if pick and (pick.get("meta") or {}).get("time") else None),
                        "track_folder": (track or {}).get("time"), "track_first": iso_hms(tfirst) if tfirst else None, "track_last": iso_hms(tlast) if tlast else None,
                        "note": "태블릿 시계. end = 화료 · 유국 폴더 시각(공개보다 늦음), end_saved = label · meta time(저장 시각)"},
            "folders": {"track": (track or {}).get("folder"), "end": (pick or {}).get("folder"), "end_pick_rule": why,
                        "all": [x["folder"] for x in g], "dropped": dropped},
            "track": {"zips": len((track or {}).get("zips") or []), "frames": sum(z["n"] for z in (track or {}).get("zips") or []),
                      "grid": z0[0].get("grid")} if track else None,
            "discard_source": {"paifu_json": paifu_json, "track_zips": len((track or {}).get("zips") or []),
                               "available": [x for x, ok in (("paifu_json", bool(paifu_json)), ("track_replay", bool(track and track.get("zips"))), ("headrec", True)) if ok],
                               "chosen": "paifu_json" if paifu_json else ("track_replay" if track and track.get("zips") else "headrec")},
            "warnings": warn})
    # 국 진행 검사(앞 판 결과로 다음 국 · 본장)
    for a, b in zip(rounds, rounds[1:]):
        want = _next_round(a)
        if want and (want[0], want[1]) != (b["kyoku_index"], b["honba"]):
            b["warnings"].append(f"국 진행: 앞 판({a['round_label']}) 결과로는 {_kyoku_name(want[0])} {want[1]}본장이어야 하는데 {b['round_label']}")
    # 판 id
    top_warn = []
    if ids is not None:
        if len(ids) != len(rounds):
            top_warn.append(f"설정 games {len(ids)}판 ≠ 촬영 기록 판 {len(rounds)}판 — 앞에서부터 짝지음")
        for r, gid in zip(rounds, ids):
            r["id"] = gid
            tf = r["folders"]["track"]
            if tf and gid.split("_")[-1] != tf.split("_")[1]:
                r["warnings"].append(f"판 id {gid} 의 시각 ≠ 추적 폴더 시각 {tf.split('_')[1]}")
    for i, r in enumerate(rounds):
        if r["id"] is None:
            tf = r["folders"]["track"] or r["folders"]["end"] or ""
            r["id"] = f"{id_prefix}{i + 1:02d}_{tf.split('_')[1] if '_' in tf else i}"
    return {"_note": "app_record.py collect(W1) — 촬영 기록 → 판 목록. 시각은 태블릿 시계(닻)", "made": datetime.now().isoformat(timespec="seconds"),
            "captures": rel(captures), "date": date, "from": t_from, "to": t_to, "reduce_rule": REDUCE_RULE,
            "rounds": rounds, "loose": loose, "warnings": top_warn}


def _kyoku_name(ki):
    return f"{WINDS[ki // 4]}{ki % 4 + 1}국"


def _next_round(a: dict):
    """앞 판 → (다음 kyoku_index, 본장). 친 화료 · 유국 친 텐파이면 연장(본장 + 1), 유국이면 본장 + 1, 그 밖은 다음 국 0본장. 모르면 None."""
    res = a.get("result") or {}
    if a.get("kyoku_index") is None or a.get("dealer") is None:
        return None
    if a["end"] == "win" and res.get("winner") is not None:
        return (a["kyoku_index"], a["honba"] + 1) if res["winner"] == a["dealer"] else (a["kyoku_index"] + 1, 0)
    if a["end"] == "draw" and res.get("tenpai") is not None:
        return (a["kyoku_index"], a["honba"] + 1) if a["dealer"] in res["tenpai"] else (a["kyoku_index"] + 1, a["honba"] + 1)
    return None


# ------------------------------------------------------------------ W2 네 자리 버림
def find_overlay_dump(captures: Path, track_folder: str) -> list:
    """results/<키>/overlay_dump.json 중 프레임 이름이 그 추적 zip 에 모두 있는 것 — [(프레임 수, 경로)] 많은 순."""
    names = set()
    for z in sorted((captures / track_folder).glob("frames_*.zip")):
        names |= {n for n in zipfile.ZipFile(z).namelist() if n.endswith(".jpg")}
    out = []
    for f in sorted(RES.glob("*/overlay_dump.json")):
        try:
            o = jl(f)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        fr = [x.get("file") for x in o.get("frames") or []]
        if fr and all(x in names for x in fr):
            out.append((len(fr), f))
    out.sort(key=lambda x: (-x[0], str(x[1])))
    return out


def make_overlay_dump(captures: Path, track_folder: str, out: Path):
    """overlay_dump.py 와 같은 꼴(t · tc + read_small t2 · tc2)로 추적 zip 의 프레임 전부를 겹쳐 보기 → out(ondevice, 판마다 1 ~ 3분)."""
    sys.path.insert(0, "C:/Users/jjh7757/dev/mahjong-recognizer")
    sys.path.append(str(ROOT / "android/app/src/main/python"))
    import ondevice  # noqa: E402
    import numpy as np  # noqa: E402
    from PIL import Image  # noqa: E402
    reader = ondevice._get_reader()
    frames, grid = [], None
    for z in sorted((captures / track_folder).glob("frames_*.zip")):
        zf = zipfile.ZipFile(z)
        meta = json.loads(zf.read("frames.json"))
        grid = grid or meta["grid"]
        for f in meta["frames"]:
            raw = zf.read(f["file"])
            q = {k: str(meta["grid"][k]) for k in ("x1", "x2", "y1", "y2")}
            o = json.loads(ondevice.overlay(raw, q))
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            W, H = im.size
            rgb = np.asarray(im)
            for t in o["tiles"]:
                x, y, w, h = t["b"]
                t["t2"], t["tc2"] = reader.read_small(rgb, (round(x * W), round(y * H), round(w * W), round(h * H)))
            frames.append({"file": f["file"], "at": f["at"], "w": W, "h": H, "tiles": o["tiles"], "ms": o["ms"]})
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"grid": grid, "frames": frames}, ensure_ascii=False), encoding="utf-8", newline="\n")
    return len(frames)


def replay_track(exe: Path, dump: Path, dealer_side: str, bottom: int, sticks: str, od: Path) -> dict:
    """앱 기록기 재생(paifu_examples.replay 와 같은 인자, 옵션 없음 = 기록기 기본값) → od/dart_app.json(+ _timeline) · od/paifu_app.json · stdout.txt."""
    od.mkdir(parents=True, exist_ok=True)
    args = [str(exe), "overlay", str(dump), dealer_side or "none", str(od / "dart_app.json"), str(od / "paifu_app.json"), str(bottom), "--sticks", sticks]
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (od / "stdout.txt").write_bytes((" ".join(args[1:]) + "\n" + p.stdout + p.stderr).encode("utf-8"))
    if p.returncode != 0 or not (od / "paifu_app.json").exists():
        raise SystemExit(f"앱 기록기 재생 실패 {od}: {p.stdout[-800:]}{p.stderr[-800:]}")
    return jl(od / "paifu_app.json")


def ensure_exe(exe: Path, candidates: list) -> Path:
    """exe 가 없으면 후보(기존 실행 폴더의 _bin)에서 mtime 째 복사(headrec_run.build 가 다시 빌드하지 않게)."""
    if exe.exists():
        return exe
    for c in candidates:
        c = Path(c)
        if c.exists():
            exe.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(c, exe)
            return exe
    raise SystemExit(f"기록기 exe 없음: {exe} (후보 {candidates}) — headrec_run.py build --hanchan … 로 만들 것")


def discard_summary(events: list) -> dict:
    """앱 버림 사건 → 수 · 처음 · 끝 at(ms) · 자리별 수 · 울기 · 리치 자리."""
    dis = [e for e in events if e.get("type") == "discard"]
    ats = [e["at"] for e in dis if e.get("at") is not None]
    return {"discards": len(dis), "calls": sum(1 for e in events if e.get("type") == "call"),
            "per_seat": dict(Counter(e["seat"] for e in dis)), "riichi_seats": sorted({e["seat"] for e in dis if e.get("riichi")}),
            "has_at": len(ats) == len(dis) and bool(dis), "first_at_ms": min(ats) if ats else None, "last_at_ms": max(ats) if ats else None}


def build(cfg_raw: dict, out: Path, exe: Path | None = None, exe_candidates=(), force_dump=False, log=print) -> dict:
    """W1 + W2: out/app_rounds.json · out/app/<판>/(paifu_app.json · dart_app.json). cfg_raw = 반장 설정(dict) — app_record · games · recording."""
    ar = cfg_raw["app_record"]
    date = ar.get("date") or (cfg_raw.get("recording") or {}).get("date")
    caps = _p(ar["captures"])
    o = collect(caps, date, ar["from"], ar["to"], ids=list(cfg_raw.get("games") or []) or None, id_prefix=ar.get("id_prefix", "a"))
    sticks_default = ar.get("sticks") or (cfg_raw.get("recorder") or {}).get("sticks") or DEFAULT_STICKS
    by_track = ar.get("sticks_by_track") or {}
    for r in o["rounds"]:
        src = r["discard_source"]
        od = out / "app" / r["id"]
        if src["chosen"] == "paifu_json":
            pj = jl(caps / src["paifu_json"] / "paifu.json")
            od.mkdir(parents=True, exist_ok=True)
            wj(od / "paifu_app.json", pj)
            src.update(used="paifu_json", file=rel(caps / src["paifu_json"] / "paifu.json"), summary=discard_summary(pj.get("events") or []),
                       paifu_dealer=pj.get("dealer"), paifu_round=pj.get("round"), paifu_honba=pj.get("honba"))
            if pj.get("dealer") is not None and r["dealer"] is not None and pj["dealer"] != r["dealer"]:
                r["warnings"].append(f"paifu.json 선 {pj['dealer']} ≠ 판 선 {r['dealer']}")
        elif src["chosen"] == "track_replay":
            if exe is None:
                src["used"] = None
                src["note"] = "collect 만 — 재생 안 함(build 에서)"
                continue
            ensure_exe(exe, list(exe_candidates))
            tf = r["folders"]["track"]
            cands = [] if force_dump else find_overlay_dump(caps, tf)
            if cands:
                dump, how = cands[0][1], f"있는 겹쳐 보기 출력 {rel(cands[0][1])}(프레임 {cands[0][0]}, 후보 {len(cands)})"
            else:
                dump = od / "overlay_dump.json"
                if not dump.exists():
                    log(f"{r['id']}: 겹쳐 보기 출력이 없어 추적 zip 에서 새로 만듦 → {rel(dump)}")
                    make_overlay_dump(caps, tf, dump)
                how = f"추적 zip 에서 새로 만든 {rel(dump)}"
            st = by_track.get(tf.split("_")[1], sticks_default)
            pj = replay_track(exe, dump, r["dealer_side"], r["bottom_seat"], st, od)
            src.update(used="track_replay", dump=rel(dump), dump_how=how, dump_candidates=[{"frames": n, "file": rel(f)} for n, f in cands],
                       sticks=st, dealer_side=r["dealer_side"], bottom_seat=r["bottom_seat"], summary=discard_summary(pj.get("events") or []),
                       check=next((ln for ln in (od / "stdout.txt").read_text(encoding="utf-8").splitlines() if ln.startswith("패보")), None))
        else:
            src["used"] = "headrec"
            src["note"] = "앱 버림 기록 없음 — 헤드 녹화 재생(paifu_auto S3)"
        sm = src.get("summary") or {}
        r["anchors"]["discard_first"] = hms_of(sm["first_at_ms"]) if sm.get("first_at_ms") else None
        r["anchors"]["discard_last"] = hms_of(sm["last_at_ms"]) if sm.get("last_at_ms") else None
        if r["end"] == "win" and (r.get("result") or {}).get("riichi_seats") is not None and sm:
            lab_r = sorted(r["result"]["riichi_seats"])
            if lab_r != sm.get("riichi_seats"):
                r["warnings"].append(f"label riichi_seats {lab_r} ≠ 앱 버림 리치 표시 자리 {sm.get('riichi_seats')}")
    o["_note"] = "app_record.py build(W1 + W2) — 촬영 기록 → 판 목록 + 네 자리 버림 출처. 시각은 태블릿 시계(닻)"
    wj(out / "app_rounds.json", o)
    return o


def app_events(out: Path, gid: str):
    f = out / "app" / gid / "paifu_app.json"
    return jl(f)["events"] if f.exists() else None


# ------------------------------------------------------------------ W3 판 결과(result_read 꼴)
def rivers_from_events(events: list, bottom: int) -> tuple[dict, dict]:
    """앱 사건 → (자리 쪽별 남은 강 [패], 자리 쪽별 리치 칸 river_index(남은 강 기준 1부터, 리치 패가 울려 나갔으면 None))."""
    river = {s: [] for s in SIDES}
    riichi = {}
    last = {}
    for e in events:
        if e["type"] == "discard":
            s = side_of(e["seat"], bottom)
            river[s].append({"tile": e["tile"], "riichi": bool(e.get("riichi")), "taken": False})
            last[e["seat"]] = river[s][-1]
        elif e["type"] == "call" and e.get("from") is not None and e.get("from") != e["seat"]:
            x = last.get(e["from"])
            if x is not None:
                x["taken"] = True
    out = {}
    for s in SIDES:
        rem = [x for x in river[s] if not x["taken"]]
        out[s] = [x["tile"] for x in rem]
        for k, x in enumerate(river[s]):
            if x["riichi"]:
                riichi[s] = (rem.index(x) + 1) if x in rem else None
    return out, riichi


def to_result_read(r: dict, events: list | None) -> dict | None:
    """앱 판 결과 → result_read.json 꼴(paifu_auto S5 ~ S9). 화료 = label.json 이 있을 때만, 유국 = 텐파이 자리만(공개 손패 없음)."""
    res = r.get("result") or {}
    b = r["bottom_seat"]
    if r["end"] == "win" and not res.get("recorded"):
        return None
    rivers, ri_idx = rivers_from_events(events, b) if events else ({s: None for s in SIDES}, {})
    base = {"id": r["id"], "_source": f"app_record({r.get('result_source')} {r['folders']['end']} · 버림 {('app/' + r['id'] + '/paifu_app.json') if events else '없음'})",
            "dealer_side": r["dealer_side"], "dealer_evidence": f"앱 {r['dealer_source']} = 자리 {r['dealer']}(아래 자리 {b})",
            "round": r["round_label"], "honba": r["honba"], "dora_evidence": "앱 기록", "rivers_final": rivers,
            "rivers_final_source": "앱 버림 기록(W2 — 울려 나간 패 뺌)" if events else None, "uncertain": []}
    if r["end"] == "win":
        w = res["winner"]
        melds_out = {s: [] for s in SIDES}
        ws = side_of(w, b)
        calls = [e for e in events or [] if e["type"] == "call" and e["seat"] == w]
        for m in res.get("melds") or []:
            fs, ct = None, None
            for e in calls:
                et = [norm(t) for t in e.get("tiles") or []]
                if et and all(t in [norm(x) for x in m["tiles"]] for t in et) and e.get("from") is not None and e["from"] != w:
                    fs, ct = side_of(e["from"], b), (e["tiles"][0] if e.get("kind") == "call" or len(e.get("tiles") or []) == 1 else None)
                    break
            melds_out[ws].append({"kind": m["kind"], "tiles": list(m["tiles"]), "from_side": fs, "called_tile": ct})
        riichi = [{"side": side_of(s, b), "river_index": ri_idx.get(side_of(s, b)), "time": None,
                   "source": "label riichi_seats" + ("" if ri_idx.get(side_of(s, b)) else " — 앱 버림에 리치 표시 칸 없음(칸 모름)")}
                  for s in sorted(res.get("riichi_seats") or [])]
        return {**base, "end": "win", "winner_side": ws, "win_type": res["type"], "loser_side": side_of(res["loser"], b) if res.get("loser") is not None else None,
                "win_evidence": f"앱 label.json({r['folders']['end']}) — 대국에 반영 때 확정", "win_tile": res["win_tile"], "hand": res["hand"],
                "hand_standing_note": "앱 label closed 순서(마지막 = 화료패)", "melds": melds_out, "riichi": riichi,
                "dora_indicators": list(res.get("dora_indicators") or []), "ura_indicators": list(res.get("ura_indicators") or []),
                "tenpai_revealed": [], "sticks_note": "앱 기록에 없음", "last_tile": None}
    tp = res.get("tenpai")
    return {**base, "end": "draw", "winner_side": None, "win_type": None, "loser_side": None, "win_tile": None, "hand": None,
            "melds": {s: [] for s in SIDES}, "riichi": [{"side": s, "river_index": i, "time": None, "source": "앱 버림 리치 표시"} for s, i in ri_idx.items()],
            "dora_indicators": [], "ura_indicators": [], "tenpai_revealed": [side_of(s, b) for s in tp] if tp is not None else None,
            "tenpai_seats": tp, "revealed_sides_app": res.get("revealed_sides"),
            "sticks_note": "앱 기록에 없음", "dora_note": "11-14 촬영 기록의 유국 폴더에는 표시패가 없음(앱 drawPaifu 는 판 중 확정 도라를 남김 — 11-24 뒤)"}


# ------------------------------------------------------------------ 앱 예시와 견주기(끝 조건 2)
def check_assets(rounds_file: Path, assets: Path) -> dict:
    o = jl(rounds_file)
    out = {"_note": "app_record.py check-assets — 앱 촬영 기록 판 결과 ↔ assets 패보(같은 추적 시각 HHMMSS 의 예시 파일). 다른 칸은 고치지 않고 까닭만",
           "rounds": {}, "total": Counter()}
    for r in o["rounds"]:
        suf = (r["folders"]["track"] or "_").split("_")[1]
        files = sorted(assets.glob(f"*_{suf}.json"))
        res = r.get("result") or {}
        rows = {}
        for f in files:
            a = jl(f)
            ar = a.get("result") or {}
            c = {}
            c["round"] = (a.get("round"), r["round"], a.get("round") == r["round"])
            c["honba"] = (a.get("honba"), r["honba"], a.get("honba") == r["honba"])
            c["dealer"] = (a.get("dealer"), r["dealer"], a.get("dealer") == r["dealer"])
            if r["end"] == "win":
                c["type"] = (ar.get("type"), res.get("type"), ar.get("type") == res.get("type"))
                c["winner"] = (ar.get("winner"), res.get("winner"), ar.get("winner") == res.get("winner"))
                c["loser"] = (ar.get("loser"), res.get("loser"), ar.get("loser") == res.get("loser"))
                c["win_tile"] = (ar.get("win_tile"), res.get("win_tile"), ar.get("win_tile") == res.get("win_tile"))
                ah, rh = ar.get("hand") or [], res.get("hand") or []
                c["hand_tiles"] = (" ".join(ah), " ".join(rh), sorted(ah) == sorted(rh))
                c["hand_order"] = (None, None, ah == rh)
                am = [(m.get("kind"), list(m.get("tiles") or [])) for m in ar.get("melds") or []]
                rm = [(m["kind"], m["tiles"]) for m in res.get("melds") or []]
                c["melds"] = (am, rm, am == rm)
                fl = (ar.get("flags") or {}).get("riichi")
                c["riichi_flag"] = (fl, res.get("riichi"), (fl is None and not res.get("riichi")) or fl == res.get("riichi"))
                asr = sorted({e["seat"] for e in a.get("events") or [] if e.get("type") == "discard" and e.get("riichi")})
                c["riichi_seats"] = (asr, sorted(res.get("riichi_seats") or []), asr == sorted(res.get("riichi_seats") or []))
                c["hero"] = (a.get("hero"), res.get("winner"), a.get("hero") == res.get("winner"))
                c["dora_indicators"] = (a.get("dora_indicators"), res.get("dora_indicators"), a.get("dora_indicators") == res.get("dora_indicators"))
                c["ura_indicators"] = (a.get("ura_indicators"), res.get("ura_indicators"), a.get("ura_indicators") == res.get("ura_indicators"))
            else:
                c["type"] = (ar.get("type"), "draw", ar.get("type") == "draw")
                tp = res.get("tenpai") or []
                c["hero_in_tenpai"] = (a.get("hero"), tp, a.get("hero") in tp)
                c["tenpai_field"] = (ar.get("tenpai"), tp, ar.get("tenpai") in (None, tp))
                c["dora_indicators"] = (a.get("dora_indicators"), [], a.get("dora_indicators") == [])
                c["ura_indicators"] = (a.get("ura_indicators"), [], a.get("ura_indicators") == [])
            diff = [k for k, v in c.items() if not v[2]]
            rows[f.stem] = {"checks": {k: {"asset": v[0], "app": v[1], "same": v[2]} for k, v in c.items()}, "diff": diff}
            # 참고(끝 조건 밖 — diff 에 안 셈): W2 앱 버림 사건 ↔ 예시 사건의 버림 · 울기(예시는 손 고침 표 · 손패가 들어간 것)
            ev = app_events(rounds_file.parent, r["id"])
            if ev is not None:
                import difflib
                dis = lambda es: [(e["seat"], e["tile"]) for e in es if e["type"] == "discard"]  # noqa: E731
                cal = lambda es: [(e["seat"], e.get("kind"), e.get("from"), list(e.get("tiles") or [])) for e in es if e["type"] == "call"]  # noqa: E731
                x, y = dis(ev), dis(a.get("events") or [])
                ops = [[tag, x[a0:a1], y[b0:b1]] for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes() if tag != "equal"]
                rows[f.stem]["discards_info"] = {"app": len(x), "asset": len(y), "same": x == y, "diff": ops,
                                                 "calls_same": cal(ev) == cal(a.get("events") or []),
                                                 "calls": None if cal(ev) == cal(a.get("events") or []) else {"app": cal(ev), "asset": cal(a.get("events") or [])}}
            out["total"]["files"] += 1
            out["total"]["checks"] += len(c)
            out["total"]["diff"] += len(diff)
        out["rounds"][r["id"]] = {"round": f"{r['round_label']}", "end": r["end"], "assets": rows, "no_asset": not files}
    out["total"] = dict(out["total"])
    return out


# ------------------------------------------------------------------ W2 ① 꼴 시험(대역)
def form_test(out: Path, exe: Path | None):
    """대역: results/h1x_*/paifu_rec.json(2반장 추적 프레임 재생, 11-20) 을 앱이 촬영 기록에 남기는 paifu.json 꼴로 바꿔 가짜 촬영 기록 폴더에 넣고
    collect · build 가 ① 로 읽는지 본다. 화료 = h17(141043 · label.json 사본), 유국 = h13(133550_draw · chosen · reveal 사본).
    꼴: 화료 = mount_screen._savePaifu 의 촬영 기록 사본({...paifu.toJson(), 'frames': 장수, 'rivers': …}), 유국 = _drawPaifuSaver(drawPaifu.toJson())."""
    caps0 = ROOT / "experiments" / "visit_20261114" / "captures"
    fake = out / "captures"
    if fake.exists():
        shutil.rmtree(fake)
    cases = [("20261114_141043", "h17_140450", "win"), ("20261114_133550_draw", "h13_132644", "draw")]
    rows = []
    for folder, key, kind in cases:
        d = fake / folder
        d.mkdir(parents=True)
        for f in ("meta.json", "label.json", "chosen.json", "reveal.json"):
            if (caps0 / folder / f).exists():
                shutil.copyfile(caps0 / folder / f, d / f)
        rec = jl(RES / key / "paifu_rec.json")
        lab = jl(d / "label.json") if (d / "label.json").exists() else None
        if kind == "win":
            meta = jl(d / "meta.json")["game"]
            pj = {**rec, "id": "1794629229382/남2국 2본장/2", "title": lab["round"], "round": round_base(lab["round"]), "honba": lab["honba"],
                  "dealer": meta["dealer"], "hero": lab["winner"], "names": meta["names"], "dora_indicators": lab["dora_indicators"],
                  "ura_indicators": lab["ura_indicators"], "note": "대역(form-test): results/h17_140450/paifu_rec.json",
                  "result": {"type": "tsumo" if lab["is_tsumo"] else "ron", "winner": lab["winner"], "loser": lab["loser"], "win_tile": lab["win_tile"],
                             "hand": lab["closed"][:-1], "melds": [parse_meld(m) for m in lab["melds"]], "flags": {"riichi": lab["riichi"]}},
                  "frames": 124, "rivers": {}}
        else:
            ch = jl(d / "chosen.json")
            pj = {**rec, "id": "1794629229382/동3국/0", "title": "동3국", "round": "동3국", "honba": 0, "dealer": 2, "hero": min(ch["tenpai_seats"]),
                  "note": "대역(form-test): results/h13_132644/paifu_rec.json", "result": {"type": "draw", "winner": None, "loser": None, "win_tile": None,
                                                                                         "hand": None, "melds": [], "tenpai": sorted(ch["tenpai_seats"])}}
        wj(d / "paifu.json", pj)
        rows.append((folder, key, kind, pj))
    cfg = {"games": [], "recording": {"date": "2026-11-14"},
           "app_record": {"captures": fake.as_posix(), "from": "13:00:00", "to": "14:30:00", "id_prefix": "f"}}
    o = build(cfg, out / "run", exe=exe)
    res = {"_note": form_test.__doc__, "cases": []}
    for (folder, key, kind, pj), r in zip(sorted(rows, key=lambda x: x[0]), o["rounds"]):
        ev = app_events(out / "run", r["id"])
        rr = to_result_read(r, ev)
        res["cases"].append({"folder": folder, "stand_in": rel(RES / key / "paifu_rec.json"), "kind": kind, "round": r["round_label"],
                             "discard_source": r["discard_source"]["chosen"], "used": r["discard_source"].get("used"),
                             "events_same_as_stand_in": ev == pj["events"], "events": len(ev or []), "summary": r["discard_source"].get("summary"),
                             "result_read_end": (rr or {}).get("end"), "result_read_ok": rr is not None,
                             "rivers_final_counts": {s: len(v) for s, v in ((rr or {}).get("rivers_final") or {}).items() if v is not None},
                             "warnings": r["warnings"]})
    wj(out / "form_test.json", res)
    return res


# ------------------------------------------------------------------ 명령
def _cfg_raw(path):
    sys.path.insert(0, str(HERE / "handtrack"))
    import hanchan_cfg as hcfg
    c = hcfg.load(path)
    if not c.app_record:
        raise SystemExit(f"{path}: app_record 칸이 없다")
    return c.raw, c


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("collect")
    p.add_argument("--hanchan")
    p.add_argument("--captures")
    p.add_argument("--from", dest="t_from")
    p.add_argument("--to", dest="t_to")
    p.add_argument("--date", default="2026-11-14")
    p.add_argument("--out")
    p = sp.add_parser("build")
    p.add_argument("--hanchan", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--exe")
    p.add_argument("--force-dump", action="store_true")
    p = sp.add_parser("check-assets")
    p.add_argument("--rounds", required=True)
    p.add_argument("--assets", default="assets/paifu")
    p.add_argument("--out")
    p = sp.add_parser("form-test")
    p.add_argument("--out", required=True)
    p.add_argument("--exe")
    a = ap.parse_args()
    if a.cmd == "collect":
        if a.hanchan:
            raw, _ = _cfg_raw(a.hanchan)
            ar = raw["app_record"]
            o = collect(ar["captures"], ar.get("date") or (raw.get("recording") or {}).get("date"), ar["from"], ar["to"],
                        ids=list(raw.get("games") or []) or None, id_prefix=ar.get("id_prefix", "a"))
        else:
            if not (a.captures and a.t_from and a.t_to):
                raise SystemExit("--hanchan 또는 --captures · --from · --to")
            o = collect(a.captures, a.date, a.t_from, a.t_to)
        if a.out:
            wj(_p(a.out), o)
        for r in o["rounds"]:
            res = r.get("result") or {}
            print(f"{r['id']} {r['round_label']:10s} 선 {r['dealer']} 아래 {r['bottom_seat']} {r['end']:5s} 결과 {res.get('type')} "
                  f"{('화료 ' + str(res.get('winner'))) if r['end'] == 'win' else ('텐파이 ' + str(res.get('tenpai')))} · 닻 {r['anchors']['end']} · "
                  f"추적 {r['folders']['track']} · 끝 {r['folders']['end']} · 버림 {r['discard_source']['chosen']}"
                  + (f" · 뺌 {[x['folder'] for x in r['folders']['dropped']]}" if r['folders']['dropped'] else "") + (f" · 경고 {r['warnings']}" if r['warnings'] else ""))
        print("판", len(o["rounds"]), "· 묶지 못한 폴더", o["loose"], "· 경고", o["warnings"])
    elif a.cmd == "build":
        raw, c = _cfg_raw(a.hanchan)
        exe = _p(a.exe) if a.exe else _p(a.out) / "_bin" / "replay_recorder.exe"
        o = build(raw, _p(a.out), exe=exe, exe_candidates=[c.exe, RES / "han3_1123" / "_bin" / "replay_recorder.exe"], force_dump=a.force_dump)
        for r in o["rounds"]:
            s = r["discard_source"]
            print(r["id"], r["round_label"], s["chosen"], s.get("dump") or s.get("file") or "", s.get("summary"), s.get("check") or "")
    elif a.cmd == "check-assets":
        o = check_assets(_p(a.rounds), _p(a.assets))
        if a.out:
            wj(_p(a.out), o)
        for gid, v in o["rounds"].items():
            for f, row in v["assets"].items():
                print(f"{gid} ↔ {f}: {'같음' if not row['diff'] else '다름 ' + str(row['diff'])}")
                for k in row["diff"]:
                    print(f"    {k}: 예시 {row['checks'][k]['asset']} · 앱 {row['checks'][k]['app']}")
                di = row.get("discards_info")
                if di:
                    print(f"    (참고) 버림 {di['app']} · 예시 {di['asset']} {'같음' if di['same'] else '다름 ' + str(di['diff'])} · 울기 {'같음' if di['calls_same'] else di['calls']}")
            if v["no_asset"]:
                print(f"{gid}: 같은 시각 예시 없음")
        print("합계", o["total"])
    elif a.cmd == "form-test":
        exe = _p(a.exe) if a.exe else _p(a.out) / "_bin" / "replay_recorder.exe"
        ensure_exe(exe, [RES / "han3_1123" / "_bin" / "replay_recorder.exe"])
        o = form_test(_p(a.out), exe)
        for c in o["cases"]:
            print(c["folder"], c["kind"], c["round"], "→ 출처", c["discard_source"], "· 사건 같음", c["events_same_as_stand_in"], c["events"],
                  "· result_read", c["result_read_end"], c["rivers_final_counts"], "· at 있음", (c["summary"] or {}).get("has_at"), c["warnings"])


if __name__ == "__main__":
    main()
