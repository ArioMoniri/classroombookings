"""A small local SMTP sink for the W3-MAIL tests (port 2721, the lane's port): EHLO, STARTTLS (self-signed
certificate for ``localhost``), AUTH PLAIN / LOGIN / XOAUTH2, MAIL / RCPT / DATA, RSET, NOOP, QUIT. It stores every
accepted message so a test can read the MIME parts the server received."""

from __future__ import annotations

import base64
import datetime as dt
import socket
import socketserver
import ssl
import threading
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.message import EmailMessage
from pathlib import Path

PORT = 2721


def make_cert(folder: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = folder / "sink.pem", folder / "sink.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_path, key_path


@dataclass
class Received:
    mail_from: str
    rcpts: list[str]
    data: bytes

    @property
    def message(self) -> EmailMessage:
        return message_from_bytes(self.data, policy=policy.default)  # type: ignore[return-value]


@dataclass
class Sink:
    user: str = "bildirim@uni.edu.tr"
    password: str = "smtp-gizli"
    bearer: str | None = None
    tls: ssl.SSLContext | None = None
    reject_rcpt: set[str] = field(default_factory=set)
    messages: list[Received] = field(default_factory=list)
    auth_seen: list[str] = field(default_factory=list)
    server: socketserver.ThreadingTCPServer | None = None

    def start(self) -> Sink:
        sink = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                sock: socket.socket = self.request
                sock.settimeout(10)
                f = sock.makefile("rb")
                secured = False
                authed = False

                def send(line: str) -> None:
                    sock.sendall(line.encode() + b"\r\n")

                def read() -> str:
                    raw = f.readline()
                    if not raw:
                        raise ConnectionError
                    return raw.decode("utf-8", "replace").rstrip("\r\n")

                send("220 sink.local ESMTP W3-MAIL test sink")
                mail_from, rcpts = "", []
                try:
                    while True:
                        line = read()
                        cmd = line.split(" ", 1)[0].upper()
                        arg = line[len(cmd) :].strip()
                        if cmd in ("EHLO", "HELO"):
                            caps = ["sink.local", "8BITMIME", "SMTPUTF8", "AUTH PLAIN LOGIN XOAUTH2"]
                            if sink.tls is not None and not secured:
                                caps.append("STARTTLS")
                            for c in caps[:-1]:
                                send(f"250-{c}")
                            send(f"250 {caps[-1]}")
                        elif cmd == "STARTTLS" and sink.tls is not None:
                            send("220 2.0.0 Ready to start TLS")
                            sock = sink.tls.wrap_socket(sock, server_side=True)
                            f = sock.makefile("rb")
                            secured = True
                        elif cmd == "AUTH":
                            parts = arg.split(" ", 1)
                            mech = parts[0].upper()
                            sink.auth_seen.append(mech)
                            if mech == "PLAIN":
                                blob = parts[1] if len(parts) > 1 else (send("334 ") or read())
                                _z, u, p = base64.b64decode(blob).decode().split("\x00")
                                authed = (u, p) == (sink.user, sink.password)
                            elif mech == "LOGIN":
                                send("334 VXNlcm5hbWU6")
                                u = base64.b64decode(read()).decode()
                                send("334 UGFzc3dvcmQ6")
                                p = base64.b64decode(read()).decode()
                                authed = (u, p) == (sink.user, sink.password)
                            elif mech == "XOAUTH2":
                                blob = base64.b64decode(parts[1]).decode()
                                authed = sink.bearer is not None and f"auth=Bearer {sink.bearer}\x01" in blob
                                if not authed:
                                    send("334 " + base64.b64encode(b'{"status":"401"}').decode())
                                    read()
                            send("235 2.7.0 Authentication successful" if authed else "535 5.7.8 Authentication failed")
                        elif cmd == "MAIL":
                            mail_from, rcpts = arg.split(":", 1)[1].strip().split(" ")[0].strip("<>"), []
                            send("250 2.1.0 OK")
                        elif cmd == "RCPT":
                            addr = arg.split(":", 1)[1].strip().strip("<>")
                            if addr in sink.reject_rcpt:
                                send("550 5.1.1 No such user")
                            else:
                                rcpts.append(addr)
                                send("250 2.1.5 OK")
                        elif cmd == "DATA":
                            send("354 End data with <CR><LF>.<CR><LF>")
                            chunks = []
                            while True:
                                raw = f.readline()
                                if raw in (b".\r\n", b".\n", b""):
                                    break
                                chunks.append(raw[1:] if raw.startswith(b"..") else raw)
                            sink.messages.append(Received(mail_from, rcpts, b"".join(chunks)))
                            send("250 2.0.0 Queued as W3MAIL")
                        elif cmd in ("RSET", "NOOP"):
                            send("250 2.0.0 OK")
                        elif cmd == "QUIT":
                            send("221 2.0.0 Bye")
                            return
                        else:
                            send("502 5.5.2 Command not recognised")
                except (ConnectionError, OSError, ssl.SSLError, ValueError):
                    return

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
