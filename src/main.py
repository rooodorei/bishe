import uuid
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 引入核心引擎
from llm_engine import generate_script_turn
from image_engine import generate_full_story_page

# 引入核心引擎
from llm_engine import generate_script_turn
from image_engine import generate_full_story_page
# 👇 新增：引入我们的数据库模块
from database import create_storybook, add_page_text, update_page_image, get_full_storybook


app = FastAPI(title="儿童绘本生成系统 API (异步加载版)")

STORY_SESSIONS = {}

# ================= 数据模型 =================
class InitRequest(BaseModel):
    child_features: str
    theme: str

class NextTurnRequest(BaseModel):
    session_id: str
    user_choice: str

class RenderRequest(BaseModel):
    session_id: str

# ================= 接口 1：生成初始化剧本 (只返回文字，极快) =================
@app.post("/api/init_story_text")
async def init_story_text(req: InitRequest):
    session_id = str(uuid.uuid4())
    opening_context = f"全局设定：故事主题是【{req.theme}】。主角准备好冒险了。"
    STORY_SESSIONS[session_id] = {"features": req.child_features, "memory_list": [opening_context]}
    
    print(f"\n--- 🚀 新游戏启动 [{session_id}] ---")
    turn_data = generate_script_turn(req.child_features, opening_context, "开始冒险")
    if not turn_data: 
        raise HTTPException(status_code=500, detail="剧本生成失败")
        
    STORY_SESSIONS[session_id]["memory_list"].append(f"故事开局：{turn_data['narrator_text']}")
    
    # 将画图需要的提示词暂存在 Session 里，留给下一步用
    STORY_SESSIONS[session_id]["current_action"] = turn_data['story_action']
    STORY_SESSIONS[session_id]["current_scene"] = turn_data['story_scene']
    # 👇 新增存入数据库
    create_storybook(session_id, req.theme, req.child_features)
    add_page_text(session_id, 0, "开始冒险", turn_data['narrator_text'], turn_data['actor_dialogue'])


    print("✅ 文字生成完毕，已返回给前端！")
    return {
        "session_id": session_id,
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }





# ================= 接口 2：生成下一幕剧本 (只返回文字，极快) =================
@app.post("/api/next_turn_text")
async def next_turn_text(req: NextTurnRequest):
    if req.session_id not in STORY_SESSIONS:
        raise HTTPException(status_code=404, detail="找不到会话")
        
    session_data = STORY_SESSIONS[req.session_id]
    context_history = "\n".join(session_data["memory_list"])
    
    print(f"\n--- ➡️ 推进故事 [{req.session_id}] | 选择: {req.user_choice} ---")
    turn_data = generate_script_turn(session_data["features"], context_history, req.user_choice)
    
    if not turn_data: 
        raise HTTPException(status_code=500, detail="剧本生成失败")

    new_memory = f"小朋友选择【{req.user_choice}】，剧情：{turn_data['narrator_text']}"
    session_data["memory_list"].append(new_memory)
    if len(session_data["memory_list"]) > 4: 
        session_data["memory_list"].pop(1)
        
    # 同样暂存画图提示词
    session_data["current_action"] = turn_data['story_action']
    session_data["current_scene"] = turn_data['story_scene']

    # 计算这是第几页 (因为 memory_list 包含全局设定，所以减去1)
    turn_index = len(session_data["memory_list"]) - 1
    # 👇 新增：把这一页的文字存入数据库
    add_page_text(req.session_id, turn_index, req.user_choice, turn_data['narrator_text'], turn_data['actor_dialogue'])
    print("✅ 文字生成完毕，已返回给前端！")
    return {
        "narrator_text": turn_data['narrator_text'],
        "actor_dialogue": turn_data['actor_dialogue'],
        "options": turn_data['options']
    }



# ================= 接口 3：画图接口 (耗时较长) =================
@app.post("/api/render_image")
async def render_image(req: RenderRequest):
    if req.session_id not in STORY_SESSIONS:
        raise HTTPException(status_code=404, detail="找不到会话")
        
    session_data = STORY_SESSIONS[req.session_id]
    print(f"🎨 正在为 [{req.session_id}] 绘制画面...")
    
    img_path = generate_full_story_page(
        req.session_id,
        session_data["features"], 
        session_data["current_action"], 
        session_data["current_scene"]
    )
    
    if not img_path:
        raise HTTPException(status_code=500, detail="图片生成失败")
        
    turn_index = len(session_data["memory_list"])
    final_img_name = f"scene_{req.session_id}_{turn_index}.png"
    if os.path.exists(final_img_name):
        os.remove(final_img_name)
    os.rename(img_path, final_img_name)
    
    # 👇 新增：把画好的图片路径更新到数据库的对应页里
    update_page_image(req.session_id, f"/{final_img_name}")
    print("✅ 画面绘制完毕，已发送图片URL！")
    return {"image_url": f"/{final_img_name}"}

# ================= 接口 4：获取完整绘本档案 (查库) =================
@app.get("/api/get_storybook/{session_id}")
async def fetch_storybook(session_id: str):
    book_data = get_full_storybook(session_id)
    if not book_data:
        raise HTTPException(status_code=404, detail="找不到这本绘本")
    return book_data





app.mount("/", StaticFiles(directory=".", html=True), name="static")