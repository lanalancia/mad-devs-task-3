"""HTTP API for the poll list. The browser never opens the database."""

from __future__ import annotations

import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.auth import issue_token, read_token
from backend.db import DatabaseError, connect
from backend.entries import (
    EntryError,
    assign_group,
    authenticate,
    delete_entry,
    load_page,
    load_poll_target,
    require_entry_id,
    require_expected_code,
    require_interval,
    require_page,
    require_page_size,
    require_poll_status,
    require_saved_url,
    require_seconds,
    require_url,
    save_new_entry,
    update_entry,
)
from backend.groups import (
    GroupError,
    create_group,
    delete_email,
    delete_group,
    load_groups,
    require_email,
    require_email_id,
    require_group_id,
    require_group_name,
    require_paused,
    save_email,
    update_email,
    update_group,
)
from backend.poll_control import ALREADY_POLLING
from backend.stats import load_statistics, parse_day, require_window

ALREADY_EXISTS = "Can't create entry, already exists"


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int, jwt_secret: str, poll_control=None) -> None:
        self.address_family = socket.AF_INET6
        try:
            super().__init__(("::", port), ApiHandler)
        except OSError:
            self.address_family = socket.AF_INET
            super().__init__(("0.0.0.0", port), ApiHandler)
        self.jwt_secret = jwt_secret
        self.poll_control = poll_control

    def server_bind(self) -> None:
        if self.address_family == socket.AF_INET6:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


class ApiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_OPTIONS(self) -> None:
        self._send_json(204, {})

    def do_GET(self) -> None:
        path, query = _split(self.path)
        if path == "/api/stats":
            self._stats(query)
            return
        if path == "/api/groups":
            self._groups()
            return
        if path != "/api/entries":
            self._send_json(404, {"error": "Not found."})
            return
        try:
            page = require_page(_query_int(query, "page", 1))
            page_size = require_page_size(_query_int(query, "page_size", 10))
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        self._with_db(lambda connection: self._send_json(200, load_page(connection, page, page_size)))

    def do_POST(self) -> None:
        path, _query = _split(self.path)
        if path == "/api/login":
            self._login()
            return
        if path == "/api/entries/poll":
            self._poll_now()
            return
        if path == "/api/entries":
            self._create()
            return
        if path == "/api/entries/delete":
            self._delete()
            return
        if path == "/api/entries/group":
            self._assign_group()
            return
        if path == "/api/groups":
            self._create_group()
            return
        if path == "/api/groups/delete":
            self._delete_group()
            return
        if path == "/api/groups/emails":
            self._save_email()
            return
        if path == "/api/groups/emails/delete":
            self._delete_email()
            return
        self._send_json(404, {"error": "Not found."})

    def do_PATCH(self) -> None:
        path, _query = _split(self.path)
        if path == "/api/groups":
            self._update_group()
            return
        if path == "/api/groups/emails":
            self._update_email()
            return
        if path != "/api/entries":
            self._send_json(404, {"error": "Not found."})
            return
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            submitted = payload.get("url")
            url = require_url(submitted)
            interval_seconds = require_interval(payload.get("interval_seconds"))
            timeout_seconds = require_seconds(payload.get("timeout_seconds"), "Timeout")
            expected_code = require_expected_code(payload.get("expected_code"))
            status = require_poll_status(payload.get("status"))
            page = require_page(payload.get("page"))
            page_size = require_page_size(payload.get("page_size"))
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = update_entry(
                connection,
                url,
                interval_seconds,
                timeout_seconds,
                status,
                page,
                page_size,
                submitted if isinstance(submitted, str) else None,
                expected_code,
            )
            if updated is None:
                self._send_json(404, {"error": "Entry not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _stats(self, query: dict[str, list[str]]) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            entry_id = require_entry_id(_query_int(query, "id", 0))
            window = require_window(_query_text(query, "window", "day"))
            page = require_page(_query_int(query, "page", 1))
            page_size = require_page_size(_query_int(query, "page_size", 10))
            day_from = parse_day(_query_text(query, "from", ""))
            day_to = parse_day(_query_text(query, "to", ""))
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            payload = load_statistics(
                connection,
                entry_id,
                window,
                day_from,
                day_to,
                page,
                page_size,
            )
            if payload is None:
                self._send_json(404, {"error": "Entry not found."})
                return
            self._send_json(200, payload)

        self._with_db(run)

    def _login(self) -> None:
        try:
            payload = self._body()
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        username = payload.get("username")
        password = payload.get("password")

        def run(connection):
            found = authenticate(connection, username, password)
            if found is None:
                self._send_json(401, {"error": "Wrong username or password"})
                return
            token = issue_token(found, self.server.jwt_secret, now=int(time.time()))
            self._send_json(200, {"token": token, "username": found})

        self._with_db(run)

    def _create(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            url = require_url(payload.get("url"))
            interval_seconds = require_interval(payload.get("interval_seconds"))
            timeout_seconds = require_seconds(payload.get("timeout_seconds"), "Timeout")
            expected_code = require_expected_code(payload.get("expected_code"))
            page = require_page(payload.get("page"))
            page_size = require_page_size(payload.get("page_size"))
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            action, updated = save_new_entry(
                connection,
                url,
                interval_seconds,
                timeout_seconds,
                page,
                page_size,
                expected_code,
            )
            if action == "exists":
                self._send_json(409, {"error": ALREADY_EXISTS})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _delete(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            url = require_saved_url(payload.get("url"))
            page = require_page(payload.get("page"))
            page_size = require_page_size(payload.get("page_size"))
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = delete_entry(connection, url, page, page_size)
            if updated is None:
                self._send_json(404, {"error": "Entry not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _poll_now(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            entry_id = require_entry_id(payload.get("id"))
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        found: dict[str, dict] = {}

        def run(connection):
            entry = load_poll_target(connection, entry_id)
            if entry is None:
                self._send_json(404, {"error": "Entry not found."})
                return
            found["entry"] = entry

        self._with_db(run)
        entry = found.get("entry")
        if entry is None:
            return
        control = self.server.poll_control
        if control is None:
            self._send_json(500, {"error": "Polling is not running."})
            return
        try:
            finished = control.request_now(entry)
        except EntryError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        if finished is None:
            self._send_json(409, {"error": ALREADY_POLLING})
            return
        try:
            finished.result()
        except Exception as exc:
            print(f"Poll now failed for {entry['url']}: {exc}")
            self._send_json(500, {"error": "The poll did not finish."})
            return
        self._send_json(200, {"started": True})

    def _groups(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        self._with_db(lambda connection: self._send_json(200, load_groups(connection)))

    def _create_group(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            name = require_group_name(payload.get("name"))
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            self._send_json(200, create_group(connection, name))

        self._with_db(run)

    def _update_group(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            group_id = require_group_id(payload.get("id"))
            name = require_group_name(payload["name"]) if "name" in payload else None
            paused = require_paused(payload["paused"]) if "paused" in payload else None
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = update_group(connection, group_id, name, paused)
            if updated is None:
                self._send_json(404, {"error": "Group not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _delete_group(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            group_id = require_group_id(payload.get("id"))
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = delete_group(connection, group_id)
            if updated is None:
                self._send_json(404, {"error": "Group not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _save_email(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            group_id = require_group_id(payload.get("group_id"))
            address = require_email(payload.get("address"))
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = save_email(connection, group_id, address)
            if updated is None:
                self._send_json(404, {"error": "Group not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _update_email(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            email_id = require_email_id(payload.get("id"))
            address = require_email(payload.get("address"))
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = update_email(connection, email_id, address)
            if updated is None:
                self._send_json(404, {"error": "Email not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _delete_email(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            email_id = require_email_id(payload.get("id"))
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = delete_email(connection, email_id)
            if updated is None:
                self._send_json(404, {"error": "Email not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _assign_group(self) -> None:
        user, failure = self._user()
        if user is None:
            self._auth_error(failure)
            return
        try:
            payload = self._body()
            url = require_saved_url(payload.get("url"))
            if "group_id" not in payload:
                raise EntryError("Group id is required.")
            raw_group = payload.get("group_id")
            group_id = None if raw_group is None else require_group_id(raw_group)
            page = require_page(payload.get("page"))
            page_size = require_page_size(payload.get("page_size"))
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
            return

        def run(connection):
            updated = assign_group(connection, url, group_id, page, page_size)
            if updated is None:
                self._send_json(404, {"error": "Entry not found."})
                return
            self._send_json(200, updated)

        self._with_db(run)

    def _user(self) -> tuple[str | None, str]:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None, "unauthorized"
        state, username = read_token(
            header[7:].strip(),
            self.server.jwt_secret,
            now=int(time.time()),
        )
        if state == "ok":
            return username, ""
        if state == "expired":
            return None, "token_expired"
        return None, "unauthorized"

    def _auth_error(self, failure: str) -> None:
        if failure == "token_expired":
            self._send_json(401, {"error": "token_expired"})
            return
        self._send_json(401, {"error": "Sign in required."})

    def _body(self) -> dict:
        length_text = self.headers.get("Content-Length", "")
        try:
            length = int(length_text)
        except ValueError as exc:
            raise EntryError("Request body must be JSON.") from exc
        if length < 0 or length > 65536:
            raise EntryError("Request body must be JSON.")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EntryError("Request body must be JSON.") from exc
        if not isinstance(payload, dict):
            raise EntryError("Request body must be a JSON object.")
        return payload

    def _with_db(self, action) -> None:
        try:
            connection = connect()
        except DatabaseError as exc:
            print(f"HTTP request failed: {exc}")
            self._send_json(500, {"error": "No access to the database."})
            return
        try:
            action(connection)
        except (EntryError, GroupError) as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception as exc:
            print(f"HTTP request failed: {exc}")
            self._send_json(500, {"error": "Internal server error."})
        finally:
            connection.close()

    def _send_json(self, status: int, payload: dict) -> None:
        if status == 204:
            body = b""
        else:
            body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        if args and str(args[1]).startswith("2"):
            return
        print(f"HTTP {fmt % args}")


def _split(path: str) -> tuple[str, dict[str, list[str]]]:
    from urllib.parse import parse_qs, urlsplit

    parsed = urlsplit(path)
    return parsed.path, parse_qs(parsed.query)


def _query_text(query: dict[str, list[str]], name: str, default: str) -> str:
    values = query.get(name)
    if not values:
        return default
    return values[0]


def _query_int(query: dict[str, list[str]], name: str, default: int) -> object:
    values = query.get(name)
    if not values:
        return default
    text = values[0]
    if text.isdigit():
        return int(text)
    return text
