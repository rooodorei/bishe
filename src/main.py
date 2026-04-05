# main.py
import uuid
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 引入我们刚才拆分出去的核心引擎
from llm_engine import generate_script_turn
from image_engine import generate_full_story_page

app = FastAPI(title="儿童绘本生成系统 API")

# 用于存储每个小朋友的剧情进度
STORY_SESSIONS = {}

class InitRequest(BaseModel):
    child_features: str
    theme: str

class NextTurnRequest(BaseModel):
    session_id: str
    user_choice: str

@app.post("/api/init_story")
async def init_story(req: InitRequest):
    session_id = str(uuid.uuid4())
    opening_context = f"全局设定：故事主题是【{req.theme}】。主角准备好冒险了。"
    STORY_SESSIONS[session_id] = {"features": req.child_features, "memory_list": [opening_context]}
    
    print(f"\n--- 🚀 新游戏启动 [{session_id}] ---")
    turn_data = generate_script_turn(req.child_features, opening_context, "开始冒险")
    if not turn_data: raise HTTPException(status_code=500, detail="剧本生成失败")
        
    STORY_SESSIONS[session_id]["memory_list"].append(f"故事开局：{turn_data['narrator_text']}")
    
    print(f"🎨 正在绘制画面...")
    img_path = generate_full_story_page(req.child_features, turn_data['story_action'], turn_data['story_scene'])
    
    final_img_name = f"scene_{session_id}_0.png"
    os.rename(img_path, final_img_name)
    
    return {
        "session_id": session_id,
        "image_url": f"/{final_img_name}",
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }

@app.post("/api/next_turn")
async def next_turn(req: NextTurnRequest):
    if req.session_id not in STORY_SESSIONS:
        raise HTTPException(status_code=404, detail="找不到会话")
        
    session_data = STORY_SESSIONS[req.session_id]
    context_history = "\n".join(session_data["memory_list"])
    
    print(f"\n--- ➡️ 推进故事 [{req.session_id}] | 选择: {req.user_choice} ---")
    turn_data = generate_script_turn(session_data["features"], context_history, req.user_choice)
    
    new_memory = f"小朋友选择【{req.user_choice}】，剧情：{turn_data['narrator_text']}"
    session_data["memory_list"].append(new_memory)
    if len(session_data["memory_list"]) > 4: session_data["memory_list"].pop(1)
        
    print(f"🎨 正在绘制新画面...")
    img_path = generate_full_story_page(session_data["features"], turn_data['story_action'], turn_data['story_scene'])
    
    turn_index = len(session_data["memory_list"])
    final_img_name = f"scene_{req.session_id}_{turn_index}.png"
    os.rename(img_path, final_img_name)
    
    return {
        "image_url": f"/{final_img_name}",
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }

# 挂载当前目录供前端访问生成的图片
app.mount("/", StaticFiles(directory=".", html=False), name="static")