import matplotlib.pyplot as plt
import numpy as np

# ==========================================
# 1. 输入你的真实评测数据
# ==========================================
# 模型名称
models = ['GPT-4o', 'DeepSeek-V3', 'Qwen-Max', 'Kimi']

# 距离检测准确率 Acc_dis (%)
acc_dis = [87.5, 85.0, 78.5, 75.0]  

# 方向检测准确率 Acc_dir (%)
acc_dir = [95.0, 92.5, 88.0, 85.0]  

# ==========================================
# 2. 设置图表样式 (学术论文风格)
# ==========================================
# 设置全局字体大小，方便论文阅读
plt.rcParams.update({'font.size': 12})

x = np.arange(len(models))  # 模型标签的 x 轴位置
width = 0.35  # 柱子的宽度

# 创建画布 (长宽比 10:6 比较适合论文)
fig, ax = plt.subplots(figsize=(10, 6))

# 画两组柱状图 (颜色使用了学术常用的沉稳蓝和清新绿)
rects1 = ax.bar(x - width/2, acc_dis, width, label='Distance Accuracy (Acc_dis)', color='#4C72B0', edgecolor='black')
rects2 = ax.bar(x + width/2, acc_dir, width, label='Direction Accuracy (Acc_dir)', color='#55A868', edgecolor='black')

# ==========================================
# 3. 添加说明文字和刻度
# ==========================================
ax.set_ylabel('Accuracy (%)', fontweight='bold')
ax.set_title('Comparison of LLM Performance on Personality Change Detection', pad=15, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels(models, fontweight='bold')
ax.set_ylim(0, 110) # y轴最高定为110，给顶部留出空间放图例和数值

# 添加图例
ax.legend(loc='upper right')

# 添加网格线，让数据更容易比对 (只留水平网格线，虚线)
ax.yaxis.grid(True, linestyle='--', alpha=0.7)
ax.set_axisbelow(True)

# ==========================================
# 4. 在柱子顶部显示具体数值
# ==========================================
def autolabel(rects):
    """在每个柱子上附加一个文本标签，显示其高度。"""
    for rect in rects:
        height = rect.get_height()
        ax.annotate(f'{height}%',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),  # 垂直向上偏移 3 个像素
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10)

autolabel(rects1)
autolabel(rects2)

# 自动调整布局，防止边缘文字被切掉
fig.tight_layout()

# ==========================================
# 5. 【核心】保存图表到本地 (用于论文)
# ==========================================
# 1. 保存为 PNG 格式 (dpi=300 满足大多数学术期刊的超清要求)
plt.savefig('llm_evaluation_results.png', dpi=300, bbox_inches='tight')
print("已保存高清图片: llm_evaluation_results.png (可直接插入 Word)")

# 2. 保存为 PDF 格式 (矢量图，无限放大不失真，强烈推荐用于 LaTeX)
plt.savefig('llm_evaluation_results.pdf', bbox_inches='tight')
print("已保存矢量图: llm_evaluation_results.pdf (推荐用于 LaTeX)")

# 弹出窗口预览图表
plt.show()