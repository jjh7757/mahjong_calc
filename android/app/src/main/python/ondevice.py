"""기기 판독 실험(exp/on-device-read): 서버 main.py 의 자체 판독 세 엔드포인트를 앱 안에서.

서버 코드(`app/` 패키지, 빌드 때 mahjong-recognizer 에서 복사)를 그대로 부르고, 요청 처리(쿼리 해석·prepare_image)만 여기서 서버와 같게 한다.
  /v2/localroles  → roles.read_roles(reader, prepare_image(4080), side, grid, mode, None, frame, grid_src)
  /v2/localdora   → reader.read_wall(prepare_image(4080), frame, grid, grid_src)
  localsetup      → table_locate.frame_for + grid_from_frame(서버에 없는 종류 — 서버 없는 자동 맞추기용, 격자 x1·x2·y1·y2·sticks)
  /v2/locallast3  → sides 가 있으면 reader.read_rivers_full(prepare_image(4080), sides, grid, frame, grid_src), 없으면 read_rivers_app([prepare_image(3072)…])
응답은 서버와 같은 JSON 문자열 + `ondevice`(기기 시간 ms: prep·work·total). 오류는 예외 그대로(Kotlin → Dart 에서 RecognizerException).
"""
from __future__ import annotations

import io
import json
import threading
import time

import numpy as np
from PIL import Image, ImageOps

MAX_PIXELS = 40_000_000  # 서버 recognizer.MAX_PIXELS 기본값
# "server" = 서버처럼 prepare_image(q90 재저장)를 거침(서버와 같은 바이트) · "skip" = 이미 긴 변 이하 JPEG 이고 EXIF 회전이 없으면 받은 바이트 그대로.
# 기본 "skip"(2026-11-11 사용자 결정 "실사용 때 1.4초는 매우 체감된다"): 앱 흐름 장면 5.92 → 4.46초. 고정 21변형 회귀는 unsafe 11 → 13 으로
# 미리 정한 기준엔 걸렸다(경계 조건 wb_fluo k12, 흰 테두리 헛검출 — problem_log 54번). 측정은 bench manifest "prep"·setPrep 로 바꾼다.
PREP = "skip"
_lock = threading.Lock()  # 판독기 만들기만(판독은 서버처럼 여러 스레드에서 동시에 — Kotlin 쪽 스레드 3개)
_reader = None
# 같은 원본의 prepare 결과를 호출끼리 나눠 쓴다(서버 main._prepare_shared 와 같은 일: 앱이 localroles·localdora·locallast3 에 같은 원본을 보냄).
_prep_lock = threading.Lock()
_prep_cache: dict = {}  # (sha1, max_side, PREP) → bytes, 최근 2개


def prepare_image(data: bytes, max_side: int = 1568) -> bytes:
    """서버 app.recognizer.prepare_image 와 같다(EXIF 회전, 긴 변 max_side 이하 LANCZOS, JPEG q90). recognizer 는 Gemini 를 import 해서 복사."""
    img = Image.open(io.BytesIO(data))
    w, h = img.size
    if w * h > MAX_PIXELS:
        raise ValueError(f"too many pixels ({w}x{h} > {MAX_PIXELS})")
    if img.format == "JPEG":
        img.draft("RGB", (max_side, max_side))
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def set_prep(v: str) -> str:
    """측정용: "server" | "skip"."""
    global PREP
    if v not in ("server", "skip"):
        raise ValueError(v)
    PREP = v
    return PREP


def _prepare(data: bytes, max_side: int) -> bytes:
    import hashlib

    key = (hashlib.sha1(data).hexdigest(), max_side, PREP)
    with _prep_lock:  # 같은 사진을 셋이 동시에 부르면 한 번만 만들고 나머지는 기다렸다 받는다
        if key in _prep_cache:
            return _prep_cache[key]
        out = _prepare_now(data, max_side)
        _prep_cache[key] = out
        while len(_prep_cache) > 2:
            _prep_cache.pop(next(iter(_prep_cache)))
        return out


def _prepare_now(data: bytes, max_side: int) -> bytes:
    if PREP == "skip":
        img = Image.open(io.BytesIO(data))
        orient = img.getexif().get(0x0112, 1)
        if img.format == "JPEG" and max(img.size) <= max_side and orient in (None, 1) and img.mode == "RGB":
            return data
    return prepare_image(data, max_side)


def _get_reader():
    global _reader
    with _lock:
        if _reader is None:
            from app.local_read import LocalReader

            _reader = LocalReader(gate=None)
        return _reader


def _int(q: dict, k: str):
    v = q.get(k)
    return None if v in (None, "") else int(v)


