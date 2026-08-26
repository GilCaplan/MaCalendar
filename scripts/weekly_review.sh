#!/bin/bash
# Weekly assistant review — run by launchd every Wednesday 10:00 local time.
# Writes DOCUMENTATION/WEEKLY_REVIEW.md (feedback/accuracy/vocab) and re-runs the
# audit corpus against the user's real history. Safe to run any time by hand.
cd "$(dirname "$0")/.." || exit 1
PY=.venv/bin/python
{
  echo "=== $(date) weekly review ==="
  $PY -m scripts.weekly_review --days 7 --out DOCUMENTATION/WEEKLY_REVIEW.md
  # audit against real history only if Ollama is up (it needs the LLM path)
  if curl -s -m 3 http://localhost:11434/api/tags >/dev/null; then
    $PY -m scripts.audit_assistant --history --out DOCUMENTATION/ASSISTANT_AUDIT_HISTORY.md
  else
    echo "Ollama offline — skipped history audit"
  fi
} >> ~/.assistant_tools/weekly_review.log 2>&1
osascript -e 'display notification "Weekly review written to DOCUMENTATION/WEEKLY_REVIEW.md — open Claude Code and ask for the analysis" with title "MACalendar assistant"' 2>/dev/null
