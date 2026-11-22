"""앱에 묶어 두는 패보 예시(assets/paifu/)를 11-14 매장 판들로 만든다(2026-11-17, 사용자 "다른 대국도 기록에 넣어줘").

  python -X utf8 experiments/paifu_frames/paifu_examples.py        (저장소 루트에서)

판마다:
- 버림 = 앱 버림 기록기(`lib/paifu/discard_recorder.dart`)를 저장된 추적 프레임에 그대로 돌린 것(`replay_recorder.dart overlay`,
  겹쳐 보기 저장분 `results/<판>/overlay_dump.json`, 펠트로 고친 격자. 11-21 부터 기록기 새 기본값 — 확정 안 된 칸 지우기, RECORDER_OPTS 주석). 사람이 고치지 않는다 — 기록기가 틀린 칸은 틀린 채로 들어간다
  (metrics 표 12-29 의 남은 틀림: r13 · r19 · r20 헛 버림, r19 울려 나감 놓침. r18 의 헛 울려 나감은 표 12-36 의 규칙으로 빠졌고, 울기는 묶음 전체(퐁 · 치 + 세 장)로 적힌다 — 표 12-37.
  r13 · r19 의 틀림은 11-21 기록기 수정(헛 칸 규칙 C, metrics 표 12-107)으로 기록기가 스스로 바르게 적어 손 고침 표에서 뺐고, r13 · r15 의 차례가 어긋난 자리 0 버림도 바로 놓인다).
- 결과(화료자 · 끝 손패 · 화료패 · 표시패 · 리치) = 그 판 화료 기록 `captures/<화료 시각>/label.json`. 유국 판은 결과만 "유국".
- 손패(판 중) = 사용자 정답이 있는 판만. 11-20 부터 고친 정답(`sam2track.truth_all` — truth_fix_1120 포함)을
  `handtrack/rebuild_opus.rebuild(gid, "truth")` 로 끝 손패에서 거꾸로 복원(add_hands_truth). 화료 판(r12 · r17 · r19)은 화료자,
  유국 판(r13 · r15 · r16 · L16)은 텐파이를 공개한 사람이 손패 주인(hero). L16 은 r16 과 같은 국의 왼쪽 자리라 파일을 나눔.
  기록기가 적은 손패 주인 버림과 정답의 버림이 한 장이라도 다르면 멈춘다. 녹화 전 버림은 손패를 모른다(null).
- 기록기 오류는 원칙상 안 고치지만, 근거가 있는 것만 표로 고침(fix_recorder — RETILE_DISCARDS · EXTRA_DISCARDS · MISSED_CALLS · MISSED_DISCARDS · MOVE_DISCARDS):
  지금 남은 것은 손패를 넣으면 앞뒤가 안 맞는 남2국 1본장 놓친 1z 퐁(r16 · L16, 추적 시작 전) 하나.
  11-21 에 뺀 것: r13 위 헛 7z · r13 치 당한 8p 차례, r19 자리 3(오른쪽) 넷(헛 9s · 종류 둘 · 놓친 9s)과 놓친 자리 0 의 6s 퐁 —
  새 기록기 출력이 그 고친 결과(r19 는 사건 · 패 그대로, r13 은 영상 프레임 순서 — results/r19_check/r13_top_evidence.jpg)와 같아서.
r11 은 따로 만든 것(`handtrack/paifu_export.py`)을 그대로 둔다.
"""
import glob
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE / "handtrack"))
import htcommon as hc  # noqa: E402
import paifu_export as pe  # noqa: E402

CAP = HERE.parent / "visit_20261114" / "captures"
RES = HERE / "results"
ASSETS = ROOT / "assets" / "paifu"
SIDES = ["bottom", "right", "top", "left"]

