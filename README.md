# AI 聊天助手 Web 版

一个功能丰富的 AI 聊天 Web 应用，支持多模型 API、识图对话、AI 文生图 / 图生图、语音交互、提示词工具、云端存档、邮箱注册与管理后台等功能。

## 功能特性

### 核心聊天
- 流式对话，实时响应
- 支持多种 AI 模型（DeepSeek、智谱、通义千问、OpenAI 等所有 OpenAI 兼容格式）
- 深度思考模式（DeepSeek Reasoner 等推理模型）
- 自定义人物设定提示词
- 回复长度、采样参数自由调节

### 多供应商管理
- 支持添加多个 API 供应商配置
- 一键切换不同 API 供应商
- 内置快速模板（DeepSeek、智谱、通义、OpenAI）
- 连接测试功能
- 供应商密钥在接口中脱敏返回

### 识图对话
- 上传图片，AI 理解图片内容
- 基于图片进行多轮对话

### AI 图片生成
- 文生图 / 图生图，支持多分辨率、长宽比与质量档位
- 支持按关键词触发：`生图` / `生成图片` / `画一张` 生成图片，`改图` / `图生图` / `修改图片` 修改图片
- 未单独配置图片 API 时，使用内置免费 Key 并默认按 9:16 竖版生成
- 免费用户有限量额度；超过后可自行在「模型配置-图片生成」中配置 API Key

### 提示词工具
- 一键生成人物设定提示词与图片提示词（文生图 / 图生图）
- 支持自选已启用模型与自定义系统提示词，替代原「清空对话」入口

### 语音交互
- 语音输入（STT），说话转文字
- 语音播报（TTS），AI 回复朗读
- 多种音色可选，音色跟随 TTS 模型配置
- 会话内可独立开关「AI 回复自动语音播报」

### 用户系统
- 邮箱注册 / 登录（JWT 认证，支持短信验证码式邮箱验证）
- 用户名限普通字符串（字母、数字、下划线），注册后与邮箱一样不可修改
- 独立管理后台 `/admin`（管理员登录、用户与对话审计）
- 云端对话存档
- 本地存储兼容模式

### 个性化设置
- 自定义头像和背景（背景支持「完全可见 / 覆盖背景」两种展示方式）
- 消息气泡透明度调节
- 会话级独立配置：AI / 用户头像、AI 采样参数（温度、频率惩罚、存在惩罚）、自动播报
- 响应式设计，支持移动端

## 项目结构

```
chatbot-web/
├── Flask/                   # 后端代码
│   ├── app.py              # 应用入口，服务启动与 JWT 校验
│   ├── config.py           # 基础配置信息（环境变量、限流与防护开关）
│   ├── models.py           # 数据库模型
│   ├── extensions.py       # 扩展与数据库初始化
│   ├── requirements.txt    # Python 依赖
│   ├── .env.example        # 环境变量示例
│   ├── .gitignore          # 忽略本地敏感配置（.env）
│   ├── routes/             # 路由层，按业务划分的接口
│   │   ├── auth.py         # 认证：注册/登录/验证码/改密
│   │   ├── chat.py         # 聊天与识图、提示词工具
│   │   ├── audio.py        # 语音识别与合成
│   │   ├── conversation.py # 对话存档
│   │   ├── provider.py     # 模型供应商与密钥管理
│   │   ├── persona.py      # 人设模板
│   │   ├── settings.py     # 系统设置
│   │   ├── image.py        # AI 图片生成
│   │   ├── admin.py        # 管理后台
│   │   └── upload.py       # 图片上传
│   └── services/           # 服务层，业务逻辑与安全处理
│       ├── ai_service.py         # AI 调用封装与 SSRF 防护
│       ├── agnes_image.py        # 图片生成调用封装
│       ├── email_service.py      # 邮件发送
│       ├── html_sanitize.py      # 输出 HTML 消毒
│       ├── markdown_streamer.py  # 流式渲染
│       ├── rate_limit.py         # 接口限流
│       ├── ssrf.py               # SSRF 校验
│       ├── upload_guard.py       # 上传文件校验
│       └── vendor_presets.py     # 供应商预设模板
└── VUE/                    # 前端应用
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.js         # 前端入口
        ├── App.vue         # 根组件
        ├── router/         # 路由配置
        ├── views/          # 页面
        │   ├── Home.vue            # 主页
        │   ├── AdminLogin.vue      # 管理后台登录
        │   └── AdminBackend.vue    # 管理后台
        ├── components/     # 组件
        │   ├── AuthModal.vue            # 登录/注册
        │   ├── ChatArea.vue             # 聊天区
        │   ├── ConversationSettings.vue # 会话设置
        │   ├── PromptToolPanel.vue      # 提示词工具
        │   ├── PersonaPanel.vue         # 人设模板面板
        │   ├── ProviderPanel.vue        # 供应商配置面板
        │   ├── AdminPanel.vue           # 管理后台面板
        │   ├── Sidebar.vue              # 侧边栏
        │   ├── SystemSettings.vue       # 系统设置
        │   └── VoiceInput.vue           # 语音输入
        ├── i18n/           # 多语言
        └── utils/          # 工具：请求封装/认证/主题
```

## 快速开始

### 后端启动

