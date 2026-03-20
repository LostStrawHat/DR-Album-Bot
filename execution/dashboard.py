import sqlite3
import os
import io
import zipfile
from flask import Flask, jsonify, request, send_file, render_template, redirect, session
from flask_cors import CORS
from dotenv import load_dotenv
import requests
from functools import wraps
import re
import subprocess

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(WORKSPACE_ROOT, 'photos.sqlite3')
CACHE_DIR = os.path.join(WORKSPACE_ROOT, 'execution', 'cache')
THUMB_DIR = os.path.join(WORKSPACE_ROOT, 'execution', 'cache', 'thumbnails')

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)
if not os.path.exists(THUMB_DIR):
    os.makedirs(THUMB_DIR, exist_ok=True)

# Mount the Discord Bot Token securely into the Dashboard memory to act as a stealth API proxy
load_dotenv(os.path.join(WORKSPACE_ROOT, '.env'), override=True)
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-12345")
CORS(app)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Admin password bypassed by user request for easy sharing
        return f(*args, **kwargs)
    return decorated_function

@app.route("/review")
def review_page():
    return render_template("review.html")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    if data.get("password") == ADMIN_PASSWORD:
        session['is_admin'] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid password"}), 401

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.pop('is_admin', None)
    return jsonify({"success": True})

@app.route("/api/auth/status")
def auth_status():
    return jsonify({"is_admin": session.get('is_admin', False)})

@app.route("/api/photos")
def api_get_photos():
    conn = get_db()
    # Explicitly ORDER BY original discord timestamp instead of archival order (ROWID)
    photos = conn.execute("SELECT message_id, user_id, user_name, cloud_url, file_name, timestamp, ROWID as id FROM photos ORDER BY timestamp DESC").fetchall()
    conn.close()
    
    res = []
    for p in photos:
        raw_ts = p["timestamp"] or ""
        # Dashboard displays the first 10 chars (YYYY-MM-DD) for simplicity
        date_only = raw_ts[:10] if raw_ts else "Unknown"
        res.append({
            "id": p["message_id"],
            "user_id": p["user_id"],
            "user_name": p["user_name"] or f"User {p['user_id']}",
            "file_name": p["file_name"],
            "sent_date": date_only,
            "sent_timestamp": raw_ts,
            "proxy_url": f"/media/{p['message_id']}",
            "is_video": p["file_name"].lower().endswith(('.mp4', '.mov'))
        })
    return jsonify(res)

@app.route("/api/authors")
def api_get_authors():
    conn = get_db()
    authors = conn.execute("SELECT DISTINCT user_id, user_name FROM photos").fetchall()
    conn.close()
    return jsonify([{"id": a["user_id"], "name": a["user_name"] or f"User {a['user_id']}"} for a in authors])

@app.route("/api/dates")
def api_get_dates():
    conn = get_db()
    dates = conn.execute("SELECT DISTINCT SUBSTR(timestamp, 1, 10) as d FROM photos WHERE timestamp != '' ORDER BY d DESC").fetchall()
    conn.close()
    return jsonify([row["d"] for row in dates])

import time

_url_cache = {}

def get_fresh_discord_attachment(channel_id, composite_id):
    """Hits the Discord JSON API with the Bot Token to mint a fresh 24-hour expiring CDN link on the fly!"""
    now = time.time()
    
    # 1. Use cached URL if it hasn't expired (valid for 24h, we cache for 23h)
    if composite_id in _url_cache:
        cached_url, expiry = _url_cache[composite_id]
        if now < expiry:
            return cached_url

    # The composite_id is `{message.id}-{attachment.id}`
    # Fallback to pure message_id if migrating from older single-attachment schema
    parts = str(composite_id).split("-")
    msg_id = parts[0]
    attach_id = parts[1] if len(parts) > 1 else None

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{msg_id}"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    
    # 2. Fetch with automatic Retry/Backoff if Discord rate-limits us (429 Too Many Requests)
    for _ in range(3):
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            data = r.json()
            attachments = data.get("attachments", [])
            for att in attachments:
                if not attach_id or str(att["id"]) == attach_id:
                    fresh_url = att["url"]
                    # Cache for 23 hours (82800 seconds)
                    _url_cache[composite_id] = (fresh_url, now + 82800)
                    return fresh_url
            return None
        elif r.status_code == 429:
            retry_after = r.json().get("retry_after", 1.0)
            print(f"Discord API 429 Rate Limit hit. Backing off for {retry_after}s...")
            time.sleep(retry_after)
        else:
            break
            
    return None

