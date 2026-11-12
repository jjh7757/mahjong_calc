"""헤드(폰) 미리보기 간격을 줄이면 얼마나 부담되나 재는 도구(2026-11-11, 사용자 "1초로 측정").

노트북이 태블릿 대신 헤드에 `/preview`(기본 긴 변 960, 태블릿 배경 프레임과 같은 요청)를 정해진 간격으로 부르고,
30초마다 폰(adb)의 배터리·배터리 온도·열 상태·센서 온도·헤드 앱 CPU 를 남긴다. 태블릿은 거치 화면을 닫아 두어
헤드를 부르는 쪽이 노트북 하나뿐이게 한다(겹치면 간격이 섞인다).

단계를 차례로 돈다(기본: 3초 15분 → 1초 60분). 열은 관성이 있어 번갈아 돌리지 않는다 → 같은 시각 비교가 아님(메모에 적기).

용법: python head_load_watch.py [--phases 3:15,1:60] [--sample 30]
결과: experiments/visit_<날짜>/load/<시작>/ (requests.jsonl, device.jsonl, summary.json)
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import threading
import time
from datetime import datetime

import supervise as sv


def phone_sample(serial: str) -> dict:
    st = sv.device_state(serial)
    th = sv.adb('shell', 'dumpsys', 'thermalservice', serial=serial, timeout=15)
    status = re.search(r'Thermal Status: (\d+)', th)
    temps: dict[str, float] = {}
    # "Current temperatures from HAL:" 아래 Temperature{mValue=..., mType=..., mName=..., mStatus=...}
    hal = th.split('Current temperatures from HAL:', 1)[-1].split('Current cooling devices', 1)[0]
    for m in re.finditer(r'mValue=([-\d.]+), mType=(-?\d+), mName=([^,]+)', hal):
        temps[m.group(3)] = round(float(m.group(1)), 1)
    top = sv.adb('shell', 'top -b -n 1 -o %CPU,RES,ARGS | grep -m1 mahjong', serial=serial, timeout=15)
    cpu = re.match(r'\s*([\d.]+)\s+(\S+)', top)
    return {**st, 'thermal_status': int(status.group(1)) if status else None, 'temps': temps,
            'app_cpu': float(cpu.group(1)) if cpu else None, 'app_res': cpu.group(2) if cpu else None}


def summarize(xs: list[float]) -> dict:
    if not xs:
        return {}
    s = sorted(xs)
    return {'n': len(s), 'median': round(statistics.median(s), 3),
            'p90': round(s[min(len(s) - 1, int(len(s) * 0.9))], 3), 'max': round(s[-1], 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--phases', default='3:15,1:60', help='간격초:분,... 차례로')
    ap.add_argument('--sample', type=float, default=30, help='폰 상태 기록 간격(초)')
    a = ap.parse_args()
    phases = [(float(p.split(':')[0]), float(p.split(':')[1])) for p in a.phases.split(',')]

    serial = sv.devices().get('phone')
    if not serial:
        raise SystemExit('폰 adb 안 붙음 — 온도를 못 잼')
    out = sv.HERE.parent / f'visit_{datetime.now():%Y%m%d}' / 'load' / f'{datetime.now():%H%M%S}'
    out.mkdir(parents=True, exist_ok=True)
    req_f = open(out / 'requests.jsonl', 'a', encoding='utf-8')
    dev_f = open(out / 'device.jsonl', 'a', encoding='utf-8')
    phase_name = {'v': None}
    stop = threading.Event()

    def sampler() -> None:
        while not stop.is_set():
            t = time.time()
            try:
                r = phone_sample(serial)
            except Exception as e:  # noqa: BLE001
                r = {'error': str(e)}
            dev_f.write(json.dumps({'t': datetime.now().isoformat(timespec='seconds'),
                                    'phase': phase_name['v'], **r}, ensure_ascii=False) + '\n')
            dev_f.flush()
            print(f"{datetime.now():%H:%M:%S} [{phase_name['v']}] 배터리 {r.get('battery')}% "
                  f"{r.get('temp_c')}°C 열상태 {r.get('thermal_status')} CPU {r.get('app_cpu')} "
                  f"앱앞 {r.get('app_front')} 충전 {r.get('plugged')}", flush=True)
            stop.wait(max(0.0, a.sample - (time.time() - t)))

    th = threading.Thread(target=sampler, daemon=True)
    phase_name['v'] = 'start'
    th.start()
    results: dict[str, dict] = {}
    for interval, minutes in phases:
        name = f'{interval:g}s'
        phase_name['v'] = name
        lat: list[float] = []
        sizes: list[int] = []
        fails = 0
        end = time.time() + minutes * 60
        nxt = time.time()
        while time.time() < end:
            t0 = time.time()
            rec: dict = {'t': datetime.now().isoformat(timespec='milliseconds'), 'phase': name}
            try:
                body, _ = sv.head_get('/preview', timeout=4)  # 태블릿 RemoteCamera 와 같은 4초
                rec['s'] = round(time.time() - t0, 3)
                rec['bytes'] = len(body)
                lat.append(rec['s'])
                sizes.append(len(body))
            except Exception as e:  # noqa: BLE001
                rec['err'] = str(e)[:200]
                fails += 1
            req_f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            req_f.flush()
            nxt += interval
            if nxt < time.time():  # 밀렸으면 다음 칸부터(태블릿 Timer.periodic + _bgFetching 건너뛰기와 같음)
                nxt = time.time() + interval
            time.sleep(max(0.0, nxt - time.time()))
        results[name] = {'interval_s': interval, 'minutes': minutes, 'fails': fails,
                         'latency_s': summarize(lat), 'kb_median': round(statistics.median(sizes) / 1024) if sizes else None}
        print(name, json.dumps(results[name], ensure_ascii=False), flush=True)
    phase_name['v'] = 'end'
    time.sleep(1)
    stop.set()
    th.join(timeout=60)
    (out / 'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf-8')
    print('결과', out)


if __name__ == '__main__':
    main()
