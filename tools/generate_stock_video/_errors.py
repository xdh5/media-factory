"""正版视频素材工具错误。"""


class StockVideoError(Exception):
    code = "STOCK_VIDEO_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class StockVideoConfigurationError(StockVideoError):
    code = "STOCK_VIDEO_CONFIGURATION_ERROR"


class StockVideoRequestError(StockVideoError):
    code = "STOCK_VIDEO_REQUEST_ERROR"


class StockVideoDownloadError(StockVideoError):
    code = "STOCK_VIDEO_DOWNLOAD_ERROR"


class StockVideoRenderError(StockVideoError):
    code = "STOCK_VIDEO_RENDER_ERROR"
