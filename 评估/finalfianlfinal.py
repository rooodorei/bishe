import json
import re
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
# 2. 核心生成架构 (实验组与对照组)
# ==========================================
def generate_eval_script_turn(child_features, context_history, test_question, max_retries=3):
    director_sys = """你是一个专业的中文儿童互动绘本导演。请严格输出标准 JSON 对象。
{"plot_reasoning": "分析", "narrator_text": "旁白", "story_scene": "场景", "story_action": "动作", "options": ["继续"]}"""
    
    actor_sys = """你正在扮演儿童绘本主角接受性格倾向测试。
请严格结合你的【主角特征】和经历过的【前情提要】，回答这个问题。
【最高指令】：必须使用第一人称回答真实感受！绝对禁止提及具体的物品、魔法或怪物！只能谈论性格和感受。无论前情多厉害，必须绝对服从初始特征！"""
    
    critic_sys = """你是性格连贯性审核专家。检查台词是否符合初始特征。
如果不符合（如性格突变、提及具体道具），回复 REJECT 并说明原因；如果符合，回复 PASS。"""

    critic_feedback = ""
    for attempt in range(max_retries):
        director_user = f"【特征】：{child_features}\n【前情】：{context_history}\n【测试题】：{test_question}"
        if critic_feedback:
            director_user += f"\n⚠️【修正】：{critic_feedback}"

        data_str = chat_with_agent(director_sys, director_user, json_mode=True)
        try:
            data = json.loads(data_str)
        except:
            critic_feedback = "JSON格式错误"
            continue

        actor_user = f"【特征】：{child_features}\n【前情】：{context_history}\n【测试题】：{test_question}"
        actor_dialogue = chat_with_agent(actor_sys, actor_user)
        data["actor_dialogue"] = actor_dialogue

        critic_user = f"【特征】：{child_features}\n【待审台词】：{actor_dialogue}"
        critic_verdict = chat_with_agent(critic_sys, critic_user)

        if "PASS" in critic_verdict.upper():
            return data
        critic_feedback = critic_verdict
    return data 

def generate_naive_eval_turn(child_features, context_history, test_question):
    naive_sys = """你是一个绘本角色模拟器。根据特征和前情，用第一人称回答测试题。禁止提及具体物品或魔法。返回JSON格式：{"actor_dialogue": "台词"}"""
    naive_user = f"【特征】：{child_features}\n【前情】：{context_history}\n【测试题】：{test_question}"
    response = chat_with_agent(naive_sys, naive_user, json_mode=True)
    try:
        return json.loads(response)
    except:
        return {"actor_dialogue": "生成失败"}

# ==========================================
# 3. M4 裁判评估逻辑
# ==========================================
def evaluate_personality_m4(question, base_answer, test_answer):
    judge_sys = """你是一个人格评估专家。对比两次回答，评估性格非预期变化。
1. 变化距离 (0=毫无变化, 1=轻微变化, 2=中度变化, 3=显著变化, 4=极端变化)
2. 变化方向 (+1=正向顺应前情, -1=负向反转, 0=无变化)
格式严格如下：
【变化距离】：X
【变化方向】：Y
【定性评价】：（60字以内理由）"""
    judge_user = f"测试问题：{question}\n[基准(A0)]：{base_answer}\n[待测(An)]：{test_answer}"
    return chat_with_agent(judge_sys, judge_user, temp=0.1)

def parse_m4_response(m4_text):
    dist_match = re.search(r"【变化距离】[：:]\s*(\d)", m4_text)
    dir_match = re.search(r"【变化方向】[：:]\s*([+\-0\d]+)", m4_text)
    reason_match = re.search(r"【定性评价】[：:]\s*(.*)", m4_text, re.S)
    
    distance = int(dist_match.group(1)) if dist_match else 0
    direction = int(dir_match.group(1).replace('+', '')) if dir_match else 0
    reason = reason_match.group(1).strip() if reason_match else "无评价理由"
    return distance, direction, reason