# (파일 이름, 재생 입력(rounds.json 키 — 지난 국 탁자에서 시작한 판은 자르지 않은 것), 손패 정답 판, 반장)
GAMES = [
    ("r12_131655", "h12full_131655", "r12_131655", 2),
    ("r13_132644", "h13_132644", "r13_132644", 2),
    ("r14_133610", "h14full_133610", "r14_133610", 2),   # 11-20: 2순 정답 있음(1순은 녹화 전)
    ("r15_134151", "h15_134151", "r15_134151", 2),
    ("r16_135321", "h16_135321", "r16_135321", 2),
    ("L16_135321", "h16_135321", "L16_135321", 2),   # 11-20: r16 과 같은 판 · 왼쪽 자리 손패(사용자 "예시 둘로 나눔")
    ("r17_140450", "h17_140450", "r17_140450", 2),
    ("r18_141259", "h18_141259", "r18_141259", 2),   # 11-20: 정답 없음 — 손패는 SAM 2 없는 Opus 하위 에이전트 읽기(HAND_FROM_OPUS)
    ("r19_142013", "h19full_142013", "r19_142013", 2),
    ("r20_143236", "h20_143236", None, 3),
]


def track_meta(track: str) -> dict:
    z = sorted(glob.glob(str(CAP / f"20261114_{track}_track" / "frames_*.zip")))[0]
    return json.loads(zipfile.ZipFile(z).read("frames.json"))


def parse_meld(s) -> dict:
    """label.json 의 울기: '[5z 5z 5z]'(남의 패) · '(5z 5z 5z 5z)'(안깡) 또는 패 목록."""
    if isinstance(s, list):
        tiles, closed = s, False
    else:
        closed = s.strip().startswith("(")
        tiles = s.strip("[]() ").split()
    same = all(t.replace("0", "5") == tiles[0].replace("0", "5") for t in tiles)
    kind = ("ankan" if closed else "kan") if len(tiles) == 4 else ("pon" if same else "chi")
    return {"kind": kind, "tiles": tiles}


# 11-21: 기록기 기본값이 "확정 안 된 칸 지우기"(dropUnconfirmed, docs/recorder_ghost_slot_plan_1121.md 후보 C, metrics 표 12-107)로 바뀌었고
# 예시도 새 기본값으로 다시 만든다(옵션 없음). 옛 동작(--no-drop-unconfirmed) 출력 번호에 걸려 있던 r13 · r19 의 손 고침 표 항목은 뺐다
# (새 출력이 스스로 바름 — 다시 만든 기록 results/ghost_slot_1121/regen_1121/). 옛 동작으로 돌리려면 ["--no-drop-unconfirmed"].
RECORDER_OPTS: list[str] = []


def replay(key: str, r: dict) -> dict:
    out = RES / key / "paifu_rec.json"
    env = dict(os.environ, PATH="C:/Users/jjh7757/flutter/bin;" + os.environ["PATH"])
    cmd = ["C:/Users/jjh7757/flutter/bin/dart.bat", "run", "experiments/paifu_frames/replay_recorder.dart", "overlay", f"experiments/paifu_frames/results/{key}/overlay_dump.json",
           r["dealer_side"], f"experiments/paifu_frames/results/{key}/dart_examples.json", f"experiments/paifu_frames/results/{key}/paifu_rec.json",
           str(r["bottom"]), "--sticks", ",".join(str(x) for x in r["sticks"]), *RECORDER_OPTS]
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0 or not out.exists():
        raise SystemExit(f"{key}: 재생 실패\n{p.stdout[-800:]}\n{p.stderr[-800:]}")
    return json.loads(out.read_text(encoding="utf-8"))


