"""태블릿 ONNX 시험 입력 만들기: 서버와 같은 전처리로 입력 텐서를 만들고, PC onnxruntime(1.29, CPU) 출력을 기대값으로 남긴다.

결과는 build/data/ 에: <이름>.in.bin(float32), <이름>.ref.bin(첫 출력 float32), cases.txt(한 줄에 이름 모델 입력이름 차원…).
기기에선 bench(ort_bench.c)가 같은 입력으로 돌려 시간과 기대값과의 최대 차이를 찍는다.

    python experiments/ondevice/make_inputs.py <원본 사진.jpg>
"""
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

HERE = Path(__file__).parent
ASSETS = Path(r"C:\Users\jjh7757\dev\mahjong-recognizer\app\assets")
OUT = HERE / "build" / "data"
IMG, CLS = 1280, 128
MEAN = np.array([0.485, 0.456, 0.406], np.float32)[:, None, None]
STD = np.array([0.229, 0.224, 0.225], np.float32)[:, None, None]


def letterbox(rgb: np.ndarray) -> np.ndarray:
    """서버 local_read._letterbox 와 같게: 긴 변 1280, 짧은 변 32 배수, 가운데 114 패딩."""
    H, W = rgb.shape[:2]
    r = min(IMG / H, IMG / W)
    nw, nh = round(W * r), round(H * r)
    cw, ch = -(-nw // 32) * 32, -(-nh // 32) * 32
    left, top = round((cw - nw) / 2 - 0.1), round((ch - nh) / 2 - 0.1)
    canvas = np.full((ch, cw, 3), 114, np.uint8)
    canvas[top:top + nh, left:left + nw] = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR))
    return canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255


def cls_batch(rgb: np.ndarray, n: int) -> np.ndarray:
    """분류기 입력 n장: 사진 아래쪽(손패 줄 근처)을 패 크기 조각으로 잘라 서버 _cls_input 처럼 128 칸에 맞춰 넣는다(시간용)."""
    H, W = rgb.shape[:2]
    tw, th = W // 40, H // 18
    xs = []
    for i in range(n):
        x0, y0 = W // 4 + i * tw, int(H * 0.8)
        im = Image.fromarray(rgb[y0:y0 + th, x0:x0 + tw])
        im.thumbnail((CLS, CLS))
        out = Image.new("RGB", (CLS, CLS), (114, 114, 114))
        out.paste(im, ((CLS - im.width) // 2, (CLS - im.height) // 2))
        xs.append((np.asarray(out, np.float32).transpose(2, 0, 1) / 255 - MEAN) / STD)
    return np.stack(xs).astype(np.float32)


def main(photo: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(Image.open(photo).convert("RGB"))
    lb = letterbox(rgb)
    cases = [
        ("obb_full", "tile-obb-r8.onnx", lb),          # 자리 판독 회전 상자, 사진 전체(full_raw)
        ("yolo26n_full", "tile-yolo26n.onnx", lb),     # 강·표시패 검출(시간용으로 사진 전체)
        ("cls_b1", "tile-cls-mnv3s-v3.onnx", cls_batch(rgb, 1)),
        ("cls_b16", "tile-cls-mnv3s-v3.onnx", cls_batch(rgb, 16)),
    ]
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    lines = []
    for name, model, x in cases:
        s = ort.InferenceSession(str(ASSETS / model), sess_options=opts, providers=["CPUExecutionProvider"])
        inp = s.get_inputs()[0]
        try:
            y = s.run(None, {inp.name: x})[0]
        except Exception as e:  # 고정 배치 모델이면 건너뜀
            print(f"{name}: 건너뜀 ({e.__class__.__name__}: {str(e)[:120]})")
            continue
        t = []
        for _ in range(5):
            a = time.perf_counter()
            s.run(None, {inp.name: x})
            t.append(time.perf_counter() - a)
        x.astype(np.float32).tofile(OUT / f"{name}.in.bin")
        y.astype(np.float32).tofile(OUT / f"{name}.ref.bin")
        lines.append(" ".join([name, model, inp.name, *map(str, x.shape)]))
        print(f"{name}: 입력 {x.shape} 출력 {y.shape}, PC 2스레드 중앙 {np.median(t):.3f}초")
    (OUT / "cases.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
