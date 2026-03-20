#!/bin/bash
# run_dev_bot.sh
# This script monitors the bot folder and restarts python execution/bot.py whenever changes are made.

echo "🚀 Starting Bot with Auto-Reload (watchmedo)..."
source venv/bin/activate
watchmedo auto-restart --pattern="*.py" --recursive --directory="execution" python execution/bot.py
