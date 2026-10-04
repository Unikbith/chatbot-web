/**
 * 渲染预设样式的注入
 *
 * 为什么用「读入 CSS 文本 + 运行时注入」而不是 `import './archive.css'`：
 * 静态引入的样式要等产物加载才生效，一旦出现缓存/HMR/顺序问题，
 * 表现就是"模板没样式"，但界面上完全看不出原因（排查成本极高）。
 * 用 `?raw` 把 CSS 作为**字符串**打进 JS，再在应用启动时同步注入，
 * 样式是否存在变成可自检的确定行为 —— 要么注入成功，要么能立刻发现。
 *
 * CSS 文件仍是唯一事实来源（各预设一个文件），本模块只负责搬运。
 */
import baseCss from '../assets/reply-templates/_base.css?raw'
import archiveCss from '../assets/reply-templates/archive.css?raw'
import minimalCss from '../assets/reply-templates/minimal.css?raw'
import neonCss from '../assets/reply-templates/neon.css?raw'
import inkCss from '../assets/reply-templates/ink.css?raw'
import terminalCss from '../assets/reply-templates/terminal.css?raw'
import scriptCss from '../assets/reply-templates/script.css?raw'
import letterCss from '../assets/reply-templates/letter.css?raw'
import oracleCss from '../assets/reply-templates/oracle.css?raw'
import blushCss from '../assets/reply-templates/blush.css?raw'
import moonlightCss from '../assets/reply-templates/moonlight.css?raw'
import smokeCss from '../assets/reply-templates/smoke.css?raw'
import whiskeyCss from '../assets/reply-templates/whiskey.css?raw'
import fateCss from '../assets/reply-templates/fate.css?raw'

const STYLE_ID = 'reply-template-styles'

/** 与 replyTemplates.js 的预设 id 一一对应 */
export const TEMPLATE_CSS = {
  _base: baseCss,
  archive: archiveCss,
  minimal: minimalCss,
  neon: neonCss,
  ink: inkCss,
  terminal: terminalCss,
  script: scriptCss,
  letter: letterCss,
  oracle: oracleCss,
  blush: blushCss,
  moonlight: moonlightCss,
  smoke: smokeCss,
  whiskey: whiskeyCss,
  fate: fateCss,
}

/**
 * 注入全部模板样式（幂等）。应用启动时调用一次。
 * @returns {boolean} 本次是否真的执行了注入
 */
export function ensureTemplateStyles() {
  if (typeof document === 'undefined') return false
  if (document.getElementById(STYLE_ID)) return false

  const style = document.createElement('style')
  style.id = STYLE_ID
  style.setAttribute('data-reply-templates', '1')
  // 骨架在前，主题在后：主题覆盖同级变量时依赖后者靠后
  style.textContent = [baseCss, archiveCss, minimalCss, neonCss, inkCss, terminalCss,
    scriptCss, letterCss, oracleCss, blushCss, moonlightCss, smokeCss, whiskeyCss, fateCss].join('\n')
  document.head.appendChild(style)
  return true
}

/**
 * 自检：模板样式是否已真实生效。
 * 通过一个探针元素读取计算样式，而不是"我以为注入了" ——
 * 这样样式没生效时能在控制台看到明确警告，而不是靠肉眼猜。
 */
export function assertTemplateStyles() {
  if (typeof document === 'undefined') return true
  ensureTemplateStyles()
  const probe = document.createElement('div')
  probe.className = 'rtpl rtpl-archive'
  probe.style.cssText = 'position:absolute;left:-9999px;top:0;width:10px;height:10px'
  document.body.appendChild(probe)
  const cs = window.getComputedStyle(probe)
  const ok = cs.borderTopStyle === 'solid' && parseFloat(cs.borderTopWidth) > 0
  document.body.removeChild(probe)
  if (!ok) {
    console.warn('[reply-template] 模板样式未生效：.rtpl.rtpl-archive 没有边框。'
      + '请检查 assets/reply-templates/*.css 是否被正确打包。')
  }
  return ok
}

/** 供预设面板展示用：某个预设的样式文本长度（用于粗查文件是否为空） */
export function templateCssSize(id) {
  return (TEMPLATE_CSS[id] || '').length
}

// 模块被引入即注入，保证在任何消息渲染之前样式就已就绪
ensureTemplateStyles()
