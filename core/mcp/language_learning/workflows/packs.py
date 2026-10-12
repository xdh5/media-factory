"""语言学习 MCP 预制包编排。"""

from .api import (
    language_learning_claim_pack,
    language_learning_commit_pack,
    language_learning_prepare_pack,
    language_learning_review_pack_subject_sheet,
    language_learning_start_compose_pack_cards,
    language_learning_validate_pack_subject_sheet,
    language_learning_validate_pack_words,
)

PACK_TOOLS = (
    language_learning_prepare_pack,
    language_learning_validate_pack_words,
    language_learning_validate_pack_subject_sheet,
    language_learning_review_pack_subject_sheet,
    language_learning_commit_pack,
    language_learning_claim_pack,
    language_learning_start_compose_pack_cards,
)
