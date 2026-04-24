# image_engine.py
import json
import random
import requests
import time
import os
from datetime import datetime
from pathlib import Path
from config import COMFYUI_SERVER_ADDRESS
from TEST_character_card import build_character_card, build_story_page_prompt

ROOT_DIR = Path(__file__).resolve().parent


def log(step, message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {step} | {message}")


def load_workflow(filename):
    with (ROOT_DIR / filename).open("r", encoding="utf-8") as f:
        return json.load(f)


def run_comfyui_task(workflow_json, output_name, task_name="未知任务", preferred_node_id=None):
    try:
        res = requests.post(f"{COMFYUI_SERVER_ADDRESS}/prompt", json={"prompt": workflow_json}, timeout=20)
        res.raise_for_status()
        prompt_id = res.json()['prompt_id']
    except Exception as e:
        log("❌ 错误", f"提交【{task_name}】失败，ComfyUI 没开吗？报错: {e}")
        return None

    output_path = Path(output_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    while True:
        try:
            history = requests.get(f"{COMFYUI_SERVER_ADDRESS}/history/{prompt_id}", timeout=20).json()
            if prompt_id in history:
                outputs = history[prompt_id]['outputs']
                node_ids = list(outputs.keys())
                if preferred_node_id and preferred_node_id in outputs:
                    node_ids = [preferred_node_id] + [node_id for node_id in node_ids if node_id != preferred_node_id]

                for node_id in node_ids:
                    if 'images' in outputs[node_id]:
                        img_info = outputs[node_id]['images'][0]
                        img_url = f"{COMFYUI_SERVER_ADDRESS}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                        img_res = requests.get(img_url, timeout=60)
                        img_res.raise_for_status()
                        output_path.write_bytes(img_res.content)
                        return str(output_path)
            time.sleep(1)
        except Exception:
            time.sleep(1)


def generate_full_story_page(session_id, child_features, story_action, story_scene):
    card = build_character_card(child_features)
    base_image_name = f"base_{session_id}.png"
    if not os.path.exists(base_image_name):
        print(f">>> 绘本[{session_id}]是新任务，正在生成专属定妆照...")
        wf1 = load_workflow("TEST_workflow_character_base.json")
        wf1["4"]["inputs"]["text"] = card.positive_prompt
        seed = random.randint(1, 999_999_999_999_999)
        wf1["7"]["inputs"]["noise_seed"] = seed
        wf1["9"]["inputs"]["noise_seed"] = seed + 1
        print(f"🔍 [Stage 1 Prompt]: {wf1['4']['inputs']['text']}")
        result = run_comfyui_task(wf1, base_image_name, "阶段1:定妆照", preferred_node_id="11")
        if not result:
            return None
    else:
        print(f">>> 绘本[{session_id}]已有定妆照，直接跳过阶段 1。")

    positive, _negative = build_story_page_prompt(card, story_action, story_scene)
    positive = (
        f"{positive}，角色必须严格延续已生成角色定妆照中的设定，画面中只能有这一个主角，"
        "每一页都必须是同一套服装，same face, same hairstyle, same outfit, "
        "服装设计不能变化，服装颜色不能变化，不能换衣服，不能增加帽子或新配饰，"
        "允许根据剧情自然改变姿态和表情，只有一个主角，儿童绘本页面插画"
    )

    wf2 = load_workflow("TEST_workflow_story_page.json")
    wf2["4"]["inputs"]["text"] = positive
    seed = random.randint(1, 999_999_999_999_999)
    wf2["7"]["inputs"]["noise_seed"] = seed
    wf2["9"]["inputs"]["noise_seed"] = seed + 1
    print(f"🔍 [Stage 2 Prompt]: {wf2['4']['inputs']['text']}")
    
    return run_comfyui_task(wf2, "final_storybook_page.png", "阶段2:最终绘本图", preferred_node_id="14")
