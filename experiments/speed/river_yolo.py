"""강 끝 위치를 공개 YOLO26 패 면 검출(HaseLab tile-yolo-26n, 학습 없이 CPU)로: 검출 상자 → river_px 와 같은 규칙으로
그 사람 강 묶기 → 줄 묶기 → 마지막 줄 오른쪽 끝. 패 종류는 쓰지 않는다(위치만). 라이선스 미확인이라 로컬 실험만(2026-10-26).

  python experiments/speed/river_yolo.py [locate|read] [--model haselab|nikmomo-s|nikmomo-m]   그림 results/river_yolo[_모델]/
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
import bench as b  # noqa: E402
import last3 as l3  # noqa: E402
import river_px as px  # noqa: E402

W = Path("C:/Users/jjh7757/dev/_downloads")
RIVERS: dict = {}  # (사진, 자리) → 그 사람 강 상자(줄마다, 위 → 아래)
OUT = ROOT / "results" / "river_yolo"


def main() -> None:
    from ultralytics import YOLO

    a = ARGS
    OUT.mkdir(parents=True, exist_ok=True)
    if a.model == "haselab":
        tile = YOLO(str(W / "haselab" / "tile-yolo-26n.pt"))
    else:  # nikmomo/Mahjong-YOLO(YOLO11 s·m 검출, MIT 저장소 — ultralytics 는 AGPL), 손패 사진으로 학습
        tile = YOLO(str(W / "nikmomo" / f"mahjong-yolo{a.model[-1]}-best.onnx"), task="detect")
    picks, ok, secs = [], 0, []
    for scene, photos in l3.PHOTOS.items():
        for photo in photos:
            for side in l3.TRUTH[scene]:
                img = cv2.imread(str(b.G / scene / photo / f"last_{side}.jpg"))
                H, Wd = img.shape[:2]
                t0 = time.perf_counter()
                if a.model == "haselab":
                    r = tile.predict(img, conf=a.conf, imgsz=a.imgsz, verbose=False, retina_masks=True)[0]
                    raw = [cv2.boundingRect(p.astype(np.float32)) for p in (r.masks.xy if r.masks is not None else [])
                           if len(p) >= 4]
                else:
                    r = tile.predict(img, conf=a.conf, imgsz=a.imgsz, verbose=False)[0]
                    raw = [(x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1 in r.boxes.xyxy.numpy()]
                secs.append(time.perf_counter() - t0)
                boxes = []
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                white = (hsv[..., 1] < 50) & (hsv[..., 2] > 140)
                for x, y, w, h in raw:
                    x, y = max(0, int(x)), max(0, int(y))
                    # 빈 펠트·기계 위 가짜 상자 거르기: 패 면이면 상자 안 대부분이 흰색
                    if white[y:y + int(h), x:x + int(w)].mean() < a.white:
                        continue
                    boxes.append((x, y, int(w), int(h)))
                boxes = dedupe(boxes)
                got = px.own_river(boxes, Wd, H)
                rows, last = [], None
                if got:
                    group, tw, th = got
                    rows = px.frame(group, th)
                    last = rows[-1][-1]
                    own = own_rows(rows, tw, th)
                    RIVERS[(photo, side)] = {"rows": [[list(map(int, b)) for b in r] for r in own], "tw": tw, "th": th}
                    (OUT / "sheets").mkdir(exist_ok=True)
                    cv2.imwrite(str(OUT / "sheets" / f"{photo}_{side}.jpg"),
                                river_sheet(img, own, f"{photo} {side}  rows {[len(r) for r in own]}"))
                vis = img.copy()
                for bx in boxes:
                    cv2.rectangle(vis, (bx[0], bx[1]), (bx[0] + bx[2], bx[1] + bx[3]), (160, 160, 160), 2)
                for ri, row in enumerate(rows):
                    for ci, bx in enumerate(row):
                        cv2.rectangle(vis, (bx[0], bx[1]), (bx[0] + bx[2], bx[1] + bx[3]), (255, 140, 0), 3)
                        cv2.putText(vis, f"{ri}.{ci}", (bx[0] + 4, bx[1] + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 255), 2)
                if last:
                    cv2.rectangle(vis, (last[0], last[1]), (last[0] + last[2], last[1] + last[3]), (0, 0, 255), 6)
                cv2.imwrite(str(OUT / f"{photo}_{side}.jpg"), vis)
                # 고른 패 조각(눈으로 정답과 비교)
                t = np.full((200, 170, 3), 255, np.uint8)
                if last:
                    x, y, w, h = last
                    c = img[max(0, y):y + h, max(0, x):x + w]
                    c = cv2.resize(c, (min(170, max(1, int(c.shape[1] * 150 / c.shape[0]))), 150))
                    t[:150, :c.shape[1]] = c
                cv2.putText(t, f"{photo[:3]} {side[:3]}", (4, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                cv2.putText(t, f"truth {l3.TRUTH[scene][side]}", (4, 192), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 200), 2)
                picks.append(t)
                if last:  # 읽기 단계용 조각(조금 넉넉히)
                    (OUT / "tiles").mkdir(exist_ok=True)
                    (OUT / "tiles" / f"{photo}_{side}.jpg").write_bytes(px.crop_tile(img, last))
                print(f"{scene} {photo} {side:6s} 검출 {len(boxes):2d}  강 {sum(len(r) for r in rows):2d}장  줄 {[len(r) for r in rows]}  정답 {l3.TRUTH[scene][side]}")
    cv2.imwrite(str(OUT / "last_picks.jpg"), np.vstack([np.hstack(picks[i:i + 9]) for i in range(0, 18, 9)]))
    import json
    (OUT / "rivers.json").write_text(json.dumps({f"{p}_{s}": v for (p, s), v in RIVERS.items()}, indent=1), encoding="utf-8")
    for (p, s), v in RIVERS.items():
        print(f"  내 강 {p} {s:6s} 줄 {[len(r) for r in v['rows']]}  가로 {[ri for ri, r in enumerate(v['rows']) for b in r if b[2] > 1.15 * b[3]]}")
    print(f"검출 시간 중앙 {sorted(secs)[len(secs) // 2]:.2f}초 (CPU)")


def dedupe(boxes):
    """같은 패에 겹친 상자(작은 쪽의 70% 이상이 겹침)는 큰 상자 하나만 남긴다."""
    keep = []
    for b in sorted(boxes, key=lambda b: -b[2] * b[3]):
        ok = True
        for k in keep:
            ix = max(0, min(b[0] + b[2], k[0] + k[2]) - max(b[0], k[0]))
            iy = max(0, min(b[1] + b[3], k[1] + k[3]) - max(b[1], k[1]))
            if ix * iy > 0.7 * min(b[2] * b[3], k[2] * k[3]):
                ok = False
                break
        if ok:
            keep.append(b)
    return keep


def own_rows(rows, tw: float, th: float):
    """줄 묶음(위 → 아래)에서 그 사람 강만: 맨 아래 줄부터 위로 올라가며, 지금까지 모은 강의 왼쪽 끝 L 에서
    [L - 0.3패, L + 6.5패] 안에 가운데가 있는 패만 남긴다. 강은 앞 줄을 6장 채워야 다음 줄로 가므로 **마지막 줄이 아닌 줄은 6장**
    (검출 누락 하나를 봐 5~6장)이어야 하고, 아니면 멈춘다. 줄 사이가 패 높이 반 넘게 벌어져도 멈춘다.
    맨 아래 줄은 6장을 넘어도 된다(셋째 줄을 계속 잇는 매장이 있다). 돌려주는 값은 위(테이블 가운데 쪽) → 아래."""
    if not rows:
        return []
    acc = [rows[-1]]
    left = min(b[0] for b in rows[-1])
    for row in reversed(rows[:-1]):
        keep = [b for b in row if left - 0.3 * tw <= b[0] + b[2] / 2 <= left + 6.5 * tw]
        if not 5 <= len(keep) <= 6:
            break
        top_prev = min(b[1] for b in acc[-1])
        bottom = max(b[1] + b[3] for b in keep)
        if top_prev - bottom > 0.5 * th:
            break
        acc.append(sorted(keep, key=lambda b: b[0]))
        left = min(left, min(b[0] for b in keep))
    return list(reversed(acc))


def river_sheet(img, rows, title: str):
    """찾은 강 패를 순서대로(줄마다 한 줄) 번호와 함께 붙인 확인용 그림. 가로 패는 * 표시."""
    cells = []
    for ri, row in enumerate(rows):
        line = []
        for ci, (x, y, w, h) in enumerate(row):
            c = img[max(0, y):y + h, max(0, x):x + w]
            c = cv2.resize(c, (max(1, int(c.shape[1] * 110 / max(1, c.shape[0]))), 110))
            cell = np.full((140, 150, 3), 255, np.uint8)
            cell[:110, :min(150, c.shape[1])] = c[:, :150]
            mark = "*" if w > 1.15 * h else ""
            cv2.putText(cell, f"{ri}.{ci}{mark}", (4, 133), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 200), 2)
            line.append(cell)
        while len(line) < 7:
            line.append(np.full((140, 150, 3), 230, np.uint8))
        cells.append(np.hstack(line[:7]))
    head = np.full((30, 150 * 7, 3), 255, np.uint8)
    cv2.putText(head, title, (5, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
    return np.vstack([head, *cells]) if cells else head


READ_PROMPT = """사진 {n}장은 각각 리치마작 패 한 장을 위에서 찍은 것입니다(버림패 줄에서 잘라 냄, 가장자리에 이웃 패가 조금 걸릴 수 있음).
사진마다 가운데에 온전히 보이는 패 한 장의 종류를 적습니다.

