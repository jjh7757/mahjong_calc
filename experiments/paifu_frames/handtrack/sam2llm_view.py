"""Gemini 에게 실제로 보낸 요청(글)을 차례 · 팔별로 보는 페이지(2026-11-18, 사용자 "제미나이에게 뭐 줬는지 그림으로 보여줘봐").

요청은 글뿐이다(그림 없음). 페이지 왼쪽 = 요청 글 그대로(sam2llm.gem_prompt 가 만든 것), 오른쪽 = 같은 차례의 SAM 2 추적 그림(v1 · 참고용 — Gemini 에게는 안 줌),
아래 = 그 요청에 대한 Gemini 의 답 2회와 정답.

  python -X utf8 sam2llm_view.py        # → _work/sam2llm_1118/gemini_input_view.html
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2llm as m  # noqa: E402
import sam2track as s1  # noqa: E402

LABEL = {"L": "줄글만", "S": "SAM 2 기록(옛 글)", "LS": "줄글 + SAM 2 기록(옛 글)", "S3": "SAM 2 기록(경로 · 뜀 · 둘째 추적)", "LS3": "줄글 + SAM 2 기록(새 글)"}
NAME = {"r12_d02": "r12 2순", "r13_d02": "r13 2순", "r16_d01": "r16 1순", "r16_d02": "r16 2순", "r16_d13": "r16 13순", "r16_d16": "r16 16순", "r17_d03": "r17 3순", "r17_d08": "r17 8순"}


def strip_b64(tid: str, a, max_tiles: int = 30, scale: float = 0.62) -> str:
    """v1 추적의 마스크 겹친 프레임 띠 → JPEG base64."""
    d = s1.run_dir(tid, a)
    tr = hc.jload(d / "track.json")
    H, W = tr["shape"]
    M = np.load(d / "masks.npz")
    n, F = tr["plan"]["n"], len(tr["frames"])
    rng = np.random.default_rng(3)
    col = rng.uniform(60, 255, (n + 1, 3)).astype(np.float32)
    step = max(1, -(-F // max_tiles))
    picks = sorted(set(range(0, F, step)) | {F - 1})
    tiles = []
    for fi in picks:
        ov = np.asarray(Image.open(d / "frames" / f"{fi:05d}.jpg")).astype(np.float32)
        cents = []
        for o in range(1, n + 1):
            key = f"{fi}_{o}"
            if key not in M:
                continue
            mk = np.unpackbits(M[key])[: H * W].reshape(H, W).astype(bool)
            if not mk.any():
                continue
            ov[mk] = 0.45 * ov[mk] + 0.55 * col[o]
            ys, xs = np.nonzero(mk)
            cents.append((o, xs.mean(), ys.mean()))
        img = Image.fromarray(ov.astype(np.uint8))
        dr = ImageDraw.Draw(img)
        for o, x, y in cents:
            dr.text((x - 4, y - 6), str(o), fill=(255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0))
        dr.text((4, 4), hc.mss(tr["frames"][fi]), fill=(255, 255, 0), stroke_width=1, stroke_fill=(0, 0, 0))
        tiles.append(img.resize((int(W * scale), int(H * scale))))
    sheet = Image.new("RGB", (tiles[0].width, sum(t.height for t in tiles)))
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y))
        y += t.height
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=72)
    return base64.b64encode(buf.getvalue()).decode()


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gemini 가 받은 입력</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c19;--mut:#6b6860;--line:#dedbd2;--card:#fff;--acc:#1f5fbf;--warn:#b3261e;--ok:#1b7f3b;--hl1:#fff1c2;--hl2:#ffd9d4;--hl3:#dcecff}
@media (prefers-color-scheme:dark){:root{--bg:#171613;--fg:#ece9e1;--mut:#a09c91;--line:#3a3832;--card:#211f1b;--acc:#8ab4ff;--warn:#ff8a80;--ok:#7bd88f;--hl1:#4a3f12;--hl2:#5a2420;--hl3:#1d3557}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 "Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif}
header{padding:16px 16px 8px;border-bottom:1px solid var(--line)}h1{margin:0 0 4px;font-size:19px}
.note{color:var(--warn);font-weight:600}.mut{color:var(--mut)}
.bar{display:flex;flex-wrap:wrap;gap:6px;padding:10px 16px;position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);z-index:2}
button{font:inherit;padding:5px 10px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
button.on{border-color:var(--acc);color:var(--acc);font-weight:700}
.grp{display:flex;flex-wrap:wrap;gap:6px;align-items:center}.grp b{margin-right:2px;color:var(--mut);font-weight:600}
main{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:14px;padding:14px 16px}
@media (max-width:900px){main{grid-template-columns:1fr}}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;min-width:0}
h2{margin:0 0 8px;font-size:15px}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font:12px/1.5 Consolas,"D2Coding",monospace}
details{margin-bottom:10px}summary{cursor:pointer;color:var(--acc)}
.ans{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:8px}
.card{border:1px solid var(--line);border-radius:6px;padding:8px}.ok{color:var(--ok);font-weight:700}.bad{color:var(--warn);font-weight:700}
.imgbox{max-height:80vh;overflow:auto;border:1px solid var(--line);border-radius:6px}.imgbox img{display:block;width:100%}
mark.a{background:var(--hl1);color:inherit}mark.b{background:var(--hl2);color:inherit}mark.c{background:var(--hl3);color:inherit}
.legend span{margin-right:10px;white-space:nowrap}
</style></head><body>
<header><h1>Gemini 가 받은 입력</h1>
<div class="note">그림은 한 장도 보내지 않았습니다. 왼쪽의 글이 요청 한 번의 전부입니다.</div>
<div class="mut">차례 하나에 요청 한 번 · 모델 gemini-3.8-flash · 팔마다 2번. 오른쪽 그림은 같은 차례의 SAM 2 추적(처음 한 번만 붙인 것)으로, 사람이 보려고 붙인 참고용입니다.</div></header>
<div class="bar"><div class="grp"><b>차례</b><span id="turns"></span></div><div class="grp"><b>준 글</b><span id="arms"></span></div></div>
<main>
<section><h2 id="ttl"></h2><div class="mut" id="meta"></div>
<div class="legend mut" style="margin:6px 0"><span><mark class="a">경로</mark> 물체가 지나간 자리</span><span><mark class="b">뜀 · 다시 나타남</mark></span><span><mark class="c">마스크 없는 상자 · 코드 배정 · 코드의 답</mark></span></div>
<details><summary>안내문(모든 차례에 똑같이 앞에 붙음) 펼치기</summary><pre id="guide"></pre></details>
<h2>이 차례의 글</h2><pre id="body"></pre>
<h2 style="margin-top:14px">이 요청에 Gemini 가 낸 답</h2><div class="ans" id="ans"></div></section>
<section><h2>참고: 같은 차례의 SAM 2 추적 그림 <span class="note">(Gemini 에게는 안 줌)</span></h2>
<div class="mut" style="margin-bottom:6px">숫자 = 물체 번호(차례 시작 줄의 왼쪽부터). 위에서 아래로 시간 순.</div><div class="imgbox"><img id="img" alt="SAM 2 추적 그림"></div></section>
</main>
<script>
const D = __DATA__;
let tid = D.ids[1], arm = "LS3";
const esc = s => s.replace(/&/g,"&amp;").replace(/</g,"&lt;");
function hl(t){
  return esc(t).split("\\n").map(l => {
    l = l.replace(/(⇐뜀\\([^)]*\\)|⇐다시 나타남\\([^)]*\\)|마지막 뜀:[^|]*)/g, '<mark class="b">$1</mark>');
    if (/^\\s*경로:/.test(l)) l = l.replace(/경로:/, '<mark class="a">경로:</mark>');
    l = l.replace(/(마스크 없는 상자:[^|]*|코드 배정:|\\[코드의 답\\][^\\n]*)/g, '<mark class="c">$1</mark>');
    return l;
  }).join("\\n");
}
function draw(){
  document.querySelectorAll("#turns button").forEach(b => b.classList.toggle("on", b.dataset.k === tid));
  document.querySelectorAll("#arms button").forEach(b => b.classList.toggle("on", b.dataset.k === arm));
  const p = D.prompts[arm][tid], tr = D.truth[tid];
  document.getElementById("ttl").textContent = D.names[tid] + " — " + D.labels[arm];
  document.getElementById("meta").textContent = "요청 글 " + (p.guide.length + p.body.length).toLocaleString() + "자(안내문 " + p.guide.length.toLocaleString() + " + 이 차례 " + p.body.length.toLocaleString() + ") · 정답: 나간 칸 " + tr.k + " · 들어간 칸 " + tr.j;
  document.getElementById("guide").textContent = p.guide;
  document.getElementById("body").innerHTML = hl(p.body);
  document.getElementById("ans").innerHTML = (D.answers[arm][tid] || []).map((r, i) => {
    const a = r.kind === "hand" ? "나간 칸 " + r.k + " · 들어간 칸 " + r.j : "쯔모기리";
    return '<div class="card"><b>' + (i + 1) + '회</b> — <span class="' + (r.ok ? "ok" : "bad") + '">' + a + (r.unsure ? " (확신 없음)" : "") + (r.ok ? " ✓" : " ✗") + '</span><div class="mut">생각 토큰 ' + (r.think || 0).toLocaleString() + '</div><div><b>근거</b> ' + esc(r.why || "") + '</div><details><summary>따져 본 과정</summary><div>' + esc(r.steps || "") + '</div></details></div>';
  }).join("");
  document.getElementById("img").src = "data:image/jpeg;base64," + D.images[tid];
}
function mk(id, keys, label, set){
  const el = document.getElementById(id);
  keys.forEach(k => { const b = document.createElement("button"); b.textContent = label(k); b.dataset.k = k; b.onclick = () => { set(k); draw(); }; el.appendChild(b); });
}
mk("turns", D.ids, k => D.names[k], k => tid = k);
mk("arms", D.arms, k => k + " · " + D.labels[k], k => arm = k);
draw();
</script></body></html>
"""


