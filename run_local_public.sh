#!/bin/bash

# Kill all background processes on exit
trap "kill 0" EXIT

echo "🚀 Starting Discord Memory Vault (Local Cloudflare Mode)..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 1. Start the Bot (Background)
python3 execution/bot.py &

# 2. Start the Dashboard (Background)
python3 execution/dashboard.py &

# 3. Wait for Dashboard to boot
sleep 2

# 4. Start the Cloudflare Tunnel
echo "🌐 Launching Cloudflare tunnel..."
./cloudflared_local tunnel --url http://localhost:5050
