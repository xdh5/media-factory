"""成片和图片文件存储错误。"""


class MediaFilesError(Exception):
    code = "MEDIA_FILES_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(MediaFilesError):
    code = "INVALID_PARAMETER"


class CredentialError(MediaFilesError):
    code = "MEDIA_FILES_CREDENTIAL_ERROR"


class UploadError(MediaFilesError):
    code = "MEDIA_FILES_UPLOAD_FAILED"


class DownloadError(MediaFilesError):
    code = "MEDIA_FILES_DOWNLOAD_FAILED"
