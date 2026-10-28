# VLM 패 인식 실험

비전 LLM(Claude)에 손패 사진을 넣어 패를 읽게 하고, 정답과 비교해 정확도·지연·비용을 잰다.

## 준비

```
set ANTHROPIC_API_KEY=sk-ant-...      (cmd)  /  $env:ANTHROPIC_API_KEY="sk-ant-..."  (PowerShell)
```

## 합성 이미지 (정답 자동 생성)

```
python gen_synthetic.py samples_synth --count 12 --seed 1
```

패 이미지는 FluffyStuff/riichi-mahjong-tiles (CC0). `tiles/` 에 받아 두었다.

## 실제 사진

`samples_real/` 에 사진을 넣고 `labels.json` 에 정답을 적는다.

```json
{"IMG_0001.jpg": "123m456p789s11z 2z"}
```

## 실행

```
python recognize_vlm.py samples_synth --models claude-opus-5-5,claude-sonnet-5-5 --effort high
python recognize_vlm.py samples_real  --models claude-opus-5-5
```

결과는 `results/` 에 JSON·마크다운으로 남는다.

## 거치 촬영 기록 집계 (`score_captures.py`)

앱의 거치 촬영은 촬영마다 기기의 `Download/mahjong_calc/<yyyyMMdd_HHmmss>/` 에 사진·판독 결과(`meta.json`)를 남긴다.
같은 국에서 "대국에 반영" 하면 그때의 입력 화면 값(판독 수정으로 고쳤으면 고친 값)이 같은 폴더의 `label.json` 으로 남는다. 이게 정답이다.
`meta.json` 의 `setup` 에는 출처(local/remote/gallery)·줌(카메라 헤드가 `X-Zoom` 헤더로 알림)·거치 높이(거치 화면 메뉴 "거치 높이" 에 적은 값)가 들어간다.

```
python score_captures.py captures --adb emulator-5554            기기에서 받아 와 집계
python score_captures.py captures --since 20261024_1300 --csv shots.csv
```

높이·줌별로 판독 성공, 손패 장수, 손패 정답(적도라 제외), 평균 틀린 패, 화료자·론/쯔모·방총자·리치·리치 4자리·도라·뒷도라(리치 화료만)·적도라, 전부 정답, 지연(화료자 고르는 시간 제외) 중앙값을 마크다운 표로 낸다. 틀린 촬영은 폴더 이름과 빠진 패·더 읽은 패를 적는다.

리치 4자리는 사진 판독(`merge.riichi_seats_photo`)과 반영 때 확정된 리치 자리(`label.riichi_seats` = 점수판 리치 + 화료 시트에서 켜 둔 자동 반영 칩)를 비교한다. 점수판을 안 누르고 자동 반영 칩만 믿으면 정답이 판독과 같아지니, 실험 때는 칩을 한 번 확인한다.

주의: 정답은 사용자가 확인하고 반영한 값이다. 틀린 판독을 고치지 않고 그대로 반영하면 그 판독이 정답이 된다. 실험 때는 결과 화면에서 손패를 한 번 보고 반영한다.