def _grid(q: dict, required: bool) -> dict | None:
    vals = [_int(q, k) for k in ("x1", "x2", "y1", "y2")]
    if None in vals:
        if required:
            raise ValueError("grid x1·x2·y1·y2 필요")
        return None
    x1, x2, y1, y2 = vals
    if not (x1 < x2 and y1 < y2):
        raise ValueError("grid")
    return {"x1": x1, "x2": x2, "y1": y1, "y2": y2}


def _frame(q: dict):
    from app import table_locate as tl

    return tl.parse_frame(q.get("frame"))


def _grid_src(q: dict):
    from app import table_locate as tl

    v = q.get("grid_src")
    if v is None or v == "":
        return None
    v = v.strip().lower()
    if v not in tl.GRID_SRCS:
        raise ValueError("grid_src=" + "|".join(tl.GRID_SRCS))
    return v


def _plain(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"JSON 으로 못 바꿈: {type(o).__name__}")


def observe(kind: str, images, query) -> str:
    imgs = [bytes(b) for b in images]
    q = {str(k): str(v) for k, v in dict(query).items()}
    if True:  # 예전엔 전역 락으로 한 번에 하나씩(metrics 표 4-1 13:47 측정) — 이제 서버처럼 동시에
        t0 = time.perf_counter()
        reader = _get_reader()
        if kind == "localroles":
            from app import roles

            side, mode = q.get("side", ""), q.get("mode", "hybrid")
            if side not in roles.SIDES or mode not in ("hybrid", "model"):
                raise ValueError("side/mode")
            grid = _grid(q, True)
            if q.get("sticks"):
                grid["sticks"] = [int(v) for v in q["sticks"].split(",")]
            fr, src = _frame(q), _grid_src(q)
            jpeg = _prepare(imgs[0], 4080)
            t1 = time.perf_counter()
            out = roles.read_roles(reader, jpeg, side, grid, mode, None, fr, src)
        elif kind == "localdora":
            grid, fr, src = _grid(q, False), _frame(q), _grid_src(q)
            jpeg = _prepare(imgs[0], 4080)
            t1 = time.perf_counter()
            out = reader.read_wall(jpeg, fr, grid, src)
        elif kind == "locallast3":
            from app import roles

            sides = [s for s in (q.get("sides") or "").split(",") if s]
            grid, fr, src = _grid(q, False), _frame(q), _grid_src(q)
            if "sides" in q:
                if len(imgs) != 1 or not 1 <= len(sides) <= 4 or any(s not in roles.SIDES for s in sides):
                    raise ValueError("sides")
                jpeg = _prepare(imgs[0], 4080)
                t1 = time.perf_counter()
                out = reader.read_rivers_full(jpeg, sides, grid, fr, src)
            else:
                jpegs = [_prepare(b, 3072) for b in imgs]
                t1 = time.perf_counter()
                out = reader.read_rivers_app(jpegs)
        elif kind == "localsetup":
            # 서버 없는 자동 맞추기(2026-11-13 사용자 "자체 판독일 때 서버 없이 맞추기"): 서버 `/v2/setup` 은 Gemini 라 기기로 못 옮긴다.
            # 대신 사진 전체 검출로 탁자 기준점(가운데 기기 → 없으면 패산, table_locate.frame_for)을 잡고 같은 뜻의 축 평행 격자로
            # (grid_from_frame — 서버 WALL_FRAME=axis 와 같은 격자). 못 잡으면 grid None + frame_error.
            from app import local_read as lr
            from app import table_locate as tl

            jpeg = _prepare(imgs[0], 4080)
            t1 = time.perf_counter()
            rgb = lr.decode_rgb(jpeg)
            tz, meta = tl.frame_for(reader, jpeg, rgb)
            out = {"grid": tl.grid_from_frame(tz) if tz is not None else None, **meta}
        else:
            raise ValueError(f"기기 판독에 없는 종류: {kind}")
        t2 = time.perf_counter()
    out = dict(out)
    out["ondevice"] = {"prep_ms": round((t1 - t0) * 1000), "work_ms": round((t2 - t1) * 1000), "total_ms": round((t2 - t0) * 1000)}
    return json.dumps(out, ensure_ascii=False, default=_plain)


def warmup() -> str:
    """모듈 import 와 모델 올리기(검출 2·분류기 2·역할 1)를 미리."""
    t0 = time.perf_counter()
    from app import roles, signals  # noqa: F401

    reader = _get_reader()
    reader._sessions()
    t1 = time.perf_counter()
    try:
        roles.RoleNet(roles.ROLE_MODEL)
    except Exception:  # noqa: BLE001 — 시간만 재는 것
        pass
    return json.dumps({"import_ms": round((t1 - t0) * 1000), "total_ms": round((time.perf_counter() - t0) * 1000)})


