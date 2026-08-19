"""Facebook / Instagram Reels 发布错误。"""


class MetaToolError(Exception):
    code = "META_TOOL_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(MetaToolError):
    code = "INVALID_PARAMETER"


class CredentialError(MetaToolError):
    code = "META_CREDENTIAL_ERROR"


class UploadError(MetaToolError):
    code = "META_UPLOAD_FAILED"
