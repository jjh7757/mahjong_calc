"""측정용 로컬 인식 서버(mahjong-recognizer, 8030). Gemini 키는 부트캠프 .env 에서 읽기만 한다(복사 금지).
판독 설정은 지난 측정(NOTES "3번 동시 + 만장일치", 로컬 8030)과 같게: thinking low, 자리 3번 동시.

  python experiments/yolo/run_local_server.py [--port 8031] [--seat-frame 0]   (launch.json "recognizer-noframe" = 지금 방식 비교용)
  --repo 로 다른 서버 코드(예: 기준 커밋 worktree)를 띄워 프롬프트 전·후를 나란히 잰다.
  --seat-split 0 --seat-table 0 = 지금 운영과 같은 자리 틀(launch.json "recognizer-base", 8031).
  홀드아웃(개선 계획 2단계, 2026-11-05): launch.json "recognizer-fold-{bcd,am,pmA,pmB}" = 그 사진을 안 배운 검출기·분류기·역할 모델 조합
  (대응표 experiments/tile_classifier/README.md 끝 절). "recognizer-prodlike"(8036) = 운영과 같은 모델.
"""
import argparse
import os
import sys

from dotenv import load_dotenv

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=8030)
ap.add_argument("--seat-frame", default="1", help="자리 판독 YOLO 틀 + 조각 읽기(app/seat.py). 0 이면 통째 읽기(지금 방식)")
ap.add_argument("--repo", default="C:/Users/jjh7757/dev/mahjong-recognizer", help="띄울 서버 코드 폴더")
ap.add_argument("--seat-split", default="1", help="?hand_frac= 로 손패 칸·모서리 칸 나눠 잡기. 0 이면 지금 규칙만")
ap.add_argument("--seat-table", default="0", help="탁자 끝 밖 지우고 검출(서버 기본 끔). 1 이면 지움")
ap.add_argument("--wide-reads", default="1", help="/v2/seatwide 조각·모서리를 각각 몇 번 읽나(운영 기본 1). 0 이면 자리 판독과 같은 수")
ap.add_argument("--local-fold", default="", help="자체 모델 나눔(예: a,pm = det_fold_a + cls_pm). 그 사진을 학습하지 않은 모델로 재려고. 비우면 배포 모델")
ap.add_argument("--seat-det", default="", help="--local-fold 와 함께: 자리 판독(localseat·localroles) 검출기도 나눔 모델로(예: det_r8 → det_r8_fold_<a|b>). 비우면 서버 assets(tile-obb-r8 final = 그 사진을 학습함)")
ap.add_argument("--other-det", default="", help="강·표시패 검출도 자리 판독 검출기로: obb(감싸는 축 상자) | obb-up(+세워 자르기). 비우면 2회차(LOCAL_DET_MODEL)")
ap.add_argument("--role-model", default="", help="역할 모델(/v2/localroles): 서버 assets 안 파일 이름(예: tile-roles-rot.onnx) 또는 "
                "server_bench/models 안 이름(예: tile-roles-rot_fold_am.onnx = 오전을 안 배운 교차 검증 가중치, 개선 계획 2단계). 비우면 서버 기본")
ap.add_argument("--cls-tag", default="cls", help="분류기 이름 앞(7-1, 2026-11-06): cls2 = 세운 크롭 재학습(server_bench/models/cls2_<나눔>{,_s1}.onnx). "
                "--local-fold 없이 cls2 면 운영 자리에 cls2_all·cls2_all_s1")
ap.add_argument("--seat-model", default="", help="--local-fold 없이 자리 검출기만 바꿀 때(7-2, 2026-11-06): server_bench/models 안 이름(예: det_r9_final.onnx) → LOCAL_SEAT_MODEL")
ap.add_argument("--lone-pair", default="", help="서버 규칙 짝은 늘 2장(LONE_PAIR_LOOSE, 2026-11-09 metrics 표 1-145): 0 끔 / 1 켬. 비우면 서버 기본")
a = ap.parse_args()
if a.lone_pair:
    os.environ["LONE_PAIR_LOOSE"] = a.lone_pair
    print("LONE_PAIR_LOOSE", a.lone_pair, flush=True)
