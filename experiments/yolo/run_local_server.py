"""측정용 로컬 인식 서버(mahjong-recognizer, 8030). Gemini 키는 부트캠프 .env 에서 읽기만 한다(복사 금지).
판독 설정은 지난 측정(NOTES "3번 동시 + 만장일치", 로컬 8030)과 같게: thinking low, 자리 3번 동시.

  python experiments/yolo/run_local_server.py [--port 8031] [--seat-frame 0]   (launch.json "recognizer-noframe" = 지금 방식 비교용)
  --repo 로 다른 서버 코드(예: 기준 커밋 worktree)를 띄워 프롬프트 전·후를 나란히 잰다.
  --seat-split 0 --seat-table 0 = 지금 운영과 같은 자리 틀(launch.json "recognizer-base", 8031).
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
a = ap.parse_args()

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
