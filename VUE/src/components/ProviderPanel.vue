<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="(val) => emit('update:modelValue', val)"
    :title="t('模型配置', 'Model Configuration')"
    direction="rtl"
    :size="drawerSize"
    class="provider-drawer"
  >
    <!-- Tab 切换：对话 / STT / TTS -->
    <div class="tabs-container">
      <div class="tabs">
        <div
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-item"
          :class="{ active: activeType === tab.key }"
          @click="switchType(tab.key)"
        >
          <el-icon><component :is="tab.icon" /></el-icon>
          <span>{{ t(tab.label, tab.labelEn) }}</span>
        </div>
      </div>
    </div>

    <div class="panel-body">
      <!-- 左列：厂商 + 我的配置 -->
      <div class="left-col">
        <div class="col-title">{{ t('厂商', 'Vendors') }}</div>
        <div class="vendor-list">
          <div
            v-for="v in vendors"
            :key="v.brand"
            class="vendor-item"
            :class="{ active: selectedVendorBrand === v.brand }"
            @click="selectVendor(v)"
          >
            <span class="vendor-name">{{ v.name }}</span>
            <span class="vendor-desc">{{ v.desc }}</span>
          </div>
          <div v-if="vendors.length === 0" class="col-empty">{{ t('暂无厂商', 'No vendors') }}</div>
        </div>

        <div class="col-title col-title-gap">
          {{ t('我的配置', 'My Configs') }}
        </div>
        <div class="provider-list" v-loading="loading">
          <div
            v-for="p in providers"
            :key="p.id"
            class="provider-card"
            :class="{ active: editingId == p.id }"
            @click="selectProvider(p)"
          >
            <div class="provider-name">
              {{ p.name }}
              <el-tag v-if="p.is_default" size="small" type="warning" effect="light" class="tag">默认</el-tag>
            </div>
            <div class="provider-actions" @click.stop>
              <el-button
                v-if="!p.is_default"
                size="small"
                text
                @click="setDefault(p)"
                title="设为默认"
              ><el-icon><Star /></el-icon></el-button>
              <el-button
                size="small"
                text
                type="danger"
                @click="deleteProvider(p)"
                title="删除"
              ><el-icon><Delete /></el-icon></el-button>
            </div>
          </div>
          <div v-if="providers.length === 0" class="col-empty">{{ t('还没有配置，点击下方新增', 'No config yet, click Add') }}</div>
        </div>

        <el-button class="new-btn" type="primary" :icon="Plus" @click="startNew">
          {{ t('新增配置', 'Add Config') }}
        </el-button>
      </div>

      <!-- 右列：配置表单 + 模型管理 -->
      <div class="right-col">
        <div class="config-card">
          <div class="config-title">{{ editingId ? t('编辑配置', 'Edit Config') : t('新增配置', 'Add Config') }}</div>

          <div class="form-row">
            <label class="form-label">{{ t('配置 ID（名称）', 'ID / Name') }}</label>
            <el-input v-model="form.name" :placeholder="t('如：我的 DeepSeek', 'e.g. My DeepSeek')" />
          </div>

          <div class="form-row">
            <label class="form-label">API Key</label>
            <el-input v-model="form.api_key" type="password" show-password :placeholder="'sk-...'" />
          </div>

          <div class="form-row">
            <label class="form-label">{{ t('API Base URL', 'API Base URL') }}</label>
            <el-input v-model="form.api_url" :placeholder="t('https://api.example.com/v1', 'https://api.example.com/v1')" />
            <div class="form-hint">{{ t('厂商地址已自动填入，可修改', 'Prefilled from vendor, editable') }}</div>
          </div>

          <!-- 语音类厂商专属参数（动态渲染） -->
          <template v-if="isAudio() && paramSchema.length">
            <div v-for="f in paramSchema" :key="f.key" class="form-row">
              <label class="form-label">
                {{ tLabel(f) }}
                <el-tag v-if="f.required" size="small" type="danger" effect="plain" class="req-tag">*</el-tag>
              </label>
              <!-- 下拉选择 -->
              <el-select
                v-if="f.type === 'select'"
                :model-value="fieldValue(f)"
                @update:model-value="(v) => setFieldValue(f, v)"
                :placeholder="t('请选择', 'Select')"
                clearable
                style="width: 100%"
              >
                <el-option
                  v-for="op in f.options"
                  :key="op.value"
                  :label="op.label"
                  :value="op.value"
                />
              </el-select>
              <!-- 数字 -->
              <el-input-number
                v-else-if="f.type === 'number'"
                :model-value="fieldValue(f)"
                @update:model-value="(v) => setFieldValue(f, v)"
                :min="f.min ?? undefined"
                :max="f.max ?? undefined"
                :step="f.step ?? 1"
                :placeholder="String(f.default ?? '')"
                controls-position="right"
                style="width: 100%"
              />
              <!-- 文本 -->
              <el-input
                v-else
                :model-value="fieldValue(f)"
                @update:model-value="(v) => setFieldValue(f, v)"
                :placeholder="t(f.placeholder, f.placeholder)"
                clearable
              />
              <div v-if="tHelp(f)" class="form-hint">{{ tHelp(f) }}</div>
            </div>
          </template>

          <div class="form-row actions-row">
            <el-button type="primary" :loading="saving" @click="saveConfig">
              {{ editingId ? t('保存修改', 'Save') : t('创建配置', 'Create') }}
            </el-button>
            <el-button v-if="editingId" :loading="testing" @click="testConfig">
              {{ t('测试配置', 'Test Config') }}
            </el-button>
          </div>
          <div v-if="testResult" class="test-result" :class="testResult.ok ? 'ok' : 'err'">
            {{ testResult.msg }}
          </div>
        </div>

        <!-- 已选配置的模型管理（仅对话模型） -->
        <template v-if="editingId && activeType === 'chat'">
          <div class="models-card">
            <div class="models-title">{{ t('已配置模型', 'Configured Models') }}</div>
            <div v-if="configuredModels.length === 0" class="col-empty">{{ t('暂无已配置模型', 'No configured models') }}</div>
            <div v-for="m in configuredModels" :key="m.id" class="model-row">
              <el-switch
                :model-value="m.enabled"
                size="small"
                @change="(v) => toggleModel(m, v)"
              />
              <span class="model-name" :class="{ off: !m.enabled }">{{ m.name }}</span>
              <el-tag v-if="m.is_custom" size="small" type="info" effect="plain">自定义</el-tag>
              <div class="model-actions">
                <el-button size="small" text :loading="testingModel === m.id" @click="testModel(m)">
                  {{ t('测试', 'Test') }}
                </el-button>
                <el-button size="small" text type="danger" @click="deleteModel(m)">
                  {{ t('删除', 'Delete') }}
                </el-button>
              </div>
            </div>
          </div>

          <div class="models-card">
            <div class="models-title models-title-row">
              <span>{{ t('可用模型', 'Available Models') }}</span>
              <el-button size="small" :loading="fetching" @click="fetchAvailable">
                {{ t('获取可用模型', 'Fetch Models') }}
              </el-button>
            </div>
            <div v-if="fetchError" class="test-result err">{{ fetchError }}</div>
            <div v-if="availableModels.length === 0 && !fetching && !fetchError" class="col-empty">
              {{ t('点击上方按钮从厂商拉取模型列表', 'Click Fetch to get models from the vendor') }}
            </div>
            <div v-for="(av, i) in availableModels" :key="i" class="model-row">
              <span class="model-name" :class="{ dim: av.configured }">{{ av.name }}</span>
              <template v-if="av.configured">
                <el-tag size="small" type="success" effect="plain">{{ t('已加入', 'Added') }}</el-tag>
              </template>
              <template v-else>
                <el-button size="small" type="primary" text @click="addAvailable(av)">
                  {{ t('加入', 'Add') }}
                </el-button>
              </template>
            </div>
          </div>

          <div class="models-card">
            <div class="models-title">{{ t('自定义模型', 'Custom Model') }}</div>
            <div class="custom-row">
              <el-input v-model="customModelId" :placeholder="t('输入模型 ID（拉取不到的）', 'Enter a model ID not listed')" />
              <el-button type="primary" :disabled="!customModelId.trim()" @click="addCustom">
                {{ t('添加', 'Add') }}
              </el-button>
            </div>
            <div class="form-hint">{{ t('适用于厂商列表拉取不到的模型，需确保该模型 ID 真实可用', 'For model IDs not returned by the vendor list') }}</div>
          </div>
        </template>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ChatDotRound, Microphone, Headset, Star, Delete } from '@element-plus/icons-vue'
