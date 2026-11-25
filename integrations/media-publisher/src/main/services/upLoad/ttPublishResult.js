import { setPublishStage } from "../publishStage.js";
import fs from "fs";
import path from "path";
import maybeClosePublishWindow from "./closeWindow.js";

export async function saveToutiaoPublicationResult(page, data, manifest, kind, event, window) {
  setPublishStage(page, "核对头条作品管理中的发布结果");
  if (kind === 'article') {
    const verified = await page.evaluate(async id => {
      const response = await fetch(`/mp/agw/article/edit?pgc_id=${id}&wxstyle=0&format=json`);
      if (!response.ok) throw new Error(`头条文章核验接口返回HTTP ${response.status}`);
      const body = await response.json();
      return { id: body.pgc_id, title: body.title, isDraft: body.is_draft, passed: body.is_passed,
        coverUris: body.pgc_feed_covers.map(cover => cover.origin_uri || cover.thumb_url) };
    }, data.toutiaoPublication.id);
    console.log('[头条文章发布核验]', JSON.stringify(verified));
    if (String(verified.id) !== data.toutiaoPublication.id || verified.title !== manifest.title || verified.isDraft !== false) {
      throw new Error('头条文章接口尚未确认正式提交，禁止自动重发');
    }
    const expected = [data.toutiaoCover.uri, data.toutiaoCover.originUri].filter(Boolean);
    if (verified.coverUris.length !== 1 || !verified.coverUris.some(uri => expected.includes(uri))) {
      throw new Error('头条文章接口保存的封面与本期指定封面不一致，禁止自动重发');
    }
    data.toutiaoPublication.verification = verified;
  } else await page.waitForFunction(type => {
    const current = location.pathname;
    if (type === "micro") return current === "/profile_v4/weitoutiao";
    return /manage\/content|xigua\/content/.test(current) || /发布成功|提交成功|全部发表成功/.test(document.body.innerText);
  }, { timeout: 60000, polling: 250 }, kind);
  const result = { ...data.toutiaoPublication, kind, title: manifest.title, management_url: page.url() };
  const filename = path.join(manifest.output_dir, `toutiao-${kind}-publication.json`);
  setPublishStage(page, "保存头条平台发布回执");
  fs.writeFileSync(filename, JSON.stringify(result, null, 2));
  event.reply("puppeteerFile-done", { ...data, status: true, message: `头条${kind}发布已提交`, publicationReceipt: filename, outcome: result });
  maybeClosePublishWindow(data, window);
  return result;
}
