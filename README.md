# mad-devs-task-3

MadDevs task #3 website monitor. Backend and frontend can run on different machines.

## 1. Install

You need Python 3.10 or newer, Docker (already installed and running), and Node.js 20 or newer with npm. The scripts do not install Docker or Node.js.

Windows: run `start_venv.bat`. Linux: run `bash start_venv.sh`. If `.venv` is missing, the script creates it, then opens a shell with that environment active.

In that shell:

```
python -m pip install -r requirements.txt
python install.py
```

Choose the Docker PostgreSQL option. That downloads `postgres:17` if needed, creates the tables, and loads the seed rows. A fresh install includes `admin` / `admin` from `init-users.json`. Running `install.py` again on that Docker database asks before replacing the tables. Connecting an existing database only writes `config.ini`.

Frontend packages are installed the first time you start the frontend.

## 2. Run

Windows: `start.bat`. Linux: `bash start.sh`.

- `1` starts the PostgreSQL container and the backend. The API port is `[http] port` in `config.ini` (17778). Stop with Ctrl+C.
- `2` starts the frontend at http://localhost:17777. `frontend/config.ini` is the API address the page calls. Stop with Ctrl+C.
- `3` starts four websites on 127.0.0.1, ports 17781–17784. Stop with Ctrl+C.

Pages, buttons, and popups are described in `docs/pages.md`.

To test the project all on the same machine, you have to run `start_venv.bat` and `start.bat` 3 times. Each time choosing the different option in `start.bat`

## 3. Not done, and added on top

Not done:

- Expected string in the response body. A check compares only the HTTP status code.
- Public status page by a link, without sign-in, limited to what the owner chose to show. A guest sees the URL list only.
- Delivery to a real mailbox. Nothing is sent over SMTP. The same start and end messages are stored on the Mailing page.
- Response time and the length of the current outage on the main status table. You can see that data on statistics page of that URL.

Not specified in task, but added on top:

- Username and password. Authorisation was optional.
- Local websites from menu option `3`.
- Response-time line chart: last 100 checks, timeouts off the line, breaks across an incident or a gap, scale from 0 to at least 1000 ms
- Sign-in session kept in the browser for one hour.
- One timeout is requested again and is not stored. The stored failure is the second timeout.