import mimetypes
import io
from PIL import Image

def get_db_info(message_id):
    conn = get_db()
    # The frontend passes `{message_id}-{attachment_id}` since Discord allows multiple attachments per message.
    # We stored the same composite ID in the `message_id` column during log_photo_to_db.
    row = conn.execute("SELECT file_name, channel_id FROM photos WHERE message_id=?", (str(message_id),)).fetchone()
    conn.close()
    return row

def ensure_local_cache(message_id, photo):
    """Ensures the original high-res file is cached from Discord."""
    cache_path = os.path.join(CACHE_DIR, message_id)
    if not os.path.exists(cache_path):
        print(f"[DEBUG] Cache miss for {message_id}, fetching fresh URL...")
        fresh_url = get_fresh_discord_attachment(photo["channel_id"], message_id)
        if not fresh_url:
            print(f"[DEBUG] Failed to get fresh URL for {message_id}")
            return None
        try:
            r = requests.get(fresh_url, stream=True)
            if r.status_code == 200:
                with open(cache_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"[DEBUG] Successfully cached original to {cache_path}")
                return cache_path
            else:
                print(f"[DEBUG] Discord CDN returned {r.status_code} for {fresh_url}")
                return None
        except Exception as e:
            print(f"[DEBUG] Fetch Error: {e}")
            return None
    return cache_path

