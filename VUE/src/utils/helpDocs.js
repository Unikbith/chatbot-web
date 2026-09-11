/**
 * 厂商 API 文档链接（帮助与反馈 / 模型配置引导共用）
 *
 * 结构：按 provider type 分组，每项 { name, url, brand? }
 * brand 用于与模型配置中的厂商品牌做匹配（存在时优先按 brand 过滤）。
 */

export const HELP_DOC_GROUPS = [
  {
    key: 'chat',
    title: '对话模型',
    titleEn: 'Chat Models',
    links: [
      { name: 'DeepSeek', url: 'https://platform.deepseek.com/api_docs', brand: 'deepseek' },
      { name: 'OpenAI', url: 'https://platform.openai.com/docs', brand: 'openai' },
      { name: '智谱 GLM', url: 'https://open.bigmodel.cn/dev/api', brand: 'zhipu' },
      { name: 'Kimi', url: 'https://platform.moonshot.cn/docs', brand: 'moonshot' },
      { name: 'MiniMax', url: 'https://api.minimax.chat/', brand: 'minimax' },
    ],
  },
  {
    key: 'stt',
    title: '语音转文字',
    titleEn: 'Speech-to-Text',
    links: [
      { name: 'OpenAI Whisper', url: 'https://platform.openai.com/docs/guides/speech-to-text', brand: 'openai' },
      { name: '通义听悟', url: 'https://help.aliyun.com/zh/dashscope/', brand: 'dashscope' },
    ],
  },
  {
    key: 'tts',
    title: '文字转语音',
    titleEn: 'Text-to-Speech',
    links: [
      { name: 'ElevenLabs', url: 'https://elevenlabs.io/docs', brand: 'elevenlabs' },
      { name: 'OpenAI TTS', url: 'https://platform.openai.com/docs/guides/text-to-speech', brand: 'openai' },
    ],
  },
  {
    key: 'image',
    title: '图片生成',
    titleEn: 'Image Generation',
    links: [
      { name: 'Agnes Image', url: 'https://apihub.agnes-ai.cn/docs', brand: 'agnes' },
      { name: 'DALL·E', url: 'https://platform.openai.com/docs/guides/images', brand: 'openai' },
    ],
  },
]

/** 取某个 provider type 的文档分组 */
export function helpGroupOf(type) {
  return HELP_DOC_GROUPS.find(g => g.key === type) || null
}

/** 在某一类里按厂商品牌找文档链接（brand 大小写无关，做包含匹配） */
export function helpLinkOfBrand(type, brand) {
  const group = helpGroupOf(type)
  if (!group || !brand) return null
  const b = String(brand).toLowerCase()
  return group.links.find(l => l.brand && (b.includes(l.brand) || l.brand.includes(b))) || null
}
