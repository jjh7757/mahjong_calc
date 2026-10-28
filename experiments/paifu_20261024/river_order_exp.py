"""강(버림패) 순서 판독 비교 실험. 실제 사진만, Gemini 를 직접 부른다(서버 코드의 GeminiRecognizer 재사용).

방식:
  A   지금 서버 방식: 가운데 크롭 1장 + TABLE_PROMPT, rivers 는 패 목록만
  B0  가운데 크롭 1장, 패마다 순서 번호 n·줄 row·칸 col 을 같이 출력
  B   B0 + 사진 기준으로 각 자리의 첫 줄 위치와 읽는 방향을 프롬프트에 명시
  C   강을 자리별로 잘라 돌린 뒤 지금 서버 프롬프트(번호 없음)로 읽기
  D   강을 자리별로 잘라 그 자리가 아래쪽에 오게 돌린 뒤, 번호와 함께 한 줄씩 출력
  D6  D 와 같되 크롭 여백 6%(옆 강 패가 끼어드는지)
  D7  D6 + "줄 정렬에서 튀어나오거나 방향이 다른 줄 끝 패는 다른 자리 패" 규칙

용법: python river_order_exp.py --captures <폴더> --names 20261024_115559,... --truth truth.json --out <폴더>
       [--variants A,B0,B,D] [--env-file ...] [--extra-rot 25] [--repeat 1]
Gemini 키는 --env-file 에서 GEMINI_API_KEY 를 읽는다(출력하지 않음).
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, r'C:\Users\jjh7757\dev\mahjong-recognizer')
from app.normalize import normalize_table  # noqa: E402
from app.prompts import NOTATION, TABLE_PROMPT  # noqa: E402
from app.recognizer import GeminiRecognizer  # noqa: E402
from app.schemas import TABLE_SCHEMA, TILE_CODES  # noqa: E402

SIDES = ['bottom', 'right', 'top', 'left']
ROTATE = {'bottom': 0, 'right': -90, 'top': 180, 'left': 90}
# 강 크롭 여백(상자 대비). D6 은 여백을 줄여 옆 강 패가 끼어드는지 본다.
PAD = {'C': 0.15, 'D': 0.15, 'D6': 0.06, 'D7': 0.06, 'D7p8': 0.08}

TILE_ITEM = {
    'type': 'object',
    'properties': {
        'n': {'type': 'integer', 'description': '버린 순서 번호(1부터)'},
        'row': {'type': 'integer', 'description': '몇 번째 줄(1부터, 가운데에 가장 가까운 줄이 1)'},
        'col': {'type': 'integer', 'description': '줄 안에서 몇 번째 칸(1부터, 그 플레이어 기준 왼쪽이 1)'},
        'code': {'type': 'string', 'enum': list(TILE_CODES)},
        'sideways': {'type': 'boolean', 'description': '같은 줄 이웃 패와 방향이 90도 다른 패(리치 선언패)'},
        'confidence': {'type': 'number'},
    },
    'required': ['n', 'row', 'col', 'code', 'sideways', 'confidence'],
}

NUM_SCHEMA = {
    'type': 'object',
    'properties': {
        'rivers': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'side': {'type': 'string', 'enum': SIDES},
                    'tile_count': {'type': 'integer', 'description': '그 자리 강에 보이는 패 수(먼저 센다)'},
                    'tiles': {'type': 'array', 'items': TILE_ITEM},
                },
                'required': ['side', 'tile_count', 'tiles'],
            },
        },
        'notes': {'type': 'string'},
    },
    'required': ['rivers', 'notes'],
}

ONE_SCHEMA = {
    'type': 'object',
    'properties': {
        'tile_count': {'type': 'integer', 'description': '강에 보이는 패 수(먼저 센다)'},
        'tiles': {'type': 'array', 'items': TILE_ITEM},
        'notes': {'type': 'string'},
    },
    'required': ['tile_count', 'tiles', 'notes'],
}

SIDE_NOTE = """자리는 이미지 기준입니다: bottom = 아래 변 쪽 플레이어, right = 오른쪽 변, top = 위 변, left = 왼쪽 변.
각 플레이어의 패는 그 사람이 앉은 변을 향해 놓여 있으므로 right 와 left 자리의 패는 90도, top 자리의 패는 180도 돌아가 보입니다."""

NUM_RULE = """버림패(강)는 각 플레이어가 자기 앞에 6장씩 줄을 지어 놓습니다. 첫 줄은 테이블 가운데에 가장 가까운 줄이고,
줄 안에서는 그 플레이어 기준 왼쪽부터 놓으며, 6장이 차면 플레이어 쪽(바깥쪽)으로 다음 줄을 시작합니다.
마지막 줄만 6장보다 적을 수 있습니다.

