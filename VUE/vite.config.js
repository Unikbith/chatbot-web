import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2018',
    // 首屏包拆分后浏览器可并行下载并长期缓存
    chunkSizeWarningLimit: 900,
    minify: 'esbuild',
    cssCodeSplit: true,
    assetsInlineLimit: 4096,
    reportCompressedSize: false,
    rollupOptions: {
      output: {
        // 第三方库按类别拆分，命中长期缓存、支持并行加载
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('@element-plus/icons-vue')) return 'ep-icons'
          if (id.includes('element-plus')) return 'element-plus'
          if (id.includes('dompurify')) return 'dompurify'
          if (id.includes('markdown-it')) return 'markdown'
          if (id.includes('@vue') || id.includes('vue-router')) return 'vue-vendor'
          return 'vendor'
        },
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  // 生产构建去掉 console 与 debugger（源码中的 logger 生产态已静默，这里再兜底一次）
  esbuild: {
    drop: ['console', 'debugger'],
  },
})
