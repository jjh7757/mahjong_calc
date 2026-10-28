# 패보(최종 상태) 복원 실험 2026-10-24

전체 패를 깐 사진 한 장으로 네 손패·울기·강(순서)·도라를 읽어 정답과 비교. 결과와 해석은 `../vlm/RESULTS.md` 의 같은 날짜 절.

- `truth_game_kakao.json`, `truth_field_115559.json`: 사람이 확대해 읽은 정답
- `game_kakao/`, `field_115559/`: `mahjong-recognizer/scripts/pipeline.py` 결과(`summary.json`, 크롭)
- `*/rivers_split/`: `river_crops.py` 로 강을 자리별로 잘라 다시 읽은 결과(`rivers.json`)
- `score_paifu.py summary.json truth.json [rivers.json]`: 채점(손패·강 패·강 순서·도라, 5장 이상 나온 패)

```
python ../../../mahjong-recognizer/scripts/pipeline.py <사진> --out <폴더> --url https://mahjong.ai-agent-develop.cloud --key-file ../../.recognizer_key
python river_crops.py <사진> <폴더>/summary.json <폴더>/rivers_split [--extra-rot 25]
python score_paifu.py <폴더>/summary.json truth_x.json <폴더>/rivers_split/rivers.json
```

## 강 순서 번호 실험 (`river_order_exp.py`)

실물 사진 6장으로 강 판독 방식 비교(A 지금 방식, B0·B 가운데 + 번호, C 강마다 자름, D·D6·D7 강마다 자름 + 번호). 결과는 `run_order6_low*/results.json`, 정리는 `../vlm/RESULTS.md`.

```
python river_order_exp.py --captures ../field_20261024/captures --names 20261024_115559,20261024_115801,20261024_115929,20261024_120037,20261024_120755,20261024_122922 --truth truth_field_115559.json --out run_x --variants A,B,D7 --thinking low
```
Gemini 키는 `--env-file`(기본 `Downloads\부트캠프\.env`)의 GEMINI_API_KEY 를 읽는다.
