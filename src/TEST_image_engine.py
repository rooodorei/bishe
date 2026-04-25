# TEST_image_engine.py
import json
import random
import shutil
import time
from datetime import datetime
from pathlib import Path

import requests

from config import COMFYUI_INPUT_DIR, COMFYUI_SERVER_ADDRESS
from TEST_character_card import build_character_card, build_story_page_prompt, save_character_card

ROOT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = ROOT_DIR.parent
TEST_ASSET_DIR = PROJECT_DIR / "TEST_assets"
TEST_ASSET_DIR.mkdir(exist_ok=True)

TEST_CHILD_FEATURES = "白色短发，红色斗篷的小女孩，戴星星发卡，浅黄色连衣裙，棕色小靴子"
TEST_STORY_PAGES = [
    {
        "page_id": 1,
        "user_choice": "开始冒险",
        "narrator_text": "星星小红帽在清晨的花园里发现了一条会发光的小路，她决定轻轻挥手，向小路尽头走去。",
        "actor_dialogue": "我看见星星在给我带路！",
        "story_action": "walking forward happily and waving one hand",
        "story_scene": "a bright morning garden path with tiny glowing flowers, warm children's picture book atmosphere",
    },
    {
        "page_id": 2,
        "user_choice": "追逐发光蝴蝶",
        "narrator_text": "一只蓝色的小蝴蝶从花丛中飞起，星星小红帽笑着跑起来，斗篷在身后轻轻飘动。",
        "actor_dialogue": "等等我，小蝴蝶！",
        "story_action": "running happily with arms slightly open, chasing a glowing butterfly",
        "story_scene": "a sunny meadow full of soft flowers and one tiny glowing blue butterfly, cheerful children's book illustration",
    },
    {
        "page_id": 3,
        "user_choice": "帮助迷路的小兔子",
        "narrator_text": "在蘑菇屋旁边，她遇见了一只迷路的小兔子。她蹲下来，温柔地伸出手安慰它。",
        "actor_dialogue": "别害怕，我会陪你回家。",
        "story_action": "kneeling down gently and reaching one hand toward a small rabbit",
        "story_scene": "a cozy mushroom house beside a forest path, a small cute rabbit nearby, warm and safe children's storybook scene",
    },
]


def log(step: str, message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {step} | {message}")


def _load_workflow(filename: str) -> dict:
    with (ROOT_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


def _copy_to_comfy_input(local_path: str | Path, comfy_name: str) -> str:
    src = Path(local_path)
    if not src.exists():
        raise FileNotFoundError(f"找不到输入图片：{src}")
    dst = Path(COMFYUI_INPUT_DIR) / comfy_name
    shutil.copy(src, dst)
    return comfy_name


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
    card_path = TEST_ASSET_DIR / f"TEST_character_card_{session_id}.json"
    base_image_path = TEST_ASSET_DIR / f"TEST_character_base_{session_id}.png"

    save_character_card(card, card_path)

    if base_image_path.exists():
        log("TEST阶段1", f"绘本[{session_id}]已有角色定妆照，跳过阶段1：{base_image_path}")
    else:
        log("TEST阶段1", f"绘本[{session_id}]是新任务，正在生成角色定妆照...")
        workflow = _load_workflow("TEST_workflow_character_base.json")
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
    base_image_path = assets["base_image_path"]

    comfy_base_name = f"TEST_input_base_{session_id}.png"
    _copy_to_comfy_input(base_image_path, comfy_base_name)

    positive, _negative = build_story_page_prompt(card, story_action, story_scene)
    positive = (
        f"{positive}，角色必须严格延续已生成角色定妆照中的设定，画面中只能有这一个主角，"
        "主角身份：白色短发的小女孩，圆脸，大眼睛，儿童绘本风格，"
        "固定服装硬约束：红色斗篷、浅黄色连衣裙、棕色小靴子、星星发卡，"
        "每一页都必须是同一套服装，same face, same hairstyle, same red cloak, same pale yellow dress, same brown boots, same star hairpin, "
        "服装设计不能变化，斗篷颜色不能变化，裙子颜色不能变化，鞋子颜色不能变化，不能换衣服，不能增加帽子或新配饰，"
        "允许根据剧情自然改变姿态和表情，一个人，只有一个主角，儿童绘本页面插画"
    )
    workflow = _load_workflow("TEST_workflow_story_page.json")
    workflow["4"]["inputs"]["text"] = positive
    seed = random.randint(1, 999_999_999_999_999)
    workflow["7"]["inputs"]["noise_seed"] = seed
    workflow["9"]["inputs"]["noise_seed"] = seed + 1

    output_path = TEST_ASSET_DIR / f"TEST_final_storybook_page_{session_id}_{page_id}.png"
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
