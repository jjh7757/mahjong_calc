"""헤드 녹화 반장 — 확실하지 않은 것(처음은 11-14 3반장 네 가지: 뒷도라 둘 · 해저 둘)을 사용자에게 영상으로 묻는 페이지(2026-11-23). 127.0.0.1 전용.

  python -X utf8 han3_checkserver.py prep [--force]                 # 영상 넷 + 정지 그림 둘 만들기(서버를 켤 때 없으면 저절로)
  python -X utf8 han3_checkserver.py [포트 8314] [--ans <답 파일>]   # 페이지 띄우기(--ans: 시험용 — 진짜 답 파일 대신 다른 파일에 씀)
  python -X utf8 han3_checkserver.py show [--ans <답 파일>]          # 저장된 답 출력

- 자료 = results/han3_1123/review2/ : <항목>.mp4(초당 10장 전부, 출력 5fps = 2배 느리게, crf 20) · <항목>_still.jpg(해저 둘)
  · clips.json(프레임 시각 목록 · 크기). 영상 한 화면 = [탁자 전체(줄임, 확대 칸 테두리)] + [관심 칸 2배 확대] 나란히.
- 답 = review2/answers_user.json(+ 저장마다 answers_log.jsonl 한 줄). --ans 로 다른 파일을 주면 기록은 <답 이름>_log.jsonl.
- 복구 때 읽어 둔 값(뒷도라 · 해저 판단)은 페이지 · 영상 어디에도 넣지 않는다(사용자가 따로 판단하게).
- 11-24: 확인 항목(item_check.items) · 자료 폴더(item_check.dir) · 페이지 제목 글은 반장 설정(hanchan_cfg.py)에서. 모든 명령에
  --hanchan <json>(안 주면 ../hanchan/h3_1123.json = 3반장)을 붙일 수 있다. 위 폴더 이름은 3반장 설정 값.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import hanchan_cfg as hcfg  # noqa: E402
import htcommon as hc  # noqa: E402

FONT = "C:/Windows/Fonts/malgun.ttf"
SRC_FPS_OUT = 5          # 출력 fps — 원본 초당 10장을 2배 느리게
BAR = 44                 # 위 글씨 띠 높이
GAP = 6
COLORS = [(0, 230, 255), (255, 80, 220)]

# 항목(ITEMS)은 반장 설정 item_check.items — {"id", "no", "kind": "ura" | "haitei", "game", "title", "desc": [문단…, 마지막 = 물음], "t0", "t1",
# "zones": [[이름, [x0, y0, x1, y1](원본 1496² 좌표), 확대 배수], …], "still": {"t", "box"}(해저만)}. 영역은 프레임을 직접 열어 보고 정함
# (집는 패산 자리 · 놓는 펠트 자리). 3반장 것 = p01_ura · n08_ura · n02_haitei · n03_haitei(11-23).
# 아래는 반장 설정에서(configure). 3반장 설정 값: H3 = results/han3_1123 · OUT = review2 · ANS_DEFAULT = review2/answers_user.json · META = review2/clips.json
CFG = None
H3 = OUT = ANS_DEFAULT = META = None
ITEMS: list = []
BY_ID: dict = {}
PAGE_TITLE = PAGE_HEADING = PREP_NOTE = None


def configure(cfg):
    global CFG, H3, OUT, ANS_DEFAULT, META, ITEMS, BY_ID, PAGE_TITLE, PAGE_HEADING, PREP_NOTE, ANS
    CFG = cfg
    H3, OUT = cfg.results_dir, cfg.item_dir
    ANS_DEFAULT = OUT / "answers_user.json"
    META = OUT / "clips.json"
    ITEMS = [dict(it) for it in cfg.items]
    BY_ID = {it["id"]: it for it in ITEMS}
    PAGE_TITLE, PAGE_HEADING, PREP_NOTE = cfg.item_page_title, cfg.item_page_heading, cfg.item_prep_note
    ANS = ANS_DEFAULT
    cfg.apply_recording(hc)

TILE_NAME = {**{f"{i}m": f"{i}만" for i in range(1, 10)}, **{f"{i}p": f"{i}통" for i in range(1, 10)},
             **{f"{i}s": f"{i}삭" for i in range(1, 10)},
             "1z": "동", "2z": "남", "3z": "서", "4z": "북", "5z": "백", "6z": "발", "7z": "중",
             "none": "뒷도라를 안 깠다", "unknown": "영상으로는 모르겠다"}
HAITEI_NAME = {"yes": "예, 마지막 패였다", "no": "아니오, 패산이 더 남아 있었다", "unknown": "모르겠다"}


def value_name(kind: str, v) -> str:
    if v is None:
        return "(값 없음)"
    return (TILE_NAME if kind == "ura" else HAITEI_NAME).get(v, f"? {v}")


# ------------------------------------------------------------------ 자료 만들기
def _font(size):
    from PIL import ImageFont
    return ImageFont.truetype(FONT, size)


def _even(n: int) -> int:
    return n + (n & 1)


def compose(rgb, it, label: str, f_bar, f_zone):
    """한 프레임 → [탁자 전체(줄임)] + [확대 칸들] 나란히 + 위에 노란 글씨."""
    from PIL import Image, ImageDraw
    full = Image.fromarray(rgb)
    zones = []
    for i, (name, box, s) in enumerate(it["zones"]):
        x0, y0, x1, y1 = box
        z = full.crop((x0, y0, x1, y1))
        z = z.resize(((x1 - x0) * s, (y1 - y0) * s), Image.LANCZOS)
        zones.append((name, box, s, z, COLORS[i % len(COLORS)]))
    H = max(z.height for *_, z, _c in zones)
    ov = full.resize((H, H), Image.LANCZOS)
    d = ImageDraw.Draw(ov)
    k = H / full.width
    for name, box, s, z, c in zones:
        d.rectangle([box[0] * k, box[1] * k, box[2] * k, box[3] * k], outline=c, width=3)
    W = _even(H + sum(GAP + z.width for *_, z, _c in zones))
    canvas = Image.new("RGB", (W, _even(BAR + H)), "black")
    canvas.paste(ov, (0, BAR))
    dc = ImageDraw.Draw(canvas)
    x = H + GAP
    for name, box, s, z, c in zones:
        y = BAR + (H - z.height) // 2
        canvas.paste(z, (x, y))
        t = f"{name} ×{s}"
        tw = dc.textlength(t, font=f_zone)
        dc.rectangle([x, y, x + tw + 12, y + 30], fill=(0, 0, 0))
        dc.text((x + 6, y + 2), t, fill=c, font=f_zone)
        dc.rectangle([x, y, x + z.width - 1, y + z.height - 1], outline=c, width=2)
        x += z.width + GAP
    dc.text((10, 6), label, fill="yellow", font=f_bar)
    return canvas


def make_video(it, force: bool) -> dict:
    import imageio_ffmpeg
    import numpy as np
    out = OUT / f"{it['id']}.mp4"
    t0, t1 = hc.to_ms(it["t0"]), hc.to_ms(it["t1"])
    ms_all = hc.frame_range(t0, t1)
    info = {"file": out.name, "frames": [hc.hms(m) for m in ms_all], "ms": ms_all, "fps": SRC_FPS_OUT}
    if out.exists() and not force:
        info["made"] = False
        return info
    f_bar, f_zone = _font(26), _font(20)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = out.with_suffix(".part.mp4")
    proc = None
    for k, ms in enumerate(ms_all):
        canvas = compose(hc.load(ms), it, f"{it['no']}. {it['title']}   {hc.hms(ms)}   #{k:03d}", f_bar, f_zone)
        if proc is None:
            info["size"] = list(canvas.size)
            proc = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                     "-s", f"{canvas.width}x{canvas.height}", "-r", str(SRC_FPS_OUT), "-i", "-",
                                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
                                     "-movflags", "+faststart", str(tmp)], stdin=subprocess.PIPE)
        proc.stdin.write(np.asarray(canvas).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg 실패: {it['id']}")
    tmp.replace(out)
    info["made"] = True
    return info


def make_still(it, force: bool) -> dict | None:
    st = it.get("still")
    if not st:
        return None
    from PIL import Image, ImageDraw
    out = OUT / f"{it['id']}_still.jpg"
    ms = hc.nearest(hc.to_ms(st["t"]))
    info = {"file": out.name, "time": hc.hms(ms), "ms": ms}
    if out.exists() and not force:
        info["made"] = False
        with Image.open(out) as im:
            info["size"] = list(im.size)
        return info
    W = 1000
    full = Image.fromarray(hc.load(ms))
    ov = full.resize((W, W), Image.LANCZOS)
    x0, y0, x1, y1 = st["box"]
    s = W / (x1 - x0)
    z = full.crop((x0, y0, x1, y1)).resize((W, round((y1 - y0) * s)), Image.LANCZOS)
    d = ImageDraw.Draw(ov)
    k = W / full.width
    d.rectangle([x0 * k, y0 * k, x1 * k, y1 * k], outline=COLORS[0], width=3)
    canvas = Image.new("RGB", (W, BAR + W + GAP + 34 + z.height), "black")
    dc = ImageDraw.Draw(canvas)
    dc.text((10, 6), f"{it['no']}. {it['title']}   {hc.hms(ms)}   (뽑기 바로 전)", fill="yellow", font=_font(24))
    canvas.paste(ov, (0, BAR))
    dc.text((10, BAR + W + GAP + 2), f"남은 패산 확대 ×{s:.1f} (위 그림의 하늘색 테두리 칸)", fill=COLORS[0], font=_font(22))
    canvas.paste(z, (0, BAR + W + GAP + 34))
    canvas.save(out, quality=93)
    info["size"] = list(canvas.size)
    info["made"] = True
    return info


def prep(force: bool = False):
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"note": f"han3_checkserver.py prep — {PREP_NOTE}", "items": {}}
    for it in ITEMS:
        v = make_video(it, force)
        s = make_still(it, force)
        if "size" not in v and META.exists():  # 이미 있던 영상이면 크기를 전 기록에서
            old = hc.jload(META).get("items", {}).get(it["id"], {}).get("video", {})
            v["size"] = old.get("size")
        meta["items"][it["id"]] = {"video": {k: v[k] for k in ("file", "frames", "fps", "size") if k in v},
                                   "still": ({k: s[k] for k in ("file", "time", "size")} if s else None)}
        f = OUT / v["file"]
        print(f"{it['id']:11s} {it['t0']} ~ {it['t1']}  {len(v['frames'])}장 → {f.name} "
              f"{f.stat().st_size // 1024} KB {v.get('size')} {'새로 만듦' if v['made'] else '있음'}"
              + (f" · 정지 {s['file']} {s['time']} {s.get('size')}" if s else ""), flush=True)
    OUT.joinpath("clips.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"→ {OUT}")


def ready() -> bool:
    if not META.exists():
        return False
    return all((OUT / f"{it['id']}.mp4").exists() and (not it.get("still") or (OUT / f"{it['id']}_still.jpg").exists())
               for it in ITEMS)


# ------------------------------------------------------------------ 답 파일
LOCK = threading.Lock()
ANS = None   # configure 가 ANS_DEFAULT 로, serve 가 --ans 로


def log_path(ans: Path) -> Path:
    return ans.parent / ("answers_log.jsonl" if ans == ANS_DEFAULT else ans.stem + "_log.jsonl")


def load_answers(ans: Path) -> dict:
    if not ans.exists():
        return {}
    try:
        return json.loads(ans.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


# ------------------------------------------------------------------ 페이지
PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f6f3;--fg:#1d1d1b;--muted:#666;--card:#fff;--line:#d8d8d2;--acc:#1f6feb;--ok:#1a7f37;--sel:#ffd84d}
@media (prefers-color-scheme: dark){:root{--bg:#16171a;--fg:#e8e8e4;--muted:#a0a0a0;--card:#202227;--line:#3a3c42;--acc:#5a9cff;--ok:#3fb950;--sel:#9a7b00}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 "Malgun Gothic","Apple SD Gothic Neo",sans-serif}
.wrap{display:flex;gap:16px;padding:12px 16px;max-width:1900px;margin:0 auto}
nav{flex:0 0 230px}
nav h1{font-size:17px;margin:4px 0 10px}
nav ol{list-style:none;padding:0;margin:0}
nav li{padding:8px 10px;border:1px solid var(--line);border-radius:8px;margin-bottom:6px;cursor:pointer;background:var(--card)}
nav li.cur{border-color:var(--acc);box-shadow:0 0 0 2px var(--acc) inset}
nav li .ck{color:var(--ok);font-weight:bold;margin-left:4px}
nav .hint{color:var(--muted);font-size:13px;margin-top:10px}
main{flex:1;min-width:0}
h2{font-size:19px;margin:4px 0 8px}
.desc p{margin:4px 0}
.desc p.q{font-weight:bold}
video{width:100%;max-height:78vh;background:#000;border-radius:6px;display:block;margin-top:8px}
.ctl{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0}
button{font:inherit;padding:6px 12px;border-radius:7px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button:hover{border-color:var(--acc)}
button.on{background:var(--sel);color:#000;border-color:#b89400}
.now{color:var(--muted);margin-left:8px;font-variant-numeric:tabular-nums}
.still img{max-width:100%;border-radius:6px;display:block;margin-top:6px}
.still a{font-size:13px}
.ans{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin-top:12px}
.tiles{display:grid;grid-template-columns:70px repeat(9,minmax(44px,1fr));gap:5px;align-items:center;max-width:720px}
.tiles .lab{color:var(--muted)}
.tiles button{padding:6px 0}
.extra{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
textarea{width:100%;min-height:64px;font:inherit;margin-top:10px;padding:6px;border-radius:7px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
.save{display:flex;gap:10px;align-items:center;margin-top:8px}
.save button{background:var(--acc);color:#fff;border-color:var(--acc);padding:8px 22px}
.msg{color:var(--muted)}
.nav2{display:flex;gap:8px;margin-top:14px}
@media (max-width:800px){.wrap{flex-direction:column}nav{flex:none}.tiles{grid-template-columns:52px repeat(9,1fr)}}
</style></head><body>
<div class="wrap">
<nav><h1>__HEADING__</h1><ol id="list"></ol>
<div class="hint">영상은 실제보다 2배 느리게 만들어 두었습니다(초당 10장 전부). 위 노란 글씨가 그날 시각과 프레임 번호입니다.
왼쪽 칸은 탁자 전체, 오른쪽 칸은 테두리 친 곳을 2배로 키운 것입니다.</div></nav>
<main>
<h2 id="title"></h2>
<div class="desc" id="desc"></div>
<video id="vid" controls loop muted playsinline preload="auto"></video>
<div class="ctl">
 <span>빠르기</span>
 <button data-rate="0.25">0.25배</button><button data-rate="0.5">0.5배</button><button data-rate="1">1배</button>
 <span style="width:12px"></span>
 <button id="prevf">◀ 한 프레임</button><button id="nextf">한 프레임 ▶</button>
 <span class="now" id="now"></span>
</div>
<div class="still" id="still"></div>
<div class="ans" id="ans"></div>
<div class="nav2"><button id="prev">← 이전 항목</button><button id="next">다음 항목 →</button></div>
</main></div>
<script>
const ITEMS = __ITEMS__;
const META = __META__;
let ANSWERS = {}, cur = 0, pick = null, rate = 1;
const $ = s => document.querySelector(s);
const vid = $("#vid");
const SUITS = [["m","만"],["p","통"],["s","삭"]];
const HONORS = [["1z","동"],["2z","남"],["3z","서"],["4z","북"],["5z","백"],["6z","발"],["7z","중"]];
const HAITEI = [["yes","예, 마지막 패였다"],["no","아니오, 패산이 더 남아 있었다"],["unknown","모르겠다"]];

function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function drawList(){
  $("#list").innerHTML = ITEMS.map((it,i)=>`<li class="${i===cur?'cur':''}" data-i="${i}">${it.no}. ${esc(it.title)}${ANSWERS[it.id]?'<span class="ck">✓</span>':''}</li>`).join("");
  document.querySelectorAll("#list li").forEach(li=>li.onclick=()=>show(+li.dataset.i));
}
function btn(v,label){return `<button data-v="${v}" class="${pick===v?'on':''}">${esc(label)}</button>`}
function drawAns(){
  const it = ITEMS[cur];
  let h = "";
  if(it.kind==="ura"){
    h += `<div><b>뒷도라 표시패를 고르세요</b></div><div class="tiles">`;
    for(const [s,n] of SUITS){ h += `<span class="lab">${n}</span>`; for(let i=1;i<=9;i++) h += btn(i+s, i+n); }
    h += `<span class="lab">자패</span>` + HONORS.map(([v,n])=>btn(v,n)).join("") + `</div>`;
    h += `<div class="extra">${btn("none","뒷도라를 안 깠다")}${btn("unknown","영상으로는 모르겠다")}</div>`;
  } else {
    h += `<div><b>이 뽑기가 패산의 마지막 패였나요?</b></div><div class="extra">` + HAITEI.map(([v,n])=>btn(v,n)).join("") + `</div>`;
  }
  const a = ANSWERS[it.id] || {};
  h += `<textarea id="note" placeholder="메모(본 것 · 기억나는 것 · 확신 정도 등, 비워도 됩니다)">${esc(a.note||"")}</textarea>`;
  h += `<div class="save"><button id="save">저장</button><span class="msg" id="msg">${a.saved_at?('저장됨 '+esc(a.saved_at)):'아직 저장 안 함'}</span></div>`;
  $("#ans").innerHTML = h;
  document.querySelectorAll("#ans button[data-v]").forEach(b=>b.onclick=()=>{pick=b.dataset.v; const n=$("#note").value; drawAns(); $("#note").value=n;});
  $("#save").onclick = save;
}
function show(i){
  cur = i; const it = ITEMS[i]; const m = META[it.id] || {};
  $("#title").textContent = `${it.no}. ${it.title}`;
  $("#desc").innerHTML = it.desc.map((p,k)=>`<p class="${k===it.desc.length-1?'q':''}">${esc(p)}</p>`).join("");
  vid.src = "/media/" + encodeURIComponent(m.video.file);
  vid.playbackRate = rate;
  const st = m.still;
  $("#still").innerHTML = st ? `<div><b>정지 그림</b> — ${esc(st.time)} (뽑기 바로 전) · <a href="/media/${encodeURIComponent(st.file)}" target="_blank">새 창에서 크게 보기</a></div><img src="/media/${encodeURIComponent(st.file)}" alt="뽑기 바로 전 탁자">` : "";
  pick = (ANSWERS[it.id]||{}).value ?? null;
  drawList(); drawAns(); tick();
  $("#prev").disabled = i===0; $("#next").disabled = i===ITEMS.length-1;
}
function fps(){const m=META[ITEMS[cur].id]; return (m&&m.video.fps)||5}
function tick(){
  const m = META[ITEMS[cur].id]; if(!m) return;
  const k = Math.min(m.video.frames.length-1, Math.max(0, Math.floor(vid.currentTime*fps()+1e-3)));
  $("#now").textContent = `#${String(k).padStart(3,"0")}  ${m.video.frames[k]||""}  (${m.video.frames.length}장)`;
}
vid.addEventListener("timeupdate", tick); vid.addEventListener("seeked", tick);
vid.addEventListener("loadedmetadata", ()=>{vid.playbackRate = rate});
function step(d){
  vid.pause();
  const f = fps(), k = Math.floor(vid.currentTime*f + 1e-3) + d;  // tick() 과 같은 프레임 번호 읽기
  const n = META[ITEMS[cur].id].video.frames.length;
  vid.currentTime = (Math.min(n-1, Math.max(0,k)) + 0.5) / f;
}
$("#prevf").onclick = ()=>step(-1); $("#nextf").onclick = ()=>step(1);
document.querySelectorAll("button[data-rate]").forEach(b=>b.onclick=()=>{
  rate = +b.dataset.rate; vid.playbackRate = rate;
  document.querySelectorAll("button[data-rate]").forEach(x=>x.classList.toggle("on", x===b));
});
document.querySelector('button[data-rate="1"]').classList.add("on");
$("#prev").onclick = ()=>cur>0 && show(cur-1);
$("#next").onclick = ()=>cur<ITEMS.length-1 && show(cur+1);
document.addEventListener("keydown", e=>{
  if(e.target.tagName==="TEXTAREA") return;
  if(e.key===",") step(-1); else if(e.key===".") step(1);
});
async function save(){
  const it = ITEMS[cur];
  if(pick===null){ $("#msg").textContent = "먼저 답을 하나 고르세요"; return; }
  const body = {id: it.id, answer: {value: pick, note: $("#note").value}};
  try{
    const r = await fetch("/save", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body)});
    if(!r.ok) throw new Error(r.status);
    const j = await r.json(); ANSWERS[it.id] = j.answer; drawList();
    $("#msg").textContent = "저장됨 " + j.answer.saved_at;
  }catch(e){ $("#msg").textContent = "저장 실패: " + e; }
}
(async()=>{
  try{ ANSWERS = await (await fetch("/api/answers")).json(); }catch(e){ ANSWERS = {}; }
  show(0);
})();
</script></body></html>
"""


