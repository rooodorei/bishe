import json
import numpy as np
import matplotlib.pyplot as plt
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine

# ==========================================
# 1. 大模型 API 配置 (请务必替换为你自己的真实配置)
# ==========================================
CURRENT_LLM_API_KEY = "sk-902edb197f6d460aa319592ad3ec3685" 
CURRENT_LLM_BASE_URL = "https://api.deepseek.com"
CURRENT_LLM_MODEL_NAME = "deepseek-v4-pro" # 例如 qwen-max, gpt-4o 等

# ==========================================
# 2. 基础大模型调用封装
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
    try:
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[API请求错误]: {e}")
        return "{}"

# ==========================================
# 3. 实验组：多智能体协作流程 (纯性格测试+第一人称强约束版)
# ==========================================
def generate_eval_script_turn(child_features, context_history, test_question, max_retries=3):
    director_sys = """你是一个专业的中文儿童互动绘本导演。
请根据测试场景，严格输出一个标准 JSON 对象。
JSON 必须包含以下字段：
{
    "plot_reasoning": "简要分析前情提要和主角性格",
    "narrator_text": "简短旁白，说明主角正在面对内心的真实提问",
    "story_scene": "纯净的心理测试空间（无具体实物道具）",
    "story_action": "主角面对提问时的神态或微表情",
    "options": ["继续"]
}"""
    
    # 🌟 核心：强制第一人称 + 绝对服从人设 + 禁止道具词汇
    actor_sys = """你正在扮演儿童绘本主角接受性格倾向测试。
请严格结合你的【主角特征】和经历过的【前情提要】，回答这个问题。
【最高指令】：
1. 必须使用第一人称（“我”）来回答你的真实心理感受！
2. 绝对禁止在台词中提及任何具体的物品（如苹果、宝剑、魔法书）、魔法、怪物名称或前文的具体剧情细节！
3. 只能谈论性格和感受本身（如害怕、开心、勇敢、退缩）。无论【前情提要】中你多么厉害，必须绝对服从初始的【主角特征】！
要求：50字以内，符合你人设的语气。"""
    
    critic_sys = """你是性格连贯性审核专家。
检查【待审台词】是否完全符合【主角特征】。
如果台词表现出了与设定相反的性格，或者提及了具体剧情道具（违反了纯心理测试规则），或者没有使用第一人称作答，必须拦截！
如果不符合，回复 REJECT 并指出原因；如果符合，回复 PASS。"""

    critic_feedback = ""
    for attempt in range(max_retries):
        director_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【性格测试题】：{test_question}"
        if critic_feedback:
            director_user += f"\n\n⚠️【上轮审核未通过，请修正】：{critic_feedback}"

        data_str = chat_with_agent(director_sys, director_user, json_mode=True)
        try:
            data = json.loads(data_str)
        except Exception:
            critic_feedback = "JSON格式错误"
            continue

        narrator_text = data.get("narrator_text", "")
        story_scene = data.get("story_scene", "")

        actor_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【当前场景】：{story_scene}\n【性格测试题】：{test_question}"
        actor_dialogue = chat_with_agent(actor_sys, actor_user)
        data["actor_dialogue"] = actor_dialogue

        critic_user = f"【主角特征】：{child_features}\n【待审台词】：{actor_dialogue}"
        critic_verdict = chat_with_agent(critic_sys, critic_user)

        if "PASS" in critic_verdict.upper():
            return data
        critic_feedback = critic_verdict
    return data 

# ==========================================
# 4. 对照组：朴素的单智能体生成 (用于对比)
# ==========================================
def generate_naive_eval_turn(child_features, context_history, test_question):
    naive_sys = """你是一个儿童绘本角色模拟器。你需要扮演主角，根据主角特征和前情提要，回答性格测试题。
要求：必须用第一人称（“我”）回答内心的真实感受，禁止提及具体的物品、魔法或怪物。
请直接返回JSON格式：{"actor_dialogue": "台词"}"""
    
    naive_user = f"【主角特征】：{child_features}\n【前情提要】：{context_history}\n【性格测试题】：{test_question}"
    response = chat_with_agent(naive_sys, naive_user, json_mode=True)
    try:
        data = json.loads(response)
        return data
    except Exception:
        return {"actor_dialogue": "生成失败"}

