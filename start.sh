#!/usr/bin/env bash
#
# StudySync AI — one-command startup script
# Starts Ollama (if not running), the FastAPI backend, and the Vite frontend.
# Press Ctrl+C once to stop everything cleanly.

set -e

# ── Colors for readable output ──────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

PIDS=()

# ── Cleanup: kill all child processes on exit (Ctrl+C) ──────────────────────
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null
    echo -e "${GREEN}Stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

echo -e "${BLUE}=== StudySync AI Startup ===${NC}"
echo ""

# ── Step 1: Check Ollama is installed ───────────────────────────────────────
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}✗ Ollama is not installed.${NC}"
    echo "  Install it from: https://ollama.ai"
    exit 1
fi
echo -e "${GREEN}✓ Ollama is installed${NC}"

# ── Step 2: Start Ollama if it's not already running ────────────────────────
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama is already running${NC}"
else
    echo -e "${YELLOW}Starting Ollama...${NC}"
    ollama serve > /tmp/studysync-ollama.log 2>&1 &
    PIDS+=($!)

    # Wait for it to come up (max 15 seconds)
    for i in $(seq 1 15); do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Ollama started${NC}"
            break
        fi
        sleep 1
        if [ "$i" -eq 15 ]; then
            echo -e "${RED}✗ Ollama failed to start. Check /tmp/studysync-ollama.log${NC}"
            cleanup
        fi
    done
fi

# ── Step 3: Check at least one model is installed ───────────────────────────
MODEL_COUNT=$(curl -s http://localhost:11434/api/tags | grep -o '"name"' | wc -l | tr -d ' ')
if [ "$MODEL_COUNT" -eq 0 ]; then
    echo -e "${RED}✗ No Ollama models installed.${NC}"
    echo "  Run: ollama pull mistral"
    cleanup
fi
echo -e "${GREEN}✓ Found $MODEL_COUNT installed model(s)${NC}"

# ── Step 4: Set up backend/.env from .env.example if needed ────────────────
cd "$BACKEND_DIR"

if [ -f ".env.example" ] && [ ! -f ".env" ]; then
    cp .env.example .env
    rm .env.example
    echo -e "${GREEN}✓ Created backend/.env from .env.example${NC}"
elif [ -f ".env.example" ] && [ -f ".env" ]; then
    rm .env.example
    echo -e "${GREEN}✓ backend/.env already exists — removed leftover .env.example${NC}"
fi

# ── Step 5: Check Python venv / dependencies ────────────────────────────────
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python3 -m venv venv
fi

source venv/bin/activate

if ! python -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}Installing backend dependencies...${NC}"
    pip install -q -r requirements.txt
fi
echo -e "${GREEN}✓ Backend dependencies ready${NC}"

# ── Step 6: Start the backend ────────────────────────────────────────────────
echo -e "${YELLOW}Starting backend on http://localhost:8000...${NC}"
python main.py > /tmp/studysync-backend.log 2>&1 &
PIDS+=($!)

for i in $(seq 1 15); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend is up${NC}"
        break
    fi
    sleep 1
    if [ "$i" -eq 15 ]; then
        echo -e "${RED}✗ Backend failed to start. Check /tmp/studysync-backend.log${NC}"
        cleanup
    fi
done

# ── Step 7: Check Node dependencies ─────────────────────────────────────────
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies (this may take a minute)...${NC}"
    npm install --silent
fi
echo -e "${GREEN}✓ Frontend dependencies ready${NC}"

# ── Step 8: Start the frontend ───────────────────────────────────────────────
echo -e "${YELLOW}Starting frontend on http://localhost:5173...${NC}"
npm run dev > /tmp/studysync-frontend.log 2>&1 &
PIDS+=($!)

sleep 2

echo ""
echo -e "${GREEN}=== StudySync AI is running ===${NC}"
echo ""
echo -e "  Frontend:  ${BLUE}http://localhost:5173${NC}"
echo -e "  Backend:   ${BLUE}http://localhost:8000${NC}"
echo -e "  Ollama:    ${BLUE}http://localhost:11434${NC}"
echo ""
echo -e "  Logs: /tmp/studysync-*.log"
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop everything"
echo ""

# ── Open the browser automatically (best-effort, ignore if it fails) ───────
sleep 1
if command -v open &> /dev/null; then
    open http://localhost:5173 2>/dev/null || true       # macOS
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5173 2>/dev/null || true   # Linux
fi

# ── Wait for all background processes; cleanup() handles Ctrl+C ────────────
wait
