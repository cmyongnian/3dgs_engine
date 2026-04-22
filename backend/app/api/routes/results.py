from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.app.services.task_service import task_service

router = APIRouter()


@router.get("/{task_id}")
def get_result(task_id: str) -> Dict[str, Any]:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    result = task.result or {}
    metrics_summary = task.metrics_summary or {}
    result_files = task.result_files or {}

    return {
        "task_id": task.task_id,
        "scene_name": task.scene_name,
        "status": task.status,
        "current_stage": task.current_stage,
        "message": task.message,
        "error": task.error,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "stop_requested": task.stop_requested,
        "retry_count": task.retry_count,
        "stage_history": [item.model_dump() for item in task.stage_history],
        "metrics_summary": metrics_summary,
        "result_files": result_files,
        "result": result,
    }