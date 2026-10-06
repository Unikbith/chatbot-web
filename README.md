# Confide（心语）· AI 聊天助手 Web 版

> **Vue 3 + Flask 全栈 AI 聊天应用** —— 流式对话、深度思考、识图与多模态、AI 生图、人物卡与人设广场，把各家大模型 API 收拢进一个随手可用的网页。

基于 **Vue 3 + Flask** 构建的 AI 聊天应用，集对话、识图、创作与角色扮演于一体：底层兼容 DeepSeek / 智谱 GLM / 通义千问 / OpenAI 等所有 OpenAI 风格接口，支持**流式响应、深度思考（Reasoner）推理、识图对话、AI 文生图 / 图生图、语音输入输出**，并提供**人物卡（AI 人设 / 用户人设）、世界书、人设广场、提示词工具、多供应商管理与独立管理后台**。自带邮箱注册登录、云端对话存档、记忆宫殿（滚动摘要）与响应式移动端适配，可一键部署到自己的云服务器。

## 功能特性

### 核心聊天
- 流式对话，实时响应
- 支持多种 AI 模型（DeepSeek、智谱 GLM、通义千问、OpenAI 等所有 OpenAI 兼容格式）
- 深度思考模式（DeepSeek Reasoner 等推理模型）
- 自定义人物设定提示词（单对话可覆盖模板）
- 回复长度、采样参数（温度 / 频率惩罚 / 存在惩罚）自由调节
- 提示词兜底开关：**默认开启**，把后端写死的全局约定（世界观 / 语气 / 禁区）接在人物设定之后，
  角色更不容易跳出设定；在意 token 时可在「对话设置」里按会话关闭
- 单角色与多角色扮演都由**人物卡自己的系统提示词**定义 —— 不再有会话级的「角色阵容」副本，
  避免同一份设定存两处、改一处不生效

### 结构化输出（界面标记 + 渲染模板）
- 模型用**行首标记**输出结构化内容（`【场景】【面板】【状态】【内心】【记忆】【推演】` 等），
  前端把它们渲染成场景条、信息卡片、数值条、内心块、记忆回廊与可点选项 —— 对白/旁白/括号动作各自成套版式
- **13 套渲染预设**（档案风 / 极简 / 霓虹 / 和纸 / 终端 / 银幕 / 信笺 / 启示 / 脸红 / 月色 / 余温 / 微醺 / 红线，
  默认「脸红」）：预设只换 CSS 变量，骨架（DOM 结构）完全一致，因此「换风格」不会改变信息结构
- 会话设置里可开关「界面标记」、选回复外观、调回复长度；**注入提示词只由后端 `Flask/reply_spec.py` 提供**，
  新建对话与历史对话行为一致，前端不再自带一份会漂移的提示词
- **结构稳定性约定**：
  - 每轮构件**种类、数量、顺序固定**（场景 → 四块面板 → 状态 → 内心 → 记忆 → 推演 →[按需]物品/提醒），
    并明确要求「场景条只写一个、地点与时间只出现一次、字段写名字、不自创标记名」
  - 前端渲染**不按位置硬取字段**：场景/状态条按「地点 / 时间 / 氛围」的语义归位，
    模型把顺序写反也不会让地点跑到时间的位置上
  - 记忆回廊的长期记忆来自系统摘要，模型漏写 `【记忆】` 时由前端补出，界面上不会时有时无
  - **没有「聊几轮后自动关闭」**：早期版本会在第 2/3 轮自动关掉提示词增强与提示词兜底来省 token，
    结果结构规范中途消失、界面构件开始漂移；现在两个开关都默认开启且只由用户控制
  - 解析容错：字面 `<br>` 还原为换行、句中标记自动拆到行首、未知标记退回通用组件（绝不把标记原文漏进正文）

### 人物卡与世界书
- **人物卡**：分别配置 AI 人设与用户人设，可设为默认、随对话切换
- **世界书（设定条目）**：为角色维护按需注入的设定条目，命中才进上下文，不命中不占 token
- 世界书支持关键词触发，条目可增删改查

