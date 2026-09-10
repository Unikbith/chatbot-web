<script setup>
import { ref, reactive, watch, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { MagicStick, CopyDocument, Plus, Delete } from '@element-plus/icons-vue';
import { promptToolApi } from '@/utils/resAi';
import { t } from '../i18n';

const props = defineProps({
  modelValue: { type: Boolean, default: false }
});

const emit = defineEmits(['update:modelValue', 'insert']);

const info = ref({ free_model: '', free_name: '', providers: [], default_prompts: { character: '', image: '' } });
const tab = ref('character');

const state = reactive({
  character: { providerId: null, model: '', customPrompt: '', baseInfo: '', result: '', loading: false },
  image: { providerId: null, model: '', customPrompt: '', baseInfo: '', result: '', loading: false },
});

const defaultPrompt = (cat) => info.value.default_prompts?.[cat] || '';

const providerOptions = () => [
  { id: null, label: info.value.free_name || t('免费 API', 'Free API') },
  ...(info.value.providers || [])
];

const onProviderChange = (cat) => {
  const s = state[cat];
  const pid = s.providerId;
  if (pid === null) {
    s.model = info.value.free_model || '';
    return;
  }
  const p = (info.value.providers || []).find(x => x.id === pid);
  if (p && p.models?.length) {
    s.model = p.models[0].id;
  }
};

const loadOptions = async () => {
  try {
    const res = await promptToolApi.options();
    if (res.code !== 200) return;
    info.value = res.data || info.value;
    ['character', 'image'].forEach(cat => {
      if (!state[cat].model) state[cat].model = info.value.free_model || '';
    });
  } catch (e) {
    // 静默失败，仅保留默认
  }
};

const fillDefault = (cat) => {
  state[cat].customPrompt = defaultPrompt(cat);
};

const clearCustom = (cat) => {
  state[cat].customPrompt = '';
};

const generate = async (cat) => {
  const s = state[cat];
  if (s.loading) return;
  s.loading = true;
  s.result = '';
  try {
    const res = await promptToolApi.generate({
      category: cat,
      provider_id: s.providerId,
      model: s.model,
      custom_prompt: s.customPrompt,
      base_info: s.baseInfo,
    });
    if (res.code === 200) {
      s.result = res.data?.content || '';
    } else {
      ElMessage.warning(res.message || t('生成失败', 'Failed'));
    }
  } catch (e) {
    const msg = e?.message || '';
    // 免费模型在繁忙时容易出现请求超时，给出明确的引导提示
    if (/timeout|timed ?out|超时|ETIMEDOUT|ECONNABORTED/i.test(msg)) {
      ElMessage.warning(t(
        '生成超时：免费模型在高峰期响应较慢。请稍后重试，或在「模型配置」中配置自己的 API Key 以获得更稳定的体验。',
        'Generation timed out: the free model can be slow during peak hours. Please retry later, or configure your own API Key for a more stable experience.'
      ));
    } else {
      ElMessage.error((t('生成失败：', 'Generation failed: ')) + (msg || t('请稍后重试', 'please retry later')));
    }
  } finally {
    s.loading = false;
  }
};

const isFreeCat = (cat) => state[cat].providerId === null;

const insertToInput = (cat) => {
  const text = state[cat].result.trim();
  if (!text) return;
  emit('insert', text);
};

const copyResult = async (cat) => {
  const text = state[cat].result.trim();
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success(t('已复制', 'Copied'));
  } catch (e) {
    ElMessage.warning(t('复制失败', 'Copy failed'));
  }
};

watch(() => props.modelValue, (open) => {
  if (open) loadOptions();
});

