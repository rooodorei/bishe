"""项目运行配置。

这里集中保存大模型和 ComfyUI 的连接参数。生产环境建议把密钥改为从环境变量读取，
避免把真实 API Key 写入代码仓库。
"""

# ================= LLM 大模型配置 =================
# OpenAI 兼容接口的 API Key。
LLM_API_KEY = "sk-f05a2b91afc74603b56ce862208422fe"

# OpenAI 兼容接口地址；当前配置为 DeepSeek。
LLM_BASE_URL = "https://api.deepseek.com"

# 具体调用的大模型名称。
LLM_MODEL_NAME = "deepseek-chat"

# ================= ComfyUI 配置 =================
# ComfyUI 后端服务地址。
COMFYUI_SERVER_ADDRESS = "http://127.0.0.1:8188"

# ComfyUI 输入目录；当前 Z-Image 正式流程主要保留该配置用于兼容旧流程或测试脚本。
COMFYUI_INPUT_DIR = r"C:/Cworkspace/MI10-Preview/ComfyUI/input"
