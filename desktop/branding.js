/* 仅定制新聊天首页标题，模型选择器及实际模型标识保持原样。 */
(() => {
  const selector = '[class~="max-w-[58rem]"] [class~="text-2xl"][class~="line-clamp-1"] span.line-clamp-1';
  const updateTitle = () => {
    const title = document.querySelector(selector);
    if (title && title.textContent !== 'Media Factory') {
      title.textContent = 'Media Factory';
      title.setAttribute('aria-label', 'Media Factory');
      title.closest('[role="button"]')?.setAttribute('aria-label', 'Media Factory');
    }
  };
  updateTitle();
  new MutationObserver(updateTitle).observe(document.body, {childList: true, subtree: true});
})();
