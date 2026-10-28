"""강을 자리별로 따로 잘라, 그 자리 플레이어가 아래쪽에 오도록 돌려서 /v1/table 로 읽는다.

가운데 크롭 하나로 네 강을 읽으면 아래쪽 강 말고는 버린 순서가 뒤집히거나 줄이 바뀐다(score_paifu.py 결과).
돌려서 '아래쪽 강' 으로 만들면 순서가 맞는지 본다. locate 상자는 앞선 pipeline.py 실행의 summary.json 것을 그대로 쓴다.

용법: python river_crops.py <사진> <summary.json> <출력폴더> [--url ..] [--key-file ..] [--pad 0.15] [--extra-rot 0]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, r'C:\Users\jjh7757\dev\mahjong-recognizer\scripts')
from try_endpoint import PATHS, post_image  # noqa: E402

ROTATE = {'bottom': 0, 'right': -90, 'top': 180, 'left': 90}


def crop(img: Image.Image, box: list[int], pad: float, rot: float) -> Image.Image:
    W, H = img.size
    y0, x0, y1, x1 = box
    bw, bh = (x1 - x0) * pad, (y1 - y0) * pad
    c = img.crop((max(0, int((x0 - bw) * W / 1000)), max(0, int((y0 - bh) * H / 1000)),
                  min(W, int((x1 + bw) * W / 1000)), min(H, int((y1 + bh) * H / 1000))))
    return c.rotate(rot, expand=True, fillcolor=(30, 90, 60)) if rot else c


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('image', type=Path)
    ap.add_argument('summary', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--url', default='https://mahjong.ai-agent-develop.cloud')
    ap.add_argument('--key-file', type=Path, default=Path(r'C:\Users\jjh7757\dev\mahjong_calc\.recognizer_key'))
    ap.add_argument('--pad', type=float, default=0.15)
    ap.add_argument('--extra-rot', type=float, default=0, help='사진 전체가 기울어 있으면 더 돌릴 각도(PIL, 반시계 +)')
    a = ap.parse_args()
    key = a.key_file.read_text(encoding='utf-8').strip()
    a.out.mkdir(parents=True, exist_ok=True)
    img = ImageOps.exif_transpose(Image.open(a.image)).convert('RGB')
    loc = json.load(open(a.summary, encoding='utf-8'))['locate']

    def run(r: dict) -> tuple[str, dict]:
        side = r['side']
        c = crop(img, r['box'], a.pad, ROTATE[side] + a.extra_rot)
        p = a.out / f'river_{side}.jpg'
        c.save(p, quality=92)
        return side, post_image(a.url + PATHS['table'], p, key)

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = dict(ex.map(run, loc['rivers']))

    rivers = {}
    for side, r in results.items():
        got = {s: v for s, v in r.get('rivers', {}).items() if v}
        # 돌렸으니 그 강은 '아래쪽' 으로 나와야 한다. 아니면 가장 긴 것.
        pick = got.get('bottom') or (max(got.values(), key=len) if got else [])
        rivers[side] = pick
        print(f'{side:6s} [{len(pick):2d}] {" ".join(pick)}   (응답 자리: {list(got)})')
    json.dump({'rivers': rivers, 'raw': results}, open(a.out / 'rivers.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
