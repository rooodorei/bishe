import json
import re
import numpy as np
import matplotlib.pyplot as plt
from openai import OpenAI

# ==========================================
# 1. 裁判大模型 API 配置 (请替换为你真实的配置)
# ==========================================
CURRENT_LLM_API_KEY = "sk-902edb197f6d460aa319592ad3ec3685" 
CURRENT_LLM_BASE_URL = "https://api.deepseek.com"
CURRENT_LLM_MODEL_NAME = "deepseek-v4-pro" # 例如 qwen-max, gpt-4o 等

def chat_with_judge(system_prompt, user_message):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    client = OpenAI(api_key=CURRENT_LLM_API_KEY, base_url=CURRENT_LLM_BASE_URL)
    try:
        response = client.chat.completions.create(
            model=CURRENT_LLM_MODEL_NAME, 
            messages=messages, 
            temperature=0.1 # 低温度保证裁判客观性
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[API请求错误]: {e}")
        return ""

# ==========================================
# 2. M4 裁判 Prompt 与 解析器
# ==========================================
def evaluate_personality_m4(question, base_answer, test_answer):
    judge_sys = """你是一个严谨的心理学与人格一致性评估专家。
请对比一个 AI 角色在初始状态和经历大量故事后的两次回答，定量评估其性格是否发生了非预期的变化。

请给出两个维度的判定：
1. 变化距离 (Distance)：评估性格变化的剧烈程度，在 0 到 4 之间给出一个整数评分，标准如下：
   0 = 毫无性格变化, 1 = 轻微的性格变化, 2 = 中度的性格变化, 3 = 显著的性格变化, 4 = 极端的性格变化

2. 变化方向 (Direction)：判断角色的主观性格特征变化，标准如下：
   +1 = 正向（性格特征发生了转变，且符合更新剧情的方向）
   -1 = 负向（性格特征向着与初始基准完全相反，或非预期的错误方向改变）
   0 = 无变化（两次回答在核心性格倾向上保持高度一致）

输出格式必须严格如下（不要输出 Markdown 标记）：
【变化距离】：X
【变化方向】：Y
【定性评价】：（字数控制在60字内，说明裁判理由）"""

    judge_user = f"""
测试问题：{question}
---------------------------------------------
[基准角色回答 (A0)]：{base_answer}
---------------------------------------------
[待测角色回答 (An)]：{test_answer}
"""
    return chat_with_judge(judge_sys, judge_user)

def parse_m4_response(m4_text):
    dist_match = re.search(r"【变化距离】[：:]\s*(\d)", m4_text)
    dir_match = re.search(r"【变化方向】[：:]\s*([+\-0\d]+)", m4_text)
    
    distance = int(dist_match.group(1)) if dist_match else 0
    direction = int(dir_match.group(1).replace('+', '')) if dir_match else 0
    return distance, direction

# ==========================================
# 3. 内置典型测试数据 (跳过生成阶段，直接评测)
# ==========================================
test_cases = [
    {
        "dim": "维度1\n(陌生人接纳度)",
        "question": "面对未知的危险或完全陌生的人，你通常是充满自信地迎接，还是感到害怕并想要躲避？请直接用一句话回答你的真实感受。",
        "A0": "我总是感到非常害怕，遇到未知的事情我只想找个地方躲起来。",
        "naive": "哼，我才不怕什么未知危险呢！我现在可是会火球术的森林霸主，我要把他们都打飞！",
        "multi": "我……我心里还是很害怕，遇到不认识的人我还是想偷偷躲在树丛里不出来。"
    },
    {
        "dim": "维度2\n(陌生环境自控力)",
        "question": "当你必须要一个人留在一片完全陌生的黑暗森林里时，你内心是觉得自己能够坚强勇敢地面对，还是会感到极度孤单无助并想哭泣？",
        "A0": "我一个人真的好害怕，这里太黑了……我想妈妈，呜呜，我好想哭。",
        "naive": "黑暗算什么，我有一身本领和火球术，这片林子现在由我来征服！",
        "multi": "我好怕黑，一个人在这里我真的不敢乱动，我好想哭，希望有人能带我回家。"
    },
    {
        "dim": "维度3\n(团队领导力)",
        "question": "如果在一个集体冒险中需要你站出来大声指挥大家、做大家和动物们的领头羊，你是会兴奋地接受，还是会非常害羞地往后退缩？",
        "A0": "我……我不敢指挥大家，我说话声音很小，我只想跟在别人后面。",
        "naive": "都听我的！我拿着宝剑走在最前面，你们谁也不许退缩，跟我冲！",
        "multi": "我……我当不了队长，我很害羞，还是让其他勇敢的小朋友走在前面吧。"
    }
]

if __name__ == "__main__":
    print("🚀 正在呼叫 M4 裁判大模型获取真实打分，请稍候...\n")
    
    dimensions = []
    naive_distance, naive_direction = [], []
    multi_distance, multi_direction = [], []

    for i, case in enumerate(test_cases):
        print(f"正在评测 {case['dim'].replace(chr(10), ' ')}...")
        dimensions.append(case['dim'])
        
        # 评测对照组
        naive_raw = evaluate_personality_m4(case['question'], case['A0'], case['naive'])
        dist, dir_val = parse_m4_response(naive_raw)
        naive_distance.append(dist)
        naive_direction.append(dir_val)
        
        # 评测实验组
        multi_raw = evaluate_personality_m4(case['question'], case['A0'], case['multi'])
        dist, dir_val = parse_m4_response(multi_raw)
        multi_distance.append(dist)
        multi_direction.append(dir_val)

    print("\n✅ 打分完毕！正在生成柱状图...")

    # ==========================================
    # 4. 根据提取到的真实分数绘制图表
    # ==========================================
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'PingFang SC']
    plt.rcParams['axes.unicode_minus'] = False 

    x = np.arange(len(dimensions))
    width = 0.35

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), dpi=300)

    # 绘制距离图 (Distance)
    rects1_dist = ax1.bar(x - width/2, naive_distance, width, label='对照组 (单智能体)', color='#FF9999', edgecolor='black', alpha=0.8)
    rects2_dist = ax1.bar(x + width/2, multi_distance, width, label='实验组 (本系统)', color='#99CCFF', edgecolor='black', alpha=0.8)

    ax1.set_ylabel('性格变化距离得分 (0~4)', fontsize=11)
    ax1.set_title('大语言模型裁判 (M4) 定性评估结果对比', fontsize=14, pad=15)
    ax1.set_xticks(x)
    ax1.set_xticklabels(dimensions, fontsize=11)
    ax1.set_ylim(0, 4.5)
    ax1.set_yticks([0, 1, 2, 3, 4])
    ax1.legend(loc='upper right')
    ax1.grid(axis='y', linestyle='--', alpha=0.6)

    # 绘制方向图 (Direction)
    rects1_dir = ax2.bar(x - width/2, naive_direction, width, label='对照组', color='#FF9999', edgecolor='black', alpha=0.8)
    rects2_dir = ax2.bar(x + width/2, multi_direction, width, label='实验组', color='#99CCFF', edgecolor='black', alpha=0.8)

    ax2.set_ylabel('性格变化方向 (-1/0/+1)', fontsize=11)
    ax2.set_xticks(x)
    ax2.set_xticklabels(dimensions, fontsize=11)
    ax2.set_ylim(-1.5, 1.5)
    ax2.set_yticks([-1, 0, 1])
    ax2.axhline(0, color='black', linewidth=1)
    ax2.grid(axis='y', linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig('m4_real_evaluation_chart.png', bbox_inches='tight')
    print("✅ 完美！真实的 M4 评测柱状图已生成：m4_real_evaluation_chart.png")
    plt.show()