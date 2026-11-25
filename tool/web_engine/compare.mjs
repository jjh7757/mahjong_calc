// 대조: compare_vm.dart(Dart VM) 줄과 compare_js.mjs(컴파일된 JS) 줄을 판마다 비교해 표로.
//
//   node tool/web_engine/compare.mjs <vm.jsonl> <js.jsonl>
// 비교는 score · review 글을 JSON 으로 읽어 깊은 비교(키 순서 무시, 숫자는 값 그대로). 다르면 첫 차이 경로를 적는다.
import fs from 'node:fs'

const read = (p) =>
  new Map(
    fs
      .readFileSync(p, 'utf8')
      .split('\n')
      .filter(Boolean)
      .map((l) => JSON.parse(l))
      .map((r) => [r.file, r]),
  )

function diff(a, b, at = '') {
  if (a === b) return null
  if (typeof a !== typeof b || a === null || b === null || typeof a !== 'object') return `${at || '/'}: ${JSON.stringify(a)} ≠ ${JSON.stringify(b)}`
  if (Array.isArray(a) !== Array.isArray(b)) return `${at}: 배열/객체 다름`
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  for (const k of keys) {
    const d = diff(a[k], b[k], `${at}/${k}`)
    if (d) return d
  }
  return null
}

const [vmPath, jsPath] = process.argv.slice(2)
const vmRows = read(vmPath)
const jsRows = read(jsPath)
let bad = 0
console.log('| 판 | 점수 | 복기 | 패효율 | 등급(최선/좋음/부정확/실수/큰실수) | 평가 안 함 | 끝 점수 | VM ms | JS ms |')
console.log('|---|---|---|---|---|---|---|---|---|')
for (const [file, v] of vmRows) {
  const j = jsRows.get(file)
  if (!j) {
    bad++
    console.log(`| ${file} | JS 없음 | | | | | | | |`)
    continue
  }
  const sd = diff(JSON.parse(v.score), JSON.parse(j.score))
  const rd = diff(JSON.parse(v.review), JSON.parse(j.review))
  if (sd || rd) bad++
  const r = JSON.parse(v.review)
  const s = JSON.parse(v.score)
  const sum = r.summary ?? {}
  const grades = (sum.grades ?? []).map((g) => g.count).join('/')
  const pts = s.kind === 'win' ? (s.score ? (s.score.valid ? `${s.score.payment.total}` : `무효(${s.score.error})`) : '계산 안 함') : s.kind
  console.log(
    `| ${file} | ${sd ? '다름: ' + sd : '같음'} | ${rd ? '다름: ' + rd : '같음'} | ${sum.efficiencyPct ?? '—'} | ${grades} | ${sum.skipText ?? r.error ?? ''} | ${pts} | ${v.ms.toFixed(0)} | ${j.ms.toFixed(0)} |`,
  )
}
for (const f of jsRows.keys()) if (!vmRows.has(f)) (bad++, console.log(`| ${f} | VM 없음 | | | | | | | |`))
console.log(`\n${vmRows.size}판 중 다름 ${bad}`)
process.exit(bad ? 1 : 0)
