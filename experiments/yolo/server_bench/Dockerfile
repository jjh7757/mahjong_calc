# 서버(EC2 t4g.small, arm64)에서 YOLO26 시간을 재는 임시 이미지. 운영 서비스와 무관하게 --rm 으로 한 번 돌리고 지운다.
# PC Docker 에는 arm64 에뮬레이션이 없어 RUN 을 못 쓴다 → aarch64 휠을 PC 에서 site/ 에 풀어 두고(pip --target --platform) 복사만 한다.
FROM --platform=linux/arm64 python:3.12-slim
WORKDIR /bench
ENV PYTHONPATH=/bench/site
COPY site ./site
COPY bench.py auto_grid.json ./
COPY models ./models
COPY photos ./photos
COPY crops ./crops
ENTRYPOINT ["python", "bench.py"]
