from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class TaskRecord:
    task_id: str
    scene_name: str
    payload: dict[str, Any]
    status: str = "created"
    current_stage: str = "未开始"
    message: str = "任务已创建"
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class TaskStore:
    def __init__(self) -> None:
        self._items: dict[str, TaskRecord] = {}
        self._lock = Lock()

    def add(self, task: TaskRecord) -> None:
        with self._lock:
            self._items[task.task_id] = task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._items.get(task_id)

    def list(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._items.values())

    def update(self, task_id: str, **kwargs: Any) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None
            for key, value in kwargs.items():
                setattr(task, key, value)
            return task

    def append_log(self, task_id: str, line: str) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None
            task.logs.append(line)
            return task


task_store = TaskStore()
