from __future__ import annotations

import threading
import uuid
from typing import List, Optional

from backend.app.schemas.task import (
    TaskActionResponse,
    TaskCreateRequest,
    TaskResponse,
)
from backend.app.services.pipeline_service import pipeline_service
from backend.app.state.task_store import TaskRecord, task_store
from engine.core.process_utils import process_registry


class TaskService:
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

        if record.status in {"running", "queued", "stopping", "retrying"}:
            return TaskActionResponse(
                ok=False,
                task_id=record.task_id,
                action="delete",
                status=record.status,
                message="任务正在执行，不能删除",
            )

        deleted = task_store.delete(task_id)
        if deleted is None:
            return None

        return TaskActionResponse(
            ok=True,
            task_id=deleted.task_id,
            action="delete",
            status=deleted.status,
            message="任务记录已删除",
        )

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        record = task_store.get(task_id)
        return self._to_response(record) if record else None

    def get_task_logs(self, task_id: str) -> Optional[List[str]]:
        record = task_store.get(task_id)
        if record is None:
            return None
        return list(record.logs)

    def list_tasks(self) -> List[TaskResponse]:
        return [self._to_response(item) for item in task_store.list() if item is not None]

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