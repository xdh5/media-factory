"""语言学习 MCP 共用查询与配置编排。"""

from .api import (
    language_learning_get_automation_plan,
    language_learning_get_production_config,
    language_learning_get_production_outputs,
    language_learning_get_publish_schedule,
    language_learning_get_topic_generation_prompt,
    language_learning_get_topics,
    language_learning_validate_topic_response,
)

COMMON_TOOLS = (
    language_learning_get_production_config,
    language_learning_get_automation_plan,
    language_learning_get_publish_schedule,
    language_learning_get_topic_generation_prompt,
    language_learning_validate_topic_response,
    language_learning_get_production_outputs,
    language_learning_get_topics,
)
