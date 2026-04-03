import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts updates to all connected clients."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected (total: %d)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.remove(websocket)
        logger.info("WebSocket client disconnected (total: %d)", len(self._connections))

    async def broadcast(self, event_type: str, data: Any) -> None:
        """Broadcast a message to all connected clients."""
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
    """WebSocket endpoint for real-time UI updates.

    Event types streamed to clients:
    - candle: new/updated candle data
    - tick: real-time price update
    - position: position opened/closed/updated
    - order: order status change
    - signal: new strategy signal
    - decision: decision made on a signal
    - news: new analyzed news event
    - account: account balance/P&L update
    - system: system events (connection status, reconciliation)
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, handle any client messages
            data = await websocket.receive_text()
            # Client can send ping or subscription messages
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
