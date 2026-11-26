"""판 supervisor 명령 한 벌(설계서 docs/paifu_auto_agent_design_1124.md 8-10절 — 3-5 · 3-10 을 코드로, 구현 1번)(2026-11-25).

S7 이 끝난 자동 패보 실행 폴더(paifu_auto.py)에 판마다 꾸러미(<실행>/sup/<판>/)를 만들고, 판 supervisor(에이전트)가 이 명령들로만
의심 차례를 다시 읽히고(reread) · 고르고(take) · 직접 정하고(set) · 검사하고(check) · 묻고(ask) · 마감한다(done).
초안은 꾸러미 안(draft.json)에만 있고, 실행 폴더의 답(read/<차례>/answer.json)은 done 이 마감 검사를 통과했을 때만 바뀐다.
(11-25 밤, 설계서 8-17 4-①) 흐름에 끼움: paifu_auto.py 의 S7s 단계가 판마다 pack 을 부르고 꾸러미(TASK.md · 끝난 표시 decision.json)를 내고 멈춘다 —
모든 판이 마감(done)되면 흐름이 S8 로 간다. 흐름 밖에서 손으로 쓸 때는 지금처럼 done 뒤 `paifu_auto.py next --run <실행> --redo S8`.
이 스크립트는 LLM 을 부르지 않는다. 에이전트(supervisor · 다시 읽기 작업자)는 세션이 띄운다.

  python -X utf8 experiments/paifu_frames/paifu_sup.py pack   --run <실행> --game <판>
  python -X utf8 experiments/paifu_frames/paifu_sup.py reread --pack <꾸러미> --turn <차례> [--frames "053-058[,060-068]"]
  python -X utf8 experiments/paifu_frames/paifu_sup.py take   --pack <꾸러미> --turn <차례> --from first|r1|r2
  python -X utf8 experiments/paifu_frames/paifu_sup.py set    --pack <꾸러미> --turn <차례> --answer <json 글 또는 파일> --evidence "<프레임 번호 · 시각>"|--evidence-file <f> --why "<글>"|--why-file <f>
  python -X utf8 experiments/paifu_frames/paifu_sup.py check  --pack <꾸러미>
  python -X utf8 experiments/paifu_frames/paifu_sup.py ask    --pack <꾸러미> --turn <차례> --candidates "<후보>"|--candidates-file <f> --why "<글>"|--why-file <f>
  python -X utf8 experiments/paifu_frames/paifu_sup.py done   --pack <꾸러미>
  python -X utf8 experiments/paifu_frames/paifu_sup.py status --pack <꾸러미>
  python -X utf8 experiments/paifu_frames/paifu_sup.py score  --run <실행> [--truth-dir <폴더>]
  python -X utf8 experiments/paifu_frames/paifu_sup.py replay --pack <꾸러미> --from <다른 실행의 마감된 꾸러미>   # 재생(LLM 0, 8-17 4-①) — 뒤에 done 을 따로 부름
(저장소 루트에서. 거절은 종료 코드 2 + "거절: …")

꾸러미(pack 이 만듦): TASK.md(supervisor 지시문 — 8-10 "지시문에 들어갈 것" 1 ~ 7) · game.md(판 요약 · 차례 표 · 영향 · S7 검사) ·
  hands.md(복원 매 순 손패 · 정렬 어긋남) · turns/<차례>/answer.json(처음 답 사본) + source.txt(프레임 · 사건 목록 폴더 = <실행>/read/<차례>/, 읽기만) ·
  pack.json(경로 · 한도 · 차례 목록) · base_rows.json(처음 답 복원 — check 가 "처음과 달라진 순" 을 셈) · impact.json(game.md 영향 칸의 원자료) ·
  log.jsonl(부를 때마다 한 줄) · scratch/(supervisor 임시 작업 자리). pack.json version 2(11-25 두 판 시험 뒤: 다시 읽기 주의는 자유 글
  --note 대신 프레임 범위 --frames 만 — 다시 읽기 TASK.md 에는 코드가 만든 고정 글 한 줄, 낱말 거름은 없앰 · 긴 글 인자는 파일로 · scratch/).
  version 1 꾸러미(rereads[] 에 note 칸)도 status · score · done 이 그대로 읽는다.
  pack.json version 3(11-26, 설계서 8-18): 읽기 답의 확신 숫자 칸 p — low_p_first(처음 답이 낮은 p 인 차례, 낮은 p = paifu_auto.answer_p < P_LOW) 칸 ·
  game.md 차례 표의 p 열 · TASK.md 에 p 한 줄. version 1 · 2 꾸러미(low_p_first 없음)는 status · score · done · replay 가 전과 같이 읽는다.
  설계서 8-22(11-26 오후): 낮은 p 는 기록만 — paifu_auto.LOW_P_ACTS 가 False 면 마감 검사 ① 이 low_p_first 를 안 보고, TASK.md 의 "의심으로 볼 것" p 줄 ·
  done 거절 까닭의 p 구절(TASK_P_LINES)을 뺀다. low_p_first · game.md p 열 · status 의 p 는 그대로(기록). True 면 8-18 동작 그대로.
  pack.json version 4(11-26, 설계서 8-19 (다) 4): window_shift(차례 → 초 — 준비 읽기 unsure 의 alt 로 돌리면 그 차례 창이 1.0초 넘게 움직인 "창 흔들림",
  paifu_auto.s6a_window_turns) 칸 · game.md 차례 표의 "창 흔들림" 열. version 1 ~ 3 꾸러미(칸 없음)는 전과 같이 읽는다.
  넣지 않는 것: 사용자 확인값 · 11-23 사람 고름(human_picked_1123) · v2 낱말 규칙 목록(questions.jsonl · signals) · 다른 판 · 옛 손 설정 메모.
  사용자 답이 apply 된 실행(state.answered)이면 pack 을 거절한다(처음 답 자리에 사용자 값이 있으므로).
명령이 쓰는 곳: 꾸러미 폴더 안(reread/<차례>_r<n>/ · try/<n>/ · _impact/ · _base/ · draft.json · decision.json · questions_sup.jsonl · log.jsonl).
  예외 둘: done 이 실행 폴더 read/<차례>/ 에 answer.json(바뀐 차례만) · answer_r0.json(처음 답 — S7 과 같은 방식) · sup.json(손댄 표시)를 쓰고,
  score 가 <실행>/sup/score.md · score.json · log.jsonl · _score/ 를 쓴다. score 는 마감(decision.json)된 판만 센다 — 마감 전 판은 이름만.
한도(설계서 3-10 의 시작값): 다시 읽기 판당 ⌈읽은 차례 수 ÷ 2⌉ · 차례당 2번, check 판당 6번, set 제한 없음(모두 표시).
"바뀐 차례" = 초안의 칸 값(kind · k · j · end_order · gone)이 처음 답과 다름. 칸 값이 같은 다시 읽기를 take 하면 처음 답 파일을 그대로 둔다(글만 다른 답으로 덮지 않음).
마감 검사(done): ① 처음 답이 unsure: true 이거나 낮은 p(version 3 의 low_p_first — 설계서 8-22 부터 paifu_auto.LOW_P_ACTS 가 True 일 때만)이거나 창 흔들림(version 4 의 window_shift)인 차례는 reread · set · ask 중 하나 ② 바뀐 차례가 있으면 마지막 check 가 지금 초안 그대로 돌았고 통과 —
  통과 못 했으면 바뀐 차례가 모두 ask 여야 하고, 그 차례들은 처음 답으로 반영(초안은 질문 줄의 supervisor 안으로 남김) ③ 답이 안 온 다시 읽기 꾸러미 없음 ④ 한도 안
  ⑤ 답이 온 다시 읽기 가운데 칸 값이 마감 초안과 다른 것이 있는 차례는 초안이 그 차례의 set 이거나 · ask 가 있거나 · 초안 칸 값이 독립 읽기
  (처음 답 + 다시 읽기들) 가운데 둘 이상과 같아야 함(설계서 3-10 "다르면 셋째 읽기 · 직접 정하기 · 질문" 의 코드 문 — 11-25 검토에서 더함).
replay(8-17 4-①): 다른 실행의 마감된 꾸러미의 초안(turns · takes · sets · asks · checks)과 다시 읽기 폴더(답 포함)를 아직 손대지 않은 이 꾸러미로 옮긴다.
  같은 판 · 같은 차례 목록 · 처음 답 칸 값이 모두 같을 때만(아니면 거절). 마감은 하지 않는다 — 뒤에 done 을 부르면 같은 마감 검사를 지나 반영된다.
  옮긴 check 기록은 다시 돌리지 않는다(replayed 표시 — 초안 칸 값이 같으므로 sig 가 같음).
check 의 "통과" = paifu_auto S7 과 같은 잣대(조립 성공 · 손패 있음 · 빠진 답 없음 · 손패 장수 문제 없음 · 같은 패 5장 없음) + 모든 초안 답 꼴(answer_form_error) 이상 없음.
  정렬 어긋남은 보고만 한다(통과 잣대 아님).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paifu_auto as pa  # noqa: E402

ROOT = pa.ROOT
HT = pa.HT
PY = pa.PY
REREAD_PER_TURN = 2
CHECK_PER_GAME = 6
FROM_CHOICES = ["first"] + [f"r{i}" for i in range(1, REREAD_PER_TURN + 1)]
SLOT_KEYS = ("kind", "k", "j", "end_order", "gone")
MSG_ASK = "남은 의심 차례는 ask 로"
P_LOW = pa.HEDGE_PCT_MAX   # 설계서 8-18: 낮은 p = 처음 답의 p 가 None 이 아니고 이 값 밑
# 설계서 8-22: paifu_auto.LOW_P_ACTS 가 False 면 pack 이 TASK.md 에서 빼는 글(TASK_TMPL 에 꼭 한 번씩 — 템플릿 자체는 안 바꿈)
TASK_P_LINES = (" · 처음 답의 p 가 @P_LOW@ 밑인 차례를 그냥 둠", "- 답의 `p`(읽기가 스스로 적은 맞을 가능성)가 @P_LOW@ 밑\n")
PACK_VERSION = 4   # 4 = 설계서 8-19 window_shift


def reread_limit(n_turns: int) -> int:
    return math.ceil(n_turns / 2)


class Reject(Exception):
    pass


# ------------------------------------------------------------------ 작은 도구
jl, wj, wt, now = pa.jl, pa.wj, pa.wt, pa.now


def posix(p) -> str:
    return Path(p).resolve().as_posix()


def append_line(p: Path, o: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")


def slot(a: dict) -> dict:
    """답의 칸 값(조립에 쓰는 것) — 글 칸은 뺌. end_order · gone 은 글자 목록으로."""
    out = {}
    for k in SLOT_KEYS:
        v = a.get(k)
        if k in ("end_order", "gone") and v is not None:
            v = [str(x) for x in v]
        if k in ("k", "j") and v is not None:
            try:
                v = int(v)
            except (TypeError, ValueError):
                pass
        out[k] = v
    return out


def is_low_p(a: dict) -> bool:
    """설계서 8-18: 낮은 p = 답의 p(paifu_auto.answer_p — 없거나 꼴이 틀리면 None = 모름)가 None 이 아니고 P_LOW 밑."""
    v = pa.answer_p(a)
    return v is not None and v < P_LOW


def p_show(a: dict) -> str:
    """status 에 보일 p 글: 읽을 수 있으면 값, 칸이 있는데 꼴이 틀리면 그 값과 '꼴 틀림'(= 모름)."""
    v = pa.answer_p(a)
    return pa.p_txt(v) if v is not None else f"{a.get('p')!r}(꼴 틀림 — 모름)"


def sig_of(answers: dict) -> str:
    return hashlib.sha256(json.dumps({t: slot(a) for t, a in sorted(answers.items())}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ 다시 읽기에 넘기는 것 = 프레임 범위뿐(11-25 두 판 시험 뒤 사용자 결정 — 자유 글 주의를 없앰)
FRAMES_RE = re.compile(r"^\d+(-\d+)?(,\d+(-\d+)?)*$")
FRAMES_MAX = 3


def frame_numbers(read_dir: Path) -> list:
    f = read_dir / "frames.txt"
    if not f.exists():
        return []
    out = []
    for ln in f.read_text(encoding="utf-8").splitlines():
        s = ln.split()
        if s and s[0].isdigit():
            out.append((int(s[0]), len(s[0])))
    return out


def parse_frames(s: str, read_dir: Path) -> list:
    """'053-058,060-068' · '055' → [(53, 58), (60, 68)]. 숫자 · - · , 만 · 시작 ≤ 끝 · 그 차례 frames.txt 번호 안 · 범위 FRAMES_MAX 개까지."""
    if not FRAMES_RE.match(s or ""):
        raise Reject(f"--frames 는 숫자 · '-' · ',' 만(예 053-058 또는 053-058,060-068, 한 장이면 055): {s!r}")
    rs = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if lo > hi:
            raise Reject(f"--frames 범위 시작 > 끝: {part}")
        rs.append((lo, hi))
    if len(rs) > FRAMES_MAX:
        raise Reject(f"--frames 범위는 {FRAMES_MAX}개까지(지금 {len(rs)})")
    nums = [n for n, _ in frame_numbers(read_dir)]
    if not nums:
        raise Reject(f"frames.txt 가 없거나 비었음: {posix(read_dir / 'frames.txt')}")
    for lo, hi in rs:
        if lo < min(nums) or hi > max(nums):
            raise Reject(f"--frames {lo}-{hi} 가 이 차례 프레임 번호({min(nums):03d} ~ {max(nums):03d}) 밖")
    return rs


def frames_line(rs: list, width: int = 3) -> str:
    seg = " · ".join(f"{lo:0{width}d}" if lo == hi else f"{lo:0{width}d} ~ {hi:0{width}d}" for lo, hi in rs)
    return f"프레임 {seg} 을 특히 자세히 본다(다른 프레임도 처음부터 다 본다)."


def text_arg(a, name: str, required: bool = False) -> str:
    """글 인자: --<name> 글 또는 --<name>-file UTF-8 파일(둘 중 하나)."""
    v, fp = getattr(a, name, None), getattr(a, f"{name}_file", None)
    if v is not None and fp is not None:
        raise Reject(f"--{name} 와 --{name}-file 은 둘 중 하나만")
    if fp is not None:
        try:
            v = Path(fp).read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as e:
            raise Reject(f"--{name}-file 을 못 읽음(UTF-8): {fp} — {e}")
    if required and not (v or "").strip():
        raise Reject(f"--{name}(또는 --{name}-file)이 비었음")
    return v or ""


# ------------------------------------------------------------------ 조립 하위 프로세스(han3_paifu.build 를 한 판에 — paifu_auto.INNER 의 hero_hands · four_check 를 그대로 씀)
def _inner_funcs() -> str:
    s = pa.INNER
    a, b = s.index("def hero_hands"), s.index("res = {{}}")
    return s[a:b].replace("{{", "{").replace("}}", "}")


SUP_INNER = r'''
import json, os, sys
from collections import Counter
sys.path.insert(0, @HERE@); sys.path.insert(0, @HT@)
os.environ["HAN3_FINAL"] = "result"
import hanchan_cfg as hcfg
import han3_paifu as hp
import han3
from replay import key, sort_scheme
spec = json.loads(open(@SPEC@, encoding="utf-8").read())
cfg = hcfg.load(@CFG@)
hp.configure(cfg, spec.get("out"))
han3.patch()
order = dict((r["id"], han3.meta_of(r["id"])) for r in hp.jl(han3.META)["rounds"])
norm = lambda t: ("5" + t[1]) if t and t[0] == "0" else t
@FUNCS@

def sort_bad(row, sch):
    if not row:
        return None
    ks = [key(v, sch) for v in row]
    return sum(1 for i in range(len(ks) - 1) if ks[i] is not None and ks[i + 1] is not None and ks[i] > ks[i + 1])

def rows_of(out, final_row):
    """손패 주인의 매 순(버림 하나 = 한 순): 시작 줄 · 뽑은 패(울기면 울기) · 버린 패 · 끝 줄 · 정렬 어긋남(끝 손패 정렬 기준)."""
    h = out["hero"]
    sch = sort_scheme(final_row)
    rows, cur, prev_end = [], None, None
    for n, e in enumerate(out["events"]):
        if e["seat"] != h:
            continue
        if e["type"] == "draw":
            cur = {"event": n, "type": "draw", "start": e.get("hand"), "drawn": e.get("tile"), "guess": bool(e.get("guess"))}
        elif e["type"] == "call":
            cur = {"event": n, "type": "call", "start": prev_end, "call": {"kind": e.get("kind"), "tiles": e.get("tiles")},
                   "after_call": e.get("hand"), "drawn": None, "guess": bool(e.get("guess"))}
        elif e["type"] == "discard":
            r = cur or {"event": n, "type": "none", "start": prev_end, "drawn": None, "guess": bool(e.get("guess"))}
            r.update(discard=e.get("tile"), tsumogiri=e.get("tsumogiri"), riichi=e.get("riichi"), end=e.get("hand"), at=e.get("at"))
            r["sort_bad_start"] = sort_bad(r["start"], sch)
            r["sort_bad_end"] = sort_bad(r["end"], sch)
            rows.append(r)
            prev_end, cur = e.get("hand"), None
    if cur is not None:   # 끝(쯔모 화료 뽑기 등)
        cur["final"] = True
        cur["sort_bad_start"] = sort_bad(cur.get("start"), sch)
        rows.append(cur)
    return rows

gid = spec["game"]
meta = order[gid]
base_root = han3.READ_ROOT
res = {}
for job in spec["jobs"]:
    han3.READ_ROOT = job.get("root") or base_root
    try:
        out, info = hp.build(gid, meta, True)
        hands = bool(info["hands"])
        final_row = list(out["result"].get("hand") or []) if out["result"].get("type") != "draw" else []
        if not final_row:
            final_row = [t for t in (next((e.get("hand") for e in reversed(out["events"]) if e["seat"] == out["hero"] and e.get("hand")), None) or [])]
        res[job["name"]] = {"ok": True, "hands": hands, "missing": info["missing_answers"], "hand_count_problems": info.get("hand_count_problems") or [],
                            "four": four_check(out) if hands else [], "call_log": info.get("call_log"),
                            "rows": rows_of(out, final_row) if hands else [], "hero_hands": [list(x[1]) for x in hero_hands(out)] if hands else [],
                            "result": out["result"], "round": out.get("round"), "hero": out.get("hero")}
    except BaseException as e:
        res[job["name"]] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:800]}
han3.READ_ROOT = base_root
print("JSON" + json.dumps(res, ensure_ascii=False))
'''


def run_inner(r: pa.Run, game: str, jobs: list, work: Path, code_tmpl: str = None, spec_extra: dict = None) -> dict:
    """han3_paifu 조립을 하위 프로세스로(work 폴더에 spec · 코드 · 기록). 실패하면 {"_error": 까닭}."""
    work.mkdir(parents=True, exist_ok=True)
    sf = work / "inner_spec.json"
    wj(sf, {"game": game, "jobs": jobs, "out": posix(work / "paifu"), **(spec_extra or {})})
    if code_tmpl is None:
        code = (SUP_INNER.replace("@HERE@", repr(str(HERE))).replace("@HT@", repr(str(HT))).replace("@SPEC@", repr(str(sf)))
                .replace("@CFG@", repr(str(r.cfg_f))).replace("@FUNCS@", _inner_funcs()))
    else:
        code = code_tmpl
    cf = work / "inner.py"
    wt(cf, code)
    t0 = time.time()
    p = pa.run([PY, "-X", "utf8", cf], log=work / "inner.log", check=False)
    s = p.stdout or ""
    if p.returncode != 0 or "JSON" not in s:
        return {"_error": f"조립 하위 프로세스 실패(rc {p.returncode}): " + ((p.stderr or "") + s)[-1500:].strip(), "_s": round(time.time() - t0, 1)}
    out = json.loads(s[s.rindex("JSON") + 4:].strip())
    out["_s"] = round(time.time() - t0, 1)
    return out


def passed(v: dict, form_errors: dict) -> bool:
    return bool(v.get("ok") and v.get("hands") and not v.get("missing") and not v.get("hand_count_problems") and not v.get("four") and not form_errors)


# ------------------------------------------------------------------ 꾸러미
class Pack:
    def __init__(self, d):
        self.d = Path(d).resolve()
        f = self.d / "pack.json"
        if not f.exists():
            raise Reject(f"꾸러미가 아님(pack.json 없음): {posix(self.d)}")
        self.meta = jl(f)
        self.draft_f = self.d / "draft.json"
        self.draft = jl(self.draft_f) if self.draft_f.exists() else None

    @property
    def turns(self):
        return list(self.meta["turns"])

    @property
    def run_dir(self) -> Path:
        return Path(self.meta["run"])

    def save(self):
        wj(self.draft_f, self.draft)

    def first(self, tid) -> dict:
        return jl(self.d / "turns" / tid / "answer.json")

    def reread_dir(self, tid, n) -> Path:
        return self.d / "reread" / f"{tid}_r{n}"

    def rereads_of(self, tid) -> list:
        return [x for x in self.draft["rereads"] if x["turn"] == tid]

    def draft_answer(self, tid) -> dict:
        v = self.draft["turns"][tid]
        return self.first(tid) if v["from"] == "first" else v["answer"]

    def drafts(self) -> dict:
        return {t: self.draft_answer(t) for t in self.turns}

    def changed(self) -> list:
        return [t for t in self.turns if slot(self.draft_answer(t)) != slot(self.first(t))]

    def asked(self) -> set:
        return {q["turn"] for q in self.draft["asks"]}

    def need_turn(self, tid):
        if tid not in self.meta["turns"]:
            raise Reject(f"이 판의 읽은 차례가 아님: {tid} (차례: {', '.join(self.turns)})")

    def need_open(self):
        if self.draft.get("done"):
            raise Reject("이미 마감(done)한 꾸러미 — 바꿀 수 없음")

    def limits(self):
        return self.meta["limits"]


def precheck(r: pa.Run, g: str):
    """폴더를 만들기 전에 거를 것(실행 폴더가 아님 · 판 없음 · S7 전 · 사용자 답 반영됨)."""
    if r.state is None:
        raise Reject(f"실행 폴더가 아님(state.json 없음): {posix(r.d)}")
    if g not in r.games():
        raise Reject(f"판이 이 실행에 없음: {g}")
    if r.stage("S7")["status"] != "done":
        raise Reject(f"S7 이 안 끝난 실행(S7 {r.stage('S7')['status']}) — supervisor 는 S7 이 끝난 실행 폴더에 돌린다")
    if r.state.get("answered"):
        raise Reject(f"사용자 답이 apply 된 실행(answered {len(r.state['answered'])}칸) — 꾸러미에 사용자 확인값이 들어가므로 만들지 않음(unapply 한 사본에서)")


def collect(r: pa.Run, g: str, d: Path) -> dict:
    """pack 재료: 차례 목록 · 처음 답 · 판 머리 · 차례 표 · 처음 답 복원(매 순 손패) · 영향 · S7 검사. 설정을 읽고(겹침 검사) 조립을 돈다."""
    cfg = r.cfg()
    tids = pa.game_answer_ids(r, g)
    if not tids:
        raise Reject(f"{g}: 읽은 차례가 없음")
    answers = {}
    for t in tids:
        f = pa.active_answer(r, t)
        if not f.exists():
            raise Reject(f"{t}: 답 없음 {posix(f)}")
        answers[t] = jl(f)
    mf = jl(r.d / cfg.meta_file.name)
    meta = dict({x["id"]: x for x in mf["rounds"]}[g])
    meta.setdefault("bottom_seat", mf.get("bottom_seat"))
    turns_all = pa.turns_after_fix(cfg, g)
    rr = jl(r.d / g / "result_read.json")
    s7 = r.stage("S7")
    s7_last = ((s7.get("checks") or [{}])[-1].get("result") or {}).get(g)
    s7_bad = (s7.get("final_bad") or {}).get(g)
    base = run_inner(r, g, [{"name": "first", "root": None}], d / "_base")
    if "_error" in base or not base.get("first", {}).get("ok"):
        raise Reject(f"{g}: 처음 답 조립 실패 — {base.get('_error') or base.get('first', {}).get('error')}")
    imp = impacts(r, g, tids, answers, d / "_impact")
    win = pa.s6a_window_turns(r)   # 설계서 8-19 (다) 4: 준비 읽기 alt 로 창만 움직인 차례(이 판의 읽은 차례만)
    return {"tids": tids, "answers": answers, "meta": meta, "turns_all": turns_all, "rr": rr, "s7_last": s7_last, "s7_bad": s7_bad,
            "base": base["first"], "impact": imp, "plan_hand": list(r.stage("S6")["plan"]["hand"].get(g, [])),
            "window_shift": {t: win[t] for t in tids if t in win}}


def impacts(r: pa.Run, g: str, tids: list, answers: dict, work: Path) -> dict:
    """차례마다 다른 후보(paifu_auto.alt_candidates — 답에 적힌 후보, 없으면 k · j ±1)로 바꿨을 때 바뀌는 순 수 — paifu_auto turn_jobs 와 같은 셈을 꾸러미 안에서."""
    if work.exists():
        shutil.rmtree(work)
    jobs, meta = [], {}
    for tid in tids:
        ans = answers[tid]
        n = len([x for x in ans.get("end_order") or [] if x != "D"]) + (1 if ans.get("kind") == "hand" else 0)
        if ans.get("kind") != "hand":
            meta[tid] = {"cands": [], "src": f"kind {ans.get('kind')} — 후보 규칙 없음"}
            continue
        cands, src = pa.alt_candidates(ans, n)
        cj = []
        for kj, v in cands:
            va = pa.variant_answer(ans, kj, v)
            if va is None:
                continue
            name = f"{kj}={v}"
            root = work / tid / name.replace("=", "")
            for t in tids:
                wj(root / t / "answer.json", answers[t])
            wj(root / tid / "answer.json", va)
            cj.append({"name": name, "root": posix(root)})
        meta[tid] = {"cands": [c["name"] for c in cj], "src": src}
        if cj:
            jobs.append({"qid": tid, "game": g, "cands": cj})
    res = {}
    if jobs:
        sf = work / "impact_spec.json"
        wj(sf, {"mode": "impact", "jobs": jobs})
        code = pa.INNER.format(here=str(HERE), ht=str(HT), spec=str(sf), cfg=str(r.cfg_f))
        cf = work / "impact.py"
        wt(cf, code)
        p = pa.run([PY, "-X", "utf8", cf], log=work / "impact.log", check=False)
        s = p.stdout or ""
        if p.returncode != 0 or "JSON" not in s:
            raise Reject(f"{g}: 영향 계산 실패(rc {p.returncode}) " + ((p.stderr or "") + s)[-800:])
        res = json.loads(s[s.rindex("JSON") + 4:].strip())
    return {tid: {**meta[tid], "impact": res.get(tid, []), "summary": pa.summarize_impact(res.get(tid, []))} for tid in tids}


def align_rows(rows: list, turns_all: list) -> list:
    """복원 순(버림 하나 = 한 순)을 차례 목록(t_ready 뒤)에 끝에서부터 맞춘다 — 차례 목록 앞의 순은 차례 id 없음(짐작 순)."""
    disc = [r for r in rows if "discard" in r]
    out = [dict(r) for r in rows]
    di = [i for i, r in enumerate(out) if "discard" in r]
    for k, t in enumerate(reversed(turns_all)):
        if k >= len(di):
            break
        i = di[len(di) - 1 - k]
        out[i]["turn"] = t["id"]
        out[i]["label"] = t.get("label")
        out[i]["turn_tile_ok"] = pa.norm(t.get("tile")) == pa.norm(out[i].get("discard"))
    for n, i in enumerate(di, 1):
        out[i]["jun"] = n
    if len(disc) < len(turns_all):
        out.append({"warn": f"복원 순 {len(disc)} < 차례 목록 {len(turns_all)}"})
    return out


def fmt_row(x) -> str:
    return " ".join(x) if x else "—"


TASK_TMPL = """# 판 supervisor — 판 `@GAME@`

