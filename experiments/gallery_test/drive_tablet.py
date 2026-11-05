"""태블릿 실기기에서 갤러리 사진 판독을 adb 로 차례로 돌린다(2026-11-05, 사용자 "너가 태블릿 조작해서 시간·정확도 재줘").

키오스크 거치 화면(대국 중) → "갤러리" → 사진 고르기 창 컬렉션 → 이 기기에서 → "마작테스트" 앨범 → i 번째 칸 → 완료 →
앱이 펠트 격자로 바로 읽음 → 결과 화면 → 뒤로(대국에 반영 안 함). 촬영 기록(Download/mahjong_calc/<시각>/)이 새로 생기면 끝으로 본다.
어느 사진이었는지는 나중에 score_tablet.py 가 기록의 original.jpg 를 원본과 맞춰 정한다(앨범 칸 순서 ≠ 파일 이름 순서).
  python -X utf8 experiments/gallery_test/drive_tablet.py <tag> [시작 칸] [끝 칸] [사이 초]
  → experiments/speed/results/tablet_gallery_<tag>.jsonl (칸, 기록 폴더, 완료 → 기록 초, 결과 화면 글자)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ADB = r"C:\Users\jjh7757\dev\android-sdk\platform-tools\adb.exe"
DIR = "/sdcard/Download/mahjong_calc"
ROOT = Path(__file__).resolve().parents[2]
N = 26


def sh(*a: str) -> str:
    return subprocess.run([ADB, "shell", *a], capture_output=True).stdout.decode("utf8", "replace")


def tap(x: int, y: int) -> None:
    sh("input", "tap", str(x), str(y))


def nodes() -> list[dict]:
    sh("uiautomator", "dump", "/sdcard/ui.xml")
    x = sh("cat", "/sdcard/ui.xml")
    out = []
    for m in re.finditer(r"<node [^>]*>", x):
        n = m.group(0)
        g = lambda k: (re.search(k + r'="([^"]*)"', n) or [None, ""])[1]
        b = list(map(int, re.findall(r"\d+", g("bounds"))))
        if len(b) == 4:
            out.append({"t": g("text"), "d": g("content-desc"), "b": b, "on": g("enabled") == "true"})
    return out


def find(ns, s):
    for n in ns:
        if n["t"] == s or n["d"] == s:
            return n
    return None


def center(n) -> tuple[int, int]:
    b = n["b"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2


def records() -> set[str]:
    return {l.strip() for l in sh("ls", DIR).split() if re.fullmatch(r"\d{8}_\d{6}", l.strip())}


def wait_for(pred, timeout: float, step: float = 0.6):
    end = time.time() + timeout
    while time.time() < end:
        ns = nodes()
        r = pred(ns)
        if r:
            return ns, r
        time.sleep(step)
    return None, None


def to_kiosk() -> None:
    for _ in range(8):
        ns = nodes()
        if find(ns, "이 격자로 읽기") and find(ns, "취소"):  # 갤러리 격자 맞추기 화면
            tap(*center(find(ns, "취소")))
            time.sleep(1.5)
            continue
        if find(ns, "갤러리") and find(ns, "화료 촬영"):
            return
        if find(ns, "컬렉션") or find(ns, "이 기기에서") or find(ns, "마작테스트") or find(ns, "무엇으로 났나요"):  # 사진 고르기 창·후보 창
            sh("input", "keyevent", "4")
            time.sleep(1.5)
            continue
        home = next((n for n in ns if (n["t"] or n["d"]).startswith("대국 이어 하기")), None)
        if home:  # 앱 첫 화면(단추 이름 뒤에 국·점수 줄이 붙는다)
            tap(*center(home))
            time.sleep(2)
            continue
        if not any(n["t"] or n["d"] for n in ns if "대국" in (n["t"] + n["d"]) or "판독" in (n["t"] + n["d"])):
            # 앱 밖(키오스크에서 뒤로 가면 홈으로 나간다): 다시 띄운다
            sh("monkey", "-p", "dev.jjh.mahjong_calc", "-c", "android.intent.category.LAUNCHER", "1")
            time.sleep(3)
            continue
        sh("input", "keyevent", "4")
        time.sleep(1.5)
    raise RuntimeError("키오스크 화면으로 못 돌아감")


def screen() -> tuple[int, int]:
    """지금 방향의 화면 가로·세로(UI 덤프의 가장 큰 상자)."""
    sh("uiautomator", "dump", "/sdcard/ui.xml")
    bs = [list(map(int, re.findall(r"\d+", b))) for b in re.findall(r'bounds="([^"]*)"', sh("cat", "/sdcard/ui.xml"))]
    return max(((b[2], b[3]) for b in bs if len(b) == 4), key=lambda wh: wh[0] * wh[1])


def swipe_up(sheet: list[dict]) -> None:
    """사진 고르기 창 안에서 위로 밀기(가로·세로 화면 모두: 창의 가운데 세로줄에서)."""
    W, H = screen()
    xs = [n["b"][0] for n in sheet] + [n["b"][2] for n in sheet]
    x = (min(xs) + max(xs)) // 2 if xs else W // 2
    sh("input", "swipe", str(x), str(int(H * .8)), str(x), str(int(H * .35)), "400")


def full(n, H: int) -> bool:
    """누를 만큼 보이는 칸: 위 끝이 아래 탐색 막대(약 70px)보다 충분히 위. 누르는 곳은 [visible_center]."""
    return n["b"][1] < H - 160 and n["b"][3] - n["b"][1] > 150


def visible_center(n, H: int) -> tuple[int, int]:
    b = n["b"]
    return (b[0] + b[2]) // 2, (b[1] + min(b[3], H - 80)) // 2


def open_album() -> list[dict]:
    tap(*center(find(nodes(), "갤러리")))
    _, H = screen()
    for _ in range(20):
        time.sleep(1.0)
        ns = nodes()
        if find(ns, "닫기"):  # 클라우드 미디어 안내
            tap(*center(find(ns, "닫기")))
            continue
        cells = [n for n in ns if n["d"].endswith("촬영한 사진")]
        title = find(ns, "마작테스트")
        if title and cells and not find(ns, "이 기기에서"):
            return ns  # 앨범 안
        if find(ns, "이 기기에서"):
            n, back = find(ns, "이 기기에서"), find(ns, "뒤로")
            inside = back and abs(back["b"][1] - n["b"][1]) < 30  # 뒤로 단추와 같은 줄이면 제목(안), 아니면 컬렉션 목록의 묶음 이름
            if not inside:
                tap(*center(n))
            elif title and title["b"][1] < H - 160:  # 보이는 부분(아래 탐색 막대 위)의 가운데를 누른다
                b = title["b"]
                tap((b[0] + b[2]) // 2, (b[1] + min(b[3], H - 80)) // 2)
            else:  # 촬영 기록 폴더가 앨범으로 쌓여 마작테스트가 아래로 밀린다
                swipe_up([x for x in ns if x["d"] or x["t"]])
            continue
        if find(ns, "컬렉션"):
            tap(*center(find(ns, "컬렉션")))
            continue
    raise RuntimeError("마작테스트 앨범을 못 엶")


def pick(i: int) -> None:
    ns = open_album()
    _, H = screen()
    allc = lambda ns: sorted([n for n in ns if n["d"].endswith("촬영한 사진")], key=lambda n: (n["b"][1], n["b"][0]))
    top = allc(ns)  # 맨 위: 보이는 칸이 0 번부터
    n = top[i] if i < len(top) and full(top[i], H) else None
    if n is None:  # 맨 아래로 내려 끝에서 센다: 보이는 칸들의 절대 번호 = N - len(보이는 칸) + k
        for _ in range(4):
            swipe_up(ns)
            time.sleep(0.7)
        time.sleep(1)
        last = allc(nodes())
        idx = {N - len(last) + k: c for k, c in enumerate(last)}
        n = idx.get(i)
        if n is None or not full(n, H):
            raise RuntimeError(f"칸 {i} 이 맨 위에도 맨 아래에도 온전히 안 보임")
    tap(*visible_center(n, H))
    time.sleep(1.0)
    ns = nodes()
    tap(*center(find(ns, "완료")))


def main() -> None:
    tag = sys.argv[1]
    a = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    z = int(sys.argv[3]) if len(sys.argv) > 3 else N - 1
    gap = float(sys.argv[4]) if len(sys.argv) > 4 else 15
    out = ROOT / "experiments/speed/results" / f"tablet_gallery_{tag}.jsonl"
    for i in range(a, z + 1):
        to_kiosk()
        before = records()
        pick(i)
        t0 = time.time()
        rec, t_rec, felt_fail, auto_s, t_dialog = None, None, None, None, None
        k = 0
        while time.time() - t0 < 150:
            new = records() - before
            if new:
                rec, t_rec = sorted(new)[-1], time.time() - t0
                break
            k += 1
            if k % 3 == 0:  # 가끔 화면도 본다(덤프가 1초쯤 걸림)
                ns = nodes()
                if felt_fail is None and find(ns, "이 격자로 읽기"):
                    # 펠트를 못 찾아 격자 맞추기 화면: 사용자가 하듯 "자동 맞추기"(서버 /v2/setup) → "이 격자로 읽기"
                    felt_fail = round(time.time() - t0, 2)
                    for _ in range(3):  # "펠트를 못 찾았습니다" 안내가 세로 화면에서 아래 단추들을 덮는다 — 먼저 닫는다
                        c = find(ns, "닫기")
                        if c is None:
                            break
                        tap(*center(c))
                        time.sleep(1)
                        ns = nodes()
                    tap(*center(find(ns, "자동 맞추기")))
                    t_a = time.time()
                    time.sleep(1.5)
                    for _ in range(90):  # 맞추는 동안 버튼이 꺼진다(_setupBusy), 다시 켜지면 끝
                        b = find(nodes(), "자동 맞추기")
                        if b is None or b["on"]:
                            break
                        time.sleep(0.5)
                    auto_s = round(time.time() - t_a, 2)
                    ns = nodes()
                    for _ in range(3):  # 자동 맞추기 결과 안내도 단추를 덮는다
                        c = find(ns, "닫기")
                        if c is None:
                            break
                        tap(*center(c))
                        time.sleep(1)
                        ns = nodes()
                    tap(*center(find(ns, "이 격자로 읽기")))
                elif t_dialog is None and any("무엇으로 났나요" in (n["t"] + n["d"]) for n in ns):
                    # 화료패 후보 고르기 창: 시간을 적고 닫는다(입력 화면으로 가고 기록이 저장됨, 채점은 후보로 "고르면 맞음")
                    t_dialog = round(time.time() - t0, 2)
                    sh("input", "keyevent", "4")
            time.sleep(0.3)
        ns, screen = wait_for(lambda ns: [n["t"] or n["d"] for n in ns if (n["t"] or n["d"]) in ("판독 수정", "직접 고치기", "대국에 반영 (동1국)", "화료패를 고르세요")]
                              or [n["t"] or n["d"] for n in ns if "화료패" in (n["t"] + n["d"])][:1], 20)
        t_screen = time.time() - t0
        texts = [x for x in ((n["t"] or n["d"]) for n in (ns or nodes())) if x][:40]
        row = {"cell": i, "record": rec, "t_record_s": round(t_rec, 2) if t_rec else None, "t_screen_s": round(t_screen, 2),
               "felt_fail_s": felt_fail, "auto_setup_s": auto_s, "win_dialog_s": t_dialog,
               "screen": screen, "texts": texts, "at": time.strftime("%H:%M:%S")}
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(i, rec, row["t_record_s"], screen, flush=True)
        to_kiosk()
        time.sleep(gap)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
