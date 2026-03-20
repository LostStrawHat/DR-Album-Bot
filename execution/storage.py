import os
import sqlite3
import datetime
from dotenv import load_dotenv
import asyncio

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Strip invalid placeholder URLs so the cloudinary library doesn't crash on import
if os.environ.get("CLOUDINARY_URL") == 'your_cloudinary_url_here':
    os.environ.pop("CLOUDINARY_URL", None)

import cloudinary
import cloudinary.uploader
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(WORKSPACE_ROOT, 'photos.sqlite3')

CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
if CLOUDINARY_URL and CLOUDINARY_URL != 'your_cloudinary_url_here':
    cloudinary.config() # Auto-picks up CLOUDINARY_URL env var

def log_photo_to_db(message_id: str, user_id: str, cloud_url: str, file_name: str):
    """Saves the final photo metadata URL map to our local SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO photos (message_id, user_id, timestamp, cloud_url, file_name) VALUES (?, ?, ?, ?, ?)",
        (str(message_id), str(user_id), datetime.datetime.now().isoformat(), cloud_url, file_name)
    )
    conn.commit()
    conn.close()

async def upload_to_cloudinary(attachment) -> str:
    """
    Takes a discord Attachment, uploads bytes to Cloudinary, returns the secure_url.
    If Cloudinary is not configured yet, falls back to a free local folder dump safely!
    """
    if not CLOUDINARY_URL or CLOUDINARY_URL == 'your_cloudinary_url_here':
        # Free Tier Fallback (Local File System Save)
        local_dir = os.path.join(WORKSPACE_ROOT, 'images')
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, attachment.filename)
        await attachment.save(local_path)
        return local_path

    # User configured Cloudinary! Upload the bytes:
    image_bytes = await attachment.read()
    
    loop = asyncio.get_event_loop()
    def do_upload():
        return cloudinary.uploader.upload(
            image_bytes,
            resource_type="auto",
            folder="discord_photos"
        )
        
    try:
        response = await loop.run_in_executor(None, do_upload)
        secure_url = response.get('secure_url', '')
        return secure_url
    except Exception as e:
        raise RuntimeError(f"Cloudinary Upload Error: {e}")
