"""픽셀 덩어리를 글로 바꿔 LLM 에 쯔모기리·나간 칸·들어간 칸을 묻는 시험(2026-11-16, 사용자 그림 제안 "패 위치 정보를 llm 에게 줘서 추론").

  python -X utf8 llmtext.py make <판 id…> --out <폴더>     # 차례마다 글(정답 없음) turns.txt + 색인 index.json(정답은 따로 truth.json)
  python -X utf8 llmtext.py score <폴더> <답 json…>        # 답 파일: [{"id": ..., "mode": "쯔모기리|손에서|모름", "k": int|null, "j": int|null}]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import beforeafter as ba  # noqa: E402
import htcommon as hc  # noqa: E402
import pixtrack as pt  # noqa: E402

HEAD = """각 차례는 위에서 내려다본 카메라로 한 사람의 세운 손패 줄(대국자 시점, 왼쪽 = 그 사람 왼손 쪽)을 초당 10장 본 기록이다.
한 줄 = 한 프레임. 표기: [n@x] = 가로 위치 x(px)에서 시작하는 패 덩어리, 길이 n장(패 한 장 폭 약 {pitch:.0f}px, 소수는 측정 오차·가림).
괄호가 ( 또는 ) 이면 그 끝에 손이 닿아 있어 패가 가려졌을 수 있다. "손 a~b" = 손이 덮은 가로 범위. 줄이 바뀐 프레임만 적었다.
이 차례에 그 사람은 패 한 장을 뽑아(오른쪽 등에서 가져옴) 한 장을 버린다. 답할 것:
 - mode: "쯔모기리"(뽑은 패를 그대로 버림, 줄의 패는 안 빠짐) / "손에서"(줄의 패 하나를 버리고 뽑은 패를 줄에 넣음) / "모름"
 - k: 손에서면 버린 패가 손 들어오기 전 줄의 왼쪽부터 몇 번째였나(1~N), 모르면 null
 - j: 손에서면 뽑은 패가 손 떠난 뒤 줄의 왼쪽부터 몇 번째에 있나(1~N), 모르면 null
줄의 패 수 N 은 차례마다 적었다. 확실하지 않으면 추측하지 말고 모름/null.
"""


def turn_text(R: pt.Row, tr: dict, n_hand: int) -> str:
    lines, last = [], None
    for ms in hc.frame_range(tr["ms_before"], tr["ms_after"]):
        f = R.frame(ms)
        rs = [r for r in f["runs"] if r["n"] >= 0.3]
        sig = tuple((round(r["n"] * 2) / 2, r["x0"] // 15, r["hl"], r["hr"]) for r in rs) + ((f["skin"][0] // 60, f["skin"][1] // 60) if f["skin"] else ())
        if sig == last:
            continue
        last = sig
        body = " ".join(("(" if r["hl"] else "[") + f"{r['n']:.1f}@{r['x0']}" + (")" if r["hr"] else "]") for r in rs) or "(줄 안 보임)"
        lines.append(f"{hc.hms(ms)[3:]}  {body}" + (f"   손 {f['skin'][0]}~{f['skin'][1]}" if f["skin"] else ""))
    return "\n".join(lines)


def cmd_make(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    texts, truth, idx = [], {}, []
    pitch = None
    for gid in a.games:
        R = pt.Row(gid)
        pitch = pitch or R.pitch
        rp = hc.jload(glob.glob(str(hc.OUT / gid / "replay2_B" / "*.json"))[0])
        tmap = {t["t"]: t for t in rp["turns"]}
        n_hand = 13
        for tr in ba.turns_from_replay(rp, R.sg):
            if "call" in " ".join(tr["events"]):
                n_hand = 10
            T = pt.truth_of(gid, tmap[tr["t"]])
            if not T["mode"]:
                continue  # 정답 없는 차례(판정 B 가 둘 다) 는 묻지 않음 — 픽셀 채점과 같은 분모
            tid = f"T{len(idx) + 1:02d}"
            body = turn_text(R, tr, n_hand)
            texts.append(f"### {tid}  (N = {n_hand})\n{body}\n")
            truth[tid] = T
            idx.append({"id": tid, "game": gid, "t": tr["t"], "segs": tr["segs"], "lines": body.count("\n") + 1, "chars": len(body)})
    (out / "turns.txt").write_text(HEAD.format(pitch=pitch) + "\n" + "\n".join(texts), encoding="utf-8")
    hc.jsave(out / "index.json", idx)
    hc.jsave(out / "truth.json", truth)
    print(len(idx), "차례 · 글", sum(i["chars"] for i in idx), "자 · 줄", sum(i["lines"] for i in idx))


def cmd_score(a):
    d = Path(a.dir)
    truth = hc.jload(d / "truth.json")
    for f in a.answers:
        ans = {x["id"]: x for x in hc.jload(f)}
        c = dict(mode_n=0, mode_ok=0, mode_bad=0, mode_unk=0, k_n=0, k_ok=0, k_bad=0, j_n=0, j_ok=0, j_bad=0, jc_n=0, jc_in=0)
        bad = []
        for tid, T in truth.items():
            G = ans.get(tid, {"mode": "모름", "k": None, "j": None})
            c["mode_n"] += 1
            if G["mode"] == "모름":
                c["mode_unk"] += 1
            elif G["mode"] == T["mode"]:
                c["mode_ok"] += 1
            else:
                c["mode_bad"] += 1
                bad.append((tid, "mode", T["mode"], G["mode"]))
            if T["mode"] == "손에서" and T["k"]:
                c["k_n"] += 1
                if G.get("k") == T["k"]:
                    c["k_ok"] += 1
                elif G.get("k") is not None:
                    c["k_bad"] += 1
                    bad.append((tid, "k", T["k"], G["k"]))
            if T["mode"] == "손에서" and T["j"]:
                c["j_n"] += 1
                if G.get("j") == T["j"]:
                    c["j_ok"] += 1
                elif G.get("j") is not None:
                    c["j_bad"] += 1
                    bad.append((tid, "j", T["j"], G["j"]))
            if T.get("j_cands"):
                c["jc_n"] += 1
                c["jc_in"] += G.get("j") in T["j_cands"]
        print(Path(f).name, json.dumps(c, ensure_ascii=False), "틀림:", bad)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("make")
    m.add_argument("games", nargs="+")
    m.add_argument("--out", required=True)
    s = sp.add_parser("score")
    s.add_argument("dir")
    s.add_argument("answers", nargs="+")
    a = ap.parse_args()
    {"make": cmd_make, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
