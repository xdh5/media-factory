import { setPublishStage } from "../publishStage.js";
import fs from "fs";
import { fillToutiaoArticle, uploadToutiaoArticleCover, setToutiaoCheckbox, clickToutiaoText, waitToutiaoArticleImagesReady } from "./ttText.js";
import { saveToutiaoPublicationResult } from "./ttPublishResult.js";
import { submitToutiaoContent } from "./ttApiResponses.js";

export async function publishToutiaoArticle(page, data, window, event) {
  const filename = data.publishOptions.toutiaoManifestPath;
  const manifest = JSON.parse(fs.readFileSync(filename, "utf8"));
  setPublishStage(page, "打开头条文章发布页");
  await page.goto("https://mp.toutiao.com/profile_v4/graphic/publish", { waitUntil: "domcontentloaded" });
  setPublishStage(page, "填写头条文章标题、正文和插图");
  const article = await fillToutiaoArticle(page, filename);
  const imageCount = article.paragraphs.filter(row => row.image).length;
  setPublishStage(page, "设置头条文章引用AI声明");
  await setToutiaoCheckbox(page, "引用AI", manifest.publish_options.quote_ai);
  setPublishStage(page, "上传和保存头条文章封面");
  data.toutiaoCover = await uploadToutiaoArticleCover(page, manifest.cover_path);
  setPublishStage(page, "等待头条文章正文图片和封面上传完成");
  await waitToutiaoArticleImagesReady(page, imageCount, true);
  setPublishStage(page, "预览头条文章并等待确认发布按钮");
  const preview = await page.evaluate(() => [...document.querySelectorAll('button')].some(element =>
    element.textContent.trim() === '预览并发布' && element.getBoundingClientRect().width > 0));
  if (preview) {
    await clickToutiaoText(page, "预览并发布");
    await page.waitForFunction(() => [...document.querySelectorAll('button')].some(element =>
      element.textContent.trim() === "确认发布" && !element.disabled), { timeout: 60000, polling: 100 });
  }
  await waitToutiaoArticleImagesReady(page, imageCount, true);
  setPublishStage(page, "确认发布头条文章");
  await submitToutiaoContent(page, data, "article", () => clickToutiaoText(page, preview ? '确认发布' : '发布'));
  return saveToutiaoPublicationResult(page, data, manifest, "article", event, window);
}
