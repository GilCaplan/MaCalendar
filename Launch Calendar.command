#!/bin/bash
# Double-click this file in Finder to launch the Calendar Assistant.

cd "$(dirname "$0")"

# Activate virtual environment
VENV_PYTHON=""
if [ -f ".venv/bin/python" ]; then
    # Validate the venv's Python interpreter actually exists (not a broken symlink)
    INTERP=$(head -1 .venv/bin/python 2>/dev/null | LC_ALL=C sed 's/#\!//')
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" 2>/dev/null && \
       .venv/bin/python -c "import PyQt6" 2>/dev/null; then
        source .venv/bin/activate
        VENV_PYTHON=".venv/bin/python"
    fi
elif [ -f "venv/bin/python" ]; then
    source venv/bin/activate
    VENV_PYTHON="venv/bin/python"
fi

# If no valid venv found, offer to create one automatically
if [ -z "$VENV_PYTHON" ]; then
    echo ""
    echo "⚠️  Virtual environment is missing or broken."
    echo "   Setting up dependencies now (this only runs once)..."
    echo ""
    # Find a Python 3.11+ interpreter
    for PY in python3.11 python3.12 python3.13; do
        if command -v $PY &>/dev/null; then
            FOUND_PY=$PY
            break
        fi
    done
    if [ -z "$FOUND_PY" ]; then
        echo "❌ Python 3.11 or later is required but not found."
        echo "   Install it via: brew install python@3.11"
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "Using $FOUND_PY — creating .venv and installing packages..."
    $FOUND_PY -m venv .venv
    .venv/bin/pip install -e ".[dev]" --quiet
    source .venv/bin/activate
    echo "✅ Setup complete."
    echo ""
fi

# Start Ollama server if it is not already running
if command -v ollama &>/dev/null; then
    if ! lsof -i :11434 -sTCP:LISTEN -t >/dev/null; then
        echo "🦙 Starting Ollama server..."
        ollama serve > /dev/null 2>&1 &
        OLLAMA_PID=$!
        # Give it a few seconds to initialize
        sleep 5
    fi
fi

# Start the iPhone API server in the background (Tailscale mode)
# If you get a port collision on 8080, change the port here and on your iPhone Settings.
PORT=8080
python -m assistant.api --tailscale --port $PORT &
API_PID=$!

echo "--------------------------------------------------------"
echo "📱 iPhone API started (PID $API_PID)"
echo "   1. Ensure Tailscale is UP on both Mac and iPhone."
echo "   2. In the iOS app, set Server URL to the Tailscale IP + :$PORT"
echo "   3. (Optional) Open Xcode to deploy: open MACalendar-iOS/MACalendar-iOS.xcodeproj"
if [ ! -z "$OLLAMA_PID" ]; then
echo "   4. Ollama server started in background (PID $OLLAMA_PID)"
fi
echo "--------------------------------------------------------"

# Start the Mac calendar app (foreground — closing this window stops everything)
python -m assistant.main

# When the Mac app exits, shut down the API server too
kill $API_PID 2>/dev/null
if [ ! -z "$OLLAMA_PID" ]; then
    kill $OLLAMA_PID 2>/dev/null
fi
