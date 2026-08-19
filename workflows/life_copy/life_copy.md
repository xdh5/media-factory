# Life Copy 工作流

中文人生文案文生图短视频。文生图 MCP 的一条业务线，id 为 `life_copy`（不能写成 `life-copy`，话题库和目录只接受小写字母和下划线）。

MCP：`python -m mcp_servers.text2image`，调用时 `line="life_copy"`。

## 你要改哪些（只改本目录）

管线、MCP 工具名、出片逻辑都不用动。按下面改即可。

| 你想换的 | 改这个文件 | 怎么改 |
|---|---|---|
| 画风 | `_constants.py` 的 `VISUAL_STYLE` | `painterly` / `realistic` / `paper` |
| BGM | `_constants.py` 的 `BGM_ID` | `cinematic_inspirational_piano` / `ambient_piano` / `ambient_techno` |
| BGM 音量、淡入淡出 | `_constants.py` 的 `BGM_GAIN`、`MIX_GAIN`、`BGM_FADE_*` | 数字；Agent 不会改 |
| 旁白音色、倍速 | `_constants.py` 的 `TTS_VOICE`、`TTS_RATE` | 例如 `zh-CN-YunjianNeural`、`+20%` |
| 发布账号组 | `_constants.py` 的 `MATRIXMEDIA_ACCOUNT_GROUP` | 必须和矩媒 GUI 账号组名一字不差 |
| 写稿口吻、题材 | `prompts/article.md` | 保留 `{{topic}}` `{{hooks}}` `{{article_examples}}` |
| 开头钩子库 | `examples/hooks.txt` | 一行一句，给模型学力度，不要当成品照抄 |
| 正文范文 | `examples/*.txt` | 至少一篇；不要命名为 `hooks.txt` |
| 镜头画面规矩 | `prompts/shot_image_rules.md` | 无文字、人物气质、场景 |
| 人物/场景参考图 | `static/ref_life_copy.png`，路径在 `_constants.py` 的 `REFERENCE_IMAGE_PATH` | 已接入；换图时覆盖同名文件即可 |
| 片头翻页音效 | `static/page_flip.wav` | 已裁尾部静音；出片时连播九次对齐翻页 |

改完后重启 `media-factory-text2image` MCP。Skill 里的账号组名如果也改了，同步改 `.agents/skills/life-copy/SKILL.md`。

## 目录与数据

- 生产目录：`data/life_copy/runs/{run_id}/`
- 话题去重命名空间：`life_copy`（和财经互不影响）

## 确认门禁

与财经相同：稿件确认 → 制作 → 成片确认发布 → 清缓存确认。发布用账号组「人生文案」（以 `_constants.py` 为准）。
