import json
import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts updates to all connected clients."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        # Buffer recent events by type so new clients get caught up
        self._recent: dict[str, deque] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected (total: %d)", len(self._connections))

    async def replay(self, websocket: WebSocket) -> None:
        """Send buffered recent events to a client (called when client is ready)."""
        for event_type, items in self._recent.items():
            for data in items:
                try:
                    await websocket.send_text(json.dumps({"type": event_type, "data": data}))
                except Exception:
                    return

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.remove(websocket)
        logger.info("WebSocket client disconnected (total: %d)", len(self._connections))

    async def broadcast(self, event_type: str, data: Any, buffer: bool = False) -> None:
        """Broadcast a message to all connected clients.

        If buffer=True, the event is stored so new clients receive it on connect.
        """
        if buffer:
            if event_type not in self._recent:
                self._recent[event_type] = deque(maxlen=50)
            self._recent[event_type].append(data)

        message = json.dumps({"type": event_type, "data": data})
        disconnected = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._connections.remove(ws)


# Singleton manager
manager = ConnectionManager()


@router.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif data == "replay":
                await manager.replay(websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
