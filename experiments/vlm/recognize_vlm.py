"""비전 LLM(Claude / Gemini)으로 마작 손패 사진을 인식하는 실험.

사용법:
    python recognize_vlm.py <이미지 폴더> --models gemini-pro-latest,claude-opus-5-5 [--effort high] [--env-file .env]

- 모델 이름이 `gemini` 로 시작하면 Google Gemini, `claude` 로 시작하면 Anthropic Claude 를 호출한다.
- 키는 환경 변수(GEMINI_API_KEY / GOOGLE_API_KEY, ANTHROPIC_API_KEY) 또는 --env-file 의 .env 에서 읽는다.
- 폴더 안에 labels.json 이 있으면 정답과 비교해 정확도를 낸다.
    {"hand1.jpg": "123m456p789s11z22z 3z", ...}   (공백 허용)

결과는 results/<timestamp>.json 과 results/<timestamp>.md 에 남긴다.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from PIL import Image

# 2026-10 기준 1M 토큰당 달러 (입력, 출력). 모르는 모델은 None.
PRICES: dict[str, tuple[float, float] | None] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50),
}

TILE_CODES = (
    [f"{n}m" for n in range(1, 10)]
    + [f"{n}p" for n in range(1, 10)]
    + [f"{n}s" for n in range(1, 10)]
    + [f"{n}z" for n in range(1, 8)]
    + ["0m", "0p", "0s"]
)

SCHEMA = {
    "type": "object",
    "properties": {
        "tiles": {
            "type": "array",
            "description": "사진에 보이는 패를 왼쪽에서 오른쪽 순서로",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": TILE_CODES},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["code", "confidence"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string", "description": "가려짐, 흐림 등 특이사항. 없으면 빈 문자열"},
    },
    "required": ["tiles", "notes"],
    "additionalProperties": False,
}

# Gemini 의 response_schema 는 additionalProperties / minimum / maximum 을 받지 않는다.
GEMINI_SCHEMA = {
    "type": "object",
    "properties": {
        "tiles": {
            "type": "array",
            "description": "사진에 보이는 패를 왼쪽에서 오른쪽 순서로",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": TILE_CODES},
                    "confidence": {"type": "number", "description": "0~1 확신도"},
                },
                "required": ["code", "confidence"],
            },
        },
        "notes": {"type": "string", "description": "가려짐, 흐림 등 특이사항. 없으면 빈 문자열"},
    },
    "required": ["tiles", "notes"],
}

PROMPT = """이 사진은 리치마작(일본식 마작) 패를 찍은 것입니다. 사진에 보이는 패를 전부, 왼쪽에서 오른쪽 순서로 읽어 주세요.

표기법:
- 만수(萬): 1m~9m. 한자 숫자(一二三四五六七八九) 위에 萬 이 있는 패.
- 통수(筒): 1p~9p. 동그라미 개수.
- 삭수(索): 1s~9s. 대나무 막대 개수. 1s 는 새 그림.
- 자패: 동 1z, 남 2z, 서 3z, 북 4z, 백(빈 패 또는 테두리만) 5z, 발(綠 發) 6z, 중(붉은 中) 7z.
- 적도라(붉은 5): 0m, 0p, 0s. 5인데 전체가 붉게 그려진 패만 해당합니다.

주의:
- 세로로 눕히거나 뒤집힌 패는 없다고 가정하고 읽습니다.
- 같은 패가 여러 장이면 장수만큼 반복해 적습니다.
- 각 패마다 확신도(0~1)를 적어 주세요. 헷갈리는 패는 낮게 주세요.
- 보이는 패 수를 먼저 세고, 그 수만큼 정확히 나열하세요."""


# ---------- 입력 준비 ----------

def load_image(path: Path, max_side: int = 1568) -> bytes:
    """긴 변 1568px 이하로 줄인 JPEG 바이트."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def parse_label(text: str) -> list[str]:
    out: list[str] = []
    for digits, suit in re.findall(r"(\d+)([mpsz])", text.replace(" ", "")):
        for d in digits:
            out.append(f"{d}{suit}")
    return out


