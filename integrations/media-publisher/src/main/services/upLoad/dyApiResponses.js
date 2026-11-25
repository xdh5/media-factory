"use strict";

/** 先监听再操作，避免快速响应丢失；操作失败或超时后释放监听器。 */
export async function runWithDyResponse(page, label, matches, action, timeout = 60000) {
  let timer;
  let listener;
  const pending = new Promise((resolve, reject) => {
    listener = async response => {
      try {
        if (await matches(response)) resolve(response);
      } catch (error) {
        reject(error);
      }
    };
    page.on("response", listener);
    timer = setTimeout(() => reject(new Error(`${label}接口在${timeout / 1000}秒内未返回确认`)), timeout);
  });
  try {
    const [response] = await Promise.all([pending, Promise.resolve().then(action)]);
    const url = new URL(response.url());
    const requestPath = url.pathname + (url.searchParams.has("Action") ? `?Action=${url.searchParams.get("Action")}` : "");
    console.log("[抖音接口响应]", JSON.stringify({ stage: label, requestPath, httpStatus: response.status() }));
    if (!response.ok()) throw new Error(`${label}接口返回HTTP ${response.status()}`);
    const body = await response.json();
    console.log("[抖音接口结果]", JSON.stringify({ stage: label, requestPath, statusCode: body.status_code,
      message: body.status_msg, itemId: body.item_id, chapterCount: body.chapter_list?.length,
      requestId: body.extra?.logid || body.ResponseMetadata?.RequestId, error: body.ResponseMetadata?.Error }));
    return { body, requestPath, httpStatus: response.status() };
  } finally {
    clearTimeout(timer);
    page.off("response", listener);
  }
}

export function requireDySuccess(receipt, label) {
  if (receipt.body.status_code !== 0) {
    throw new Error(`${label}接口失败：状态码${receipt.body.status_code}，${receipt.body.status_msg || "平台未返回成功状态"}`);
  }
  return receipt.body;
}
