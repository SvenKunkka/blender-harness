"""Minimal RFC 6455 WebSocket *client* implemented on the Python standard
library (socket, ssl, base64, os, struct). Blender ships no websocket module,
so the add-on carries its own ~200 line client.

Supported: text frames (incl. fragmentation), protocol ping/pong, close, TLS.
Client frames are always masked per the spec.

Two read styles:
  * read_loop()    — blocking, meant for a dedicated socket thread
  * pump_once(t)   — non-blocking single-frame poll used by the bridge worker
"""

from __future__ import annotations

import base64
import os
import socket
import ssl
import struct
from typing import Callable, Optional


class WsError(Exception):
    pass


class WsClient:
    def __init__(self, host: str, port: int, path: str = "/", use_ssl: bool = False,
                 on_text: Optional[Callable[[str], None]] = None,
                 on_close: Optional[Callable[[Optional[str]], None]] = None,
                 origin: str = "blender-harness") -> None:
        self.host = host
        self.port = port
        self.path = path or "/"
        self.use_ssl = use_ssl
        self.on_text = on_text
        self.on_close = on_close
        self.origin = origin
        self.sock: Optional[socket.socket] = None
        self.closed = True
        self._frag = bytearray()
        self._frag_open = False

    # ------------------------------------------------------------- public
    def connect(self, timeout: float = 5.0) -> None:
        family = socket.AF_INET6 if ":" in self.host else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.host, self.port))
            if self.use_ssl:
                ctx = ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=self.host)
            self.sock = sock
            self._handshake()
            self.closed = False
            sock.settimeout(20.0)
        except Exception:
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass
            self.sock = None
            raise

    def close(self, code: int = 1000, reason: str = "") -> None:
        if self.sock is not None and not self.closed:
            try:
                self._send_frame(0x8, struct.pack("!H", code) + reason.encode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
        self._teardown()

    def _teardown(self) -> None:
        self.closed = True
        self._frag = bytearray()
        self._frag_open = False
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:  # noqa: BLE001
                pass
            self.sock = None

    def send_text(self, text: str) -> None:
        if self.closed or self.sock is None:
            raise WsError("socket closed")
        self._send_frame(0x1, text.encode("utf-8"))

    def send_pong(self, payload: bytes) -> None:
        if self.sock is not None and not self.closed:
            self._send_frame(0xA, payload)

    # ------------------------------------------------------------- reading
    def read_loop(self) -> None:
        """Blocking reader for a dedicated thread; returns when the socket dies."""
        try:
            while not self.closed:
                opcode, payload, fin = self._read_frame()
                self._handle_frame(opcode, payload, fin)
        except (WsError, OSError, ssl.SSLError):
            pass
        finally:
            if not self.closed:
                self._teardown()
            if self.on_close is not None:
                try:
                    self.on_close("closed")
                except Exception:  # noqa: BLE001
                    pass

    def pump_once(self, timeout: float = 0.25) -> bool:
        """Try to read and handle one frame. Returns True when any message was
        processed, False on socket timeout (caller should flush outbound).
        Raises WsError when the connection is gone."""
        if self.closed or self.sock is None:
            raise WsError("socket closed")
        self.sock.settimeout(timeout)
        try:
            opcode, payload, fin = self._read_frame()
        except socket.timeout:
            return False
        except (WsError, OSError, ssl.SSLError) as exc:
            self._teardown()
            raise WsError(str(exc)) from exc
        return self._handle_frame(opcode, payload, fin)

    def _handle_frame(self, opcode: int, payload: bytes, fin: bool) -> bool:
        if opcode == 0x8:  # close
            self._teardown()
            raise WsError("peer closed connection")
        if opcode == 0x9:  # ping -> pong
            try:
                self.send_pong(payload)
            except WsError:
                pass
            return True
        if opcode == 0xA:  # pong (protocol-level)
            return True
        if opcode == 0x2:  # binary (we never request binary)
            return False
        if opcode == 0x1:
            self._frag.extend(payload)
            self._frag_open = True
        elif opcode == 0x0 and self._frag_open:
            self._frag.extend(payload)
        else:
            return False
        if fin and self._frag_open:
            text = bytes(self._frag).decode("utf-8", "replace")
            self._frag = bytearray()
            self._frag_open = False
            if self.on_text is not None:
                self.on_text(text)
            return True
        return False

    # ------------------------------------------------------------- frames
    def _read_frame(self):
        hdr = self._recv_exact(2)
        b0, b1 = hdr[0], hdr[1]
        fin = (b0 & 0x80) != 0
        opcode = b0 & 0x0F
        masked = (b1 & 0x80) != 0
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload, fin

    def _recv_exact(self, n: int) -> bytes:
        if self.sock is None:
            raise WsError("no socket")
        chunks = bytearray()
        while len(chunks) < n:
            part = self.sock.recv(n - len(chunks))
            if not part:
                raise WsError("connection closed by peer")
            chunks.extend(part)
        return bytes(chunks)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.sock is None:
            raise WsError("no socket")
        header = bytearray([0x80 | opcode])  # fin set
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)  # masked bit set
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _handshake(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Origin: {self.origin}\r\n\r\n"
        )
        if self.sock is None:
            raise WsError("no socket")
        self.sock.sendall(req.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            part = self.sock.recv(4096)
            if not part:
                raise WsError("no handshake response")
            response += part
        head = response.split(b"\r\n\r\n", 1)[0].decode("ascii", "replace")
        lines = head.split("\r\n")
        if " 101 " not in (lines[0] if lines else ""):
            raise WsError(f"handshake failed: {lines[0] if lines else 'empty response'}")
