# 대국 기록 사이트 설계 (2026-11-25)

## 0. 정한 것 (사용자 결정, 11-25)

- 마블리와 연계하지 않는다(남의 사이트라 연계가 어렵다). 우리 단독 사이트가 대국 기록의 원천이다. 마블리 자동 등록 기능은 앱에 그대로 둔다.
- 화면·이름은 마블리를 따라 하지 않는다. 우리 앱 기능(전적, 대국 흐름, 패보) 중심으로 새로 짠다.
- 로그인: **관리자 한 명 + 매장(태블릿) 키**. 멤버 개인 로그인은 두지 않는다(태블릿 한 대를 넷이 같이 쓰고, 대국을 시작할 때 멤버 명단에서 자리를 고르므로 "누구 기록인가" 는 이미 정해진다. 오프라인 대국도 있다).
- 조회 화면은 로그인 없이 링크로 본다(검색 엔진 색인은 막는다). 멤버 이름은 앱 명단의 별명을 그대로 저장한다(실명이 아니라는 전제).

## 1. 목표와 범위

| 넣는 것 | 넣지 않는 것 |
| --- | --- |
| 태블릿 앱이 끝난 대국(결과 + 국별 사건 + 패보)을 올림, 오프라인이면 쌓아 두었다가 올림 | 멤버 가입 · 개인 로그인 |
| 웹: 멤버 순위표, 멤버 상세, 대국 목록, 대국 상세(국별 점수 흐름, 패보 재생) | 마블리 연계 · 마블리 화면 흉내 |
| 관리자: 매장 키 발급 · 폐기, 대국 숨기기 | 웹에서 대국 입력 · 수정(입력은 앱에서만) |
| 측정 · 판독 기록 분석 표(experiments/db, 이미 있음)는 그대로 둠 | 판독 서버(mahjong-recognizer)에 DB 의존 추가 |

## 2. 구성

```
태블릿 앱 ──(대국 끝 · 직접 입력)──▶ POST /records/api/v1/games   (X-Store-Key)
                                          │
                     mahjong-records 컨테이너 (FastAPI + 빌드된 React 정적 파일)
                                          │  psycopg 풀 최대 3
                          공용 postgres 의 database `mahjong`, schema `app`
                                          ▲
웹 브라우저 ──▶ https://mahjong.ai-agent-develop.cloud/records/  (Caddy 가 /records* 만 이 컨테이너로)
```

- **새 저장소 `jjh7757/mahjong-records`(공개 — ARM 러너 무료 조건, TIL 새앱배포절차 3).** 판독 서버와 나눈 이유: 판독 서버는 운영 판독 경로라 DB 장애 · 배포 실수가 판독을 막으면 안 되고, 의존성(onnxruntime · opencv)도 무겁다.
- **새 서브도메인을 만들지 않고 기존 `mahjong.ai-agent-develop.cloud` 의 `/records` 경로**로 연다. 가비아 DNS 작업이 필요 없고, 인증서도 이미 있다. Caddy 에 `handle /records*` 블록 하나를 판독 서버 블록보다 앞에 넣는다(경로를 떼지 않고 그대로 넘김 — 앱이 `/records` 접두어를 안다).
- 컨테이너 메모리 상한 256MB(서버 여유 약 780MB, TIL 환경정보 RAM 예산).
- DB 는 11-25 에 만든 database `mahjong` · role `mahjong` 을 쓰되 **schema `app`** 에 둔다. `public` 의 분석 표(experiments/db, 전체 재적재로 지우고 다시 만듦)와 섞이지 않게.

## 3. 저장 형식 (schema `app`)

```sql
store(id serial pk, name text, key_hash text unique, created_at, revoked_at null)
game(id bigserial pk, store_id fk, client_game_id text,        -- 앱 Game.id
     started_at timestamptz, finished bool, ended_by text, manual bool,
     east_only bool, settings jsonb, raw jsonb,                -- 앱 Game.toJson() 그대로
     payload_sha256 text, app_version text,
     uploaded_at, updated_at, hidden bool default false,
     unique(store_id, client_game_id))
game_player(game_id fk, seat int, name text, final_points int, rank int,
            score numeric(6,1), stars int, bust bool, pk(game_id, seat))
game_event(game_id fk, seq int, kind text, round_label text, description text,
           delta int[], stars int[] null, pk(game_id, seq))
paifu_round(game_id fk, seq int, paifu_id text, round_name text, honba int, dealer int,
            hero int, result_type text null, winner int null, loser int null,
            raw jsonb, pk(game_id, seq))
schema_migrations(version int pk, applied_at)
```

- **정산은 앱이 계산해 보낸다**(`Game.settle()` 의 rank · points · score · stars). 우마 · 오카 · 별 규칙을 서버에 또 짜면 두 곳의 계산이 어긋날 수 있다. 서버는 가볍게만 검사한다: 자리 4개, 순위가 1~4 를 한 번씩(동점 규칙상 같은 순위가 없음 — 앱 규칙 확인 후 확정), 이름 비어 있지 않음.
- 패보는 `raw` 를 그대로 두고 요약 열만 뽑는다. 웹 재생은 `raw` 로 그린다.
- 멤버는 따로 표를 두지 않는다. `game_player.name` 으로 모은다(앱도 이름으로 모은다, `memberStats`).

## 4. API (모두 `/records` 아래)

