# mad-devs-task-3

MadDevs task #3 website monitor

## Requirements

- Python 3.10 or newer
- Docker. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) on Windows or macOS, or Docker Engine on Linux. Start Docker before setup. `install.py` downloads the `postgres:17` image and runs it. The script does not install Docker.

## Setup

Create a virtual environment, install packages, and run the installer. Choose the Docker PostgreSQL option. That creates the application tables and the seed rows. Connecting an existing database only saves `config.ini` and does not change that database.

On Windows, run `start_venv.bat`. It opens a command prompt with the virtual environment active. Then run:

```
python -m pip install -r requirements.txt
python install.py
```

On Linux, use `python3 -m venv .venv`, activate it, and run the same commands with that interpreter.

Running `install.py` again on the Docker database asks before replacing the application tables.

## Run

On Windows, run `start.bat`. On Linux, run `bash start.sh`. Choose `1`.

That starts the PostgreSQL container and the backend. SMTP is not started. The backend polls each active URL on its own interval and prints one line per saved result. Stop it with Ctrl+C.
