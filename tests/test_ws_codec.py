"""Codec-level tests for the add-on's dependency-free WebSocket client."""

from __future__ import annotations

import socket
import struct

from blender_addon.transport.wsclient import WsClient


def _server_frame(opcode: int, payload: bytes) -> bytes:
    """Server->client frames are NOT masked."""
    b0 = 0x80 | opcode
    n = len(payload)
    if n < 126:
        return bytes([b0, n]) + payload
    if n < 65536:
        return bytes([b0, 126]) + struct.pack("!H", n) + payload
    return bytes([b0, 127]) + struct.pack("!Q", n) + payload


def _read_client_frame(sock: socket.socket):
    """Read one masked client frame and return (opcode, payload)."""
    b0, b1 = sock.recv(2)
    assert b1 & 0x80, "client frames must be masked"
    n = b1 & 0x7F
    if n == 126:
        n = struct.unpack("!H", sock.recv(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", sock.recv(8))[0]
    mask = sock.recv(4)
    payload = sock.recv(n)
    unmasked = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
    return b0 & 0x0F, unmasked


def test_send_text_is_masked_and_readable():
    a, b = socket.socketpair()
    ws = WsClient("127.0.0.1", 1)
    ws.sock = a
    ws.closed = False
    try:
        ws.send_text('{"type": "hello"}')
        opcode, payload = _read_client_frame(b)
        assert opcode == 0x1
        assert payload == b'{"type": "hello"}'
    finally:
        a.close()
        b.close()


def test_receives_unmasked_text_and_pong():
    a, b = socket.socketpair()
    received = []
    ws = WsClient("127.0.0.1", 1, on_text=lambda t: received.append(t))
    ws.sock = a
    ws.closed = False
    try:
        b.sendall(_server_frame(0x1, "tool_result".encode()))
        assert ws.pump_once(0.5) is True
        assert received == ["tool_result"]

        # server ping -> client must answer with a pong frame
        b.sendall(_server_frame(0x9, b"x"))
        assert ws.pump_once(0.5) is True
        opcode, payload = _read_client_frame(b)
        assert opcode == 0xA and payload == b"x"
    finally:
        a.close()
        b.close()


def test_large_frame_split_across_recv():
    import threading

    a, b = socket.socketpair()
    received = []
    ws = WsClient("127.0.0.1", 1, on_text=lambda t: received.append(t))
    ws.sock = a
    ws.closed = False
    try:
        big = ("x" * 70000).encode()
        frame = _server_frame(0x1, big)

        # socketpair buffers are small: send from a thread so the reader
        # (below) can drain concurrently, dribbling like a slow network
        def sender():
            i = 0
            while i < len(frame):
                b.sendall(frame[i:i + 997])
                i += 997
            b.close()

        t = threading.Thread(target=sender, daemon=True)
        t.start()
        assert ws.pump_once(2.0) is True
        assert received == ["x" * 70000]
        t.join(timeout=5)
    finally:
        a.close()
        b.close()


def test_fragmented_text_message():
    a, b = socket.socketpair()
    received = []
    ws = WsClient("127.0.0.1", 1, on_text=lambda t: received.append(t))
    ws.sock = a
    ws.closed = False
    try:
        # fin=0 text frame with "hel"
        b.sendall(bytes([0x01, 3]) + b"hel")
        assert ws.pump_once(0.5) is False  # partial frame, nothing delivered yet
        # fin=1 continuation with "lo"
        b.sendall(bytes([0x80, len(b"lo")]) + b"lo")
        assert ws.pump_once(0.5) is True
        assert received == ["hello"]
    finally:
        a.close()
        b.close()
