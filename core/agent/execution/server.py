"""Execution WebSocket Server — exposes ExecutionEngine to external clients.

Runs on localhost:9100. Accepts JSON messages.
Connects to DialogMesh cognitive pipeline through agent_native.

Clients (Python/TS/Rust) connect → send execute/list_tools/status → receive results.
"""

from __future__ import annotations
import asyncio
import json
import logging
import struct
import hashlib
import base64

logger = logging.getLogger(__name__)


class ExecutionServer:
    """Lightweight WebSocket server for ExecutionEngine.

    No external deps — pure Python asyncio WebSocket implementation.
    """

    def __init__(self, engine=None, host: str = "127.0.0.1", port: int = 9100):
        self._host = host
        self._port = port
        self._server = None

        from core.agent.execution.engine import ExecutionEngine, ExecutionBridge
        self._engine = engine or ExecutionEngine()
        self._bridge = ExecutionBridge(self._engine)

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_client, self._host, self._port
        )
        logger.info("Execution WebSocket server: ws://%s:%d", self._host, self._port)

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Execution server stopped")

    async def _handle_client(self, reader, writer):
        """Handle one WebSocket client connection."""
        peer = writer.get_extra_info('peername')
        logger.debug("Client connected: %s", peer)
        try:
            # WebSocket handshake
            request = await reader.readuntil(b'\r\n\r\n')
            if not self._do_handshake(request, writer):
                writer.close()
                return

            # Message loop
            buffer = b""
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                buffer += data
                while len(buffer) >= 2:
                    opcode = buffer[0] & 0x0F
                    if opcode == 0x8:  # close
                        writer.close()
                        return
                    if opcode == 0x9:  # ping
                        writer.write(b'\x8a\x00')
                        await writer.drain()
                        buffer = buffer[2:]
                        continue
                    if opcode == 0x1:  # text
                        frame = self._parse_frame(buffer)
                        if frame is None:
                            break  # incomplete frame
                        buffer = buffer[frame:]
                        msg = await self._bridge.handle_message(frame.decode('utf-8'))
                        await self._send_text(writer, msg)
                    else:
                        buffer = buffer[1:]  # skip unknown
        except Exception as e:
            logger.debug("Client error: %s", e)
        finally:
            writer.close()

    def _do_handshake(self, request: bytes, writer) -> bool:
        """Minimal WebSocket handshake (RFC 6455)."""
        try:
            headers = request.decode('utf-8', errors='ignore')
            key = None
            for line in headers.split('\r\n'):
                if line.lower().startswith('sec-websocket-key:'):
                    key = line.split(':', 1)[1].strip()
            if not key:
                return False

            accept = base64.b64encode(
                hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()
            ).decode()

            response = (
                'HTTP/1.1 101 Switching Protocols\r\n'
                'Upgrade: websocket\r\n'
                'Connection: Upgrade\r\n'
                f'Sec-WebSocket-Accept: {accept}\r\n'
                '\r\n'
            )
            writer.write(response.encode())
            return True
        except Exception:
            return False

    def _parse_frame(self, buffer: bytes):
        """Parse one WebSocket text frame. Returns payload length or None."""
        if len(buffer) < 2:
            return None
        masked = bool(buffer[1] & 0x80)
        length = buffer[1] & 0x7F
        pos = 2
        if length == 126:
            if len(buffer) < 4: return None
            length = struct.unpack('>H', buffer[2:4])[0]
            pos = 4
        elif length == 127:
            if len(buffer) < 10: return None
            length = struct.unpack('>Q', buffer[2:10])[0]
            pos = 10
        if masked:
            if len(buffer) < pos + 4: return None
            pos += 4
        if len(buffer) < pos + length:
            return None
        payload = buffer[pos:pos + length]
        if masked:
            mask = buffer[pos - 4:pos]
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return pos + length  # return bytes consumed

    async def _send_text(self, writer, text: str):
        """Send a WebSocket text frame."""
        payload = text.encode('utf-8')
        length = len(payload)
        header = bytes([0x81])  # FIN + text opcode
        if length < 126:
            header += bytes([length])
        elif length < 65536:
            header += bytes([126]) + struct.pack('>H', length)
        else:
            header += bytes([127]) + struct.pack('>Q', length)
        writer.write(header + payload)
        await writer.drain()

    @property
    def url(self) -> str:
        return f"ws://{self._host}:{self._port}"


async def start_execution_server(port: int = 9100):
    """Convenience — start the execution WebSocket server."""
    server = ExecutionServer(port=port)
    await server.start()
    return server
