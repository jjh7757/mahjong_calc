# experiments/db — 패보 · 측정 기록을 PostgreSQL 16 에

흩어진 JSON · 마크다운을 SQL 로 묻고 답하려고 적재한다(예: "날짜별 측정 표 수", "자리별 쯔모기리 비율").
DB 에 직접 붙지 않고 `.sql` 텍스트만 만든다. 표준 라이브러리 Python 만 쓴다.

| 자료 | 원본 | 표 |
| --- | --- | --- |
| 패보 22판 | `assets/paifu/*.json`, `assets/paifu_h3/*.json` | `hanchan` · `round` · `round_event` · `round_result`, 뷰 `v_discard` |
| 측정 기록 | `docs/metrics.md` | `metrics_section` · `metrics_table` · `metrics_part` · `metrics_row` · `metrics_cell`, 뷰 `v_accuracy` · `v_timing` |

## 다시 적재하기

```sh
python experiments/db/build_sql.py            # → experiments/db/out/load.sql, 표별 행 수 출력
python experiments/db/build_sql.py --sample   # 정확도 · 시간 칸 무작위 표본도 출력(오탐 점검)
psql -v ON_ERROR_STOP=1 -f experiments/db/out/load.sql
psql -f experiments/db/queries.sql            # 예시 질문 8개
```

`load.sql` = `BEGIN;` + `schema.sql`(맨 앞에서 `DROP ... IF EXISTS CASCADE`) + INSERT(500행씩) + `COMMIT;`.
전체 재적재라 몇 번 부어도 같은 상태가 된다. `out/` 은 결과물이라 커밋하지 않는다(`.gitignore`).
문자열은 `standard_conforming_strings = on` 기준(작은따옴표만 두 번, 백슬래시 그대로, NUL 제거).

## 운영 서버(EC2 공용 Postgres)에 붓기

2026-11-25 부터 운영 인스턴스(`i-05ee0665bbba15a52`)의 공용 `postgres` 컨테이너에 database `mahjong` · role `mahjong` 이 있다.
DB 는 외부에 안 열려 있고(TIL `AWS배포환경/DB환경구성.md`), 비밀번호는 서버 `/srv/db/.env.mahjong`(600)에만 있다.
판독 서버(mahjong-recognizer)는 이 DB 를 쓰지 않는다 — 운영 판독 경로와 분리.

```sh
bash experiments/db/push.sh experiments/db/out/load.sql   # 전체 재적재
PYTHONIOENCODING=utf-8 bash experiments/db/push.sh experiments/db/queries.sql   # 쿼리 결과 보기(한글 출력 때문에 인코딩 지정)
```

`push.sh`: S3 백업 버킷 `seed/mahjong/` 에 올림(30일 뒤 자동 삭제) → 5분 presigned URL → SSM 으로 서버가 받아 `psql -U mahjong`.
로컬에 admin AWS 자격증명이 있어야 한다. 첫 적재(11-25): 12MB, 행 수는 아래 표와 같음.

## 표 구조

- `hanchan(id '2026-11-14_h3', played_on, hanchan_no)` — 제목의 날짜 + "N반장".
- `round(id = JSON id, hanchan_id, title, round_name, wind, kyoku_no, honba, dealer, hero, names[], kyotaku?, start_scores[]?, dora_indicators[], ura_indicators[], source?, note, version, event_count, file_path)`.
- `round_event(round_id, seq, type, seat, tile, tsumogiri?, riichi?, at_ms?, call_kind, call_from, call_tiles[], hand[]?, guess?, raw jsonb)` pk (round_id, seq).
  제안과 다르게 `hand` 는 `text[]`, `guess` 는 `boolean` — 실제 값이 패 문자열 목록과 true/false 뿐이어서. 원본은 `raw` 에 그대로 있다.
- `round_result(round_id, type, winner, loser, win_tile, hand[], melds jsonb, flags jsonb)` — `result` 가 없는 판(r20_143236)은 행 없음.
- `v_discard` — 버림만, `seat_discard_no`(자리별 몇 번째) · `round_discard_no`.
- `metrics_section(id, label '1' | null, title, line_no)` — `## ` 절.
- `metrics_table(id, section_id, label '1-3' | null, title, line_no, is_section_own, measured_on, out_of_eval, eval_mixed, title_verdict)` — `### ` 표.
  절 머리 바로 아래(`###` 전)에 있는 마크다운 표는 절 자체를 표 하나로 넣는다(`is_section_own`, label 은 절 번호, 번호 없는 절은 null).
  같은 번호가 두 번 나와서(1-54, 15-18) 번호는 pk 가 아니다. 제안에 없던 `eval_mixed` 를 더했다: 제목의 "평가 밖 포함"(48표)은
  평가 세트와 평가 밖이 섞였다는 뜻인데, 규칙대로 `out_of_eval` 도 true 가 되므로 따로 가려낼 수 있게.
