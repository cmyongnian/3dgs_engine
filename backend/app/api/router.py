from fastapi import APIRouter

from backend.app.api.routes import results, system, tasks
from backend.app.ws.log_ws import router as log_ws_router

api_router = APIRouter()
api_router.include_router(system.router, prefix="/system", tags=["系统"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["任务"])
api_router.include_router(results.router, prefix="/results", tags=["结果"])
api_router.include_router(log_ws_router, prefix="/ws", tags=["日志"])
