# llm_engine.py
import json
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME

# 初始化 OpenAI 客户端
client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

def chat_with_agent(system_prompt, user_message, json_mode=False):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    kwargs = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.7}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
        
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()

def generate_script_turn(child_features, context_history, user_choice):
    director_sys = """你是一个儿童绘本导演。请严格输出JSON格式：{"narrator_text": "中文旁白...", "story_scene": "英文场景...", "story_action": "英文动作...", "options": ["选项1", "选项2"]}。提取英文提示词时必须包含给定的主角特征。"""
    director_user = f"主角特征：{child_features}\n前情提要：{context_history}\n小朋友的最新选择：{user_choice}\n请生成下一幕。"
    
    print("🧠 [LLM] 导演正在思考剧情...")
    director_response = chat_with_agent(director_sys, director_user, json_mode=True)
    
    try:
        data = json.loads(director_response)
    except:
        print("❌ 导演输出JSON失败，原始输出:", director_response)
        return None

    actor_sys = "你正在扮演儿童绘本的主角。根据旁白，用第一人称输出一句童趣的台词，20字以内。"
    actor_dialogue = chat_with_agent(actor_sys, f"旁白：{data.get('narrator_text')}")

    data['actor_dialogue'] = actor_dialogue
    return data