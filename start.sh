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

OLLAMA_LOG=/tmp/studysync-ollama.log
BACKEND_LOG=/tmp/studysync-backend.log
FRONTEND_LOG=/tmp/studysync-frontend.log

STARTUP_TIMEOUT=30  # seconds to wait for each service to start responding

PIDS=()          # every background process we started; all killed on exit
OLLAMA_PID=""    # only set if this script started Ollama itself
BACKEND_PID=""
FRONTEND_PID=""
CLEANED_UP=0

# ── Cleanup: stop everything we started, then exit with the given code ──────
cleanup() {
    local code=${1:-0} pid i alive
    if [ "$CLEANED_UP" -eq 1 ]; then
        return
    fi
    CLEANED_UP=1
    set +e  # never abort halfway through shutting down

    if [ ${#PIDS[@]} -gt 0 ]; then
        echo ""
        echo -e "${YELLOW}Shutting down...${NC}"
        for pid in "${PIDS[@]}"; do
            kill "$pid" 2>/dev/null
        done

        # Give everything up to 5 seconds to exit, then force-kill stragglers
        for i in $(seq 1 10); do
            alive=0
            for pid in "${PIDS[@]}"; do
                kill -0 "$pid" 2>/dev/null && alive=1
            done
            [ "$alive" -eq 0 ] && break
            sleep 0.5
        done
        for pid in "${PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}⚠ Process $pid didn't stop in time — force-killing it${NC}"
                kill -9 "$pid" 2>/dev/null
            fi
        done
        wait 2>/dev/null
        echo -e "${GREEN}Stopped.${NC}"
    fi
    exit "$code"
}

# Print an error (plus optional indented detail lines), then stop everything
fail() {
    echo -e "${RED}✗ $1${NC}" >&2
    shift
    if [ $# -gt 0 ]; then
        printf '%s\n' "$@" | sed 's/^/  /' >&2
    fi
    cleanup 1
}

# Like fail(), but also shows the end of a service's log so the cause is visible
fail_with_log() {  # fail_with_log <log file> <message>
    fail "$2" "Last lines of $1:" "$(tail -n 50 "$1" 2>/dev/null | sed 's/^/  /')"
}

# Safety net for anything set -e catches that isn't handled explicitly below
on_unexpected_exit() {
    local code=$?
    if [ "$CLEANED_UP" -eq 0 ]; then
        echo -e "${RED}✗ start.sh stopped unexpectedly (exit code $code)${NC}" >&2
        cleanup "$code"
    fi
}

trap 'cleanup 0' SIGINT SIGHUP SIGTERM  # SIGHUP = terminal window closed
trap 'fail "Unexpected error on line $LINENO: $BASH_COMMAND"' ERR
trap on_unexpected_exit EXIT

# ── Helpers ─────────────────────────────────────────────────────────────────
require_command() {  # require_command <command> <name> <install hint>
    if ! command -v "$1" &> /dev/null; then
        fail "$2 is not installed." "$3"
    fi
}

port_in_use() {
    local rc=0
    curl -s -o /dev/null --max-time 2 "http://localhost:$1" || rc=$?
    [ "$rc" -ne 7 ]  # curl exit code 7 = connection refused (nothing listening)
}

# Fail (showing its log) if a process we started has exited
ensure_running() {  # ensure_running <name> <pid> <log file>
    local name=$1 pid=$2 log=$3 code=0
    if [ -z "$pid" ] || kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    wait "$pid" 2>/dev/null || code=$?
    fail_with_log "$log" "$name exited unexpectedly (exit code $code)."
}

# Wait for a service we started to respond at its URL. Fails fast if the
# process dies during startup, or after STARTUP_TIMEOUT seconds.
wait_for_service() {  # wait_for_service <name> <url> <pid> <log file>
    local name=$1 url=$2 pid=$3 log=$4
    local deadline=$((SECONDS + STARTUP_TIMEOUT))
    while [ "$SECONDS" -lt "$deadline" ]; do
        ensure_running "$name" "$pid" "$log"
        if curl -sf -o /dev/null --max-time 2 "$url"; then
            return 0
        fi
        sleep 1
    done
    fail_with_log "$log" "$name did not respond at $url within ${STARTUP_TIMEOUT}s."
}

# Relays the backend's progress messages ("[INGEST] Chunk 1/5 → 2 cards", ...)
# from its log file to this terminal. Polls the file in plain bash rather than
# piping `tail -f`, so that killing this one process stops the whole relay.
relay_backend_progress() {
    local line partial=""
    while true; do
        if IFS= read -r line; then
            line="$partial$line"
            partial=""
            case "$line" in
                "[INGEST] ✓"*)           printf '%b%s%b\n' "$GREEN" "$line" "$NC" ;;
                "[INGEST]"*|"[CONFIG]"*) printf '%s\n' "$line" ;;
                "[OLLAMA]"*|"[PARSE]"*)  printf '%b%s%b\n' "$YELLOW" "$line" "$NC" ;;
            esac
        else
            partial="$partial$line"  # hold a half-written line until the rest arrives
            sleep 0.5
        fi
    done < "$BACKEND_LOG"
}

