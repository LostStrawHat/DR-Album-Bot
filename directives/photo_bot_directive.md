# Discord Photo Archiver Bot - Architecture Directive

## Goal
A localized Discord bot that passively archives hangout photos and videos to Cloudinary, while strictly filtering out internet memes directly inside Discord.

## Tools/Scripts to Use
- `execution/bot.py` (Main Discord listener, Slash commands, interactive Queue UI, Discord logger hook)
- `execution/filter_logic.py` (Handles heuristic file-size checks and SQLite cache hashing logic)
- `execution/storage.py` (Handles Cloudinary uploads and safe environmental fallback extraction)
- `execution/db_manager.py` (Creates the persistent local tables for meme and photo caching)
- `execution/test_suite.py` (A deterministic unit test script simulating Discord attachments to violently validate logic)

## Architecture & Foundational Learnings
- **Heuristics Over AI**: We heavily pivoted from HuggingFace to an offline 500KB size limit. Memes are notoriously small; photos from modern smartphones easily clear 1MB. Highly effective and completely free.
- **Meme Cache & Duplicate Shields**: We use SHA256 hashing specifically via `hashlib` to create fingerprints of successfully deployed photos and discarded meme cache components, creating infinite API-savings by intercepting duplicates.
- **Pyspark / Dotenv Bug**: The `cloudinary` python SDK literally crashes on import if a placeholder `your_cloudinary_url_here` URL is present in `os.environ`. We actively patched `storage.py` to intercept and `.pop()` the placeholder from the environment before letting the SDK library dynamically boot up to save crashes.
- **Discord Private Logging**: When users spawn the active environment via `/setup_server`, directly manipulate the Discord `PermissionOverwrite` on categories to secure `#bot-logs` invisibly.

## Outputs
- Persistent `photos.sqlite3` Database recording `photos`, `meme_cache`, `uploaded_cache`, and `config`.
- Images uploaded successfully to Cloudinary.
- Native Discord logging directly into `#bot-logs`.
- Custom Dashboard Link accessible via `/album` slash command.

## New Features & UI Optimizations
- **Public Album Access**: Added `/album` (public) and `/set_album_url` (admin only) commands to manage and share the dashboard link easily.
- **Mobile Density**: Implementation of a 2-column gallery grid on mobile devices (via `repeat(2, 1fr)`) and reduced container padding to maximize information density.
- **Sticky UX**: The filter bar now uses `position: sticky` to remain accessible at the top of the screen during scrolling while starting below the page title.
- **Clean Hyperlinks**: Dashboard links are sent as compressed markdown hyperlinks `[Album](<url>)` with embed suppression to avoid bulky Discord previews.
