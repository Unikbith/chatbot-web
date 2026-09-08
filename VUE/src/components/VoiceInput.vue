<script setup>
import { ref, computed, onUnmounted } from 'vue';
import { ElMessage } from 'element-plus';
import { Microphone, Warning } from '@element-plus/icons-vue';
import { audioApi, providersApi } from '@/utils/resAi';

const emit = defineEmits(['textReady']);
const props = defineProps({
  providerId: {
    type: [Number, String],
    default: null
  }
});

const isRecording = ref(false);
const isProcessing = ref(false);
const recordingTime = ref(0);
let mediaRecorder = null;
let audioChunks = [];
let timer = null;

const timeDisplay = computed(() => {
  const mins = Math.floor(recordingTime.value / 60);
  const secs = recordingTime.value % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
});

const startRecording = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = handleRecordingStop;

    mediaRecorder.start();
    isRecording.value = true;
    recordingTime.value = 0;

    timer = setInterval(() => {
      recordingTime.value++;
    }, 1000);

  } catch (e) {
    console.error('录音失败', e);
    ElMessage.error('无法访问麦克风，请检查权限设置');
  }
};

const stopRecording = () => {
  if (mediaRecorder && isRecording.value) {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
    isRecording.value = false;
    
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }
};

const handleRecordingStop = async () => {
  if (audioChunks.length === 0) {
    ElMessage.warning('没有录到声音');
    return;
  }

  isProcessing.value = true;
  try {
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const audioFile = new File([audioBlob], 'recording.webm', { type: 'audio/webm' });

    const providerId = props.providerId || providersApi.getCurrentId('stt');
    const res = await audioApi.speechToText(audioFile, providerId);

    if (res.code === 200 && res.data?.text) {
      emit('textReady', res.data.text);
      ElMessage.success('语音识别成功');
    } else {
      ElMessage.error(res.message || '语音识别失败');
    }
  } catch (e) {
    console.error('语音识别错误', e);
    ElMessage.error('语音识别失败，请检查 API 配置');
  } finally {
    isProcessing.value = false;
    audioChunks = [];
  }
};

const toggleRecording = () => {
  if (isRecording.value) {
    stopRecording();
  } else {
    startRecording();
  }
};

onUnmounted(() => {
  if (mediaRecorder && isRecording.value) {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
  }
  if (timer) clearInterval(timer);
});
</script>

<template>
  <div class="voice-input">
    <el-button
      :class="{ recording: isRecording }"
      :icon="isRecording ? Warning : Microphone"
      circle
      @click="toggleRecording"
      :loading="isProcessing"
      :title="isRecording ? '停止录音' : '语音输入'"
    />
    <div v-if="isRecording" class="recording-indicator">
      <span class="pulse"></span>
      <span class="time">{{ timeDisplay }}</span>
    </div>
  </div>
</template>

<style scoped>
.voice-input {
  display: flex;
  align-items: center;
  gap: 8px;
}

.voice-input :deep(.el-button) {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: #6b7280;
}

.voice-input :deep(.el-button:hover) {
  background: #e5e7eb;
  color: #374151;
}

.voice-input :deep(.el-button.recording) {
  background: #fee2e2;
  color: #dc2626;
  animation: pulse-bg 1s infinite;
}

@keyframes pulse-bg {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.recording-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #dc2626;
}

.pulse {
  width: 8px;
  height: 8px;
  background: #dc2626;
  border-radius: 50%;
  animation: pulse-dot 1s infinite;
}

@keyframes pulse-dot {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.3); opacity: 0.7; }
}

.time {
  font-family: monospace;
  font-weight: 500;
}
</style>