### 人设广场
- 发布自己的人物卡到广场，支持标题、简介、系统提示词与开场白
- **与人物卡字段对齐**：还可以带上「玩家设定」（这张卡里你是谁）与「世界书」
  （随卡分享的按需注入设定）—— 两者**都是可选的**，不填一样能发布
- 采用（一键添加）时，玩家设定与世界书条目会一并复制成你自己名下的数据，
  之后随便改；卡片列表上会标出「随卡带了几条世界书设定」
- 浏览、筛选、按类型过滤，查看他人卡片详情与评论
- 投票、评论与点赞互动
- **一键采用**：把广场卡片导入为自己的角色（可取消采用）
- 确定性假名展示，发布者身份不外泄
- **每日签到**：签到即赠 5 次免费生图机会，签到状态可查询

### 上下文成本优化
- **记忆回廊**：每轮回复里同时展示「短期记忆」（模型写的条目）与「长期记忆 = 记忆宫殿」
  （应用自己的滚动摘要）。长期记忆来自系统数据，**模型某一轮漏写标记也会照常显示**；
  摘要默认折叠、按行展示，不会糊成一坨
- **记忆宫殿（滚动摘要）**：每 N 轮把较早对话压成一条摘要，既防遗忘又减少输入 token，阈值可调（1–20 轮，默认 10）
- 摘要历史可查看，压缩记录留存
- 历史正文设字数预算，条数窗口不够时自动截断，控制长对话成本

### 识图对话
- 上传图片，AI 理解图片内容，支持基于图片多轮对话
- 识图同样支持模型选择与深度思考开关
- 失败原因可视化：鉴权失败 / 接口不存在 / 模型不支持图片 / 图片过大 / 服务不可用等分类诊断
- 识图图片落库留档，聊天记录可回看

### AI 图片生成
- 文生图 / 图生图，支持多分辨率、长宽比与画质档位
- 支持按关键词触发：`生图` / `生成图片` / `画一张` 生成图片，`改图` / `图生图` / `修改图片` 修改图片
- **配置优先**：只要能挑到用户自己的图片配置就用它 —— 优先「已启用」的那条，
  其次任意一条（停止启用状态也会用），一条都没有才回退到内置免费 Key。
  「配好了却因为忘了拨启用开关而落到免费通道」这一坑不会再出现
- 保存图片配置即视为启用（列表里的启用开关只用于在多个图片配置之间挑选）
- 免费用户有每日额度，签到可补充；超过后可自行在「模型配置 - 图片生成」中配置 API Key
- 参考图与生成结果自动写入对话记录
- **失败原因可执行**：报错会指出用的是哪条配置，提示去检查该配置的 Key / 地址 / 模型；
  共享免费通道不可用时明确提示改用自有 Key，而不是笼统的「请稍后重试」
- 「模型配置 → 图片生成」会显示当前生图实际使用哪条配置，状态一目了然

### 提示词工具
- 一键生成人物设定提示词与图片提示词（文生图 / 图生图）
- 支持自选已启用模型与自定义系统提示词，替代原「清空对话」入口
- 生成失败会把原因直接写进输出框

### 语音交互
- 语音输入（STT），说话转文字
- 语音播报（TTS），AI 回复朗读
- 多种音色可选，音色跟随 TTS 模型配置
- 会话内可独立开关「AI 回复自动语音播报」

### 用户系统
- 邮箱注册 / 登录（JWT 认证，邮箱验证码）
- 用户名限普通字符串（字母、数字、下划线），注册后与邮箱一样不可修改
- 注册须勾选用户须知与免责声明（`/user-agreement`）
- 独立管理后台（管理员登录、用户与对话审计、广场内容管理）
- 云端对话存档，本地存储兼容模式
- 帮助与反馈：内置帮助文档，可提交反馈并留联系方式
- **新用户教程**：侧边栏常驻入口，注册后首次登录自动弹出一次；
  内容与《新用户使用教程》一致（配置 API → 获取 Key → 拉模型 → 建人物卡 → 提示词工具 → 开始畅聊 → 反馈）
