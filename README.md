# Discord Memory Vault

A passive Discord bot and dashboard for archiving hangout photos and videos locally.

## Features
- **Passive Archiving**: Automatically detects and saves high-resolution media.
- **Meme Filtering**: Offline size-based heuristics (500KB limit) to ignore internet memes.
- **Interactive Dashboard**: A glassmorphism web interface to browse and filter your memories.
- **Slash Commands**: `/album` to get the link, `/set_photo_channel` to bind the listener.

## Local Deployment

This vault is optimized for local hosting with secure public access via Cloudflare Tunnels.

### Prerequisites
- Python 3.10+
- Discord Bot Token (with Message Content Intent)

### Setup
1. **Clone & Install**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure**:
   Update your `.env` file with `DISCORD_TOKEN`, `ADMIN_PASSWORD`, and `SECRET_KEY`.
3. **Run**:
   ```bash
   chmod +x run_local_public.sh
   ./run_local_public.sh
   ```

### Access
The script will launch a Cloudflare tunnel. Use `/set_album_url <url>` in Discord to save the link for the `/album` command.
