"""Cloudflare R2 对象存储错误。"""


class R2StorageError(Exception):
    code = "R2_STORAGE_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(R2StorageError):
    code = "INVALID_PARAMETER"


class CredentialError(R2StorageError):
    code = "R2_CREDENTIAL_ERROR"


class UploadError(R2StorageError):
    code = "R2_UPLOAD_FAILED"
