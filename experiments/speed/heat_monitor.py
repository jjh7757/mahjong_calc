"""헤드 휴대폰 발열 기록(2026-11-12): 30초마다 발열 단계·센서 온도(AP·SKIN·BAT·PA·USB)·배터리(잔량·충전량·전류·충전 중)와
가장 최근 녹화 폴더의 저장 장수·record.json(스트림 속도·버림)을 한 줄 JSON 으로.

  python -I experiments/speed/heat_monitor.py <adb 시리얼> <출력.jsonl> <초> [간격=30]
"""
import json, os, re, subprocess, sys, time
ADB = r"C:/Users/jjh7757/dev/android-sdk/platform-tools/adb.exe"
S, OUT, DUR = sys.argv[1], sys.argv[2], float(sys.argv[3])
GAP = float(sys.argv[4]) if len(sys.argv) > 4 else 30
REC = "/sdcard/Android/data/dev.jjh.mahjong_calc.ondevice/files/rec"
env = dict(os.environ, MSYS_NO_PATHCONV="1")


def sh(cmd):
    try:
        return subprocess.run([ADB, "-s", S, "shell", cmd], capture_output=True, text=True, timeout=30, env=env).stdout
    except Exception:
        return ""


end = time.time() + DUR
with open(OUT, "a", encoding="utf-8") as f:
    while time.time() < end:
        t0 = time.time()
        th = sh("dumpsys thermalservice")
        temps = {m.group(2): float(m.group(1)) for m in re.finditer(r"Temperature\{mValue=([\d.]+), mType=\d+, mName=(\w+)", th.split("Current cooling")[0].split("Current temperatures from HAL")[-1])}
        st = re.search(r"Thermal Status: (\d+)", th)
        b = sh("dumpsys battery")
        def g(k):
            m = re.search(rf"\n\s*{k}: (-?\d+)", b)
            return int(m.group(1)) if m else None
        last = sh(f"ls -t {REC} | head -1").strip()
        n = sh(f"ls {REC}/{last} | wc -l").strip()
        rj = sh(f"cat {REC}/{last}/record.json")
        try:
            rj = json.loads(rj)
            rec = {"saved": rj.get("saved"), "dropped": rj.get("dropped"), "final": rj.get("final"), "streamFps": rj.get("streamFps", {}).get("recent"), "writtenAtMs": rj.get("writtenAtMs")}
        except Exception:
            rec = None
        top = re.search(r"topResumedActivity=\S+ \S+ (\S+)", sh("dumpsys activity activities | grep -m1 topResumedActivity"))
        row = {"t": round(t0, 1), "status": int(st.group(1)) if st else None, "temps": temps,
               "level": g("level"), "cc": g("Charge counter"), "current_now": g("current now"), "bat_temp": g("temperature"),
               "usb": "USB powered: true" in b, "rec_dir": last, "files": int(n) if n.isdigit() else None, "rec": rec,
               "top": top.group(1) if top else None}
        f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
        time.sleep(max(0, GAP - (time.time() - t0)))
