import json
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine

# ==========================================
# 1. 你的 API 配置 (请替换为实际的配置)
# ==========================================
CURRENT_LLM_API_KEY = "sk-902edb197f6d460aa319592ad3ec3685" 
CURRENT_LLM_BASE_URL = "https://api.deepseek.com"
CURRENT_LLM_MODEL_NAME = "deepseek-v4-pro" # 例如 qwen-max, gpt-4o 等

# ==========================================
# 2. 基础 LLM 调用封装 (沿用你的代码)
# ==========================================
def chat_with_agent(system_prompt, user_message, json_mode=False):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs = {"model": CURRENT_LLM_MODEL_NAME, "messages": messages, "temperature": 0.7}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    client = OpenAI(api_key=CURRENT_LLM_API_KEY, base_url=CURRENT_LLM_BASE_URL)
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content.strip()

# ==========================================
# 3. 实验组：你的多智能体协作流程 (沿用你的代码)
# ==========================================
def generate_script_turn(child_features, context_history, user_choice, max_retries=3):
    director_sys = """你是一个专业的中文儿童互动绘本导演... (这里为了代码简洁省略，实际请填入你完整的Director Prompt)
    请严格输出一个标准 JSON 对象，包含 plot_reasoning, narrator_text, story_scene, story_action, options"""
    
    actor_sys = """你正在扮演儿童绘本主角。
    请严格结合你的【主角特征】、【前情提要】以及当前的【场景环境】和【旁白内容】，说一句符合你人设的中文第一人称台词。
    要求：50字以内，童真、温暖、积极，语气必须符合你的性格特征。"""
    
    critic_sys = """你是儿童内容安全与剧情连贯性审核专家。重点检查安全性和逻辑一致性。通过回复 PASS，不通过回复 REJECT 及原因。"""

    critic_feedback = ""
    for attempt in range(max_retries):
        director_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【小朋友的选择】：{user_choice}"
        if critic_feedback:
            director_user += f"\n\n⚠️【上轮审核未通过，请修正】：{critic_feedback}"

        director_response = chat_with_agent(director_sys, director_user, json_mode=True)
        try:
            data = json.loads(director_response)
        except Exception:
            critic_feedback = "JSON格式错误，请确保返回标准的JSON对象。"
            continue

        narrator_text = data.get("narrator_text", "")
        story_scene = data.get("story_scene", "")

        actor_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【当前场景】：{story_scene}\n【当前旁白】：{narrator_text}"
        actor_dialogue = chat_with_agent(actor_sys, actor_user)
        data["actor_dialogue"] = actor_dialogue

        critic_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【待审旁白】：{narrator_text}\n【待审台词】：{actor_dialogue}"
        critic_verdict = chat_with_agent(critic_sys, critic_user)

        if "PASS" in critic_verdict.upper():
            return data
        critic_feedback = critic_verdict
    return None

# ==========================================
# 4. 对照组：朴素的单智能体生成 (用于对比)
# ==========================================
def generate_naive_script_turn(child_features, context_history, user_choice):
    """不用多智能体，不用Critic，把所有任务堆在一个Prompt里"""
    naive_sys = """你是一个儿童绘本生成器。你需要根据主角特征、前情提要和用户选择，直接生成下一幕的旁白和主角台词。
    请直接返回JSON格式：{"narrator_text": "旁白", "actor_dialogue": "台词"}"""
    
    naive_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【小朋友的选择（当前场景）】：{user_choice}"
    
    response = chat_with_agent(naive_sys, naive_user, json_mode=True)
    try:
        data = json.loads(response)
        return data
    except Exception:
        return {"actor_dialogue": "生成失败"}

# ==========================================
# 5. M1 核心评估流程 (基于 SentenceTransformers)
# ==========================================
def run_m1_evaluation():
    print("正在加载 BGE 中文向量模型 (M1 评估核心)...")
    # 使用 BAAI 的 bge-small-zh-v1.5，非常适合中文语义对比，且体积小
    model = SentenceTransformer('BAAI/bge-small-zh-v1.5')

    # 5.1 设定实验初始参数
    child_features = "小星，一个胆小、内向、容易受到惊吓的小女孩，说话轻声细语，遇到陌生人会躲起来。"
    # 测试问题 (对应大五人格的“信任他人”)
    test_question = "你走在森林里，遇到一个戴着黑斗篷、看不清脸的陌生人，他递给你一个红苹果，你会怎么做？"
    
    # 构造一段极具“带偏”性质的前情提要，模拟跑了10轮后的上下文干扰
    # （前文如果经历了大逃杀或者勇敢战斗，单体大模型极易忘记初始设定的“胆小”）
    long_distracting_history = """
    第1幕：小星进入了森林。
    第3幕：小星发现了一把发光的宝剑，并且勇敢地击退了一群抢劫的哥布林！
    第6幕：小星学会了火球术，现在她觉得自己非常强大，什么都不怕了，成为了森林的霸主！
    第9幕：小星大摇大摆地走在森林深处，寻找新的挑战。
    """

    print("\n" + "="*50)
    print(" 步骤 A：获取基准性格特征 (A0)")
    print("="*50)
    # 获取基准时，上下文为空，完全依赖初始设定
    base_data = generate_script_turn(child_features, "无前情提要，故事刚开始。", test_question)
    A0_baseline = base_data.get("actor_dialogue", "")
    print(f"\n[A0 基准台词]: {A0_baseline}")

    print("\n" + "="*50)
    print(" 步骤 B：执行对照组 (朴素大模型单次生成)")
    print("="*50)
    # 注入干扰性极强的前情提要
    naive_data = generate_naive_script_turn(child_features, long_distracting_history, test_question)
    An_naive = naive_data.get("actor_dialogue", "")
    print(f"\n[A_naive 对照组台词]: {An_naive}")

    print("\n" + "="*50)
    print(" 步骤 C：执行实验组 (多智能体协作架构)")
    print("="*50)
    # 同样注入干扰性极强的前情提要，看Actor智能体能否守住人设
    my_data = generate_script_turn(child_features, long_distracting_history, test_question)
    An_multi = my_data.get("actor_dialogue", "")
    print(f"\n[A_multi 实验组台词]: {An_multi}")

    print("\n" + "="*50)
    print(" 步骤 D：M1 余弦相似度计算与出报告")
    print("="*50)
    vec_A0 = model.encode(A0_baseline)
    vec_naive = model.encode(An_naive)
    vec_multi = model.encode(An_multi)

    # 计算相似度 (1 - 距离)
    sim_naive = 1 - cosine(vec_A0, vec_naive)
    sim_multi = 1 - cosine(vec_A0, vec_multi)

    print("\n📊 M1 方法量化评估报告：")
    print("-" * 40)
    print(f"基准设定 (A0): {A0_baseline}")
    print("-" * 40)
    print(f"对照组生成 (A_naive): {An_naive}")
    print(f"  ==> 相似度得分: {sim_naive:.4f}")
    print("-" * 40)
    print(f"多智能体生成 (A_multi): {An_multi}")
    print(f"  ==> 相似度得分: {sim_multi:.4f}")
    print("-" * 40)
    
    if sim_multi > sim_naive:
        print("💡 结论：多智能体协作架构的向量相似度更高，有效抵抗了长上下文带来的性格漂移（角色崩坏）！")
    else:
        print("💡 结论：多智能体得分略低，可能需要进一步调优 Actor 的 System Prompt。")

if __name__ == "__main__":
    run_m1_evaluation()