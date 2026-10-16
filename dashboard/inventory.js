const API_BASE_URL = "https://media-data.cyberlab.lol";

const status = document.querySelector("#status");
const results = document.querySelector("#inventoryResults");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderEmpty(message) {
  results.replaceChildren(element("div", "empty", message));
}

function wordAt(words, mode, index) {
  const rows = Array.isArray(words?.[mode]) ? words[mode] : [];
  return rows[index] || {};
}

function renderLanguagePack(pack) {
  const card = element("article", "pack-card");
  card.append(element("h2", "pack-topic", pack.topic));

  const grid = element("div", "word-grid");
  const imageUrls = Array.isArray(pack.image_urls) ? pack.image_urls : [];
  for (let index = 0; index < 10; index += 1) {
    const zh = wordAt(pack.words, "en-zh", index);
    const ko = wordAt(pack.words, "en-ko", index);
    const wordCard = element("article", "word-card");
    const imageFrame = element("div", "word-thumbnail");
    if (imageUrls[index]) {
      const image = document.createElement("img");
      image.alt = `${zh.english || ko.english || `第 ${index + 1} 个`}主体图`;
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("load", () => {
        const fitted = fitSubjectIntoFrameRatio(image.naturalWidth, image.naturalHeight);
        image.style.width = fitted.width;
        image.style.height = fitted.height;
        image.style.left = fitted.left;
        image.style.top = fitted.top;
      });
      image.src = imageUrls[index];
      imageFrame.append(image);
    } else {
      imageFrame.append(element("span", "image-missing", "缺少图片"));
    }
    wordCard.append(imageFrame);
    wordCard.append(element("strong", "word-english", zh.english || ko.english || "—"));
    wordCard.append(element("span", "word-translation", [zh.chinese, ko.korean].filter(Boolean).join(" · ")));
    grid.append(wordCard);
  }
  card.append(grid);

  return card;
}

const PAGE_SIZE = 5;
let lazyObserver = null;

function mountLazyList(items, renderItem, emptyMessage) {
  lazyObserver?.disconnect();
  lazyObserver = null;
  results.replaceChildren();
  if (!items.length) {
    renderEmpty(emptyMessage);
    return;
  }
  let shown = 0;
  const sentinel = element("div", "lazy-sentinel");
  const finish = () => {
    sentinel.remove();
    lazyObserver?.disconnect();
    lazyObserver = null;
  };
  const reveal = () => {
    items.slice(shown, shown + PAGE_SIZE).forEach((item) => results.insertBefore(renderItem(item), sentinel));
    shown = Math.min(shown + PAGE_SIZE, items.length);
    if (shown >= items.length) finish();
  };
  const nearViewport = () => {
    const box = sentinel.getBoundingClientRect();
    return box.top <= window.innerHeight + 240;
  };
  const pump = () => {
    if (!sentinel.isConnected || shown >= items.length || !nearViewport()) return;
    reveal();
    window.requestAnimationFrame(pump);
  };
  const watch = () => {
    if (!sentinel.isConnected || shown >= items.length) return;
    lazyObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) pump();
    }, { rootMargin: "240px" });
    lazyObserver.observe(sentinel);
  };
  const fillUntilScrollable = () => {
    if (!sentinel.isConnected || shown >= items.length) {
      watch();
      return;
    }
    if (document.documentElement.scrollHeight > window.innerHeight + 8) {
      watch();
      return;
    }
    reveal();
    window.requestAnimationFrame(fillUntilScrollable);
  };
  results.append(sentinel);
  reveal();
  window.requestAnimationFrame(fillUntilScrollable);
}

async function loadLanguagePacks() {
  status.textContent = "正在读取语言词包…";
  try {
    const response = await fetch(`${API_BASE_URL}/v1/dashboard/language-packs`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "读取失败");
    const filters = [...document.querySelectorAll("[data-pack-status]")];
    let selectedStatus = "ready";
    const unusedCount = payload.packs.filter((pack) => pack.status === "ready").length;
    const renderFiltered = () => {
      const packs = payload.packs.filter((pack) => !selectedStatus || pack.status === selectedStatus);
      mountLazyList(
        packs,
        renderLanguagePack,
        selectedStatus ? "这个状态下还没有语言词包。" : "目前还没有语言词包。",
      );
    };
    filters.forEach((button) => button.addEventListener("click", () => {
      selectedStatus = button.dataset.packStatus;
      filters.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      renderFiltered();
    }));
    status.textContent = `还剩 ${unusedCount} 篇未使用词包`;
    renderFiltered();
  } catch (error) {
    renderEmpty("语言词包暂时无法显示。");
    status.textContent = `读取失败：${error.message}`;
  }
}

function articleSearchText(article) {
  return [
    article.caption,
    article.article,
    article.author_name,
    ...(article.search_keywords || []),
  ].join(" ").toLocaleLowerCase("zh-CN");
}

function renderFinanceArticle(article) {
  const details = element("details", "article-card");
  const heading = element("summary", "article-summary");
  const main = element("div", "article-summary-main");
  const title = String(article.caption || "").replace(/#[^\s#]+/gu, "").replace(/\s+/gu, " ").trim();
  main.append(element("h2", "", title || "未命名文章"));
  heading.append(main);
  heading.append(element("span", "details-hint", "展开正文"));
  details.append(heading);

  const body = element("div", "article-body");
  body.append(element("p", "article-text", article.article || "暂无正文"));
  const meta = element("div", "article-meta");
  meta.append(element("span", "", `来源：${article.author_name || "未知作者"}`));
  if (article.run_id) meta.append(element("span", "", `生产任务：${article.run_id}`));
  if (article.aweme_url) {
    const sourceLink = element("a", "", "查看来源");
    sourceLink.href = article.aweme_url;
    sourceLink.target = "_blank";
    sourceLink.rel = "noreferrer";
    meta.append(sourceLink);
  }
  body.append(meta);
  details.append(body);
  return details;
}

function renderFinanceArticles(articles) {
  const query = String(document.querySelector("#searchInput")?.value || "").trim().toLocaleLowerCase("zh-CN");
  const selectedStatus = document.querySelector("#statusFilter")?.value || "";
  const filtered = articles.filter((article) =>
    (!selectedStatus || article.status === selectedStatus)
    && (!query || articleSearchText(article).includes(query)));
  mountLazyList(
    filtered,
    renderFinanceArticle,
    "没有符合当前筛选条件的财经文章。",
  );
}

async function loadFinanceArticles() {
  status.textContent = "正在读取财经文章…";
  try {
    const response = await fetch(`${API_BASE_URL}/v1/dashboard/finance-articles`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "读取失败");
    document.querySelector("#inventoryNote").textContent = `还剩 ${payload.summary.ready} 篇未使用文章`;
    status.textContent = "";
    const rerender = () => renderFinanceArticles(payload.articles);
    document.querySelector("#searchInput").addEventListener("input", rerender);
    document.querySelector("#statusFilter").addEventListener("change", rerender);
    rerender();
  } catch (error) {
    renderEmpty("财经文章暂时无法显示。");
    status.textContent = `读取失败：${error.message}`;
  }
}

if (document.body.dataset.page === "language-packs") {
  loadLanguagePacks();
} else if (document.body.dataset.page === "finance-articles") {
  loadFinanceArticles();
}