패마다 버린 순서 번호 n(1부터), 줄 번호 row(1부터, 가운데 쪽이 1), 줄 안 칸 번호 col(1부터)을 적어 주세요.
n = (row - 1) × 6 + col 이 되어야 합니다. 먼저 각 강의 패 수(tile_count)를 세고, 그 수만큼 빠짐없이 번호를 매기세요."""

DIRECTION_HINT = """사진 기준으로 하면 순서는 이렇습니다(사진이 조금 기울어 있어도 같은 원리):
- bottom: 가운데 쪽(위쪽) 줄이 1번 줄, 줄 안에서는 사진의 왼쪽 → 오른쪽.
- right: 가운데 쪽(왼쪽) 열이 1번 줄, 줄 안에서는 사진의 아래 → 위.
- top: 가운데 쪽(아래쪽) 줄이 1번 줄, 줄 안에서는 사진의 오른쪽 → 왼쪽.
- left: 가운데 쪽(오른쪽) 열이 1번 줄, 줄 안에서는 사진의 위 → 아래.
패에 그려진 글자·무늬가 그 플레이어 쪽으로 똑바로 보이도록 머릿속에서 돌려 놓고 읽으면, 줄 안의 왼쪽이 1번 칸입니다."""


def center_prompt(hint: bool) -> str:
    return f"""이 사진은 리치마작 자동탁 가운데를 위에서 찍은 것입니다. 네 플레이어의 버림패(강)를 읽어 주세요.

{SIDE_NOTE}

{NOTATION}

{NUM_RULE}

{DIRECTION_HINT if hint else ''}

주의: 손패·벽패(뒷면)·도라 표시패는 읽지 않습니다. 강이 안 보이는 자리는 생략합니다. 헷갈리는 패는 확신도를 낮게 주세요."""


ONE_PROMPT = f"""이 사진은 리치마작 한 플레이어의 버림패(강)를 위에서 찍은 것입니다. 그 플레이어는 사진 아래쪽에 앉아 있고,
테이블 가운데는 사진 위쪽입니다. 패의 글자·무늬는 대체로 똑바로 보입니다.

{NOTATION}

{NUM_RULE}

사진 기준으로는 가운데 쪽(위쪽) 줄이 1번 줄이고, 줄 안에서는 왼쪽 → 오른쪽입니다.

주의: 이 플레이어의 강만 읽습니다. 사진 가장자리에 걸친 다른 자리의 강·손패·벽패는 읽지 않습니다. 헷갈리는 패는 확신도를 낮게 주세요."""


ONE_PROMPT_ALIGN = ONE_PROMPT + """

