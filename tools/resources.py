"""从已安装的业务包定位只读资源。"""

from importlib.metadata import distribution
from pathlib import Path


def package_resource_path(*parts: str) -> Path:
    return Path(distribution("media-factory").locate_file(Path(*parts)))
