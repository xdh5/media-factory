"""抖音研究工具错误。"""


class DouyinResearchError(Exception):
    code = "DOUYIN_RESEARCH_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class IngestError(DouyinResearchError):
    code = "DOUYIN_RESEARCH_INGEST_ERROR"
