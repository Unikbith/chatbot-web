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
      { name: '火山引擎（豆包 ASR）', url: 'https://docs.volcengine.com/docs/6561/1558163', brand: 'volcengine' },
      { name: '阿里云百炼（Paraformer）', url: 'https://help.aliyun.com/zh/model-studio/paraformer-real-time-speech-recognition-python-sdk', brand: 'bailian' },
    ],
  },
  {
    key: 'tts',
    title: '文字转语音',
    titleEn: 'Text-to-Speech',
    links: [
      { name: 'MiniMax', url: 'https://platform.minimaxi.com/docs/guides/models-intro', brand: 'mimotts' },
      { name: '火山引擎', url: 'https://docs.volcengine.com/docs/82379/1099455?lang=zh', brand: 'volcengine' },
      { name: '阿里云百炼', url: 'https://docs.bailian.console.aliyun.com/zh/model-studio/what-is-model-studio?spm=a2ty07.bailian_model_settings_kms.0.0.1d9274a1lGaLxb', brand: 'bailian' },
    ],
  },
  {
    key: 'image',
    title: '图片生成',
    titleEn: 'Image Generation',
    links: [
      { name: 'Agnes Image', url: 'https://agnes-ai.com/zh-Hans/docs/overview', brand: 'agnes' },
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