이 꾸러미 폴더: `@PACK@`
명령은 저장소 루트(`@ROOT@`)에서 `python -X utf8 experiments/paifu_frames/paifu_sup.py <명령> --pack @PACK@ …` 로 부른다.

## 1. 하는 일
이 판의 차례 답들 가운데 틀렸을 수 있는 것을 가려서 풀고, 못 푼 것만 사용자 질문으로 남긴다. 차례를 처음부터 다시 다 읽지 않는다.

## 2. 일하는 순서
1. `game.md` · `hands.md` 를 읽는다.
2. 모든 차례의 답 글을 읽는다 — `turns/<차례>/answer.json`(kind · k · j · end_order · unsure · p · events_used · why).
3. 의심 차례를 고른다(아래 3).
4. 차례마다 `reread` 로 독립 다시 읽기를 맡기거나, 그 차례의 프레임(`turns/<차례>/source.txt` 에 적힌 폴더의 `frames.txt` · `events.txt` · `raw/`)을 열어 보고 `set` 으로 답을 정한다.
5. `check` 로 초안을 돌려 본다.
6. 못 풀면 `ask`.
7. `done`.

명령:
- `reread --turn <차례> [--frames "053-058,060-068"]` — 다시 읽기 꾸러미 `reread/<차례>_r<n>/` 를 만들고 작업자에게 줄 말을 찍는다. 작업자에게 넘길 수 있는 것은 더 볼 프레임 범위뿐이다(숫자 범위 3개까지, 안 줘도 됨).
- `take --turn <차례> --from first|r1|r2` — 그 차례의 초안 답을 처음 답 또는 다시 읽기 답 가운데 하나로 고른다.
- `set --turn <차례> --answer '<답 json>' --evidence "<프레임 번호 · 시각>" --why "<글>"` — 직접 정한 답을 초안으로 둔다(답 꼴은 `turns/<차례>/answer.json` 과 같게, evidence 필수). set 한 차례는 표시된다.
- `check` — 지금 초안으로 이 판을 거꾸로 복원 · 검사한다(매 순 손패 · 검사 결과 · 정렬 어긋남 수 · 처음과 달라진 순).
- `ask --turn <차례> --candidates "<후보>" --why "<글>"` — 사용자 질문 한 줄을 더한다.
- 긴 글은 파일로: `set` 은 `--evidence-file` · `--why-file`, `ask` 는 `--candidates-file` · `--why-file`(UTF-8 파일, 글 인자와 둘 중 하나).
- `status` — 라운드 · 다시 읽기 수 · 초안 상태 · 남은 한도 · 다시 읽기 답이 처음과 같은지(칸 값 비교).
- `done` — 마감. 거절되면 까닭을 찍는다(처음 답이 unsure 인 차례를 그냥 둠 · 처음 답의 p 가 @P_LOW@ 밑인 차례를 그냥 둠 · game.md 의 창 흔들림 차례를 그냥 둠 · 처음과 다른 초안인데 마지막 check 가 그 초안으로 통과하지 않음 · 답이 안 온 다시 읽기 · 다시 읽기가 초안과 다른데 set · ask · 둘 이상 일치가 없음 · 한도).