```bash
cd Flask

# 安装依赖
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env
# 编辑 .env 配置你的密钥（可选，也可以在前端界面配置供应商）

# 启动服务
python app.py
```

后端默认运行在 `http://localhost:5000`

开发环境默认账号：`admin` / `admin123`（生产环境不会自动创建默认管理员，请通过邮箱注册）

### 前端启动

```bash
cd VUE

# 安装依赖
npm install

# 启动开发服务
npm run dev
```

前端默认运行在 `http://localhost:5173`

### SMTP 邮件配置（邮箱注册 / 重置密码）

在 `Flask/.env` 中配置邮件服务，用于发送注册与重置密码的验证码：

```
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的发件邮箱
SMTP_PASS=你的 SMTP 授权码
SENDER_NAME=AI 聊天助手
```

未配置 SMTP 时，邮箱注册与重置密码功能不可用。

## API 接口列表

### 认证相关
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/send-code` | 发送验证码邮件 |
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/refresh` | 刷新 Token |
| GET | `/api/auth/userinfo` | 获取用户信息 |
| PUT | `/api/auth/password` | 修改密码 |
| POST | `/api/auth/delete-account` | 注销账号 |

### 聊天相关
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 流式聊天（SSE） |
| POST | `/api/chat/vision` | 识图聊天（SSE） |
| GET | `/api/chat/models` | 获取模型列表 |
| GET | `/api/chat/status` | 聊天服务状态 |
| GET | `/api/chat/prompt-tool` | 提示词工具配置（候选模型/默认提示词） |
| POST | `/api/chat/prompt-tool` | 生成人物设定 / 图片提示词 |

### 图片生成
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/image/generate` | 文生图 / 图生图 |

### 语音相关
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/audio/transcriptions` | 语音转文字（STT） |
| POST | `/api/audio/speech` | 文字转语音（TTS） |
| GET | `/api/audio/voices` | 获取可用音色列表 |

### 供应商管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/providers` | 获取供应商列表 |
| GET | `/api/providers/all` | 获取全部供应商（含未启用） |
| GET | `/api/providers/vendors` | 获取供应商类型枚举 |
| GET | `/api/providers/config-schema` | 获取供应商配置字段 |
| POST | `/api/providers` | 创建供应商 |
| GET | `/api/providers/:id` | 获取供应商详情 |
| PUT | `/api/providers/:id` | 更新供应商 |
| DELETE | `/api/providers/:id` | 删除供应商 |
| PUT | `/api/providers/:id/default` | 设为默认供应商 |
| POST | `/api/providers/:id/test` | 测试连接 |
| GET | `/api/providers/:id/models` | 获取供应商模型列表 |
| POST | `/api/providers/:id/models/fetch` | 拉取模型列表 |

### 人设模板
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/personas` | 获取人设列表 |
| POST | `/api/personas` | 创建人设 |
| PUT | `/api/personas/:id` | 更新人设 |
| DELETE | `/api/personas/:id` | 删除人设 |
| PUT | `/api/personas/:id/default` | 设为默认人设 |

### 系统设置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 获取系统设置 |
| PUT | `/api/settings` | 更新系统设置 |
| PUT | `/api/settings/profile` | 更新个人资料（头像等；用户名与邮箱注册后不可修改） |

### 管理后台
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/login` | 管理后台登录 |
| GET | `/api/admin/me` | 当前管理员信息 |
| GET | `/api/admin/stats` | 平台概览统计 |
| GET | `/api/admin/users` | 用户列表 |
| GET | `/api/admin/users/:id/conversations` | 指定用户的对话列表 |
| GET | `/api/admin/conversations/:id/messages` | 指定对话的消息内容 |
| GET | `/api/admin/conversations/:id/export` | 导出指定对话 |

### 文件上传
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload/image` | 上传图片 |
| GET | `/api/upload/image/:filename` | 获取图片 |

### 对话存档
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 获取对话列表 |
| POST | `/api/conversations` | 创建对话 |
| GET | `/api/conversations/:id` | 获取对话详情 |
| PUT | `/api/conversations/:id` | 更新对话 |
| PUT | `/api/conversations/:id/pin` | 置顶对话 |
| DELETE | `/api/conversations/:id` | 删除对话 |
| DELETE | `/api/conversations/:id/messages` | 清空对话消息 |

## 支持的 API 类型

所有兼容 OpenAI 格式的 API 都可以使用，包括但不限于：

- **DeepSeek** - `https://api.deepseek.com/v1/chat/completions`
- **智谱 AI (GLM)** - `https://open.bigmodel.cn/api/paas/v4/chat/completions`
- **通义千问** - `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`
- **OpenAI** - `https://api.openai.com/v1/chat/completions`
- **Moonshot (月之暗面)** - `https://api.moonshot.cn/v1/chat/completions`
- 以及其他任何 OpenAI 兼容格式的 API

> 注意：识图和语音功能需要对应模型支持视觉 / 音频能力。

## 使用说明

1. 启动后端和前端服务
2. 访问前端页面，注册账号（用户名仅限字母、数字、下划线，注册后不可修改）并登录
3. 进入「模型配置」添加你的 AI 供应商（聊天、语音、图片生成可分别配置）
4. 开始聊天，或使用提示词工具生成人物设定 / 图片提示词
5. 管理后台入口为 `/admin`，需要使用 `.env` 中配置的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录

## License

MIT