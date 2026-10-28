# 하이브리드 측정 결과

| 모델 | 세트 | 결과 |
| --- | --- | --- |
| nikmomo-s (seat) | A~E 10장 | 10장 중 자동 반영 1(정답 1, 틀림 0), Gemini 로 9 | 후처리 뒤 손패 정답 1/10 | 기대 정답 9.5/10(95%), 기대 시간 평균 6.3초, Gemini 호출 90% |
| nikmomo-s (seat) | B·C·D 6장 | 6장 중 자동 반영 1(정답 1, 틀림 0), Gemini 로 5 | 후처리 뒤 손패 정답 1/6 | 기대 정답 5.8/6(96%), 기대 시간 평균 5.8초, Gemini 호출 83% |
| nikmomo-m (seat) | A~E 10장 | 10장 중 자동 반영 0(정답 0, 틀림 0), Gemini 로 10 | 후처리 뒤 손패 정답 0/10 | 기대 정답 9.5/10(95%), 기대 시간 평균 6.9초, Gemini 호출 100% |
| nikmomo-m (seat) | B·C·D 6장 | 6장 중 자동 반영 0(정답 0, 틀림 0), Gemini 로 6 | 후처리 뒤 손패 정답 0/6 | 기대 정답 5.7/6(95%), 기대 시간 평균 6.9초, Gemini 호출 100% |
| haselab (table) | A~E 10장 | 10장 중 자동 반영 2(정답 2, 틀림 0), Gemini 로 8 | 후처리 뒤 손패 정답 2/10 | 기대 정답 9.6/10(96%), 기대 시간 평균 5.6초, Gemini 호출 80% |
| haselab (table) | B·C·D 6장 | 6장 중 자동 반영 0(정답 0, 틀림 0), Gemini 로 6 | 후처리 뒤 손패 정답 0/6 | 기대 정답 5.7/6(95%), 기대 시간 평균 6.9초, Gemini 호출 100% |
| nikmomo-s + haselab 일치 | A~E 10장 | 10장 중 자동 반영 0(정답 0, 틀림 0), Gemini 로 10 | 후처리 뒤 손패 정답 0/10 | 기대 정답 9.5/10(95%), 기대 시간 평균 6.9초, Gemini 호출 100% |
| nikmomo-s + haselab 일치 | B·C·D 6장 | 6장 중 자동 반영 0(정답 0, 틀림 0), Gemini 로 6 | 후처리 뒤 손패 정답 0/6 | 기대 정답 5.7/6(95%), 기대 시간 평균 6.9초, Gemini 호출 100% |

## nikmomo-s (seat)
- A/k20: Gemini 로 (10장) | 손패 3p 3p 5p 5p 4m 3m 6m 6s 7s 8s | 버림 2장
- A/k24: Gemini 로 (10장) | 손패 8s 7s 6s 2m 3m 4m 5p 5p 3p 3p | 버림 2장
- B/k25: Gemini 로 (13장인데 대기패 없음) | 손패 7z 1m 1m 1m 9s 9s 9p 9p 9p 9p | 울기 6z 6z 6z
- B/k28: 자동 반영 · 정답 | 손패 7z 1m 1m 1m 9s 9s 9s 9p 9p 9p | 울기 6z 6z 6z
- C/k15: Gemini 로 (13장인데 대기패 없음) | 손패 1z 1z 1z 1m 2m 3m 4m 5m 3m 9m 8m 9m 2z | 버림 2장
- C/k26: Gemini 로 (2장) | 손패 2m 3m | 버림 18장
- D/k12: Gemini 로 (10장) | 손패 1m 2m 3m 4m 0p 6m 7m 8m 9m 2z | 버림 2장
- D/k16: Gemini 로 (13장인데 대기패 없음) | 손패 1m 2m 3m 4m 0p 6m 7m 8m 9m 2z | 울기 7m 6m 8m
- E/k00: Gemini 로 (13장인데 대기패 없음) | 손패 1z 1z 1z 1z 8m 9m 1s 2s 3s 7s 8s 7z 7z | 버림 4장
- E/k04: Gemini 로 (13장인데 대기패 없음) | 손패 7z 7z 8s 7s 3s 2s 7p 9m 8m 9m 1z 1z 1z | 버림 5장

## nikmomo-m (seat)
- A/k20: Gemini 로 (10장) | 손패 8s 7s 6s 9m 6m 4m 5p 5p 3p 3p | 버림 2장
- A/k24: Gemini 로 (10장) | 손패 7s 7s 6s 3m 4m 4m 5p 5p 3p 3p | 버림 2장
- B/k25: Gemini 로 (10장) | 손패 7z 1m 1m 1m 9s 9s 9s 9p 9p 9p | 버림 2장
- B/k28: Gemini 로 (9장) | 손패 1m 1m 1m 9s 9s 9s 9p 9p 9p
- C/k15: Gemini 로 (7장) | 손패 4m 3m 3m 1m 1z 1z 1z | 버림 5장
- C/k26: Gemini 로 (9장) | 손패 6m 4m 4m 3m 2m 1m 1z 1z 1z | 버림 3장
- D/k12: Gemini 로 (13장인데 대기패 없음) | 손패 2z 9m 8m 7m 6m 0p 4m 3m 2m 1m | 울기 8m 7m 6m
- D/k16: Gemini 로 (13장인데 대기패 없음) | 손패 2z 9m 8m 7m 6m 0p 4m 3m 2m 1m | 울기 8m 7m 6m
- E/k00: Gemini 로 (9장) | 손패 7s 3s 2s 1s 9m 8m | 울기 1z 1z 1z | 버림 4장
- E/k04: Gemini 로 (12장) | 손패 7z 7z 8s 7s 3s 2s 1s 9m 8m | 울기 1z 1z 1z | 버림 3장

## haselab (table)
- A/k20: 자동 반영 · 정답 | 손패 8s 7s 6s 6m 5m 4m 5p 5p 3p 3p | 울기 4s 4s 4s 4s (후처리 전엔 오답)
- A/k24: Gemini 로 (10장) | 손패 8s 7s 6s 6m 5m 4m 5p 5p 3p 3p | 버림 9장
- B/k25: Gemini 로 (같은 패 5장 이상) | 손패 9s 9s 9s 1m 1m | 울기 1m 1m 1m | 버림 11장
- B/k28: Gemini 로 (12장) | 손패 7z 1m 1m 1m 1m 9s 9s 9s 9s 9p 9p 9p | 버림 1장
- C/k15: Gemini 로 (10장) | 손패 6m 5m 4m 3m 2m 1m 1z | 울기 5z 5z 5z | 버림 1장
- C/k26: Gemini 로 (9장) | 손패 1z 1z 1m 2m 3m 4m 5m 6m 7m
- D/k12: Gemini 로 (10장) | 손패 2z 9m 8m 7m 6m 0m 4m 3m 2m 1m | 버림 7장
- D/k16: Gemini 로 (11장) | 손패 1m 2m 3m 4m 0m 6m 7m 8m 8m 9m 2z | 버림 9장
- E/k00: 자동 반영 · 정답 | 손패 1z 1z 1z 7m 8m 9m 1s 2s 3s 7s 8s 7z 7z | 버림 3장 (후처리 전엔 오답)
- E/k04: Gemini 로 (14장인데 화료형 아님) | 손패 1z 1z 1z 7m 8m 9m 1s 2s 3s 7s 7s 8s 7z 7z | 버림 4장
