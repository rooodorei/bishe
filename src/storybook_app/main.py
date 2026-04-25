"""FastAPI 后端入口。

这个模块是整个后端的调度中心，主要负责把前端请求转换成具体业务流程：

1. 文本生成接口：调用 `llm_engine.py` 生成旁白、台词、动作提示词、场景提示词和选项。
2. 数据持久化：调用 `database.py` 保存绘本会话、剧情节点、图片 URL 和分支关系。
3. 图片生成接口：调用 `image_engine.py` 使用 ComfyUI 生成绘本页。
4. 静态资源：挂载前端页面和生成图片目录，让浏览器可以直接访问。

运行方式示例：
`uv run uvicorn storybook_app.main:app --app-dir src --reload --port 8000`
"""

import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import FRONTEND_DIR, IMAGE_OUTPUT_DIR
from .database import (
    add_page_node,
    create_storybook,
    get_all_nodes,
    get_page,
    get_storybook_info,
    init_db,
    rebuild_llm_context,
    update_page_image,
)
from .image_engine import generate_full_story_page
from .llm_engine import generate_script_turn


# FastAPI 应用对象。`storybook_app.main:app` 中的 app 就是这个变量。
app = FastAPI(title="儿童绘本生成系统 - 命运之树版")

# 模块加载时初始化数据库表。`CREATE TABLE IF NOT EXISTS` 不会覆盖已有数据。
init_db()


class InitRequest(BaseModel):
    """创建新绘本的请求体。

    Attributes:
        child_features: 用户输入的主角特征，例如“白色短发，红色斗篷的小女孩”。
        theme: 故事主题，例如“魔法森林探险”。
    """

    child_features: str
    theme: str


class NextTurnRequest(BaseModel):
    """生成下一幕剧情的请求体。

    Attributes:
        session_id: 当前绘本会话 ID。
        parent_page_id: 用户当前所在的剧情节点 ID，新节点会挂在它下面。
        user_choice: 用户选择的选项文本，也会作为 LLM 生成下一幕的输入。
    """

    session_id: str
    parent_page_id: int
    user_choice: str


class RenderRequest(BaseModel):
    """渲染图片的请求体。

    Attributes:
        page_id: 需要生成图片的剧情节点 ID。
    """

    page_id: int


@app.post("/api/init_story_text")
async def init_story_text(req: InitRequest):
    """创建新绘本并生成根节点剧情。

    该接口只生成文本，不生成图片。前端拿到 `page_id` 后，如果需要显示图片，
    会再调用 `/api/render_image`。
    """
    # 每本绘本使用一个 UUID 作为会话 ID，后续所有剧情节点都通过它归属到同一本书。
    session_id = str(uuid.uuid4())

    # 开局上下文会作为第一轮 LLM 的前情提要，帮助模型围绕主题开始故事。
    opening_context = f"全局设定：故事主题是【{req.theme}】。主角准备好冒险了。"

    # 生成第一幕剧情。第三个参数固定为“开始冒险”，代表根节点的用户选择。
    turn_data = generate_script_turn(req.child_features, opening_context, "开始冒险")
    if not turn_data:
        raise HTTPException(status_code=500, detail="剧本生成失败")

    # 先保存绘本会话，再保存根节点。根节点 parent_id=0，depth=0。
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
    # 从父节点一路回溯到根节点，恢复当前分支的剧情记忆和主角特征。
    features, memory_list, current_path = rebuild_llm_context(req.parent_page_id)
    if not features:
        raise HTTPException(status_code=404, detail="找不到时间线")

    # 将上下文列表拼成字符串，让 LLM 知道当前故事走到了哪里。
    turn_data = generate_script_turn(features, "\n".join(memory_list), req.user_choice)
    if not turn_data:
        raise HTTPException(status_code=500, detail="剧本生成失败")

    # 新节点深度等于父节点深度 + 1。current_path 最后一个节点就是当前父节点。
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
    # 先查页面节点，因为页面里保存了 action_prompt 和 scene_prompt。
    page = get_page(req.page_id)
    if not page:
        raise HTTPException(status_code=404, detail="找不到节点")

    # 再查绘本信息，因为绘本表里保存了原始主角特征 features。
    book = get_storybook_info(page["session_id"])

    # 图片生成需要三类信息：主角特征、当前动作、当前场景。
    img_path = generate_full_story_page(
        page["session_id"],
        book["features"],
        page["action_prompt"],
        page["scene_prompt"],
    )
    if not img_path:
        raise HTTPException(status_code=500, detail="图片生成失败")

    # ComfyUI 生成的临时图会被移动成稳定的节点图片文件名，方便前端缓存和数据库记录。
    final_img_name = f"node_{req.page_id}.png"
    final_img_path = IMAGE_OUTPUT_DIR / final_img_name

    # 重复渲染同一节点时覆盖旧图。
    if final_img_path.exists():
        final_img_path.unlink()
    os.replace(img_path, final_img_path)

    # `/images` 在本文件底部挂载到 IMAGE_OUTPUT_DIR，因此这个 URL 可被前端直接访问。
    image_url = f"/images/{final_img_name}"
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


# 图片必须先挂载到 `/images`，否则会被下面的 `/` 静态页面挂载拦截。
app.mount("/images", StaticFiles(directory=IMAGE_OUTPUT_DIR), name="images")

# 前端单页 HTML 挂载在根路径，访问 http://127.0.0.1:8000/ 即可打开页面。
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
