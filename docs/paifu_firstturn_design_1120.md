# 패보 1순 — 강 기준 차례 목록과 판 경계 설계 (2026-11-20)

사용자 "1순을 강 기준 차례 목록으로 정식 흐름에 넣는 설계" → "네, 설계해 줘". 설계만 있고 구현 · 측정은 아직 없다. 근거 숫자는 metrics 표 12-95(1순 복원) · 12-98(갈림이 14장을 바꾸나), problem_log 66번 끝.

## 0. 한 줄

- **오프라인:** 줄이 서기 전에 버린 차례를 차례 목록의 `turns` 에 끼우지 않고 판마다 `pre_turns` 로 따로 둔다. 마지막 pre 차례의 14장은 추적 없이 정해지므로(다음 차례 시작 줄 + 버린 패) 그것부터 패보에 싣고, 뽑은 패 칸은 있으면 싣고 없으면 후보로 둔다.
- **앱:** 결과 화면 · 유국 창이 떠 있는 동안에도 버림 기록기만은 계속 먹인다. 다음 판 친이 아직 안 정해진 동안의 시작 문을 따로 둔다.
- **범위 밖:** 손 밑 두 장 순서 가르기(표 12-97 다시 묻기 쪽), 앱에서 hero 손패 복원, 유국 판 패보 저장.

## 1. 지금 구조와 빠지는 곳

오프라인(`experiments/paifu_frames/handtrack/`):

- 판 구간은 `t_ready`(13장 줄이 정지한 첫 시각)부터다. `segment.py:50-53` 이 `ms >= t_ready` 만 남기고 `:59` 가 첫 프레임을 정지로 고정한다.
- `truthprep.py:39-44` 는 구간마다 강 장수 `[x, y]` 에서 `x+1..y` 만 차례로 센다. 첫 정지 상태에 이미 있던 x장은 차례가 안 되고 `game.json` 의 `river_before_ready` 로만 남는다. 판의 `first_i` = 그 장수 + 1.
- 줄 앞 버림 수는 판마다 다르다: r16 · r15 = 0, r12 · r17 · r19 · r13 · L16 = 1, r11 · n02 · n07 · n03 = 2. `firstturn.py` 는 "1장 · 친 아님" 만 다루고, 버린 패 · 시각을 손으로 적은 표(`GAMES`)에 기댄다.
- `turns` 의 차례가 "13장 줄에서 시작" 이라는 가정에 기대는 곳: `slotgrid.anchor`(:91-104), `sam2track.plan`(:106-108), `opusread.prep`(:65, :100-102), `rebuild_opus.rebuild`(:104, 정답 없는 차례는 조용히 쯔모기리로 셈 :35-36 · :57-58), `firstturn.rebuild`(:110-111, `recs[0]` = 2순), `paifu_export`(:49-50, :185), `turncut`(:100-116).
- `paifu_export.py:186` 은 줄 앞 hero 차례를 `None` 으로 채워 draw · discard 의 `hand` · `tsumogiri` 를 null 로 내보낸다. `firstturn.py rebuild` 의 `haipai.json` 을 읽는 코드는 없다.
- 친 여부는 `captures/<dir>/meta.json` 이 있는 판만 코드가 안다(r12 · r17 · r19 = 화료자 친 아님). r13 · r16 · L16 은 meta 가 없다. **r13 은 config 메모가 "이 자리가 첫 버림 = 친으로 보임" 인데 `firstturn.py` 는 "넷 다 친이 아님" 으로 적었다 — 어긋남.**

앱(`lib/`):

- 버림 기록기는 `_tickBg` → `_runOverlay` → `_recordDiscards` 로만 먹는다(`mount_screen.dart:597-606, 1306`). `_tickBg` 는 `_busy` 이거나 위에 다른 화면이 있으면 통째로 쉰다(`:520-524`). 화료 판독은 결과 화면이 닫힐 때까지 `_busy` 다(`:2267, 2520, 2580`). 유국 창 · 천화 결과도 위에 뜨는 화면이라 같다.
- 판 경계는 기록기가 스스로 안다: 네 강이 빈 장면이 2번 이어지면 칸을 비운다(`discard_recorder.dart:333-345`). 시작은 `dealer` 자리 강에 패가 두 장면 이어 보일 때다(`:346-358`). `dealer` 는 장면마다 `g.dealer` 로 덮인다(`mount_screen.dart:1331`).
- `_syncTrackerRound`(`mount_screen.dart:1631-1647`)는 추적기들만 비우고 기록기는 안 건드린다.
- 패보 저장은 화료 판독 때, 결과 화면을 띄우기 전이다(`:2463`).
- 리뷰는 버리기 전 손패를 "뽑기 쪽(draw.hand + draw.tile) → 없으면 버림 쪽(discard.hand + 버린 패)" 로 만든다(`paifu_review.dart:266-284`). 둘 다 있으면 같아야 한다.

