<script setup>
import { ref, reactive, watch, onMounted, computed } from 'vue';
import { ElMessage } from 'element-plus';
import { MagicStick, CopyDocument, Plus, Delete, WarningFilled } from '@element-plus/icons-vue';
import { promptToolApi } from '@/utils/resAi';
import { t } from '../i18n';

const props = defineProps({
  modelValue: { type: Boolean, default: false }
});

const emit = defineEmits(['update:modelValue', 'insert']);

const info = ref({ free_model: '', free_name: '', providers: [], default_prompts: { character: '', image: '' } });
const tab = ref('character');

const state = reactive({
  character: { selection: '', customPrompt: '', baseInfo: '', result: '', hasError: false, loading: false },
  image: { selection: '', customPrompt: '', baseInfo: '', result: '', hasError: false, loading: false },
});

const defaultPrompt = (cat) => info.value.default_prompts?.[cat] || '';

// 人物设定占位提示：仅展示给用户看，与后端实际下发的系统提示词解耦。
// 后端 DEFAULT_CHARACTER_PROMPT 可换成真实使用的提示词，前端占位仍显示这份友好说明。
// 刻意写得简短并写明字数上限：生成结果通常会被贴回「AI 人设」，那段文本每轮都会注入，
// 越详细每轮越费 token —— 所以默认提示词引导模型产出精简版。
const CHARACTER_PLACEHOLDER = '你是一位资深的人物设定策划师。请根据用户的需求，产出一份可直接用于角色扮演、小说或剧本创作的、精简够用的人物设定，全文控制在 400 字以内：这段文字会随每轮对话注入，写长会持续消耗 token。覆盖：姓名、年龄、身份与职业、性格（含优点与缺点）、背景经历、外貌特征、说话风格与口头禅、能力与特长、目标与动机、人际关系与潜在冲突。用短句分点呈现，只写扮演时用得上的信息，不必逐项枚举身体细节，避免空洞套话。只输出设定正文，不要任何额外解释。';

// 扁平化的可选模型列表：直接选出「某配置下的某个模型」，无需先选厂商再选模型。
// 每个选项的 value 编码为 `${providerId}::${modelId}`（免费模型为 `free::${free_model}`），
// 提交时再拆解出 provider_id 与 model 传给后端。
const buildFlatOptions = (cat) => {
  const list = [];
  const fm = info.value.free_model;
  if (fm) {
    list.push({ value: `free::${fm}`, label: info.value.free_name || t('免费 API', 'Free API') });
  }
  for (const p of (info.value.providers || [])) {
    for (const m of (p.models || [])) {
      list.push({ value: `${p.id}::${m.id}`, label: `${p.name} / ${m.name || m.id}` });
    }
  }
  return list;
};

// 缓存为 computed：仅在 info（候选模型列表）变化时重算，避免每次渲染
// （含用户边输入自定义提示词边触发）都重建数组与对象。
const characterModelOptions = computed(() => buildFlatOptions('character'));
const imageModelOptions = computed(() => buildFlatOptions('image'));

const loadOptions = async () => {
  try {
    const res = await promptToolApi.options();
    if (res.code !== 200) return;
    info.value = res.data || info.value;
    ['character', 'image'].forEach((cat) => {
      if (!state[cat].selection) {
        const fm = info.value.free_model;
        state[cat].selection = fm ? `free::${fm}` : (buildFlatOptions(cat)[0]?.value || '');
      }
    });
  } catch (e) {
    // 静默失败，仅保留默认
  }
};

// 「填入默认」填入的内容：
// - 人物设定：填入与 placeholder 完全一致的「安全版」提示词，界面上不暴露后端
//   DEFAULT_CHARACTER_PROMPT；只有用户一个字都没填时，后端才回落到那份实际提示词。
// - 生图：沿用后端下发的默认提示词（非敏感，可安全展示）。
const fillDefault = (cat) => {
  state[cat].customPrompt = cat === 'character' ? CHARACTER_PLACEHOLDER : defaultPrompt(cat);
};

const clearCustom = (cat) => {
  state[cat].customPrompt = '';
};

const generate = async (cat) => {
  const s = state[cat];
  if (s.loading) return;
  s.loading = true;
  s.result = '';
  s.hasError = false;
  // 从复合选择里拆出 provider_id 与 model
  const [rawPid, mid] = (s.selection || '').split('::');
  const providerId = rawPid && rawPid !== 'free' ? Number(rawPid) : null;
  const model = mid || '';
  try {
    const res = await promptToolApi.generate({
      category: cat,
      provider_id: providerId,
      model,
      custom_prompt: s.customPrompt,
      base_info: s.baseInfo,
    });
    if (res.code === 200) {
      s.result = res.data?.content || '';
      s.hasError = false;
    } else {
      // 后端返回非 200：把原因写进输出框，同时保留轻量 toast
      const reason = res.message || t('生成失败', 'Failed');
      s.result = (t('生成失败：', 'Generation failed: ')) + reason;
      s.hasError = true;
      ElMessage.warning(reason);
    }
  } catch (e) {
    const msg = e?.message || '';
    let reason;
    // 免费模型在繁忙时容易出现请求超时，给出明确的引导提示
    if (/timeout|timed ?out|超时|ETIMEDOUT|ECONNABORTED/i.test(msg)) {
      reason = t(
        '生成超时：免费模型在高峰期响应较慢。请稍后重试，或在「模型配置」中配置自己的 API Key 以获得更稳定的体验。',
        'Generation timed out: the free model can be slow during peak hours. Please retry later, or configure your own API Key for a more stable experience.'
      );
      ElMessage.warning(reason);
    } else {
      reason = (t('生成失败：', 'Generation failed: ')) + (msg || t('请稍后重试', 'please retry later'));
      ElMessage.error(reason);
    }
    // 把失败原因直接写进输出框，而非只弹 toast
    s.result = reason;
    s.hasError = true;
  } finally {
    s.loading = false;
  }
};