if a.seat_model:
    os.environ["LOCAL_SEAT_MODEL"] = f"C:/Users/jjh7757/dev/mahjong_calc/experiments/tile_classifier/server_bench/models/{a.seat_model}"
    if not os.path.exists(os.environ["LOCAL_SEAT_MODEL"]):
        raise SystemExit(f"자리 검출기 없음: {os.environ['LOCAL_SEAT_MODEL']}")
    print("자리 검출기", os.environ["LOCAL_SEAT_MODEL"], flush=True)
if a.other_det:
    os.environ["LOCAL_OTHER_DET"] = a.other_det
if a.role_model:
    _bench = f"C:/Users/jjh7757/dev/mahjong_calc/experiments/tile_classifier/server_bench/models/{a.role_model}"
    os.environ["LOCAL_ROLE_MODEL"] = _bench if "_fold_" in a.role_model or os.path.exists(_bench) else f"{a.repo}/app/assets/{a.role_model}"
    if not os.path.exists(os.environ["LOCAL_ROLE_MODEL"]):
        raise SystemExit(f"역할 모델 없음: {os.environ['LOCAL_ROLE_MODEL']}")
    print("역할 모델", os.environ["LOCAL_ROLE_MODEL"], flush=True)

if a.local_fold:
    _det, _cls = a.local_fold.split(",")
    _models = "C:/Users/jjh7757/dev/mahjong_calc/experiments/tile_classifier/server_bench/models"
    os.environ["LOCAL_DET_MODEL"] = f"{_models}/det_fold_{_det}.onnx"
    os.environ["LOCAL_CLS_MODEL"] = f"{_models}/{a.cls_tag}_{_cls}.onnx"
    # 불확실성 신호 S3 의 두 번째 분류기(같은 나눔·씨드 1 = 이 사진을 안 배움, 개선 계획 5단계 prep_alt_cls.py). 서버 코드가 신호를 안 내면 안 쓴다
    if os.path.exists(f"{_models}/{a.cls_tag}_{_cls}_s1.onnx"):
        os.environ["LOCAL_ALT_CLS_MODEL"] = f"{_models}/{a.cls_tag}_{_cls}_s1.onnx"
    if a.seat_det:
        os.environ["LOCAL_SEAT_MODEL"] = f"{_models}/{a.seat_det}_fold_{_det}.onnx"
if a.cls_tag != "cls" and not a.local_fold:  # 운영 자리에 새 분류기(7-1)
    _models = "C:/Users/jjh7757/dev/mahjong_calc/experiments/tile_classifier/server_bench/models"
    os.environ["LOCAL_CLS_MODEL"] = f"{_models}/{a.cls_tag}_all.onnx"
    os.environ["LOCAL_ALT_CLS_MODEL"] = f"{_models}/{a.cls_tag}_all_s1.onnx"
if a.cls_tag != "cls" or a.local_fold:
    print("분류기", os.environ.get("LOCAL_CLS_MODEL"), os.environ.get("LOCAL_ALT_CLS_MODEL"), flush=True)
load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
os.environ.setdefault("GEMINI_THINKING", "low")
os.environ.setdefault("RATE_PER_MIN", "1000")
os.environ["SEAT_FRAME"] = a.seat_frame
os.environ["SEAT_SPLIT"] = a.seat_split
os.environ["SEAT_TABLE"] = a.seat_table
os.environ["WIDE_READS"] = a.wide_reads
os.environ["RECOGNIZER_API_KEY"] = ""  # 로컬 측정은 인증 없음
os.environ["ALLOW_NO_AUTH"] = "1"  # 키 없으면 서버가 기동을 거부한다(d9cc340)
REPO = a.repo
os.chdir(REPO)
sys.path.insert(0, REPO)

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=a.port)
