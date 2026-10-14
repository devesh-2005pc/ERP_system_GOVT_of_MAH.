"""
Real-time event broadcasting over WebSockets.

Connections are tagged with the connecting user's department code (and
cross-department flag). Events are broadcast only to connections authorized
to see them: MANAGER/SUB_ADMIN receive everything; other departments only
receive events tagged with their own department (or explicitly public
events like LOW_STOCK visible to STORE + MANAGER/SUB_ADMIN).
"""
import asyncio
import json
from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass
class Connection:
    ws: WebSocket
    department_code: str
    cross_department: bool


class ConnectionManager:
    def __init__(self):
        self._connections: list[Connection] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, department_code: str, cross_department: bool):
        await ws.accept()
        async with self._lock:
            self._connections.append(Connection(ws, department_code, cross_department))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections = [c for c in self._connections if c.ws is not ws]

    async def broadcast(self, event_type: str, payload: dict, visible_to_departments: set[str] | None = None):
        """visible_to_departments=None means visible to all departments (rare —
        prefer explicit sets). MANAGER/SUB_ADMIN always receive every event."""
        message = json.dumps({"event": event_type, "data": payload})
        stale = []
        async with self._lock:
            targets = list(self._connections)
        for conn in targets:
            allowed = conn.cross_department or visible_to_departments is None or conn.department_code in visible_to_departments
            if not allowed:
                continue
            try:
                await conn.ws.send_text(message)
            except Exception:
                stale.append(conn)
        if stale:
            async with self._lock:
                self._connections = [c for c in self._connections if c not in stale]


manager = ConnectionManager()
