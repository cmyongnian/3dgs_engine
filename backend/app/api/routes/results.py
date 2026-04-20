from fastapi import APIRouter, HTTPException

from backend.app.services.task_service import task_service

router = APIRouter()


@router.get("/{task_id}")
def get_result(task_id: str) -> dict:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": task.task_id,
        "status": task.status,
        "scene_name": task.scene_name,
        "result": task.result,
        "error": task.error,
    }
