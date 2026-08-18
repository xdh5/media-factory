"""TTS 常量配置。"""

# 各语言倍速：中文 1.2 倍，英文 1.1 倍，韩语原速
TTS_RATES = {
    "zh": "+20%",
    "en": "+10%",
    "ko": "+0%",
}

# Edge TTS 网络与重试策略。降低并发可减少批量台词触发服务端限流或空音频。
TTS_CONCURRENCY = 3
TTS_CONNECT_TIMEOUT_SECONDS = 15
TTS_RECEIVE_TIMEOUT_SECONDS = 60
TTS_MAX_ATTEMPTS = 5
TTS_RETRY_BASE_SECONDS = 1.0
TTS_RETRY_MAX_SECONDS = 8.0
TTS_RETRY_JITTER_SECONDS = 0.25

# 文生图时间轴参数：与 ai-video-maker 的中文旁白保持相同语义
TTS_SAMPLE_RATE = 24_000
TTS_CHANNELS = 1
TTS_SENTENCE_GAP_SECONDS = 0.4
TTS_ENDING_PADDING_SECONDS = 0.5
TTS_EXPECTED_LEADING_SILENCE_SECONDS = 0.16
TTS_BETWEEN_SENTENCE_TRAILING_SECONDS = (
    TTS_SENTENCE_GAP_SECONDS - TTS_EXPECTED_LEADING_SILENCE_SECONDS
)
TTS_SILENCE_THRESHOLD_DB = -45.0
TTS_SILENCE_DETECTION_SECONDS = 0.02
TTS_SILENCE_KEEP_COMPENSATION_SECONDS = 0.028

# 配音响度标准化；时长必须与标准化前一致
TTS_LOUDNESS_CACHE_VERSION = 1
TTS_TARGET_LUFS = -14.0
TTS_TRUE_PEAK_DB = -1.5
TTS_LRA = 7.0


# 音色库
TTS_VOICES = [
    {"id": "zh-CN-XiaoxiaoNeural", "language": "zh-CN", "gender": "female", "name": "Xiaoxiao"},
    {"id": "zh-CN-YunxiNeural", "language": "zh-CN", "gender": "male", "name": "Yunxi"},
    {"id": "zh-CN-YunjianNeural", "language": "zh-CN", "gender": "male", "name": "Yunjian"},
    {"id": "zh-CN-XiaoyiNeural", "language": "zh-CN", "gender": "female", "name": "Xiaoyi"},
    {"id": "en-US-AriaNeural", "language": "en-US", "gender": "female", "name": "Aria"},
    {"id": "en-US-GuyNeural", "language": "en-US", "gender": "male", "name": "Guy"},
    {"id": "en-US-JennyNeural", "language": "en-US", "gender": "female", "name": "Jenny"},
    {"id": "en-US-AndrewNeural", "language": "en-US", "gender": "male", "name": "Andrew"},
    {"id": "ko-KR-SunHiNeural", "language": "ko-KR", "gender": "female", "name": "SunHi"},
    {"id": "ko-KR-InJoonNeural", "language": "ko-KR", "gender": "male", "name": "InJoon"},
    {"id": "ko-KR-JiMinNeural", "language": "ko-KR", "gender": "female", "name": "JiMin"},
]