@app.route("/thumbnail/<message_id>")
def proxy_thumbnail(message_id):
    """Serves a lightweight, compressed thumbnail of the image for the gallery grid."""
    photo = get_db_info(message_id)
    if not photo:
        return "Media metadata destroyed", 404

    file_name = photo["file_name"].lower()
    is_video = file_name.endswith(('.mp4', '.mov'))
    
    thumb_path = os.path.join(THUMB_DIR, f"{message_id}.jpg")
    
    # 1. Provide cached thumbnail immediately if it exists
    if os.path.exists(thumb_path):
        return send_file(thumb_path, mimetype='image/jpeg', max_age=31536000)

    # 2. Guarantee the original asset is cached offline
    original_cache_path = ensure_local_cache(message_id, photo)
    if not original_cache_path:
        return "Failed to bridge native Discord API", 502

    # 3. Generate the thumbnail on the fly
    try:
        if is_video:
            # Use FFmpeg to extract a frame at 1s (or 0s if it fails)
            # -ss 1.0 (seek to 1s) -i (input) -frames:v 1 (one frame) -q:v 2 (high quality jpg)
            cmd = [
                'ffmpeg', '-y', 
                '-ss', '1.0', 
                '-i', original_cache_path, 
                '-frames:v', '1', 
                '-q:v', '4', 
                thumb_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        else:
            with Image.open(original_cache_path) as img:
                # Convert to RGB if necessary (e.g. for PNGs with transparency)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # Heavy compression logic: Max 300x300
                img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                img.save(thumb_path, "JPEG", quality=65, optimize=True)
        
        return send_file(thumb_path, mimetype='image/jpeg', max_age=31536000)
    except Exception as e:
        print(f"Thumbnail generation failed for {message_id}: {e}")
        # If FFmpeg fails (e.g. video too short), try seeking to 0
        if is_video:
            try:
                cmd_fallback = ['ffmpeg', '-y', '-i', original_cache_path, '-frames:v', '1', '-q:v', '4', thumb_path]
                subprocess.run(cmd_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return send_file(thumb_path, mimetype='image/jpeg', max_age=31536000)
            except:
                pass
        
        # Final graceful fallback: serve original
        return redirect(f"/media/{message_id}")


@app.route("/media/<message_id>")
def proxy_media(message_id):
    """Bridge Discord API with aggressive local caching and streaming Range support."""
    photo = get_db_info(message_id)
    if not photo:
        return "Media metadata destroyed", 404

    cache_path = ensure_local_cache(message_id, photo)
    if not cache_path:
        return "Failed to bridge native Discord API", 502

    # 2. Stream from Local Cache with Range Support
    guessed_type, _ = mimetypes.guess_type(photo["file_name"])
    mimetype = guessed_type or 'application/octet-stream'
    
    file_size = os.path.getsize(cache_path)
    range_header = request.headers.get('Range', None)
    
    if not range_header:
        # Standard full-file response
        return send_file(
            cache_path,
            mimetype=mimetype,
            max_age=31536000
        )

    # Range request (Browser wanting only part of the file, common for videos)
    try:
        byte1, byte2 = 0, None
        range_match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            byte1 = int(range_match.group(1))
            if range_match.group(2):
                byte2 = int(range_match.group(2))
        
        if byte2 is None:
            byte2 = file_size - 1
        if byte2 >= file_size:
            byte2 = file_size - 1
            
        length = byte2 - byte1 + 1
        
        def generate():
            with open(cache_path, 'rb') as f:
                f.seek(byte1)
                remaining = length
                while remaining > 0:
                    chunk_size = min(remaining, 8192)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)

        resp = app.response_class(generate(), 206, mimetype=mimetype, direct_passthrough=True)
        resp.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
        resp.headers.add('Accept-Ranges', 'bytes')
        resp.headers.add('Content-Length', str(length))
        resp.headers.add('Cache-Control', 'public, max-age=31536000')
        return resp
    except Exception as e:
        print(f"Streaming Error: {e}")
        return send_file(cache_path, mimetype=mimetype)

@app.route("/api/download_bulk", methods=["POST"])
def bulk_download():
    req = request.json
    ids = req.get("message_ids", [])
    if not ids:
        return "No IDs", 400
        
    conn = get_db()
    placeholders = ",".join("?" * len(ids))
    photos = conn.execute(f"SELECT message_id, channel_id, file_name FROM photos WHERE message_id IN ({placeholders})", ids).fetchall()
    conn.close()
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for p in photos:
            try:
                fresh_url = get_fresh_discord_attachment(p["channel_id"], p["message_id"])
                if fresh_url:
                    r = requests.get(fresh_url, stream=True)
                    if r.status_code == 200:
                        zf.writestr(p["file_name"], r.content)
            except Exception as e:
                print(f"Failed skipping bulk zip entry bridging Discord API: {e}")

    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='discord_memory_vault.zip'
    )

