import json
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME


client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

def chat_with_agent(system_prompt, user_message, json_mode=False):
    """输入输出监控"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    # 打印发送给 LLM 的提示词（方便调试）
    print("\n" + "="*25 + " LLM INPUT " + "="*25)
    print(f"【User Message】: {user_message}")

    kwargs = {"model": LLM_MODEL_NAME, "messages": messages, "temperature": 0.7}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
        
    response = client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content.strip()

    # 打印 LLM 返回的结果
    print("-" * 25 + " LLM RESPONSE " + "-" * 25)
    print(result)
    print("=" * 64)
    
    return result

def generate_script_turn(child_features, context_history, user_choice, max_retries=3):
    """
    自省型多智能体协作管线 (Reflective Multi-Agent Pipeline)
    解决了导演不看反馈、演员不看环境的问题
    """
    
    # 1. 导演人设：增加了对反馈的处理逻辑
    director_sys = f"""你是一个专业的儿童绘本导演。
    请根据小朋友的选择构思下一幕，并严格输出JSON格式：
    {{
        "narrator_text": "150字左右的生动旁白...",
        "story_scene": "英文场景提示词",
        "story_action": "英文动作提示词...",
        "options": ["选项1", "选项2"]
    }}
    注意：如果收到评论家的打回意见，请务必针对性修改，避开违规内容。"""

    # 2. 演员人设：要求参考场景信息
    actor_sys = "你正在扮演绘本主角。请结合当前的【场景环境】和【旁白内容】，说一句充满童趣的第一人称台词（50字以内）。"
    
    # 3. 评论家人设：安全审核
    critic_sys = "你是儿童内容安全专家。审核内容是否包含暴力、血腥、恐怖或成人暗示。安全回复 PASS，否则回复 REJECT 及具体原因。"

    # --- 初始化反馈变量 ---
    critic_feedback = "" 

    for attempt in range(max_retries):
        print(f"\n🎬 [LLM] 第 {attempt + 1} 次尝试生成剧情...")
        
        # --- 步骤 1: 导演构思 ---
        director_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【小朋友的选择】：{user_choice}"
        # 如果有上一次的失败反馈，强行喂给导演
        if critic_feedback:
            director_user += f"\n\n⚠️【上轮审核未通过，请修正】：{critic_feedback}"

        director_response = chat_with_agent(director_sys, director_user, json_mode=True)
        
        try:
            data = json.loads(director_response)
        except:
            critic_feedback = "JSON格式错误，请确保返回标准的JSON对象。"
            continue
            
        narrator_text = data.get("narrator_text", "")
        story_scene = data.get("story_scene", "") # 提取导演设定的场景

        # --- 步骤 2: 演员配音 (语境对齐) ---
        # 这里把 story_scene 喂给演员，解决“语境隔离”问题
        print("🗣️ 演员正在根据场景配音...")
        actor_user = f"【当前场景】：{story_scene}\n【当前旁白】：{narrator_text}"
        actor_dialogue = chat_with_agent(actor_sys, actor_user)
        data['actor_dialogue'] = actor_dialogue
        
        # --- 步骤 3: 评论家审核 (闭环反馈) ---
        print("🛡️ 评论家正在逐字审核...")
        critic_user = f"【旁白】：{narrator_text}\n【台词】：{actor_dialogue}"
        critic_verdict = chat_with_agent(critic_sys, critic_user)
        
        if "PASS" in critic_verdict.upper():
            print("✅ 剧本完美！通过安全审核。")
            return data
        else:
            # 捕获反馈，进入下一轮循环，导演就会看到这个反馈了
            critic_feedback = critic_verdict 
            print(f"⚠️ 触发拦截！评论家意见：{critic_feedback}")
            print("🔄 正在将意见反馈给导演进行重写...")
            
    print("❌ 达到最大尝试次数，生成失败。")
    return None