def bench(manifest: str) -> str:
    """측정용(OnDeviceBenchReceiver): manifest JSON {"tag", "items": [{"name", "kind", "images": [기기 경로…], "query": {…}}]} 을
    차례로 [observe] 하고 결과(사진별 응답·시간·오류)를 manifest 옆 result_<tag>.json 으로. 첫 항목 전에 [warmup]."""
    import os

    with open(manifest, encoding="utf-8") as f:
        m = json.loads(f.read())
    global PREP
    PREP = m.get("prep", PREP)
    out = {"tag": m.get("tag"), "prep": PREP, "warmup": json.loads(warmup()), "items": []}
    t_all = time.perf_counter()
    prof = None
    if m.get("profile"):  # 측정용: cProfile 누적 상위 함수(앞 몇 장만)
        import cProfile

        prof = cProfile.Profile()
    items = m["items"][: int(m["limit"])] if m.get("limit") else m["items"]
    for it in items:
        imgs = []
        for p in it["images"]:
            with open(p, "rb") as f:
                imgs.append(f.read())
        t0 = time.perf_counter()
        try:
            if prof is not None:
                prof.enable()
            if it["kind"] == "overlay":  # 겹쳐 보기 시간 재기
                res, err = json.loads(overlay(imgs[0], it.get("query", {}))), None
            else:
                res, err = json.loads(observe(it["kind"], imgs, it.get("query", {}))), None
        except Exception as e:  # noqa: BLE001 — 한 장 실패가 전체를 멈추지 않게
            res, err = None, f"{type(e).__name__}: {e}"
        finally:
            if prof is not None:
                prof.disable()
        out["items"].append({"name": it["name"], "kind": it["kind"], "secs": round(time.perf_counter() - t0, 3), "err": err, "res": res})
    out["total_s"] = round(time.perf_counter() - t_all, 1)
    if prof is not None:
        import pstats

        buf = io.StringIO()
        st = pstats.Stats(prof, stream=buf)
        st.sort_stats("tottime").print_stats(40)
        st.sort_stats("cumulative").print_stats(40)
        out["profile"] = buf.getvalue()
    path = os.path.join(os.path.dirname(manifest), f"result_{m.get('tag', 'x')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return json.dumps({"path": path, "n": len(out["items"]), "total_s": out["total_s"]})


HAND_MIN = 0.8  # 진짜 손패는 자기 자리 기준 hand 0.83~0.90, 헛 손패(패산 위 표시패)는 한 자리에서만 0.63(11-11 164501·k25)


def _pick_role(per_side: dict) -> tuple[str, float, str | None]:
    """네 자리 기준 역할 답 {자리: (역할, 확신)} → (역할, 확신, 주인 자리 또는 None)."""
    best = max(((c, s) for s, (r, c) in per_side.items() if r == "hand"), default=None)
    if best is not None and best[0] >= HAND_MIN:
        return "hand", best[0], best[1]
    votes: dict = {}
    for r, c in per_side.values():
        votes[r] = votes.get(r, 0.0) + c
    role = max(votes, key=votes.get)
    # 주인 자리는 손패만 역할 모델에서(울기·짝 등은 네 자리 모두 같은 답이라 확신이 큰 자리가 주인이 아님 → 상자가 든 격자 칸으로)
    return role, votes[role] / len(per_side), None


# 역할 + 주인 모델 D(실험 5a, 2026-11-12, docs/role_owner_plan_1111.md 5단계): 요청에 role=d 가 있을 때만 쓴다. 사진 기준 토큰 1회 →
# 출력 role[1, n, 6]·owner[1, n, 4](씨드 3 평균 확률, 자리 = roles.SIDES). 파일은 ONDEVICE_ROLE_D, 없으면 서버 assets 옆.
_role_d_lock = threading.Lock()
_role_d = None


def _get_role_d():
    """roles.RoleNet 과 같은 세션(같은 스레드 수·옵션·잠금, 한 번 만들어 재사용)."""
    global _role_d
    with _role_d_lock:
        if _role_d is None:
            import os
            from pathlib import Path

            from app import roles

            _role_d = roles.RoleNet(Path(os.environ.get("ONDEVICE_ROLE_D") or Path(roles.__file__).parent / "assets" / "tile-roles-owner-d.onnx"))
        return _role_d


def overlay(image, query) -> str:
    """판 중 미리보기 겹쳐 보기(실험, 2026-11-11): 사진 전체의 앞면 패마다 상자·패 종류·역할을 낸다. 답에는 안 쓰는 표시용.

    검출 = 서버 화료 판독과 같은 사진 전체 회전 상자(`reader.detect_full`). 종류 = 상자 모양에 맞는 방향 중 확신이 가장 높은 것
    (`read_any2` 와 같은 규칙, 강·다른 자리 패는 뒤집혀 놓여서). 역할 = 역할 모델을 네 자리 기준으로(그 자리를 아래로 돌려) 한 번씩 돌리고
    상자마다 [_pick_role] 로 고른다(어느 자리든 hand 확신이 [HAND_MIN] 이상이면 그 자리 손패, 아니면 네 답을 확신도로 더한 투표).
    처음엔 상자가 든 격자 칸의 자리 답을 썼는데, 가운데 칸에 걸친 손패가 wall, 패산 위 표시패가 hand 로 나왔다(metrics 표 4-1, 11-11).
    좌표는 0~1(사진 너비·높이 비율).
    query role=d(실험 5a)면 역할 단계만 D 모델 1회(역할 + 주인 자리)로 바꾼다. 출력 모양·ms 칸은 같다(ms.roles = 같은 구간, 모델 1회).
    """
    from app import local_read as lr
    from app import obb, roles

    t0 = time.perf_counter()
    q = {str(k): str(v) for k, v in dict(query).items()}
    use_d = q.get("role") == "d"  # 역할 + 주인 모델 D 1회(실험 5a). 없거나 다른 값이면 지금 그대로(4회 + _pick_role + side_of)
    grid = _grid(q, False) or {"x1": 280, "x2": 745, "y1": 173, "y2": 713}
    jpeg = _prepare(bytes(image), 4080)
    reader = _get_reader()
    net = roles.role_net()
    with obb.session():
        full = lr.decode_rgb(jpeg)
        H, W = full.shape[:2]
        t1 = time.perf_counter()
        boxes = reader.detect_full(jpeg, full)
        t2 = time.perf_counter()
        # 종류: 모든 상자의 후보 방향 조각을 한 번에 분류
        crops, owner = [], []
        for i, b in enumerate(boxes):
            im = lr.cut(full, b)
            ts = (0, 2) if b[3] > 1.15 * b[2] else (1, 3) if b[2] > 1.15 * b[3] else (0, 1, 2, 3)
            for k in ts:
                crops.append(im.rotate(90 * k, expand=True))
                owner.append(i)
        best: dict = {}
        for s in range(0, len(crops), 64):
            p = reader.probs(crops[s:s + 64])
            for j, row in enumerate(p):
                i = owner[s + j]
                if i not in best or row.max() > best[i].max():
                    best[i] = row
        kinds = [lr.top2(best[i]) if i in best else ("?", 0.0, None, None) for i in range(len(boxes))]
        t3 = time.perf_counter()
        # 역할: 자리마다 한 번(입력 토큰은 모든 상자), 상자가 든 자리의 답
        pts = [roles._pts_of(full, b) for b in boxes]
        backs = [(b, obb.corners(rc)) for b, rc in obb.backs_of(full)] if use_d or net.feat == roles.FEAT_ROT else []
        by_side, d_ans = {}, None
        if use_d:  # 사진 기준(side bottom) 토큰 1회 → 역할 = 역할 확률 최대(확신 = 그 확률), 주인 = 주인 확률 최대. 뒷면 토큰의 답은 버림
            d_ans = []
            if boxes:
                pr, po = _get_role_d()._session().run(["role", "owner"], {"x": roles.tokens(boxes, W, H, grid, "bottom", roles.FEAT_ROT, pts, backs)[None]})
                d_ans = [(roles.ROLES[int(pr[0][i].argmax())], round(float(pr[0][i].max()), 3), roles.SIDES[int(po[0][i].argmax())]) for i in range(len(boxes))]
        else:
            for side in roles.SIDES:
                x = roles.tokens(boxes, W, H, grid, side, net.feat, pts, backs)
                r, c = net.predict(x)
                by_side[side] = (r[: len(boxes)], c[: len(boxes)])
        t4 = time.perf_counter()

    def side_of(b) -> str:
        cx, cy = (b[0] + b[2] / 2) / W * 1000, (b[1] + b[3] / 2) / H * 1000
        for s in roles.SIDES:
            y0, x0, y1, x1 = roles.seat_box(grid, s, grow=0)
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return s
        return "center"

    out = []
    for i, b in enumerate(boxes):
        role, conf, owner = d_ans[i] if use_d else _pick_role({s: (by_side[s][0][i], float(by_side[s][1][i])) for s in roles.SIDES})
        k = kinds[i]
        out.append({"b": [round(b[0] / W, 4), round(b[1] / H, 4), round(b[2] / W, 4), round(b[3] / H, 4)], "t": k[0], "tc": round(float(k[1]), 3),
                    "r": role, "rc": round(conf, 3), "s": owner or side_of(b)})
    ms = {"decode": round((t1 - t0) * 1000), "detect": round((t2 - t1) * 1000), "classify": round((t3 - t2) * 1000),
          "roles": round((t4 - t3) * 1000), "total": round((time.perf_counter() - t0) * 1000)}
    return json.dumps({"tiles": out, "backs": len(backs), "w": W, "h": H, "ms": ms}, ensure_ascii=False, default=_plain)
