#!/usr/bin/env bash
# 임시 이미지를 EC2 t4g.small 에서 한 번 돌리고 지운다(운영 컨테이너는 그대로). build.sh 다음에, 운영 측정이 돌지 않을 때.
#   bash experiments/tile_classifier/server_bench/run_on_server.sh [--single]    → server_bench/server_run[_single].log, 채점: score.py <로그>
set -euo pipefail
EXTRA=${1:-}
LOG=server_run${EXTRA//-/_}.log
LOG=${LOG/__/_}
cd "$(dirname "$0")"
export MSYS_NO_PATHCONV=1
R=ap-northeast-2
REG=403187831140.dkr.ecr.$R.amazonaws.com
IMG=$REG/tile-bench-tmp:r2
I=i-05ee0665bbba15a52
aws ecr create-repository --region $R --repository-name tile-bench-tmp --output text --query repository.repositoryName
trap 'aws ecr delete-repository --region $R --repository-name tile-bench-tmp --force --output text --query repository.repositoryName' EXIT
aws ecr get-login-password --region $R | docker login --username AWS --password-stdin "$REG"
docker tag tile-bench:arm64 "$IMG"
docker push -q "$IMG"
C=$(aws ssm send-command --region $R --instance-ids $I --document-name AWS-RunShellScript --comment "temporary tile model benchmark" --timeout-seconds 900 \
  --parameters "{\"commands\":[\"aws ecr get-login-password --region $R | docker login --username AWS --password-stdin $REG\",\"docker run --rm --memory 700m --memory-swap 700m $IMG --repeat 3 $EXTRA\",\"docker run --rm --memory 700m --memory-swap 700m $IMG --repeat 2 --one $EXTRA | grep -v RESULT\",\"docker rmi $IMG\"],\"executionTimeout\":[\"900\"]}" \
  --query Command.CommandId --output text)
echo "명령 $C, 끝날 때까지 기다림(수 분)"
aws ssm wait command-executed --region $R --command-id "$C" --instance-id $I || true
for i in $(seq 1 60); do
  S=$(aws ssm get-command-invocation --region $R --command-id "$C" --instance-id $I --query Status --output text)
  case "$S" in Pending|InProgress|Delayed) sleep 10;; *) break;; esac
done
echo "상태 $S"
# SSM 출력은 24KB 에서 잘리므로 RESULT 줄이 일부 빠질 수 있다. 요약 줄은 뒤쪽에 있다.
aws ssm get-command-invocation --region $R --command-id "$C" --instance-id $I --query StandardOutputContent --output text > "$LOG"
aws ssm get-command-invocation --region $R --command-id "$C" --instance-id $I --query StandardErrorContent --output text >> "$LOG"
grep -av RESULT "$LOG" | tail -25
