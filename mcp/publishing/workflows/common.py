"""发布工作流错误映射。"""

from __future__ import annotations


from ..infrastructure import (
    MediaRecordsError,
    PublishMediaError,
)

from ..errors import PublishingError, PublishingRequestError


def _map_error(exc: Exception) -> PublishingError:
    if isinstance(exc, PublishingError):
        return exc
    if isinstance(exc, PublishMediaError):
        return PublishingRequestError(str(exc), {"tool_code": exc.code, **exc.details})
    if isinstance(exc, MediaRecordsError):
        return PublishingRequestError(exc.message, exc.details)
    raise exc
