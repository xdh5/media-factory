"""心灵鸡汤时间轴工具错误。"""


class QuizTimelineError(Exception):
    """时间轴生成基础错误。"""


class QuizTimelineInputError(QuizTimelineError):
    """时间轴输入不符合合同。"""
