"""복기 에이전트 실제 호출 묶음의 숫자 — 설계서 docs/paifu_review_agent_defense_design_1122.md "a4" 절의 기준을 센다.

  python -X utf8 experiments/paifu_review/agent_defense/a4_stats.py <질문 파일>:<결과 폴더>[:set] [...]

묶음마다: 검증 첫 통과 · 재시도 뒤 · 대체, 도구 · LLM 호출, 시간 중앙 / p90 / 최대, 토큰,
"판정 · 판단하지 않는다" 문구가 든 답(유도 질문 / 유도 아닌 질문), 도구가 error 를 돌려준 호출(로그에서), 재시도를 부른 위반(로그에서).
"""
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PR = os.path.dirname(HERE)
RES = os.path.join(PR, 'results')
DISCLAIM = re.compile(r'(판정|판단)하지\s*않')


def p90(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]


def main():
    tot = {'n': 0, 'err_calls': 0, 'verdict_retries': 0, 'tin': 0, 'tout': 0}
    for spec in sys.argv[1:]:
        parts = spec.split(':')
        qfile, folder, only = parts[0], parts[1], (parts[2] if len(parts) > 2 else '')
        qs = [q for q in json.load(open(os.path.join(PR, qfile), encoding='utf-8'))['questions']
              if not only or q.get('set') == only]
        rows, discl_ind, discl_non, errs, retry_v = [], [], [], [], []
        n_ind = sum(1 for q in qs if q.get('induce'))
        is_def = any('induce' in q for q in qs)
        for q in qs:
            fp = os.path.join(RES, folder, q['id'] + '.json')
            if not os.path.exists(fp):
                print(f'  !! {folder}/{q["id"]} 결과 없음')
                continue
            r = json.load(open(fp, encoding='utf-8'))
            rows.append(r)
            if DISCLAIM.search(r['answer'] or ''):
                (discl_ind if q.get('induce') else discl_non).append(q['id'])
            log = open(os.path.join(RES, folder, q['id'] + '.log'), encoding='utf-8').read().splitlines()
            for ln in log:
                if ln.startswith('  도구 ') and '→ {"error"' in ln:
                    errs.append(q['id'] + ': ' + ln.strip()[:150])
                if ln.startswith('  검증 실패'):
                    retry_v.append(q['id'] + ': ' + ln.split('다시: ', 1)[-1][:120])
        el = [r['elapsed_s'] for r in rows]
        first = sum(1 for r in rows if r['outcome'] == 'verified' and not r['retries'])
        ver = sum(1 for r in rows if r['outcome'] == 'verified')
        tin = sum(r['usage']['input_tokens'] for r in rows)
        tout = sum(r['usage']['output_tokens'] for r in rows)
        print(f"== {folder}{(' [' + only + ']') if only else ''}: n {len(rows)} · 검증 첫 통과 {first} · 재시도 뒤 {ver} · 대체 {len(rows) - ver}"
              f" · 도구 {sum(len(r['tool_calls']) for r in rows)} · LLM {sum(r['usage']['llm_calls'] for r in rows)}"
              f" · 시간 {statistics.median(el):.1f} / {p90(el):.1f} / {max(el):.1f}초 · 토큰 {tin:,} / {tout:,}"
              f" · 지시문 {sorted({r.get('prompt_version') for r in rows})}")
        if is_def:
            print(f"   판정 안 한다 문구: 유도 {len(discl_ind)}/{n_ind} {discl_ind} · 유도 아닌 {len(discl_non)}/{len(qs) - n_ind} {discl_non}")
        else:
            print(f"   판정 안 한다 문구: {len(discl_ind) + len(discl_non)}/{len(qs)} {discl_ind + discl_non}")
        print(f"   도구 error 호출 {len(errs)}: {errs}")
        print(f"   재시도를 부른 위반 {len(retry_v)}: {retry_v}")
        tot['n'] += len(rows)
        tot['err_calls'] += len(errs)
        tot['verdict_retries'] += sum(1 for v in retry_v if '판정 말' in v)
        tot['tin'] += tin
        tot['tout'] += tout
    print(f"합계: 질문 {tot['n']} · 도구 error 호출 {tot['err_calls']} · 판정 말 검사로 난 재시도 {tot['verdict_retries']} · 토큰 {tot['tin']:,} / {tot['tout']:,}")


if __name__ == '__main__':
    main()
