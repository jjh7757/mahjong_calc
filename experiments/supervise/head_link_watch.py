"""태블릿 → 헤드(폰) 연결이 왜 끊기는지 오래 지켜보는 도구(2026-11-06, 사용자 "1시간 동안 연결해 보면서 끊기는지").

10-30 집·10-31 매장에서 태블릿 ↔ 폰만 끊기고(서로 ping 실패·ARP 미완료) 노트북 → 폰은 정상이었다.
그 순간을 잡으려고 몇 초마다 같은 시각에 두 길을 잰다.

- 태블릿 → 헤드: `nc` 8765, ping, `ip neigh`(ARP 상태·MAC), 태블릿 → 공유기 ping
- 노트북 → 헤드: `/status`(토큰 없이), `/preview?w=240`(30초마다, 폰 앱이 앞인지), ping, `arp -a` 의 헤드 MAC
- 30초마다 태블릿 `cmd wifi status`(BSSID·주파수·RSSI·링크 속도)·화면 상태·앱 앞
- 태블릿 logcat 중 Wi-Fi·네트워크·flutter 줄만 따로 저장
- 태블릿 쪽이 끊기는 순간 supervise.net_diag + 태블릿 화면 캡처

용법: python head_link_watch.py [--minutes 65] [--interval 5]
결과: experiments/visit_<날짜>/link/<시작>/ (probes.jsonl, events.txt, logcat.txt, summary.json)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import supervise as sv

LOGCAT_KEEP = re.compile(
    r'wifi|wpa|supplicant|dhcp|connectivity|networkmonitor|netd|wlan|roam|arp|neigh|'
    r'flutter|mahjong|deviceidle|doze|powermanager|sleep|disconnect|beacon|bssid',
    re.I)


def tablet_probe(serial: str, host: str, gw: str | None) -> dict:
    sh = (f'nc -z -w 2 {host} 8765 </dev/null >/dev/null 2>&1; echo nc=$?; '
          f'ping -c 1 -W 1 {host} >/dev/null 2>&1; echo ping=$?; '
          f'echo neigh=$(ip neigh show {host}); ')
    if gw:
        sh += f'ping -c 1 -W 1 {gw} >/dev/null 2>&1; echo gw=$?; '
    t0 = time.time()
    out = sv.adb('shell', sh, serial=serial, timeout=15)
    r = {'t_ms': round((time.time() - t0) * 1000)}
    for k in ('nc', 'ping', 'gw'):
        m = re.search(rf'^{k}=(\d+)', out, re.M)
        r[k] = int(m.group(1)) if m else None
    m = re.search(r'^neigh=(.*)$', out, re.M)
    r['neigh'] = m.group(1).strip() if m else out.strip()[:200]
    return r


def tablet_wifi(serial: str) -> dict:
    out = sv.adb('shell', 'cmd wifi status; dumpsys power | grep -m1 mWakefulness=; '
                 'dumpsys activity activities | grep -m1 topResumedActivity', serial=serial, timeout=15)
    r: dict = {}
    for key, pat in (('bssid', r'BSSID: ([0-9a-f:]{17})'), ('freq', r'Frequency: (\d+)'),
                     ('rssi', r'RSSI: (-?\d+)'), ('link', r'Link speed: (\d+)'),
                     ('ssid', r'SSID: "([^"]*)"'), ('wake', r'mWakefulness=(\w+)')):
        m = re.search(pat, out)
        r[key] = m.group(1) if m else None
    r['wifi_on'] = 'Wifi is enabled' in out
    r['app_front'] = sv.APP in out
    return r


def laptop_probe(host: str, with_preview: bool) -> dict:
    r: dict = {}
    t0 = time.time()
    try:
        with urllib.request.urlopen(f'http://{host}:8765/status', timeout=2) as resp:
            resp.read()
        r['status'] = round((time.time() - t0) * 1000)
    except (OSError, urllib.error.URLError) as e:
        r['status'] = None
        r['status_err'] = str(e)[:80]
    if with_preview:
        t0 = time.time()
        try:
            sv.head_get('/preview?w=240', timeout=4)
            r['preview'] = round((time.time() - t0) * 1000)
        except (OSError, ValueError, urllib.error.URLError) as e:
            r['preview'] = None
            r['preview_err'] = str(e)[:80]
    ping = sv.local('ping', '-n', '1', '-w', '1000', host)
    r['ping'] = bool(re.search(r'TTL=', ping, re.I))
    if with_preview:
        line = next((x for x in sv.local('arp', '-a').splitlines()
                     if re.search(rf'\b{re.escape(host)}\b', x)), '')
        r['arp'] = line.split()[1] if len(line.split()) > 1 else None
    return r


def logcat_thread(serial: str, path, stop: threading.Event) -> subprocess.Popen:
    sv.adb('logcat', '-c', serial=serial)  # 지난 로그는 버리고 지금부터
    p = subprocess.Popen([sv.ADB, '-s', serial, 'logcat', '-v', 'threadtime'],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def run():
        with path.open('w', encoding='utf-8') as f:
            for raw in p.stdout:
                line = raw.decode('utf-8', 'replace')
                if LOGCAT_KEEP.search(line):
                    f.write(line)
                    f.flush()
                if stop.is_set():
                    break
    threading.Thread(target=run, daemon=True).start()
    return p


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--minutes', type=float, default=65)
    ap.add_argument('--interval', type=float, default=5)
    a = ap.parse_args()

    tablet = sv.devices().get('tablet')
    host = sv.head_host()
    if not tablet or not host:
        raise SystemExit(f'태블릿 {tablet} / 헤드 {host} — 둘 다 있어야 함')
    gw_m = re.search(r'default via (\S+)', sv.adb('shell', 'ip route show table all', serial=tablet))
    gw = gw_m.group(1) if gw_m else None
    out = sv.VISIT / 'link' / sv.now_stamp()
    out.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    lc = logcat_thread(tablet, out / 'logcat.txt', stop)
    events = (out / 'events.txt').open('w', encoding='utf-8')

    def event(msg: str) -> None:
        line = f'{datetime.now():%H:%M:%S} {msg}'
        print(line, flush=True)
        events.write(line + '\n')
        events.flush()

    event(f'시작 태블릿 {tablet} 헤드 {host} 공유기 {gw} → {out}')
    event('기준 진단 ' + str(sv.net_diag(tablet)))
    end = time.time() + a.minutes * 60
    n = 0
    prev_tab = prev_lap = None
    wifi: dict = {}
    outages: list[dict] = []
    cur: dict | None = None
    with (out / 'probes.jsonl').open('w', encoding='utf-8') as f:
        while time.time() < end:
            t_start = time.time()
            slow = n % max(1, round(30 / a.interval)) == 0
            rec = {'ts': f'{datetime.now():%H:%M:%S}'}
            res: dict = {}
            th = threading.Thread(target=lambda: res.update(lap=laptop_probe(host, slow)))
            th.start()
            try:
                rec['tab'] = tablet_probe(tablet, host, gw)
            except subprocess.TimeoutExpired:
                rec['tab'] = {'nc': None, 'adb_timeout': True}
            if slow:
                try:
                    w = tablet_wifi(tablet)
                    if wifi and (w.get('bssid'), w.get('freq'), w.get('ip')) != (wifi.get('bssid'), wifi.get('freq'), wifi.get('ip')):
                        event(f'Wi-Fi 바뀜 {wifi.get("bssid")}/{wifi.get("freq")} → {w.get("bssid")}/{w.get("freq")}')
                    if wifi and w.get('wake') != wifi.get('wake'):
                        event(f'태블릿 화면 {wifi.get("wake")} → {w.get("wake")}')
                    if wifi and w.get('app_front') != wifi.get('app_front'):
                        event(f'태블릿 앱 앞 {wifi.get("app_front")} → {w.get("app_front")}')
                    wifi = w
                    rec['wifi'] = w
                except subprocess.TimeoutExpired:
                    rec['wifi'] = {'adb_timeout': True}
            th.join()
            rec['lap'] = res.get('lap', {})
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()

            tab_ok = rec['tab'].get('nc') == 0
            lap_ok = rec['lap'].get('status') is not None
            if prev_tab is not None and tab_ok != prev_tab:
                if not tab_ok:
                    t = rec['tab']
                    event(f'끊김(태블릿→헤드) nc={t.get("nc")} ping={t.get("ping")} gw={t.get("gw")} '
                          f'neigh="{t.get("neigh")}" | 노트북 status={rec["lap"].get("status")} ping={rec["lap"].get("ping")}')
                    cur = {'start': rec['ts'], 'lap_ok_at_start': lap_ok, 'gw_ok_at_start': t.get('gw') == 0,
                           'neigh_at_start': t.get('neigh')}
                    try:
                        cur['diag'] = str(sv.net_diag(tablet))
                        cur['shot'] = str(sv.screencap('tablet'))
                    except Exception as e:  # 진단 실패로 감시를 멈추지 않는다
                        cur['diag_err'] = str(e)
                    event(f'  진단 {cur.get("diag")} 화면 {cur.get("shot")}')
                else:
                    event(f'다시 붙음(태블릿→헤드) neigh="{rec["tab"].get("neigh")}"')
                    if cur:
                        cur['end'] = rec['ts']
                        outages.append(cur)
                        cur = None
            if prev_lap is not None and lap_ok != prev_lap:
                event(('다시 붙음' if lap_ok else '끊김') + f'(노트북→헤드) {rec["lap"].get("status_err", "")} '
                      f'ping={rec["lap"].get("ping")} | 태블릿 nc={rec["tab"].get("nc")}')
            prev_tab, prev_lap = tab_ok, lap_ok
            n += 1
            if n % 120 == 0:
                event(f'진행 {n}회, 태블릿 끊김 {len(outages) + (1 if cur else 0)}번')
            time.sleep(max(0.0, a.interval - (time.time() - t_start)))

    if cur:
        cur['end'] = None
        outages.append(cur)
    stop.set()
    lc.terminate()
    rows = [json.loads(x) for x in (out / 'probes.jsonl').read_text(encoding='utf-8').splitlines()]
    summary = {
        'probes': len(rows),
        'tablet_fail': sum(1 for r in rows if r['tab'].get('nc') != 0),
        'laptop_fail': sum(1 for r in rows if r['lap'].get('status') is None),
        'both_fail': sum(1 for r in rows if r['tab'].get('nc') != 0 and r['lap'].get('status') is None),
        'outages': outages,
    }
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    event(f'끝 {json.dumps({k: v for k, v in summary.items() if k != "outages"}, ensure_ascii=False)} '
          f'끊김 {len(outages)}번')


if __name__ == '__main__':
    main()
