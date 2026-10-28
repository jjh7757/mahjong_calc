# 서버(EC2 t4g.small)에서 YOLO26 시간 재기

결과는 `../README.md` 4-1절, 원본 출력은 `server_run.txt`(서버), `pc_run.txt`(PC).

다시 하려면(빌드 재료는 커서 지워 둠):

```
# 1) 재료 채우기
mkdir models photos crops
cp C:/Users/jjh7757/dev/_downloads/onnx/*.onnx models/            # ONNX 3개(구역·패·ResNet-50)
cp ../../field_20261024/kakao_photos/{k25,k28,k15,k26,k12,k16}.jpg photos/
#   crops/<장면>_<사진>.jpg = grid5_scenes/<장면>/<사진>_1/hand_*.jpg
cp ../results/auto_grid/auto_grid.json .
# 2) arm64 휠을 site/ 에(PC Docker 엔 arm64 에뮬레이션이 없어 RUN 을 못 씀)
python -m pip install --target ./site --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 \
  --python-version 3.12 --implementation cp --only-binary=:all: onnxruntime numpy opencv-python-headless
# 3) 이미지 → 임시 ECR → 서버에서 SSM 으로 --rm 실행(메모리 700MB 상한) → 지우기
docker buildx build --platform linux/arm64 -t yolo26-bench:arm64 --load .
python -I bench.py --parts grid --check auto_grid.json   # PC 에서 먼저 확인
```

서버 실행은 `docker run --memory 700m --memory-swap 700m <이미지> --repeat 3 --parts grid` 와 `--parts verify --cls-batch 2` 를 따로(한 번에 돌리면 ResNet-50 이 OOM).