- {keys}: 첫째부터 순서대로 그 사진 패의 code 와 확신도.

{notation}

마지막 사진은 이 패 세트의 통수(1p~9p)·삭수(1s~9s) 실물 참고표입니다(이름표가 위에 있음). 통수·삭수는 참고표와 무늬 개수·배치를 비교해 정합니다.
참고표는 답에 넣지 않습니다."""


def read(runs: int, workers: int) -> None:
    """main() 이 잘라 둔 마지막 패 조각을 장면마다 한 호출(조각 3장 + 참고표)로 읽는다. 결과 results/river_yolo_read.json."""
    import json
    import statistics
    from concurrent.futures import ThreadPoolExecutor

    ob = b.ob
    per = {"type": "object", "properties": {"tile": ob.LAST_SCHEMA_V2["properties"]["last_tile"]}, "required": ["tile"]}

    def one(job):
        run_i, scene, photo = job
        sides = list(l3.TRUTH[scene])
        datas = [(OUT / "tiles" / f"{photo}_{s}.jpg").read_bytes() for s in sides]
        n = len(sides)
        keys = [f"photo{i + 1}" for i in range(n)]
        schema = {"type": "object", "properties": {**{k: per for k in keys}, "notes": {"type": "string"}}, "required": keys}
        prompt = READ_PROMPT.format(n=n, keys=", ".join(keys), notation=ob.NOTATION)
        r = b.call(datas[0], prompt, schema, l3.MODEL, "low", None,
                   extra=[b.image_part(d, None) for d in datas[1:]] + [b.image_part(b.ref_sheet_set2(), None)])
        tiles = {s: (l3.code((r["data"].get(k) or {}).get("tile")) if "data" in r else "ERR") for s, k in zip(sides, keys)}
        ok = {s: tiles[s] == l3.TRUTH[scene][s] for s in sides}
        print(f"{scene} {photo} #{run_i} {r['s']:5.1f}s {sum(ok.values())}/3 {tiles}", flush=True)
        return {"run": run_i, "scene": scene, "photo": photo, "wall": r["s"], "tiles": tiles, "ok": ok,
                "ron_ok": ok[l3.RON[scene]], "calls": [{k: r.get(k) for k in ("s", "in", "out", "think", "error")}]}

    jobs = [(r, s, p) for r in range(runs) for s, ps in l3.PHOTOS.items() for p in ps]
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, jobs))
    (OUT.parent / f"{OUT.name}_read.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    w = sorted(r["wall"] for r in rows)
    print(f"\n장면 {len(rows)}  세 자리 모두 {sum(all(r['ok'].values()) for r in rows)}  론 패 {sum(r['ron_ok'] for r in rows)}  "
          f"자리별 {sum(sum(r['ok'].values()) for r in rows)}/{3 * len(rows)}  시간 중앙 {statistics.median(w):.1f} / p90 {w[int(.9 * len(w))]:.1f} / 최대 {w[-1]:.1f}  "
          f"입력 {statistics.median(r['calls'][0]['in'] or 0 for r in rows):.0f}  생각>0 {sum((r['calls'][0]['think'] or 0) > 0 for r in rows)}")
    for r in rows:
        for s, good in r["ok"].items():
            if not good:
                print(f"  틀림 {r['photo']} {s}: {r['tiles'][s]} → {l3.TRUTH[r['scene']][s]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="locate", choices=["locate", "read"])
    ap.add_argument("--model", default="haselab", choices=["haselab", "nikmomo-s", "nikmomo-m"])
    ap.add_argument("--imgsz", type=int, default=0, help="0 이면 모델 기본(haselab 1024, nikmomo 640)")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--white", type=float, default=0.5, help="상자 안 흰 픽셀 비율이 이보다 낮으면 버림")
    ap.add_argument("--runs", type=int, default=10)
    ARGS = ap.parse_args()
    ARGS.imgsz = ARGS.imgsz or (1024 if ARGS.model == "haselab" else 640)
    if ARGS.model != "haselab":
        OUT = ROOT / "results" / f"river_yolo_{ARGS.model}"
    if ARGS.mode == "read":
        read(ARGS.runs, 6)
    else:
        main()
