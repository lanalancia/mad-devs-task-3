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

if ! .venv/bin/python -c "import psycopg" >/dev/null 2>&1; then
    echo "Installing Python packages..."
    .venv/bin/python -m pip install -r requirements.txt
fi

while true; do
    echo ""
    echo "Services:"
    echo "  1. backend+db+smtp"
    echo "  2. frontend"
    echo "  3. mock-website"
    echo ""
    printf "Start service: "
    read -r choice || exit 0
    case "$choice" in
        1)
            if ! docker start mad-devs-postgres >/dev/null 2>&1; then
                echo "PostgreSQL container mad-devs-postgres is not available."
                echo "Run .venv/bin/python install.py and choose the Docker PostgreSQL install."
                continue
            fi
            ready=0
            i=0
            while [ "$i" -lt 30 ]; do
                if docker exec mad-devs-postgres pg_isready >/dev/null 2>&1; then
                    ready=1
                    break
                fi
                i=$((i + 1))
                sleep 1
            done
            if [ "$ready" -ne 1 ]; then
                echo "PostgreSQL is not accepting connections yet."
                continue
            fi
            echo "Starting backend. SMTP is not started in this step."
            .venv/bin/python -m backend || true
            echo "Backend stopped."
            ;;
        2|3)
            echo "This service is not available in this step."
            ;;
        *)
            echo "Unknown service. Enter 1, 2, or 3. The valid service in this step is 1."
            ;;
    esac
done