## 2. 원칙

1. **차례 목록의 원천은 강이다.** 줄이 섰는지(`t_ready`)는 그 차례를 무엇으로 읽을지 고르는 속성이다.
2. **기존 `turns` 는 그대로 둔다.** 줄 앞 차례는 따로(`pre_turns`) 둬서 위 일곱 스크립트를 건드리지 않는다.
3. **14장 묶음 먼저.** 마지막 pre 차례의 14장은 읽기 없이 정해진다. 뽑은 패가 무엇이었나는 그다음이다(표 12-98: 1순 칸 후보 2건 모두 14장은 그대로).
4. **모르면 모른다고 싣는다.** null · 후보로 싣고, 조용히 쯔모기리로 채우지 않는다.

## 3. 오프라인 설계

### A1. `pre_turns` — `truthprep.py`

- 판마다 `pre_turns: [{id, i, tile, t_disc, pre: true}]` 를 더한다. `id` 는 기존 꼴 그대로 `<판 3글자>_d<i 두 자리>`(r12 면 `r12_d01` — 지금 비어 있는 번호). `first_i` · `turns` 는 안 바꾼다.
- `tile` = `game.json` 의 `river_before_ready[i-1]`.
- `t_disc` = 화료자 강 장수가 `i` 로 오른 첫 시각. `river.py` 의 강 세기를 `t_start ~ t_ready` 에 1초 간격으로 돌려, 장수가 `i` 이상으로 두 번 이어 나온 첫 시각을 쓴다. 손 가림으로 못 세는 프레임은 건너뛴다.
- 검사: `t_start` 의 강 장수는 0 이어야 한다(판 경계가 맞게 잡혔나). 아니면 멈추고 보고한다.

### A2. 친 여부 — `game.py`

- `game.json` 에 `hero_dealer: true | false | null` 과 출처를 넣는다. meta 가 있으면 `dealer` 와 화료자 자리로 계산하고, 없으면 config 의 `hero_dealer`(손으로 적음, 근거 메모 포함)를 쓴다. 둘 다 없으면 null.
- null 이면 A4 는 "뽑은 패 모름" 으로만 내고 배패 장수를 정하지 않는다.

### A3. 읽기 — `firstturn.py` 를 넓힘(K ≥ 2 는 3단계)

- K = `pre_turns` 수. K = 0 이면 할 일 없음.
- K = 1 · 친 아님: 지금 과제 그대로(뽑은 패가 `t_ready` 줄의 몇 번째 칸인가). 이미 읽은 네 판 답은 다시 읽지 않고 쓴다. `GAMES` 표의 패 · 시각은 `pre_turns` 에서 읽는다.
- K = 1 · 친: 뽑기가 없다. 읽기 없이 배패 14장 = `t_ready` 줄 + 버린 패.
- K ≥ 2: 과제를 "이 구간에 패산에서 가져온 패 각각이 (가) 몇 번째 버림으로 나갔나 (나) 끝 줄 몇 번째 칸에 섰나" 로 넓힌다. 답은 뽑기마다 `{draw_time, fate: "discard_k" | "slot", slot, unsure, candidates}`.

### A4. 복원 — 새 함수 `rebuild_pre(gid, grid_rows)`

`R` = 칸 틀 첫 차례의 시작 줄(`rebuild_opus.rebuild` 의 `rows[0]["before"]`). k = K 부터 1 까지 거꾸로:

- `after_k` = k 가 K 면 `R`(줄 순서까지), 아니면 `before_{k+1}`(묶음만 — 줄 순서는 모름).
- `hand14_k` = `after_k` + 버린 패. **k = K 는 항상 확정.**
- 뽑은 패: 답이 "k번째 버림으로 나감" 이면 쯔모기리, "칸 s" 면 `R[s-1]`, 친의 1순이면 없음, 답이 없거나 unsure 면 후보 목록.
- `before_k` = `hand14_k` − 뽑은 패. 후보가 여럿이면 가지마다 따로 굴린다.
- 가지를 다 굴린 뒤 차례마다 `hand14` 가 가지 사이에 같으면 확정, 다르면 `hand14_candidates` 로 낸다(K = 1 에서는 생기지 않는다).

차례마다 내는 것: `{id, label, river, hand14, hand14_exact, drawn, drawn_candidates, tsumogiri, before, after, src}`. 배패는 친이 아니면 `before_1`(13장), 친이면 `hand14_1`(14장).

`rebuild_opus.py` 와 `firstturn.rebuild` 는 고치지 않는다.

### A5. 내보내기 — `paifu_export.py`

- `hero_info = pre_rows + turns`(지금은 `[None] * (first_i - 1) + turns`).
- pre 차례의 discard 사건: `hand` = `after_k`(k = K 는 `R` 줄 그대로, 그 앞은 정렬한 묶음), `tsumogiri` = 알면 값 · 모르면 null.
- pre 차례의 draw 사건: 뽑은 패가 확정이면 `tile` · `hand`(= `before_k`)를 싣고, 후보면 `tile: null` · `hand: null` · `candidates: [...]`.
- 이렇게 하면 앱 리뷰는 draw 쪽이 null 이어도 discard 쪽으로 14장을 만들어 평가한다 — **앱 코드를 안 고쳐도 1순이 "손패 모름" 에서 평가 대상으로 바뀐다.**
- `start_hand` 는 확정일 때만 싣는다. note 의 "첫 n순은 녹화 전이라 없음" 은 pre 로 채운 판에서는 "첫 n순은 줄을 세우기 전 — 뽑은 패는 (확정 | 후보)" 로 바꾼다.
- `river_before_ready` 단언(:185)은 그대로 둔다.
- 확인할 것: 엮기 고리가 `drew = True` 로 시작해(:193) 친 hero 의 첫 버림에도 draw 사건이 붙는다. 친 1순은 `tile: null` · `hand: null` 로 두면 되는지 재생 화면에서 본다.

### 자료 꼴(C)

`Paifu` JSON 은 version 1 그대로. draw 사건에 선택 키 `candidates`(뽑은 패 후보, `tile` 이 null 일 때만) 하나를 더한다. `PaifuEvent.fromJson` 은 모르는 키를 읽지 않으므로 옛 앱도 그대로 읽는다. 재생 화면에 "3s 또는 5s" 로 보여 주는 것은 3단계.

## 4. 앱 설계

### B1. 기록 전용 틱

- `_busy` 를 둘로 나눈다: **판독 중**(촬영 ~ 병합 — 지금처럼 전부 쉼)과 **결과 화면 표시 중**.
- 패보 기록이 켜져 있으면, 결과 화면 표시 중이거나 위에 다른 화면이 있어도 3초 틱에서 "프레임 받기 → 패 인식 → `_recordDiscards`" 만 돈다. 추적기(Meld · River · Dora) · 자동 반영 · 음성 안내 · 겹쳐 보기 갱신 · 프레임 기록은 지금처럼 쉰다.
- 패 인식을 부르는 조건(장면이 바뀌었거나 15초)은 대국 중과 같게 둬서 부하를 늘리지 않는다.
- 주의: 이 경로는 거치 화면이 맨 위가 아닐 때 돌므로 `setState` · 창 띄우기를 하지 않아야 한다.

### B2. 친이 안 정해진 동안의 시작 문 — `DiscardRecorder`

- 결과 화면 표시 중에는 `g.dealer` 가 아직 지난 판 값이다. 지금 문은 그 자리 강만 보므로, 친이 바뀌는 판에서는 새 친의 첫 버림 장면들을 버린다(패는 나중에 한꺼번에 들어오지만 처음 본 시각 · 순서를 잃는다).
- `dealerPending`(bool)을 더한다. 참이면 "어느 자리든 같은 자리 강에 패가 두 장면 이어 보임" 으로 시작하고, 그 자리를 `startedSide` 로 남긴다.
- 거치 화면은 결과 화면 표시 중에 `dealerPending = true`, 닫히면 false 로 돌리고 `dealer = g.dealer` 를 넣는다. `startedSide` 가 새 `dealer` 와 다르면 패보 note 에 적는다(조용히 넘기지 않음).

