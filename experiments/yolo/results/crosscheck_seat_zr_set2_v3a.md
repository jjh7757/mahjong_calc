# Gemini 1회 + YOLO26 교차 확인 시뮬레이션 (Gemini 기록: seat_zr_set2_v3a, YOLO 시간 2.0초)

## B·C·D 6장

| 방식 | 자동 반영 | 틀린 채 반영 | 사람 확인 | Gemini 호출(평균) | 입력 토큰(평균) | 시간 중앙 / p90 |
| --- | --- | --- | --- | --- | --- | --- |
| base3 | 87% | 0.0% | 13% | 3.00 | 32.2k | 11.6 / 25.2초 |
| one | 100% | 5.6% | 0% | 1.00 | 10.7k | 6.4 / 18.7초 |
| x-exact | 87% | 0.0% | 13% | 3.00 | 32.2k | 21.1 / 41.5초 |
| x-sub70 | 87% | 0.0% | 13% | 2.33 | 25.1k | 16.3 / 37.7초 |
| x-sub0 | 87% | 0.0% | 13% | 2.00 | 21.5k | 12.2 / 37.7초 |
| two | 91% | 1.1% | 9% | 2.09 | 22.4k | 10.8 / 25.2초 |
| x2-sub0 | 87% | 0.0% | 13% | 2.50 | 26.8k | 14.3 / 37.7초 |

## 사진별 YOLO26 손패(후처리 뒤)와 Gemini 6회와의 일치
- B/k25: YOLO 12장 [1m 1m 1m 1m 7z 9p 9p 9p 9s 9s 9s 9s] | Gemini 정답 6/6 | 일치 exact 0/6, sub70 0/6, sub0 0/6
- B/k28: YOLO 12장 [1m 1m 1m 1m 7z 9p 9p 9p 9s 9s 9s 9s] | Gemini 정답 4/6 | 일치 exact 0/6, sub70 0/6, sub0 0/6
- C/k15: YOLO 10장 [1m 1z 2m 3m 4m 5m 5z 5z 5z 6m] | Gemini 정답 6/6 | 일치 exact 0/6, sub70 0/6, sub0 0/6
- C/k26: YOLO 9장 [1m 1z 1z 2m 3m 4m 5m 6m 7m] | Gemini 정답 6/6 | 일치 exact 0/6, sub70 0/6, sub0 6/6
- D/k12: YOLO 10장 [1m 2m 2z 3m 4m 5m 6m 7m 8m 9m] | Gemini 정답 6/6 | 일치 exact 0/6, sub70 6/6, sub0 6/6
- D/k16: YOLO 11장 [1m 2m 2z 3m 4m 5m 6m 7m 8m 8m 9m] | Gemini 정답 6/6 | 일치 exact 0/6, sub70 6/6, sub0 6/6
