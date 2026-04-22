from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
    started_at: str | None = None
    finished_at: str | None = None

    stop_requested: bool = False
    retry_count: int = 0

    stage_history: list[dict[str, Any]] = field(default_factory=list)
    runtime_dir: str | None = None
    result_files: dict[str, Any] = field(default_factory=dict)
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    last_error_type: str | None = None


class TaskStore:
    def __init__(self) -> None:
        self._items: dict[str, TaskRecord] = {}
        self._lock = Lock()

    def add(self, task: TaskRecord) -> None:
        with self._lock:
            task.updated_at = _utc_now_iso()
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

            task.updated_at = _utc_now_iso()
            return task

    def append_log(self, task_id: str, line: str) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.logs.append(line)
            task.updated_at = _utc_now_iso()
            return task

    def request_stop(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.stop_requested = True
            task.updated_at = _utc_now_iso()
            return task

    def reset_for_retry(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.status = "retrying"
            task.current_stage = "准备重试"
            task.message = "任务准备重新执行"
            task.logs.clear()
            task.result.clear()
            task.error = None
            task.finished_at = None
            task.started_at = None
            task.stop_requested = False
            task.stage_history.clear()
            task.result_files.clear()
            task.metrics_summary.clear()
            task.last_error_type = None
            task.retry_count += 1
            task.updated_at = _utc_now_iso()
            return task

    def delete(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._items.pop(task_id, None)

    def mark_started(self, task_id: str, stage: str | None = None) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            now = _utc_now_iso()
            task.status = "running"
            task.started_at = task.started_at or now
            task.updated_at = now
            if stage is not None:
                task.current_stage = stage
            return task

    def mark_finished(
        self,
        task_id: str,
        *,
        status: str,
        message: str,
        error: str | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            now = _utc_now_iso()
            task.status = status
            task.message = message
            task.error = error
            task.finished_at = now
            task.updated_at = now
            return task

    def push_stage(self, task_id: str, stage_record: dict[str, Any]) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.stage_history.append(stage_record)
            task.updated_at = _utc_now_iso()
            return task

    def start_stage(
        self,
        task_id: str,
        *,
        stage_key: str,
        stage_label: str,
        order: int,
    ) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            now = _utc_now_iso()
            record = {
                "stage_key": stage_key,
                "stage_label": stage_label,
                "order": order,
                "status": "running",
                "started_at": now,
                "finished_at": None,
                "duration_seconds": None,
                "error_type": None,
                "error_message": None,
            }
            task.stage_history.append(record)
            task.current_stage = stage_label
            task.updated_at = now
            return task

    def finish_stage(
        self,
        task_id: str,
        *,
        stage_key: str,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            now_dt = datetime.now(timezone.utc)
            now = now_dt.isoformat()

            for stage in reversed(task.stage_history):
                if stage.get("stage_key") != stage_key:
                    continue
                if stage.get("finished_at") is not None:
                    continue

                stage["status"] = status
                stage["finished_at"] = now
                stage["error_type"] = error_type
                stage["error_message"] = error_message

                started_at = stage.get("started_at")
                if started_at:
                    try:
                        started_dt = datetime.fromisoformat(started_at)
                        duration = (now_dt - started_dt).total_seconds()
                        stage["duration_seconds"] = round(duration, 3)
                    except ValueError:
                        stage["duration_seconds"] = None
                break

            task.updated_at = now
            return task

    def update_result_files(
        self, task_id: str, result_files: dict[str, Any]
    ) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.result_files = dict(result_files)
            task.updated_at = _utc_now_iso()
            return task

    def update_metrics_summary(
        self, task_id: str, metrics_summary: dict[str, Any]
    ) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.metrics_summary = dict(metrics_summary)
            task.updated_at = _utc_now_iso()
            return task


task_store = TaskStore()