| 방법 · 경로 | 인증 | 내용 |
| --- | --- | --- |
| `POST /api/v1/games` | 매장 키 | 본문 `{game, settlement[4], paifu[], app_version}`. `(store, game.id)` 로 멱등 upsert. 같은 해시면 `{"status":"unchanged"}`, 다르면 지우고 다시 씀(`updated`), 처음이면 `created`. 본문 2MB 상한 |
| `GET /api/v1/members` | 없음 | 이름별: 대국 수, 정산 합, 평균 순위, 1~4위 수, 토비, 별, 최고 점수. `?from=&to=` |
| `GET /api/v1/members/{name}` | 없음 | 위 + 최근 대국 목록 + 순위 흐름 |
| `GET /api/v1/games` | 없음 | 목록(최신순, `?member=&page=`), hidden 제외 |
| `GET /api/v1/games/{id}` | 없음 | 정산 + 국별 사건 + 패보 raw |
| `GET /api/v1/overview` | 없음 | 총 대국 수, 월별 대국 수, 화료 · 유국 비율 |
| `POST /api/admin/login` · `logout` | 비밀번호 | 서명한 세션 쿠키(HttpOnly · Secure · SameSite=Strict · 12시간). 실패 5번이면 15분 잠금 |
| `GET/POST /api/admin/stores`, `POST /api/admin/stores/{id}/revoke` | 관리자 | 매장 키 발급(평문은 발급 응답에 한 번만), 폐기 |
| `POST /api/admin/games/{id}/hide` · `unhide` | 관리자 | 숨기기(지우지 않음) |
| `GET /healthz` | 없음 | DB 연결 확인 |

- 매장 키: 32바이트 무작위, DB 에는 sha256 만. 관리자 비밀번호: 서버 `.env` 의 `ADMIN_PASSWORD_HASH`(hashlib.scrypt). 세션 서명 키도 `.env`.
- CORS 없음(같은 출처). 쓰기 요청은 매장 키 또는 관리자 쿠키 + `X-Requested-With` 확인. 모든 SQL 은 매개변수 바인딩.
- `X-Robots-Tag: noindex` · `robots.txt` 로 색인 막음.

## 5. 웹 화면 (React + Vite, `base: '/records/'`)

1. **순위표**(첫 화면): 멤버별 정산 합 · 평균 순위 · 1위율 · 4위율 · 별 · 대국 수. 기간 고르기.
2. **멤버 상세**: 순위 분포, 최근 20국 순위 흐름 그래프, 대국 목록.
3. **대국 목록**: 날짜 · 네 사람 · 최종 점수 · 순위.
4. **대국 상세**: 정산 표, 국별 사건 표(누가 누구에게 몇 점), 점수 흐름 선 그래프, 패보가 있는 국은 "패보 보기".
5. **패보 재생**: 네 자리 버린 패 줄 + 손패 주인의 손패, 한 걸음씩 / 자동. 패는 글자 칩(1m 등 → 색 · 숫자)으로 그린다(그림 파일 출처 문제를 피함).
6. **관리자**: 로그인, 매장 키 발급 · 폐기, 대국 숨기기.

모바일 우선(손님이 휴대폰으로 봄). 그래프는 가벼운 라이브러리 하나(또는 SVG 직접).

## 6. 앱 쪽

- 설정 화면에 "기록 사이트" 칸: 주소(기본 `https://mahjong.ai-agent-develop.cloud/records`), 매장 키(QR 또는 직접 입력), 켜기/끄기.
- 올릴 차례: `GameStore.finish()` · `addFinished()` 직후 그 대국 id 를 대기열(SharedPreferences `records.queue`)에 넣고 바로 올리기 시도. 앱 시작 · 지난 대국 화면을 열 때도 대기열을 비운다. 실패하면 남겨 두고 다음 기회에(기존 `server_backoff.dart` 방식 참고).
- 올린 본문: `Game.toJson()` + `settle()` 결과 + `PaifuStore.list(game.id)` + 앱 버전.
- 성공하면 `Game.recordsUploadedAt` 을 남겨 지난 대국 화면에 표시. "지난 대국 모두 올리기" 버튼으로 옛 기록도 올린다(멱등이라 여러 번 눌러도 됨).
- 대국 진행 · 판독 흐름은 건드리지 않는다. 올리기는 비동기 · 실패해도 화면을 막지 않는다.

## 7. 시험

- 서버: pytest + 실제 Postgres(CI 는 GitHub Actions `services: postgres:16-alpine`, 로컬은 Docker). 멱등 upsert, 키 폐기, 관리자 잠금, 순위 집계를 앱 `memberStats` 와 같은 입력으로 비교(앱 시험의 고정 대국 몇 개를 JSON 으로 내보내 서버 시험 자료로).
- 앱: 대기열 · 본문 만들기 · 재시도 단위 시험. 기존 analyze · test 통과.
- 배포 뒤: 운영 `/records/healthz`, 시험 매장 키로 대국 하나 올리고 화면 확인 후 숨기기. 태블릿에서 실제 업로드 한 번(설치는 `adb install -r`).

## 8. 배포 순서 (사람 확인이 필요한 곳 ★)

1. GitHub 공개 저장소 `mahjong-records` 생성.
2. ECR 리포지토리 `mahjong-records`(Mutable, 이미지 10개 수명 주기).
3. ★ IAM `github-actions-deploy` 신뢰 정책에 새 저장소 한 줄 추가(보안 설정 변경).
4. 서버 `/srv/mahjong-records/` compose(메모리 256M) + `.env`(DATABASE_URL — `/srv/db/.env.mahjong` 값, ADMIN_PASSWORD_HASH, SESSION_SECRET). 관리자 비밀번호는 사용자가 정해 직접 넣거나, 서버에서 만들어 사용자에게만 보여 줌.
5. Caddy `mahjong.ai-agent-develop.cloud` 블록에 `handle /records*` 추가 → `caddy validate` → reload.
6. TIL `환경정보.md` · `monitor.sh` 에 앱 추가(별도 저장소, 사용자 확인 뒤).
