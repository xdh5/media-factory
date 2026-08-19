"""语言学习 MCP 错误定义。"""


class LanguageLearningError(Exception):
    """语言学习 MCP 错误基类。"""

    code = "LANGUAGE_LEARNING_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidVocabularyError(LanguageLearningError):
    code = "INVALID_VOCABULARY"


class CardCompositionError(LanguageLearningError):
    code = "CARD_COMPOSITION_ERROR"


class VocabularyVideoError(LanguageLearningError):
    code = "VOCABULARY_VIDEO_ERROR"


class ConfirmationRequiredError(LanguageLearningError):
    code = "CONFIRMATION_REQUIRED"


class PublishError(LanguageLearningError):
    code = "PUBLISH_ERROR"
