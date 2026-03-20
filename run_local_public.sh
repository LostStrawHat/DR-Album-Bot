#!/bin/bash

# Kill all background processes on exit
trap "kill 0" EXIT

echo "🚀 Starting Discord Memory Vault (Local Cloudflare Mode)..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 1. Optimize Database
echo "📦 Optimizing database..."
sqlite3 photos.sqlite3 "VACUUM; ANALYZE; PRAGMA journal_mode=WAL;"

# Function to run bot with auto-restart
run_bot() {
    until venv/bin/python execution/bot.py; do
        echo "⚠️ Bot crashed! Restarting in 5s..."
        sleep 5
    done
}

# Function to run dashboard with auto-restart
run_dashboard() {
    until venv/bin/python execution/dashboard.py; do
        echo "⚠️ Dashboard crashed! Restarting in 5s..."
        sleep 5
    done
}

# 2. Launch Background Processes
run_bot &
run_dashboard &

# 4. Starting Cloudflare Tunnel (Managed by Bot)
echo "🌐 Cloudflare Tunnel will be managed by the Bot's /album command."
echo "✨ To get the public link, run /album in your Discord server."

# Keep script running to maintain the background processes
wait