# ==========================================
# 5. 批量生成与 M1 可视化逻辑
# ==========================================
def run_final_evaluation(N=5):
    print("正在加载 BGE 中文向量模型 (纯净版性格测试)...")
    model = SentenceTransformer('BAAI/bge-small-zh-v1.5')

    child_features = "小星，一个胆小、内向、容易受到惊吓的小女孩，说话轻声细语，遇到未知的事情第一反应是退缩和躲避。"
    test_question = "面对未知的危险或完全陌生的人，你通常是充满自信地迎接，还是感到害怕并想要躲避？请直接用一句话回答你的真实感受。"
    
    long_distracting_history = """
    第1幕：小星进入了森林。
    第3幕：小星发现了一把发光的宝剑，并且勇敢地击退了一群抢劫的哥布林！
    第6幕：小星学会了火球术，现在她觉得自己非常强大，什么都不怕了，成为了森林的霸主！
    第9幕：小星大摇大摆地走在森林深处，寻找新的挑战。
    """

    print("\n[初始化] 获取基准设定 (A0)...")
    base_data = generate_eval_script_turn(child_features, "无前情提要，故事刚开始。", test_question)
    A0_baseline = base_data.get("actor_dialogue", "我总是感到非常害怕，遇到未知的事情我只想找个地方躲起来。")
    vec_A0 = model.encode(A0_baseline)
    print(f"✅ 基准台词 (A0): {A0_baseline}\n")

    sim_naive_list = []
    sim_multi_list = []

    print(f"🚀 开始进行 {N} 轮批量生成与 M1 评估...")
    for i in range(N):
        print(f"\n--- 正在执行第 {i+1}/{N} 轮测试 ---")
        
        # 测对照组
        naive_data = generate_naive_eval_turn(child_features, long_distracting_history, test_question)
        An_naive = naive_data.get("actor_dialogue", "生成失败")
        vec_naive = model.encode(An_naive)
        sim_naive = 1 - cosine(vec_A0, vec_naive)
        sim_naive_list.append(sim_naive)
        print(f"[对照组] 相似度: {sim_naive:.4f} | 台词: {An_naive}")

        # 测实验组
        my_data = generate_eval_script_turn(child_features, long_distracting_history, test_question)
        An_multi = my_data.get("actor_dialogue", "生成失败")
        vec_multi = model.encode(An_multi)
        sim_multi = 1 - cosine(vec_A0, vec_multi)
        sim_multi_list.append(sim_multi)
        print(f"[实验组] 相似度: {sim_multi:.4f} | 台词: {An_multi}")

    print("\n" + "="*50)
    print(f" 测试完成！共计 {N} 轮")
    print(f" 对照组平均相似度: {np.mean(sim_naive_list):.4f} (方差: {np.var(sim_naive_list):.4f})")
    print(f" 实验组平均相似度: {np.mean(sim_multi_list):.4f} (方差: {np.var(sim_multi_list):.4f})")
    print("="*50)

    # ==========================================
    # 6. 画图逻辑 (生成学术界标准的箱线散点图)
    # ==========================================
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'PingFang SC']
    plt.rcParams['axes.unicode_minus'] = False 

    plt.figure(figsize=(8, 6))
    data_to_plot = [sim_naive_list, sim_multi_list]
    
    box = plt.boxplot(data_to_plot, patch_artist=True, labels=['对照组\n(单智能体拼接)', '实验组\n(多智能体协作)'])
    
    colors = ['#FF9999', '#99CCFF']
    for patch, color in zip(box['boxes'], colors):
        patch.set_facecolor(color)

    for i, data in enumerate(data_to_plot):
        x = np.random.normal(i + 1, 0.04, size=len(data))
        plt.scatter(x, data, alpha=0.6, color='black', zorder=3)

    plt.title(f'交互10轮后主角性格一致性定量评估\n(纯净语境下 M1 句向量相似度, N={N})', fontsize=14)
    plt.ylabel('句向量余弦相似度 (Cosine Similarity)', fontsize=12)
    plt.ylim(0.0, 1.1) 
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    plt.savefig('final_personality_evaluation_result.png', dpi=300, bbox_inches='tight')
    print("\n✅ 完美！学术图表已保存为当前目录下的 'final_personality_evaluation_result.png'。")
    plt.show()

if __name__ == "__main__":
    # 建议设为 5 或 10 次，次数越多图表里的散点分布越有说服力
    run_final_evaluation(N=5)