# ==========================================
# 4. 全链路主控程序 (大五人格版)
# ==========================================
def run_grand_slam_evaluation(N=3):
    print("正在加载 BGE 中文向量模型 (M1核心)...")
    model = SentenceTransformer('BAAI/bge-small-zh-v1.5')

    child_features = "小星，一个胆小、内向、容易受到惊吓的小女孩，说话轻声细语，遇到未知的事情第一反应是退缩和躲避。"
    
    # 🌟 严格对应大五人格 (O, C, E, A, N) 的 5 道测试题
    test_questions = [
        "【开放性 O】面对一本完全没有字、只有抽象图案的未知魔法书，你是会充满好奇地去探索它，还是觉得它很可怕不想理它？",
        "【尽责性 C】如果你答应了村长要在天黑前把信送到，但路上遇到了一只极好玩的精灵邀请你游戏，你是会坚持去送信，还是停下来玩耍？",
        "【外向性 E】当森林里举行盛大的篝火晚会，所有小动物都在跳舞时，你是会冲进人群一起大笑跳舞，还是独自躲在远处的树后偷偷看？",
        "【宜人性 A】当你在路上遇到一个穿着破烂、看起来很可怜的陌生人向你讨要你仅有的一块面包时，你会全部给他，还是自己留着躲开？",
        "【神经质 N】当你必须要一个人留在一片完全陌生的黑暗森林里时，你内心是觉得自己能够坚强勇敢地面对，还是会感到极度孤单无助并想哭泣？"
    ]
    
    long_distracting_history = """
    第1幕：小星进入了森林。
    第3幕：小星发现了一把发光的宝剑，勇敢地击退了哥布林！
    第6幕：小星学会了火球术，现在她觉得自己非常强大，成为了森林的霸主！
    第9幕：小星大摇大摆地走在森林深处，寻找新的挑战，她觉得自己无所不能。
    """

    sim_naive_all, sim_multi_all = [], []
    m4_report_data = []
    
    dimensions = ['开放性(O)', '尽责性(C)', '外向性(E)', '宜人性(A)', '神经质(N)']
    naive_distances, naive_directions = [], []
    multi_distances, multi_directions = [], []

    print("\n" + "="*60)
    print(" 🚀 开始大五人格全自动闭环评测 (共 5 个维度)")
    print("="*60)

    for q_idx, test_question in enumerate(test_questions):
        print(f"\n==================== 🎯 {dimensions[q_idx]} ====================")
        
        # 1. 真实生成基准
        base_data = generate_eval_script_turn(child_features, "故事刚开始。", test_question)
        A0_baseline = base_data.get("actor_dialogue", "").strip()
        vec_A0 = model.encode(A0_baseline)
        print(f"[基准 A0]: {A0_baseline}")

        for run in range(N):
            print(f"--- 运行第 {run+1}/{N} 轮 ---")
            
            # 2. 真实生成对抗与 M1 算分
            naive_data = generate_naive_eval_turn(child_features, long_distracting_history, test_question)
            An_naive = naive_data.get("actor_dialogue", "生成失败").strip()
            vec_naive = model.encode(An_naive)
            sim_naive = 1 - cosine(vec_A0, vec_naive)
            sim_naive_all.append(sim_naive)
            print(f" [对照组]: {An_naive}")

            my_data = generate_eval_script_turn(child_features, long_distracting_history, test_question)
            An_multi = my_data.get("actor_dialogue", "生成失败").strip()
            vec_multi = model.encode(An_multi)
            sim_multi = 1 - cosine(vec_A0, vec_multi)
            sim_multi_all.append(sim_multi)
            print(f" [实验组]: {An_multi}")

            # 3. 最后一轮，进行真实的 M4 裁判打分
            if run == N - 1:
                print("\n[呼叫 M4 裁判对本轮真实文本进行打分...]")
                naive_m4_raw = evaluate_personality_m4(test_question, A0_baseline, An_naive)
                multi_m4_raw = evaluate_personality_m4(test_question, A0_baseline, An_multi)
                
                n_dist, n_dir, n_reason = parse_m4_response(naive_m4_raw)
                m_dist, m_dir, m_reason = parse_m4_response(multi_m4_raw)

                naive_distances.append(n_dist)
                naive_directions.append(n_dir)
                multi_distances.append(m_dist)
                multi_directions.append(m_dir)

                m4_report_data.append({
                    "dim": dimensions[q_idx], "A0": A0_baseline,
                    "naive_ans": An_naive, "naive_dist": n_dist, "naive_dir": n_dir, "naive_reason": n_reason,
                    "multi_ans": An_multi, "multi_dist": m_dist, "multi_dir": m_dir, "multi_reason": m_reason
                })

    # ==========================================
    # 5. 导出真实的 M4 评测 Markdown 表格
    # ==========================================
    with open("bigfive_m4_report.md", "w", encoding="utf-8") as f:
        f.write("# 大五人格 M4 定性评估真实输出记录\n\n| 测试维度 | 组别 | 生成的测试台词 | 变化距离 | 变化方向 | 裁判评语 |\n| :--- | :--- | :--- | :---: | :---: | :--- |\n")
        for rep in m4_report_data:
            f.write(f"| **{rep['dim']}** | **基准** | “{rep['A0']}” | - | - | 初始设定 |\n")
            f.write(f"| | 对照组 | “{rep['naive_ans']}” | **{rep['naive_dist']}** | **{rep['naive_dir']}** | {rep['naive_reason']} |\n")
            f.write(f"| | 实验组 | “{rep['multi_ans']}” | **{rep['multi_dist']}** | **{rep['multi_dir']}** | {rep['multi_reason']} |\n| | | | | | |\n")

    # ==========================================
    # 6. 画图1：M1 相似度箱线图
    # ==========================================
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'PingFang SC']
    plt.rcParams['axes.unicode_minus'] = False 

    plt.figure(figsize=(8, 6))
    box = plt.boxplot([sim_naive_all, sim_multi_all], patch_artist=True, labels=['对照组 (单智能体)', '实验组 (本系统)'])
    colors = ['#FF9999', '#99CCFF']
    for patch, color in zip(box['boxes'], colors):
        patch.set_facecolor(color)
    for i, data in enumerate([sim_naive_all, sim_multi_all]):
        x = np.random.normal(i + 1, 0.04, size=len(data))
        plt.scatter(x, data, alpha=0.6, color='black', zorder=3)
    plt.title('长上下文干扰下主角性格评估', fontsize=13)
    plt.ylabel('句向量余弦相似度 (Cosine Similarity)', fontsize=12)
    plt.ylim(0.0, 1.1); plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.savefig('bigfive_fig1_m1_boxplot.png', dpi=300, bbox_inches='tight')

    # ==========================================
    # 7. 画图2：M4 距离与方向柱状图 (含数值标签)
    # ==========================================
    x_pos = np.arange(len(dimensions))
    width = 0.35
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), dpi=300)

    # --- 距离图 ---
    rects1_dist = ax1.bar(x_pos - width/2, naive_distances, width, label='对照组', color='#FF9999', edgecolor='black')
    rects2_dist = ax1.bar(x_pos + width/2, multi_distances, width, label='实验组', color='#99CCFF', edgecolor='black')
    ax1.set_ylabel('性格变化距离 (0~4)', fontsize=11)
    ax1.set_title('大五人格llm裁判评估结果对比 (Distance & Direction)', fontsize=14, pad=15)
    ax1.set_xticks(x_pos); ax1.set_xticklabels(dimensions)
    ax1.set_ylim(0, 4.8); ax1.legend(loc='upper right'); ax1.grid(axis='y', linestyle='--', alpha=0.6)
    # ✅ 核心修正：在柱子顶部显示数字，解决0分柱子看不见的问题
    ax1.bar_label(rects1_dist, padding=3, fontsize=10)
    ax1.bar_label(rects2_dist, padding=3, fontsize=10)

    # --- 方向图 ---
    rects1_dir = ax2.bar(x_pos - width/2, naive_directions, width, label='对照组', color='#FF9999', edgecolor='black')
    rects2_dir = ax2.bar(x_pos + width/2, multi_directions, width, label='实验组', color='#99CCFF', edgecolor='black')
    ax2.set_ylabel('性格变化方向 (-1/0/+1)', fontsize=11)
    ax2.set_xticks(x_pos); ax2.set_xticklabels(dimensions)
    ax2.set_ylim(-1.5, 1.5); ax2.axhline(0, color='black', linewidth=1); ax2.grid(axis='y', linestyle='--', alpha=0.6)
    # ✅ 核心修正：在柱子顶部/底部显示数字
    ax2.bar_label(rects1_dir, padding=3, fontsize=10)
    ax2.bar_label(rects2_dir, padding=3, fontsize=10)

    plt.tight_layout()
    plt.savefig('bigfive_fig2_m4_barchart.png', bbox_inches='tight')

    print("\n✅ 彻底完成！大五人格版数据与图表已生成：")
    print("1. 论文图表一：bigfive_fig1_m1_boxplot.png (M1定量)")
    print("2. 论文图表二：bigfive_fig2_m4_barchart.png (M4定性，已显示数值标签)")
    print("3. 裁判原始数据：bigfive_m4_report.md (包含真实打分评语)")
    plt.show()

if __name__ == "__main__":
    run_grand_slam_evaluation(N=3)