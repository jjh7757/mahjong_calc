"""패보 JSON 과 docs/metrics.md 를 PostgreSQL 16 적재용 SQL 로 바꾼다.

DB 에 직접 붙지 않는다. experiments/db/out/load.sql 을 쓰고, 운영 서버에서
    psql -v ON_ERROR_STOP=1 -f load.sql
로 붓는다. 내용은 BEGIN; + schema.sql + INSERT + COMMIT; (전체 재적재).

표준 라이브러리만 쓴다.
    python experiments/db/build_sql.py [--out PATH] [--sample]
--sample 은 정확도 · 시간 칸 무작위 표본(오탐 점검용)을 함께 찍는다.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import sys
from collections import Counter
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PAIFU_GLOBS = ["assets/paifu/*.json", "assets/paifu_h3/*.json"]
METRICS_MD = "docs/metrics.md"
BATCH = 500


# ---------------------------------------------------------------- SQL 값 쓰기

def q(s) -> str:
    """문자열 리터럴. standard_conforming_strings = on 기준(백슬래시는 그대로)."""
    if s is None:
        return "NULL"
    s = str(s).replace("\x00", "")
    return "'" + s.replace("'", "''") + "'"


def strip_nul(v):
    if isinstance(v, str):
        return v.replace("\x00", "")
    if isinstance(v, list):
        return [strip_nul(x) for x in v]
    if isinstance(v, dict):
        return {strip_nul(k): strip_nul(x) for k, x in v.items()}
    return v


def qjson(v) -> str:
    if v is None:
        return "NULL"
    return q(json.dumps(strip_nul(v), ensure_ascii=False, separators=(",", ":"))) + "::jsonb"


def qtext_arr(v) -> str:
    if v is None:
        return "NULL"
    return "ARRAY[" + ",".join(q(x) for x in v) + "]::text[]"


def qint_arr(v) -> str:
    if v is None:
        return "NULL"
    return "ARRAY[" + ",".join(qint(x) for x in v) + "]::int[]"


def qint(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        raise TypeError(f"int 자리에 bool: {v!r}")
    return str(int(v))


def qbool(v) -> str:
    if v is None:
        return "NULL"
    return "TRUE" if v else "FALSE"


def qnum(v) -> str:
    return "NULL" if v is None else str(v)


def qdate(v) -> str:
    return "NULL" if v is None else q(v) + "::date"


def inserts(table: str, cols: list[str], rows: list[list[str]]) -> list[str]:
    out = []
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        out.append(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n"
            + ",\n".join("(" + ", ".join(r) + ")" for r in chunk)
            + ";"
        )
    return out


# ---------------------------------------------------------------- 자료 1: 패보

TITLE_HANCHAN = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(\d+)\s*반장")


def load_paifu():
    files = []
    for g in PAIFU_GLOBS:
        files += glob.glob(os.path.join(ROOT, g))
    files.sort()
    hanchans: dict[str, tuple] = {}
    rounds, events, results = [], [], []
    for path in files:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        m = TITLE_HANCHAN.search(d["title"])
        if not m:
            raise ValueError(f"{rel}: 제목에서 날짜·반장을 못 찾음: {d['title']!r}")
        hid = f"{m.group(1)}_h{int(m.group(2))}"
        hanchans[hid] = (hid, m.group(1), int(m.group(2)))
        rname = d["round"]
        km = re.search(r"(\d+)", rname)
        evs = d.get("events") or []
        rounds.append([
            q(d["id"]), q(hid), q(d["title"]), q(rname), q(rname[:1]),
            qint(int(km.group(1)) if km else None),
            qint(d.get("honba", 0)), qint(d["dealer"]), qint(d["hero"]),
            qtext_arr(d.get("names") or []),
            qint(d.get("kyotaku")), qint_arr(d.get("start_scores")),
            qtext_arr(d.get("dora_indicators") or []), qtext_arr(d.get("ura_indicators") or []),
            q(d.get("source")), q(d.get("note") or ""), qint(d.get("version")),
            qint(len(evs)), q(rel),
        ])
        for seq, e in enumerate(evs):
            t = e.get("type")
            is_call = t == "call"
            events.append([
                q(d["id"]), qint(seq), q(t), qint(e.get("seat")),
                q(None if is_call else e.get("tile")),
                qbool(e.get("tsumogiri")) if t == "discard" else "NULL",
                qbool(e.get("riichi")) if t == "discard" else "NULL",
                qint(e.get("at")),
                q(e.get("kind")) if is_call else "NULL",
                qint(e.get("from")) if is_call else "NULL",
                qtext_arr(e.get("tiles")) if is_call else "NULL",
                qtext_arr(e.get("hand")),
                qbool(e.get("guess")) if "guess" in e else "NULL",
                qjson(e),
            ])
        r = d.get("result")
        if r:
            results.append([
                q(d["id"]), q(r.get("type")), qint(r.get("winner")), qint(r.get("loser")),
                q(r.get("win_tile")), qtext_arr(r.get("hand")),
                qjson(r.get("melds")) if "melds" in r else "NULL",
                qjson(r.get("flags")) if "flags" in r else "NULL",
            ])
    hrows = [[q(h[0]), qdate(h[1]), qint(h[2])] for h in sorted(hanchans.values())]
    return hrows, rounds, events, results


# ---------------------------------------------------------------- 자료 2: metrics.md

RE_SECTION = re.compile(r"^##\s+(.*)$")
RE_TABLE = re.compile(r"^###\s+(.*)$")
RE_SECTION_LABEL = re.compile(r"^표\s+(\d+)\.")
RE_TABLE_LABEL = re.compile(r"^(?:표\s+)?(\d+(?:-\d+)+[a-z]?)\.")
RE_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
RE_SEP_CELL = re.compile(r"^:?-{3,}:?$")
VERDICT_MARKS = ["❌", "미채택", "🗑"]


def split_row(line: str) -> list[str]:
    """'| a | b \\| c |' → ['a', 'b \\| c']. 이스케이프한 \\| 는 구분자가 아님(원문 보존)."""
    s = line.strip()
    cells, cur, i = [], [], 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            cur.append("\\|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur))
    if s.startswith("|"):
        cells = cells[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        cells = cells[:-1]
    return [c.strip() for c in cells]


def is_sep(line: str) -> bool:
    if not line.strip().startswith("|"):
        return False
    cells = split_row(line)
    return bool(cells) and all(RE_SEP_CELL.match(c.replace(" ", "")) for c in cells)


def is_pipe_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def plain(v: str) -> str:
    """파싱용: 굵게 · 기울임 · 취소선 · 코드 표기와 \\| 를 벗긴다."""
    v = v.replace("\\|", "|")
    v = re.sub(r"(\*\*|__|~~|`)", "", v)
    return v.strip()


def drop_parens(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\([^()]*\)|（[^（）]*）|\[[^\[\]]*\]", " ", s)
    return s


# 정확도 'a/b': 칸 값이 그 꼴로 시작. 분모 뒤는 끝 · 공백 · 문장부호만(‘1/2반장’ · ‘10/31매장’ 같은 붙은 글자 거름),
# 뒤에 '/ 숫자' 가 또 오면(세 수 묶음) 아님, 숫자 앞에 소수점 · 숫자가 붙어 있으면 아님.
RE_FRAC = re.compile(r"^(\d+)\s*/\s*(\d+)(?=$|[\s,;:·%)\]（(])")
# 나머지 안에 또 다른 'a/b' · 'x.y / z' 같은 슬래시 수 묶음이 있는지(소수 포함)
RE_FRAC_ANY = re.compile(r"\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?")
# 머리가 'A / B' 처럼 슬래시로 나뉘면 값 'a / b' 는 보통 두 양(A 값, B 값)의 나열이다.
# 마지막 몫이 분모를 뜻하는 말로 시작할 때만 분수로 본다('맞음 / 정답 있음', '닻/전체', '맞음/라벨(헛)').
DENOM_WORDS = re.compile(r"^(정답|전체|라벨|장면|총|분모)")
# 시간 묶음: 머리에 시간 말이 있거나, 값에 '초'/'s' 단위가 붙거나,
# 머리가 '중앙 / p90 / 최대' 만 말하고 시간이 아닌 양(오차 · 차 · diff · 분율 · 비율 · % · px · 화소 · (u) · 점수)을 이름 붙이지 않았을 때.
TIME_WORDS = re.compile(r"시간|초|지연|latency|sec|느린|(?<![A-Za-z])ms(?![A-Za-z])", re.I)
STAT_WORDS = re.compile(r"중앙|p90", re.I)
NON_TIME = re.compile(r"오차|(?<![가-힣])차(?![가-힣])|diff|분율|비율|%|px|화소|\(u\)|점수", re.I)
NUM = r"(\d+(?:\.\d+)?|[—–-])"
RE_TRIPLE = re.compile(r"^" + NUM + r"\s*/\s*" + NUM + r"\s*/\s*" + NUM + r"\s*(초|s(?![a-zA-Z]))?(?=$|[\s,;·)(\]（])")
ARROWS = ("→", "->", "⇒", "=>")


def rest_ok(rest: str) -> bool:
    """뽑은 값 뒤의 나머지가 다른 값(전·후 화살표, 두 번째 분수)을 담고 있으면 애매 → False."""
    r = drop_parens(rest)
    if any(a in r for a in ARROWS):
        return False
    if RE_FRAC_ANY.search(r):
        return False
    return True


def parse_frac(header: str | None, value: str):
    p = plain(value)
    m = RE_FRAC.match(p)
    if not m:
        return None
    rest = p[m.end():]
    if re.match(r"\s*/\s*\d", rest):          # 'a / b / c'
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if b <= 0 or a > b:
        return None
    if not rest_ok(rest):
        return None
    hparts = drop_parens(header_plain(header)).split("/")
    if len(hparts) > 1 and not DENOM_WORDS.match(hparts[-1].strip()):
        return None
    return a, b


def header_plain(header: str | None) -> str:
    """머리에서 코드 표기(`/v2/setup` 같은 경로)를 통째로 빼고 굵게 등을 벗긴다."""
    h = re.sub(r"`[^`]*`", " ", header or "")
    return plain(h)


def parse_triple(header: str | None, value: str):
    p = plain(value)
    m = RE_TRIPLE.match(p)
    if not m:
        return None
    h = plain(header or "")
    has_unit = bool(m.group(4))
    if has_unit:
        pass
    elif TIME_WORDS.search(h):
        pass
    elif STAT_WORDS.search(h) and not NON_TIME.search(h):
        pass
    else:
        return None
    if re.match(r"\s*/", p[m.end():]):          # 네 개 이상 묶음
        return None
    if not rest_ok(p[m.end():]):
        return None
    vals = []
    for g in m.group(1, 2, 3):
        vals.append(None if g in ("—", "–", "-") else Decimal(g))
    med, p90, mx = vals
    if med is None or (p90 is None and mx is None):
        return None
    present = [x for x in vals if x is not None]
    if any(present[i] > present[i + 1] for i in range(len(present) - 1)):
        return None                              # 중앙 ≤ p90 ≤ 최대 가 아니면 시간 묶음이 아님
    if not has_unit and re.search(r"(?<![A-Za-z])ms(?![A-Za-z])", h):   # 머리가 ms 단위면 초로 바꿈
        med, p90, mx = (None if x is None else x / 1000 for x in (med, p90, mx))
    return med, p90, mx


def load_metrics():
    path = os.path.join(ROOT, METRICS_MD)
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    sections, tables, parts, rows, cells = [], [], [], [], []
    sec_id = 0
    tab_id = 0
    cur_sec = None        # (id, label, title, line_no)
    cur_tab = None        # dict
    part_no = 0

    def new_table(label, title, line_no, own):
        nonlocal tab_id, cur_tab, part_no
        tab_id += 1
        dm = RE_DATE.search(title)
        measured = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else None
        verdict = " ".join(m for m in VERDICT_MARKS if m in title) or None
        cur_tab = dict(id=tab_id, section_id=cur_sec[0], label=label, title=title, line_no=line_no,
                       own=own, measured_on=measured, out_of_eval="평가 밖" in title,
                       eval_mixed="평가 밖 포함" in title, verdict=verdict)
        tables.append(cur_tab)
        part_no = 0

    i = 0
    n = len(lines)
    pending_own = False   # 절 머리 뒤 '###' 전에 표가 나오면 절 자체를 표로
    while i < n:
        line = lines[i]
        ms = RE_SECTION.match(line)
        mt = RE_TABLE.match(line)
        if ms and not line.startswith("###"):
            sec_id += 1
            title = ms.group(1).strip()
            lm = RE_SECTION_LABEL.match(title)
            cur_sec = (sec_id, lm.group(1) if lm else None, title, i + 1)
            sections.append(cur_sec)
            cur_tab = None
            pending_own = True
            i += 1
            continue
        if mt:
            title = mt.group(1).strip()
            lm = RE_TABLE_LABEL.match(title)
            if cur_sec is None:
                raise ValueError(f"{i+1}: '##' 절 없이 '###'")
            new_table(lm.group(1) if lm else None, title, i + 1, False)
            pending_own = False
            i += 1
            continue
        if is_pipe_line(line) and i + 1 < n and is_sep(lines[i + 1]) and cur_sec is not None:
            if cur_tab is None and pending_own:
                new_table(cur_sec[1], cur_sec[2], cur_sec[3], True)
                pending_own = False
            headers = split_row(line)
            part_no += 1
            head_line = i + 1
            i += 2
            row_no = 0
            prow = []
            while i < n and is_pipe_line(lines[i]) and not is_sep(lines[i]):
                row_no += 1
                vals = split_row(lines[i])
                keys, seen = [], Counter()
                for c in range(len(vals)):
                    h = headers[c] if c < len(headers) else None
                    k = h if h else f"_col{c+1}"
                    seen[k] += 1
                    keys.append(k if seen[k] == 1 else f"{k} ({seen[k]})")
                cdict = dict(zip(keys, vals))
                adopted = None
                for c, v in enumerate(vals):
                    if c < len(headers) and plain(headers[c]) == "채택":
                        adopted = v
                        break
                prow.append(dict(table_id=cur_tab["id"], part=part_no, row_no=row_no, line_no=i + 1,
                                 cells=cdict, adopted=adopted, raw=lines[i]))
                for c, v in enumerate(vals):
                    h = headers[c] if c < len(headers) else None
                    fr = parse_frac(h, v)
                    tr = None if fr else parse_triple(h, v)
                    cells.append(dict(table_id=cur_tab["id"], part=part_no, row_no=row_no, col_no=c + 1,
                                      header=h, value=v, frac=fr, triple=tr))
                i += 1
            parts.append(dict(table_id=cur_tab["id"], part=part_no, line_no=head_line,
                              headers=headers, row_count=row_no))
            rows += prow
            continue
        i += 1
    return sections, tables, parts, rows, cells


# ---------------------------------------------------------------- 쓰기

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out", "load.sql"))
    ap.add_argument("--sample", action="store_true", help="오탐 점검 표본 찍기")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    hrows, rounds, events, results = load_paifu()
    sections, tables, parts, rows, cells = load_metrics()

    with open(os.path.join(HERE, "schema.sql"), encoding="utf-8") as f:
        schema = f.read()

    out: list[str] = [
        "-- 자동 생성: experiments/db/build_sql.py — 손으로 고치지 말 것",
        "\\set ON_ERROR_STOP 1",
        "SET client_encoding = 'UTF8';",
        "SET standard_conforming_strings = on;",
        "BEGIN;",
        schema,
    ]
    out += inserts("hanchan", ["id", "played_on", "hanchan_no"], hrows)
    out += inserts("round", ["id", "hanchan_id", "title", "round_name", "wind", "kyoku_no", "honba",
                             "dealer", "hero", "names", "kyotaku", "start_scores", "dora_indicators",
                             "ura_indicators", "source", "note", "version", "event_count", "file_path"], rounds)
    out += inserts("round_event", ["round_id", "seq", "type", "seat", "tile", "tsumogiri", "riichi", "at_ms",
                                   "call_kind", "call_from", "call_tiles", "hand", "guess", "raw"], events)
    out += inserts("round_result", ["round_id", "type", "winner", "loser", "win_tile", "hand", "melds",
                                    "flags"], results)

    out += inserts("metrics_section", ["id", "label", "title", "line_no"],
                   [[qint(s[0]), q(s[1]), q(s[2]), qint(s[3])] for s in sections])
    out += inserts("metrics_table", ["id", "section_id", "label", "title", "line_no", "is_section_own",
                                     "measured_on", "out_of_eval", "eval_mixed", "title_verdict"],
                   [[qint(t["id"]), qint(t["section_id"]), q(t["label"]), q(t["title"]), qint(t["line_no"]),
                     qbool(t["own"]), qdate(t["measured_on"]), qbool(t["out_of_eval"]),
                     qbool(t["eval_mixed"]), q(t["verdict"])] for t in tables])
    out += inserts("metrics_part", ["table_id", "part", "line_no", "headers", "row_count"],
                   [[qint(p["table_id"]), qint(p["part"]), qint(p["line_no"]), qtext_arr(p["headers"]),
                     qint(p["row_count"])] for p in parts])
    out += inserts("metrics_row", ["table_id", "part", "row_no", "line_no", "cells", "adopted", "raw_line"],
                   [[qint(r["table_id"]), qint(r["part"]), qint(r["row_no"]), qint(r["line_no"]),
                     qjson(r["cells"]), q(r["adopted"]), q(r["raw"])] for r in rows])
    out += inserts("metrics_cell", ["table_id", "part", "row_no", "col_no", "header", "value", "frac_num",
                                    "frac_den", "t_median", "t_p90", "t_max"],
                   [[qint(c["table_id"]), qint(c["part"]), qint(c["row_no"]), qint(c["col_no"]), q(c["header"]),
                     q(c["value"]),
                     qint(c["frac"][0] if c["frac"] else None), qint(c["frac"][1] if c["frac"] else None),
                     qnum(c["triple"][0] if c["triple"] else None), qnum(c["triple"][1] if c["triple"] else None),
                     qnum(c["triple"][2] if c["triple"] else None)] for c in cells])
    out += [
        "SELECT setval(pg_get_serial_sequence('metrics_section', 'id'), (SELECT COALESCE(max(id), 1) FROM metrics_section));",
        "SELECT setval(pg_get_serial_sequence('metrics_table', 'id'), (SELECT COALESCE(max(id), 1) FROM metrics_table));",
        "COMMIT;",
        "",
    ]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as f:
        f.write("\n".join(out).encode("utf-8"))

    counts = [
        ("hanchan", len(hrows)), ("round", len(rounds)), ("round_event", len(events)),
        ("round_result", len(results)), ("metrics_section", len(sections)), ("metrics_table", len(tables)),
        ("metrics_part", len(parts)), ("metrics_row", len(rows)), ("metrics_cell", len(cells)),
    ]
    print(f"썼음: {os.path.relpath(args.out, ROOT)} ({os.path.getsize(args.out):,} 바이트)")
    for name, c in counts:
        print(f"  {name:16s} {c:7,d}")
    nf = sum(1 for c in cells if c["frac"])
    nt = sum(1 for c in cells if c["triple"])
    print(f"  metrics_cell 중 정확도(frac) {nf:,} · 시간(t) {nt:,}")
    dup = Counter(t["label"] for t in tables if t["label"])
    print("  같은 번호 표:", {k: v for k, v in dup.items() if v > 1})

    if args.sample:
        rnd = random.Random(args.seed)
        fs = [c for c in cells if c["frac"]]
        ts = [c for c in cells if c["triple"]]
        print("\n[정확도 표본 30]")
        for c in rnd.sample(fs, min(30, len(fs))):
            print(f"  {c['header']!r} | {c['value']!r} → {c['frac'][0]}/{c['frac'][1]}")
        print("\n[시간 표본 20]")
        for c in rnd.sample(ts, min(20, len(ts))):
            print(f"  {c['header']!r} | {c['value']!r} → {tuple(str(x) if x is not None else None for x in c['triple'])}")


if __name__ == "__main__":
    sys.exit(main())