echo -e "${BLUE}=== StudySync AI Startup ===${NC}"
echo ""

# ── Step 1: Check required tools are installed ──────────────────────────────
require_command ollama  "Ollama"        "Install it from: https://ollama.com"
require_command python3 "Python 3"      "Install it from: https://www.python.org/downloads/"
require_command npm     "Node.js (npm)" "Install it from: https://nodejs.org"
require_command curl    "curl"          "Install it with your system's package manager."
echo -e "${GREEN}✓ Ollama, Python 3, Node.js and curl are installed${NC}"

# ── Step 2: Make sure the backend/frontend ports are free ───────────────────
# A leftover instance would answer our health checks while the new one fails
# to bind, making a broken start look successful.
for port in 8000 5173; do
    if port_in_use "$port"; then
        fail "Port $port is already in use — is StudySync already running?" \
             "Stop the old instance with ./stop.sh, then try again."
    fi
done

# ── Step 3: Start Ollama if it's not already running ────────────────────────
if curl -s --max-time 5 http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ollama is already running${NC}"
else
    echo -e "${YELLOW}Starting Ollama...${NC}"
    ollama serve > "$OLLAMA_LOG" 2>&1 &
    OLLAMA_PID=$!
    PIDS+=("$OLLAMA_PID")
    wait_for_service "Ollama" "http://localhost:11434/api/tags" "$OLLAMA_PID" "$OLLAMA_LOG"
    echo -e "${GREEN}✓ Ollama started${NC}"
fi

