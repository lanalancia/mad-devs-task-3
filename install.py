"""Step-by-step project setup.

New questions are added as a method on the Installer class and a line in Installer.steps.
"""

from __future__ import annotations

import configparser
import io
import json
import subprocess
import time
from pathlib import Path

from backend.urls import UrlError, normalize_url

POSTGRES_IMAGE = "postgres:17"
CONTAINER_NAME = "mad-devs-postgres"
VOLUME_NAME = "mad-devs-postgres"

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.ini"
SCHEMA_PATH = ROOT / "backend" / "schema.sql"
POLL_ENTRIES_PATH = ROOT / "init-poll-entries.json"
USERS_PATH = ROOT / "init-users.json"
APPLICATION_TABLES = ("poll_entries", "poll_history", "users")

DEFAULTS = {
    "host": "localhost",
    "port": "5432",
    "database": "postgres",
    "user": "postgres",
    "password": "",
}


def ask_yes_no(question: str) -> bool:
    while True:
        try:
            answer = input(f"{question} [yes/no]: ").strip().lower()
        except EOFError:
            print()
            return False
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Enter yes or no.")


def ask_text(question: str, default: str | None = None) -> str:
    hint = f" [{default}]" if default else ""
    while True:
        try:
            answer = input(f"{question}{hint}: ").strip()
        except EOFError:
            print()
            answer = ""
        if answer:
            return answer
        if default is not None:
            return default
        print("Value cannot be empty.")


def ask_port(default: str) -> str:
    while True:
        value = ask_text("Port", default)
        if value.isdigit() and 1 <= int(value) <= 65535:
            return value
        print("Port must be a number from 1 to 65535.")


def ask_password(prompt: str) -> str:
    import getpass

    try:
        return getpass.getpass(prompt)
    except EOFError:
        print()
        return ""


def load_config() -> dict[str, str]:
    values = dict(DEFAULTS)
    parser = configparser.ConfigParser(interpolation=None)
    if CONFIG_PATH.exists():
        parser.read(CONFIG_PATH, encoding="utf-8")
    if parser.has_section("postgresql"):
        for key in values:
            if parser.has_option("postgresql", key):
                values[key] = parser.get("postgresql", key)
    return values


def save_config(values: dict[str, str]) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    if CONFIG_PATH.exists():
        parser.read(CONFIG_PATH, encoding="utf-8")
    parser["postgresql"] = {key: values[key] for key in DEFAULTS}
    buffer = io.StringIO()
    parser.write(buffer)
    header = (
        "# Application connection to PostgreSQL.\n"
        "# install.py writes either the local Docker container "
        "or an existing database here.\n"
        "# The http section is the API port and JWT secret.\n\n"
    )
    CONFIG_PATH.write_text(header + buffer.getvalue(), encoding="utf-8")
    shown = (
        f"postgresql://{values['user']}@{values['host']}:"
        f"{values['port']}/{values['database']}"
    )
    print(f"Connection saved to {CONFIG_PATH.name}: {shown}")


