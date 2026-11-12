"""매장 실험 감독 도구. 노트북에서 Claude 가 태블릿(USB adb)과 헤드(HTTP)를 본다. 폰은 adb 로 붙이지 않는다.

절차는 docs/visit_supervision.md. 받은 기록은 experiments/visit_<날짜>/ (커밋 안 함).

용법:
  python supervise.py connect                무선 디버깅 기기를 찾아 붙임
  python supervise.py status                 기기·헤드·서버 상태 한 번
  python supervise.py head-set IP|주소        헤드 주소 저장. IP 만 주면 저장된 토큰을 그대로 씀
  python supervise.py head-qr                (폰을 adb 로 붙였을 때만) 폰 화면 QR 에서 주소·토큰 저장
  python supervise.py preview                헤드 최대 해상도 프레임 한 장 저장(거치·패 폭 확인)
  python supervise.py netdiag                태블릿 ↔ 헤드 네트워크 상태를 net/<시각>.txt 로(정상 때 한 번 떠 두면 비교용)
                                             태블릿에서 헤드가 안 될 때는 status·watch 가 알아서 남긴다
  python supervise.py shot [tablet|phone]    기기 화면 캡처 저장
  python supervise.py pull                   새 촬영 기록을 받음
  python supervise.py report [--since 시각]  받은 화료별 표와 요약
  python supervise.py watch [--since 시각]   새 화료·이상이 생길 때까지 기다렸다 이유를 찍고 끝남
  python supervise.py track [--all]          가장 최근 판 추적(track.json)만 바로 읽어 버림·리치·이벤트 요약
                                             (frames zip 은 안 받음. track.json 은 도라·리치봉 읽기 때 갱신 — 15초쯤 기다렸다 볼 것)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'vlm'))
from score_captures import DEFAULT_ADB, DEVICE_DIR, load_shots, score_shot  # noqa: E402

ADB = shutil.which('adb') or DEFAULT_ADB
APP = 'dev.jjh.mahjong_calc'
SERVER = 'https://mahjong.ai-agent-develop.cloud/'
VISIT = HERE.parent / f'visit_{datetime.now():%Y%m%d}'
HEAD_FILE = HERE.parent / 'visit_head.txt'  # 토큰은 새 QR 을 만들기 전까지 그대로라 날짜와 상관없이 둔다

BATTERY_MIN = 20  # 충전기 안 꽂힌 채 이 아래면 알림
TEMP_MAX_C = 42.0  # 헤드가 열로 프레임을 떨어뜨리기 전에 알림
SLOW_S = 20.0  # 체크리스트의 "취소하고 직접 입력" 강조 기준과 같게
HEAD_FAILS = 3  # 일시적 끊김은 넘기고 이어지면 알림


def adb(*args: str, serial: str | None = None, timeout: float = 30) -> str:
    cmd = [ADB] + (['-s', serial] if serial else []) + list(args)
    env = dict(os.environ, MSYS_NO_PATHCONV='1')
    r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    return r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')


def devices() -> dict[str, str]:
    """{역할: 시리얼}. 삼성 태블릿 모델은 SM-X, 그 밖의 기기는 폰으로 본다."""
    out: dict[str, str] = {}
    for line in adb('devices', '-l').splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2 or parts[1] != 'device':
            continue
        model = next((p[6:] for p in parts if p.startswith('model:')), '')
        role = 'tablet' if model.startswith(('SM_X', 'SM-X')) else 'phone'
        # 같은 기기가 USB·무선 둘로 보이면 먼저 나온 것 하나만
        out.setdefault(role, parts[0])
    return out


def device_state(serial: str) -> dict:
    bat = adb('shell', 'dumpsys', 'battery', serial=serial)
    level = re.search(r'^\s*level: (\d+)', bat, re.M)
    temp = re.search(r'^\s*temperature: (\d+)', bat, re.M)
    plugged = re.search(r'^\s*(AC|USB|Wireless) powered: true', bat, re.M)
    top = adb('shell', 'dumpsys activity activities | grep -m1 topResumedActivity', serial=serial)
    ip = re.search(r'inet (\d+\.\d+\.\d+\.\d+)',
                   adb('shell', 'ip -f inet addr show wlan0', serial=serial))
    return {
        'battery': int(level.group(1)) if level else None,
        'temp_c': int(temp.group(1)) / 10 if temp else None,
        'plugged': bool(plugged),
        'app_front': APP in top,
        'ip': ip.group(1) if ip else None,
    }


def device_alerts(role: str, st: dict) -> list[str]:
    alerts = []
    if not st['app_front']:
        alerts.append(f'{role}: 앱이 앞에 없음' + (' (헤드는 뒤로 가면 촬영 실패)' if role == 'phone' else ''))
    if st['battery'] is not None and st['battery'] < BATTERY_MIN and not st['plugged']:
        alerts.append(f'{role}: 배터리 {st["battery"]}%, 충전 안 됨')
    if st['temp_c'] is not None and st['temp_c'] >= TEMP_MAX_C:
        alerts.append(f'{role}: 온도 {st["temp_c"]}°C')
    return alerts


def head_url() -> str | None:
    return HEAD_FILE.read_text(encoding='utf-8').strip() if HEAD_FILE.exists() else None


def head_get(path: str, timeout: float = 5) -> tuple[bytes, dict]:
    """저장된 `http://IP:8765?t=토큰` 으로 GET."""
    base = head_url()
    if not base:
        raise RuntimeError('헤드 주소 없음 (head-set 먼저)')
    addr, _, token = base.partition('?t=')
    req = urllib.request.Request(addr + path, headers={'X-Head-Token': token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), {k.lower(): v for k, v in r.headers.items()}  # 헤드는 헤더 이름을 소문자로 보냄


def head_alert() -> str | None:
    if not head_url():
        return None
    try:
        status = json.loads(head_get('/status')[0])
        if not status.get('auth'):
            return '헤드 토큰이 맞지 않음 (새 QR?)'
        head_get('/preview?w=240')  # 폰 adb 없이 앱이 뒤로 갔는지 아는 길. /status 는 뒤로 가도 응답한다
    except (OSError, ValueError, urllib.error.URLError) as e:
        return f'헤드 프레임 못 받음 (폰 앱이 앞에 있는지 확인): {e}'
    return None


def tablet_head_alert(tablet: str) -> str | None:
    """태블릿에서 헤드로 가는 길. 노트북에서 된다고 태블릿에서도 되는 건 아니다(공유기가 무선끼리 막을 때)."""
    base = head_url()
    if not base:
        return None
    host, _, port = base.removeprefix('http://').partition('?')[0].partition(':')
    out = adb('shell', f'nc -z -w 3 {host} {port} </dev/null; echo rc=$?', serial=tablet)
    if 'rc=0' in out:
        return None
    return f'태블릿에서 헤드({host}:{port})로 연결 안 됨 (공유기·Wi-Fi 확인) — 진단 {net_diag(tablet)}'


def head_host() -> str | None:
    base = head_url()
    return base.removeprefix('http://').partition('?')[0].partition(':')[0] if base else None


def local(*cmd: str) -> str:
    """노트북(Windows) 명령. 출력이 한글 코드페이지라 mbcs 로 푼다."""
    r = subprocess.run(list(cmd), capture_output=True, timeout=20)
    enc = 'mbcs' if os.name == 'nt' else 'utf-8'
    return (r.stdout + r.stderr).decode(enc, 'replace')


def net_diag(tablet: str | None) -> Path:
    """태블릿 ↔ 폰 끊김(ping 실패·ARP 미완료, 10-30·10-31) 원인을 가리려고 그 순간을 남긴다.

    비교할 것: 태블릿 ip neigh 의 헤드 줄(FAILED/INCOMPLETE 인지, MAC) vs 노트북 arp 의 헤드 MAC
    (다르면 MAC 이 바뀐 것), 태블릿 → 공유기·노트북 ping(되면 두 기기 사이만 막힌 것),
    cmd wifi status 의 BSSID·주파수·MAC(재연결·대역 이동·랜덤 MAC).
    """
    host = head_host()
    out = VISIT / 'net' / f'{now_stamp()}.txt'
    out.parent.mkdir(parents=True, exist_ok=True)
    parts = [f'# {datetime.now():%Y-%m-%d %H:%M:%S} 헤드 {host}']
    if tablet:
        st = device_state(tablet)
        gw = re.search(r'default via (\S+)', adb('shell', 'ip route show table all', serial=tablet))
        sh = [
            'ip -f inet addr show wlan0',
            'ip neigh show dev wlan0',
            f'ping -c 3 -W 1 {host}' if host else 'true',
            f'ping -c 3 -W 1 {gw.group(1)}' if gw else 'echo 기본 경로 없음',
            'ip neigh show dev wlan0',  # ping 으로 ARP 를 다시 시도한 뒤 상태
            'cmd wifi status',
        ]
        if host:
            sh.insert(3, f'nc -z -w 3 {host} 8765 </dev/null; echo nc rc=$?')
        for c in sh:
            parts.append(f'\n## 태블릿$ {c}\n' + adb('shell', c, serial=tablet).rstrip())
        tablet_ip = st['ip']
    else:
        parts.append('\n(태블릿 adb 안 붙음)')
        tablet_ip = None
    if host:
        parts.append(f'\n## 노트북> ping {host}\n' + local('ping', '-n', '2', '-w', '1000', host).rstrip())
    if tablet_ip:
        parts.append(f'\n## 노트북> ping {tablet_ip}\n' + local('ping', '-n', '2', '-w', '1000', tablet_ip).rstrip())
    arp = local('arp', '-a')
    want = [ip for ip in (host, tablet_ip) if ip]
    parts.append('\n## 노트북> arp -a (헤드·태블릿 줄)\n' + '\n'.join(
        line for line in arp.splitlines() if any(re.search(rf'\b{re.escape(ip)}\b', line) for ip in want)))
    out.write_text('\n'.join(parts) + '\n', encoding='utf-8')
    return out


def server_state() -> str:
    t0 = time.time()
    try:
        with urllib.request.urlopen(SERVER, timeout=8) as r:
            sha = json.loads(r.read()).get('git_sha', '?')[:7]
        return f'서버 {sha} {time.time() - t0:.1f}초'
    except (OSError, ValueError) as e:
        return f'서버 응답 없음: {e}'


def remote_folders(serial: str) -> list[str]:
    out = adb('shell', f'ls {DEVICE_DIR}', serial=serial)
    return sorted(x for x in out.split() if re.fullmatch(r'\d{8}_\d{6}(_track)?', x))


def hands_after(serial: str, since: str) -> list[str]:
    return [d for d in remote_folders(serial) if not d.endswith('_track') and d > since]


def has_file(serial: str, folder: str, name: str) -> bool:
    return 'yes' in adb('shell', f'[ -f {DEVICE_DIR}/{folder}/{name} ] && echo yes', serial=serial)


def now_stamp() -> str:
    return f'{datetime.now():%Y%m%d_%H%M%S}'


# ---------------- 명령 ----------------

def cmd_connect(_) -> None:
    for line in adb('mdns', 'services').splitlines():
        m = re.search(r'_adb-tls-connect\._tcp\.?\s+(\S+:\d+)', line)
        if m:
            print(m.group(1), adb('connect', m.group(1)).strip())
    print(devices() or '붙은 기기 없음. 기기 무선 디버깅 켜기·페어링 확인')


def cmd_status(_) -> None:
    devs = devices()
    alerts = []
    if 'tablet' not in devs:
        alerts.append('tablet: adb 안 붙음')
    for role in ('tablet', 'phone'):
        if role not in devs:
            print(f'{role}: adb 안 붙음')
            continue
        st = device_state(devs[role])
        print(f'{role}: {devs[role]} 배터리 {st["battery"]}%{"(충전)" if st["plugged"] else ""} '
              f'{st["temp_c"]}°C 앱 앞={st["app_front"]} IP {st["ip"]}')
        alerts += device_alerts(role, st)
    print(server_state())
    if head_url():
        print('헤드(노트북에서):', head_alert() or '응답·토큰 정상')
        if 'tablet' in devs:
            alert = tablet_head_alert(devs['tablet'])
            print('헤드(태블릿에서):', alert or '연결됨')
            if alert:
                alerts.append(alert)
    else:
        print('헤드: 주소 모름 (head-set)')
    if 'tablet' in devs:
        hands = [d for d in remote_folders(devs['tablet']) if not d.endswith('_track')]
        print(f'태블릿 촬영 기록 {len(hands)}개, 마지막 {hands[-1] if hands else "-"}')
    for a in alerts:
        print('! ' + a)


def screencap(role: str) -> Path:
    serial = devices().get(role)
    if not serial:
        raise SystemExit(f'{role} 안 붙음')
    out = VISIT / 'screens' / f'{role}_{now_stamp()}.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MSYS_NO_PATHCONV='1')
    with out.open('wb') as f:
        subprocess.run([ADB, '-s', serial, 'exec-out', 'screencap', '-p'],
                       stdout=f, check=True, timeout=30, env=env)
    return out


def cmd_netdiag(_) -> None:
    print(net_diag(devices().get('tablet')))


def cmd_shot(a) -> None:
    print(screencap(a.role))


def cmd_head_set(a) -> None:
    addr = a.addr.removeprefix('http://')
    if '?t=' not in addr:
        old = head_url()
        if not old:
            raise SystemExit('저장된 토큰이 없음. 헤드 화면의 http://IP:8765?t=토큰 을 통째로 주기')
        addr = f'{addr.partition(":")[0]}:8765?t={old.partition("?t=")[2]}'
    HEAD_FILE.write_text(f'http://{addr}', encoding='utf-8')
    print(f'헤드 {addr.partition("?")[0]} 저장,', head_alert() or '응답·토큰 정상')


def cmd_head_qr(_) -> None:
    import cv2
    png = screencap('phone')
    text, _pts, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(png)))
    m = re.fullmatch(r'mahjongcam://([\d.]+:\d+)\?t=(\S+)', text or '')
    if not m:
        raise SystemExit(f'QR 을 못 읽음 ({png}). 폰이 헤드 화면인지 확인')
    HEAD_FILE.write_text(f'http://{m.group(1)}?t={m.group(2)}', encoding='utf-8')
    print(f'헤드 {m.group(1)} 저장')


def cmd_preview(_) -> None:
    body, headers = head_get('/preview?w=8192', timeout=20)
    out = VISIT / 'preview' / f'{now_stamp()}.jpg'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body)
    print(f'{out} 프레임 {headers.get("x-frame-size", "?")}, {len(body) // 1024}KB')


def cmd_pull(a) -> None:
    serial = devices().get('tablet')
    if not serial:
        raise SystemExit('tablet 안 붙음')
    dest = VISIT / 'captures'
    dest.mkdir(parents=True, exist_ok=True)
    for d in remote_folders(serial):
        if a.since and d < a.since:
            continue
        local = dest / d
        # 추적 폴더는 계속 자라고, 화료 폴더는 반영할 때 label.json 이 늦게 생긴다
        if not d.endswith('_track') and (local / 'label.json').exists():
            continue
        adb('pull', f'{DEVICE_DIR}/{d}', str(dest), serial=serial, timeout=300)
    print(f'{dest} 에 {sum(1 for _ in dest.iterdir())}개')


def cmd_report(a) -> None:
    rows = []
    for name, meta, label in load_shots(VISIT / 'captures', a.since):
        r = score_shot(meta, label)
        rows.append(r)
        sec = (r['latency_ms'] or 0) / 1000
        calls = meta.get('call_ms') or {}
        slow = max(calls, key=calls.get) if calls else '-'
        flags = ' '.join(f.split(':')[0] for f in r['flags']) or '-'
        answer = '정답없음' if not label else ('맞음' if r['all'] else '틀림 ' + ','.join(
            k for k in ('hand', 'red', 'winner', 'tsumo', 'loser', 'riichi', 'dora', 'ura') if r.get(k) is False))
        print(f'{name} {(meta.get("game") or {}).get("round", "?")} {meta.get("winner_side", "?")} '
              f'{sec:.1f}초(가장 느린 호출 {slow}) 경고 {len(meta.get("warnings") or [])} '
              f'오류 {meta.get("error") or "-"} | {flags} | {answer}')
    if not rows:
        print('기록 없음')
        return
    secs = sorted(r['latency_ms'] / 1000 for r in rows if r['latency_ms'])
    labeled = [r for r in rows if r['labeled']]
    if secs:
        p90 = secs[min(len(secs) - 1, int(0.9 * len(secs)))]
        print(f'시간 중앙 {statistics.median(secs):.1f} / p90 {p90:.1f} / 최대 {secs[-1]:.1f}초, '
              f'{SLOW_S:.0f}초 넘음 {sum(s > SLOW_S for s in secs)}/{len(secs)}')
    print(f'맞은 수 {sum(1 for r in labeled if r["all"])}/{len(labeled)}, 정답 없음 {len(rows) - len(labeled)}')


def cmd_watch(a) -> None:
    """알릴 일이 생기면 한 줄 찍고 끝난다. 호출한 쪽이 처리하고 다시 부른다."""
    since = a.since or now_stamp()
    head_fails = 0
    deadline = time.time() + a.max_minutes * 60
    while time.time() < deadline:
        devs = devices()
        if 'tablet' not in devs:
            print('ALERT tablet: adb 끊김')
            return
        for role, serial in devs.items():
            for alert in device_alerts(role, device_state(serial)):
                print('ALERT ' + alert)
                return
        alert = head_alert() or tablet_head_alert(devs['tablet'])
        head_fails = head_fails + 1 if alert else 0
        if head_fails >= HEAD_FAILS:
            print('ALERT ' + alert)
            return
        tablet = devs['tablet']
        for d in hands_after(tablet, since):
            if has_file(tablet, d, 'meta.json'):
                print(f'NEW_HAND {d}')
                return
        for d in a.pending:
            if has_file(tablet, d, 'label.json'):
                print(f'LABELED {d}')
                return
        time.sleep(a.every)
    print('TIMEOUT 새 일 없음')


SIDES = ['bottom', 'right', 'top', 'left']
SIDE_KO = {'bottom': '아래', 'right': '오른쪽', 'top': '위', 'left': '왼쪽'}


def summarize_track(j: dict, show_all: bool = False) -> list[str]:
    """track.json 한 개를 사람이 읽을 몇 줄로. 자리 이름은 bottom_seat·names 로 붙인다."""
    names = j.get('names') or []
    bottom = j.get('bottom_seat') or 0

    def who(side: str) -> str:
        if side not in SIDES:
            return side
        seat = (bottom + SIDES.index(side)) % 4
        n = names[seat] if seat < len(names) else ''
        return f'{SIDE_KO[side]}({n})' if n else SIDE_KO[side]

    rv = j.get('rivers') or {}
    per = rv.get('rivers') or {}
    lines = [f"판 {j.get('round', '?')} · 입력 긴 변 {j.get('preview_long_side')}"]
    lines.append('버림 수: ' + ' · '.join(f"{who(s)} {per.get(s, {}).get('discards', 0)}" for s in SIDES))
    last = next((per[s]['last'] for s in SIDES if per.get(s, {}).get('last')), None)
    riichi = rv.get('riichi') or []
    lines.append('리치: ' + (', '.join(who(s) for s in riichi) if riichi else '없음'))
    melds = {s: len(v.get('melds') or []) for s, v in (j.get('seats') or {}).items()}
    if any(melds.values()):
        lines.append('울기: ' + ' · '.join(f'{who(s)} {n}' for s, n in melds.items() if n))
    # rebase 는 울기·강 추적기가 같이 남겨 두 번씩 찍힌다 → 강 쪽만 센다. 평소 대국에도 손이 지나가면 판당 수십 번 나와(11-07 매장
    # 판당 20~70) 그 자체로는 이상이 아니다.
    ev = [(e, 'river') for e in rv.get('events') or []] + [(e, 'meld') for e in j.get('events') or [] if e.get('kind') != 'rebase']
    ev.sort(key=lambda x: x[0].get('at', ''))
    counts: dict[str, int] = {}
    for e, _ in ev:
        counts[e['kind']] = counts.get(e['kind'], 0) + 1
    lines.append('이벤트 수: ' + (', '.join(f'{k} {v}' for k, v in sorted(counts.items())) or '없음'))
    pixel = sum(1 for e, _ in ev if e['kind'] == 'sticks_confirmed' and e.get('detail', '').startswith('픽셀'))
    lines.append(f"리치봉: 픽셀 확정 {pixel} · 서버 읽기 {counts.get('sticks_candidate', 0) + counts.get('sticks_failed', 0)}번"
                 f"(실패 {counts.get('sticks_failed', 0)} — 자체 판독 모드면 서버를 안 불러 실패가 정상, 리치는 픽셀 확정)")
    if not counts.get('discard'):
        lines.append('⚠ 버림 이벤트 0 — 추적이 안 돌거나 강 칸이 어긋남(더보기 "판 상태 추적" 문구에 "(격자를 맞추면 시작)" 있는지)')
    else:
        lines.append(f"✓ 버림 이벤트 {counts['discard']}개 잡힘")
    shown = ev if show_all else ev[-12:]
    if shown:
        lines.append(f"최근 이벤트 {len(shown)}/{len(ev)}:")
        for e, _ in shown:
            k, d = e['kind'], e.get('detail', '')
            # 리치봉 서버 읽기·장면 이벤트는 자리 없이 bottom 으로 남는다 — 자리를 붙이지 않는다
            seated = k in ('discard', 'cleared', 'taken', 'changed', 'confirmed', 'sticks_seen') or (k == 'sticks_confirmed' and d.startswith('픽셀'))
            if k in ('sticks_confirmed', 'sticks_candidate') and not d.startswith('픽셀'):
                d = ' '.join(who(x) for x in d.split()) if d != '없음' else d
            t = e.get('at', '')[11:19]
            lines.append(f"  {t} {who(e.get('side', '')) if seated else '-'} {k} {d}".rstrip())
    return lines


def cmd_track(a) -> None:
    serial = devices().get('tablet')
    if not serial:
        raise SystemExit('tablet 안 붙음')
    tracks = [d for d in remote_folders(serial) if d.endswith('_track')]
    for d in reversed(tracks):
        r = subprocess.run([ADB, '-s', serial, 'exec-out', 'cat', f'{DEVICE_DIR}/{d}/track.json'],
                           capture_output=True, timeout=30, env=dict(os.environ, MSYS_NO_PATHCONV='1'))
        if r.returncode == 0 and r.stdout.strip().startswith(b'{'):
            out = VISIT / 'track' / f'{d}_{now_stamp()}.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.stdout)
            print(f'{d}/track.json ({out})')
            print('\n'.join(summarize_track(json.loads(r.stdout.decode('utf-8')), a.all)))
            return
        if not a.all:
            print(f'{d}: track.json 아직 없음(도라·리치봉 읽기 전) — 15초쯤 뒤 다시')
            return
    print('추적 폴더 없음 — 추적이 한 번도 안 돌았음')


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('connect').set_defaults(fn=cmd_connect)
    sub.add_parser('status').set_defaults(fn=cmd_status)
    sub.add_parser('head-qr').set_defaults(fn=cmd_head_qr)
    s = sub.add_parser('head-set')
    s.add_argument('addr')
    s.set_defaults(fn=cmd_head_set)
    sub.add_parser('preview').set_defaults(fn=cmd_preview)
    sub.add_parser('netdiag').set_defaults(fn=cmd_netdiag)
    s = sub.add_parser('pull')
    s.add_argument('--since')
    s.set_defaults(fn=cmd_pull)
    s = sub.add_parser('shot')
    s.add_argument('role', nargs='?', default='tablet', choices=['tablet', 'phone'])
    s.set_defaults(fn=cmd_shot)
    s = sub.add_parser('report')
    s.add_argument('--since')
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser('watch')
    s.add_argument('--since', help='이 시각 뒤의 화료만 새 것으로 (기본: 지금)')
    s.add_argument('--pending', nargs='*', default=[], help='label.json 을 기다리는 화료 폴더')
    s.add_argument('--every', type=float, default=15)
    s.add_argument('--max-minutes', type=float, default=30)
    s.set_defaults(fn=cmd_watch)
    s = sub.add_parser('track')
    s.add_argument('--all', action='store_true', help='이벤트 전부, track.json 없으면 이전 판까지')
    s.set_defaults(fn=cmd_track)
    a = p.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