def add_hero_hands(name: str, events: list, hero: int, gid: str, final_row: list, tsumo_tile) -> tuple[list, int]:
    """기록기 사건에 화료자의 뽑기·손패(사용자 정답)를 끼운다. 기록기 버림과 정답 버림이 다르면 멈춘다."""
    game = hc.jload(hc.OUT / gid / "game.json")
    turns, first_i = pe.rebuild_turns(gid, game)
    mine = [e for e in events if e["type"] == "discard" and e["seat"] == hero]
    if any(e["type"] == "call" and e["seat"] == hero for e in events):
        raise SystemExit(f"{name}: 화료자가 운 판은 아직 안 다룬다")
    want = [t["discard"] for t in turns]
    got = [e["tile"] for e in mine][first_i - 1:]
    if got != want:
        raise SystemExit(f"{name}: 기록기의 화료자 버림과 정답이 다름\n 기록기 {got}\n 정답   {want}")
    out, k = [], 0
    for e in events:
        if e["type"] == "discard" and e["seat"] == hero:
            if k < first_i - 1:  # 녹화 전 — 손패 모름
                out.append({"type": "draw", "seat": hero, "tile": None, "hand": None})
                out.append({**e, "hand": None})
            else:
                t = turns[k - (first_i - 1)]
                out.append({"type": "draw", "seat": hero, "tile": t["draw"], "hand": t["before"]})
                out.append({**e, "tsumogiri": t["tsumogiri"], "hand": t["after"]})
            k += 1
        else:
            out.append(e)
    if turns and turns[-1]["after"] != final_row:
        raise SystemExit(f"{name}: 마지막 손패가 끝 손패와 다름")
    if tsumo_tile:
        out.append({"type": "draw", "seat": hero, "tile": tsumo_tile, "hand": final_row})
    return out, first_i - 1


# 11-20: 기록기가 놓친 울기 — 손패 주인(hero) 차례가 이어지려면 필요한 것만, 근거와 함께.
# L16(자리 1) 2순 1z 퐁: 기록기 사건에서 자리 1 의 둘째 버림(2p) 바로 앞에 자리 0 의 버림이 빠져 있고(자리 3 → 자리 1),
# 정답(L16_d02 kind call · game.json meld 1z 1z 1z, 첫 패 누움)과 맞음 → 자리 0 이 버린 1z 를 퐁.
# (자리 0 버림이 16장으로 다른 자리보다 적음 · 표 12-29 "r16 은 0(묶음 1 — 퐁이 추적 시작 전)" 의 그 퐁) — r16 · L16 같은 판이라 둘 다.
_PON_1Z = {"seat": 1, "nth": 1, "prev_seat": 3, "tile": "2p",
           "insert": [{"type": "discard", "seat": 0, "tile": "1z", "tsumogiri": None, "riichi": False},
                      {"type": "call", "seat": 1, "kind": "pon", "from": 0, "tiles": ["1z", "1z", "1z"]}]}
# 11-21: r19 자리 0 의 6s 퐁(자리 3 의 6s 를 14:23:15 ~ 18 사이)은 옛 기록기가 놓쳐 여기 있었으나, 새 기본값 기록기가 스스로 적어 뺌.
MISSED_CALLS = {"r16_135321": _PON_1Z, "L16_135321": _PON_1Z}
# 11-21: 기록기가 놓친 버림(MISSED_CALLS 와 같은 꼴 — fx["seat"] 의 nth 번째 버림 바로 앞에 끼움). 판 → {seat, nth, prev_seat, prev_tile, tile, insert}.
# r19 자리 3 의 놓친 6번째 9s(14:23:39)가 있었으나 새 기록기가 스스로 적어 뺌 → 지금 빈 표.
MISSED_DISCARDS: dict = {}
# 11-21: 기록기가 종류를 잘못 적은 버림(판 → [{seat, nth(기록기 출력 그대로에서 그 자리의 몇 번째, 0부터), tile, to}]).
# r19 자리 3 의 4 · 5번째(3z → 9s · 9s → 6s)가 있었으나 새 기록기가 스스로 바르게 적어 뺌 → 지금 빈 표.
RETILE_DISCARDS: dict = {}
# 패보 note 끝에 덧붙이는 고친 사실(fill_pre_record 의 PRE_NOTE 뒤). r19 의 것은 위 고침을 뺄 때 같이 뺌 → 지금 빈 표.
FIX_NOTES: dict = {}
# 11-20: 사용자 정답이 없는 판은 Opus 읽기(opusread prep --nosam --fromplan, _work/<폴더>/<차례>/answer.json)로 끝 손패에서 거꾸로 복원
# (rebuild_opus.rebuild(gid, "full") — 리치 뒤는 규칙). 정답으로 잰 같은 꼴: r15 · L16 32/32 · 판 2/2(metrics 표 12-103 · 12-104).
HAND_FROM_OPUS = {"r18_141259": "rawread_r18_1120"}
SAME_ROUND_SECOND = {"L16_135321"}   # 같은 국 둘째 예시 — 앱 목록에서 갈리게 제목에 손패 주인 이름을 붙임