import { providersApi } from '@/utils/resAi'
import { t } from '../i18n'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  currentProviderId: { type: [Number, String], default: null },
})

const emit = defineEmits(['update:modelValue', 'select'])

const tabs = [
  { key: 'chat', label: '对话模型', labelEn: 'Chat', icon: ChatDotRound },
  { key: 'stt', label: '语音转文字', labelEn: 'STT', icon: Microphone },
  { key: 'tts', label: '文字转语音', labelEn: 'TTS', icon: Headset },
]

const activeType = ref('chat')
const vendors = ref([])
const providers = ref([])
const selectedVendorBrand = ref(null)

const editingId = ref(null)
const drawerSize = ref('760px')
const form = ref({ name: '', api_key: '', api_url: '', model: '', paramValues: {} })
const paramSchema = ref([]) // 厂商专属额外字段（STT/TTS）
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)
const loading = ref(false)

const isAudio = () => activeType.value === 'stt' || activeType.value === 'tts'
function tLabel(field) {
  return field.label_en ? t(field.label, field.label_en) : field.label
}
function tHelp(field) {
  return field.help_en ? t(field.help, field.help_en) : (field.help || '')
}
function fieldValue(field) {
  return field.target === 'model' ? form.value.model : form.value.paramValues[field.key]
}
function setFieldValue(field, v) {
  if (field.target === 'model') form.value.model = v
  else form.value.paramValues[field.key] = v
}