- **免费模型提醒**：未配置自有 API 的用户**每次进入都会提醒一次**（弹窗 + 侧边栏常驻提示条），
  说明共享免费模型（GLM-4-Flash）限制多、回复容易出戏，建议换成自己的 API Key；
  已配置自己模型的用户不再打扰

### 个性化设置
- 自定义头像和背景（背景支持「完全可见 / 覆盖背景」两种展示方式）
- 消息气泡透明度调节
- 会话级独立配置：AI / 用户头像、AI 采样参数、自动播报、背景
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
│   ├── routes/             # 路由层，按业务划分的接口
│   │   ├── auth.py         # 认证：注册/登录/验证码/改密/重置
│   │   ├── chat.py         # 聊天与识图、提示词工具、上下文压缩与世界书注入
│   │   ├── audio.py        # 语音识别与合成
│   │   ├── conversation.py # 对话存档与摘要
│   │   ├── provider.py     # 模型供应商与密钥管理、连接测试
│   │   ├── persona.py      # 人物卡模板与世界书条目
│   │   ├── marketplace.py  # 人设广场：发布/投票/评论/采用、每日签到
│   │   ├── feedback.py     # 用户反馈
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
│       ├── media_log.py          # 对话素材记录统一写入口
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
        ├── router/         # 路由配置（/、/admin、/chatbotAdmin、/user-agreement）
        ├── views/          # 页面
        │   ├── Home.vue            # 主页（聊天 + 各设置面板）
        │   ├── AdminLogin.vue      # 管理后台登录
        │   ├── AdminBackend.vue    # 管理后台
        │   └── UserAgreement.vue   # 用户须知与免责声明
        ├── components/     # 组件
        │   ├── AuthModal.vue            # 登录/注册
        │   ├── ChatArea.vue             # 聊天区（含识图与生图链路）
        │   ├── ConversationSettings.vue # 会话设置（记忆宫殿等）
        │   ├── FreeApiReminderDialog.vue # 免费模型提醒（未配置 API 的用户每次进入提醒）
        │   ├── NewUserTutorialDialog.vue # 新用户使用教程
        │   ├── PromptToolPanel.vue      # 提示词工具
        │   ├── PersonaPanel.vue         # 人物卡与世界书面板
        │   ├── PersonaMarketplace.vue   # 人设广场
        │   ├── ProviderPanel.vue        # 供应商配置面板
        │   ├── Sidebar.vue              # 侧边栏
        │   ├── SystemSettings.vue       # 系统设置（通用/账号/帮助反馈）
        │   ├── ImageUpload.vue          # 图片上传
        │   └── VoiceInput.vue           # 语音输入
        ├── i18n/           # 多语言
        └── utils/          # 工具：请求封装/认证/主题/帮助文档等
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

### 生产部署（Nginx + gunicorn）

```bash
# 1. 构建前端（产物在 VUE/dist）
cd VUE && npm ci && npm run build

# 2. 启动后端（生产环境务必设置 FLASK_ENV=production 与强随机密钥）
cd ../Flask
pip install -r requirements.txt
FLASK_ENV=production gunicorn -w 4 -k gthread --threads 4 -b 127.0.0.1:5000 app:create_app()
```