# 기록기 시간 순서가 어긋나 울기가 엉뚱한 차례에 붙은 버림을 옮김(판 → {seat, nth, tile, after_call_seat}).
# 11-20 r13 자리 0 의 둘째 3p(치 당한 8p 앞에 적힘)를 치 뒤로 옮겼으나, 11-21 새 기록기가 영상 프레임 순서대로 적어 뺌 → 지금 빈 표.
MOVE_DISCARDS: dict = {}


# 기록기 헛 버림 중 손패를 넣으면 패 장수가 어긋나는 것만 뺌(판 → {seat, nth 또는 nth_from_end, tile}).
# 11-20 r13 자리 0 마지막 헛 7z · 11-21 r19 자리 3 의 헛 9s(14:21:36)가 있었으나 새 기록기가 둘 다 안 적어 뺌 → 지금 빈 표.
EXTRA_DISCARDS: dict = {}


def drop_extra_discards(name: str, events: list) -> list:
    fx = EXTRA_DISCARDS.get(name)
    if not fx:
        return events
    idx = [i for i, e in enumerate(events) if e["type"] == "discard" and e["seat"] == fx["seat"]]
    i = idx[fx["nth"]] if "nth" in fx else idx[-fx["nth_from_end"]]
    if events[i]["tile"] != fx["tile"]:
        raise SystemExit(f"{name}: 뺄 헛 버림이 예상과 다름 — {events[i]}")
    return events[:i] + events[i + 1:]


def hand_seat(gid: str, bottom: int) -> int:
    """손패를 읽은 사람의 자리 — 카메라 아래 자리(rounds bottom)에서 config side 만큼(차례 순서 = bottom → right → top → left)."""
    return (bottom + SIDES.index(hc.config(gid)["side"])) % 4


def _insert_before(name: str, events: list, fx: dict | None, what: str) -> list:
    """fx["seat"] 의 nth 번째 버림 바로 앞에 fx["insert"] 를 끼운다(앞 사건의 자리 · 패가 예상과 다르면 멈춤)."""
    if not fx:
        return events
    idx = [i for i, e in enumerate(events) if e["type"] == "discard" and e["seat"] == fx["seat"]]
    i = idx[fx["nth"]]
    prev = events[i - 1]
    if events[i]["tile"] != fx["tile"] or prev["seat"] != fx["prev_seat"] or ("prev_tile" in fx and prev.get("tile") != fx["prev_tile"]):
        raise SystemExit(f"{name}: 놓친 {what} 자리가 예상과 다름 — {prev} / {events[i]}")
    return events[:i] + [dict(e) for e in fx["insert"]] + events[i:]


def add_missed_calls(name: str, events: list) -> list:
    return _insert_before(name, events, MISSED_CALLS.get(name), "울기")


def add_missed_discards(name: str, events: list) -> list:
    return _insert_before(name, events, MISSED_DISCARDS.get(name), "버림")


def retile_discards(name: str, events: list) -> list:
    """기록기가 종류를 잘못 적은 버림의 패를 바꾼다(nth 는 기록기 출력에서 그 자리의 몇 번째). 시각(at) 등 다른 칸은 그대로."""
    fixes = RETILE_DISCARDS.get(name)
    if not fixes:
        return events
    ev = list(events)
    for fx in fixes:
        idx = [i for i, e in enumerate(ev) if e["type"] == "discard" and e["seat"] == fx["seat"]]
        i = idx[fx["nth"]]
        if ev[i]["tile"] != fx["tile"]:
            raise SystemExit(f"{name}: 종류를 고칠 버림이 예상과 다름 — {ev[i]}")
        ev[i] = {**ev[i], "tile": fx["to"]}
    return ev


def fix_recorder(name: str, events: list) -> list:
    """근거 있는 기록기 오류 고침을 한 순서로: 종류 → 헛 버림 뺌 → 놓친 울기 → 놓친 버림 → 차례 옮김.
    (11-21 전에는 유국 판에만 move(drop(calls)) 로 걸었음 — 그때 고친 판(r13 · r16 · L16)은 판마다 한 종류뿐이라 순서가 바뀌어도 같음.)"""
    events = retile_discards(name, events)
    events = drop_extra_discards(name, events)
    events = add_missed_calls(name, events)
    events = add_missed_discards(name, events)
    return move_discards(name, events)


