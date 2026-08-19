"""公开对象存储错误。"""


class StorageError(Exception):
    code = "STORAGE_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(StorageError):
    code = "INVALID_PARAMETER"


class CredentialError(StorageError):
    code = "STORAGE_CREDENTIAL_ERROR"


class UploadError(StorageError):
    code = "STORAGE_UPLOAD_FAILED"
