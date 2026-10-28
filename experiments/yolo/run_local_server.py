"""측정용 로컬 인식 서버(mahjong-recognizer, 8030). Gemini 키는 부트캠프 .env 에서 읽기만 한다(복사 금지).
판독 설정은 지난 측정(NOTES "3번 동시 + 만장일치", 로컬 8030)과 같게: thinking low, 자리 3번 동시.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv("C:/Users/jjh7757/Downloads/부트캠프/.env")
os.environ.setdefault("GEMINI_THINKING", "low")
os.environ.setdefault("RATE_PER_MIN", "1000")
os.environ["RECOGNIZER_API_KEY"] = ""  # 로컬 측정은 인증 없음
REPO = "C:/Users/jjh7757/dev/mahjong-recognizer"
os.chdir(REPO)
sys.path.insert(0, REPO)

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=8030)
