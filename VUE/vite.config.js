import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import path from 'path'
import { readFileSync, writeFileSync, existsSync } from 'node:fs'

// 生产构建清理产物注释：index.html 不会被 esbuild 处理，
// 其中的 HTML 注释与内联 <style> 的 CSS 注释会原样保留到 dist，
// 开发者工具查看源码即可读到实现说明，这里在打包完成后统一剥离。
function stripBuildComments() {
  return {
    name: 'strip-build-comments',
    apply: 'build',
    closeBundle() {
      const distHtml = path.resolve(__dirname, 'dist/index.html')
      if (!existsSync(distHtml)) return
      let html = readFileSync(distHtml, 'utf8')
      // 移除 HTML 注释（<!---->、<!--v-if--> 等功能性锚点由 Vue 运行时生成，
      // 不在产物 HTML 中，正则只需清掉源码注释）
      html = html.replace(/<!--[\s\S]*?-->/g, '')
      // 移除内联 <style> 块内的 CSS 注释
      html = html.replace(/<style([^>]*)>([\s\S]*?)<\/style>/gi, (m, attr, css) => {
        const clean = css.replace(/\/\*[\s\S]*?\*\//g, '')
        return `<style${attr}>${clean}</style>`
      })
      writeFileSync(distHtml, html)
    },
  }
}

export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需引入：只打包模板里实际用到的组件与对应样式，
    // 不再整包注册（整包约 244 KB gzip，按需后通常几十 KB）。
    // 未在模板中出现的组件不会进入产物，也不会因漏配而白屏——
    // 真正用到却没被扫描到时，dev 控制台会给出明确警告。
    Components({
      resolvers: [ElementPlusResolver()],
      dts: false,
    }),
    stripBuildComments(),
  ],
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
          // element-plus 不强制合并：按需引入后各组件样式/JS 粒度已很小，
          // 强行打进同一 chunk 反而会让未用到的样式无法被摇掉
          // （实测合并后 CSS 185 KB，不合并仅 21 KB）。
          if (id.includes('element-plus')) return
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
    // 连第三方库的 license 头注释也一并剥离，避免产物残留可读说明
    legalComments: 'none',
  },
})
