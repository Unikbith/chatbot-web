/**
 * 新用户使用教程数据
 *
 * 文案与配图来自产品使用说明文档《新用户使用教程》（2026-10 更新版）。
 * 要点：**一定要配置自己的 API**，否则只能跟免费模型聊 —— 免费模型又慢又呆、
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

export const TUTORIAL_STEPS = [
  {
    title: '先换成自己的 API',
    titleEn: 'Use your own API first',
    desc: '默认用的是免费模型，能聊天但很降智、限制多、没法畅聊（破甲），点「去配置」换成自己的。',
    descEn: 'The free model works but is weak and restricted. Click "Configure" to use your own API.',
    images: [{ src: step1, caption: '' }],
  },
  {
    title: '获取 API Key',
    titleEn: 'Get an API Key',
    desc: '还没有 Key？点一下可直接跳到 DeepSeek 官网获取（已有可跳过）。',
    descEn: 'No key yet? One click jumps to the DeepSeek site (skip if you already have one).',
    images: [{ src: step2, caption: '' }],
  },
  {
    title: '创建并保存 Key',
    titleEn: 'Create and save the key',
    desc: '在官网创建 API Key，创建好后一定要立刻保存，关掉页面就再也看不到了。',
    descEn: 'Create the key on the official site — save it immediately, it will not be shown again.',
    images: [
      { src: step3pc, caption: '电脑端获取' },
      { src: step3phone1, caption: '手机端获取（一）' },
      { src: step3phone2, caption: '手机端获取（二）' },
    ],
  },
  {
    title: '获取模型',
    titleEn: 'Fetch models',
    desc: '回到配置页点「获取模型」，自动拉取可用模型列表。',
    descEn: 'Back on the config page, click "Fetch models" to load the list.',
    images: [{ src: step4, caption: '' }],
  },
  {
    title: '创建人物卡',
    titleEn: 'Create a persona card',
    desc: '能走到这一步就说明 API 配置成功了，接着开始创建人物卡。',
    descEn: 'If you made it here, your API setup succeeded. Now create a persona card.',
    images: [{ src: step5, caption: '' }],
  },
  {
    title: '用提示词工具生成人设',
    titleEn: 'Generate a persona prompt',
    desc: '用提示词工具生成人物设定提示词（入口在聊天框的右上角）。',
    descEn: 'Use the prompt tool to generate a persona prompt (top-right of the chat box).',
    images: [{ src: step6, caption: '' }],
  },
  {
    title: '开始畅聊',
    titleEn: 'Start chatting',
    desc: '选择人设、打开「神秘」按钮，就可以开始畅聊了（恭喜完成配置）。',
    descEn: 'Pick a persona and turn on the "Mystery" switch, then start chatting.',
    images: [{ src: step7, caption: '' }],
  },
  {
    title: '有建议就告诉我们',
    titleEn: 'Tell us what you think',
    desc: '想反馈修改建议、或想了解更多免费模型与配置模型的办法，点右上角头像 →「系统设置」→「帮助和反馈」，在最下面留言即可，我们会帮忙。',
    descEn: 'For feedback or more model tips, open the avatar menu → Settings → Help & Feedback and leave a message.',
    images: [],
  },
]

export default TUTORIAL_STEPS
