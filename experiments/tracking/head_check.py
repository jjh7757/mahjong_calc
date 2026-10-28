"""패 없이 되는 실기기 확인(설계 9절 7의 절반): 실제 폰 카메라 헤드에 붙어 해상도 게이트·스트림+촬영 공존·3초 폴링 안정성을 잰다.

  python experiments/tracking/head_check.py http://192.168.50.35:8765 --token <QR 의 t=값> [--polls 20] [--w 2000]
  (폰: 앱 더보기 → 카메라 헤드. 화면 아래 주소 글의 `?t=…` 이 토큰. USB 면 `adb forward tcp:8765 tcp:8765` 뒤 http://127.0.0.1:8765)

재는 것:
1. /status
2. /preview(기본) 5번 — 크기·시간 (테이블 화면 배경용)
3. /preview?w=W 5번 — 실제 긴 변, X-Frame-Size(줄이기 전 스트림 프레임 크기), 시간
4. /capture 1번(셔터, 12MP) → 바로 /preview 가 이어지는지(스트림 재시작 시간)
5. 3초 간격 폴링 N번 — 실패 수, 시간 분포 (추적기의 배경 폴링과 같음)
6. 해상도 게이트 어림: 촬영 사진에서 패 폭이 90cm 높이 12MP 기준 약 75px(HANDOFF) → 거치 높이별 패 폭 = 75 × 90/h,
   미리보기 패 폭 = 그 값 × (미리보기 긴 변 / 촬영 긴 변). 100px 넘는 높이가 (가) 고해상 미리보기 경로의 조건.
   집 패 없이 어림이므로, 실제 패가 있는 날 모서리 패 폭을 눈으로 재 바꾼다.
결과 JSON: experiments/tracking/results/head_check_<시각>.json
"""
from __future__ import annotations

import argparse
import io
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

OUT = Path(__file__).parent / "results"


def get(url: str, path: str, token: str, timeout: float = 20) -> tuple[requests.Response, float]:
    t0 = time.perf_counter()
    r = requests.get(url + path, headers={"X-Head-Token": token}, timeout=timeout)
    return r, time.perf_counter() - t0


def size_of(r: requests.Response) -> tuple[int, int]:
    return Image.open(io.BytesIO(r.content)).size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--token", default="")
    ap.add_argument("--polls", type=int, default=20)
    ap.add_argument("--w", type=int, default=2000)
    a = ap.parse_args()
    url = a.url.rstrip("/")
    res: dict = {"url": url, "when": datetime.now().isoformat(timespec="seconds")}

    r, dt = get(url, "/status", a.token)
    print(f"/status {r.status_code} {dt:.2f}s {r.text[:200]}")
    res["status"] = {"code": r.status_code, "body": r.text[:500], "s": round(dt, 2)}
    if r.status_code == 401:
        print("토큰이 틀림 — 헤드 화면의 ?t= 값을 --token 으로")
        return

    def previews(path: str, n: int, label: str) -> dict:
        rows = []
        for _ in range(n):
            r, dt = get(url, path, a.token)
            if r.status_code != 200:
                rows.append({"code": r.status_code, "s": round(dt, 2)})
                continue
            rows.append({"code": 200, "s": round(dt, 2), "size": size_of(r), "bytes": len(r.content),
                         "frame": r.headers.get("X-Frame-Size")})
        ok = [x for x in rows if x["code"] == 200]
        print(f"{label}: {len(ok)}/{n} 성공, 크기 {ok[0]['size'] if ok else None}, 스트림 프레임 {ok[0]['frame'] if ok else None}, "
              f"시간 중앙 {statistics.median(x['s'] for x in rows):.2f}s 최대 {max(x['s'] for x in rows):.2f}s, "
              f"{statistics.median(x['bytes'] for x in ok) / 1024 if ok else 0:.0f}KB")
        return {"rows": rows}

    res["preview_default"] = previews("/preview", 5, "/preview 기본")
    res["preview_w"] = previews(f"/preview?w={a.w}", 5, f"/preview?w={a.w}")

    r, dt = get(url, "/capture", a.token, timeout=60)
    cap = {"code": r.status_code, "s": round(dt, 2)}
    if r.status_code == 200:
        cap.update(size=size_of(r), bytes=len(r.content))
        OUT.mkdir(exist_ok=True)
        (OUT / "last_capture.jpg").write_bytes(r.content)
    print(f"/capture {cap}")
    res["capture"] = cap
    # 촬영 직후 미리보기가 다시 오는지(스트림 재시작): 실패하면 0.5초 쉬고 다시, 최대 10초
    t0 = time.perf_counter()
    back = None
    while time.perf_counter() - t0 < 10:
        try:
            r, dt = get(url, "/preview", a.token, timeout=5)
            if r.status_code == 200:
                back = round(time.perf_counter() - t0, 2)
                break
        except requests.RequestException:
            pass
        time.sleep(0.5)
    print(f"촬영 뒤 미리보기 복귀: {back}s" if back is not None else "촬영 뒤 10초 안에 미리보기 안 옴")
    res["preview_after_capture_s"] = back

    polls = []
    for i in range(a.polls):
        t0 = time.perf_counter()
        try:
            r, dt = get(url, f"/preview?w={a.w}", a.token, timeout=10)
            polls.append({"code": r.status_code, "s": round(dt, 2)})
        except requests.RequestException as e:
            polls.append({"code": 0, "s": round(time.perf_counter() - t0, 2), "error": type(e).__name__})
        time.sleep(max(0.0, 3 - (time.perf_counter() - t0)))
    ok = [p["s"] for p in polls if p["code"] == 200]
    print(f"3초 폴링 {a.polls}번: 성공 {len(ok)}, 시간 중앙 {statistics.median(ok) if ok else 0:.2f}s 최대 {max(ok) if ok else 0:.2f}s")
    res["polls"] = polls

    # 해상도 게이트 어림
    pw = next((x for x in res["preview_w"]["rows"] if x["code"] == 200), None)
    if pw and cap.get("size"):
        plong, clong = max(pw["size"]), max(cap["size"])
        flong = max(int(v) for v in pw["frame"].split("x")) if pw.get("frame") else None
        gate = {"preview_long": plong, "stream_frame_long": flong, "capture_long": clong}
        print(f"미리보기 긴 변 {plong}px (스트림 프레임 {flong}), 촬영 긴 변 {clong}px -> 비율 {plong / clong:.2f}")
        for h in (60, 75, 90):
            tile_cap = 75 * 90 / h
            tile_prev = tile_cap * plong / clong
            gate[f"tile_px_{h}cm"] = {"capture": round(tile_cap), "preview": round(tile_prev)}
            print(f"  거치 {h}cm: 촬영 패 폭 약 {tile_cap:.0f}px, 미리보기 패 폭 약 {tile_prev:.0f}px "
                  f"{'-> (가) 고해상 미리보기 가능' if tile_prev >= 100 else '-> (나) 촬영 한 장 필요'}")
        res["gate"] = gate

    OUT.mkdir(exist_ok=True)
    p = OUT / f"head_check_{datetime.now():%Y%m%d_%H%M%S}.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장", p)


if __name__ == "__main__":
    main()
