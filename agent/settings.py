"""Agent 配置，业务配置仍由各 MCP 提供。"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SERVERS = {name: f"core.mcp.{name}" for name in (
    "finance", "language_learning", "anime", "publishing"
)}


@dataclass
class AgentSettings:
    database: Path = ROOT / "data/agent/checkpoints.sqlite"
    max_steps: int = 60
    max_attempts: int = 3
    tool_timeout: float = 180
    run_timeout: float = 1800
    llm_timeout: float = 180
    max_llm_tokens: int = 100000

    def __post_init__(self):
        if min(self.max_steps, self.max_attempts, self.tool_timeout,
               self.run_timeout, self.llm_timeout, self.max_llm_tokens) <= 0:
            raise ValueError("执行次数和超时必须大于零")


def llm_configuration() -> dict:
    load_dotenv(ROOT / ".env")
    if os.getenv("AGENT_API_KEY"):
        return {
            "api_key": os.environ["AGENT_API_KEY"],
            "base_url": os.environ["AGENT_BASE_URL"].rstrip("/"),
            "model": os.environ["AGENT_MODEL"],
        }
    from core.tools.qwen_text.qwen_text import get_qwen_configuration
    return get_qwen_configuration()
