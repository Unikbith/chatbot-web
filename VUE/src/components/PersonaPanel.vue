<template>
  <el-drawer
    v-model="visible"
    title="人物卡管理"
    size="min(500px, 100vw)"
    class="persona-drawer"
    @close="handleClose"
  >
    <div class="persona-panel">
      <div class="persona-list">
        <div
          v-for="persona in personas"
          :key="persona.id"
          class="persona-card"
          :class="{ active: selectedId === persona.id }"
          @click="editPersona(persona)"
        >
          <el-avatar :size="44" :src="persona.avatar" class="persona-avatar">
            <el-icon><MagicStick /></el-icon>
          </el-avatar>
          <div class="persona-info">
            <div class="persona-name">
              {{ persona.name }}
              <el-tag v-if="persona.source === 'marketplace'" size="small" type="warning" effect="light" class="source-tag">卡片广场</el-tag>
            </div>
            <div class="persona-desc">{{ persona.description || '暂无描述' }}</div>
          </div>
          <div class="persona-actions" @click.stop>
            <el-button
              size="small"
              text
              type="primary"
              @click="editPersona(persona)"
            >
              编辑
            </el-button>
            <el-button
              size="small"
              text
              type="danger"
              @click="confirmDelete(persona.id)"
            >
              删除
            </el-button>
          </div>
        </div>

        <div v-if="personas.length === 0" class="empty-tip">
          <el-empty description="暂无人物卡，点击下方按钮创建" :image-size="80" />
        </div>
      </div>

      <div class="panel-footer">
        <span class="footer-count">人物卡 {{ personas.length }}/{{ PERSONA_CARD_LIMIT }}</span>
        <el-button
          type="primary"
          icon="Plus"
          :disabled="personas.length >= PERSONA_CARD_LIMIT"
          @click="openCreateDialog"
        >
          新建人物卡
        </el-button>
      </div>
    </div>

    <!-- 编辑/创建对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      :title="editingPersona ? '编辑人物卡' : '新建人物卡'"
      width="min(560px, 94vw)"
      @close="resetForm"
    >
      <el-form :model="form" label-position="top" class="persona-form">
        <!-- 头像上传：居中大图预览，与系统卡片风格一致 -->
        <el-form-item>
          <div class="form-avatar-section">
            <div class="form-avatar-preview">
              <img v-if="form.avatar" :src="form.avatar" alt="" />
              <el-icon v-else class="form-avatar-placeholder"><MagicStick /></el-icon>
            </div>
            <el-upload
              :show-file-list="false"
              :before-upload="handleAvatarUpload"
              accept="image/*"
            >
              <el-button size="small" type="primary" plain>
                <el-icon><Upload /></el-icon> 上传头像
              </el-button>
            </el-upload>
          </div>
        </el-form-item>

        <div class="form-card">
          <el-form-item label="角色名称">
            <el-input v-model="form.name" placeholder="如：加藤惠" maxlength="1000" />
          </el-form-item>
          <el-form-item label="角色简介">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              :autosize="false"
              resize="none"
              placeholder="简述角色特点（只是用于人物卡信息展示不作为提示词参考，人设相关提示词请写入下方AI角色设定）"
              maxlength="1000"
            />
          </el-form-item>
        </div>

        <div class="form-card">
          <el-form-item label="AI角色设定">
            <el-input
              v-model="form.system_prompt"
              type="textarea"
              :rows="8"
              :autosize="false"
              resize="none"
              placeholder="详细的角色设定，指导 AI 如何扮演这个角色...（这是 AI 真正遵循的系统提示词。角色名称会作为身份提示一并发送；简介不会。）"
              maxlength="10000"
            />
            <!-- 这段提示词每轮都会原样发给模型，是固定成本：提醒用户别把协议正文抄进来 -->
            <div class="form-hint">
              这段设定每轮都会发送给模型，越长越费 token —— 建议控制在几百字：写清身份、性格、外貌、说话方式就够，
              不要把协议条目（创作/结构/玩法规范）的正文复制进来，那些由「对话设置」的开关控制。
              <span v-if="promptLenHint" class="form-hint__len">当前 {{ promptLenHint }} 字</span>
            </div>
          </el-form-item>
          <!-- 玩家侧设定：与 AI 提示词同卡绑定，换卡即换整套角色关系 -->
          <el-form-item label="玩家设定">
            <el-input
              v-model="form.user_prompt"
              type="textarea"
              :rows="4"
              :autosize="false"
              resize="none"
              placeholder="你自己（玩家）在这张卡里的身份设定：姓名、年龄、身份、与角色的关系、性格外貌等。留空则 AI 不知道你是谁。（这里写「你是谁」。会随 AI 提示词一起发给模型，让角色认得你、称呼你、按你们的关系互动。）"
              maxlength="4000"
            />
          </el-form-item>
          <el-form-item label="开场问候语">
            <el-input
              v-model="form.greeting"
              type="textarea"
              :rows="2"
              :autosize="false"
              resize="none"
              placeholder="角色第一次打招呼时说的话（可选）"
              maxlength="1000"
            />
            <div class="form-hint">不会作为系统规则注入；新建对话时会作为第一条 AI 问候展示并保存。</div>
          </el-form-item>
        </div>

        <!-- 世界书：编辑时立即保存；新建时先作为草稿，随人物卡一起提交 -->
        <div class="form-card">
          <div class="wb-head">
            <div class="wb-head-text">
              <div class="wb-title">
                {{ t('世界书', 'Worldbook') }}
                <span class="wb-count">{{ wbEntries.length }}</span>
              </div>
              <div class="wb-desc">
                {{ t('只在聊到相关词时才加载的设定，省 token 也能写更多内容。', 'Lore loaded only when relevant — saves tokens, holds more.') }}
                <b>{{ t('常驻', 'Always') }}</b>{{ t('＝每轮都注入（如「③ 剧情推进与体验协议」）；其余按触发词命中才注入。② 创作与内容协议默认关，由「对话设置 → 提示词兜底」控制；这里关掉某条只影响这张卡。', ' = injected every turn (e.g. the pacing protocol); others load when a trigger word appears. The writing & content entry is off by default and gated by the “Fallback Prompt” switch in Conversation Settings; turning an entry off here only affects this card.') }}
                <span v-if="!editingPersona" class="wb-draft-note">{{ t('新建模式下条目会随人物卡一起保存。', 'In create mode, entries are saved with the card.') }}</span>
              </div>
            </div>
            <div class="wb-head-ops">
              <el-button
                v-if="editingPersona"
                size="small"
                plain
                :loading="protocolRestoring"
                @click="restoreProtocolPack"
              >
                {{ t('恢复默认协议包', 'Restore protocol pack') }}
              </el-button>
              <el-button size="small" type="primary" plain @click="openWbCreate">
                <el-icon><Plus /></el-icon> {{ t('添加条目', 'Add entry') }}
              </el-button>
            </div>
          </div>

          <div v-if="wbLoading" class="wb-empty">{{ t('加载中…', 'Loading…') }}</div>
          <div v-else-if="!wbEntries.length" class="wb-empty">
            {{ editingPersona ? t('暂无条目 —— 协议包与设定都为空，AI 将没有输出结构与创作规范（可点「恢复默认协议包」一键补回）', 'No entries — neither protocol pack nor lore. The AI will have no structure or writing rules (use Restore protocol pack).') : t('暂无条目，可先添加触发词和设定内容，新建人物卡时会一起保存', 'No entries yet. Add trigger words and content; they are saved with the new card.') }}
          </div>

          <template v-else>
            <!-- 分组展示：协议包（系统种入的规范）与自己的设定条目分开，
                 避免十份长规范把用户自己的设定淹没 -->
            <div v-for="grp in wbGroups" :key="grp.key" class="wb-group">
              <div class="wb-group-head">
                <span class="wb-group-name">{{ grp.name }}</span>
                <span class="wb-group-hint">{{ grp.hint }}</span>
                <span class="wb-group-count">{{ grp.items.length }}</span>
              </div>

              <div class="wb-list">
                <div
                  v-for="e in grp.items"
                  :key="e.id"
                  class="wb-item"
                  :class="{ 'is-protocol': e.category === 'protocol', 'is-off': !e.enabled }"
                >
                  <!-- 条目标题行：标记 + 名称 + 触发词摘要 + 操作 -->
                  <div class="wb-item-head" @click="toggleWbExpand(e)">
                    <span class="wb-caret" :class="{ open: isWbExpanded(e) }">▸</span>
                    <span v-if="e.category === 'protocol'" class="wb-tag is-proto">{{ t('协议', 'Protocol') }}</span>
                    <span
                      class="wb-tag"
                      :class="isCoreProtocol(e) ? 'is-switch' : (e.always_on ? 'is-on' : 'is-demand')"
                    >
                      {{ wbTagText(e) }}
                    </span>
                    <span class="wb-name">{{ e.title || t('未命名条目', 'Untitled') }}</span>
                    <span v-if="!e.enabled" class="wb-tag is-off">{{ t('已停用', 'Disabled') }}</span>
                    <span v-if="!isWbExpanded(e)" class="wb-preview">{{ wbPreview(e) }}</span>
                    <span class="wb-size">{{ e.content.length }}{{ t(' 字', ' chars') }}</span>
                    <div class="wb-ops" @click.stop>
                      <el-switch
                        v-model="e.enabled"
                        size="small"
                        @change="(val) => toggleWb(e, val)"
                      />
                      <el-button size="small" text @click="openWbEdit(e)">{{ t('编辑', 'Edit') }}</el-button>
                      <el-button size="small" text type="danger" @click="removeWb(e)">{{ t('删除', 'Delete') }}</el-button>
                    </div>
                  </div>

                  <!-- 展开后才显示正文与触发词：默认收起，列表才看得清 -->
                  <div v-if="isWbExpanded(e)" class="wb-item-body">
                    <div v-if="e.keywords" class="wb-kw-row">
                      <span class="wb-kw-label">{{ t('触发词', 'Triggers') }}</span>
                      <span v-for="kw in wbKeywordList(e)" :key="kw" class="wb-kw-chip">{{ kw }}</span>
                      <span v-if="!wbKeywordList(e).length" class="wb-kw-none">
                        {{ isCoreProtocol(e) ? t('（由会话设置里的开关控制，无需触发词）', '(controlled by the switch in Conversation Settings)') : t('（常驻，无需触发词）', '(always on)') }}
                      </span>
                    </div>
                    <pre class="wb-content">{{ e.content }}</pre>
                    <div v-if="e.source_key" class="wb-source">
                      {{ t('系统条目', 'System entry') }} · {{ e.source_key }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="savePersona" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 世界书条目编辑（append-to-body，避免被外层弹窗裁剪） -->
    <el-dialog
      v-model="wbDialogVisible"
      :title="wbEditing ? '编辑设定条目' : '添加设定条目'"
      width="min(560px, 94vw)"
      append-to-body
    >
      <el-form :model="wbForm" label-position="top">
        <el-form-item label="条目名称（方便自己认，不发给 AI）">
          <el-input v-model="wbForm.title" placeholder="如：童年经历 / 咖啡馆设定" maxlength="200" />
        </el-form-item>
        <el-form-item label="触发词（逗号分隔，最近对话里出现就加载本条）">
          <el-input
            v-model="wbForm.keywords"
            type="textarea"
            :rows="2"
            :autosize="false"
            resize="none"
            placeholder="如：童年,妈妈,小时候"
            maxlength="1000"
          />
        </el-form-item>
        <el-form-item label="设定内容">
          <el-input
            v-model="wbForm.content"
            type="textarea"
            :rows="6"
            :autosize="false"
            resize="none"
            placeholder="命中触发词后才注入的设定正文…"
            maxlength="8000"
          />
        </el-form-item>
        <el-form-item>
          <!-- 核心协议的注入由会话开关控制，条目自身的「常驻」已无意义：
               这里换成说明文字，避免用户勾了却发现没效果 -->
          <div v-if="editingCoreWb" class="wb-core-note">
            这是协议包的核心条目：要不要注入由「对话设置」里的开关决定（提示词兜底 / 界面标记 + 丰富面板内容），
            这里不需要设常驻或触发词。
          </div>
          <el-checkbox v-else v-model="wbForm.always_on">常驻（每次对话都加载，用于核心人设）</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="wbDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveWbEntry" :loading="wbSaving">保存</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import logger from '@/utils/logger';
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Upload, Plus } from '@element-plus/icons-vue'
import { personaApi, uploadApi } from '../utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: Boolean,
  selectedId: [String, Number],
})

