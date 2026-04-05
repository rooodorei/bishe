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

def generate_script_turn(child_features, context_history, user_choice, max_retries=3):
    """
    包含 导演、演员、评论家 三大Agent的生成流水线
    带有 Self-Refine (自动重试) 机制
    """
    # ================= 智能体人设 =================
    director_sys = """你是一个儿童绘本导演。请严格输出JSON格式：{"narrator_text": "中文旁白...", "story_scene": "英文场景...", "story_action": "英文动作...", "options": ["选项1", "选项2"]}。提取英文提示词时必须包含给定的主角特征。"""
    
    actor_sys = "你正在扮演儿童绘本的主角。根据旁白，用第一人称输出一句童趣的台词，20字以内。"
    
    critic_sys = "你是儿童内容安全专家。审核以下内容，安全回复PASS，不安全回复REJECT及原因。不可包含任何暴力、流血、恐怖、怪异、成人暗示或消极词汇。"

    # ================= 多智能体协作循环 =================
    for attempt in range(max_retries):
        print(f"\n🎬 [LLM] 第 {attempt + 1} 次尝试生成剧情...")
        
        # 1. 呼叫导演
        print("🧠 导演正在构思剧情与画面...")
        director_user = f"主角特征：{child_features}\n前情提要：{context_history}\n小朋友的最新选择：{user_choice}\n请生成下一幕。"
        director_response = chat_with_agent(director_sys, director_user, json_mode=True)
        
        try:
            data = json.loads(director_response)
        except Exception as e:
            print("❌ 导演输出格式错误，打回重做...")
            continue # 直接进入下一次循环重试
            
        narrator_text = data.get("narrator_text", "")
        
        # 2. 呼叫演员
        print("🗣️ 演员正在配音...")
        actor_dialogue = chat_with_agent(actor_sys, f"旁白：{narrator_text}")
        data['actor_dialogue'] = actor_dialogue
        
        # 3. 呼叫评论家 (核心安全防线)
        print("🛡️ 评论家正在逐字审核...")
        critic_user = f"旁白：{narrator_text}\n台词：{actor_dialogue}"
        critic_verdict = chat_with_agent(critic_sys, critic_user)
        
        # 判定结果
        if "PASS" in critic_verdict.upper():
            print("✅ 剧本完美！通过安全审核。")
            return data
        else:
            print(f"⚠️ 触发拦截！评论家意见：{critic_verdict}")
            print("🔄 剧情被打回，勒令导演重新修改...")
            # 循环继续，自动进行下一次生成
            
    print("❌ 连续尝试失败，无法生成安全合规的剧本。")
    return None