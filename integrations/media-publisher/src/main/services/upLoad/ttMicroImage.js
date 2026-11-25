import fs from "fs";
import path from "path";

/** 从本期预制插图中选一张，发布重试复用同一选择。 */
export function selectToutiaoMicroImage(manifest) {
  const selectionPath = path.join(manifest.output_dir, "toutiao-micro-image.json");
  let filename;
  if (fs.existsSync(selectionPath)) {
    filename = JSON.parse(fs.readFileSync(selectionPath, "utf8")).image_filename;
  } else {
    const images = [1, 2, 3].map(index => manifest[`article_image_${index}_path`]);
    filename = path.basename(images[Math.floor(Math.random() * images.length)]);
    fs.writeFileSync(selectionPath, JSON.stringify({ image_filename: filename }, null, 2));
  }
  const imagePath = path.join(manifest.output_dir, filename);
  console.log("[微头条配图选择]", JSON.stringify({ imagePath, selectionPath }));
  return imagePath;
}
