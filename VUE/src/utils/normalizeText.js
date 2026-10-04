/**
 * 模型输出文本的规范化
 *
 * 背景：模型有时会把换行写成 `<br>` 字面标签（多受历史消息影响而互相模仿）。
 * 若不还原成真实换行，会同时引发两个问题：
 *   1. `<br>` 会以文字形式显示出来（渲染时被转义，很难看）；
 *   2. 整段变成"一行"，而行首标记（如【进度】）的解析依赖行边界，
 *      于是标记识别失败、以原文形式漏到气泡里。
 *
 * 因此所有入口（标记解析、模板渲染、正文渲染）都先过一遍本函数，
 * 让后续逻辑面对的文本始终是"换行就是换行"的干净文本。
 */

/** `<br>` / `<br/>` / `<br />` 等各种写法 */
const BR_RE = /<br\s*\/?>/gi
/** `</br>` 这种非标准闭合也算换行 */
const BR_CLOSE_RE = /<\/br\s*>/gi

export function normalizeModelText(input) {
  let s = String(input ?? '')
  s = s.replace(BR_RE, '\n')
  s = s.replace(BR_CLOSE_RE, '\n')
  // 常见实体：不还原会让 &nbsp; 直接显示出来
  s = s.replace(/&nbsp;/gi, ' ')
  // 折叠过多的连续空行（模型常写一大串换行），最多保留一个空行
  s = s.replace(/\n{3,}/g, '\n\n')
  return s
}

export default normalizeModelText
