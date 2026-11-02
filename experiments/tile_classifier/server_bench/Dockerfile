# 서버(EC2 t4g.small, arm64)에서 자체 YOLO26n + 분류기 시간을 재는 임시 이미지. 운영 서비스와 무관하게 --rm 으로 한 번 돌리고 지운다.
# PC Docker 는 RUN 이 안 되므로 aarch64 휠을 site/ 에 풀어 복사만 한다. 빌드 맥락은 build/ (build.sh 가 만듦).
FROM --platform=linux/arm64 python:3.12-slim
WORKDIR /bench
ENV PYTHONPATH=/bench/site
ENV RECOGNIZER_REPO=/bench
ENV PYTHONUTF8=1
COPY site ./site
COPY app ./app
COPY rules_core.py ./
COPY server_bench ./server_bench
ENTRYPOINT ["python", "server_bench/bench.py"]
