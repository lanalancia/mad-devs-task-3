# mad-devs-task-3

MadDevs task #3 website monitor

Backend and frontend can run on different machines. Install only the requirements for the part you start.

## Backend requirements

- Python 3.10 or newer
- Docker. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows or macOS, or Docker Engine on Linux. Start Docker before setup. `install.py` downloads the `postgres:17` image and runs it. The script does not install Docker.

## Frontend requirements

- Node.js 20 or newer, including npm

## Setup

Create a virtual environment, install packages, and run the installer. Choose the Docker PostgreSQL option. That creates the application tables and the seed rows. Connecting an existing database only saves `config.ini` and does not change that database.

On Windows, run `start_venv.bat`. It opens a command prompt with the virtual environment active. Then run:

```
python -m pip install -r requirements.txt
python install.py
```

On Linux, use `python3 -m venv .venv`, activate it, and run the same commands with that interpreter.

Running `install.py` again on the Docker database asks before replacing the application tables.

Frontend packages are installed when you start the frontend. To install them yourself, run `npm install` in the `frontend` directory.

## Run

On Windows, run `start.bat`. On Linux, run `bash start.sh`.

- `1` starts the PostgreSQL container and the backend. SMTP is not started. The backend polls each active URL on its own interval, prints one line per saved result, and serves the HTTP API. Stop it with Ctrl+C.
- `2` starts the frontend at http://localhost:17777. It does not start the backend. Stop it with Ctrl+C.
- `3` starts four fixed websites on 127.0.0.1, ports 17781–17784: 200 after 100 ms, 404 after 300 ms, 200 that alternates between 100 ms and 900 ms every 10 minutes of UTC, and 200 after 6 seconds. Stop them with Ctrl+C.

The API listens on port 17778. Change `[http] port` in `config.ini` to use another port. `frontend/config.ini` is the address the page calls. On one machine that is `http://localhost:17778`.

The page asks for the current page of entries every 5 seconds. Sign in with a user from `init-users.json`. A fresh install includes `admin` / `admin`. Wrong credentials leave the page in guest mode. The token lasts one hour. Guests see `polling` or `paused`. A signed-in user can change the polling rate and timeout, pause or resume an entry, delete it, or add a URL on the empty row. Deleting hides the entry and keeps its history. Adding the same URL again restores that entry.

A signed-in user opens Statistics with `[i]` on a row. That page shows the share of successful checks and the average response time for the last 24 hours, 7 days, or 30 days, a response-time graph, and the incident log. Under the last poll time it shows how long the current open incident has lasted, or "no incidents right now", and the response time of the latest saved poll. A new URL must use `http` or `https`, or start with `www` or `localhost`. A port is allowed. A slash that is the whole path is removed; a slash after a page path stays. Long addresses show the first 20 characters in the table, and the full address in the hint.
