"""Trusted loopback HTTPS bridge for the local Policy Router demonstration."""

import http.client
import ipaddress
import os
import ssl
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import NameOID

_MAX_BODY = 512 * 1024


def _issue_loopback_certificates(directory: Path) -> tuple[Path, Path, Path]:
    """Create an ephemeral local CA and a localhost server certificate signed by it."""
    now = datetime.now(UTC)
    ca_key = ed25519.Ed25519PrivateKey.generate()
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Gateway demo local CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, algorithm=None)
    )
    server_key = ed25519.Ed25519PrivateKey.generate()
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(ca_key, algorithm=None)
    )
    ca_path = directory / "demo-ca.pem"
    cert_path = directory / "gateway-demo.pem"
    key_path = directory / "gateway-demo-key.pem"
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ca_path, cert_path, key_path


class LocalVerifiedHttpsProxy:
    """Expose a loopback Router HTTP port over trusted local HTTPS for Gateway transport."""

    def __init__(self, *, upstream_host: str = "127.0.0.1", upstream_port: int = 8001) -> None:
        self._upstream_host = upstream_host
        self._upstream_port = upstream_port
        self._directory = tempfile.TemporaryDirectory(prefix="gateway-demo-tls-")
        directory = Path(self._directory.name)
        ca_path, cert_path, key_path = _issue_loopback_certificates(directory)
        self.ca_path = ca_path
        self._server = self._make_server(cert_path, key_path)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._previous_ssl_cert_file = os.environ.get("SSL_CERT_FILE")

    def _make_server(self, cert_path: Path, key_path: Path) -> ThreadingHTTPServer:
        upstream_host = self._upstream_host
        upstream_port = self._upstream_port

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                del format, args

            def _proxy(self) -> None:
                if self.path not in {"/health", "/route"}:
                    self.send_error(404)
                    return
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length < 0 or content_length > _MAX_BODY:
                    self.send_error(413)
                    return
                body = self.rfile.read(content_length)
                connection = http.client.HTTPConnection(upstream_host, upstream_port, timeout=5.0)
                try:
                    headers = {
                        key: value
                        for key, value in self.headers.items()
                        if key.lower() in {"content-type", "accept", "x-api-key"}
                    }
                    connection.request(self.command, self.path, body=body, headers=headers)
                    response = connection.getresponse()
                    payload = response.read(_MAX_BODY + 1)
                    if len(payload) > _MAX_BODY:
                        self.send_error(502)
                        return
                    self.send_response(response.status)
                    for key in ("Content-Type", "Retry-After"):
                        value = response.getheader(key)
                        if value is not None:
                            self.send_header(key, value)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (OSError, http.client.HTTPException):
                    self.send_error(502)
                finally:
                    connection.close()

            do_GET = _proxy
            do_POST = _proxy

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        return server

    @property
    def endpoint(self) -> str:
        """Return the verified HTTPS Router endpoint bound to an ephemeral port."""
        return f"https://127.0.0.1:{self._server.server_port}/route"

    def __enter__(self) -> "LocalVerifiedHttpsProxy":
        os.environ["SSL_CERT_FILE"] = str(self.ca_path)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5.0)
        if self._previous_ssl_cert_file is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = self._previous_ssl_cert_file
        self._directory.cleanup()