Nginx 参考配置（已针对首屏性能做 gzip 与长期缓存优化）：

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    root /path/to/chatbot-web/VUE/dist;
    index index.html;

    # gzip 压缩：JS/CSS 体积可减少约 70%，显著加快首屏
    gzip on;
    gzip_comp_level 6;
    gzip_min_length 1k;
    gzip_vary on;
    gzip_types text/plain text/css application/javascript application/json
               application/xml image/svg+xml application/wasm;

    # 带 hash 的静态资源长期缓存（内容变更即换名，可放心 immutable）
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }
    location ~* \.(png|jpe?g|gif|webp|svg|woff2?)$ {
        expires 30d;
        add_header Cache-Control "public";
    }

    # index.html 不缓存，保证每次拿到最新入口
    location = /index.html {
        add_header Cache-Control "no-cache, must-revalidate";
    }

    # API 反向代理（流式接口需关闭缓冲）
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;              # SSE 流式聊天必须关闭
        proxy_read_timeout 300s;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }

    # 安全响应头
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

> 部署在 Nginx/网关之后时，将 `Flask/.env` 的 `TRUST_PROXY_HEADERS` 设为 `true`，
> 并把 `CORS_ORIGINS` 改为你的真实域名。

### 数据库选型与迁移建议

默认 SQLite 适合单机、低到中等写入量的部署；当前代码会自动启用 WAL、`busy_timeout`
和 `foreign_keys`，管理后台也已改为分页查询。以下情况建议迁移到 MySQL 8 或 PostgreSQL：

- 多个写入进程同时高频写消息，或开始出现 `database is locked`；
- 需要定时备份、在线扩容、主从、监控和更细粒度的用户权限；
- 单表数据达到百万级，后台统计和复合查询开始明显变慢。

迁移前必须先备份 `Flask/instance/chatbot.db`。配置示例：

```text
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/confide?charset=utf8mb4
APP_TIMEZONE=Asia/Shanghai
```

数据库类型切换只通过 `DATABASE_URL` 完成，但历史数据不会自动搬迁；生产环境应先做
“停写 → 备份 → 数据导出/导入 → 校验行数和 Token 汇总 → 切换 DNS/环境变量 → 回滚演练”。
时间字段历史数据存在“旧 UTC + 新应用时区”混用，切库前应按实际部署切换时间做一次
离线校准，不能在新库里直接对所有时间统一加固定偏移。

### ⚠️ 上线前安全清单

1. **轮换密钥**：`.env` 中若曾填写过真实密钥，上线前务必在对应平台重置
   （SMTP 授权码、免费 API Key、生图 Key、管理员密码），并重新生成
   `SECRET_KEY` / `JWT_SECRET_KEY`（`python -c "import secrets;print(secrets.token_hex(32))"`）。
2. **不要提交 `.env`**：`.env` 已被 `.gitignore` 排除；服务器上用环境变量注入，而非上传文件。
3. **HTTPS**：生产必须启用 HTTPS，否则令牌与内容明文传输。
4. **Access Token 有效期** 默认 2 小时（`JWT_ACCESS_TOKEN_EXPIRES`），过期后前端自动静默续期。
5. **SSRF 防护** 保持开启（`SSRF_PROTECTION=true`），拦截指向内网/云元数据的外发请求。

### SMTP 邮件配置（邮箱注册 / 重置密码）

在 `Flask/.env` 中配置邮件服务，用于发送注册与重置密码的验证码：

```
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的发件邮箱
SMTP_PASS=你的 SMTP 授权码
SENDER_NAME=心语
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
| POST | `/api/auth/verify-code` | 校验验证码 |
| POST | `/api/auth/reset-password` | 重置密码 |
| POST | `/api/auth/delete-account` | 注销账号 |

### 聊天相关
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chat/status` | 聊天服务状态 |
| POST | `/api/chat` | 流式聊天（SSE） |
| POST | `/api/chat/vision` | 识图聊天（SSE，支持 model_id / deep_think / image_url） |
| GET | `/api/chat/models` | 获取模型列表 |
| GET | `/api/chat/prompt-tool` | 提示词工具配置（候选模型 / 默认提示词） |
| POST | `/api/chat/prompt-tool` | 生成人物设定 / 图片提示词 |

