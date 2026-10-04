/**
 * 前端回归测试入口：`npm test`
 *
 * 覆盖两块最容易出错、也最值得守住的地方：
 *   · 渲染模板引擎（标记 → DOM 骨架、转义、正文不被吞）
 *   · HTML 消毒通道（脚本/事件必须清掉，模板需要的排版能力必须保留）
 *
 * 消毒测试依赖 jsdom（仅测试用，未列入 dependencies）：
 * 缺失时自动跳过，不让整个测试失败。
 */
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))

function run(file) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [join(here, file)], { stdio: 'inherit' })
    child.on('exit', (code) => resolve(code ?? 1))
  })
}

const hasJsdom = existsSync(join(here, '..', 'node_modules', 'jsdom'))

const jobs = [
  ['render-template.test.mjs', true],
  ['template-css.test.mjs', true],
  ['template-presets.test.mjs', true],
  ['e2e-render.test.mjs', true],
]
jobs.push(['sanitize.test.mjs', hasJsdom])
jobs.push(['prose.test.mjs', hasJsdom])

let failed = 0
for (const [file, enabled] of jobs) {
  if (!enabled) {
    console.log(`\n跳过 ${file}（需要 jsdom：npm i -D jsdom 后可运行）`)
    continue
  }
  console.log(`\n=== ${file} ===`)
  const code = await run(file)
  if (code !== 0) failed++
}

console.log(failed ? `\n有 ${failed} 个测试文件失败` : '\n全部测试通过')
process.exit(failed ? 1 : 0)
