import hashlib
import sqlite3
import os
import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(WORKSPACE_ROOT, 'photos.sqlite3')

def get_db():
    return sqlite3.connect(DB_PATH)

def is_known_meme(file_hash: str) -> bool:
    """Check if the digital hash is inside the local blacklist database."""
    conn = get_db()
    cursor = conn.execute("SELECT 1 FROM meme_cache WHERE file_hash=?", (file_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_to_meme_cache(file_hash: str):
    """Add a confirmed meme fingerprint to the cache to ignore it forever."""
    if not file_hash: return
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO meme_cache (file_hash, date_added) VALUES (?, ?)", 
                 (file_hash, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def remove_from_meme_cache(file_hash: str):
    """Removes a meme fingerprint from cache for the Undo feature."""
    conn = get_db()
    conn.execute("DELETE FROM meme_cache WHERE file_hash=?", (file_hash,))
    conn.commit()
    conn.close()

def is_known_upload(file_hash: str) -> bool:
    """Check if the digital hash was already successfully uploaded."""
    conn = get_db()
    cursor = conn.execute("SELECT 1 FROM uploaded_cache WHERE file_hash=?", (file_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_to_uploaded_cache(file_hash: str, cloud_url: str):
    """Log an uploaded photo's signature so it isn't uploaded again."""
    if not file_hash: return
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO uploaded_cache (file_hash, cloud_url, date_added) VALUES (?, ?, ?)", 
                 (file_hash, cloud_url, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def remove_from_uploaded_cache(file_hash: str):
    """Removes an uploaded fingerprint from cache for the Undo feature."""
    conn = get_db()
    conn.execute("DELETE FROM uploaded_cache WHERE file_hash=?", (file_hash,))
    conn.commit()
    conn.close()

async def process_attachment(attachment) -> tuple[str, str]:
    """
    Returns a tuple of (Action, Hash).
    Action can be 'DISCARD', 'SAVE', 'REVIEW', or 'DUPLICATE'.
    """
    filename = attachment.filename.lower()
    
    if filename.endswith(".gif") or "tenor" in filename:
        return ("DISCARD", "")
        
    if not any(filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov']):
        return ("DISCARD", "")
        
    try:
        image_bytes = await attachment.read()
    except Exception:
        return ("DISCARD", "") 
        
    file_hash = hashlib.sha256(image_bytes).hexdigest()
    
    if is_known_meme(file_hash):
        return ("DISCARD", file_hash)
        
    if is_known_upload(file_hash):
        return ("DUPLICATE", file_hash)
        
    # Videos should unconditionally bypass the review queue and auto-save instantly
    if filename.endswith(".mp4") or filename.endswith(".mov"):
        return ("SAVE", file_hash) 
        
    if attachment.size >= 500_000:
        return ("SAVE", file_hash)
    else:
        return ("REVIEW", file_hash)
