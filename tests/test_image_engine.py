"""ComfyUI 绘图测试脚本。

该脚本不会被正式 API 调用，主要用于单独验证角色卡和 Z-Image 工作流。
"""

import json
import random
import time
from datetime import datetime
from pathlib import Path

import requests

from storybook_app.character_card import build_character_card, build_story_page_prompt, save_character_card
from storybook_app.config import COMFYUI_SERVER_ADDRESS, PROJECT_ROOT


TEST_ASSET_DIR = PROJECT_ROOT / "outputs" / "test_assets"
WORKFLOW_DIR = PROJECT_ROOT / "workflows" / "zimage"
TEST_ASSET_DIR.mkdir(parents=True, exist_ok=True)

TEST_CHILD_FEATURES = "白色短发，红色斗篷的小女孩，戴星星发卡，浅黄色连衣裙，棕色小靴子"
TEST_STORY_PAGES = [
    {
        "page_id": 1,
        "user_choice": "开始冒险",
        "narrator_text": "星星小红帽在清晨的花园里发现了一条会发光的小路，她决定轻轻挥手，向小路尽头走去。",
        "actor_dialogue": "我看见星星在给我带路！",
        "story_action": "开心地向前走，一只手轻轻挥动，脸上带着好奇微笑",
        "story_scene": "清晨的花园小路，柔和阳光，发光小花，温暖明亮，儿童绘本插画",
    },
    {
        "page_id": 2,
        "user_choice": "追逐发光蝴蝶",
        "narrator_text": "一只蓝色的小蝴蝶从花丛中飞起，星星小红帽笑着跑起来，斗篷在身后轻轻飘动。",
        "actor_dialogue": "等等我，小蝴蝶！",
        "story_action": "开心地小跑，双臂微微张开，追逐一只发光的蓝色小蝴蝶",
        "story_scene": "阳光明媚的花草地，柔软花朵，蓝色发光蝴蝶，欢快的儿童绘本氛围",
    },
]


def log(step: str, message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {step} | {message}")


def _load_workflow(filename: str) -> dict:
    with (WORKFLOW_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


def run_comfyui_task(
    workflow_json: dict,
    output_name: str | Path,
    task_name: str = "TEST任务",
    preferred_node_id: str | None = None,
) -> str | None:
    try:
        res = requests.post(f"{COMFYUI_SERVER_ADDRESS}/prompt", json={"prompt": workflow_json}, timeout=20)
        res.raise_for_status()
        prompt_id = res.json()["prompt_id"]
    except Exception as exc:
        log("错误", f"提交【{task_name}】失败，ComfyUI 没开吗？报错：{exc}")
        return None

    output_path = Path(output_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            history = requests.get(f"{COMFYUI_SERVER_ADDRESS}/history/{prompt_id}", timeout=20).json()
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                node_ids = list(outputs.keys())
                if preferred_node_id and preferred_node_id in outputs:
                    node_ids = [preferred_node_id] + [node_id for node_id in node_ids if node_id != preferred_node_id]

                for node_id in node_ids:
                    node_output = outputs[node_id]
                    if "images" not in node_output:
                        continue
                    image_info = node_output["images"][0]
                    image_url = (
                        f"{COMFYUI_SERVER_ADDRESS}/view?filename={image_info['filename']}"
                        f"&subfolder={image_info['subfolder']}&type={image_info['type']}"
                    )
                    img_res = requests.get(image_url, timeout=60)
                    img_res.raise_for_status()
                    output_path.write_bytes(img_res.content)
                    log("TEST输出", f"已下载节点 {node_id} 的图片：{output_path}")
                    return str(output_path)
            time.sleep(0.5)
        except Exception:
            time.sleep(0.5)


def create_test_character_assets(session_id: str, child_features: str) -> dict:
    card = build_character_card(child_features)
    card_path = TEST_ASSET_DIR / f"character_card_{session_id}.json"
    base_image_path = TEST_ASSET_DIR / f"character_base_{session_id}.png"

    save_character_card(card, card_path)

    if base_image_path.exists():
        log("TEST阶段1", f"绘本[{session_id}]已有角色定妆照，跳过阶段1：{base_image_path}")
    else:
        log("TEST阶段1", f"绘本[{session_id}]是新任务，正在生成角色定妆照...")
        workflow = _load_workflow("character_base.json")
        workflow["4"]["inputs"]["text"] = card.positive_prompt
        seed = random.randint(1, 999_999_999_999_999)
        workflow["7"]["inputs"]["noise_seed"] = seed
        workflow["9"]["inputs"]["noise_seed"] = seed + 1
        log("TEST阶段1 Prompt", card.positive_prompt)
        result = run_comfyui_task(workflow, base_image_path, "TEST阶段1:角色定妆照", preferred_node_id="11")
        if not result:
            raise RuntimeError("TEST角色定妆照生成失败")

    return {
        "card_path": str(card_path),
        "base_image_path": str(base_image_path),
        "character_card": card,
    }


def generate_test_full_story_page(
    session_id: str,
    child_features: str,
    story_action: str,
    story_scene: str,
    page_id: int = 1,
) -> str:
    assets = create_test_character_assets(session_id, child_features)
    card = assets["character_card"]

    positive, _negative = build_story_page_prompt(card, story_action, story_scene)
    positive = (
        f"{positive}，角色必须严格延续已生成角色定妆照中的设定，画面中只能有这一个主角，"
        "服装设计不能变化，不能换衣服，不能增加帽子或新配饰，儿童绘本页面插画"
    )
    workflow = _load_workflow("story_page.json")
    workflow["4"]["inputs"]["text"] = positive
    seed = random.randint(1, 999_999_999_999_999)
    workflow["7"]["inputs"]["noise_seed"] = seed
    workflow["9"]["inputs"]["noise_seed"] = seed + 1

    output_path = TEST_ASSET_DIR / f"storybook_page_{session_id}_{page_id}.png"
    log("TEST阶段2 Prompt", positive)
    result = run_comfyui_task(workflow, output_path, "TEST阶段2:最终绘本图", preferred_node_id="14")
    if not result:
        raise RuntimeError("TEST最终绘本图生成失败")
    return result


def generate_test_storybook_content(session_id: str = "demo", child_features: str = TEST_CHILD_FEATURES) -> list[dict]:
    results = []
    for page in TEST_STORY_PAGES:
        log("TEST绘本节点", f"第 {page['page_id']} 页 | 选择：{page['user_choice']}")
        image_path = generate_test_full_story_page(
            session_id=session_id,
            child_features=child_features,
            story_action=page["story_action"],
            story_scene=page["story_scene"],
            page_id=page["page_id"],
        )
        results.append({**page, "image_path": image_path})
    return results


if __name__ == "__main__":
    pages = generate_test_storybook_content()
    print(json.dumps(pages, ensure_ascii=False, indent=2))