onMounted(() => {
  if (props.modelValue) loadOptions();
});
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    @update:model-value="v => emit('update:modelValue', v)"
    size="min(440px, 100%)"
    class="pt-drawer"
    append-to-body
    :destroy-on-close="false"
  >
    <template #header>
      <div class="pt-title">
        <el-icon class="pt-title-icon"><MagicStick /></el-icon>
        <span>{{ t('提示词工具', 'Prompt Tool') }}</span>
      </div>
    </template>

    <el-tabs v-model="tab">
      <!-- 人物设定 -->
      <el-tab-pane :label="t('人物设定', 'Character')" name="character">
        <div class="pt-pane">
          <div v-if="isFreeCat('character')" class="pt-free-hint">
            <el-icon class="pt-free-icon"><MagicStick /></el-icon>
            <span>{{ t('当前使用免费模型，高峰期生成可能较慢或超时；若失败请稍后重试，或配置自己的 API Key 更稳定。', 'Using the free model now; generation may be slow or time out during peak hours. Retry later, or configure your own API Key for stability.') }}</span>
          </div>
          <div class="pt-field">
            <label class="pt-label">{{ t('模型', 'Model') }}</label>
            <div class="pt-row">
              <el-select
                :model-value="state.character.providerId"
                class="pt-provider"
                @update:model-value="v => { state.character.providerId = v; onProviderChange('character'); }"
              >
                <el-option v-for="p in providerOptions()" :key="p.id ?? 'free'" :value="p.id" :label="p.label" />
              </el-select>
              <el-input v-model="state.character.model" :placeholder="t('模型 ID（可自定义）', 'Model ID (custom)')" />
            </div>
          </div>

          <div class="pt-field">
            <div class="pt-label-row">
              <label class="pt-label">{{ t('自定义提示词（留空则用默认）', 'Custom prompt (empty = default)') }}</label>
              <div class="pt-actions">
                <el-button size="small" text :icon="Plus" @click="fillDefault('character')">
                  {{ t('填入默认', 'Use default') }}
                </el-button>
                <el-button v-if="state.character.customPrompt" size="small" text :icon="Delete" @click="clearCustom('character')">
                  {{ t('清空', 'Clear') }}
                </el-button>
              </div>
            </div>
            <el-input
              v-model="state.character.customPrompt"
              type="textarea"
              :rows="6"
              :placeholder="defaultPrompt('character')"
            />
          </div>

          <div class="pt-field">
            <label class="pt-label">{{ t('基础信息（可选，留空则随机生成）', 'Base info (optional, empty = random)') }}</label>
            <el-input
              v-model="state.character.baseInfo"
              type="textarea"
              :rows="3"
              :placeholder="t('如：想生成一位冷艳的末世女剑客，穿黑色长风衣', 'e.g. A cold apocalyptic female swordsman in a black trench coat')"
            />
          </div>

          <el-button
            type="primary"
            class="pt-gen"
            :icon="MagicStick"
            :loading="state.character.loading"
            @click="generate('character')"
          >
            {{ t('一键生成人物设定', 'Generate character') }}
          </el-button>

          <div v-if="state.character.result" class="pt-result">
            <el-input v-model="state.character.result" type="textarea" :rows="8" readonly />
            <div class="pt-result-actions">
              <el-button size="small" type="primary" plain @click="insertToInput('character')">
                {{ t('插入输入框', 'Insert to input') }}
              </el-button>
              <el-button size="small" :icon="CopyDocument" @click="copyResult('character')">
                {{ t('复制', 'Copy') }}
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 图片提示词 -->
      <el-tab-pane :label="t('图片提示词', 'Image Prompt')" name="image">
        <div class="pt-pane">
          <div v-if="isFreeCat('image')" class="pt-free-hint">
            <el-icon class="pt-free-icon"><MagicStick /></el-icon>
            <span>{{ t('当前使用免费模型，高峰期生成可能较慢或超时；若失败请稍后重试，或配置自己的 API Key 更稳定。', 'Using the free model now; generation may be slow or time out during peak hours. Retry later, or configure your own API Key for stability.') }}</span>
          </div>
          <div class="pt-field">
            <label class="pt-label">{{ t('模型', 'Model') }}</label>
            <div class="pt-row">
              <el-select
                :model-value="state.image.providerId"
                class="pt-provider"
                @update:model-value="v => { state.image.providerId = v; onProviderChange('image'); }"
              >
                <el-option v-for="p in providerOptions()" :key="p.id ?? 'free'" :value="p.id" :label="p.label" />
              </el-select>
              <el-input v-model="state.image.model" :placeholder="t('模型 ID（可自定义）', 'Model ID (custom)')" />
            </div>
          </div>

          <div class="pt-field">
            <div class="pt-label-row">
              <label class="pt-label">{{ t('自定义提示词（留空则用默认）', 'Custom prompt (empty = default)') }}</label>
              <div class="pt-actions">
                <el-button size="small" text :icon="Plus" @click="fillDefault('image')">
                  {{ t('填入默认', 'Use default') }}
                </el-button>
                <el-button v-if="state.image.customPrompt" size="small" text :icon="Delete" @click="clearCustom('image')">
                  {{ t('清空', 'Clear') }}
                </el-button>
              </div>
            </div>
            <el-input
              v-model="state.image.customPrompt"
              type="textarea"
              :rows="6"
              :placeholder="defaultPrompt('image')"
            />
          </div>

          <div class="pt-field">
            <label class="pt-label">{{ t('基础信息（可选，留空则随机生成）', 'Base info (optional, empty = random)') }}</label>
            <el-input
              v-model="state.image.baseInfo"
              type="textarea"
              :rows="3"
              :placeholder="t('如：海边日落，赛博朋克城市，一只猫咪宇航员', 'e.g. Seaside sunset, cyberpunk city, a cat astronaut')"
            />
          </div>

          <el-button
            type="primary"
            class="pt-gen"
            :icon="MagicStick"
            :loading="state.image.loading"
            @click="generate('image')"
          >
            {{ t('一键生成图片提示词', 'Generate image prompt') }}
          </el-button>

          <div v-if="state.image.result" class="pt-result">
            <el-input v-model="state.image.result" type="textarea" :rows="8" readonly />
            <div class="pt-result-actions">
              <el-button size="small" type="primary" plain @click="insertToInput('image')">
                {{ t('插入输入框', 'Insert to input') }}
              </el-button>
              <el-button size="small" :icon="CopyDocument" @click="copyResult('image')">
                {{ t('复制', 'Copy') }}
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<style scoped>
.pt-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #4a3520);
}

.pt-title-icon {
  color: var(--brand, #b06a2e);
  font-size: 18px;
}

.pt-pane {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.pt-free-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fdf3e4;
  border: 1px solid #f0d7b8;
  color: #8a6a3a;
  font-size: 12px;
  line-height: 1.6;
}

.pt-free-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: #b06a2e;
}

.pt-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pt-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.pt-label {
  font-size: 13px;
  font-weight: 500;
  color: #8a6a48;
}

.pt-actions {
  display: flex;
  gap: 4px;
}

.pt-row {
  display: flex;
  gap: 8px;
}

.pt-provider {
  width: 45%;
  flex-shrink: 0;
}

.pt-gen {
  width: 100%;
  background: var(--brand-gradient, linear-gradient(135deg, #8a4a1f, #b06a2e));
  border: none;
}

.pt-result {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pt-result-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>

<style>
/* 移动端：抽屉宽度自适应，内容可滚动并适配底部安全区（append-to-body 需用全局样式） */
@media (max-width: 768px) {
  .pt-drawer .el-drawer__body,
  .persona-drawer .el-drawer__body {
    height: 100%;
    overflow-y: auto;
    padding-left: 16px !important;
    padding-right: 16px !important;
    padding-bottom: calc(24px + env(safe-area-inset-bottom));
    box-sizing: border-box;
  }
}
</style>