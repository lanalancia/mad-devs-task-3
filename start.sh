#!/bin/sh
set -eu

cd "$(CDPATH= cd -- "$(dirname "$0")" && pwd)"

python_ok() {
    "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
}

if [ ! -x .venv/bin/python ]; then
    echo "Creating virtual environment..."
    launcher=""
    if command -v python3 >/dev/null 2>&1 && python_ok python3; then
        launcher="python3"
    elif command -v python >/dev/null 2>&1 && python_ok python; then
        launcher="python"
    else
        echo "Python 3.10 or newer is required."
        exit 1
    fi
    "$launcher" -m venv .venv
fi

if [ ! -x .venv/bin/python ]; then
    echo "Failed to create the virtual environment."
    exit 1
fi

# shellcheck disable=SC1091
. .venv/bin/activate

echo ""
echo "Virtual environment is active."
echo "Python: $(command -v python)"
echo "Run: python install.py"
echo ""

exec "${SHELL:-/bin/sh}"
