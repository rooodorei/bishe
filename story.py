import json
from openai import OpenAI

# 这里以兼容 OpenAI 格式的 API 为例（比如深度求索 DeepSeek, 智谱 GLM, 或通义千问）
# 请替换为你实际申请的 API Key 和 Base URL
client = OpenAI(
    api_key="sk-f05a2b91afc74603b56ce862208422fe",
    base_url="https://api.deepseek.com" 
)
MODEL_NAME = "deepseek-chat" # 例如 "glm-4" 或 "qwen-max"

def chat_with_agent(system_prompt, user_message, json_mode=False):
    """通用的调用大模型的基础函数"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    # 如果要求返回 JSON，可以加上相应的参数 (取决于具体模型API是否支持 response_format)
    kwargs = {"model": MODEL_NAME, "messages": messages, "temperature": 0.7}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
        
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()

def generate_script_turn(child_features, context_history, user_choice):
    """
    生成单轮剧本的核心流水线
    :param child_features: 儿童设定的主角特征 (例如 "1 girl, blue hair, red dress")
    :param context_history: 之前的剧情摘要 (防止模型遗忘)
    :param user_choice: 儿童刚刚点击的选项 (例如 "去右边的山洞")
    """
    print(f"\n--- 🎬 剧本生成开始 | 用户选择: {user_choice} ---")
    
    # ================= 1. 呼叫导演 =================
    director_sys = """你是一个儿童绘本导演。请严格输出JSON格式：{"narrator_text": "...", "story_scene": "...", "story_action": "...", "options": ["...", "..."]}。提取英文提示词时必须包含给定的主角特征。"""
    
    director_user = f"""
    主角特征：{child_features}
    前情提要：{context_history}
    小朋友的最新选择：{user_choice}
    请顺着这个选择，生成下一幕剧情、英文画图提示词以及接下来的两个选项。
    """
    
    print("🧠 导演正在思考剧情和画面...")
    director_response = chat_with_agent(director_sys, director_user, json_mode=True)
    
    try:
        # 解析导演输出的 JSON
        director_data = json.loads(director_response)
        narrator_text = director_data.get("narrator_text", "")
        story_scene = director_data.get("story_scene", "")
        story_action = director_data.get("story_action", "")
        options = director_data.get("options", [])
    except Exception as e:
        print(f"❌ 导演输出格式错误，请重试: {e}")
        print("原始输出:", director_response)
        return None

    # ================= 2. 呼叫演员 =================
    actor_sys = "你正在扮演儿童绘本的主角。根据旁白，用第一人称输出一句童趣的台词，20字以内。"
    actor_user = f"当前旁白：{narrator_text}"
    
    print("🗣️ 演员正在准备台词...")
    actor_dialogue = chat_with_agent(actor_sys, actor_user)

    # ================= 3. 呼叫评论家 (安全审核) =================
    critic_sys = "你是儿童内容安全专家。审核以下内容，安全回复PASS，不安全回复REJECT及原因。"
    critic_user = f"旁白：{narrator_text}\n台词：{actor_dialogue}"
    
    print("🛡️ 评论家正在进行安全审核...")
    critic_verdict = chat_with_agent(critic_sys, critic_user)
    
    if "PASS" not in critic_verdict.upper():
        print(f"⚠️ 触发安全拦截！原因：{critic_verdict}")
        # 在实际系统中，这里可以触发重新生成逻辑 (Self-Refine)
        # return generate_script_turn(child_features, context_history, user_choice)
        return None

    print("✅ 剧本生成完毕！通过安全审核。")
    
    # 组合最终数据
    turn_data = {
        "narrator_text": narrator_text,
        "actor_dialogue": actor_dialogue,
        "story_scene": story_scene,
        "story_action": story_action,
        "options": options
    }
    
    return turn_data

# ================= 测试运行 =================
if __name__ == "__main__":
    # 模拟测试数据
    test_features = "1 girl, 6 years old, blue short hair, wearing a red polka dot dress"
    test_context = "主角奇奇在森林里走着，面前出现了一条分叉路。左边是一条长满蘑菇的小路，右边是一座摇摇晃晃的木桥。"
    test_choice = "走左边的蘑菇小路"
    
    # 运行剧本流水线
    result = generate_script_turn(test_features, test_context, test_choice)
    
    if result:
        print("\n最终输出给前端和 ComfyUI 的数据包：")
        print(json.dumps(result, indent=4, ensure_ascii=False))


        # ================= 动态上下文管理测试 =================
if __name__ == "__main__":
    # 1. 初始设定（这是永远不变的“绝对记忆”）
    test_features = "1 girl, 6 years old, blue short hair, wearing a red polka dot dress"
    
    # 2. 故事的开篇（第一幕往往是预设好的，或者由没有前置上下文的系统生成）
    current_context = "主角奇奇来到了魔法森林的入口。面前出现了一条分叉路。左边是一条长满蘑菇的小路，右边是一座摇摇晃晃的木桥。"
    print(f"【故事开篇】: {current_context}")
    
    # 3. 创建一个记忆列表，用来存放历史记录
    # 初始状态下，只有开篇剧情
    memory_list = [f"开篇剧情：{current_context}"]
    
    # 4. 模拟小朋友连续玩了 3 个回合
    # 我们预设好小朋友这 3 次要点的选项
    mock_user_choices = [
        "走左边的蘑菇小路",      # 第一回合的点击
        "用手摸一下发光的蘑菇",   # 第二回合的点击
        "跟蝴蝶打招呼"          # 第三回合的点击
    ]
    
    for round_num, choice in enumerate(mock_user_choices, 1):
        print("\n" + "="*50)
        print(f"🎮 第 {round_num} 回合开始 | 小朋友点击了: 【{choice}】")
        
        # 【关键步骤 A】：生成本次请求的 context_history
        # 我们把 memory_list 里的句子用回车拼起来，生成一段文本给大模型
        context_history = "\n".join(memory_list)
        
        # 【关键步骤 B】：调用我们之前写好的生成器
        result = generate_script_turn(test_features, context_history, choice)
        
        if result:
            narrator_text = result['narrator_text']
            actor_dialogue = result['actor_dialogue']
            
            print(f"\n📺 前端界面展示：")
            print(f"📖 旁白: {narrator_text}")
            print(f"👧 主角说: {actor_dialogue}")
            print(f"👇 出现新选项: 1. {result['options'][0]}  2. {result['options'][1]}")
            
            # 【关键步骤 C】：更新记忆池！准备给下一回合用
            # 将刚刚发生的“选择”和“结果”存入记忆
            new_memory = f"小朋友选择了【{choice}】，随后剧情发展：{narrator_text}"
            memory_list.append(new_memory)
            
            # 【关键步骤 D】：滑动窗口（防止记忆太长撑爆大模型）
            # 假设我们最多只保留最近的 3 条记忆（即最近 3 个回合的剧情）
            if len(memory_list) > 3:
                memory_list.pop(0) # 删掉最旧的那一条