#!/bin/bash
# Fix Weekly Chart — regenerates weekly_pick_chart.png for the current pick
# Run this any time the weekly pick ticker changes (or use the cronjob).
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use the project's venv Python (has matplotlib, yfinance installed)
PYTHON="$SCRIPT_DIR/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
fi
if [ ! -x "$PYTHON" ]; then
    echo "[fix-chart] ERROR: no venv Python found at $SCRIPT_DIR/venv/bin/python(3)"
    exit 1
fi

echo "[fix-chart] $(date) — Regenerating weekly pick chart..."
"$PYTHON" "$SCRIPT_DIR/scripts/generate_weekly_pick_chart.py"
RC=$?

if [ $RC -eq 0 ]; then
    echo "[fix-chart] Chart regenerated OK."
    # Also update ACWX chart
    "$PYTHON" "$SCRIPT_DIR/generate_acwx_chart.py" 2>/dev/null || true
    # Commit & push if inside a git repo
    if [ -d ".git" ]; then
        git add weekly_pick_chart.png acwx_chart.png 2>/dev/null || true
        git diff --cached --quiet || git commit -m "chart: regenerate weekly pick & ACWX charts ($(date +%Y-%m-%d))" >/dev/null 2>&1 || true
        git push origin main >/dev/null 2>&1 || true
        echo "[fix-chart] Pushed updated charts to origin/main"
    fi
else
    echo "[fix-chart] FAILED (exit $RC)"
fi

exit $RC