def run_docker(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["docker", *args],
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError:
        return None


def docker_engine_ready() -> bool:
    completed = run_docker(["info"])
    if completed is None:
        print("Docker was not found.")
        print("Install Docker, start it, and run this step again.")
        return False
    if completed.returncode != 0:
        print("Docker is installed, but the engine is not running.")
        print("Start Docker and run this step again.")
        return False
    return True


def pull_image() -> bool:
    print(f"Downloading {POSTGRES_IMAGE}.")
    completed = run_docker(["pull", POSTGRES_IMAGE], capture=False)
    if completed is None or completed.returncode != 0:
        print(f"Failed to download {POSTGRES_IMAGE}.")
        return False
    return True


def container_inspect() -> dict | None:
    completed = run_docker(["inspect", CONTAINER_NAME])
    if completed is None or completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    if not payload:
        return None
    return payload[0]


def ask_docker_connection(current: dict[str, str]) -> dict[str, str]:
    values = dict(current)
    values["host"] = "localhost"
    values["port"] = ask_port(current["port"] or "5432")
    values["user"] = ask_text("User", current["user"] or "postgres")
    values["database"] = ask_text("Database", current["database"] or "postgres")
    while True:
        password = ask_password("Password: ")
        if password:
            values["password"] = password
            return values
        print("Password cannot be empty.")


def create_container(values: dict[str, str]) -> bool:
    print(f"Starting {CONTAINER_NAME} on localhost:{values['port']}.")
    completed = run_docker(
        [
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "--restart",
            "unless-stopped",
            "-e",
            f"POSTGRES_USER={values['user']}",
            "-e",
            f"POSTGRES_PASSWORD={values['password']}",
            "-e",
            f"POSTGRES_DB={values['database']}",
            "-p",
            f"{values['port']}:5432",
            "-v",
            f"{VOLUME_NAME}:/var/lib/postgresql/data",
            POSTGRES_IMAGE,
        ]
    )
    if completed is None or completed.returncode != 0:
        detail = ""
        if completed is not None:
            detail = (completed.stderr or completed.stdout or "").strip()
        print("Failed to start the container.")
        if detail:
            print(detail)
        return False
    return True


def start_container() -> bool:
    print(f"Starting existing container {CONTAINER_NAME}.")
    completed = run_docker(["start", CONTAINER_NAME])
    if completed is None or completed.returncode != 0:
        detail = ""
        if completed is not None:
            detail = (completed.stderr or completed.stdout or "").strip()
        print("Failed to start the container.")
        if detail:
            print(detail)
        return False
    return True


def connection_from_container(info: dict, current: dict[str, str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for item in info.get("Config", {}).get("Env") or []:
        key, separator, value = item.partition("=")
        if separator:
            env[key] = value
    bindings = (info.get("HostConfig", {}).get("PortBindings") or {}).get("5432/tcp") or []
    port = current["port"] or "5432"
    if bindings and bindings[0].get("HostPort"):
        port = bindings[0]["HostPort"]
    user = env.get("POSTGRES_USER") or current["user"] or "postgres"
    database = env.get("POSTGRES_DB") or user
    return {
        "host": "localhost",
        "port": port,
        "database": database,
        "user": user,
        "password": env.get("POSTGRES_PASSWORD", ""),
    }


def wait_until_ready(user: str) -> bool:
    print("Waiting until PostgreSQL accepts connections.")
    for _ in range(60):
        completed = run_docker(
            ["exec", CONTAINER_NAME, "pg_isready", "-U", user]
        )
        if completed is not None and completed.returncode == 0:
            return True
        time.sleep(1)
    return False


def psql(user: str, database: str, statement: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                CONTAINER_NAME,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                user,
                "-d",
                database,
                "-t",
                "-A",
            ],
            input=statement,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        return None


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def existing_application_tables(user: str, database: str) -> list[str] | None:
    names = ", ".join(sql_literal(name) for name in APPLICATION_TABLES)
    statement = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name IN "
        f"({names}) ORDER BY table_name;"
    )
    completed = psql(user, database, statement)
    if completed is None or completed.returncode != 0:
        detail = ""
        if completed is not None:
            detail = (completed.stderr or completed.stdout or "").strip()
        print("Failed to read application tables.")
        if detail:
            print(detail)
        return None
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def load_json_list(path: Path) -> list | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Failed to read {path.name}: {exc}")
        return None
    if not isinstance(payload, list):
        print(f"{path.name} must contain a list.")
        return None
    return payload


def require_positive_int(item: dict, key: str, url: str) -> int | None:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        print(f"{key} for {url} must be an integer of at least 1.")
        return None
    return value


def parse_poll_entry(item: object) -> tuple[str, int, int, int, str] | None:
    if not isinstance(item, dict):
        print("Each poll entry in init-poll-entries.json must be an object.")
        return None
    raw_url = item.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        print("A poll entry is missing a url.")
        return None
    try:
        url = normalize_url(raw_url)
    except UrlError as exc:
        print(f"{raw_url}: {exc}")
        return None
    status = item.get("polling_status")
    if status not in {"ACTIVE", "PAUSED"}:
        print(f"Polling status for {url} must be ACTIVE or PAUSED.")
        return None
    timeout = require_positive_int(item, "timeout", url)
    interval = require_positive_int(item, "polling_rate", url)
    expected = require_positive_int(item, "expected_code", url)
    if timeout is None or interval is None or expected is None:
        return None
    return url, timeout, interval, expected, status


def parse_user(item: object) -> tuple[str, str] | None:
    if not isinstance(item, dict):
        print("Each user in init-users.json must be an object.")
        return None
    username = item.get("username")
    password = item.get("password")
    if not isinstance(username, str) or not username:
        print("A user is missing a username.")
        return None
    if not isinstance(password, str):
        print(f"Password for {username} must be a string.")
        return None
    return username, password


def seed_statements() -> list[str] | None:
    entries = load_json_list(POLL_ENTRIES_PATH)
    users = load_json_list(USERS_PATH)
    if entries is None or users is None:
        return None
    statements: list[str] = []
    for item in entries:
        parsed = parse_poll_entry(item)
        if parsed is None:
            return None
        url, timeout, interval, expected, status = parsed
        statements.append(
            "INSERT INTO poll_entries "
            "(url, timeout_seconds, interval_seconds, expected_code, status) VALUES ("
            f"{sql_literal(url)}, {timeout}, {interval}, {expected}, {sql_literal(status)});"
        )
    for item in users:
        parsed_user = parse_user(item)
        if parsed_user is None:
            return None
        username, password = parsed_user
        statements.append(
            "INSERT INTO users (username, password) VALUES ("
            f"{sql_literal(username)}, {sql_literal(password)});"
        )
    return statements


def setup_application_database(user: str, database: str) -> bool:
    present = existing_application_tables(user, database)
    if present is None:
        return False
    dropping = ""
    if present:
        print("Application tables already exist: " + ", ".join(present) + ".")
        if not ask_yes_no(
            "Reinstall the database on this step? "
            "This deletes poll entries, history, and users, then loads the seed again"
        ):
            print("Existing tables left unchanged.")
            return True
        dropping = (
            "DROP TABLE IF EXISTS poll_entry_events, poll_history, poll_entries, users CASCADE;\n"
        )
    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Failed to read {SCHEMA_PATH.name}: {exc}")
        return False
    seed = seed_statements()
    if seed is None:
        return False
    print("Creating application tables and loading the seed.")
    statement = "BEGIN;\n" + dropping + schema + "\n" + "\n".join(seed) + "\nCOMMIT;\n"
    completed = psql(user, database, statement)
    if completed is None or completed.returncode != 0:
        detail = ""
        if completed is not None:
            detail = (completed.stderr or completed.stdout or "").strip()
        print("Failed to create application tables.")
        if detail:
            print(detail)
        return False
    print("Application tables are ready.")
    return True


def install_postgresql(current: dict[str, str]) -> None:
    if not docker_engine_ready():
        return
    if not pull_image():
        return
    info = container_inspect()
    if info is None:
        values = ask_docker_connection(current)
        if not create_container(values):
            return
    else:
        status = (info.get("State") or {}).get("Status") or "unknown"
        print(f"Container {CONTAINER_NAME} already exists ({status}).")
        if status != "running" and not start_container():
            return
        values = connection_from_container(info, current)
        while not values["password"]:
            values["password"] = ask_password("Password: ")
            if not values["password"]:
                print("Password cannot be empty.")
    if not wait_until_ready(values["user"]):
        print("The container is up, but PostgreSQL is not accepting connections yet.")
        if not ask_yes_no("Save the connection anyway"):
            return
        save_config(values)
        print("Password saved to config.ini. Do not commit this file with a real password.")
        print(f"PostgreSQL is running in Docker as {CONTAINER_NAME}.")
        print("Application tables were not created because PostgreSQL is not ready.")
        return
    save_config(values)
    print("Password saved to config.ini. Do not commit this file with a real password.")
    if not setup_application_database(values["user"], values["database"]):
        print(f"PostgreSQL is running in Docker as {CONTAINER_NAME}.")
        print("Application tables were not created.")
        return
    print(f"PostgreSQL is running in Docker as {CONTAINER_NAME}.")


def configure_existing_database(current: dict[str, str]) -> None:
    print("A local database runs on this computer. A remote one is at another address.")
    while True:
        try:
            kind = input("Is the database local or remote? [local/remote]: ").strip().lower()
        except EOFError:
            print()
            return
        if kind in {"local", "l"}:
            host = "localhost"
            break
        if kind in {"remote", "r"}:
            previous = current["host"] if current["host"] != "localhost" else None
            host = ask_text("Server address", previous)
            break
        print("Enter local or remote.")
    values = dict(current)
    values["host"] = host
    values["port"] = ask_port(current["port"] or "5432")
    values["database"] = ask_text("Database", current["database"] or "postgres")
    values["user"] = ask_text("User", current["user"] or "postgres")
    values["password"] = ask_password("Password: ")
    save_config(values)
    print("Existing database connection saved. Application tables were not created.")


class Installer:
    def steps(self):
        return [
            self.step_postgresql,
        ]

    def step_postgresql(self, number: int) -> None:
        print(f"\n{number}. PostgreSQL")
        current = load_config()
        print(
            "config.ini currently has "
            f"{current['host']}:{current['port']}."
        )
        if ask_yes_no(f"Download and start {POSTGRES_IMAGE} in Docker"):
            install_postgresql(current)
            return
        if ask_yes_no("Connect to an existing database (local or remote)"):
            configure_existing_database(current)
            return
        print("config.ini left unchanged: localhost, port 5432.")

    def run(self) -> None:
        print("Project setup. The following questions can be answered with yes or no.")
        for number, step in enumerate(self.steps(), start=1):
            step(number)
        print("\nDone.")


def main() -> None:
    Installer().run()


if __name__ == "__main__":
    main()
