from dotenv import load_dotenv
import sqlite3
import os

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(WORKSPACE_ROOT, 'photos.sqlite3')

def get_db():
    return sqlite3.connect(DB_PATH)

def log_photo_to_db(message_id: int, channel_id: int, user_id: int, user_name: str, original_url: str, file_name: str, sent_date: str = ""):
    conn = get_db()
    
    # 1. Log the new photo using the latest identity
    conn.execute('''
        INSERT OR REPLACE INTO photos (message_id, channel_id, user_id, user_name, cloud_url, file_name, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (str(message_id), str(channel_id), str(user_id), user_name, original_url, file_name, sent_date))
    
    # 2. Propagate this fresh nickname/global_name to all historical records for this user
    # This ensures that if they change their Discord name, the dashboard updates their entire history!
    conn.execute("UPDATE photos SET user_name = ? WHERE user_id = ?", (user_name, str(user_id)))
    
    conn.commit()
    conn.close()

def remove_photo_from_db(message_id: int):
    conn = get_db()
    conn.execute("DELETE FROM photos WHERE message_id=?", (str(message_id),))
    conn.commit()
    conn.close()


