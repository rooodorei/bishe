# database.py
import sqlite3
import uuid
import json  # ⭐ 新增：用于把数组转成字符串存进数据库
from datetime import datetime

DB_FILE = "storybook.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS storybooks (
            session_id TEXT PRIMARY KEY,
            theme TEXT,
            features TEXT,
            create_time TEXT
        )
    ''')
    
    # ⭐ 新增 options_json 字段
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            parent_id INTEGER,  
            depth INTEGER,      
            user_choice TEXT,
            narrator_text TEXT,
            actor_dialogue TEXT,
            action_prompt TEXT, 
            scene_prompt TEXT,  
            image_url TEXT,
            options_json TEXT   -- ⭐ 专门用来存这回合大模型给出的选项
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

# ⭐ 参数中新增 options_list
def add_page_node(session_id, parent_id, depth, user_choice, narrator_text, actor_dialogue, action_prompt, scene_prompt, options_list):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # 把 Python 的列表转成 JSON 字符串存进去
    options_str = json.dumps(options_list, ensure_ascii=False) 
    
    cursor.execute(
        """INSERT INTO pages 
           (session_id, parent_id, depth, user_choice, narrator_text, actor_dialogue, action_prompt, scene_prompt, image_url, options_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, parent_id, depth, user_choice, narrator_text, actor_dialogue, action_prompt, scene_prompt, "", options_str)
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
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE session_id = ? ORDER BY depth ASC", (session_id,))
    nodes = cursor.fetchall()
    conn.close()
    
    # ⭐ 取出数据时，把 options_json 重新解析为真实的数组返回给前端
    result = []
    for n in nodes:
        node_dict = dict(n)
        try:
            node_dict["options"] = json.loads(node_dict.get("options_json") or "[]")
        except:
            node_dict["options"] = []
        result.append(node_dict)
    return result

def rebuild_llm_context(page_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    path = []
    current_id = page_id
    
    while current_id:
        cursor.execute("SELECT * FROM pages WHERE id = ?", (current_id,))
        node = cursor.fetchone()
        if not node: break
        path.append(node)
        current_id = node["parent_id"]
        
    conn.close()
    
    if not path: return None, [], []
    path.reverse()
    book = get_storybook_info(path[0]["session_id"])
    
    memory_list = [f"全局设定：故事主题是【{book['theme']}】。主角准备好冒险了。"]
    for p in path:
        if p["depth"] == 0:
            memory_list.append(f"故事开局：{p['narrator_text']}")
        else:
            memory_list.append(f"小朋友选择【{p['user_choice']}】，剧情：{p['narrator_text']}")
            
    if len(memory_list) > 4:
        memory_list = [memory_list[0]] + memory_list[-3:]
        
    return book['features'], memory_list, [dict(p) for p in path]