- `metrics_part(table_id, part, line_no, headers[], row_count)` — 제안에 없던 표. 한 절 안 마크다운 표마다 머리가 달라서 머리 목록을 둔다.
- `metrics_row(table_id, part, row_no, line_no, cells jsonb {머리: 원문}, adopted, raw_line)` — 머리가 겹치면 `머리 (2)`, 머리보다 칸이 많으면 `_col<N>`.
- `metrics_cell(table_id, part, row_no, col_no, header, value 원문, frac_num, frac_den, t_median, t_p90, t_max)`.
- `v_accuracy` · `v_timing` — 뽑힌 칸 + 표 label · title · measured_on · out_of_eval (+ `ratio`).

## 파싱 규칙 요약(데이터 전체에 같은 규칙, 표별 예외 없음)

파싱용 값은 `**` · `__` · `~~` · 백틱 · `\|` 를 벗긴 것. 원문은 그대로 저장.

- **표 찾기**: 파이프 줄 바로 다음 줄이 `|---|` 꼴이면 표 시작, 파이프 줄이 끝날 때까지 데이터. 앞 공백(목록 안 표) 허용. `\|` 는 구분자 아님.
- **measured_on**: 제목에서 처음 나온 `YYYY-MM-DD`. **out_of_eval**: 제목에 "평가 밖". **title_verdict**: 제목의 ❌ · 미채택 · 🗑 를 공백으로 이음.
- **정확도 `a/b`**: 값이 `a/b`(공백 허용)로 시작하고, 분모 바로 뒤가 끝 · 공백 · 문장부호일 때(`1/2반장` 같은 붙은 글자 거름),
  0 ≤ a ≤ b, b > 0. 다음이면 null(애매): 뒤에 `/ 숫자` 가 또 옴(세 수 묶음), 괄호 밖 나머지에 화살표(→, 전·후 값)나 또 다른 `x/y` 가 있음,
  머리가 슬래시로 나뉘는데(`넓은 판독 씀 / 미리 보냄`) 마지막 몫이 분모 말(정답 · 전체 · 라벨 · 장면 · 총 · 분모)로 시작하지 않음 — 이때 값 `a / b` 는 두 양의 나열이라서.
- **시간 `x / y / z`**: 값이 숫자 세 개(가운데 · 끝은 `—` 허용, 중앙은 숫자) + 선택 `초`/`s` 로 시작하고, 중앙 ≤ p90 ≤ 최대.
  게다가 (값에 초 단위) 또는 (머리에 시간 · 초 · 지연 · latency · sec · 느린 · ms) 또는 (머리에 중앙 · p90 이 있고 오차 · 차 · diff · 분율 · 비율 · % · px · 화소 · (u) · 점수가 없음).
  머리가 ms 이면 1000 으로 나눠 초로 둔다. 나머지 조건(화살표 · 또 다른 묶음)은 정확도와 같다.
- **adopted**: 머리가 정확히 "채택" 인 열의 원문.

## 한계

- 정확도 꼴로 시작하지만 null 로 둔 칸이 약 660개: `12/12 → 12/12`(전·후), `11/13 · 738/755`(두 값), `12 / 10 / 9, 31/32`, 슬래시 머리 아래 나열 등.
  전·후 값을 나눠 뽑지 않는다. 값 중간에만 나오는 분수(`표시패 7/12`)도 안 뽑는다.
- 시간은 "중앙 / p90 / 최대" 세 수 꼴만. `장면 중앙 10.7~20.6`, `locate 25 + 읽기 27`, 한 수만 적힌 시간은 안 뽑는다. 시간이 아닌 양의 머리가 위 낱말 목록에 없으면 시간으로 잘못 뽑힐 수 있다.
- `measured_on` 은 제목의 첫 날짜라 사진 날짜가 먼저 나오면 틀린다(예 표 1-123 "첫날(2026-10-22) 사진을 … (2026-11-08" → 10-22). 서로 다른 날짜가 둘 이상인 제목이 3개. 날짜 없는 표 25개는 null(연도 없는 `10-25` 는 안 읽음).
- "평가 밖" 은 제목만 본다. 행 단위(한 표 안 일부 행이 평가 밖)는 구분 못 한다. `## 표 6. 평가 밖` 절 자체의 표는 절 제목이 들어가 true.
- 패보: `L16_135321` 과 `r16_135321` 은 같은 판(2반장 남2국 1본장)을 다른 손패 주인으로 적은 것, `r20_143236`(앱 기록, 결과 없음)과 `h3_143158`(녹화 복구)은 같은 3반장 동1국이다. 반장별 집계에 둘 다 들어간다.
  `seat` 는 JSON 의 자리 번호 그대로(0 ~ 3), 버림의 `tsumogiri` 는 1,134개 중 820개가 null(모름).