def page_bytes() -> bytes:
    meta = hc.jload(META)["items"]
    items = [{k: it[k] for k in ("id", "no", "kind", "title", "desc")} for it in ITEMS]
    m = {i: {"video": {k: v["video"][k] for k in ("file", "frames", "fps")}, "still": v.get("still")} for i, v in meta.items()}
    js = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")  # noqa: E731
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    page = PAGE.replace("__TITLE__", esc(PAGE_TITLE), 1).replace("__HEADING__", esc(PAGE_HEADING), 1)
    return page.replace("__ITEMS__", js(items)).replace("__META__", js(m)).encode("utf-8")


def media_files() -> dict:
    out = {}
    for it in ITEMS:
        out[f"{it['id']}.mp4"] = "video/mp4"
        if it.get("still"):
            out[f"{it['id']}_still.jpg"] = "image/jpeg"
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 조용히(오류만)
        if len(args) > 1 and str(args[1])[:1] in ("4", "5"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send(self, code, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        return self.do_GET()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self.send(200, page_bytes(), "text/html; charset=utf-8")
        if path == "/api/answers":
            with LOCK:
                a = load_answers(ANS)
            return self.send(200, json.dumps(a, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        if path.startswith("/media/"):
            from urllib.parse import unquote
            name = unquote(path[len("/media/"):])
            types = media_files()
            if name not in types or not (OUT / name).exists():
                return self.send(404, b"not found", "text/plain")
            return self.send_file(OUT / name, types[name])
        return self.send(404, b"not found", "text/plain")

    def send_file(self, f: Path, ctype: str):
        size = f.stat().st_size
        rng = self.headers.get("Range")
        start, end, code = 0, size - 1, 200
        if rng:
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
            if not m or (m.group(1) == "" and m.group(2) == ""):
                return self.send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            if m.group(1) == "":
                start = max(0, size - int(m.group(2)))
            else:
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            if start >= size or start > end:
                return self.send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            code = 206
        n = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(n))
        self.send_header("Cache-Control", "no-store")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(f, "rb") as fp:
                fp.seek(start)
                left = n
                while left > 0:
                    chunk = fp.read(min(1 << 16, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass  # 브라우저가 앞뒤로 넘기며 끊는 것은 정상

    def do_POST(self):
        if self.path != "/save":
            return self.send(404, b"not found", "text/plain")
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            iid, ans = str(d["id"]), d["answer"]
            it = BY_ID[iid]
            v = ans.get("value")
            ok = (TILE_NAME if it["kind"] == "ura" else HAITEI_NAME)
            assert isinstance(ans, dict) and v in ok
            note = str(ans.get("note") or "")[:4000]
        except Exception:  # noqa: BLE001
            return self.send(400, b"bad request", "text/plain")
        rec = {"value": v, "value_name": value_name(it["kind"], v), "note": note,
               "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with LOCK:
            a = load_answers(ANS)
            a[iid] = rec
            ANS.parent.mkdir(parents=True, exist_ok=True)
            tmp = ANS.with_suffix(".tmp")
            tmp.write_text(json.dumps(a, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
            tmp.replace(ANS)
            with open(log_path(ANS), "a", encoding="utf-8", newline="\n") as fp:
                fp.write(json.dumps({"id": iid, **rec}, ensure_ascii=False) + "\n")
        self.send(200, json.dumps({"ok": True, "answer": rec}, ensure_ascii=False).encode("utf-8"), "application/json")


def serve(port: int, ans: Path):
    global ANS
    if not ready():
        print("영상이 없어 먼저 만든다(몇 분 걸림)", flush=True)
        prep()
    page_bytes()  # 켜기 전에 페이지가 만들어지는지 확인
    ANS = ans
    print(f"http://127.0.0.1:{port}  (답 → {ans}, 기록 → {log_path(ans)})", flush=True)
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def show(ans: Path):
    a = load_answers(ans)
    print(f"답 파일: {ans}{'' if ans.exists() else ' (없음)'}")
    lp = log_path(ans)
    if lp.exists():
        print(f"기록: {lp} ({sum(1 for _ in lp.open(encoding='utf-8'))}줄)")
    for it in ITEMS:
        r = a.get(it["id"])
        print(f"\n■ {it['no']}. {it['title']}  [{it['id']} · {it['game']}]")
        if not r:
            print("   아직 없음")
            continue
        print(f"   답: {value_name(it['kind'], r.get('value'))}  ({r.get('value')})   저장 {r.get('saved_at')}")
        if r.get("note"):
            print(f"   메모: {r['note']}")
    print(f"\n적은 항목 {sum(1 for it in ITEMS if it['id'] in a)} / {len(ITEMS)}")


configure(hcfg.load(check=False))   # main 이 --hanchan 을 읽어 다시 부름(겹침 검사와 함께)


def main():
    args = sys.argv[1:]
    configure(hcfg.from_argv(args))   # --hanchan(· --prep, 여기선 안 씀)을 꺼냄 + 겹침 검사
    if args and args[0] in ("prep", "show"):
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        ap.add_argument("--force", action="store_true")
        ap.add_argument("--ans", default=str(ANS_DEFAULT))
        a = ap.parse_args(args)
        return prep(a.force) if a.cmd == "prep" else show(Path(a.ans).resolve())
    ans = ANS_DEFAULT
    if "--ans" in args:
        i = args.index("--ans")
        ans = Path(args[i + 1]).resolve()
        del args[i:i + 2]
    serve(int(args[0]) if args else 8314, ans)


if __name__ == "__main__":
    main()
