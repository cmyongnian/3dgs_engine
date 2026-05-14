from fastapi import APIRouter, HTTPException

from backend.app.schemas.task import (
    TaskActionResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskLogResponse,
    ColmapReuseListResponse,
)
from backend.app.services.task_service import task_service
from backend.app.services.colmap_reuse_service import colmap_reuse_service

router = APIRouter()


@router.post("", response_model=TaskResponse)
def create_task(payload: TaskCreateRequest) -> TaskResponse:
    return task_service.create_task(payload)


@router.post("/run", response_model=TaskResponse)
def create_and_start_task(payload: TaskCreateRequest) -> TaskResponse:
    task = task_service.create_and_start_task(payload)
    if task is None:
        raise HTTPException(status_code=500, detail="任务创建后启动失败")
    return task


@router.get("/colmap-reuse", response_model=ColmapReuseListResponse)
def list_colmap_reuse_options(scene_name: str) -> ColmapReuseListResponse:
    items = colmap_reuse_service.list_options(scene_name)
    return ColmapReuseListResponse(scene_name=scene_name, items=items, count=len(items))


@router.post("/{task_id}/start", response_model=TaskResponse)
def start_task(task_id: str) -> TaskResponse:
    task = task_service.start_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/{task_id}/stop", response_model=TaskActionResponse)
def stop_task(task_id: str) -> TaskActionResponse:
    action = task_service.stop_task(task_id)
    if action is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return action


@router.post("/{task_id}/force-stop", response_model=TaskActionResponse)
def force_stop_task(task_id: str) -> TaskActionResponse:
    action = task_service.force_stop_task(task_id)
    if action is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return action


@router.post("/{task_id}/retry", response_model=TaskActionResponse)
def retry_task(task_id: str) -> TaskActionResponse:
    action = task_service.retry_task(task_id)
    if action is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return action


@router.delete("/{task_id}", response_model=TaskActionResponse)
def delete_task(task_id: str) -> TaskActionResponse:
    action = task_service.delete_task(task_id)
    if action is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return action


@router.get("/{task_id}/logs", response_model=TaskLogResponse)
def get_task_logs(task_id: str) -> TaskLogResponse:
    lines = task_service.get_task_logs(task_id)
    if lines is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskLogResponse(task_id=task_id, lines=lines, count=len(lines))


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("")
def list_tasks() -> dict:
    return {"items": [item.model_dump() for item in task_service.list_tasks()]}