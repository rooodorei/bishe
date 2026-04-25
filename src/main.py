"""FastAPI 后端入口。

本模块负责：
1. 初始化数据库和图片目录。
2. 暴露绘本文本生成、图片渲染、时间线查询接口。
3. 在 API 层串联 LLM、数据库和 ComfyUI 绘图模块。
"""

import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import (
    add_page_node,
    create_storybook,
    get_all_nodes,
    get_page,
    get_storybook_info,
    init_db,
    rebuild_llm_context,
    update_page_image,
)
from image_engine import generate_full_story_page
from llm_engine import generate_script_turn


app = FastAPI(title="儿童绘本生成系统 - 命运之树版")
init_db()

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)


class InitRequest(BaseModel):
    """创建新绘本时前端提交的数据。"""

    child_features: str
    theme: str


class NextTurnRequest(BaseModel):
    """生成下一幕剧情时前端提交的数据。"""

    session_id: str
    parent_page_id: int
    user_choice: str


class RenderRequest(BaseModel):
    """渲染某个剧情节点图片时前端提交的数据。"""

    page_id: int


@app.post("/api/init_story_text")
async def init_story_text(req: InitRequest):
    """创建新绘本并生成根节点剧情。

    该接口只生成文本，不立即生成图片。图片会在前端调用
    `/api/render_image` 时再进入 ComfyUI 绘图流程。
    """
    session_id = str(uuid.uuid4())
    opening_context = f"全局设定：故事主题是【{req.theme}】。主角准备好冒险了。"

    turn_data = generate_script_turn(req.child_features, opening_context, "开始冒险")
    if not turn_data:
        raise HTTPException(status_code=500, detail="剧本生成失败")

    create_storybook(session_id, req.theme, req.child_features)
    page_id = add_page_node(
        session_id,
        0,
        0,
        "开始冒险",
        turn_data["narrator_text"],
        turn_data["actor_dialogue"],
        turn_data["story_action"],
        turn_data["story_scene"],
        turn_data["options"],
    )

    return {
        "session_id": session_id,
        "page_id": page_id,
        "narrator_text": turn_data["narrator_text"],
        "actor_dialogue": turn_data["actor_dialogue"],
        "options": turn_data["options"],
    }


@app.post("/api/next_turn_text")
async def next_turn_text(req: NextTurnRequest):
    """根据用户选择生成新的剧情分支节点。"""
    features, memory_list, current_path = rebuild_llm_context(req.parent_page_id)
    if not features:
        raise HTTPException(status_code=404, detail="找不到时间线")

    turn_data = generate_script_turn(features, "\n".join(memory_list), req.user_choice)
    if not turn_data:
        raise HTTPException(status_code=500, detail="剧本生成失败")

    depth = current_path[-1]["depth"] + 1 if current_path else 1
    page_id = add_page_node(
        req.session_id,
        req.parent_page_id,
        depth,
        req.user_choice,
        turn_data["narrator_text"],
        turn_data["actor_dialogue"],
        turn_data["story_action"],
        turn_data["story_scene"],
        turn_data["options"],
    )

    return {
        "page_id": page_id,
        "narrator_text": turn_data["narrator_text"],
        "actor_dialogue": turn_data["actor_dialogue"],
        "options": turn_data["options"],
    }


@app.post("/api/render_image")
async def render_image(req: RenderRequest):
    """为指定剧情节点生成图片并写回数据库。"""
    page = get_page(req.page_id)
    if not page:
        raise HTTPException(status_code=404, detail="找不到节点")

    book = get_storybook_info(page["session_id"])
    img_path = generate_full_story_page(
        page["session_id"],
        book["features"],
        page["action_prompt"],
        page["scene_prompt"],
    )
    if not img_path:
        raise HTTPException(status_code=500, detail="图片生成失败")

    final_img_name = f"node_{req.page_id}.png"
    final_img_path = os.path.join(IMAGE_DIR, final_img_name)

    if os.path.exists(final_img_path):
        os.remove(final_img_path)
    os.rename(img_path, final_img_path)

    image_url = f"/{IMAGE_DIR}/{final_img_name}"
    update_page_image(req.page_id, image_url)

    return {"image_url": image_url}


@app.get("/api/get_timeline/{session_id}")
async def get_timeline(session_id: str):
    """返回一个绘本会话的所有节点，用于前端绘制命运之树。"""
    book = get_storybook_info(session_id)
    nodes = get_all_nodes(session_id)
    if not book or not nodes:
        raise HTTPException(status_code=404, detail="无记录")
    return {"theme": book["theme"], "features": book["features"], "nodes": nodes}


app.mount("/", StaticFiles(directory=".", html=True), name="static")