def backfill_user_names():
    """One-time migration: fetch real Discord server nicknames for any records missing user_name."""
    if not DISCORD_TOKEN:
        return
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT user_id FROM photos WHERE user_name IS NULL OR user_name = ''").fetchall()
    if not rows:
        conn.close()
        return
    
    # Get guild_id from config (set by the bot on startup)
    guild_row = conn.execute("SELECT value FROM config WHERE key='guild_id'").fetchone()
    guild_id = guild_row["value"] if guild_row else None
    
    print(f"[Backfill] Found {len(rows)} user(s) missing names. Fetching from Discord API...")
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    
    for row in rows:
        uid = row["user_id"]
        name = None
        
        # 1. Try the Guild Members endpoint first to get the server nickname
        if guild_id:
            try:
                r = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/members/{uid}", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    # nick = server nickname, user.global_name = display name, user.username = handle
                    name = data.get("nick") or data.get("user", {}).get("global_name") or data.get("user", {}).get("username")
            except Exception as e:
                print(f"[Backfill] Guild member lookup failed for {uid}: {e}")
        
        # 2. Fallback to global user endpoint if guild lookup didn't yield a name
        if not name:
            try:
                r = requests.get(f"https://discord.com/api/v10/users/{uid}", headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    name = data.get("global_name") or data.get("username")
            except Exception as e:
                print(f"[Backfill] User lookup failed for {uid}: {e}")
        
        if name:
            conn.execute("UPDATE photos SET user_name = ? WHERE user_id = ? AND (user_name IS NULL OR user_name = '')", (name, uid))
            print(f"[Backfill] {uid} -> {name}")
        else:
            print(f"[Backfill] Could not resolve name for {uid}")
            
    conn.commit()
    conn.close()
    print("[Backfill] Done!")

@app.route("/api/review/photos")
def api_get_review_photos():
    """Returns all photos currently in the review queue (meme_cache)."""
    conn = get_db()
    # Ensure we only show items that have a cloud_url stored
    photos = conn.execute("SELECT file_hash, date_added, cloud_url, file_name, user_name, timestamp FROM meme_cache WHERE cloud_url IS NOT NULL ORDER BY date_added DESC").fetchall()
    conn.close()
    
    res = []
    for p in photos:
        res.append({
            "file_hash": p["file_hash"],
            "date_added": p["date_added"],
            "cloud_url": p["cloud_url"],
            "file_name": p["file_name"],
            "user_name": p["user_name"] or "Unknown User",
            "timestamp": p["timestamp"]
        })
    return jsonify(res)

@app.route("/api/review/approve", methods=["POST"])
def api_approve_photos():
    """Moves selected photos from review queue to the main vault."""
    data = request.json
    hashes = data.get("hashes", [])
    if not hashes:
        return jsonify({"status": "error", "message": "No photos selected"}), 400
        
    conn = get_db()
    processed = 0
    for h in hashes:
        # Get metadata from meme_cache
        row = conn.execute("SELECT cloud_url, file_name, user_id, user_name, timestamp FROM meme_cache WHERE file_hash=?", (h,)).fetchone()
        if row:
            # 1. Add to main photos table
            # We use a special message_id prefix to indicate it was a web-approved item
            conn.execute('''
                INSERT OR IGNORE INTO photos (message_id, channel_id, user_id, user_name, timestamp, cloud_url, file_name)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (f"web-{h[:12]}", "web-review", row["user_id"], row["user_name"], row["timestamp"], row["cloud_url"], row["file_name"]))
            
            # 2. Add to uploaded_cache to prevent future duplicates
            conn.execute("INSERT OR IGNORE INTO uploaded_cache (file_hash, cloud_url, date_added) VALUES (?, ?, ?)",
                         (h, row["cloud_url"], row["timestamp"]))
            
            # 3. Remove from meme_cache
            conn.execute("DELETE FROM meme_cache WHERE file_hash=?", (h,))
            processed += 1
            
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "processed": processed})

@app.route("/api/review/blacklist", methods=["POST"])
def api_blacklist_photos():
    """Confirms items should stay blacklisted (strips metadata to save space)."""
    data = request.json
    hashes = data.get("hashes", [])
    if not hashes:
        return jsonify({"status": "error", "message": "No photos selected"}), 400
        
    conn = get_db()
    for h in hashes:
        # Keep the hash but wipe the metadata to save DB space (converted to a "permanent" blacklist)
        conn.execute("UPDATE meme_cache SET cloud_url=NULL, file_name=NULL, user_id=NULL, user_name=NULL, timestamp=NULL WHERE file_hash=?", (h,))
            
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "processed": len(hashes)})

if __name__ == "__main__":
    backfill_user_names()
    port = int(os.getenv("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
