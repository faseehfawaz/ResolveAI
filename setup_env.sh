#!/bin/bash
# ──────────────────────────────────────────────────────────────
# ResolveAI – Environment Setup Script (macOS)
# ──────────────────────────────────────────────────────────────
# Run this once to set up your Python environment for the plugin.
#
# Usage:
#   chmod +x setup_env.sh
#   ./setup_env.sh
# ──────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║           ResolveAI – Environment Setup                 ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Check Python ─────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "❌ Python not found. Please install Python 3.10+ first."
    echo "   Download from: https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$($PYTHON_CMD --version 2>&1)
echo "✅ Found $PY_VERSION"

# ── Create Virtual Environment ───────────────────────────────
if [ -d "$VENV_DIR" ]; then
    echo "✅ Virtual environment already exists at .venv/"
else
    echo "📦 Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
    echo "✅ Virtual environment created at .venv/"
fi

# ── Activate & Install Dependencies ──────────────────────────
echo "📦 Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q

echo "✅ Dependencies installed."

# ── Set Resolve API Environment Variables ────────────────────
RESOLVE_SCRIPTS="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
RESOLVE_MODULES="$RESOLVE_SCRIPTS/Modules"
RESOLVE_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"

echo ""
echo "─── Resolve API Paths ───"

if [ -d "$RESOLVE_MODULES" ]; then
    echo "✅ Resolve scripting modules found at:"
    echo "   $RESOLVE_MODULES"
else
    echo "⚠️  Resolve scripting modules NOT found at default path."
    echo "   Expected: $RESOLVE_MODULES"
    echo "   You may need to configure this manually."
fi

echo ""
echo "─── Environment Variables ───"
echo "Add these to your shell profile (~/.zshrc) if not already set:"
echo ""
echo "  export RESOLVE_SCRIPT_API=\"$RESOLVE_SCRIPTS\""
echo "  export RESOLVE_SCRIPT_LIB=\"$RESOLVE_LIB\""
echo "  export PYTHONPATH=\"\$PYTHONPATH:$RESOLVE_MODULES\""
echo ""

# ── Create luts output directory ─────────────────────────────
mkdir -p "$SCRIPT_DIR/luts"
echo "✅ LUT output directory ready: luts/"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Setup complete! To activate the environment:          ║"
echo "║                                                         ║"
echo "║   source .venv/bin/activate                             ║"
echo "║                                                         ║"
echo "║   Then run the plugin with:                             ║"
echo "║                                                         ║"
echo "║   python main.py                                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
