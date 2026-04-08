# database.py
import sqlite3
from datetime import datetime

DB_FILE = "storybook_archive.db"

def init_db():
    """初始化数据库，创建表结构"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 创建绘本总表 (一本完整的书)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS storybooks (
            session_id TEXT PRIMARY KEY,
            theme TEXT,
            features TEXT,
            create_time TEXT
        )
    ''')
    
    # 创建书页表 (书里的每一页)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            turn_index INTEGER,
            user_choice TEXT,
            narrator_text TEXT,
            actor_dialogue TEXT,
            image_url TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def create_storybook(session_id, theme, features):
    """新建一本绘本档案"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO storybooks VALUES (?, ?, ?, ?)', 
                   (session_id, theme, features, create_time))
    conn.commit()
    conn.close()

def add_page_text(session_id, turn_index, user_choice, narrator_text, actor_dialogue):
    """保存一页的文字内容"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO pages (session_id, turn_index, user_choice, narrator_text, actor_dialogue, image_url)
        VALUES (?, ?, ?, ?, ?, "")
    ''', (session_id, turn_index, user_choice, narrator_text, actor_dialogue))
    conn.commit()
    conn.close()

#def update_page_image(session_id, turn_index, image_url):
#    """当图片画好后，更新这一页的图片链接"""
#    conn = sqlite3.connect(DB_FILE)
#    cursor = conn.cursor()
#    cursor.execute('''
#        UPDATE pages SET image_url = ? WHERE session_id = ? AND turn_index = ?
#    ''', (image_url, session_id, turn_index))
#    conn.commit()
#    conn.close() 
def update_page_image(session_id, image_url):
    """当图片画好后，直接更新这本绘本最新一页的图片（无视页码，绝对不会错位）"""
    import sqlite3 # 确保导入了
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # SQL 找到这本绘本 ID 最大（也就是刚刚最新插入）的那一页，把图片塞进去
    cursor.execute('''
        UPDATE pages SET image_url = ? 
        WHERE id = (SELECT MAX(id) FROM pages WHERE session_id = ?)
    ''', (image_url, session_id))
    
    conn.commit()
    conn.close()



def get_full_storybook(session_id):
    """读取整本绘本的完整内容（可以用来做'我的书架'功能）"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT theme, features, create_time FROM storybooks WHERE session_id = ?', (session_id,))
    book_info = cursor.fetchone()
    
    cursor.execute('SELECT turn_index, user_choice, narrator_text, actor_dialogue, image_url FROM pages WHERE session_id = ? ORDER BY turn_index ASC', (session_id,))
    pages = cursor.fetchall()
    conn.close()
    
    if not book_info:
        return None
        
    return {
        "session_id": session_id,
        "theme": book_info[0],
        "features": book_info[1],
        "create_time": book_info[2],
        "pages": [
            {
                "page_num": p[0], "choice": p[1], "narrator": p[2], 
                "dialogue": p[3], "image": p[4]
            } for p in pages
        ]
    }

# 当这个文件被加载时，自动建表
init_db()