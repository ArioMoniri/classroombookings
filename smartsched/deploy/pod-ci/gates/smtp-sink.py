"""SMTP sink for the browser e2e stack: accepts every message, delivers none, and lists them as JSON.

E2E stack only (pod CI gate e2e-real.sh runs it as the ``smtp`` container on the per-run network; run it
locally the same way). Standard library only (``smtpd`` is gone in Python 3.12), plain SMTP without TLS: the
specs set SMTP security ``none``, host ``smtp`` (``E2E_SMTP_HOST``), port 1025 (``E2E_SMTP_PORT``). STARTTLS
is not offered, so the default ``starttls`` setting fails loudly instead of sending in clear text. ``AUTH
PLAIN/LOGIN`` accepts any credentials; the user name is recorded, the password never.

    python smtp-sink.py [--host 0.0.0.0] [--smtp-port 1025] [--api-port 8025]

HTTP API (``E2E_SMTP_API``, e.g. http://smtp:8025):
    GET    /health     {"ok": true, "messages": N}
    GET    /messages   [{"id", "received_at", "from", "to", "auth_user", "subject", "text", "headers"}]
    DELETE /messages   {"deleted": N}
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import json
import threading
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MAX_MESSAGES = 500
MAX_BYTES = 10 * 1024 * 1024
NAME = "smartsched-e2e-smtp-sink"


class Mailbox:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[dict[str, Any]] = []
        self._next = 1

    def add(self, envelope_from: str, rcpts: list[str], data: bytes, auth_user: str | None) -> dict[str, Any]:
        msg = BytesParser(policy=policy.default).parsebytes(data)
        body = msg.get_body(preferencelist=("plain", "html")) if msg.is_multipart() else msg
        try:
            text = body.get_content() if body is not None else ""
        except (KeyError, LookupError):
            text = data.decode("utf-8", "replace")
        with self._lock:
            item = {
                "id": self._next, "received_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "from": envelope_from, "to": rcpts, "auth_user": auth_user,
                "subject": str(msg.get("Subject", "")), "text": text,
                "headers": {k: str(v) for k, v in msg.items()},
            }
            self._next += 1
            self._items.append(item)
            del self._items[:-MAX_MESSAGES]
        return item

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._items)

    def clear(self) -> int:
        with self._lock:
            n = len(self._items)
            self._items.clear()
            return n


def _addr(arg: str) -> str:
    """``FROM:<a@b> SIZE=1`` -> ``a@b``."""
    value = arg.split(":", 1)[1].strip() if ":" in arg else arg
    if value.startswith("<"):
        value = value[1 : value.find(">")] if ">" in value else value[1:]
    else:
        value = value.split()[0] if value.split() else ""
    return parseaddr(value)[1] or value


class Session:
    def __init__(self, box: Mailbox, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.box, self.reader, self.writer = box, reader, writer
        self.reset()
        self.auth_user: str | None = None

    def reset(self) -> None:
        self.mail_from: str | None = None
        self.rcpts: list[str] = []

    async def send(self, line: str) -> None:
        self.writer.write(line.encode() + b"\r\n")
        await self.writer.drain()

    async def readline(self) -> str | None:
        raw = await self.reader.readline()
        return raw.decode("utf-8", "replace").rstrip("\r\n") if raw else None

    async def auth(self, arg: str) -> None:
        parts = arg.split()
        mech = parts[0].upper() if parts else ""
        if mech == "PLAIN":
            token = parts[1] if len(parts) > 1 else None
            if token is None:
                await self.send("334 ")
                token = await self.readline() or ""
            try:
                fields = base64.b64decode(token, validate=True).split(b"\0")
            except (binascii.Error, ValueError):
                await self.send("501 5.5.2 cannot decode")
                return
            self.auth_user = (fields[1] if len(fields) > 1 else b"").decode("utf-8", "replace")
        elif mech == "LOGIN":
            if len(parts) > 1:
                user_b64 = parts[1]
            else:
                await self.send("334 VXNlcm5hbWU6")
                user_b64 = await self.readline() or ""
            await self.send("334 UGFzc3dvcmQ6")
            await self.readline()  # the password: read and dropped
            try:
                self.auth_user = base64.b64decode(user_b64).decode("utf-8", "replace")
            except (binascii.Error, ValueError):
                await self.send("501 5.5.2 cannot decode")
                return
        else:
            await self.send("504 5.5.4 unrecognized authentication type")
            return
        await self.send("235 2.7.0 authentication successful")

    async def data(self) -> None:
        if self.mail_from is None or not self.rcpts:
            await self.send("503 5.5.1 need MAIL and RCPT first")
            return
        await self.send("354 end data with <CR><LF>.<CR><LF>")
        lines: list[bytes] = []
        size = 0
        while True:
            raw = await self.reader.readline()
            if not raw:
                return
            if raw in (b".\r\n", b".\n"):
                break
            if raw.startswith(b".."):
                raw = raw[1:]  # RFC 5321 4.5.2 dot-unstuffing
            size += len(raw)
            if size <= MAX_BYTES:
                lines.append(raw)
        if size > MAX_BYTES:
            await self.send("552 5.3.4 message too big")
        else:
            item = self.box.add(self.mail_from, self.rcpts, b"".join(lines), self.auth_user)
            print(f"captured #{item['id']} {item['subject']!r} -> {', '.join(self.rcpts)}", flush=True)
            await self.send(f"250 2.0.0 queued as {item['id']}")
        self.reset()

    async def run(self) -> None:
        await self.send(f"220 {NAME} ESMTP")
        while (line := await self.readline()) is not None:
            verb, _, arg = line.partition(" ")
            verb = verb.upper()
            if verb == "EHLO":
                await self.send(f"250-{NAME}")
                await self.send(f"250-SIZE {MAX_BYTES}")
                await self.send("250-8BITMIME")
                await self.send("250 AUTH PLAIN LOGIN")
            elif verb == "HELO":
                await self.send(f"250 {NAME}")
            elif verb == "MAIL":
                self.reset()
                self.mail_from = _addr(arg)
                await self.send("250 2.1.0 ok")
            elif verb == "RCPT":
                if self.mail_from is None:
                    await self.send("503 5.5.1 need MAIL first")
                    continue
                self.rcpts.append(_addr(arg))
                await self.send("250 2.1.5 ok")
            elif verb == "DATA":
                await self.data()
            elif verb == "AUTH":
                await self.auth(arg)
            elif verb == "RSET":
                self.reset()
                await self.send("250 2.0.0 ok")
            elif verb in ("NOOP", "VRFY"):
                await self.send("250 2.0.0 ok")
            elif verb == "STARTTLS":
                await self.send("454 4.7.0 TLS not available")
            elif verb == "QUIT":
                await self.send("221 2.0.0 bye")
                break
            else:
                await self.send("502 5.5.2 command not recognized")


def api_handler(box: Mailbox) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            path = self.path.split("?", 1)[0].rstrip("/")
            if path == "/health":
                self._json(200, {"ok": True, "messages": len(box.list())})
            elif path == "/messages":
                self._json(200, box.list())
            else:
                self._json(404, {"detail": "not found"})

        def do_DELETE(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0].rstrip("/") == "/messages":
                self._json(200, {"deleted": box.clear()})
            else:
                self._json(404, {"detail": "not found"})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - quiet access log
            return

    return Handler


async def serve(host: str, smtp_port: int, api_port: int) -> None:
    box = Mailbox()
    httpd = ThreadingHTTPServer((host, api_port), api_handler(box))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await Session(box, reader, writer).run()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(on_client, host, smtp_port)
    print(f"{NAME}: SMTP on {host}:{smtp_port}, API on http://{host}:{api_port}", flush=True)
    async with server:
        await server.serve_forever()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 - reached by alias on the per-run network
    p.add_argument("--smtp-port", type=int, default=1025)
    p.add_argument("--api-port", type=int, default=8025)
    a = p.parse_args()
    try:
        asyncio.run(serve(a.host, a.smtp_port, a.api_port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