## 3. 의심으로 볼 것(예시가 아니라 종류)
- 답 글이 스스로 확신이 낮다고 하거나 다른 답을 저울질함
- 답의 `p`(읽기가 스스로 적은 맞을 가능성)가 @P_LOW@ 밑
- 글과 k · j · end_order 가 서로 안 맞음
- 복원된 손패가 그 사람의 정렬과 어긋남
- 검사 실패
- 영향이 큰데 근거가 얇음

## 4. 풀었다고 볼 때
독립 다시 읽기가 처음 답과 같음, 또는 직접 프레임을 보고 근거를 적을 수 있음. 둘 다 아니면 `ask`.

## 5. 지킬 것
- 이 꾸러미 폴더와 이 판의 `read/<차례>/` 폴더(`pack.json` 의 `read_dirs`) 밖을 열지 않는다. 그림을 이어 붙이거나 스크립트를 쓸 때는 이 꾸러미의 `scratch/` 에만 쓴다.
- 다시 읽기 작업자에게 앞 답 · 칸 번호 · 패를 알리지 않는다(넘길 수 있는 것은 프레임 범위뿐). 작업자에게는 `reread` 가 찍어 준 말만 준다.
- 한도: 다시 읽기는 이 판 @RR_GAME@개 · 차례당 @RR_TURN@번, `check` 는 @CHECK@번. 넘으면 명령이 거절한다 — 남은 의심 차례는 `ask` 로.
- 답은 명령으로만 낸다. 파일을 직접 고치지 않는다.

