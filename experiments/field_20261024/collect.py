"""매장 실험(2026-10-24 이수보드카페유화) 기록 모으기.

에뮬레이터(조작 기기)의 Download/mahjong_calc 촬영 기록을 이 폴더 captures/ 로 받아 오고,
각 촬영의 서버 응답에 남은 토큰 수(usage)로 API 비용을 계산해 costs.csv 와 합계를 낸다.
usage 는 서버 2281355(2026-10-24 12:27) 배포 뒤 촬영부터 남는다. 그 전 촬영은 비용 칸이 비어 있다.
/v2(관찰 JSON) 촬영은 observation.json 의 usage 를 쓰고, 강 4개 호출은 center 칸에 더한다.

python experiments/field_20261024/collect.py [--adb emulator-5554] [--no-pull]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADB = r"C:\Users\jjh7757\dev\android-sdk\platform-tools\adb.exe"
REMOTE = "/sdcard/Download/mahjong_calc"

# Gemini 3.8 Flash, 100만 토큰당 달러 (docs/market_research.md "비용")
PRICE_IN = 0.75
PRICE_OUT = 3.75
CALLS = ["locate", "hand", "center", "wall"]


def pull(serial: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    subprocess.run([ADB, "-s", serial, "pull", REMOTE + "/.", str(dest)], check=True, env=env)


def usage_of(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    u = json.loads(path.read_text(encoding="utf-8")).get("usage") or {}
    if "input_tokens" not in u:
        return None
    return int(u["input_tokens"]), int(u.get("output_tokens", 0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default="emulator-5554")
    ap.add_argument("--no-pull", action="store_true")
    args = ap.parse_args()

    captures = HERE / "captures"
    if not args.no_pull:
        pull(args.adb, captures)

    rows = []
    total_in = total_out = 0
    for d in sorted(p for p in captures.iterdir() if p.is_dir()):
        row: dict[str, object] = {"capture": d.name}
        cin = cout = 0
        known = False
        obs = d / "observation.json"
        # /v2 촬영: 손패·강 4개·가운데·왕패 토큰이 observation.json 의 usage 에 호출별로 있다.
        obs_usage = json.loads(obs.read_text(encoding="utf-8")).get("usage", {}) if obs.exists() else {}
        for call in CALLS:
            u = usage_of(d / f"{call}.json") if call == "locate" or not obs_usage else None
            if obs_usage and call != "locate":
                parts = [v for k, v in obs_usage.items() if k == call or (call == "center" and k.startswith("river_"))]
                if parts:
                    u = (sum(p.get("input_tokens", 0) for p in parts), sum(p.get("output_tokens", 0) for p in parts))
            row[f"{call}_in"], row[f"{call}_out"] = u if u else ("", "")
            if u:
                known = True
                cin += u[0]
                cout += u[1]
        row["usd"] = round(cin * PRICE_IN / 1e6 + cout * PRICE_OUT / 1e6, 5) if known else ""
        row["labeled"] = (d / "label.json").exists()
        total_in += cin
        total_out += cout
        rows.append(row)

    out = HERE / "costs.csv"
    fields = ["capture"] + [f"{c}_{k}" for c in CALLS for k in ("in", "out")] + ["usd", "labeled"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    priced = [r for r in rows if r["usd"] != ""]
    usd = total_in * PRICE_IN / 1e6 + total_out * PRICE_OUT / 1e6
    print(f"촬영 {len(rows)}개 (비용 기록 있음 {len(priced)}개, 정답 있음 {sum(bool(r['labeled']) for r in rows)}개)")
    print(f"토큰 입력 {total_in:,} / 출력 {total_out:,} → ${usd:.4f}"
          + (f", 촬영당 평균 ${usd / len(priced):.4f}" if priced else ""))
    print(f"→ {out}")


if __name__ == "__main__":
    main()
