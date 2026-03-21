# Handover Note: Hybrid Moderation & Media Vault Enhancements

## Phase 2 Objective
Establish a unified, multi-tier moderation system using both Discord and Web interfaces, and optimize the gallery for local hosting and accurate server attribution.

## Key Changes Summary
1. **Hybrid Moderation System**:
   - **Discord Level**: The `#admin-queue` now supports ✅ and ❌ reactions. Approving an item via Discord correctly preserves its source metadata and anchors it to the vault.
   - **Web Level**: A dedicated `/review` dashboard handles bulk moderation with glassmorphism UI and multi-select.
   - **Persistence**: Both systems use a unified `channel_id` preservation logic in `photos.sqlite3` to ensure Discord CDN links never break.

2. **Database & ID Handling**:
   - Upgraded `meme_cache` and `photos` tables to include `channel_id`.
   - Web-approved items now use their original source `channel_id` instead of a placeholder, allowing permanent Discord link refreshing.
   - Legacy fallback: Older `web-` prefixed items without channel data now safely fall back to their stored `cloud_url`.

3. **Gallery Optimization**:
   - **Delete & Blacklist**: Web dashboard now includes an `/api/delete` endpoint. Deleting an item wipes the disk cache and auto-blacklists the file hash.
   - **Server Nicknames**: All attribution now strictly uses `interaction.guild.fetch_member()` to prioritize server-specific nicknames over global names.
   - **FFmpeg posters**: Extracts frame previews from videos. Graceful fallback implemented if `ffmpeg` is missing on the host.

4. **Service Autonomy**:
   - The bot (`bot.py`) now serves as the primary process, automatically spawning the Flask dashboard and Cloudflare tunnel on startup.

## Critical Setup Information
For new instances (e.g., secondary Mac or Raspberry Pi):
1. **PULL** latest code (`main`).
2. **ENVIRONMENT**: Ensure `DISCORD_TOKEN`, `ADMIN_PASSWORD`, and `SECRET_KEY` are in `.env`.
3. **MIGRATE**: Run `venv/bin/python execution/db_manager.py` to reconcile schema.
4. **DEPENDENCIES**: Install `ffmpeg` for video support (`brew install ffmpeg`).

## Current Status
- **Bot**: Online and listening for media.
- **Moderation**: Syncing perfectly between Discord Reactions and Web Dashboard.
- **Gallery**: Accessible via Cloudflare tunnel URL (see `#bot-logs` or `/album` command).