def main():
    a = argparse.Namespace(model="t", device="xpu")
    bl = m.blocks(a)
    truth = s1.truth_all()
    prompts, answers = {}, {}
    for arm in m.ALL_ARMS:
        prompts[arm], answers[arm] = {}, {}
        for t in m.IDS:
            full = m.gem_prompt(bl[arm][0], bl[arm][1][t])
            guide, body = full.split("# 차례\n\n", 1)
            prompts[arm][t] = {"guide": guide + "# 차례\n", "body": body}
            answers[arm][t] = []
        for rep in (1, 2):
            f = m.OUT / f"read_gem_{arm}_r{rep}.json"
            if not f.exists():
                continue
            for r in hc.jload(f)["rows"]:
                answers[arm][r["id"]].append({"kind": r.get("kind"), "k": r.get("k"), "j": r.get("j"), "unsure": bool(r.get("unsure")), "why": r.get("why"),
                                              "steps": r.get("steps"), "think": r.get("think"), "ok": m.right(m.norm(r), truth[r["id"]])})
    data = {"ids": list(m.IDS), "arms": list(m.ALL_ARMS), "labels": LABEL, "names": NAME, "prompts": prompts, "answers": answers,
            "truth": {t: {"k": truth[t]["k_id"], "j": truth[t]["j_closed"]} for t in m.IDS},
            "images": {t: strip_b64(t, a) for t in m.IDS}}
    out = m.OUT / "gemini_input_view.html"
    out.write_text(PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8", newline="\n")
    print(out, f"{out.stat().st_size / 1e6:.1f}MB")
    _ = html  # (html 모듈은 안 씀 — 글은 페이지 쪽에서 escape)


if __name__ == "__main__":
    main()
