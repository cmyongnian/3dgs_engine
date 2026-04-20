from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class LogHub:
    def __init__(self) -> None:
        self.connections: DefaultDict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[task_id].append(websocket)

    def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        if task_id in self.connections and websocket in self.connections[task_id]:
            self.connections[task_id].remove(websocket)

    async def broadcast(self, task_id: str, message: str) -> None:
        for websocket in list(self.connections.get(task_id, [])):
            await websocket.send_text(message)


log_hub = LogHub()


@router.websocket("/logs/{task_id}")
async def logs_ws(websocket: WebSocket, task_id: str) -> None:
    await log_hub.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_hub.disconnect(task_id, websocket)