def move_discards(name: str, events: list) -> list:
    fx = MOVE_DISCARDS.get(name)
    if not fx:
        return events
    idx = [i for i, e in enumerate(events) if e["type"] == "discard" and e["seat"] == fx["seat"]]
    i = idx[fx["nth"]]
    if events[i]["tile"] != fx["tile"]:
        raise SystemExit(f"{name}: 옮길 버림이 예상과 다름 — {events[i]}")
    ev = events[:i] + events[i + 1:]
    ci = next(k for k, e in enumerate(ev) if e["type"] == "call" and k >= i)
    j = next(k for k, e in enumerate(ev) if k > ci and e["type"] == "discard" and e["seat"] == fx["after_call_seat"])
    return ev[:j + 1] + [events[i]] + ev[j + 1:]


def add_hands_truth(name: str, events: list, hero: int, gid: str, final_row: list, tsumo_tile) -> tuple[list, int]:
    """11-20: 화료자 · 텐파이 공개자의 손패를 고친 정답(sam2track.truth_all — truth_fix_1120 포함)으로 끝 손패에서 거꾸로 복원해 끼운다.
    복원은 handtrack/rebuild_opus.rebuild(gid, "truth")(울기 차례 · 안 보인 차례 처리 포함, r15 · L16 Opus 복원 34/34 와 같은 것).
    안 보인 차례(r15 3순)는 뽑은 패를 버린 패로 짐작(그 앞 차례 손패도 이 짐작을 따름), 울기 차례는 울기 사건에 울고 난 손패(순서는 정렬로 짐작, 묶음은 확실)."""
    import rebuild_opus as rb
    import sam2track as s1
    truth = s1.truth_all()
    game = hc.jload(hc.OUT / gid / "game.json")
    if gid in HAND_FROM_OPUS:
        rb.OP = hc.WORK / HAND_FROM_OPUS[gid]
        rows, _ = rb.rebuild(gid, "full")
    else:
        rows, _ = rb.rebuild(gid, "truth")
    first_i = next(x for x in hc.jload(pe.BASE / "turns.json")["games"] if x["id"] == gid)["first_i"]
    mine = [e for e in events if e["type"] == "discard" and e["seat"] == hero]
    got = [e["tile"] for e in mine][first_i - 1:]
    want = [r["river"] for r in rows]
    if got != want:
        raise SystemExit(f"{name}: 기록기의 손패 주인 버림과 정답이 다름\n 기록기 {got}\n 정답   {want}")
    if rows[-1]["after"] != list(final_row):
        raise SystemExit(f"{name}: 복원 마지막 손패가 끝 손패와 다름")
    turns = {t["id"]: t for t in next(x for x in hc.jload(pe.BASE / "turns.json")["games"] if x["id"] == gid)["turns"]}
    out, k, pend_call = [], 0, None
    for e in events:
        if e["type"] == "call" and e["seat"] == hero:
            r = rows[k - (first_i - 1)]
            if r.get("special") != "call":
                raise SystemExit(f"{name}: 손패 주인의 울기 사건인데 정답 차례 {r['id']} 는 울기가 아님")
            hand = list(r["before"])
            for v in rb.call_hand_tiles(game, turns[r["id"]]):
                hand.remove(v)
            out.append({**e, "hand": hand})
            pend_call = r["id"]
            continue
        if e["type"] == "discard" and e["seat"] == hero:
            if k < first_i - 1:  # 녹화 전 — 손패 모름
                out.append({"type": "draw", "seat": hero, "tile": None, "hand": None})
                out.append({**e, "hand": None})
            else:
                r = rows[k - (first_i - 1)]
                sp = r.get("special")
                if sp == "call":
                    if pend_call != r["id"]:
                        raise SystemExit(f"{name}: 정답 {r['id']} 는 울기인데 앞에 울기 사건이 없음")
                    out.append({**e, "tsumogiri": False, "hand": r["after"]})
                elif sp == "unseen":   # 뽑기가 화면 밖 — 복원과 같은 짐작(뽑은 패 = 버린 패)으로 이음, 쯔모기리 여부는 모름
                    out.append({"type": "draw", "seat": hero, "tile": r["drawn"], "hand": r["before"]})
                    out.append({**e, "tsumogiri": None, "hand": r["after"]})
                else:
                    tg = (truth[r["id"]]["kind"] == "tsumogiri") if gid not in HAND_FROM_OPUS else (r["src"] != "Opus")   # Opus(쯔모) · 규칙 = 쯔모기리
                    out.append({"type": "draw", "seat": hero, "tile": r["drawn"], "hand": r["before"]})
                    out.append({**e, "tsumogiri": tg, "hand": r["after"]})
            k += 1
        else:
            out.append(e)
    if tsumo_tile:
        out.append({"type": "draw", "seat": hero, "tile": tsumo_tile, "hand": list(final_row)})
    return out, first_i - 1


