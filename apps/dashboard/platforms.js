(() => {
  const names = {
    youtube: "YouTube", facebook: "Facebook", instagram: "Instagram", tiktok: "TikTok",
    bilibili: "哔哩哔哩", kuaishou: "快手", douyin: "抖音", toutiao: "头条号", wechat_channels: "视频号",
    baijiahao: "百家号", xiaohongshu: "小红书",
  };
  const order = Object.keys(names);
  // 财经同一平台需发布的内容条数：头条视频、文章、微头条，YouTube 长视频、Shorts。
  const financePublishRequirements = { toutiao: 3, youtube: 2 };

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function safeUrl(value) {
    try {
      const url = new URL(value);
      return ["https:", "http:"].includes(url.protocol) ? url.href : "";
    } catch {
      return "";
    }
  }

  function renderPlatforms(publications = [], configured = null, businessLine = "") {
    const list = element("div", "platforms");
    const platforms = [...new Set(Array.isArray(configured)
      ? configured
      : publications.map((item) => item.platform))];
    platforms.sort((left, right) => order.indexOf(left) - order.indexOf(right));
    for (const platform of platforms) {
      const records = publications.filter((item) => item.platform === platform);
      const published = records.find((item) => item.status === "published");
      const scheduled = records.find((item) => item.status === "scheduled");
      const record = published || scheduled;
      const state = published ? "已发送" : scheduled ? "已预约，尚未发送" : "未发送";
      const name = names[platform] || platform;
      const url = safeUrl(record?.external_url);
      const requiredCount = businessLine === "finance" ? financePublishRequirements[platform] : 0;
      const shouldLight = requiredCount
        ? records.filter((item) => item.status === "published").length >= requiredCount
        : Boolean(published || scheduled);
      const icon = element(url ? "a" : "span", `platform-icon${shouldLight ? " is-published" : ""}`);
      icon.title = `${name} · ${state}`;
      icon.setAttribute("aria-label", icon.title);
      if (url) {
        icon.href = url;
        icon.target = "_blank";
        icon.rel = "noopener noreferrer";
      } else {
        icon.tabIndex = 0;
      }
      if (names[platform]) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("aria-hidden", "true");
        const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
        use.setAttribute("href", `./assets/platform-icons.svg?v=20261126-1#${platform}`);
        svg.append(use);
        icon.append(svg);
      } else {
        icon.append(element("span", "platform-fallback", name.slice(0, 1)));
      }
      list.append(icon);
    }
    return list;
  }

  window.dashboardPlatforms = { element, renderPlatforms };
})();
