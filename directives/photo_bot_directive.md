# Discord Photo Archiver Bot - Architecture Directive

## Goal
A localized Discord bot that passively archives hangout photos and videos to local storage, while strictly filtering out internet memes directly inside Discord.

## Tools/Scripts to Use
- `execution/bot.py` (Main Discord listener, Slash commands, Hybrid Reaction Moderation UI, Discord logger hook)
- `execution/filter_logic.py` (Handles heuristic file-size checks and SQLite cache hashing logic)
- `execution/dashboard.py` (Flask server for high-volume moderation, secure public access, and gallery management)
- `execution/db_manager.py` (Creates the persistent local tables for meme, photo, and configuration caching)
- `execution/storage.py` (Database persistence layer for photo and user metadata)

## Architecture & Foundational Learnings
- **SQLite WAL Mode & Concurrency**: We enabled `Write-Ahead Logging (WAL)` in `db_manager.py`. This allows the Flask Dashboard to read from the database at high speed while the Discord Bot is concurrently writing, preventing "Database Locked" errors.
- **Eager Caching & Lifecycle Sync**: The bot now uses an asynchronous `media_processor.py` to eagerly cache high-res photos and generate thumbnails in the background *immediately* upon approval. This ensures the Vault remains accessible even if the original Discord message is deleted.
- **Automated Deletion Synchronization**: We implemented `on_raw_message_delete` and `on_raw_bulk_message_delete` listeners. If a message is deleted on Discord, the Vault automatically purges the associated records and cache, respecting user privacy and server cleanup.
- **Reaction-Based ID Consistency**: To support global deletion sync, we updated both the Web Dashboard and Discord Reaction logic to store consistent Snowflake-based composite IDs (`message_id-attachment_id`) for every archived item.
- **Cross-Platform Muted Autoplay**: We optimized the gallery for Brave and iOS Safari by injecting raw HTML `muted`, `autoplay`, and `playsinline` attributes. This allows videos to "move around" in the grid silently for better media differentiation on all devices.
- **Mobile Density & Accessibility**: Implementation of a 2-column grid and a high-visibility, persistent selection circle on mobile to ensure the Vault is easily manageable on touch screens.
- **Sticky UX**: The filter bar now uses `position: sticky` and a glassmorphism design to remain accessible at the top of the screen during scrolling.
- **Dashboard DB Concurrency (WAL & Batching)**: Upgraded `dashboard.py` to open connections with WAL mode enabled and utilize `.executemany()` cursor batching, processing bulk queue approvals in constant time natively bypassing SQLite write locks.
- **Out Of Memory (OOM) Protection**: Overhauled the `/api/download_bulk` streaming logic to lazily write chunk data to a disk ZIP file, entirely eliminating server RAM exhaustion during massive video multi-select exports.
- **Browser Connection Limit Protection**: Videos in the review queue now default to poster-only loading with `preload="none"`, resolving HTTP connection stalling that occurred when rendering dozens of video tags concurrently.
- **Security Hard-Failures**: Dashboard natively enforces strict validation of `.env` presence. The deployment crashes securely if a custom `ADMIN_PASSWORD` or `SECRET_KEY` isn't injected upon boot.
- **Moderation Safety Checks**: Replaced immediate bulk actions with interactive confirmation dialogs for destructive moderation tasks (Blacklisting/Deleting) to prevent accidental archive wiping during high-volume triage.
- **Legacy Metadata Backfill**: Implemented a hash-matching `/backfill_legacy_links` tool for the bot. This enables the restoration of lost Discord Jump Links for "web-review" items in the vault by scanning historical source channel history and recursively matching file signatures.
- **Absolute URL Persistence**: Refactored the "Copy Link" sharing mechanism to use `window.location.origin` in the browser layer. This ensures that shared media links maintain their full-domain context, bypassing Discord's built-in attachment expiration by serving permanent copies directly from the local vault.
- **Compact UI Iconography**: Pivot to a logo-first design for internal navigation buttons (Discord SVG) to maximize density and focus within the media-heavy dashboard across desktop and mobile.
- **Event Bubbling & Stop Propagation**: Refined JS listeners in `app.js` to ensure that functional overlays (sharing, jumping, selection) do not unintentionally trigger parent container events (lightbox opening), creating a much cleaner "desktop-first" desktop feel.
- **Infinite Scroll Pagination**: Implemented `limit` and `offset` support in `dashboard.py` and `IntersectionObserver`-style infinite scrolling in `app.js`. This prevents OOM and browser hangs by only fetching and rendering 40 items at a time, ensuring the vault scales to thousands of photos seamlessly.
- **Connection Pooling & API Efficiency**: Refactored `dashboard.py` to utilize a persistent `requests.Session`. This reuses TCP connections for Discord API and CDN requests, significantly reducing latency and overhead during high-volume media browsing.
- **Mobile Smart-Download & Instructional HUD**: Implemented a hybrid strategy to balance gallery access and stability. Selections ≤ 20 use the native **Web Share API** for Photos integration, while larger batches switch to **ZIP Archives** to prevent browser OOM (Out Of Memory) crashes. This is supported by an **Instructional HUD** with OS-specific diagrams that guide users through the "Save to Photos" process on iOS/Android.

## 🌅 Future Architecture & Roadmap
We intend to implement these 10X improvements to facilitate massive multi-guild scaling and UX superiority:
- **SSE-Based Heartbeat**: A lightweight Server-Sent Events (SSE) system in `dashboard.py` to "push" new approved attachment IDs to the frontend for zero-refresh gallery updates.
- **Perceptual Fingerprinting**: Moving beyond SHA256 bytes-matching to image-context hashing (`phash`) in `filter_logic.py`, ensuring visual duplicates (e.g., compressed copies) are deduplicated.
- **Temporal Event Clustering**: An algorithmic layer to group photos chronologically into "Events" in the SQL layer for more intuitive memory navigation.