## 6. 작업자 띄우기
다시 읽기 꾸러미 하나에 하위 에이전트 하나(Opus · effort high)를 띄우고, `reread` 가 찍어 준 말만 준다. 여러 개면 한꺼번에 띄운다.
띄울 수 없으면 이 폴더에 `next_actions.json`(`{"reread": ["<다시 읽기 꾸러미 폴더>", …], "why": "<글>"}`)을 쓰고 멈춘다 — 세션이 작업자를 돌린 뒤 이어 부른다.

## 7. 끝낼 때 보고
고른 차례와 까닭, 푼 방법, 남긴 질문, 쓴 명령 수.
"""


def write_pack(d: Path, r_dir: Path, g: str, c: dict):
    """collect 결과 → 꾸러미 파일들(TASK.md · game.md · hands.md · turns/ · pack.json · base_rows.json · draft.json)."""
    tids, answers = c["tids"], c["answers"]
    read_dirs = {t: posix(r_dir / "read" / t) for t in tids}
    lim = {"reread_game": reread_limit(len(tids)), "reread_turn": REREAD_PER_TURN, "check": CHECK_PER_GAME, "set": None}
    for t in tids:
        wj(d / "turns" / t / "answer.json", answers[t])
        wt(d / "turns" / t / "source.txt", read_dirs[t] + "\n")
    rows = align_rows(c["base"].get("rows") or [], c["turns_all"])
    wj(d / "base_rows.json", {"rows": rows, "hero_hands": c["base"].get("hero_hands")})
    wj(d / "impact.json", c["impact"])
    (d / "scratch").mkdir(exist_ok=True)   # supervisor 의 임시 작업 자리(그림 붙이기 · 스크립트)
    meta, rr = c["meta"], c["rr"]
    hero_side = pa.SIDES[(meta["hero"] - meta["bottom_seat"]) % 4] if meta.get("hero") is not None and meta.get("bottom_seat") is not None else "?"
    # game.md
    L = [f"# 판 요약 — `{g}`", "",
         f"- 국: {meta.get('round')}" + (f" {meta.get('honba')}본장" if meta.get("honba") else "") + f" · 선 자리 {meta.get('dealer')} · 손패 주인 자리 {meta.get('hero')}(사진 {hero_side} 쪽)",
         f"- 결과: {rr.get('end')}" + (f" · {rr.get('win_type')} · 화료패 {rr.get('win_tile')}" if rr.get("end") == "win" else "")
         + f" · 끝 손패(닫힌 줄, 왼쪽부터) {fmt_row(rr.get('hand'))}"
         + (" · 울기 " + "; ".join(f"{m.get('kind')} {' '.join(m.get('tiles') or [])}" for m in ((rr.get("melds") or {}).get(hero_side) or [])) if (rr.get("melds") or {}).get(hero_side) else ""),
         f"- 읽은 차례 {len(tids)}개(손패 {len([t for t in tids if t in c['plan_hand']])} · 울기 {len([t for t in tids if t not in c['plan_hand']])}) · 차례 목록 전체 {len(c['turns_all'])}순",
         "", "## 차례 표", "",
         "영향 = 그 답이 다른 후보(답에 적힌 후보, 없으면 k · j ±1)로 바뀌면 손패가 바뀌는 순의 수(가장 큰 값) · 결과가 바뀌는지.", "",
         "p = 읽기가 답에 적은 맞을 가능성(%) — `—` 는 없음(또는 꼴이 틀림).", "",
         "창 흔들림 = 준비 읽기(줄이 선 때 · 공개 · 손패 줄 영역)의 다른 후보로 돌리면 이 차례의 프레임 창이 움직인 초(1.0초 넘게) — 빈 칸은 없음.", "",
         "| 차례 | 순 | 버린 패 | 리치 | kind | k | j | end_order | unsure | p | 창 흔들림 | 영향 |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    riichi_seen = False
    code_turns = []
    for t in c["turns_all"]:
        tid = t["id"]
        rch = "리치" if t.get("sideways") else ""
        if tid in answers:
            a = answers[tid]
            im = c["impact"].get(tid) or {}
            sm = im.get("summary") or {}
            if im.get("cands"):
                imp_s = f"최대 {sm.get('max_hand_turns')}순" + (" · 결과 바뀜" if sm.get("result_changed") else "") + f" (후보 {', '.join(im['cands'])})"
                bad = [x for x in im.get("impact") or [] if not x.get("ok")]
                if bad:
                    imp_s += f" · 조립 실패 후보 {len(bad)}"
            else:
                imp_s = f"— ({im.get('src')})"
            L.append(f"| {tid} | {t.get('label')} | {t.get('tile')} | {rch} | {a.get('kind')} | {a.get('k')} | {a.get('j')} | {' '.join(str(x) for x in a.get('end_order') or [])}"
                     + (f" (gone {a.get('gone')})" if a.get("gone") else "") + f" | {'true' if a.get('unsure') else 'false'} | {pa.p_txt(pa.answer_p(a))} | {(str(c['window_shift'][tid]) + '초') if tid in c['window_shift'] else ''} | {imp_s} |")
        else:
            why = "리치 뒤 — 규칙(쯔모기리)" if riichi_seen else "읽지 않음(코드로 정함)"
            code_turns.append((tid, t.get("label"), t.get("tile"), why))
            L.append(f"| {tid} | {t.get('label')} | {t.get('tile')} | {rch} | (코드) | | | | | | | {why} |")
        if t.get("sideways"):
            riichi_seen = True
    L += ["", "## 코드로 정한 차례", ""]
    L += [f"- {tid}({lab}순 · {tile}): {why}" for tid, lab, tile, why in code_turns] or ["- 없음"]
    v = c["s7_last"] or {}
    L += ["", "## S7 검사 결과(처음 답)", "",
          f"- 조립 {'됨' if v.get('ok') else '실패 — ' + str(v.get('error'))} · 손패 {'있음' if v.get('hands') else '없음'} · 빠진 답 {v.get('missing') or '없음'} · "
          f"손패 장수 문제 {v.get('hand_count_problems') or '없음'} · 같은 패 5장 {v.get('four') or '없음'}",
          f"- S7 이 끝에 남긴 문제: {c['s7_bad'] or '없음'}"]
    if v.get("call_log"):
        L += [f"- 울기 차례 {k}: {'울기 답' if x.get('how') == 'answer' else '정렬로 짐작'} — {x.get('note')}" for k, x in v["call_log"].items()]
    wt(d / "game.md", "\n".join(L) + "\n")
    # hands.md
    H = [f"# 복원된 매 순 손패 — `{g}`(처음 답으로 끝 손패에서 거꾸로)", "",
         "정렬 어긋남 = 끝 손패에서 읽은 정렬(무늬 순서 · 숫자 방향)로 줄의 이웃 쌍이 거꾸로 선 곳의 수(시작 줄 / 끝 줄). 짐작 = 차례 목록 앞(줄이 선 때 전) 순.", "",
         "| 순 | 차례 | 시작 줄 | 뽑은 패 / 울기 | 버린 패 | 끝 줄 | 정렬 어긋남(시작 / 끝) |", "|---|---|---|---|---|---|---|"]
    tot = 0
    for x in rows:
        if "warn" in x:
            H.append(f"| ⚠ | | {x['warn']} | | | | |")
            continue
        got = (f"울기 {x['call'].get('kind')} {' '.join(x['call'].get('tiles') or [])} → {fmt_row(x.get('after_call'))}" if x.get("type") == "call" else (x.get("drawn") or "—"))
        sb, se = x.get("sort_bad_start"), x.get("sort_bad_end")
        tot += (sb or 0)
        if x.get("final"):
            H.append(f"| 끝 | | {fmt_row(x.get('start'))} | {got} | (화료) | | {sb} / |")
            continue
        H.append(f"| {x.get('jun')}{' (짐작)' if x.get('guess') else ''} | {x.get('turn') or ''}{'' if x.get('turn_tile_ok', True) else ' ⚠ 버린 패가 차례 목록과 다름'} | {fmt_row(x.get('start'))} | {got} | "
                 f"{x.get('discard')}{' 쯔모기리' if x.get('tsumogiri') else ''}{' 리치' if x.get('riichi') else ''} | {fmt_row(x.get('end'))} | {sb} / {se} |")
    H += ["", f"시작 줄 정렬 어긋남 합: {tot}"]
    wt(d / "hands.md", "\n".join(H) + "\n")
    # TASK.md
    tmpl = TASK_TMPL
    if not pa.LOW_P_ACTS:   # 설계서 8-22: 낮은 p 는 기록만 — 의심 줄 · 거절 까닭 구절을 뺌
        for x in TASK_P_LINES:
            if tmpl.count(x) != 1:
                raise SystemExit(f"TASK_TMPL 에 뺄 p 글이 꼭 한 번이 아님({tmpl.count(x)}번): {x!r} — 설계서 8-22")
            tmpl = tmpl.replace(x, "")
    task = (tmpl.replace("@GAME@", g).replace("@PACK@", posix(d)).replace("@ROOT@", ROOT.as_posix())
            .replace("@RR_GAME@", str(lim["reread_game"])).replace("@RR_TURN@", str(lim["reread_turn"])).replace("@CHECK@", str(lim["check"]))
            .replace("@P_LOW@", str(P_LOW)))
    wt(d / "TASK.md", task)
    wj(d / "pack.json", {"_note": "paifu_sup.py pack — 판 supervisor 꾸러미(설계서 8-10). 이 파일 · turns/ 는 바꾸지 않는다(초안은 draft.json).",
                         "version": PACK_VERSION, "created": now(), "run": posix(r_dir), "game": g, "turns": tids,
                         "unsure_first": [t for t in tids if answers[t].get("unsure")],
                         "low_p_first": [t for t in tids if is_low_p(answers[t])], "window_shift": c["window_shift"], "read_dirs": read_dirs,
                         "first_sha": {t: pa.sha(r_dir / "read" / t / "answer.json") for t in tids}, "limits": lim,
                         "files": ["TASK.md", "game.md", "hands.md", "turns/", "pack.json", "base_rows.json", "impact.json", "draft.json", "log.jsonl", "scratch/"]})
    wj(d / "draft.json", {"turns": {t: {"from": "first"} for t in tids}, "rereads": [], "takes": [], "sets": [], "asks": [], "checks": [], "done": False})


# ------------------------------------------------------------------ 명령
def cmd_pack(a):
    r = pa.Run(a.run)
    d = r.d / "sup" / a.game
    if (d / "pack.json").exists():
        print(f"이미 있음: {posix(d)} — 그대로 둠")
        return d, {"exists": True}
    precheck(r, a.game)
    t0 = time.time()
    if d.exists():   # 만들다 끊긴 꾸러미(pack.json 없음)는 지우고 다시
        shutil.rmtree(d)
    d.mkdir(parents=True)
    try:
        c = collect(r, a.game, d)
    except (Reject, SystemExit) as e:   # SystemExit = 반장 설정 오류(겹침 검사 등) · 하위 프로세스 실패
        shutil.rmtree(d, ignore_errors=True)
        raise Reject(f"꾸러미를 못 만듦 — {e}")
    write_pack(d, r.d, a.game, c)
    s = round(time.time() - t0, 1)
    print(f"→ {posix(d)} · 차례 {len(c['tids'])} · 다시 읽기 한도 {reread_limit(len(c['tids']))} · {s}s")
    return d, {"turns": len(c["tids"]), "s": s}


def cmd_reread(a):
    pk = Pack(a.pack)
    pk.need_open()
    pk.need_turn(a.turn)
    src = Path(pk.meta["read_dirs"][a.turn])
    rs = parse_frames(a.frames, src) if a.frames is not None else []
    width = max((w for _, w in frame_numbers(src)), default=3)
    lim = pk.limits()
    mine = pk.rereads_of(a.turn)
    if len(mine) >= lim["reread_turn"]:
        raise Reject(f"{a.turn}: 차례당 다시 읽기 한도 {lim['reread_turn']}번을 다 씀 — {MSG_ASK}")
    if len(pk.draft["rereads"]) >= lim["reread_game"]:
        raise Reject(f"판당 다시 읽기 한도 {lim['reread_game']}개를 다 씀 — {MSG_ASK}")
    n = len(mine) + 1
    dst = pk.reread_dir(a.turn, n)
    if dst.exists():
        raise Reject(f"이미 있는 폴더: {posix(dst)}")
    (dst / "work").mkdir(parents=True)
    s_src = src.as_posix()
    for f in ("TASK.md", "frames.txt", "events.txt"):
        if (src / f).exists():
            txt = (src / f).read_text(encoding="utf-8").replace(s_src + "/answer.json", (dst / "answer.json").as_posix()).replace(s_src + "/work", (dst / "work").as_posix())
            if f == "TASK.md" and rs:   # 코드가 만든 고정 글 한 줄만(범위가 없으면 절을 안 넣음)
                add = f"## 이번 읽기에서 더 볼 곳\n{frames_line(rs, width)}\n\n"
                i = txt.find("\n## 답")
                txt = (txt[:i + 1] + add + txt[i + 1:]) if i >= 0 else (txt.rstrip("\n") + "\n\n" + add)
            wt(dst / f, txt)
    msg = f"`{(dst / 'TASK.md').as_posix()}` 를 읽고 그대로 하라. 답은 `{(dst / 'answer.json').as_posix()}` 한 파일만 쓴다."
    pk.draft["rereads"].append({"turn": a.turn, "n": n, "dir": posix(dst), "frames": [list(x) for x in rs], "message": msg, "at": now()})
    pk.save()
    print(f"→ {posix(dst)}")
    print("작업자에게 줄 말(이것만 준다):")
    print(msg)
    left_g = pk.limits()["reread_game"] - len(pk.draft["rereads"])
    print(f"남은 다시 읽기: 이 판 {left_g} · 이 차례 {lim['reread_turn'] - n}")
    return pk.d, {"turn": a.turn, "n": n, "dir": posix(dst)}


def load_answer_arg(s: str) -> dict:
    p = Path(s)
    try:
        if len(s) < 400 and p.exists():
            return jl(p)
    except OSError:
        pass
    try:
        o = json.loads(s)
    except json.JSONDecodeError as e:
        raise Reject(f"--answer 가 JSON 도 파일도 아님 — {e}")
    if not isinstance(o, dict):
        raise Reject("--answer 는 JSON 객체여야 함")
    return o


def cmd_take(a):
    pk = Pack(a.pack)
    pk.need_open()
    pk.need_turn(a.turn)
    if a.src == "first":
        ans = pk.first(a.turn)
        pk.draft["turns"][a.turn] = {"from": "first"}
    else:
        n = int(a.src[1:])
        f = pk.reread_dir(a.turn, n) / "answer.json"
        if not any(x["n"] == n for x in pk.rereads_of(a.turn)):
            raise Reject(f"{a.turn}: 다시 읽기 {a.src} 가 없음")
        if not f.exists():
            raise Reject(f"{a.turn}: 다시 읽기 {a.src} 답이 아직 없음 ({posix(f)})")
        try:
            ans = jl(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise Reject(f"{a.turn}: 다시 읽기 {a.src} 답이 JSON 이 아님 — {e}")
        why = pa.answer_form_error(ans)
        if why:
            raise Reject(f"{a.turn}: 다시 읽기 {a.src} 답 꼴 이상 — {why}")
        if ans.get("id") not in (None, a.turn):
            raise Reject(f"{a.turn}: 다시 읽기 {a.src} 답의 id 가 {ans.get('id')}")
        pk.draft["turns"][a.turn] = {"from": a.src, "answer": ans}
    same = slot(ans) == slot(pk.first(a.turn))
    pk.draft["takes"].append({"turn": a.turn, "from": a.src, "same_as_first": same, "at": now()})
    pk.save()
    print(f"{a.turn}: 초안 = {a.src}" + (" (칸 값이 처음 답과 같음)" if same else " (처음 답과 다름 — check 로 돌려 볼 것)"))
    return pk.d, {"turn": a.turn, "from": a.src, "same_as_first": same}


def cmd_set(a):
    pk = Pack(a.pack)
    pk.need_open()
    pk.need_turn(a.turn)
    evidence = text_arg(a, "evidence")
    why_s = text_arg(a, "why")
    if not evidence.strip():
        raise Reject("evidence 가 비었음 — 근거 프레임 번호 · 시각을 적는다")
    ans = load_answer_arg(a.answer)
    if ans.get("id") not in (None, a.turn):
        raise Reject(f"답의 id {ans.get('id')} ≠ {a.turn}")
    ans = {**ans, "id": a.turn}
    why = pa.answer_form_error(ans)
    if why:
        raise Reject(f"답 꼴 이상 — {why}")
    first = pk.first(a.turn)
    if (ans.get("kind") == "call") != (first.get("kind") == "call"):
        raise Reject(f"울기 차례 · 손패 차례를 바꿀 수 없음(처음 kind {first.get('kind')} · 새 kind {ans.get('kind')})")
    n_first = len(first.get("end_order") or [])   # hand(n−1 + D) · tsumogiri(n) · call 모두 끝 줄 장수 = end_order 길이
    if len(ans.get("end_order") or []) != n_first:
        raise Reject(f"end_order 길이 {len(ans.get('end_order') or [])} ≠ 처음 답 {n_first}(줄 장수가 다름)")
    k = len(pk.draft["sets"]) + 1
    pk.draft["turns"][a.turn] = {"from": "set", "answer": ans, "evidence": evidence, "why": why_s, "set_no": k}
    pk.draft["sets"].append({"turn": a.turn, "no": k, "answer": ans, "evidence": evidence, "why": why_s, "at": now()})
    pk.save()
    same = slot(ans) == slot(first)
    print(f"{a.turn}: 초안 = set #{k}" + (" (칸 값이 처음 답과 같음)" if same else " (처음 답과 다름 — check 로 돌려 볼 것)"))
    return pk.d, {"turn": a.turn, "set_no": k, "same_as_first": same}


def cmd_ask(a):
    pk = Pack(a.pack)
    pk.need_open()
    pk.need_turn(a.turn)
    cands = text_arg(a, "candidates")
    why_s = text_arg(a, "why")
    if not cands.strip():
        raise Reject("후보가 비었음")
    pk.draft["asks"].append({"turn": a.turn, "candidates": cands, "why": why_s, "at": now()})
    pk.save()
    print(f"{a.turn}: 질문 한 줄 더함(이 판 질문 {len(pk.draft['asks'])})")
    return pk.d, {"turn": a.turn, "asks": len(pk.draft["asks"])}


def row_diff(base: list, new: list) -> list:
    """처음과 달라진 순: (순 · 차례 · 무엇이 — 시작 줄 묶음 / 시작 줄 순서 / 뽑은 패 / 끝 줄)."""
    out = []
    bd = [x for x in base if "discard" in x or x.get("final")]
    nd = [x for x in new if "discard" in x or x.get("final")]
    if len(bd) != len(nd):
        return [{"jun": None, "what": f"순 수 다름 {len(nd)} ≠ {len(bd)}"}]
    for x, y in zip(bd, nd):
        w = []
        if Counter(x.get("start") or []) != Counter(y.get("start") or []):
            w.append("시작 줄 묶음")
        elif (x.get("start") or []) != (y.get("start") or []):
            w.append("시작 줄 순서")
        if x.get("drawn") != y.get("drawn"):
            w.append("뽑은 패")
        if (x.get("end") or []) != (y.get("end") or []):
            w.append("끝 줄")
        if w:
            out.append({"jun": y.get("jun") or ("끝" if y.get("final") else None), "turn": y.get("turn"), "what": w,
                        "start_first": x.get("start"), "start_now": y.get("start"), "drawn_first": x.get("drawn"), "drawn_now": y.get("drawn")})
    return out


def cmd_check(a):
    pk = Pack(a.pack)
    pk.need_open()
    lim = pk.limits()
    if len(pk.draft["checks"]) >= lim["check"]:
        raise Reject(f"판당 check 한도 {lim['check']}번을 다 씀 — {MSG_ASK}")
    n = len(pk.draft["checks"]) + 1
    tdir = pk.d / "try" / str(n)
    if tdir.exists():
        shutil.rmtree(tdir)
    drafts = pk.drafts()
    for t, ans in drafts.items():
        wj(tdir / "read" / t / "answer.json", ans)
    form = {t: e for t, e in ((t, pa.answer_form_error(x)) for t, x in drafts.items()) if e}
    r = pa.Run(pk.run_dir)
    res = run_inner(r, pk.meta["game"], [{"name": "try", "root": posix(tdir / "read")}], tdir)
    v = res.get("try") or {"ok": False, "error": res.get("_error")}
    base = jl(pk.d / "base_rows.json")
    turns_all = None
    try:
        turns_all = pa.turns_after_fix(r.cfg(), pk.meta["game"]) if v.get("ok") else None
    except BaseException as e:   # 설정 읽기 실패 — 차례 id 없이 셈
        v.setdefault("note", f"차례 목록 못 읽음: {e}"[:300])
    rows = align_rows(v.get("rows") or [], turns_all) if turns_all is not None else (v.get("rows") or [])
    diff = row_diff(base["rows"], rows) if v.get("ok") and v.get("hands") else []
    ok = passed(v, form)
    changed = pk.changed()
    sbad = sum((x.get("sort_bad_start") or 0) for x in rows if "discard" in x)
    sbad0 = sum((x.get("sort_bad_start") or 0) for x in base["rows"] if "discard" in x)
    rep = {"n": n, "at": now(), "sig": sig_of(drafts), "passed": ok, "changed_turns": changed,
           "drafts_from": {t: pk.draft["turns"][t]["from"] for t in pk.turns},
           "result": {k: v.get(k) for k in ("ok", "error", "hands", "missing", "hand_count_problems", "four", "note")},
           "form_errors": form, "sort_bad_start_total": sbad, "sort_bad_start_total_first": sbad0, "rows_changed": diff, "rows": rows, "s": res.get("_s")}
    wj(tdir / "report.json", rep)
    M = [f"# check {n} — `{pk.meta['game']}` · {rep['at']}", "",
         f"- **{'통과' if ok else '통과 못 함'}** · 처음과 다른 초안: {', '.join(changed) or '없음'}",
         f"- 조립 {'됨' if v.get('ok') else '실패 — ' + str(v.get('error'))} · 손패 {'있음' if v.get('hands') else '없음'} · 빠진 답 {v.get('missing') or '없음'} · "
         f"손패 장수 문제 {v.get('hand_count_problems') or '없음'} · 같은 패 5장 {v.get('four') or '없음'} · 답 꼴 이상 {form or '없음'}",
         f"- 시작 줄 정렬 어긋남 합: {sbad}(처음 답 {sbad0})",
         f"- 처음과 달라진 순: {len(diff)}", ""]
    for x in diff:
        M.append(f"  - {x.get('jun')}순 {x.get('turn') or ''}: {', '.join(x['what']) if isinstance(x.get('what'), list) else x.get('what')}"
                 + (f" — 시작 줄 {fmt_row(x.get('start_first'))} → {fmt_row(x.get('start_now'))}" if x.get("start_first") is not None else "")
                 + (f" · 뽑은 패 {x.get('drawn_first')} → {x.get('drawn_now')}" if x.get("drawn_first") != x.get("drawn_now") else ""))
    if rows and v.get("hands"):
        M += ["", "| 순 | 차례 | 시작 줄 | 뽑은 패 / 울기 | 버린 패 | 끝 줄 | 정렬 어긋남(시작 / 끝) |", "|---|---|---|---|---|---|---|"]
        for x in rows:
            if "warn" in x:
                M.append(f"| ⚠ | | {x['warn']} | | | | |")
                continue
            got = (f"울기 {x['call'].get('kind')} {' '.join(x['call'].get('tiles') or [])}" if x.get("type") == "call" else (x.get("drawn") or "—"))
            M.append(f"| {x.get('jun') or ('끝' if x.get('final') else '')}{' (짐작)' if x.get('guess') else ''} | {x.get('turn') or ''} | {fmt_row(x.get('start'))} | {got} | "
                     f"{x.get('discard') or ('(화료)' if x.get('final') else '')} | {fmt_row(x.get('end'))} | {x.get('sort_bad_start')} / {x.get('sort_bad_end')} |")
    wt(tdir / "report.md", "\n".join(M) + "\n")
    pk.draft["checks"].append({"n": n, "at": rep["at"], "sig": rep["sig"], "passed": ok, "changed_turns": changed, "report": posix(tdir / "report.md")})
    pk.save()
    print("\n".join(M[:6]))
    for x in diff[:12]:
        print(f"  {x.get('jun')}순 {x.get('turn') or ''}: {x.get('what')}")
    print(f"보고서: {posix(tdir / 'report.md')} · 남은 check {lim['check'] - n}")
    return pk.d, {"n": n, "passed": ok, "changed": changed, "rows_changed": len(diff), "error": v.get("error") or res.get("_error")}


def reread_answers(pk: Pack, tid: str) -> list:
    """답이 온 다시 읽기 [(n, 답 또는 None(JSON 아님 · 꼴 이상))]."""
    out = []
    for x in pk.rereads_of(tid):
        f = Path(x["dir"]) / "answer.json"
        if not f.exists():
            continue
        try:
            a = jl(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            a = None
        if a is not None and pa.answer_form_error(a):
            a = None
        out.append((x["n"], a))
    return out


def closure(pk: Pack) -> dict:
    """마감 검사 ① ~ ④. {"ok", "why": [...], "apply": {차례: 답}, "revert_asked": [...]}"""
    why = []
    asked = pk.asked()
    rr_turns = {x["turn"] for x in pk.draft["rereads"]}
    set_turns = {x["turn"] for x in pk.draft["sets"]}
    unsure_first = list(pk.meta.get("unsure_first") or [])
    low_first = list(pk.meta.get("low_p_first") or []) if pa.LOW_P_ACTS else []   # version 3(설계서 8-18) — 옛 꾸러미는 칸이 없어 전과 같음 · 8-22 스위치가 꺼지면 기록만
    win = dict(pk.meta.get("window_shift") or {})          # version 4(설계서 8-19) — 옛 꾸러미는 칸이 없어 전과 같음
    order = unsure_first + [x for x in low_first if x not in unsure_first]
    order += [x for x in pk.turns if x in win and x not in order]
    for t in order:
        if t not in asked and t not in rr_turns and t not in set_turns:
            what = ((["unsure"] if t in unsure_first else []) + ([f"p {pa.p_txt(pa.answer_p(pk.first(t)))} < {P_LOW}"] if t in low_first else [])
                    + ([f"창 흔들림 {win[t]}초"] if t in win else []))
            why.append(f"① {t}: 처음 답이 {' · '.join(what)} 인데 reread · set · ask 가 없음")
    changed = pk.changed()
    drafts = pk.drafts()
    last = pk.draft["checks"][-1] if pk.draft["checks"] else None
    apply = {t: drafts[t] for t in changed}
    revert = []
    if changed:
        good = bool(last and last["passed"] and last["sig"] == sig_of(drafts))
        if not good:
            un = [t for t in changed if t not in asked]
            state = "check 를 안 돌림" if not last else ("마지막 check 가 지금 초안과 다름" if last["sig"] != sig_of(drafts) else "마지막 check 가 통과 못 함")
            if un:
                why.append(f"② 처음과 다른 초안 {un} — {state}(통과 못 한 채 마감하려면 그 차례를 ask 로)")
            else:
                revert = list(changed)    # 모두 ask — 처음 답으로 반영하고 초안은 질문 줄에
                apply = {}
    for x in pk.draft["rereads"]:
        f = Path(x["dir"]) / "answer.json"
        okf = f.exists()
        if okf:
            try:
                jl(f)
            except (json.JSONDecodeError, UnicodeDecodeError):
                okf = False
        if not okf:
            why.append(f"③ 다시 읽기 {x['turn']} r{x['n']} 답이 안 옴({posix(f)})")
    # ⑤ 다시 읽기가 초안과 다르면: 초안이 그 차례의 set 이거나 · ask 가 있거나 · 초안 칸 값이 독립 읽기(처음 답 + 답이 온 다시 읽기) 가운데 둘 이상과 같아야 함
    for t in pk.turns:
        got = reread_answers(pk, t)
        if not got:
            continue
        dsl = slot(drafts[t])
        diff = [n for n, a in got if a is None or slot(a) != dsl]
        if not diff:
            continue
        v = pk.draft["turns"][t]
        agree = (slot(pk.first(t)) == dsl) + sum(1 for _, a in got if a is not None and slot(a) == dsl)
        if not ((v["from"] == "set" and t in set_turns) or t in asked or agree >= 2):
            why.append(f"⑤ {t}: 다시 읽기 {', '.join(f'r{n}' for n in diff)} 가 초안과 다른데 set · ask · 둘 이상 일치가 없음")
    lim = pk.limits()
    if len(pk.draft["rereads"]) > lim["reread_game"]:
        why.append(f"④ 다시 읽기 {len(pk.draft['rereads'])} > 판 한도 {lim['reread_game']}")
    for t, c in Counter(x["turn"] for x in pk.draft["rereads"]).items():
        if c > lim["reread_turn"]:
            why.append(f"④ {t} 다시 읽기 {c} > 차례 한도 {lim['reread_turn']}")
    if len(pk.draft["checks"]) > lim["check"]:
        why.append(f"④ check {len(pk.draft['checks'])} > 한도 {lim['check']}")
    return {"ok": not why, "why": why, "apply": apply, "revert_asked": revert, "changed": changed}


def cmd_done(a):
    pk = Pack(a.pack)
    pk.need_open()
    c = closure(pk)
    if not c["ok"]:
        raise Reject("마감 검사 통과 못 함 — " + " / ".join(c["why"]))
    run_read = pk.run_dir / "read"
    stale = [t for t in pk.turns if pa.sha(run_read / t / "answer.json") != pk.meta["first_sha"][t]]
    if stale:
        raise Reject(f"실행 폴더의 답이 꾸러미를 만든 뒤 바뀜: {stale} — 꾸러미를 새로(sup/<판> 을 치우고 pack)")
    asked = pk.asked()
    rr_turns = {x["turn"] for x in pk.draft["rereads"]}
    set_turns = {x["turn"] for x in pk.draft["sets"]}
    log_n = sum(1 for _ in open(pk.d / "log.jsonl", encoding="utf-8")) if (pk.d / "log.jsonl").exists() else 0
    turns = {}
    for t in pk.turns:
        v = pk.draft["turns"][t]
        how = []
        if t in rr_turns:
            how.append(f"reread×{len(pk.rereads_of(t))}")
        if t in set_turns:
            how.append("set")
        if t in asked:
            how.append("ask")
        turns[t] = {"from": v["from"], "changed": t in c["changed"], "applied": t in c["apply"], "reverted_for_ask": t in c["revert_asked"],
                    "how": how, "unsure_first": t in (pk.meta.get("unsure_first") or []), "marked": bool(set(how) - {"ask"}) and t in c["apply"]}
        if "low_p_first" in pk.meta:   # version 3(설계서 8-18)
            turns[t]["low_p_first"] = t in pk.meta["low_p_first"]
        if "window_shift" in pk.meta:  # version 4(설계서 8-19)
            turns[t]["window_shift"] = pk.meta["window_shift"].get(t)
        if v["from"] == "set":
            turns[t].update(evidence=v.get("evidence"), why=v.get("why"))
    for t, ans in c["apply"].items():
        d = run_read / t
        keep = d / "answer_r0.json"
        if not keep.exists():
            shutil.copyfile(d / "answer.json", keep)
        wj(d / "answer.json", ans)
        v = pk.draft["turns"][t]
        wj(d / "sup.json", {"_note": "paifu_sup.py done — supervisor 가 바꾼 답(표시: 사용자 표본 확인에 먼저)", "pack": posix(pk.d), "from": v["from"],
                            "evidence": v.get("evidence"), "why": v.get("why"), "at": now()})
    qs = []
    for q in pk.draft["asks"]:
        t = q["turn"]
        qs.append({"id": t, "kind": "turn_slot", "stage": "sup", "game": pk.meta["game"], "signal": "sup:ask", "candidates": q["candidates"], "why": q["why"],
                   "current": slot(pa.jl(run_read / t / "answer.json")), "sup_draft": slot(pk.draft_answer(t)) if t in c["revert_asked"] else None})
    wt(pk.d / "questions_sup.jsonl", "".join(json.dumps(q, ensure_ascii=False) + "\n" for q in qs))
    dec = {"_note": "paifu_sup.py done — 판 supervisor 마감 기록", "at": now(), "game": pk.meta["game"], "run": pk.meta["run"],
           "applied": sorted(c["apply"]), "reverted_for_ask": c["revert_asked"], "asks": pk.draft["asks"], "turns": turns,
           "counts": {"turns": len(pk.turns), "rereads": len(pk.draft["rereads"]), "sets": len(pk.draft["sets"]), "takes": len(pk.draft["takes"]),
                      "checks": len(pk.draft["checks"]), "asks": len(pk.draft["asks"]), "commands_logged": log_n + 1},
           "next": f"python -X utf8 experiments/paifu_frames/paifu_auto.py next --run {pa.rel(pk.run_dir)} --redo S8"}
    wj(pk.d / "decision.json", dec)
    pk.draft["done"] = True
    pk.draft["done_at"] = dec["at"]
    pk.save()
    print(f"마감: 반영 {len(c['apply'])}차례 {sorted(c['apply'])} · 질문 {len(qs)} · 처음 답으로 돌린 질문 차례 {c['revert_asked']}")
    print(f"다음: {dec['next']}")
    return pk.d, {"applied": sorted(c["apply"]), "asks": len(qs), "reverted": c["revert_asked"]}


def cmd_status(a):
    pk = Pack(a.pack)
    lim = pk.limits()
    dr = pk.draft
    last = dr["checks"][-1] if dr["checks"] else None
    print(f"판 {pk.meta['game']} · 차례 {len(pk.turns)} · {'마감됨 ' + str(dr.get('done_at')) if dr.get('done') else '마감 전'}")
    print(f"라운드(check) {len(dr['checks'])}/{lim['check']}" + (f" · 마지막 check {last['n']}: {'통과' if last['passed'] else '통과 못 함'}{'' if last['sig'] == sig_of(pk.drafts()) else ' (그 뒤 초안이 바뀜)'}" if last else ""))
    print(f"다시 읽기 {len(dr['rereads'])}/{lim['reread_game']}(차례당 {lim['reread_turn']}) · set {len(dr['sets'])} · take {len(dr['takes'])} · ask {len(dr['asks'])}")
    asked = pk.asked()
    ch = set(pk.changed())
    for t in pk.turns:
        v = dr["turns"][t]
        rr = pk.rereads_of(t)
        got = dict(reread_answers(pk, t))
        first = pk.first(t)
        fs = slot(first)

        def rstate(n):
            if n not in got:
                return "답 기다림"
            if got[n] is None:
                return "답 꼴 이상"
            return ("처음과 같음" if slot(got[n]) == fs else "처음과 다름") + (f" · p {p_show(got[n])}" if "p" in got[n] else "")   # p 는 칸 값 비교 밖(8-18)
        rs = ", ".join(f"r{x['n']} = {rstate(x['n'])}" for x in rr)
        print(f"  {t}: 초안 {v['from']}{' · 처음과 다름' if t in ch else ''}{' · unsure(처음)' if t in (pk.meta.get('unsure_first') or []) else ''}"
              f"{(' · p(처음) ' + p_show(first) + ('(낮음)' if is_low_p(first) else '')) if 'p' in first else ''}"
              f"{(' · 창 흔들림 ' + str(pk.meta['window_shift'][t]) + '초') if t in (pk.meta.get('window_shift') or {}) else ''}"
              f"{' · 다시 읽기 ' + rs if rr else ''}{' · ask' if t in asked else ''}")
    c = closure(pk)
    print("마감 검사: " + ("통과할 수 있음" if c["ok"] else " / ".join(c["why"])))
    return pk.d, {"checks": len(dr["checks"]), "rereads": len(dr["rereads"]), "sets": len(dr["sets"]), "asks": len(dr["asks"]), "closure_ok": c["ok"]}


# ------------------------------------------------------------------ score(평가 — 사용자 확인값은 여기서만 읽는다)
def user_values(truth_dir: Path) -> dict:
    """사용자 확인값(차례 답만): <truth_dir>/answers_user.json 의 kind 가 hand · tsumogiri · call 인 칸."""
    f = truth_dir / "answers_user.json"
    if not f.exists():
        return {}
    return {k: v for k, v in jl(f).items() if not k.startswith("_") and isinstance(v, dict) and v.get("kind") in ("hand", "tsumogiri", "call")}


def cmd_score(a):
    r = pa.Run(a.run)
    sd = r.d / "sup"
    packs = sorted(p.parent for p in sd.glob("*/pack.json"))
    if not packs:
        raise Reject(f"꾸러미가 없음: {posix(sd)}")
    truth_dir = Path(a.truth_dir) if a.truth_dir else (pa.ROOT / (r.state.get("hand_settings") or r.state.get("reuse") or "") / "review")
    uv = user_values(truth_dir)
    per_game = []
    tot = Counter()
    conf_rows, changed_rows = [], []
    undone = [jl(d / "pack.json")["game"] for d in packs if not (d / "decision.json").exists()]   # 마감 전 판은 이름만(세지 않음)
    for d in [d for d in packs if (d / "decision.json").exists()]:
        pk = Pack(d)
        g = pk.meta["game"]
        dec = jl(d / "decision.json")
        asked = pk.asked()
        rr_turns = {x["turn"] for x in pk.draft["rereads"]}
        set_turns = {x["turn"] for x in pk.draft["sets"]}
        touched = asked | rr_turns | set_turns
        changed = [t for t in pk.turns if (dec["turns"][t]["applied"] if dec else slot(pk.draft_answer(t)) != slot(pk.first(t)))]
        final = {t: (pk.draft_answer(t) if (t in changed) else pk.first(t)) for t in pk.turns}
        v2 = [t for t in pk.turns if pa.turn_signal(pk.first(t))[0]]     # v2 낱말 규칙(paifu_auto.turn_signal)을 처음 답에 — 견줌용(꾸러미에는 안 넣음)
        t_first = t_last = None
        lf = d / "log.jsonl"
        n_cmd = Counter()
        if lf.exists():
            ls = [json.loads(x) for x in lf.read_text(encoding="utf-8").splitlines() if x.strip()]
            if ls:
                t_first, t_last = ls[0]["at"], ls[-1]["at"]
            n_cmd = Counter(x["cmd"] for x in ls)
        per_game.append({"game": g, "done": bool(dec), "turns": len(pk.turns), "asks": len(pk.draft["asks"]), "rereads": len(pk.draft["rereads"]),
                         "sets": len(pk.draft["sets"]), "checks": len(pk.draft["checks"]), "changed": changed, "touched": sorted(touched),
                         "v2": v2, "commands": dict(n_cmd), "first_at": t_first, "last_at": t_last})
        tot.update({"asks": len(pk.draft["asks"]), "rereads": len(pk.draft["rereads"]), "sets": len(pk.draft["sets"]), "checks": len(pk.draft["checks"]),
                    "changed": len(changed), "turns": len(pk.turns), "v2": len(v2), "v2_touched": len([t for t in v2 if t in touched]),
                    "new_touched": len([t for t in touched if t not in v2])})
        for t in pk.turns:
            if t in uv:
                ua = pa.user_turn_answer(uv[t], pk.first(t))
                same = slot(final[t])["kind"] == ua["kind"] and slot(final[t])["end_order"] == [str(x) for x in ua["end_order"]]
                state = "ask 에 남음" if t in asked else ("supervisor 가 풂" if t in (rr_turns | set_turns) else "손대지 않음")
                verdict = "같음" if same else None
                if not same:
                    verdict = hands_same(r, g, pk, final, t, ua, sd / "_score" / g / t)
                conf_rows.append({"turn": t, "game": g, "state": state, "how": sorted(({"reread"} if t in rr_turns else set()) | ({"set"} if t in set_turns else set()) | ({"ask"} if t in asked else set())),
                                  "changed": t in changed, "final_vs_user": verdict, "first_vs_user": "같음" if (slot(pk.first(t))["kind"] == ua["kind"] and slot(pk.first(t))["end_order"] == [str(x) for x in ua["end_order"]]) else "다름"})
            if t in changed:
                changed_rows.append({"turn": t, "game": g, "user": t in uv})
    def ok_verdict(v):
        return v in ("같음", "결과 같음(손패 같음)")
    solved = [x for x in conf_rows if x["state"] == "supervisor 가 풂"]
    silent = [x for x in solved if not ok_verdict(x["final_vs_user"])]
    ch_user = [x for x in conf_rows if x["changed"]]
    # 판 결과 · 기록 질문(그대로) — 실행의 questions.jsonl 가운데 차례 질문이 아닌 것(꾸러미 판만)
    games = {x["game"] for x in per_game}
    qf = r.d / "questions.jsonl"
    other_q = [json.loads(x) for x in qf.read_text(encoding="utf-8").splitlines() if x.strip()] if qf.exists() else []
    other_q = [q for q in other_q if q.get("kind") != "turn_slot" and q.get("game") in games]
    smf = r.d / "samples.jsonl"
    samples = [json.loads(x) for x in smf.read_text(encoding="utf-8").splitlines() if x.strip()] if smf.exists() else []
    samples = [q for q in samples if q.get("game") in games]
    L = [f"# supervisor 평가 — `{pa.rel(r.d)}` · {now()}", "",
         f"마감 전(세지 않음): {', '.join(undone) or '없음'}", "",
         f"마감된 판 {len(per_game)}개({', '.join(x['game'] for x in per_game) or '없음'}) · 사용자 확인값 `{pa.rel(truth_dir / 'answers_user.json')}` 차례 {len(uv)}개 중 이 판들 몫 {len(conf_rows)}", "",
         "| 볼 것 | supervisor | 견줄 값(v2 · 이 판들 몫) |", "|---|---|---|",
         f"| 차례 질문 수(ask) + 판 결과 · 기록 질문(그대로) | {tot['asks']} + {len(other_q)} = {tot['asks'] + len(other_q)} | 낱말 규칙이 올린 차례 {tot['v2']}(그중 사용자 확인 차례 {len([x for x in conf_rows if any(x['turn'] in y['v2'] for y in per_game)])}) · 표본 {len(samples)}(실행 samples.jsonl) |",
         f"| 사용자 확인 차례가 ask 에 남음 / supervisor 가 풂 / 손대지 않음 | {len([x for x in conf_rows if x['state'] == 'ask 에 남음'])} / {len(solved)} / {len([x for x in conf_rows if x['state'] == '손대지 않음'])} (전체 {len(conf_rows)}) | v2 는 여섯 모두 올림(이 판들 몫 {len([x for x in conf_rows if any(x['turn'] in y['v2'] for y in per_game)])}) |",
         f"| 풀었다면 그 답이 사용자 확인값과 같은가 | 같음 {len([x for x in solved if ok_verdict(x['final_vs_user'])])} · 어긋남(조용한 틀림) {len(silent)} {[x['turn'] for x in silent] or ''} | 어긋남 0 이어야 |",
         f"| supervisor 가 답을 바꾼 차례 · 그중 확인값 있는 것 맞음 / 틀림 | {tot['changed']} · {len([x for x in ch_user if ok_verdict(x['final_vs_user'])])} / {len([x for x in ch_user if not ok_verdict(x['final_vs_user'])])} · 확인값 없는 {tot['changed'] - len(ch_user)} 은 가릴 수 없음 | — |",
         f"| v2 가 올린 차례 가운데 supervisor 가 의심으로 고른 수 / 안 고른 수 · 그 밖에 새로 고른 수 | {tot['v2_touched']} / {tot['v2'] - tot['v2_touched']} · {tot['new_touched']} | 참고(고름 = reread · set · ask 가운데 하나) |",
         f"| 토큰 · 라운드(check) · 다시 읽기 · set · 시간 | 토큰은 세션이 적음 · {tot['checks']} · {tot['rereads']} · {tot['sets']} · " + "; ".join(f"{x['game']} {x['first_at']} ~ {x['last_at']}" for x in per_game) + " | — |",
         "", "## 사용자 확인 차례", "", "| 차례 | 상태 | 손댐 | 바꿈 | 마감 답 vs 확인값 | 처음 답 vs 확인값 |", "|---|---|---|---|---|---|"]
    L += [f"| {x['turn']} | {x['state']} | {', '.join(x['how']) or '—'} | {'예' if x['changed'] else ''} | {x['final_vs_user']} | {x['first_vs_user']} |" for x in conf_rows] or ["| (없음) | | | | | |"]
    L += ["", "## 판마다", "", "| 판 | 마감 | 차례 | ask | 다시 읽기 | set | check | 바꾼 차례 | 고른 차례 | v2 가 올린 차례 | 명령 수 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {x['game']} | {'예' if x['done'] else '아니오'} | {x['turns']} | {x['asks']} | {x['rereads']} | {x['sets']} | {x['checks']} | {', '.join(x['changed']) or '—'} | "
          f"{', '.join(x['touched']) or '—'} | {', '.join(x['v2']) or '—'} | {sum(x['commands'].values())} |" for x in per_game]
    L += ["", "사용자 확인값의 '결과 같음' 은 칸 값이 달라도 그 판을 마감 답 / 확인값으로 각각 조립해 손패 주인의 매 순 손패(14장 묶음)가 같으면 맞음으로 센다."]
    out = {"at": now(), "run": posix(r.d), "games": per_game, "undone": undone, "confirmed": conf_rows, "changed": changed_rows, "other_questions": len(other_q), "samples": len(samples), "totals": dict(tot)}
    wj(sd / "score.json", out)
    wt(sd / "score.md", "\n".join(L) + "\n")
    print("\n".join(L))
    return sd, {"games": len(per_game), "asks": tot["asks"], "silent_wrong": len(silent)}


def hands_same(r: pa.Run, g: str, pk: Pack, final: dict, tid: str, ua: dict, work: Path) -> str:
    """칸 값이 다를 때: 마감 답 / 확인값으로 그 판을 각각 조립해 손패 주인의 매 순 14장 묶음이 같으면 '결과 같음'."""
    if work.exists():
        shutil.rmtree(work)
    for name, sub in (("final", {}), ("user", {tid: {**final[tid], **{k: ua.get(k) for k in ("kind", "k", "j", "end_order", "gone") if k in ua}}})):
        for t in pk.turns:
            wj(work / name / t / "answer.json", sub.get(t, final[t]))
    res = run_inner(r, g, [{"name": "final", "root": posix(work / "final")}, {"name": "user", "root": posix(work / "user")}], work)
    if "_error" in res:
        return "가릴 수 없음(조립 실패: " + res["_error"][:120] + ")"
    a, b = res.get("final") or {}, res.get("user") or {}
    if not (a.get("ok") and b.get("ok") and a.get("hands") and b.get("hands")):
        return "가릴 수 없음(조립 실패: " + str(a.get("error") or b.get("error"))[:120] + ")"
    ha, hb = a["hero_hands"], b["hero_hands"]
    if len(ha) == len(hb) and all(Counter(x) == Counter(y) for x, y in zip(ha, hb)):
        return "결과 같음(손패 같음)"
    return "틀림"


# ------------------------------------------------------------------ replay(설계서 8-17 4-① — 다른 실행의 마감된 꾸러미를 같은 마감으로 다시 적용, LLM 0)
def cmd_replay(a):
    pk = Pack(a.pack)
    pk.need_open()
    q = Pack(a.src)
    if pk.d == q.d:
        raise Reject("같은 꾸러미")
    if not (q.draft and q.draft.get("done") and (q.d / "decision.json").exists()):
        raise Reject(f"가져올 꾸러미가 마감 전: {posix(q.d)}")
    if q.meta["game"] != pk.meta["game"] or q.turns != pk.turns:
        raise Reject(f"판 · 차례 목록이 다름: {q.meta['game']} {q.turns} ≠ {pk.meta['game']} {pk.turns}")
    diff = [t for t in pk.turns if slot(q.first(t)) != slot(pk.first(t))]
    if diff:
        raise Reject(f"처음 답(칸 값)이 다른 차례 {diff} — 같은 마감을 다시 적용할 수 없음")
    used = any(pk.draft.get(k) for k in ("rereads", "takes", "sets", "asks", "checks"))
    if used and pk.draft.get("replayed_from") != posix(q.d):
        raise Reject("이미 손댄 꾸러미 — 재생은 손대지 않은 꾸러미에만")
    if (pk.d / "reread").exists() and pk.draft.get("replayed_from") == posix(q.d):
        shutil.rmtree(pk.d / "reread")   # 같은 출처 재생을 다시 부름 — 옮긴 다시 읽기 폴더를 새로
    src_run, dst_run = posix(q.run_dir), posix(pk.run_dir)
    rereads = []
    for x in q.draft["rereads"]:
        sd, dd = Path(x["dir"]), pk.reread_dir(x["turn"], x["n"])
        (dd / "work").mkdir(parents=True, exist_ok=True)
        for f in ("TASK.md", "frames.txt", "events.txt", "answer.json"):
            if not (sd / f).exists():
                continue
            if f == "answer.json":
                shutil.copyfile(sd / f, dd / f)   # 작업자 답은 바이트 그대로
            else:
                wt(dd / f, (sd / f).read_text(encoding="utf-8").replace(posix(sd), posix(dd)).replace(src_run, dst_run))
        y = dict(x)
        y.update(dir=posix(dd), replayed_from=posix(sd), message=str(x.get("message") or "").replace(posix(sd), posix(dd)))
        rereads.append(y)
    pk.draft = {"turns": json.loads(json.dumps(q.draft["turns"])), "rereads": rereads, "takes": list(q.draft["takes"]), "sets": list(q.draft["sets"]),
                "asks": list(q.draft["asks"]), "checks": [{**c, "replayed": True} for c in q.draft["checks"]], "done": False,
                "replayed_from": posix(q.d), "replayed_at": now()}
    pk.save()
    c = closure(pk)
    print(f"재생: {posix(q.d)} → {posix(pk.d)} · 다시 읽기 {len(rereads)} · set {len(pk.draft['sets'])} · ask {len(pk.draft['asks'])} · check {len(pk.draft['checks'])}"
          f" · 마감 검사 {'통과할 수 있음' if c['ok'] else ' / '.join(c['why'])}")
    print(f"다음: paifu_sup.py done --pack {posix(pk.d)}")
    return pk.d, {"from": posix(q.d), "rereads": len(rereads), "sets": len(pk.draft["sets"]), "asks": len(pk.draft["asks"]), "closure_ok": c["ok"]}


# ------------------------------------------------------------------ main
CMDS = {"pack": cmd_pack, "reread": cmd_reread, "take": cmd_take, "set": cmd_set, "check": cmd_check, "ask": cmd_ask,
        "done": cmd_done, "status": cmd_status, "score": cmd_score, "replay": cmd_replay}


def log_dir_of(a):
    if getattr(a, "pack", None):
        return Path(a.pack).resolve()
    if a.cmd == "pack":
        return pa.Run(a.run).d / "sup" / a.game
    if a.cmd == "score":
        return pa.Run(a.run).d / "sup"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="판 supervisor 명령(설계서 8-10)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("pack")
    p.add_argument("--run", required=True)
    p.add_argument("--game", required=True)
    p = sp.add_parser("reread")
    p.add_argument("--pack", required=True)
    p.add_argument("--turn", required=True)
    p.add_argument("--frames", help="더 볼 프레임 범위(예 053-058 또는 053-058,060-068, 한 장이면 055, 3개까지) — 안 주면 주의 없이")
    p = sp.add_parser("take")
    p.add_argument("--pack", required=True)
    p.add_argument("--turn", required=True)
    p.add_argument("--from", dest="src", required=True, choices=FROM_CHOICES)
    p = sp.add_parser("set")
    p.add_argument("--pack", required=True)
    p.add_argument("--turn", required=True)
    p.add_argument("--answer", required=True)
    p.add_argument("--evidence")
    p.add_argument("--evidence-file", help="UTF-8 파일(--evidence 대신)")
    p.add_argument("--why")
    p.add_argument("--why-file", help="UTF-8 파일(--why 대신)")
    for name in ("check", "done", "status"):
        sp.add_parser(name).add_argument("--pack", required=True)
    p = sp.add_parser("ask")
    p.add_argument("--pack", required=True)
    p.add_argument("--turn", required=True)
    p.add_argument("--candidates")
    p.add_argument("--candidates-file", help="UTF-8 파일(--candidates 대신)")
    p.add_argument("--why")
    p.add_argument("--why-file", help="UTF-8 파일(--why 대신)")
    p = sp.add_parser("score")
    p.add_argument("--run", required=True)
    p.add_argument("--truth-dir")
    p = sp.add_parser("replay")
    p.add_argument("--pack", required=True)
    p.add_argument("--from", dest="src", required=True, help="다른 실행의 마감된 꾸러미 폴더(<실행>/sup/<판>)")
    a = ap.parse_args(argv)
    args = {k: v for k, v in vars(a).items() if k != "cmd"}
    t0 = time.time()
    ld = None
    try:
        ld = log_dir_of(a)
        d, summary = CMDS[a.cmd](a)
        ld = Path(d)
        append_line(ld / "log.jsonl", {"at": now(), "cmd": a.cmd, "args": args, "ok": True, "result": summary, "s": round(time.time() - t0, 2)})
        return 0
    except Reject as e:
        print(f"거절: {e}")
        if a.cmd == "pack" and ld is not None and not ld.exists():
            ld = ld.parent    # 꾸러미를 못 만든 pack — 실행 폴더 sup/ 가 이미 있을 때만 그 log.jsonl 에(새 폴더는 안 만듦)
        if ld is not None and ld.exists():
            append_line(ld / "log.jsonl", {"at": now(), "cmd": a.cmd, "args": args, "ok": False, "rejected": str(e)[:1500], "s": round(time.time() - t0, 2)})
        return 2
    except SystemExit as e:   # 거절이 아닌 오류(설정 · 하위 프로세스) — 기록하고 종료 코드 1
        print(f"오류: {e}")
        if ld is not None and ld.exists():
            append_line(ld / "log.jsonl", {"at": now(), "cmd": a.cmd, "args": args, "ok": False, "error": str(e)[:1500], "s": round(time.time() - t0, 2)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
