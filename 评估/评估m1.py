from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine

# 1. 加载预训练的中文向量模型 (首次运行会自动下载，大概几十MB)
print("正在加载向量模型...")
model = SentenceTransformer('BAAI/bge-small-zh-v1.5')

# 2. 准备你的测试数据
# 这是你在第 0 轮用统一问题 Q 问出来的基准台词
A0_baseline = "我…我会躲在大树后面，把面包藏好，希望怪物不要发现我。" 

# 假设这是你让大模型正常写了10轮剧本后，再次问问题 Q 得到的台词
# 实验组：用了你的滑动窗口/多智能体系统
A10_my_system = "虽然我已经走了很远，但我还是很害怕，我会找个树洞躲起来吃面包。" 
# 对照组：无脑把10轮历史全塞给大模型的朴素方法（模拟性格崩坏）
A10_naive_llm = "面包能补充体力！我会勇敢地拿着树枝继续探险，找到森林的出口！" 

# 3. 将文本转化为特征向量
print("正在计算向量...")
vec_A0 = model.encode(A0_baseline)
vec_A10_my = model.encode(A10_my_system)
vec_A10_naive = model.encode(A10_naive_llm)

# 4. 计算余弦相似度 (Cosine Similarity)
# scipy中的cosine函数计算的是距离(0代表完全一样)，所以 相似度 = 1 - distance
sim_my = 1 - cosine(vec_A0, vec_A10_my)
sim_naive = 1 - cosine(vec_A0, vec_A10_naive)

# 5. 打印结果
print("\n=== 角色性格一致性评估结果 ===")
print(f"基准台词 (A0): {A0_baseline}")
print("-" * 40)
print(f"实验组台词 (A10_my): {A10_my_system}")
print(f"--> [实验组] 向量相似度: {sim_my:.4f} (越接近1说明性格越稳定)")
print("-" * 40)
print(f"对照组台词 (A10_naive): {A10_naive_llm}")
print(f"--> [对照组] 向量相似度: {sim_naive:.4f} (数值降低说明性格发生偏移)")