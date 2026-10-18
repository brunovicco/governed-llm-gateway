from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from scripts.demo_pdp_https import LocalVerifiedHttpsProxy


def test_local_proxy_serves_router_over_certificate_verified_https() -> None:
    class UpstreamHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    proxy = LocalVerifiedHttpsProxy(upstream_port=upstream.server_port)
    try:
        with proxy:
            import http.client
            from urllib.parse import urlsplit

            parsed = urlsplit(proxy.endpoint)
            assert parsed.hostname is not None
            connection = http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=3)
            try:
                connection.request("GET", "/health")
                response = connection.getresponse()
                assert response.status == 200
                assert response.read() == b"ok"
            finally:
                connection.close()
    finally:
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=3)
