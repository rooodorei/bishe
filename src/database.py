# database.py
import sqlite3
import uuid
from datetime import datetime

DB_FILE = "storybook.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 绘本总表：一个 session_id 代表一整个平行宇宙树
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS storybooks (
            session_id TEXT PRIMARY KEY,
            theme TEXT,
            features TEXT,
            create_time TEXT
        )
    ''')
    
    # 书页表：加入 parent_id，形成树状图结构；加入 prompt 字段，避免内存缓存丢失
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            parent_id INTEGER,  -- ⭐ 指向上一页的 ID，如果是 0 或 NULL 则是根节点
            depth INTEGER,      -- 第几回合（深度）
            user_choice TEXT,
            narrator_text TEXT,
            actor_dialogue TEXT,
            action_prompt TEXT, -- ⭐ 暂存动作提示词
            scene_prompt TEXT,  -- ⭐ 暂存场景提示词
            image_url TEXT
        )
    ''')
    conn.commit()
    conn.close()

def create_storybook(session_id, theme, features):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO storybooks (session_id, theme, features, create_time) VALUES (?, ?, ?, ?)",
        (session_id, theme, features, create_time)
    )
    conn.commit()
    conn.close()

def add_page_node(session_id, parent_id, depth, user_choice, narrator_text, actor_dialogue, action_prompt, scene_prompt):
    """添加一个节点，并返回这个节点的专属 ID"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO pages 
           (session_id, parent_id, depth, user_choice, narrator_text, actor_dialogue, action_prompt, scene_prompt, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, parent_id, depth, user_choice, narrator_text, actor_dialogue, action_prompt, scene_prompt, "")
    )
    new_page_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_page_id

def update_page_image(page_id, image_url):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE pages SET image_url = ? WHERE id = ?", (image_url, page_id))
    conn.commit()
    conn.close()

def get_page(page_id):
    """获取单个节点信息"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE id = ?", (page_id,))
    page = cursor.fetchone()
    conn.close()
    return page

def get_storybook_info(session_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM storybooks WHERE session_id = ?", (session_id,))
    book = cursor.fetchone()
    conn.close()
    return book

def get_all_nodes(session_id):
    """【新功能】获取这棵树上的所有节点，交给前端画世界线"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE session_id = ? ORDER BY depth ASC", (session_id,))
    nodes = cursor.fetchall()
    conn.close()
    return [dict(n) for n in nodes]

def rebuild_llm_context(page_id):
    """【黑科技】顺着树干往上爬，找出当前节点所在的唯一时间线，重建记忆"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    path = []
    current_id = page_id
    
    # 🌟 功能 1：溯源找祖先（顺藤摸瓜）
    # 用一个 while 循环，从当前节点开始，不断向上找 parent_id，直到 parent_id 为 0（根节点）
    while current_id:
        cursor.execute("SELECT * FROM pages WHERE id = ?", (current_id,))
        node = cursor.fetchone()
        if not node: break
        path.append(node)
        current_id = node["parent_id"] # 把目光指向上一个节点，准备下一次循环
        
    conn.close()
    
    if not path: return None, [], []
    
    # 🌟 功能 2：时间线倒转
    # 因为我们是从下往上找的，列表里的顺序是【最新 -> 最老】
    # 使用 reverse() 把它反转成大模型习惯的阅读顺序【最老 -> 最新】
    path.reverse()
    
    # 获取这本绘本的全局设定（比如主题、主角长相）
    book = get_storybook_info(path[0]["session_id"])
    
    # 🌟 功能 3：组装给大模型看的“记忆剧本”
    # 第 1 句话永远是全局设定，确保大模型知道在这个世界里主角长什么样
    memory_list = [f"全局设定：故事主题是【{book['theme']}】。主角准备好冒险了。"]
    
    # 遍历刚才整理好的时间线，把玩家的选择和旁白拼成一句话，塞进记忆列表
    for p in path:
        if p["depth"] == 0:
            memory_list.append(f"故事开局：{p['narrator_text']}")
        else:
            memory_list.append(f"小朋友选择【{p['user_choice']}】，剧情：{p['narrator_text']}")
            
    # 🌟 功能 4：防止记忆过载（大模型很容易遗忘或者token超载）
    # 如果历史记录太长，我们只保留“全局设定(索引0)” + “最近的3次回合(切片[-3:])”
    if len(memory_list) > 4:
        memory_list = [memory_list[0]] + memory_list[-3:]
        
    # 返回：主角设定特征、整理好的记忆列表、完整的故事路径字典
    return book['features'], memory_list, [dict(p) for p in path]