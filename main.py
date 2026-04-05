from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import uuid
import os

# 导入你之前写好的生成函数 (假设它们在你之前的 story.py 和 draw.py 里，你可以把它们合并到这里)
# from your_module import generate_script_turn, generate_full_story_page, run_comfyui_task

app = FastAPI(title="儿童交互式绘本生成系统 API")

# ================= 1. 数据模型与状态管理 =================

# 内存数据库，用于存储每个小朋友的剧情进度
# 实际商业项目中会用 MySQL/Redis，毕设用字典完全足够
STORY_SESSIONS = {}

# 前端请求体定义
class InitRequest(BaseModel):
    child_features: str  # 例如："1 girl, blue short hair, red dress"
    theme: str           # 例如："魔法森林探险"

class NextTurnRequest(BaseModel):
    session_id: str
    user_choice: str     # 例如："走左边的蘑菇小路"

# ================= 2. 核心 API 接口 =================

@app.post("/api/init_story")
async def init_story(req: InitRequest):
    """
    游戏初始化接口：
    当小朋友填完角色设定，点击“开始冒险”时调用。
    """
    session_id = str(uuid.uuid4()) # 生成一个唯一的用户ID
    
    # 1. 记录初始状态和第一句开场白
    opening_context = f"全局设定：这是一个关于【{req.theme}】的童话故事。主角马上要开始冒险了。"
    STORY_SESSIONS[session_id] = {
        "features": req.child_features,
        "memory_list": [opening_context]
    }
    
    # 2. 调用大模型，生成故事的【第一幕】（假装用户的选择是“开始冒险”）
    print(f"[{session_id}] 正在生成开场故事...")
    turn_data = generate_script_turn(
        child_features=req.child_features, 
        context_history=opening_context, 
        user_choice="开始冒险"
    )
    
    if not turn_data:
        raise HTTPException(status_code=500, detail="大模型生成开场失败")
        
    # 3. 记录剧情到记忆池
    new_memory = f"故事开局：{turn_data['narrator_text']}"
    STORY_SESSIONS[session_id]["memory_list"].append(new_memory)
    
    # 4. 调用 ComfyUI 生成【阶段一：定妆照】和【阶段二三：第一幕画面】
    print(f"[{session_id}] 正在渲染开场画面...")
    # 注意：这里需要你修改之前的生图函数，让它返回生成的图片文件名
    final_img_path = generate_full_story_page(
        child_features=req.child_features,
        story_action=turn_data['story_action'],
        story_scene=turn_data['story_scene']
    )
    
    # 将图片重命名为带有 session_id 的名字，防止覆盖
    safe_img_name = f"scene_{session_id}_0.png"
    os.rename(final_img_path, safe_img_name)
    
    return {
        "session_id": session_id,
        "image_url": f"/{safe_img_name}", # 前端通过这个地址加载图片
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }


@app.post("/api/next_turn")
async def next_turn(req: NextTurnRequest):
    """
    故事推进接口：
    当小朋友点击了选项 A 或 B 时调用。
    """
    if req.session_id not in STORY_SESSIONS:
        raise HTTPException(status_code=404, detail="找不到该会话，请重新开始游戏")
        
    session_data = STORY_SESSIONS[req.session_id]
    
    # 1. 组装最新的上下文记忆
    context_history = "\n".join(session_data["memory_list"])
    
    # 2. 调用大模型，生成下一幕
    print(f"[{req.session_id}] 正在生成下一幕，用户选择：{req.user_choice}")
    turn_data = generate_script_turn(
        child_features=session_data["features"], 
        context_history=context_history, 
        user_choice=req.user_choice
    )
    
    if not turn_data:
        raise HTTPException(status_code=500, detail="大模型生成失败")
        
    # 3. 更新记忆池 (滑动窗口管理)
    new_memory = f"小朋友选择了【{req.user_choice}】，随后剧情发展：{turn_data['narrator_text']}"
    session_data["memory_list"].append(new_memory)
    if len(session_data["memory_list"]) > 4: # 保留最近4轮记忆
        session_data["memory_list"].pop(1)   # 注意：保留第0个全局设定，删掉最旧的具体剧情
        
    # 4. 调用 ComfyUI 生成画面
    print(f"[{req.session_id}] 正在渲染新画面...")
    final_img_path = generate_full_story_page(
        child_features=session_data["features"],
        story_action=turn_data['story_action'],
        story_scene=turn_data['story_scene']
    )
    
    # 每次生成新的图片名字
    turn_index = len(session_data["memory_list"])
    safe_img_name = f"scene_{req.session_id}_{turn_index}.png"
    os.rename(final_img_path, safe_img_name)
    
    return {
        "image_url": f"/{safe_img_name}",
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }

# ================= 3. 静态文件代理 (给前端提供图片) =================
from fastapi.staticfiles import StaticFiles
# 假设你的图片都保存在当前目录下，直接把当前目录挂载出去供前端访问图片
app.mount("/", StaticFiles(directory=".", html=False), name="static")