const isFreeCat = (cat) => (state[cat].selection || '').startsWith('free::');

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
            <span>{{ t('当前使用免费模型，配置自己的 API Key 更能稳定生成，选择已配置的key什么都可以生成哦(๑•̀ㅂ•́)و✧。', 'Using the free model now; generation may be slow or time out during peak hours. Retry later, or configure your own API Key for stability.') }}</span>
          </div>
          <div class="pt-field">
            <label class="pt-label">{{ t('模型', 'Model') }}</label>
            <el-select
              v-model="state.character.selection"
              :placeholder="t('选择模型', 'Select model')"
              class="pt-model-select"
              filterable
            >
              <el-option
                v-for="m in characterModelOptions"
                :key="m.value"
                :value="m.value"
                :label="m.label"
              />
            </el-select>
          </div>

          <div class="pt-field">
            <div class="pt-label-row">
              <label class="pt-label">{{ t('（想吃肉就不输入，正常人设点击填入默认）', 'Leave empty for unrestricted generation; use default for a normal persona') }}</label>
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
              :placeholder="CHARACTER_PLACEHOLDER"
            />
          </div>

          <div class="pt-field">
            <label class="pt-label">{{ t('参考素材（可选，留空则随机生成）', 'Reference material (optional, empty = random)') }}</label>
            <el-input
              v-model="state.character.baseInfo"
              type="textarea"
              :rows="3"
              :placeholder="t('如：冷艳的末世女剑客，黑色长风衣，沉默但保护欲强', 'e.g. a cold apocalyptic swordswoman in a black trench coat')"
            />
            <div class="pt-field-hint">
              （{{ t('只填入人物基础信息，也可以是你复制过来的人物设定，', 'Enter only basic character info or a copied persona.') }}
              <strong>【{{ t('但是需要去掉提示词约束', 'Remove any prompt constraints first') }}】</strong>）
            </div>
            <div class="pt-field-hint">
              {{ t('生成的人设建议保持精简：它会被贴回「AI 人设」，每轮对话都要带上，篇幅越长越费 token。',
                'Keep the generated persona short: it becomes the AI persona and is sent with every turn, so length costs tokens.') }}
            </div>
          </div>

          <el-button
            type="primary"
            class="pt-gen"
            :icon="MagicStick"
            :loading="state.character.loading"
            @click="generate('character')"
          >
            {{ t('一键增强角色设定', 'Enhance character') }}
          </el-button>

          <div v-if="state.character.result" class="pt-result" :class="{ 'is-error': state.character.hasError }">
            <el-input
              v-model="state.character.result"
              type="textarea"
              :rows="8"
              readonly
              :class="{ 'pt-result-input-error': state.character.hasError }"
            />
            <div v-if="!state.character.hasError" class="pt-result-actions">
              <el-button size="small" type="primary" plain @click="insertToInput('character')">
                {{ t('插入输入框', 'Insert to input') }}
              </el-button>
              <el-button size="small" :icon="CopyDocument" @click="copyResult('character')">
                {{ t('复制', 'Copy') }}
              </el-button>
            </div>
            <div v-else class="pt-result-error-tip">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ t('生成未完成，请修正后重试', 'Generation failed. Please fix and retry.') }}</span>
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
            <el-select
              v-model="state.image.selection"
              :placeholder="t('选择模型', 'Select model')"
              class="pt-model-select"
              filterable
            >
              <el-option
                v-for="m in imageModelOptions"
                :key="m.value"
                :value="m.value"
                :label="m.label"
              />
            </el-select>
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

          <div v-if="state.image.result" class="pt-result" :class="{ 'is-error': state.image.hasError }">
            <el-input
              v-model="state.image.result"
              type="textarea"
              :rows="8"
              readonly
              :class="{ 'pt-result-input-error': state.image.hasError }"
            />
            <div v-if="!state.image.hasError" class="pt-result-actions">
              <el-button size="small" type="primary" plain @click="insertToInput('image')">
                {{ t('插入输入框', 'Insert to input') }}
              </el-button>
              <el-button size="small" :icon="CopyDocument" @click="copyResult('image')">
                {{ t('复制', 'Copy') }}
              </el-button>
            </div>
            <div v-else class="pt-result-error-tip">
              <el-icon><WarningFilled /></el-icon>
              <span>{{ t('生成未完成，请修正后重试', 'Generation failed. Please fix and retry.') }}</span>
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

.pt-field-hint {
  margin-top: -2px;
  font-size: 11.5px;
  line-height: 1.45;
  color: #9b846c;
}

.pt-actions {
  display: flex;
  gap: 4px;
}

.pt-model-select {
  flex: 1;
  min-width: 0;
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

/* 输出框：失败原因呈现时整体标红，提醒用户这不是可插入的提示词 */
.pt-result.is-error :deep(.pt-result-input-error .el-textarea__inner) {
  background: #fdf2f2;
  color: #b03a2e;
  border-color: #f0c9c9;
  box-shadow: none;
}

.pt-result-error-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #b03a2e;
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
