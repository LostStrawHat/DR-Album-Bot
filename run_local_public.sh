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

# 4. Start the Cloudflare Tunnel and Auto-Update Link
echo "🌐 Launching Cloudflare tunnel..."
LOG_FILE=".tmp/tunnel.log"
mkdir -p .tmp
touch $LOG_FILE

# Start tunnel in background and tee output to log
./cloudflared_local tunnel --url http://localhost:5050 2>&1 | tee $LOG_FILE &

# Foreground loop to find and sync the URL
echo "⏳ Waiting for public URL to generate..."
while true; do
    URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' $LOG_FILE | head -n 1)
    if [ ! -z "$URL" ]; then
        echo "✅ Public URL detected: $URL"
        echo "🔄 Syncing with Discord Bot database..."
        sqlite3 photos.sqlite3 "INSERT OR REPLACE INTO config (key, value) VALUES ('album_url', '$URL');"
        echo "✨ Done! The /album command is now active at this address."
        break
    fi
    sleep 1
done

# Keep script running to maintain the background processes
wait