def read_env_key(env_file: Path | None, *names: str) -> str | None:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    if env_file and env_file.exists():
        text = env_file.read_text(encoding="utf-8")
        for n in names:
            m = re.search(rf'^\s*{n}\s*=\s*"?([^"\r\n]+)"?', text, re.M)
            if m:
                return m.group(1).strip()
    return None


# ---------- 채점 ----------

def normalize(code: str) -> str:
    return "5" + code[1] if code[0] == "0" else code


def score(pred: list[str], truth: list[str]) -> dict:
    p = Counter(normalize(c) for c in pred)
    t = Counter(normalize(c) for c in truth)
    matched = sum((p & t).values())
    exact = [normalize(c) for c in pred] == [normalize(c) for c in truth]
    red_pred = sum(1 for c in pred if c[0] == "0")
    red_truth = sum(1 for c in truth if c[0] == "0")
    return {
        "truth_count": len(truth),
        "pred_count": len(pred),
        "matched": matched,
        "tile_accuracy": matched / len(truth) if truth else None,
        "all_correct": matched == len(truth) == len(pred),
        "order_exact": exact,
        "red_ok": red_pred == red_truth,
    }


def cost_of(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1e6, 5)


# ---------- Claude ----------

def recognize_claude(client, model: str, image: bytes, effort: str, use_fallbacks: bool) -> dict:
    kwargs: dict = dict(
        model=model,
        max_tokens=4000,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(image).decode("ascii")}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    t0 = time.perf_counter()
    if use_fallbacks:
        response = client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    else:
        response = client.messages.create(**kwargs)
    latency = time.perf_counter() - t0
    u = response.usage
    usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
             "cost_usd": cost_of(model, u.input_tokens, u.output_tokens)}
    if response.stop_reason == "refusal":
        return {"error": "refusal", "latency_s": latency, "usage": usage}
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return {"tiles": [t["code"] for t in data["tiles"]],
            "confidence": [t["confidence"] for t in data["tiles"]],
            "notes": data.get("notes", ""), "latency_s": latency, "usage": usage,
            "served_by": response.model}


# ---------- Gemini ----------

