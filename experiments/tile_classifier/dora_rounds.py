"""판 중 프레임으로 도라 표시패를 확정하는 추적기 시연(2026-11-03, API 없음). metrics 표 1-53.

10-31 매장 추적 프레임(1020×764, 2,094장)을 시각순으로 넣고, 화료 기록 시각마다 "그때 확정돼 있던 표시패" 를 `truth.json`
(없으면 label.json 의 기록 표시패)와 대조한다. 표 1-34 는 위치만 봤고, 여기서는 종류까지 프레임 여러 장의 투표로 정한다.
앱 `lib/table/dora_tracker.dart` 와 같은 규칙이어야 한다(규칙을 바꾸면 둘 다).

규칙(프레임 1장 → 관측 1개):
  관측 = 서버 read_wall 규칙의 1순위 상자(옆에 패 뒷면이 붙은 앞면 패) + 그 상자를 키워 읽은 분류기 확률.
  위치 묶음 = 가운데가 패 1.5장 안이면 같은 묶음. 확정 = 지금 묶음의 최근 5개 관측 중 3개 이상이 한 종류이고 확률 합이 60% 이상.
  지금 묶음 = 마지막 관측이 든 묶음(관측 3개 미만이면 바로 전 확정을 유지). 같은 자리에서 종류가 바뀌면 최근 5개 창이 바꿔 준다.

  python -I -X utf8 experiments/tile_classifier/dora_rounds.py [--size 96] [--limit N]
결과 data/dora_rounds/online.json
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wall_frames as wf  # noqa: E402
import wall_frames_read as wfr  # noqa: E402
from app import local_read as lr  # noqa: E402

OUT = HERE / "data" / "dora_rounds"
TRUTH = json.loads((wf.ROOT / "experiments/visit_20261031/truth.json").read_text(encoding="utf-8"))["scenes"]

WINDOW, MIN_READS, MIN_SHARE, SAME_POS, RECENT, MIN_CONF = 5, 3, 0.6, 1.5, 20, 0.7  # MIN_CONF = 서버 WALL_CONF(이보다 낮은 읽기는 관측이 아님)


class DoraTracker:
    """앱 DoraTracker 와 같은 규칙(순수 계산)."""

    def __init__(self):
        self.clusters: list[dict] = []
        self.current: dict | None = None
        self.n = 0
        self.stale: tuple | None = None  # 전판 확정(위치·종류): 기록 직후 아직 남은 전판 패산은 관측이 아니다

    def observe(self, cx: float, cy: float, tw: float, tile: str, conf: float, at: str) -> None:
        if self.stale and abs(self.stale[0] - cx) <= SAME_POS * tw and abs(self.stale[1] - cy) <= SAME_POS * tw and self.stale[2] == tile:
            return
        c = next((k for k in self.clusters if abs(k["cx"] - cx) <= SAME_POS * tw and abs(k["cy"] - cy) <= SAME_POS * tw), None)
        if c is None:
            c = dict(cx=cx, cy=cy, reads=[], seq=[], first=at, last_n=0)
            self.clusters.append(c)
        c["seq"].append((tile, self.n + 1))
        c["reads"].append((tile, conf, at))
        c["cx"], c["cy"] = (c["cx"] * 0.8 + cx * 0.2), (c["cy"] * 0.8 + cy * 0.2)
        self.n += 1
        c["last_n"] = self.n
        # 지금 묶음 = 최근 RECENT 관측 안에서 가장 많이 본 묶음(같으면 최근 것). 화료 순간 탁자에 내놓은 표시패 짝(관측 몇 개)이
        # 판 내내 본 패산 표시패를 밀어내지 않고, 기록 없이 판이 바뀌어 옛 패산이 사라지면 새 묶음이 이긴다.
        best = max(self.clusters, key=lambda k: (sum(1 for *_, n in k["seq"] if n > self.n - RECENT), k["last_n"]))
        if sum(1 for *_, n in best["seq"] if n > self.n - RECENT) >= MIN_READS:
            self.current = best

    def confirmed(self) -> tuple[str, float, int, str] | None:
        """(종류, 확률 몫, 관측 수, 확정 시각) 또는 None."""
        c = self.current
        if c is None:
            return None
        recent = c["reads"][-WINDOW:]
        votes = collections.Counter()
        for t, p, _ in recent:
            votes[t] += p
        tile, w = votes.most_common(1)[0]
        n = sum(1 for t, _, _ in recent if t == tile)
        share = w / sum(votes.values())
        if n >= MIN_READS and share >= MIN_SHARE:
            at = [a for t, _, a in c["reads"] if t == tile][min(MIN_READS, n) - 1]
            return tile, round(share, 3), n, at
        return None

    def reset(self):
        got = self.confirmed()
        self.stale = (self.current["cx"], self.current["cy"], got[0]) if got and self.current else None
        self.clusters, self.current, self.n = [], None, 0


def captures() -> list[dict]:
    out = []
    for p in sorted(x for x in wf.CAPS.glob("20261031_1*") if not x.name.endswith("_track")):
        m = json.loads((p / "meta.json").read_text(encoding="utf-8"))
        t = TRUTH.get(p.name)
        if t:
            inds, src, riichi = t["indicators"], "truth", t["riichi"]
        elif (p / "label.json").exists():
            j = json.loads((p / "label.json").read_text(encoding="utf-8"))
            mg = j.get("merge") or {}
            inds, src, riichi = sorted(mg.get("dora_indicators", []) + mg.get("ura_indicators", [])) or None, "label", bool(mg.get("riichi"))
        else:
            inds, src, riichi = None, None, None
        out.append(dict(name=p.name, at=m["time"], inds=inds, src=src, riichi=riichi))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=lr.CLS_SIZE * 3 // 4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-reset", action="store_true", help="화료 기록 때 추적기를 비우지 않음")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = wf.all_frames()
    if a.limit:
        rows = rows[:a.limit]
    caps = [c for c in captures() if c["at"] >= rows[0]["at"]]
    readers = {"a": lr.LocalReader(det_model=wf.MODELS / "det_fold_a.onnx", cls_model=wf.MODELS / "cls_pm.onnx"),
               "b": lr.LocalReader(det_model=wf.MODELS / "det_fold_b.onnx", cls_model=wf.MODELS / "cls_am.onnx")}
    tr = DoraTracker()
    obs_log, results = [], []
    ci = 0
    t0 = time.time()
    n_obs = 0
    prev_cap_at = rows[0]["at"]
    for i, r in enumerate(rows):
        # 이 프레임보다 앞선 화료 기록은 그 시점의 확정값으로 채점
        while ci < len(caps) and caps[ci]["at"] <= r["at"]:
            c = caps[ci]
            got = tr.confirmed()
            frames_in = sum(1 for o in obs_log if prev_cap_at < o["at"] <= c["at"])
            res = dict(**c, confirmed=got, frames_since_prev=frames_in, prev_cap=prev_cap_at)
            if c["inds"] is not None:
                res["ok"] = bool(got and got[0] in c["inds"])
                res["wrong"] = bool(got and got[0] not in c["inds"])
            results.append(res)
            if not a.no_reset:
                tr.reset()  # 화료 기록 → 새 판(앱 _syncTrackerRound 와 같음). 10-31 오후는 실제로 기록이 없었다(가정)
            print(c["name"][-6:], c["src"], "정답", c["inds"], "리치" if c["riichi"] else "    ", "확정", got, "OK" if res.get("ok") else ("틀림" if res.get("wrong") else "없음" if got is None else "-"), flush=True)
            prev_cap_at = c["at"]
            ci += 1
        rgb = wf.load(r)
        rd = readers[wf.fold(r["at"])[0]]
        cands = wf.candidates(rgb, rd.detect(rgb))
        if cands:
            b = cands[0]["box"]
            tile, conf = wfr.read_up(rd, rgb, b, a.size)
            tw = float(min(b[2], b[3]))
            cx, cy = wf.center(b)
            obs_log.append(dict(i=i, at=r["at"], box=b, tile=tile, conf=conf, used=conf >= MIN_CONF))
            if conf >= MIN_CONF:
                tr.observe(cx, cy, tw, tile, conf, r["at"])
                n_obs += 1
            obs_log[-1]["confirmed"] = tr.confirmed()
        if i % 300 == 0:
            print("  프레임", i, "관측", n_obs, round(time.time() - t0), "초", flush=True)
    scored = [x for x in results if x["inds"] is not None]
    ok = sum(x["ok"] for x in scored)
    wrong = sum(x["wrong"] for x in scored)
    summary = dict(frames=len(rows), observations=n_obs, captures=len(results), scored=len(scored), ok=ok, wrong=wrong, none=len(scored) - ok - wrong,
                   truth_only=dict(n=sum(x["src"] == "truth" for x in scored), ok=sum(x["ok"] for x in scored if x["src"] == "truth"), wrong=sum(x["wrong"] for x in scored if x["src"] == "truth")),
                   size=a.size, rule=dict(window=WINDOW, min_reads=MIN_READS, min_share=MIN_SHARE, same_pos=SAME_POS, recent=RECENT, min_conf=MIN_CONF, reset_on_capture=not a.no_reset), seconds=round(time.time() - t0))
    print(json.dumps(summary, ensure_ascii=False))
    (OUT / "online.json").write_text(json.dumps(dict(summary=summary, results=results, observations=obs_log), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
