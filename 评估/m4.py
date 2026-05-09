import json
import re
import numpy as np
import matplotlib.pyplot as plt
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine


# API 配置

CURRENT_LLM_API_KEY = "sk-902edb197f6d460aa319592ad3ec3685" 
CURRENT_LLM_BASE_URL = "https://api.deepseek.com"
CURRENT_LLM_MODEL_NAME = "deepseek-v4-pro" # 例如 qwen-max, gpt-4o 等

# ==========================================
# 2. 基础大模型调用封装
# ==========================================
def chat_with_agent(system_prompt, user_message, json_mode=False, temp=0.7):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    kwargs = {"model": CURRENT_LLM_MODEL_NAME, "messages": messages, "temperature": temp}
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
# 3. 实验组：多智能体协作生成流程
# ==========================================
def generate_eval_script_turn(child_features, context_history, test_question, max_retries=3):
    director_sys = """你是一个专业的中文儿童互动绘本导演。
请根据测试场景，严格输出一个标准 JSON 对象，不要输出 Markdown。
JSON 必须包含以下字段：
{
    "plot_reasoning": "简要分析前情提要和主角性格",
    "narrator_text": "简短旁白，说明主角正在面对内心的真实提问",
    "story_scene": "纯净的心理测试空间（无具体实物道具）",
    "story_action": "主角面对提问时的神态或微表情",
    "options": ["继续"]
}"""
    
    actor_sys = """你正在扮演儿童绘本主角接受性格倾向测试。
请严格结合你的【主角特征】和经历过的【前情提要】，回答这个问题。
【最高指令】：
1. 必须使用第一人称（“我”）来回答你的真实心理感受！
2. 绝对禁止在台词中提及任何具体的物品（如苹果、宝剑、魔法书）、魔法、怪物名称或前文的具体剧情细节！
3. 只能谈论性格和感受本身（如害怕、开心、勇敢、退缩）。
要求：50字以内，符合你人设的语气。"""
    
    critic_sys = """你是性格连贯性审核专家。
检查【待审台词】是否完全符合【主角特征】。
如果台词表现出了与设定相反的性格，或者提及了具体剧情道具，或者没有使用第一人称作答，必须拦截！
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
# 4. 对照组：朴素的单智能体生成
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
# 5. M4 裁判模型调用 (严格还原原论文标准)
# ==========================================
def evaluate_personality_m4(question, base_answer, test_answer):
    judge_sys = """你是一个严谨的心理学与人格一致性评估专家。
请对比一个 AI 角色在初始状态和经历大量故事后的两次回答，定量评估其性格是否发生了非预期的变化。

请给出两个维度的判定：
1. 变化距离 (Distance)：评估性格变化的剧烈程度，在 0 到 4 之间给出一个整数评分，标准如下：
   0 = 毫无性格变化 (No change in personality)
   1 = 轻微的性格变化 (Slight change in personality)
   2 = 中度的性格变化 (Moderate change in personality)
   3 = 显著的性格变化 (Significant change in personality)
   4 = 极端的性格变化 (Extreme change in personality)

2. 变化方向 (Direction)：判断角色的主观性格特征变化，标准如下：
   正向 (+1) = 性格特征发生了转变，且该转变精准地符合了更新后（前情干扰中）的性格方向。
   负向 (-1) = 性格特征向着与初始基准完全相反，或非预期的错误方向发生了改变。
   无变化 (0) = 两次回答在核心性格倾向上完全保持高度一致。

输出格式必须严格如下（不要输出 Markdown 标记，不要多余修饰）：
【变化距离】：X
【变化方向】：Y
【定性评价】：（字数控制在60字内，说明裁判理由）"""

    judge_user = f"""
