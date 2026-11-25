// 대조용: 컴파일된 mj_engine.js 를 node 로 불러 패보 파일마다 score · review 를 돌려 한 줄 JSON 으로 적는다.
//
//   node tool/web_engine/compare_js.mjs <mj_engine.js> <출력.jsonl> <패보.json>...
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'

const [enginePath, outPath, ...files] = process.argv.slice(2)
if (!enginePath || !outPath || files.length === 0) {
  console.error('쓰는 법: node compare_js.mjs <mj_engine.js> <출력.jsonl> <패보.json>...')
  process.exit(2)
}
// 브라우저처럼 전역 하나에 싣는다(dart2js 는 self 를 전역으로 쓸 수 있다).
const ctx = { console }
ctx.self = ctx
ctx.globalThis = ctx
vm.createContext(ctx)
vm.runInContext(fs.readFileSync(enginePath, 'utf8'), ctx, { filename: 'mj_engine.js' })
const eng = ctx.mjEngine
if (!eng) {
  console.error('mjEngine 이 없습니다')
  process.exit(1)
}
const lines = []
for (const f of files) {
  const raw = fs.readFileSync(f, 'utf8')
  const t0 = performance.now()
  const score = eng.score(raw)
  const review = eng.review(raw)
  const ms = performance.now() - t0
  lines.push(JSON.stringify({ file: path.basename(f), score, review, ms }))
}
fs.writeFileSync(outPath, lines.join('\n') + '\n')
console.log(`version=${eng.version} apiVersion=${eng.apiVersion} files=${files.length}`)
