"""사본 앱 화면 조작 도우미(adb uiautomator): python -X utf8 experiments/ondevice/ui.py <명령…>
  dump             보이는 글자 목록
  tap <글자>       그 글자를 가진 요소 가운데를 누름
  xy <x> <y>       좌표 누름
  type <글자>      입력
  shot <이름>      화면 캡처 → experiments/ondevice/build/shots/<이름>.png (절반 크기 _s 도)
"""
import re, subprocess, sys
from pathlib import Path
ADB = r"C:\Users\jjh7757\dev\android-sdk\platform-tools\adb.exe"
SHOTS = Path(__file__).parent / "build" / "shots"


def sh(*a):
    return subprocess.run([ADB, "shell", *a], capture_output=True).stdout.decode("utf8", "replace")


def nodes():
    sh("uiautomator", "dump", "/sdcard/ui_ondevice.xml")
    x = sh("cat", "/sdcard/ui_ondevice.xml")
    sh("rm", "/sdcard/ui_ondevice.xml")
    out = []
    for m in re.finditer(r"<node [^>]*>", x):
        n = m.group(0)
        g = lambda k: (re.search(k + r'="([^"]*)"', n) or [None, ""])[1]
        b = list(map(int, re.findall(r"\d+", g("bounds"))))
        if len(b) == 4 and (g("text") or g("content-desc")):
            out.append({"t": g("text"), "d": g("content-desc"), "b": b})
    return out


cmd = sys.argv[1]
if cmd == "dump":
    for n in nodes():
        print(n["b"], repr(n["t"] or n["d"])[:80])
elif cmd == "tap":
    want = sys.argv[2]
    for n in nodes():
        if want in (n["t"] or "") or want in (n["d"] or ""):
            b = n["b"]
            sh("input", "tap", str((b[0] + b[2]) // 2), str((b[1] + b[3]) // 2))
            print("눌렀음", b, (n["t"] or n["d"])[:40])
            break
    else:
        print("못 찾음", want)
elif cmd == "xy":
    sh("input", "tap", sys.argv[2], sys.argv[3])
elif cmd == "type":
    sh("input", "text", sys.argv[2])
elif cmd == "shot":
    from PIL import Image
    SHOTS.mkdir(parents=True, exist_ok=True)
    p = SHOTS / f"{sys.argv[2]}.png"
    p.write_bytes(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)
    im = Image.open(p)
    im.resize((im.width // 2, im.height // 2)).save(SHOTS / f"{sys.argv[2]}_s.png")
    print(p)
