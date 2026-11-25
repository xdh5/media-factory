import fs from "fs";
import path from "path";
import { runWithPublishResponse } from "../publishApiResponse.js";

const submitPaths = {
  video: "/xigua/api/upload/PublishVideo",
  article: "/mp/agw/article/publish",
  micro: "/mp/agw/article/wtt",
};

export async function uploadToutiaoImages(page, label, count, action) {
  const images = [];
  await runWithPublishResponse(page, label, async response => {
    const url = new URL(response.url());
    const imageX = ["imagex.bytedanceapi.com", "open.bytedanceapi.com"].includes(url.hostname) && url.searchParams.get("Action") === "CommitImageUpload";
    const material = url.hostname === "mp.toutiao.com" && url.pathname === "/mp/agw/article_material/photo/upload_picture";
    if (response.request().method() !== "POST" || (!imageX && !material)) return false;
    if (!response.ok()) throw new Error(`${label}接口返回HTTP ${response.status()}`);
    const body = await response.json();
    const image = imageX ? body.Result?.Results?.[0] : body;
    const uri = imageX ? image?.Uri : (image?.web_uri || image?.data?.web_uri);
    const success = imageX ? !body.ResponseMetadata?.Error && [200, 2000].includes(image?.UriStatus)
      : (body.state === "SUCCESS" || body.code === 0 || body.err_no === 0);
    if (!success || !uri) throw new Error(`${label}接口未确认图片保存成功：${body.message || body.state || JSON.stringify(body.ResponseMetadata?.Error)}`);
    images.push({ requestPath: url.pathname, httpStatus: response.status(), uri, status: imageX ? image.UriStatus : body.state || body.code || body.err_no });
    console.log("[头条图片接口回执]", JSON.stringify({ operation: label, completed: images.length, expected: count, ...images[images.length - 1] }));
    return images.length === count;
  }, action, 600000);
  return images;
}

export async function submitToutiaoContent(page, data, kind, action) {
  data.toutiaoSubmitting = true;
  const receipt = await runWithPublishResponse(page, `头条${kind}提交`, response =>
    response.request().method() === "POST" && new URL(response.url()).pathname.replace(/\/$/, "") === submitPaths[kind],
  action, 600000);
  const body = receipt.body;
  const success = kind === "video" ? body.status === 0 && body.data?.Code === 0
    : (body.code === 0 || body.err_no === 0 || body.errno === 0 || body.message === "success" || body.message === "提交成功");
  if (!success) throw new Error(`头条${kind}提交失败：${body.data?.Message || body.message || body.err_tips || JSON.stringify(body)}`);
  // 从原始响应读取长整数，避免作品编号经过浮点数转换失真。
  const match = receipt.responseText.match(/"(?:ItemId|pgc_id|group_id|post_id|item_id)"\s*:\s*"?([1-9]\d*)"?/)
    || ((body.data?.id || body.id) && receipt.responseText.match(/"id"\s*:\s*"?([1-9]\d*)"?/));
  if (!match) throw new Error(`头条${kind}提交未返回作品ID，结果待核对，禁止自动重发`);
  const id = match[1];
  const result = { status: true, id, kind, published_at: new Date().toISOString(),
    url: kind === "micro" ? `https://www.toutiao.com/w/${id}/` : `https://www.toutiao.com/${kind === "article" ? "article" : "video"}/${id}/`,
    apiReceipt: { requestPath: receipt.requestPath, httpStatus: receipt.httpStatus,
      statusCode: body.status ?? body.code ?? body.err_no ?? body.errno, code: body.data?.Code, message: body.data?.Message || body.message } };
  const directory = data.publishOptions?.toutiaoManifestPath
    ? JSON.parse(fs.readFileSync(data.publishOptions.toutiaoManifestPath, "utf8")).output_dir
    : path.dirname(path.resolve(data.filePath));
  fs.writeFileSync(path.join(directory, `toutiao-${kind}-publication.json`), JSON.stringify(result, null, 2));
  data.toutiaoPublication = result;
  console.log("[头条提交回执]", JSON.stringify(result));
  return result;
}
