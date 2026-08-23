"""抖音研究工具错误。"""


class DouyinResearchError(Exception):
    code = "DOUYIN_RESEARCH_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class ConfigurationError(DouyinResearchError):
    code = "DOUYIN_RESEARCH_CONFIGURATION_ERROR"


class SearchError(DouyinResearchError):
    code = "DOUYIN_RESEARCH_SEARCH_ERROR"


class ContextError(DouyinResearchError):
    code = "DOUYIN_RESEARCH_CONTEXT_ERROR"


class ConfirmationRequiredError(DouyinResearchError):
    code = "DOUYIN_RESEARCH_CONFIRMATION_REQUIRED"
