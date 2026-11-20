"""SAM 2 출력 번호 고치기 — 저장된 마스크(SAM 2 다시 안 돌림)에 고침 목록을 대고 다시 그린 뒤 코드 검사 · k·j(2026-11-19 밤).

사용자 제안(11-19): "sam2 에게 오류를 알려주는게 아니라 sam2출력을 수정해서 오퍼스가 올바른 sam2출력을 참고하게 만드는거야".
1번(장치 확인, API 0달러): 고침을 손으로 넣어 — 고친 그림 · 검사가 모순을 드러내는지 본다.

  python -X utf8 relabel.py run r16_d01 --tag base                         # 고침 없이(지금 SAM 2 출력 그대로) 검사
  python -X utf8 relabel.py run r16_d01 --tag k2 --edits '[{"op":"relabel","o":13,"start":44,"to":"D"}]'
고침(edits, JSON 목록 — 프레임 번호는 color 그림 번호, end 를 빼면 끝 프레임까지):
  {"op":"relabel","o":13,"start":44,"end":123,"to":"D"}   # 마스크 13 의 번호를 그 구간에서 "D"(또는 다른 번호 "11")로
  {"op":"drop","o":11,"start":55,"end":56}                # 마스크 11 을 그 구간에서 지움
  {"op":"box","label":"D","start":30,"end":43,"box":[x0,y0,x1,y1]}   # 마스크 없는 패에 상자로 번호
검사(프레임마다): 같은 번호가 두 패 · 한 패에 번호 둘(마스크 겹침) · D 가 정해진 뒤 번호 없는 패(검출 상자) · 줄 장수.
결과: _work/relabel_1119/<id>/<tag>/(frames/NNNNN.jpg · report.txt · result.json). 정답은 읽지 않음(채점은 따로).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import htcommon as hc  # noqa: E402
import sam2img as si  # noqa: E402
import sam2track as s1  # noqa: E402
import sam2verify as sv  # noqa: E402
import slotgrid as sg  # noqa: E402

OUT = hc.WORK / "relabel_1119"
V1 = argparse.Namespace(model="t", device="xpu")
SAME_TILE = 0.5     # 두 마스크 겹친 넓이 / 작은 쪽 넓이 ≥ 이 값이면 한 패에 번호 둘
BOX_COVER = 0.25    # 검출 상자 넓이 중 마스크가 덮은 몫 < 이 값이면 번호 없는 패
MIN_AREA = 60       # 이보다 작은 마스크 조각은 없는 것으로(화소)


class Track:
    def __init__(self, tid: str):
        self.tid = tid
        self.d = s1.run_dir(tid, V1)
        self.tr = hc.jload(self.d / "track.json")
        self.H, self.W = self.tr["shape"]
        self.n = self.tr["plan"]["n"]
        self.F = len(self.tr["frames"])
        self.M = np.load(self.d / "masks.npz")
        p = self.tr["plan"]
        det = hc.jload(sg.OUT / f"det_{s1.turn_of(tid)[0]}.json")
        self.boxes = {}
        for fi, ms in enumerate(self.tr["frames"]):
            e = det.get(str(ms))
            self.boxes[fi] = [s1.remap_box(b, p["band"], p["band2"], p["side"]) for b in e["b"]] if e else None

    def mask(self, fi: int, o: int):
        key = f"{fi}_{o}"
        if key not in self.M:
            return None
        mk = np.unpackbits(self.M[key])[: self.H * self.W].reshape(self.H, self.W).astype(bool)
        return mk if mk.sum() >= MIN_AREA else None

    def raw(self, fi: int) -> np.ndarray:
        return np.asarray(Image.open(self.d / "frames" / f"{fi:05d}.jpg").convert("RGB")).astype(np.float32)


def apply_edits(T: Track, edits: list) -> list:
    """프레임마다 [(번호 글자, 마스크)] — 고침을 차례대로 적용."""
    out = []
    for fi in range(T.F):
        items = []
        for o in range(1, T.n + 1):
            mk = T.mask(fi, o)
            if mk is None:
                continue
            lab = str(o)
            keep = True
            for e in edits:
                if e.get("o") != o or not (e["start"] <= fi <= e.get("end", T.F - 1)):
                    continue
                if e["op"] == "relabel":
                    lab = str(e["to"])
                elif e["op"] == "drop":
                    keep = False
            if keep:
                items.append((lab, mk))
        for e in edits:
            if e["op"] == "box" and e["start"] <= fi <= e.get("end", T.F - 1):
                x0, y0, x1, y1 = [int(v) for v in e["box"]]
                mk = np.zeros((T.H, T.W), bool)
                mk[max(0, y0):y1, max(0, x0):x1] = True
                items.append((str(e["label"]), mk))
        out.append(items)
    return out


FLOAT_AREA = 0.40    # 떠 있는 숫자: 처음(프레임 0) 넓이의 40% 밑으로 줄어든 마스크
FLOAT_SKIN = None    # 살색 기준은 끔 — r13 · r17 판은 패 등 색 때문에 손 안 닿은 첫 프레임에서도 줄 전체가 살색으로 걸림(11-19 밤 점검)


def skin(px: np.ndarray) -> np.ndarray:
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (r > 120) & (r > b + 20) & (r > g + 8)


def float_ids(T: Track, fi: int) -> set:
    """그 프레임에서 위치를 못 믿을 마스크(SAM 2 원래 번호) — 손 밑으로 거의 가려졌거나 손 위에 올라탄 것(11-19 밤, r16 13순 · 3순)."""
    if not hasattr(T, "_a0"):
        T._a0 = {o: (T.mask(0, o).sum() if T.mask(0, o) is not None else None) for o in range(1, T.n + 1)}
    raw = None
    out = set()
    for o in range(1, T.n + 1):
        mk = T.mask(fi, o)
        if mk is None or not T._a0.get(o):
            continue
        if mk.sum() < FLOAT_AREA * T._a0[o]:
            out.add(o)
            continue
        if FLOAT_SKIN is None:
            continue
        raw = T.raw(fi) if raw is None else raw
        if skin(raw[mk]).mean() >= FLOAT_SKIN:
            out.add(o)
    return out


def apply_edits_frame(T: Track, fi: int) -> list:
    """고침 없이 한 프레임의 [(번호 글자, 마스크)] — 다시 그리기용(전체 프레임을 돌지 않음)."""
    return [(str(o), mk) for o in range(1, T.n + 1) if (mk := T.mask(fi, o)) is not None]


def color_of(lab: str):
    return (255, 255, 255) if lab == "D" else si.COLORS[(int(lab) - 1) % len(si.COLORS)]


def render(T: Track, items: list, fi: int, font, floats: set | None = None) -> Image.Image:
    """floats = 떠 있다고 볼 번호 글자들 — 흐린 칠 + 회색 '숫자?' 로 그림."""
    floats = floats or set()
    ov = T.raw(fi)
    cents = []
    for lab, mk in items:
        a = 0.65 if lab == "D" else 0.5
        if lab in floats:
            a = 0.2
        ov[mk] = (1 - a) * ov[mk] + a * np.array(color_of(lab), np.float32)
        if lab == "D":   # D 는 흰 칠 + 검은 테두리(sam2img D 팔과 같은 꼴)
            inner = mk.copy()
            inner[1:, :] &= mk[:-1, :]
            inner[:-1, :] &= mk[1:, :]
            inner[:, 1:] &= mk[:, :-1]
            inner[:, :-1] &= mk[:, 1:]
            ov[mk & ~inner] = 0
        ys, xs = np.nonzero(mk)
        cents.append((lab, xs.mean(), ys.mean()))
    img = Image.fromarray(ov.astype(np.uint8))
    dr = ImageDraw.Draw(img)
    seen = {}
    for lab, x, y in cents:
        k = (round(x / 14), round(y / 14))
        off = seen.get(k, 0)
        seen[k] = off + 1
        if lab in floats:
            dr.text((x, y - 15 * off), lab + "?", fill=(200, 200, 200), font=font, anchor="mm", stroke_width=2, stroke_fill=(60, 60, 60))
        elif lab == "D":
            dr.text((x, y - 15 * off), "D", fill=(230, 0, 0), font=font, anchor="mm", stroke_width=2, stroke_fill=(255, 255, 255))
        else:
            dr.text((x, y - 15 * off), lab, fill=(255, 255, 255), font=font, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
    return img


def row_band(T: Track) -> tuple:
    """첫 프레임 마스크들의 세로 범위(줄 높이) — 검출 상자 중 줄에 있는 것만 고르려고."""
    ys = []
    for o in range(1, T.n + 1):
        mk = T.mask(0, o)
        if mk is not None:
            yy = np.nonzero(mk)[0]
            ys += [yy.min(), yy.max()]
    y0, y1 = min(ys), max(ys)
    h = y1 - y0
    return y0 - 0.6 * h, y1 + 0.6 * h


def checks(T: Track, items: list, fi: int, band: tuple, d_seen: bool) -> list:
    msgs = []
    labs = [l for l, _ in items]
    for l in sorted(set(labs)):
        if labs.count(l) > 1:
            same = [m for x, m in items if x == l]
            if not any((same[0] & m).sum() / max(1, min(same[0].sum(), m.sum())) >= SAME_TILE for m in same[1:]):
                msgs.append(f"번호 {l} 이 두 곳")
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (la, ma), (lb, mb) = items[i], items[j]
            if la == lb:
                continue
            inter = (ma & mb).sum()
            if inter and inter / max(1, min(ma.sum(), mb.sum())) >= SAME_TILE:
                msgs.append(f"한 패에 {la}·{lb}")
    bs = T.boxes.get(fi)
    if bs is not None:
        allm = np.zeros((T.H, T.W), bool)
        for _, mk in items:
            allm |= mk
        row = []
        for x0, y0, x1, y1 in bs:
            yc = (y0 + y1) / 2
            if not (band[0] <= yc <= band[1]):
                continue
            xa, xb, ya, yb = int(max(0, x0)), int(min(T.W, x1)), int(max(0, y0)), int(min(T.H, y1))
            if xb <= xa or yb <= ya:
                continue
            row.append((xa, xb))
            cov = allm[ya:yb, xa:xb].mean()
            if cov < BOX_COVER and d_seen:
                msgs.append(f"번호 없는 패 x {xa}~{xb}")
        if len(row) > T.n + 1:
            msgs.append(f"줄 {len(row)}장(> {T.n + 1})")
    return msgs


def end_order(items: list) -> list:
    c = []
    for lab, mk in items:
        xs = np.nonzero(mk)[1]
        c.append((xs.mean(), lab))
    return [l for _, l in sorted(c)]


def check_edits(edits: list, n: int, F: int) -> list:
    """고침 목록 꼴 검사 → 잘못된 것 설명 목록(비면 통과). claudeagent edit 도구가 그대로 돌려줌."""
    bad = []
    labs = {"D"} | {str(i) for i in range(1, n + 1)}
    for i, e in enumerate(edits):
        op = e.get("op")
        if op not in ("relabel", "drop", "box"):
            bad.append(f"{i}: op 는 relabel · drop · box")
            continue
        if not isinstance(e.get("start"), int) or not (0 <= e["start"] < F) or ("end" in e and e["end"] is not None and not (e["start"] <= e["end"] < F)):
            bad.append(f"{i}: start · end 는 0 ~ {F - 1} 의 프레임(start ≤ end)")
        if op in ("relabel", "drop") and not (isinstance(e.get("o"), int) and 1 <= e["o"] <= n):
            bad.append(f"{i}: o 는 SAM 2 원래 번호 1 ~ {n}")
        if op == "relabel" and str(e.get("to")) not in labs:
            bad.append(f"{i}: to 는 \"D\" 또는 \"1\" ~ \"{n}\"")
        if op == "box":
            if str(e.get("label")) not in labs:
                bad.append(f"{i}: label 은 \"D\" 또는 \"1\" ~ \"{n}\"")
            b = e.get("box")
            if not (isinstance(b, list) and len(b) == 4 and b[2] > b[0] and b[3] > b[1]):
                bad.append(f"{i}: box 는 [x0, y0, x1, y1](x1 > x0 · y1 > y0)")
    return bad


def analyze(T: Track, edits: list, render_to: Path | None = None) -> dict:
    """고침 적용 → 프레임마다 항목 · 검사 · 끝 번호 순서 · k·j. render_to 를 주면 그림도 저장."""
    edits = [{k: v for k, v in e.items() if not (k == "end" and v is None)} for e in edits]   # end 가 null 이면 끝 프레임까지
    font = ImageFont.truetype("arialbd.ttf", 15)
    per = apply_edits(T, edits)
    band = row_band(T)
    lines, flags, d_seen = [], {}, False
    for fi, items in enumerate(per):
        d_seen = d_seen or any(l == "D" for l, _ in items)
        if render_to is not None:
            render(T, items, fi, font).save(render_to / f"{fi:05d}.jpg", quality=90)
        ms = checks(T, items, fi, band, d_seen)
        for m in ms:
            flags.setdefault(m.split(" x ")[0], []).append(fi)
        if ms:
            lines.append(f"{fi:03d} {hc.mss(T.tr['frames'][fi])} | " + " · ".join(ms))
    eo = end_order(per[-1])
    kj = sv.from_order([x for x in eo if x == "D" or x.isdigit()], T.n) if "D" in eo else None
    return {"per": per, "flags": flags, "lines": lines, "end_order": eo, "kj": kj}


def summary(res: dict, max_lines: int = 20) -> str:
    eo, kj = res["end_order"], res["kj"]
    out = [f"끝 프레임 번호 순서(왼쪽부터): {' '.join(eo)} → k·j {('k ' + str(kj[0]) + ' · j ' + str(kj[1])) if kj else '(끝 줄에 D 표시가 하나가 아니어서 못 셈)'}",
           "검사에 걸린 종류(프레임 구간): " + (" | ".join(f"{k}: {si_ranges(v)}" for k, v in res["flags"].items()) or "없음")]
    if res["lines"]:
        out.append("걸린 프레임(앞에서 " + str(min(max_lines, len(res["lines"]))) + "줄):")
        out += res["lines"][:max_lines]
    return "\n".join(out)


def cmd_run(a):
    T = Track(a.id)
    edits = json.loads(a.edits) if a.edits else []
    od = OUT / a.id / a.tag
    (od / "frames").mkdir(parents=True, exist_ok=True)
    bad = check_edits(edits, T.n, T.F)
    if bad:
        raise SystemExit("고침 꼴 틀림: " + " / ".join(bad))
    res = analyze(T, edits, od / "frames")
    flags, lines, eo, kj = res["flags"], res["lines"], res["end_order"], res["kj"]
    head = [f"[{a.id} · {a.tag}] 줄 {T.n}장 · 프레임 {T.F} · 고침 {json.dumps(edits, ensure_ascii=False)}",
            f"끝 프레임 번호 순서(왼쪽부터): {' '.join(eo)}  → k·j {kj if kj else '(D 표시 없음 — 끝 줄에서 못 셈)'}",
            "검사 걸린 종류(프레임 구간): " + " | ".join(f"{k}: {si_ranges(v)}" for k, v in flags.items())]
    (od / "report.txt").write_text("\n".join(head + [""] + lines) + "\n", encoding="utf-8")
    hc.jsave(od / "result.json", {"id": a.id, "tag": a.tag, "edits": edits, "end_order": eo, "kj": kj,
                                  "flags": {k: v for k, v in flags.items()}}, indent=None)
    print("\n".join(head))
    print("그림:", od / "frames")


def si_ranges(xs: list) -> str:
    out, s, p = [], None, None
    for x in xs:
        if s is None or x != p + 1:
            if s is not None:
                out.append(f"{s}" if s == p else f"{s}~{p}")
            s = x
        p = x
    if s is not None:
        out.append(f"{s}" if s == p else f"{s}~{p}")
    return ",".join(out)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("run")
    q.add_argument("id")
    q.add_argument("--tag", default="base")
    q.add_argument("--edits", default="")
    a = ap.parse_args()
    {"run": cmd_run}[a.cmd](a)


if __name__ == "__main__":
    main()
