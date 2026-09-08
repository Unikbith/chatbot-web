<script setup>
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import { Picture, Close } from '@element-plus/icons-vue';

const emit = defineEmits(['imageSelected', 'clear']);

const selectedImage = ref(null);
const fileInput = ref(null);

const triggerUpload = () => {
  fileInput.value?.click();
};

const handleFileChange = (event) => {
  const file = event.target.files[0];
  if (!file) return;

  // 检查文件大小（限制 10MB）
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 10MB');
    return;
  }

  // 检查文件类型
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件');
    return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    selectedImage.value = {
      file,
      dataUrl: e.target.result,
      name: file.name,
    };
    emit('imageSelected', selectedImage.value);
  };
  reader.readAsDataURL(file);
  
  // 清空 input，允许重复选择同一文件
  event.target.value = '';
};

const clearImage = () => {
  selectedImage.value = null;
  emit('clear');
};

defineExpose({
  clearImage,
  getImage: () => selectedImage.value,
});
</script>

<template>
  <div class="image-upload">
    <input
      ref="fileInput"
      type="file"
      accept="image/*"
      style="display: none"
      @change="handleFileChange"
    />
    
    <div v-if="selectedImage" class="image-preview">
      <img :src="selectedImage.dataUrl" alt="预览" class="preview-img" />
      <el-button
        class="remove-btn"
        :icon="Close"
        circle
        size="small"
        @click="clearImage"
      />
    </div>
    
    <el-button
      v-else
      :icon="Picture"
      circle
      @click="triggerUpload"
      title="上传图片"
      class="upload-btn"
    />
  </div>
</template>

<style scoped>
.image-upload {
  position: relative;
}

.upload-btn {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: #6b7280;
}

.upload-btn:hover {
  background: #e5e7eb;
  color: #374151;
}

.image-preview {
  position: relative;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  overflow: hidden;
  border: 2px solid var(--brand);
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.remove-btn {
  position: absolute;
  top: -8px;
  right: -8px;
  width: 18px;
  height: 18px;
  --el-button-bg-color: #ef4444;
  --el-button-hover-bg-color: #dc2626;
  --el-button-text-color: #fff;
  --el-button-hover-text-color: #fff;
}

.remove-btn :deep(.el-icon) {
  font-size: 10px;
}
</style>
