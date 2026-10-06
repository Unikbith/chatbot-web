/**
 * 新用户使用教程数据
 *
 * 文案与配图同步自产品使用说明文档《新用户使用教程》（2026-10-06 据文档全量更新）。
 * 要点：**一定要配置自己的 API**，否则只能跟免费模型聊 —— 免费模型能力有限、
 * 限制多，只适合先看看效果。因此教程前几步全部围绕「配置 API」展开。
 *
 * 每步可有 1~N 张配图（第 3 步区分电脑端与手机端）。
 */
import step1 from '../assets/tutorial/step1.png'
import step2 from '../assets/tutorial/step2.png'
import step3pc from '../assets/tutorial/step3-pc.png'
import step3phone1 from '../assets/tutorial/step3-phone1.png'
import step3phone2 from '../assets/tutorial/step3-phone2.png'
import step4 from '../assets/tutorial/step4.png'
import step5 from '../assets/tutorial/step5.png'
import step6 from '../assets/tutorial/step6.png'
import step7 from '../assets/tutorial/step7.png'
import step8 from '../assets/tutorial/step8.png'
import step9 from '../assets/tutorial/step9.png'

export const TUTORIAL_STEPS = [
  {
    title: '先换成自己的 API',
    titleEn: 'Use your own API first',
    desc: '当前使用的是免费模型，虽能对话但能力受限、无法畅聊。点击「去配置」进入设置。',
    descEn: 'The default free model can chat but is limited and cannot handle deep conversations. Click "Configure" to set it up.',
    images: [{ src: step1, caption: '' }],
  },
  {
    title: '获取 API Key',
    titleEn: 'Get an API Key',
    desc: '若还没有 API Key，点击即可跳转 DeepSeek 官网获取；已拥有的可直接跳过。',
    descEn: 'No API Key yet? Click to jump to the DeepSeek site to get one; skip if you already have it.',
    images: [{ src: step2, caption: '' }],
  },
  {
    title: '创建并保存 Key',
    titleEn: 'Create and save the key',
    desc: '创建 API Key（生成后请务必立即保存，关闭页面后将无法再次查看完整 Key）。',
    descEn: 'Create the API Key (save it immediately after generation — once you leave the page the full key can no longer be viewed).',
    images: [
      { src: step3pc, caption: '电脑端获取方式' },
      { src: step3phone1, caption: '手机端获取方式（一）' },
      { src: step3phone2, caption: '手机端获取方式（二）' },
    ],
  },
  {
    title: '获取模型',
    titleEn: 'Fetch models',
    desc: '获取模型：在配置页选择并填入所需模型。',
    descEn: 'Fetch models: on the config page, select and fill in the model you need.',
    images: [{ src: step4, caption: '' }],
  },
  {
    title: '创建人物卡',
    titleEn: 'Create a persona card',
    desc: '恭喜，API 已配置成功！现在开始创建你的「人物卡」。',
    descEn: 'Congrats — your API is configured! Now create your persona card.',
    images: [{ src: step5, caption: '' }],
  },
  {
    title: '用提示词工具生成人设',
    titleEn: 'Generate a persona prompt',
    desc: '使用提示词工具生成人物设定：点击聊天框右上角的「提示词工具」，一键生成角色设定提示词。',
    descEn: 'Use the prompt tool to generate the persona: click "Prompt Tool" at the top-right of the chat box to generate persona prompts in one click.',
    images: [{ src: step6, caption: '' }],
  },
  {
    title: '开始畅聊',
    titleEn: 'Start chatting',
    desc: '选择人设、打开「神秘按钮」，即可开始畅聊（恭喜你完成配置）。',
    descEn: 'Pick a persona, turn on the "Mystery" button, and start chatting (setup complete).',
    images: [{ src: step7, caption: '' }],
  },
  {
    title: '生图模型',
    titleEn: 'Image generation',
    desc: '关于生图模型：未配置生图模型前有次数限制，配置后将不再受限。',
    descEn: 'About image generation: before configuring an image model there is a usage limit; after configuring your own, it is unlimited.',
    images: [{ src: step8, caption: '' }],
  },
  {
    title: '反馈与更多玩法',
    titleEn: 'Feedback & more',
    desc: '如需修改建议，或想了解更多的白嫖模型与配置方法（例如配置阿里百炼的语音模型，让文字被朗读出来），可直接与管理员对话反馈，我们会协助你！',
    descEn: "For suggestions, or to learn about more free models and configuration (e.g. set up Alibaba Bailian's voice model to read text aloud), just chat with the admin — we will help!",
    images: [{ src: step9, caption: '' }],
  },
]

export default TUTORIAL_STEPS
