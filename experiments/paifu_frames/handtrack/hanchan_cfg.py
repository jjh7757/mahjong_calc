"""반장 설정(헤드 녹화 → 패보 흐름의 판 목록 · 경로 · 손 설정) 불러오기(2026-11-24, 자동 패보 설계서 0단계).

han3.py · han3_paifu.py · han3_install.py · han3_truthserver.py · han3_checkserver.py 가 11-14 3반장에 박아 두었던 값을
`experiments/paifu_frames/hanchan/<이름>.json` 으로 뺐다. 스크립트마다 `--hanchan <json>` 을 받고, 안 주면 DEFAULT(3반장 h3_1123.json).
상대 경로는 모두 저장소 루트 기준.

설정 꼴(괄호 = 안 적으면 쓰는 값):
  id                 설정 이름(겹침 검사 · 보고용)
  label              짧은 이름("3반장") — 차례 목록 note 등 글에 들어감
  results_dir        반장 결과 폴더(기록기 결과 <판>/ · rounds_meta.json · recorder_fix.json · _bin/)
  prep_dir           (results_dir/_prep) 손패 재료 폴더 — 실행 때 --prep 로 바꿀 수 있음
  read_root          읽기 폴더 이름(results/handtrack/_work/ 아래) — 차례마다 <차례 id>/TASK.md · answer.json
  recording          (없음 = htcommon 기본: 11-14 녹화) {"root", "recs": [...], "date": "YYYY-MM-DD"} — 있으면 htcommon 의 녹화 자리 · 날짜를 실행 중에 바꿈
  games              판 id 목록(시간 순)
  turn_prefix        {차례 id 앞 세 글자: 판 id} — truthprep 이 차례 id 를 <판 id 앞 세 글자>_dNN 으로 지으므로 접두사 = 판 id[:3] 이어야 함
  replaces_base      ([]) 기존 판 목록(_work/testtruth_1116/turns.json)에 같은 판 id 로 이미 있고, 이 설정의 차례 목록으로 덮어쓰는 판
  files              ({}) 파일 이름 — turns(turns.json) · turns_cut(turns_cut.json) · turn_fix(turn_fix.json): prep_dir 기준,
                     rounds_meta(rounds_meta.json) · recorder_fix(recorder_fix.json): results_dir 기준
  recorder           {"exe": (results_dir/_bin/replay_recorder.exe), "sticks": 기록기 --sticks 값}
  hand               {"row_at": {판: "HH:MM:SS.s"}, "cut_lag_ms": (1000), "anchor_lead_ms": (1500), "row_pad_px": (80), "call_turns": [울기 차례 id]}
  paifu              {"out_dir": (prep_dir/paifu), "title_prefix", "names": (플레이어 1 ~ 4), "start_score": (25000), "event_fix": {판: [고침]}}
  install            {"src": (paifu.out_dir), "dst", "id_prefix"}
  truth_check        {"dir": (results_dir/review), "ids": [차례 id], "page_title", "page_group", "prep_note"}
  item_check         {"dir": (results_dir/review2), "page_title", "page_heading", "prep_note", "items": [항목]}
  rerun_of           (없음) 같은 반장을 다른 폴더에서 다시 돌리는 설정(자동 패보 paifu_auto.py 실행 폴더, 11-24)이면 원래 설정의 id.
                     겹침 검사 ④ 에서 그 id 의 설정은 판 목록이 똑같을 때만 건너뛴다(판 id 가 같은 것이 당연하므로).
  app_record         (없음 = 앱 기록 없이 헤드 녹화만 — 지금 흐름 그대로) 앱 촬영 기록을 1차 입력으로 쓰는 반장(설계서 8-5 · 8-6, 11-24 저녁):
                     {"captures": 촬영 기록 폴더, "from": "HH:MM:SS", "to": "HH:MM:SS"(폴더 시각 구간 — 그 반장만), "date": (recording.date),
                      "sticks": (recorder.sticks) 추적 프레임 재생 --sticks, "sticks_by_track": {추적 폴더 HHMMSS: --sticks}, "id_prefix": ("a"),
                      "clock_ref": {"offset_ms", "source"}(선택 — W5 시계 차와 견줄 다른 측정), "check_windows": {판: headrec_rounds.json 키}(선택 — W5 견줌)}
                     판 목록 · 결과 · 버림 출처는 app_record.py 가 만든다(games 는 촬영 기록 판 순서와 같아야 함 — 다르면 S0 가 질문으로 올림).
  frame              (없음) 녹화 틀 {"sides": {자리: {"band", "river", "meld", "reveal_region", "wide", "search": [x0, y0, x1, y1]}}, "how", "recording"}
                     — 자동 패보 S6a(handtrack_auto.py)가 손 설정이 없는 판의 판별 설정 영역으로 씀(11-24). 틀이 없는 자리가 손패 주인이면 S6a 가 멈춤.
  handtrack          (없음 = 판별 설정 · 출력은 공용 자리 handtrack/config · results/handtrack/ 그대로) {"dir": 폴더, "games": [판]} —
                     그 판의 판별 설정 · 출력을 dir 아래(config/ · <판>/ · _work/)에서 읽고 씀(handtrack/ht_redirect.py, 실행 중에만 경로를 바꿈).
                     paifu_auto S6a 가 실행 설정에 적는다(손 설정이 없는 판만).

겹침 검사(load(check=True), 스크립트 시작 때): 이 설정의 판 id · 차례 id 접두사 · 차례 id 가 기존 판(testtruth_1116 의 turns.json · turns_cut*.json ·
정답 파일들의 차례 id)이나 다른 반장 설정(hanchan/ 폴더와 이 설정 파일의 폴더 — 판 목록 · results_dir 이 똑같은 사본은 뺌)과 겹치면 멈춘다
(replaces_base 에 적은 같은 판 id 만 허용). sam2track.GAMES 와의 겹침은 han3.patch 가 본다.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                   # 저장소 루트(mahjong_calc)
CFG_DIR = ROOT / "experiments" / "paifu_frames" / "hanchan"
DEFAULT = CFG_DIR / "h3_1123.json"
WORK = ROOT / "experiments" / "paifu_frames" / "results" / "handtrack" / "_work"   # = htcommon.WORK(여기서 htcommon 을 import 하지 않으려고 같은 값)
BASE = WORK / "testtruth_1116"
TRUTH_FILES = [BASE / "truth_final.json", WORK / "slotgrid_1117" / "truth_r13.json", WORK / "slotgrid_1117" / "truth_fix_1120.json"]


class HanchanError(SystemExit):
    """설정 오류 — 메시지를 찍고 종료 코드 1."""
    def __init__(self, msg: str):
        super().__init__("반장 설정 오류: " + msg)
        self.msg = msg


def _p(v) -> Path:
    p = Path(v)
    return p if p.is_absolute() else ROOT / p


def pop_opt(args: list, name: str, default=None):
    """args 에서 `name 값` 을 꺼내 지우고 값을 돌려준다(없으면 default). args 는 제자리에서 바뀐다."""
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            raise HanchanError(f"{name} 뒤에 값이 없다")
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


class Hanchan:
    def __init__(self, path: Path, d: dict, prep: str | None = None):
        self.path = Path(path).resolve()
        self.raw = d
        g = lambda k, dv=None: d.get(k, dv)  # noqa: E731
        self.id = g("id") or self.path.stem
        self.label = g("label", self.id)
        if not g("results_dir"):
            raise HanchanError(f"{self.path.name}: results_dir 이 없다")
        self.results_dir = _p(d["results_dir"])
        self.prep_dir = _p(prep) if prep else (_p(d["prep_dir"]) if g("prep_dir") else self.results_dir / "_prep")
        self.read_root = g("read_root")
        if not self.read_root:
            raise HanchanError(f"{self.path.name}: read_root 이 없다")
        self.recording = g("recording")
        self.games = list(g("games") or [])
        self.turn_prefix = dict(g("turn_prefix") or {})
        self.replaces_base = list(g("replaces_base") or [])
        f = g("files") or {}
        self.turns_file = self.prep_dir / f.get("turns", "turns.json")
        self.cut_file = self.prep_dir / f.get("turns_cut", "turns_cut.json")
        self.fix_file = self.prep_dir / f.get("turn_fix", "turn_fix.json")
        self.meta_file = self.results_dir / f.get("rounds_meta", "rounds_meta.json")
        self.recfix_file = self.results_dir / f.get("recorder_fix", "recorder_fix.json")
        r = g("recorder") or {}
        self.exe = _p(r["exe"]) if r.get("exe") else self.results_dir / "_bin" / "replay_recorder.exe"
        self.sticks = r.get("sticks")
        h = g("hand") or {}
        self.row_at = dict(h.get("row_at") or {})
        self.cut_lag = int(h.get("cut_lag_ms", 1000))
        self.anchor_lead = int(h.get("anchor_lead_ms", 1500))
        self.row_pad = int(h.get("row_pad_px", 80))
        self.call_turns = list(h.get("call_turns") or [])
        p = g("paifu") or {}
        self.paifu_dir = _p(p["out_dir"]) if p.get("out_dir") else self.prep_dir / "paifu"
        self.title_prefix = p.get("title_prefix", self.label)
        self.names = list(p.get("names") or [f"플레이어 {i}" for i in range(1, 5)])
        self.start_score = int(p.get("start_score", 25000))
        self.event_fix = dict(p.get("event_fix") or {})
        i = g("install") or {}
        self.install_src = _p(i["src"]) if i.get("src") else self.paifu_dir
        self.install_dst = _p(i["dst"]) if i.get("dst") else None
        self.install_prefix = i.get("id_prefix")
        t = g("truth_check") or {}
        self.truth_dir = _p(t["dir"]) if t.get("dir") else self.results_dir / "review"
        self.truth_ids = list(t.get("ids") or [])
        self.truth_page_title = t.get("page_title", f"{self.label} 차례 정답")
        self.truth_page_group = t.get("page_group", f"{self.label} — 확인할 차례")
        self.truth_prep_note = t.get("prep_note", f"{self.label} 확인할 차례")
        c = g("item_check") or {}
        self.item_dir = _p(c["dir"]) if c.get("dir") else self.results_dir / "review2"
        self.item_page_title = c.get("page_title", f"{self.label} 확인")
        self.item_page_heading = c.get("page_heading", f"{self.label} — 확인할 것")
        self.item_prep_note = c.get("prep_note", f"{self.label} 확인할 것")
        self.items = [dict(x) for x in (c.get("items") or [])]
        self.rerun_of = g("rerun_of")
        ar = g("app_record")
        self.app_record = dict(ar) if ar else None
        self.frame = dict(g("frame") or {}) or None
        ht = g("handtrack") or {}
        self.ht_dir = _p(ht["dir"]) if ht.get("dir") else None
        self.ht_games = list(ht.get("games") or [])
        self._validate_self()

    # ---------------------------------------------------------------- 차례 id ↔ 판
    def prefix_of(self, gid: str) -> str:
        for k, v in self.turn_prefix.items():
            if v == gid:
                return k
        raise HanchanError(f"{gid}: turn_prefix 에 이 판이 없다")

    def game_of(self, tid: str) -> str | None:
        """차례 id(또는 판 id) → 이 설정의 판 id. 이 설정의 판이 아니면 None."""
        return self.turn_prefix.get(tid[:3])

    def owns(self, tid: str, gid: str) -> bool:
        return self.game_of(tid) == gid

    # ---------------------------------------------------------------- 검사
    def _validate_self(self):
        name = self.path.name
        err = []
        if not self.games:
            err.append("games 가 비었다")
        if len(set(self.games)) != len(self.games):
            err.append(f"games 에 같은 판이 두 번: {[x for x in self.games if self.games.count(x) > 1]}")
        for k, v in self.turn_prefix.items():
            if len(k) != 3:
                err.append(f"turn_prefix 의 접두사 {k!r} 는 세 글자여야 한다(sam2track.turn_of 가 차례 id 앞 세 글자로 판을 찾음)")
            if v not in self.games:
                err.append(f"turn_prefix {k} → {v}: games 에 없는 판")
            elif v[:3] != k:
                err.append(f"turn_prefix {k} → {v}: 접두사가 판 id 앞 세 글자({v[:3]})와 다르다(truthprep 이 차례 id 를 판 id 앞 세 글자로 지음)")
        for gid in self.games:
            if gid not in self.turn_prefix.values():
                err.append(f"{gid}: turn_prefix 에 이 판의 접두사가 없다")
        if len(set(self.turn_prefix.values())) != len(self.turn_prefix):
            err.append("turn_prefix 의 두 접두사가 같은 판을 가리킨다")
        for gid in self.replaces_base:
            if gid not in self.games:
                err.append(f"replaces_base {gid}: games 에 없는 판")
        for gid in self.row_at:
            if gid not in self.games:
                err.append(f"hand.row_at {gid}: games 에 없는 판")
        for gid in self.event_fix:
            if gid not in self.games:
                err.append(f"paifu.event_fix {gid}: games 에 없는 판")
        for tid in self.call_turns + self.truth_ids:
            if self.game_of(tid) is None:
                err.append(f"차례 {tid}: 접두사 {tid[:3]} 가 turn_prefix 에 없다")
        for it in self.items:
            if it.get("game") not in self.games:
                err.append(f"item_check 항목 {it.get('id')}: 판 {it.get('game')} 가 games 에 없다")
        if self.install_dst is not None and not self.install_prefix:
            err.append("install.id_prefix 가 없다")
        if self.app_record is not None:
            for k in ("captures", "from", "to"):
                if not self.app_record.get(k):
                    err.append(f"app_record.{k} 가 없다")
            if not (self.app_record.get("date") or (self.recording or {}).get("date")):
                err.append("app_record.date 도 recording.date 도 없다")
            for gid in self.app_record.get("check_windows") or {}:
                if gid not in self.games:
                    err.append(f"app_record.check_windows {gid}: games 에 없는 판")
        for gid in self.ht_games:
            if gid not in self.games:
                err.append(f"handtrack.games {gid}: games 에 없는 판")
        if self.ht_games and self.ht_dir is None:
            err.append("handtrack.games 가 있는데 handtrack.dir 이 없다")
        for side, v in ((self.frame or {}).get("sides") or {}).items():
            miss = [k for k in ("band", "river", "meld", "reveal_region", "wide", "search") if not (isinstance(v.get(k), list) and len(v[k]) == 4)]
            if side not in ("bottom", "right", "top", "left") or miss:
                err.append(f"frame.sides.{side}: 자리 이름이 아니거나 영역이 모자람 {miss}")
        if err:
            raise HanchanError(f"{name}: " + " / ".join(err))

    def check_collisions(self):
        """기존 판 · 다른 반장 설정과 판 id · 차례 id 접두사 · 차례 id 가 겹치면 HanchanError."""
        mine = {self.prefix_of(g): g for g in self.games}
        err = []
        # ① 기존 판 목록(차례 목록 · 새 묶음)
        base_turns = BASE / "turns.json"
        known: dict[str, str] = {}          # 판 id → 어디서
        base_tids: set[str] = set()
        files = ([base_turns] if base_turns.exists() else []) + sorted(BASE.glob("turns_cut*.json"))
        for f in files:
            for gg in json.loads(f.read_text(encoding="utf-8")).get("games", []):
                known.setdefault(gg["id"], f.name)
                if f == base_turns and gg["id"] not in self.replaces_base:
                    base_tids.update(t["id"] for t in gg.get("turns", []))
        for gid in self.replaces_base:
            if known.get(gid) is None:
                err.append(f"replaces_base {gid}: 기존 판 목록({base_turns.name})에 없다 — 덮어쓸 판이 아니면 빼라")
        replaced_prefix = {g[:3] for g in self.replaces_base}
        for kid, src in known.items():
            p = kid[:3]
            if p not in mine:
                continue
            if kid == mine[p] and kid in self.replaces_base:
                continue
            if kid == mine[p]:
                err.append(f"판 id {kid} 가 기존 판({src})과 같다 — 다른 판 id 를 쓰거나, 정말 덮어쓸 것이면 replaces_base 에 적어라")
            else:
                err.append(f"차례 id 접두사 {p}({mine[p]}) 가 기존 판 {kid}({src}) 와 겹친다 — 차례 id {p}_dNN 이 섞임, 판 id 앞 세 글자를 바꿔라")
        # ② 정답 파일들의 차례 id(접두사만 겹쳐도 sam2track.truth_all 에서 섞임)
        for f in TRUTH_FILES:
            if not f.exists():
                continue
            ps = {k[:3] for k in json.loads(f.read_text(encoding="utf-8")) if not k.startswith("_")}
            for p in sorted(ps & set(mine)):
                if p not in replaced_prefix:
                    err.append(f"차례 id 접두사 {p}({mine[p]}) 가 정답 파일 {f.name} 의 차례 id 와 겹친다")
        # ③ 이 설정의 차례 목록이 이미 있으면 차례 id 그대로도 본다
        if self.turns_file.exists():
            tids = {t["id"] for gg in json.loads(self.turns_file.read_text(encoding="utf-8")).get("games", []) for t in gg.get("turns", [])}
            both = sorted(tids & base_tids)
            if both:
                err.append(f"차례 id {both[:8]}{' …' if len(both) > 8 else ''} 가 기존 판 목록({base_turns.name})에 이미 있다")
        # ④ 다른 반장 설정(hanchan/ 폴더 + 이 설정 파일이 있는 폴더). 판 목록 · 결과 폴더가 똑같은 설정(같은 반장의 시험용 사본)은 건너뜀
        others = {f.resolve() for d in {CFG_DIR, self.path.parent} if d.exists() for f in d.glob("*.json")} - {self.path}
        for f in sorted(others):
            try:
                o = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(o, dict) or "games" not in o:
                continue
            if list(o.get("games") or []) == self.games and o.get("results_dir") and _p(o["results_dir"]).resolve() == self.results_dir.resolve():
                continue
            if self.rerun_of and o.get("id") == self.rerun_of and list(o.get("games") or []) == self.games:
                continue                      # 같은 반장을 다른 실행 폴더에서 다시 돌리는 설정(paifu_auto.py)
            if o.get("id") == self.id:
                err.append(f"설정 id {self.id} 가 {f.name} 과 같다")
            og = set(o.get("games") or [])
            for p, gid in mine.items():
                if gid in og:
                    err.append(f"판 id {gid} 가 다른 반장 설정 {f.name} 에도 있다")
                elif p in (o.get("turn_prefix") or {}) or any(x[:3] == p for x in og):
                    err.append(f"차례 id 접두사 {p}({gid}) 가 다른 반장 설정 {f.name} 의 판과 겹친다")
        if err:
            raise HanchanError(f"{self.path.name}: " + " / ".join(dict.fromkeys(err)))
        return True

    # ---------------------------------------------------------------- 녹화 자리
    def apply_recording(self, hc):
        """recording 이 있으면 htcommon 의 녹화 자리(REC_ROOT · RECS) · 날짜(to_ms 의 시각만 있는 글)를 바꾼다. 두 번 불러도 한 번만 감쌈."""
        r = self.recording
        if not r:
            return
        hc.REC_ROOT = _p(r["root"])
        hc.RECS = list(r["recs"])
        orig = getattr(hc, "_to_ms_orig", None) or hc.to_ms
        hc._to_ms_orig = orig
        date = r["date"]

        def to_ms(t: str) -> int:
            return orig(t if "T" in t else f"{date}T{t}")
        to_ms.__doc__ = orig.__doc__
        hc.to_ms = to_ms

    def ms_near(self, mmss: str, ref_ms: int, hc) -> int:
        """'MM:SS.s' → ref_ms 와 가장 가까운 시각(ms) — 시는 ref 의 앞 · 같은 · 뒤 시 중 고름(sam2track.ms_of 와 같은 규칙)."""
        h = int(hc.hms(ref_ms)[:2])
        return min((hc.to_ms(f"{x:02d}:{mmss}") for x in (h - 1, h, h + 1) if 0 <= x < 24), key=lambda m: abs(m - ref_ms))


def load(path=None, prep: str | None = None, check: bool = True) -> Hanchan:
    """반장 설정을 읽는다. path 없으면 DEFAULT. prep = prep_dir 덮어쓰기(--prep). check = 겹침 검사."""
    p = _p(path) if path else DEFAULT
    if not p.exists():
        raise HanchanError(f"설정 파일 없음: {p}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HanchanError(f"{p.name}: JSON 이 아님 — {e}")
    h = Hanchan(p, d, prep=prep)
    if check:
        h.check_collisions()
    return h


def from_argv(args: list, check: bool = True) -> Hanchan:
    """args 에서 --hanchan · --prep 를 꺼내(제자리에서 지움) 설정을 읽는다."""
    path = pop_opt(args, "--hanchan")
    prep = pop_opt(args, "--prep")
    return load(path, prep=prep, check=check)