# 11-20 사용자 "손패 모르는 순 가능성 높은거로 채워놔": 녹화 전 순(손패 null)을 채운다.
# 그 순에 버린 뒤 손패 = 다음 순 시작 손패(확실), 그 순의 14장 = 그것 + 버린 패(확실). 모르는 것은 14장 중 어느 것이 뽑은 패였나뿐 —
# 14장 각각이 마지막에 뽑혔을 확률이 같으므로(배패 · 뽑기 모두 무작위) 같은 종류가 가장 많은 패가 가장 그럴듯함(동률이면 버린 패, 아니면 정렬 순 앞).
# 뽑기 전 손패 줄 = 버린 뒤 줄에 버린 패를 정렬 자리에 끼우고 뽑은 패 한 장을 뺌(줄 순서는 정렬로 짐작). 채운 사건에는 "guess": true(앱은 안 읽음).
def fill_pre_record(name: str, events: list, hero: int) -> tuple[list, int]:
    from collections import Counter
    from replay import key as rkey, sort_scheme
    ev = [dict(e) for e in events]
    hands = [e["hand"] for e in ev if e["seat"] == hero and e.get("hand")]
    if not hands:
        return ev, 0
    sch = sort_scheme(hands[-1])
    norm = lambda t: t.replace("0", "5")  # noqa: E731
    def insert(row, t):
        k = rkey(t, sch)
        pos = len(row) if k is None else next((i for i, x in enumerate(row) if rkey(x, sch) is not None and rkey(x, sch) > k), len(row))
        return row[:pos] + [t] + row[pos:]
    filled = 0
    idx = [i for i, e in enumerate(ev) if e["seat"] == hero and e["type"] == "discard"]
    for i in reversed(idx):            # 뒤에서 앞으로 — 다음 순 시작 손패가 먼저 채워져 있어야 함
        e = ev[i]
        if e.get("hand") is not None:
            continue
        nxt = next((x for x in ev[i + 1:] if x["seat"] == hero and x["type"] in ("draw", "call")), None)
        if nxt is None or nxt.get("hand") is None:
            raise SystemExit(f"{name}: 녹화 전 순 다음 손패를 모름 — 채울 수 없음")
        after = list(nxt["hand"])
        if nxt["type"] == "call":       # 울기 전 손패 = 울고 난 손패 + 손에서 나간 패(묶음의 둘째부터)
            for t in nxt["tiles"][1:]:
                after = insert(after, t)
        fourteen = insert(after, e["tile"])
        c = Counter(norm(t) for t in fourteen)
        top = max(c.values())
        if c[norm(e["tile"])] == top:
            drawn = e["tile"]
        else:
            drawn = next(t for t in fourteen if c[norm(t)] == top)
        before = list(fourteen)
        before.remove(drawn)
        d = ev[i - 1]
        if not (d["type"] == "draw" and d["seat"] == hero and d.get("hand") is None):
            raise SystemExit(f"{name}: 녹화 전 버림 앞에 빈 뽑기 사건이 없음 — {d}")
        ev[i - 1] = {**d, "tile": drawn, "hand": before, "guess": True}
        ev[i] = {**e, "tsumogiri": drawn == e["tile"], "hand": after, "guess": True}
        filled += 1
    return ev, filled


