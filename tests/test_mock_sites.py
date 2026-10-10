import socket
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from mock_sites import HOST, handler_for, response_for, serve

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ResponseTests(unittest.TestCase):
    def test_the_fixed_sites_do_not_depend_on_the_clock(self):
        moment = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(response_for("steady", moment), (200, 100))
        self.assertEqual(response_for("missing", moment), (404, 300))
        self.assertEqual(response_for("slow", moment), (200, 6000))

    def test_the_square_wave_follows_even_and_odd_10_minute_utc_pieces(self):
        self.assertEqual(response_for("square", EPOCH), (200, 100))
        self.assertEqual(response_for("square", EPOCH + timedelta(seconds=599)), (200, 100))
        self.assertEqual(response_for("square", EPOCH + timedelta(seconds=600)), (200, 900))
        self.assertEqual(response_for("square", EPOCH + timedelta(seconds=1199)), (200, 900))
        self.assertEqual(response_for("square", EPOCH + timedelta(seconds=1200)), (200, 100))


class ServerTests(unittest.TestCase):
    def test_a_taken_port_stops_startup(self):
        taken = socket.socket()
        taken.bind((HOST, 0))
        port = taken.getsockname()[1]
        try:
            with self.assertRaises(SystemExit):
                serve(((port, "steady"),))
        finally:
            taken.close()

    def test_the_handler_waits_before_it_answers(self):
        with patch("mock_sites.time.sleep") as sleep:
            server = ThreadingHTTPServer((HOST, 0), handler_for("slow"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            try:
                with urllib.request.urlopen(f"http://{HOST}:{port}/", timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), b"ok\n")
            finally:
                server.shutdown()
                server.server_close()
        sleep.assert_called_with(6.0)

    def test_the_missing_site_returns_404(self):
        with patch("mock_sites.time.sleep"):
            server = ThreadingHTTPServer((HOST, 0), handler_for("missing"))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            try:
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"http://{HOST}:{port}/", timeout=2)
            finally:
                server.shutdown()
                server.server_close()
        self.assertEqual(caught.exception.code, 404)
