/**
 * 图片大图预览（el-image-viewer）打开时，锁住底下的页面滚动。
 *
 * 为什么需要：
 *   Element Plus 的 el-image-viewer 有两个默认行为没兜住 ——
 *     1) 缩放只监听 wheel 做「放大/缩小」，但**没有 preventDefault**，
 *        滚轮事件继续冒泡，浏览器照常滚动底层；
 *     2) 拖动用的是 document 上的 touchmove，同样没拦默认行为，
 *        手指一划就产生滚动链（scroll chaining），底下的聊天列表跟着动。
 *   而且它默认不 teleport（teleported 默认 false），就渲染在当前组件树里，
 *   更贴近底层滚动容器。表现就是「滚轮缩放 / 手指滑动时，图片底下的聊天框一起滚」。
 *
 * 做法：
 *   在 document 上做一次全局拦截，命中「发生在预览层内」的 wheel / touchmove 就
 *   preventDefault。用捕获阶段 + 只 preventDefault（**不** stopPropagation），
 *   所以预览自己的缩放 / 拖动监听照常执行，不会被我们弄失效。
 */
export function installViewerScrollLock() {
  if (typeof document === 'undefined') return;

  const inViewer = (e) => {
    const el = e.target;
    return !!(el && typeof el.closest === 'function' && el.closest('.el-image-viewer__wrapper'));
  };

  const onWheel = (e) => {
    if (inViewer(e)) e.preventDefault();
  };

  const onTouchMove = (e) => {
    if (!inViewer(e)) return;
    // 单指拖动由预览自己处理平移；双指缩放浏览器默认行为在这里也不需要
    // （预览没实现捏合缩放，交给它只会变成页面缩放）
    if (e.cancelable) e.preventDefault();
  };

  document.addEventListener('wheel', onWheel, { passive: false, capture: true });
  document.addEventListener('touchmove', onTouchMove, { passive: false, capture: true });
}