### B3. 빈 탁자를 못 본 판

- `_syncTrackerRound` 에서 판이 바뀔 때, 기록기의 `resetAt` 이 지난 화료 판독 시각보다 앞이면(그 뒤로 빈 탁자를 못 봄) 표지를 세우고 다음 패보 note 에 "판 경계를 못 봄 — 앞 판 버림이 섞였을 수 있음" 을 적는다.
- 칸을 강제로 비우지는 않는다(이미 본 새 판 버림을 지우게 됨).

## 5. 검증 — 기대값은 돌리기 전에 적는다

오프라인(새 읽기 없음):

| 번호 | 검사 | 기대값 |
| --- | --- | --- |
| V1 | `t_disc` 자동 시각(네 판) | r12 13:17:49 · r17 14:04:14 · r19 14:20:59 · r13 13:27:16, 각 ±2초(읽기 에이전트가 근거에 적은 놓인 시각 — r17 · r19 는 `GAMES` 표 값과 2 ~ 4초 다름) |
| V2 | `t_start` 강 장수 | 다섯 판 모두 0 |
| V3 | K = 1 회귀 | `rebuild_pre` 의 1순 뽑은 패 r12 2p · r17 0s · r19 3s · r13 1z, 배패가 `haipai.json` 과 같음 |
| V4 | 후보 그대로 넣기 | r19 칸 {6, 7} → `hand14_exact` 참 · 후보 [3s, 5s], r13 칸 {13, 1} → 참 · [1s, 1z] |
| V5 | 내보낸 패보를 앱 리뷰에 | r12 · r17 · r19 의 1순이 "손패 모름" → 평가됨, 2순부터의 결과는 고치기 전과 같음(`flutter test`) |

앱:

| 번호 | 검사 | 기대값 |
| --- | --- | --- |
| V6 | `test/discard_recorder_test.dart` | `dealerPending` 문 · `startedSide` 단위 시험, 기존 시험 그대로 통과 |
| V7 | `integration_test/paifu_live_replay_test.dart` 에 "r16 끝 ~ r17 3순 동안 위에 화면을 띄워 둠" | 고치기 전: r17 강이 1순보다 늦게 시작(실패 재현). 고친 뒤: r17 네 자리 강이 1순부터 · `resets` 가 1 늘어남 |

V7 은 `flutter drive` 라 앱 데이터를 지운다 — 돌리기 전에 사용자에게 묻고, 한 번에 하나만 돌린다.

## 6. 단계

구현은 Opus 5.5(높음) 하위 에이전트, 검토는 이 세션(다시 돌리고 따로 대조).

1. **오프라인 1단계(새 읽기 없음):** A1 · A2 · A4 · A5 + V1 ~ V5. 건드릴 파일: `truthprep.py` · `game.py` · `firstturn.py` · `paifu_export.py` · (새) `rebuild_pre` 가 들어갈 곳.
2. **앱 2단계:** B1 · B2 · B3 + V6 · V7. 건드릴 파일: `lib/paifu/discard_recorder.dart` · `lib/ui/mount/mount_screen.dart` · 시험 둘.
3. **3단계(선택):** K ≥ 2 판 읽기(A3 넓힘 — 새 읽기라 metrics 에 적음, 정답이 없어 사용자 확인이 필요) · `candidates` 를 재생 화면에 표시.

## 7. 사용자가 정할 것

1. **r13 화료자가 친인가.** 친이면 r13 1순의 "뽑은 패 칸 13(후보 1)" 은 뽑기가 아니라 배패의 마지막 장이고, 배패는 14장으로 적는다. 표 12-95 의 "넷 다 친 아님" 도 고쳐야 한다. L16 도 같은 물음.
2. **기록 전용 틱의 범위.** 결과 화면 · 유국 창만 / 위에 무엇이 있든(설정 · 패보 화면 포함). 뒤쪽이 단순하고 빠지는 경우가 없다 — 권장.
3. **유국 판 패보.** 지금은 저장하지 않는다. 강만이라도 저장할지.
4. **K ≥ 2 판(r11 · n02 · n07 · n03) 읽기를 할지.** 정답이 없어 맞는지 재려면 사용자 확인이 든다.
