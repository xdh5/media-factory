const API_BASE_URL = "https://media-data.cyberlab.lol";

const statusNames = {
  ready: "可用",
  reserved: "已占用",
  used: "已使用",
  claimed: "已领取",
};

const status = document.querySelector("#status");
const summary = document.querySelector("#summary");
const results = document.querySelector("#inventoryResults");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusChip(value) {
  return element("span", `inventory-status status-${value}`, statusNames[value] || value);
}

function renderSummary(items) {
  summary.replaceChildren();
  for (const item of items) {
    const card = element("article", "summary-card");
    card.append(element("strong", "", String(item.value)));
    card.append(element("span", "", item.label));
    summary.append(card);
  }
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
  const heading = element("div", "inventory-heading");
  const title = element("div");
  title.append(element("p", "inventory-kicker", pack.pack_id));
  title.append(element("h2", "", pack.topic));
  heading.append(title, statusChip(pack.status));
  card.append(heading);

  const grid = element("div", "word-grid");
  const imageUrls = Array.isArray(pack.image_urls) ? pack.image_urls : [];
  for (let index = 0; index < 10; index += 1) {
    const zh = wordAt(pack.words, "en-zh", index);
    const ko = wordAt(pack.words, "en-ko", index);
    const wordCard = element("article", "word-card");
    const imageFrame = element("div", "word-thumbnail");
    if (imageUrls[index]) {
      const image = document.createElement("img");
      image.src = imageUrls[index];
      image.alt = `${zh.english || ko.english || `第 ${index + 1} 个`}主体图`;
      image.loading = "lazy";
      image.decoding = "async";
      imageFrame.append(image);
    } else {
      imageFrame.append(element("span", "image-missing", "缺少图片"));
    }
    wordCard.append(imageFrame);
    wordCard.append(element("strong", "word-english", zh.english || ko.english || "—"));
    wordCard.append(element("span", "word-translation", `${zh.chinese || "—"} · ${zh.romanization || "—"}`));
    wordCard.append(element("span", "word-translation", `${ko.korean || "—"} · ${ko.romanization || "—"}`));
    grid.append(wordCard);
  }
  card.append(grid);

  const meta = element("p", "inventory-meta");
  meta.textContent = pack.status === "claimed" && pack.publish_date
    ? `计划发布日期：${pack.publish_date}`
    : `创建时间：${pack.created_at || "未知"}`;
  card.append(meta);
  return card;
}

async function loadLanguagePacks() {
  status.textContent = "正在读取语言词包…";
  try {
    const response = await fetch(`${API_BASE_URL}/v1/dashboard/language-packs`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "读取失败");
    renderSummary([
      { label: "全部词包", value: payload.summary.total },
      { label: "可用", value: payload.summary.ready },
      { label: "已领取", value: payload.summary.claimed },
    ]);
    results.replaceChildren();
    if (!payload.packs.length) {
      renderEmpty("目前还没有语言词包。");
    } else {
      payload.packs.forEach((pack) => results.append(renderLanguagePack(pack)));
    }
    status.textContent = `已显示 ${payload.packs.length} 个语言词包。`;
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

function renderFinanceArticles(articles) {
  const query = String(document.querySelector("#searchInput")?.value || "").trim().toLocaleLowerCase("zh-CN");
  const selectedStatus = document.querySelector("#statusFilter")?.value || "";
  const filtered = articles.filter((article) =>
    (!selectedStatus || article.status === selectedStatus)
    && (!query || articleSearchText(article).includes(query)));

  results.replaceChildren();
  if (!filtered.length) {
    renderEmpty("没有符合当前筛选条件的财经文章。");
  } else {
    for (const article of filtered) {
      const details = element("details", "article-card");
      const heading = element("summary", "article-summary");
      const main = element("div", "article-summary-main");
      main.append(element("h2", "", article.caption || "未命名文章"));
      const chips = element("div", "article-chips");
      chips.append(statusChip(article.status));
      for (const keyword of article.search_keywords || []) {
        chips.append(element("span", "keyword-chip", keyword));
      }
      main.append(chips);
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
      results.append(details);
    }
  }
  status.textContent = `已显示 ${filtered.length} / ${articles.length} 篇财经文章。`;
}

async function loadFinanceArticles() {
  status.textContent = "正在读取财经文章…";
  try {
    const response = await fetch(`${API_BASE_URL}/v1/dashboard/finance-articles`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "读取失败");
    renderSummary([
      { label: "全部文章", value: payload.summary.total },
      { label: "可用", value: payload.summary.ready },
      { label: "已占用", value: payload.summary.reserved },
      { label: "已使用", value: payload.summary.used },
    ]);
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
