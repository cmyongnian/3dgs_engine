from fastapi import APIRouter, HTTPException

from backend.app.schemas.task import TaskCreateRequest, TaskResponse
from backend.app.services.task_service import task_service

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


@router.post("/{task_id}/start", response_model=TaskResponse)
def start_task(task_id: str) -> TaskResponse:
    task = task_service.start_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("")
def list_tasks() -> dict:
    return {"items": [item.model_dump() for item in task_service.list_tasks()]}