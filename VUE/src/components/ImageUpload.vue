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

// 与后端 upload_guard.MAX_IMAGE_SIZE 保持一致：
// 前端放行、后端拒绝会造成「选了图却没保存」的静默失败
const MAX_IMAGE_SIZE = 5 * 1024 * 1024;
// 与后端 magic bytes 白名单对齐：HEIC / AVIF / SVG / TIFF 等前端放行也会被后端拒
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp'];
const ALLOWED_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'];

const handleFileChange = (event) => {
  const file = event.target.files[0];
  // 清空 input 必须放在所有 return 之前，否则校验失败后无法再次选择同一文件
  event.target.value = '';
  if (!file) return;

  // 检查文件大小（与后端一致：5MB）
  if (file.size > MAX_IMAGE_SIZE) {
    ElMessage.warning('图片大小不能超过 5MB');
    return;
  }

  // 格式校验：file.type 在部分系统/浏览器上为空，用扩展名兜底；
  // 两者其一命中白名单即放行，后端还有 magic bytes 做最终校验
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  const mimeOk = ALLOWED_TYPES.includes(file.type);
  const extOk = ALLOWED_EXTS.includes(ext);
  if (!mimeOk && !extOk) {
    ElMessage.warning('仅支持 PNG / JPG / GIF / WebP / BMP 格式的图片');
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
      accept="image/png,image/jpeg,image/gif,image/webp,image/bmp"
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
