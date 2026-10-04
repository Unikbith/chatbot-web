/**
 * 新用户使用教程数据
 *
 * 文案与配图来自产品使用说明文档《新用户使用教程》：
 * 只保留关键动作，每步一句话，避免长段落把新用户劝退。
 * 配图按原文档顺序导入，构建时由 Vite 处理为带 hash 的静态资源。
 */
import step1 from '../assets/tutorial/step-1.png'
import step2 from '../assets/tutorial/step-2.png'
import step3 from '../assets/tutorial/step-3.png'
import step4 from '../assets/tutorial/step-4.png'
import step5 from '../assets/tutorial/step-5.png'
import step6 from '../assets/tutorial/step-6.png'
import step7 from '../assets/tutorial/step-7.png'

export const TUTORIAL_STEPS = [
  {
    title: '换成自己的 API Key',
    titleEn: 'Use your own API Key',
    desc: '默认用的是免费模型，能聊天但比较降智、也没法畅聊（破甲），点「去配置」换成自己的。',
    descEn: 'The free model works but is limited. Click "Configure" to switch to your own API Key.',
    image: step1,
  },
  {
    title: '获取 API Key',
    titleEn: 'Get an API Key',
    desc: '还没有 Key？点一下可直接跳到 DeepSeek 官网获取（已有可跳过）。',
    descEn: 'No key yet? One click jumps to the DeepSeek site to get one (skip if you already have one).',
    image: step2,
  },
  {
    title: '创建并保存 Key',
    titleEn: 'Create and save it',
    desc: '在官网创建 API Key，创建好后一定要立刻保存！！！',
    descEn: 'Create the API Key on the official site — be sure to save it right away!',
    image: step3,
  },
  {
    title: '获取模型',
    titleEn: 'Fetch models',
    desc: '回到配置页点「获取模型」，自动拉取可用模型列表。',
    descEn: 'Back on the config page, click "Fetch models" to load the available model list.',
    image: step4,
  },
  {
    title: '创建人物卡',
    titleEn: 'Create a persona card',
    desc: '能走到这一步，恭喜你 API 配置成功，接着开始创建人物卡。',
    descEn: 'If you made it here, your API setup succeeded. Now create a persona card.',
    image: step5,
  },
  {
    title: '提示词工具生成人设',
    titleEn: 'Generate a persona prompt',
    desc: '用提示词工具生成人物设定提示词（入口在聊天框的右上角）。',
    descEn: 'Use the prompt tool to generate a persona prompt (button at the top-right of the chat box).',
    image: step6,
  },
  {
    title: '开始畅聊',
    titleEn: 'Start chatting',
    desc: '选择人设、打开「神秘」按钮，就可以开始畅聊了（恭喜你完成配置）。',
    descEn: 'Pick a persona and turn on the "Mystery" switch, then start chatting. Setup complete!',
    image: step7,
  },
]

export default TUTORIAL_STEPS
