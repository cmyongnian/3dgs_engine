from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from backend.app.schemas.task import TaskCreateRequest


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
    force_stop_requested: bool = False
    retry_count: int = 0

    stage_history: list[dict[str, Any]] = field(default_factory=list)
    runtime_dir: str | None = None
    result_files: dict[str, Any] = field(default_factory=dict)
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    last_error_type: str | None = None


class TaskStore:
    """线程安全任务仓库。

    这一版在保留原有内存读写行为的基础上增加了两个能力：
    1. 任务元数据持久化到 backend/runtime/task_store/tasks.json。
    2. 每个任务的日志追加保存到 backend/runtime/task_logs/{task_id}.log。

    这样前端原有的任务查询、任务列表、历史日志接口都不需要改，
    后端重启后仍然能恢复已创建/已完成/失败/停止的任务记录与日志。
    """

    ACTIVE_STATUSES = {"running", "queued", "stopping", "retrying"}

    def __init__(self) -> None:
        self._items: dict[str, TaskRecord] = {}
        self._lock = Lock()

        self.project_root = Path(__file__).resolve().parents[3]
        self.runtime_root = self.project_root / "backend" / "runtime"
        self.store_root = self.runtime_root / "task_store"
        self.log_root = self.runtime_root / "task_logs"
        self.store_file = self.store_root / "tasks.json"

        self.store_root.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    # ---------- 持久化辅助方法 ----------

    def _log_path(self, task_id: str) -> Path:
        return self.log_root / f"{task_id}.log"

    def _payload_to_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = payload.get("model")
        if hasattr(model, "model_dump"):
            model = model.model_dump()
        elif hasattr(model, "dict"):
            model = model.dict()
        return {"model": model}

    def _payload_from_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = payload.get("model", payload)
        if isinstance(model, TaskCreateRequest):
            return {"model": model}
        if isinstance(model, dict):
            return {"model": TaskCreateRequest.model_validate(model)}
        raise TypeError("无法恢复任务配置 payload")

    def _record_to_json(self, task: TaskRecord) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "scene_name": task.scene_name,
            "payload": self._payload_to_json(task.payload),
            "status": task.status,
            "current_stage": task.current_stage,
            "message": task.message,
            "result": task.result,
            "error": task.error,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "stop_requested": task.stop_requested,
            "force_stop_requested": task.force_stop_requested,
            "retry_count": task.retry_count,
            "stage_history": task.stage_history,
            "runtime_dir": task.runtime_dir,
            "result_files": task.result_files,
            "metrics_summary": task.metrics_summary,
            "last_error_type": task.last_error_type,
            "log_file": str(self._log_path(task.task_id)),
        }

    def _read_log_file(self, task_id: str) -> list[str]:
        path = self._log_path(task_id)
        if not path.exists():
            return []
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []

    def _write_log_file(self, task_id: str, lines: list[str]) -> None:
        path = self._log_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not lines:
            path.write_text("", encoding="utf-8")
            return
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _append_log_file(self, task_id: str, line: str) -> None:
        path = self._log_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")

    def _record_from_json(self, data: dict[str, Any]) -> TaskRecord:
        task_id = str(data.get("task_id", ""))
        status = str(data.get("status", "created"))
        message = str(data.get("message", "任务已创建"))
        current_stage = str(data.get("current_stage", "未开始"))
        finished_at = data.get("finished_at")
        stop_requested = bool(data.get("stop_requested", False))
        force_stop_requested = bool(data.get("force_stop_requested", False))

        # 后端重启后，原先正在执行的线程已经不存在。
        # 为避免页面一直显示“运行中”，将这类任务恢复为“已停止”，用户可直接重试。
        if status in self.ACTIVE_STATUSES:
            status = "stopped"
            current_stage = "服务重启后任务中断"
            message = "服务重启后任务已中断，可点击重试重新执行"
            finished_at = finished_at or _utc_now_iso()
            stop_requested = False
            force_stop_requested = False

        task = TaskRecord(
            task_id=task_id,
            scene_name=str(data.get("scene_name", "")),
            payload=self._payload_from_json(data.get("payload", {})),
            status=status,
            current_stage=current_stage,
            message=message,
            logs=self._read_log_file(task_id),
            result=dict(data.get("result", {}) or {}),
            error=data.get("error"),
            created_at=str(data.get("created_at") or _utc_now_iso()),
            updated_at=str(data.get("updated_at") or _utc_now_iso()),
            started_at=data.get("started_at"),
            finished_at=finished_at,
            stop_requested=stop_requested,
            force_stop_requested=force_stop_requested,
            retry_count=int(data.get("retry_count", 0) or 0),
            stage_history=list(data.get("stage_history", []) or []),
            runtime_dir=data.get("runtime_dir"),
            result_files=dict(data.get("result_files", {}) or {}),
            metrics_summary=dict(data.get("metrics_summary", {}) or {}),
            last_error_type=data.get("last_error_type"),
        )
        return task

    def _load_from_disk(self) -> None:
        if not self.store_file.exists():
            return

        try:
            raw = json.loads(self.store_file.read_text(encoding="utf-8"))
        except Exception:
            return

        items = raw.get("items", []) if isinstance(raw, dict) else []
        changed = False
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                task = self._record_from_json(item)
            except Exception:
                continue
            if not task.task_id:
                continue
            if item.get("status") in self.ACTIVE_STATUSES:
                changed = True
            self._items[task.task_id] = task

        if changed:
            self._persist_locked()

    def _persist_locked(self) -> None:
        self.store_root.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "updated_at": _utc_now_iso(),
            "items": [self._record_to_json(task) for task in self._items.values()],
        }
        tmp_file = self.store_file.with_suffix(".json.tmp")
        tmp_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_file.replace(self.store_file)

    # ---------- 原有任务仓库接口 ----------

    def add(self, task: TaskRecord) -> None:
        with self._lock:
            task.updated_at = _utc_now_iso()
            self._items[task.task_id] = task
            self._persist_locked()

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._items.get(task_id)

    def list(self) -> list[TaskRecord]:
        with self._lock:
            return sorted(
                self._items.values(),
                key=lambda item: item.created_at or "",
                reverse=True,
            )

    def update(self, task_id: str, **kwargs: Any) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            for key, value in kwargs.items():
                setattr(task, key, value)

            task.updated_at = _utc_now_iso()
            self._persist_locked()
            return task

    def append_log(self, task_id: str, line: str) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            clean_line = line.rstrip("\n")
            task.logs.append(clean_line)
            task.updated_at = _utc_now_iso()
            self._append_log_file(task_id, clean_line)
            return task

    def get_logs(self, task_id: str) -> list[str] | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            file_lines = self._read_log_file(task_id)
            if file_lines:
                task.logs = file_lines
            return list(task.logs)

    def request_stop(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.stop_requested = True
            task.updated_at = _utc_now_iso()
            self._persist_locked()
            return task

    def request_force_stop(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.stop_requested = True
            task.force_stop_requested = True
            task.updated_at = _utc_now_iso()
            self._persist_locked()
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
            self._write_log_file(task_id, [])
            task.result.clear()
            task.error = None
            task.finished_at = None
            task.started_at = None
            task.stop_requested = False
            task.force_stop_requested = False
            task.stage_history.clear()
            task.result_files.clear()
            task.metrics_summary.clear()
            task.last_error_type = None
            task.retry_count += 1
            task.updated_at = _utc_now_iso()
            self._persist_locked()
            return task

    def delete(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            deleted = self._items.pop(task_id, None)
            if deleted is None:
                return None

            try:
                self._log_path(task_id).unlink(missing_ok=True)
            except Exception:
                pass
            self._persist_locked()
            return deleted

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
            self._persist_locked()
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
            self._persist_locked()
            return task

    def push_stage(self, task_id: str, stage_record: dict[str, Any]) -> TaskRecord | None:
        with self._lock:
            task = self._items.get(task_id)
            if task is None:
                return None

            task.stage_history.append(stage_record)
            task.updated_at = _utc_now_iso()
            self._persist_locked()
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
            self._persist_locked()
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
            self._persist_locked()
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
            self._persist_locked()
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
            self._persist_locked()
            return task


task_store = TaskStore()
