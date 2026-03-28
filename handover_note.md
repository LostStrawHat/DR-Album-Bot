# Handover Note: High-Performance Media Vault & Lifecycle Sync

## Phase 3 Objective
Optimize the vault for professional-grade concurrency, ensure 100% lifecycle synchronization with Discord events, and maximize cross-platform media accessibility (Brave/iOS).

## Key Changes Summary
1. **High-Performance Architecture**:
   - **SQLite WAL Mode**: Enabled `Write-Ahead Logging` in `db_manager.py`, allowing the Flask Dashboard and Discord Bot to access the database simultaneously without locking.
   - **Eager Background Processing**: Integrated `media_processor.py` for asynchronous, non-blocking media downloads and OpenCV thumbnail generation immediately upon approval.
   - **Lazy Loading & Autoplay**: Unified gallery grid to allow muted, automated video previews using direct HTML attributes (`playsinline`, `muted`, `autoplay`) for wide browser compatibility (Brave/Safari).

2. **Life-Cycle Synchronization**:
   - **Dynamic Deletion Sync**: Implemented `on_raw_message_delete` and `on_raw_bulk_message_delete`. Deleting the source message on Discord now automatically purges the vault record and local cache.
   - **Reaction-Based ID Consistency**: Standardized the use of Snowflake-based composite IDs (`message_id-attachment_id`) across both Discord Reactions and Web Approvals to ensure deletion sync works globally.

3. **User Experience & Accessibility**:
   - **Mobile "Save to Photos" Integration**: Replaced standard file downloads on iOS/Android with the native **Web Share API**. This allows users to save media directly to their native Gallery/Photos app instead of the hidden "Files" folder.
   - **Batch-Processing UI**: Implemented a 15-item batching constraint for mobile sharing to prevent OOM (Out Of Memory) crashes. Added dynamic UI notifications (`Batch 1/3...`) and browser alerts to guide users through multi-share operations.
   - **Global Name Sync**: Updated attribution logic to prioritize server-specific nicknames and automatically propagate name changes across historical records.

## Critical Setup Information
For new instances:
1. **PULL** latest code (`main`).
2. **MIGRATE**: Run `venv/bin/python execution/db_manager.py` to reconcile schema additions (including the new `original_msg_id` and `attachment_id` columns in `meme_cache`).
3. **DEPENDENCIES**: Ensure `opencv-python` and `Pillow` are installed for background media processing.

## Current Status
- **Bot**: Online with advanced event listeners for deletion sync.
- **Moderation**: Fully unified ID system between Web and Discord.
- **Gallery**: Highly optimized with background-processed thumbnails and cross-platform video support.
- **Performance**: Near-zero blocking on the main Discord event loop.

---
*Maintained with ❤️ for a reliable community vault.*