async function loadSchema(type, brand) {
  if (type === 'chat' || !brand) {
    paramSchema.value = []
    return
  }
  try {
    const res = await providersApi.configSchema(type, brand)
    if (res.code === 200) {
      paramSchema.value = res.data || []
      // 为没有显式值的字段填充默认值
      const schema = res.data || []
      const values = form.value.paramValues || {}
      for (const f of schema) {
        if (f.target !== 'params') continue
        const has = form.value.paramValues && Object.prototype.hasOwnProperty.call(form.value.paramValues, f.key)
        if (!has && f.default !== undefined && f.default !== null && f.default !== '') {
          values[f.key] = f.default
        }
      }
      form.value.paramValues = { ...values }
    }
  } catch (e) {
    paramSchema.value = []
  }
}

function applyDefaults() {
  form.value.model = ''
  form.value.paramValues = {}
  for (const f of paramSchema.value) {
    if (f.target === 'model') {
      if (f.default && !form.value.model) form.value.model = f.default
    } else {
      if (f.default !== undefined && f.default !== null && f.default !== '') {
        form.value.paramValues[f.key] = f.default
      }
    }
  }
  loadSchema(activeType.value, selectedVendorBrand.value)
}

const configuredModels = ref([])
const availableModels = ref([])
const fetching = ref(false)
const fetchError = ref('')
const testingModel = ref(null)
const customModelId = ref('')

async function loadVendors() {
  try {
    const res = await providersApi.vendors(activeType.value)
    if (res.code === 200) vendors.value = res.data || []
  } catch (e) {
    vendors.value = []
  }
}

