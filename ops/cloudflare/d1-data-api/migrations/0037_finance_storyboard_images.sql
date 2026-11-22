-- 分镜图片按原稿和分镜版本存放，绑定成片后才进入发布后的清理流程。
CREATE TABLE finance_storyboard_image_sets (
    aweme_id TEXT NOT NULL REFERENCES douyin_research_contents(aweme_id),
    storyboard_hash TEXT NOT NULL,
    images_json TEXT NOT NULL CHECK(json_valid(images_json)),
    production_id TEXT,
    publish_date TEXT,
    deleted_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (aweme_id, storyboard_hash)
);

-- 发送前记录全部目标，避免部分平台成功就误判整条视频已经发布。
CREATE TABLE production_publication_targets (
    production_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    PRIMARY KEY (production_id, platform, account_id)
);
