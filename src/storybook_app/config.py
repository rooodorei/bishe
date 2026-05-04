"""项目运行配置模块。

本模块集中管理三类配置：
1. 项目目录：用于让后端在任何工作目录下都能稳定找到前端、工作流、数据库和输出目录。
2. 大模型配置：用于 `llm_engine.py` 调用 OpenAI 兼容接口。
3. ComfyUI 配置：用于 `image_engine.py` 提交绘图任务和下载图片。

设计原则：
- 路径统一由这里计算，其他模块不要手写相对路径，避免重构后路径混乱。
- 敏感配置优先从环境变量读取，代码里的默认值只用于本地开发。
- 运行时目录在导入配置模块时自动创建，避免后续写文件时报目录不存在。
"""

import os
from pathlib import Path


# ================= 项目路径配置 =================
# 当前文件路径：项目根目录/src/storybook_app/config.py
# parents[0] = src/storybook_app
# parents[1] = src
# parents[2] = 项目根目录 bishe
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Python 源码目录，运行命令中 `--app-dir src` 指向这里。
SRC_DIR = PROJECT_ROOT / "src"

# 前端静态页面目录，`main.py` 会把它挂载到 `/`。
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# ComfyUI 工作流根目录。
WORKFLOW_DIR = PROJECT_ROOT / "workflows"

# 当前正式使用的 Z-Image 工作流目录。
ZIMAGE_WORKFLOW_DIR = WORKFLOW_DIR / "zimage"

# 旧三阶段工作流目录，保留用于对照或回退，不参与正式流程。
LEGACY_WORKFLOW_DIR = WORKFLOW_DIR / "legacy"

# SQLite 数据库目录。
DATA_DIR = PROJECT_ROOT / "data"

# 所有运行产物统一放在 outputs 下，避免污染源码目录。
OUTPUT_DIR = PROJECT_ROOT / "outputs"

# 最终提供给前端访问的图片目录，对应 URL 前缀 `/images`。
IMAGE_OUTPUT_DIR = OUTPUT_DIR / "images"

# 每个绘本会话的角色卡 JSON 目录。
CHARACTER_CARD_OUTPUT_DIR = OUTPUT_DIR / "character_cards"

# 临时图片目录，例如 ComfyUI 刚生成、尚未移动到最终 images 目录的文件。
TEMP_OUTPUT_DIR = OUTPUT_DIR / "temp"

# 这些目录都是运行时必需目录。这里统一创建，其他模块可以直接写文件。
for directory in (DATA_DIR, IMAGE_OUTPUT_DIR, CHARACTER_CARD_OUTPUT_DIR, TEMP_OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# ================= LLM 大模型配置 =================
# 大模型 API Key。生产环境建议在系统环境变量中配置 LLM_API_KEY。
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-f05a2b91afc74603b56ce862208422fe")

# OpenAI 兼容接口地址。DeepSeek、OpenAI 兼容网关都可以使用该字段。
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")

# 具体模型名称。这里从环境变量读取，方便在不改代码的情况下切换模型。
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-flash")


# ================= ComfyUI 配置 =================
# ComfyUI HTTP 服务地址，`image_engine.py` 会访问 /prompt、/history、/view。
COMFYUI_SERVER_ADDRESS = os.getenv("COMFYUI_SERVER_ADDRESS", "http://127.0.0.1:8188")

# ComfyUI 输入目录。当前 Z-Image 正式流程不依赖复制输入图，但测试或旧流程可能会使用。
COMFYUI_INPUT_DIR = os.getenv("COMFYUI_INPUT_DIR", r"C:/Cworkspace/MI10-Preview/ComfyUI/input")