PRE_NOTE = " 녹화 전 순 손패는 짐작으로 채움(버린 뒤 손패와 14장은 확실, 뽑은 패는 14장 중 가장 많은 종류 — guess 표시)."


def fill_r11():
    """r11 은 handtrack/paifu_export.py 가 따로 만든 것 — 여기서는 녹화 전 순만 채워 덮어씀(두 번 돌려도 같음)."""
    f = ASSETS / "r11_130921.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    d["events"], n = fill_pre_record("r11_130921", d["events"], d["hero"])
    if n:
        d["note"] = d["note"].rstrip() + PRE_NOTE
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("r11_130921: 녹화 전 순 채움", n)


def main():
    rounds = json.loads((RES / "heldout_1114" / "rounds.json").read_text(encoding="utf-8"))
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name, key, gid, han in GAMES:
        r = rounds[key]
        meta = track_meta(r["track"])
        p = replay(key, r)
        lab = None
        # 화료 기록(label.json)은 그 판을 "대국에 반영" 했을 때만 남는다. 화료 사진은 있는데 기록이 없는 판(r20 — 판독이 손패를 못 읽음)은 결과 없이 버림만.
        if r.get("src") == "win" and (CAP / r["cap"] / "label.json").exists():
            lab = json.loads((CAP / r["cap"] / "label.json").read_text(encoding="utf-8"))
        no_record = r.get("src") == "win" and lab is None
        parts = meta["round_key"].split("/")
        rnd = (lab["round"] if lab else parts[1]).split()[0]
        honba = lab["honba"] if lab else int(parts[2])
        events = p["events"]
        n_dis = sum(1 for e in events if e["type"] == "discard")
        if lab:
            hero = lab["winner"]
            closed = lab["closed"]
            if closed[-1] != lab["win_tile"]:
                raise SystemExit(f"{name}: label closed 의 마지막이 화료패가 아님")
            final_row, unknown, src = closed[:-1], None, "recorder"
            events = fix_recorder(name, events)   # 11-21: 화료 판에도(r19)
            if gid:
                final_row = hc.jload(hc.OUT / gid / "game.json")["final_hand"]["closed"]
                if sorted(final_row) != sorted(closed[:-1]):
                    raise SystemExit(f"{name}: 끝 손패(정답)와 label 이 다름")
                if hand_seat(gid, r["bottom"]) != hero:
                    raise SystemExit(f"{name}: 손패 정답 자리 {hand_seat(gid, r['bottom'])} ≠ 화료자 {hero}")
                events, unknown = add_hands_truth(name, events, hero, gid, final_row, lab["win_tile"] if lab["is_tsumo"] else None)
                src = "recorder+opus_hand" if gid in HAND_FROM_OPUS else "recorder+user_hand"
            result = {"type": "tsumo" if lab["is_tsumo"] else "ron", "winner": hero, "loser": lab["loser"], "win_tile": lab["win_tile"],
                      "hand": final_row, "melds": [parse_meld(m) for m in lab["melds"]], "flags": {"riichi": bool(lab["riichi"])}}
            dora, ura = lab["dora_indicators"], lab["ura_indicators"]
            if gid:
                who = ("Opus 가 영상에서 읽은 칸(정답 없음, 리치 뒤는 규칙)으로 끝 손패에서 거꾸로 복원한 것" if gid in HAND_FROM_OPUS
                       else "사람이 적은 정답으로 복원한 것")
                note = (f"버림은 앱 기록기가 저장된 장면에서 적은 그대로, 내 손패는 {who}" + (f"(첫 {unknown}순은 녹화 전이라 없음)" if unknown else "")
                        + ". 점수는 그날 화료 기록의 끝 손패로 계산.")
            else:
                note = "버림은 앱 기록기가 저장된 장면에서 적은 그대로(사람이 고치지 않음). 판 중 손패는 없고 화료자의 끝 손패만 있음. 점수는 그날 화료 기록으로 계산."
        elif no_record:
            cap_meta = json.loads((CAP / r["cap"] / "meta.json").read_text(encoding="utf-8"))
            hero, result, dora, ura, src = cap_meta["merge"]["winner"], None, [], [], "recorder"
            note = "버림은 앱 기록기가 저장된 장면에서 적은 그대로(사람이 고치지 않음). 이 판은 그날 화료 기록이 남지 않아 끝 손패와 점수가 없음."
        elif gid:   # 11-20: 유국 + 텐파이 공개(game.json result draw_tenpai) — 공개한 사람을 손패 주인으로
            g = hc.jload(hc.OUT / gid / "game.json")
            if not str(g.get("result", "")).startswith("draw"):
                raise SystemExit(f"{name}: 화료 기록이 없는데 정답 판 결과가 {g.get('result')}")
            hero, result, dora, ura = hand_seat(gid, r["bottom"]), {"type": "draw"}, [], []
            final_row = g["final_hand"]["closed"]
            events = fix_recorder(name, events)
            events, unknown = add_hands_truth(name, events, hero, gid, final_row, None)
            src = "recorder+user_hand"
            fixed = "".join([
                " 기록기가 놓친 울기 하나(자리 0 의 1z 를 자리 1 이 퐁)는 정답 · 화료 사진으로 넣음." if name in MISSED_CALLS else "",
                " 기록기 헛 버림 하나(자리 0 마지막 7z)는 강 사진 정답으로 뺌." if name in EXTRA_DISCARDS else "",
                " 기록기 시간 순서가 어긋난 버림 하나(자리 0 의 둘째 3p)는 치 뒤로 옮김(차례 장수로 정함)." if name in MOVE_DISCARDS else "",
                " 3순은 뽑기가 화면 밖이라 뽑은 패를 버린 패로 짐작함(그 앞 1 · 2순 손패도 이 짐작을 따름 — 한 장이 다를 수 있음)." if name == "r15_134151" else ""])
            note = (f"유국(텐파이 공개). 버림은 앱 기록기가 저장된 장면에서 적은 그대로, 손패 주인은 텐파이를 공개한 사람이고 손패는 사람이 적은 정답"
                    "(영상으로 고친 것 포함)으로 끝 손패에서 거꾸로 복원한 것" + (f"(첫 {unknown}순은 녹화 전이라 없음)" if unknown else "")
                    + f".{fixed} 표시패 기록은 없음.")
        else:
            hero, result, dora, ura, src = r["bottom"], {"type": "draw"}, [], [], "recorder"
            note = "유국. 버림은 앱 기록기가 저장된 장면에서 적은 그대로(사람이 고치지 않음). 손패와 표시패 기록은 없음."
        out = {
            "version": 1,
            "id": name,
            "title": f"2026-11-14 {han}반장 {rnd}" + (f" {honba}본장" if honba else "") + (f" · {meta['names'][hero]} 손패" if name in SAME_ROUND_SECOND else ""),
            "round": rnd,
            "honba": honba,
            "dealer": r["dealer"],
            "hero": hero,
            "names": meta["names"],
            "dora_indicators": dora,
            "ura_indicators": ura,
            "note": note,
            "source": src,
            "events": events,
            **({"result": result} if result else {}),
        }
        if out["dealer"] != p["dealer"]:
            raise SystemExit(f"{name}: 선 자리가 재생({p['dealer']})과 다름({out['dealer']})")
        out["events"], n_fill = fill_pre_record(name, out["events"], hero)
        events = out["events"]
        if n_fill:
            out["note"] = out["note"] + PRE_NOTE
        out["note"] = out["note"] + FIX_NOTES.get(name, "")
        (ASSETS / f"{name}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        n_dis = sum(1 for e in events if e["type"] == "discard")
        calls = sum(1 for e in events if e["type"] == "call")
        riichi = [e["seat"] for e in events if e["type"] == "discard" and e.get("riichi")]
        print(f"{name}: {out['title']} · 버림 {n_dis} · 울기 {calls} · 리치 자리 {riichi} · 결과 {result['type'] if result else '기록 없음'} · hero {hero} · {src}")


if __name__ == "__main__":
    main()
    fill_r11()