async function loadProviders() {
  loading.value = true
  try {
    const res = await providersApi.list(activeType.value)
    if (res.code === 200) providers.value = res.data || []
    // 自动选中默认或当前
    if (!editingId.value && providers.value.length > 0) {
      const saved = providers.value.find(p => p.id == props.currentProviderId)
      selectProvider(saved || providers.value.find(p => p.is_default) || providers.value[0])
    }
  } catch (e) {
    console.error('加载配置失败', e)
  } finally {
    loading.value = false
  }
}

async function selectProvider(p) {
  if (!p) return
  editingId.value = p.id
  selectedVendorBrand.value = p.brand
  try {
    const res = await providersApi.get(p.id)
    if (res.code === 200) {
      form.value = {
        name: res.data.name || '',
        api_key: res.data.api_key || '',
        api_url: res.data.api_url || '',
        model: res.data.model || '',
        paramValues: res.data.params || {},
      }
      await loadSchema(activeType.value, res.data.brand || p.brand)
      // 缺省的模型 ID 用厂商默认值与 schema 默认值补齐
      if (!form.value.model) {
        for (const f of paramSchema.value) {
          if (f.target === 'model' && f.default) form.value.model = f.default
        }
      }
      if (activeType.value === 'chat') loadConfiguredModels(p.id)
    }
  } catch (e) {
    ElMessage.error(t('加载详情失败', 'Failed to load details'))
  }
}

function selectVendor(v) {
  selectedVendorBrand.value = v.brand
  // 未在编辑某个已有配置时，自动用厂商默认地址
  if (!editingId.value) {
    if (!form.value.name) form.value.name = v.name
    form.value.api_url = v.default_api_url || form.value.api_url
    form.value.model = ''
    form.value.paramValues = {}
  }
  loadSchema(activeType.value, v.brand)
}

function startNew() {
  editingId.value = null
  form.value = {
    name: '',
    api_key: '',
    api_url: selectedVendorBrand.value
      ? (vendors.value.find(v => v.brand === selectedVendorBrand.value)?.default_api_url || '')
      : '',
    model: '',
    paramValues: {},
  }
  loadSchema(activeType.value, selectedVendorBrand.value)
  configuredModels.value = []
  availableModels.value = []
  fetchError.value = ''
  testResult.value = null
}

