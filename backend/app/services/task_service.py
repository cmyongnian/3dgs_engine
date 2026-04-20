from __future__ import annotations

import threading
import uuid

from backend.app.schemas.task import TaskCreateRequest, TaskResponse
from backend.app.services.pipeline_service import pipeline_service
from backend.app.state.task_store import TaskRecord, task_store


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

    def start_task(self, task_id: str) -> TaskResponse | None:
        record = task_store.get(task_id)
        if record is None:
            return None
        if record.status == "running":
            return self._to_response(record)

        task_store.update(task_id, status="queued", current_stage="等待启动", message="任务已进入执行队列")
        worker = threading.Thread(target=pipeline_service.run_task, args=(task_id,), daemon=True)
        worker.start()
        updated = task_store.get(task_id)
        return self._to_response(updated) if updated else None

    def get_task(self, task_id: str) -> TaskResponse | None:
        record = task_store.get(task_id)
        return self._to_response(record) if record else None

    def list_tasks(self) -> list[TaskResponse]:
        return [self._to_response(item) for item in task_store.list()]

    @staticmethod
    def _to_response(record: TaskRecord | None) -> TaskResponse | None:
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
        )


task_service = TaskService()
