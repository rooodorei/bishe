"""ComfyUI 绘图调用模块。

正式绘图流程：
1. 根据用户输入构建角色卡，并保存为 JSON 方便复查。
2. 使用角色卡、动作提示词、场景提示词和 `workflows/zimage/story_page.json` 生成绘本页。

当前绘本页工作流没有使用定妆照作为图像输入，角色一致性主要依赖角色卡提示词重复注入，
因此正式接口不再生成 `character_base.json` 对应的角色定妆照。
"""

import json
import random
import time
from datetime import datetime
from pathlib import Path

import requests

from .character_card import build_character_card, build_story_page_prompt, save_character_card
from .config import CHARACTER_CARD_OUTPUT_DIR, COMFYUI_SERVER_ADDRESS, TEMP_OUTPUT_DIR, ZIMAGE_WORKFLOW_DIR


def log(step, message):
    """输出带时间戳的绘图日志。"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {step} | {message}")


def load_workflow(filename):
    """从 `workflows/zimage` 目录加载 ComfyUI 工作流 JSON。

    Args:
        filename: 工作流文件名，例如 `character_base.json` 或 `story_page.json`。
    """
    with (ZIMAGE_WORKFLOW_DIR / filename).open("r", encoding="utf-8") as f:
        return json.load(f)


def run_comfyui_task(workflow_json, output_name, task_name="未知任务", preferred_node_id=None):
    """提交 ComfyUI 任务，轮询执行结果并下载生成图片。

    Args:
        workflow_json: 已经注入提示词和随机种子的 ComfyUI 工作流字典。
        output_name: 图片下载到本地后的保存路径。
        task_name: 日志中显示的任务名称。
        preferred_node_id: 优先下载的输出节点 ID。用于避免下载到 PreviewImage 节点。

    Returns:
        str | None: 成功时返回本地图片路径；提交失败时返回 None。
    """
    try:
        # /prompt 会把工作流加入 ComfyUI 队列，返回 prompt_id 用于查询执行状态。
        res = requests.post(f"{COMFYUI_SERVER_ADDRESS}/prompt", json={"prompt": workflow_json}, timeout=20)
        res.raise_for_status()
        prompt_id = res.json()["prompt_id"]
    except Exception as e:
        log("❌ 错误", f"提交【{task_name}】失败，ComfyUI 没开吗？报错: {e}")
        return None

    output_path = Path(output_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            # /history/{prompt_id} 在任务完成后会包含各节点输出。
            history = requests.get(f"{COMFYUI_SERVER_ADDRESS}/history/{prompt_id}", timeout=20).json()
            if prompt_id in history:
                outputs = history[prompt_id]["outputs"]
                node_ids = list(outputs.keys())

                # 优先检查指定保存节点，例如角色定妆照节点 11、绘本页节点 14。
                if preferred_node_id and preferred_node_id in outputs:
                    node_ids = [preferred_node_id] + [node_id for node_id in node_ids if node_id != preferred_node_id]

                for node_id in node_ids:
                    if "images" in outputs[node_id]:
                        img_info = outputs[node_id]["images"][0]
                        img_url = f"{COMFYUI_SERVER_ADDRESS}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                        img_res = requests.get(img_url, timeout=60)
                        img_res.raise_for_status()
                        output_path.write_bytes(img_res.content)
                        return str(output_path)

            # 任务未完成时等待一秒再查，避免频繁请求 ComfyUI。
            time.sleep(1)
        except Exception:
            # 轮询过程中偶发网络错误时继续等待，而不是立即中断整次绘图。
            time.sleep(1)


def generate_full_story_page(session_id, child_features, story_action, story_scene):
    """生成一个剧情节点对应的最终绘本页图片。

    Args:
        session_id: 当前绘本会话 ID。
        child_features: 用户最初输入的主角特征。
        story_action: LLM 输出的中文动作提示词。
        story_scene: LLM 输出的中文场景提示词。

    Returns:
        str | None: 成功时返回临时绘本页图片路径，失败返回 None。
    """
    # 角色卡把用户输入整理成稳定的角色设定；后续每一页都复用这些固定字段。
    card = build_character_card(child_features)
    save_character_card(card, CHARACTER_CARD_OUTPUT_DIR / f"character_card_{session_id}.json")

    # 把角色卡和本页剧情动作/场景合成最终绘图提示词。
    positive, _negative = build_story_page_prompt(card, story_action, story_scene)

    wf2 = load_workflow("story_page.json")

    # 节点 4 是绘本页工作流里的正向提示词节点。
    wf2["4"]["inputs"]["text"] = positive
    seed = random.randint(1, 999_999_999_999_999)
    wf2["7"]["inputs"]["noise_seed"] = seed
    wf2["9"]["inputs"]["noise_seed"] = seed + 1
    print(f"🔍 [Stage 2 Prompt]: {wf2['4']['inputs']['text']}")

    # 先下载到 temp 目录，随后 main.py 会移动成 outputs/images/node_{page_id}.png。
    final_page_path = TEMP_OUTPUT_DIR / "final_storybook_page.png"
    return run_comfyui_task(wf2, final_page_path, "最终绘本图", preferred_node_id="14")
