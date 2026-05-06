#!/bin/bash
set -e

echo ""
echo "  ╔════════════════════════════════════════╗"
echo "  ║   DMS Upload Automation — Spyne        ║"
echo "  ╚════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "  [ERROR] Python 3 not found."
    echo "  Install via: brew install python3   (Mac)"
    echo "           or: sudo apt install python3 python3-pip  (Linux)"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "  [1/3] Checking dependencies..."
python3 -m pip install -q playwright 2>/dev/null || python3 -m pip install playwright

echo "  [2/3] Installing Playwright browser (first run only)..."
python3 -m playwright install chromium 2>/dev/null || true

echo "  [3/3] Starting server..."
echo ""
echo "  UI will open in your browser automatically."
echo "  Press Ctrl+C to stop."
echo ""

python3 "$SCRIPT_DIR/server.py"
