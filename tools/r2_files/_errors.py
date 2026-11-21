"""R2 文件操作错误。"""


class R2FilesError(Exception):
    code = "R2_FILES_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(R2FilesError):
    code = "INVALID_PARAMETER"


class CredentialError(R2FilesError):
    code = "R2_FILES_CREDENTIAL_ERROR"


class UploadError(R2FilesError):
    code = "R2_FILES_UPLOAD_FAILED"


class DownloadError(R2FilesError):
    code = "R2_FILES_DOWNLOAD_FAILED"
