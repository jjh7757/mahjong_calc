"""만든 음성 파일을 Gemini 로 받아써서 말이 맞는지 본다(덧붙인 말·잘못 읽은 숫자 찾기).

    python tool/check_voice.py                       # assets/voice/<목소리>/ 전부, lines.json 과 비교
    python tool/check_voice.py assets/voice/Puck assets/voice/Leda   # 목소리 폴더만
    python tool/check_voice.py experiments/voice/*.mp3
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_voice import ROOT, VOICE_DIR, load_key, spoken  # noqa: E402

# 문맥 없이 받아쓰면 마작 용어를 비슷한 일상어로 적는다("량페코" → "양배추"). 용어 목록을 같이 준다.
ASK = ("이 음성은 리치마작 게임에서 화료 결과(역 이름·도라·점수 등급)를 외친 한국어 한 마디입니다. "
       "아래 용어 중 하나일 가능성이 높지만, 실제로 들리는 대로 받아 적으세요. 숫자는 들리는 발음대로 한글로"
       "(예: '둘', '사배'). 빠지거나 덧붙은 말이 있으면 그대로 적으세요. 받아 적은 글만 답하세요.\n용어: ")


def duration(p: Path) -> float:
    import imageio_ffmpeg

    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(p)], capture_output=True, text=True)
    t = r.stderr.split("Duration: ")[1].split(",")[0]
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def main():
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=load_key(str(Path.home() / "Downloads" / "부트캠프" / ".env")))
    lines = json.loads((VOICE_DIR / "lines.json").read_text(encoding="utf-8"))
    vocab = ", ".join(spoken(t) for t in lines.values())
    # 인자는 파일 또는 폴더(Windows 는 파일 344개를 늘어놓으면 명령 줄이 너무 길다).
    files = [f for a in map(Path, sys.argv[1:]) for f in (sorted(a.glob("*.mp3")) if a.is_dir() else [a])]
    files = files or sorted(VOICE_DIR.glob("*/*.mp3"))

    def one(p: Path):
        r = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[types.Part.from_bytes(data=p.read_bytes(), mime_type="audio/mp3"), ASK + vocab])
        return p, r.text.strip(), duration(p)

    with ThreadPoolExecutor(6) as ex:
        for p, heard, sec in ex.map(one, files):
            want = spoken(lines[p.stem]) if p.stem in lines else ""
            norm = lambda t: t.replace(" ", "").strip(".!?")
            mark = "" if not want or norm(heard) == norm(want) else "  ← 확인"
            print(f"{p.parent.name}/{p.stem:24} {sec:4.2f}s  원래 '{want}'  들림 '{heard}'{mark}", flush=True)


if __name__ == "__main__":
    main()
