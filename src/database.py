"""SQLite 数据库访问层。

数据库保存两类数据：
1. `storybooks`：绘本会话级信息，例如主题和主角特征。
2. `pages`：剧情节点级信息，例如父子关系、旁白、绘图提示词和图片 URL。
"""

import json
import sqlite3
from datetime import datetime


DB_FILE = "storybook.db"


def init_db():
    """初始化数据库表；若表已存在则不会覆盖原有数据。"""
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
            options_json TEXT
        )
    ''')
    conn.commit()
    conn.close()


def create_storybook(session_id, theme, features):
    """创建一个新的绘本会话记录。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO storybooks (session_id, theme, features, create_time) VALUES (?, ?, ?, ?)",
        (session_id, theme, features, create_time),
    )
    conn.commit()
    conn.close()


def add_page_node(
    session_id,
    parent_id,
    depth,
    user_choice,
    narrator_text,
    actor_dialogue,
    action_prompt,
    scene_prompt,
    options_list,
):
    """新增一个剧情节点，并返回新节点 ID。

    `options_list` 是 Python 列表，写入 SQLite 前需要序列化为 JSON 字符串。
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    options_str = json.dumps(options_list, ensure_ascii=False)

    cursor.execute(
        """INSERT INTO pages
           (session_id, parent_id, depth, user_choice, narrator_text, actor_dialogue, action_prompt, scene_prompt, image_url, options_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            parent_id,
            depth,
            user_choice,
            narrator_text,
            actor_dialogue,
            action_prompt,
            scene_prompt,
            "",
            options_str,
        ),
    )
    new_page_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_page_id


def update_page_image(page_id, image_url):
    """把生成后的图片 URL 写入指定剧情节点。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE pages SET image_url = ? WHERE id = ?", (image_url, page_id))
    conn.commit()
    conn.close()


def get_page(page_id):
    """按节点 ID 查询单个剧情节点。"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE id = ?", (page_id,))
    page = cursor.fetchone()
    conn.close()
    return page


def get_storybook_info(session_id):
    """按会话 ID 查询绘本基础信息。"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM storybooks WHERE session_id = ?", (session_id,))
    book = cursor.fetchone()
    conn.close()
    return book


def get_all_nodes(session_id):
    """查询一个绘本会话下的全部剧情节点。"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE session_id = ? ORDER BY depth ASC", (session_id,))
    nodes = cursor.fetchall()
    conn.close()

    result = []
    for node in nodes:
        node_dict = dict(node)
        try:
            node_dict["options"] = json.loads(node_dict.get("options_json") or "[]")
        except Exception:
            node_dict["options"] = []
        result.append(node_dict)
    return result


def rebuild_llm_context(page_id):
    """从当前节点回溯到根节点，重建给大模型使用的上下文。

    为了控制提示词长度，只保留全局设定和最近三段剧情记忆。
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    path = []
    current_id = page_id

    while current_id:
        cursor.execute("SELECT * FROM pages WHERE id = ?", (current_id,))
        node = cursor.fetchone()
        if not node:
            break
        path.append(node)
        current_id = node["parent_id"]

    conn.close()

    if not path:
        return None, [], []

    path.reverse()
    book = get_storybook_info(path[0]["session_id"])

    memory_list = [f"全局设定：故事主题是【{book['theme']}】。主角准备好冒险了。"]
    for page in path:
        if page["depth"] == 0:
            memory_list.append(f"故事开局：{page['narrator_text']}")
        else:
            memory_list.append(f"小朋友选择【{page['user_choice']}】，剧情：{page['narrator_text']}")

    if len(memory_list) > 4:
        memory_list = [memory_list[0]] + memory_list[-3:]

    return book["features"], memory_list, [dict(page) for page in path]