const emit = defineEmits(['update:modelValue', 'update:selectedId', 'persona-changed', 'persona-deleted'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 人物卡（AI 人设）数量上限，与后端 PERSONA_CARD_LIMIT 保持一致
const PERSONA_CARD_LIMIT = 10

const personas = ref([])
const editDialogVisible = ref(false)
const editingPersona = ref(null)
const saving = ref(false)

const defaultForm = {
  name: '',
  description: '',
  avatar: '',
  system_prompt: '',
  user_prompt: '',
  greeting: '',
  persona_type: 'ai',
}

const form = reactive({ ...defaultForm })

watch(() => props.modelValue, (val) => {
  if (val) {
    loadPersonas()
  }
})

async function loadPersonas() {
  try {
    const res = await personaApi.list()
    if (res.code === 200) {
      personas.value = res.data
    }
  } catch (e) {
    logger.error('加载角色失败', e)
  }
}

function handleClose() {
  visible.value = false
}

function selectPersona(persona) {
  emit('update:selectedId', persona.id)
  emit('persona-changed', persona)
}

function editPersona(persona) {
  editingPersona.value = persona
  Object.assign(form, {
    name: persona.name,
    description: persona.description || '',
    avatar: persona.avatar || '',
    system_prompt: persona.system_prompt,
    user_prompt: persona.user_prompt || '',
    greeting: persona.greeting || '',
    persona_type: persona.persona_type || 'ai',
  })
  editDialogVisible.value = true
  loadWorldBook()
}

/**
 * 供侧边栏「人物卡」列表点击后直接打开对应人物卡的编辑详情。
 * 打开抽屉 → 拉取最新列表 → 弹出编辑对话框。
 */
async function openEdit(persona) {
  visible.value = true
  await loadPersonas()
  const fresh = personas.value.find(p => p.id === persona.id) || persona
  editPersona(fresh)
}

defineExpose({ openEdit })

function openCreateDialog() {
  editingPersona.value = null
  resetForm()
  editDialogVisible.value = true
}

function resetForm() {
  Object.assign(form, defaultForm)
  wbEntries.value = []
}

/* ---------- 世界书（设定条目 + 协议包） ---------- */
const wbEntries = ref([])
const wbLoading = ref(false)
const wbDialogVisible = ref(false)
const wbEditing = ref(null)
const wbSaving = ref(false)
const protocolRestoring = ref(false)
// 展开的条目 id 集合：世界书默认全部收起，否则十份长规范会把面板撑成一片文字墙
const wbExpanded = ref(new Set())
let wbDraftSeq = 0

function isWbExpanded(entry) {
  return wbExpanded.value.has(entry.id)
}

function toggleWbExpand(entry) {
  const next = new Set(wbExpanded.value)
  if (next.has(entry.id)) next.delete(entry.id)
  else next.add(entry.id)
  wbExpanded.value = next
}

// 收起状态下的一行摘要：去掉换行、标记，截断到 ~60 字
function wbPreview(entry) {
  const text = String(entry.content || '')
    .replace(/【[^】]*】/g, '')
    .replace(/^[·\-*\s]+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > 60 ? text.slice(0, 60) + '…' : text
}

function wbKeywordList(entry) {
  return String(entry.keywords || '')
    .split(/[,，;；\n\r]+/)
    .map(s => s.trim())
    .filter(Boolean)
}

// AI 角色设定的字数提示（`0` 表示没填，不显示）
const promptLenHint = computed(() => (form.system_prompt || '').trim().length)

// 三条核心协议（输出结构 / 创作与内容 / 剧情推进）的注入方式各不相同：
//   ① 输出结构 ← 对话设置里的「界面标记 + 丰富面板内容」
//   ② 创作与内容 ← 对话设置里的「提示词兜底」（默认关）
//   ③ 剧情推进 ← 常驻（每轮注入，不看对话开关）
// 所以角标显示「开关控制」「常驻」而不是统一的「常驻 / 按需」，避免误导。
const CORE_PROTOCOL_KINDS = ['structure', 'content', 'experience']
function isCoreProtocol(entry) {
  return entry.category === 'protocol' && CORE_PROTOCOL_KINDS.includes(entry.kind)
}

// 角标文案：常驻协议 → 常驻；开关控制的协议 → 开关控制；玩法包 → 按需
function wbTagText(entry) {
  if (entry.category === 'protocol' && entry.kind === 'experience') return t('常驻', 'Always')
  if (isCoreProtocol(entry)) return t('开关控制', 'By switch')
  if (entry.category === 'protocol' || !entry.always_on) return t('按需', 'On demand')
  return t('常驻', 'Always')
}

// 正在编辑的是不是「协议包核心条目」：是的话不需要填触发词、也没有常驻开关
const editingCoreWb = computed(() => !!wbEditing.value && isCoreProtocol(wbEditing.value))

// 分组：协议包（系统种入）在前，自己的设定条目在后
const wbGroups = computed(() => {
  const protocol = wbEntries.value.filter(e => e.category === 'protocol')
  const lore = wbEntries.value.filter(e => e.category !== 'protocol')
  const groups = []
  if (protocol.length) {
    groups.push({
      key: 'protocol',
      name: t('协议包', 'Protocol pack'),
      hint: t('这里的开关只影响这一张卡。对话设置里的开关是全局闸门（对所有人物的世界书生效），两层都开才会注入。常驻＝每轮注入；玩法包按触发词命中才注入。',
        'These switches only affect this card. Switches in Conversation Settings are the global gate for every card; both layers must be on. “Always” = injected every turn; play packs load on trigger words.'),
      items: protocol,
    })
  }
  if (lore.length) {
    groups.push({
      key: 'lore',
      name: t('我的设定条目', 'My lore entries'),
      hint: t('聊到触发词才注入的角色设定与世界观。', 'Character lore injected when a trigger word appears.'),
      items: lore,
    })
  }
  return groups
})

// 恢复默认协议包：用户删掉/改坏协议条目后的一键救援（后端按 source_key 幂等重建）
async function restoreProtocolPack() {
  if (!editingPersona.value) return
  try {
    await ElMessageBox.confirm(
      t('将把协议条目（输出结构 / 创作与内容 / 剧情推进 / 玩法扩展包）恢复成默认内容并启用，你改写过的协议条目会被覆盖。注意：是否真的注入还取决于「对话设置」里的总开关（提示词兜底 / 界面标记 + 丰富面板内容）。继续？', 'This restores all protocol entries to their defaults and enables them. Your edits to protocol entries will be overwritten. Whether they are injected still depends on the master switches in Conversation Settings. Continue?'),
      t('恢复默认协议包', 'Restore protocol pack'),
      { type: 'warning', confirmButtonText: t('恢复', 'Restore'), cancelButtonText: t('取消', 'Cancel') }
    )
  } catch (e) {
    return // 用户取消
  }
  protocolRestoring.value = true
  try {
    const res = await personaApi.restoreProtocol(editingPersona.value.id)
    if (res.code === 200) {
      ElMessage.success(res.message || t('已恢复默认协议包', 'Protocol pack restored'))
      loadWorldBook()
    } else {
      ElMessage.warning(res.message || t('恢复失败', 'Restore failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('恢复失败', 'Restore failed'))
  } finally {
    protocolRestoring.value = false
  }
}
const defaultWbForm = {
  title: '',
  keywords: '',
  content: '',
  always_on: false,
}
const wbForm = reactive({ ...defaultWbForm })

async function loadWorldBook() {
  if (!editingPersona.value) return
  wbLoading.value = true
  try {
    const res = await personaApi.listWorldBook(editingPersona.value.id)
    wbEntries.value = res.code === 200 ? (res.data || []) : []
  } catch (e) {
    wbEntries.value = []
  } finally {
    wbLoading.value = false
  }
}

function openWbCreate() {
  wbEditing.value = null
  Object.assign(wbForm, defaultWbForm)
  wbDialogVisible.value = true
}

function openWbEdit(entry) {
  wbEditing.value = entry
  Object.assign(wbForm, {
    title: entry.title || '',
    keywords: entry.keywords || '',
    content: entry.content || '',
    always_on: !!entry.always_on,
  })
  wbDialogVisible.value = true
}

async function saveWbEntry() {
  if (!wbForm.content.trim()) {
    ElMessage.warning('请填写设定内容')
    return
  }
  if (!editingCoreWb.value && !wbForm.always_on && !wbForm.keywords.trim()) {
    ElMessage.warning('非常驻条目请至少填一个触发词（或勾「常驻」）')
    return
  }
  const payload = {
    title: wbForm.title.trim(),
    keywords: wbForm.keywords.trim(),
    content: wbForm.content.trim(),
    always_on: !!wbForm.always_on,
  }

  // 新建人物卡尚未有 id：先保存在表单草稿里，保存人物卡时一次性提交。
  if (!editingPersona.value) {
    if (wbEditing.value?._draft) {
      Object.assign(wbEditing.value, payload)
    } else {
      wbEntries.value.push({
        id: `draft-${++wbDraftSeq}`,
        ...payload,
        enabled: true,
        _draft: true,
      })
    }
    wbDialogVisible.value = false
    ElMessage.success(wbEditing.value ? '草稿已更新' : '草稿已添加')
    return
  }

  wbSaving.value = true
  try {
    const pid = editingPersona.value.id
    const res = wbEditing.value
      ? await personaApi.updateWorldBook(pid, wbEditing.value.id, payload)
      : await personaApi.createWorldBook(pid, payload)
    if (res.code === 200) {
      ElMessage.success(wbEditing.value ? '已保存' : '已添加')
      wbDialogVisible.value = false
      loadWorldBook()
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    wbSaving.value = false
  }
}

async function toggleWb(entry, val) {
  if (!editingPersona.value || entry._draft) {
    entry.enabled = !!val
    return
  }
  try {
    await personaApi.updateWorldBook(editingPersona.value.id, entry.id, { enabled: !!val })
  } catch (e) {
    entry.enabled = !val
    ElMessage.error(t('操作失败', 'Operation failed'))
  }
}

async function removeWb(entry) {
  try {
    await ElMessageBox.confirm(
      t(`确定删除条目「${entry.title || '未命名条目'}」吗？`, `Delete entry "${entry.title || 'Untitled'}"?`),
      t('确认删除', 'Confirm delete'),
      {
        type: 'warning',
        confirmButtonText: t('删除', 'Delete'),
        cancelButtonText: t('取消', 'Cancel'),
      })
  } catch (e) {
    return
  }
  if (!editingPersona.value || entry._draft) {
    wbEntries.value = wbEntries.value.filter(item => item !== entry)
    ElMessage.success(t('草稿已删除', 'Draft removed'))
    return
  }
  // 协议条目可能被删空（模板里明说了「删掉就不再注入」），失败必须让用户看见，
  // 否则会出现"以为删了、其实还在注入"的静默状态
  try {
    const res = await personaApi.removeWorldBook(editingPersona.value.id, entry.id)
    if (res.code === 200) {
      ElMessage.success(t('已删除', 'Deleted'))
      loadWorldBook()
    } else {
      ElMessage.error(res.message || t('删除失败', 'Delete failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('删除失败', 'Delete failed'))
  }
}

async function handleAvatarUpload(file) {
  try {
    const res = await uploadApi.uploadImage(file)
    if (res.code === 200) {
      form.avatar = res.data.url
      ElMessage.success('上传成功')
    }
  } catch (e) {
    ElMessage.error('上传失败')
  }
  return false
}

async function savePersona() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入角色名称')
    return
  }
  if (!form.system_prompt.trim()) {
    ElMessage.warning('请输入 AI 提示词')
    return
  }

  // 新建时前端先拦截上限，避免无谓请求
  if (!editingPersona.value && personas.value.length >= PERSONA_CARD_LIMIT) {
    ElMessage.warning(`人物卡数量已达上限（${PERSONA_CARD_LIMIT} 个），请先删除部分人物卡`)
    return
  }

  saving.value = true
  try {
    let res
    if (editingPersona.value) {
      res = await personaApi.update(editingPersona.value.id, form)
    } else {
      const payload = {
        ...form,
        worldbook: wbEntries.value
          .filter(entry => (entry.content || '').trim())
          .map(entry => ({
            title: entry.title || '',
            keywords: entry.keywords || '',
            content: entry.content.trim(),
            always_on: !!entry.always_on,
            enabled: entry.enabled !== false,
            weight: Number(entry.weight) || 0,
          })),
      }
      res = await personaApi.create(payload)
    }
    if (res.code === 200) {
      ElMessage.success(editingPersona.value ? '更新成功' : '创建成功')
      editDialogVisible.value = false
      loadPersonas()
      emit('persona-changed', res.data)
    } else {
      ElMessage.error(res.message || '保存失败')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function confirmDelete(id) {
  ElMessageBox.confirm('确定删除这个人物卡吗？', '确认删除', {
    type: 'warning',
    confirmButtonText: '删除',
    cancelButtonText: '取消',
  }).then(async () => {
    const res = await personaApi.remove(id)
    if (res.code === 200) {
      ElMessage.success('已删除')
      loadPersonas()
      // 通知主页面同步侧边栏人物卡列表（删除后卡片广场恢复为「添加」状态）
      emit('persona-deleted', id)
    }
  }).catch(() => {})
}
</script>

<style scoped>
.persona-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.persona-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.persona-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.persona-card:hover {
  border-color: #dcdfe6;
  background: #fafafa;
}

.persona-card.active {
  border-color: var(--brand);
  background: var(--brand-soft);
}

.persona-avatar {
  flex-shrink: 0;
}

.persona-info {
  flex: 1;
  min-width: 0;
}

.persona-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.default-tag {
  font-size: 11px;
}

.persona-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.persona-actions {
  display: none;
  flex-shrink: 0;
}

.persona-card:hover .persona-actions {
  display: flex;
  gap: 4px;
}

.empty-tip {
  padding: 40px 0;
}

.panel-footer {
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.footer-count {
  font-size: 12px;
  color: var(--text-muted, #909399);
  white-space: nowrap;
}

/* 来源标签：与「默认 / 系统」同款小方框 */
.source-tag {
  font-size: 11px;
}

.persona-name :deep(.el-tag) {
  margin-right: 0;
  padding: 0 5px;
  height: 18px;
  line-height: 17px;
}

/* 编辑/新建对话框：与系统整体风格一致的卡片式表单 */
.persona-form {
  padding: 4px 8px;
}

.persona-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  padding-bottom: 6px;
}

.form-avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 0 8px;
}

.form-avatar-preview {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  overflow: hidden;
  background: linear-gradient(135deg, #eef3fc, #e6edfa);
  border: 2px solid var(--border-color, #e4e7ed);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.form-avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.form-avatar-placeholder {
  font-size: 32px;
  color: #bfc9dc;
}

.form-card {
  background: var(--surface, #f5f7fa);
  border: 1px solid var(--border-color, #e4e7ed);
  border-radius: 14px;
  padding: 16px;
  margin-bottom: 16px;
}

.form-card :deep(.el-textarea__inner) {
  background: var(--bg, #ffffff);
  border-radius: 10px;
  resize: none;
}

.form-card :deep(.el-input__wrapper) {
  background: var(--bg, #ffffff);
  border-radius: 10px;
}

/* ===== 世界书（设定条目） ===== */
.wb-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.wb-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  margin-bottom: 4px;
}

.wb-desc {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary, #606266);
}

.wb-desc b {
  color: var(--brand, #c98a5a);
  font-weight: 600;
}

/* 表单字段下方的辅助说明。此前只引用了类名却没在本组件定义样式，
   提示文字会按正文渲染 —— 这里补上统一样式（与 ProviderPanel 的观感一致）。 */
.form-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-muted, #909399);
}

/* 「AI 角色设定」字数提示：超过建议长度时变暖色，提醒这属于每轮固定成本 */
.form-hint__len {
  margin-left: 6px;
  color: var(--brand, #c98a5a);
  white-space: nowrap;
}

/* 标题右侧的条目总数 */
.wb-count {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
  background: var(--surface-hover, rgba(0, 0, 0, .05));
  color: var(--text-secondary, #606266);
  vertical-align: middle;
}

.wb-head-text {
  min-width: 0;
  flex: 1 1 auto;
}

.wb-head-ops {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}

/* 协议条目：左侧一道品牌色刻度，一眼看出是系统种的规范而不是人设设定 */
.wb-item.is-protocol {
  border-left: 3px solid var(--brand, #c98a5a);
}

.wb-draft-note {
  display: inline-block;
  margin-top: 4px;
  color: var(--brand, #c98a5a);
  font-weight: 600;
}

.wb-empty {
  font-size: 12px;
  color: var(--text-muted, #909399);
  padding: 10px 0 2px;
}

.wb-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wb-item {
  border: 1px solid var(--border-color, #e4e7ed);
  border-radius: 10px;
  background: var(--bg, #ffffff);
  overflow: hidden;
}

/* 停用的条目整体压暗，但仍可操作（不必进二级菜单才能恢复） */
.wb-item.is-off {
  opacity: .62;
}

.wb-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
}

.wb-item-head:hover {
  background: var(--surface-hover, rgba(0, 0, 0, .03));
}

.wb-caret {
  flex: none;
  width: 12px;
  font-size: 11px;
  color: var(--text-muted, #909399);
  transition: transform .15s ease;
}

.wb-caret.open {
  transform: rotate(90deg);
}

.wb-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 46%;
}

/* 收起时的一行摘要，让用户不展开也知道里面是什么 */
.wb-preview {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12px;
  color: var(--text-muted, #909399);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wb-size {
  flex: none;
  font-size: 11px;
  color: var(--text-muted, #909399);
  font-variant-numeric: tabular-nums;
}

.wb-tag {
  flex-shrink: 0;
  font-size: 11px;
  line-height: 1;
  padding: 3px 6px;
  border-radius: 5px;
  background: var(--surface-hover, #eef1f6);
  color: var(--text-secondary, #606266);
}

.wb-tag.is-on {
  background: var(--brand, #c98a5a);
  color: #fff;
}

/* 「按需」用描边而非填充：与「常驻」的品牌色实心形成强弱对比 */
.wb-tag.is-demand {
  background: transparent;
  border: 1px solid var(--border-color, #dcdfe6);
  color: var(--text-muted, #909399);
}

.wb-tag.is-off {
  background: #fde2e2;
  color: #f56c6c;
}

/* 「协议」标记：深色描边，与「常驻/按需」区分（两条会同时出现） */
.wb-tag.is-proto {
  background: transparent;
  color: var(--text-primary, #303133);
  border: 1px solid currentColor;
}

/* 「开关控制」：三条核心协议不靠常驻注入，由会话设置里的开关决定，
   用虚线描边区分于实心的「常驻」与实线描边的「按需」 */
.wb-tag.is-switch {
  background: transparent;
  border: 1px dashed var(--brand, #c98a5a);
  color: var(--brand, #c98a5a);
}

/* 核心协议编辑弹窗里的说明（替代「常驻」勾选框） */
.wb-core-note {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary, #606266);
}

.wb-item-body {
  padding: 2px 12px 12px 32px;
  border-top: 1px dashed var(--border-color, #e4e7ed);
}

.wb-kw-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}

.wb-kw-label {
  font-size: 11px;
  color: var(--text-muted, #909399);
}

.wb-kw-chip {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 9px;
  background: var(--surface-hover, rgba(0, 0, 0, .04));
  color: var(--text-secondary, #606266);
}

.wb-kw-none {
  font-size: 11px;
  color: var(--text-muted, #909399);
}

/* 正文用 pre 保留换行，展开后完整可读、可滚动，不再挤压成三行截断 */
.wb-content {
  margin: 0;
  max-height: 46vh;
  overflow-y: auto;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--surface, #f5f7fa);
  font-family: inherit;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary, #606266);
  white-space: pre-wrap;
  word-break: break-word;
}

.wb-source {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-muted, #909399);
}

.wb-ops {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}

/* ===== 世界书分组（协议包 / 我的设定条目） ===== */
.wb-group + .wb-group {
  margin-top: 16px;
}

.wb-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid var(--brand, #c98a5a);
}

.wb-group-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #303133);
  flex: none;
}

.wb-group-hint {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-muted, #909399);
}

.wb-group-count {
  flex: none;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9px;
  background: var(--brand, #c98a5a);
  color: #fff;
}

/* ===== 移动端响应式 ===== */
@media (max-width: 768px) {
  /* 世界书表头：窄屏下按钮组（恢复协议包 + 添加条目）会把说明列挤成窄柱 */
  .wb-head {
    flex-direction: column;
    align-items: stretch;
  }
  .wb-head-ops {
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  /* 世界书条目：窄屏下名字与操作分行，摘要不再挤在一行 */
  .wb-item-head {
    flex-wrap: wrap;
    row-gap: 6px;
  }
  .wb-name { max-width: 100%; }
  .wb-preview { flex-basis: 100%; }
  .wb-ops { margin-left: 0; }
  .persona-card {
    flex-wrap: wrap;
    align-items: flex-start;
  }
  /* 移动端无 hover，操作按钮常驻显示 */
  .persona-actions,
  .persona-card:hover .persona-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    width: 100%;
    margin-left: 56px;
  }
  .avatar-upload {
    width: 100%;
  }
  .persona-desc {
    white-space: normal;
  }
}

/* 超窄屏（iPhone SE 一类）：取消操作按钮的头像缩进，把宽度让给按钮本身 */
@media (max-width: 420px) {
  .persona-actions,
  .persona-card:hover .persona-actions {
    margin-left: 0;
  }
}
</style>
