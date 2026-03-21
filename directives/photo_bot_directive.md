# Discord Photo Archiver Bot - Architecture Directive

## Goal
A localized Discord bot that passively archives hangout photos and videos to local storage, while strictly filtering out internet memes directly inside Discord.

## Tools/Scripts to Use
- `execution/bot.py` (Main Discord listener, Slash commands, Hybrid Reaction Moderation UI, Discord logger hook)
- `execution/filter_logic.py` (Handles heuristic file-size checks and SQLite cache hashing logic)
- `execution/dashboard.py` (Flask server for high-volume moderation, secure public access, and gallery management)
- `execution/db_manager.py` (Creates the persistent local tables for meme, photo, and configuration caching)
- `execution/storage.py` (Legacy Cloudinary logic / environment variable extraction)

## Architecture & Foundational Learnings
- **Heuristics Over AI**: We heavily pivoted from HuggingFace to an offline 500KB size limit. Memes are notoriously small; photos from modern smartphones easily clear 1MB. Highly effective and completely free.
- **Meme Cache & Duplicate Shields**: We use SHA256 hashing specifically via `hashlib` to create fingerprints of successfully deployed photos and discarded meme cache components, creating infinite API-savings by intercepting duplicates.
- **Hybrid Moderation**: Moderation is handled via a 2-tier system. Individual items can be approved/discarded directly in Discord via ✅/❌ reactions in the `#admin-queue`. For high-volume days, a Web Review Queue provides a bulk management interface.
- **Channel ID Preservation**: To ensure media links remain refreshable via Discord's CDN API, we store the original `channel_id` in both the `photos` and `meme_cache` tables.
- **Server Nicknames**: The bot prioritizes server nicknames (`fetch_member`) over global display names for all attribution, ensuring the dashboard reflects the community's local identities.

## Outputs
- Persistent `photos.sqlite3` Database recording `photos`, `meme_cache`, `uploaded_cache`, and `config`.
- Local media and thumbnail cache in `execution/cache/`.
- Native Discord logging directly into `#bot-logs`.
- Custom Dashboard Link accessible via `/album` slash command.

## New Features & UI Optimizations
- **Gallery Delete & Blacklist**: Admins can wipe items from the dashboard. Deletion automatically converts the file hash into a permanent blacklist entry, preventing re-upload.
- **FFmpeg Fallback**: Thumbnail generation for videos requires `ffmpeg`. The code includes a graceful fallback that shows a broken icon/info message if the dependency is missing, without crashing the server.
- **Mobile Density**: Implementation of a 2-column gallery grid on mobile devices (via `repeat(2, 1fr)`) and reduced container padding to maximize information density.
- **Sticky UX**: The filter bar now uses `position: sticky` to remain accessible at the top of the screen during scrolling.
