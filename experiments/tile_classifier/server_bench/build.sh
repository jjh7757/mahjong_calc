#!/usr/bin/env bash
# 임시 이미지를 만든다(prep.py 다음에). 서버 실행: docker run --rm --memory 700m --memory-swap 700m <이미지> --repeat 3
cd "$(dirname "$0")"
set -euo pipefail
rm -rf build && mkdir -p build/app build/server_bench
python -m pip install -q --target build/site --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 --platform manylinux_2_27_aarch64 \
  --python-version 3.12 --implementation cp --only-binary=:all: onnxruntime numpy pillow
cp /c/Users/jjh7757/dev/mahjong-recognizer/app/{__init__,river,seat}.py build/app/
cp ../rules_core.py build/
cp -r bench.py meta.json models crops build/server_bench/
cp Dockerfile build/
docker buildx build --platform linux/arm64 -t tile-bench:arm64 --load build
docker images tile-bench:arm64 --format '{{.Size}}'
