#!/bin/bash
# Double-click this file in Finder to launch the Calendar Assistant.

cd "$(dirname "$0")"

# Activate virtual environment
VENV_PYTHON=""
if [ -f ".venv/bin/python" ]; then
    # Validate the venv's Python interpreter actually exists (not a broken symlink)
    INTERP=$(head -1 .venv/bin/python 2>/dev/null | sed 's/#\!//')
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

python -m assistant.main
