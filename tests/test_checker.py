"""Integration and unit tests for checker module."""

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import unittest

from src.checker import check_http_target, check_target, check_tcp_port


class MockServerHandler(BaseHTTPRequestHandler):
    status_to_return = 200

    def do_GET(self):
        if self.path == "/down":
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bad Gateway Error")
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # Suppress log noise during tests
        pass


class TestChecker(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    async def test_check_http_success(self):
        url = f"http://127.0.0.1:{self.port}/"
        result = await check_http_target(url, timeout=3.0)
        self.assertTrue(result.is_up)
        self.assertEqual(result.status_code, 200)
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertIsNone(result.error_message)

    async def test_check_http_server_error_down(self):
        url = f"http://127.0.0.1:{self.port}/down"
        result = await check_http_target(url, timeout=3.0)
        self.assertFalse(result.is_up)
        self.assertEqual(result.status_code, 502)
        self.assertIn("502", result.error_message)

    async def test_check_http_connection_refused(self):
        # Pick an unused port
        unused_port = 54321
        url = f"http://127.0.0.1:{unused_port}/"
        result = await check_http_target(url, timeout=1.0)
        self.assertFalse(result.is_up)
        self.assertIsNone(result.status_code)
        self.assertIn("Koneksi Gagal", result.error_message)

    async def test_check_tcp_port(self):
        is_up, latency, err = await check_tcp_port("127.0.0.1", self.port, timeout=2.0)
        self.assertTrue(is_up)
        self.assertIsNone(err)

        is_up_fail, _, err_fail = await check_tcp_port("127.0.0.1", 54321, timeout=1.0)
        self.assertFalse(is_up_fail)
        self.assertIsNotNone(err_fail)


if __name__ == "__main__":
    unittest.main()