### 对话存档
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 获取对话列表 |
| POST | `/api/conversations` | 创建对话 |
| GET | `/api/conversations/:conv_id` | 获取对话详情 |
| PUT | `/api/conversations/:conv_id` | 更新对话 |
| GET | `/api/conversations/:conv_id/summaries` | 获取记忆宫殿压缩摘要 |
| PUT | `/api/conversations/:conv_id/pin` | 置顶对话 |
| DELETE | `/api/conversations/:conv_id` | 删除对话 |
| DELETE | `/api/conversations/:conv_id/messages` | 清空对话消息 |

### 人物卡与世界书
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/personas` | 获取人物卡列表 |
| POST | `/api/personas` | 创建人物卡 |
| GET | `/api/personas/:persona_id` | 获取人物卡详情 |
| PUT | `/api/personas/:persona_id` | 更新人物卡 |
| DELETE | `/api/personas/:persona_id` | 删除人物卡 |
| PUT | `/api/personas/:persona_id/default` | 设为默认人物卡 |
| GET | `/api/personas/:persona_id/worldbook` | 获取世界书条目 |
| POST | `/api/personas/:persona_id/worldbook` | 新增世界书条目 |
| PUT | `/api/personas/:persona_id/worldbook/:entry_id` | 更新世界书条目 |
| DELETE | `/api/personas/:persona_id/worldbook/:entry_id` | 删除世界书条目 |

### 人设广场
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/marketplace` | 广场卡片列表 |
| POST | `/api/marketplace` | 发布卡片 |
| GET | `/api/marketplace/:pid` | 卡片详情 |
| PUT | `/api/marketplace/:pid` | 更新卡片 |
| DELETE | `/api/marketplace/:pid` | 删除卡片 |
| GET | `/api/marketplace/public` | 公开卡片列表 |
| GET | `/api/marketplace/public/:pid` | 公开卡片详情 |
| GET | `/api/marketplace/public/:pid/comments` | 公开卡片评论 |
| GET | `/api/marketplace/genders` | 类型（性别）枚举 |
| POST | `/api/marketplace/:pid/vote` | 投票 |
| POST | `/api/marketplace/:pid/adopt` | 采用卡片 |
| POST | `/api/marketplace/:pid/unadopt` | 取消采用 |
| GET | `/api/marketplace/:pid/comments` | 获取评论 |
| POST | `/api/marketplace/:pid/comments` | 发表评论 |
| POST | `/api/marketplace/comments/:cid/like` | 评论点赞 |
| POST | `/api/marketplace/checkin` | 每日签到（赠免费生图次数） |
| GET | `/api/marketplace/checkin/status` | 签到状态 |

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
| GET | `/api/providers/vendors` | 获取供应商类型枚举 |
| GET | `/api/providers/config-schema` | 获取供应商配置字段 |
| GET | `/api/providers` | 获取供应商列表 |
| GET | `/api/providers/all` | 获取全部供应商（含未启用） |
| POST | `/api/providers` | 创建供应商 |
| GET | `/api/providers/:provider_id` | 获取供应商详情 |
| PUT | `/api/providers/:provider_id` | 更新供应商 |
| DELETE | `/api/providers/:provider_id` | 删除供应商 |
| PUT | `/api/providers/:provider_id/default` | 设为默认供应商 |
| POST | `/api/providers/:provider_id/test` | 测试连接（图片类为真实出图探测） |
| GET | `/api/providers/:provider_id/models` | 获取供应商模型列表 |
| POST | `/api/providers/:provider_id/models` | 新增模型 |
| POST | `/api/providers/:provider_id/models/fetch` | 拉取模型列表 |
| PUT | `/api/providers/:provider_id/models/:model_id` | 更新模型 |
| DELETE | `/api/providers/:provider_id/models/:model_id` | 删除模型 |
| POST | `/api/providers/:provider_id/models/:model_id/test` | 测试单个模型 |

### 系统设置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 获取系统设置 |
| PUT | `/api/settings` | 更新系统设置 |
| PUT | `/api/settings/profile` | 更新个人资料（头像等；用户名与邮箱注册后不可修改） |

