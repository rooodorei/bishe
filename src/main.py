# main.py
import uuid
import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from llm_engine import generate_script_turn
from image_engine import generate_full_story_page
from database import (
    init_db, create_storybook, add_page_node, update_page_image, 
    get_page, get_storybook_info, get_all_nodes, rebuild_llm_context
)

app = FastAPI(title="儿童绘本生成系统 - 命运之树版")
init_db()

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

class InitRequest(BaseModel):
    child_features: str
    theme: str

class NextTurnRequest(BaseModel):
    session_id: str
    parent_page_id: int
    user_choice: str

class RenderRequest(BaseModel):
    page_id: int

@app.post("/api/init_story_text")
async def init_story_text(req: InitRequest):
    session_id = str(uuid.uuid4())
    opening_context = f"全局设定：故事主题是【{req.theme}】。主角准备好冒险了。"
    
    turn_data = generate_script_turn(req.child_features, opening_context, "开始冒险")
    if not turn_data: raise HTTPException(status_code=500, detail="剧本生成失败")
        
    create_storybook(session_id, req.theme, req.child_features)
    page_id = add_page_node(
        session_id, 0, 0, "开始冒险", 
        turn_data['narrator_text'], turn_data['actor_dialogue'],
        turn_data['story_action'], turn_data['story_scene'],
        turn_data['options'] # ⭐ 把选项存进数据库
    )

    return {
        "session_id": session_id, "page_id": page_id,
        "narrator_text": turn_data['narrator_text'], "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }

@app.post("/api/next_turn_text")
async def next_turn_text(req: NextTurnRequest):
    features, memory_list, current_path = rebuild_llm_context(req.parent_page_id)
    if not features: raise HTTPException(status_code=404, detail="找不到时间线")
        
    turn_data = generate_script_turn(features, "\n".join(memory_list), req.user_choice)
    if not turn_data: raise HTTPException(status_code=500, detail="剧本生成失败")

    depth = current_path[-1]["depth"] + 1 if current_path else 1
    page_id = add_page_node(
        req.session_id, req.parent_page_id, depth, req.user_choice, 
        turn_data['narrator_text'], turn_data['actor_dialogue'],
        turn_data['story_action'], turn_data['story_scene'],
        turn_data['options'] # ⭐ 把选项存进数据库
    )
    
    return {
        "page_id": page_id, "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'], "options": turn_data['options']
    }


'''
@app.post("/api/render_image")
async def render_image(req: RenderRequest):
    page = get_page(req.page_id)
    if not page: raise HTTPException(status_code=404, detail="找不到节点")
    book = get_storybook_info(page["session_id"])

    # 真实调用 ComfyUI 生成图片
    img_path = generate_full_story_page(
        page["session_id"], book["features"], 
        page["action_prompt"], page["scene_prompt"]
    )
    if not img_path: raise HTTPException(status_code=500, detail="图片生成失败")
        
    # 👇 修改点 1：组装新的保存路径 (例如: images/node_1.png)
    final_img_name = f"node_{req.page_id}.png"
    final_img_path = os.path.join(IMAGE_DIR, final_img_name)
    
    if os.path.exists(final_img_path): 
        os.remove(final_img_path)
    os.rename(img_path, final_img_path)
    
    # 👇 修改点 2：存入数据库和返回给前端的 URL 加上 /images/ 前缀
    image_url = f"/{IMAGE_DIR}/{final_img_name}"
    update_page_image(req.page_id, image_url)
    
    return {"image_url": image_url}
'''
#记得改回去
@app.post("/api/render_image")
async def render_image(req: RenderRequest):
    page = get_page(req.page_id)
    if not page: raise HTTPException(status_code=404, detail="找不到节点")
    book = get_storybook_info(page["session_id"])

    print(f"🎨 [调试模式] 正在为节点 [{req.page_id}] 生成占位图...")
    await asyncio.sleep(1.5) 
    
    placeholder_url = f"https://placehold.co/800x400/2b2b36/00d2ff.png?text=Node+{req.page_id}"
    update_page_image(req.page_id, placeholder_url)
    
    return {"image_url": placeholder_url}

@app.get("/api/get_timeline/{session_id}")
async def get_timeline(session_id: str):
    book = get_storybook_info(session_id)
    nodes = get_all_nodes(session_id)
    if not book or not nodes: raise HTTPException(status_code=404, detail="无记录")
    return {"theme": book["theme"], "features": book["features"], "nodes": nodes}

app.mount("/", StaticFiles(directory=".", html=True), name="static")