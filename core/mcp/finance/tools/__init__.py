"""财经 MCP 内部编排模块。"""

from .assemble_finance_video import finish_finance_video
from .agent_tasks import (
    build_article_generation_prompt,
    build_article_chunk_generation_prompt,
    build_metadata_generation_prompt,
    build_source_hook_prompt,
    build_topic_prompt,
    plan_article_chunks,
    validate_article_chunk_response,
    validate_article_response,
    validate_metadata_response,
    validate_source_hook_response,
    validate_topic_response,
)
from .generate_qwen_shot_images import commit_existing_qwen_shot_images, generate_qwen_shot_images
from .parse_metadata import parse_metadata
from .prepare_shot_images import prepare_shot_images
from .prepare_videos import (
    build_stock_video_selection_prompt,
    download_selected_videos,
    prepare_video_searches,
    validate_stock_video_selection_response,
)
from .prompts import build_article_prompt, build_metadata_prompt
from .save_draft import load_draft, save_draft, save_source_usage
from .storyboard import parse_storyboard, prepare_storyboard, resolve_material_strategy
from .upload_to_r2 import upload_finance_assets_to_r2

__all__ = [
    "build_article_prompt",
    "build_article_generation_prompt",
    "build_article_chunk_generation_prompt",
    "build_metadata_generation_prompt",
    "build_metadata_prompt",
    "build_source_hook_prompt",
    "build_stock_video_selection_prompt",
    "build_topic_prompt",
    "plan_article_chunks",
    "commit_existing_qwen_shot_images",
    "download_selected_videos",
    "finish_finance_video",
    "generate_qwen_shot_images",
    "load_draft",
    "parse_metadata",
    "parse_storyboard",
    "prepare_shot_images",
    "prepare_storyboard",
    "prepare_video_searches",
    "resolve_material_strategy",
    "save_draft",
    "save_source_usage",
    "upload_finance_assets_to_r2",
    "validate_article_response",
    "validate_article_chunk_response",
    "validate_metadata_response",
    "validate_source_hook_response",
    "validate_stock_video_selection_response",
    "validate_topic_response",
]
