"""发送前登记成片的全部目标平台和账号。"""

from .client import _request


def commit_publication_targets(records: list[dict]) -> dict:
    return _request("POST", "/v1/production-publication-targets", body={"records": records})
