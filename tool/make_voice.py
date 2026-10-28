"""결과 화면 음성 파일을 Gemini TTS 로 만든다.

읽을 말 목록은 앱 코드(lib/services/voice_lines.dart)가 정하고, 먼저 JSON 으로 뽑는다:
    dart run tool/voice_lines.dart                         # → assets/voice/lines.json
    python tool/make_voice.py                              # 앱 목소리 전부, 없는 파일만 만듦
    python tool/make_voice.py --voice Puck --force         # 한 목소리만 전부 다시
    python tool/make_voice.py --voice Kore --only yaku_riichi,call_ron  # 몇 개만
    python tool/make_voice.py --sample "리치, 이페코, 도라 2, 하네만" --voices Zephyr,Kore,Puck,Fenrir
                                                           # 목소리 비교용 파일(experiments/voice/)

결과: assets/voice/<목소리>/<이름>.mp3 (앞뒤 무음을 잘라 짧게, 음량 맞춤). 앱이 고를 수 있는 목소리는
lib/services/voice_lines.dart 의 voiceChoices 와 같아야 한다(새 목소리는 pubspec.yaml assets 에도 폴더를 더함). Gemini 키는 --env-file 의 GEMINI_API_KEY.
직접 녹음한 파일로 바꾸려면 같은 이름의 mp3 를 넣으면 된다.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
VOICE_DIR = ROOT / "assets" / "voice"
RATE = 24000  # Gemini TTS 출력: 16bit mono PCM 24kHz
VOICES = ["Kore", "Zephyr", "Leda", "Puck", "Fenrir"]  # 앱 voiceChoices 와 같은 순서

# 스타일 지시문을 앞에 붙이면 목소리 여럿이 지시문까지 소리 내어 읽었다(2026-10-27). 말만 보내고 느낌표로 힘을 준다.
# 숫자는 "도라 투" 처럼 영어로 읽어서 한글로 바꿔 보낸다.
_NATIVE = {1: "하나", 2: "둘", 3: "셋", 4: "넷", 5: "다섯", 6: "여섯", 7: "일곱", 8: "여덟", 9: "아홉",
           10: "열", 11: "열하나", 12: "열둘"}
_SINO = {2: "이", 3: "삼", 4: "사", 5: "오", 6: "육", 13: "십삼"}


def spoken(text: str) -> str:
    """TTS 에 보낼 글: `도라 2` → `도라 둘!`, `4배 역만` → `사배 역만!`, `13면` → `십삼면`."""
    words = text.split(" ")
    if words[-1].isdigit():
        words[-1] = _NATIVE[int(words[-1])]
    out = []
    for w in words:
        num = "".join(c for c in w if c.isdigit())
        out.append(w.replace(num, _SINO[int(num)]) if num and not w.isdigit() else w)
    return " ".join(out) + "!"


def load_key(env_file: str) -> str:
    for line in open(env_file, encoding="utf-8"):
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit(f"GEMINI_API_KEY 가 {env_file} 에 없습니다")


def synth(client, model: str, voice: str, text: str) -> np.ndarray:
    from google.genai import types

    for attempt in range(5):
        try:
            r = client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
                ),
            )
            return pcm_of(r.candidates[0].content.parts[0].inline_data.data)
        except Exception as e:  # 429·일시 오류는 기다렸다 다시
            if attempt == 4:
                raise
            wait = 5 * (attempt + 1)
            print(f"  {text}: {type(e).__name__} {str(e)[:80]} → {wait}초 뒤 다시", flush=True)
            time.sleep(wait)


def pcm_of(data: bytes) -> np.ndarray:
    """응답 오디오 → 16bit mono 샘플. 지금 모델은 WAV(끝에 C2PA 출처 덩어리가 붙음)를 주므로 data 청크만 읽는다.
    통째로 PCM 으로 읽으면 헤더·C2PA 가 끝의 큰 잡음이 된다(2026-10-27). 옛 모델처럼 맨 PCM 이면 그대로."""
    if data[:4] == b"RIFF":
        with wave.open(io.BytesIO(data)) as w:
            assert w.getframerate() == RATE and w.getsampwidth() == 2 and w.getnchannels() == 1, w.getparams()
            data = w.readframes(w.getnframes())
    return np.frombuffer(data, dtype="<i2")


def trim(pcm: np.ndarray, pad_ms: int = 40) -> np.ndarray:
    """앞뒤 무음을 자르고(문턱 = 최대의 4%) 최대 음량을 -1dBFS 로 맞춘다."""
    x = pcm.astype(np.float32)
    if len(x) == 0 or np.abs(x).max() == 0:
        return pcm
    loud = np.where(np.abs(x) > np.abs(x).max() * 0.04)[0]
    pad = RATE * pad_ms // 1000
    x = x[max(0, loud[0] - pad): loud[-1] + pad]
    x *= (32767 * 0.89) / np.abs(x).max()
    return x.astype("<i2")


def to_mp3(pcm: np.ndarray, out: Path) -> None:
    import imageio_ffmpeg

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", tmp,
                    "-codec:a", "libmp3lame", "-b:a", "64k", str(out)], check=True)
    os.remove(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=str(Path.home() / "Downloads" / "부트캠프" / ".env"))
    ap.add_argument("--model", default="gemini-3.8-flash-tts")
    ap.add_argument("--voice", default=",".join(VOICES), help="쉼표로 나눈 목소리들")
    ap.add_argument("--only", help="쉼표로 나눈 파일 이름들")
    ap.add_argument("--force", action="store_true", help="있는 파일도 다시 만든다")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sample", help="목소리 비교용 문장(experiments/voice/sample_<목소리>.mp3)")
    ap.add_argument("--voices", default="Zephyr,Kore,Leda,Puck,Fenrir")
    args = ap.parse_args()

    from google import genai
    client = genai.Client(api_key=load_key(args.env_file))

    if args.sample:
        out_dir = ROOT / "experiments" / "voice"
        out_dir.mkdir(parents=True, exist_ok=True)
        for v in args.voices.split(","):
            out = out_dir / f"sample_{v}.mp3"
            to_mp3(trim(synth(client, args.model, v, args.sample)), out)
            print(f"{v} → {out.relative_to(ROOT)}")
        return

    lines = json.loads((VOICE_DIR / "lines.json").read_text(encoding="utf-8"))
    if args.only:
        keep = set(args.only.split(","))
        lines = {k: v for k, v in lines.items() if k in keep}
    for voice in args.voice.split(","):
        out_dir = VOICE_DIR / voice
        out_dir.mkdir(exist_ok=True)
        todo = {k: v for k, v in lines.items() if args.force or not (out_dir / f"{k}.mp3").exists()}
        print(f"{voice}: {len(todo)}개 생성 (모델 {args.model})", flush=True)

        def one(item, voice=voice, out_dir=out_dir):
            key, text = item
            pcm = trim(synth(client, args.model, voice, spoken(text)))
            to_mp3(pcm, out_dir / f"{key}.mp3")
            sec = len(pcm) / RATE
            # 말에 비해 너무 길면 덧붙인 말이 섞였을 수 있다.
            warn = "  ← 길다, 들어 볼 것" if sec > 0.5 + 0.22 * len(text.replace(" ", "")) else ""
            print(f"{voice}/{key:24} {text:14} {sec:.2f}s{warn}", flush=True)
            return key, sec

        with ThreadPoolExecutor(args.workers) as ex:
            done = dict(ex.map(one, todo.items()))
        print(f"{voice} 끝: {len(done)}개", flush=True)
    (VOICE_DIR / "VOICE.md").write_text(
        "# 결과 음성\n\n"
        f"`tool/make_voice.py` 로 만든 파일. 모델 `{args.model}` (Gemini TTS), 목소리별 폴더.\n"
        "같은 이름의 mp3 로 바꿔 넣으면 그 소리를 쓴다(직접 녹음 가능). 목록은 `lines.json`.\n",
        encoding="utf-8")


if __name__ == "__main__":
    main()
