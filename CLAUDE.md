# mahjong_calc 작업 규칙

- 답변·진행 보고는 한국어로.
- 새 세션은 `HANDOFF.md` 를 먼저 읽는다(현황·경로·결정).
- 매장에서 "감독 시작" 이라고 하면 `docs/visit_supervision.md` 대로 한다.

## 속도·정확도 측정을 했으면 `docs/metrics.md` 를 고친다

판독 속도·정확도를 재는 실험이나 측정(bench.py 계열, 앱 흐름 `read_grid_timing_test`·`score_seat3.py`, 운영 배포 뒤 확인 측정, 틀 잡기 점검 등)이 끝나면 **같은 턴 안에** `docs/metrics.md` 의 해당 표에 한 줄 더한다. NOTES.md 에 절을 쓰는 것과 별개다. 채택하지 않은 실험도 넣고 "채택" 열에 ✗ 를 적는다.

- 표는 지표·조건별로 나뉘어 있다(앱 흐름 / 자리 판독 단독 / 강 끝 / 기기 처리 / 앞면 판정 / 평가 밖 / 자원·비용). 조건이 맞는 표에 넣고, 어느 표에도 안 맞으면 새 표를 만든다.
- 평가 세트는 B·C·D 6장 고정. 매장 사진·A·E 는 "평가 밖" 표에만.
- 시간은 "중앙 / p90 / 최대" 초, 정확도는 "맞은 수/전체". 서버 변경이면 mahjong-recognizer 커밋 해시, 앱 변경이면 파일명.
- 운영 배포가 포함된 변경이면 "지금 기준값" 절도 갱신한다.
- 같은 시각에 나란히 돌린 비교만 전·후로 적는다. 시각이 다르면 메모에 적는다.
- 손·팔 가림 사진과 사용자 문제 사진(손패를 흩어 놓는 등 사용 규칙 위반)은 채점에서 뺀다. 목록은 `experiments/speed/seat_grow.py` 의 `OCCLUDED`·`USER_ERROR`(합쳐서 `EXCLUDED`), 채점 스크립트는 `sg.eval_scenes()`(또는 `EXCLUDED` 로 거르기)를 쓴다. 앱 흐름 `integration_test/read_grid_timing_test.dart` 의 `_visit` 목록에서도 뺀다. 새 사진은 채점 전에 사진만 보고 판단해 목록에 더한다.

## 저장소

- 앱: 이 폴더(GitHub `jjh7757/mahjong_calc`, 비공개). push 마다 `.github/workflows/ci.yml` 이 analyze·test, master 엔 APK. `**.md`·`docs/`·`experiments/` 만 바뀌면 안 돈다.
- 서버: `C:\Users\jjh7757\dev\mahjong-recognizer`(GitHub `jjh7757/mahjong-recognizer`). master push → pytest → 배포 → 운영 git_sha·라우트 확인.
- `experiments/` 의 사진·결과물은 커밋하지 않는다(.gitignore). 스크립트·메모만.
