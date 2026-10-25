#!/usr/bin/env python3
"""Stdlib HTTP front-end for the NPPAD-Edge handler (EC2 fallback).

Adapts plain HTTP requests to Lambda Function-URL-style events and
calls lambda_function.handler, so the exact same code path (bundle
SHA-256 verification included) serves both deployment targets.
No third-party dependencies — Python standard library only.
"""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lambda_function import handler


class H(BaseHTTPRequestHandler):
    def _go(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        event = {"requestContext": {"http": {"method": method}},
                 "body": body, "isBase64Encoded": False}
        resp = handler(event)
        data = resp["body"].encode()
        self.send_response(resp["statusCode"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")

    def log_message(self, *args):  # keep the demo quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
