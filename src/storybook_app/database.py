"""SQLite 数据库访问层。

数据库保存三类数据：
1. `users`：多用户账号信息。
2. `storybooks`：绘本会话级信息，例如所属用户、标题、主题和主角特征。
3. `pages`：剧情节点级信息，例如父子关系、旁白、绘图提示词和图片 URL。

当前项目使用同步 SQLite 访问。对本地演示和毕业设计原型来说足够简单；如果后续并发量变大，
可以考虑迁移到 SQLAlchemy 或异步数据库访问。
"""

import json
import sqlite3
from datetime import datetime

from .config import DATA_DIR


# 数据库文件放在 data/ 下，避免和源码混在一起。
DB_FILE = DATA_DIR / "storybook.db"


def _now() -> str:
    """返回统一格式的当前时间字符串。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """把 sqlite3.Row 转成 dict。"""
    return dict(row) if row else None


def _ensure_storybook_columns(cursor: sqlite3.Cursor) -> None:
    """为旧数据库补齐多用户故事管理需要的新字段。"""
    cursor.execute("PRAGMA table_info(storybooks)")
    columns = {row[1] for row in cursor.fetchall()}

    if "user_id" not in columns:
        cursor.execute("ALTER TABLE storybooks ADD COLUMN user_id INTEGER")
    if "title" not in columns:
        cursor.execute("ALTER TABLE storybooks ADD COLUMN title TEXT")
    if "update_time" not in columns:
        cursor.execute("ALTER TABLE storybooks ADD COLUMN update_time TEXT")


def init_db():
    """初始化数据库表；若表已存在则不会覆盖原有数据。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            create_time TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS storybooks (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER,
            title TEXT,
            theme TEXT,
            features TEXT,
            create_time TEXT,
            update_time TEXT
        )
    ''')
    _ensure_storybook_columns(cursor)

    # 页面节点表：每一次剧情生成都会产生一个节点。
    # parent_id + depth 用于构造“剧情树”。
    # action_prompt 和 scene_prompt 是 LLM 输出的中文绘图提示词。
    # options_json 保存下一步选项，读取时会重新解析为 Python list。
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


def create_user(username: str, password_hash: str) -> int:
    """创建用户并返回用户 ID。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, create_time) VALUES (?, ?, ?)",
        (username, password_hash, _now()),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


def get_user_by_username(username: str) -> dict | None:
    """按用户名查询用户。"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = _row_to_dict(cursor.fetchone())
    conn.close()
    return user


def get_user_by_id(user_id: int) -> dict | None:
    """按用户 ID 查询用户。"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, create_time FROM users WHERE id = ?", (user_id,))
    user = _row_to_dict(cursor.fetchone())
    conn.close()
    return user


def create_storybook(session_id, theme, features, user_id=None, title=None):
    """创建一个新的绘本会话记录。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    create_time = _now()
    story_title = title or f"{theme}绘本"
    cursor.execute(
        """INSERT INTO storybooks
           (session_id, user_id, title, theme, features, create_time, update_time)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, story_title, theme, features, create_time, create_time),
    )
    conn.commit()
    conn.close()


def list_storybooks(user_id: int) -> list[dict]:
    """查询指定用户的全部绘本故事。"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """SELECT s.session_id, s.user_id, s.title, s.theme, s.features, s.create_time, s.update_time,
                  COUNT(p.id) AS page_count,
                  MAX(p.id) AS latest_page_id
           FROM storybooks s
           LEFT JOIN pages p ON p.session_id = s.session_id
           WHERE s.user_id = ?
           GROUP BY s.session_id
           ORDER BY COALESCE(s.update_time, s.create_time) DESC""",
        (user_id,),
    )
    stories = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return stories


def delete_storybook(user_id: int, session_id: str) -> bool:
    """删除指定用户名下的一本绘本及其剧情节点。"""
    if not user_owns_storybook(user_id, session_id):
        return False

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM storybooks WHERE session_id = ? AND user_id = ?", (session_id, user_id))
    conn.commit()
    conn.close()
    return True


def user_owns_storybook(user_id: int, session_id: str) -> bool:
    """判断绘本是否属于指定用户。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM storybooks WHERE session_id = ? AND user_id = ?", (session_id, user_id))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def touch_storybook(session_id: str) -> None:
    """更新绘本最后修改时间。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE storybooks SET update_time = ? WHERE session_id = ?", (_now(), session_id))
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
    """新增一个剧情节点，并返回新节点 ID。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # SQLite 没有原生 list 类型，所以选项列表以 JSON 字符串形式保存。
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
    touch_storybook(session_id)
    return new_page_id


def update_page_image(page_id, image_url):
    """把生成后的图片 URL 写入指定剧情节点。"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE pages SET image_url = ? WHERE id = ?", (image_url, page_id))
    cursor.execute(
        """UPDATE storybooks
           SET update_time = ?
           WHERE session_id = (SELECT session_id FROM pages WHERE id = ?)""",
        (_now(), page_id),
    )
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
    """查询一个绘本会话下的全部剧情节点。

    返回给前端前会把 `options_json` 解析成 `options` 字段，方便前端直接使用。
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pages WHERE session_id = ? ORDER BY depth ASC, id ASC", (session_id,))
    nodes = cursor.fetchall()
    conn.close()

    result = []
    for node in nodes:
        node_dict = dict(node)
        try:
            node_dict["options"] = json.loads(node_dict.get("options_json") or "[]")
        except Exception:
            # 即使某条历史数据的 options_json 损坏，也不要影响整棵树返回。
            node_dict["options"] = []
        result.append(node_dict)
    return result


def rebuild_llm_context(page_id):
    """从当前节点回溯到根节点，重建给大模型使用的上下文。

    LLM 不需要看到整棵树，只需要看到当前分支的前情提要。本函数会沿 `parent_id`
    从当前节点回溯到根节点，再反转为从根到当前的顺序。

    为了控制提示词长度，最终只保留：
    - 全局设定。
    - 最近 10 条剧情记忆。
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    path = []
    current_id = page_id

    # parent_id=0 表示到达根节点之前的终止位置。
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

    # 回溯得到的是“当前 -> 根”，反转后变成“根 -> 当前”。
    path.reverse()
    book = get_storybook_info(path[0]["session_id"])

    memory_list = [f"全局设定：故事主题是【{book['theme']}】。主角准备好冒险了。"]
    for page in path:
        if page["depth"] == 0:
            memory_list.append(f"故事开局：{page['narrator_text']}")
        else:
            memory_list.append(f"小朋友选择【{page['user_choice']}】，剧情：{page['narrator_text']}")

    if len(memory_list) > 11:
        memory_list = [memory_list[0]] + memory_list[-10:]

    return book["features"], memory_list, [dict(page) for page in path]
