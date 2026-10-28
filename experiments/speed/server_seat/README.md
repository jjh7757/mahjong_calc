# 운영 서버(EC2 t4g.small)에서 자리 판독 검출 시간 재기 (2026-10-26 밤)

결과는 `../../field_20261024/NOTES.md` 23번 끝, 원본 출력은 `server_run.txt`.

방법(이미지를 새로 만들지 않음 — 운영 이미지에 onnxruntime·YOLO11s·`app/river.py` 가 이미 있음):
1. `photos/<사진>.jpg` = `grid5_scenes/<장면>/<사진>/hand_*.jpg`(B k25_1·k28_1, C k15_1·k26_1, D k12_1·k16_1) — 측정 뒤 지움
2. `bench_seat.py` + `photos/` 를 tgz 로 묶어 임시 S3 버킷에 올리고 30분짜리 presign 주소를 만든다(PC 의 `python` 은 cmd 래퍼라 주소의 `&` 가 깨짐 → 주소를 파일로 넘김)
3. SSM(AWS-RunShellScript): `/tmp/seatbench` 에 받아 풀고
   `docker run --rm --name seatbench --memory 700m --memory-swap 700m -v /tmp/seatbench:/bench:ro --entrypoint python <운영 이미지> /bench/bench_seat.py --repeat 5 --dir /bench`
   → `/tmp/seatbench` 삭제
4. 임시 버킷 삭제(`aws s3 rb --force`)

운영 컨테이너는 건드리지 않음. PC 확인은 `/srv/app` 대신 mahjong-recognizer 저장소 경로로 돌림.