다른 자리의 패를 섞지 않는 법:
- 이 플레이어의 강은 줄마다 왼쪽 끝이 서로 맞춰져 있습니다. 2번 줄이 있으면, 2번 줄 첫 패보다 왼쪽으로 튀어나온 패는 이 강의 패가 아닙니다(옆 자리 강의 끝 패가 붙어 있는 것).
- 이 강의 패는 모두 글자가 사진 위쪽을 향해 똑바로 놓여 있고, 리치 선언패 한 장만 옆으로 눕습니다. 줄 끝(맨 왼쪽·맨 오른쪽) 바깥에 붙은, 글자가 옆이나 거꾸로 향한 패는 다른 자리 패로 보고 빼세요.
- 사진 가장자리에서 잘린 패도 빼세요."""


def load_key(env_file: Path) -> str:
    key = ''
    for line in env_file.read_text(encoding='utf-8').splitlines():
        if line.strip().startswith('GEMINI_API_KEY='):
            v = line.split('=', 1)[1].strip().strip('"').strip("'")
            if v:
                key = v
    if not key:
        sys.exit('GEMINI_API_KEY 없음')
    return key


def jpeg(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, format='JPEG', quality=92)
    return b.getvalue()


def crop_box(img: Image.Image, box: list[int], pad: float, rot: float) -> Image.Image:
    W, H = img.size
    y0, x0, y1, x1 = box
    bw, bh = (x1 - x0) * pad, (y1 - y0) * pad
    c = img.crop((max(0, int((x0 - bw) * W / 1000)), max(0, int((y0 - bh) * H / 1000)),
                  min(W, int((x1 + bw) * W / 1000)), min(H, int((y1 + bh) * H / 1000))))
    return c.rotate(rot, expand=True, fillcolor=(30, 90, 60)) if rot else c


def ordered(tiles: list[dict]) -> tuple[list[str], int]:
    """번호순 패 목록과, n 이 row·col 과 어긋난 개수."""
    ts = sorted(tiles, key=lambda t: (t.get('n', 0), t.get('row', 0), t.get('col', 0)))
    bad = sum(1 for t in ts if t.get('n') != (t.get('row', 0) - 1) * 6 + t.get('col', 0))
    return [t['code'] for t in ts if t.get('code') in TILE_CODES], bad


def norm(c: str) -> str:
    return '5' + c[1] if c and c[0] == '0' else c


def score(pred: dict[str, list[str]], truth: dict[str, list[str]]) -> dict:
    out = {}
    for s in SIDES:
        p, t = [norm(x) for x in pred.get(s, [])], [norm(x) for x in truth[s]]
        out[s] = {
            'n_true': len(t), 'n_pred': len(p),
            'tiles': sum((Counter(p) & Counter(t)).values()),
            'pos': sum(1 for a, b in zip(p, t) if a == b),
        }
    return out


def call_retry(rec: GeminiRecognizer, data: bytes, prompt: str, schema: dict, tries: int = 3):
    for k in range(tries):
        try:
            return rec.call(data, prompt, schema)
        except Exception as e:  # 502·타임아웃 등
            if k == tries - 1:
                raise
            print(f'  재시도 {k + 1}: {e}', file=sys.stderr)
            time.sleep(2)


def run_variant(rec, variant: str, cap: Path, extra_rot: float, out: Path) -> tuple[dict, dict]:
    """(강 판독 {side: [codes]}, 부가정보)"""
    loc = json.load(open(cap / 'locate.json', encoding='utf-8'))
    info: dict = {'calls': 0, 'in_tok': 0, 'out_tok': 0, 'ms': 0, 'n_mismatch': 0, 'count_mismatch': 0}

    def add(c):
        info['calls'] += 1
        info['in_tok'] += c.input_tokens
        info['out_tok'] += c.output_tokens
        info['ms'] = max(info['ms'], c.latency_ms)

    if variant in ('A', 'B0', 'B'):
        data = (cap / 'center.jpg').read_bytes()
        if variant == 'A':
            c = call_retry(rec, data, TABLE_PROMPT, TABLE_SCHEMA)
            add(c)
            rivers = normalize_table(c.data)['rivers']
            raw = c.data
        else:
            c = call_retry(rec, data, center_prompt(variant == 'B'), NUM_SCHEMA)
            add(c)
            raw = c.data
            rivers = {}
            for r in c.data.get('rivers', []):
                codes, bad = ordered(r.get('tiles', []))
                rivers[r['side']] = codes
                info['n_mismatch'] += bad
                info['count_mismatch'] += int(r.get('tile_count', len(codes)) != len(codes))
        return rivers, {**info, 'raw': raw}

    # C·D: 강마다 따로. C 는 지금 서버 프롬프트(번호 없음)로 읽어 'bottom' 강을 쓰고, D 는 번호 프롬프트.
    img = ImageOps.exif_transpose(Image.open(cap / 'original.jpg')).convert('RGB')
    boxes = {r['side']: r['box'] for r in loc.get('rivers', [])}
    numbered = variant.startswith('D')
    pad = PAD.get(variant, 0.15)

    def one(side: str):
        im = crop_box(img, boxes[side], pad, ROTATE[side] + extra_rot)
        im.save(out / f'{cap.name}_{variant}_{side}.jpg', quality=88)
        if numbered:
            prompt = ONE_PROMPT_ALIGN if variant.startswith('D7') else ONE_PROMPT
            return side, call_retry(rec, jpeg(im), prompt, ONE_SCHEMA)
        return side, call_retry(rec, jpeg(im), TABLE_PROMPT, TABLE_SCHEMA)

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = dict(ex.map(one, [s for s in SIDES if s in boxes]))
    rivers, raw = {}, {}
    for side, c in res.items():
        add(c)
        if not numbered:
            got = {s: v for s, v in normalize_table(c.data)['rivers'].items() if v}
            rivers[side] = got.get('bottom') or (max(got.values(), key=len) if got else [])
            raw[side] = c.data
            continue
        codes, bad = ordered(c.data.get('tiles', []))
        rivers[side] = codes
        raw[side] = c.data
        info['n_mismatch'] += bad
        info['count_mismatch'] += int(c.data.get('tile_count', len(codes)) != len(codes))
    return rivers, {**info, 'raw': raw}


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--captures', type=Path, required=True)
    ap.add_argument('--names', required=True)
    ap.add_argument('--truth', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--variants', default='A,B0,B,D')
    ap.add_argument('--env-file', type=Path, default=Path(r'C:\Users\jjh7757\Downloads\부트캠프\.env'))
    ap.add_argument('--model', default='gemini-3.8-flash')
    ap.add_argument('--thinking', default='default')
    ap.add_argument('--extra-rot', type=float, default=25)
    ap.add_argument('--repeat', type=int, default=1)
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    truth = json.load(open(a.truth, encoding='utf-8'))['rivers']
    rec = GeminiRecognizer(load_key(a.env_file), model=a.model, thinking=a.thinking)
    names = a.names.split(',')
    variants = a.variants.split(',')

    jobs = [(v, n, r) for r in range(a.repeat) for n in names for v in variants]
    results: list[dict] = []

    def work(job):
        v, n, r = job
        t0 = time.perf_counter()
        try:
            rivers, info = run_variant(rec, v, a.captures / n, a.extra_rot, a.out)
        except Exception as e:  # 재시도 뒤에도 실패: 기록하고 다음으로
            return {'variant': v, 'shot': n, 'run': r, 'failed': f'{type(e).__name__}: {str(e)[:120]}',
                    'ms': round((time.perf_counter() - t0) * 1000)}
        sc = score(rivers, truth)
        return {'variant': v, 'shot': n, 'run': r, 'rivers': rivers, 'score': sc,
                **{k: info[k] for k in ('calls', 'in_tok', 'out_tok', 'ms', 'n_mismatch', 'count_mismatch')},
                'raw': info['raw']}

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res in ex.map(work, jobs):
            results.append(res)
            json.dump(results, open(a.out / 'results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            if res.get('failed'):
                print(f"{res['variant']:3s} {res['shot']} run{res['run']}: 실패 {res['failed']}", flush=True)
                continue
            tot = sum(x['n_true'] for x in res['score'].values())
            print(f"{res['variant']:3s} {res['shot']} run{res['run']}: 패 {sum(x['tiles'] for x in res['score'].values())}/{tot}"
                  f" 순서 {sum(x['pos'] for x in res['score'].values())}/{tot}  ({res['ms'] / 1000:.1f}s, {res['calls']}호출)",
                  flush=True)

    json.dump(results, open(a.out / 'results.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # 요약 표
    print('\n| 방식 | 성공/시도 | 패 맞음 | 순서까지 맞음 | 자리별 순서(bottom/right/top/left) | 번호 어긋남 | 장수 어긋남 | 호출/장 | 토큰/장(입력+출력) | 지연 중앙값 |')
    print('|---|---|---|---|---|---|---|---|---|---|')
    for v in variants:
        allv = [x for x in results if x['variant'] == v]
        rs = [x for x in allv if not x.get('failed')]
        if not rs:
            print(f'| {v} | 0/{len(allv)} | - | - | - | - | - | - | - | - |')
            continue
        tot = sum(sum(s['n_true'] for s in x['score'].values()) for x in rs)
        tiles = sum(sum(s['tiles'] for s in x['score'].values()) for x in rs)
        pos = sum(sum(s['pos'] for s in x['score'].values()) for x in rs)
        per = []
        for side in SIDES:
            t = sum(x['score'][side]['n_true'] for x in rs)
            p = sum(x['score'][side]['pos'] for x in rs)
            per.append(f'{round(100 * p / t)}%')
        ms = sorted(x['ms'] for x in rs)[len(rs) // 2]
        tok = (sum(x['in_tok'] for x in rs) // len(rs), sum(x['out_tok'] for x in rs) // len(rs))
        print(f"| {v} | {len(rs)}/{len(allv)} | {tiles}/{tot} ({round(100 * tiles / tot)}%) | {pos}/{tot} ({round(100 * pos / tot)}%) | "
              f"{' / '.join(per)} | {sum(x['n_mismatch'] for x in rs)} | {sum(x['count_mismatch'] for x in rs)} | "
              f"{rs[0]['calls']} | {tok[0]}+{tok[1]} | {ms / 1000:.1f}초 |")


if __name__ == '__main__':
    main()
