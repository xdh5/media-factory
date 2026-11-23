"""按标点和中文词边界划分单行字幕，保持原台词时间范围。"""

import math
import re
import unicodedata

import jieba


def _clean_edges(text: str) -> str:
    while text and (text[0].isspace() or unicodedata.category(text[0]).startswith('P')):
        text = text[1:]
    while text and (text[-1].isspace() or unicodedata.category(text[-1]).startswith('P')):
        text = text[:-1]
    return text


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    pairs = {'“': '”', '‘': '’', '「': '」', '『': '』', '（': '）', '(': ')', '《': '》', '【': '】', '"': '"'}
    protected = {index for match in re.finditer(r'https?://\S+|[A-Za-z0-9]+(?:[.:/@_-][A-Za-z0-9]+)+', text) for index in range(match.start(), match.end())}
    stack = []
    spans = []
    start = 0
    for index, char in enumerate(text):
        if stack and char == stack[-1]:
            stack.pop()
        elif char in pairs and pairs[char] in text[index + 1:]:
            stack.append(pairs[char])
        elif not stack and index not in protected and unicodedata.category(char).startswith('P') and char not in '；;':
            spans.append((start, index))
            start = index + 1
    spans.append((start, len(text)))
    return spans


def paginate_subtitle(text: str, start: float, end: float) -> list[dict]:
    """优先标点断句，长句按分词边界均衡拆分，每屏最多二十字符。"""
    text = text.replace('【', '').replace('】', '')
    pages = []
    for left, right in _sentence_spans(text):
        value = text[left:right]
        boundaries = {0, len(value)}
        offset = 0
        for token in jieba.cut(value, HMM=False):
            offset += len(token)
            boundaries.add(offset)
        cursor = 0
        while cursor < len(value):
            remaining = len(value) - cursor
            if remaining <= 20:
                cut = len(value)
            else:
                target = remaining / math.ceil(remaining / 20)
                candidates = [point for point in boundaries if cursor < point <= cursor + 20 and _clean_edges(value[cursor:point])]
                cut = min(candidates, key=lambda point: abs(point - cursor - target)) if candidates else cursor + 20
            displayed = _clean_edges(value[cursor:cut])
            if displayed:
                pages.append({'text': displayed, 'start': start + (end - start) * (left + cursor) / len(text),
                              'end': start + (end - start) * (left + cut) / len(text)})
            cursor = cut
    return pages
