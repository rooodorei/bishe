# main.py
import uuid
import asyncio
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from llm_engine import generate_script_turn
from image_engine import generate_full_story_page
from database import (
    init_db, create_storybook, add_page_node, update_page_image, 
    get_page, get_storybook_info, get_all_nodes, rebuild_llm_context
)

app = FastAPI(title="儿童绘本生成系统 - 世界线版")
init_db()
IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

class InitRequest(BaseModel):
    child_features: str
    theme: str

class NextTurnRequest(BaseModel):
    session_id: str
    parent_page_id: int  # ⭐ 告诉服务器我们是从哪个节点开始分支的
    user_choice: str

class RenderRequest(BaseModel):
    page_id: int # ⭐ 直接传节点 ID 渲染

@app.post("/api/init_story_text")
async def init_story_text(req: InitRequest):
    session_id = str(uuid.uuid4())
    opening_context = f"全局设定：故事主题是【{req.theme}】。主角准备好冒险了。"
    
    turn_data = generate_script_turn(req.child_features, opening_context, "开始冒险")
    if not turn_data: raise HTTPException(status_code=500, detail="剧本生成失败")
        
    create_storybook(session_id, req.theme, req.child_features)
    # 创建根节点，parent_id 为 0，深度为 0
    page_id = add_page_node(
        session_id, 0, 0, "开始冒险", 
        turn_data['narrator_text'], turn_data['actor_dialogue'],
        turn_data['story_action'], turn_data['story_scene']
    )

    return {
        "session_id": session_id,
        "page_id": page_id,
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }

@app.post("/api/next_turn_text")
async def next_turn_text(req: NextTurnRequest):
    
    # 🌟 步骤 1：调用数据库里的函数，拿到“纯净版”的记忆列表
    # req.parent_page_id 是前端传来的，代表玩家是“站在哪个节点上”做出的新选择
    features, memory_list, current_path = rebuild_llm_context(req.parent_page_id)
    if not features: raise HTTPException(status_code=404, detail="找不到时间线")
        
    # 🌟 步骤 2：把数组拼接成大段文字
    # memory_list 只是一个数组，我们用 "\n".join() 把它们用回车符连起来，变成一大段连续的字符串
    # 这样大模型读起来就像在读前情提要
    context_history = "\n".join(memory_list)
    
    # 🌟 步骤 3：正式喂给大模型！
    # 调用 llm_engine.py 里的 generate_script_turn 函数
    # 把主角长相 (features)、历史记忆 (context_history)、用户的新决定 (req.user_choice) 一起发过去
    turn_data = generate_script_turn(features, context_history, req.user_choice)
    if not turn_data: raise HTTPException(status_code=500, detail="剧本生成失败")

    # 🌟 步骤 4：计算新节点的深度
    # 看看刚才走过的路径最后一个节点的深度是多少，新节点就在它基础上 +1
    depth = current_path[-1]["depth"] + 1 if current_path else 1
    
    # 🌟 步骤 5：大模型生成完新剧情后，把这些新内容作为一个“新叶子节点”长在数据库的树上
    page_id = add_page_node(
        req.session_id, req.parent_page_id, depth, req.user_choice, 
        turn_data['narrator_text'], turn_data['actor_dialogue'],
        turn_data['story_action'], turn_data['story_scene']
    )
    
    # 把结果返回给前端去展示
    return {
        "page_id": page_id,
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
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
#调试记得改回去
@app.post("/api/render_image")
async def render_image(req: RenderRequest):
    page = get_page(req.page_id)
    if not page: raise HTTPException(status_code=404, detail="找不到节点")
    
    print(f"🎨 [调试模式] 正在为节点 [{req.page_id}] 生成占位图...")
    
    # 模拟稍微加载一下，让你能看到前端那个 "影像合成中..." 的动画（1.5秒后出图）
    await asyncio.sleep(1.5) 
    
    # 【核心修改】使用在线占位图取代 ComfyUI 真实画图
    # 占位图上会写着 "Node {ID}"，背景是深灰色，字是亮蓝色，完美契合你的底特律UI
    placeholder_url = f"https://placehold.co/800x400/2b2b36/00d2ff.png?text=Node+{req.page_id}"
    
    # 将这个虚拟的图片 URL 更新到数据库中
    update_page_image(req.page_id, placeholder_url)
    
    print(f"✅ [调试模式] 节点 [{req.page_id}] 占位图已返回")
    return {"image_url": placeholder_url}




@app.get("/api/get_timeline/{session_id}")
async def get_timeline(session_id: str):
    """返回整棵故事树的数据供前端绘制底特律UI"""
    book = get_storybook_info(session_id)
    nodes = get_all_nodes(session_id)
    if not book or not nodes: raise HTTPException(status_code=404, detail="无记录")
    
    return {
        "theme": book["theme"], "features": book["features"],
        "nodes": nodes
    }

@app.get("/api/get_path/{page_id}")
async def get_path(page_id: int):
    """沿着时间线提取当前绘本的完整故事"""
    features, memory, path = rebuild_llm_context(page_id)
    return path

app.mount("/", StaticFiles(directory=".", html=True), name="static")