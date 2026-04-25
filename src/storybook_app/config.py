"""项目运行配置。

这里集中保存大模型、ComfyUI、项目目录和运行产物目录。生产环境建议把密钥放到
环境变量 `LLM_API_KEY` 中，避免把真实 API Key 写入代码仓库。
"""

import os
from pathlib import Path


# ================= 项目路径配置 =================
# 当前文件位于 `src/storybook_app/config.py`，向上两级是项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
WORKFLOW_DIR = PROJECT_ROOT / "workflows"
ZIMAGE_WORKFLOW_DIR = WORKFLOW_DIR / "zimage"
LEGACY_WORKFLOW_DIR = WORKFLOW_DIR / "legacy"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
IMAGE_OUTPUT_DIR = OUTPUT_DIR / "images"
BASE_IMAGE_OUTPUT_DIR = OUTPUT_DIR / "base_images"
CHARACTER_CARD_OUTPUT_DIR = OUTPUT_DIR / "character_cards"
TEMP_OUTPUT_DIR = OUTPUT_DIR / "temp"

for directory in (DATA_DIR, IMAGE_OUTPUT_DIR, BASE_IMAGE_OUTPUT_DIR, CHARACTER_CARD_OUTPUT_DIR, TEMP_OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# ================= LLM 大模型配置 =================
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-f05a2b91afc74603b56ce862208422fe")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-pro")


# ================= ComfyUI 配置 =================
COMFYUI_SERVER_ADDRESS = os.getenv("COMFYUI_SERVER_ADDRESS", "http://127.0.0.1:8188")
COMFYUI_INPUT_DIR = os.getenv("COMFYUI_INPUT_DIR", r"C:/Cworkspace/MI10-Preview/ComfyUI/input")
