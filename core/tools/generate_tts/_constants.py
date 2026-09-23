"""生成配音常量配置。"""

# Edge TTS 默认原速；工作流如需加速由 generate_tts(rate=...) 传入，例如 "+20%"。
TTS_DEFAULT_RATE = "+0%"

# Edge TTS 网络与重试策略。降低并发可减少批量台词触发服务端限流或空音频。
TTS_CONCURRENCY = 3
TTS_CONNECT_TIMEOUT_SECONDS = 15
TTS_RECEIVE_TIMEOUT_SECONDS = 60
TTS_MAX_ATTEMPTS = 5
TTS_RETRY_BASE_SECONDS = 1.0
TTS_RETRY_MAX_SECONDS = 8.0
TTS_RETRY_JITTER_SECONDS = 0.25
# 全局请求节流：相邻两次合成请求的起始最小间隔（秒），防止批量台词触发限流。
# 注意：NoAudioReceived 更常见的原因是台词里出现纯标点行（如 lone "，"），
# 排查时先用 split_narration_lines 复现切句结果，再怀疑网络。
TTS_MIN_REQUEST_INTERVAL_SECONDS = 1.5

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


# Fish Audio TTS：与 edge-tts 完全独立的第二个 TTS 服务。
# API Key 从环境变量 FISH_AUDIO_API_KEY 读取；音色用 Voice Library 的 reference_id。
FISH_AUDIO_API_BASE = "https://api.fish.audio"
FISH_AUDIO_TTS_PATH = "/v1/tts"
FISH_AUDIO_MODEL = "s2.1-pro-free"  # 可用环境变量 FISH_AUDIO_MODEL 覆盖；付费 key 可改 "s2.1-pro"
FISH_AUDIO_FORMAT = "mp3"
FISH_AUDIO_MP3_BITRATE = 192
FISH_AUDIO_CHUNK_LENGTH = 200  # 100-300，默认 200
FISH_AUDIO_LATENCY = "normal"  # normal 比 balanced 稳定，适合批量旁白
FISH_AUDIO_NORMALIZE = True  # 展开数字/日期为自然朗读
# Fish Audio 语速走 prosody.speed（0.5-2.0），与 edge 的 "+20%" 写法互转见 _fish.rate_to_speed
FISH_AUDIO_CONCURRENCY = 2
FISH_AUDIO_MIN_REQUEST_INTERVAL_SECONDS = 0.8
FISH_AUDIO_CONNECT_TIMEOUT_SECONDS = 15
FISH_AUDIO_READ_TIMEOUT_SECONDS = 120
FISH_AUDIO_MAX_ATTEMPTS = 4
FISH_AUDIO_RETRY_BASE_SECONDS = 1.0
FISH_AUDIO_RETRY_MAX_SECONDS = 8.0
FISH_AUDIO_RETRY_JITTER_SECONDS = 0.25

# 音色绑定的语速：脚本行用到该 reference_id 时，**只要没在行内显式写 rate**，就用这里的值，
# 优先级高于调用方的 rate 参数（即"这个音色天然就是 +10%"）。
# 2026-09-23 用户要求：财经线（原心灵鸡汤）音色固定 +10%。
FISH_VOICE_RATES = {
    "28df7fe4d3ec45f692af03d0a372805b": "+10%",
}


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
