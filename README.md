# 📸 Discord Memory Vault (Local-First Edition)

A beautifully optimized, high-performance photo and video archive system for your Discord community. Designed to run on a local machine (Mac, PC, or Raspberry Pi) and accessible globally via secure Cloudflare Tunnels.

## ✨ Core Features

### 🚀 Performance
- **Pillow Compression**: Automatically generates lightweight thumbnails for instant gallery loading.
- **OpenCV Video Posters**: Robust frame-extraction for videos (fallback from locally missing FFmpeg) ensuring consistent gallery previews.
- **Lazy Loading & Deferred Media**: Zero video data is downloaded until you hover or click, avoiding browser connection limits and making the UI extremely snappy.
- **Chunked File Streaming**: Zero-memory bulk downloads safely process massive HD video zip exports without crashing the lightweight server.

### 🛡️ Smart Archiving & Moderation
- **Hybrid Moderation**: Approve or discard items directly in Discord using ✅/❌ reactions, or use the high-volume Web Review Queue.
- **Discord Jump Links**: Quickly view the original message context inside the Discord application directly from the dashboard using the "Discord" icon.
- **Direct Link Sharing**: Copy permanent, absolute media URLs to your clipboard for sharing across all platforms—even if the original Discord attachment expires.
- **Meme Filtering**: Integrated hashing logic to catch and discard duplicates or zero-value memes.
- **Local-First Reliability**: All approved media is cached locally on your machine, ensuring the vault stays alive and healthy regardless of Discord's security rotations.
- **Gallery Delete & Blacklist**: Admins can delete items directly from the gallery with built-in confirmation dialogs, which automatically wipes the cache and adds the file signature to a permanent blacklist.
- **Server Nicknames**: Automatically captures and synchronizes server-specific nicknames for accurate attribution.

### 🌐 Secure Public Access
- **Strict Environment Validations**: Web server enforces hard-failures for missing keys—never falls back to default passwords.
- **Cloudflare Tunnels**: No port forwarding or static IP required.
- **Auto-Sync URL**: The bot automatically detects and synchronizes its public URL with Discord slash commands on every startup.

---

## 🛠️ Quick Setup (Local Deployment)

### 1. Prerequisites
- **Python 3.10+**
- **OpenCV** (required for video posters): automatically installed in the project `venv`. Fallback is used if FFmpeg is missing.
- **Cloudflare Tunnel binary** (`cloudflared_local` is provided for Mac, download ARM for RPi).

### 2. Environment Configuration
Create a `.env` file based on `.env.example`:
```env
DISCORD_TOKEN=your_token_here
ADMIN_PASSWORD=your_dashboard_password
SECRET_KEY=generate_a_random_string
PHOTO_CHANNEL_ID=your_id
REVIEW_CHANNEL_ID=your_id
```

### 3. Execution
Simply run the helper script:
```bash
sh run_local_public.sh
```
*Wait for the `✅ Public URL detected` message. The `/album` command in Discord will automatically be updated with the new link.*

---

## 🤖 Discord Commands

- `/album`: Get the latest public link to the vault.
- `/set_photo_channel`: Bind the bot to a specific channel.
- `/refresh_names`: Re-poll the Discord API to update all stored names to current server nicknames.
- `/backfill_legacy_links`: **[Repair Tool]** Scrapes history to restore missing Discord jump links for older "Legacy" vault entries.
- `/reset_database`: Wipe all records (Admins only).

---

## 📂 Project Structure
- `execution/bot.py`: The core Discord logic and reaction listeners.
- `execution/dashboard.py`: The Flask web server with Admin moderation tools.
- `execution/static/`: Premium Vanilla CSS & JS frontend.
- `execution/cache/`: Local media and thumbnail storage.

---
*Built with ❤️ for memories that last.*
