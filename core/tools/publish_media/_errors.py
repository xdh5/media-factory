"""统一视频发布异常。"""


class PublishMediaError(Exception):
    """统一视频发布错误。"""

    code = "PUBLISH_MEDIA_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class InvalidPublishRequestError(PublishMediaError):
    """发布请求缺少必要信息或格式错误。"""

    code = "INVALID_PUBLISH_REQUEST"


class PublishContentNotFoundError(PublishMediaError):
    """找不到与指定日期和业务线匹配的本地产物。"""

    code = "PUBLISH_CONTENT_NOT_FOUND"


class PublishAccountGroupError(PublishMediaError):
    """账号组不存在、缺少平台账号或登录态不可用。"""

    code = "PUBLISH_ACCOUNT_GROUP_ERROR"


class DuplicatePublicationError(PublishMediaError):
    """目标内容已经在相同账号和平台发布或预约。"""

    code = "DUPLICATE_PUBLICATION"


class MatrixMediaCommandError(PublishMediaError):
    """MatrixMedia CLI 不可用或返回失败。"""

    code = "MATRIXMEDIA_COMMAND_ERROR"
