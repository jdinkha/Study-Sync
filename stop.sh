#!/usr/bin/env bash
#
# StudySync AI — force-stop script
# Use this if start.sh's Ctrl+C didn't clean up properly
# (e.g. you closed the terminal window instead of pressing Ctrl+C).

echo "Stopping StudySync AI processes..."

# Kill anything listening on our three ports
for port in 8000 5173; do
    pid=$(lsof -ti :$port 2>/dev/null)
    if [ -n "$pid" ]; then
        echo "  Killing process on port $port (PID $pid)"
        kill -9 $pid 2>/dev/null
    fi
done

echo "Done. (Ollama on port 11434 was left running — stop it separately with 'pkill ollama' if needed.)"
