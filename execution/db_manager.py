import sqlite3
import os

# Root of the workspace
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(WORKSPACE_ROOT, 'photos.sqlite3')

def get_connection():
    """Returns a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH)

def setup_database():
    """Sets up the initial tables for the photo archiver."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Stores valid photos mapped to their cloud URLs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT UNIQUE,
            channel_id TEXT,
            user_id TEXT,
            user_name TEXT,
            timestamp TEXT,
            cloud_url TEXT,
            file_name TEXT
        )
    ''')
    
    # Stores fingerprints of known memes or items pending review
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meme_cache (
            file_hash TEXT PRIMARY KEY,
            date_added TEXT,
            cloud_url TEXT,
            file_name TEXT,
            user_id TEXT,
            user_name TEXT,
            timestamp TEXT
        )
    ''')
    
    # Prevents duplicate archival of identical photos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uploaded_cache (
            file_hash TEXT PRIMARY KEY,
            cloud_url TEXT,
            date_added TEXT
        )
    ''')
    
    # Config table (e.g., storing the active photo_channel_id and review_channel_id)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()
    
    # Migration for existing databases
    try:
        cursor.execute("ALTER TABLE meme_cache ADD COLUMN cloud_url TEXT")
        cursor.execute("ALTER TABLE meme_cache ADD COLUMN file_name TEXT")
        cursor.execute("ALTER TABLE meme_cache ADD COLUMN user_id TEXT")
        cursor.execute("ALTER TABLE meme_cache ADD COLUMN user_name TEXT")
        cursor.execute("ALTER TABLE meme_cache ADD COLUMN timestamp TEXT")
    except sqlite3.OperationalError:
        # Columns already exist
        pass
        
    conn.commit()
    conn.close()
    print(f"Database setup and migration complete at {DB_PATH}")

def reset_all_data():
    """Wipes all user data tables but preserves the config bindings."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM photos")
    cursor.execute("DELETE FROM meme_cache")
    cursor.execute("DELETE FROM uploaded_cache")
    # We DO NOT delete from config so they don't have to redefine channels
    conn.commit()
    conn.close()

if __name__ == "__main__":
    setup_database()
