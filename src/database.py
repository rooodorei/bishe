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
    
    # 从叶子节点一路查找到根节点
    while current_id:
        cursor.execute("SELECT * FROM pages WHERE id = ?", (current_id,))
        node = cursor.fetchone()
        if not node: break
        path.append(node)
        current_id = node["parent_id"]
        
    conn.close()
    
    if not path: return None, [], []
    
    # 倒序，变成从根到叶子的正常时间线
    path.reverse()
    
    book = get_storybook_info(path[0]["session_id"])
    
    # 构建大模型记忆
    memory_list = [f"全局设定：故事主题是【{book['theme']}】。主角准备好冒险了。"]
    for p in path:
        if p["depth"] == 0:
            memory_list.append(f"故事开局：{p['narrator_text']}")
        else:
            memory_list.append(f"小朋友选择【{p['user_choice']}】，剧情：{p['narrator_text']}")
            
    if len(memory_list) > 4:
        memory_list = [memory_list[0]] + memory_list[-3:]
        
    return book['features'], memory_list, [dict(p) for p in path]