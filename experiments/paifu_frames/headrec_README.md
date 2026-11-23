# 헤드 녹화 → 버림 기록기 (2026-11-23)

`headrec_dump.py` 는 헤드 폰 녹화(`experiments/visit_20261114/head_rec/rec_20261114_125617/f_<epoch ms>.jpg`, 1496², 초당 약 10장)에서 판 구간을 3.0초 눈금으로 나눠 눈금마다 가장 가까운 프레임에 앱 겹쳐 보기(`ondevice.overlay`)를 돌리고 `overlay_dump.json` 꼴로 쓴다(`--mode ab` = 1496 그대로 t · tc + read_small t2 · tc2, `c2x` = 2배로 키워서 → `overlay_dump_c2x.json`, `reveal` · `reveal_c2x` = `t_reveal` + 2 · + 4초 두 장 → `reveal_overlay*.json`). 판 정의 파일은 JSON 하나로 `{"<판 id>": {"t_from": "HH:MM:SS[.f]", "t_to": "HH:MM:SS[.f]", "t_reveal": "HH:MM:SS[.f]"(선택, reveal 에 필요), "first_discard": "top"(선택, 선 후보와 견줄 자리 bottom/right/top/left), "note": "…"(선택)}}` — 시각은 현지(KST), 날짜는 `--date`(기본 2026-11-14), `_` 로 시작하는 키는 건너뜀. 판 목록 꼴 `{"rounds": [{"id", "t_start", "t_end_play", "t_reveal", "note", "dealer_side": {"first": …}}]}`(v1114rec `rounds.json` · `results/han3_1123/rounds_p.json`)도 그대로 받아 t_start − 15초 ~ t_reveal − 0.3초로 바꾼다. 출력은 `results/han3_1123/<판 id>/`(이미 있으면 건너뜀, `--force` 로 다시). `headrec_rounds.json` 은 `headrec_dump.py defs` 가 만든 검증 4판(`val_*`) + 3반장 n01~n08(t_start − 15초 ~ t_reveal − 0.3초). 격자는 줄 격자 264/783/259/777 · 리치봉 구역 424,425,618,622(2 · 3반장 공통) 고정. `headrec_run.py` 가 기록기(`replay_recorder.dart`, exe 로 컴파일)를 돌린다: `val` = 검증 4판 추적 프레임 · A(`overlay --min-side 0`) · B(`overlay-small`) · C(2배 `overlay`) 채점(heldout_1114 score 와 같은 규칙) → `val_summary.json`, `play <A|B|C> [판 id …] [--defs 파일] [--bottom-seat 0]` = 선 없이 한 번 → 자리별 첫 칸 `first_at` 이 가장 이른 자리를 선으로 다시 → `dart_overlay.json` · `dart_overlay_timeline.json` · `paifu_rec.json` · `river_check.jpg` + 엮임 검사 · 같은 종류 5장 · 울기 · 의심 칸 → `han3_summary.json`.

```
P=experiments/paifu_frames/results/han3_1123/rounds_p.json
python -X utf8 experiments/paifu_frames/headrec_dump.py dump $P --mode c2x
python -X utf8 experiments/paifu_frames/headrec_dump.py dump $P --mode reveal_c2x
python -X utf8 experiments/paifu_frames/headrec_run.py play C p01_143158 p02_143539 p03_144427 --defs $P
```
