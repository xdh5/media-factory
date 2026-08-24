const API_BASE_URL = "https://media-data.cyberlab.lol";
const PIN_STORAGE_KEY = "media-factory-dashboard-pin";

const platformNames = {
  youtube: "YouTube",
  facebook: "Facebook",
  instagram: "Instagram",
  tiktok: "TikTok",
  kuaishou: "快手",
  douyin: "抖音",
  baijiahao: "百家号",
  toutiao: "头条号",
  wechat_channels: "视频号",
};

const lineNames = { finance: "财经", language_learning: "学语言" };
const sourceNames = { local_mcp: "本地产物", github_workflow: "GitHub 产物" };

const loginLayer = document.querySelector("#loginLayer");
const loginForm = document.querySelector("#loginForm");
const pinInput = document.querySelector("#pinInput");
const loginError = document.querySelector("#loginError");
const toolbar = document.querySelector("#toolbar");
const logoutButton = document.querySelector("#logoutButton");
const dateInput = document.querySelector("#dateInput");
const queryButton = document.querySelector("#queryButton");
const allButton = document.querySelector("#allButton");
const status = document.querySelector("#status");
const results = document.querySelector("#results");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function showLogin(message = "") {
  loginLayer.hidden = false;
  toolbar.hidden = true;
  logoutButton.hidden = true;
  loginError.textContent = message;
  pinInput.focus();
}

function showDashboard() {
  loginLayer.hidden = true;
  toolbar.hidden = false;
  logoutButton.hidden = false;
}

function render(data) {
  results.replaceChildren();
  const dates = Array.isArray(data.dates) ? data.dates : [];
  if (!dates.length) {
    results.append(element("div", "empty", "这个日期还没有产物或发布记录。"));
    return;
  }
  for (const day of dates) {
    const section = element("section", "day-section");
    const heading = element("div", "day-heading");
    heading.append(element("h2", "", day.date));
    heading.append(element("span", "day-count", `${day.contents.length} 条内容`));
    section.append(heading);
    const grid = element("div", "content-grid");
    for (const content of day.contents) {
      const card = element("article", "content-card");
      const meta = element("div", "content-meta");
      meta.append(element("span", "badge", lineNames[content.business_line] || content.business_line));
      if (content.content_kind) meta.append(element("span", "badge neutral", content.content_kind));
      if (Number(content.content_part || 1) > 1) meta.append(element("span", "badge neutral", `第 ${content.content_part} 段`));
      for (const source of new Set((content.outputs || []).map((item) => item.source))) {
        meta.append(element("span", "badge neutral", sourceNames[source] || source));
      }
      card.append(meta, element("h3", "", content.title));
      const publications = content.publications || [];
      if (!publications.length) {
        card.append(element("span", "unpublished", "未发布"));
      } else {
        const platforms = element("div", "platforms");
        const seen = new Set();
        for (const publication of publications) {
          if (seen.has(publication.platform)) continue;
          seen.add(publication.platform);
          const label = `${platformNames[publication.platform] || publication.platform} · ${publication.status === "scheduled" ? "已预约" : "已发布"}`;
          const chip = element(publication.external_url ? "a" : "span", "platform-chip", label);
          if (publication.external_url) {
            chip.href = publication.external_url;
            chip.target = "_blank";
            chip.rel = "noreferrer";
          }
          chip.title = publication.publish_at;
          platforms.append(chip);
        }
        card.append(platforms);
      }
      grid.append(card);
    }
    section.append(grid);
    results.append(section);
  }
}

async function loadRecords(date = "") {
  const pin = localStorage.getItem(PIN_STORAGE_KEY) || "";
  if (!/^\d{6}$/.test(pin)) {
    showLogin();
    return false;
  }
  status.textContent = "正在读取 Cloudflare 数据…";
  queryButton.disabled = true;
  allButton.disabled = true;
  try {
    const query = date ? `?date=${encodeURIComponent(date)}` : "";
    const response = await fetch(`${API_BASE_URL}/v1/dashboard/records${query}`, {
      headers: { "X-Dashboard-Pin": pin },
      cache: "no-store",
    });
    const payload = await response.json();
    if (response.status === 401) {
      localStorage.removeItem(PIN_STORAGE_KEY);
      showLogin("PIN 不正确，请重新输入。");
      return false;
    }
    if (!response.ok) throw new Error(payload?.error?.message || "读取失败");
    showDashboard();
    render(payload);
    status.textContent = date ? `已显示 ${date} 的记录。` : "已显示数据库中的全部日期。";
    return true;
  } catch (error) {
    status.textContent = `读取失败：${error.message}`;
    return false;
  } finally {
    queryButton.disabled = false;
    allButton.disabled = false;
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const pin = pinInput.value.trim();
  if (!/^\d{6}$/.test(pin)) {
    loginError.textContent = "请输入完整的 6 位数字 PIN。";
    return;
  }
  localStorage.setItem(PIN_STORAGE_KEY, pin);
  loginError.textContent = "";
  await loadRecords(dateInput.value);
});

queryButton.addEventListener("click", () => loadRecords(dateInput.value));
allButton.addEventListener("click", () => {
  dateInput.value = "";
  loadRecords();
});
logoutButton.addEventListener("click", () => {
  localStorage.removeItem(PIN_STORAGE_KEY);
  pinInput.value = "";
  results.replaceChildren();
  status.textContent = "";
  showLogin();
});

dateInput.value = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}).format(new Date());

if (localStorage.getItem(PIN_STORAGE_KEY)) loadRecords();
else showLogin();
