from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Union

import yaml

from backend.app.schemas.task import (
    TaskActionResponse,
    TaskCreateRequest,
    TaskResponse,
)
from backend.app.services.pipeline_service import pipeline_service
from backend.app.state.task_store import TaskRecord, task_store
from engine.core.process_utils import process_registry


class TaskService:
    """任务服务。

    删除逻辑说明：
    1. 正在运行、排队、停止中、重试中的任务不允许直接删除。
    2. 删除任务时先清理该任务独立目录下的文件，再删除任务记录。
    3. 只清理路径中包含 task_id 且位于安全根目录下的文件/目录。
       这样可以避免误删原始数据目录、共享场景目录或项目根目录。
    """

    ACTIVE_STATUSES = {"running", "queued", "stopping", "retrying"}

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.engine_root = self.project_root / "engine"
        self.runtime_root = self.project_root / "backend" / "runtime"

    def create_task(self, payload: TaskCreateRequest) -> TaskResponse:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(
            task_id=task_id,
            scene_name=payload.scene.scene_name,
            payload={"model": payload},
        )
        task_store.add(record)
        return self._to_response(record)

    def create_and_start_task(self, payload: TaskCreateRequest) -> Optional[TaskResponse]:
        created = self.create_task(payload)
        return self.start_task(created.task_id)

    def start_task(self, task_id: str) -> Optional[TaskResponse]:
        record = task_store.get(task_id)
        if record is None:
            return None

        if record.status in {"running", "queued", "stopping"}:
            return self._to_response(record)

        task_store.update(
            task_id,
            status="queued",
            current_stage="等待启动",
            message="任务已进入执行队列",
            error=None,
        )

        worker = threading.Thread(
            target=pipeline_service.run_task,
            args=(task_id,),
            daemon=True,
        )
        worker.start()

        updated = task_store.get(task_id)
        return self._to_response(updated) if updated else None

    def stop_task(self, task_id: str) -> Optional[TaskActionResponse]:
        record = task_store.get(task_id)
        if record is None:
            return None

        if record.status in {"success", "failed", "stopped"}:
            return TaskActionResponse(
                ok=True,
                task_id=record.task_id,
                action="stop",
                status=record.status,
                message="任务当前状态无需停止",
            )

        task_store.request_stop(task_id)
        task_store.update(
            task_id,
            status="stopping",
            message="已请求停止，当前阶段结束后将终止任务",
        )

        updated = task_store.get(task_id)
        if updated is None:
            return None

        return TaskActionResponse(
            ok=True,
            task_id=updated.task_id,
            action="stop",
            status=updated.status,
            message=updated.message,
        )

    def force_stop_task(self, task_id: str) -> Optional[TaskActionResponse]:
        record = task_store.get(task_id)
        if record is None:
            return None

        if record.status in {"success", "failed", "stopped"}:
            return TaskActionResponse(
                ok=True,
                task_id=record.task_id,
                action="force_stop",
                status=record.status,
                message="任务当前状态无需立即停止",
            )

        task_store.request_force_stop(task_id)
        terminated_count = process_registry.request_force_stop(task_id)

        if terminated_count > 0:
            message = "已请求立即停止，正在终止当前子进程"
        else:
            message = "已请求立即停止；当前没有可终止的外部子进程，将在最近检查点停止"

        task_store.append_log(task_id, message)
        task_store.update(
            task_id,
            status="stopping",
            message=message,
        )

        updated = task_store.get(task_id)
        if updated is None:
            return None

        return TaskActionResponse(
            ok=True,
            task_id=updated.task_id,
            action="force_stop",
            status=updated.status,
            message=updated.message,
        )

    def retry_task(self, task_id: str) -> Optional[TaskActionResponse]:
        record = task_store.get(task_id)
        if record is None:
            return None

        if record.status not in {"failed", "stopped", "partial_success"}:
            return TaskActionResponse(
                ok=False,
                task_id=record.task_id,
                action="retry",
                status=record.status,
                message="当前状态不允许重试",
            )

        reset = task_store.reset_for_retry(task_id)
        if reset is None:
            return None

        task_store.update(
            task_id,
            status="queued",
            current_stage="等待重试",
            message="任务已重新进入执行队列",
        )

        worker = threading.Thread(
            target=pipeline_service.run_task,
            args=(task_id,),
            daemon=True,
        )
        worker.start()

        updated = task_store.get(task_id)
        if updated is None:
            return None

        return TaskActionResponse(
            ok=True,
            task_id=updated.task_id,
            action="retry",
            status=updated.status,
            message=updated.message,
        )

    def delete_task(self, task_id: str) -> Optional[TaskActionResponse]:
        record = task_store.get(task_id)
        if record is None:
            return None

        if record.status in self.ACTIVE_STATUSES:
            return TaskActionResponse(
                ok=False,
                task_id=record.task_id,
                action="delete",
                status=record.status,
                message="任务正在执行，不能删除。请先停止任务，等待状态变为已停止/失败/完成后再删除。",
            )

        cleanup = self._cleanup_task_artifacts(record)
        deleted = task_store.delete(task_id)
        process_registry.clear_task(task_id)

        if deleted is None:
            return None

        removed_count = len(cleanup["removed"])
        skipped_count = len(cleanup["skipped"])
        error_count = len(cleanup["errors"])

        message = f"任务记录已删除；已清理 {removed_count} 个任务文件/目录"
        if skipped_count:
            message += f"，跳过 {skipped_count} 个非任务隔离路径"
        if error_count:
            message += f"，{error_count} 个路径清理失败"

        return TaskActionResponse(
            ok=True,
            task_id=deleted.task_id,
            action="delete",
            status=deleted.status,
            message=message,
        )

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        record = task_store.get(task_id)
        return self._to_response(record) if record else None

    def get_task_logs(self, task_id: str) -> Optional[List[str]]:
        if hasattr(task_store, "get_logs"):
            return task_store.get_logs(task_id)

        record = task_store.get(task_id)
        if record is None:
            return None
        return list(record.logs)

    def list_tasks(self) -> List[TaskResponse]:
        return [self._to_response(item) for item in task_store.list() if item is not None]

    # ---------- 删除文件辅助逻辑 ----------

    def _safe_read_yaml(self, path: Path) -> Dict[str, Any]:
        if not path.exists() or not path.is_file():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _safe_roots(self) -> List[Path]:
        roots = [
            self.runtime_root,
            self.runtime_root / "task_logs",
            self.engine_root / "outputs",
            self.engine_root / "datasets" / "processed",
            self.engine_root / "logs",
            self.project_root / "outputs",
            self.project_root / "datasets" / "processed",
            self.project_root / "logs",
        ]

        safe_roots: List[Path] = []
        for root in roots:
            try:
                safe_roots.append(root.resolve())
            except OSError:
                # Windows 下遇到非法路径时不要让删除接口崩溃。
                continue
        return safe_roots

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _looks_like_path(value: str) -> bool:
        if not value:
            return False
        return (
            "/" in value
            or "\\" in value
            or ":" in value
            or value.endswith((".yaml", ".yml", ".json", ".txt", ".log", ".png", ".jpg", ".jpeg"))
        )

    @staticmethod
    def _is_scalar_path_value(value: Any) -> bool:
        # 删除路径只允许来自字符串/Path。不要把 dict/list 直接转成字符串，
        # 否则 Windows 会把 "{'project_root': ...}" 当成非法路径并抛 WinError 123。
        return isinstance(value, (str, Path))

    @staticmethod
    def _safe_resolve(path: Path) -> Optional[Path]:
        try:
            return path.resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    def _resolve_candidate_paths(self, value: Any) -> List[Path]:
        if value is None or not self._is_scalar_path_value(value):
            return []

        text = str(value).strip().strip('"').strip("'")
        if not text or not self._looks_like_path(text):
            return []

        # 明确过滤 Python 字典/列表被错误转成字符串后的形态。
        if text.startswith("{") or text.startswith("[") or text.startswith("("):
            return []

        try:
            raw = Path(text)
        except (OSError, RuntimeError, ValueError):
            return []

        candidate_inputs: List[Path]
        if raw.is_absolute():
            candidate_inputs = [raw]
        else:
            candidate_inputs = [self.engine_root / raw, self.project_root / raw]

        unique: List[Path] = []
        seen: Set[str] = set()
        for item in candidate_inputs:
            resolved = self._safe_resolve(item)
            if resolved is None:
                continue
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                unique.append(resolved)
        return unique

    def _collect_path_values(self, obj: Any) -> Iterable[Any]:
        path_key_words = (
            "path",
            "dir",
            "file",
            "root",
            "output",
            "workspace",
            "database",
            "log",
            "model",
            "source",
        )

        if isinstance(obj, dict):
            for key, value in obj.items():
                key_text = str(key).lower()
                if any(word in key_text for word in path_key_words) and self._is_scalar_path_value(value):
                    yield value
                # value 是 dict/list 时只递归读取内部字段，绝不把整个容器当路径。
                if isinstance(value, (dict, list, tuple)):
                    yield from self._collect_path_values(value)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                if self._is_scalar_path_value(item):
                    yield item
                else:
                    yield from self._collect_path_values(item)

    def _is_safe_task_path(self, path: Path, task_id: str) -> bool:
        resolved = self._safe_resolve(path)
        if resolved is None:
            return False

        has_task_id = task_id in resolved.parts or task_id in resolved.name
        if not has_task_id:
            return False

        return any(self._is_relative_to(resolved, root) for root in self._safe_roots())

    def _collect_cleanup_paths(self, record: TaskRecord) -> List[Path]:
        task_id = record.task_id
        candidates: Set[Path] = set()

        runtime_dir_raw = Path(record.runtime_dir) if record.runtime_dir else (self.runtime_root / task_id)
        runtime_dir = self._safe_resolve(runtime_dir_raw) or (self.runtime_root / task_id)
        log_path = self._safe_resolve(self.runtime_root / "task_logs" / f"{task_id}.log")
        candidates.add(runtime_dir)
        if log_path is not None:
            candidates.add(log_path)

        # 从运行时配置中读取实际输出目录。先收集，最后再删除 runtime_dir。
        if runtime_dir.exists():
            for config_file in runtime_dir.glob("*.yaml"):
                data = self._safe_read_yaml(config_file)
                for value in self._collect_path_values(data):
                    for path in self._resolve_candidate_paths(value):
                        candidates.add(path)

        # 从任务内存/持久化记录中补充结果文件路径。
        for source in (record.result, record.result_files, record.metrics_summary):
            for value in self._collect_path_values(source):
                for path in self._resolve_candidate_paths(value):
                    candidates.add(path)

        # 只保留安全路径。父目录优先删除，子目录自然会被覆盖清理。
        safe_paths = [path for path in candidates if self._is_safe_task_path(path, task_id)]
        return sorted(set(safe_paths), key=lambda item: len(item.parts))

    def _cleanup_task_artifacts(self, record: TaskRecord) -> Dict[str, List[str]]:
        removed: List[str] = []
        skipped: List[str] = []
        errors: List[str] = []

        for path in self._collect_cleanup_paths(record):
            if not self._is_safe_task_path(path, record.task_id):
                skipped.append(str(path))
                continue

            if not path.exists():
                skipped.append(str(path))
                continue

            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                removed.append(str(path))
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        return {"removed": removed, "skipped": skipped, "errors": errors}

    @staticmethod
    def _to_response(record: Optional[TaskRecord]) -> Optional[TaskResponse]:
        if record is None:
            return None

        return TaskResponse(
            task_id=record.task_id,
            scene_name=record.scene_name,
            status=record.status,
            current_stage=record.current_stage,
            message=record.message,
            result=record.result,
            error=record.error,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            stop_requested=record.stop_requested,
            force_stop_requested=record.force_stop_requested,
            retry_count=record.retry_count,
            stage_history=record.stage_history,
            metrics_summary=record.metrics_summary,
            result_files=record.result_files,
        )


task_service = TaskService()