async function saveConfig() {
  if (!form.value.name.trim()) {
    ElMessage.warning(t('请填写配置 ID', 'Please fill in the config ID'))
    return
  }
  if (!form.value.api_key.trim()) {
    ElMessage.warning('API Key ' + t('不能为空', 'is required'))
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      api_key: form.value.api_key.trim(),
      api_url: form.value.api_url.trim(),
      brand: selectedVendorBrand.value || 'deepseek',
      provider_type: activeType.value,
    }
    if (isAudio()) {
      // 由 schema 决定哪些字段进 model / params
      const params = {}
      for (const f of paramSchema.value) {
        const raw = f.target === 'model' ? form.value.model : form.value.paramValues[f.key]
        if (raw === undefined || raw === null || raw === '') continue
        if (f.target === 'model') payload.model = raw
        else params[f.key] = raw
      }
      if (payload.model) payload.model = String(payload.model).trim()
      payload.params = params
    }
    let res
    if (editingId.value) {
      res = await providersApi.update(editingId.value, payload)
    } else {
      res = await providersApi.create(payload)
    }
    if (res.code === 200) {
      ElMessage.success(editingId.value ? t('保存成功', 'Saved') : t('创建成功', 'Created'))
      editingId.value = res.data.id
      form.value.api_key = res.data.api_key || form.value.api_key
      loadProviders()
      loadConfiguredModels(res.data.id)
    } else {
      ElMessage.error(res.message || t('操作失败', 'Failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('操作失败', 'Failed'))
  } finally {
    saving.value = false
  }
}

async function testConfig() {
  testing.value = true
  testResult.value = null
  try {
    const res = await providersApi.test(editingId.value)
    if (res.code === 200) {
      testResult.value = { ok: true, msg: t('连接成功', 'Connection OK') }
    } else {
      testResult.value = { ok: false, msg: res.message || t('连接失败', 'Failed') }
    }
  } catch (e) {
    testResult.value = { ok: false, msg: e.response?.data?.message || t('测试失败', 'Test failed') }
  } finally {
    testing.value = false
  }
}

async function setDefault(p) {
  try {
    await providersApi.setDefault(p.id)
    ElMessage.success(t('已设为默认', 'Set as default'))
    loadProviders()
  } catch (e) {
    ElMessage.error(t('设置失败', 'Failed'))
  }
}

function deleteProvider(p) {
  ElMessageBox.confirm(
    t('确定要删除「', 'Delete ') + p.name + t('」吗？', '?'),
    t('删除确认', 'Delete Confirm'),
    { type: 'warning' }
  ).then(async () => {
    const res = await providersApi.remove(p.id)
    if (res.code === 200) {
      ElMessage.success(t('删除成功', 'Deleted'))
      if (editingId.value == p.id) startNew()
      loadProviders()
    }
  }).catch(() => {})
}

// ---------- 模型 ----------
async function loadConfiguredModels(pid) {
  const id = pid || editingId.value
  if (!id) return
  try {
    const res = await providersApi.listModels(id)
    if (res.code === 200) configuredModels.value = res.data || []
  } catch (e) {
    configuredModels.value = []
  }
}

async function toggleModel(m, v) {
  try {
    await providersApi.updateModel(m.provider_id || editingId.value, m.id, { enabled: v })
    m.enabled = v
  } catch (e) {
    ElMessage.error(t('操作失败', 'Failed'))
  }
}

async function testModel(m) {
  testingModel.value = m.id
  try {
    const res = await providersApi.testModel(m.provider_id || editingId.value, m.id)
    if (res.code === 200) {
      ElMessage.success(`${m.name}: ` + t('连接正常', 'OK'))
    } else {
      ElMessage.error(`${m.name}: ${res.message || t('连接失败', 'Failed')}`)
    }
  } catch (e) {
    ElMessage.error(`${m.name}: ` + t('测试失败', 'Failed'))
  } finally {
    testingModel.value = null
  }
}

async function deleteModel(m) {
  ElMessageBox.confirm(t('删除该模型？', 'Delete this model?'), t('确认', 'Confirm'), { type: 'warning' })
    .then(async () => {
      await providersApi.deleteModel(m.provider_id || editingId.value, m.id)
      ElMessage.success(t('已删除', 'Deleted'))
      loadConfiguredModels()
      // 更新可用模型状态
      availableModels.value = availableModels.value.map(a =>
        a.model_id === m.model_id ? { ...a, configured: false } : a
      )
    }).catch(() => {})
}

async function fetchAvailable() {
  fetching.value = true
  fetchError.value = ''
  try {
    const res = await providersApi.fetchAvailable(editingId.value)
    if (res.code === 200) {
      availableModels.value = res.data || []
      if (availableModels.value.length === 0) {
        fetchError.value = t('厂商未返回模型列表，可尝试自定义添加', 'No models returned, try custom add')
      }
    } else {
      fetchError.value = res.message || t('获取失败', 'Failed')
    }
  } catch (e) {
    fetchError.value = e.response?.data?.message || t('获取失败', 'Failed')
  } finally {
    fetching.value = false
  }
}

async function addAvailable(av) {
  try {
    const res = await providersApi.addModel(editingId.value, { model_id: av.model_id, name: av.name })
    if (res.code === 200) {
      ElMessage.success(t('已加入', 'Added'))
      av.configured = true
      loadConfiguredModels()
    } else {
      ElMessage.warning(res.message || t('添加失败', 'Failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('添加失败', 'Failed'))
  }
}

async function addCustom() {
  try {
    const res = await providersApi.addModel(editingId.value, {
      model_id: customModelId.value.trim(),
      is_custom: true,
    })
    if (res.code === 200) {
      ElMessage.success(t('已添加', 'Added'))
      customModelId.value = ''
      loadConfiguredModels()
    } else {
      ElMessage.warning(res.message || t('添加失败', 'Failed'))
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || t('添加失败', 'Failed'))
  }
}

function switchType(type) {
  if (type === activeType.value) return
  activeType.value = type
  editingId.value = null
  form.value = { name: '', api_key: '', api_url: '', model: '', paramValues: {} }
  paramSchema.value = []
  configuredModels.value = []
  availableModels.value = []
  fetchError.value = ''
  testResult.value = null
  loadVendors()
  loadProviders()
}

function syncDrawerSize() {
  drawerSize.value = (typeof window !== 'undefined' && window.innerWidth <= 768) ? '100%' : '760px'
}

watch(() => props.modelValue, (val) => {
  if (val) {
    loadVendors()
    loadProviders()
  }
})

onMounted(() => {
  syncDrawerSize()
  window.addEventListener('resize', syncDrawerSize)
  if (props.modelValue) {
    loadVendors()
    loadProviders()
  }
})
</script>

<style scoped>
.provider-drawer :deep(.el-drawer__header) {
  margin: 0;
  padding: 16px 20px;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-color);
}

.provider-drawer :deep(.el-drawer__body) {
  padding: 0;
  display: flex;
  flex-direction: column;
}

/* Tab */
.tabs-container {
  border-bottom: 1px solid var(--border-color);
  padding: 0 12px;
  background: var(--surface-hover);
}

.tabs {
  display: flex;
  gap: 4px;
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  font-size: 14px;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all 0.2s;
}

.tab-item:hover { color: var(--text-secondary); }
.tab-item.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
  font-weight: 500;
}
.tab-item .el-icon { font-size: 16px; }

/* 主体两列 */
.panel-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

.left-col {
  width: 230px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color);
  padding: 16px 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: var(--surface-hover);
}

.col-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.col-title-gap { margin-top: 16px; }
.col-empty { font-size: 12px; color: var(--text-muted); padding: 8px 0; }

.vendor-item {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  display: flex;
  flex-direction: column;
  transition: background 0.15s;
}
.vendor-item:hover { background: var(--surface); }
.vendor-item.active { background: var(--brand); color: #fff; }
.vendor-item.active .vendor-desc { color: rgba(255,255,255,0.85); }
.vendor-name { font-size: 13px; font-weight: 500; }
.vendor-desc { font-size: 11px; color: var(--text-muted); margin-top: 1px; }

.provider-list {
  flex: 1;
  overflow-y: auto;
}
.provider-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  border: 1px solid transparent;
  transition: all 0.15s;
}
.provider-card:hover { background: var(--surface); }
.provider-card.active {
  border-color: var(--brand);
  background: var(--surface);
}
.provider-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.provider-actions { display: flex; gap: 2px; flex-shrink: 0; }
.tag { font-size: 10px; height: 18px; line-height: 16px; }

.new-btn { margin-top: 12px; width: 100%; }

/* 右列配置 */
.right-col {
  flex: 1;
  padding: 16px 20px;
  overflow-y: auto;
}

.config-card, .models-card {
  background: var(--surface);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 16px;
}
.config-title, .models-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 14px;
}
.models-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.form-row { margin-bottom: 14px; }
.form-label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.form-hint { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.req-tag { margin-left: 6px; height: 16px; line-height: 14px; font-size: 10px; vertical-align: middle; }
.actions-row { display: flex; gap: 10px; margin-bottom: 0; }

.test-result {
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.test-result.ok { background: #f0fdf4; color: #16a34a; }
.test-result.err { background: #fef2f2; color: #dc2626; }

.model-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
}
.model-row:last-child { border-bottom: none; }
.model-name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-name.off { color: var(--text-muted); text-decoration: line-through; }
.model-name.dim { color: var(--text-muted); }
.model-actions { display: flex; gap: 4px; flex-shrink: 0; }

.custom-row { display: flex; gap: 10px; }
</style>