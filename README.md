# Hybrid Photo Archiver Bot

A Discord bot that passively archives hangout photos and videos to a central repository (Cloudinary or local disk), while intelligently keeping messy memes out of your gallery! 

## Core Filtering Pipeline
Because managing a gallery can be tedious, this bot uses **Heuristic Size Filtering combined with a Human Moderation Queue**.

- **Automatic Pre-Approval**: The bot instantly analyzes file sizes and extensions. Any media file larger than 500 KB is safely assumed to be a high-quality phone camera photograph and is automatically accepted and uploaded to the Cloudinary vault.
- **Admin Review Validation**: Smaller files (under 500 KB, which are usually compressed internet memes or heavily cropped screenshots) are redirected to an admin queue where a human can quickly glance and decide their fate.
- **Persistent Meme Blacklisting**: When discarding a confirmed meme from the queue, you can choose to **"Blacklist"** its distinct digital crypto-hash. If anyone on your server posts that exact meme *ever again*, the bot instantly recognizes the hash and automatically ignores it!

## Development Setup
**Prerequisites**: Python 3.10+ and a Discord App API Account.

1. Clone or download the repository to your machine.
2. Initialize a local virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install discord.py python-dotenv cloudinary
   ```
4. Configure Secrets: 
   Paste your Discord Bot Token into the `.env` file. You can optionally add a `CLOUDINARY_URL` to point to a free Cloudinary bucket. If omitted, the bot defaults safety to storing images inside a local `/images/` directory.
5. Boot the bot up!
   ```bash
   python execution/bot.py
   ```

## Discord Slash Commands
These commands are exposed natively inside your Discord server to dictate the bot's behavior.

- `/set_photo_channel #channel`: Binds the bot scanner to a specific chat room. It will remain dormant in all other channels.
- `/set_review_channel #channel`: Binds the triage interface to an admin/private channel where the UI Buttons will be rendered.
- `/sync_history`: Initiates a deep backwards scan of the complete history of the designated photo channel. This forces all prior messages through the active heuristic filtering pipeline, bridging old media to your cloud system without duplicates!
