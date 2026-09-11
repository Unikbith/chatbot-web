// utils/identicon.js - 本地生成评论/创作者的方块头像
// 用本地 SVG 替代外部 api.dicebear.com 请求，避免跨境网络导致头像加载缓慢或失败。

const PALETTE = [
  '#d96c4e', '#e07c5a', '#c96a7e', '#b8615a', '#d99a4e',
  '#7fa88a', '#5b8fa8', '#7a6fae', '#a86f8a', '#8a7f6f',
]

function hashString(str) {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

/**
 * 生成 identicon 的 data-uri（无需网络请求）
 * @param {string|number} seed 种子（如 identicon_seed）
 * @param {number} size 输出尺寸（px）
 * @returns {string} data:image/svg+xml,...
 */
export function identiconDataUrl(seed, size = 40) {
  const s = String(seed ?? 'guest')
  const base = hashString(s)
  const color = PALETTE[base % PALETTE.length]
  const grid = 5
  const half = Math.ceil(grid / 2)

  let cells = ''
  const push = (x, y) => {
    cells += `<rect x="${x}" y="${y}" width="1" height="1" fill="${color}"/>`
  }

  for (let y = 0; y < grid; y++) {
    for (let x = 0; x < half; x++) {
      // 用独立的哈希保证同一个 seed 结果稳定
      if (hashString(`${s}#${x},${y}`) % 100 < 55) {
        push(x, y)
        if (x !== grid - 1 - x) push(grid - 1 - x, y)
      }
    }
  }

  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${grid} ${grid}" shape-rendering="crispEdges">` +
    `<rect width="${grid}" height="${grid}" fill="#f3ece6"/>${cells}</svg>`

  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

export default identiconDataUrl