# ── Step 4: Check at least one model is installed ───────────────────────────
if ! TAGS=$(curl -sf --max-time 10 http://localhost:11434/api/tags); then
    fail "Could not get the list of installed models from Ollama." \
         "Try restarting Ollama, then run this script again."
fi
MODEL_COUNT=$(printf '%s' "$TAGS" | grep -o '"name"' | wc -l | tr -d ' ')
if [ "$MODEL_COUNT" -eq 0 ]; then
    fail "No Ollama models installed." "Install one with: ollama pull <model>"
fi
echo -e "${GREEN}✓ Found $MODEL_COUNT installed model(s)${NC}"

# ── Step 5: Set up backend/.env from .env.example if needed ────────────────
cd "$BACKEND_DIR" || fail "Backend directory not found: $BACKEND_DIR"

# .env.example is a tracked template — copy it, never delete it
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env || fail "Could not create backend/.env from .env.example"
        echo -e "${GREEN}✓ Created backend/.env from .env.example${NC}"
    else
        echo -e "${YELLOW}⚠ No backend/.env or .env.example found — using defaults${NC}"
    fi
fi

# ── Step 6: Check Python venv / dependencies ────────────────────────────────
# A venv breaks if the Python it was built from is upgraded or removed
if [ -d "venv" ] && ! venv/bin/python -c 'import sys' &> /dev/null; then
    echo -e "${YELLOW}⚠ Existing virtual environment is broken (was Python upgraded?) — recreating it${NC}"
    rm -rf venv
fi

if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    if ! OUTPUT=$(python3 -m venv venv 2>&1); then
        rm -rf venv  # don't leave a half-built venv behind for the next run
        fail "Failed to create Python virtual environment:" "$OUTPUT" \
             "(On Debian/Ubuntu you may need: sudo apt install python3-venv)"
    fi
fi

if ! source venv/bin/activate; then
    fail "Could not activate the Python virtual environment." \
         "Delete backend/venv and run this script again to recreate it."
fi

echo -e "${YELLOW}Checking dependencies...${NC}"

# --only-binary=pymupdf: never compile MuPDF from source (it maxes out every
# core and can exhaust RAM). If no prebuilt wheel exists, fail fast instead.
if ! OUTPUT=$(pip install -q --only-binary=pymupdf -r requirements.txt 2>&1); then
    fail "Failed to install backend dependencies:" "$OUTPUT"
fi

echo -e "${GREEN}✓ Backend dependencies ready${NC}"

# ── Step 7: Start the backend ────────────────────────────────────────────────
echo -e "${YELLOW}Starting backend on http://localhost:8000...${NC}"
# -u: unbuffered output, so progress messages hit the log as they're printed
python -u main.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
PIDS+=("$BACKEND_PID")
wait_for_service "Backend" "http://localhost:8000/health" "$BACKEND_PID" "$BACKEND_LOG"
echo -e "${GREEN}✓ Backend is up${NC}"

relay_backend_progress &
PIDS+=($!)

# ── Step 8: Check Node dependencies ─────────────────────────────────────────
cd "$FRONTEND_DIR" || fail "Frontend directory not found: $FRONTEND_DIR"

# Checking for vite (not just node_modules) also catches interrupted installs
if [ ! -x "node_modules/.bin/vite" ]; then
    echo -e "${YELLOW}Installing frontend dependencies (this may take a minute)...${NC}"
    if ! OUTPUT=$(npm install --silent 2>&1); then
        fail "Failed to install frontend dependencies:" "$OUTPUT"
    fi
fi
echo -e "${GREEN}✓ Frontend dependencies ready${NC}"

# ── Step 9: Start the frontend ───────────────────────────────────────────────
echo -e "${YELLOW}Starting frontend on http://localhost:5173...${NC}"
# --strictPort: error out instead of silently switching to another port
npm run dev -- --strictPort > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
PIDS+=("$FRONTEND_PID")
wait_for_service "Frontend" "http://localhost:5173" "$FRONTEND_PID" "$FRONTEND_LOG"
echo -e "${GREEN}✓ Frontend is up${NC}"

echo ""
echo -e "${GREEN}=== StudySync AI is running ===${NC}"
echo ""
echo -e "  Frontend:  ${BLUE}http://localhost:5173${NC}"
echo -e "  Backend:   ${BLUE}http://localhost:8000${NC}"
echo -e "  Ollama:    ${BLUE}http://localhost:11434${NC}"
echo ""
echo -e "  Logs: /tmp/studysync-*.log"
echo -e "  PDF processing progress will appear below."
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop everything"
echo ""

# ── Open the browser automatically (best-effort, ignore if it fails) ───────
if command -v open &> /dev/null; then
    open http://localhost:5173 2>/dev/null || true       # macOS
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5173 2>/dev/null || true   # Linux
fi

# ── Keep running until Ctrl+C; stop everything if any service crashes ──────
while true; do
    ensure_running "Ollama" "$OLLAMA_PID" "$OLLAMA_LOG"
    ensure_running "Backend" "$BACKEND_PID" "$BACKEND_LOG"
    ensure_running "Frontend" "$FRONTEND_PID" "$FRONTEND_LOG"
    sleep 1
done
