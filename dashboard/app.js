const API_BASE_URL = "https://media-data.cyberlab.lol";
const { element, renderPlatforms } = window.dashboardPlatforms;
const dateInput = document.querySelector("#dateInput");
const endDateInput = document.querySelector("#endDateInput");
const queryButton = document.querySelector("#queryButton");
const allButton = document.querySelector("#allButton");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const modeButtons = [...document.querySelectorAll("[data-date-mode]")];
let dateMode = "single";

function downloadState(outputs) {
  const rows = Array.isArray(outputs) ? outputs : [];
  const available = rows.find((item) => item.r2_url && !item.r2_expired);
  if (available) return { enabled: true, url: available.r2_url, label: "下载" };
  return { enabled: false, url: "", label: "下载", reason: rows.some((item) => item.r2_expired) ? "产物已过期" : "暂无可下载文件" };
}

function downloadOutput(url) {
  const frameName = "cloudflare-download-frame";
  let frame = document.querySelector(`iframe[name="${frameName}"]`);
  if (!frame) {
    frame = document.createElement("iframe");
    frame.name = frameName;
    frame.hidden = true;
    document.body.append(frame);
  }
  const form = document.createElement("form");
  form.method = "post";
  form.action = `${API_BASE_URL}/v1/dashboard/download`;
  form.target = frameName;
  form.hidden = true;
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = "url";
  input.value = url;
  form.append(input);
  document.body.append(form);
  form.submit();
  form.remove();
}

function beijingDate() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
}

function render(data) {
  results.replaceChildren();
  const dates = (data.dates || []).map((day) => ({
    ...day, contents: day.contents.filter((content) => content.business_line !== "anime"),
  })).filter((day) => day.contents.length);
  if (!dates.length) {
    results.append(element("div", "empty", "所选日期没有产物或发布记录。"));
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
      card.append(element("h3", "", content.title));
      const footer = element("div", "card-footer");
      const configured = data.platforms_by_business_line?.[content.business_line]
        || ["youtube", "facebook", "instagram", "tiktok", "douyin", "kuaishou", "toutiao", "wechat_channels"];
      footer.append(renderPlatforms(content.publications || [], configured));
      const download = downloadState(content.outputs);
      const button = element("button", "card-button download-button", download.label);
      button.type = "button";
      button.disabled = !download.enabled;
      button.title = download.reason || "下载成片";
      button.setAttribute("aria-label", `${download.label}：${content.title}`);
      if (download.enabled) button.addEventListener("click", () => downloadOutput(download.url));
      footer.append(button);
      card.append(footer);
      grid.append(card);
    }
    section.append(grid);
    results.append(section);
  }
}

async function loadRecords(range = null) {
  status.textContent = "正在读取记录…";
  queryButton.disabled = true;
  allButton.disabled = true;
  try {
    const query = range ? `?from=${encodeURIComponent(range.from)}&to=${encodeURIComponent(range.to)}` : "";
    const response = await fetch(`${API_BASE_URL}/v1/dashboard/records${query}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "读取失败");
    if (range) {
      payload.dates = (payload.dates || []).filter((item) => item.date >= range.from && item.date <= range.to);
      payload.dates.sort((left, right) => left.date.localeCompare(right.date));
    }
    render(payload);
    status.textContent = "";
  } catch (error) {
    results.replaceChildren();
    status.textContent = `读取失败：${error.message}`;
  } finally {
    queryButton.disabled = false;
    allButton.disabled = false;
  }
}

for (const button of modeButtons) {
  button.addEventListener("click", () => {
    dateMode = button.dataset.dateMode;
    modeButtons.forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    document.querySelector("#endDateField").hidden = dateMode !== "range";
    document.querySelector("#dateLabel").textContent = dateMode === "range" ? "开始日期" : "日期";
    if (!dateInput.value) dateInput.value = beijingDate();
    if (!endDateInput.value || endDateInput.value < dateInput.value) endDateInput.value = dateInput.value;
  });
}

queryButton.addEventListener("click", () => {
  const from = dateInput.value;
  const to = dateMode === "single" ? from : endDateInput.value;
  if (!from || !to) {
    status.textContent = dateMode === "single" ? "请选择日期。" : "请选择开始和结束日期。";
    return;
  }
  if (from > to) {
    status.textContent = "结束日期不能早于开始日期。";
    return;
  }
  loadRecords({ from, to });
});
allButton.addEventListener("click", () => loadRecords());
dateInput.value = beijingDate();
endDateInput.value = dateInput.value;
loadRecords({ from: dateInput.value, to: dateInput.value });
