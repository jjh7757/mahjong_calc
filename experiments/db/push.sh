#!/usr/bin/env bash
# 운영 EC2 공용 Postgres 의 mahjong DB 에 SQL 파일을 붓는다.
# DB 는 외부에 안 열려 있으므로: S3(seed/) 에 올림 → 5분짜리 presigned URL → SSM 으로 서버가 받아 psql.
# 서버 역할엔 s3:PutObject 만 있어서 presigned URL 로 받는다(TIL AWS배포환경/DB환경구성.md 복구 절차와 같은 방식).
#
#   bash experiments/db/push.sh experiments/db/out/load.sql      # 전체 재적재
#   bash experiments/db/push.sh experiments/db/queries.sql       # 쿼리 돌려 결과 보기
set -euo pipefail
SQL="${1:?SQL 파일}"
INSTANCE=i-05ee0665bbba15a52
BUCKET=ai-agent-develop-db-backup-403187831140   # 30일 수명주기 규칙으로 자동 삭제됨
KEY="seed/mahjong/$(date +%Y%m%d_%H%M%S)_$(basename "$SQL")"
REGION=ap-northeast-2

aws s3 cp "$SQL" "s3://$BUCKET/$KEY" --region "$REGION" --only-show-errors
URL=$(aws s3 presign "s3://$BUCKET/$KEY" --expires-in 300 --region "$REGION")

PARAMS="$(dirname "$0")/.ssm_params.json"   # Windows aws 는 MSYS /tmp 경로를 못 읽어서 상대 경로로
python_json() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
# SSM 셸은 dash 라 pipefail 이 없다 → 파일로 받은 뒤 붓는다(받기 실패면 psql 을 안 돌림)
CMD="T=\$(mktemp) && curl -fsS '$URL' -o \$T && docker exec -i postgres psql -U mahjong -d mahjong -v ON_ERROR_STOP=1 -P pager=off < \$T; RC=\$?; rm -f \$T; exit \$RC"
printf '{"commands":["%s"]}' "$(python_json "$CMD")" > "$PARAMS"

ID=$(aws ssm send-command --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
      --parameters "file://$PARAMS" --region "$REGION" --query Command.CommandId --output text)
rm -f "$PARAMS"
for _ in $(seq 1 60); do
  S=$(aws ssm get-command-invocation --command-id "$ID" --instance-id "$INSTANCE" --region "$REGION" \
        --query Status --output text 2>/dev/null || true)
  case "$S" in Success|Failed|Cancelled|TimedOut) break;; esac
  timeout 2 tail -f /dev/null || true
done
aws ssm get-command-invocation --command-id "$ID" --instance-id "$INSTANCE" --region "$REGION" \
  --query '[Status,StandardOutputContent,StandardErrorContent]' --output text
[ "$S" = Success ]
