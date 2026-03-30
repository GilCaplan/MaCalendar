#!/bin/bash
# Double-click this file in Finder to launch the Calendar Assistant.

# Change to the project directory (works regardless of where the file is placed)
cd "$(dirname "$0")"

# Activate virtual environment if one exists
if [ -d ".venv/bin" ]; then
    source .venv/bin/activate
elif [ -d "venv/bin" ]; then
    source venv/bin/activate
fi

python -m assistant.main
