"""语言学习 MCP 直接制作编排。"""

from .api import (
    language_learning_build_vocabulary_prompt,
    language_learning_compose_cards,
    language_learning_get_sheet_validation_prompt,
    language_learning_get_visual_validation_prompt,
    language_learning_occupy_topic,
    language_learning_parse_vocabulary_response,
    language_learning_prepare_images,
    language_learning_review_subject_sheet,
    language_learning_save_images,
    language_learning_start_compose_cards,
    language_learning_start_submit_images,
    language_learning_submit_images,
    language_learning_validate_subject_sheet,
)

DIRECT_TOOLS = (
    language_learning_occupy_topic,
    language_learning_build_vocabulary_prompt,
    language_learning_get_visual_validation_prompt,
    language_learning_get_sheet_validation_prompt,
    language_learning_parse_vocabulary_response,
    language_learning_prepare_images,
    language_learning_save_images,
    language_learning_submit_images,
    language_learning_start_submit_images,
    language_learning_validate_subject_sheet,
    language_learning_review_subject_sheet,
    language_learning_compose_cards,
    language_learning_start_compose_cards,
)
