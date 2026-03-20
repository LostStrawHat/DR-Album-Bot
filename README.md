# Discord Memory Vault - Render Deployment Guide

This repository is configured for easy deployment to **Render.com**.

## Deployment Steps

1. **Push to GitHub**: Push your code to a GitHub repository.
2. **Create Web Service (Dashboard)**:
   - Connect your repo to Render.
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python execution/dashboard.py`
   - **Environment Variables**: Add your `DISCORD_TOKEN`, `ADMIN_PASSWORD`, and `SECRET_KEY`.
3. **Create Background Worker (Bot)**:
   - Connect the same repo again.
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python execution/bot.py`
   - **Environment Variables**: Use the same environment variables as the web service.

## Persistence Note (Free Tier)
Render's free tier uses an ephemeral disk. The `photos.sqlite3` database will reset on every deploy/restart. For permanent storage, consider connecting to a free hosted PostgreSQL database (like Neon or Supabase) and updating the storage logic.
