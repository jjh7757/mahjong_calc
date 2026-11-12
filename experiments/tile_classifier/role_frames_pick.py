"""판 중 프레임 역할·주인 평가 세트 — 프레임 고르기(2026-11-11, `docs/role_owner_plan_1111.md` 3-3절·5절 1단계).

매장 추적 기록(`experiments/visit_2026{1031,1107}/captures/*_track/frames_##.zip`, 1020×764 약 3초 간격)에서
판마다 early / mid / late (+ 덤 open) 프레임을 고른다. 고르기는 사람이 프레임을 열어 보고 정한 것을 아래 PICKS 표에 적은 것이다
(손·팔 가림, 대국 아님, 판 경계는 눈으로 판단). 이 스크립트는 그 표를 검증·풀기·목록 파일로 만든다.

  python -I -X utf8 experiments/tile_classifier/role_frames_pick.py scan     # 도움: 프레임마다 강 앞면 수(검출) → data/role/frames/scan/scan.json
  python -I -X utf8 experiments/tile_classifier/role_frames_pick.py sheet <track> [start] [count] [step]  # 도움: 훑어보기 그림
  python -I -X utf8 experiments/tile_classifier/role_frames_pick.py pick     # PICKS → pick.json + images/<이름>.jpg

나눔: 10-31 판 = dev, 11-07 판 = test(계획 3-3). 역할 모델은 쓰지 않는다.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments"
OUT = EXP / "tile_classifier/data/role/frames"
REC = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer")
SIDES = ("bottom", "right", "top", "left")


def tracks() -> list[Path]:
    out = []
    for v in ("visit_20261031", "visit_20261107"):
        out += [t for t in sorted((EXP / v / "captures").glob("*_track")) if list(t.glob("frames_*.zip"))]
    return out


def frames(track: Path):
    """(zip 이름, frames.json 메타, 프레임 항목) 차례로."""
    for z in sorted(track.glob("frames_*.zip")):
        with zipfile.ZipFile(z) as zf:
            meta = json.loads(zf.read("frames.json"))
        for f in meta["frames"]:
            yield z.name, meta, f


def read_jpg(track: Path, zname: str, fname: str) -> bytes:
    with zipfile.ZipFile(track / zname) as zf:
        return zf.read(fname)


def dark_device(rgb: np.ndarray, cx: float, cy: float, r: int = 160) -> tuple[float, float, float]:
    """기기(어두운 사각형) 중심·반 크기 — paifu_frames.device_box 와 같음."""
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = int(max(0, cx - r)), int(max(0, cy - r)), int(min(W, cx + r)), int(min(H, cy + r))
    a = rgb[y0:y1, x0:x1].astype(int)
    dark = (a.max(2) < 90) & ~((a[..., 1] > a[..., 0] + 25) & (a[..., 1] > a[..., 2]))
    ys, xs = np.nonzero(dark)
    if len(xs) < 500:
        return cx, cy, 70.0
    lx, hx = np.percentile(xs, [3, 97])
    ly, hy = np.percentile(ys, [3, 97])
    return x0 + (lx + hx) / 2, y0 + (ly + hy) / 2, ((hx - lx) + (hy - ly)) / 4


def device(grid: dict, W: int, H: int, rgb: np.ndarray | None = None) -> tuple[float, float, float]:
    """grid.sticks [ymin, xmin, ymax, xmax](1000분율) → 기기 중심·반 크기(px). sticks 가 없으면 격자 가운데에서 어두운 화소로."""
    if "sticks" not in grid:
        return dark_device(rgb, (grid["x1"] + grid["x2"]) / 2000 * W, (grid["y1"] + grid["y2"]) / 2000 * H)
    y0, x0, y1, x1 = grid["sticks"]
    cx, cy = (x0 + x1) / 2000 * W, (y0 + y1) / 2000 * H
    return cx, cy, ((x1 - x0) / 1000 * W + (y1 - y0) / 1000 * H) / 4


def to_side(side: str, dx: float, dy: float) -> tuple[float, float]:
    """기기 중심 상대 좌표 → 그 자리 기준 (u = 그 자리 사람의 오른쪽, v = 그 사람 쪽 바깥)."""
    return {"bottom": (dx, dy), "right": (-dy, dx), "top": (-dx, -dy), "left": (dy, -dx)}[side]


def river_side(cx, cy, hd, box) -> str | None:
    """강 띠(기기 변에서 바깥 0.8~2.9 hd, 옆으로 −1.4~1.8 hd)에 든 자리. paifu_frames.assign 과 같은 꼴(띠를 조금 넓힘)."""
    bx, by = box[0] + box[2] / 2 - cx, box[1] + box[3] / 2 - cy
    best = None
    for s in SIDES:
        u, v = to_side(s, bx, by)
        if v < hd * 0.8 or v > hd * 2.9 or u < -hd * 1.4 or u > hd * 1.8:
            continue
        over = max(0.0, abs(u) - hd) if u < 0 else max(0.0, u - hd * 1.05)
        if best is None or (over, v) < best[0]:
            best = ((over, v), s)
    return None if best is None else best[1]


def scan():
    """프레임마다 사진 전체 검출(운영 자리 판독 검출기) → 강 띠 자리별 앞면 수·그 밖 앞면 수. 판 경계·시점 고르기 도움용."""
    sys.path.insert(0, str(REC))
    from app.local_read import LocalReader

    rd = LocalReader(threads=4)
    rd._sessions()
    dst = OUT / "scan"
    dst.mkdir(parents=True, exist_ok=True)
    path = dst / "scan.json"
    res = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for t in tracks():
        if t.name in res:
            continue
        rows = []
        for zname, meta, f in frames(t):
            rgb = np.asarray(Image.open(io.BytesIO(read_jpg(t, zname, f["file"]))).convert("RGB"))
            H, W = rgb.shape[:2]
            faces, backs, _, _ = rd._seat_raw(rgb)
            cx, cy, hd = device(meta["grid"], W, H, rgb)
            riv = {s: 0 for s in SIDES}
            other = 0
            for b, _ in faces:
                s = river_side(cx, cy, hd, b)
                if s:
                    riv[s] += 1
                else:
                    other += 1
            rows.append({"zip": zname, "file": f["file"], "at": f["at"], "river": riv, "other": other, "backs": len(backs)})
        res[t.name] = rows
        path.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(t.name, len(rows), flush=True)


def sheet(track_name: str, start: int = 0, count: int = 30, step: int = 1, tw: int = 340):
    t = next(x for x in tracks() if x.name == track_name)
    fr = list(frames(t))
    sel = list(range(len(fr)))[start::step][:count]
    th = int(tw * 764 / 1020)
    cols = 6
    rows = (len(sel) + cols - 1) // cols
    sh = Image.new("RGB", (cols * tw, rows * (th + 14)), "black")
    d = ImageDraw.Draw(sh)
    for k, i in enumerate(sel):
        zname, meta, f = fr[i]
        im = Image.open(io.BytesIO(read_jpg(t, zname, f["file"]))).convert("RGB").resize((tw, th))
        x, y = (k % cols) * tw, (k // cols) * (th + 14)
        sh.paste(im, (x, y + 14))
        d.text((x + 2, y), f"{i} {zname[7:9]}/{f['file']}", fill="yellow")
    dst = OUT / "scan/sheets"
    dst.mkdir(parents=True, exist_ok=True)
    p = dst / f"{track_name}_{start:04d}.jpg"
    sh.save(p, quality=85)
    print(p, len(fr))


# ---------------------------------------------------------------- 고른 프레임 표(눈으로 정함)
# (track, zip, file, phase, round 메모) — 판(round_key)은 frames.json 에서 읽고, 한 트랙에 여러 판이 든 긴 기록은 메모에 판 번호를 적는다.
PICKS: list[tuple] = [
    # ---- 10-31 (dev). 오전 기록은 한 사람이 네 자리를 혼자 두는 모습이라 빼고(SKIP_TRACKS), 4명 대국만.
    # 남3국 133940 (13:43~13:48, 화료 사진 134815)
    ("20261031_133940_track", "frames_01.zip", "f0086_134425.jpg", "early", "남3국(13:43~13:48, 화료 134815)"),
    ("20261031_133940_track", "frames_01.zip", "f0108_134610.jpg", "mid", "남3국(13:43~13:48, 화료 134815)"),
    ("20261031_133940_track", "frames_01.zip", "f0129_134752.jpg", "late", "남3국(13:43~13:48, 화료 134815)"),
    ("20261031_133940_track", "frames_01.zip", "f0132_134807.jpg", "open", "남3국(13:43~13:48, 화료 134815)"),
    # 141615 기록 안의 판들(앱이 판을 안 넘겨 한 기록에 여러 판)
    ("20261031_141615_track", "frames_01.zip", "f0089_142249.jpg", "early", "141615 판B(14:21~14:25, 화료 142535)"),
    ("20261031_141615_track", "frames_01.zip", "f0101_142340.jpg", "mid", "141615 판B(14:21~14:25, 화료 142535)"),
    ("20261031_141615_track", "frames_01.zip", "f0111_142422.jpg", "late", "141615 판B(14:21~14:25, 화료 142535)"),
    ("20261031_141615_track", "frames_02.zip", "f0149_142746.jpg", "early", "141615 판C(14:26~14:31, 화료 143104)"),
    ("20261031_141615_track", "frames_02.zip", "f0175_142937.jpg", "mid", "141615 판C(14:26~14:31, 화료 143104)"),
    ("20261031_141615_track", "frames_02.zip", "f0187_143025.jpg", "late", "141615 판C(14:26~14:31, 화료 143104)"),
    ("20261031_141615_track", "frames_03.zip", "f0310_164322.jpg", "early", "141615 판F(16:42~16:45, 화료 164501)"),
    ("20261031_141615_track", "frames_03.zip", "f0318_164437.jpg", "mid", "141615 판F(16:42~16:45, 화료 164501)"),
    ("20261031_141615_track", "frames_03.zip", "f0322_164455.jpg", "late", "141615 판F(16:42~16:45, 화료 164501)"),
    # 170310 기록 안의 판들
    ("20261031_170310_track", "frames_01.zip", "f0052_170849.jpg", "early", "170310 판P2(17:07~17:10, 화료 171025)"),
    ("20261031_170310_track", "frames_01.zip", "f0060_170928.jpg", "mid", "170310 판P2(17:07~17:10, 화료 171025)"),
    ("20261031_170310_track", "frames_01.zip", "f0069_171016.jpg", "late", "170310 판P2(17:07~17:10, 화료 171025)"),
    ("20261031_170310_track", "frames_03.zip", "f0133_172031.jpg", "early", "170310 판P6(17:19~17:24, 화료 172424)"),
    ("20261031_170310_track", "frames_03.zip", "f0153_172158.jpg", "mid", "170310 판P6(17:19~17:24, 화료 172424)"),
    ("20261031_170310_track", "frames_03.zip", "f0173_172416.jpg", "late", "170310 판P6(17:19~17:24, 화료 172424)"),
    ("20261031_170310_track", "frames_04.zip", "f0177_172504.jpg", "open", "170310 판P6(17:19~17:24, 화료 172424)"),
    ("20261031_170310_track", "frames_04.zip", "f0216_172819.jpg", "early", "170310 판P7(17:26~17:33)"),
    ("20261031_170310_track", "frames_04.zip", "f0228_172919.jpg", "mid", "170310 판P7(17:26~17:33)"),
    ("20261031_170310_track", "frames_04.zip", "f0264_173301.jpg", "late", "170310 판P7(17:26~17:33)"),
    ("20261031_170310_track", "frames_04.zip", "f0298_173537.jpg", "early", "170310 판P8(17:33~17:40, 화료 174020)"),
    ("20261031_170310_track", "frames_04.zip", "f0314_173658.jpg", "mid", "170310 판P8(17:33~17:40, 화료 174020)"),
    ("20261031_170310_track", "frames_05.zip", "f0334_173922.jpg", "late", "170310 판P8(17:33~17:40, 화료 174020)"),
    ("20261031_170310_track", "frames_07.zip", "f0525_180810.jpg", "early", "170310 판P12(18:06~18:12, 화료 181209)"),
    ("20261031_170310_track", "frames_07.zip", "f0538_180955.jpg", "mid", "170310 판P12(18:06~18:12, 화료 181209)"),
    ("20261031_170310_track", "frames_08.zip", "f0570_181928.jpg", "early", "170310 판P13(18:18~18:24, 유국 텐파이 공개)"),
    ("20261031_170310_track", "frames_08.zip", "f0582_182037.jpg", "mid", "170310 판P13(18:18~18:24, 유국 텐파이 공개)"),
    ("20261031_170310_track", "frames_08.zip", "f0620_182410.jpg", "late", "170310 판P13(18:18~18:24, 유국 텐파이 공개)"),
    ("20261031_170310_track", "frames_08.zip", "f0622_182425.jpg", "open", "170310 판P13(18:18~18:24, 유국 텐파이 공개)"),
    ("20261031_170310_track", "frames_08.zip", "f0643_182555.jpg", "early", "170310 판P14(18:24~18:30, 화료 183022)"),
    ("20261031_170310_track", "frames_08.zip", "f0657_182737.jpg", "mid", "170310 판P14(18:24~18:30, 화료 183022)"),
    ("20261031_170310_track", "frames_08.zip", "f0683_182958.jpg", "late", "170310 판P14(18:24~18:30, 화료 183022)"),
    # ---- 11-07 (test). 오전 기록은 혼자 두는 연출이라 빼고, 오후 손님 4명 대국만.
    ("20261107_140304_track", "frames_01.zip", "f0031_140504.jpg", "early", "140304 판Q1(14:04~14:11)"),
    ("20261107_140304_track", "frames_01.zip", "f0060_140658.jpg", "mid", "140304 판Q1(14:04~14:11)"),
    ("20261107_140304_track", "frames_01.zip", "f0123_141101.jpg", "late", "140304 판Q1(14:04~14:11)"),
    ("20261107_140304_track", "frames_01.zip", "f0143_141213.jpg", "early", "140304 판Q2(14:11~14:17)"),
    ("20261107_140304_track", "frames_02.zip", "f0173_141358.jpg", "mid", "140304 판Q2(14:11~14:17)"),
    ("20261107_140304_track", "frames_02.zip", "f0215_141652.jpg", "late", "140304 판Q2(14:11~14:17)"),
    ("20261107_140304_track", "frames_02.zip", "f0219_141704.jpg", "open", "140304 판Q2(14:11~14:17)"),
    ("20261107_140304_track", "frames_02.zip", "f0242_141822.jpg", "early", "140304 판Q3(14:17~14:21, 화료 142136)"),
    ("20261107_140304_track", "frames_02.zip", "f0267_141955.jpg", "mid", "140304 판Q3(14:17~14:21, 화료 142136)"),
    ("20261107_140304_track", "frames_02.zip", "f0285_142113.jpg", "late", "140304 판Q3(14:17~14:21, 화료 142136)"),
    ("20261107_140304_track", "frames_03.zip", "f0292_142513.jpg", "mid", "140304 판Q4(~14:26, 화료 142639, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_03.zip", "f0305_142622.jpg", "late", "140304 판Q4(~14:26, 화료 142639, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_04.zip", "f0313_142858.jpg", "mid", "140304 판Q5(~14:32, 화료 143234, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_04.zip", "f0365_143228.jpg", "late", "140304 판Q5(~14:32, 화료 143234, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_05.zip", "f0388_143919.jpg", "late", "140304 판Q6(~14:39, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_05.zip", "f0389_143928.jpg", "open", "140304 판Q6(~14:39, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_05.zip", "f0408_144031.jpg", "early", "140304 판Q7(14:39~14:43, 화료 144348)"),
    ("20261107_140304_track", "frames_05.zip", "f0430_144228.jpg", "mid", "140304 판Q7(14:39~14:43, 화료 144348)"),
    ("20261107_140304_track", "frames_05.zip", "f0440_144322.jpg", "late", "140304 판Q7(14:39~14:43, 화료 144348)"),
    ("20261107_140304_track", "frames_06.zip", "f0447_144710.jpg", "mid", "140304 판Q8(~14:50, 화료 145058, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_06.zip", "f0492_145041.jpg", "late", "140304 판Q8(~14:50, 화료 145058, 앞부분 프레임 없음)"),
    ("20261107_140304_track", "frames_07.zip", "f0502_145243.jpg", "early", "140304 판Q9(14:52~14:58)"),
    ("20261107_140304_track", "frames_07.zip", "f0521_145404.jpg", "mid", "140304 판Q9(14:52~14:58)"),
    ("20261107_140304_track", "frames_07.zip", "f0575_145749.jpg", "late", "140304 판Q9(14:52~14:58)"),
    ("20261107_140304_track", "frames_07.zip", "f0577_145804.jpg", "open", "140304 판Q9(14:52~14:58)"),
    ("20261107_140304_track", "frames_08.zip", "f0746_150910.jpg", "early", "140304 판Q12(15:08~15:13, 화료 151320)"),
    ("20261107_140304_track", "frames_08.zip", "f0773_151052.jpg", "mid", "140304 판Q12(15:08~15:13, 화료 151320)"),
    ("20261107_140304_track", "frames_09.zip", "f0803_151304.jpg", "late", "140304 판Q12(15:08~15:13, 화료 151320)"),
    ("20261107_140304_track", "frames_10.zip", "f0877_152143.jpg", "early", "140304 판Q14(15:21~15:26)"),
    ("20261107_140304_track", "frames_10.zip", "f0901_152313.jpg", "mid", "140304 판Q14(15:21~15:26)"),
    ("20261107_140304_track", "frames_10.zip", "f0929_152507.jpg", "late", "140304 판Q14(15:21~15:26)"),
    ("20261107_153128_track", "frames_01.zip", "f0023_153157.jpg", "early", "R2 동2국(15:30~15:33, 화료 153311)"),
    ("20261107_153128_track", "frames_01.zip", "f0034_153233.jpg", "mid", "R2 동2국(15:30~15:33, 화료 153311)"),
    ("20261107_153128_track", "frames_01.zip", "f0040_153301.jpg", "late", "R2 동2국(15:30~15:33, 화료 153311)"),
    ("20261107_153423_track", "frames_01.zip", "f0018_153437.jpg", "early", "R3a 동3국(15:33~15:36, 화료 153638)"),
    ("20261107_153423_track", "frames_01.zip", "f0034_153539.jpg", "mid", "R3a 동3국(15:33~15:36, 화료 153638)"),
    ("20261107_153423_track", "frames_01.zip", "f0041_153621.jpg", "late", "R3a 동3국(15:33~15:36, 화료 153638)"),
    ("20261107_153423_track", "frames_02.zip", "f0046_153816.jpg", "early", "R3b 동3국 1본장(15:38~15:39, 화료 153939, 앞부분 프레임 적음)"),
    ("20261107_153423_track", "frames_02.zip", "f0058_153900.jpg", "mid", "R3b 동3국 1본장(15:38~15:39, 화료 153939, 앞부분 프레임 적음)"),
    ("20261107_153423_track", "frames_02.zip", "f0064_153924.jpg", "late", "R3b 동3국 1본장(15:38~15:39, 화료 153939, 앞부분 프레임 적음)"),
    ("20261107_154029_track", "frames_01.zip", "f0015_154049.jpg", "early", "R4 동4국(15:40~15:44, 화료 154417)"),
    ("20261107_154029_track", "frames_01.zip", "f0041_154233.jpg", "mid", "R4 동4국(15:40~15:44, 화료 154417)"),
    ("20261107_154029_track", "frames_01.zip", "f0064_154401.jpg", "late", "R4 동4국(15:40~15:44, 화료 154417)"),
    ("20261107_154029_track", "frames_01.zip", "f0066_154410.jpg", "open", "R4 동4국(15:40~15:44, 화료 154417)"),
    ("20261107_154548_track", "frames_01.zip", "f0017_154558.jpg", "early", "R5 남1국(15:45~15:47)"),
    ("20261107_154548_track", "frames_01.zip", "f0039_154704.jpg", "mid", "R5 남1국(15:45~15:47)"),
    ("20261107_155125_track", "frames_01.zip", "f0006_155134.jpg", "early",
     "R6 새 대국 남1국(15:51~15:55, 화료 155553, 카메라 위치 다름)"),
    ("20261107_155125_track", "frames_01.zip", "f0041_155352.jpg", "mid", "R6 새 대국 남1국(15:51~15:55, 화료 155553, 카메라 위치 다름)"),
    ("20261107_155125_track", "frames_01.zip", "f0061_155510.jpg", "late", "R6 새 대국 남1국(15:51~15:55, 화료 155553, 카메라 위치 다름)"),
    ("20261107_155125_track", "frames_01.zip", "f0073_155552.jpg", "open", "R6 새 대국 남1국(15:51~15:55, 화료 155553, 카메라 위치 다름)"),
]
# 뺀 판·트랙(사유)
SKIP_TRACKS: dict[str, str] = {
    "20261029_220330_track": "10-29 밤(10-31 매장 아님) — 패를 세워 둔 시험 기록 9장, 대국 아님",
    "20261029_230849_track": "10-29 밤(10-31 매장 아님) — 시험 기록 6장, 대국 아님",
    "20261030_133951_track": "10-30(10-31 매장 아님) — 테스트 세트 지침(B·C·D + 10-31 + 11-07)에 안 듦",
    "20261031_122417_track": "10-31 오전 — 한 사람이 네 자리를 혼자 두는 연출(손님 없음), 실제 대국 아님",
    "20261031_123457_track": "10-31 오전 연출(혼자 네 자리)",
    "20261031_124830_track": "10-31 오전 연출(혼자 네 자리)",
    "20261031_125948_track": "10-31 오전 연출(혼자 네 자리)",
    "20261031_131554_track": "10-31 오전 연출(혼자 네 자리)",
    "20261031_132352_track": "10-31 오전 연출(혼자 네 자리)",
    "20261031_133112_track": "10-31 오전 연출(혼자 네 자리)",
    "20261031_141615_track#A": "141615 첫 판(14:16~14:21): 기록이 판 중간부터 시작(첫 프레임 강 39장), early 없음 — 판B·C·F 만 씀",
    "20261031_141615_track#DE": "141615 16:35~16:42: 앱 재시작 직후 손·팔이 계속 들어오고(장면 변화 반복) 강이 이미 51장인 채 시작 — 가림 많아 뺌",
    "20261031_170310_track#P1": "170310 첫 판(17:03~17:07): 판 중간부터 시작, 남은 프레임은 손패 펼침 직전뿐",
    "20261031_170310_track#P3P4P5": "170310 17:14~17:19: 판 중간에 기록이 끊겨(221·132초 틈) 시점 셋을 못 맞춤 — 판 수가 충분해 뺌",
    "20261031_170310_track#P9P10P11": "170310 17:48~18:06: 판 수 목표(dev 약 35장)를 채워 고르지 않음(가림 확인 안 함)",
    "20261031_170310_track#P15": "170310 18:33~18:38: 판 중간부터 시작 + 끝(18:37~)에 손이 패를 계속 가림",
    "20261107_113757_track": "11-07 오전 시험 기록(18장, 1분) — 대국 아님",
    "20261107_114438_track": "11-07 오전 연출(혼자 네 자리)",
    "20261107_120534_track": "11-07 오전 연출(한 사람이 네 자리를 두며 팔이 계속 가림, 화료 사진은 연출 121515)",
    "20261107_121543_track": "11-07 오전 연출(혼자 네 자리)",
    "20261107_122355_track": "11-07 오전 연출(혼자 네 자리)",
    "20261107_123155_track": "11-07 오전 연출(혼자 네 자리)",
    "20261107_123820_track": "11-07 오전 연출(혼자 네 자리)",
    "20261107_124740_track": "11-07 오전 연출(혼자 네 자리)",
    "20261107_125549_track": "11-07 오전 연출(혼자 네 자리)",
    "20261107_130655_track": "11-07 13시 연출(혼자, 태블릿이 탁자 위에 놓여 가림)",
    "20261107_140034_track": "프레임 1장",
    "20261107_140227_track": "프레임 4장(판 시작 전)",
    "20261107_153020_track": "프레임 2장(판 시작 전)",
    "20261107_154823_track": "프레임 2장",
    "20261107_154851_track": "프레임 1장",
    "20261107_154903_track": "프레임 4장",
    "20261107_163212_track": "프레임 4장(패 섞는 중)",
    "20261107_140304_track#Q10Q11Q13": "140304 14:58~15:08·15:16~15:20: 판 수 목표(test 약 45장)를 채워 고르지 않음(가림 확인 안 함)",
    "20261107_155125_track#camera": "R6 는 판 중 카메라가 움직여(기기 중심 580 → 648px) 격자의 기기 상자가 안 맞음 — 초안에서 프레임마다 기기를 손으로 잼(FIXES device). early 는 강 5장씩(첫 줄 거의 참)",
}
# 뺀 프레임(가림 등) — 고르려다 뺀 것만 적는다(전부 적지 않음)
SKIP_FRAMES: list[tuple] = [
    ("20261031_133940_track", "f0132_134807.jpg", "late 후보였으나 아래 사람이 이미 손패를 펼침(화료 직후) → open 으로 돌리고 late 는 f0129"),
    ("20261031_133940_track", "f0138_134858.jpg", "open 후보: 화료 뒤 손패를 정리하며 손이 강 위를 지나감"),
    ("20261107_140304_track", "f0124_141104.jpg", "Q1 late 후보: 왼쪽 팔이 왼쪽 패산·강 쪽을 가림"),
    ("20261107_140304_track", "f0524_145416.jpg", "Q9 mid 후보: 위 사람 팔이 강 위를 가림"),
    ("20261107_140304_track", "f0172_141349.jpg", "Q2 mid 후보: 왼쪽 손이 강 가까이 들어옴"),
    ("20261107_153128_track", "f0031_153225.jpg", "R2 mid 후보: 팔이 기기·아래 강을 가림 → f0034"),
    ("20261107_153128_track", "f0041_153303.jpg", "R2 late 후보: 팔이 강·패산을 가림"),
    ("20261107_153423_track", "f0030_153527.jpg", "R3a mid 후보: 왼쪽 팔이 강을 가림"),
    ("20261107_153423_track", "f0063_153922.jpg", "R3b late 후보: 왼쪽 팔이 강을 가림"),
    ("20261107_140304_track", "f0431_144231.jpg", "Q7 mid 후보: 위 사람 손이 왼쪽 위 모서리 울기를 놓는 중(셋째 장 가림) → f0430"),
    ("20261107_155125_track", "f0024_155246.jpg", "R6 mid 후보: 왼쪽 손이 왼쪽 강 위에 얹힘 → f0041"),
    ("20261107_154029_track", "f0040_154231.jpg", "R4 mid 후보: 오른쪽 팔이 강을 가림"),
]


def name_of(track: str, file: str) -> str:
    return f"{track[:15]}_f{file[1:5]}"


def pick():
    import shutil

    by = {t.name: t for t in tracks()}
    img = OUT / "images"
    img.mkdir(parents=True, exist_ok=True)
    out = []
    for tr, zname, fname, phase, note in PICKS:
        t = by[tr]
        meta = json.loads(zipfile.ZipFile(t / zname).read("frames.json"))
        f = next(x for x in meta["frames"] if x["file"] == fname)
        nm = name_of(tr, fname)
        (img / f"{nm}.jpg").write_bytes(read_jpg(t, zname, fname))
        split = "dev" if "visit_20261031" in str(t) else "test"
        out.append({"name": nm, "track": f"{t.parent.parent.name}/captures/{tr}", "zip": zname, "file": fname, "at": f["at"],
                    "round_key": meta.get("round_key"), "round": note, "phase": phase, "split": split,
                    "bottom_seat": meta.get("bottom_seat"), "grid": meta["grid"]})
    names = [o["name"] for o in out]
    assert len(names) == len(set(names)), "같은 프레임 두 번"
    # 고른 표에 없는 옛 그림 지우기(다시 돌려도 같은 결과)
    for p in img.glob("*.jpg"):
        if p.stem not in names:
            p.unlink()
    cnt = {}
    for o in out:
        cnt.setdefault(o["split"], {}).setdefault(o["phase"], 0)
        cnt[o["split"]][o["phase"]] += 1
    rounds = {sp: len({(o["track"], o["round"]) for o in out if o["split"] == sp}) for sp in ("dev", "test")}
    doc = {"_note": "판 중 프레임 역할·주인 평가 세트 고르기(role_frames_pick.py). 10-31 판 = dev, 11-07 판 = test. "
                    "early = 강 사람마다 1~4장, mid = 강 둘째 줄, late = 그 판 끝 무렵 아직 아무도 손패를 펼치지 않음, open = 손패를 펼친 장면(덤). "
                    "가림 기준: 손·팔이 앞면 패(강·울기·표시패)나 패산을 가리면 뺌. 자기 세운 손패 뒤에 손을 얹은 것은 앞면을 안 가리면 둠.",
           "counts": cnt, "rounds": rounds, "frames": out,
           "skipped_tracks": SKIP_TRACKS,
           "skipped_frames": [{"track": a, "file": b, "why": c} for a, b, c in SKIP_FRAMES]}
    (OUT / "pick.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(cnt, ensure_ascii=False), rounds, len(out))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pick"
    if cmd == "scan":
        scan()
    elif cmd == "sheet":
        a = sys.argv[2:]
        sheet(a[0], *(int(x) for x in a[1:]))
    else:
        pick()
