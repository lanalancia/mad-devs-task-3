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
    if ! "$launcher" -m venv .venv; then
        echo "Failed to create the virtual environment."
        exit 1
    fi
    if [ ! -x .venv/bin/python ]; then
        echo "Failed to create the virtual environment."
        exit 1
    fi
fi

echo ""
echo "Virtual environment is active."
echo "Install packages with: python -m pip install -r requirements.txt"
echo "Then run: python install.py"
echo ""

export VIRTUAL_ENV="$PWD/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
unset PYTHONHOME || true
exec "${SHELL:-/bin/sh}" -i
