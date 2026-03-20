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

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(WORKSPACE_ROOT, 'photos.sqlite3')
CACHE_DIR = os.path.join(WORKSPACE_ROOT, 'execution', 'cache')

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR, exist_ok=True)

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

@app.route("/media/<message_id>")
def proxy_media(message_id):
    """Bridge Discord API with aggressive local caching and streaming Range support."""
    cache_path = os.path.join(CACHE_DIR, message_id)
    
    # helper to get file info and guess mimetype
    def get_info():
        conn = get_db()
        row = conn.execute("SELECT file_name, channel_id FROM photos WHERE message_id=?", (message_id,)).fetchone()
        conn.close()
        return row

    photo = get_info()
    if not photo:
        return "Media metadata destroyed", 404

    # 1. Handle Cache Miss: Download from Discord first
    if not os.path.exists(cache_path):
        fresh_url = get_fresh_discord_attachment(photo["channel_id"], message_id)
        if not fresh_url:
            return "Failed to bridge native Discord API", 502
        try:
            r = requests.get(fresh_url, stream=True)
            if r.status_code == 200:
                with open(cache_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            else:
                return f"Discord CDN blocked fetch: {r.status_code}", 502
        except Exception as e:
            print(f"Fetch Error: {e}")
            return "Fetch failed", 500

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

if __name__ == "__main__":
    backfill_user_names()
    port = int(os.getenv("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=False)