### 文件上传
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload/image` | 上传图片 |
| GET | `/api/upload/image/:filename` | 获取图片 |

### 用户反馈
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/feedback` | 提交反馈（需登录） |
| GET | `/api/feedback` | 反馈列表（管理员） |

### 管理后台
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/login` | 管理后台登录 |
| GET | `/api/admin/me` | 当前管理员信息 |
| GET | `/api/admin/stats` | 平台概览统计 |
| GET | `/api/admin/users` | 用户列表 |
| GET | `/api/admin/users/:user_id/conversations` | 指定用户的对话列表 |
| GET | `/api/admin/users/:user_id/summary` | 用户概览与 Token 汇总 |
| GET | `/api/admin/users/:user_id/personas` | 用户人物卡与玩家设定 |
| GET | `/api/admin/users/:user_id/providers` | 用户模型配置（Key 掩码） |
| GET | `/api/admin/users/:user_id/settings` | 用户设置只读视图 |
| GET | `/api/admin/users/:user_id/usage` | 按天/模型/对话聚合 Token 用量 |
| DELETE | `/api/admin/conversations/:conv_id` | 删除指定对话 |
| POST | `/api/admin/conversations/batch-delete` | 批量删除对话 |
| GET | `/api/admin/conversations/:conv_id/messages` | 指定对话的消息内容 |
| GET | `/api/admin/conversations/:conv_id/export` | 导出指定对话 |
| GET | `/api/admin/marketplace` | 广场卡片管理列表 |
| GET | `/api/admin/marketplace/:pid` | 广场卡片详情 |
| PUT | `/api/admin/marketplace/:pid` | 更新广场卡片 |
| DELETE | `/api/admin/marketplace/:pid` | 下架广场卡片 |
| GET | `/api/admin/prompt-tool-logs` | 提示词记录 |
| DELETE | `/api/admin/prompt-tool-logs/:log_id` | 删除单条提示词记录 |
| POST | `/api/admin/prompt-tool-logs/batch-delete` | 批量删除提示词记录 |
| GET | `/api/admin/conversation-media-logs` | 对话素材记录 |
| DELETE | `/api/admin/conversation-media-logs/:log_id` | 删除单条素材记录 |
| POST | `/api/admin/conversation-media-logs/batch-delete` | 批量删除素材记录 |

**对话素材记录**覆盖用户所有图片素材（按类型可筛，系统级素材显示为「系统」而非对话标题）：

| media_type | 含义 | 归属 |
| --- | --- | --- |
| `background` / `ai_avatar` / `user_avatar` | 对话设置里的背景图 / AI 头像 / 用户头像 | 具体对话 |
| `profile_background` / `profile_avatar` / `profile_ai_avatar` | 系统设置里的背景图 / 用户头像 / AI 头像 | 系统 |
| `upload` | 一切经 `/api/upload/image` 上传的图片（聊天发送的图片、识图兜底落盘等） | 系统或所属对话 |

同一用户同一类型下重复提交完全相同的图片不会重复记录；记录与素材本身分离，
管理员删除记录不会影响用户界面上正在生效的头像或背景。


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
2. 访问前端页面，注册账号（需勾选用户须知与免责声明；用户名仅限字母、数字、下划线，注册后不可修改）并登录
3. 进入「模型配置」添加你的 AI 供应商（聊天、语音、图片生成可分别配置），可用「测试连接」验证配置是否可用
4. 开始聊天；需要角色扮演时在「人物卡」中配置 AI / 用户人设，并可为角色维护「世界书」条目
5. 想参考或分享设定，去「人设广场」浏览、投票、评论，或一键采用他人的卡片；每日签到可补充免费生图次数
6. 长对话可在「会话设置 - 记忆宫殿」中开启滚动摘要，控制上下文成本
7. 使用提示词工具生成人物设定 / 图片提示词
8. 管理后台入口为 `/chatbotAdmin`（登录页 `/admin`），使用 `.env` 中配置的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录
