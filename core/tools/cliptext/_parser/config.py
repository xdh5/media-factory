import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PARSER_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PARSER_ROOT.parents[4]
VIDEO_DIR = _PROJECT_ROOT / "data" / "cliptext" / "videos"
IMAGE_DIR = _PROJECT_ROOT / "data" / "cliptext" / "images"
STATIC_DIR = _PROJECT_ROOT / "data" / "cliptext"

DOMAIN = os.getenv("DOMAIN")


def load_business_json(json_path):
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"找不到平台配置：{json_path}")

    try:
        with open(json_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"平台配置不是有效 JSON：{json_path}\n{exc}") from exc


business_config = load_business_json(_PARSER_ROOT / "platforms.json")

static_dir = str(STATIC_DIR)
SAVE_VIDEO_PATH = str(VIDEO_DIR)
SAVE_IMAGE_PATH = str(IMAGE_DIR)

DOMAIN_TO_NAME = business_config["DOMAIN_TO_NAME"]
PLATFORM_MAP = business_config["PLATFORM_MAP"]
MINI_PROGRAM_LEGAL_DOMAIN = business_config["MINI_PROGRAM_LEGAL_DOMAIN"]
USER_AGENT_PC = business_config["USER_AGENT_PC"]
USER_AGENT_M = business_config["USER_AGENT_M"]


def check_essential_dirs():
    for dir_path in [SAVE_VIDEO_PATH, SAVE_IMAGE_PATH]:
        os.makedirs(dir_path, exist_ok=True)


check_essential_dirs()
