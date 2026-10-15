const API_BASE_URL = "https://media-data.cyberlab.lol";
const { element, renderPlatforms } = window.dashboardPlatforms;
const status = document.querySelector("#status");
const results = document.querySelector("#animeResults");
const search = document.querySelector("#searchInput");
let contents = [];

function render() {
  const query = search.value.trim().toLocaleLowerCase("zh-CN");
  const filtered = contents.filter((item) => item.title.toLocaleLowerCase("zh-CN").includes(query));
  results.replaceChildren();
  if (!filtered.length) {
    results.append(element("div", "empty", query ? "没有找到这部动画。" : "还没有已发布的动画。"));
    return;
  }
  for (const content of filtered) {
    const card = element("article", "content-card");
    card.append(element("h2", "", content.title));
    card.append(renderPlatforms(content.publications));
    results.append(card);
  }
}

async function loadAnime() {
  status.textContent = "正在读取动画发布记录…";
  try {
    const response = await fetch(`${API_BASE_URL}/v1/dashboard/anime`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "读取失败");
    contents = payload.contents || [];
    render();
    status.textContent = "";
  } catch (error) {
    status.textContent = `读取失败：${error.message}`;
  }
}

search.addEventListener("input", render);
loadAnime();