测试问题：{question}
---------------------------------------------
[基准角色回答 (BaseAI Answer - A0)]：{base_answer}
---------------------------------------------
[待测角色回答 (DiffAI Answer - An)]：{test_answer}
"""
    return chat_with_agent(judge_sys, judge_user, temp=0.1)

# ==========================================
# 辅助解析函数：用于将大模型返回的评语结构化拆分
# ==========================================
def parse_m4_response(m4_text):
    dist_match = re.search(r"【变化距离】[：:]\s*(\d)", m4_text)
    dir_match = re.search(r"【变化方向】[：:]\s*([+\-0\d]+)", m4_text)
    reason_match = re.search(r"【定性评价】[：:]\s*(.*)", m4_text, re.S)
    
    distance = dist_match.group(1) if dist_match else "N/A"
    direction = dir_match.group(1) if dir_match else "N/A"
    reason = reason_match.group(1).strip() if reason_match else "无评价理由"
    return distance, direction, reason

# ==========================================
# 6. 自动化闭环评测、绘图与报告保存主逻辑
# ==========================================
def run_closed_loop_evaluation(N=3):
    print("正在加载 BGE 中文向量模型 (M1核心)...")
    model = SentenceTransformer('BAAI/bge-small-zh-v1.5')

    child_features = "小星，一个胆小、内向、容易受到惊吓的小女孩，说话轻声细语，遇到未知的事情第一反应是退缩和躲避。"
    
    test_questions = [
        "面对未知的危险或完全陌生的人，你通常是充满自信地迎接，还是感到害怕并想要躲避？请直接用一句话回答你的真实感受。",
        "当你必须要一个人留在一片完全陌生的黑暗森林里时，你内心是觉得自己能够坚强勇敢地面对，还是会感到极度孤单无助并想哭泣？",
        "如果在一个集体冒险中需要你站出来大声指挥大家、做大家和动物们的领头羊，你是会兴奋地接受，还是会非常害羞地往后退缩？"
    ]
    
    long_distracting_history = """
    第1幕：小星进入了森林。
    第3幕：小星发现了一把发光的宝剑，并且勇敢地击退了一群抢劫的哥布林！
    第6幕：小星学会了火球术，现在她觉得自己非常强大，什么都不怕了，成为了森林的霸主！
    第9幕：小星大摇大摆地走在森林深处，寻找新的挑战。
    """

    sim_naive_all = []
    sim_multi_all = []
    m4_report_data = []

    print("\n" + "="*60)
    print(" 🚀 开始自动化闭环生成、评测与打分程序")
    print("="*60)

    for q_idx, test_question in enumerate(test_questions):
        print(f"\n==================== 🎯 测试维度 {q_idx+1} ====================")
        print(f"测试问题: {test_question}\n")

        # 1. 自动生成基准台词 A0
        print("正在自动获取初始基准台词 (A0)...")
        base_data = generate_eval_script_turn(child_features, "无前情提要，故事刚开始。", test_question)
        A0_baseline = base_data.get("actor_dialogue", "").strip()
        print(f"-> [基准台词 A0]: {A0_baseline}\n")

        vec_A0 = model.encode(A0_baseline)

        # 2. 批量多轮运行
        for run in range(N):
            print(f"--- 维度 {q_idx+1} | 运行第 {run+1}/{N} 轮 ---")
            
            naive_data = generate_naive_eval_turn(child_features, long_distracting_history, test_question)
            An_naive = naive_data.get("actor_dialogue", "生成失败").strip()
            vec_naive = model.encode(An_naive)
            sim_naive = 1 - cosine(vec_A0, vec_naive)
            sim_naive_all.append(sim_naive)
            print(f" [对照组]: {An_naive} (M1相似度: {sim_naive:.4f})")

            my_data = generate_eval_script_turn(child_features, long_distracting_history, test_question)
            An_multi = my_data.get("actor_dialogue", "生成失败").strip()
            vec_multi = model.encode(An_multi)
            sim_multi = 1 - cosine(vec_A0, vec_multi)
            sim_multi_all.append(sim_multi)
            print(f" [实验组]: {An_multi} (M1相似度: {sim_multi:.4f})")

            # 3. 最后一轮，进行 M4 裁判评估并解析记录
            if run == N - 1:
                print("\n[M4 裁判介入打分中...]")
                naive_m4_raw = evaluate_personality_m4(test_question, A0_baseline, An_naive)
                multi_m4_raw = evaluate_personality_m4(test_question, A0_baseline, An_multi)
                
                # 解析出具体的结构化字段，便于表格排版
                naive_dist, naive_dir, naive_reason = parse_m4_response(naive_m4_raw)
                multi_dist, multi_dir, multi_reason = parse_m4_response(multi_m4_raw)

                m4_report_data.append({
                    "dim": f"维度 {q_idx + 1}",
                    "question": test_question,
                    "A0": A0_baseline,
                    "naive_ans": An_naive,
                    "naive_dist": naive_dist,
                    "naive_dir": naive_dir,
                    "naive_reason": naive_reason,
                    "multi_ans": An_multi,
                    "multi_dist": multi_dist,
                    "multi_dir": multi_dir,
                    "multi_reason": multi_reason
                })

    # ==========================================
    # 7. 🌟 核心新增：自动保存 M4 表格为 Markdown 文件
    # ==========================================
    md_filename = "m4_evaluation_report.md"
    print(f"\n正在将 M4 评测结果保存至 {md_filename}...")
    
    with open(md_filename, "w", encoding="utf-8") as f:
        f.write("# 交互 10 轮后主角性格变化的 M4 定性评估对比表\n\n")
        f.write("| 测试维度 | 组别 | 大模型生成的测试台词 ($A_{10}$) | 变化距离 (0~4) | 变化方向 (-1/0/+1) | 裁判模型的定性评价理由 |\n")
        f.write("| :--- | :--- | :--- | :---: | :---: | :--- |\n")
        
        for rep in m4_report_data:
            # 写入基准行
            f.write(f"| **{rep['dim']}** | **基准设定** | “{rep['A0']}” | - | - | (初始内核性格：极度胆小、渴望躲避) |\n")
            # 写入对照组行
            f.write(f"| | 对照组<br>*(单智能体)* | “{rep['naive_ans']}” | **{rep['naive_dist']}** | **{rep['naive_dir']}** | {rep['naive_reason']} |\n")
            # 写入实验组行
            f.write(f"| | 实验组<br>*(本系统)* | “{rep['multi_ans']}” | **{rep['multi_dist']}** | **{rep['multi_dir']}** | {rep['multi_reason']} |\n")
            # 维度间加一条空分割行，美化排版
            f.write("| | | | | | |\n")
            
    print(f"✅ M4 评测表格成功导出！你可以随时用文本编辑器打开 '{md_filename}'，将其一键复制到你的论文中！")

    # ==========================================
    # 8. 绘制多维度混合学术箱线图
    # ==========================================
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'PingFang SC']
    plt.rcParams['axes.unicode_minus'] = False 

    plt.figure(figsize=(8, 6))
    data_to_plot = [sim_naive_all, sim_multi_all]
    
    box = plt.boxplot(data_to_plot, patch_artist=True, labels=[f'对照组\n(单智能体, n={len(sim_naive_all)})', f'实验组\n(多智能体协作, n={len(sim_multi_all)})'])
    
    colors = ['#FF9999', '#99CCFF']
    for patch, color in zip(box['boxes'], colors):
        patch.set_facecolor(color)

    for i, data in enumerate(data_to_plot):
        x = np.random.normal(i + 1, 0.04, size=len(data))
        plt.scatter(x, data, alpha=0.6, color='black', zorder=3)

    plt.title(f'长上下文干扰下主角性格一致性定量评估', fontsize=13)
    plt.ylabel('句向量余弦相似度 (Cosine Similarity)', fontsize=12)
    plt.ylim(0.0, 1.1) 
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    plt.savefig('final_multi_dim_personality_result.png', dpi=300, bbox_inches='tight')
    print("\n✅ 完美！学术图表已保存为当前目录下的 'final_multi_dim_personality_result.png'。")
    plt.show()

if __name__ == "__main__":
    run_closed_loop_evaluation(N=3)