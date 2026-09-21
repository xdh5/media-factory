# 正版视频素材工具

公开入口：`core.tools.stock_video`。

## 能力

- `search_stock_videos`：按 Pexels → Pixabay → Coverr 顺序搜索；上一站无结果、缺少密钥或请求失败时才进入下一站。
- `download_stock_video`：只下载搜索结果中的受信任官方域名 MP4。
- `prepare_stock_clip`：循环、裁切、静音并规范化为指定时长和尺寸，同时可提取封面帧。

## 环境变量

- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `COVERR_API_KEY`

搜索结果缓存24小时。候选记录始终保留来源页、作者和署名文案；工具不会把署名烧进视频。
