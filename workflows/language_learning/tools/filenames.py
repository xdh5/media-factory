"""把标题转成可用的文件名，只替换系统非法字符。"""

INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def safe_filename(title: str) -> str:
    """文件名必须等于标题，仅去掉 Windows 非法字符。"""
    name = "".join("_" if char in INVALID_FILENAME_CHARS else char for char in str(title or "").strip())
    name = name.rstrip(" .")
    if not name:
        raise ValueError("标题为空，无法生成文件名")
    return name