def recognize_gemini(client, model: str, image: bytes) -> dict:
    from google.genai import types

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=GEMINI_SCHEMA,
    )
    t0 = time.perf_counter()
    response = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=image, mime_type="image/jpeg"), PROMPT],
        config=config,
    )
    latency = time.perf_counter() - t0
    um = response.usage_metadata
    inp = um.prompt_token_count or 0
    out = (um.candidates_token_count or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
    usage = {"input_tokens": inp, "output_tokens": out, "cost_usd": cost_of(model, inp, out)}
    if not response.text:
        return {"error": f"empty response ({response.candidates[0].finish_reason if response.candidates else 'no candidates'})",
                "latency_s": latency, "usage": usage}
    data = json.loads(response.text)
    tiles = [t["code"] for t in data["tiles"]]
    bad = [c for c in tiles if c not in TILE_CODES]
    return {"tiles": tiles, "confidence": [t.get("confidence") for t in data["tiles"]],
            "notes": data.get("notes", "") + (f" [잘못된 코드: {bad}]" if bad else ""),
            "latency_s": latency, "usage": usage, "served_by": model}


# ---------- 실행 ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--models", default="gemini-pro-latest")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"],
                    help="Claude 전용")
    ap.add_argument("--no-fallbacks", action="store_true", help="Claude server-side fallbacks 끄기")
    ap.add_argument("--env-file", type=Path, default=None, help="키를 읽을 .env 파일")
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N장만")
    args = ap.parse_args()

    folder: Path = args.folder
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
    if args.limit:
        images = images[: args.limit]
    if not images:
        print(f"이미지가 없습니다: {folder}", file=sys.stderr)
        return 1
    labels_path = folder / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    claude_client = None
    gemini_client = None
    if any(m.startswith("claude") for m in models):
        import anthropic
        key = read_env_key(args.env_file, "ANTHROPIC_API_KEY")
        claude_client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        if claude_client.api_key is None and claude_client.auth_token is None:
            print("ANTHROPIC_API_KEY 가 없습니다.", file=sys.stderr)
            return 2
    if any(m.startswith("gemini") for m in models):
        from google import genai
        key = read_env_key(args.env_file, "GEMINI_API_KEY", "GOOGLE_API_KEY")
        if not key:
            print("GEMINI_API_KEY 가 없습니다.", file=sys.stderr)
            return 2
        gemini_client = genai.Client(api_key=key)

    results: list[dict] = []
    for img_path in images:
        image = load_image(img_path)
        truth = parse_label(labels[img_path.name]) if img_path.name in labels else None
        for model in models:
            print(f"[{model}] {img_path.name} ...", end=" ", flush=True)
            try:
                if model.startswith("claude"):
                    r = recognize_claude(claude_client, model, image, args.effort, not args.no_fallbacks)
                else:
                    r = recognize_gemini(gemini_client, model, image)
            except Exception as e:  # noqa: BLE001 - 실험 스크립트: 어떤 오류든 기록하고 계속
                r = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
            row = {"image": img_path.name, "model": model, **r}
            if truth is not None and "tiles" in r:
                row["truth"] = truth
                row["score"] = score(r["tiles"], truth)
            results.append(row)
            if "error" in r:
                print(r["error"])
            else:
                s = row.get("score")
                acc = f" acc={s['tile_accuracy']:.0%} all={s['all_correct']}" if s else ""
                cost = r["usage"]["cost_usd"]
                cost_s = f"${cost}" if cost is not None else f"{r['usage']['input_tokens']}+{r['usage']['output_tokens']}tok"
                print(f"{len(r['tiles'])}장 {r['latency_s']:.1f}s {cost_s}{acc}")
                print("    pred ", " ".join(r["tiles"]))
                if truth is not None:
                    print("    truth", " ".join(truth))

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (out_dir / f"{stamp}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md = summary_md(results, models)
    (out_dir / f"{stamp}.md").write_text(md, encoding="utf-8")
    print(f"\n결과: {out_dir / (stamp + '.md')}")
    print(md)
    return 0


def summary_md(results: list[dict], models: list[str]) -> str:
    lines = ["| 모델 | 사진 수 | 패 단위 정확도 | 전부 맞음 | 순서까지 맞음 | 적도라 맞음 | 평균 지연(s) | 사진당 비용($) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for model in models:
        rows = [r for r in results if r["model"] == model and "tiles" in r]
        scored = [r for r in rows if "score" in r]
        if not rows:
            lines.append(f"| {model} | 0 | - | - | - | - | - | - |")
            continue
        lat = sum(r["latency_s"] for r in rows) / len(rows)
        costs = [r["usage"]["cost_usd"] for r in rows if r["usage"]["cost_usd"] is not None]
        cost_s = f"{sum(costs) / len(costs):.4f}" if costs else "?"
        if scored:
            total_truth = sum(r["score"]["truth_count"] for r in scored)
            matched = sum(r["score"]["matched"] for r in scored)
            all_ok = sum(1 for r in scored if r["score"]["all_correct"])
            order_ok = sum(1 for r in scored if r["score"]["order_exact"])
            red_ok = sum(1 for r in scored if r["score"]["red_ok"])
            lines.append(f"| {model} | {len(rows)} | {matched / total_truth:.1%} ({matched}/{total_truth}) | {all_ok}/{len(scored)} | {order_ok}/{len(scored)} | {red_ok}/{len(scored)} | {lat:.1f} | {cost_s} |")
        else:
            lines.append(f"| {model} | {len(rows)} | (정답 없음) | - | - | - | {lat:.1f} | {cost_s} |")
    errors = [r for r in results if "error" in r]
    if errors:
        lines.append("")
        lines.append("오류: " + "; ".join(f"{r['model']}/{r['image']}: {r['error']}" for r in errors))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
